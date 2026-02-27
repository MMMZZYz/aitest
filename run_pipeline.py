"""
一键流水线：需求 → 需求分析(5W1H) → MD 测试点 → XMind 测试点 → Excel 测试用例。

用法：
  python run_pipeline.py
     从 inputs/ 自动取第一个需求文件，依次执行四步。
  python run_pipeline.py inputs/我的需求.md
     指定需求文件路径。

目录约定：
  inputs/    放入需求文档（.md / .txt / .pdf 或图片）
  outputs/   生成 需求分析.md、test_points.md、test_points.xmind、测试用例.xlsx
  templates/ 放置 用例模板.xlsx（可选）
"""
import sys
from pathlib import Path

# 确保从项目根执行
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    argv_before = sys.argv.copy()

    # Step0: 需求 → 需求分析（5W1H）MD
    sys.argv = [sys.argv[0]]
    if len(argv_before) >= 2:
        sys.argv.append(argv_before[1])
    try:
        import step0_req_to_analysis
        step0_req_to_analysis.main()
    finally:
        sys.argv = argv_before

    # Step1: 需求 → 测试点 MD
    sys.argv = [sys.argv[0]]
    if len(argv_before) >= 2:
        sys.argv.append(argv_before[1])
    try:
        import step1_req_to_md
        step1_req_to_md.main()
    finally:
        sys.argv = argv_before

    # Step2: MD → XMind
    sys.argv = [sys.argv[0]]
    try:
        import step2_md_to_xmind
        step2_md_to_xmind.main()
    finally:
        sys.argv = argv_before

    # Step3: XMind → Excel
    sys.argv = [sys.argv[0]]
    try:
        import step3_xmind_to_excel
        step3_xmind_to_excel.main()
    finally:
        sys.argv = argv_before

    print("\n✅ 流水线全部完成。输出目录: outputs/（含 需求分析.md、test_points.md、test_points.xmind、测试用例.xlsx）")


if __name__ == "__main__":
    main()
