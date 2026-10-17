"""
Markdown / plain-text parser.
Reads a Markdown outline or pasted text, identifies heading levels,
auto-paginates by H2, and outputs page_type-tagged slide data.

Structure (cover/toc/summary/thanks) is completed later by
utils.outline.normalize_outline; this module only tags what it sees.
"""
import re
import logging
from pathlib import Path

logger = logging.getLogger("smartppt.parser")


def _is_markdown(text: str) -> bool:
    """Heuristic: does the text look like Markdown?"""
    for line in text.strip().splitlines()[:20]:
        if re.match(r'^#{1,6}\s+', line.strip()):
            return True
    return False


def _content_page(title: str, section_id, section_title: str) -> dict:
    return {
        "page_type": "content",
        "title": title,
        "subtitle": "",
        "section_id": section_id,
        "section_title": section_title,
        "display_points": [],
        "layout_id": "text_focus",
        "needs_image": False,
        "image_topic": "",
        "key_points": [],
        "logic_role": "内容页",
    }


def parse_markdown(text: str) -> list[dict]:
    """Parse Markdown text into a list of page dicts.

    Rules:
      - First H1       -> cover page
      - Later H1       -> section divider + new section context
      - H2             -> new content page under the current section
      - H3 / plain text -> bullet points under the current content page

    Returns:
        list of page dicts (page_type, title, subtitle, section_id,
        section_title, key_points, display_points, layout_id, needs_image,
        image_topic, logic_role)
    """
    lines = text.strip().splitlines()
    pages: list[dict] = []
    current_page = None
    first_h1 = True
    section_id = 0
    section_title = "主要内容"

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        h1_match = re.match(r'^#\s+(.+)$', stripped)
        h2_match = re.match(r'^##\s+(.+)$', stripped)
        h3_match = re.match(r'^###\s+(.+)$', stripped)

        if h1_match:
            title = h1_match.group(1).strip()[:50]
            if current_page:
                pages.append(current_page)
                current_page = None
            if first_h1:
                pages.append({
                    "page_type": "cover",
                    "title": title,
                    "subtitle": "",
                    "display_points": [],
                    "layout_id": "cover",
                    "needs_image": False,
                    "image_topic": "",
                    "key_points": [],
                    "logic_role": "封面/主题引入",
                })
                first_h1 = False
            else:
                section_id += 1
                section_title = title
                pages.append({
                    "page_type": "section",
                    "title": title,
                    "subtitle": "",
                    "section_id": section_id,
                    "section_title": section_title,
                    "display_points": [],
                    "layout_id": "section_divider",
                    "needs_image": False,
                    "image_topic": "",
                    "key_points": [],
                    "logic_role": "章节分隔",
                })
        elif h2_match:
            if current_page:
                pages.append(current_page)
            current_page = _content_page(
                h2_match.group(1).strip()[:50], section_id, section_title
            )
        elif h3_match:
            point = h3_match.group(1).strip()
            if current_page is None:
                current_page = _content_page(point[:50], section_id, section_title)
            current_page["display_points"].append(point)
            current_page["key_points"].append(point)
        else:
            if current_page is None:
                current_page = _content_page(stripped[:50], section_id, section_title)
            current_page["display_points"].append(stripped)
            current_page["key_points"].append(stripped)

    if current_page:
        pages.append(current_page)

    # Fill defaults and auto-assign image layouts for sparse content pages.
    for i, page in enumerate(pages):
        page.setdefault("index", i + 1)
        page.setdefault("speaker_notes", "")
        page.setdefault("needs_image", False)
        page.setdefault("image_topic", "")

        if page["page_type"] == "content":
            if not page["image_topic"]:
                page["image_topic"] = page["title"]
            if not page["needs_image"] and len(page["display_points"]) <= 3:
                page["layout_id"] = "content_with_image"
                page["needs_image"] = True

    logger.info("Parsed Markdown -> %d slides", len(pages))
    return pages


def parse_file(filepath: str) -> list[dict]:
    """Read a file (.md or plain text) and parse into slides."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    text = path.read_text(encoding="utf-8")
    return parse_markdown(text)


def plain_text_to_slides(text: str) -> list[dict]:
    """Parse plain text (no Markdown headings) into auto-paginated slides."""
    text = text.strip()
    if not text:
        return []

    numbered = re.split(r'\n\s*\d+[.、]\s*', text)
    numbered = [p.strip() for p in numbered if p.strip()]

    if len(numbered) > 1:
        points = numbered
    else:
        points = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    if not points:
        points = [text]

    PAGE_SIZE = 5
    pages = []
    for chunk_start in range(0, len(points), PAGE_SIZE):
        chunk = points[chunk_start:chunk_start + PAGE_SIZE]
        title = chunk[0][:50] if chunk[0] else "内容页"
        page = _content_page(title, 1, "主要内容")
        page["display_points"] = chunk
        page["key_points"] = chunk
        pages.append(page)

    for i, page in enumerate(pages):
        page["index"] = i + 1

    return pages
