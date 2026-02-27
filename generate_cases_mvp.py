# generate_cases_mvp.py
import os
import re
import json
import zipfile
import io
import tempfile
from typing import List, Dict, Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


# ========= 1) 解析 XMind =========
def parse_xmind_leaf_paths(xmind_path: str) -> List[List[str]]:
    """
    返回所有节点路径（含中间节点），你可以把最后一个视作“测试点”。
    """
    out: List[List[str]] = []

    def walk(node: Dict[str, Any], path: List[str]):
        title = (node.get("title") or "").strip()
        cur = path + ([title] if title else [])
        if title:
            out.append(cur)
        for child in node.get("children", {}).get("attached", []) or []:
            walk(child, cur)

    with zipfile.ZipFile(xmind_path, "r") as z:
        # 通常是 content.json
        name = "content.json" if "content.json" in z.namelist() else None
        if not name:
            cand = [n for n in z.namelist() if n.endswith("content.json")]
            if not cand:
                return []
            name = cand[0]
        data = json.loads(z.read(name).decode("utf-8"))

    if isinstance(data, list):
        for sheet in data:
            root = sheet.get("rootTopic")
            if root:
                walk(root, [])
    elif isinstance(data, dict):
        root = data.get("rootTopic")
        if root:
            walk(root, [])

    # 只保留“叶子节点路径”（最后一级不再有 children）
    # 简化：把所有路径里“不是任何其他路径前缀的”当叶子
    set_paths = [tuple(p) for p in out if len(p) >= 2]
    set_all = set(set_paths)
    leaf = []
    for p in set_paths:
        is_prefix = False
        for q in set_paths:
            if len(q) > len(p) and q[: len(p)] == p:
                is_prefix = True
                break
        if not is_prefix:
            leaf.append(list(p))
    return leaf


# ========= 2) 调千问（OpenAI兼容） =========
def build_prompt(path: List[str]) -> str:
    """
    超简 prompt：给一个测试点路径，让模型产出可执行用例 JSON。
    """
    return f"""
你是资深测试工程师。根据“测试点路径”生成测试用例。
测试点路径：{" > ".join(path)}

要求：
- 输出 1~3 条测试用例（不要太多）
- 每条用例包含：title / preconditions / steps / expected / priority
- steps 和 expected 要一一对应、可执行
- 只能输出严格 JSON，不要解释、不要Markdown

输出JSON格式：
{{
  "cases": [
    {{
      "title": "...",
      "preconditions": ["..."],
      "steps": ["1...", "2..."],
      "expected": ["1...", "2..."],
      "priority": "High|Medium|Low"
    }}
  ]
}}
""".strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def llm_generate(client: OpenAI, model: str, prompt: str) -> List[Dict[str, Any]]:
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "输出必须是严格JSON。"},
            {"role": "user", "content": prompt},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()

    # 兼容 ```json 包裹
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    data = json.loads(text)
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("LLM output: cases is not a list")
    return cases


# ========= 3) 写入 Excel（按模板表头自动匹配） =========
def read_template_columns(xlsx_path: str, sheet_name: str = None) -> List[str]:
    """
    读取用例模板表头：
    - 默认取第一个工作表
    - sheet_name 传入时则按指定工作表名/索引
    """
    try:
        df_or_dict = pd.read_excel(
            xlsx_path,
            sheet_name=sheet_name if sheet_name is not None else 0,
            engine="openpyxl",
        )
    except ValueError as e:
        # pandas 有时无法自动识别格式（例如文件不是标准 xlsx、内容损坏、或被错误改了后缀）
        raise SystemExit(
            f"读取模板失败：{xlsx_path}\n"
            f"- 可能原因：文件不是标准 .xlsx（例如 .csv 改后缀）、文件损坏、或被占用\n"
            f"- 建议：用 Excel 重新“另存为 .xlsx”，并确保关闭占用该文件的 Excel\n"
            f"- 原始错误：{e}"
        )

    # 兼容 sheet_name=None 返回 dict 的情况，取第一个 sheet
    if isinstance(df_or_dict, dict):
        if not df_or_dict:
            raise SystemExit(f"读取模板失败：{xlsx_path} 没有任何工作表")
        df = next(iter(df_or_dict.values()))
    else:
        df = df_or_dict

    return list(df.columns)


def _strip_leading_number(text: str) -> str:
    """去掉字符串开头已有的序号（如 '1. '、'2、'），避免与后续统一编号重复成 1.1、2.2。"""
    if not (text or text.strip()):
        return text
    return re.sub(r"^\s*\d+[\.、]\s*", "", text.strip()).strip() or text.strip()


def map_case_to_row(case: Dict[str, Any], columns: List[str]) -> Dict[str, Any]:
    """
    按列名关键词匹配，尽量通用：
    - 名称/标题/summary
    - 前置/precondition
    - 步骤/step
    - 预期/expected
    - 优先级/priority
    """
    title = case.get("title", "")
    pre = "\n".join(case.get("preconditions", []) or [])
    raw_steps = case.get("steps", []) or []
    raw_expected = case.get("expected", []) or []
    steps = "\n".join([f"{i+1}. {_strip_leading_number(s)}" for i, s in enumerate(raw_steps)])
    exp = "\n".join([f"{i+1}. {_strip_leading_number(e)}" for i, e in enumerate(raw_expected)])
    prio = case.get("priority", "Medium")

    row = {}
    for col in columns:
        k = str(col).lower()
        if ("summary" in k) or ("标题" in col) or ("名称" in col) or ("用例" in col and "名" in col):
            row[col] = title
        elif ("precondition" in k) or ("前置" in col):
            row[col] = pre
        elif ("step" in k) or ("步骤" in col) or ("操作" in col):
            row[col] = steps
        elif ("expected" in k) or ("预期" in col) or ("结果" in col):
            row[col] = exp
        elif ("priority" in k) or ("优先级" in col):
            row[col] = prio
        else:
            row[col] = ""
    return row


def generate_cases_from_xmind_bytes(xmind_bytes: bytes, template_xlsx: str) -> bytes:
    """
    将上传的 XMind bytes + 本地模板，生成 Excel bytes（用于 Web 下载）。
    """
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.getenv("QWEN_MODEL", "qwen-plus")

    if not api_key:
        raise SystemExit("缺少 DASHSCOPE_API_KEY（请在 .env 里配置）")
    if not os.path.exists(template_xlsx):
        raise SystemExit(f"找不到模板文件：{template_xlsx}")

    # 写入临时 xmind 文件
    with tempfile.NamedTemporaryFile(suffix=".xmind", delete=False) as tmp:
        tmp.write(xmind_bytes)
        tmp_path = tmp.name

    try:
        leaf_paths = parse_xmind_leaf_paths(tmp_path)
        if not leaf_paths:
            raise SystemExit("没有解析到有效的 XMind 叶子节点（测试点）")
        print(f"[CASES] 解析到叶子测试点数量: {len(leaf_paths)}")

        client = OpenAI(api_key=api_key, base_url=base_url)
        columns = read_template_columns(template_xlsx)
        rows: List[Dict[str, Any]] = []

        # 每个叶子节点生成 1~3 条
        for idx, path in enumerate(leaf_paths, start=1):
            prompt = build_prompt(path)
            cases = llm_generate(client, model, prompt)
            for c in cases:
                rows.append(map_case_to_row(c, columns))
            if idx % 5 == 0:
                print(f"[CASES] 已处理测试点 {idx}/{len(leaf_paths)}，当前用例总数={len(rows)}")

        out_df = pd.DataFrame(rows, columns=columns)
        buf = io.BytesIO()
        out_df.to_excel(buf, index=False)
        buf.seek(0)
        print(f"[CASES] 生成用例完成，总用例数={len(rows)}")
        return buf.getvalue()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def main():
    """
    本地 CLI 入口：从当前目录读取“测试点.xmind”，输出“输出用例.xlsx”。
    """
    xmind_file = "测试点.xmind"
    template_xlsx = "用例模板.xlsx"
    out_xlsx = "输出用例.xlsx"

    if not os.path.exists(xmind_file):
        raise SystemExit(f"找不到 {xmind_file}")

    with open(xmind_file, "rb") as f:
        xmind_bytes = f.read()

    excel_bytes = generate_cases_from_xmind_bytes(xmind_bytes, template_xlsx)
    with open(out_xlsx, "wb") as f:
        f.write(excel_bytes)

    print(f"✅ 已生成：{out_xlsx}")


if __name__ == "__main__":
    main()