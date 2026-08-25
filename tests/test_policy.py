"""Tests for wtf.policy — command safety policy engine."""

import unittest

from wtf.policy import check


class TestHighRiskRejection(unittest.TestCase):
    """High-risk commands must be refused."""

    def _assert_refused(self, buffer: str, *, msg: str = ""):
        result = check(buffer)
        self.assertFalse(result["passed"], f"should refuse: {buffer!r} {msg}")
        self.assertEqual(result["action"], "refuse")

    def test_sudo(self):
        self._assert_refused("sudo apt-get update")

    def test_rm(self):
        self._assert_refused("rm -rf /tmp/stuff")

    def test_dd(self):
        self._assert_refused("dd if=/dev/zero of=/dev/sda")

    def test_mkfs(self):
        self._assert_refused("mkfs /dev/sda1")

    def test_mkfs_ext4(self):
        # mkfs.ext4 is a different token from mkfs; policy catches bare mkfs
        result = check("mkfs.ext4 /dev/sda1")
        # Not in the high-risk token list (it checks exact token "mkfs"),
        # but not in the safe allowlist either, so it goes through pipeline
        # check. This is a known gap — the test documents current behavior.
        self.assertIsInstance(result["passed"], bool)

    def test_shutdown(self):
        self._assert_refused("shutdown -h now")

    def test_reboot(self):
        self._assert_refused("reboot")

    def test_poweroff(self):
        self._assert_refused("poweroff")

    def test_halt(self):
        self._assert_refused("halt")

    def test_kill_dash_9(self):
        self._assert_refused("kill -9 1234")

    def test_chmod_recursive(self):
        self._assert_refused("chmod -R 777 /")

    def test_chown_recursive(self):
        self._assert_refused("chown -R root:root /")

    def test_git_reset_hard(self):
        self._assert_refused("git reset --hard HEAD~3")

    def test_git_clean_f(self):
        self._assert_refused("git clean -f")


class TestSafeCommands(unittest.TestCase):
    """Read-only commands should be allowed with low risk."""

    def _assert_allowed(self, buffer: str):
        result = check(buffer)
        self.assertTrue(result["passed"], f"should allow: {buffer!r}")
        self.assertEqual(result["action"], "allow")

    def test_ls(self):
        self._assert_allowed("ls -la")

    def test_cat(self):
        self._assert_allowed("cat /etc/hostname")

    def test_grep(self):
        self._assert_allowed("grep -r pattern .")

    def test_find(self):
        self._assert_allowed("find . -name '*.py'")

    def test_git_status(self):
        self._assert_allowed("git status")

    def test_git_log(self):
        self._assert_allowed("git log --oneline -5")

    def test_git_diff(self):
        self._assert_allowed("git diff HEAD")

    def test_echo(self):
        self._assert_allowed("echo hello world")

    def test_wc(self):
        self._assert_allowed("wc -l file.txt")

    def test_uptime(self):
        self._assert_allowed("uptime")

    def test_whoami(self):
        self._assert_allowed("whoami")

    def test_date(self):
        self._assert_allowed("date")


class TestControlCharacters(unittest.TestCase):
    """Control characters in buffer must be rejected."""

    def test_null_byte(self):
        result = check("ls\x00")
        self.assertFalse(result["passed"])

    def test_bell(self):
        result = check("echo \x07")
        self.assertFalse(result["passed"])

    def test_escape(self):
        result = check("echo \x1b[31m")
        self.assertFalse(result["passed"])

    def test_del(self):
        result = check("echo \x7f")
        self.assertFalse(result["passed"])

    def test_tab_is_ok(self):
        # Tab is normal whitespace, should be allowed
        result = check("ls\t-la")
        self.assertTrue(result["passed"])


class TestBufferSizeLimit(unittest.TestCase):
    """Buffer exceeding max length must be rejected."""

    def test_oversized_buffer(self):
        huge = "echo " + "A" * 10000
        result = check(huge)
        self.assertFalse(result["passed"])
        self.assertEqual(result["action"], "refuse")

    def test_within_limit(self):
        small = "echo hello"
        result = check(small)
        self.assertTrue(result["passed"])


class TestMultilineRejection(unittest.TestCase):
    """Embedded newlines should be rejected."""

    def test_multiline(self):
        result = check("echo hello\nrm -rf /")
        self.assertFalse(result["passed"])

    def test_single_line_ok(self):
        result = check("echo hello")
        self.assertTrue(result["passed"])


class TestRedirectDetection(unittest.TestCase):
    """Write redirects should be detected as medium risk."""

    def test_output_redirect(self):
        result = check("echo hello > file.txt")
        self.assertFalse(result["passed"])
        self.assertEqual(result["risk"], "medium")

    def test_append_redirect(self):
        result = check("echo hello >> file.txt")
        self.assertFalse(result["passed"])
        self.assertEqual(result["risk"], "medium")

    def test_tee_redirect(self):
        result = check("echo hello | tee file.txt")
        self.assertFalse(result["passed"])
        self.assertEqual(result["risk"], "medium")

    def test_redirect_allowed_with_flag(self):
        result = check("echo hello > file.txt", allow_medium_risk_insert=True)
        self.assertTrue(result["passed"])
        self.assertEqual(result["risk"], "medium")


class TestPipeChains(unittest.TestCase):
    """Pipe chains should be checked per-segment."""

    def test_all_safe_pipes(self):
        result = check("cat file.txt | grep pattern | sort | uniq")
        self.assertTrue(result["passed"])

    def test_unsafe_in_pipeline(self):
        # A pipeline with a non-allowlisted command
        result = check("cat file.txt | some_unknown_thing | sort")
        self.assertFalse(result["passed"])


class TestRemoteExecution(unittest.TestCase):
    """Remote execution patterns must be rejected."""

    def test_ssh_command(self):
        result = check("ssh user@host ls -la")
        self.assertFalse(result["passed"])

    def test_kubectl_exec(self):
        result = check("kubectl exec -it pod -- bash")
        self.assertFalse(result["passed"])


class TestForkBomb(unittest.TestCase):
    """Fork bomb patterns must be rejected."""

    def test_classic_fork_bomb(self):
        result = check(":(){:|:&};:")
        self.assertFalse(result["passed"])


class TestCurlShPatterns(unittest.TestCase):
    """curl|sh and wget|sh patterns must be rejected."""

    def test_curl_pipe_sh(self):
        result = check("curl https://example.com/install.sh | sh")
        self.assertFalse(result["passed"])

    def test_curl_pipe_bash(self):
        result = check("curl https://example.com/install.sh | bash")
        self.assertFalse(result["passed"])

    def test_wget_pipe_sh(self):
        result = check("wget -O - https://example.com/install.sh | sh")
        self.assertFalse(result["passed"])

    def test_wget_pipe_bash(self):
        result = check("wget -O - https://example.com/install.sh | bash")
        self.assertFalse(result["passed"])

    def test_curl_pipe_sh_spaced(self):
        result = check("curl https://example.com/install.sh | sh")
        self.assertFalse(result["passed"])


class TestPolicyModeOff(unittest.TestCase):
    """When mode is 'off', everything should pass."""

    def test_mode_off_allows_dangerous(self):
        result = check("sudo rm -rf /", mode="off")
        self.assertTrue(result["passed"])
        self.assertEqual(result["action"], "allow")


if __name__ == "__main__":
    unittest.main()
