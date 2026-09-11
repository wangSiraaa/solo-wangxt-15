"""
业务规则引擎：BOM 树构建、版本比较、替代环检测、区间冲突检测、按序列号解析。

所有函数都是纯数据操作，不依赖 request，便于单测与复用。
"""
from collections import defaultdict
from decimal import Decimal

from .models import BOMLine, BOMVersion, SubstituteRule


# ---------------------------------------------------------------------------
# BOM 树
# ---------------------------------------------------------------------------

def _qty(value) -> str:
    """Decimal → 无尾零、无科学计数法的字符串（10.0000 → "10"）。"""
    return format(value.normalize(), "f")


def build_tree(version: BOMVersion):
    """把版本的 BOMLine 拍平结果组装成嵌套树。

    返回节点列表，节点结构：
    {line_id, material_id, code, name, spec, unit, quantity, path, children[]}
    path 形如 "PWR-01/CAP-100"，用于冲突定位与前端展示。
    """
    lines = list(version.lines.select_related("material"))
    nodes = {}
    for ln in lines:
        nodes[ln.id] = {
            "line_id": ln.id,
            "material_id": ln.material_id,
            "code": ln.material.code,
            "name": ln.material.name,
            "spec": ln.material.spec,
            "unit": ln.material.unit,
            "quantity": _qty(ln.quantity),
            "children": [],
            "_parent_id": ln.parent_id,
            "_sort": (ln.sort_order, ln.id),
        }
    roots = []
    for ln in lines:
        node = nodes[ln.id]
        parent = nodes.get(ln.parent_id) if ln.parent_id else None
        (parent["children"] if parent else roots).append(node)

    def finalize(node, prefix):
        node["path"] = f"{prefix}/{node['code']}" if prefix else node["code"]
        node["children"].sort(key=lambda n: n["_sort"])
        for ch in node["children"]:
            finalize(ch, node["path"])
        node.pop("_parent_id", None)
        node.pop("_sort", None)

    roots.sort(key=lambda n: n["_sort"])
    for r in roots:
        finalize(r, "")
    return roots


def material_paths(version: BOMVersion):
    """{material_id: [path, ...]} —— 物料在树中出现的所有位置。"""
    result = defaultdict(list)

    def walk(node):
        result[node["material_id"]].append(node["path"])
        for ch in node["children"]:
            walk(ch)

    for root in build_tree(version):
        walk(root)
    return dict(result)


# ---------------------------------------------------------------------------
# 版本比较（树形差异）
# ---------------------------------------------------------------------------

def _match_children(from_children, to_children):
    """按 (物料编码, 同码出现次序) 配对两棵树的同级节点。

    返回 (pairs, removed, added)。同物料多实例按 sort_order 顺序一一对应，
    保证「数量变化」与「增删行」都能稳定识别。
    """
    def key_groups(children):
        groups = defaultdict(list)
        for ch in children:
            groups[ch["code"]].append(ch)
        return groups

    from_groups, to_groups = key_groups(from_children), key_groups(to_children)
    pairs, removed, added = [], [], []
    for code in sorted(set(from_groups) | set(to_groups)):
        fs, ts = from_groups.get(code, []), to_groups.get(code, [])
        for i in range(max(len(fs), len(ts))):
            f = fs[i] if i < len(fs) else None
            t = ts[i] if i < len(ts) else None
            if f and t:
                pairs.append((f, t))
            elif f:
                removed.append(f)
            else:
                added.append(t)
    return pairs, removed, added


def _diff_node(from_node, to_node):
    if from_node is None:  # 整棵子树新增
        return {
            **_public_node(to_node),
            "status": "added",
            "children": [_diff_node(None, ch) for ch in to_node["children"]],
        }
    if to_node is None:  # 整棵子树删除
        return {
            **_public_node(from_node),
            "status": "removed",
            "children": [_diff_node(ch, None) for ch in from_node["children"]],
        }
    pairs, removed, added = _match_children(from_node["children"], to_node["children"])
    children = (
        [_diff_node(f, t) for f, t in pairs]
        + [_diff_node(ch, None) for ch in removed]
        + [_diff_node(None, ch) for ch in added]
    )
    changed = Decimal(from_node["quantity"]) != Decimal(to_node["quantity"])
    own = "changed" if changed else "unchanged"
    return {
        **_public_node(to_node),
        "status": own,
        "quantity_from": from_node["quantity"],
        "quantity_to": to_node["quantity"],
        "children": children,
        "has_descendant_change": any(
            c["status"] != "unchanged" or c.get("has_descendant_change") for c in children
        ),
    }


def _public_node(node):
    return {
        "line_id": node["line_id"],
        "code": node["code"],
        "name": node["name"],
        "spec": node["spec"],
        "unit": node["unit"],
        "quantity": node["quantity"],
        "path": node["path"],
    }


def diff_versions(v_from: BOMVersion, v_to: BOMVersion):
    """两版 BOM 的树形差异。节点 status: added / removed / changed / unchanged。"""
    from_tree, to_tree = build_tree(v_from), build_tree(v_to)
    pairs, removed, added = _match_children(from_tree, to_tree)
    tree = (
        [_diff_node(f, t) for f, t in pairs]
        + [_diff_node(ch, None) for ch in removed]
        + [_diff_node(None, ch) for ch in added]
    )
    summary = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}

    def count(node):
        summary[node["status"]] += 1
        for ch in node["children"]:
            count(ch)

    for n in tree:
        count(n)
    return {"tree": tree, "summary": summary}


# ---------------------------------------------------------------------------
# 替代关系环检测
# ---------------------------------------------------------------------------

def find_cycles(rules):
    """检测 原物料→替代物料 有向图中的环。

    返回环列表，每个环是物料编码路径，如 ["IC-OLD", "IC-NEW", "IC-OLD"]。
    """
    graph = defaultdict(set)
    label = {}
    for r in rules:
        graph[r.original_id].add(r.substitute_id)
        label[r.original_id] = r.original.code
        label[r.substitute_id] = r.substitute.code

    WHITE, GRAY, BLACK = 0, 1, 2
    color = defaultdict(int)
    cycles, stack = [], []

    def dfs(u):
        color[u] = GRAY
        stack.append(u)
        for v in sorted(graph.get(u, ())):
            if color[v] == GRAY:  # 回边 → 找到一个环
                idx = stack.index(v)
                cycles.append([label[m] for m in stack[idx:]] + [label[v]])
            elif color[v] == WHITE:
                dfs(v)
        stack.pop()
        color[u] = BLACK

    for node in sorted(graph):
        if color[node] == WHITE:
            dfs(node)
    return cycles


# ---------------------------------------------------------------------------
# 区间冲突检测
# ---------------------------------------------------------------------------

def find_conflicts(version: BOMVersion):
    """同一原物料的区间两两比较：交叠且指向不同替代料 → 冲突。

    返回冲突列表，每项包含：原物料、交叠区间、两条规则、以及原物料在
    BOM 树中的全部位置（冲突路径），便于质量人员定位影响面。
    """
    rules = list(
        version.rules.select_related("original", "substitute").order_by(
            "original_id", "serial_start", "id"
        )
    )
    paths = material_paths(version)
    by_original = defaultdict(list)
    for r in rules:
        by_original[r.original_id].append(r)

    conflicts = []
    for original_id, group in by_original.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                lo, hi = max(a.serial_start, b.serial_start), min(a.serial_end, b.serial_end)
                if lo <= hi and a.substitute_id != b.substitute_id:
                    conflicts.append(
                        {
                            "original": {"id": a.original_id, "code": a.original.code, "name": a.original.name},
                            "overlap": {"serial_start": lo, "serial_end": hi},
                            "rules": [
                                {
                                    "id": a.id,
                                    "substitute": {"id": a.substitute_id, "code": a.substitute.code, "name": a.substitute.name},
                                    "serial_start": a.serial_start,
                                    "serial_end": a.serial_end,
                                },
                                {
                                    "id": b.id,
                                    "substitute": {"id": b.substitute_id, "code": b.substitute.code, "name": b.substitute.name},
                                    "serial_start": b.serial_start,
                                    "serial_end": b.serial_end,
                                },
                            ],
                            "locations": paths.get(original_id, []),
                        }
                    )
    return conflicts


def validate_version(version: BOMVersion):
    """发布前校验：替代环 + 区间冲突。ok=True 才允许发布。"""
    rules = list(version.rules.select_related("original", "substitute"))
    cycles = find_cycles(rules)
    conflicts = find_conflicts(version)
    return {"ok": not cycles and not conflicts, "cycles": cycles, "conflicts": conflicts}


# ---------------------------------------------------------------------------
# 按序列号解析（反查）
# ---------------------------------------------------------------------------

class ResolutionError(Exception):
    """解析期防御：已发布版本理论上无环无冲突，仍兜底防脏数据。"""


def _rules_index(rules):
    index = defaultdict(list)
    for r in rules:
        index[r.original_id].append(r)
    return index


def resolve_material(rules_index, material_id, serial):
    """沿替代链解析某物料在某序列号下的最终物料。

    每一跳都要求「当前物料有规则且序列号落在区间内」；区间不命中即停。
    同一物料多条命中规则若指向不同替代料（已发布版本不应出现）→ 报错。
    返回 (最终 material_id, chain)，chain 记录每一跳的规则便于前端展示。
    """
    chain, seen, current = [], {material_id}, material_id
    while True:
        hits = [r for r in rules_index.get(current, []) if r.serial_start <= serial <= r.serial_end]
        if not hits:
            return current, chain
        targets = {r.substitute_id for r in hits}
        if len(targets) > 1:
            raise ResolutionError(f"物料 {current} 在序列号 {serial} 命中多条互斥规则")
        rule = min(hits, key=lambda r: (r.serial_end - r.serial_start, r.id))  # 取最窄区间，确定性
        nxt = rule.substitute_id
        if nxt in seen:
            raise ResolutionError(f"替代链在序列号 {serial} 上成环")
        chain.append(
            {
                "rule_id": rule.id,
                "from": {"id": rule.original_id, "code": rule.original.code, "name": rule.original.name},
                "to": {"id": rule.substitute_id, "code": rule.substitute.code, "name": rule.substitute.name},
                "serial_start": rule.serial_start,
                "serial_end": rule.serial_end,
            }
        )
        seen.add(nxt)
        current = nxt


def resolve_tree(version: BOMVersion, serial: int):
    """整棵 BOM 按序列号解析：每个节点给出 原物料→生效物料 与替代链。"""
    rules = list(version.rules.select_related("original", "substitute"))
    index = _rules_index(rules)

    def walk(node):
        effective_id, chain = resolve_material(index, node["material_id"], serial)
        effective = chain[-1]["to"] if chain else None
        return {
            "line_id": node["line_id"],
            "path": node["path"],
            "quantity": node["quantity"],
            "unit": node["unit"],
            "original": {"id": node["material_id"], "code": node["code"], "name": node["name"]},
            "effective": effective
            or {"id": node["material_id"], "code": node["code"], "name": node["name"]},
            "substituted": bool(chain),
            "chain": chain,
            "children": [walk(ch) for ch in node["children"]],
        }

    return [walk(root) for root in build_tree(version)]


def latest_published(product):
    return (
        product.versions.filter(status=BOMVersion.Status.PUBLISHED)
        .order_by("-published_at", "-id")
        .first()
    )


def snapshot_payload(product, version, serial, source, issued_at=None):
    """发料冻结 / 实时解析共用的载荷结构。"""
    payload = {
        "product": {"id": product.id, "code": product.code, "name": product.name},
        "serial_no": serial,
        "source": source,  # live=按最新发布版实时解析 / issued=发料冻结快照
        "version": {"id": version.id, "version": version.version, "status": version.status},
        "lines": resolve_tree(version, serial),
    }
    if issued_at is not None:
        payload["issued_at"] = issued_at.isoformat()
    return payload
