# SmartPPT-AI 智能PPT生成系统

从主题/大纲到视觉呈现的自动化 PPT 生成工具。支持输入 Markdown 大纲或纯文本，自动识别标题层级、智能分页、匹配配图，导出专业 16:9 演示文稿。

## 核心功能

| # | 功能 | 实现方式 |
|---|------|----------|
| ① | **Markdown大纲输入 + 标题层级识别 + 自动分页** | `parser.py` 解析 `#/##/###` 标题，H2 自动分页，纯文本自动分段 |
| ② | **根据关键词推荐配图** | `agents/image_fetcher.py` 调用 Unsplash API，渐进式关键词降级（具体→宽泛） |
| ③ | **主题色 + 布局模板可选择** | `config.py` 6套主题色 + `templates/slide_templates.py` 9种布局模板 |
| ④ | **联网搜索补充真实信息** | `agents/tavily_search.py` 调用 Tavily API，缓解 AI 幻觉 |
| ⑤ | **导出可编辑 PPTX** | `engine/pptx_renderer.py` 基于 python-pptx 渲染，16:9 标准比例 |

## 技术栈

| 组件 | 技术 |
|------|------|
| 大模型 | 智谱 GLM（规划 glm-4-plus / 扩写与翻译 glm-4-flash） |
| 联网搜索 | Tavily API（检索真实资讯、案例、数据，可关闭） |
| 图片库 | Unsplash API |
| PPT渲染 | python-pptx |
| Web框架 | FastAPI + SSE 实时进度推送 |
| 并发 | ThreadPoolExecutor |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的智谱 GLM 密钥（必须）与 Unsplash / Tavily 密钥（可选）
```

| 密钥 | 是否必须 | 说明 |
|------|---------|------|
| `GLM_API_KEY` | ✅ 必须 | 智谱开放平台申请：https://open.bigmodel.cn |
| `UNSPLASH_ACCESS_KEY` | ✅ 必须 | Unsplash 开发者平台申请：https://unsplash.com/developers |
| `TAVILY_API_KEY` | ⭕ 可选 | 缺失时自动降级为纯 AI 生成（不联网搜索） |

### 3. 运行

**Web 模式（推荐）：**

```bash
cd ppt_agent
python server.py
# 浏览器打开 http://localhost:8000
```

**CLI 模式：**

```bash
cd ppt_agent

# 方式1：输入主题
python main.py "人工智能在医疗领域的应用"

# 方式2：指定 Markdown 文件
python main.py outline.md

# 方式3：指定主题 + 主题色
python main.py "校园低碳生活" --theme eco_nature

# 方式4：交互式输入
python main.py
```

### 4. 主题色选择

| 主题ID | 名称 | 适用场景 |
|--------|------|----------|
| `campus_academic` | 校园学术 | 学术报告、课程作业 |
| `business_report` | 商务汇报 | 企业汇报、商业计划 |
| `tech_creative` | 科技创意 | 技术分享、创新方案 |
| `eco_nature` | 环保自然 | 环保主题、自然生态 |
| `literature_art` | 文艺阅读 | 文化艺术、历史哲学 |
| `minimal_general` | 简约通用 | 通用场景 |

## 项目结构

```
SmartPPT-AI/
├── ppt_agent/                          # 主代码目录
│   ├── main.py                         # CLI 入口（支持 --search on/off）
│   ├── server.py                       # FastAPI Web 服务（SSE进度推送）
│   ├── config.py                       # 配置中心 + 6套主题色方案 + IPv4 网络偏好
│   ├── search_config.py                # 联网搜索配置（开关、参数、缓存）
│   ├── pipeline.py                     # 统一流水线（含并发联网搜索节点）
│   ├── parser.py                       # Markdown/纯文本解析器
│   ├── index.html                      # 前端页面
│   │
│   ├── agents/                         # AI Agent 层
│   │   ├── planner.py                  # GLM-4-Plus: 主题 → 结构化大纲
│   │   ├── writer.py                   # GLM-4-Flash: 大纲 → 详细内容
│   │   ├── translator.py              # GLM-4-Flash: 中文 → 英文关键词
│   │   ├── image_fetcher.py            # Unsplash API: 关键词 → 图片
│   │   └── tavily_search.py            # Tavily API: 联网搜索真实资讯
│   │
│   ├── engine/                         # 渲染引擎层
│   │   ├── layout_engine.py            # 9种布局坐标定义 (Region dataclass)
│   │   └── pptx_renderer.py           # python-pptx 底层绘制原语
│   │
│   ├── templates/                      # 模板层
│   │   └── slide_templates.py          # 9种布局渲染器 + 分发表
│   │
│   └── utils/                          # 工具层
│       ├── json_parser.py              # 多策略JSON解析器
│       └── font_size.py                # 自适应字号计算器
│
├── output/                             # 生成的PPTX文件输出目录（运行时创建）
├── .env.example                        # 密钥配置模板（复制为 .env 后填写）
├── requirements.txt                    # Python依赖
└── README.md
```

## 模块说明

| 模块 | 职责 |
|------|------|
| `parser.py` | 解析 Markdown 大纲：识别 `#/##/###` 标题层级，H2 自动分页，纯文本按段落分页 |
| `config.py` | 加载 .env 配置、定义 6 套主题色方案、关键词自动匹配主题、强制 IPv4 网络偏好 |
| `search_config.py` | 联网搜索配置：功能开关、检索参数、缓存设置（密钥从 .env 读取） |
| `pipeline.py` | 统一流水线：搜索→规划→扩写→翻译→搜图→渲染，搜索与扩写节点并发执行 |
| `agents/planner.py` | 调用 GLM-4-Plus，根据主题生成 12~22 页结构化大纲 JSON |
| `agents/writer.py` | 调用 GLM-4-Flash，将大纲扩写为 4~6 条详细展示要点 + 演讲者注释 |
| `agents/translator.py` | 调用 GLM-4-Flash，将中文关键词翻译为 3 级英文搜索词（具体→宽泛） |
| `agents/image_fetcher.py` | 调用 Unsplash Search API，渐进式搜索 + LRU缓存 + 自动降级 |
| `agents/tavily_search.py` | 调用 Tavily API 联网搜索，内存缓存 + 异常降级 |
| `engine/layout_engine.py` | 定义 9 种布局的精确坐标（Region dataclass，16:9 英寸坐标系） |
| `engine/pptx_renderer.py` | python-pptx 绘制原语：矩形、文本框、要点列表、图片嵌入 |
| `templates/slide_templates.py` | 9 种布局的具体渲染逻辑 + 动态主题色支持 |
| `utils/json_parser.py` | 多策略 LLM 输出 JSON 解析（围栏去除、括号提取、智能引号修复） |
| `utils/font_size.py` | 中英文混排自适应字号计算器 |

## 核心算法流程

```
输入（主题 / Markdown大纲 / 纯文本）
  │
  ├─ Markdown/文本 → parser.py 解析 → 结构化页面数据
  └─ 主题字符串 → tavily_search.py → 联网搜索主题资讯
  │
  ▼
agents/planner.py → GLM-4-Plus 生成大纲JSON（参考联网资讯）
  │
  ▼
tavily_search.py → 并发搜索各页面定向资料
  │
  ▼
agents/writer.py → GLM-4-Flash 并发扩写每页内容（参考联网资料）
  │
  ▼
agents/translator.py → 中文关键词 → 3级英文搜索词
  │
  ▼
agents/image_fetcher.py → Unsplash 并发搜图（4线程）
  │
  ▼
templates/slide_templates.py → 9种布局 + 动态主题色渲染
  │
  ▼
engine/pptx_renderer.py → python-pptx 生成可编辑 .pptx 文件
```

## 联网搜索功能

### 功能说明

联网搜索模块通过 Tavily API 获取真实网络资讯，用于：
- 补充最新数据、案例、统计信息
- 缓解 AI 生成内容的幻觉问题
- 丰富 PPT 素材的真实性和可信度

### 搜索嵌入节点

| 节点 | 搜索目的 | 传递方式 |
|------|----------|----------|
| 大纲生成前 | 搜索主题相关资讯、背景资料 | `web_context` 传入 planner |
| 正文扩写前 | 搜索各页面定向资料、具体数据 | `_web_context` 传入 writer |

### 全局开关

```bash
# CLI 模式：通过 --search 参数控制
python main.py "人工智能" --search on   # 开启
python main.py "人工智能" --search off  # 关闭

# Web 模式：通过 API 请求体控制
POST /api/generate
{
  "topic": "人工智能",
  "search_enabled": true
}

# 环境变量控制
export TAVILY_SEARCH_ENABLED=1  # 开启
export TAVILY_SEARCH_ENABLED=0  # 关闭
```

### 异常降级

联网搜索异常时自动降级为纯 AI 生成，保证 PPT 主流程正常运行：
- 网络超时 → 跳过搜索，继续生成
- API 调用失败 → 跳过搜索，继续生成
- 无搜索结果 → 跳过搜索，继续生成

## 网络说明

- 代码在 `config.py` 中统一强制 IPv4 优先，规避部分网络环境下 IPv6 路由不稳定导致的连接失败
- 本项目的 API 供应商（智谱、Unsplash、Tavily）均为国内直连可用，无需代理

## 运行命令汇总

```bash
# Web 模式
cd ppt_agent && python server.py

# CLI 模式
cd ppt_agent && python main.py "主题"
cd ppt_agent && python main.py outline.md
cd ppt_agent && python main.py "主题" --theme tech_creative
cd ppt_agent && python main.py "主题" --search on    # 开启联网搜索
cd ppt_agent && python main.py "主题" --search off   # 关闭联网搜索
```

## 安全约定

- 所有 API 密钥统一存放于 `.env`（已被 `.gitignore` 排除），源码中不硬编码任何密钥
- 提交代码前请勿将 `.env`、`archive/`、`output/` 中的文件加入版本控制
