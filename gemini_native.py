# 使用 Google 新 SDK (google-genai) 调用 Gemini，支持 gemini-1.5-flash 等全部模型，带请求超时
import base64
import os
import re
import time
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

# 请求超时（秒），避免卡住不动
GEMINI_REQUEST_TIMEOUT_SEC = int(os.getenv("GEMINI_TIMEOUT_SEC", "180"))
# 429 限流时最多自动重试次数；网络断开等临时错误也会重试
GEMINI_429_MAX_RETRIES = int(os.getenv("GEMINI_429_MAX_RETRIES", "3"))
# 连接/网络类错误重试前等待秒数
GEMINI_NETWORK_RETRY_WAIT_SEC = int(os.getenv("GEMINI_NETWORK_RETRY_WAIT_SEC", "10"))

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment, misc]

try:
    import httpx
    _REMOTE_PROTOCOL_ERROR = (httpx.RemoteProtocolError,)
except ImportError:
    _REMOTE_PROTOCOL_ERROR = ()  # type: ignore[assignment]


def _get_client():
    """创建带超时的 Client。"""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("未配置 GEMINI_API_KEY")
    # timeout 单位：秒（新 SDK 的 HttpOptions.timeout 一般为秒）
    timeout_ms = GEMINI_REQUEST_TIMEOUT_SEC * 1000
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=timeout_ms) if types else None,
    )


def _message_content_to_parts(content: Any) -> List[Any]:
    """将 OpenAI 风格 message content（str 或 list）转为可传给新 SDK 的 parts。"""
    if isinstance(content, str):
        return [content]
    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and "text" in item:
            parts.append(item["text"])
        elif item.get("type") == "image_url" and "image_url" in item:
            url = item["image_url"].get("url") or ""
            m = re.match(r"data:([^;]+);base64,(.+)", url.strip())
            if m:
                mime = m.group(1).strip()
                b64 = m.group(2).strip()
                if types and hasattr(types.Part, "from_bytes"):
                    parts.append(types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime))
                else:
                    parts.append({"inline_data": {"mime_type": mime, "data": base64.b64decode(b64)}})
    return parts if parts else [""]


def _parts_to_text(parts: List[Any]) -> str:
    return " ".join(p for p in parts if isinstance(p, str)) if parts else ""


def _parse_429_retry_seconds(error: Exception) -> int:
    """从 429 错误信息中解析「Please retry in X.XXs」的秒数，默认 30。"""
    msg = str(getattr(error, "message", "")) or str(error)
    m = re.search(r"[Rr]etry in (\d+(?:\.\d+)?)\s*s", msg)
    if m:
        return max(1, int(float(m.group(1))) + 1)
    return 30


def _is_retryable_network_error(e: Exception) -> bool:
    """是否为可重试的网络/连接类错误（如服务器断开、连接重置）。"""
    if _REMOTE_PROTOCOL_ERROR and isinstance(e, _REMOTE_PROTOCOL_ERROR):
        return True
    err_name = type(e).__name__
    msg = str(e).lower()
    if "disconnect" in msg or "connection" in msg or "reset" in msg or "protocol" in msg:
        return True
    if err_name in ("RemoteProtocolError", "ConnectError", "ReadTimeout", "WriteTimeout"):
        return True
    return False


def _do_generate_content(client: Any, model_name: str, contents: Any, config: Any) -> Any:
    """执行 generate_content，遇 429 或网络断开时等待后重试。"""
    last_err = None
    max_attempts = GEMINI_429_MAX_RETRIES
    for attempt in range(max_attempts):
        try:
            return client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
        except ClientError as e:
            last_err = e
            status = getattr(e, "code", None)
            if status == 429 and attempt < max_attempts - 1:
                wait_sec = _parse_429_retry_seconds(e)
                print(f"[Gemini] 触发限流(429)，{wait_sec} 秒后重试 ({attempt + 1}/{max_attempts})…")
                time.sleep(wait_sec)
                continue
            raise
        except Exception as e:
            last_err = e
            if _is_retryable_network_error(e) and attempt < max_attempts - 1:
                wait = GEMINI_NETWORK_RETRY_WAIT_SEC
                print(f"[Gemini] 网络/连接异常（{type(e).__name__}），{wait} 秒后重试 ({attempt + 1}/{max_attempts})…")
                time.sleep(wait)
                continue
            raise
    raise last_err


def gemini_chat(model_name: str, messages: List[Dict[str, Any]], temperature: float = 0.2) -> str:
    """
    使用新 SDK 单次或多轮对话。
    messages: [{"role": "system"|"user"|"assistant", "content": str 或 list}, ...]
    返回最后一轮模型回复文本。
    """
    if genai is None or types is None:
        raise RuntimeError("请安装: pip install google-genai")
    client = _get_client()
    system = ""
    turns: List[tuple[str, str]] = []
    for m in messages:
        role = (m.get("role") or "").strip().lower()
        content = m.get("content")
        if role == "system":
            system = content if isinstance(content, str) else ""
            continue
        parts = _message_content_to_parts(content)
        text = _parts_to_text(parts)
        if role == "user":
            turns.append(("user", text))
        elif role in ("assistant", "model"):
            turns.append(("model", text))
    if not turns or turns[-1][0] != "user":
        return ""
    prompt_parts = []
    for r, t in turns:
        prefix = "User:" if r == "user" else "Assistant:"
        prompt_parts.append(f"{prefix}\n{t}")
    prompt = "\n\n".join(prompt_parts)
    if system:
        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
    else:
        config = types.GenerateContentConfig(temperature=temperature)
    try:
        response = _do_generate_content(client, model_name, prompt, config)
    finally:
        try:
            client.close()
        except Exception:
            pass
    if not response or not getattr(response, "text", None):
        return ""
    return (response.text or "").strip()


def gemini_vision(
    model_name: str,
    image_data_url: str,
    text_prompt: str,
    temperature: float = 0.2,
) -> str:
    """带图片的请求（如需求截图识别）。"""
    if genai is None or types is None:
        raise RuntimeError("请安装: pip install google-genai")
    m = re.match(r"data:([^;]+);base64,(.+)", image_data_url.strip())
    if not m:
        return ""
    mime = m.group(1).strip()
    b64 = m.group(2).strip()
    image_bytes = base64.b64decode(b64)
    client = _get_client()
    try:
        if hasattr(types.Part, "from_bytes"):
            contents = [types.Part.from_bytes(data=image_bytes, mime_type=mime), text_prompt]
        else:
            contents = [{"inline_data": {"mime_type": mime, "data": image_bytes}}, text_prompt]
        config = types.GenerateContentConfig(temperature=temperature)
        response = _do_generate_content(client, model_name, contents, config)
    finally:
        try:
            client.close()
        except Exception:
            pass
    if not response or not getattr(response, "text", None):
        return ""
    return (response.text or "").strip()
