"""
Configuration center: .env loading, API keys, theme color system.
No heavy dependencies (pptx, etc.) — pure configuration.
"""
import os
import logging
import socket as _socket
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (parent of ppt_agent/)
load_dotenv(Path(__file__).parent.parent / ".env")

# -- IPv4 强制偏好 -----------------------------------------------------
# 国内网络环境下 IPv6 路由不稳定（Unsplash/Tavily 首次连接易失败，
# 部分境外域名甚至只解析出 IPv6）。统一让进程内所有 HTTP 客户端
# （requests/urllib3/httpx）优先走 IPv4；IPv4 不可用时回退原行为。
_orig_getaddrinfo = _socket.getaddrinfo


def _ipv4_preferred_getaddrinfo(host, *args, **kwargs):
    try:
        results = _orig_getaddrinfo(host, *args, **kwargs)
    except _socket.gaierror:
        raise
    v4 = [r for r in results if r[0] == _socket.AF_INET]
    return v4 or results


_socket.getaddrinfo = _ipv4_preferred_getaddrinfo

# -- Logging setup ------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("smartppt")

# -- GLM (唯一 LLM 供应商：规划 / 扩写 / 翻译) ---------------------
GLM_API_KEY          = os.getenv("GLM_API_KEY", "")
GLM_BASE_URL         = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
GLM_DEFAULT_MODEL    = os.getenv("GLM_DEFAULT_MODEL", "glm-4-flash")
GLM_STRONG_MODEL     = os.getenv("GLM_STRONG_MODEL", "glm-4-plus")

# -- Unsplash (image fetcher) -------------------------------------
UNSPLASH_KEY         = os.getenv("UNSPLASH_ACCESS_KEY", "")

# -- Tavily (web search, optional) ---------------------------------
TAVILY_API_KEY       = os.getenv("TAVILY_API_KEY", "")

# -- Global LLM settings -----------------------------------------
try:
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
except (ValueError, TypeError):
    LLM_MAX_RETRIES = 3
try:
    LLM_TIMEOUT     = int(os.getenv("LLM_TIMEOUT", "60"))
except (ValueError, TypeError):
    LLM_TIMEOUT = 60


def validate_keys(required: list[str] | None = None) -> list[str]:
    """Check that required API keys are set. Returns list of missing key names."""
    key_map = {
        "GLM_API_KEY":         GLM_API_KEY,
        "UNSPLASH_ACCESS_KEY": UNSPLASH_KEY,
        "TAVILY_API_KEY":      TAVILY_API_KEY,
    }
    if required is None:
        required = list(key_map.keys())
    missing = [k for k in required if not (key_map.get(k) or "").strip()]
    if missing:
        logger.warning("以下 API 密钥未配置: %s", ", ".join(missing))
    return missing


def check_startup_keys():
    """Validate critical keys at startup; warn but don't block."""
    critical = ["GLM_API_KEY", "UNSPLASH_ACCESS_KEY"]
    missing = validate_keys(critical)
    if missing:
        logger.warning("缺少关键密钥，部分功能可能无法使用。请检查 .env 文件。")


# ====================================================================
# Theme Color System — 6 presets
# Colors stored as (r, g, b) tuples; converted to RGBColor by renderer.
# ====================================================================

THEMES = {
    "campus_academic": {
        "name": "校园学术",
        "primary": (0x1A, 0x3A, 0x5C),
        "accent":  (0x24, 0x71, 0xA3),
        "light":   (0xD6, 0xEA, 0xF8),
        "text":    (0x1C, 0x28, 0x33),
        "white":   (0xFF, 0xFF, 0xFF),
    },
    "business_report": {
        "name": "商务汇报",
        "primary": (0x2C, 0x3E, 0x50),
        "accent":  (0xE6, 0x7E, 0x22),
        "light":   (0xEC, 0xF0, 0xF1),
        "text":    (0x2C, 0x3E, 0x50),
        "white":   (0xFF, 0xFF, 0xFF),
    },
    "tech_creative": {
        "name": "科技创意",
        "primary": (0x0D, 0x47, 0xA1),
        "accent":  (0x00, 0xBC, 0xD4),
        "light":   (0xE1, 0xF5, 0xFE),
        "text":    (0x21, 0x21, 0x21),
        "white":   (0xFF, 0xFF, 0xFF),
    },
    "eco_nature": {
        "name": "环保自然",
        "primary": (0x1B, 0x5E, 0x20),
        "accent":  (0x4C, 0xAF, 0x50),
        "light":   (0xE8, 0xF5, 0xE9),
        "text":    (0x1B, 0x5E, 0x20),
        "white":   (0xFF, 0xFF, 0xFF),
    },
    "literature_art": {
        "name": "文艺阅读",
        "primary": (0x4A, 0x14, 0x8C),
        "accent":  (0x9C, 0x27, 0xB0),
        "light":   (0xF3, 0xE5, 0xF5),
        "text":    (0x33, 0x33, 0x33),
        "white":   (0xFF, 0xFF, 0xFF),
    },
    "minimal_general": {
        "name": "简约通用",
        "primary": (0x33, 0x33, 0x33),
        "accent":  (0x75, 0x75, 0x75),
        "light":   (0xF5, 0xF5, 0xF5),
        "text":    (0x33, 0x33, 0x33),
        "white":   (0xFF, 0xFF, 0xFF),
    },
}

THEME_KEYWORDS = {
    "campus_academic": ["学术", "教育", "学习", "研究", "论文", "课程", "大学", "学生", "考试", "知识"],
    "business_report": ["商务", "汇报", "报告", "管理", "企业", "公司", "财务", "市场", "战略", "团队"],
    "tech_creative":   ["科技", "技术", "创新", "AI", "人工智能", "数据", "互联网", "编程", "算法", "系统"],
    "eco_nature":      ["环保", "自然", "生态", "绿色", "低碳", "可持续", "能源", "环境", "植物", "动物"],
    "literature_art":  ["文艺", "文化", "艺术", "历史", "哲学", "文学", "美学", "传统", "古典", "设计"],
    "minimal_general": ["简约", "通用"],
}


def get_theme(theme_id: str = None) -> dict:
    """Get theme colors by ID. Falls back to campus_academic."""
    return THEMES.get(theme_id, THEMES["campus_academic"])


def auto_match_theme(text: str) -> str:
    """Auto-match the best theme based on content keywords."""
    scores = {}
    for theme_id, keywords in THEME_KEYWORDS.items():
        scores[theme_id] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "campus_academic"
