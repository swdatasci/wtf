"""Deterministic post-model policy enforcement.

This module checks proposed commands against safety rules AFTER the model
generates them. It never executes anything -- it only inspects text.
"""

from __future__ import annotations

import re
import shlex
from typing import Any


# Commands considered safe (read-only). Each entry is matched as a token.
READ_ONLY_ALLOWLIST: frozenset[str] = frozenset({
    # filesystem inspection
    "ls", "cat", "head", "tail", "less", "more", "file", "stat", "wc",
    "du", "df", "tree", "bat", "exa", "eza",
    # search
    "grep", "rg", "ag", "find", "fd", "locate", "which", "whereis",
    "ripgrep", "fzf",
    # system info
    "free", "top", "htop", "ps", "uptime", "uname", "hostname",
    "whoami", "id", "date", "cal",
    # text processing (read-only)
    "echo", "printf", "env", "printenv", "sort", "uniq", "cut", "tr",
    "seq", "diff", "comm", "join", "paste", "column", "jq", "yq",
    # binary inspection
    "xxd", "hexdump", "od", "strings", "readelf", "objdump", "nm", "ldd",
    "strace", "ltrace",
    # network diagnostics (read-only)
    "dig", "nslookup", "host", "ping", "traceroute", "ss", "netstat",
    "ip", "ifconfig",
    # git read-only
    "git",
    # system services (read-only)
    "journalctl",
    "systemctl",
    # containers (read-only)
    "docker",
    "kubectl",
    # data plumbing (read-only)
    "xargs", "tee", "yes", "timeout", "time", "watch", "basename",
    "dirname", "realpath", "readlink", "rev", "tac", "nl", "expand",
    "unexpand", "fold", "fmt", "pr", "tsort", "shuf",
    # help / type
    "man", "help", "type", "command",
})

# Git subcommands that are read-only
_GIT_RO_SUBS = frozenset({
    "status", "log", "diff", "show", "branch", "tag", "remote", "stash",
})

# Docker subcommands that are read-only
_DOCKER_RO_SUBS = frozenset({"ps", "logs", "images"})

# Kubectl subcommands that are read-only
_KUBECTL_RO_SUBS = frozenset({"get", "describe", "logs"})

# Systemctl subcommands that are read-only
_SYSTEMCTL_RO_SUBS = frozenset({"status"})

# High-risk patterns matched as shell tokens
_HIGH_RISK_TOKENS: list[tuple[str, ...]] = [
    ("sudo",),
    ("rm",),
    ("dd",),
    ("mkfs",),
    ("shutdown",),
    ("reboot",),
    ("poweroff",),
    ("halt",),
    ("kill", "-9"),
    ("chmod", "-R"),
    ("chown", "-R"),
    ("git", "reset", "--hard"),
    ("git", "clean", "-f"),
]

# High-risk patterns matched as substrings (for hard-to-tokenize cases)
_HIGH_RISK_SUBSTRINGS: list[str] = [
    ":(){",        # fork bomb
    "curl|sh",     # pipe to shell
    "curl |sh",
    "curl | sh",
    "wget|sh",
    "wget |sh",
    "wget | sh",
    "curl|bash",
    "curl |bash",
    "curl | bash",
    "wget|bash",
    "wget |bash",
    "wget | bash",
]

# Remote execution patterns
_REMOTE_EXEC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bssh\s+\S+\s+."),      # ssh host command
    re.compile(r"\bkubectl\s+exec\b"),
    re.compile(r"\bansible\b"),
]

# Write redirects (medium risk)
_WRITE_REDIRECT_RE = re.compile(r"(?:>>?|(?<!\|)\btee\b)")


def _has_control_chars(text: str) -> bool:
    """Check for ASCII control characters (except normal whitespace)."""
    for ch in text:
        code = ord(ch)
        if code < 32 and ch not in ("\n", "\r", "\t", " "):
            return True
        if code == 127:  # DEL
            return True
    return False


def _token_sequence_in(tokens: list[str], pattern: tuple[str, ...]) -> bool:
    """Check if a token sequence appears consecutively in the token list."""
    plen = len(pattern)
    for i in range(len(tokens) - plen + 1):
        if tuple(tokens[i:i + plen]) == pattern:
            return True
    return False


def _is_read_only_pipeline(text: str) -> bool:
    """Check if all commands in a pipeline/chain are in the read-only allowlist."""
    # Split on pipes and command separators
    segments = re.split(r"\s*[|;]\s*|\s*&&\s*|\s*\|\|\s*", text.strip())

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            return False
        if not tokens:
            continue

        cmd = tokens[0]

        # Handle commands with significant subcommands
        if cmd == "git":
            if len(tokens) < 2 or tokens[1] not in _GIT_RO_SUBS:
                return False
        elif cmd == "docker":
            if len(tokens) < 2 or tokens[1] not in _DOCKER_RO_SUBS:
                return False
        elif cmd == "kubectl":
            if len(tokens) < 2 or tokens[1] not in _KUBECTL_RO_SUBS:
                return False
        elif cmd == "systemctl":
            if len(tokens) < 2 or tokens[1] not in _SYSTEMCTL_RO_SUBS:
                return False
        elif cmd == "curl":
            # curl is OK only without piping (already handled by pipeline check)
            # but reject if flags suggest non-GET
            for t in tokens[1:]:
                if t in ("-X", "--request", "-d", "--data", "--data-raw",
                          "--data-binary", "-F", "--form", "-T", "--upload-file"):
                    return False
        elif cmd == "wget":
            pass  # wget without pipe is fine; pipe checked at pipeline level
        elif cmd not in READ_ONLY_ALLOWLIST:
            return False

    return True


def check(
    buffer: str,
    *,
    max_buffer_bytes: int = 8192,
    allow_medium_risk_insert: bool = False,
    mode: str = "enforce",
) -> dict[str, Any]:
    """Check a proposed command buffer against policy rules.

    Returns a dict with:
        passed: bool
        action: "allow" | "refuse"
        risk: "low" | "medium" | "high"
        reason: str (explanation if refused)
        buffer: str (original buffer, always preserved)
    """
    if mode == "off":
        return {
            "passed": True,
            "action": "allow",
            "risk": "low",
            "reason": "",
            "buffer": buffer,
        }

    # Rule 1: Control characters
    if _has_control_chars(buffer):
        return _refuse(buffer, "high", "Buffer contains ASCII control characters")

    # Rule 2: Buffer length
    if len(buffer.encode("utf-8", errors="replace")) > max_buffer_bytes:
        return _refuse(
            buffer, "high",
            f"Buffer exceeds maximum length ({max_buffer_bytes} bytes)"
        )

    # Rule 3: Multiline
    stripped = buffer.strip()
    if "\n" in stripped:
        return _refuse(buffer, "high", "Multiline commands are not allowed")

    # Rule 4: High-risk substring patterns
    for pattern in _HIGH_RISK_SUBSTRINGS:
        if pattern in buffer:
            return _refuse(buffer, "high", f"High-risk pattern detected: {pattern}")

    # Rule 5: High-risk token patterns
    try:
        tokens = shlex.split(buffer)
    except ValueError:
        tokens = buffer.split()

    for pattern in _HIGH_RISK_TOKENS:
        if _token_sequence_in(tokens, pattern):
            label = " ".join(pattern)
            return _refuse(buffer, "high", f"High-risk command: {label}")

    # Rule 6: Remote execution
    for pat in _REMOTE_EXEC_PATTERNS:
        if pat.search(buffer):
            return _refuse(buffer, "high", f"Remote execution detected: {pat.pattern}")

    # Rule 7: Write redirects (medium risk)
    if _WRITE_REDIRECT_RE.search(buffer):
        if not allow_medium_risk_insert:
            return _refuse(
                buffer, "medium",
                "Write redirect detected (>, >>, tee). "
                "Set allow_medium_risk_insert to permit."
            )
        # Medium risk but allowed
        return {
            "passed": True,
            "action": "allow",
            "risk": "medium",
            "reason": "Write redirect allowed by policy",
            "buffer": buffer,
        }

    # Rule 8: Pipelines/separators -- all segments must be read-only
    if re.search(r"[|;]|&&|\|\|", buffer):
        if not _is_read_only_pipeline(buffer):
            return _refuse(
                buffer, "medium",
                "Pipeline contains commands not in the read-only allowlist"
            )

    return {
        "passed": True,
        "action": "allow",
        "risk": "low",
        "reason": "",
        "buffer": buffer,
    }


def _refuse(buffer: str, risk: str, reason: str) -> dict[str, Any]:
    return {
        "passed": False,
        "action": "refuse",
        "risk": risk,
        "reason": reason,
        "buffer": buffer,
    }
