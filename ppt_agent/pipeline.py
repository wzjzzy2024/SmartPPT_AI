"""
Unified PPT generation pipeline.
Shared by CLI (main.py) and Web server (server.py) to eliminate duplication.
"""

import datetime
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from agents.planner import plan
from agents.writer import write_slide_safe, validate_and_retry
from agents.translator import translate_to_search_keywords
from agents.image_fetcher import fetch_image_bytes
from agents.tavily_search import search_for_topic, search_for_slide, clear_cache
from templates.slide_templates import render_slide
from parser import parse_markdown, plain_text_to_slides, _is_markdown
from config import get_theme, auto_match_theme
from search_config import SEARCH_ENABLED

logger = logging.getLogger("smartppt.pipeline")


def make_filename(topic: str) -> str:
    """Generate a safe output filename from topic."""
    safe_topic = re.sub(r'[\\/*?:"<>|]', "", topic)[:10]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_topic}_{ts}.pptx"


def get_output_dir(project_root: Path = None) -> Path:
    """Get or create the output directory."""
    if project_root is None:
        project_root = Path(__file__).parent.parent
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def generate_ppt(
    topic: str,
    output_path: str = None,
    theme_id: str = None,
    markdown_text: str = None,
    progress_callback=None,
) -> str:
    """Full pipeline: topic/markdown -> .pptx file.

    Args:
        topic: PPT topic string.
        output_path: Explicit output path. If None, auto-generated in output/.
        theme_id: Theme color ID. If None, auto-matched from topic.
        markdown_text: Optional Markdown/text input to parse instead of LLM planning.
        progress_callback: Optional callable(step: int, msg: str) for progress updates.

    Returns:
        Output file path.
    """
    t0 = time.time()

    if output_path is None:
        output_path = str(get_output_dir() / make_filename(topic))

    def progress(step: int, msg: str):
        logger.info("[Step %d] %s", step, msg)
        if progress_callback:
            progress_callback(step, msg)

    # -- Resolve theme --
    theme = get_theme(theme_id) if theme_id else get_theme(auto_match_theme(topic))
    progress(0, f"主题色: {theme.get('name', 'auto')}")

    # -- Step 0: Tavily web search for topic context (before outline) --
    topic_context = ""
    if SEARCH_ENABLED and not markdown_text:
        progress(0.5, f"联网搜索主题资讯: {topic}")
        try:
            search_result = search_for_topic(topic)
            if search_result["success"]:
                topic_context = search_result["summary"]
                progress(0.5, f"搜索完成，获取 {len(search_result['results'])} 条资讯")
            else:
                progress(
                    0.5, f"搜索未获取到结果: {search_result.get('error', '未知原因')}"
                )
        except Exception as e:
            logger.warning("Topic search failed, continuing without web context: %s", e)
            progress(0.5, "搜索异常，降级为纯AI生成")

    # -- Step 1: Determine slides_plan --
    if markdown_text:
        if _is_markdown(markdown_text):
            slides_plan = parse_markdown(markdown_text)
        else:
            slides_plan = plain_text_to_slides(markdown_text)
        progress(1, f"解析输入完成，共 {len(slides_plan)} 页")
    else:
        progress(1, f"GLM 规划大纲: {topic}")
        outline = plan(topic, web_context=topic_context)
        slides_plan = outline["slides"]
        for i, s in enumerate(slides_plan):
            if "index" not in s:
                s["index"] = i + 1
        progress(1, f"大纲规划完成，共 {len(slides_plan)} 页")

    # -- Step 1.5: Tavily web search for each slide (before content expansion) --
    if SEARCH_ENABLED:
        progress(1.5, "联网搜索各页面资料...")

        def search_one(slide):
            try:
                slide_result = search_for_slide(
                    slide.get("title", ""), slide.get("key_points", [])
                )
                if slide_result["success"] and slide_result["summary"]:
                    slide["_web_context"] = slide_result["summary"]
            except Exception as e:
                logger.warning(
                    "Slide search failed for '%s': %s", slide.get("title", ""), e
                )
            return slide

        with ThreadPoolExecutor(max_workers=5) as ex:
            slides_plan = list(ex.map(search_one, slides_plan))
        progress(1.5, "页面资料搜索完成")

    # -- Step 2: Expand content with GLM --
    progress(2, f"GLM 并发扩写 {len(slides_plan)} 页内容...")
    with ThreadPoolExecutor(max_workers=5) as ex:
        written = list(ex.map(write_slide_safe, slides_plan))
    for s, w in zip(slides_plan, written):
        result = validate_and_retry(s, w)
        s.update(result)
    progress(2, "内容扩写完成")

    # -- Step 3: Translate image keywords --
    progress(3, "翻译配图关键词...")
    for slide in slides_plan:
        if slide.get("needs_image"):
            cn_topic = slide.get("image_topic", topic)
            slide["_en_keywords"] = translate_to_search_keywords(cn_topic)
    progress(3, "关键词翻译完成")

    # -- Step 4: Fetch images from Unsplash --
    progress(4, "Unsplash 并发获取图片...")
    _topic_en = translate_to_search_keywords(topic) if topic else []

    def fetch_for_slide(slide):
        idx = slide.get("index", 0)
        if slide.get("needs_image") and slide.get("_en_keywords"):
            return idx, fetch_image_bytes(slide["_en_keywords"], topic=_topic_en)
        return idx, None

    image_map = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fetch_for_slide, s): s for s in slides_plan}
        for future in as_completed(futures):
            try:
                idx, img = future.result()
                image_map[idx] = img
            except Exception as e:
                slide = futures[future]
                logger.warning(
                    "Image fetch failed for slide %s: %s", slide.get("index", "?"), e
                )
                image_map[slide.get("index", 0)] = None
    img_count = sum(1 for v in image_map.values() if v)
    progress(4, f"图片获取完成 ({img_count} 张)")

    # -- Step 5: Render PPTX --
    progress(5, "python-pptx 渲染 PPTX...")
    prs = Presentation()
    prs.slide_width = Inches(16)
    prs.slide_height = Inches(9)

    # Use a guaranteed blank layout (last one in most cases)
    blank_layout = prs.slide_layouts[-1]

    for i, slide_data in enumerate(slides_plan):
        # 致谢页只保留主标题，清除 display_points 避免渲染底部小字
        if i == len(slides_plan) - 1 and "感谢" in slide_data.get("title", ""):
            slide_data["display_points"] = []
        slide = prs.slides.add_slide(blank_layout)
        img = image_map.get(slide_data["index"])
        render_slide(slide, slide_data, img, theme=theme)

        if slide_data.get("speaker_notes"):
            notes_slide = slide.notes_slide
            tf = notes_slide.notes_text_frame
            tf.text = slide_data["speaker_notes"]

    # Save with fallback on PermissionError
    try:
        prs.save(output_path)
    except PermissionError:
        fallback = output_path.replace(".pptx", f"_v{int(time.time()) % 100000}.pptx")
        logger.warning("文件被锁定，保存为: %s", fallback)
        prs.save(fallback)
        output_path = fallback

    elapsed = time.time() - t0
    logger.info(
        "完成! %s | %d 页 | %d 张配图 | 耗时 %.1f 秒",
        output_path,
        len(slides_plan),
        img_count,
        elapsed,
    )
    return output_path
