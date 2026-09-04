"""Novel Studio 实体与叙事拓扑图分析器（基于 NetworkX）。

提供：
  - path: 实体间最短剧情/社交链路寻路（破局跳板分析）
  - neighbors: 查看任意实体的 1-Hop/2-Hop 关联网络
  - isolated: 孤立/边缘资产排查（防伏笔与人物烂尾）
  - centrality: 关键枢纽角色/核心道具中介中心度排名
  - summary: 全书叙事关系网全局体检
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import common

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False


def build_narrative_graph(ws_path: Path) -> nx.Graph:
    """从 state/entities.json 与 state/lines.json 构建全景叙事拓扑图。"""
    if not _HAS_NX:
        raise RuntimeError("未安装 networkx 库，请运行 pip install networkx")

    G = nx.Graph()
    state_dir = ws_path / "state"

    # 1. 实体加载
    entities_file = state_dir / "entities.json"
    if entities_file.is_file():
        try:
            data = common.load_json(entities_file, default={}) or {}
            entries = data.get("entries", [])
            for ent in entries:
                name = ent.get("name")
                if not name:
                    continue
                G.add_node(
                    name,
                    node_type="entity",
                    entity_type=ent.get("type", "other"),
                    realm=ent.get("realm", ""),
                    faction=ent.get("faction", ""),
                    holder=ent.get("holder", ""),
                    location=ent.get("location", ""),
                    status=ent.get("status", "active"),
                    summary=ent.get("summary", ""),
                    scope=ent.get("scope", ""),
                    golden_quote=ent.get("golden_quote", ""),
                    dossier=ent.get("dossier", ""),
                )

            for ent in entries:
                name = ent.get("name")
                if not name or name not in G:
                    continue
                faction = ent.get("faction")
                if faction and faction in G:
                    G.add_edge(name, faction, relation="faction", label="所属势力")
                holder = ent.get("holder")
                if holder and holder in G:
                    G.add_edge(name, holder, relation="holder", label="持有")
                loc = ent.get("location")
                if loc:
                    for node in list(G.nodes):
                        if G.nodes[node].get("entity_type") == "place" and node in loc and node != name:
                            G.add_edge(name, node, relation="located_in", label="位于")
                for rel in ent.get("relations", []):
                    target = rel.get("target")
                    if target and target in G:
                        rtype = rel.get("type", "tension")
                        rdesc = rel.get("desc", "")
                        G.add_edge(name, target, relation=rtype, label=rdesc)
        except Exception:
            pass

    # 2. 伏笔/误会/秘密线索关联加载
    lines_file = state_dir / "lines.json"
    if lines_file.is_file():
        try:
            ldata = common.load_json(lines_file, default={}) or {}
            for mis in ldata.get("misunderstandings", []):
                parties = mis.get("parties", "")
                mis_id = mis.get("id", "MIS")
                G.add_node(mis_id, node_type="line", line_type="misunderstanding", content=mis.get("content", ""), requires=mis.get("requires", []))
                for node in list(G.nodes):
                    if node in parties and node != mis_id:
                        G.add_edge(node, mis_id, relation="misunderstanding", label="认知差牵涉")

            for gun in ldata.get("foreshadows", []):
                gun_id = gun.get("id", "GUN")
                gun_name = gun.get("name", "")
                plan = gun.get("plan", "")
                G.add_node(gun_id, node_type="line", line_type="foreshadow", name=gun_name, plan=plan, requires=gun.get("requires", []))
                for node in list(G.nodes):
                    if (node in gun_name or (plan and node in plan)) and node != gun_id:
                        G.add_edge(node, gun_id, relation="foreshadow", label="伏笔关联")

            for kno in ldata.get("knowledge", []):
                kno_id = kno.get("id", "KNO")
                secret = kno.get("secret", "")
                note = kno.get("note", "")
                G.add_node(kno_id, node_type="line", line_type="knowledge", secret=secret, note=note, requires=kno.get("requires", []))
                for node in list(G.nodes):
                    if (node in secret or (note and node in note)) and node != kno_id:
                        G.add_edge(node, kno_id, relation="knowledge", label="秘密关联")

            for item in (ldata.get("foreshadows", []) + ldata.get("misunderstandings", []) + ldata.get("knowledge", [])):
                lid = item.get("id")
                if lid and lid in G:
                    for req in item.get("requires", []):
                        if req in G:
                            G.add_edge(lid, req, relation="requires", label="前置因果依赖")
        except Exception:
            pass

    return G


def extract_scene_tensions(G: nx.Graph, present_entities: list[str]) -> list[str]:
    """计算当前场景中实体两两之间的张力、恩怨与利益博弈切片（AI专用）。"""
    if not _HAS_NX or not G:
        return []
    valid = [e for e in present_entities if e in G]
    if len(valid) < 2:
        return []

    tensions = []
    seen_pairs = set()
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            u, v = valid[i], valid[j]
            pair_key = tuple(sorted((u, v)))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            if G.has_edge(u, v):
                edge_data = G.get_edge_data(u, v, default={})
                rel = edge_data.get("relation", "")
                label = edge_data.get("label", "")
                if rel in ("debt", "rival", "ally", "distrust", "subordinate", "tension", "hostile", "friend") or label:
                    detail = f"：{label}" if label else ""
                    tensions.append(f"{u} ➔ {v}【{rel}】{detail}")
            else:
                # 检查 dossier 中是否存在对方的备忘
                u_dossier = G.nodes[u].get("dossier", "")
                v_dossier = G.nodes[v].get("dossier", "")
                if u_dossier and v in u_dossier:
                    tensions.append(f"{u} 对 {v}【历史备忘】：{u_dossier[:40]}")
                elif v_dossier and u in v_dossier:
                    tensions.append(f"{v} 对 {u}【历史备忘】：{v_dossier[:40]}")

    return tensions[:4]


def cmd_summary(G: nx.Graph) -> None:
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    n_entities = sum(1 for _, d in G.nodes(data=True) if d.get("node_type") == "entity")
    n_lines = sum(1 for _, d in G.nodes(data=True) if d.get("node_type") == "line")
    components = list(nx.connected_components(G))
    comp_count = len(components)
    main_pct = 0.0
    if components and n_nodes > 0:
        main_comp = max(components, key=len)
        main_pct = (len(main_comp) / n_nodes) * 100.0

    print("=" * 65)
    print(" 🌐 [NetworkX 实体与叙事关系网全景]")
    print("=" * 65)
    print(f" 节点总数: {n_nodes}（实体: {n_entities}, 线索: {n_lines}）")
    print(f" 关系边数: {n_edges}")
    print(f" 连通分支: {comp_count} 个")
    if components and n_nodes > 0:
        print(f" 最大主连通子图覆盖: {len(max(components, key=len))} / {n_nodes} 节点 ({main_pct:.1f}%)")
    print("=" * 65)


def cmd_path(G: nx.Graph, source: str, target: str) -> None:
    print(f" 🔍 寻找从 [{source}] 到 [{target}] 的破局跳板/叙事路径...")
    if source not in G:
        print(f"❌ 未找到起点节点: {source}")
        return
    if target not in G:
        print(f"❌ 未找到终点节点: {target}")
        return

    if not nx.has_path(G, source, target):
        print(f"⚠️ [{source}] 与 [{target}] 在当前拓扑中暂无连通路径（二者完全孤立或尚未产生交集）！")
        return

    shortest = nx.shortest_path(G, source, target)
    print(f"\n ⭐ 【最短破局链路】 (距离: {len(shortest) - 1} 跳):")
    chain = []
    for i in range(len(shortest) - 1):
        u, v = shortest[i], shortest[i + 1]
        edge_data = G.get_edge_data(u, v, default={})
        rel = edge_data.get("label", edge_data.get("relation", "关联"))
        chain.append(f"[{u}] ──({rel})──> ")
    chain.append(f"[{shortest[-1]}]")
    print("   " + "".join(chain))

    all_paths = list(nx.all_simple_paths(G, source, target, cutoff=4))
    if len(all_paths) > 1:
        print(f"\n 💡 备选叙事跳板路径 (前 {min(len(all_paths), 3)} 条):")
        for idx, p in enumerate(all_paths[:3], 1):
            print(f"   {idx}. {' -> '.join(p)}")


def cmd_neighbors(G: nx.Graph, node: str, depth: int = 1) -> None:
    if node not in G:
        print(f"❌ 未找到节点: {node}")
        return
    print(f" 🕸️ 实体 [{node}] 的 {depth}-Hop 关联子网:")
    if depth == 1:
        neighbors = list(G.neighbors(node))
        if not neighbors:
            print("   （当前无直接关联节点）")
            return
        for n in neighbors:
            edge = G.get_edge_data(node, n, default={})
            rel = edge.get("label", edge.get("relation", "关联"))
            ntype = G.nodes[n].get("entity_type", G.nodes[n].get("node_type", ""))
            summary = G.nodes[n].get("summary", G.nodes[n].get("content", ""))
            print(f"   • ({rel}) ──> [{n}] ({ntype}): {summary[:40]}")
    else:
        sub_nodes = {node}
        for n in G.neighbors(node):
            sub_nodes.add(n)
            for nn in G.neighbors(n):
                sub_nodes.add(nn)
        print(f"   共涵盖 {len(sub_nodes)} 个节点: {', '.join(sorted(sub_nodes))}")


def cmd_isolated(G: nx.Graph) -> None:
    print(" ⚠️ [孤立/边缘资产排查（防烂尾与闲置设定）]")
    isolated = [n for n in G.nodes if G.degree(n) == 0]
    low_degree = [n for n in G.nodes if G.degree(n) == 1 and G.nodes[n].get("node_type") == "entity"]

    if isolated:
        print(f"\n 🚫 完全孤立节点（与其他任何人物/势力/道具零关联，共 {len(isolated)} 个）:")
        for n in isolated:
            d = G.nodes[n]
            print(f"   • [{n}] ({d.get('entity_type', d.get('node_type'))}): {d.get('summary', '')[:40]}")
    else:
        print(" ✅ 未发现完全孤立节点（0 度）。")

    if low_degree:
        print(f"\n ⚠️ 边缘单边节点（仅有 1 条关联，后续易被遗忘，共 {len(low_degree)} 个）:")
        for n in low_degree:
            neighbor = next(iter(G.neighbors(n)))
            d = G.nodes[n]
            print(f"   • [{n}] 仅连接 [{neighbor}] ｜ 简介: {d.get('summary', '')[:35]}")


def cmd_centrality(G: nx.Graph) -> None:
    print(" 👑 [叙事核心与中介枢纽度排名 (Betweenness Centrality)]")
    if not G.nodes:
        print("   （当前图无节点）")
        return
    bc = nx.betweenness_centrality(G)
    dc = nx.degree_centrality(G)

    ranked = sorted(G.nodes, key=lambda n: (bc[n], dc[n]), reverse=True)
    print(f"{'排名':<4} {'实体/节点':<18} {'类型':<10} {'度中心度':<10} {'中介中心度(剧情枢纽)':<12}")
    print("-" * 65)
    for idx, n in enumerate(ranked[:12], 1):
        d = G.nodes[n]
        t = d.get("entity_type", d.get("line_type", d.get("node_type", "other")))
        print(f"{idx:<4} {n:<18} {t:<10} {dc[n]:<10.3f} {bc[n]:<12.3f}")


def run_graph(book: Path, action: str | None, **kwargs) -> int:
    common.reconfigure_utf8()
    if not _HAS_NX:
        print("❌ 未检测到 networkx 库，请运行 pip install networkx")
        return 1

    try:
        G = build_narrative_graph(book)
    except Exception as exc:
        print(f"❌ 拓扑图构建失败: {exc}")
        return 1

    act = action or "summary"
    if act == "summary":
        cmd_summary(G)
    elif act == "path":
        cmd_path(G, kwargs.get("source", ""), kwargs.get("target", ""))
    elif act == "neighbors":
        cmd_neighbors(G, kwargs.get("name", ""), kwargs.get("depth", 1))
    elif act == "isolated":
        cmd_isolated(G)
    elif act == "centrality":
        cmd_centrality(G)
    else:
        print(f"❌ 未知 graph 动作: {act}")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-w", "--workspace", help="工作区路径")

    parser = argparse.ArgumentParser(description="Novel Studio 实体与叙事拓扑图分析器", parents=[parent_parser])
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("summary", help="全图拓扑总览", parents=[parent_parser])
    p_path = subparsers.add_parser("path", help="两实体间最短剧情/社交链路寻路", parents=[parent_parser])
    p_path.add_argument("source", help="起点实体名称")
    p_path.add_argument("target", help="终点实体名称")

    p_neighbors = subparsers.add_parser("neighbors", help="查看实体关联子网", parents=[parent_parser])
    p_neighbors.add_argument("name", help="实体名称")
    p_neighbors.add_argument("--depth", type=int, default=1, choices=[1, 2], help="关联跳数")

    subparsers.add_parser("isolated", help="排查孤立/边缘资产", parents=[parent_parser])
    subparsers.add_parser("centrality", help="计算角色与道具的剧情中介枢纽排名", parents=[parent_parser])

    args = parser.parse_args(argv)
    book = common.resolve_workspace(args.workspace)
    if book is None:
        print("❌ 未找到有效工作区（请用 -w 指定书目录）")
        return 1

    return run_graph(
        book,
        args.subcommand,
        source=getattr(args, "source", None),
        target=getattr(args, "target", None),
        name=getattr(args, "name", None),
        depth=getattr(args, "depth", 1),
    )


if __name__ == "__main__":
    raise SystemExit(main())
