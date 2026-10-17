"""
CLI entry point for SmartPPT-AI.
Full pipeline: topic / markdown / text -> .pptx file
"""

import logging
import os
import sys
from pathlib import Path

from config import check_startup_keys
from pipeline import generate_ppt
import search_config

logger = logging.getLogger("smartppt.main")


def main():
    check_startup_keys()

    # Usage: python main.py [topic or filepath.md] [--theme THEME_ID] [--search on|off]
    args = sys.argv[1:]
    theme_id = None
    input_text = None

    # Parse --theme argument
    if "--theme" in args:
        idx = args.index("--theme")
        if idx + 1 < len(args):
            theme_id = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    # Parse --search argument (global switch for web search)
    if "--search" in args:
        idx = args.index("--search")
        if idx + 1 < len(args):
            search_val = args[idx + 1].lower()
            search_config.SEARCH_ENABLED = search_val in ("on", "1", "true", "yes")
            logger.info(
                "联网搜索: %s", "开启" if search_config.SEARCH_ENABLED else "关闭"
            )
            args = args[:idx] + args[idx + 2:]
        else:
            logger.warning("--search 参数需要指定 on 或 off")

    if args:
        arg = args[0]
        if os.path.isfile(arg):
            input_text = Path(arg).read_text(encoding="utf-8")
            topic = Path(arg).stem
        else:
            topic = arg
    else:
        print("请输入PPT主题或粘贴Markdown大纲（输入空行结束）：")
        lines = []
        while True:
            try:
                line = input()
                if line == "":
                    if lines:
                        break
                    continue
                lines.append(line)
            except EOFError:
                break
        if lines:
            input_text = "\n".join(lines)
            topic = lines[0][:50]
        else:
            topic = "人工智能在医疗领域的应用"

    try:
        generate_ppt(topic, theme_id=theme_id, markdown_text=input_text)
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error("生成失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
