"""
Writer Agent: slide outline -> expanded display_points + speaker_notes.
Uses GLM (glm-4-flash) for content expansion with retry and validation.
"""

import logging
from openai import OpenAI
from config import (
    GLM_API_KEY,
    GLM_BASE_URL,
    GLM_DEFAULT_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT,
)
from utils.json_parser import parse_json

logger = logging.getLogger("smartppt.writer")

client = OpenAI(
    api_key=GLM_API_KEY,
    base_url=GLM_BASE_URL.rstrip("/") + "/",
    timeout=LLM_TIMEOUT,
)

SYSTEM_PROMPT = """
你是一位PPT内容撰写专家。你会收到一张幻灯片的规划信息，需要输出两部分内容：
1. display_points（展示要点）：必须输出4~6条，每条不少于25个字，必须是包含完整信息的陈述句。
   错误示例："提高效率"（太短，无信息）
   正确示例："采用并行处理架构后，系统吞吐量提升47%，延迟降低至原来的1/3"
   每条要点必须有具体数据、明确结论或可操作的观点，不能是空洞的短语。
2. speaker_notes（演讲者注释）：100~200字，帮助演讲者展开讲解的提示。

严格输出纯JSON，行末不加逗号，字符串内部双引号用反斜杠转义：
{"display_points":["...","...","...","..."],"speaker_notes":"..."}
"""

_FALLBACK = {"display_points": ["内容生成失败，请重试"], "speaker_notes": ""}


def write_slide(slide: dict) -> dict:
    user_msg = (
        f"幻灯片标题：{slide['title']}\n"
        f"在演讲中的作用：{slide.get('logic_role', '')}\n"
        f"草稿要点：{chr(10).join(slide.get('key_points', []))}"
    )
    web_context = slide.get("_web_context", "")
    if web_context:
        user_msg += f"\n\n联网搜索到的相关资料（请参考真实数据和案例）：\n{web_context}"
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=GLM_DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.6,
                max_tokens=4096,
            )
            if not response.choices:
                raise ValueError("Empty response.choices from GLM writer")
            raw = response.choices[0].message.content
            if not raw:
                raise ValueError("Empty message.content from GLM writer")
            return parse_json(raw, label=f"Writer slide {slide.get('index', '?')}")
        except Exception as e:
            logger.warning(
                "Writer slide %s attempt %d failed: %s",
                slide.get("index", "?"),
                attempt + 1,
                e,
            )
            if attempt == LLM_MAX_RETRIES - 1:
                raise
    return _FALLBACK  # unreachable, satisfies type checker


def validate_and_retry(slide: dict, result: dict, max_retry: int = 2) -> dict:
    """Re-invoke write_slide if display_points don't meet quantity/length requirements."""
    for _ in range(max_retry):
        points = result.get("display_points", [])
        if len(points) >= 4 and all(len(p) >= 25 for p in points):
            return result
        try:
            result = write_slide(slide)
        except Exception:
            result = _FALLBACK
    return result


def write_slide_safe(slide: dict) -> dict:
    """Write a slide with top-level error handling so one failure doesn't crash the batch."""
    try:
        return write_slide(slide)
    except Exception as e:
        logger.warning("Writer slide %s failed: %s", slide.get("index", "?"), e)
        return _FALLBACK
