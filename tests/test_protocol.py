"""Tests for wtf.protocol — response protocol validation."""

import json
import unittest

from wtf.protocol import parse_response, VALID_ACTIONS, VALID_RISKS


def _make_raw(**overrides) -> str:
    """Build a valid response JSON string, with optional overrides."""
    base = {
        "version": 1,
        "action": "replace_buffer",
        "buffer": "ls -la",
        "summary": "list files",
        "risk": "low",
        "reason": "",
    }
    base.update(overrides)
    return json.dumps(base)


class TestValidResponses(unittest.TestCase):
    """Valid responses should parse without error."""

    def test_replace_buffer(self):
        result = parse_response(_make_raw(action="replace_buffer"))
        self.assertEqual(result["action"], "replace_buffer")
        self.assertEqual(result["buffer"], "ls -la")
        self.assertEqual(result["risk"], "low")
        self.assertEqual(result["version"], 1)

    def test_ask(self):
        result = parse_response(_make_raw(action="ask", buffer="git push"))
        self.assertEqual(result["action"], "ask")
        self.assertEqual(result["buffer"], "git push")

    def test_refuse(self):
        result = parse_response(_make_raw(
            action="refuse",
            buffer="",
            reason="policy violation",
        ))
        self.assertEqual(result["action"], "refuse")
        self.assertEqual(result["reason"], "policy violation")

    def test_error(self):
        result = parse_response(_make_raw(
            action="error",
            buffer="",
            reason="model failure",
        ))
        self.assertEqual(result["action"], "error")


class TestMissingFields(unittest.TestCase):
    """Missing required fields should produce error responses."""

    def test_missing_version(self):
        raw = json.dumps({"action": "replace_buffer", "buffer": "ls"})
        result = parse_response(raw)
        self.assertEqual(result["action"], "error")
        self.assertIn("version", result["reason"].lower())

    def test_missing_action(self):
        raw = json.dumps({"version": 1, "buffer": "ls"})
        result = parse_response(raw)
        self.assertEqual(result["action"], "error")

    def test_missing_buffer(self):
        raw = json.dumps({"version": 1, "action": "replace_buffer"})
        result = parse_response(raw)
        self.assertEqual(result["action"], "error")
        self.assertIn("buffer", result["reason"].lower())


class TestInvalidAction(unittest.TestCase):
    """Invalid action values should produce error responses."""

    def test_bogus_action(self):
        result = parse_response(_make_raw(action="exec_now"))
        self.assertEqual(result["action"], "error")

    def test_none_action(self):
        raw = json.dumps({"version": 1, "action": None, "buffer": "ls"})
        result = parse_response(raw)
        self.assertEqual(result["action"], "error")


class TestInvalidRisk(unittest.TestCase):
    """Invalid risk values should produce error responses."""

    def test_bogus_risk(self):
        result = parse_response(_make_raw(risk="extreme"))
        self.assertEqual(result["action"], "error")
        self.assertIn("risk", result["reason"].lower())


class TestInvalidVersion(unittest.TestCase):
    """Non-v1 versions should produce error responses."""

    def test_version_2(self):
        result = parse_response(_make_raw(version=2))
        self.assertEqual(result["action"], "error")
        self.assertIn("version", result["reason"].lower())

    def test_version_none(self):
        result = parse_response(_make_raw(version=None))
        self.assertEqual(result["action"], "error")


class TestControlCharsInBuffer(unittest.TestCase):
    """Control characters in the buffer field should be rejected."""

    def test_null_in_buffer(self):
        result = parse_response(_make_raw(buffer="ls\x00"))
        self.assertEqual(result["action"], "error")
        self.assertIn("control", result["reason"].lower())

    def test_escape_in_buffer(self):
        result = parse_response(_make_raw(buffer="echo \x1b[31m"))
        self.assertEqual(result["action"], "error")

    def test_tab_is_ok(self):
        result = parse_response(_make_raw(buffer="echo\thello"))
        self.assertNotEqual(result["action"], "error")


class TestCodeFenceStripping(unittest.TestCase):
    """Markdown code fences wrapping JSON should be stripped."""

    def test_json_code_fence(self):
        inner = _make_raw()
        fenced = f"```json\n{inner}\n```"
        result = parse_response(fenced)
        self.assertEqual(result["action"], "replace_buffer")
        self.assertEqual(result["buffer"], "ls -la")

    def test_plain_code_fence(self):
        inner = _make_raw()
        fenced = f"```\n{inner}\n```"
        result = parse_response(fenced)
        self.assertEqual(result["action"], "replace_buffer")

    def test_no_fence(self):
        result = parse_response(_make_raw())
        self.assertEqual(result["action"], "replace_buffer")


class TestOversizedResponse(unittest.TestCase):
    """Malformed / garbage input should produce error responses."""

    def test_not_json(self):
        result = parse_response("this is not json at all")
        self.assertEqual(result["action"], "error")
        self.assertIn("json", result["reason"].lower())

    def test_json_array(self):
        result = parse_response("[1,2,3]")
        self.assertEqual(result["action"], "error")

    def test_empty_string(self):
        result = parse_response("")
        self.assertEqual(result["action"], "error")


if __name__ == "__main__":
    unittest.main()
