"""Build the request context from CLI args and environment."""

from __future__ import annotations

import os
import subprocess
from typing import Any


def _run_git(*args: str, cwd: str | None = None) -> str | None:
    """Run a git command, return stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _detect_git(cwd: str | None = None) -> dict[str, Any]:
    """Auto-detect git info from the working directory."""
    root = _run_git("rev-parse", "--show-toplevel", cwd=cwd)
    if root is None:
        return {"is_repo": False, "root": None, "branch": None, "dirty": False}

    branch = _run_git("branch", "--show-current", cwd=cwd)
    porcelain = _run_git("status", "--porcelain=v1", "-uno", cwd=cwd)
    dirty = bool(porcelain)

    return {
        "is_repo": True,
        "root": root,
        "branch": branch or None,
        "dirty": dirty,
    }


def build_context(args: Any, config: dict[str, Any]) -> dict[str, Any]:
    """Build the context object from CLI args and auto-detection.

    Returns a dict conforming to context schema version 1.
    """
    cwd = getattr(args, "cwd", None) or os.getcwd()
    ctx_cfg = config.get("context", {})
    pol_cfg = config.get("policy", {})

    # Git info
    git_info: dict[str, Any]
    if ctx_cfg.get("include_git", True):
        git_root = getattr(args, "git_root", None)
        git_branch = getattr(args, "git_branch", None)
        git_dirty = getattr(args, "git_dirty", None)

        if git_root is not None:
            # Explicit git args provided
            git_info = {
                "is_repo": True,
                "root": git_root,
                "branch": git_branch,
                "dirty": bool(git_dirty),
            }
        else:
            git_info = _detect_git(cwd)
    else:
        git_info = {"is_repo": False, "root": None, "branch": None, "dirty": False}

    # Last output truncation
    last_output = getattr(args, "last_output", None) or ""
    max_output = ctx_cfg.get("max_last_output_bytes", 4096)
    if len(last_output.encode("utf-8", errors="replace")) > max_output:
        last_output = last_output.encode("utf-8", errors="replace")[:max_output].decode(
            "utf-8", errors="replace"
        )

    # Last exit code
    last_exit_code_raw = getattr(args, "last_exit_code", None)
    last_exit_code: int | None = None
    if last_exit_code_raw is not None:
        try:
            last_exit_code = int(last_exit_code_raw)
        except (ValueError, TypeError):
            pass

    context = {
        "version": 1,
        "shell": getattr(args, "shell", None) or os.environ.get("SHELL", "/bin/sh"),
        "cwd": cwd,
        "buffer": getattr(args, "buffer", None) or "",
        "cursor": getattr(args, "cursor", None),
        "last_command": getattr(args, "last_command", None) or "",
        "last_exit_code": last_exit_code,
        "last_output": last_output if ctx_cfg.get("include_last_output", True) else "",
        "git": git_info,
        "policy": {
            "mode": pol_cfg.get("mode", "enforce"),
            "cwd_scope_only": True,
            "allow_medium_risk_insert": pol_cfg.get("allow_medium_risk_insert", False),
        },
    }

    return context
