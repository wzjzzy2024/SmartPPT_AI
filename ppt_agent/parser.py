"""
Markdown / plain-text parser.
Reads a Markdown outline or pasted text, identifies heading levels,
auto-paginates by H2, and outputs structured slide data.
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


def parse_markdown(text: str) -> list[dict]:
    """Parse Markdown text into a list of slide dicts.

    Rules:
      - H1 (#)  -> title_hero page (only the first H1)
      - H2 (##) -> new page start
      - H3 (###) -> bullet points under current H2
      - Plain text lines -> auto-paginated into pages

    Returns:
        list of dicts with keys: title, display_points, layout_id,
        needs_image, image_topic, key_points, logic_role
    """
    lines = text.strip().splitlines()
    pages: list[dict] = []
    current_page = None
    first_h1 = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        h1_match = re.match(r'^#\s+(.+)$', stripped)
        h2_match = re.match(r'^##\s+(.+)$', stripped)
        h3_match = re.match(r'^###\s+(.+)$', stripped)

        if h1_match:
            title = h1_match.group(1).strip()[:50]
            if first_h1:
                pages.append({
                    "title": title,
                    "display_points": [],
                    "layout_id": "title_hero",
                    "needs_image": False,
                    "image_topic": "",
                    "key_points": [],
                    "logic_role": "封面/主题引入",
                })
                first_h1 = False
            else:
                if current_page:
                    pages.append(current_page)
                current_page = {
                    "title": title,
                    "display_points": [],
                    "layout_id": "section_divider",
                    "needs_image": False,
                    "image_topic": "",
                    "key_points": [],
                    "logic_role": "章节分隔",
                }
        elif h2_match:
            if current_page:
                pages.append(current_page)
            title = h2_match.group(1).strip()[:50]
            current_page = {
                "title": title,
                "display_points": [],
                "layout_id": "text_focus",
                "needs_image": False,
                "image_topic": "",
                "key_points": [],
                "logic_role": "内容页",
            }
        elif h3_match:
            point = h3_match.group(1).strip()
            if current_page is None:
                current_page = {
                    "title": point[:50],
                    "display_points": [],
                    "layout_id": "text_focus",
                    "needs_image": False,
                    "image_topic": "",
                    "key_points": [],
                    "logic_role": "内容页",
                }
            else:
                current_page["display_points"].append(point)
                current_page["key_points"].append(point)
        else:
            if current_page is None:
                current_page = {
                    "title": stripped[:50],
                    "display_points": [],
                    "layout_id": "text_focus",
                    "needs_image": False,
                    "image_topic": "",
                    "key_points": [],
                    "logic_role": "内容页",
                }
            current_page["display_points"].append(stripped)
            current_page["key_points"].append(stripped)

    if current_page:
        pages.append(current_page)

    # Post-process: fill defaults and infer layout
    for i, page in enumerate(pages):
        page.setdefault("index", i + 1)
        page.setdefault("speaker_notes", "")
        page.setdefault("needs_image", False)
        page.setdefault("image_topic", "")

        if page["layout_id"] not in ("title_hero", "section_divider"):
            if not page["image_topic"]:
                page["image_topic"] = page["title"]
            # Only auto-switch to content_with_image when needs_image
            # was NOT explicitly set by the caller
            if page["needs_image"] is False and len(page["display_points"]) <= 3:
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
        pages.append({
            "title": title,
            "display_points": chunk,
            "layout_id": "text_focus",
            "needs_image": False,
            "image_topic": "",
            "key_points": chunk,
            "logic_role": "内容页",
        })

    for i, page in enumerate(pages):
        page["index"] = i + 1

    return pages
