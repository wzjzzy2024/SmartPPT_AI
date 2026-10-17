"""
Translator Agent:
  - generate_visual_prompt: slide content -> concrete English visual prompts
  - translate_to_search_keywords: Chinese topic -> English search keywords
Uses GLM-4-Flash. Returns multiple keyword options for fallback chain.
Thread-safe cache for concurrent access.
"""
import logging
import re
import threading
from openai import OpenAI
from config import GLM_API_KEY, GLM_BASE_URL, GLM_DEFAULT_MODEL, LLM_MAX_RETRIES, LLM_TIMEOUT

logger = logging.getLogger("smartppt.translator")

_cache: dict[str, list[str]] = {}
_cache_lock = threading.Lock()
_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = OpenAI(
                api_key=GLM_API_KEY,
                base_url=GLM_BASE_URL.rstrip("/") + "/",
                timeout=LLM_TIMEOUT,
            )
    return _client


def _prefer_concrete(keywords: list[str]) -> list[str]:
    """Promote the first multi-word keyword when the model returns a lone noun.

    e.g. ["doctor", "analyzing medical images with AI system", ...] -> the
    second entry is the actual visual prompt and makes a far better query.
    """
    for i, keyword in enumerate(keywords):
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", keyword)
        if 2 <= len(words) <= 8:
            return [keyword] + keywords[:i] + keywords[i + 1:]
    return keywords


def _parse_keywords(raw: str) -> list[str]:
    """Split a comma list and strip numbering/markdown the model adds."""
    keywords = []
    for part in raw.replace("，", ",").split(","):
        part = re.sub(r"^\s*\d+\s*[.)、]\s*", "", part)
        part = part.strip(" \"'`*。.")
        if part:
            keywords.append(part)
    return keywords


def generate_visual_prompt(slide: dict) -> list[str]:
    """Turn a slide's core idea into concrete English Unsplash visual prompts.

    Returns 3 keywords from specific to broad. The first entry is a concrete,
    photographable visual prompt (with light/composition modifiers allowed).

    Falls back to the Chinese image_topic; the pipeline appends an English
    topic fallback so the fetcher can still degrade gracefully.
    """
    title = slide.get("title", "")
    points = slide.get("display_points") or slide.get("key_points") or []
    image_topic = slide.get("image_topic", "")
    cache_key = f"visual::{title}::{image_topic}"
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]

    points_text = "；".join(str(p) for p in points[:5])
    user_msg = f"""根据幻灯片的核心思想，生成 Unsplash 图库的具象英文视觉搜索词。

幻灯片标题：{title}
页面要点：{points_text}
参考画面：{image_topic}

要求：
1. 输出3个英文搜索词，从具体到宽泛，用英文逗号分隔
2. 第1个：具象视觉Prompt（2~6个词），必须描述可拍摄的场景/主体，可含光线、构图、质感修饰词
   示例："close-up of solar panels at golden hour"
3. 第2个：去掉修饰的主体词；第3个：最宽泛的类别词
4. 禁止抽象概念词（technology / innovation / strategy / business）作为第1个词
5. 只输出逗号分隔英文，不要其他内容"""

    client = _get_client()
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=GLM_DEFAULT_MODEL,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0,
                max_tokens=80,
                timeout=LLM_TIMEOUT,
            )
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty response from GLM visual prompt generator")
            raw = response.choices[0].message.content.strip()
            keywords = _prefer_concrete(_parse_keywords(raw))
            if not keywords:
                raise ValueError("No keywords parsed from GLM visual prompt")
            with _cache_lock:
                _cache[cache_key] = keywords
            logger.info("Visual prompt: '%s' -> %s", title, keywords)
            return keywords
        except Exception as e:
            logger.warning("Visual prompt attempt %d failed: %s", attempt + 1, e)
            if attempt == LLM_MAX_RETRIES - 1:
                fallback = [image_topic or title]
                with _cache_lock:
                    _cache[cache_key] = fallback
                logger.error("Visual prompt failed for '%s', fallback: %s",
                             title, fallback)
                return fallback
    return [image_topic or title]


def translate_to_search_keywords(chinese_topic: str) -> list[str]:
    """Translate Chinese topic to a list of English keywords (specific -> broad).

    Returns multiple options so the image fetcher can try them in order.
    Example: "金色麦田日落" -> ["golden wheat field sunset", "wheat field", "sunset"]
    """
    with _cache_lock:
        if chinese_topic in _cache:
            return _cache[chinese_topic]

    client = _get_client()
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=GLM_DEFAULT_MODEL,
                messages=[
                    {"role": "user", "content": f"""将以下中文翻译为Unsplash图库搜索关键词。

要求：
1. 输出3个搜索词，从具体到宽泛，用英文逗号分隔
2. 第1个：最具体的描述（2-3个词）
3. 第2个：中等宽泛（1-2个词）
4. 第3个：最常见的宽泛词（1个词）
5. 所有词必须是能在照片中拍到的东西（人、物、场景、自然）
6. 不要抽象概念

示例：
输入："人工智能医疗应用"
输出：medical AI technology, healthcare technology, medical

输入："上海外滩夜景"
输出：Shanghai skyline night, city skyline, Shanghai

输入："深度学习神经网络"
输出：neural network visualization, data technology, technology

只输出逗号分隔的英文，不要其他内容。
中文：{chinese_topic}"""},
                ],
                temperature=0,
                max_tokens=80,
                timeout=LLM_TIMEOUT,
            )
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty response from GLM translator")
            raw = response.choices[0].message.content.strip()
            keywords = [kw.strip() for kw in raw.split(",") if kw.strip()]
            if not keywords:
                keywords = [chinese_topic]
            with _cache_lock:
                _cache[chinese_topic] = keywords
            logger.info("Translated: '%s' -> %s", chinese_topic, keywords)
            return keywords
        except Exception as e:
            logger.warning("Translation attempt %d failed: %s", attempt + 1, e)
            if attempt == LLM_MAX_RETRIES - 1:
                logger.error("Translation failed for '%s'", chinese_topic)
                with _cache_lock:
                    _cache[chinese_topic] = [chinese_topic]
                return [chinese_topic]
    return [chinese_topic]


def translate_to_search_keyword(chinese_topic: str) -> str:
    """Backward-compatible single-keyword wrapper."""
    return translate_to_search_keywords(chinese_topic)[0]
