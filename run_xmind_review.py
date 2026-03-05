"""
流程3 入口：用户上传 XMind + 可选 PRD/原型文本 → AI 遗漏检测 → 在原 XMind 对应节点上增加 AI 建议并输出新 XMind

输出：仅一份 .xmind（原结构 + 在对应节点下增加【AI建议新增】【AI建议补充】【风险】等子节点）

用法：
  python run_xmind_review.py
      从 xmind_review_input/ 列出 .xmind，选一个；同目录下可选 prd.txt / prototype.txt
  python run_xmind_review.py <测试点.xmind> [--prd 需求.txt] [--prototype 原型.txt]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
XMIND_REVIEW_INPUT = ROOT / "xmind_review_input"
XMIND_REVIEW_OUTPUT = ROOT / "xmind_review_output"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _list_xmind_files() -> list[Path]:
    if not XMIND_REVIEW_INPUT.exists():
        return []
    return sorted([p for p in XMIND_REVIEW_INPUT.glob("*.xmind") if p.is_file()], key=lambda p: p.name.lower())


def _select_xmind() -> Path:
    files = _list_xmind_files()
    if not files:
        raise SystemExit(
            f"未在 {XMIND_REVIEW_INPUT} 下找到任何 .xmind 文件。\n"
            "请将测试点 xmind 放入 xmind_review_input/ 后重新运行，或直接传入文件路径：\n"
            "  python run_xmind_review.py 你的测试点.xmind"
        )
    if len(files) == 1:
        print(f"检测到 1 个 xmind 文件: {files[0].name}")
        return files[0]
    print("\n请选择要评审的 xmind 文件：")
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


def _read_optional_text(path: Path) -> str:
    if not path or not path.exists():
        return ""
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=enc).strip()
        except Exception:
            continue
    return ""


def main() -> None:
    argv = sys.argv[1:]
    xmind_path: Path | None = None
    prd_path: Path | None = None
    prototype_path: Path | None = None

    i = 0
    while i < len(argv):
        if argv[i] == "--prd" and i + 1 < len(argv):
            prd_path = Path(argv[i + 1]).resolve()
            i += 2
            continue
        if argv[i] == "--prototype" and i + 1 < len(argv):
            prototype_path = Path(argv[i + 1]).resolve()
            i += 2
            continue
        if not argv[i].startswith("--"):
            xmind_path = Path(argv[i]).resolve()
            if not xmind_path.is_absolute() or not xmind_path.exists():
                cand = XMIND_REVIEW_INPUT / (xmind_path.name or argv[i])
                if cand.exists():
                    xmind_path = cand.resolve()
        i += 1

    if xmind_path is None:
        xmind_path = _select_xmind()
    else:
        if not xmind_path.exists():
            cand = XMIND_REVIEW_INPUT / xmind_path.name
            if cand.exists():
                xmind_path = cand
            else:
                raise SystemExit(f"文件不存在: {xmind_path}")

    # 需求/原型：优先用 --prd/--prototype 指定；否则在 xmind_review_input 里找（固定名或任意 .md/.txt）
    search_dir = XMIND_REVIEW_INPUT if XMIND_REVIEW_INPUT.exists() else xmind_path.parent
    if prd_path is None:
        for name in ("prd.txt", "需求.txt", "prd.md", "需求.md"):
            p = search_dir / name
            if p.exists():
                prd_path = p
                break
    if prototype_path is None:
        for name in ("prototype.txt", "原型.txt", "prototype.md", "原型.md"):
            p = search_dir / name
            if p.exists():
                prototype_path = p
                break

    prd_text = _read_optional_text(prd_path) if prd_path else _read_optional_text(search_dir / "prd.txt")
    prototype_text = _read_optional_text(prototype_path) if prototype_path else _read_optional_text(search_dir / "prototype.txt")

    # 若仍未找到，则用 xmind_review_input 下任意 .md / .txt（排除 .xmind）
    if not prd_text and not prototype_text:
        if XMIND_REVIEW_INPUT.exists():
            extra = sorted(
                [
                    p
                    for p in XMIND_REVIEW_INPUT.iterdir()
                    if p.is_file() and p.suffix.lower() in (".md", ".txt")
                ],
                key=lambda p: p.name.lower(),
            )
            if extra:
                parts = []
                for p in extra:
                    t = _read_optional_text(p)
                    if t:
                        parts.append(t)
                if parts:
                    prd_text = "\n\n---\n\n".join(parts)
                    prototype_text = prd_text
                    print(f"[流程3] 已使用 xmind_review_input 下的文档: {[p.name for p in extra]}")

    if not prd_text and not prototype_text:
        print("提示：未找到 PRD/原型文本，将仅基于当前测试树做简单检查。请把 .md 或 .txt 放入 xmind_review_input/ 目录。")

    from xmind_to_test_tree import xmind_to_test_tree
    from review_engine import run_review
    from review_to_xmind import merge_ai_suggestions_into_tree, write_merged_xmind

    roots, flat = xmind_to_test_tree(str(xmind_path))
    if not flat:
        raise SystemExit("未解析到任何测试树节点，请检查 XMind 格式（需含 content.json）。")

    print(f"[流程3] 解析到节点数: {len(flat)}")
    report = run_review(prd_text, prototype_text, flat)
    print("[流程3] AI 评审完成")

    details = report.get("details") or []
    merge_ai_suggestions_into_tree(roots, flat, details)
    print("[流程3] 已合并 AI 建议到测试树")

    XMIND_REVIEW_OUTPUT.mkdir(parents=True, exist_ok=True)
    stem = xmind_path.stem
    out_xmind_path = XMIND_REVIEW_OUTPUT / f"{stem}_评审结果.xmind"
    write_merged_xmind(roots, str(out_xmind_path))

    summary = report.get("summary", {})
    print(f"\n✅ 流程3 完成，输出: {out_xmind_path}")
    print(f"  - 缺失场景: {summary.get('total_missing', 0)}  覆盖不足: {summary.get('weak_nodes', 0)}  风险节点: {summary.get('risk_count', 0)}")


if __name__ == "__main__":
    main()
