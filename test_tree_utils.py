# 流程3：测试树工具——树转 MD、路径列表、按 id 查找
from typing import Any, Dict, List


def tree_to_md_lines(node: Dict[str, Any], indent: int = 0) -> List[str]:
    """将统一测试树节点转为 Markdown 列表（供 LLM 语义理解）。"""
    lines: List[str] = []
    prefix = "  " * indent + "- "
    title = node.get("title") or "(无标题)"
    path = node.get("path", "")
    nid = node.get("id", "")
    line = f"{prefix}{title}"
    if path:
        line += f"  `{path}`"
    if nid:
        line += f"  [id:{nid}]"
    lines.append(line)
    for child in node.get("children", []) or []:
        lines.extend(tree_to_md_lines(child, indent + 1))
    return lines


def tree_to_standard_md(roots: List[Dict[str, Any]]) -> str:
    """多棵根节点转为一整份标准化 MD 文本。"""
    blocks: List[str] = []
    for root in roots:
        blocks.extend(tree_to_md_lines(root))
    return "\n".join(blocks) if blocks else ""


def flat_to_compressed_path_list(flat: List[Dict[str, Any]]) -> str:
    """将扁平节点列表转为「压缩路径列表」文本，供 AI 输入用（控制 token）。"""
    lines = []
    for n in flat:
        path = n.get("path") or ""
        nid = n.get("id") or ""
        level = n.get("level", 0)
        lines.append(f"  {path}  [id:{nid}] level={level}")
    return "\n".join(lines) if lines else "（无节点）"


def build_id_to_node(flat: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """建立 node_id -> 节点 的映射，便于分支定位与高亮。"""
    return {n["id"]: n for n in flat if n.get("id")}
