"""
FastAPI web server with SSE progress streaming.
Provides /api/generate, /api/progress, /api/download endpoints.
Supports topic, markdown text, and theme selection.
"""

import asyncio
import contextlib
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    FileResponse,
    JSONResponse,
    StreamingResponse,
)

from pipeline import generate_ppt, get_output_dir
from config import check_startup_keys, THEMES
import search_config

logger = logging.getLogger("smartppt.server")


@contextlib.asynccontextmanager
async def lifespan(app):
    check_startup_keys()
    get_output_dir()  # ensure output/ exists
    logger.info("SmartPPT-AI Server started at http://localhost:8000")
    yield


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"error": f"服务器内部错误: {exc}"},
    )


# -- task registry with TTL cleanup --------------------------------
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()
_TASK_TTL = 3600  # seconds

STATIC_DIR = Path(__file__).parent


def _cleanup_old_tasks():
    """Remove tasks older than _TASK_TTL."""
    with _tasks_lock:
        now = time.time()
        expired = [
            tid
            for tid, t in _tasks.items()
            if now - t.get("created_at", now) > _TASK_TTL
        ]
        for tid in expired:
            _tasks.pop(tid, None)
    if expired:
        logger.info("Cleaned up %d expired tasks", len(expired))


def _make_filename(topic: str) -> str:
    safe_topic = re.sub(r'[\\/*?:"<>|]', "", topic)[:10]
    ts = time.strftime("%Y%m%d_%H%M%S")
    return f"{safe_topic}_{ts}.pptx"


def _run_pipeline(
    topic: str, task_id: str, markdown_text: str = None, theme_id: str = None
):
    """Run the full pipeline in a background thread, pushing progress via SSE."""
    with _tasks_lock:
        t = _tasks.get(task_id)
    if t is None:
        return

    with _tasks_lock:
        t["status"] = "running"

    output_dir = get_output_dir()
    output_path = str(output_dir / _make_filename(topic))

    def on_progress(step: int, msg: str):
        with _tasks_lock:
            t["step"] = step
            t["message"] = msg
        t["progress_q"].put({"step": step, "message": msg})

    try:
        result_path = generate_ppt(
            topic,
            output_path=output_path,
            theme_id=theme_id,
            markdown_text=markdown_text,
            progress_callback=on_progress,
        )
        filename = Path(result_path).name
        with _tasks_lock:
            t["status"] = "done"
            t["filename"] = filename
        t["progress_q"].put(
            {
                "step": "done",
                "message": f"生成完成！文件: {filename}",
                "filename": filename,
            }
        )
        logger.info("Task %s done: %s", task_id, filename)

    except Exception as e:
        with _tasks_lock:
            t["status"] = "error"
            t["error"] = str(e)
        t["progress_q"].put({"step": "error", "message": f"生成失败: {e}"})
        logger.error("Task %s failed: %s", task_id, e)


# -- API routes ---------------------------------------------------


@app.get("/")
async def index():
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/themes")
async def api_themes():
    """Return available theme list for the frontend."""
    return {tid: {"name": t["name"]} for tid, t in THEMES.items()}


@app.post("/api/generate")
async def api_generate(request: Request):
    try:
        _cleanup_old_tasks()

        try:
            body = await request.json()
        except Exception:
            return {"error": "请求格式错误，请发送有效的JSON"}

        if not isinstance(body, dict):
            return {"error": "请求体格式错误"}

        topic = (body.get("topic") or "").strip()
        markdown_text = (body.get("markdown_text") or "").strip() or None
        theme_id = (body.get("theme_id") or "").strip() or None
        search_enabled = body.get("search_enabled")

        # Override search switch if provided in request
        if search_enabled is not None:
            search_config.SEARCH_ENABLED = bool(search_enabled)

        if markdown_text:
            for line in markdown_text.splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    topic = line[:50]
                    break
            if not topic:
                topic = "PPT演示"
        elif not topic:
            return {"error": "请输入主题或粘贴Markdown大纲"}

        task_id = uuid.uuid4().hex[:12]
        with _tasks_lock:
            _tasks[task_id] = {
                "status": "pending",
                "step": 0,
                "message": "准备中...",
                "progress_q": queue.Queue(),
                "filename": None,
                "created_at": time.time(),
            }

        threading.Thread(
            target=_run_pipeline,
            args=(topic, task_id),
            kwargs={"markdown_text": markdown_text, "theme_id": theme_id},
            daemon=True,
        ).start()
        return {"task_id": task_id}

    except Exception as e:
        logger.error("api_generate failed: %s", e)
        return {"error": f"服务器内部错误: {e}"}


@app.get("/api/progress/{task_id}")
async def api_progress(task_id: str):
    with _tasks_lock:
        t = _tasks.get(task_id)
    if t is None:

        async def _not_found():
            yield f"data: {json.dumps({'step': 'error', 'message': '任务不存在'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            _not_found(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def stream():
        try:
            with _tasks_lock:
                snap = {
                    "step": t["step"],
                    "message": t["message"],
                    "status": t["status"],
                }
            yield _sse_msg({"step": snap["step"], "message": snap["message"]})
            if snap["status"] in ("done", "error"):
                return

            q = t["progress_q"]
            while True:
                try:
                    item = await asyncio.to_thread(q.get, timeout=1)
                except queue.Empty:
                    yield _sse_msg({"step": "heartbeat"})
                    with _tasks_lock:
                        if t["status"] in ("done", "error"):
                            break
                    continue

                yield _sse_msg(item)
                if item.get("step") in ("done", "error"):
                    break
        except asyncio.CancelledError:
            pass  # client disconnected, clean exit

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/download/{task_id}")
async def api_download(task_id: str):
    with _tasks_lock:
        t = _tasks.get(task_id)
    if t is None or t.get("status") != "done":
        return {"error": "文件未就绪"}
    filename = t.get("filename")
    if not filename:
        return {"error": "文件未就绪"}
    filepath = get_output_dir() / filename
    if not filepath.exists():
        return {"error": "文件不存在或已过期"}
    return FileResponse(
        str(filepath),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )


# -- SSE helpers --------------------------------------------------


def _sse_msg(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 50)
    logger.info("  SmartPPT-AI Server 启动中...")
    logger.info("  前端页面: http://localhost:8000")
    logger.info("  API文档:  http://localhost:8000/docs")
    logger.info("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
