# 流程3：将 AI 建议合并回原测试树，并输出为新的 XMind 文件
# 在对应节点下增加「AI 建议新增」「AI 建议补充」「风险」等子节点
import json
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from xmind_to_test_tree import _make_node_id


def _xmind_topic_id() -> str:
    return uuid.uuid4().hex


def _standard_node_to_xmind_topic(node: Dict[str, Any]) -> Dict[str, Any]:
    """将统一测试树节点转为 XMind content.json 中的 topic 结构。"""
    title = node.get("title") or "(无标题)"
    children = node.get("children") or []
    out: Dict[str, Any] = {
        "id": _xmind_topic_id(),
        "class": "topic",
        "title": title,
    }
    if children:
        out["children"] = {
            "attached": [_standard_node_to_xmind_topic(c) for c in children]
        }
    return out


def _add_standard_child(parent: Dict[str, Any], title: str, parent_path: str) -> Dict[str, Any]:
    """在父节点下追加一个标准格式的子节点，并加入父的 children，返回新节点。"""
    new_id = _make_node_id()
    new_path = f"{parent_path}/{title}" if parent_path else title
    child: Dict[str, Any] = {
        "id": new_id,
        "parent_id": parent.get("id", ""),
        "path": new_path,
        "title": title,
        "type": "case",
        "level": parent.get("level", 0) + 1,
        "children": [],
    }
    parent.setdefault("children", []).append(child)
    return child


def merge_ai_suggestions_into_tree(
    roots: List[Dict[str, Any]],
    flat: List[Dict[str, Any]],
    details: List[Dict[str, Any]],
) -> None:
    """
    将 AI 评审结果合并进测试树（原地修改）。
    - missing_branch：在 suggest_parent_path 对应节点下增加「【AI建议新增】missing_scene」及原因
    - insufficient_coverage：在 node_id 对应节点下增加「【AI建议补充】problem」
    - risk_node：在 node_id 对应节点下增加「【风险】reason (评分:N)」
    """
    id_to_node = {n["id"]: n for n in flat}
    path_to_node: Dict[str, Dict[str, Any]] = {}
    for n in flat:
        p = (n.get("path") or "").strip()
        if p:
            path_to_node[p] = n
        # 根节点 path 可能等于 title
        if n.get("title") and not p:
            path_to_node[n["title"]] = n

    for item in details or []:
        t = item.get("type")
        if t == "missing_branch":
            parent_path = (item.get("suggest_parent_path") or "").strip()
            scene = (item.get("missing_scene") or "未命名场景").strip()
            reason = (item.get("reason") or "").strip()
            parent = path_to_node.get(parent_path)
            if not parent:
                # 若路径不存在，挂在第一个 sheet 的根下
                parent = roots[0] if roots else None
            if parent:
                title = f"【AI建议新增】{scene}"
                child = _add_standard_child(parent, title, parent.get("path", ""))
                if reason:
                    _add_standard_child(child, reason, child.get("path", ""))
                flat.append(child)
                if child.get("path"):
                    path_to_node[child["path"]] = child

        elif t == "insufficient_coverage":
            nid = item.get("node_id", "").strip()
            problem = (item.get("problem") or "").strip()
            parent = id_to_node.get(nid)
            if parent and problem:
                title = f"【AI建议补充】{problem}"
                child = _add_standard_child(parent, title, parent.get("path", ""))
                flat.append(child)
                if child.get("path"):
                    path_to_node[child["path"]] = child

        elif t == "risk_node":
            nid = item.get("node_id", "").strip()
            score = item.get("risk_score", 0)
            reason = (item.get("reason") or "").strip()
            parent = id_to_node.get(nid)
            if parent:
                title = f"【风险】{reason} (评分:{score})" if reason else f"【风险】评分:{score}"
                child = _add_standard_child(parent, title, parent.get("path", ""))
                flat.append(child)
                if child.get("path"):
                    path_to_node[child["path"]] = child


def write_merged_xmind(roots: List[Dict[str, Any]], out_path: str) -> None:
    """将合并后的标准测试树（多 sheet）写入为 XMind Zen 格式的 .xmind 文件。"""
    content: List[Dict[str, Any]] = []
    for root in roots:
        sheet_id = _xmind_topic_id()
        content.append({
            "id": sheet_id,
            "class": "sheet",
            "title": root.get("title") or "测试点",
            "rootTopic": _standard_node_to_xmind_topic(root),
        })

    metadata = {
        "dataStructureVersion": "2",
        "createdTime": int(time.time() * 1000),
        "modifiedTime": int(time.time() * 1000),
    }
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}, "manifest.json": {}}}

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()

    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(content, ensure_ascii=False))
        z.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
