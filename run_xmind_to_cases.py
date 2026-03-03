"""
# 流程2 入口：用户上传 XMind → AI 生成指定格式测试用例（默认 Excel）
# 输入目录：xmind_excel_input；输出目录：xmind_excel_output；输出 Excel 与 xmind 同名。
#
用法：
  python run_xmind_to_cases.py
     从 xmind_excel_input/ 列出 .xmind 文件，交互选择后执行（与流程1 相同方式）。
  python run_xmind_to_cases.py <测试点.xmind>
     指定文件路径，直接执行。
  python run_xmind_to_cases.py <测试点.xmind> [--template 用例模板.xlsx] [--output 路径.xlsx]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
XMIND_INPUT_DIR = ROOT / "xmind_excel_input"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _list_xmind_files() -> list[Path]:
    """列出 xmind_excel_input 下所有 .xmind 文件。"""
    if not XMIND_INPUT_DIR.exists():
        return []
    files = sorted(XMIND_INPUT_DIR.glob("*.xmind"), key=lambda p: p.name.lower())
    return [p for p in files if p.is_file()]


def _select_xmind() -> Path:
    """交互选择 xmind 文件（与流程1 相同：单选、支持仅一个文件时自动选中）。"""
    files = _list_xmind_files()
    if not files:
        raise SystemExit(
            f"未在 {XMIND_INPUT_DIR} 下找到任何 .xmind 文件。\n"
            "请将测试点 xmind 放入 xmind_excel_input/ 后重新运行，或直接传入文件路径：\n"
            "  python run_xmind_to_cases.py 你的测试点.xmind"
        )
    if len(files) == 1:
        print(f"检测到 1 个 xmind 文件: {files[0].name}")
        return files[0]
    print("\n请选择要转换的 xmind 文件：")
    for i, p in enumerate(files, 1):
        print(f"  {i}. {p.name}")
    while True:
        try:
            s = input(f"\n请输入序号 (1-{len(files)}): ").strip()
            n = int(s)
            if 1 <= n <= len(files):
                return files[n - 1]
        except ValueError:
            pass
        print("无效输入，请重新输入序号。")


def _resolve_xmind_path(raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    if p.exists():
        return p.resolve()
    for candidate in [XMIND_INPUT_DIR / raw, XMIND_INPUT_DIR / p.name]:
        if candidate.exists():
            return candidate.resolve()
    return Path(raw).resolve()


def main() -> None:
    argv = sys.argv[1:]
    opts = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--template" and i + 1 < len(argv):
            opts["template"] = Path(argv[i + 1]).resolve()
            i += 2
            continue
        if argv[i] == "--output" and i + 1 < len(argv):
            opts["output"] = Path(argv[i + 1]).resolve()
            i += 2
            continue
        if not argv[i].startswith("--"):
            opts["xmind"] = _resolve_xmind_path(argv[i])
        i += 1

    if "xmind" not in opts:
        xmind_path = _select_xmind()
    else:
        xmind_path = opts["xmind"]

    if not xmind_path.exists():
        print(f"错误: 文件不存在 {xmind_path}\n可将文件放入 {XMIND_INPUT_DIR} 后重新运行或只传文件名。")
        sys.exit(1)

    # 调用 step3：argv = [脚本, xmind路径, 可选模板, 可选输出]
    sys.argv = [sys.argv[0], str(xmind_path)]
    if opts.get("template"):
        sys.argv.append(str(opts["template"]))
    if opts.get("output"):
        sys.argv.append(str(opts["output"]))

    import step3_xmind_to_excel

    step3_xmind_to_excel.main()


if __name__ == "__main__":
    main()
