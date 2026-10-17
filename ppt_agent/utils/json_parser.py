"""
Robust JSON parser for LLM outputs.
Handles markdown fences, smart quotes, unescaped characters, extra text.
"""
import json
import re
import logging

logger = logging.getLogger("smartppt.json_parser")


def parse_json(raw: str, label: str = "LLM") -> dict:
    """
    Multi-strategy JSON extraction from LLM response.
    Raises ValueError only after all strategies fail.
    """
    text = raw.strip()
    original = text

    # -- Strategy 1: strip markdown fences, try direct parse --
    for prefix, suffix in [("```json", "```"), ("```JSON", "```"), ("```", "```")]:
        t = text
        if t.startswith(prefix):
            t = t[len(prefix):]
        if t.endswith(suffix):
            t = t[:-len(suffix)]
        t = t.strip()
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            continue

    # -- Strategy 2: find outermost { ... } --
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # -- Strategy 3: fix common LLM mistakes then retry --
        fixed = candidate
        # smart/curly quotes -> straight double quotes (they usually replace ")
        fixed = fixed.replace("“", '"').replace("”", '"')  # " "
        fixed = fixed.replace("‘", "'").replace("’", "'")  # ' '
        # unescaped literal newlines inside string values -> space
        fixed = re.sub(r'(?<=[^\\])"\s*\n\s*"', '" "', fixed)
        # trailing comma before ] or }
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"[{label}] Unable to parse JSON. Raw starts: {original[:300]}")


def safe_parse(raw: str, label: str = "LLM") -> dict:
    """Like parse_json but returns an empty dict instead of raising."""
    try:
        return parse_json(raw, label)
    except ValueError as e:
        logger.warning("%s", e)
        return {}
