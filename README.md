# 需求分析-测试点与用例生成

项目提供**三套流程**：

- **流程1**：需求文档 → 需求分析 + 测试点 MD + XMind（不生成测试用例）
- **流程2**：用户上传 XMind → AI 按指定格式生成测试用例（默认 Excel）
- **流程3**：用户上传 XMind + 可选 PRD/原型 → AI 测试智能评审（遗漏清单 JSON + 可回填 MD）

---

## 一、环境配置与依赖安装（首次使用必做）

按下面顺序做一遍，之后即可反复跑流程。

### 1. 虚拟环境（推荐）

用虚拟环境可避免依赖和本机其它项目混在一起。

| 在虚拟环境里运行     | 不在虚拟环境里运行         |
|----------------------|----------------------------|
| 依赖只装在本项目环境 | 容易装到系统/其它项目环境 |
| 换机器、协作更一致   | 容易版本冲突、行为不一致   |

**操作步骤：**

```bash
# 在项目根目录创建虚拟环境（如 .venv）
python -m venv .venv

# 激活虚拟环境
# Windows (PowerShell / CMD):
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
```

激活后，终端提示符前会多出 `(.venv)`，之后所有命令都在此环境下执行。

**在 macOS / Linux 上运行：** 本项目使用 `pathlib` 与 UTF-8，无 Windows 专用代码，可直接在 Mac 上使用。创建并激活虚拟环境后，流程命令与 Windows 一致；若系统只有 `python3`，将下文中的 `python` 改为 `python3` 即可（如 `python3 run_pipeline.py`）。

### 2. 安装依赖

在**已激活虚拟环境**的终端里执行：

```bash
pip install -r requirements.txt
```

### 3. 配置 API（必填）

在项目根目录新建 `.env` 文件，填入你的 API 配置（可从 `.env.example` 复制后修改）。**二选一**即可：

**方式 A：使用 Gemini（Google AI Studio，原生 SDK）**

- **GEMINI_API_KEY**：在 [Google AI Studio](https://aistudio.google.com/apikey) 申请 API Key，填此项即可
- GEMINI_MODEL：可选，默认 `gemini-2.0-flash`；支持文档中的全部模型，如 **gemini-1.5-flash**
- GEMINI_VISION_MODEL：流程1 图片识别时使用，可选，默认同 GEMINI_MODEL

**方式 B：使用阿里云 DashScope（通义千问）**

- **DASHSCOPE_API_KEY**：阿里云 DashScope API Key，**必填**
- DASHSCOPE_BASE_URL：可选
- QWEN_MODEL / DASHSCOPE_MODEL：可选，默认 `qwen-plus`
- DASHSCOPE_VISION_MODEL：流程1 图片识别时使用，可选，默认 `qwen-vl-plus`

若配置了 `GEMINI_API_KEY`，程序会优先使用 Gemini；否则使用 DashScope。完成以上三步后，即可按下面「二、流程执行」跑流程。

---

## 二、流程执行

### 流程1：需求 → 分析 + 测试点 + XMind

**做什么**：从需求文档生成「需求分析」「测试点 MD」「对话记录」「XMind」，不生成测试用例。

**步骤：**

1. 把需求文件放进 **inputs/** 目录。支持格式：`.md` / `.txt` / `.pdf` 或需求截图（`.png` / `.jpg` / `.jpeg` / `.webp`）。
2. 在项目根目录、已激活虚拟环境的终端里执行：

   ```bash
   # 不传参数：会列出 inputs/ 下的文件，让你选一个
   python run_pipeline.py

   # 或直接指定文件
   python run_pipeline.py inputs/我的需求.md
   ```

3. 运行结束后，在 **outputs/<需求文件名>/** 下查看：
   - `需求分析.md`
   - `测试点分析.md`
   - `对话记录.md`
   - `测试点.xmind`

---

### 流程2：上传 XMind → 生成测试用例

**做什么**：根据你提供的测试点 .xmind，用 AI 按模板生成 Excel 测试用例。

**步骤：**

1. 把要转换的 **.xmind** 文件放进 **xmind_excel_input/**（也可记下任意路径，后面直接传路径）。
2. 在项目根目录、已激活虚拟环境的终端里执行：

   ```bash
   # 不传参数：会列出 xmind_excel_input/ 下的 .xmind，让你选一个
   python run_xmind_to_cases.py

   # 或直接指定文件（可以是 xmind_excel_input/ 里的文件名或任意路径）
   python run_xmind_to_cases.py 测试点.xmind
   ```

3. 运行结束后，在 **xmind_excel_output/** 下查看生成的 Excel，**文件名与上传的 xmind 一致**（如 `测试点.xmind` → `测试点.xlsx`）。

**可选**：指定用例模板或输出路径：

```bash
python run_xmind_to_cases.py 测试点.xmind --template templates/用例模板.xlsx --output 我的用例.xlsx
```

用例模板：优先使用 `templates/用例模板.xlsx`，不存在则使用项目根目录的 `用例模板.xlsx`。表头支持：用例名称/标题、前置条件、步骤、预期、优先级等（中英文均可）。

---

### 流程3：上传 XMind + PRD/原型 → 测试智能评审 → 输出带 AI 建议的 XMind

**做什么**：基于「业务需求 + 页面原型」对比当前测试树，由 AI 输出遗漏清单；**在原有 XMind 的对应节点下增加 AI 建议内容**，只输出一份新的 .xmind 文件（原结构 + 【AI建议新增】【AI建议补充】【风险】等子节点）。

**步骤：**

1. 把待评审的 **.xmind** 放进 **xmind_review_input/**。可选：同目录下放需求/原型文档，支持固定名 `prd.txt`、`原型.txt` 等，**或任意 .md / .txt**（会一并作为需求与原型内容用于对比）。
2. 在项目根目录执行：

   ```bash
   # 不传参数：列出 xmind_review_input/ 下的 .xmind 选一个
   python run_xmind_review.py

   # 或指定 xmind 与 PRD/原型
   python run_xmind_review.py 测试点.xmind --prd 需求.txt --prototype 原型.txt
   ```

3. 运行结束后，在 **xmind_review_output/** 下得到 **`<文件名>_评审结果.xmind`**：在原测试树基础上，在对应节点下增加了 AI 建议（建议新增场景、建议补充、风险节点等），可直接用 XMind 打开编辑。

**说明**：测试树解析采用统一协议（每个节点含 id、path、parent_id、level），便于 AI 用 node_id 精确定位；若未提供 PRD/原型，仅基于当前树做简单检查。

---

## 三、目录结构

```
aitest/
├── inputs/                 # 流程1：把需求文档放这里
├── outputs/                # 流程1：生成结果（按需求文件名分子目录）
├── xmind_excel_input/      # 流程2：把待转换的 .xmind 放这里（内有 .gitkeep 占位）
├── xmind_excel_output/     # 流程2：生成的 Excel 在这里（内有 .gitkeep 占位）
├── xmind_review_input/     # 流程3：待评审 .xmind + 可选 prd.txt / prototype.txt
├── xmind_review_output/    # 流程3：评审结果.xmind
├── templates/              # 流程2：用例模板.xlsx（可选）
├── prompt/
│   ├── system_template.txt   # 流程1：需求→测试点
│   ├── review_system.txt    # 流程3：评审用 system 提示词
│   ├── cases_system.txt    # 流程2：XMind→Excel 系统提示词
│   └── cases_user.txt      # 流程2：XMind→Excel 用户提示词（占位符 {{TEST_POINT_PATH}}）
├── run_pipeline.py         # 流程1 入口
├── run_xmind_to_cases.py   # 流程2 入口
├── run_xmind_review.py     # 流程3 入口
├── step0_req_to_analysis.py
├── step1_req_to_md.py
├── step2_md_to_xmind.py
├── step3_xmind_to_excel.py # 流程2 核心
├── generate_md_v2.py       # 流程1 核心逻辑（需求解析、测试点生成）
├── generate_cases_mvp.py   # 流程2 核心逻辑（XMind 解析、用例生成）
├── xmind_to_test_tree.py   # 流程3：XMind → 统一测试树（id/path/level）
├── test_tree_utils.py      # 流程3：树转 MD、路径列表、id 映射
├── review_engine.py        # 流程3：拼 prompt、调 AI、解析遗漏清单
├── review_output.py        # 流程3：写报告 JSON、可回填 MD
├── review_to_xmind.py      # 流程3：合并 AI 建议到测试树并输出评审结果.xmind
├── .env                    # 你的 API 配置（必填）
└── .env.example             # 配置示例
```

**关于 .gitkeep**：`xmind_excel_input/`、`xmind_excel_output/`、`xmind_review_input/`、`xmind_review_output/` 下的 `.gitkeep` 是占位文件，用于在 Git 中保留空目录。

---

## 四、脚本说明

| 文件 | 说明 |
|------|------|
| `run_pipeline.py` | 流程1 入口：需求 → 分析 + 测试点 + XMind |
| `run_xmind_to_cases.py` | 流程2 入口：用户 XMind → 指定格式测试用例 |
| `run_xmind_review.py` | 流程3 入口：XMind + PRD/原型 → AI 遗漏检测 → 报告 + 可回填 MD |
| `step0_req_to_analysis.py` | 流程1：需求 → 5W1H 需求分析 MD |
| `step1_req_to_md.py` | 流程1：需求 → 测试点 MD + 对话记录 |
| `step2_md_to_xmind.py` | 流程1：MD → XMind |
| `step3_xmind_to_excel.py` | 流程2：XMind + 模板 → Excel 用例 |
| `generate_md_v2.py` | 流程1 核心：需求解析与测试点 MD 生成（被 step0/step1/run_pipeline 调用） |
| `generate_cases_mvp.py` | 流程2 核心：解析 XMind、调 LLM 生成用例并填 Excel（被 step3 调用） |
| `xmind_to_test_tree.py` | 流程3：XMind → 统一测试树协议（id/path/parent_id/level） |
| `test_tree_utils.py` | 流程3：树转 MD、压缩路径列表、node_id 映射 |
| `review_engine.py` | 流程3：拼接 PRD/原型/测试树、调 LLM、解析遗漏清单 JSON |
| `review_output.py` | 流程3：输出 AI检查报告.json、可回填.md |
| `review_to_xmind.py` | 流程3：将 AI 建议合并回测试树并写出评审结果.xmind |
