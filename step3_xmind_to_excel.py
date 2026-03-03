"""
# 流程2：用户上传 XMind → AI 生成指定格式测试用例（默认 Excel）
# 输入目录：xmind_excel_input；输出目录：xmind_excel_output；输出 Excel 文件名与上传的 xmind 文件名一致。
#
用法：
  python step3_xmind_to_excel.py <测试点.xmind>
     从 xmind_excel_input/ 读取同名文件，或使用当前目录/绝对路径；输出到 xmind_excel_output/测试点.xlsx
  python step3_xmind_to_excel.py <测试点.xmind> [用例模板.xlsx] [输出路径.xlsx]
"""
import os
import sys
from pathlib import Path

from generate_cases_mvp import generate_cases_from_xmind_bytes

ROOT = Path(__file__).resolve().parent
XMIND_INPUT_DIR = ROOT / "xmind_excel_input"
XMIND_OUTPUT_DIR = ROOT / "xmind_excel_output"
TEMPLATES_DIR = ROOT / "templates"
DEFAULT_TEMPLATE = TEMPLATES_DIR / "用例模板.xlsx"
FALLBACK_TEMPLATE = ROOT / "用例模板.xlsx"


def _resolve_xmind_path(raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    if p.exists():
        return p.resolve()
    # 仅文件名或相对路径且不存在时，到流程2 输入目录查找
    in_dir = XMIND_INPUT_DIR / raw
    if in_dir.exists():
        return in_dir.resolve()
    in_dir = XMIND_INPUT_DIR / p.name
    if in_dir.exists():
        return in_dir.resolve()
    return Path(raw).resolve()


def main() -> None:
    raw_xmind = sys.argv[1] if len(sys.argv) >= 2 else None
    if not raw_xmind:
        raise SystemExit(
            "请指定测试点 .xmind 文件。\n"
            "用法: python step3_xmind_to_excel.py <测试点.xmind>\n"
            "可将 xmind 放入 xmind_excel_input/ 后只传文件名。"
        )
    xmind_path = _resolve_xmind_path(raw_xmind)
    template_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else DEFAULT_TEMPLATE
    out_path = Path(sys.argv[3]) if len(sys.argv) >= 4 else None

    if not xmind_path.exists():
        raise SystemExit(
            f"XMind 文件不存在: {xmind_path}\n"
            f"请将文件放入 {XMIND_INPUT_DIR} 或指定正确路径。"
        )
    if not template_path.exists():
        template_path = FALLBACK_TEMPLATE
    if not template_path.exists():
        raise SystemExit(
            f"用例模板不存在: {template_path}\n请在 templates/ 下放置 用例模板.xlsx，或项目根目录放置 用例模板.xlsx。"
        )

    if out_path is None:
        XMIND_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = XMIND_OUTPUT_DIR / (xmind_path.stem + ".xlsx")
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    xmind_bytes = xmind_path.read_bytes()
    excel_bytes = generate_cases_from_xmind_bytes(xmind_bytes, str(template_path))
    out_path.write_bytes(excel_bytes)
    print(f"[流程2] XMind → 测试用例 完成: {out_path}")


if __name__ == "__main__":
    main()
