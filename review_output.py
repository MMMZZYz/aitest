# 流程3：评审结果输出——AI检查报告.json、可回填 MD、分支定位映射
import json
import os
from collections import defaultdict
from typing import Any, Dict, List


def write_report_json(report: Dict[str, Any], out_path: str) -> None:
    """写入 AI检查报告.json。"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def details_to_backfill_md(details: List[Dict[str, Any]], id_to_node: Dict[str, Dict[str, Any]]) -> str:
    """
    将 details 转为「可回填 MD」：按父路径分组的建议新增场景 + 覆盖不足节点 + 风险节点。
    """
    lines = ["# 测试评审补充建议", ""]
    missing_by_path: Dict[str, List[str]] = defaultdict(list)
    weak: List[Dict[str, Any]] = []
    risk: List[Dict[str, Any]] = []

    for item in details or []:
        t = item.get("type")
        if t == "missing_branch":
            path = item.get("suggest_parent_path") or "其他"
            scene = item.get("missing_scene") or "未命名场景"
            missing_by_path[path].append(scene)
        elif t == "insufficient_coverage":
            weak.append(item)
        elif t == "risk_node":
            risk.append(item)

    if missing_by_path:
        lines.append("## 建议新增场景")
        lines.append("")
        for path in sorted(missing_by_path.keys()):
            lines.append(f"### {path}")
            for scene in missing_by_path[path]:
                lines.append(f"- {scene}")
            lines.append("")
        lines.append("")

    if weak:
        lines.append("## 覆盖不足节点")
        lines.append("")
        for w in weak:
            nid = w.get("node_id", "")
            problem = w.get("problem", "")
            node = id_to_node.get(nid, {})
            path = node.get("path", nid)
            lines.append(f"- **{path}** [id:{nid}]")
            lines.append(f"  - 问题：{problem}")
            lines.append("")
        lines.append("")

    if risk:
        lines.append("## 风险节点（建议优先覆盖）")
        lines.append("")
        for r in risk:
            nid = r.get("node_id", "")
            score = r.get("risk_score", 0)
            reason = r.get("reason", "")
            node = id_to_node.get(nid, {})
            path = node.get("path", nid)
            lines.append(f"- **{path}** [id:{nid}] 风险分：{score}")
            lines.append(f"  - 原因：{reason}")
            lines.append("")
        lines.append("")

    return "\n".join(lines).strip()


def write_backfill_md(content: str, out_path: str) -> None:
    """写入可回填 MD 文件。"""
    dirpath = os.path.dirname(out_path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")
