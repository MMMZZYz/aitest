# 需求分析-测试点与用例生成

项目提供**两套流程**：

- **流程1**：需求文档 → 需求分析 + 测试点 MD + XMind（不生成测试用例）
- **流程2**：用户上传 XMind → AI 按指定格式生成测试用例（默认 Excel）

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

### 2. 安装依赖

在**已激活虚拟环境**的终端里执行：

```bash
pip install -r requirements.txt
```

### 3. 配置 API（必填）

在项目根目录新建 `.env` 文件，填入你的 API 配置（可从 `.env.example` 复制后修改）：

- **DASHSCOPE_API_KEY**：阿里云 DashScope（通义千问）API Key，**必填**
- DASHSCOPE_BASE_URL：可选
- QWEN_MODEL / DASHSCOPE_MODEL：可选，默认 `qwen-plus`
- DASHSCOPE_VISION_MODEL：流程1 用图片识别时使用，可选，默认 `qwen-vl-plus`

完成以上三步后，即可按下面「二、流程执行」跑流程。

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

## 三、目录结构

```
aitest/
├── inputs/                 # 流程1：把需求文档放这里
├── outputs/                # 流程1：生成结果（按需求文件名分子目录）
├── xmind_excel_input/      # 流程2：把待转换的 .xmind 放这里（内有 .gitkeep 占位）
├── xmind_excel_output/     # 流程2：生成的 Excel 在这里（内有 .gitkeep 占位）
├── templates/              # 流程2：用例模板.xlsx（可选）
├── prompt/
│   └── system_template.txt
├── run_pipeline.py         # 流程1 入口
├── run_xmind_to_cases.py   # 流程2 入口
├── step0_req_to_analysis.py
├── step1_req_to_md.py
├── step2_md_to_xmind.py
├── step3_xmind_to_excel.py # 流程2 核心
├── generate_md_v2.py       # 流程1 核心逻辑（需求解析、测试点生成）
├── generate_cases_mvp.py   # 流程2 核心逻辑（XMind 解析、用例生成）
├── .env                    # 你的 API 配置（必填）
└── .env.example             # 配置示例
```

**关于 .gitkeep**：`xmind_excel_input/` 和 `xmind_excel_output/` 下的 `.gitkeep` 是占位文件。Git 默认不跟踪空目录，放一个空文件（习惯命名 `.gitkeep`）可以让仓库里保留这两个文件夹，别人克隆后不用再新建，直接把 xmind 放进 `xmind_excel_input/` 即可使用。无需删除，也不影响使用。

---

## 四、脚本说明

| 文件 | 说明 |
|------|------|
| `run_pipeline.py` | 流程1 入口：需求 → 分析 + 测试点 + XMind |
| `run_xmind_to_cases.py` | 流程2 入口：用户 XMind → 指定格式测试用例 |
| `step0_req_to_analysis.py` | 流程1：需求 → 5W1H 需求分析 MD |
| `step1_req_to_md.py` | 流程1：需求 → 测试点 MD + 对话记录 |
| `step2_md_to_xmind.py` | 流程1：MD → XMind |
| `step3_xmind_to_excel.py` | 流程2：XMind + 模板 → Excel 用例 |
| `generate_md_v2.py` | 流程1 核心：需求解析与测试点 MD 生成（被 step0/step1/run_pipeline 调用） |
| `generate_cases_mvp.py` | 流程2 核心：解析 XMind、调 LLM 生成用例并填 Excel（被 step3 调用） |
