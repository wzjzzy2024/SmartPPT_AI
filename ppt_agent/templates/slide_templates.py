"""
9 slide template renderers + dispatch table.
Each renderer maps a layout_id to python-pptx shape composition.
All renderers accept a `theme` dict for dynamic color support.
"""
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

from engine.layout_engine import get_layout, Region
from engine.pptx_renderer import add_rect, add_textbox, add_bullet_points, add_image


# -- 1. title_hero -----------------------------------------------

def render_title_hero(slide, slide_data: dict, theme: dict):
    L = get_layout("title_hero")
    add_rect(slide, L["bg_rect"],   theme["primary"])
    add_rect(slide, L["deco_rect"], theme["accent"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=44, color=theme["white"], bold=True,
                align=PP_ALIGN.LEFT)
    points = slide_data.get("display_points") or [""]
    add_textbox(slide, L["subtitle"], points[0],
                font_size=24, color=theme["light"],
                align=PP_ALIGN.LEFT)


# -- 2. content_with_image ---------------------------------------

def render_content_with_image(slide, slide_data: dict, theme: dict, image_bytes=None):
    L = get_layout("content_with_image")
    header_band = Region(0, 0, 16, 1.1)
    add_rect(slide, header_band, theme["primary"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=28, color=theme["white"], bold=True)
    add_bullet_points(slide, L["body"],
                      slide_data.get("display_points", []),
                      base_font_size=18, theme=theme)
    add_image(slide, L["image"], image_bytes)
    if image_bytes is None:
        add_rect(slide, L["image"], theme["light"])


# -- 3. two_column -----------------------------------------------

def render_two_column(slide, slide_data: dict, theme: dict):
    L = get_layout("two_column")
    header_band = Region(0, 0, 16, 1.1)
    add_rect(slide, header_band, theme["primary"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=26, color=theme["white"], bold=True)
    points = slide_data.get("display_points", [])
    mid = max(1, len(points) // 2)
    add_bullet_points(slide, L["left"],  points[:mid], theme=theme)
    add_bullet_points(slide, L["right"], points[mid:], theme=theme)
    sep = Region(7.9, 1.3, 0.08, 6.2)
    add_rect(slide, sep, theme["accent"])


# -- 4. icon_grid_3 ----------------------------------------------

def render_icon_grid_3(slide, slide_data: dict, theme: dict):
    L = get_layout("icon_grid_3")
    header_band = Region(0, 0, 16, 1.1)
    add_rect(slide, header_band, theme["primary"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=26, color=theme["white"], bold=True)
    points = slide_data.get("display_points", ["", "", ""])
    colors = [theme["primary"], theme["accent"], RGBColor(0x11, 0x7A, 0x65)]
    for i, card_region in enumerate(L["cards"]):
        add_rect(slide, card_region, colors[i % 3])
        num_region  = Region(card_region.left + 0.2, card_region.top + 0.3, 1.0, 1.0)
        text_region = Region(card_region.left + 0.2, card_region.top + 1.4,
                             card_region.width - 0.4, card_region.height - 1.6)
        add_textbox(slide, num_region, str(i + 1),
                    font_size=48, color=theme["white"], bold=True)
        text = points[i] if i < len(points) else ""
        add_textbox(slide, text_region, text,
                    font_size=16, color=theme["white"], auto_size=True)


# -- 5. icon_grid_4 (4-card variant) -----------------------------

def render_icon_grid_4(slide, slide_data: dict, theme: dict):
    L = get_layout("icon_grid_4")
    header_band = Region(0, 0, 16, 1.1)
    add_rect(slide, header_band, theme["primary"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=26, color=theme["white"], bold=True)
    points = slide_data.get("display_points", ["", "", "", ""])
    colors = [theme["primary"], theme["accent"], RGBColor(0x11, 0x7A, 0x65), RGBColor(0x7D, 0x3C, 0x98)]
    for i, card_region in enumerate(L["cards"]):
        add_rect(slide, card_region, colors[i % 4])
        num_region  = Region(card_region.left + 0.2, card_region.top + 0.3, 1.0, 1.0)
        text_region = Region(card_region.left + 0.2, card_region.top + 1.4,
                             card_region.width - 0.4, card_region.height - 1.6)
        add_textbox(slide, num_region, str(i + 1),
                    font_size=48, color=theme["white"], bold=True)
        text = points[i] if i < len(points) else ""
        add_textbox(slide, text_region, text,
                    font_size=14, color=theme["white"], auto_size=True)


# -- 6. stat_callout ---------------------------------------------

def render_stat_callout(slide, slide_data: dict, theme: dict):
    L = get_layout("stat_callout")
    bg = Region(0, 0, 16, 9)
    add_rect(slide, bg, theme["primary"])
    add_rect(slide, L["bg_band"], theme["accent"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=24, color=theme["light"])
    points = slide_data.get("display_points", [""])
    add_textbox(slide, L["stat"], points[0] if points else "",
                font_size=48, color=theme["white"], bold=True,
                align=PP_ALIGN.CENTER, auto_size=True)
    desc = " . ".join(points[1:3]) if len(points) > 1 else ""
    add_textbox(slide, L["desc"], desc,
                font_size=20, color=theme["light"], align=PP_ALIGN.CENTER)


# -- 7. quote_highlight ------------------------------------------

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


# -- 8. text_focus (dual-column text) ----------------------------

def render_text_focus(slide, slide_data: dict, theme: dict):
    L = get_layout("text_focus")
    header_band = Region(0, 0, 16, 1.1)
    add_rect(slide, header_band, theme["primary"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=26, color=theme["white"], bold=True)
    points = slide_data.get("display_points", [])
    mid = max(1, len(points) // 2)
    add_bullet_points(slide, L["col1"], points[:mid], theme=theme)
    add_bullet_points(slide, L["col2"], points[mid:], theme=theme)


# -- 9. section_divider ------------------------------------------

def render_section_divider(slide, slide_data: dict, theme: dict):
    L = get_layout("section_divider")
    add_rect(slide, L["bg_rect"], theme["primary"])
    add_rect(slide, L["deco_line"], theme["accent"])
    add_textbox(slide, L["title"], slide_data["title"],
                font_size=40, color=theme["white"], bold=True,
                align=PP_ALIGN.LEFT)
    points = slide_data.get("display_points") or [""]
    add_textbox(slide, L["subtitle"], points[0],
                font_size=20, color=theme["light"],
                align=PP_ALIGN.LEFT)


# -- Dispatch table -----------------------------------------------

RENDERERS = {
    "title_hero":         render_title_hero,
    "two_column":         render_two_column,
    "content_with_image": render_content_with_image,
    "icon_grid_3":        render_icon_grid_3,
    "icon_grid_4":        render_icon_grid_4,
    "stat_callout":       render_stat_callout,
    "quote_highlight":    render_quote_highlight,
    "text_focus":         render_text_focus,
    "section_divider":    render_section_divider,
}


def render_slide(slide, slide_data: dict, image_bytes=None, theme: dict = None):
    layout_id = slide_data.get("layout_id", "text_focus")
    # degrade content_with_image -> two_column when no image available
    if image_bytes is None and layout_id == "content_with_image":
        layout_id = "two_column"
    renderer = RENDERERS.get(layout_id, render_text_focus)
    if layout_id == "content_with_image":
        renderer(slide, slide_data, theme, image_bytes)
    else:
        renderer(slide, slide_data, theme)
