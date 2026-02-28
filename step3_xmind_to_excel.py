"""
# XMind → Excel。解析 测试点.xmind，按模板生成 测试用例.xlsx。
步骤3：根据测试点 XMind 与用例模板，生成 Excel 测试用例。
用法：python step3_xmind_to_excel.py [outputs/测试点.xmind] [templates/用例模板.xlsx]
输出：outputs/测试用例.xlsx（或 OUTPUT_DIR 下）
"""
import os
import sys
from pathlib import Path

from generate_cases_mvp import generate_cases_from_xmind_bytes

_out = os.environ.get("OUTPUT_DIR")
OUTPUTS_DIR = Path(_out) if _out else Path(__file__).resolve().parent / "outputs"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_XMIND = OUTPUTS_DIR / "测试点.xmind"
DEFAULT_TEMPLATE = TEMPLATES_DIR / "用例模板.xlsx"
# 兼容：若 templates 下没有，用项目根目录的模板
FALLBACK_TEMPLATE = Path(__file__).resolve().parent / "用例模板.xlsx"
OUT_EXCEL = OUTPUTS_DIR / "测试用例.xlsx"


def main() -> None:
    xmind_path = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_XMIND
    template_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else DEFAULT_TEMPLATE

    if not xmind_path.exists():
        raise SystemExit(
            f"XMind 文件不存在: {xmind_path}\n请先运行 step2_md_to_xmind.py 生成测试点 XMind。"
        )
    if not template_path.exists():
        template_path = FALLBACK_TEMPLATE
    if not template_path.exists():
        raise SystemExit(
            f"用例模板不存在: {template_path}\n请在 templates/ 下放置 用例模板.xlsx，或项目根目录放置 用例模板.xlsx。"
        )

    xmind_bytes = xmind_path.read_bytes()
    excel_bytes = generate_cases_from_xmind_bytes(xmind_bytes, str(template_path))

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_EXCEL.write_bytes(excel_bytes)
    print(f"[Step3] XMind → Excel 完成: {OUT_EXCEL}")


if __name__ == "__main__":
    main()
