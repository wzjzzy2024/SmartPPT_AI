"""
Slide template renderers + dispatch table.
Each renderer maps a layout_id to python-pptx shape composition.
All renderers accept a `theme` dict for dynamic color support.

Layout tiers:
  structural -> cover / toc / thanks / section_divider
  content    -> content_with_image / content_decor / two_column /
                icon_grid_3 / icon_grid_4 / stat_callout /
                quote_highlight / text_focus / data_chart
"""
from io import BytesIO

from pptx.enum.text import PP_ALIGN

from engine.layout_engine import get_layout, Region
from engine.pptx_renderer import (
    add_rect, add_round_rect, add_oval, add_hline,
    add_textbox, add_bullet_points, add_text_lines, add_image,
    add_image_fit, add_gradient_rect, add_gradient_round_rect,
    set_fill_alpha, set_gradient_stop_alpha, shade, lighten,
)
from utils.icon_matcher import get_icon_png, get_icon_png_for_text

# Shared slot on content header bands (title regions end at 14.8").
_HEADER_ICON = Region(15.1, 0.14, 0.82, 0.82)


def _split_two(points: list) -> tuple[list, list]:
    """Split points into two balanced columns."""
    mid = max(1, (len(points) + 1) // 2)
    return points[:mid], points[mid:]


def _place_icon(slide, region: Region, png: bytes | None) -> bool:
    """Embed a rasterized icon; returns False when nothing was drawn."""
    if not png:
        return False
    add_image(slide, region, BytesIO(png))
    return True


def _content_header(slide, L: dict, slide_data: dict, theme: dict,
                    font_size: int = 28, with_icon: bool = True) -> None:
    """Gradient header band + title + optional white icon on the right."""
    add_gradient_rect(slide, L["header_band"],
                      theme["primary"], theme["accent"], angle_deg=0.0)
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=font_size, color=theme["white"], bold=True)
    if with_icon:
        icon = get_icon_png(slide_data, theme, color=theme["white"])
        _place_icon(slide, _HEADER_ICON, icon)


# -- 1. cover (centered full-bleed title page) --------------------

def render_cover(slide, slide_data: dict, theme: dict):
    L = get_layout("cover")
    add_gradient_rect(slide, L["bg_rect"],
                      theme["primary"], shade(theme["primary"], 0.80),
                      angle_deg=90.0)
    set_fill_alpha(add_oval(slide, L["deco_circle_1"], color=theme["accent"]), 30)
    set_fill_alpha(add_oval(slide, L["deco_circle_2"], color=theme["light"]), 25)
    set_fill_alpha(add_oval(slide, L["deco_circle_3"], color=theme["accent"]), 30)
    add_hline(slide, L["rule"], theme["white"], width_pt=3)
    _place_icon(
        slide, Region(7.65, 1.95, 0.7, 0.7),
        get_icon_png(slide_data, theme, color=theme["white"]),
    )
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=44, color=theme["white"], bold=True,
                align=PP_ALIGN.CENTER)
    subtitle = slide_data.get("subtitle") or ""
    if subtitle:
        add_textbox(slide, L["subtitle"], subtitle,
                    font_size=20, color=theme["light"],
                    align=PP_ALIGN.CENTER)


# -- 2. toc (table of contents, deterministic entries) ------------

def render_toc(slide, slide_data: dict, theme: dict):
    L = get_layout("toc")
    add_rect(slide, L["accent_bar"], theme["accent"])
    add_oval(slide, L["deco_circle"], color=theme["light"])
    add_textbox(slide, L["title"], slide_data.get("title") or "目录",
                font_size=40, color=theme["primary"], bold=True)
    add_hline(slide, L["rule"], theme["accent"], width_pt=4)
    entries = [e for e in (slide_data.get("display_points") or []) if e]
    col1, col2 = _split_two(entries)
    add_text_lines(slide, L["col1"], col1, font_size=22,
                   color=theme["text"], line_spacing=1.35)
    add_text_lines(slide, L["col2"], col2, font_size=22,
                   color=theme["text"], line_spacing=1.35)


# -- 3. thanks (standard Thank You / Q&A closing page) ------------

def render_thanks(slide, slide_data: dict, theme: dict):
    L = get_layout("thanks")
    add_gradient_rect(slide, L["bg_rect"],
                      theme["primary"], shade(theme["primary"], 0.80),
                      angle_deg=90.0)
    set_fill_alpha(add_oval(slide, L["deco_circle_1"], color=theme["accent"]), 30)
    set_fill_alpha(add_oval(slide, L["deco_circle_2"], color=theme["light"]), 25)
    add_oval(slide, L["deco_ring"], outline=theme["white"], line_width=2.5)
    add_hline(slide, L["rule"], theme["white"], width_pt=3)
    _place_icon(
        slide, Region(7.65, 2.2, 0.7, 0.7),
        get_icon_png(slide_data, theme, color=theme["white"]),
    )
    add_textbox(slide, L["title"], slide_data.get("title") or "Thank You",
                font_size=54, color=theme["white"], bold=True,
                align=PP_ALIGN.CENTER)
    subtitle = slide_data.get("subtitle") or "感谢观看 · Q & A"
    add_textbox(slide, L["subtitle"], subtitle,
                font_size=20, color=theme["light"],
                align=PP_ALIGN.CENTER)


# -- 4. content_with_image ---------------------------------------

def render_content_with_image(slide, slide_data: dict, theme: dict, image_bytes=None):
    L = get_layout("content_with_image")
    _content_header(slide, L, slide_data, theme, font_size=28)
    add_bullet_points(slide, L["body"],
                      slide_data.get("display_points", []),
                      base_font_size=18, theme=theme)
    # Landscape photo card: tinted backing absorbs letterboxing, accent
    # bar anchors the column, and the image keeps its native aspect ratio.
    panel = add_round_rect(slide, L["image_panel"], theme["light"], radius=0.04)
    set_fill_alpha(panel, 55)
    add_rect(slide, L["image_accent"], theme["accent"])
    add_image_fit(slide, L["image"], image_bytes)


# -- 5. content_decor (no-image fallback, pure geometry) ---------

def render_content_decor(slide, slide_data: dict, theme: dict):
    L = get_layout("content_decor")
    _content_header(slide, L, slide_data, theme, font_size=28)
    add_bullet_points(slide, L["body"],
                      slide_data.get("display_points", []),
                      base_font_size=18, theme=theme)
    # right-side geometric panel: soft gradient + translucent accents
    panel = add_gradient_round_rect(
        slide, L["panel"],
        theme["light"], lighten(theme["light"], 0.45),
        angle_deg=0.0, radius=0.08,
    )
    set_gradient_stop_alpha(panel, 85)
    set_fill_alpha(add_oval(slide, L["deco_circle_1"], color=theme["accent"]), 32)
    set_fill_alpha(add_oval(slide, L["deco_circle_2"], color=theme["primary"]), 28)
    add_oval(slide, L["deco_ring"], outline=theme["accent"], line_width=2.5)
    set_fill_alpha(add_oval(slide, L["deco_circle_3"], color=theme["white"]), 35)
    _place_icon(
        slide, Region(11.6, 1.7, 1.5, 1.5),
        get_icon_png(slide_data, theme, color=theme["accent"]),
    )
    add_textbox(slide, L["page_num"], f"{slide_data.get('index', 0):02d}",
                font_size=54, color=theme["primary"], bold=True,
                align=PP_ALIGN.CENTER)


# -- 6. two_column ------------------------------------------------

def render_two_column(slide, slide_data: dict, theme: dict):
    L = get_layout("two_column")
    _content_header(slide, L, slide_data, theme, font_size=26)
    points = slide_data.get("display_points", [])
    left, right = _split_two(points)
    add_bullet_points(slide, L["left"],  left, theme=theme)
    add_bullet_points(slide, L["right"], right, theme=theme)
    sep = Region(7.9, 1.3, 0.08, 6.2)
    add_rect(slide, sep, theme["accent"])


# -- 7. icon_grid_3 -----------------------------------------------

def render_icon_grid_3(slide, slide_data: dict, theme: dict):
    L = get_layout("icon_grid_3")
    _content_header(slide, L, slide_data, theme, font_size=26, with_icon=False)
    points = slide_data.get("display_points", ["", "", ""])
    colors = [theme["primary"], shade(theme["primary"], 0.72), theme["accent"]]
    for i, card_region in enumerate(L["cards"]):
        add_rect(slide, card_region, colors[i % 3])
        text_region = Region(card_region.left + 0.2, card_region.top + 1.4,
                             card_region.width - 0.4, card_region.height - 1.6)
        text = points[i] if i < len(points) else ""
        icon = get_icon_png_for_text(text, theme["white"])
        drawn = _place_icon(
            slide,
            Region(card_region.left + 0.25, card_region.top + 0.35, 0.7, 0.7),
            icon,
        )
        if not drawn:
            add_textbox(slide, Region(card_region.left + 0.2,
                                      card_region.top + 0.3, 1.0, 1.0),
                        str(i + 1), font_size=48,
                        color=theme["white"], bold=True)
        add_textbox(slide, text_region, text,
                    font_size=16, color=theme["white"], auto_size=True)


# -- 8. icon_grid_4 (4-card variant) ------------------------------

def render_icon_grid_4(slide, slide_data: dict, theme: dict):
    L = get_layout("icon_grid_4")
    _content_header(slide, L, slide_data, theme, font_size=26, with_icon=False)
    points = slide_data.get("display_points", ["", "", "", ""])
    colors = [
        theme["primary"], shade(theme["primary"], 0.72),
        theme["accent"], shade(theme["accent"], 0.72),
    ]
    for i, card_region in enumerate(L["cards"]):
        add_rect(slide, card_region, colors[i % 4])
        text_region = Region(card_region.left + 0.2, card_region.top + 1.4,
                             card_region.width - 0.4, card_region.height - 1.6)
        text = points[i] if i < len(points) else ""
        icon = get_icon_png_for_text(text, theme["white"])
        drawn = _place_icon(
            slide,
            Region(card_region.left + 0.25, card_region.top + 0.35, 0.7, 0.7),
            icon,
        )
        if not drawn:
            add_textbox(slide, Region(card_region.left + 0.2,
                                      card_region.top + 0.3, 1.0, 1.0),
                        str(i + 1), font_size=48,
                        color=theme["white"], bold=True)
        add_textbox(slide, text_region, text,
                    font_size=14, color=theme["white"], auto_size=True)


# -- 9. stat_callout ----------------------------------------------

def render_stat_callout(slide, slide_data: dict, theme: dict):
    L = get_layout("stat_callout")
    bg = Region(0, 0, 16, 9)
    add_gradient_rect(slide, bg, theme["primary"],
                      shade(theme["primary"], 0.85), angle_deg=90.0)
    add_rect(slide, L["bg_band"], theme["accent"])
    _place_icon(
        slide, Region(0.45, 0.4, 0.5, 0.5),
        get_icon_png(slide_data, theme, color=theme["white"]),
    )
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=24, color=theme["light"])
    points = slide_data.get("display_points", [""])
    add_textbox(slide, L["stat"], points[0] if points else "",
                font_size=48, color=theme["white"], bold=True,
                align=PP_ALIGN.CENTER, auto_size=True)
    desc = "，".join(points[1:3]) if len(points) > 1 else ""
    add_textbox(slide, L["desc"], desc,
                font_size=20, color=theme["light"], align=PP_ALIGN.CENTER)


# -- 10. quote_highlight ------------------------------------------

def render_quote_highlight(slide, slide_data: dict, theme: dict):
    L = get_layout("quote_highlight")
    add_rect(slide, L["side_band"], theme["accent"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=20, color=theme["primary"])
    add_textbox(slide, L["quote_mark"], ">",
                font_size=96, color=theme["light"])
    text = "\n".join(slide_data.get("display_points", []))
    add_textbox(slide, L["body"], text,
                font_size=28, color=theme["primary"], auto_size=True)


# -- 11. text_focus (dual-column text) ----------------------------

def render_text_focus(slide, slide_data: dict, theme: dict):
    L = get_layout("text_focus")
    _content_header(slide, L, slide_data, theme, font_size=26)
    points = slide_data.get("display_points", [])
    left, right = _split_two(points)
    add_bullet_points(slide, L["col1"], left, theme=theme)
    add_bullet_points(slide, L["col2"], right, theme=theme)


# -- 12. section_divider ------------------------------------------

def render_section_divider(slide, slide_data: dict, theme: dict):
    L = get_layout("section_divider")
    add_gradient_rect(slide, L["bg_rect"],
                      theme["primary"], shade(theme["primary"], 0.80),
                      angle_deg=90.0)
    add_rect(slide, L["deco_line"], theme["accent"])
    _place_icon(
        slide, Region(2.0, 2.25, 0.7, 0.7),
        get_icon_png(slide_data, theme, color=theme["white"]),
    )
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=40, color=theme["white"], bold=True,
                align=PP_ALIGN.LEFT)
    subtitle = slide_data.get("subtitle") or ""
    if not subtitle:
        points = slide_data.get("display_points") or [""]
        subtitle = points[0]
    add_textbox(slide, L["subtitle"], subtitle,
                font_size=20, color=theme["light"],
                align=PP_ALIGN.LEFT)


# -- 13. data_chart (pipeline-only, generated PNG) ----------------

def render_data_chart(slide, slide_data: dict, theme: dict):
    L = get_layout("data_chart")
    _content_header(slide, L, slide_data, theme, font_size=28)
    add_bullet_points(slide, L["body"],
                      slide_data.get("display_points", []),
                      base_font_size=18, theme=theme)
    png = slide_data.get("_chart_png")
    if png:
        add_image(slide, L["chart"], BytesIO(png))


# -- Dispatch table -----------------------------------------------

RENDERERS = {
    "cover":              render_cover,
    "toc":                render_toc,
    "thanks":             render_thanks,
    "content_with_image": render_content_with_image,
    "content_decor":      render_content_decor,
    "two_column":         render_two_column,
    "icon_grid_3":        render_icon_grid_3,
    "icon_grid_4":        render_icon_grid_4,
    "stat_callout":       render_stat_callout,
    "quote_highlight":    render_quote_highlight,
    "text_focus":         render_text_focus,
    "section_divider":    render_section_divider,
    "data_chart":         render_data_chart,
}


def render_slide(slide, slide_data: dict, image_bytes=None, theme: dict = None):
    layout_id = slide_data.get("layout_id", "text_focus")
    # No image available -> geometric decoration layout (never a bare box)
    if image_bytes is None and layout_id == "content_with_image":
        layout_id = "content_decor"
    # Chart rendering failed upstream -> reuse the decorated layout
    if layout_id == "data_chart" and not slide_data.get("_chart_png"):
        layout_id = "content_decor"
    renderer = RENDERERS.get(layout_id, render_text_focus)
    if layout_id == "content_with_image":
        renderer(slide, slide_data, theme, image_bytes)
    else:
        renderer(slide, slide_data, theme)
