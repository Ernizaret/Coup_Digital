"""Tests for AI_game.response_parser — JSON extraction and action matching."""

import unittest
from AI_game.response_parser import parse_response, _extract_json, _match_option, ParseError


class TestExtractJson(unittest.TestCase):
    """Test the multiple JSON extraction strategies."""

    def test_direct_json(self):
        text = '{"speech": "hello", "action": "Income"}'
        result = _extract_json(text)
        self.assertEqual(result["action"], "Income")

    def test_direct_json_with_whitespace(self):
        text = '  \n {"speech": "hi", "action": "Tax"} \n '
        result = _extract_json(text)
        self.assertEqual(result["action"], "Tax")

    def test_markdown_code_block(self):
        text = 'Here is my response:\n```json\n{"speech": "hi", "action": "Coup"}\n```'
        result = _extract_json(text)
        self.assertEqual(result["action"], "Coup")

    def test_markdown_code_block_no_lang(self):
        text = '```\n{"speech": "hi", "action": "Steal"}\n```'
        result = _extract_json(text)
        self.assertEqual(result["action"], "Steal")

    def test_embedded_json_simple(self):
        text = 'I think I will do this: {"speech": "ok", "action": "Income"} end.'
        result = _extract_json(text)
        self.assertEqual(result["action"], "Income")

    def test_nested_braces_brace_depth(self):
        text = 'Response: {"speech": "I said {something}", "action": "Tax"}'
        result = _extract_json(text)
        self.assertEqual(result["action"], "Tax")

    def test_no_json_raises_parse_error(self):
        with self.assertRaises(ParseError):
            _extract_json("no json here at all")

    def test_invalid_json_raises_parse_error(self):
        with self.assertRaises(ParseError):
            _extract_json("{this is not valid json}")

    def test_non_dict_json_raises_parse_error(self):
        with self.assertRaises(ParseError):
            _extract_json("[1, 2, 3]")


class TestMatchOption(unittest.TestCase):
    """Test the fuzzy action matching logic."""

    def test_exact_match(self):
        result = _match_option("Income", ["Income", "Tax", "Coup"])
        self.assertEqual(result, "Income")

    def test_case_insensitive_match(self):
        result = _match_option("income", ["Income", "Tax", "Coup"])
        self.assertEqual(result, "Income")

    def test_case_insensitive_with_whitespace(self):
        result = _match_option("  tax  ", ["Income", "Tax", "Coup"])
        self.assertEqual(result, "Tax")

    def test_partial_match_substring(self):
        result = _match_option("Ass", ["Income", "Assassinate", "Coup"])
        self.assertEqual(result, "Assassinate")

    def test_reverse_partial_match(self):
        result = _match_option("I choose Income now", ["Income", "Tax", "Coup"])
        self.assertEqual(result, "Income")

    def test_ambiguous_partial_raises(self):
        # "a" matches both "Tax" and "Assassinate" (both contain "a")
        with self.assertRaises(ParseError):
            _match_option("a", ["Tax", "Assassinate"])

    def test_no_match_raises(self):
        with self.assertRaises(ParseError):
            _match_option("Nonexistent", ["Income", "Tax"])

    def test_empty_options_raises(self):
        with self.assertRaises(ParseError):
            _match_option("Income", [])


class TestParseResponse(unittest.TestCase):
    """Test the full parse pipeline."""

    def test_valid_response(self):
        raw = '{"speech": "hello", "action": "Income"}'
        result = parse_response(raw, ["Income", "Tax", "Coup"])
        self.assertEqual(result["speech"], "hello")
        self.assertEqual(result["action"], "Income")

    def test_private_thought_included(self):
        raw = '{"speech": "hi", "action": "Tax", "private_thought": "they might block"}'
        result = parse_response(raw, ["Income", "Tax"])
        self.assertEqual(result["action"], "Tax")
        self.assertEqual(result["private_thought"], "they might block")

    def test_private_thought_absent(self):
        raw = '{"speech": "hi", "action": "Tax"}'
        result = parse_response(raw, ["Income", "Tax"])
        self.assertNotIn("private_thought", result)

    def test_case_insensitive_action(self):
        raw = '{"speech": "", "action": "tax"}'
        result = parse_response(raw, ["Income", "Tax"])
        self.assertEqual(result["action"], "Tax")

    def test_invalid_json_raises(self):
        with self.assertRaises(ParseError):
            parse_response("not json", ["Income"])

    def test_invalid_action_raises(self):
        raw = '{"speech": "hi", "action": "Fly"}'
        with self.assertRaises(ParseError):
            parse_response(raw, ["Income", "Tax"])


if __name__ == "__main__":
    unittest.main()
