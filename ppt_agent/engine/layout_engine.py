"""
Layout Engine: layout_id -> Region coordinates for each element.
All coordinates are in inches for a 16:9 (16x9 inch) slide.
"""
from dataclasses import dataclass


@dataclass
class Region:
    left: float
    top: float
    width: float
    height: float


# Shared header band for content-style layouts (single source of truth).
HEADER_BAND = Region(0.0, 0.0, 16.0, 1.1)

LAYOUTS = {
    # -- structural layouts --------------------------------------
    "cover": {
        "bg_rect":       Region(0.0, 0.0, 16.0, 9.0),
        "deco_circle_1": Region(10.8, -2.2, 6.5, 6.5),
        "deco_circle_2": Region(12.6, 3.2, 3.4, 3.4),
        "deco_circle_3": Region(-1.8, 5.8, 4.6, 4.6),
        "rule":          Region(6.75, 4.42, 2.5, 0.07),
        "title":         Region(2.0, 2.7, 12.0, 1.6),
        "subtitle":      Region(2.0, 4.7, 12.0, 0.9),
    },
    "toc": {
        "accent_bar":    Region(0.0, 0.0, 0.35, 9.0),
        "title":         Region(1.0, 0.6, 8.0, 1.1),
        "rule":          Region(1.0, 1.75, 3.0, 0.08),
        "col1":          Region(1.0, 2.3, 7.2, 6.2),
        "col2":          Region(8.4, 2.3, 7.2, 6.2),
        "deco_circle":   Region(12.8, -1.8, 4.2, 4.2),
    },
    "thanks": {
        "bg_rect":       Region(0.0, 0.0, 16.0, 9.0),
        "deco_circle_1": Region(-1.6, -2.0, 5.0, 5.0),
        "deco_circle_2": Region(12.8, 6.2, 4.6, 4.6),
        "deco_ring":     Region(10.6, 1.6, 2.2, 2.2),
        "rule":          Region(6.75, 4.5, 2.5, 0.07),
        "title":         Region(2.0, 2.9, 12.0, 1.4),
        "subtitle":      Region(2.0, 4.75, 12.0, 0.8),
    },
    "section_divider": {
        "bg_rect":       Region(0.0, 0.0, 16.0, 9.0),
        "title":         Region(2.0, 3.0, 12.0, 1.5),
        "subtitle":      Region(2.0, 4.8, 12.0, 1.0),
        "deco_line":     Region(2.0, 4.5, 4.0, 0.06),
    },

    # -- content layouts -----------------------------------------
    "content_with_image": {
        "header_band":   HEADER_BAND,
        "title":         Region(0.5, 0.2, 14.3, 0.8),
        "body":          Region(0.5, 1.2, 8.5, 6.5),
        "image_panel":   Region(9.2, 2.3, 6.3, 4.3),
        "image_accent":  Region(9.05, 2.3, 0.06, 4.3),
        "image":         Region(9.2, 2.3, 6.3, 4.3),
    },
    "content_decor": {
        "header_band":   HEADER_BAND,
        "title":         Region(0.5, 0.2, 14.3, 0.8),
        "body":          Region(0.5, 1.5, 8.4, 6.4),
        "panel":         Region(9.2, 1.4, 6.3, 6.6),
        "deco_circle_1": Region(10.3, 2.2, 1.6, 1.6),
        "deco_circle_2": Region(13.0, 2.0, 1.2, 1.2),
        "deco_ring":     Region(13.2, 6.4, 1.4, 1.4),
        "deco_circle_3": Region(10.5, 6.2, 1.2, 1.2),
        "page_num":      Region(10.2, 4.0, 5.0, 1.5),
    },
    "two_column": {
        "header_band":   HEADER_BAND,
        "title":         Region(0.5, 0.2, 14.3, 0.8),
        "left":          Region(0.5, 1.2, 7.0, 6.5),
        "right":         Region(8.5, 1.2, 7.0, 6.5),
    },
    "icon_grid_3": {
        "header_band":   HEADER_BAND,
        "title":         Region(0.5, 0.2, 14.3, 0.8),
        "cards":         [Region(0.5, 1.2, 4.5, 5.5), Region(5.75, 1.2, 4.5, 5.5), Region(11.0, 1.2, 4.5, 5.5)],
    },
    "icon_grid_4": {
        "header_band":   HEADER_BAND,
        "title":         Region(0.5, 0.2, 14.3, 0.8),
        "cards":         [Region(0.5, 1.2, 3.5, 5.5), Region(4.5, 1.2, 3.5, 5.5), Region(8.5, 1.2, 3.5, 5.5), Region(12.5, 1.2, 3.5, 5.5)],
    },
    "stat_callout": {
        "title":         Region(1.0, 0.3, 14.0, 0.8),
        "stat":          Region(2.0, 1.8, 12.0, 3.5),
        "desc":          Region(2.0, 5.3, 12.0, 1.7),
        "bg_band":       Region(0.0, 8.0, 16.0, 1.0),
    },
    "quote_highlight": {
        "title":         Region(1.5, 0.2, 13.0, 0.8),
        "side_band":     Region(0.0, 0.0, 0.6, 9.0),
        "quote_mark":    Region(1.2, 1.2, 2.0, 2.0),
        "body":          Region(1.5, 3.2, 13.0, 4.5),
    },
    "text_focus": {
        "header_band":   HEADER_BAND,
        "title":         Region(1.0, 0.3, 14.0, 0.8),
        "col1":          Region(1.0, 1.4, 6.8, 6.5),
        "col2":          Region(8.2, 1.4, 6.8, 6.5),
    },
    "data_chart": {
        "header_band":   HEADER_BAND,
        "title":         Region(0.5, 0.2, 14.3, 0.8),
        "body":          Region(0.5, 1.4, 8.2, 6.4),
        "chart":         Region(8.9, 1.4, 6.6, 6.4),
    },
}


def get_layout(layout_id: str) -> dict:
    return LAYOUTS.get(layout_id, LAYOUTS["text_focus"])
