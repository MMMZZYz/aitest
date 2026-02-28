# 旧版：需求 → 测试点 MD（固定 schema），未接图片识别和 5W1H。
import os
import re
import json
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

load_dotenv()

# ========== DashScope(OpenAI Compatible) ==========
API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    raise SystemExit("Missing DASHSCOPE_API_KEY in .env")

BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-plus")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ========== Output Schema: sections -> subsections -> points ==========
SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "subsections": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "minLength": 1},
                                "points": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"type": "string", "minLength": 1},
                                },
                            },
                            "required": ["title", "points"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "subsections"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}

CONTEXT_GOODS_PATH = "context_goods.txt"


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _extract_json_object(text: str) -> str:
    """
    模型有时会在 JSON 前后夹杂解释文字；这里做稳健截取：
    - 优先截取第一个 '{' 到最后一个 '}' 之间的内容
    """
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return text[start : end + 1]


def llm_generate_sections(req_text: str) -> Dict[str, Any]:
    goods_ctx = ""
    if os.path.exists(CONTEXT_GOODS_PATH):
        goods_ctx = read_text(CONTEXT_GOODS_PATH)

    prompt_parts: List[str] = []
    prompt_parts.append("你是资深软件测试工程师，擅长把需求拆成可评审的测试点结构。")
    if goods_ctx:
        prompt_parts.append("下面是【业务上下文】（请充分利用）：")
        prompt_parts.append(goods_ctx)

    prompt_parts.append("下面是【需求正文】：")
    prompt_parts.append(req_text)

    prompt_parts.append(
        """
请输出“测试点清单”，必须严格只输出 JSON（不要任何多余文字），结构如下：

{
  "sections": [
    {
      "title": "一、功能一：按钮-导出",
      "subsections": [
        {
          "title": "1️⃣ 按钮展示与交互",
          "points": ["测试点1", "测试点2"]
        }
      ]
    }
  ]
}

强制要求：
1）顶层必须包含以下 5 个 section（按顺序、标题必须一致）：
- 一、功能一：按钮-导出
- 二、功能二：按钮-批量作废
- 三、复选框逻辑
- 四、跨功能联动测试
- 五、隐藏雷点（重点）

2）每个 section 必须至少 2 个 subsections（“隐藏雷点”至少 1 个）。
3）每个 subsection 的 points 不要写空数组；每条测试点写成一句话，尽量可直接转用例。
4）要体现供应链系统的风险意识：口径一致性、并发一致性、分页/批量上限、导出任务幂等性、日志审计等（放在合适 section 或隐藏雷点里）。
"""
    )

    prompt = "\n\n".join(prompt_parts)

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content or ""
    json_text = _extract_json_object(raw)
    data = json.loads(json_text)

    # schema validate
    validate(instance=data, schema=SCHEMA)
    return data


def save_to_markdown(data: Dict[str, Any], out_path: str, title: str = "测试点清单") -> None:
    lines: List[str] = []
    lines.append(f"# {title}\n")

    for section in data["sections"]:
        lines.append(f"## {section['title']}\n")
        for subsection in section["subsections"]:
            lines.append(f"### {subsection['title']}\n")
            for p in subsection["points"]:
                lines.append(f"- {p}")
            lines.append("")  # blank line

    content = "\n".join(lines).rstrip() + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)


def save_to_json(data: Dict[str, Any], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python generate_md.py inputs/req.md")

    in_path = sys.argv[1]
    req_text = read_text(in_path)

    result = llm_generate_sections(req_text)

    os.makedirs("outputs", exist_ok=True)
    json_path = os.path.join("outputs", "test_points_struct.json")
    md_path = os.path.join("outputs", "test_points.md")

    save_to_json(result, json_path)
    save_to_markdown(result, md_path, title=os.path.basename(in_path))

    print(f"OK -> {json_path}")
    print(f"OK -> {md_path}")


if __name__ == "__main__":
    main()