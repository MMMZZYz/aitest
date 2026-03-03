"""
# 流程1：需求 → 需求分析 + 测试点 + XMind（不生成测试用例）
# 一键流水线：列出 inputs/ 下的需求文件，交互选择后依次执行 Step0 → Step1 → Step2。
#
用法：
  python run_pipeline.py
     从 inputs/ 列出需求文件（.md / .txt / .pdf / 图片），交互选择后执行。
  python run_pipeline.py inputs/我的需求.md
     指定需求文件路径，直接执行。

目录约定：
  inputs/    放入需求文档（.md / .txt / .pdf 或图片）
  outputs/  按需求文件名创建子文件夹
            outputs/<需求文件名>/需求分析.md、测试点分析.md、对话记录.md、测试点.xmind

说明：Step0 与 Step1 共享同一次解析结果，仅识别内嵌图片一次。
生成测试用例请使用流程2：python run_xmind_to_cases.py <你的测试点.xmind>
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _list_input_files() -> list[Path]:
    """列出 inputs 下所有需求文件：.md / .txt / .pdf 或图片（.png / .jpg / .jpeg / .webp）。"""
    inputs_dir = ROOT / "inputs"
    if not inputs_dir.exists():
        return []
    patterns = ["*.md", "*.markdown", "*.txt", "*.pdf", "*.png", "*.jpg", "*.jpeg", "*.webp"]
    seen = set()
    files = []
    for pat in patterns:
        for p in sorted(inputs_dir.glob(pat)):
            if p.is_file() and p not in seen:
                seen.add(p)
                files.append(p)
    return sorted(files, key=lambda p: p.name.lower())


def _select_input() -> Path:
    """交互选择需求文件。"""
    files = _list_input_files()
    if not files:
        raise SystemExit("未在 inputs/ 下找到任何需求文件（.md / .txt / .pdf / 图片），请放入后再运行。")
    if len(files) == 1:
        print(f"检测到 1 个需求文件: {files[0].name}")
        return files[0]

    print("\n请选择要执行的需求文件：")
    for i, p in enumerate(files, 1):
        print(f"  {i}. {p.name}")
    while True:
        try:
            s = input("\n请输入序号 (1-{}): ".format(len(files))).strip()
            n = int(s)
            if 1 <= n <= len(files):
                return files[n - 1]
        except ValueError:
            pass
        print("无效输入，请重新输入序号。")


def main() -> None:
    argv_before = sys.argv.copy()

    # 确定输入文件
    if len(argv_before) >= 2:
        in_path = Path(argv_before[1])
        if not in_path.is_absolute():
            in_path = Path.cwd() / in_path
        if not in_path.exists():
            raise SystemExit(f"文件不存在: {in_path}")
    else:
        in_path = _select_input()

    # 输出目录：outputs/<需求文件名>，不覆盖
    output_name = in_path.stem
    output_dir = ROOT / "outputs" / output_name
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["OUTPUT_DIR"] = str(output_dir)
    print(f"输出目录: {output_dir}\n")

    # 只解析一次，Step0 与 Step1 共享 req_text
    from generate_md_v2 import get_req_text

    req_text = get_req_text(in_path, prefix="[解析]")
    if not req_text.strip():
        raise SystemExit("需求内容为空，无法分析。")

    # Step0: 需求分析
    try:
        import step0_req_to_analysis

        step0_req_to_analysis.main(req_text=req_text, in_path=in_path)
    finally:
        sys.argv = argv_before

    # Step1: 测试点 MD
    try:
        import step1_req_to_md

        step1_req_to_md.main(req_text=req_text, in_path=in_path)
    finally:
        sys.argv = argv_before

    # Step2: MD → XMind
    sys.argv = [sys.argv[0]]
    try:
        import step2_md_to_xmind
        step2_md_to_xmind.main()
    finally:
        sys.argv = argv_before

    print(f"\n✅ 流程1 完成。输出目录: {output_dir}")


if __name__ == "__main__":
    main()
