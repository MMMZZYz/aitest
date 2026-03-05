# 流程3：XMind → 统一测试树协议（带 id / path / parent_id / level）
# 供测试智能评审引擎使用：精确定位分支、AI 遗漏检测
import json
import zipfile
import uuid
from typing import Any, Dict, List, Optional, Tuple

# 统一测试树节点类型（可按需扩展）
NODE_TYPES = ("module", "scene", "case", "condition")


def _make_node_id() -> str:
    return "node-" + uuid.uuid4().hex[:8]


def _infer_type(level: int, has_children: bool) -> str:
    """根据层级与是否有子节点推断 type。"""
    if level <= 1:
        return "module"
    if level == 2:
        return "scene" if has_children else "case"
    if level >= 3:
        return "condition" if has_children else "case"
    return "case"


def _walk_xmind(
    node: Dict[str, Any],
    path: List[str],
    parent_id: Optional[str],
    level: int,
    out_flat: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    递归遍历 XMind content.json 中的节点，转为统一测试树节点。
    out_flat 收集所有节点（含 id/path）便于后续查找与输出。
    """
    title = (node.get("title") or "").strip()
    children_raw = node.get("children", {})
    attached = (children_raw.get("attached") or []) if isinstance(children_raw, dict) else []
    has_children = bool(attached)

    node_id = _make_node_id()
    path_parts = path + ([title] if title else [])
    path_str = "/".join(path_parts) if path_parts else ""

    node_type = _infer_type(level, has_children)
    standard: Dict[str, Any] = {
        "id": node_id,
        "parent_id": parent_id or "",
        "path": path_str,
        "title": title or "(无标题)",
        "type": node_type,
        "level": level,
        "children": [],
    }

    out_flat.append(standard)

    for child in attached:
        child_standard = _walk_xmind(child, path_parts, node_id, level + 1, out_flat)
        standard["children"].append(child_standard)

    return standard


def _load_xmind_content(xmind_path: str) -> List[Dict[str, Any]]:
    """从 .xmind（zip）中读取 content.json，返回 sheet 列表。"""
    with zipfile.ZipFile(xmind_path, "r") as z:
        name = "content.json" if "content.json" in z.namelist() else None
        if not name:
            cand = [n for n in z.namelist() if n.endswith("content.json")]
            if not cand:
                return []
            name = cand[0]
        data = json.loads(z.read(name).decode("utf-8"))

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def xmind_to_test_tree(xmind_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    解析 XMind 为统一测试树协议。

    返回:
        roots: 各 sheet 的根节点列表（树形，每个节点含 id/parent_id/path/title/type/level/children）
        flat: 所有节点的扁平列表，便于按 id 查找
    """
    sheets = _load_xmind_content(xmind_path)
    roots: List[Dict[str, Any]] = []
    flat: List[Dict[str, Any]] = []

    for sheet in sheets:
        root_topic = sheet.get("rootTopic")
        if not root_topic:
            continue
        root_standard = _walk_xmind(root_topic, [], None, 1, flat)
        roots.append(root_standard)

    return roots, flat


def test_tree_to_flat_id_path(flat: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """导出供 AI 使用的「id + 路径」压缩列表，便于精确定位分支。"""
    return [{"id": n["id"], "path": n["path"], "title": n["title"], "level": n["level"]} for n in flat]
