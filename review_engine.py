# 流程3：测试智能评审引擎——拼 prompt、调 AI、解析遗漏清单 JSON
import os
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from test_tree_utils import flat_to_compressed_path_list

try:
    from gemini_native import gemini_chat as _gemini_chat
except ImportError:
    _gemini_chat = None  # type: ignore[assignment]

# 期望的 AI 输出结构（供校验与文档）
REVIEW_ITEM_SCHEMA = """
items 数组中每项为以下之一：
- missing_branch: { "type": "missing_branch", "suggest_parent_path": "模块/子模块", "missing_scene": "场景名", "reason": "原因" }
- insufficient_coverage: { "type": "insufficient_coverage", "node_id": "node-xxx", "problem": "问题描述" }
- risk_node: { "type": "risk_node", "node_id": "node-xxx", "risk_score": 1-10, "reason": "原因" }
"""


def build_review_user_prompt(
    prd_text: str,
    prototype_text: str,
    compressed_path_list: str,
) -> str:
    """拼接 PRD + 原型 + 测试树路径列表 + 任务说明。"""
    return f"""# 业务需求
{prd_text or '（未提供）'}

# 页面原型说明
{prototype_text or '（未提供）'}

# 当前测试结构（树形，每行：路径 [id:xxx] level=N）
{compressed_path_list}

# 任务
1. 找出「完全缺失」的测试场景（原型/需求有但测试树没有），用 missing_branch 表示。
2. 找出「已存在但覆盖不完整」的节点，用 insufficient_coverage 表示，node_id 必须来自上面测试结构中的 id。
3. 可选：对涉及资金、权限、核心流程的节点给出 risk_node（risk_score 1-10）。

请只输出一个 JSON 对象，格式如下（不要其他说明）：
{{
  "summary": {{
    "total_missing": 数量,
    "weak_nodes": 数量,
    "risk_count": 数量
  }},
  "details": [
    {{ "type": "missing_branch", "suggest_parent_path": "...", "missing_scene": "...", "reason": "..." }},
    {{ "type": "insufficient_coverage", "node_id": "node-xxx", "problem": "..." }},
    {{ "type": "risk_node", "node_id": "node-xxx", "risk_score": 8, "reason": "..." }}
  ]
}}
"""


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """从模型回复中提取 JSON（兼容 ```json ... ``` 包裹）。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def call_review_llm(
    client: Any,
    model: str,
    system_content: str,
    user_content: str,
    use_gemini_native: bool = False,
) -> Dict[str, Any]:
    """调用 LLM 做评审，返回解析后的 JSON。"""
    if use_gemini_native and _gemini_chat:
        raw = _gemini_chat(
            model,
            [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
    else:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
    return _extract_json_from_response(raw)


def run_review(
    prd_text: str,
    prototype_text: str,
    flat_nodes: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    system_template_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    执行一次评审：拼 prompt、调 LLM、返回标准化的报告结构。
    flat_nodes 来自 xmind_to_test_tree 的 flat 列表。
    """
    load_dotenv()
    # 优先使用 Gemini（原生 SDK，支持 gemini-1.5-flash）；未配置则使用 DashScope（通义）
    use_gemini_native = bool(os.getenv("GEMINI_API_KEY"))
    if use_gemini_native:
        model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        api_key = os.getenv("GEMINI_API_KEY")
        client = None
    else:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        model = model or os.getenv("QWEN_MODEL", "qwen-plus")
        client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
    if not api_key and not use_gemini_native:
        raise RuntimeError("请在 .env 里配置 GEMINI_API_KEY 或 DASHSCOPE_API_KEY")

    root = os.path.dirname(os.path.abspath(__file__))
    prompt_dir = os.path.join(root, "prompt")
    system_path = system_template_path or os.path.join(prompt_dir, "review_system.txt")
    system_content = "输出必须是严格 JSON，不要写作文。"
    if os.path.exists(system_path):
        with open(system_path, "r", encoding="utf-8") as f:
            system_content = f.read()

    compressed = flat_to_compressed_path_list(flat_nodes)
    user_content = build_review_user_prompt(prd_text, prototype_text, compressed)
    raw_result = call_review_llm(client, model, system_content, user_content, use_gemini_native=use_gemini_native)

    # 标准化为统一报告结构
    summary = raw_result.get("summary") or {}
    details = raw_result.get("details")
    if not isinstance(details, list):
        details = []
    return {
        "summary": {
            "total_missing": summary.get("total_missing", 0),
            "weak_nodes": summary.get("weak_nodes", 0),
            "risk_count": summary.get("risk_count", 0),
        },
        "details": details,
    }
