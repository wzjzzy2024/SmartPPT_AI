"""
Outline normalization: the single structural choke point shared by
LLM-planned outlines and parsed Markdown/plain-text inputs.

After this module runs, every input path produces the same slide dict shape:

    cover -> toc -> (section) content/summary ... -> summary -> thanks

Structural pages (TOC entries, Thank You, summary insertion, slide cap) are
generated deterministically here, so the LLM never owns page structure.
"""
import logging

from config import (
    DEFAULT_LAYOUTS,
    IMAGE_LAYOUTS,
    MAX_SLIDES,
    PAGE_TYPE_LAYOUTS,
    PAGE_TYPES,
)

logger = logging.getLogger("smartppt.outline")

_STRUCTURAL = {"cover", "toc", "thanks"}


def flatten_sections(outline: dict) -> list[dict]:
    """Flatten planner sections into a page list with section metadata."""
    slides = []
    for section in outline.get("sections", []):
        sid = section.get("section_id")
        stitle = section.get("section_title", "")
        srole = section.get("section_role", "")
        for page in section.get("pages", []):
            p = dict(page)
            p["section_id"] = sid
            p["section_title"] = stitle
            p.setdefault("section_role", srole)
            slides.append(p)
    return slides


def _blank_page(page_type: str, title: str, layout_id: str, **extra) -> dict:
    page = {
        "page_type": page_type,
        "title": title,
        "subtitle": "",
        "layout_id": layout_id,
        "logic_role": "",
        "key_points": [],
        "display_points": [],
        "speaker_notes": "",
        "needs_image": False,
        "image_topic": "",
        "section_id": None,
        "section_title": "",
    }
    page.update(extra)
    return page


def _make_cover(topic: str, first: dict | None) -> dict:
    subtitle = ""
    if first is not None:
        subtitle = first.get("subtitle") or first.get("title") or ""
    return _blank_page("cover", topic or "演示文稿", "cover",
                       subtitle=subtitle, logic_role="封面")


def _make_toc() -> dict:
    return _blank_page("toc", "目录", "toc", logic_role="目录")


def _make_summary(pages: list[dict]) -> dict:
    """Summary page: one first key_point per section, deterministic."""
    seen = set()
    points = []
    last_sid = None
    last_title = ""
    for p in pages:
        if p.get("page_type") != "content":
            continue
        sid = p.get("section_id")
        last_sid, last_title = sid, p.get("section_title", "")
        if sid in seen:
            continue
        seen.add(sid)
        kp = p.get("key_points") or p.get("display_points") or []
        if kp:
            points.append(str(kp[0]))
    if not points:
        points = [
            p.get("title", "") for p in pages
            if p.get("page_type") == "content" and p.get("title")
        ][:4]
    return _blank_page(
        "summary", "总结与展望", "stat_callout",
        logic_role="结论总结",
        key_points=points[:5],
        display_points=points[:5],
        section_id=last_sid,
        section_title=last_title,
    )


def _make_thanks() -> dict:
    return _blank_page("thanks", "Thank You", "thanks",
                       subtitle="感谢观看 · Q & A", logic_role="致谢")


_THANKS_WORDS = ("感谢", "致谢", "谢谢", "thank", "q&a", "q & a", "qa")


def _is_thanks_like(page: dict) -> bool:
    text = f"{page.get('title') or ''} {page.get('subtitle') or ''}".lower()
    return any(word in text for word in _THANKS_WORDS)


_SUMMARY_WORDS = ("总结", "结论", "小结", "summary")


def _summary_like_in_tail(pages: list[dict]) -> list[dict]:
    """Content pages in the final section whose title marks them as a summary."""
    last_section = -1
    for i, p in enumerate(pages):
        if p["page_type"] == "section":
            last_section = i
    tail = pages[last_section + 1:] if last_section >= 0 else pages
    return [
        p for p in tail
        if p["page_type"] == "content"
        and any(w in (p.get("title") or "").lower() for w in _SUMMARY_WORDS)
    ]


def _cleanup_structural(pages: list[dict]) -> list[dict]:
    """Remove duplicated structural pages emitted by the planner."""
    # Keep only the last thanks page.
    thanks_idx = [i for i, p in enumerate(pages) if p["page_type"] == "thanks"]
    for i in reversed(thanks_idx[:-1]):
        pages.pop(i)

    # A trailing section divider titled "致谢" is a closing page, not a real
    # section (only check the last few pages to avoid false positives).
    tail_start = max(0, len(pages) - 3)
    pages = [
        p for i, p in enumerate(pages)
        if not (i >= tail_start and p["page_type"] == "section"
                and _is_thanks_like(p))
    ]

    # Keep only the first TOC.
    toc_idx = [i for i, p in enumerate(pages) if p["page_type"] == "toc"]
    for i in reversed(toc_idx[1:]):
        pages.pop(i)
    return pages


def _validate_slide(page: dict, index: int) -> None:
    """Fill defaults and correct page_type/layout/needs_image in place."""
    page_type = page.get("page_type")
    if page_type not in PAGE_TYPES:
        if index == 0:
            page_type = "cover"
        elif page.get("layout_id") == "section_divider":
            page_type = "section"
        else:
            page_type = "content"
        page["page_type"] = page_type

    layout_id = page.get("layout_id")
    if layout_id not in PAGE_TYPE_LAYOUTS[page_type]:
        layout_id = DEFAULT_LAYOUTS[page_type]
    page["layout_id"] = layout_id

    page.setdefault("title", "")
    page.setdefault("subtitle", "")
    page.setdefault("logic_role", "")
    page.setdefault("speaker_notes", "")
    page.setdefault("section_id", None)
    page.setdefault("section_title", "")
    if not isinstance(page.get("key_points"), list):
        page["key_points"] = []
    if not isinstance(page.get("display_points"), list):
        page["display_points"] = []

    # Only content pages with an image-capable layout may fetch images.
    needs_image = (
        bool(page.get("needs_image"))
        and page_type == "content"
        and layout_id in IMAGE_LAYOUTS
    )
    page["needs_image"] = needs_image
    if needs_image:
        if not page.get("image_topic"):
            page["image_topic"] = page.get("title", "")
    else:
        page["image_topic"] = ""

    # Structural pages have deterministic content.
    if page_type == "thanks":
        page["title"] = "Thank You"
        page["subtitle"] = page.get("subtitle") or "感谢观看 · Q & A"
        page["key_points"] = []
        page["display_points"] = []
    elif page_type == "toc":
        page["title"] = page.get("title") or "目录"
        page["key_points"] = []
    elif page_type == "cover":
        page["key_points"] = []
        page["display_points"] = []


def _assign_sections(pages: list[dict]) -> None:
    """Fill section_id/section_title for pages that lack them."""
    divider_count = sum(1 for p in pages if p["page_type"] == "section")
    if divider_count >= 2:
        # Weaker models often return one flat section containing several
        # visible section dividers. Re-segment by the dividers actually shown
        # so the TOC matches what the audience sees.
        next_id = 1
        current_id = None
        current_title = ""
        for page in pages:
            page_type = page["page_type"]
            if page_type in _STRUCTURAL:
                page["section_id"] = None
                page["section_title"] = ""
                continue
            if page_type == "section":
                page["section_id"] = next_id
                page["section_title"] = (
                    page.get("title") or page.get("section_title") or "章节"
                )
                current_id = next_id
                current_title = page["section_title"]
                next_id += 1
                continue
            if current_id is None:
                current_id = next_id
                next_id += 1
                current_title = page.get("section_title") or "主要内容"
            page["section_id"] = current_id
            page["section_title"] = current_title
        return

    next_id = 1
    current = None
    for page in pages:
        page_type = page["page_type"]
        if page_type in _STRUCTURAL:
            page["section_id"] = None
            page["section_title"] = ""
            continue

        if page_type == "section":
            if page.get("section_id") is None:
                page["section_id"] = next_id
                next_id += 1
            else:
                try:
                    next_id = max(next_id, int(page["section_id"]) + 1)
                except (TypeError, ValueError):
                    pass
            page["section_title"] = (
                page.get("section_title") or page.get("title") or "章节"
            )
            current = page
            continue

        sid = page.get("section_id")
        if sid is None:
            if current is not None:
                page["section_id"] = current["section_id"]
                page["section_title"] = current["section_title"]
            else:
                page["section_id"] = next_id
                page["section_title"] = page.get("section_title") or "主要内容"
                current = {"section_id": page["section_id"],
                           "section_title": page["section_title"]}
                next_id += 1
        elif not page.get("section_title"):
            page["section_title"] = (current or {}).get("section_title") or "主要内容"


def _build_sections(pages: list[dict]) -> list[dict]:
    """Sections that actually carry content (structural-only ones excluded)."""
    sections = []
    seen = {}
    for p in pages:
        if p["page_type"] not in ("content", "summary"):
            continue
        sid = p.get("section_id")
        key = ("id", sid) if sid is not None else ("title", p.get("section_title"))
        if key in seen:
            continue
        section = {
            "section_id": len(sections) + 1,
            "section_title": p.get("section_title") or "主要内容",
            "section_role": p.get("section_role", ""),
        }
        seen[key] = section
        sections.append(section)
    return sections


def _toc_entries(pages: list[dict], sections: list[dict]) -> list[str]:
    """TOC entries: section titles, or content-page titles for one-section decks."""
    if len(sections) >= 2:
        return [
            f"{i:02d}  {s['section_title']}"
            for i, s in enumerate(sections, 1)
        ]
    titles = [
        p["title"] for p in pages
        if p["page_type"] == "content" and p.get("title")
    ][:8]
    return [f"{i:02d}  {t}" for i, t in enumerate(titles, 1)]


def _truncate(pages: list[dict]) -> list[dict]:
    """Enforce the hard slide cap by dropping trailing non-structural pages."""
    if len(pages) <= MAX_SLIDES:
        return pages
    pages = list(pages)
    while len(pages) > MAX_SLIDES:
        drop_at = None
        for i in range(len(pages) - 1, -1, -1):
            if pages[i]["page_type"] in ("content", "section"):
                drop_at = i
                break
        if drop_at is None:
            break
        removed = pages.pop(drop_at)
        logger.info("Slide cap reached, dropped: %s", removed.get("title", ""))
    return pages


def _drop_orphan_sections(pages: list[dict]) -> list[dict]:
    """Remove section divider pages whose section no longer has content."""
    counts = {}
    for p in pages:
        if p["page_type"] in ("content", "summary"):
            sid = p.get("section_id")
            counts[sid] = counts.get(sid, 0) + 1
    result = []
    for p in pages:
        if p["page_type"] == "section" and counts.get(p.get("section_id"), 0) == 0:
            continue
        result.append(p)
    return result


def normalize_outline(pages: list[dict], topic: str) -> tuple[list[dict], list[dict]]:
    """Force cover/toc/summary/thanks structure and return (slides, sections)."""
    pages = [dict(p) for p in (pages or []) if isinstance(p, dict)]
    if not pages:
        pages = [_make_cover(topic, None)]

    for i, page in enumerate(pages):
        _validate_slide(page, i)
    pages = _cleanup_structural(pages)

    # 1) cover must be first
    if pages[0]["page_type"] != "cover":
        pages.insert(0, _make_cover(topic, pages[0]))
    elif not pages[0].get("title"):
        pages[0]["title"] = topic or "演示文稿"

    # 2) thanks must be last (drop redundant thanks-like closing pages first)
    if pages[-1]["page_type"] != "thanks":
        while len(pages) > 1 and _is_thanks_like(pages[-1]):
            pages.pop()
        pages.append(_make_thanks())

    # 3) summary before thanks for content-heavy decks
    content_count = sum(
        1 for p in pages if p["page_type"] in ("content", "summary")
    )
    if content_count >= 3 and not any(
        p["page_type"] == "summary" for p in pages
    ):
        candidates = _summary_like_in_tail(pages)
        if candidates:
            # A closing content page already acts as the summary; reclassify it
            # instead of inserting a duplicate summary page.
            summary_page = candidates[-1]
            summary_page["page_type"] = "summary"
            summary_page["needs_image"] = False
            summary_page["image_topic"] = ""
            if summary_page["layout_id"] not in PAGE_TYPE_LAYOUTS["summary"]:
                summary_page["layout_id"] = DEFAULT_LAYOUTS["summary"]
            logger.info("Reclassified closing page as summary: %s",
                        summary_page.get("title", ""))
        else:
            pages.insert(len(pages) - 1, _make_summary(pages))

    # 4) section labels + TOC insertion (content-heavy decks only)
    _assign_sections(pages)
    has_toc = any(p["page_type"] == "toc" for p in pages)
    if not has_toc and content_count >= 3:
        pages.insert(1, _make_toc())

    # 5) hard cap, then clean up sections left empty
    pages = _truncate(pages)
    pages = _drop_orphan_sections(pages)

    # 6) rebuild sections and refresh TOC entries after truncation
    sections = _build_sections(pages)
    entries = _toc_entries(pages, sections)
    for p in pages:
        if p["page_type"] == "toc":
            p["display_points"] = entries
            p["key_points"] = []

    # 7) deterministic final indexes
    for i, p in enumerate(pages, 1):
        p["index"] = i

    logger.info(
        "Normalized outline: %d slides / %d sections (cover=%s, toc=%s, thanks=%s)",
        len(pages), len(sections),
        pages[0]["page_type"], pages[1]["page_type"] if len(pages) > 1 else "-",
        pages[-1]["page_type"],
    )
    return pages, sections
