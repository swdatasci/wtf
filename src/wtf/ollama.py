"""Ollama HTTP client using only urllib.request (stdlib)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT = 20


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST JSON to a URL and return the parsed JSON response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _get_json(url: str, *, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """GET a URL and return the parsed JSON response."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def chat(
    messages: list[dict[str, str]],
    *,
    model: str = "qwen2.5-coder:14b",
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send a chat completion request to Ollama.

    Returns the assistant message content as a string.
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    result = _post_json(url, payload, timeout=timeout)
    # Ollama returns: {"message": {"role": "assistant", "content": "..."}, ...}
    msg = result.get("message", {})
    return msg.get("content", "")


def check_health(base_url: str = DEFAULT_BASE_URL, timeout: int = 5) -> tuple[bool, str]:
    """Check if Ollama is reachable.

    Returns (ok, message).
    """
    try:
        url = f"{base_url.rstrip('/')}/api/tags"
        _get_json(url, timeout=timeout)
        return True, "Ollama is reachable"
    except urllib.error.URLError as exc:
        return False, f"Cannot reach Ollama: {exc.reason}"
    except Exception as exc:
        return False, f"Cannot reach Ollama: {exc}"


def list_models(
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 5,
) -> list[str]:
    """List available models from Ollama.

    Returns a list of model name strings.
    """
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        data = _get_json(url, timeout=timeout)
    except Exception:
        return []
    models = data.get("models", [])
    return [m.get("name", "") for m in models if isinstance(m, dict)]
