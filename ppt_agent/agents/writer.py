"""
Writer Agent: slide outline -> expanded display_points + speaker_notes.
Uses GLM (glm-4-flash) for content expansion with retry and validation.
"""

import logging
import re
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
1. display_points（展示要点）：输出3~5条，每条8~22个字，必须是短小精悍的bullet短语。
   - 一个要点只表达一个信息点，可含一个数字或结论
   - 禁止把资料原文整句搬上幻灯片，禁止"Word搬家"式长段落
   - 数字只能来自草稿要点或联网资料；草稿中没有具体数字时只写定性结论，
     禁止自行编造百分比、年份、排名或统计数字
   正确示例："端到端延迟降低 60%"、"三甲医院已规模落地"、"监管框架仍待完善"
   错误示例："采用并行处理架构后，系统吞吐量提升了47%，同时将延迟降低至原来的三分之一"（长句搬家）
2. speaker_notes（演讲者注释）：80~150字，帮助演讲者展开讲解的提示。

严格输出纯JSON，行末不加逗号，字符串内部双引号用反斜杠转义：
{"display_points":["...","...","..."],"speaker_notes":"..."}
"""

_FALLBACK = {"display_points": ["内容生成失败，请重试"], "speaker_notes": ""}


def _clean_points(result: dict) -> dict:
    """Normalize a spaced ASCII period used as a clause separator."""
    points = result.get("display_points")
    if isinstance(points, list):
        result["display_points"] = [
            re.sub(r"\s+\.\s+", "，", str(p)).strip()
            for p in points
        ]
    return result


def write_slide(slide: dict) -> dict:
    user_msg = (
        f"幻灯片标题：{slide['title']}\n"
        f"页面类型：{slide.get('page_type', 'content')}\n"
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
                response_format={"type": "json_object"},
            )
            if not response.choices:
                raise ValueError("Empty response.choices from GLM writer")
            raw = response.choices[0].message.content
            if not raw:
                raise ValueError("Empty message.content from GLM writer")
            return _clean_points(
                parse_json(raw, label=f"Writer slide {slide.get('index', '?')}")
            )
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


def _points_ok(points) -> bool:
    """3~6 short bullets, each 6~30 chars (8~22 target lives in the prompt)."""
    return (
        isinstance(points, list)
        and 3 <= len(points) <= 6
        and all(6 <= len(str(p).strip()) <= 30 for p in points)
    )


def validate_and_retry(slide: dict, result: dict, max_retry: int = 2) -> dict:
    """Re-invoke write_slide if display_points don't meet quantity/length requirements.

    Final fallback: the slide's own key_points, so a page is never left empty.
    """
    for _ in range(max_retry):
        if _points_ok(result.get("display_points", [])):
            return result
        try:
            result = write_slide(slide)
        except Exception:
            result = _FALLBACK
    if not _points_ok(result.get("display_points", [])):
        key_points = [
            str(p).strip() for p in (slide.get("key_points") or []) if str(p).strip()
        ]
        if key_points:
            notes = result.get("speaker_notes", "") if isinstance(result, dict) else ""
            return {"display_points": key_points[:6], "speaker_notes": notes}
    return result


def write_slide_safe(slide: dict) -> dict:
    """Write a slide with top-level error handling so one failure doesn't crash the batch."""
    try:
        return write_slide(slide)
    except Exception as e:
        logger.warning("Writer slide %s failed: %s", slide.get("index", "?"), e)
        return _FALLBACK
