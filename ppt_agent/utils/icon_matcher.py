"""
Deterministic icon matching + SVG rasterization.

The deck ships a small local set of Bootstrap Icons (MIT). A page title and
its bullets are matched against a Chinese keyword map; the best icon is
rasterized to a transparent PNG at request time and cached in memory.

Fail-closed: no confident match -> no icon (never a wrong icon). Missing
cairosvg or a broken SVG -> None, and the renderer falls back to its current
number/geometry treatment.
"""

import logging
import threading
from pathlib import Path

from config import ICON_SCALE

logger = logging.getLogger("smartppt.icon_matcher")

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

# icon file stem -> Chinese keywords. Longest match wins; insertion order
# breaks exact ties.
ICON_KEYWORDS = {
    "cpu-fill": ["人工智能", "大模型", "算法", "芯片", "智能", "计算", "AI"],
    "robot": ["机器人", "自动化", "无人", "RPA"],
    "heart-pulse-fill": ["医疗", "健康", "医院", "生命", "诊断", "护理", "就医"],
    "capsule": ["药物", "医药", "药品", "临床", "治疗", "患者", "研发"],
    "clipboard2-pulse": ["病历", "健康记录", "诊疗", "随访"],
    "bar-chart-fill": ["数据", "分析", "统计", "对比", "图表", "指标"],
    "pie-chart-fill": ["占比", "份额", "比例", "构成", "结构"],
    "graph-up-arrow": ["增长", "趋势", "上升", "发展", "提升", "增长点"],
    "shield-fill": ["安全", "防护", "保障", "隐私", "合规", "风控"],
    "book-fill": ["教育", "学习", "课程", "培训", "阅读", "知识"],
    "mortarboard-fill": ["大学", "学位", "学术", "研究", "论文", "高校"],
    "bank": ["金融", "银行", "投资", "理财", "资本"],
    "cash-coin": ["支付", "货币", "资金", "成本", "预算", "收益"],
    "people-fill": ["团队", "用户", "人群", "社会", "员工", "客户", "群体"],
    "person-badge-fill": ["人才", "专家", "个人", "职业", "从业者"],
    "clock-fill": ["时间", "周期", "效率", "速度", "时效"],
    "hourglass-split": ["历史", "进程", "阶段", "演变", "演进"],
    "tree-fill": ["环境", "生态", "环保", "绿色", "自然", "可持续", "碳"],
    "globe2": ["全球", "世界", "国际", "海外", "全球化", "出海"],
    "diagram-3-fill": ["架构", "系统", "平台", "网络", "拓扑", "中台"],
    "bullseye": ["目标", "定位", "战略", "聚焦", "愿景"],
    "lightbulb-fill": ["灵感", "创意", "创新", "想法", "方案", "机遇"],
    "gear-fill": ["设置", "配置", "机制", "模式", "运营", "治理"],
    "file-earmark-text-fill": ["文档", "报告", "文件", "资料", "案例", "政策"],
    "chat-dots-fill": ["沟通", "交流", "对话", "客服", "交互", "反馈"],
    "cloud-fill": ["云计算", "云存储", "云端", "云平台", "上云", "SaaS"],
    "lock-fill": ["加密", "权限", "访问控制", "密码"],
    "star-fill": ["亮点", "特色", "优势", "重点", "核心"],
    "award-fill": ["荣誉", "成就", "认可", "排名", "奖"],
    "rocket-takeoff-fill": ["创业", "启动", "突破", "加速", "落地"],
    "speedometer2": ["性能", "效能", "响应", "延迟", "吞吐"],
    "buildings-fill": ["城市", "建筑", "产业", "园区", "地产", "制造"],
    "briefcase-fill": ["工作", "企业", "事业", "就业", "商务"],
    "eye-fill": ["观察", "洞察", "视野", "预测", "展望", "审视"],
    "search": ["搜索", "调研", "检索", "探索", "研究现状"],
    "check-circle-fill": ["结论", "完成", "达成", "总结", "验证"],
    "exclamation-triangle-fill": ["挑战", "风险", "问题", "困难", "危机", "痛点"],
}

# Very common words should not outrank a specific domain keyword.
_GENERIC = {
    "AI", "智能", "数据", "分析", "系统", "平台", "指标", "方案",
    "发展", "提升", "趋势", "变化", "用户", "企业", "工作", "重点",
    "优势", "核心",
}

_lock = threading.Lock()
_png_cache: dict[tuple[str, str], bytes | None] = {}
_warned_missing = False


def _hex(color) -> str:
    if isinstance(color, str):
        return color
    return "#{:02X}{:02X}{:02X}".format(int(color[0]), int(color[1]), int(color[2]))


def match_icon_name(text: str, title: str = "") -> str | None:
    """Return the best-matching icon stem, or None when nothing is confident."""
    text = str(text or "")
    title = str(title or "")
    best = None  # (score, keyword_len, icon_name)
    for name, keywords in ICON_KEYWORDS.items():
        for keyword in keywords:
            if keyword not in text:
                continue
            score = len(keyword) * (3 if keyword in title else 1)
            if keyword in _GENERIC:
                score *= 0.7
            candidate = (score, len(keyword), name)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    return best[2] if best else None


def rasterize_icon(icon_name: str, color, scale: float = ICON_SCALE) -> bytes | None:
    """Rasterize assets/icons/{name}.svg to a transparent PNG (cached)."""
    global _warned_missing
    color_hex = _hex(color)
    key = (icon_name, color_hex)
    with _lock:
        if key in _png_cache:
            return _png_cache[key]

    svg_path = ICON_DIR / f"{icon_name}.svg"
    png = None
    if not svg_path.exists():
        logger.warning("Icon not found: %s", svg_path)
    else:
        try:
            import cairosvg

            svg = svg_path.read_text(encoding="utf-8").replace(
                "currentColor", color_hex
            )
            size = max(8, int(16 * float(scale)))
            png = cairosvg.svg2png(
                bytestring=svg.encode("utf-8"),
                output_width=size,
                output_height=size,
            )
        except ImportError:
            if not _warned_missing:
                logger.warning(
                    "cairosvg not installed; icons disabled (pip install cairosvg)"
                )
                _warned_missing = True
        except Exception as e:
            logger.warning("Icon rasterization failed for %s: %s", icon_name, e)

    with _lock:
        _png_cache[key] = png
    return png


def get_icon_png_for_text(text: str, color, title: str = "") -> bytes | None:
    """Match + rasterize an icon for a snippet of text."""
    name = match_icon_name(f"{title} {text}", title=title)
    if not name:
        return None
    return rasterize_icon(name, color)


def get_icon_png(slide_data: dict, theme: dict, color=None) -> bytes | None:
    """Icon for a whole slide (title is weighted above bullet text)."""
    title = slide_data.get("title", "")
    points = slide_data.get("display_points") or slide_data.get("key_points") or []
    text = " ".join([title, str(slide_data.get("subtitle", ""))] +
                    [str(p) for p in points])
    if color is None:
        color = theme.get("white", (255, 255, 255))
    return get_icon_png_for_text(text, color, title=title)
