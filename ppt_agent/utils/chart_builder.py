"""
Deterministic data-chart generation from provenanced slide numbers.

numeric_guard has already removed numbers without a trusted source by the
time this module runs, so every plotted value comes from the slide draft or
web context. We parse those claims, convert an eligible content page to the
`data_chart` layout, and render a transparent matplotlib PNG.

No LLM involvement: the model can never invent chart data.
"""

import logging
import re
from io import BytesIO
from pathlib import Path

from config import (
    CHART_DPI,
    CHART_MAX_LABEL_LEN,
    CHART_MAX_POINTS,
    CHART_MIN_SAME_UNIT_POINTS,
    CJK_FONT_CANDIDATES,
)
from utils.numeric_guard import _NUM_CLAIM, claim_is_sourced

logger = logging.getLogger("smartppt.chart_builder")

_TIME_WORDS = ("年", "月", "季", "日", "周", "趋势", "增长", "变化", "阶段", "历年")
# Verb + direction pairs ("降至", "增长到") are removed as a unit; the
# verb alone ("增长") is meaningful and stays. Longer forms come first.
_TRAILING_CONNECTORS = re.compile(
    r"(?:约为|达到|突破|超过|"
    r"(?:下降|上升|提升|增长|增加|减少|降低|上涨|升|降|涨|跌)?(?:至|到)|"
    r"近|超|约|达|为|至|到)\s*$"
)
_CONVERTIBLE_LAYOUTS = {
    "content_with_image",
    "content_decor",
    "two_column",
    "text_focus",
}
# numeric_guard's claim regex stops before measure/currency words, so
# "120万辆" matches only "120万". Absorb the following character(s) into
# the displayed claim: the unit becomes "万辆" and the leftover label no
# longer ends in a dangling "辆"/"元".
_MEASURE_WORDS = set("辆台人家项次例个艘架只张所位名件份篇部款套条头元")

_CHART_FONT = None
_FONT_REGISTERED = False


def _clean_label(point: str, start: int, end: int) -> str:
    label = (point[:start] + point[end:]).strip()
    label = re.sub(r"\s+", " ", label)
    label = _TRAILING_CONNECTORS.sub("", label)
    label = re.sub(r"\s*[.。,，;；:：\-—]+\s*$", "", label)
    return label.strip()


def _unit_of(claim: str) -> str:
    match = re.match(r"\d+(?:\.\d+)?\s*(.*)", claim)
    unit = (match.group(1) if match else "").strip().replace("％", "%")
    if unit == "个月":
        unit = "月"
    return unit.lower() if unit.isascii() else unit


def _value_of(claim: str) -> float | None:
    match = re.match(r"\d+(?:\.\d+)?", claim)
    try:
        return float(match.group(0)) if match else None
    except (TypeError, ValueError):
        return None


def extract_chart_data(slide: dict) -> dict | None:
    """Parse display bullets into a single-unit series, or None."""
    points = [
        str(p).strip() for p in (slide.get("display_points") or [])
        if str(p).strip()
    ]
    if len(points) < 2 or len(points) > CHART_MAX_POINTS:
        return None

    records = []
    for point in points:
        matches = list(_NUM_CLAIM.finditer(point))
        if not matches:
            continue
        match = matches[-1]  # Chinese bullets put the resulting figure last
        short_claim = re.sub(r"\s+", "", match.group(0))
        end = match.end()
        while end < len(point) and point[end] in _MEASURE_WORDS:
            end += 1
        claim = re.sub(r"\s+", "", point[match.start():end])
        if not claim_is_sourced(slide, claim):
            # The source may spell the number without the measure word;
            # fall back to the guard-verified prefix rather than dropping.
            claim, end = short_claim, match.end()
            if not claim_is_sourced(slide, claim):
                continue
        value = _value_of(claim)
        label = _clean_label(point, match.start(), end)
        if value is None or not label or len(label) > CHART_MAX_LABEL_LEN:
            continue
        records.append({
            "label": label,
            "value": value,
            "unit": _unit_of(claim),
            "claim": claim,
        })

    if len(records) < CHART_MIN_SAME_UNIT_POINTS:
        return None

    # One chart has one unit. Keep the dominant unit when bullets mix units.
    counts = {}
    for record in records:
        counts[record["unit"]] = counts.get(record["unit"], 0) + 1
    unit = max(counts, key=lambda u: (counts[u], -list(counts).index(u)))
    records = [r for r in records if r["unit"] == unit][:CHART_MAX_POINTS]

    # After unit filtering every surviving point shares one unit; two points
    # are enough, and the cap above keeps the series readable.
    if len(records) < CHART_MIN_SAME_UNIT_POINTS:
        return None

    labels = [r["label"] for r in records]
    chart_type = "line" if sum(
        1 for label in labels if any(w in label for w in _TIME_WORDS)
    ) >= 2 else "bar"

    return {
        "labels": labels,
        "values": [r["value"] for r in records],
        "unit": unit,
        "claims": [r["claim"] for r in records],
        "chart_type": chart_type,
        "orig_layout_id": slide.get("layout_id", "text_focus"),
    }


def should_convert(slide: dict) -> bool:
    """Only photo-less content pages with a readable series are converted."""
    if slide.get("page_type") != "content":
        return False
    if slide.get("_image_approved"):
        return False
    if slide.get("layout_id") not in _CONVERTIBLE_LAYOUTS:
        return False
    points = slide.get("display_points") or []
    # 3+ bullets are the norm; exactly 2 still qualifies when the pair
    # shares a unit (enforced by extract_chart_data).
    if not (CHART_MIN_SAME_UNIT_POINTS <= len(points) <= 6):
        return False
    return extract_chart_data(slide) is not None


def convert_slide_to_chart(slide: dict) -> bool:
    data = extract_chart_data(slide)
    if not data:
        return False
    slide["_orig_layout_id"] = slide.get("layout_id")
    slide["_chart_data"] = data
    slide["layout_id"] = "data_chart"
    slide["needs_image"] = False
    return True


def revert_slide(slide: dict) -> None:
    original = slide.pop("_orig_layout_id", None)
    slide.pop("_chart_data", None)
    slide.pop("_chart_png", None)
    if original:
        slide["layout_id"] = original
    slide["needs_image"] = False


def _hex(color) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        int(color[0]), int(color[1]), int(color[2])
    )


def _wrap_label(label: str, width: int = 6) -> str:
    """Wrap a long label into two lines at a readable boundary."""
    if len(label) <= width:
        return label
    split = (len(label) + 1) // 2
    # "2023年出口翻倍" reads best as "2023年" / "出口翻倍"; prefer a year
    # marker in the first half over a blind middle split.
    year = label.rfind("年", 2, max(3, len(label) - 2))
    if year != -1:
        split = year + 1
    return label[:split] + "\n" + label[split:]


def _register_cjk_font():
    """Register a CJK TTF once per process (TTC files are unreliable)."""
    global _CHART_FONT, _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _CHART_FONT
    _FONT_REGISTERED = True
    try:
        from matplotlib import font_manager

        # matplotlib 3.11 dropped the module-level addfont; the manager
        # instance method works across 3.x.
        addfont = getattr(font_manager, "addfont", None) or (
            font_manager.fontManager.addfont
        )
        for path in CJK_FONT_CANDIDATES:
            if not Path(path).exists():
                continue
            try:
                addfont(path)
                _CHART_FONT = font_manager.FontProperties(fname=path).get_name()
                logger.info("Chart CJK font: %s (%s)", _CHART_FONT, path)
                return _CHART_FONT
            except Exception as e:
                logger.warning("Font registration failed for %s: %s", path, e)
    except Exception as e:
        logger.warning("matplotlib font setup failed: %s", e)
    logger.warning("No CJK font found; chart labels may show missing glyphs")
    return None


def build_chart_png(chart_data: dict, theme: dict) -> bytes | None:
    """Render a transparent, axis-light chart sized to the layout region."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from engine.layout_engine import LAYOUTS

        region = LAYOUTS["data_chart"]["chart"]
        _register_cjk_font()
        if _CHART_FONT:
            matplotlib.rcParams["font.sans-serif"] = [
                _CHART_FONT, "Droid Sans Fallback", "DejaVu Sans",
            ]
        matplotlib.rcParams["axes.unicode_minus"] = False

        labels = chart_data["labels"]
        values = chart_data["values"]
        claims = chart_data["claims"]
        unit = chart_data.get("unit") or ""
        primary = _hex(theme.get("primary", (0x1A, 0x3A, 0x5C)))
        accent = _hex(theme.get("accent", (0x24, 0x71, 0xA3)))
        text_color = _hex(theme.get("text", (0x1C, 0x28, 0x33)))
        light = _hex(theme.get("light", (0xD6, 0xEA, 0xF8)))
        max_value = max(values) if values else 0

        fig, ax = plt.subplots(
            figsize=(region.width, region.height), dpi=CHART_DPI
        )
        fig.patch.set_alpha(0)
        ax.patch.set_alpha(0)

        x = list(range(len(values)))
        if chart_data.get("chart_type") == "line":
            ax.plot(
                x, values, color=primary, linewidth=2.5,
                marker="o", markersize=7, zorder=3,
            )
            ax.scatter(
                [x[-1]], [values[-1]], color=accent, s=110, zorder=4,
            )
            ax.margins(x=0.08)
            ax.set_ylim(
                min(values) * 0.9 if min(values) > 0 else 0,
                max_value * 1.18 if max_value else 1,
            )
        else:
            bars = ax.bar(x, values, width=0.55, color=primary, zorder=3)
            if bars:
                bars[values.index(max_value)].set_color(accent)
            ax.set_xlim(-0.6, len(values) - 0.4)
            ax.set_ylim(0, max_value * 1.18 if max_value else 1)

        for xi, value, claim in zip(x, values, claims):
            # Offset in points + an opaque pad so a steep line never cuts
            # through the value text (slide background is white).
            ax.annotate(
                claim, xy=(xi, value), xytext=(0, 12),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=11, color=text_color, zorder=5,
                bbox=dict(boxstyle="round,pad=0.15", fc="white",
                          ec="none", alpha=0.9),
            )

        ax.set_xticks(x)
        # Long labels wrap onto two lines; rotation is only needed when the
        # series is dense enough that even wrapped labels would collide.
        n_points = len(labels)
        rotate = n_points > 4
        wrap_width = 12 if n_points <= 3 else (8 if n_points == 4 else 6)
        ax.set_xticklabels(
            [_wrap_label(label, wrap_width) for label in labels],
            fontsize=11 if n_points <= 4 else 10, color=text_color,
            rotation=15 if rotate else 0,
            ha="right" if rotate else "center",
        )
        ax.get_yaxis().set_visible(False)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(light)
        ax.spines["bottom"].set_linewidth(1.2)
        ax.tick_params(axis="x", length=0, pad=8)

        if unit:
            ax.text(
                0.0, 1.02, f"单位：{unit}", transform=ax.transAxes,
                fontsize=10, color=text_color, alpha=0.65,
                ha="left", va="bottom",
            )

        # Rotated ticks lean left of the first point; without extra left
        # padding the first label is clipped by the figure edge.
        fig.subplots_adjust(
            left=0.13 if rotate else 0.06, right=0.97,
            top=0.90, bottom=0.16,
        )
        buffer = BytesIO()
        fig.savefig(buffer, format="png", transparent=True, dpi=CHART_DPI)
        plt.close(fig)
        return buffer.getvalue()
    except Exception as e:
        logger.warning("Chart generation failed: %s", e)
        return None
