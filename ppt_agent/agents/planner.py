"""
Planner Agent: topic -> hierarchical outline JSON (sections -> pages).
Uses GLM-4-Plus for planning with retry logic.

The outline is intentionally structural: page_type drives layout and the
TOC/thanks pages are normalized deterministically downstream by
utils/outline.py, so the LLM never invents page numbers.
"""

import logging
from openai import OpenAI
from config import (
    GLM_API_KEY,
    GLM_BASE_URL,
    GLM_DEFAULT_MODEL,
    GLM_STRONG_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT,
    MAX_SLIDES,
    PAGE_TYPES,
    PAGE_TYPE_LAYOUTS,
    DEFAULT_LAYOUTS,
    IMAGE_LAYOUTS,
)
from utils.json_parser import parse_json

logger = logging.getLogger("smartppt.planner")

client = OpenAI(
    api_key=GLM_API_KEY,
    base_url=GLM_BASE_URL.rstrip("/") + "/",
    timeout=LLM_TIMEOUT,
)

SYSTEM_PROMPT = """
你是一位专业的演讲策划师。请为给定主题规划一份完整的演示文稿大纲，只输出一行合法 JSON。

【整体结构】
1. 页面顺序固定：第1页为封面（page_type=cover）；第2页为目录（page_type=toc）；
   中间为章节页（page_type=section）与内容页（page_type=content）；
   倒数第2页为总结页（page_type=summary）；最后一页为致谢页（page_type=thanks）。
2. 章节之间必须有强烈的逻辑递进，section_role 按顺序体现：
   提出问题 → 分析原因 → 给出方案 → 结论总结。
3. 内容页数量由主题复杂程度动态决定，总页数 12~26 张（含结构页），软上限 30 张。
   每个内容页只承载一个核心论点，禁止注水、禁止口水话。
4. 绝对不允许编造 Q&A、观众提问、互动环节等虚构内容；不得杜撰数据。
   致谢页（thanks）只允许出现一次，且不要再额外添加标题为"致谢"的章节页。
5. 封面页与目录页放在第一个章节（章节名可为"开场"），总结页与致谢页放在最后一个章节
   （章节名可为"结论"）；其余章节各自包含章节页与内容页。

【每页字段】
- page_type: cover | toc | section | content | summary | thanks
- title: 中文主标题（不超过20字）
- subtitle: 仅 cover / section 页需要，一句话副标题（不超过25字），其他页为空字符串
- logic_role: 本页在论证中的作用，如"背景事实""原因剖析""方案要点""数据佐证"
- layout_id: 必须匹配 page_type：
    cover → cover
    toc → toc
    section → section_divider
    content → content_with_image / two_column / icon_grid_3 / icon_grid_4 / stat_callout / quote_highlight / text_focus
    summary → stat_callout / two_column / text_focus
    thanks → thanks
- key_points: 3~5 条内容要点草稿，每条 8~20 字，必须是短小精悍的短语，禁止长句；
  不要写具体百分比/统计数字（除非联网资料明确给出），用定性表述代替编造的数据
- needs_image: 仅当 page_type=content 且 layout_id=content_with_image 时为 true，其余必须为 false
- image_topic: needs_image=true 时给出具象中文画面短语（可拍摄的人/物/场景，如"放射科医生查看CT影像"），
  禁止"技术架构""商业模式""发展趋势"等抽象词；needs_image=false 时为空字符串
- toc 页与 thanks 页的 key_points 必须为空数组 []

【输出 JSON 结构】
{"topic":"...","sections":[{"section_id":1,"section_title":"章节标题","section_role":"提出问题","pages":[{...}]}]}

所有字符串必须使用双引号；不要输出 markdown 代码块、注释或任何解释文字。
"""


def _fix_page(page: dict) -> None:
    """Normalize a single page dict in place (tolerant, never raises)."""
    page_type = page.get("page_type")
    if page_type not in PAGE_TYPES:
        if page.get("layout_id") == "section_divider":
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
    if not isinstance(page.get("key_points"), list):
        page["key_points"] = []
    if page_type in ("cover", "toc", "thanks"):
        page["key_points"] = []

    needs_image = bool(page.get("needs_image")) and page_type == "content" \
        and layout_id in IMAGE_LAYOUTS
    page["needs_image"] = needs_image
    if needs_image:
        if not page.get("image_topic"):
            page["image_topic"] = page.get("title", "")
    else:
        page["image_topic"] = ""


def _validate_outline(result: dict) -> dict:
    """Validate and fix planner output; raises ValueError to trigger a retry."""
    sections = result.get("sections")

    # Tolerate a flat V1-style {"slides": [...]} response.
    if not isinstance(sections, list) or not sections:
        slides = result.get("slides")
        if isinstance(slides, list) and slides:
            sections = [{
                "section_id": 1,
                "section_title": "主要内容",
                "section_role": "",
                "pages": slides,
            }]
            result["sections"] = sections
        else:
            raise ValueError("Planner returned no sections")

    # A single section is tolerated: normalize_outline falls back to listing
    # content-page titles in the TOC. Weaker models often flatten the outline.
    if not (1 <= len(sections) <= 8):
        raise ValueError(f"Section count out of range: {len(sections)} (need 1~8)")

    total = 0
    for si, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            raise ValueError("Section is not an object")
        section["section_id"] = si
        title = section.get("section_title") or section.get("title") or "主要内容"
        section["section_title"] = str(title)[:40]
        section.setdefault("section_role", "")

        pages = section.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError(f"Section {si} has no pages")
        for page in pages:
            if not isinstance(page, dict):
                raise ValueError("Page is not an object")
            _fix_page(page)
        total += len(pages)

    if not (8 <= total <= MAX_SLIDES):
        raise ValueError(f"Page count out of range: {total} (need 8~{MAX_SLIDES})")

    result.setdefault("topic", "")
    return result


def plan(topic: str, web_context: str = "") -> dict:
    """Generate a hierarchical outline. Retries on JSON/structure failure.

    Args:
        topic: PPT topic string.
        web_context: Optional web search context for better content.

    Returns:
        {"topic": str, "sections": [{"section_id", "section_title",
         "section_role", "pages": [page dicts]}]}
    """
    user_msg = f"请为以下主题规划PPT大纲：{topic}"
    if web_context:
        user_msg += (
            f"\n\n以下是联网搜索到的相关资讯，请参考使用真实数据和案例：\n{web_context}"
        )

    # Prefer the strong model, but degrade to the default model when it is
    # unavailable (e.g. GLM returns 429/balance errors for paid tiers).
    models = [GLM_STRONG_MODEL]
    if GLM_DEFAULT_MODEL and GLM_DEFAULT_MODEL != GLM_STRONG_MODEL:
        models.append(GLM_DEFAULT_MODEL)

    last_error = None
    for model in models:
        for attempt in range(LLM_MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.3,
                    max_tokens=16384,
                    response_format={"type": "json_object"},
                )
                if not response.choices:
                    raise ValueError("Empty response.choices from GLM planner")
                raw = response.choices[0].message.content
                if not raw:
                    raise ValueError("Empty message.content from GLM planner")
                result = parse_json(raw, label=f"Planner attempt {attempt+1}")
                result = _validate_outline(result)

                total = sum(len(s["pages"]) for s in result["sections"])
                logger.info("Planned %d sections / %d slides for topic: %s (model=%s)",
                            len(result["sections"]), total, topic, model)
                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    "Planner attempt %d/%d failed (model=%s): %s",
                    attempt + 1, LLM_MAX_RETRIES, model, e,
                )
        logger.warning("Planner model %s exhausted, trying next fallback", model)

    raise RuntimeError(
        f"[Planner] all models/attempts failed. Last error: {last_error}"
    )
