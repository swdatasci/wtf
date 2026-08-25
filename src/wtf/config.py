"""Configuration loader: CLI args > env vars > config file > defaults."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, dict[str, Any]] = {
    "provider": {
        "kind": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5-coder:14b",
        "timeout_seconds": 20,
    },
    "context": {
        "include_git": True,
        "include_last_command": True,
        "include_last_output": True,
        "max_last_output_bytes": 4096,
    },
    "policy": {
        "mode": "enforce",
        "allow_medium_risk_insert": False,
        "max_buffer_bytes": 8192,
    },
    "ui": {
        "show_summary": True,
    },
}

# Env var mapping: WTF_PROVIDER_MODEL -> provider.model, etc.
_ENV_PREFIX = "WTF_"


def _config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg) / "wtf" / "config.toml"


def _load_file() -> dict[str, Any]:
    """Load TOML config file if it exists."""
    p = _config_path()
    if not p.is_file():
        return {}
    with open(p, "rb") as f:
        return tomllib.load(f)


def _env_overrides() -> dict[str, dict[str, Any]]:
    """Read WTF_* environment variables into nested dict."""
    result: dict[str, dict[str, Any]] = {}
    for key, val in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        parts = key[len(_ENV_PREFIX):].lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, name = parts
        if section not in DEFAULTS:
            continue
        if name not in DEFAULTS[section]:
            continue
        # Coerce to same type as default
        default_val = DEFAULTS[section][name]
        if isinstance(default_val, bool):
            coerced: Any = val.lower() in ("1", "true", "yes")
        elif isinstance(default_val, int):
            coerced = int(val)
        else:
            coerced = val
        result.setdefault(section, {})[name] = coerced
    return result


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge overlay into base (one level deep)."""
    out = {}
    for k in set(base) | set(overlay):
        bv = base.get(k, {})
        ov = overlay.get(k, {})
        if isinstance(bv, dict) and isinstance(ov, dict):
            out[k] = {**bv, **ov}
        elif k in overlay:
            out[k] = ov
        else:
            out[k] = bv
    return out


def _cli_overrides(args: Any) -> dict[str, dict[str, Any]]:
    """Extract config-relevant CLI args into nested dict."""
    result: dict[str, dict[str, Any]] = {}
    mapping = {
        "model": ("provider", "model"),
        "ollama_base_url": ("provider", "base_url"),
        "timeout": ("provider", "timeout_seconds"),
    }
    for attr, (section, name) in mapping.items():
        val = getattr(args, attr, None)
        if val is not None:
            result.setdefault(section, {})[name] = val
    return result


def load_config(cli_args: Any = None) -> dict[str, Any]:
    """Load fully resolved config: defaults < file < env < CLI."""
    cfg = dict(DEFAULTS)
    # Deep copy defaults
    cfg = {k: dict(v) for k, v in cfg.items()}

    file_cfg = _load_file()
    cfg = _deep_merge(cfg, file_cfg)

    env_cfg = _env_overrides()
    cfg = _deep_merge(cfg, env_cfg)

    if cli_args is not None:
        cli_cfg = _cli_overrides(cli_args)
        cfg = _deep_merge(cfg, cli_cfg)

    return cfg


def config_to_toml(cfg: dict[str, Any]) -> str:
    """Render config dict as TOML string (simple, no third-party deps)."""
    lines: list[str] = []
    for section, values in sorted(cfg.items()):
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for k, v in sorted(values.items()):
            if isinstance(v, bool):
                lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v, int):
                lines.append(f"{k} = {v}")
            elif isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            else:
                lines.append(f'{k} = "{v}"')
        lines.append("")
    return "\n".join(lines)
