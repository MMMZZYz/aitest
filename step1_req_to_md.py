"""
步骤1：从 inputs 目录读取需求文件，生成 MD 测试点文档。
用法：python step1_req_to_md.py [inputs/需求.md]
      不传参数时自动使用 inputs 下第一个 .md 或 .txt 文件。
输出：outputs/test_points.md, outputs/test_points_struct.json
"""
import os
import sys
from pathlib import Path

# 使用现有「需求→测试点 MD」逻辑（支持文字、图片、PDF）
from generate_md_v2 import (
    IMAGE_EXTENSIONS,
    PDF_EXTENSION,
    read_text,
    read_pdf_text,
    llm_generate_struct,
    llm_generate_struct_from_image,
    save_to_markdown,
    save_json,
)

INPUTS_DIR = Path(__file__).resolve().parent / "inputs"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


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


def main() -> None:
    if len(sys.argv) >= 2:
        in_path = Path(sys.argv[1])
        if not in_path.is_absolute():
            in_path = Path.cwd() / in_path
        if not in_path.exists():
            raise SystemExit(f"文件不存在: {in_path}")
    else:
        in_path = find_input_file()

    if is_image_path(in_path):
        print("[Step1] 检测到图片需求，使用视觉模型识别…")
        result = llm_generate_struct_from_image(str(in_path))
    elif is_pdf_path(in_path):
        print("[Step1] 检测到 PDF，解析正文后生成测试点…")
        req_text = read_pdf_text(str(in_path))
        result = llm_generate_struct(req_text)
    else:
        req_text = read_text(str(in_path))
        result = llm_generate_struct(req_text)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUTS_DIR / "test_points_struct.json"
    md_path = OUTPUTS_DIR / "test_points.md"

    save_json(result, str(json_path))
    save_to_markdown(result, str(md_path), file_title=in_path.name)

    print(f"[Step1] 需求 → 测试点 MD 完成")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
