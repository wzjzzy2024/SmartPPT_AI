"""
Adaptive font size calculator. Handles CJK and Latin text separately.
"""
import math


def adaptive_font_size(text: str, box_width_inch: float, box_height_inch: float,
                       base_size: int = 18, min_size: int = 10) -> int:
    """
    Calculate appropriate font size to fit text within given box dimensions.
    Chinese characters are ~2x wider than Latin, handled separately.
    """
    # CJK Unified Ideographs range (covers all common Chinese characters)
    cn_chars = sum(1 for c in text if "一" <= c <= "鿿"
                   or "　" <= c <= "〿"
                   or "＀" <= c <= "￯")
    en_chars = len(text) - cn_chars
    # per pt: Chinese char ~ 0.75pt wide, English char ~ 0.5pt wide
    avg_char_width_pt = (cn_chars * 0.75 + en_chars * 0.5) / max(len(text), 1)

    box_width_pt  = box_width_inch  * 72
    box_height_pt = box_height_inch * 72

    size = base_size
    for _ in range(20):
        char_w = size * avg_char_width_pt
        if char_w <= 0:
            size = min_size
            break
        chars_per_line = max(1, box_width_pt / char_w)
        lines = math.ceil(len(text) / chars_per_line)
        line_h = size * 1.4
        if lines * line_h <= box_height_pt:
            break
        size -= 1
        if size <= min_size:
            size = min_size
            break
    return size
