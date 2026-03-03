"""
# 需求 → 测试点 MD。生成 测试点分析.md、对话记录.md（与 AI 的完整对话流程）。
步骤1：从 inputs 目录读取需求文件，生成 MD 测试点文档。
用法：python step1_req_to_md.py [inputs/需求.md]
      不传参数时自动使用 inputs 下第一个 .md 或 .txt 文件。
输出：outputs/测试点分析.md、outputs/对话记录.md（或 OUTPUT_DIR 下）
"""
import os
import sys
from pathlib import Path

# SAVE_PROMPT=0 可禁用对话记录保存；默认保存到 对话记录.md
SAVE_PROMPT = os.environ.get("SAVE_PROMPT", "1").strip().lower() != "0"

from generate_md_v2 import (
    IMAGE_EXTENSIONS,
    PDF_EXTENSION,
    get_req_text,
    llm_generate_struct,
    llm_generate_struct_from_image,
    save_to_markdown,
)

INPUTS_DIR = Path(__file__).resolve().parent / "inputs"
_out = os.environ.get("OUTPUT_DIR")
OUTPUTS_DIR = Path(_out) if _out else Path(__file__).resolve().parent / "outputs"


def find_input_file() -> Path:
    """在 inputs 目录下查找第一个需求文件：.md / .txt / .pdf 或图片。"""
    if not INPUTS_DIR.exists():
        INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    patterns = ["*.md", "*.txt", "*.pdf", "*.png", "*.jpg", "*.jpeg", "*.webp"]
    for pat in patterns:
        for p in INPUTS_DIR.glob(pat):
            if p.is_file():
                return p
    raise SystemExit(
        f"未在 {INPUTS_DIR} 下找到任何需求文件（.md / .txt / .pdf / 图片），请放入后再运行。"
    )


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_pdf_path(path: Path) -> bool:
    return path.suffix.lower() == PDF_EXTENSION


def main(req_text: str | None = None, in_path: Path | None = None) -> None:
    if in_path is None:
        if len(sys.argv) >= 2:
            in_path = Path(sys.argv[1])
            if not in_path.is_absolute():
                in_path = Path.cwd() / in_path
            if not in_path.exists():
                raise SystemExit(f"文件不存在: {in_path}")
        else:
            in_path = find_input_file()

    conversation_md = ""
    if req_text is None:
        if is_image_path(in_path):
            print("[Step1] 检测到图片需求，使用视觉模型识别…")
            result, conversation_md = llm_generate_struct_from_image(str(in_path))
        else:
            req_text = get_req_text(in_path, prefix="[Step1]")
            result, conversation_md = llm_generate_struct(req_text)
    else:
        result, conversation_md = llm_generate_struct(req_text)

    if SAVE_PROMPT and conversation_md:
        out = OUTPUTS_DIR / "对话记录.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(conversation_md, encoding="utf-8")
        print(f"[Step1] 对话记录已保存: {out}")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUTPUTS_DIR / "测试点分析.md"

    save_to_markdown(result, str(md_path), file_title=in_path.name)

    print(f"[Step1] 需求 → 测试点 MD 完成")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
