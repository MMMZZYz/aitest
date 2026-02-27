import re
from pathlib import Path

import xmind
from xmind.core.topic import TopicElement


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)\s*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


def md_to_xmind(md_path: str, out_xmind_path: str) -> None:
    md_path = str(md_path)
    out_xmind_path = str(out_xmind_path)

    lines = Path(md_path).read_text(encoding="utf-8").splitlines()

    # 1) 创建工作簿与根主题
    wb = xmind.load(out_xmind_path)  # 不存在会新建
    sheet = wb.getPrimarySheet()
    sheet.setTitle("Mind Map")

    root = sheet.getRootTopic()
    root.setTitle("Root")

    # stack: [(md_heading_level, topic)]
    stack: list[tuple[int, TopicElement]] = [(1, root)]

    # 表格收集缓存（简化：作为子主题结构输出）
    table_buf: list[str] = []
    in_table = False

    def flush_table() -> None:
        nonlocal table_buf, in_table
        if in_table and table_buf:
            current_topic = stack[-1][1]
            table_topic = current_topic.addSubTopic()
            table_topic.setTitle("表格")
            for row in table_buf:
                r = table_topic.addSubTopic()
                r.setTitle(row)
        table_buf = []
        in_table = False

    for raw in lines:
        line = raw.rstrip("\n")

        # 空行：如果在表格中，空行视为表格结束
        if not line.strip():
            flush_table()
            continue

        # 表格行：收集到 notes（原样保留）
        if TABLE_ROW_RE.match(line):
            in_table = True
            table_buf.append(line)
            continue
        else:
            # 一旦离开表格区域，flush
            flush_table()

        # 标题
        mh = HEADING_RE.match(line)
        if mh:
            level = len(mh.group(1))  # 1..6
            title = mh.group(2).strip()

            # # 作为根标题：更新 root title
            if level == 1:
                root.setTitle(title or "Root")
                stack = [(1, root)]
                continue

            # 找到父层：弹栈直到 stack_top_level < 当前 level
            while stack and stack[-1][0] >= level:
                stack.pop()
            if not stack:
                stack = [(1, root)]

            parent_topic = stack[-1][1]
            child = parent_topic.addSubTopic()
            child.setTitle(title or "(empty)")

            stack.append((level, child))
            continue

        # 列表项：做成子主题（你也可以改成写入 notes）
        mb = BULLET_RE.match(line)
        if mb:
            text = mb.group(1).strip()
            if text:
                current = stack[-1][1]
                t = current.addSubTopic()
                t.setTitle(text)
            continue

        # 普通文本行：默认也做成子主题（更“可视化”）
        current = stack[-1][1]
        t = current.addSubTopic()
        t.setTitle(line.strip())

    # 最后再 flush 一次表格
    flush_table()

    xmind.save(wb, out_xmind_path)


if __name__ == "__main__":
    # 你可以改成自己的路径
    md_file = r"C:\Users\meng\Desktop\aitest\outputs\test_points.md"
    out_file = "req.xmind"
    md_to_xmind(md_file, out_file)
    print(f"OK -> {out_file}")