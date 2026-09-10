"""proposal v3 寻址式提案：编译到 v2 后走同一管线（语义对齐 by construction）。

v3 核心价值 = typo-safe 的精确寻址：
- v2 upsert 按 id-or-名匹配，名写错就静默新建（实体碎片化之源）；
- v3 按 kind 表 + id 双重寻址：create 要求 id/名双不存在，update/retire 要求
  id 存在且归属表一致，错一位就编译期报错（带 [op#N] 定位）。

架构：
- v3 提案只含 ops 分区（全十一表皆有 op，不混写 v2 分区；locked_candidates /
  两个 v2 专属分区除外——locked_candidates 要用请写 v2；consequences 已废弃、不落盘）；
- compile_ops 把 ops 编译为等价 v2 提案；新语义代码仅限寻址/存在性/表一致性
  检查（本模块），字段级校验与合并重用 v2 管线（validate/merge/verify 原样跑）；
- 存在性检查面向编译时刻的 live 状态；幂等按 v3 原文哈希 + 编译前预门
  （同字节重提短路为干净 skip，同效异写如实报存在性错误——见 apply 头注释）。

op 形状（ envelope 严格，载荷按表区分）：
- 实体表 persons/items/factions/places（严格寻址，v3 价值所在）：
    {"table", "action": create/update/retire, "id"?, "entry"?/{set}?}
    create: entry{id 必填, name 必填, ...}；type 缺省按寻址表推断（items→item…），
            与表不一致则报错；id/名必须双不存在。
    update: id 必填且须存在、归属表须一致；set 非空；set 禁 name/id（改名请走手术刀）；
            set.type 允许变 kind（搬迁，编译警告）。
    retire: id 必填且须存在、归属表须一致。
- current: {"table": "current", "action": "update", "set": {patch}}（同案重复 set 同键报错）。
- lines/timeline/locked/cognition/ledger/synopsis：{"table", "action", ...v2 条目字段}
  直通编译（action 即 v2 动作名；字段级校验归 v2 管线，错误沿用 v2 措辞）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

V3_SCHEMA = "novel-studio.state-mutation/v3"

_ENTITY_ACTIONS = ("create", "update", "retire")
_TABLE_IMPLIED_TYPE = {"persons": "person", "items": "item",
                       "factions": "faction", "places": "place"}
_V2_SECTIONS = ("current", "entities", "lines", "timeline", "ledger", "synopsis",
                "locked", "locked_candidates", "cognition", "cognition_delta",
                "consequences")


def _tag(i: int, op: dict) -> str:
    base = f"[op#{i} {op.get('table')}/{op.get('action')}]"
    oid = op.get("id")
    if oid:
        base += f" {oid}"
    return base


def _live_index(book: Path) -> tuple[dict[str, tuple[str, dict]],
                                     dict[str, tuple[str, dict]]]:
    from . import state as state_mod
    by_id: dict[str, tuple[str, dict]] = {}
    by_name: dict[str, tuple[str, dict]] = {}
    for k in state_mod.KIND_TABLES:
        for e in state_mod.load_state(book, k).get("entries", []) or []:
            if not isinstance(e, dict):
                continue
            if e.get("id"):
                by_id[str(e["id"])] = (k, e)
            if e.get("name"):
                by_name[str(e["name"])] = (k, e)
    return by_id, by_name


def compile_ops(book: Path | None, proposal: dict
                ) -> tuple[dict, list[str], list[str]]:
    """编译 v3 ops → 等价 v2 提案。返回 (v2, errors, warnings)。

    book 为 None 时只做结构编译（存在性检查跳过；供无状态调用方）。
    纯函数：不读不写磁盘（除存在性检查的 load_state），可反复调用。
    """
    from . import state as state_mod
    errors: list[str] = []
    warnings: list[str] = []
    v2: dict[str, Any] = {"schema": state_mod.MUTATION_SCHEMA,
                          "chapter": proposal.get("chapter"),
                          "operation_id": proposal.get("operation_id")}
    ops = proposal.get("ops")
    if not isinstance(ops, list) or not ops:
        return v2, ["v3 提案 ops 必须为非空数组"], warnings
    for sec in _V2_SECTIONS:
        if sec in proposal:
            errors.append(f"v3 提案禁止混写 v2 分区「{sec}」（全表皆有对应 op，请改写为 ops）")
    if errors:
        return v2, errors, warnings

    by_id: dict[str, tuple[str, dict]] = {}
    by_name: dict[str, tuple[str, dict]] = {}
    index_built = False

    def _ensure_index(tag: str) -> bool:
        nonlocal index_built, by_id, by_name
        if index_built:
            return True
        if book is None:
            return False
        try:
            by_id, by_name = _live_index(book)
        except (ValueError, OSError) as exc:
            errors.append(f"{tag} 状态不可读，存在性检查失败: {exc}")
            return False
        index_built = True
        return True

    v_entities: list[dict] = []
    v_current: dict[str, Any] = {}
    v_lines: list[dict] = []
    v_events: list[dict] = []
    v_clocks: list[dict] = []
    v_arcs: list[dict] = []
    v_milestones: list[dict] = []
    v_locked: list[dict] = []
    v_cognition: list[dict] = []
    v_txs: list[dict] = []
    v_pools: dict[str, Any] = {}
    v_synopsis: dict[str, Any] = {}

    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            errors.append(f"[op#{i}] 必须为对象")
            continue
        tag = _tag(i, op)
        table = op.get("table")
        action = op.get("action")
        if table not in state_mod.ASSERTED_KEYS:
            errors.append(f"{tag} 未知寻址表「{table}」"
                          f"（合法：{'/'.join(state_mod.ASSERTED_KEYS)}）")
            continue
        if not isinstance(action, str) or not action:
            errors.append(f"{tag} action 必填")
            continue

        # ---- 实体四表：严格寻址 ----
        if table in state_mod.KIND_TABLES:
            if action not in _ENTITY_ACTIONS:
                errors.append(f"{tag} 实体 op action 须为 create/update/retire")
                continue
            if not _ensure_index(tag):
                continue  # 无状态调用方：存在性检查跳过（结构错误仍照报）
            if action == "create":
                entry = op.get("entry")
                if not isinstance(entry, dict):
                    errors.append(f"{tag} create 须带 entry 对象")
                    continue
                eid, name = entry.get("id"), str(entry.get("name", "")).strip()
                if not eid or not isinstance(eid, str):
                    errors.append(f"{tag} create.entry.id 必填（v3 寻址要求稳定 id）")
                    continue
                if not name:
                    errors.append(f"{tag} create.entry.name 必填")
                    continue
                if eid in by_id:
                    errors.append(f"{tag} id「{eid}」已存在（{by_id[eid][0]}），create 拒绝覆盖"
                                  "（更新请用 update）")
                    continue
                if name in by_name:
                    errors.append(f"{tag} 名「{name}」已存在（{by_name[name][0]}），create 拒绝重名"
                                  "（更新请用 update）")
                    continue
                raw_t = entry.get("type")
                if raw_t is None:
                    etype = _TABLE_IMPLIED_TYPE[table]  # 地址即类型：静默推断（文档口径）
                else:
                    etype = state_mod.canonical_entity_type(raw_t)
                    if etype is None:
                        errors.append(f"{tag} type 非法：{raw_t!r}")
                        continue
                    if state_mod.TYPE_TO_TABLE[etype] != table:
                        errors.append(f"{tag} 地址表 {table} 与 type {etype} 不一致"
                                      f"（该 type 应寻址 {state_mod.TYPE_TO_TABLE[etype]}）")
                        continue
                item = {"action": "upsert", **entry, "type": etype}
                v_entities.append(item)
                by_id[eid] = (table, item)  # 同案后继 op 可见（create 后 update 同 id 合法）
                by_name[name] = (table, item)
            elif action == "update":
                eid = op.get("id")
                if not eid or not isinstance(eid, str):
                    errors.append(f"{tag} update.id 必填")
                    continue
                hit = by_id.get(eid)
                if hit is None:
                    errors.append(f"{tag} id「{eid}」未登记（新建请用 create，防拼写碎片化）")
                    continue
                owner, live = hit
                if owner != table:
                    errors.append(f"{tag} 地址表错：{eid} 在 {owner} 表不在 {table} 表")
                    continue
                patch = op.get("set")
                if not isinstance(patch, dict) or not patch:
                    errors.append(f"{tag} update.set 必须为非空对象")
                    continue
                if "name" in patch or "id" in patch:
                    errors.append(f"{tag} set 禁止 name/id（身份不可变；改名请走手术刀）")
                    continue
                if "type" in patch:
                    etype = state_mod.canonical_entity_type(patch["type"])
                    if etype is None:
                        errors.append(f"{tag} set.type 非法：{patch['type']!r}")
                        continue
                    dest = state_mod.TYPE_TO_TABLE[etype]
                    if dest != owner:
                        warnings.append(f"{tag} 将搬迁 {owner}→{dest}（type 变更为 {etype}）")
                    patch = {**patch, "type": etype}
                v_entities.append({"action": "upsert", "id": eid,
                                   "name": live.get("name", ""), **patch})
            else:  # retire
                eid = op.get("id")
                if not eid or not isinstance(eid, str):
                    errors.append(f"{tag} retire.id 必填")
                    continue
                hit = by_id.get(eid)
                if hit is None:
                    errors.append(f"{tag} id「{eid}」未登记，无可退役")
                    continue
                owner, live = hit
                if owner != table:
                    errors.append(f"{tag} 地址表错：{eid} 在 {owner} 表不在 {table} 表")
                    continue
                v_entities.append({"action": "retire", "id": eid,
                                   "name": live.get("name", "")})
            continue

        # ---- current：set 补丁 ----
        if table == "current":
            if action != "update":
                errors.append(f"{tag} current 只支持 update")
                continue
            patch = op.get("set")
            if not isinstance(patch, dict) or not patch:
                errors.append(f"{tag} current.update.set 必须为非空对象")
                continue
            for k in patch:
                if k in v_current:
                    errors.append(f"{tag} current.{k} 同案重复 set（请合并为一个 op）")
            v_current.update(patch)
            continue

        # ---- 其余表：直通编译（字段校验归 v2 管线） ----
        rest = {k: v for k, v in op.items() if k not in ("table", "action")}
        if table == "lines":
            if not rest.get("kind"):
                errors.append(f"{tag} lines op 须带 kind（foreshadow/misunderstanding/knowledge）")
                continue
            v_lines.append({"action": action, **rest})
        elif table == "timeline":
            if action == "append_event":
                if not isinstance(rest.get("event"), dict):
                    errors.append(f"{tag} append_event 须带 event 对象")
                    continue
                v_events.append(rest["event"])
            elif action == "revise_event":
                if not rest.get("id") and not rest.get("event"):
                    errors.append(f"{tag} revise_event 须带 id（或 time+event 原文）")
                    continue
                v_events.append(rest)
            elif action == "append_clock":
                if not isinstance(rest.get("clock"), dict):
                    errors.append(f"{tag} append_clock 须带 clock 对象")
                    continue
                v_clocks.append(rest["clock"])
            elif action == "append_arc":
                if not isinstance(rest.get("arc"), dict):
                    errors.append(f"{tag} append_arc 须带 arc 对象")
                    continue
                v_arcs.append(rest["arc"])
            elif action == "append_milestone":
                if not isinstance(rest.get("milestone"), dict):
                    errors.append(f"{tag} append_milestone 须带 milestone 对象")
                    continue
                v_milestones.append(rest["milestone"])
            else:
                errors.append(f"{tag} timeline action 须为 append_event/revise_event/"
                              "append_clock/append_arc/append_milestone")
        elif table == "locked":
            if action not in ("plant", "upsert", "retire"):
                errors.append(f"{tag} locked action 须为 plant/upsert/retire")
                continue
            v_locked.append({"action": action, **rest})
        elif table == "cognition":
            if action not in ("plant", "upsert", "retire"):
                errors.append(f"{tag} cognition action 须为 plant/upsert/retire")
                continue
            v_cognition.append({"action": action, **rest})
        elif table == "ledger":
            if action == "append_transaction":
                if not isinstance(rest.get("entry"), dict):
                    errors.append(f"{tag} append_transaction 须带 entry 对象")
                    continue
                v_txs.append(rest["entry"])
            elif action == "declare_pool":
                pid, spec = rest.get("pool"), rest.get("spec")
                if not pid or not isinstance(spec, dict):
                    errors.append(f"{tag} declare_pool 须带 pool（池键名）+ spec（name/unit/initial）")
                    continue
                if pid in v_pools:
                    errors.append(f"{tag} 同案重复声明池 {pid}")
                    continue
                v_pools[pid] = spec
            else:
                errors.append(f"{tag} ledger action 须为 append_transaction/declare_pool")
        elif table == "synopsis":
            if action != "set":
                errors.append(f"{tag} synopsis 只支持 set")
                continue
            v_synopsis.update(rest)

    if errors:
        return v2, errors, warnings
    if v_entities:
        v2["entities"] = v_entities
    if v_current:
        v2["current"] = v_current
    if v_lines:
        v2["lines"] = v_lines
    tl: dict[str, Any] = {}
    if v_events:
        tl["events"] = v_events
    if v_clocks:
        tl["clocks"] = v_clocks
    if v_arcs:
        tl["arcs"] = v_arcs
    if v_milestones:
        tl["milestones"] = v_milestones
    if tl:
        v2["timeline"] = tl
    if v_locked:
        v2["locked"] = v_locked
    if v_cognition:
        v2["cognition"] = v_cognition
    led: dict[str, Any] = {}
    if v_txs:
        led["transactions"] = v_txs
    if v_pools:
        led["pools"] = v_pools
    if led:
        v2["ledger"] = led
    if v_synopsis:
        v2["synopsis"] = v_synopsis
    return v2, [], warnings


# ---------------------------------------------------------------------------
# 提案形状速查（单一真源）
# ---------------------------------------------------------------------------
# 为什么在这里而不是只写在 state/inbox/README.md：README 是**人类与主控**的完整契约，
# 而 Stage 4 Reader 的角色网关禁读 `state/`（ROLE_DENY），它拿不到 README。
# 本表由 `beats new` 注入到「本章一致性速查」小节——beats 在 Reader 的准读清单内，
# 于是键形状与它唯一的写入口同处一纸，不再要求子代理越权取证。
# ⚠️ 改动 compile_ops 支持的动作/载荷键时，必须同步本表（tests/test_docs_parity.py 会断言
#    本表动作名全部被 compile_ops 认得）。
V3_OP_SHAPES: tuple[tuple[str, str, str], ...] = (
    ("persons/items/factions/places", "create", '{"entry":{"id":"p_010","name":"…","type?":"…","…":"实体字段"}}'),
    ("persons/items/factions/places", "update", '{"id":"it_003","set":{"只写要改的键（禁 id/name）"}}'),
    ("persons/items/factions/places", "retire", '{"id":"loc_002"}'),
    ("current", "update", '{"set":{"location":"…","time?":"…","present_refs?":[…],"…"}}'),
    ("lines", "plant/update/remind/resolve/escalate",
     '{"kind":"foreshadow|misunderstanding|knowledge"（必填）,"action":…,"id":"GUN-004"（plant 可省）,'
     '"target_ch":30（plant 必填：int / ch_NNN / "第N章" / "longline"）,"…":"同 v2 条目字段"}'),
    ("timeline", "append_event / revise_event / append_clock / append_arc / append_milestone",
     '{"event":{"time","event","quote?"}} ｜ {"id":"EVT-003","replace":"…"} ｜ '
     '"clock" 只五键：name/target_ch(int)/urgency/desc/status'),
    ("locked", "plant/upsert/retire",
     '{"id":"LOCK-001"（必填，^LOCK-\\d{3,}$，从水位线之后起号）,"fact","kind","note"（必填红线提示）,'
     '"since_ch","quote?"}'),
    ("cognition", "plant/upsert/retire",
     '{"character","content","kind":"fact","since_ch","quote?"}（id 省略=引擎自动编号并按指纹去重）'),
    ("ledger", "append_transaction / declare_pool",
     '{"entry":{"chapter":"ch_001","pool":"已声明池键","delta":-30,"type":"expense","subject","note?","quote?"}} '
     '｜ {"pool":"stone","spec":{"name","unit","initial"}}（三键必填、禁 current）'),
    ("synopsis", "set", '{"title":"逐字拷贝 final 首行章题","text":"1~2 句梗概","quote?"}'),
)

V3_UNAVAILABLE_V2_ONLY: tuple[str, ...] = ("locked_candidates", "consequences")
