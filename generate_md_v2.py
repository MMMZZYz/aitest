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

try:
    from gemini_native import gemini_chat as _gemini_chat
    from gemini_native import gemini_vision as _gemini_vision
except ImportError:
    _gemini_chat = _gemini_vision = None  # type: ignore[assignment]

try:
    import json_repair
except ImportError:
    json_repair = None  # type: ignore[assignment]

load_dotenv()


def _get_llm_config():
    """优先使用 Gemini（原生 SDK），否则使用 DashScope。"""
    if os.getenv("GEMINI_API_KEY"):
        return {
            "provider": "gemini",
            "api_key": os.getenv("GEMINI_API_KEY"),
            "base_url": os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            "vision_model": os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash"),
        }
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("请在 .env 里配置 GEMINI_API_KEY 或 DASHSCOPE_API_KEY")
    return {
        "provider": "dashscope",
        "api_key": api_key,
        "base_url": os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model": os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
        "vision_model": os.getenv("DASHSCOPE_VISION_MODEL", "qwen-vl-plus"),
    }


_cfg = _get_llm_config()
USE_NATIVE_GEMINI = _cfg.get("provider") == "gemini"
API_KEY = _cfg["api_key"]
BASE_URL = _cfg["base_url"]
MODEL = _cfg["model"]
VISION_MODEL = _cfg["vision_model"]
client = None if USE_NATIVE_GEMINI else OpenAI(api_key=API_KEY, base_url=BASE_URL)

ROOT = Path(__file__).resolve().parent
CONTEXT_GOODS_PATH = "context.md"
SYSTEM_TEMPLATE_PATH = ROOT / "prompt" / "system_template.txt"

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


def image_to_requirement_text(image_path: str) -> tuple[str, str]:
    """
    用多模态视觉模型理解图片中的需求，返回 (需求描述文本, 本轮对话记录 Markdown)。
    """
    data_url = _image_to_data_url(image_path)
    prompt = """请用多模态能力理解本图，并输出一份「软件需求描述」，便于后续编写测试点。要求：
- 若为逻辑图/流程图/架构图：理解节点、箭头、分支与流程，用文字描述业务逻辑、判断条件、状态流转与数据流，不要只罗列图中的文字。
- 若为需求文档/说明：提取并整理为条理清晰的需求正文（可保留小标题与要点）。
- 若为界面截图/原型图：描述页面元素、功能入口、主要操作与业务逻辑。
不要做纯 OCR 式的文字识别；重点理解图所表达的逻辑与需求。只输出需求正文，不要输出“根据图片……”等前缀。"""
    if USE_NATIVE_GEMINI and _gemini_vision:
        req_text = _gemini_vision(VISION_MODEL, data_url, prompt, temperature=0.2)
    else:
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
        req_text = (resp.choices[0].message.content or "").strip()
    vision_md = (
        "## 第1轮：图片识别\n\n**User**\n\n(已发送图片)\n\n" + prompt + "\n\n**Assistant**\n\n" + req_text
    )
    return (req_text, vision_md)


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
    解析 Markdown 中的图片引用 ![](url)：统一用多模态视觉模型理解图中逻辑与需求，
    将结果替换原图片引用。不再读取或复用任何 OCR 注释，逻辑图/流程图等均由 AI 直接解析。

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

        is_local = not url_or_path.startswith(("http://", "https://"))
        display_path = url_or_path if len(url_or_path) <= 60 else url_or_path[:57] + "..."
        print(f"[视觉] 正在解析图片: {alt or '图片'} ({'本地文件: ' if is_local else '已下载: '}{display_path})")
        try:
            recognized, _ = image_to_requirement_text(local_path)
        except Exception as e:
            print(f"[视觉] 解析失败（该图将不会进入后续分析）: {e}")
            recognized = ""
        finally:
            if url_or_path.startswith(("http://", "https://")):
                try:
                    os.unlink(local_path)
                except OSError:
                    pass

        if recognized:
            print(f"[视觉] 解析完成，得到 {len(recognized)} 字")
            return f"\n\n<!-- 图片「{alt}」识别结果：\n{recognized}\n-->\n\n"
        print(f"[视觉] 解析结果为空，保留原图引用")
        return match.group(0)

    return _IMG_REF_RE.sub(_replace_one, md_text)


def read_markdown_with_images(path: str) -> str:
    """
    读取 Markdown 文件，并对其中嵌入的图片（URL 或相对路径）用多模态视觉模型解析，
    返回合并了解析结果的需求正文。逻辑图/流程图等由 AI 直接理解，不使用 OCR。
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
        return image_to_requirement_text(str(p))[0]
    if p.suffix.lower() == PDF_EXTENSION:
        print(f"{prefix} 检测到 PDF，解析正文…")
        return read_pdf_text(str(p))
    if p.suffix.lower() in (".md", ".markdown"):
        print(f"{prefix} 检测到 Markdown，解析正文并识别内嵌图片…")
        return read_markdown_with_images(str(p))
    return read_text(str(p))


def llm_generate_struct_from_image(image_path: str) -> tuple[Dict[str, Any], str]:
    """从需求图片生成测试点结构，返回 (结构 dict, 完整对话记录 Markdown)。"""
    req_text, vision_md = image_to_requirement_text(image_path)
    if not req_text:
        raise ValueError("视觉模型未返回需求内容，请换图或检查图片是否清晰。")
    data, conv_md = llm_generate_struct(req_text)
    # 合并为一份对话记录：总标题 + 第1轮图片识别 + 第2轮测试点生成（去掉 conv 内重复的 # 对话记录）
    second_part = conv_md.replace("# 对话记录\n\n", "", 1).strip()
    full_conv = "# 对话记录\n\n" + vision_md + "\n\n---\n\n## 第2轮：测试点生成\n\n" + second_part
    return (data, full_conv)


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
    if USE_NATIVE_GEMINI and _gemini_chat:
        raw = _gemini_chat(
            MODEL,
            [
                {"role": "system", "content": "你输出一篇简洁的 Markdown 需求分析，语言浅显易懂。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
    else:
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


# ===== Schema: 递归节点，层级不限；每节点可有 title、points、tables、callouts、children =====
_NODE_CONTENT = {
    "points": {"type": "array", "items": {"type": "string"}},
    "tables": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "headers": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}, "minItems": 2}},
            },
            "required": ["title", "headers", "rows"],
            "additionalProperties": False,
        },
    },
    "callouts": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "items": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "points": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "items"],
            "additionalProperties": False,
        },
    },
}

# 递归节点：title 必填；points/tables/callouts/children 可选；children 为同结构子节点数组
SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "definitions": {
        "node": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                **_NODE_CONTENT,
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/node"},
                },
            },
            "required": ["title"],
            "additionalProperties": False,
        },
    },
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/definitions/node"},
        },
    },
    "required": ["title", "sections"],
    "additionalProperties": False,
}

# 无 context 时的兜底：保证模型知道要输出的 JSON 结构，代码才能解析通过
_MINIMAL_OUTPUT_INSTRUCTIONS = r"""
请根据上述需求，输出测试点清单。严格只输出一个 JSON，不要任何解释。

JSON 结构（必须遵守）：
- 根：{"title": "测试点清单", "sections": [节点数组]}
- 每个节点：{"title": "标题", "points": ["条目1", ...], "tables": [], "callouts": [], "children": [子节点同结构]}
- callouts 每项：{"title": "标题", "items": ["一条描述"]}
- tables 每项：{"title": "表名", "headers": ["列1","列2"], "rows": [["a","b"], ...]}
- 无子节点时 children 可省略或 []；有子节点时递归同结构。只输出 JSON。
"""


def build_test_point_prompt(req_text: str, append_minimal_schema: bool = False) -> str:
    """
    根据解析后的需求正文，构建发给 AI 的「需求正文」部分（供 step2 使用）。
    append_minimal_schema：为 True 时在末尾追加最小输出格式说明（无 context 时兜底）。
    """
    out = "【需求正文】：\n\n" + req_text
    if append_minimal_schema:
        out += _MINIMAL_OUTPUT_INSTRUCTIONS
    return out


def _message_content_to_str(content: Any) -> str:
    """将 API 消息 content（可能为 str 或 list，如多模态）转为可读字符串。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "image_url":
                    parts.append("[已发送图片]")
            else:
                parts.append(str(item))
        return "\n".join(parts).strip() or "(空)"
    return str(content) if content is not None else "(空)"


def _format_conversation_md(messages: List[Dict[str, Any]], final_assistant: str) -> str:
    """将完整对话（messages + 最后一轮 Assistant 回复）格式化为可保存的对话记录 Markdown。"""
    lines = ["# 对话记录", "", "以下为与 AI 的完整对话（测试点生成流程）。", ""]
    role_label = {"system": "System", "user": "User", "assistant": "Assistant"}
    for i, msg in enumerate(messages, 1):
        role = msg.get("role", "")
        content = msg.get("content", "")
        label = role_label.get(role, role)
        text = _message_content_to_str(content)
        lines.append(f"## {label}")
        lines.append("")
        lines.append(text)
        lines.append("")
    lines.append("## Assistant")
    lines.append("")
    lines.append(final_assistant)
    lines.append("")
    return "\n".join(lines)


def _load_system_prompt() -> str:
    """读取 prompt/system_template.txt 作为 AI 系统提示词；不存在则兜底。"""
    if SYSTEM_TEMPLATE_PATH.exists():
        return SYSTEM_TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    return "You output ONLY valid JSON."


def _build_two_turn_messages(req_text: str) -> List[Dict[str, str]]:
    """
    构建分两次发送的对话消息：第一次只发 context，第二次发需求。
    System 使用 prompt/system_template.txt（你的 AI 提示词）；返回完整 messages 列表。
    """
    goods_ctx = ""
    if os.path.exists(CONTEXT_GOODS_PATH):
        goods_ctx = read_text(CONTEXT_GOODS_PATH)

    system_content = _load_system_prompt()
    # 你的提示词要求输出 Markdown，当前流程需解析 JSON；在 system 末尾说明以 JSON 输出
    if system_content != "You output ONLY valid JSON.":
        system_content += "\n\n【程序解析说明】为便于后续转 XMind，请将测试点树按 User 消息末尾的 JSON 结构输出，只输出一个合法 JSON，不要其他解释。"
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]

    if goods_ctx:
        # 第一次：只发 context
        messages.append({"role": "user", "content": goods_ctx})
        if USE_NATIVE_GEMINI and _gemini_chat:
            reply1 = _gemini_chat(MODEL, messages, temperature=0.1) or "好的，我已理解上述规则，请提供需求正文。"
        else:
            resp1 = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.1,
            )
            reply1 = (resp1.choices[0].message.content or "").strip() or "好的，我已理解上述规则，请提供需求正文。"
        messages.append({"role": "assistant", "content": reply1})

    # 第二次：发需求正文；无 context 时追加最小输出格式说明，保证能解析
    second_content = build_test_point_prompt(req_text, append_minimal_schema=not bool(goods_ctx))
    messages.append({"role": "user", "content": second_content})
    return messages


def llm_generate_struct(req_text: str) -> tuple[Dict[str, Any], str]:
    """返回 (测试点结构 dict, 完整对话记录 Markdown)。"""
    messages = _build_two_turn_messages(req_text)

    if USE_NATIVE_GEMINI and _gemini_chat:
        raw = _gemini_chat(MODEL, messages, temperature=0.2) or ""
    else:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or ""
    conversation_md = _format_conversation_md(messages, raw)
    json_str = extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        if json_repair is None:
            raise ValueError(
                f"模型返回的 JSON 无法解析（位置约 line {e.lineno} col {e.colno}）：{e.msg}。"
                " 可安装 json-repair 以尝试自动修复，或检查 prompt 是否过长导致截断。"
            ) from e
        try:
            data = json_repair.loads(json_str)
        except Exception:
            raise ValueError(
                f"模型返回的 JSON 无法解析（位置约 line {e.lineno} col {e.colno}）：{e.msg}，json_repair 也无法修复。"
                " 可重试或缩短需求正文。"
            ) from e

    _NODE_KEYS = frozenset({"title", "points", "tables", "callouts", "children"})

    def _fix_callouts_and_tables(container: Dict[str, Any], table_prefix: str = "表格") -> None:
        callouts = container.get("callouts")
        if not isinstance(callouts, list):
            callouts = []
            container["callouts"] = callouts
        for i, c in enumerate(callouts):
            if isinstance(c, str):
                callouts[i] = {"title": c, "items": [c]}
            elif isinstance(c, dict):
                if "content" in c and "items" not in c:
                    content = c.pop("content", None)
                    c["items"] = [str(content)] if content is not None else []
                if "title" not in c:
                    c["title"] = "要点"
                items = c.get("items")
                if isinstance(items, str):
                    c["items"] = [items]
                elif not isinstance(items, list):
                    c["items"] = []
                c["items"] = [str(x) for x in c["items"]]
                if not c["items"]:
                    pts = c.get("points")
                    if isinstance(pts, list) and pts:
                        c["items"] = [str(x) for x in pts]
                    else:
                        c["items"] = [c.get("title", "要点")]

        tables = container.get("tables")
        if not isinstance(tables, list):
            tables = []
            container["tables"] = tables
        for idx, t in enumerate(tables, start=1):
            if not isinstance(t, dict):
                tables[idx - 1] = {"title": f"{table_prefix}{idx}", "headers": ["列1", "列2"], "rows": []}
                continue
            if "title" not in t:
                t["title"] = f"{table_prefix}{idx}"
            if not isinstance(t.get("headers"), list) or len(t.get("headers", [])) < 2:
                t["headers"] = (t.get("headers") or [])[:2] if isinstance(t.get("headers"), list) else ["列1", "列2"]
            if len(t["headers"]) < 2:
                t["headers"] = t["headers"] + ["列2"] * (2 - len(t["headers"]))
            t["headers"] = [str(h) for h in t["headers"]]
            if not isinstance(t.get("rows"), list):
                t["rows"] = []
            t["rows"] = [[str(cell) for cell in (r if isinstance(r, list) else [r])] for r in t["rows"]]
            for r in t["rows"]:
                if len(r) < len(t["headers"]):
                    r.extend([""] * (len(t["headers"]) - len(r)))
                elif len(r) > len(t["headers"]):
                    r[:] = r[: len(t["headers"])]

        points = container.get("points")
        if not isinstance(points, list):
            container["points"] = []
        else:
            container["points"] = [str(p) for p in points]

    def _fix_node(node: Dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return
        # 只保留 schema 允许的 key，避免 additionalProperties 报错
        allowed = {k: node[k] for k in _NODE_KEYS if k in node}
        node.clear()
        node.update(allowed)
        if not node.get("title"):
            node["title"] = "未命名"
        node["title"] = str(node["title"])
        _fix_callouts_and_tables(node)
        children = node.get("children")
        if not isinstance(children, list):
            node["children"] = []
            children = []
        node["children"] = [ch for ch in children if isinstance(ch, dict)]
        for ch in node["children"]:
            _fix_node(ch)

    # 根层：确保有 title、sections 且 sections 非空（minItems 1）
    if not data.get("title"):
        data["title"] = "测试点清单"
    data["title"] = str(data["title"])
    sections = data.get("sections")
    if not isinstance(sections, list):
        data["sections"] = []
        sections = []
    data["sections"] = [s for s in sections if isinstance(s, dict)]
    if not data["sections"]:
        data["sections"] = [{"title": "未命名", "points": [], "tables": [], "callouts": [], "children": []}]
    for section in data["sections"]:
        _fix_node(section)

    validate(instance=data, schema=SCHEMA)
    return (data, conversation_md)


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
    def _render_node(node: Dict[str, Any], depth: int) -> None:
        level = min(depth + 2, 6)
        out.append(f"{'#' * level} {node['title']}")
        out.append("")
        for p in node.get("points", []) or []:
            out.append(p)
            out.append("")
        for t in node.get("tables", []) or []:
            if t.get("title"):
                out.append(t["title"])
                out.append("")
            out.append(md_table(t["headers"], t["rows"]))
            out.append("")
        for c in node.get("callouts", []) or []:
            out.append(c["title"])
            if c.get("description"):
                out.append(c["description"])
            out.append("")
            for it in c.get("items", []) or []:
                out.append(f"- {it}")
            for p in c.get("points", []) or []:
                if p not in (c.get("items") or []):
                    out.append(f"- {p}")
            out.append("")
        for ch in node.get("children") or []:
            _render_node(ch, depth + 1)

    for section in data["sections"]:
        _render_node(section, 0)
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

    result, _ = llm_generate_struct(req_text)

    os.makedirs("outputs", exist_ok=True)
    json_path = os.path.join("outputs", "test_points_struct.json")
    md_path = os.path.join("outputs", "test_points.md")

    save_json(result, json_path)
    save_to_markdown(result, md_path, file_title=os.path.basename(in_path))

    print(f"OK -> {json_path}")
    print(f"OK -> {md_path}")


if __name__ == "__main__":
    main()