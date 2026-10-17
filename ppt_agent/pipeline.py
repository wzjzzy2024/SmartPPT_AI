"""
Unified PPT generation pipeline.
Shared by CLI (main.py) and Web server (server.py) to eliminate duplication.

V2 flow:
  outline (LLM or parser) -> normalize_outline -> per-page search ->
  writer (content/summary only) -> visual prompts -> fetch + semantic judge
  -> data charts for photo-less pages -> render (13 layouts, geometric
  fallback when no image).
"""

import datetime
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from agents.planner import plan
from agents.writer import write_slide_safe, validate_and_retry
from agents.translator import generate_visual_prompt, translate_to_search_keywords
from agents.image_fetcher import fetch_image
from agents.image_judge import judge_image
from agents.tavily_search import search_for_topic, search_for_slide
from templates.slide_templates import render_slide
from parser import parse_markdown, plain_text_to_slides, _is_markdown
from utils.outline import flatten_sections, normalize_outline
from utils.numeric_guard import strip_unsupported_numbers
from utils import chart_builder
from config import get_theme, auto_match_theme
import search_config

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
    if search_config.SEARCH_ENABLED and not markdown_text:
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

    # -- Step 1: Outline -> normalize (single structural choke point) --
    if markdown_text:
        if _is_markdown(markdown_text):
            raw_pages = parse_markdown(markdown_text)
        else:
            raw_pages = plain_text_to_slides(markdown_text)
        slides_plan, _sections = normalize_outline(raw_pages, topic)
        progress(1, f"解析输入完成，共 {len(slides_plan)} 页（目录/致谢已就绪）")
    else:
        progress(1, f"GLM 规划大纲: {topic}")
        outline = plan(topic, web_context=topic_context)
        slides_plan, _sections = normalize_outline(flatten_sections(outline), topic)
        progress(1, f"大纲规划完成，共 {len(slides_plan)} 页（封面/目录/总结/致谢已就绪）")

    # -- Step 1.5: Tavily web search for content pages only --
    if search_config.SEARCH_ENABLED:
        progress(1.5, "联网搜索各页面资料...")

        def search_one(slide):
            if slide.get("page_type") not in ("content", "summary"):
                return slide
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

    # -- Step 2: Expand content with GLM (content/summary pages only) --
    expandable = [
        s for s in slides_plan if s.get("page_type") in ("content", "summary")
    ]
    progress(2, f"GLM 并发扩写 {len(expandable)} 页内容...")
    with ThreadPoolExecutor(max_workers=5) as ex:
        written = list(ex.map(write_slide_safe, expandable))
    for s, w in zip(expandable, written):
        result = validate_and_retry(s, w)
        s.update(result)
        strip_unsupported_numbers(s)
    progress(2, "内容扩写完成")

    # -- Step 3: Generate concrete visual prompts (parallel) --
    progress(3, "生成配图视觉提示词...")

    def make_visual_prompt(slide):
        if slide.get("needs_image"):
            try:
                slide["_en_keywords"] = generate_visual_prompt(slide)
            except Exception as e:
                logger.warning(
                    "Visual prompt failed for '%s': %s", slide.get("title", ""), e
                )
        return slide

    with ThreadPoolExecutor(max_workers=5) as ex:
        slides_plan = list(ex.map(make_visual_prompt, slides_plan))
    progress(3, "视觉提示词生成完成")

    # -- Step 4: Fetch images + LLM relevance judge --
    progress(4, "Unsplash 获取图片并判定相关性...")
    _topic_en = []
    if topic and any(s.get("needs_image") for s in slides_plan):
        _topic_en = translate_to_search_keywords(topic)

    def fetch_and_judge(slide):
        idx = slide.get("index", 0)
        try:
            if not (slide.get("needs_image") and slide.get("_en_keywords")):
                return idx, None
            meta = fetch_image(slide["_en_keywords"], topic=_topic_en)
            if meta is None:
                return idx, None
            slide["_image_meta"] = meta
            approved = judge_image(slide, meta)
            slide["_image_approved"] = approved
            return idx, meta["bytes"] if approved else None
        except Exception as e:
            logger.warning("Image pipeline failed for slide %s: %s", idx, e)
            return idx, None

    with ThreadPoolExecutor(max_workers=4) as ex:
        fetch_results = list(ex.map(fetch_and_judge, slides_plan))

    image_map = {idx: img for idx, img in fetch_results if img is not None}
    attempted = sum(1 for s in slides_plan if s.get("needs_image"))
    img_count = len(image_map)
    dropped = max(0, attempted - img_count)
    progress(4, f"配图获取完成 (保留 {img_count} 张，淘汰 {dropped} 张)")

    # -- Step 4.5: Build data charts for photo-less pages with real numbers --
    # Photos win: a page that already has an approved image is never converted.
    progress(4.5, "生成数据图表...")
    chart_count = 0
    for slide_data in slides_plan:
        if image_map.get(slide_data.get("index")) is not None:
            continue
        if not chart_builder.should_convert(slide_data):
            continue
        if not chart_builder.convert_slide_to_chart(slide_data):
            continue
        png = chart_builder.build_chart_png(slide_data["_chart_data"], theme)
        if png:
            slide_data["_chart_png"] = png
            chart_count += 1
        else:
            chart_builder.revert_slide(slide_data)
    progress(4.5, f"数据图表完成 (生成 {chart_count} 张)")

    # -- Step 5: Render PPTX --
    progress(5, "python-pptx 渲染 PPTX...")
    prs = Presentation()
    prs.slide_width = Inches(16)
    prs.slide_height = Inches(9)

    # Use a guaranteed blank layout (last one in most cases)
    blank_layout = prs.slide_layouts[-1]

    for slide_data in slides_plan:
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
        "完成! %s | %d 页 | %d 张配图 | %d 张图表 | 耗时 %.1f 秒",
        output_path,
        len(slides_plan),
        img_count,
        chart_count,
        elapsed,
    )
    return output_path
