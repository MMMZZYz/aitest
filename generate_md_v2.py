# 需求 → 测试点核心逻辑（含 get_req_text、图片识别、5W1H、llm_generate_struct、build_test_point_prompt 等）
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI
from pypdf import PdfReader

load_dotenv()

# ===== DashScope(OpenAI compatible) =====
API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    raise SystemExit("Missing DASHSCOPE_API_KEY in .env")

BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-plus")
# 视觉模型：用于从需求截图/文档图中提取文字（需开通多模态能力）
VISION_MODEL = os.getenv("DASHSCOPE_VISION_MODEL", "qwen-vl-plus")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

CONTEXT_GOODS_PATH = "context_goods.txt"

# 需求端支持的图片格式
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
PDF_EXTENSION = ".pdf"


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def read_pdf_text(path: str) -> str:
    """
    从 PDF 文件提取文本（适用于可选中文字的数字 PDF）。
    若为扫描件/纯图 PDF，提取结果可能为空，建议改为上传图片或使用 OCR。
    """
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text()
            if t:
                parts.append(t.strip())
        except Exception:
            continue
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError(
            "PDF 中未提取到文字（可能是扫描件或图片型 PDF），请尝试："
            " 将每页导出为图片后上传，或使用带 OCR 的工具先转成文字。"
        )
    return text


def _image_to_data_url(image_path: str) -> str:
    """将本地图片转为 data URL，供视觉 API 使用。"""
    ext = os.path.splitext(image_path)[1].lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def image_to_requirement_text(image_path: str) -> str:
    """
    用视觉模型识别图片中的需求（文档、原型图、截图等），返回结构化需求描述文本。
    后续可交给 llm_generate_struct 生成测试点。
    """
    data_url = _image_to_data_url(image_path)
    prompt = """请识别本图中的内容，并输出一份「软件需求描述」，便于后续编写测试点。要求：
- 若为需求文档/说明：提取并整理为条理清晰的需求正文（可保留小标题与要点）。
- 若为界面截图/原型图：描述页面元素、功能入口、主要操作与业务逻辑。
- 若为手写/拍照文档：尽量识别文字并整理为可读的需求说明。
只输出需求正文，不要输出“根据图片……”等前缀。"""
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


# 图片引用正则：![alt](url_or_path)
_IMG_REF_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _download_image_to_temp(url: str) -> str:
    """从 URL 下载图片到临时文件，返回本地路径。"""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        data = resp.read()
        ct = resp.headers.get("Content-Type", "")
    ext = ".png"
    if "jpeg" in ct or "jpg" in ct:
        ext = ".jpg"
    elif "webp" in ct:
        ext = ".webp"
    fd, path = tempfile.mkstemp(suffix=ext)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return path


def enrich_markdown_with_image_content(md_text: str, base_dir: str = ".") -> str:
    """
    解析 Markdown 中的图片引用 ![](url)，用视觉模型识别图片内容，
    将识别结果替换原图片引用，使需求分析/测试点生成能利用图中信息。

    base_dir: 解析相对路径时的基准目录（通常为 md 文件所在目录）。
    """
    base_path = Path(base_dir) if base_dir else Path(".")

    def _replace_one(match: re.Match) -> str:
        alt = match.group(1) or "图片"
        url_or_path = match.group(2).strip()
        local_path: Optional[str] = None

        if url_or_path.startswith(("http://", "https://")):
            try:
                local_path = _download_image_to_temp(url_or_path)
            except Exception:
                return match.group(0)
        else:
            full = (base_path / url_or_path).resolve()
            if full.exists() and full.is_file():
                local_path = str(full)
            else:
                return match.group(0)

        if not local_path:
            return match.group(0)

        try:
            recognized = image_to_requirement_text(local_path)
        except Exception:
            recognized = ""
        finally:
            if url_or_path.startswith(("http://", "https://")):
                try:
                    os.unlink(local_path)
                except OSError:
                    pass

        if recognized:
            return f"\n\n<!-- 图片「{alt}」识别结果：\n{recognized}\n-->\n\n"
        return match.group(0)

    return _IMG_REF_RE.sub(_replace_one, md_text)


def read_markdown_with_images(path: str) -> str:
    """
    读取 Markdown 文件，并对其中嵌入的图片（URL 或相对路径）调用视觉模型识别，
    返回合并了识别结果的需求正文。
    """
    text = read_text(path)
    base_dir = str(Path(path).resolve().parent)
    return enrich_markdown_with_image_content(text, base_dir)


def get_req_text(in_path: Path | str, prefix: str = "[解析]") -> str:
    """
    根据文件类型获取需求正文（统一入口，避免多处重复解析）。
    prefix: 日志前缀，如 [Step0]、[Step1]、[解析]。
    """
    p = Path(in_path) if not isinstance(in_path, Path) else in_path
    if p.suffix.lower() in IMAGE_EXTENSIONS:
        print(f"{prefix} 检测到图片需求，识别图中内容…")
        return image_to_requirement_text(str(p))
    if p.suffix.lower() == PDF_EXTENSION:
        print(f"{prefix} 检测到 PDF，解析正文…")
        return read_pdf_text(str(p))
    if p.suffix.lower() in (".md", ".markdown"):
        print(f"{prefix} 检测到 Markdown，解析正文并识别内嵌图片…")
        return read_markdown_with_images(str(p))
    return read_text(str(p))


def llm_generate_struct_from_image(image_path: str) -> Dict[str, Any]:
    """从需求图片生成测试点结构：先视觉识别出需求文本，再走文字版测试点生成。"""
    req_text = image_to_requirement_text(image_path)
    if not req_text:
        raise ValueError("视觉模型未返回需求内容，请换图或检查图片是否清晰。")
    return llm_generate_struct(req_text)


def llm_req_analysis_5w1h(req_text: str) -> str:
    """
    用 5W1H 分析需求，输出一篇浅显易懂的 Markdown，让用户快速理解「这次需求到底在做什么」。
    返回纯 Markdown 字符串。
    """
    prompt = f"""请对下面这份【需求正文】用 5W1H 方法做一次简要分析，并写成一篇 Markdown 文档，让读者用最少时间搞懂「这次需求在干什么」。

要求：
1. 按 5W1H 组织：Who（谁/角色）、What（做什么）、When（什么时候/时机）、Where（在哪/范围）、Why（为什么做）、How（怎么实现/怎么做）。每项用浅显的话写 1～3 句即可，不要堆术语。
2. 语言通俗，像在给同事口头解释需求，避免冗长和官话。
3. 文末用 2～3 句话做「一句话总结」：这次需求本质上是在做什么。
4. 直接输出 Markdown（可用 ## 小标题），不要输出 JSON、不要代码块包裹、不要「根据需求……」等前缀。

【需求正文】
{req_text}
"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你输出一篇简洁的 Markdown 需求分析，语言浅显易懂。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    raw = (resp.choices[0].message.content or "").strip()
    # 若模型用 ```markdown 包裹，去掉
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].lower().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw


def extract_json(text: str) -> str:
    """从模型输出中截取第一个 JSON 对象（容错：前后夹杂文字）。"""
    text = (text or "").strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return text[start : end + 1]


# ===== Schema: 支持 points + tables + callouts =====
SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "subsections": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                # 清单条目：短语/短句
                                "points": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                # 可选：表格（场景-预期）
                                "tables": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "headers": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                                            "rows": {
                                                "type": "array",
                                                "items": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                                            },
                                        },
                                        "required": ["title", "headers", "rows"],
                                        "additionalProperties": False,
                                    },
                                },
                                # 可选：⚠️块
                                "callouts": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "items": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                        },
                                        "required": ["title", "items"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["title"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "subsections"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "sections"],
    "additionalProperties": False,
}


_TEST_POINT_INSTRUCTIONS = r"""
严格只输出 JSON，不要任何解释文字。

输出必须是"清单式测试点模板"，且必须完全根据【需求正文】归纳出一级、二级结构：
- section 的 title：根据需求中的功能模块/业务块自行归纳（如"一、xxx""二、xxx"），不要使用与需求无关的固定标题。
- subsections：每个 section 下按测试维度拆分子标题（如 1️⃣ 展示与交互、2️⃣ 校验逻辑 等），子标题和 points/tables/callouts 都要紧扣该需求。

风格要求：
- points 必须是【短条目/短短句】，不要以"验证/确认/校验/检查/测试"开头，不要写成用例句式。
- 需要表格的地方用 tables 输出（如勾选逻辑、状态矩阵等）。
- 需要强调的边界/异常用 callouts 输出，title 以 "⚠️" 开头，例如 "⚠️ 边界点"。

JSON 结构示例（section 数量、标题、子标题均按需求灵活组织，至少 1 个 section）：
{
  "title": "测试点清单",
  "sections": [
    {
      "title": "一、<根据需求归纳的功能/模块名>",
      "subsections": [
        {
          "title": "1️⃣ <子维度>",
          "points": ["...", "..."],
          "tables": [],
          "callouts": []
        }
      ]
    }
  ]
}

注意：tables 的 rows 每行必须与 headers 列数一致。sections 至少 1 项，建议根据需求拆成 3～7 个一级模块为宜。
"""


def build_test_point_prompt(req_text: str) -> str:
    """
    根据解析后的需求正文，构建发给 AI 的「测试点生成」完整提示。
    返回的是 user 角色的 content，不含 system 消息。
    """
    goods_ctx = ""
    if os.path.exists(CONTEXT_GOODS_PATH):
        goods_ctx = read_text(CONTEXT_GOODS_PATH)

    parts: List[str] = ["你是资深软件测试工程师，输出用于评审的【测试点清单模板】。"]
    if goods_ctx:
        parts.append("【业务上下文】（供参考）：")
        parts.append(goods_ctx)
    parts.append("【需求正文】：")
    parts.append(req_text)
    parts.append(_TEST_POINT_INSTRUCTIONS)
    return "\n\n".join(parts)


def llm_generate_struct(req_text: str) -> Dict[str, Any]:
    prompt = build_test_point_prompt(req_text)

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content or ""
    data = json.loads(extract_json(raw))

    # 轻量纠错 1：有些 callout 会误输出成 {"title": "...", "content": "..."}
    # 这里自动兼容为 {"title": "...", "items": ["..."]}
    for section in data.get("sections", []) or []:
        for sub in section.get("subsections", []) or []:
            callouts = sub.get("callouts") or []
            for c in callouts:
                if isinstance(c, dict) and "content" in c and "items" not in c:
                    content = c.pop("content")
                    c["items"] = [str(content)] if content is not None else []

    # 轻量纠错 2：有些 table 会漏掉 title，这里补一个默认标题，避免 schema 报错
    for section in data.get("sections", []) or []:
        for sub in section.get("subsections", []) or []:
            tables = sub.get("tables") or []
            for idx, t in enumerate(tables, start=1):
                if isinstance(t, dict) and "title" not in t:
                    t["title"] = f"表格{idx}"

    validate(instance=data, schema=SCHEMA)
    return data


def md_table(headers: List[str], rows: List[List[str]]) -> str:
    # Markdown table
    line1 = "| " + " | ".join(headers) + " |"
    line2 = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines = [line1, line2]
    for r in rows:
        # 容错：列数不齐就补空
        if len(r) < len(headers):
            r = r + [""] * (len(headers) - len(r))
        if len(r) > len(headers):
            r = r[: len(headers)]
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def save_to_markdown(data: Dict[str, Any], out_path: str, file_title: str) -> None:
    out: List[str] = [f"# {file_title}", ""]
    # section 级别：你希望是“## 一、xxx”还是“ 一、xxx ”都行；我按 Markdown 标准输出
    for section in data["sections"]:
        out.append(f"## {section['title']}")
        out.append("")
        for sub in section["subsections"]:
            out.append(f"### {sub['title']}")
            out.append("")

            # points：逐条换行（不加“验证”前缀）
            for p in sub.get("points", []) or []:
                out.append(p)
                out.append("")

            # tables：输出标题 + 表格
            for t in sub.get("tables", []) or []:
                if t.get("title"):
                    out.append(t["title"])
                    out.append("")
                out.append(md_table(t["headers"], t["rows"]))
                out.append("")

            # callouts：⚠️块
            for c in sub.get("callouts", []) or []:
                out.append(c["title"])
                out.append("")
                for it in c["items"]:
                    out.append(f"- {it}")
                out.append("")

    content = "\n".join(out).rstrip() + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)


def save_json(data: Dict[str, Any], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python generate_md_v2.py inputs/req.md")

    in_path = sys.argv[1]
    req_text = read_text(in_path)

    result = llm_generate_struct(req_text)

    os.makedirs("outputs", exist_ok=True)
    json_path = os.path.join("outputs", "test_points_struct.json")
    md_path = os.path.join("outputs", "test_points.md")

    save_json(result, json_path)
    save_to_markdown(result, md_path, file_title=os.path.basename(in_path))

    print(f"OK -> {json_path}")
    print(f"OK -> {md_path}")


if __name__ == "__main__":
    main()