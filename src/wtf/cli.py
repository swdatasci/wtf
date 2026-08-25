"""CLI entry point for wtf — What's The Function?

Subcommands:
    propose     Propose a command line replacement (outputs JSON to stdout)
    doctor      Check system readiness
    config show Print resolved configuration as TOML
    policy check -- COMMAND   Run policy checker on a command
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from wtf import __version__
from wtf.config import config_to_toml, load_config
from wtf.context import build_context
from wtf.ollama import chat, check_health, list_models
from wtf.policy import check as policy_check
from wtf.prompt import build_messages
from wtf.protocol import parse_response


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wtf",
        description="What's The Function? — local-first AI shell line editor",
    )
    parser.add_argument("--version", action="version", version=f"wtf {__version__}")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- propose ---
    propose = sub.add_parser("propose", help="Propose a command line replacement")
    propose.add_argument("--shell", type=str, default=None,
                         help="Current shell (e.g. /bin/bash)")
    propose.add_argument("--cwd", type=str, default=None,
                         help="Current working directory")
    propose.add_argument("--buffer", type=str, default="",
                         help="Current line buffer contents")
    propose.add_argument("--cursor", type=int, default=None,
                         help="Cursor position in the buffer")
    propose.add_argument("--last-command", type=str, default=None,
                         help="Previous command")
    propose.add_argument("--last-exit-code", type=int, default=None,
                         help="Exit code of the previous command")
    propose.add_argument("--last-output", type=str, default=None,
                         help="Output of the previous command")
    propose.add_argument("--git-root", type=str, default=None,
                         help="Git repository root (auto-detected if omitted)")
    propose.add_argument("--git-branch", type=str, default=None,
                         help="Current git branch")
    propose.add_argument("--git-dirty", action="store_true", default=None,
                         help="Whether the git working tree is dirty")
    propose.add_argument("--model", type=str, default=None,
                         help="Ollama model to use")
    propose.add_argument("--ollama-base-url", type=str, default=None,
                         help="Ollama base URL")
    propose.add_argument("--timeout", type=int, default=None,
                         help="Request timeout in seconds")
    propose.add_argument("--debug", action="store_true", default=False,
                         help="Print debug info to stderr")

    # --- doctor ---
    sub.add_parser("doctor", help="Check system readiness")

    # --- config ---
    config_parser = sub.add_parser("config", help="Configuration commands")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_sub.add_parser("show", help="Print resolved configuration")

    # --- policy ---
    policy_parser = sub.add_parser("policy", help="Policy commands")
    policy_sub = policy_parser.add_subparsers(dest="policy_command")
    check_parser = policy_sub.add_parser("check", help="Check a command against policy")
    check_parser.add_argument("command_text", nargs=argparse.REMAINDER,
                              help="Command to check (use -- before the command)")

    return parser


def _cmd_propose(args: argparse.Namespace) -> int:
    """Run the propose subcommand."""
    config = load_config(args)
    prov = config.get("provider", {})
    pol = config.get("policy", {})

    context = build_context(args, config)

    if args.debug:
        print(json.dumps(context, indent=2), file=sys.stderr)

    # Call Ollama
    messages = build_messages(context)
    try:
        raw = chat(
            messages,
            model=prov.get("model", "qwen2.5-coder:14b"),
            base_url=prov.get("base_url", "http://127.0.0.1:11434"),
            timeout=prov.get("timeout_seconds", 20),
        )
    except Exception as exc:
        response: dict[str, Any] = {
            "version": 1,
            "action": "error",
            "buffer": args.buffer or "",
            "summary": f"Ollama request failed: {exc}",
            "risk": "high",
            "reason": str(exc),
        }
        print(json.dumps(response))
        return 1

    if args.debug:
        print(f"Raw model response: {raw!r}", file=sys.stderr)

    # Parse and validate model response
    response = parse_response(raw)

    # Policy enforcement on replace_buffer actions
    if response["action"] == "replace_buffer" and pol.get("mode", "enforce") != "off":
        policy_result = policy_check(
            response["buffer"],
            max_buffer_bytes=pol.get("max_buffer_bytes", 8192),
            allow_medium_risk_insert=pol.get("allow_medium_risk_insert", False),
            mode=pol.get("mode", "enforce"),
        )
        if not policy_result["passed"]:
            response = {
                "version": 1,
                "action": "refuse",
                "buffer": response["buffer"],
                "summary": f"Policy blocked: {policy_result['reason']}",
                "risk": policy_result["risk"],
                "reason": policy_result["reason"],
            }
        elif policy_result["risk"] != "low":
            response["risk"] = policy_result["risk"]

    print(json.dumps(response))
    return 0


def _cmd_doctor(_args: argparse.Namespace) -> int:
    """Run the doctor subcommand."""
    config = load_config()
    prov = config.get("provider", {})
    base_url = prov.get("base_url", "http://127.0.0.1:11434")
    model = prov.get("model", "qwen2.5-coder:14b")
    all_ok = True

    # Check 1: Python version
    v = sys.version_info
    py_ok = v >= (3, 11)
    status = "ok" if py_ok else "FAIL"
    print(f"[{status}] Python version: {v.major}.{v.minor}.{v.micro}")
    if not py_ok:
        all_ok = False

    # Check 2: Ollama reachability
    ok, msg = check_health(base_url)
    status = "ok" if ok else "FAIL"
    print(f"[{status}] Ollama: {msg}")
    if not ok:
        all_ok = False

    # Check 3: Model availability
    if ok:
        models = list_models(base_url)
        # Model names may include tags like :latest
        model_found = any(
            m == model or m.startswith(model + ":") or model.startswith(m.split(":")[0])
            for m in models
        )
        if model_found:
            print(f"[ok] Model '{model}' is available")
        else:
            print(f"[FAIL] Model '{model}' not found. Available: {', '.join(models) or 'none'}")
            all_ok = False
    else:
        print(f"[skip] Model check skipped (Ollama unreachable)")

    # Check 4: Test JSON generation
    if ok and model_found:
        try:
            test_messages = [
                {"role": "system", "content": "Reply with exactly: {\"ok\": true}"},
                {"role": "user", "content": "test"},
            ]
            raw = chat(test_messages, model=model, base_url=base_url, timeout=15)
            import json as _json
            _json.loads(raw.strip().strip("`").strip())
            print("[ok] JSON generation test passed")
        except Exception as exc:
            print(f"[FAIL] JSON generation test: {exc}")
            all_ok = False
    elif ok:
        print("[skip] JSON generation test skipped (model not available)")

    return 0 if all_ok else 1


def _cmd_config_show(_args: argparse.Namespace) -> int:
    """Print resolved config as TOML."""
    config = load_config()
    print(config_to_toml(config))
    return 0


def _cmd_policy_check(args: argparse.Namespace) -> int:
    """Run policy checker on given command text."""
    config = load_config()
    pol = config.get("policy", {})

    # command_text comes as a list from REMAINDER; join it
    parts = args.command_text
    # Strip leading '--' if present
    if parts and parts[0] == "--":
        parts = parts[1:]
    command = " ".join(parts)

    if not command:
        print("Error: no command provided", file=sys.stderr)
        return 1

    result = policy_check(
        command,
        max_buffer_bytes=pol.get("max_buffer_bytes", 8192),
        allow_medium_risk_insert=pol.get("allow_medium_risk_insert", False),
        mode=pol.get("mode", "enforce"),
    )

    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "propose":
        sys.exit(_cmd_propose(args))
    elif args.command == "doctor":
        sys.exit(_cmd_doctor(args))
    elif args.command == "config":
        if getattr(args, "config_command", None) == "show":
            sys.exit(_cmd_config_show(args))
        else:
            parser.parse_args(["config", "--help"])
    elif args.command == "policy":
        if getattr(args, "policy_command", None) == "check":
            sys.exit(_cmd_policy_check(args))
        else:
            parser.parse_args(["policy", "--help"])
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
