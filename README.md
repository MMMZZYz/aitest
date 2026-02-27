# 测试点与用例生成流水线

从**需求文档**生成 **需求分析(5W1H)** → **MD 测试点** → **XMind 测试点** → **Excel 测试用例** 的一键流水线。

## 目标流程

1. **inputs** 放入需求：**.md / .txt**、**.pdf** 或 **需求截图**（.png / .jpg / .jpeg / .webp）
2. 生成 **需求分析 MD**（outputs/需求分析.md）：用 5W1H 浅显说明「这次需求在做什么」，方便用户快速理解
3. 生成 **MD 测试点文件**（outputs/test_points.md）
4. MD 转为 **XMind 测试点文档**（outputs/test_points.xmind）
5. 根据测试点 + 用例模板 生成 **Excel 用例**（outputs/测试用例.xlsx）

- **PDF**：直接上传 PDF，会先解析正文文字再生成测试点（适用于可选中文字的数字 PDF；扫描件建议导出为图片后上传）。
- **图片**：使用视觉模型（如 qwen-vl-plus）识别图中需求/原型/文档，再生成测试点。

## 目录结构

```
aitest/
├── inputs/           # 放需求文档（.md 或 .txt）
├── outputs/          # 生成结果
│   ├── 需求分析.md       # 5W1H 需求说明（先于测试点生成）
│   ├── test_points.md
│   ├── test_points_struct.json
│   ├── test_points.xmind
│   └── 测试用例.xlsx
├── templates/        # 用例模板（可选）
│   └── 用例模板.xlsx
├── run_pipeline.py   # 一键运行全流程
├── step0_req_to_analysis.py  # 需求 → 需求分析（5W1H）MD
├── step1_req_to_md.py        # 需求 → MD 测试点
├── step2_md_to_xmind.py  # MD → XMind
├── step3_xmind_to_excel.py  # XMind + 模板 → Excel
├── generate_md_v2.py      # 需求→MD 核心逻辑
├── generate_cases_mvp.py  # XMind→Excel 核心逻辑
└── .env              # DASHSCOPE_API_KEY 等配置
```

## 环境与配置

1. 安装依赖：`pip install -r requirements.txt`
2. 在项目根目录新建 `.env`，配置：
   - `DASHSCOPE_API_KEY`：阿里云 DashScope（通义千问）API Key，必填
   - `DASHSCOPE_BASE_URL`：可选，默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`
   - `QWEN_MODEL` / `DASHSCOPE_MODEL`：可选，默认 `qwen-plus`
   - `DASHSCOPE_VISION_MODEL`：需求端图片识别时使用的视觉模型，可选，默认 `qwen-vl-plus`（需在百炼/控制台开通多模态能力）

## 使用方式

### 一键运行（推荐）

```bash
# 自动使用 inputs 下第一个 .md 或 .txt
python run_pipeline.py

# 指定需求文件
python run_pipeline.py inputs/我的需求.md
```

### 分步执行

```bash
# 步骤0：需求 → 需求分析（5W1H）MD
python step0_req_to_analysis.py
python step0_req_to_analysis.py inputs/需求.md

# 步骤1：需求 → MD 测试点
python step1_req_to_md.py
python step1_req_to_md.py inputs/需求.md

# 步骤2：MD → XMind
python step2_md_to_xmind.py

# 步骤3：XMind + 模板 → Excel 用例
python step3_xmind_to_excel.py
```

### 用例模板

- 优先使用 `templates/用例模板.xlsx`
- 若不存在则使用项目根目录的 `用例模板.xlsx`
- 表头支持：用例名称/标题、前置条件、步骤、预期、优先级等（中英文均可，脚本会按关键词匹配）

## 其他脚本说明

| 文件 | 说明 |
|------|------|
| `step0_req_to_analysis.py` | 需求 → 5W1H 需求分析 MD（outputs/需求分析.md） |
| `generate_md_v2.py` | 需求 → 结构化测试点 JSON + MD（含 5W1H 分析函数，step1 调用） |
| `generate_cases_mvp.py` | 解析 XMind 叶子节点，调 LLM 生成用例并填 Excel（step3 调用） |
| `md_to_xmind.py` | 旧版：用 xmind 库将 MD 转 XMind（step2 使用自带的 Zen 格式转换，与此独立） |
| `generate.py` | 旧版：需求→六维测试点 JSON/Excel/XMind（另一套结构，可按需使用） |
| `xmind_export_zen.py` | 将六维测试点 dict 导出为 XMind Zen 格式（供 generate.py 使用） |
| `app_cases.py` | FastAPI 服务：上传 XMind，返回生成的 Excel 下载 |

## Web 服务（可选）

```bash
uvicorn app_cases:app --reload
```

- **需求端**：上传需求文档（.md/.txt）、**PDF** 或需求图片（.png/.jpg/.jpeg/.webp），可下载生成的测试点 MD。
- **XMind → Excel**：上传测试点 XMind，下载生成的 Excel 用例。
