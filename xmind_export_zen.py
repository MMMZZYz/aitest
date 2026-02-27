# xmind_export_zen.py
import os, json, zipfile, time, uuid
from collections import defaultdict

def _new_id():
    return uuid.uuid4().hex

def _infer_module(item: str, module_rules):
    s = str(item)
    for module_name, keywords in module_rules:
        for kw in keywords:
            if kw and kw in s:
                return module_name
    return "未归类"

def _topic(title: str, children: list[dict] | None = None):
    t = {"id": _new_id(), "class": "topic", "title": title}
    if children:
        t["children"] = {"attached": children}
    return t

def save_to_xmind_zen_by_module_reviewable(
    data: dict,
    out_path: str,
    root_title: str,
    module_rules,
    add_placeholders: bool = True,
    print_uncategorized: bool = True,
):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    category_order = ["功能测试","边界测试","异常测试","权限测试","性能与容量风险","隐藏雷点提示"]
    cat_code = {"功能测试":"FUNC","边界测试":"BND","异常测试":"ERR","权限测试":"AUTH","性能与容量风险":"PERF","隐藏雷点提示":"RISK"}

    buckets: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for cat in category_order:
        for item in (data.get(cat) or []):
            mod = _infer_module(str(item), module_rules)
            buckets[mod][cat].append(str(item))

    if print_uncategorized:
        uncat_count = sum(len(v) for v in buckets.get("未归类", {}).values())
        print(f"[XMind] 未归类测试点数量: {uncat_count}")

    modules = sorted(buckets.keys(), key=lambda x: (x == "未归类", x))

    module_topics = []
    for mod in modules:
        cat_topics = []
        module_seq = 0

        for cat in category_order:
            items = buckets[mod].get(cat, [])
            if not items:
                continue

            tp_topics = []
            code = cat_code.get(cat, "GEN")

            for it in items:
                module_seq += 1
                tp_id = f"TP-{code}-{module_seq:03d}"
                title = f"{tp_id}  {it}"
                if cat == "隐藏雷点提示":
                    title = f"⚠ {title}"

                children = []
                if add_placeholders:
                    children = [
                        _topic("优先级：P0/P1/P2（待定）"),
                        _topic("备注：口径/数据/前置（待补）"),
                        _topic("关联：页面/接口/字段（待补）"),
                    ]
                tp_topics.append(_topic(title, children if children else None))

            cat_topics.append(_topic(cat, tp_topics))

        module_topics.append(_topic(mod, cat_topics))

    content = [{
        "id": _new_id(),
        "class": "sheet",
        "title": root_title,
        "rootTopic": _topic(root_title, module_topics)
    }]

    metadata = {
        "dataStructureVersion": "2",
        "createdTime": int(time.time() * 1000),
        "modifiedTime": int(time.time() * 1000),
    }
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}, "manifest.json": {}}}

    # 覆盖旧文件（避免残留半成品）
    if os.path.exists(out_path):
        os.remove(out_path)

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(content, ensure_ascii=False))
        z.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))