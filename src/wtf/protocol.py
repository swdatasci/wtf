"""Response protocol: validate and parse model responses.

Schema version 1:
{
    "version": 1,
    "action": "replace_buffer" | "ask" | "refuse" | "error",
    "buffer": "<string>",
    "summary": "<string>",
    "risk": "low" | "medium" | "high",
    "reason": "<string>"
}
"""

from __future__ import annotations

import json
import re
from typing import Any


VALID_ACTIONS = frozenset({"replace_buffer", "ask", "refuse", "error"})
VALID_RISKS = frozenset({"low", "medium", "high"})

# Pattern to strip markdown code fences
_CODE_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?\s*```$",
    re.DOTALL,
)


def _has_control_chars(text: str) -> bool:
    """Reject control characters in response strings."""
    for ch in text:
        code = ord(ch)
        if code < 32 and ch not in ("\n", "\r", "\t", " "):
            return True
        if code == 127:
            return True
    return False


def _strip_fences(text: str) -> str:
    """Strip markdown code fences if the model wrapped JSON in them."""
    text = text.strip()
    m = _CODE_FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


def parse_response(raw: str) -> dict[str, Any]:
    """Parse and validate a model response string.

    Returns a validated response dict, or an error response dict if invalid.
    """
    text = _strip_fences(raw)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return _error(f"Invalid JSON from model: {exc}")

    if not isinstance(data, dict):
        return _error("Model response is not a JSON object")

    # Version check
    version = data.get("version")
    if version != 1:
        return _error(f"Unsupported response version: {version}")

    # Action check
    action = data.get("action")
    if action not in VALID_ACTIONS:
        return _error(f"Invalid action: {action}")

    # Buffer must be a string
    buffer = data.get("buffer")
    if not isinstance(buffer, str):
        return _error("Missing or invalid 'buffer' field")

    # Check for control characters in buffer
    if _has_control_chars(buffer):
        return _error("Response buffer contains control characters")

    # Summary
    summary = data.get("summary", "")
    if not isinstance(summary, str):
        summary = str(summary)

    # Risk
    risk = data.get("risk", "low")
    if risk not in VALID_RISKS:
        return _error(f"Invalid risk level: {risk}")

    # Reason
    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = str(reason)

    return {
        "version": 1,
        "action": action,
        "buffer": buffer,
        "summary": summary,
        "risk": risk,
        "reason": reason,
    }


def _error(msg: str) -> dict[str, Any]:
    """Construct an error response."""
    return {
        "version": 1,
        "action": "error",
        "buffer": "",
        "summary": msg,
        "risk": "high",
        "reason": msg,
    }
