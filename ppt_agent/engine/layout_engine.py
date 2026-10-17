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


LAYOUTS = {
    "title_hero": {
        "title":     Region(1.0, 2.8, 10.0, 1.8),
        "subtitle":  Region(1.0, 4.8, 10.0, 1.2),
        "bg_rect":   Region(0.0, 0.0, 16.0, 9.0),
        "deco_rect": Region(13.0, 7.0, 2.5, 1.5),
    },
    "content_with_image": {
        "title":  Region(0.5, 0.2, 15.0, 0.8),
        "body":   Region(0.5, 1.2,  8.5, 6.5),
        "image":  Region(9.2, 1.0,  6.3, 7.0),
    },
    "two_column": {
        "title":  Region(0.5, 0.2, 15.0, 0.8),
        "left":   Region(0.5, 1.2,  7.0, 6.5),
        "right":  Region(8.5, 1.2,  7.0, 6.5),
    },
    "icon_grid_3": {
        "title":  Region(0.5, 0.2, 15.0, 0.8),
        "cards":  [Region(0.5, 1.2, 4.5, 5.5), Region(5.75, 1.2, 4.5, 5.5), Region(11.0, 1.2, 4.5, 5.5)],
    },
    "icon_grid_4": {
        "title":  Region(0.5, 0.2, 15.0, 0.8),
        "cards":  [Region(0.5, 1.2, 3.5, 5.5), Region(4.5, 1.2, 3.5, 5.5), Region(8.5, 1.2, 3.5, 5.5), Region(12.5, 1.2, 3.5, 5.5)],
    },
    "stat_callout": {
        "title":   Region(1.0, 0.3, 14.0, 0.8),
        "stat":    Region(2.0, 1.8, 12.0, 3.5),
        "desc":    Region(2.0, 5.5, 12.0, 1.5),
        "bg_band": Region(0.0, 8.0, 16.0, 1.0),
    },
    "quote_highlight": {
        "title":      Region(1.5, 0.2, 13.0, 0.8),
        "side_band":  Region(0.0, 0.0,  0.6, 9.0),
        "quote_mark": Region(1.2, 1.2,  2.0, 2.0),
        "body":       Region(1.5, 3.2, 13.0, 4.5),
    },
    "text_focus": {
        "title":  Region(1.0, 0.3, 14.0, 0.8),
        "col1":   Region(1.0, 1.4,  6.8, 6.5),
        "col2":   Region(8.2, 1.4,  6.8, 6.5),
    },
    "section_divider": {
        "bg_rect":   Region(0.0, 0.0, 16.0, 9.0),
        "title":     Region(2.0, 3.0, 12.0, 1.5),
        "subtitle":  Region(2.0, 4.8, 12.0, 1.0),
        "deco_line": Region(2.0, 4.5, 4.0, 0.06),
    },
}


def get_layout(layout_id: str) -> dict:
    return LAYOUTS.get(layout_id, LAYOUTS["text_focus"])
