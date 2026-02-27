"""
步骤2：将 outputs/test_points.md 转为 XMind 测试点文档（Zen 格式，便于步骤3解析）。
用法：python step2_md_to_xmind.py [outputs/test_points.md]
输出：outputs/test_points.xmind
"""
import json
import re
import zipfile
import time
import uuid
from pathlib import Path

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
DEFAULT_MD = OUTPUTS_DIR / "test_points.md"
DEFAULT_XMIND = OUTPUTS_DIR / "test_points.xmind"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


def _new_id() -> str:
    return uuid.uuid4().hex


def _topic(title: str, children: list | None = None) -> dict:
    t = {"id": _new_id(), "class": "topic", "title": title}
    if children:
        t["children"] = {"attached": children}
    return t


def _parse_md_to_tree(lines: list[str]) -> list[dict]:
    """
    解析 MD 标题与列表为层级结构，返回根下的子节点列表（每个元素为 _topic 格式）。
    # 为根标题，## ### 等为层级，列表项和普通行为当前节点的子节点。
    """
    root_children: list[dict] = []
    # stack: (heading_level, list of topic dicts 的引用，用于追加当前层子节点)
    # 用 list 包装以便内部函数修改
    stack: list[tuple[int, list]] = [(0, root_children)]
    table_buf: list[str] = []
    in_table = False

    def flush_table():
        nonlocal table_buf, in_table
        if in_table and table_buf:
            _, current_children = stack[-1]
            table_text = "\n".join(table_buf)
            current_children.append(_topic(table_text))
        table_buf = []
        in_table = False

    for raw in lines:
        line = raw.rstrip("\r\n")

        if not line.strip():
            flush_table()
            continue

        if TABLE_ROW_RE.match(line):
            in_table = True
            table_buf.append(line)
            continue
        flush_table()

        mh = HEADING_RE.match(line)
        if mh:
            level = len(mh.group(1))
            title = mh.group(2).strip() or "(无标题)"

            if level == 1:
                # 根标题：作为根的子节点（即第一层主题），并为其创建 attached 列表供 ## 挂载
                child = _topic(title)
                child.setdefault("children", {"attached": []})
                root_children.append(child)
                stack = [(1, child["children"]["attached"])]
                continue

            # 弹栈直到栈顶 level < 当前 level
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            _, parent_children = stack[-1]
            child = _topic(title)
            parent_children.append(child)
            child_list = child.setdefault("children", {}).setdefault("attached", [])
            stack.append((level, child_list))
            continue

        mb = BULLET_RE.match(line)
        if mb:
            text = mb.group(1).strip()
            if text:
                _, parent_children = stack[-1]
                parent_children.append(_topic(text))
            continue

        # 普通文本行
        _, parent_children = stack[-1]
        if line.strip():
            parent_children.append(_topic(line.strip()))

    flush_table()
    return root_children


def md_to_xmind_zen(md_path: str, out_xmind_path: str, root_title: str = "测试点") -> None:
    """将 MD 文件转为 XMind Zen 格式（content.json + zip）。"""
    path = Path(md_path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    root_children = _parse_md_to_tree(lines)
    if not root_children:
        root_children = [_topic("(无内容)")]

    root = _topic(root_title, root_children)
    content = [{
        "id": _new_id(),
        "class": "sheet",
        "title": root_title,
        "rootTopic": root,
    }]
    metadata = {
        "dataStructureVersion": "2",
        "createdTime": int(time.time() * 1000),
        "modifiedTime": int(time.time() * 1000),
    }
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}, "manifest.json": {}}}

    out_path = Path(out_xmind_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(content, ensure_ascii=False))
        z.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))


def main() -> None:
    import sys
    md_file = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_MD
    if not md_file.exists():
        raise SystemExit(f"MD 文件不存在: {md_file}\n请先运行 step1_req_to_md.py 生成 outputs/test_points.md")

    out_file = DEFAULT_XMIND
    root_title = md_file.stem.replace("test_points", "测试点").replace("_", " ")
    if root_title == "test_points" or root_title == "测试点":
        root_title = "测试点"

    md_to_xmind_zen(str(md_file), str(out_file), root_title=root_title)
    print(f"[Step2] MD → XMind 完成: {out_file}")


if __name__ == "__main__":
    main()
