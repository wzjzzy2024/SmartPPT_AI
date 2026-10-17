"""
Low-level python-pptx rendering primitives.
All coordinates use Region dataclass from layout_engine.
Theme colors are (r,g,b) tuples from config.py, converted to RGBColor here.
"""
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn
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


def shade(color, factor: float) -> tuple:
    """Darken a color by multiplying each channel by factor (0..1)."""
    rgb = _to_rgb(color)
    return tuple(max(0, min(255, int(c * factor))) for c in (rgb[0], rgb[1], rgb[2]))


def lighten(color, factor: float) -> tuple:
    """Blend a color toward white by factor (0..1)."""
    rgb = _to_rgb(color)
    return tuple(
        max(0, min(255, c + int((255 - c) * factor)))
        for c in (rgb[0], rgb[1], rgb[2])
    )


def _apply_gradient(shape, color1, color2, angle_deg: float) -> None:
    """Fill an existing shape with an explicit two-stop linear gradient."""
    try:
        fill = shape.fill
        fill.gradient()
        stops = fill.gradient_stops
        if len(stops) == 2:
            stops[0].color.rgb = _to_rgb(color1)
            stops[0].position = 0.0
            stops[1].color.rgb = _to_rgb(color2)
            stops[1].position = 1.0
            fill.gradient_angle = angle_deg
        else:  # unexpected template: keep a usable solid fill
            fill.solid()
            fill.fore_color.rgb = _to_rgb(color1)
    except Exception:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _to_rgb(color1)
    shape.line.fill.background()


def add_gradient_rect(slide, region: Region, color1, color2,
                      angle_deg: float = 0.0) -> object:
    """Add a two-stop linear-gradient rectangle (0° = left→right, 90° = bottom→top)."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    _apply_gradient(shape, color1, color2, angle_deg)
    return shape


def add_gradient_round_rect(slide, region: Region, color1, color2,
                            angle_deg: float = 0.0,
                            radius: float = 0.08) -> object:
    """Add a two-stop linear-gradient rounded rectangle."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    _apply_gradient(shape, color1, color2, angle_deg)
    try:
        shape.adjustments[0] = radius
    except Exception:
        pass
    return shape


def _inject_alpha(color_parent, alpha_pct: float) -> None:
    """Append <a:alpha> to a srgbClr/schemeClr element (alpha_pct 0..100)."""
    for old in color_parent.findall(qn("a:alpha")):
        color_parent.remove(old)
    alpha = color_parent.makeelement(
        qn("a:alpha"), {"val": str(int(alpha_pct * 1000))}
    )
    color_parent.append(alpha)


def set_fill_alpha(shape, alpha_pct: float) -> None:
    """Apply transparency to a solid-filled shape (no-op on other fill types)."""
    try:
        spPr = shape._element.spPr
        solid = spPr.find(qn("a:solidFill"))
        if solid is None:
            return
        color = solid.find(qn("a:srgbClr"))
        if color is None:
            color = solid.find(qn("a:schemeClr"))
        if color is not None:
            _inject_alpha(color, alpha_pct)
    except Exception:
        pass


def set_gradient_stop_alpha(shape, alpha_pct: float) -> None:
    """Apply the same transparency to every stop of a gradient fill."""
    try:
        grad = shape._element.spPr.find(qn("a:gradFill"))
        if grad is None:
            return
        for color in grad.iter(qn("a:srgbClr")):
            _inject_alpha(color, alpha_pct)
    except Exception:
        pass


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


def add_round_rect(slide, region: Region, color, radius: float = 0.08) -> object:
    """Add a filled rounded rectangle. radius is 0..0.5 (corner ratio)."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _to_rgb(color)
    shape.line.fill.background()
    try:
        shape.adjustments[0] = radius
    except Exception:
        pass
    return shape


def add_oval(slide, region: Region, color=None, outline=None,
             line_width: float = 2.0) -> object:
    """Add an oval. color=None -> no fill; outline=None -> no border."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.OVAL,
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    if color is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _to_rgb(color)
    if outline is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _to_rgb(outline)
        shape.line.width = Pt(line_width)
    return shape


def add_line(slide, x1: float, y1: float, x2: float, y2: float,
             color, width_pt: float = 2.0) -> object:
    """Add a straight connector line between two points (inches)."""
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1), Inches(y1), Inches(x2), Inches(y2),
    )
    line.line.color.rgb = _to_rgb(color)
    line.line.width = Pt(width_pt)
    return line


def add_hline(slide, region: Region, color, width_pt: float = 2.0) -> object:
    """Add a horizontal rule described by a Region."""
    y = region.top + region.height / 2
    return add_line(slide, region.left, y,
                    region.left + region.width, y, color, width_pt)


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


def _set_bullet(paragraph, char: str = "•") -> None:
    """Attach a visible bullet char with hanging indent to a paragraph.

    Schema order matters: buFont/buChar must sit before defRPr.
    """
    pPr = paragraph._p.get_or_add_pPr()
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    buFont = pPr.makeelement(qn("a:buFont"), {"typeface": "Arial"})
    buChar = pPr.makeelement(qn("a:buChar"), {"char": char})
    defRPr = pPr.find(qn("a:defRPr"))
    if defRPr is not None:
        defRPr.addprevious(buFont)
        defRPr.addprevious(buChar)
    else:
        pPr.append(buFont)
        pPr.append(buChar)
    # hanging indent: bullet at 0.25", text aligned at 0.25"
    pPr.set("marL", "228600")
    pPr.set("indent", "-228600")


def add_bullet_points(slide, region: Region, points: list,
                      base_font_size: int = 16, color=None,
                      theme: dict = None):
    """Add bullet points list with visible native bullet formatting."""
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
        _set_bullet(p)
    return txBox


def add_text_lines(slide, region: Region, lines: list, font_size: int = 22,
                   color=None, bold=False, align=PP_ALIGN.LEFT,
                   line_spacing: float = 1.2, theme: dict = None):
    """Add a bullet-free multi-paragraph text box (e.g. TOC entries)."""
    if color is None:
        color = theme["text"] if theme else (0x1C, 0x28, 0x33)
    txBox = slide.shapes.add_textbox(
        Inches(region.left), Inches(region.top),
        Inches(region.width), Inches(region.height),
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    lines = [str(x) for x in (lines or [])]
    if not lines:
        return txBox

    height_per_line = region.height / max(len(lines), 1)
    for i, line in enumerate(lines):
        size = adaptive_font_size(line, region.width, height_per_line, font_size)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = _to_rgb(color)
        p.font.name = _FONT_NAME
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_before = Pt(6)
    return txBox


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


def add_image_fit(slide, region: Region, image_bytes: BytesIO):
    """Embed an image contained in region at its native aspect ratio.

    Unsplash returns landscape photos while slide regions are often more
    square; filling the region would stretch faces/scenes. Letterboxing
    inside the (usually tinted) region keeps the subject undistorted.
    """
    if image_bytes is None:
        return None
    try:
        image_bytes.seek(0)
        pic = slide.shapes.add_picture(
            image_bytes, Inches(region.left), Inches(region.top))
        box_w = int(Inches(region.width))
        box_h = int(Inches(region.height))
        ratio = pic.width / pic.height
        if ratio >= box_w / box_h:
            width = box_w
            height = int(round(box_w / ratio))
        else:
            height = box_h
            width = int(round(box_h * ratio))
        pic.width = width
        pic.height = height
        pic.left = int(Inches(region.left) + (box_w - width) / 2)
        pic.top = int(Inches(region.top) + (box_h - height) / 2)
        return pic
    except Exception:
        return None  # corrupted image, skip silently
