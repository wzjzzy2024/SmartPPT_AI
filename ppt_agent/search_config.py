"""
Search configuration: Tavily search settings, feature switch, cache params.
密钥统一放在 .env（源码中禁止硬编码任何 API Key）。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of ppt_agent/)
load_dotenv(Path(__file__).parent.parent / ".env")

# -- API Key（.env 中的 TAVILY_API_KEY）-------------------------------
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# -- Feature Switch (全局开关) ----------------------------------------
# 环境变量 TAVILY_SEARCH_ENABLED: "1"=开启, "0"=关闭
# 也可在代码中直接修改 SEARCH_ENABLED 的值
SEARCH_ENABLED = os.getenv("TAVILY_SEARCH_ENABLED", "1") == "1"

# -- Search Parameters (检索参数) ------------------------------------
# 每次搜索返回的最大结果数
TAVILY_MAX_RESULTS = 5

# 摘要最大字符数（每条结果）
TAVILY_SUMMARY_MAX_CHARS = 300

# 大纲生成前：主题搜索的最大结果数
TAVILY_TOPIC_MAX_RESULTS = 5

# 正文扩写前：页面定向搜索的最大结果数
TAVILY_PAGE_MAX_RESULTS = 3

# 搜索超时时间（秒）
TAVILY_SEARCH_TIMEOUT = 15

# -- Cache Settings (内存缓存) ----------------------------------------
# 内存缓存最大条目数
CACHE_MAX_ENTRIES = 100
