"""Extract valid JSON actions from AI response text."""

import json
import re


class ParseError(Exception):
    """Raised when no valid action can be extracted from the response."""


def parse_response(raw_text, valid_options):
    """Parse an AI response into {"speech": str, "action": str}.

    Tries multiple extraction strategies, then validates the action against
    valid_options. Raises ParseError if nothing works.
    """
    data = _extract_json(raw_text)
    speech = str(data.get("speech", ""))
    raw_action = str(data.get("action", ""))
    action = _match_option(raw_action, valid_options)
    result = {"speech": speech, "action": action}
    if data.get("private_thought"):
        result["private_thought"] = str(data["private_thought"])
    return result


def _extract_json(text):
    """Try multiple strategies to pull a JSON object from text."""
    # Strategy 1: Direct parse
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Markdown code block ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: First {...} via regex
    match = re.search(r"\{[^{}]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: Brace-depth matching for outermost {...}
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start:i + 1])
                        if isinstance(data, dict):
                            return data
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break

    raise ParseError(f"Could not extract JSON from response: {text[:200]}")


def _match_option(raw_action, valid_options):
    """Match raw_action to one of the valid options.

    Tries: exact match, case-insensitive match, unambiguous partial match.
    Raises ParseError if no match found.
    """
    if not valid_options:
        raise ParseError("No valid options to match against.")

    # Exact match
    if raw_action in valid_options:
        return raw_action

    # Case-insensitive match
    lower_action = raw_action.lower().strip()
    for opt in valid_options:
        if opt.lower() == lower_action:
            return opt

    # Partial match — raw_action is a substring of exactly one option
    partial = [opt for opt in valid_options if lower_action in opt.lower()]
    if len(partial) == 1:
        return partial[0]

    # Reverse partial — option is a substring of raw_action
    reverse = [opt for opt in valid_options if opt.lower() in lower_action]
    if len(reverse) == 1:
        return reverse[0]

    raise ParseError(
        f"Could not match action '{raw_action}' to valid options: {valid_options}"
    )
