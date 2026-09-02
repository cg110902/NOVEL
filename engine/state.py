"""状态机核心（SSOT + 提案确定性合并）。

全部「死板」操作：
- 6 个 JSON 状态文件为机器真值；读写都过 engine/schemas/ 的声明式校验，引擎自身也不写非法数据。
- 提案 = 唯一写入口：信封 schema + 分区规则校验 → 全部通过才落盘（内存事务：先全量合并到副本，
  任一分区报错则整体不写）；落盘阶段再带字节级备份，写失败即整体回滚。
- 幂等：operation_id → canonical hash 登记于 .applied_operations.json；重复跳过、同 id 异内容拒绝。
- 账本：余额永远由流水重算得出，balance_after/current 都不是 AI 可信字段——引擎重算后写回。
- sync 流水线：apply_inbox → verify_state → snapshot <ch>_done（由 cli.cmd_sync 编排）。
"""
from __future__ import annotations

import contextlib
import copy
import json
import re
from pathlib import Path

from . import common, validator

MUTATION_SCHEMA = "novel-studio.state-mutation/v2"
STATE_DIR_NAME = "state"
INBOX_NAME = "inbox"
MARKER_NAME = ".applied_operations.json"
STATE_KEYS = ("current", "entities", "lines", "timeline", "ledger", "synopsis")

CH_RE = re.compile(r"ch_(\d{3,})$")
GUN_ID_RE = re.compile(r"GUN-\d{3,}")
MIS_ID_RE = re.compile(r"MIS-\d{3,}")
KNO_ID_RE = re.compile(r"KNO-\d{3,}")
NO_MERGE_SUFFIXES = (".draft.json", ".template.json", ".sample.json")

_SCHEMA_CACHE: dict[str, dict] = {}

# lines 台账三类的机械口径（ID 前缀/状态枚举/可更新字段）——合并与校验共用，零语义
_LINE_KIND_SPEC = {
    "foreshadow": {"id_re": GUN_ID_RE, "prefix": "GUN",
                   "statuses": ("Planted", "Reminded", "Resolved"), "resolved": "Resolved",
                   "plant_fields": {"name", "target_ch", "plant_ch", "plan", "weight"},
                   "plant_need": ("name",), "update_str": ("name", "plan"),
                   "update_fields": {"status", "target_ch", "plan", "name", "weight"}},
    "misunderstanding": {"id_re": MIS_ID_RE, "prefix": "MIS",
                         "statuses": ("Active", "Resolved"), "resolved": "Resolved",
                         "plant_fields": {"parties", "content", "truth", "level", "target_ch"},
                         "plant_need": ("parties", "content"),
                         "update_str": ("content", "truth", "parties"),
                         "update_fields": {"status", "target_ch", "content", "truth", "level", "parties"}},
    "knowledge": {"id_re": KNO_ID_RE, "prefix": "KNO",
                  "statuses": ("Concealed", "Revealed"), "resolved": "Revealed",
                  "plant_fields": {"secret", "target_ch", "plant_ch", "note", "weight"},
                  "plant_need": ("secret",), "update_str": ("secret", "note"),
                  "update_fields": {"status", "target_ch", "secret", "note", "weight"}},
}


def _schema(name: str) -> dict:
    if name not in _SCHEMA_CACHE:
        p = Path(__file__).resolve().parent / "schemas" / f"{name}.schema.json"
        _SCHEMA_CACHE[name] = json.loads(p.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[name]


_ENTITY_TYPES = frozenset(
    _schema("entities")["properties"]["entries"]["items"]["properties"]["type"]["enum"])


# ---------------------------------------------------------------------------
# 目录与默认值
# ---------------------------------------------------------------------------
def state_dir(book: Path) -> Path:
    return Path(book) / STATE_DIR_NAME


def inbox_dir(book: Path) -> Path:
    return state_dir(book) / INBOX_NAME


def defaults_for(key: str) -> dict:
    if key == "current":
        return {"time": "", "region": "", "location": "", "power_level": "", "abilities": "",
                "injury": "", "equipment": "", "assets": "", "situation": "", "mood": "",
                "goal": "", "key_relationships": "", "present_characters": []}
    if key == "entities":
        return {"entries": []}
    if key == "lines":
        return {"foreshadows": [], "misunderstandings": [], "knowledge": []}
    if key == "timeline":
        return {"events": [], "arcs": [], "clocks": []}
    if key == "ledger":
        return {"note": "复式多资源池账本：余额一律由流水重算，禁止手改",
                "pools": {"standard_currency": {"name": "主通货", "unit": "枚", "initial": 0, "current": 0}},
                "transactions": []}
    if key == "synopsis":
        return {"book_logline": "", "chapters": {}}
    raise KeyError(f"未知状态键: {key}")


INBOX_README = """# state/inbox — 提案收件箱（Stage 4 Reader 交付 / Stage 5 主控审定工位）

一切状态修改从这里进：每章一个 `ch_XXX.json`（填提案以本 README 样例为准，
业务规则见 novel_workflow.md#Stage 5）。processed/ = 已应用的审计记录（永不删改）；
failed/ = 失败提案，就地处修复后重跑 `sync`，引擎自动捡回。

正式提案必须带 operation_id（`ch_XXX.director.<序号>`）；`*.draft.json`/`*.template.json`/`*.sample.json` 不参与合并，
可放这里当草稿。最小样例（各分区都给了最短合法形状）：

```json
{
  "schema": "novel-studio.state-mutation/v2",
  "chapter": "ch_007",
  "operation_id": "ch_007.director.0829a",
  "current": {"location": "青石镇·祠堂", "present_characters": ["沈拓", "村长"],
              "mood": "强压着怒意，面上赔笑", "goal": "查清公册下落，先稳住村长"},
  "entities": [{"action": "upsert", "name": "村长", "type": "person",
               "summary": "青石镇村长，玉佩旧案的知情人", "aliases": ["老丈"]},
              {"action": "upsert", "name": "祠堂", "type": "place",
               "summary": "册墙藏十年公册。现状：钥匙轮值周——'现状'写进 summary；status 是枚举"},
              {"action": "upsert", "name": "玉佩", "type": "item",
               "summary": "沈家遗物，认主", "holder": "沈拓", "location": "怀中", "condition": "完整"}],
  "lines": [
    {"kind": "foreshadow", "action": "plant", "name": "祠堂牌位下的匣子", "target_ch": 12,
     "weight": 3},
    {"kind": "foreshadow", "action": "resolve", "id": "GUN-003"},
    {"kind": "misunderstanding", "action": "plant", "parties": "沈拓与村长", "content": "村长误以为沈拓来夺公册",
     "level": 1, "target_ch": 10},
    {"kind": "knowledge", "action": "plant", "secret": "村长认得沈家旧印", "target_ch": 9,
     "note": "沈拓 ch_9 前不得知道", "weight": 2},
    {"kind": "knowledge", "action": "resolve", "id": "KNO-001"}
  ],
  "timeline": {"events": [{"time": "次日清晨", "event": "开祠堂"}]},
  "ledger": {"transactions": [{"pool": "standard_currency", "delta": -30,
                  "subject": "香火钱", "counterparty": "祠堂"}]},
  "synopsis": {"title": "祠堂", "text": "沈拓借赔罪进祠堂，瞥见牌位下露出半角匣子。"}
}
```

写提案的纪律：只写增量；事实必须能在本章 final 正文找到出处；不确定就不上账。
current 只写要刷新的字段：缺省/空值＝不修改（引擎跳过空串与空数组，不当作清档）。
status 只许 active/retired（越界整案回滚进 failed/）；"现状/近况"一律并入 summary——upsert 即覆盖，逐章刷新。
修订通道（随提案合并，全程留审计痕迹）：
  timeline.events 条目支持 {"time": "…", "event": "既有事件原文", "replace": "修订后描述"}——
  按 time+event 逐字命中既有事件后只改写其描述（不新增、chapter 保持原值），未命中整案拒绝；
  synopsis 支持 {"chapters": {"ch_XXX": {"title": "…", "synopsis": "…"}}}——跨章修订历史章的标题/梗概。
引文接地（强烈建议）：各条目（entities/lines/ledger.transactions/timeline.events/timeline.clocks/synopsis）
  可携带 "quote": "逐字摘自本章 final 的支撑句"——sync 前引擎机械校验引文必须是当章 final 的子串，
  编造或改写引文将整案拒绝；未携带引文的条目由 `proposal verify` 提示。
填完六区先 `python studio.py proposal check ch_XXX`（结构预检+三方事实对照，不落盘），
再 `sync ch_XXX --dry-run` 预演。
"""


def init_state(book: Path) -> int:
    """建目录树 + 播种 6 个状态文件与 inbox 样例（已存在者不动）。返回播种数。"""
    sd = state_dir(book)
    seeded = 0
    for key in STATE_KEYS:
        p = sd / f"{key}.json"
        if not p.exists():
            common.dump_json(p, defaults_for(key))
            seeded += 1
    (sd / INBOX_NAME / "processed").mkdir(parents=True, exist_ok=True)
    (sd / INBOX_NAME / "failed").mkdir(parents=True, exist_ok=True)
    (sd / "snapshots").mkdir(parents=True, exist_ok=True)
    (Path(book) / "log" / "review").mkdir(parents=True, exist_ok=True)
    readme = sd / INBOX_NAME / "README.md"
    if not readme.exists():
        readme.write_text(INBOX_README, encoding="utf-8")
    return seeded


# ---------------------------------------------------------------------------
# 读写（双双过 schema）
# ---------------------------------------------------------------------------
def _fill_missing_required(key: str, data: dict) -> dict:
    """读时补全：旧版状态文件缺新增 required 键时按结构默认值补齐（纯结构，零语义）。
    补齐只在内存生效，下一次 save 自然落盘；不改写文件内容以外的任何东西。"""
    if key == "lines":
        for arr_key in ("foreshadows", "misunderstandings", "knowledge"):
            if arr_key not in data:
                data[arr_key] = []
    return data


def load_state(book: Path, key: str) -> dict:
    p = state_dir(book) / f"{key}.json"
    if not p.exists():
        raise ValueError(f"状态文件缺失: {p.name}（先运行 studio init）")
    data = common.load_json(p)  # 损坏 → 直接抛，不静默兜底
    data = _fill_missing_required(key, data)
    errors = validator.validate(data, _schema(key))
    if errors:
        raise ValueError(f"{p.name} schema 校验失败: " + "; ".join(errors[:5]))
    return data


def save_state(book: Path, key: str, data: dict) -> None:
    errors = validator.validate(data, _schema(key))
    if errors:
        raise ValueError(f"拒绝写入非法 {key}.json: " + "; ".join(errors[:5]))
    common.dump_json(state_dir(book) / f"{key}.json", data)


def _load_marker(book: Path) -> dict:
    p = state_dir(book) / MARKER_NAME
    if not p.exists():
        return {}
    marker = common.load_json(p)
    if not isinstance(marker, dict):
        raise ValueError(f"{MARKER_NAME} 必须是对象，实际 {type(marker).__name__}")
    return marker


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _chapter_num(ch: str) -> int | None:
    m = CH_RE.search(ch or "")
    return int(m.group(1)) if m else None


def _next_id(items: list[dict], id_key: str, prefix: str) -> str:
    maxn = 0
    for it in items:
        m = re.search(prefix + r"-(\d+)", str(it.get(id_key, "")))
        if m:
            maxn = max(maxn, int(m.group(1)))
    return f"{prefix}-{maxn + 1:03d}"


def _norm_target(value) -> tuple[object, str | None]:
    """target_ch：正整数（引爆章）或 'longline'（长线）。返回 (规范值, 错误)。"""
    if value is None:
        return "longline", None
    if isinstance(value, int) and not isinstance(value, bool):
        return (value, None) if value >= 1 else (value, 'target_ch 必须为正整数章号或 "longline"')
    if isinstance(value, str):
        if value == "longline":
            return "longline", None
        m = re.fullmatch(r"第\s*(\d+)\s*章", value)
        if m:
            return int(m.group(1)), None
    return value, f"target_ch 非法: {value!r}（允许：正整数章号 或 \"longline\"；「第N章」写法自动折算）"


def _index_by(items: list[dict], key: str) -> dict:
    return {str(it.get(key, "")): it for it in items}


# ---------------------------------------------------------------------------
# 提案：校验
# ---------------------------------------------------------------------------
def validate_proposal(proposal, expected_chapter: str | None = None) -> tuple[list[str], dict]:
    """返回 (errors, section_plan)。section_plan 用于 dry-run 展示。"""
    errors: list[str] = []
    plan: dict[str, str] = {}
    if not isinstance(proposal, dict):
        return ["提案必须是 JSON 对象"], plan

    errors.extend(validator.validate(proposal, _schema("proposal")))
    for k in proposal:
        if k.startswith("candidate_"):
            errors.append(f"{k}: 候选字段仅供复核，禁止直接进入合并")
    if proposal.get("_draft"):
        errors.append("这是草稿提案（_draft:true）：复核补全后另存为正式提案再 sync")
    if not proposal.get("operation_id"):
        errors.append("正式提案必须提供 operation_id（幂等身份）")

    chapter = proposal.get("chapter")
    if expected_chapter is not None and chapter != expected_chapter:
        errors.append(f"chapter 与同步目标不一致: {chapter} != {expected_chapter}")

    def _plan(sec, n):
        plan[sec] = f"合并 {sec} × {n}"

    # --- current ---
    cur = proposal.get("current")
    if isinstance(cur, dict):
        _plan("current", len(cur))
        for k in cur:
            if k not in _schema("current")["properties"]:
                errors.append(f"current 含未知字段: {k}")
        pcs = cur.get("present_characters")
        if pcs is not None and (not isinstance(pcs, list) or any(not isinstance(x, str) for x in pcs)):
            errors.append("current.present_characters 必须是字符串数组")

    # --- entities ---
    ents = proposal.get("entities")
    if isinstance(ents, list):
        _plan("entities", len(ents))
        allowed_entity_keys = {"action", "name", "type", "card", "summary", "status", "aliases",
                               "holder", "location", "condition", "quote",
                               "realm", "faction", "life_status", "attitude", "charges", "max_charges"}
        for i, e in enumerate(ents):
            if not isinstance(e, dict):
                errors.append(f"entities[{i}] 必须为对象")
                continue
            for k in e:
                if k not in allowed_entity_keys:
                    errors.append(f"entities[{i}] 含未知字段: {k}")
            if e.get("action", "upsert") not in ("upsert", "register", "retire"):
                errors.append(f"entities[{i}].action 必须为 upsert/retire")
            if not str(e.get("name", "")).strip():
                errors.append(f"entities[{i}].name 必填")
            if "status" in e and e["status"] not in ("active", "retired"):
                errors.append(f"entities[{i}].status 必须 ∈ ['active', 'retired']，收到 {e['status']!r}")
            if "life_status" in e and e["life_status"] not in ("alive", "deceased", "missing"):
                errors.append(f"entities[{i}].life_status 必须 ∈ ['alive', 'deceased', 'missing']，收到 {e['life_status']!r}")
            if "attitude" in e and e["attitude"] not in ("hostile", "neutral", "friendly", "allied"):
                errors.append(f"entities[{i}].attitude 必须 ∈ ['hostile', 'neutral', 'friendly', 'allied']，收到 {e['attitude']!r}")
            if "charges" in e and (not isinstance(e["charges"], int) or isinstance(e["charges"], bool) or e["charges"] < 0):
                errors.append(f"entities[{i}].charges 必须为 ≥0 的整数")
            if "max_charges" in e and (not isinstance(e["max_charges"], int) or isinstance(e["max_charges"], bool) or e["max_charges"] < 1):
                errors.append(f"entities[{i}].max_charges 必须为 ≥1 的整数")
            if "type" in e and e["type"] not in _ENTITY_TYPES:
                errors.append(f"entities[{i}].type 非法: {e['type']!r}（合法：{'/'.join(sorted(_ENTITY_TYPES))}）")
            for f in ("card", "summary", "holder", "location", "condition", "realm", "faction", "quote"):
                if f in e and not isinstance(e[f], str):
                    errors.append(f"entities[{i}].{f} 必须为字符串")
            if "aliases" in e:
                if not isinstance(e["aliases"], list):
                    errors.append(f"entities[{i}].aliases 必须为字符串数组（收到 {type(e['aliases']).__name__}）")
                elif any(not isinstance(a, str) for a in e["aliases"]):
                    errors.append(f"entities[{i}].aliases 的元素必须为字符串")

    # --- lines ---
    lines = proposal.get("lines")
    if isinstance(lines, list):
        _plan("lines", len(lines))
        for i, g in enumerate(lines):
            if not isinstance(g, dict):
                errors.append(f"lines[{i}] 必须为对象")
                continue
            kind = g.get("kind")
            spec = _LINE_KIND_SPEC.get(kind)
            if spec is None:
                errors.append(f"lines[{i}].kind 必须为 foreshadow/misunderstanding/knowledge")
                continue
            action = g.get("action", "plant")
            if kind == "knowledge":
                if action not in ("plant", "update", "resolve"):
                    errors.append(f"lines[{i}].action 非法: {action}（knowledge 支持 plant/update/resolve，"
                                  f"揭不揭由你判断——引擎只记账）")
                    continue
            elif action not in ("plant", "update", "remind", "resolve"):
                errors.append(f"lines[{i}].action 非法: {action}")
                continue
            base_keys = {"kind", "action", "id", "quote"}
            if action == "plant":
                allowed = base_keys | spec["plant_fields"]
                for k in g:
                    if k not in allowed:
                        errors.append(f"lines[{i}] 含未知字段: {k}")
                for f in spec["plant_need"]:
                    if not str(g.get(f, "")).strip():
                        errors.append(f"lines[{i}]（plant {kind}）必须提供 {f}")
                    elif not isinstance(g[f], str):
                        errors.append(f"lines[{i}].{f} 必须为字符串")
                if kind == "misunderstanding" and "level" in g and (
                        not isinstance(g["level"], int) or isinstance(g["level"], bool) or g["level"] < 1):
                    errors.append(f"lines[{i}].level 必须为 ≥1 的整数")
                if kind in ("foreshadow", "knowledge") and "weight" in g and (
                        not isinstance(g["weight"], int) or isinstance(g["weight"], bool) or g["weight"] < 1):
                    errors.append(f"lines[{i}].weight 必须为 ≥1 的整数")
                if g.get("id") and not spec["id_re"].fullmatch(str(g["id"])):
                    errors.append(f"lines[{i}].id 必须匹配 {spec['id_re'].pattern}")
                _, terr = _norm_target(g.get("target_ch"))
                if terr:
                    errors.append(f"lines[{i}]: {terr}")
                pc = g.get("plant_ch")
                if pc is not None and (not isinstance(pc, int) or isinstance(pc, bool) or pc < 1):
                    errors.append(f"lines[{i}].plant_ch 必须为正整数")
            else:
                if action in ("remind", "resolve"):
                    allowed = base_keys | spec["plant_fields"] | spec["update_fields"]
                    for k in g:
                        if k not in allowed:
                            errors.append(f"lines[{i}] 含未知字段: {k}")
                if not g.get("id"):
                    errors.append(f"lines[{i}]（{action}）必须提供 id")
                if action == "remind" and kind != "foreshadow":
                    errors.append(f"lines[{i}]: remind 只适用于 foreshadow（knowledge/misunderstanding 保持现状即可，无需多余动作）")
                if action == "update":
                    for f in spec["update_str"]:
                        if f in g and not isinstance(g[f], str):
                            errors.append(f"lines[{i}].{f} 必须为字符串")
                    if kind == "misunderstanding" and "level" in g and (
                            not isinstance(g["level"], int) or isinstance(g["level"], bool) or g["level"] < 1):
                        errors.append(f"lines[{i}].level 必须为 ≥1 的整数")
                    if kind in ("foreshadow", "knowledge") and "weight" in g and (
                            not isinstance(g["weight"], int) or isinstance(g["weight"], bool) or g["weight"] < 1):
                        errors.append(f"lines[{i}].weight 必须为 ≥1 的整数")

    # --- timeline ---
    tl = proposal.get("timeline")
    if isinstance(tl, dict):
        n = len(tl.get("events", []) or []) + len(tl.get("arcs", []) or []) + len(tl.get("clocks", []) or [])
        _plan("timeline", n)
        for k in tl:
            if k not in ("events", "arcs", "clocks"):
                errors.append(f"timeline 含未知字段: {k}")
        for i, ev in enumerate(tl.get("events", []) or []):
            if not isinstance(ev, dict):
                errors.append(f"timeline.events[{i}] 必须为对象")
                continue
            # time/event 必须是字符串：非字符串会让合并期的去重键不可哈希（直接崩）
            if (not isinstance(ev.get("time"), str) or not ev["time"].strip()
                    or not isinstance(ev.get("event"), str) or not ev["event"].strip()):
                errors.append(f"timeline.events[{i}] 必须含非空字符串 time 与 event")
            for k in ev:
                if k not in ("time", "event", "replace", "quote"):
                    errors.append(f"timeline.events[{i}] 含未知字段: {k}（chapter 由引擎按提案章写入）")
            if "replace" in ev and (not isinstance(ev["replace"], str) or not ev["replace"].strip()):
                errors.append(f"timeline.events[{i}].replace 必须为非空字符串"
                              "（修订语义：按 time+event 逐字命中既有事件后改写其描述）")
            if "quote" in ev and (not isinstance(ev["quote"], str) or not ev["quote"].strip()):
                errors.append(f"timeline.events[{i}].quote 必须为非空字符串（逐字摘自 final 的支撑句）")
        for i, a in enumerate(tl.get("arcs", []) or []):
            if not isinstance(a, dict) or not isinstance(a.get("name"), str) or not a["name"].strip():
                errors.append(f"timeline.arcs[{i}] 必须含非空字符串 name")
                continue
            for k in a:
                if k not in ("name", "baseline", "stage", "inciting_event", "strategy", "ultimate"):
                    errors.append(f"timeline.arcs[{i}] 含未知字段: {k}")
            for f in ("baseline", "stage", "inciting_event", "strategy", "ultimate"):
                if f in a and not isinstance(a[f], str):
                    errors.append(f"timeline.arcs[{i}].{f} 必须为字符串")
        for i, c in enumerate(tl.get("clocks", []) or []):
            if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"].strip():
                errors.append(f"timeline.clocks[{i}] 必须含非空字符串 name")
                continue
            for k in c:
                if k not in ("name", "target_ch", "urgency", "desc", "status", "quote"):
                    errors.append(f"timeline.clocks[{i}] 含未知字段: {k}")
            tch = c.get("target_ch")
            if not isinstance(tch, int) or isinstance(tch, bool) or tch < 1:
                errors.append(f"timeline.clocks[{i}].target_ch 必须为 ≥1 的正整数")
            if "urgency" in c and c["urgency"] not in ("low", "medium", "high", "critical"):
                errors.append(f"timeline.clocks[{i}].urgency 必须 ∈ ['low', 'medium', 'high', 'critical']")
            if "status" in c and c["status"] not in ("Active", "Triggered", "Defused", "Expired"):
                errors.append(f"timeline.clocks[{i}].status 必须 ∈ ['Active', 'Triggered', 'Defused', 'Expired']")

    # --- ledger ---
    led = proposal.get("ledger")
    if isinstance(led, dict):
        txs = led.get("transactions", []) or []
        _plan("ledger", len(txs))
        for k in led:
            if k not in ("pools", "transactions"):
                errors.append(f"ledger 含未知字段: {k}（说明性字段不进提案）")
        pools = led.get("pools")
        if pools is not None:
            if not isinstance(pools, dict):
                errors.append("ledger.pools 必须为对象（新增/修订资源池声明）")
            else:
                for pid, p in pools.items():
                    if not isinstance(p, dict):
                        errors.append(f"ledger.pools[{pid}] 必须为对象")
                        continue
                    if "current" in p:
                        errors.append(f"ledger.pools[{pid}].current 不接受声明（余额一律由流水重算，禁止手改）")
                    if "initial" in p and (not isinstance(p["initial"], int) or isinstance(p["initial"], bool)):
                        errors.append(f"ledger.pools[{pid}].initial 必须为整数")
                    for f in ("name", "unit"):
                        if f in p and not isinstance(p[f], str):
                            errors.append(f"ledger.pools[{pid}].{f} 必须为字符串")
        for i, t in enumerate(txs):
            if not isinstance(t, dict):
                errors.append(f"ledger.transactions[{i}] 必须为对象")
                continue
            for k in t:
                if k not in ("chapter", "pool", "delta", "type", "subject", "counterparty", "note", "quote"):
                    errors.append(f"ledger.transactions[{i}] 含未知字段: {k}")
            if "pool" in t and not isinstance(t["pool"], str):
                errors.append(f"ledger.transactions[{i}].pool 必须为字符串")
            elif not str(t.get("pool", "")).strip():
                errors.append(f"ledger.transactions[{i}].pool 必填")
            if "subject" in t and not isinstance(t["subject"], str):
                errors.append(f"ledger.transactions[{i}].subject 必须为字符串")
            elif not str(t.get("subject", "")).strip():
                errors.append(f"ledger.transactions[{i}].subject 必填（记账事由）")
            if "type" in t and t["type"] not in ("income", "expense", "opening_balance", "manual"):
                errors.append(f"ledger.transactions[{i}].type 必须 ∈ "
                              "['income', 'expense', 'opening_balance', 'manual']")
            delta = t.get("delta")
            if not isinstance(delta, int) or isinstance(delta, bool):
                errors.append(f"ledger.transactions[{i}].delta 必须为整数（收入为正/支出为负；拒绝浮点）")
            else:
                ttype = t.get("type")
                if ttype == "income" and delta < 0:
                    errors.append(f"ledger.transactions[{i}]: type=income 但 delta={delta}（正收负支）")
                if ttype == "expense" and delta > 0:
                    errors.append(f"ledger.transactions[{i}]: type=expense 但 delta={delta}（支出必须为负数）")
            if t.get("chapter") is not None and not re.fullmatch(r"ch_\d{3,}", str(t["chapter"])):
                errors.append(f"ledger.transactions[{i}].chapter 须匹配 ch_NNN（缺省用提案章节）")
            for f in ("counterparty", "note", "quote"):
                if f in t and not isinstance(t[f], str):
                    errors.append(f"ledger.transactions[{i}].{f} 必须为字符串")

    # --- synopsis ---
    syn = proposal.get("synopsis")
    if isinstance(syn, dict):
        _plan("synopsis", 1)
        for k in syn:
            if k not in ("book_logline", "title", "text", "chapters", "quote"):
                errors.append(f"synopsis 含未知字段: {k}")
        for f in ("text", "title", "book_logline", "quote"):
            if f in syn and not isinstance(syn[f], str):
                errors.append(f"synopsis.{f} 必须为字符串")
        chapters = syn.get("chapters")
        if chapters is not None:
            # 跨章修订通道：键=ch_XXX，值={title?/synopsis?}——修正历史章的标题/梗概。
            if not isinstance(chapters, dict):
                errors.append("synopsis.chapters 必须为对象（键=ch_XXX，值={title?, synopsis?}）")
            else:
                for c, cp in chapters.items():
                    if not re.fullmatch(r"ch_\d{3,}", str(c)):
                        errors.append(f"synopsis.chapters 键须匹配 ch_NNN: {c!r}")
                        continue
                    if not isinstance(cp, dict):
                        errors.append(f"synopsis.chapters[{c}] 必须为对象")
                        continue
                    for f in cp:
                        if f not in ("title", "synopsis"):
                            errors.append(f"synopsis.chapters[{c}] 含未知字段: {f}（该通道只修订标题/梗概）")
                    for f in ("title", "synopsis"):
                        if f in cp and not isinstance(cp[f], str):
                            errors.append(f"synopsis.chapters[{c}].{f} 必须为字符串")
    return errors, plan


# ---------------------------------------------------------------------------
# 提案：各分区内存合并（只改传入的 data 副本；错误写入 report.errors）
# ---------------------------------------------------------------------------
def _merge_current(state: dict, patch: dict, rep: dict) -> None:
    allowed = set(_schema("current")["properties"])
    for k, v in patch.items():
        if k not in allowed:
            rep["errors"].append(f"current 含未知字段: {k}")
            continue
        if k == "present_characters":
            if not isinstance(v, list):
                rep["errors"].append("current.present_characters 必须为字符串数组")
                continue
            if not v:
                rep["warnings"].append("current.present_characters 为空数组，按未提供处理（留空＝不修改）")
                continue
            state["present_characters"] = list(v)
        elif isinstance(v, str):
            if not v:
                # 空串不落盘：这些是描述性字段，"清档"应写成描述（如"伤势已愈"）；
                # 空串几乎只会来自未填写的表单/骨架，照单全收会抹掉上一章的现场速写。
                rep["warnings"].append(f"current.{k} 为空字符串，按未提供处理（留空＝不修改）")
                continue
            state[k] = v
        else:
            rep["errors"].append(f"current.{k} 必须为字符串")
            continue
        rep["updated"].append(f"📍 current.{k} 已更新")


def _merge_entities(state: dict, items: list[dict], rep: dict) -> None:
    idx = _index_by(state["entries"], "name")
    valid_types = _ENTITY_TYPES
    for e in items:
        action, name = e.get("action", "upsert"), e["name"]
        if action == "retire":
            ent = idx.get(name)
            if ent is None:
                rep["errors"].append(f"retire 未登记实体「{name}」——不猜测，先补 upsert")
                continue
            ent["status"] = "retired"
            rep["updated"].append(f"🗂️ 实体退役：{name}")
            continue
        ent = idx.get(name)
        etype = e.get("type", "other")
        if etype not in valid_types:
            rep["errors"].append(
                f"实体「{name}」type 非法: {etype}（合法：{'/'.join(sorted(valid_types))}）"
            )
            continue
        if ent is None:
            ent = {"name": name, "type": etype, "aliases": [], "card": "", "summary": "", "status": "active"}
            state["entries"].append(ent)
            idx[name] = ent
        for f in ("type", "card", "summary", "holder", "location", "condition",
                  "realm", "faction", "life_status", "attitude", "charges", "max_charges"):
            if f in e:
                ent[f] = e[f]
        if "status" in e:
            ent["status"] = e["status"]
        if "aliases" in e:
            ent["aliases"] = sorted(set(ent.get("aliases", [])) | {str(a) for a in e["aliases"]})
        rep["updated"].append(f"🗂️ 实体登记/更新：{name}")


def _merge_lines(state: dict, items: list[dict], ch_num: int, rep: dict) -> None:
    buckets = {"foreshadow": state["foreshadows"], "misunderstanding": state["misunderstandings"],
               "knowledge": state["knowledge"]}
    for g in items:
        kind, action = g["kind"], g.get("action", "plant")
        spec = _LINE_KIND_SPEC[kind]
        arr = buckets[kind]
        idx = _index_by(arr, "id")
        if action == "plant":
            gid = g.get("id") or _next_id(arr, "id", spec["prefix"])
            if gid in idx:
                rep["errors"].append(f"{gid} 已存在，重复 plant 拒绝（改状态请用 update/resolve）")
                continue
            target, terr = _norm_target(g.get("target_ch"))
            if terr:
                rep["errors"].append(f"plant {gid}: {terr}")
                continue
            if kind == "foreshadow":
                arr.append({"id": gid, "name": g["name"], "plant_ch": g.get("plant_ch") or ch_num,
                            "status": "Planted", "target_ch": target, "weight": g.get("weight", 1),
                            "plan": g.get("plan", "")})
                rep["updated"].append(f"🕸️ 埋设伏笔 {gid}《{g['name']}》→ target {target}"
                                      f"（权重 {g.get('weight', 1)}）")
            elif kind == "misunderstanding":
                arr.append({"id": gid, "parties": g["parties"], "content": g["content"],
                            "truth": g.get("truth", ""), "level": g.get("level", 1),
                            "target_ch": target, "status": "Active"})
                rep["updated"].append(f"🎭 新误会 {gid}：{g['content'][:30]}")
            else:  # knowledge
                arr.append({"id": gid, "secret": g["secret"], "plant_ch": g.get("plant_ch") or ch_num,
                            "status": "Concealed", "target_ch": target,
                            "weight": g.get("weight", 1), "note": g.get("note", "")})
                rep["updated"].append(f"🔒 知识线登记 {gid}《{g['secret'][:24]}》→ 计划揭示 {target}"
                                      f"（权重 {g.get('weight', 1)}）")
            idx[gid] = arr[-1]
            continue
        gid = g.get("id")
        ent = idx.get(gid)
        if ent is None:
            rep["errors"].append(f"{action} 目标 {gid} 不存在——台账里没有这条，拒绝猜测")
            continue
        if action == "resolve":
            ent["status"] = spec["resolved"]
            if kind == "knowledge":
                t = ent.get("target_ch")
                if ch_num and isinstance(t, int) and t != ch_num:
                    tag = "提前" if ch_num < t else "逾期"
                    rep["updated"].append(f"🔓 {gid} 已揭示（{tag}：计划 ch_{t:03d}，本章 ch_{ch_num:03d}）")
                else:
                    rep["updated"].append(f"🔓 {gid} 已揭示")
            else:
                rep["updated"].append(f"✅ {gid} 已回收/澄清")
        elif action == "remind":
            ent["status"] = "Reminded"
            rep["updated"].append(f"🔔 {gid} 已回唤")
        else:  # update
            for k, v in g.items():
                if k in ("kind", "action", "id", "quote"):
                    continue
                if k not in spec["update_fields"]:
                    rep["errors"].append(f"update {gid}: 不允许修改字段 {k}")
                    continue
                if k == "target_ch":
                    v, terr = _norm_target(v)
                    if terr:
                        rep["errors"].append(f"update {gid}: {terr}")
                        continue
                if k == "status":
                    if v not in spec["statuses"]:
                        rep["errors"].append(f"update {gid}: status 必须 ∈ {sorted(spec['statuses'])}")
                        continue
                ent[k] = v
            rep["updated"].append(f"🔁 {gid} 已更新")


def _merge_timeline(state: dict, patch: dict, ch: str, rep: dict) -> None:
    existing = {(e.get("time", ""), e.get("event", "")) for e in state["events"]}
    added = replaced = skipped = 0
    for ev in patch.get("events", []) or []:
        key = (ev.get("time", ""), ev.get("event", ""))
        new_text = ev.get("replace")
        if new_text is not None:
            # 修订通道：按 (time, event) 逐字命中既有事件，只改写 event 描述（chapter 保持原值）。
            target = next((e for e in state["events"]
                           if (e.get("time", ""), e.get("event", "")) == key), None)
            if target is None:
                rep["errors"].append(
                    f"timeline 事件修订未命中: {key[0]}｜{str(key[1])[:30]}…"
                    "（time+event 须与 state/timeline.json 逐字一致）")
                continue
            target["event"] = new_text
            replaced += 1
            rep["updated"].append(f"📜 编年史修订：{key[0]}「{str(key[1])[:20]}…」→「{new_text[:32]}…」")
            continue
        if key in existing:
            skipped += 1
            continue
        state["events"].append({"time": ev["time"], "event": ev["event"], "chapter": ch})
        existing.add(key)
        added += 1
    if added:
        rep["updated"].append(f"📜 编年史 +{added} 条")
    if replaced:
        rep["updated"].append(f"📜 编年史修订 {replaced} 条")
    if skipped:
        rep["warnings"].append(f"编年史去重跳过 {skipped} 条重复事件")
    arcs = state["arcs"]
    idx = _index_by(arcs, "name")
    for a in patch.get("arcs", []) or []:
        name = a["name"]
        ent = idx.get(name)
        if ent is None:
            ent = {"name": name, "baseline": a.get("baseline") or a.get("stage") or "初始基线",
                   "stage": a.get("stage", ""), "inciting_event": a.get("inciting_event", ""),
                   "ultimate": a.get("ultimate", "")}
            arcs.append(ent)
            idx[name] = ent
            rep["updated"].append(f"🧠 新建成长弧：{name}")
        for f in ("stage", "baseline", "inciting_event", "ultimate"):
            if a.get(f):
                ent[f] = a[f]
        if a.get("strategy"):
            ent["strategy"] = a["strategy"]  # 覆盖式：当前策略只留最新，历史按章归档
            hist = ent.setdefault("strategy_history", [])
            entry = {"chapter": ch, "strategy": a["strategy"]}
            # 去重：同章同策略只在历史里记一次，避免重复提案/重放导致膨胀。
            if not any(h.get("chapter") == ch and h.get("strategy") == a["strategy"] for h in hist):
                hist.append(entry)
        rep["updated"].append(f"🧠 {name} 阶段 → {ent.get('stage', '')}")

    clocks = state.setdefault("clocks", [])
    c_idx = _index_by(clocks, "name")
    for c in patch.get("clocks", []) or []:
        cname = c["name"]
        cent = c_idx.get(cname)
        if cent is None:
            cent = {
                "name": cname,
                "target_ch": c["target_ch"],
                "urgency": c.get("urgency", "medium"),
                "desc": c.get("desc", ""),
                "status": c.get("status", "Active")
            }
            clocks.append(cent)
            c_idx[cname] = cent
            rep["updated"].append(f"⏰ 新增危机时钟「{cname}」→ 目标 ch_{c['target_ch']:03d}")
        else:
            for f in ("target_ch", "urgency", "desc", "status"):
                if f in c:
                    cent[f] = c[f]
            rep["updated"].append(f"⏰ 危机时钟「{cname}」已更新（状态: {cent.get('status')}）")


def _merge_ledger(state: dict, patch: dict, ch: str, rep: dict) -> None:
    pools = state["pools"]
    for pid, p in (patch.get("pools") or {}).items():
        if pid in pools:
            # 已有池只允许改 display 名/单位；initial 是历史事实，禁止事后改
            #（否则既有 balance_after 与重算值必然冲突，造成"永不可合并"的死路）。
            for f in ("name", "unit"):
                if f in p:
                    pools[pid][f] = p[f]
            if "initial" in p and int(p["initial"]) != int(pools[pid].get("initial", 0)):
                rep["errors"].append(
                    f"资源池 '{pid}' 是既有池，禁止修改 initial（按账本不变量，改期初=改历史）")
                return
            if any(f in p for f in ("name", "unit")):
                rep["warnings"].append(f"资源池 {pid} 声明已修订（余额随重算变化属预期）")
        else:
            pools[pid] = {"name": p.get("name", pid), "unit": p.get("unit", ""),
                          "initial": p.get("initial", 0), "current": p.get("initial", 0)}
            rep["updated"].append(f"💱 新资源池 {pid}（{p.get('name', pid)}）")

    running = {k: v.get("initial", 0) for k, v in pools.items()}
    for i, t in enumerate(state["transactions"]):
        pool = t.get("pool")
        if pool not in running:
            rep["errors"].append(f"既有流水 #{i + 1} 引用未声明池 '{pool}'（数据损坏：修复 ledger 或回滚快照）")
            return
        running[pool] += int(t.get("delta", 0))
        rec = t.get("balance_after")
        if rec is not None and int(rec) != running[pool]:
            rep["errors"].append(
                f"既有流水 #{i + 1} balance_after={rec} 与重算值 {running[pool]} 不符——"
                "状态文件疑似被手改；回滚到最近快照（见 studio snapshot list）")
            return

    for t in patch.get("transactions", []) or []:
        pool = t["pool"]
        if pool not in pools:
            rep["errors"].append(f"流水引用未声明资源池 '{pool}'（先在 ledger.pools 登记）")
            continue
        delta = int(t["delta"])
        running[pool] += delta
        tx = {"chapter": t.get("chapter", ch), "pool": pool, "delta": delta,
              "type": t.get("type") or ("income" if delta >= 0 else "expense"),
              "subject": t["subject"], "balance_after": running[pool]}
        for f in ("counterparty", "note"):
            if t.get(f):
                tx[f] = t[f]
        state["transactions"].append(tx)
        rep["updated"].append(f"💰 {pool} {delta:+} → 余额 {running[pool]}（{tx['subject']}）")

    for k, v in pools.items():
        v["current"] = running.get(k, v.get("initial", 0))
    if patch.get("transactions"):
        rep["updated"].append(f"🧮 余额已从流水全量重算（{len(state['transactions'])} 笔）")


def _merge_synopsis(state: dict, patch: dict, ch: str, rep: dict) -> None:
    if patch.get("book_logline"):
        state["book_logline"] = patch["book_logline"]
        rep["updated"].append("📖 全书 logline 已更新")
    if patch.get("text"):
        chs = state.setdefault("chapters", {})
        prev = chs.get(ch, {})
        if prev.get("source") == "manual" and prev.get("synopsis") and prev["synopsis"] != patch["text"]:
            rep["warnings"].append(f"⚠️ {ch} 已有人工梗概，本次提交覆盖之（旧：{prev['synopsis'][:30]}…）")
        chs[ch] = {"num": _chapter_num(ch) or 0, "title": patch.get("title", prev.get("title", "")),
                   "synopsis": patch["text"], "source": "manual"}
        rep["updated"].append(f"📖 章节梗概已登记（{ch}）")
    # 跨章修订通道（处理顺序在 text 之后：同章同字段时以显式修订为准）
    for c, cp in (patch.get("chapters") or {}).items():
        chs = state.setdefault("chapters", {})
        ent = chs.get(c)
        if ent is None:
            ent = {"num": _chapter_num(c) or 0, "title": "", "synopsis": "", "source": "manual"}
            chs[c] = ent
            rep["updated"].append(f"📖 新增章节梗概占位（{c}）")
        for f in ("title", "synopsis"):
            if f in cp:
                v = cp[f]
                if not v.strip():
                    rep["warnings"].append(f"synopsis.chapters.{c}.{f} 为空白字符串，按未提供处理")
                    continue
                ent[f] = v
                rep["updated"].append(f"📖 {c} {f} 已修订 →「{v[:24]}…」")


# ---------------------------------------------------------------------------
# 应用一份提案
# ---------------------------------------------------------------------------
def _merge_proposal_into(data: dict, proposal: dict, ch, ch_num, rep: dict) -> None:
    """在内存副本上执行全部分区合并；rep['errors'] 非空 = 整体拒绝（含 dry-run 预演）。"""
    if proposal.get("current"):
        _merge_current(data["current"], proposal["current"], rep)
    if proposal.get("entities"):
        _merge_entities(data["entities"], proposal["entities"], rep)
    if proposal.get("lines"):
        _merge_lines(data["lines"], proposal["lines"], ch_num or 0, rep)
    if proposal.get("timeline"):
        _merge_timeline(data["timeline"], proposal["timeline"], ch, rep)
    if proposal.get("ledger"):
        _merge_ledger(data["ledger"], proposal["ledger"], ch, rep)
    if proposal.get("synopsis"):
        _merge_synopsis(data["synopsis"], proposal["synopsis"], ch, rep)


def apply_proposal(book: Path, proposal: dict, expected_chapter: str | None = None,
                   dry_run: bool = False) -> dict:
    rep: dict = {"updated": [], "warnings": [], "errors": [],
                 "chapter": proposal.get("chapter") if isinstance(proposal, dict) else None}
    errors, plan = validate_proposal(proposal, expected_chapter)
    rep["plan"] = plan
    if errors:
        rep["errors"] = errors
        return rep

    ch, op = proposal["chapter"], proposal["operation_id"]
    ch_num = _chapter_num(ch)
    proposal_hash = common.canonical_json_hash({k: v for k, v in proposal.items() if k != "operation_id"})
    try:
        marker = _load_marker(book)
    except (ValueError, OSError) as exc:
        rep["errors"].append(f"幂等登记簿损坏，拒绝合并: {exc}")
        return rep
    if op in marker:
        if marker[op] != proposal_hash:
            rep["errors"].append(f"operation_id {op} 已用于不同内容，拒绝复用（请换新 id）")
        else:
            rep["warnings"].append(f"operation_id {op} 已应用过，跳过（幂等）")
            rep["duplicate"] = True
        return rep
    if proposal_hash in marker.values():
        rep["warnings"].append("相同内容提案（canonical hash）已应用过，跳过（幂等）")
        rep["duplicate"] = True
        return rep

    # 内存事务：先取全部 SSOT 副本，任何损坏 → 拒绝合并（dry-run 与正式同一条路）。
    try:
        data = {key: copy.deepcopy(load_state(book, key)) for key in STATE_KEYS}
    except ValueError as exc:
        rep["errors"].append(f"状态 SSOT 不可用，拒绝合并: {exc}")
        return rep
    before_hash = {key: common.canonical_json_hash(data[key]) for key in STATE_KEYS}

    _merge_proposal_into(data, proposal, ch, ch_num, rep)
    if rep["errors"]:
        # 有错 → 一个字节都不写。dry-run 也返回真实合并错误，而非只给"计划"。
        # 清空"已更新"列出以免误导（整体回滚，任何分区都未生效）。
        rep["updated"] = []
        rep["warnings"] = []
        if dry_run:
            rep["dry_run"] = True
        return rep

    # 同步前置闸门（Stage 5 状态落盘前体检闸门，novel_workflow.md#Stage 5）：
    # 在内存副本上先跑"状态体检"（账本重算/唯一性/实体闭合），全部通过才允许落盘。
    # 任何体检失败 → 整体拒绝，一个字节都不写、不归档、不封存快照——避免"脏状态已写入、
    # 提案却进了 processed/、无法走 failed/ 捡回"的不可恢复污染。
    verify_errors = verify_data(data)
    if verify_errors:
        rep["errors"].extend(verify_errors)
        rep["updated"] = []
        rep["warnings"] = []
        if dry_run:
            rep["dry_run"] = True
        return rep

    # 空提案识别：以合并前后六表的 canonical hash 为准，而不是"有没有写过字段"——
    # 写入与原值相同或空的内容不算变更。防止未填骨架/零信息提案被计入 applied 并封存快照。
    rep["changed"] = any(common.canonical_json_hash(data[key]) != before_hash[key]
                         for key in STATE_KEYS)

    if dry_run:
        rep["dry_run"] = True
        return rep

    # 落盘阶段：全量备份 → 写 → 登记幂等；异常 → 字节级回滚
    sd = state_dir(book)
    paths = {key: sd / f"{key}.json" for key in STATE_KEYS}
    marker_path = sd / MARKER_NAME
    backup = {p: p.read_bytes() for p in list(paths.values()) + ([marker_path] if marker_path.exists() else [])}
    try:
        for key in STATE_KEYS:
            save_state(book, key, data[key])
        marker[op] = proposal_hash
        common.dump_json(marker_path, marker)
    except Exception as exc:
        for p, content in backup.items():
            with contextlib.suppress(OSError):
                p.write_bytes(content)
        rep["errors"].append(f"落盘异常，已整体回滚: {exc}")
        rep["rollback"] = True
    return rep


# ---------------------------------------------------------------------------
# 收件箱批处理（sync 的第一步）
# ---------------------------------------------------------------------------
def _gather(inbox: Path) -> list[Path]:
    if not inbox.exists():
        return []
    return sorted(p for p in inbox.glob("*.json") if not p.name.endswith(NO_MERGE_SUFFIXES))


def _archive(pf: Path, dst: Path) -> Path:
    """移动提案到归档目录；重名自动加 .2/.3… 绝不覆盖审计记录；rename 竞态自动重试（P3-17）。"""
    dst.mkdir(parents=True, exist_ok=True)
    try:
        target = dst / pf.name
        if not target.exists():
            pf.rename(target)
            return target
    except OSError:
        pass
    for i in range(2, 100):
        cand = dst / f"{pf.stem}.{i}{pf.suffix}"
        try:
            if not cand.exists():
                pf.rename(cand)
                return cand
        except OSError:
            continue
    target = dst / f"{pf.stem}.{common.time_suffix()}{pf.suffix}"
    pf.rename(target)
    return target


def pending_proposals(book: Path) -> list[Path]:
    """inbox 中的未决正式提案（CLI status 共用；不含 drafts/templates/samples）。"""
    return _gather(inbox_dir(book))


def apply_inbox(book: Path, expect_chapter: str | None = None, dry_run: bool = False) -> dict:
    """锁内批处理收件箱。expect_chapter 模式只合并本章提案，其余留在原地；
    非 dry-run 时先从 failed/ 捡回本章提案重试。失败即停（不带着病状态继续合并下一份）。"""
    inbox = inbox_dir(book)
    overall = {"applied": 0, "failed": 0, "duplicates": 0, "skipped": 0, "results": [], "picked_up": False}
    def _failed_candidates() -> list[Path]:
        """failed/ 中本章提案候选——含重名归档的 .2/.3 变体（P2-5：只认精确名会让二次失败永远滞留）。"""
        fdir = inbox / "failed"
        if not expect_chapter or not fdir.is_dir():
            return []
        return sorted(p for p in fdir.glob(f"{expect_chapter}*.json")
                      if not p.name.endswith(NO_MERGE_SUFFIXES))

    with common.file_lock(state_dir(book), name=".state.lock", timeout=30.0):
        files = _gather(inbox)  # gather 置于锁内，消除 TOCTOU（P3-17）
        # 捡回 failed/ 中本章提案；同章在途提案已存在时不捡回（以在途为准）。
        if expect_chapter and not (inbox / f"{expect_chapter}.json").exists():
            cands = _failed_candidates()
            if cands and not dry_run:
                for c in cands:
                    dest = inbox / c.name
                    if not dest.exists():
                        c.rename(dest)
                overall["picked_up"] = True
                files = _gather(inbox)
            elif cands:
                files = cands + files  # dry-run 不落盘，仅纳入预演，保持与正式捡回语义一致
        for pf in files:
            result = {"file": pf.name}
            try:
                proposal = common.load_json(pf)
            except (ValueError, OSError) as exc:
                result["errors"] = [f"提案 JSON 解析失败: {exc}"]
                overall["results"].append(result)
                overall["failed"] += 1
                if not dry_run:
                    result["archived_to"] = str(_archive(pf, inbox / "failed"))
                # P2-2: 文件名可判定为其他章节的坏提案 → 归档后继续合并目标章；
                # 归属不明（文件名无章号）或正是目标章 → 维持"失败即停"。
                fn = common.chapter_number_from_name(pf.name)
                tn = common.chapter_token_to_num(expect_chapter) if expect_chapter else None
                if expect_chapter is None or fn is None or fn == tn:
                    break
                result["note"] = "非目标章提案，已归档 failed/ 并继续"
                continue
            ch = proposal.get("chapter") if isinstance(proposal, dict) else None
            if expect_chapter is not None and ch != expect_chapter:
                result["skipped"] = f"提案章节 {ch} ≠ 同步目标 {expect_chapter}（留在收件箱）"
                overall["skipped"] += 1
                overall["results"].append(result)
                continue
            rep = apply_proposal(book, proposal, expected_chapter=expect_chapter, dry_run=dry_run)
            rep["file"] = pf.name
            overall["results"].append(rep)
            if rep["errors"]:
                overall["failed"] += 1
                if not dry_run:
                    rep["archived_to"] = str(_archive(pf, inbox / "failed"))
                break
            if rep.get("duplicate"):
                overall["duplicates"] += 1
            elif rep.get("changed"):
                overall["applied"] += 1
            else:  # no-op：合并后无任何实际变更 → 计为 skipped，不推进流水线、不封存快照
                overall["skipped"] += 1
                rep["noop"] = True
                rep["warnings"].append("提案合并后无任何实际变更（no-op），不计入已应用、不封存")
            if not dry_run:
                rep["archived_to"] = str(_archive(pf, inbox / "processed"))
    return overall


# ---------------------------------------------------------------------------
# 合并后体检（sync 第二步；M2 的 check 命令复用）
# ---------------------------------------------------------------------------
def verify_data(data: dict[str, dict]) -> list[str]:
    """在内存/磁盘的六表副本上跑机械体检：账本重算、唯一性、实体闭合。
    与 verify_state 同口径，但接受任意 data 副本（apply_proposal 在落盘前用它预检）。"""
    errors: list[str] = []

    led = data["ledger"]
    running = {k: v.get("initial", 0) for k, v in led.get("pools", {}).items()}
    for i, t in enumerate(led.get("transactions", []), 1):
        pool = t.get("pool")
        if pool not in running:
            errors.append(f"流水 #{i} 引用未声明池 '{pool}'")
            continue
        running[pool] += int(t.get("delta", 0))
        if t.get("balance_after") is not None and int(t["balance_after"]) != running[pool]:
            errors.append(f"流水 #{i} balance_after={t['balance_after']} ≠ 重算 {running[pool]}")
    for k, v in led.get("pools", {}).items():
        if int(v.get("current", 0)) != running.get(k, 0):
            errors.append(f"资源池 {k} 声明余额 {v.get('current')} ≠ 流水累计 {running.get(k, 0)}")

    for arr_key, id_re, label in (("foreshadows", GUN_ID_RE, "伏笔"), ("misunderstandings", MIS_ID_RE, "误会"),
                                  ("knowledge", KNO_ID_RE, "知识线")):
        ids = [str(g.get("id", "")) for g in data["lines"].get(arr_key, [])]
        dup = sorted({x for x in ids if ids.count(x) > 1})
        if dup:
            errors.append(f"{label}台账重复编号: {dup}")
        bad = [x for x in ids if not id_re.fullmatch(x)]
        if bad:
            errors.append(f"{label}台账非法编号: {bad[:5]}")
    names = [str(e.get("name", "")) for e in data["entities"].get("entries", [])]
    dup = sorted({x for x in names if names.count(x) > 1})
    if dup:
        errors.append(f"实体注册表重名: {dup}")

    # 闭合性与生死状态：current.present_characters 必须已注册且非离世
    known = set(names)
    deceased_names = set()
    for e in data["entities"].get("entries", []):
        known.update(str(a) for a in e.get("aliases", []) if a)
        if e.get("life_status") == "deceased":
            deceased_names.add(e["name"])
            deceased_names.update(str(a) for a in e.get("aliases", []) if a)
    for name in data["current"].get("present_characters", []):
        if str(name).strip() and str(name) not in known:
            errors.append(f"current.present_characters 引用未登记实体「{name}」"
                          "（先在 entities 提案注册，名字须与卡一致）")
        elif str(name) in deceased_names:
            errors.append(f"current.present_characters 引用已离世/战死实体「{name}」（life_status=deceased）")

    # 闭合性：item 实体的 holder 必须已注册（人名/别名）——持有关系不许悬空
    for e in data["entities"].get("entries", []):
        holder = str(e.get("holder", "")).strip()
        if holder and holder not in known:
            errors.append(f"实体「{e.get('name','')}」的 holder「{holder}」未登记"
                          "（先注册持有者；holder 必须是已注册实体名）")

    # 危机时钟校验
    for i, clk in enumerate(data["timeline"].get("clocks", []), 1):
        cname = clk.get("name")
        if not cname:
            errors.append(f"时钟 #{i} 缺少 name 名称")
        tch = clk.get("target_ch")
        if not isinstance(tch, int) or tch < 1:
            errors.append(f"时钟「{cname or i}」target_ch 非法: {tch}（须为 ≥1 的正整数）")
    return errors


def verify_state(book: Path) -> list[str]:
    """从磁盘加载六表并跑机械体检（M2 的 check 命令与 sync 复用）。"""
    data: dict[str, dict] = {}
    for key in STATE_KEYS:
        try:
            data[key] = load_state(book, key)
        except (ValueError, FileNotFoundError) as exc:
            return [str(exc)]
    return verify_data(data)
