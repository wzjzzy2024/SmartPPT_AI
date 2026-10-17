"""
Planner Agent: topic -> structured 15-20 slide outline JSON.
Uses GLM-4-Plus for planning with retry logic.
"""

import logging
from openai import OpenAI
from config import (
    GLM_API_KEY,
    GLM_BASE_URL,
    GLM_STRONG_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT,
)
from utils.json_parser import parse_json

logger = logging.getLogger("smartppt.planner")

client = OpenAI(
    api_key=GLM_API_KEY,
    base_url=GLM_BASE_URL.rstrip("/") + "/",
    timeout=LLM_TIMEOUT,
)

VALID_LAYOUTS = {
    "title_hero",
    "two_column",
    "content_with_image",
    "icon_grid_3",
    "icon_grid_4",
    "stat_callout",
    "quote_highlight",
    "text_focus",
    "section_divider",
}

SYSTEM_PROMPT = """
你是一位专业的演讲策划师。用户会给你一个PPT主题或粗略大纲。
你的任务是规划一套完整的、有说服力的演讲结构，要求：
1. 幻灯片数量：根据主题的复杂度和逻辑需要自动生成合理页数（通常12~22张），确保论证完整。
2. 必须包含完整叙事弧：
   - 开场（1~2张）：钩子/问题引入/本次演讲将解决什么
   - 背景（1~2张）：为什么这个问题重要/现状分析
   - 主体（N张）：核心内容，每个论点必须有支撑，根据主题实际需要决定论点数量
   - 结论（1~2张）：核心观点总结+行动呼吁或展望；最后一页必须是致谢页
3. 每张幻灯片必须说明它在整体论证中的作用（logic_role字段）
4. layout_id必须从以下列表选择：
   title_hero / two_column / content_with_image / icon_grid_3 /
   icon_grid_4 / stat_callout / quote_highlight / text_focus / section_divider
5. 配图规则（非常重要）：
   - needs_image：只有title_hero、content_with_image、quote_highlight三种布局才设为true，其他布局设为false
   - image_topic：必须是一个具体的、有视觉画面感的中文名词短语，能直接翻译成英文去搜图。
     好的示例："金色麦田日落"、"手术室中的达芬奇机器人"、"上海外滩夜景天际线"、"太空中的地球"
     坏的示例："技术架构"、"商业模式"、"数据分析"、"发展趋势"（这些太抽象，搜不出图）
   - image_topic必须和当前幻灯片的具体内容紧密相关，不要用PPT总主题去搜图
   - 致谢页不需要配图（needs_image=false）
6. 重要约束：
   - 最后一页（最后一张slide）必须是致谢页，title固定用"感谢倾听，敬请指正"，
     key_points必须为空数组[]（不生成副标题或任何小字），layout_id用title_hero或quote_highlight
   - 绝对不允许编造Q&A、观众提问、互动环节等虚构内容
   - 不允许在致谢页之前插入"问答环节"幻灯片
   - 所有内容必须基于真实可验证的信息，不得杜撰数据或引述

你必须只输出一行合法的JSON，不包含任何其他文字、注释或markdown标记。
字段名必须使用 "index"（不是 slide_id），"title"，"layout_id"，"logic_role"，"key_points"，"needs_image"，"image_topic"。
key_points 每条1-3个要点，每个要点为纯中文文本，不要使用特殊符号（如 -、* 等）。
JSON中所有字符串值必须用双引号包裹，内部的双引号必须用反斜杠转义。
"""


def plan(topic: str, web_context: str = "") -> dict:
    """Generate slide outline. Retries on JSON parse failure.

    Args:
        topic: PPT topic string.
        web_context: Optional web search context for better content.
    """
    user_msg = f"请为以下主题规划PPT：{topic}"
    if web_context:
        user_msg += (
            f"\n\n以下是联网搜索到的相关资讯，请参考使用真实数据和案例：\n{web_context}"
        )

    last_error = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=GLM_STRONG_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=16384,
            )
            if not response.choices:
                raise ValueError("Empty response.choices from GLM planner")
            raw = response.choices[0].message.content
            if not raw:
                raise ValueError("Empty message.content from GLM planner")
            result = parse_json(raw, label=f"Planner attempt {attempt+1}")

            slides = result.get("slides", [])
            if not isinstance(slides, list) or len(slides) < 5:
                raise ValueError(f"Slide count too low: {len(slides)} (need >=5)")

            for i, s in enumerate(slides):
                if "index" not in s and "slide_id" in s:
                    s["index"] = s.pop("slide_id")
                s.setdefault("index", i + 1)
                s.setdefault("needs_image", False)
                s.setdefault("image_topic", "")
                s.setdefault("key_points", [])
                s.setdefault("logic_role", "")

                lid = s.get("layout_id", "text_focus")
                if lid not in VALID_LAYOUTS:
                    logger.warning(
                        "Slide %s has invalid layout_id '%s', falling back to text_focus",
                        s.get("index", i + 1),
                        lid,
                    )
                    s["layout_id"] = "text_focus"
                else:
                    s["layout_id"] = lid

            logger.info("Planned %d slides for topic: %s", len(slides), topic)
            return result

        except Exception as e:
            last_error = e
            logger.warning("Planner attempt %d failed: %s", attempt + 1, e)

    raise RuntimeError(
        f"[Planner] all {LLM_MAX_RETRIES} attempts failed. Last error: {last_error}"
    )
