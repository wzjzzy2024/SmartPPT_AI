"""
Image Judge Agent: LLM semantic relevance check for a candidate image.
Fail-closed by design: any error, empty metadata or low score -> drop the
image ("宁可无图，绝不乱配图").
"""
import logging
import threading

from openai import OpenAI

from config import (
    GLM_API_KEY,
    GLM_BASE_URL,
    GLM_DEFAULT_MODEL,
    IMAGE_MIN_SCORE,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT,
)
from utils.json_parser import safe_parse

logger = logging.getLogger("smartppt.image_judge")

_client = None
_client_lock = threading.Lock()

SYSTEM_PROMPT = """
你是幻灯片配图相关性评审。判断候选图片是否适合作为该页幻灯片的配图。

判断以「页面标题 + 配图意图」为主，页面要点仅作参考：图片不需要覆盖每一个要点，
也不要求出现要点中的具体疾病名/产品名/数据，更不要求图片里出现"AI"字样或算法界面
（图库中的 AI 多为概念化表达）。只要视觉主体与页面核心概念属于同一场景或主题即可。

相关示例（应保留）：
- 页面讲医学影像诊断，图片是 CT/MRI/脑部扫描图或医生阅片 → 直接相关
- 页面讲数据安全/隐私，图片是挂锁、加密、服务器机房 → 合理象征
- 页面讲药物研发，图片是实验室、移液操作、显微镜 → 场景相关
- 页面讲人才培养，图片是课堂、团队讨论、实验教学 → 场景相关

评分标准：
- 视觉主体直接呈现页面核心场景或专业领域 → 80~100
- 场景相关或使用合理象征，能支撑页面主题 → 60~79
- 仅氛围相关、过于宽泛的通用图（如纯色背景、无关人群） → 40~59
- 主体错误、抽象词直译、与内容无关 → 0~39
- 图库描述完全为空时，给 30 分（无法验证相关性）

只输出JSON：{"score":0,"verdict":"keep|drop","reason":"一句中文理由"}
score 低于 60 时 verdict 必须为 "drop"。
"""


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


def judge_image(slide: dict, img_meta: dict) -> bool:
    """Return True only when the image is semantically relevant to the page."""
    alt = (img_meta.get("alt_description") or "").strip()
    desc = (img_meta.get("description") or "").strip()
    points = slide.get("display_points") or slide.get("key_points") or []
    user_msg = (
        f"页面标题：{slide.get('title', '')}\n"
        f"配图意图：{slide.get('image_topic', '')}\n"
        f"页面要点（仅作参考，不要求逐条覆盖）：{'；'.join(points[:5])}\n"
        f"候选图片信息（图库作者描述）：\n"
        f"- alt_description: {alt or '无'}\n"
        f"- description: {desc or '无'}\n"
        f"- 尺寸: {img_meta.get('width')}x{img_meta.get('height')}\n\n"
        '只输出JSON：{"score":0,"verdict":"keep|drop","reason":"一句中文理由"}'
    )

    client = _get_client()
    for attempt in range(max(1, min(2, LLM_MAX_RETRIES))):
        try:
            response = client.chat.completions.create(
                model=GLM_DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=150,
                response_format={"type": "json_object"},
            )
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty response from GLM image judge")
            result = safe_parse(
                response.choices[0].message.content,
                label=f"ImageJudge slide {slide.get('index', '?')}",
            )
            if not result:
                raise ValueError("Unparseable image judge result")
            score = int(result.get("score", 0))
            verdict = str(result.get("verdict", "")).lower()
            keep = score >= IMAGE_MIN_SCORE and verdict != "drop"
            logger.info(
                "Image judge slide %s: score=%s verdict=%s keep=%s reason=%s",
                slide.get("index", "?"), score, verdict or "-", keep,
                result.get("reason", ""),
            )
            return keep
        except Exception as e:
            logger.warning(
                "Image judge slide %s attempt %d failed: %s",
                slide.get("index", "?"), attempt + 1, e,
            )

    logger.info("Image judge slide %s failed closed (image dropped)",
                slide.get("index", "?"))
    return False
