"""
# 需求 → 5W1H 需求分析。生成 需求分析.md，用 5W1H 讲清楚需求在做什么。
步骤0：在生成测试点之前，先根据需求生成一篇「需求分析」MD，用 5W1H 讲清楚这次需求在做什么。
用法：python step0_req_to_analysis.py [inputs/需求.md]
      不传参数时自动使用 inputs 下第一个需求文件。
输出：outputs/需求分析.md（或 OUTPUT_DIR/需求分析.md）
"""
import os
import sys
from pathlib import Path

from generate_md_v2 import get_req_text, llm_req_analysis_5w1h

INPUTS_DIR = Path(__file__).resolve().parent / "inputs"
_out = os.environ.get("OUTPUT_DIR")
OUTPUTS_DIR = Path(_out) if _out else Path(__file__).resolve().parent / "outputs"
OUTPUT_FILENAME = "需求分析.md"


def find_input_file() -> Path:
    """在 inputs 目录下查找第一个需求文件。"""
    if not INPUTS_DIR.exists():
        INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    for pat in ["*.md", "*.txt", "*.pdf", "*.png", "*.jpg", "*.jpeg", "*.webp"]:
        for p in INPUTS_DIR.glob(pat):
            if p.is_file():
                return p
    raise SystemExit(f"未在 {INPUTS_DIR} 下找到任何需求文件，请放入后再运行。")


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

    if req_text is None:
        req_text = get_req_text(in_path, prefix="[Step0]")
    if not req_text.strip():
        raise SystemExit("需求内容为空，无法分析。")

    print("[Step0] 正在用 5W1H 分析需求并生成说明文档…")
    md_content = llm_req_analysis_5w1h(req_text)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / OUTPUT_FILENAME
    out_path.write_text(md_content, encoding="utf-8")

    print(f"[Step0] 需求分析 MD 已生成: {out_path}")


if __name__ == "__main__":
    main()
