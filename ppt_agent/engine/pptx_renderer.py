"""
Low-level python-pptx rendering primitives.
All coordinates use Region dataclass from layout_engine.
Theme colors are (r,g,b) tuples from config.py, converted to RGBColor here.
"""
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from io import BytesIO

from engine.layout_engine import Region
from utils.font_size import adaptive_font_size

# Cross-platform Chinese font fallback (use first candidate on Windows)
_FONT_CANDIDATES = ["微软雅黑", "Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "PingFang SC"]
_FONT_NAME = _FONT_CANDIDATES[0]


def _to_rgb(color) -> RGBColor:
    """Convert (r,g,b) tuple or RGBColor to RGBColor."""
    if isinstance(color, RGBColor):
        return color
    if isinstance(color, (tuple, list)) and len(color) == 3:
        return RGBColor(color[0], color[1], color[2])
    return RGBColor(0x1C, 0x28, 0x33)  # fallback dark text


def add_rect(slide, region: Region, color) -> object:
    """Add a filled rectangle shape."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _to_rgb(color)
    shape.line.fill.background()
    return shape


def add_textbox(slide, region: Region, text: str, font_size: int,
                color, bold=False, align=PP_ALIGN.LEFT,
                auto_size=False) -> object:
    """Add a text box with optional auto-sizing."""
    txBox = slide.shapes.add_textbox(
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    if auto_size:
        font_size = adaptive_font_size(text, region.width, region.height, font_size)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = _to_rgb(color)
    run.font.name = _FONT_NAME
    return txBox


def add_bullet_points(slide, region: Region, points: list,
                      base_font_size: int = 16, color=None,
                      theme: dict = None):
    """Add bullet points list with native python-pptx bullet formatting."""
    if color is None:
        color = theme["text"] if theme else (0x1C, 0x28, 0x33)
    txBox = slide.shapes.add_textbox(
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    tf = txBox.text_frame
    tf.word_wrap = True

    height_per_point = region.height / max(len(points), 1)

    for i, point in enumerate(points):
        font_size = adaptive_font_size(point, region.width, height_per_point, base_font_size)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = point
        p.font.size = Pt(font_size)
        p.font.color.rgb = _to_rgb(color)
        p.font.name = _FONT_NAME
        p.space_before = Pt(4)
        p.level = 0  # bullet level


def add_image(slide, region: Region, image_bytes: BytesIO):
    """Embed image directly from BytesIO, no disk path involved."""
    if image_bytes is None:
        return
    try:
        image_bytes.seek(0)
        slide.shapes.add_picture(
            image_bytes,
            Inches(region.left), Inches(region.top),
            Inches(region.width), Inches(region.height),
        )
    except Exception:
        pass  # corrupted image, skip silently
