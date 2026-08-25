"""Tests for wtf.context — context building for LLM proposals."""

import os
import types
import unittest
from unittest.mock import patch, MagicMock

from wtf.context import build_context, _detect_git, _run_git


class TestBasicContext(unittest.TestCase):
    """Basic context construction from CLI args."""

    def _make_args(self, **kwargs):
        defaults = {
            "cwd": "/tmp/test",
            "shell": "bash",
            "buffer": "ls -la",
            "cursor": 5,
            "last_command": "echo hi",
            "last_exit_code": 0,
            "last_output": "",
            "git_root": None,
            "git_branch": None,
            "git_dirty": None,
        }
        defaults.update(kwargs)
        return types.SimpleNamespace(**defaults)

    def test_basic_fields(self):
        args = self._make_args()
        config = {"context": {"include_git": False}}
        ctx = build_context(args, config)

        self.assertEqual(ctx["version"], 1)
        self.assertEqual(ctx["shell"], "bash")
        self.assertEqual(ctx["cwd"], "/tmp/test")
        self.assertEqual(ctx["buffer"], "ls -la")
        self.assertEqual(ctx["cursor"], 5)
        self.assertEqual(ctx["last_command"], "echo hi")
        self.assertEqual(ctx["last_exit_code"], 0)

    def test_cwd_defaults_to_os_getcwd(self):
        args = self._make_args(cwd=None)
        config = {"context": {"include_git": False}}
        ctx = build_context(args, config)
        self.assertEqual(ctx["cwd"], os.getcwd())

    def test_explicit_git_args(self):
        args = self._make_args(
            git_root="/home/user/repo",
            git_branch="main",
            git_dirty=True,
        )
        config = {"context": {"include_git": True}}
        ctx = build_context(args, config)
        self.assertTrue(ctx["git"]["is_repo"])
        self.assertEqual(ctx["git"]["branch"], "main")
        self.assertTrue(ctx["git"]["dirty"])

    def test_git_disabled(self):
        args = self._make_args()
        config = {"context": {"include_git": False}}
        ctx = build_context(args, config)
        self.assertFalse(ctx["git"]["is_repo"])


class TestGitDetection(unittest.TestCase):
    """Git detection via subprocess (mocked)."""

    @patch("wtf.context.subprocess.run")
    def test_inside_git_repo(self, mock_run):
        """Simulate being inside a git repo."""
        # Three calls: rev-parse --show-toplevel, branch --show-current, status --porcelain
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/home/user/repo\n"),
            MagicMock(returncode=0, stdout="main\n"),
            MagicMock(returncode=0, stdout=""),
        ]
        result = _detect_git("/home/user/repo")
        self.assertTrue(result["is_repo"])
        self.assertEqual(result["branch"], "main")
        self.assertFalse(result["dirty"])

    @patch("wtf.context.subprocess.run")
    def test_dirty_repo(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/home/user/repo\n"),
            MagicMock(returncode=0, stdout="feature\n"),
            MagicMock(returncode=0, stdout=" M file.txt\n"),
        ]
        result = _detect_git("/home/user/repo")
        self.assertTrue(result["is_repo"])
        self.assertTrue(result["dirty"])

    @patch("wtf.context.subprocess.run")
    def test_not_a_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = _detect_git("/tmp")
        self.assertFalse(result["is_repo"])

    @patch("wtf.context.subprocess.run")
    def test_git_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        result = _detect_git("/tmp")
        self.assertFalse(result["is_repo"])

    @patch("wtf.context.subprocess.run")
    def test_git_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="git", timeout=5)
        result = _detect_git("/tmp")
        self.assertFalse(result["is_repo"])


class TestContextSerialization(unittest.TestCase):
    """Context dicts should be JSON-serializable."""

    def test_serializable(self):
        import json
        args = types.SimpleNamespace(
            cwd="/tmp",
            shell="zsh",
            buffer="echo test",
            cursor=9,
            last_command="pwd",
            last_exit_code=0,
            last_output="",
            git_root=None,
            git_branch=None,
            git_dirty=None,
        )
        config = {"context": {"include_git": False}}
        ctx = build_context(args, config)
        # Should not raise
        serialized = json.dumps(ctx)
        self.assertIsInstance(serialized, str)
        roundtrip = json.loads(serialized)
        self.assertEqual(roundtrip["buffer"], "echo test")


class TestLastOutputTruncation(unittest.TestCase):
    """Last output should be truncated to configured max."""

    def test_truncation(self):
        big_output = "x" * 10000
        args = types.SimpleNamespace(
            cwd="/tmp",
            shell="bash",
            buffer="",
            cursor=0,
            last_command="",
            last_exit_code=0,
            last_output=big_output,
            git_root=None,
            git_branch=None,
            git_dirty=None,
        )
        config = {
            "context": {
                "include_git": False,
                "max_last_output_bytes": 4096,
            }
        }
        ctx = build_context(args, config)
        self.assertLessEqual(
            len(ctx["last_output"].encode("utf-8")),
            4096,
        )


if __name__ == "__main__":
    unittest.main()
