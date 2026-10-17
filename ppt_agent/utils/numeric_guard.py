"""
Deterministic number provenance guard.

The writer model is allowed to keep numbers from the slide draft (key_points)
or from web search context, but weaker models still invent percentages and
statistics ("提升 30%", "缩短至 6 个月"). Any numeric claim that cannot be
traced back to the draft or the web context is dropped from display_points;
the page is then topped up with trusted draft points.

This is deliberately conservative: only numbers carrying a unit (%, 倍, 年,
个月, 万人 ...) are checked, so structural language such as "3 个方面"
is not affected.
"""

import logging
import re

logger = logging.getLogger("smartppt.numeric_guard")

# Percentages, years, multiples and measured quantities. Bare integers are
# intentionally ignored (e.g. "3 个方面" is not a data claim).
_NUM_CLAIM = re.compile(
    r"\d+(?:\.\d+)?\s*"
    r"(?:%|％|倍|年|个月|月|天|小时|分钟|秒|万|亿|人|例|项|家|台|次|GB|TB|ms)",
    re.IGNORECASE,
)


def _norm(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).replace("％", "%")


def _source_text(slide: dict) -> str:
    """Text the writer is allowed to quote numbers from."""
    parts = [
        slide.get("title", ""),
        slide.get("subtitle", ""),
        slide.get("_web_context", ""),
    ]
    parts.extend(str(p) for p in (slide.get("key_points") or []))
    return _norm("".join(parts))


def claim_is_sourced(slide: dict, claim: str) -> bool:
    """True when a numeric claim appears in the slide's trusted source text.

    Used by chart_builder for a final fail-closed check: the last-resort
    branch of strip_unsupported_numbers may keep an unsourced bullet to avoid
    a blank page, but such a number must never become chart data.
    """
    return _norm(claim) in _source_text(slide)


def _unsupported_claims(point: str, source: str) -> list[str]:
    claims = []
    for match in _NUM_CLAIM.finditer(point):
        if _norm(match.group(0)) not in source:
            claims.append(match.group(0).strip())
    return claims


def _sanitize_point(point: str, claims: list[str]) -> str:
    """Remove unsupported numeric claims while keeping the sentence readable."""
    text = point
    for claim in claims:
        text = text.replace(claim, "")
    text = re.sub(r"\s*([.。,，;；:：])\s*", r"\1", text)
    # "缩短至6个月" -> "缩短至" -> "缩短"
    text = re.sub(r"(?:至|到|为|约|近|超|达)\s*$", "", text.strip())
    text = re.sub(r"\s*[.。,，;；:：\-—]+\s*$", "", text.strip())
    return re.sub(r"\s{2,}", " ", text).strip()


def strip_unsupported_numbers(slide: dict) -> dict:
    """Remove display bullet(s) whose numeric claims have no trusted source.

    A bullet is dropped only when it carries at least one unsupported numeric
    claim. Remaining trusted draft points are used to top the page back up to
    three bullets. Returns the mutated slide for convenience.
    """
    points = [
        str(p).strip() for p in (slide.get("display_points") or [])
        if str(p).strip()
    ]
    if not points:
        return slide

    source = _source_text(slide)
    kept = []
    dropped = []
    for point in points:
        claims = _unsupported_claims(point, source)
        if claims:
            dropped.append((point, claims))
        else:
            kept.append(point)

    if not dropped:
        return slide

    for draft in slide.get("key_points") or []:
        if len(kept) >= 3:
            break
        draft = str(draft).strip()
        if draft and draft not in kept:
            kept.append(draft)

    # No trusted draft available: keep the sentence but strip only the number
    # so a summary page never ends up completely blank.
    if not kept:
        for point, claims in dropped:
            cleaned = _sanitize_point(point, claims)
            if len(cleaned) >= 4 and cleaned not in kept:
                kept.append(cleaned)
            if len(kept) >= 3:
                break

    # Last resort: never leave the page body empty.
    if not kept:
        kept = [point for point, _ in dropped[:3]]
        logger.warning(
            "Slide %s: no trusted replacement, keeping original bullets",
            slide.get("index", "?"),
        )

    slide["display_points"] = kept
    for point, claims in dropped:
        logger.warning(
            "Slide %s: dropped unsupported numeric claim(s) %s -> %r",
            slide.get("index", "?"), claims, point,
        )
    return slide
