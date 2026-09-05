"""状态机核心（SSOT + 提案确定性合并）。

全部「死板」操作：
- 6 个 JSON 状态文件为机器真值；读写都过 engine/schemas/ 的声明式校验，引擎自身也不写非法数据。
- 提案 = 唯一写入口：信封 schema + 分区规则校验 → 全部通过才落盘（内存事务：先全量合并到副本，
  任一分区报错则整体不写）；落盘阶段再带字节级备份，写失败即整体回滚。
- 幂等：operation_id → canonical hash 登记于 .applied_operations.json；重复跳过、同 id 异内容拒绝。
- 账本：余额永远由流水重算得出，balance_after/current 都不是 AI 可信字段——引擎重算后写回。
- 迁移守卫（advisory）：高危实体状态迁移（复活/退场反转/立场大翻转/充能回升）与时间线回退
  只出警示、绝不阻断，裁决权归主控。
- sync 流水线：apply_inbox → verify_state → snapshot <ch>_done（由 cli.cmd_sync 编排）。
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import json
import re
from pathlib import Path

from . import common, migrations, validator, models

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

_LINE_KIND_SPEC = {
    "foreshadow": {"id_re": GUN_ID_RE, "prefix": "GUN",
                   "statuses": ("Planted", "Reminded", "Resolved"), "resolved": "Resolved",
                   "plant_fields": {"name", "target_ch", "plant_ch", "plan", "weight", "requires"},
                   "plant_need": ("name",), "update_str": ("name", "plan"),
                   "update_fields": {"status", "target_ch", "plan", "name", "weight", "requires"}},
    "misunderstanding": {"id_re": MIS_ID_RE, "prefix": "MIS",
                         "statuses": ("Active", "Escalated", "Resolved"), "resolved": "Resolved",
                         "plant_fields": {"parties", "content", "truth", "level", "target_ch", "requires"},
                         "plant_need": ("parties", "content"),
                         "update_str": ("content", "truth", "parties"),
                         "update_fields": {"status", "target_ch", "content", "truth", "level", "parties", "requires"}},
    "knowledge": {"id_re": KNO_ID_RE, "prefix": "KNO",
                  "statuses": ("Concealed", "Revealed"), "resolved": "Revealed",
                  # QA P17：holders = 知情圈（知情方实体名/别名列表，选填）——
                  # POV 推导对 holders 内角色不再误标「不应知情」，防吃书
                  "plant_fields": {"secret", "target_ch", "plant_ch", "note", "weight", "requires", "holders"},
                  "plant_need": ("secret",), "update_str": ("secret", "note"),
                  "update_fields": {"status", "target_ch", "secret", "note", "weight", "requires", "holders"}},
}


def _schema(name: str) -> dict:
    if name not in _SCHEMA_CACHE:
        p = Path(__file__).resolve().parent / "schemas" / f"{name}.schema.json"
        _SCHEMA_CACHE[name] = json.loads(p.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[name]


_ENTITY_TYPES = frozenset(t.value for t in models.EntityType)  # 唯一真源：Pydantic 枚举


def state_dir(book: Path) -> Path:
    return Path(book) / STATE_DIR_NAME


def inbox_dir(book: Path) -> Path:
    return state_dir(book) / INBOX_NAME


def defaults_for(key: str) -> dict:
    if key == "current":
        return {"time": "", "region": "", "location": "", "power_level": "", "abilities": "",
                "injury": "", "equipment": "", "assets": "", "situation": "", "mood": "",
                "goal": "", "key_relationships": "", "present_characters": [],
                "aftershock": "", "active_pressures": []}
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
业务规则见 `AGENTS.md` 与 `.agents/skills/reader/SKILL.md`）。processed/ = 已应用的审计记录（永不删改；
唯一例外：`init --force` 整本重开）；failed/ = 失败提案，就地处修复后重跑 `sync`，
引擎自动捡回（含重名归档的 .2/.3 变体）。

正式提案必须带 operation_id（建议 `<ch>.<角色>.<时间戳/序号>`，如 ch_007.director.0829a、
ch_007.reader.0901_2125）；`*.draft.json`/`*.template.json`/`*.sample.json` 不参与合并，
可放这里当草稿。entities.action 支持 upsert/register/retire（register 为 upsert 别名）。
 

写提案的纪律：只写增量；事实必须能在本章 final 正文找到出处；不确定就不上账。
current 只写要刷新的字段：缺省/空值＝不修改（引擎跳过空串与空数组，不当作清档）。
status 只许 active/retired（越界整案回滚进 failed/）；"现状/近况"一律并入 summary——upsert 即覆盖，逐章刷新。
修订通道（随提案合并，全程留审计痕迹）：
  timeline.events 条目支持 {"time": "…", "event": "既有事件原文", "replace": "修订后描述"}——
  按 time+event 逐字命中既有事件后只改写其描述（不新增、chapter 保持原值），未命中整案拒绝；
  synopsis 支持 {"chapters": {"ch_XXX": {"title": "…", "synopsis": "…"}}——跨章修订历史章的标题/梗概。
  ⚠️ 跨章梗概修订仅对「已登记」章节生效：指向未注册章整案拒收（不再静默 no-op）。
lines 字段口径：
  target_ch 取值 = int 章号（如 21）/ ch_NNN（三位补零，如 ch_007）/ "第N章"（如 "第29章"）/ "longline" 四选一；
  字符串数字（"21"）与无补零章号（ch_7）均拒收。plant 必填 target_ch。
  knowledge（秘密线）plant 可携带选填 "holders": ["实体名/别名", …] 声明知情圈——
  pov 推导对知情圈内角色不再误标「不应知情」（防吃书）；缺省 = 除正文另行交代外全员不知情。
引文柔性接地（建议携带，绝不阻断）：各条目（entities/lines/ledger.transactions/timeline.events/timeline.clocks/synopsis）
  可携带 "quote": "凭印象摘录的本章 final 支撑句"——引擎模糊接地：相似度 ≥85% 视为命中；
  60~85% 提示「近似命中」；更低仅提示「存疑」。全程只出提示、绝不阻断 sync，
  摘录严禁逐字抠字眼浪费算力；但战死/退役等高危变更强烈建议附引文，便于日后回溯审计。
注：提案写入后由 Stage 5 主控统一运行 `python studio.py sync ch_XXX` 校验并合并（支持 --dry-run 预演）。
Stage 4 Reader 仅需落盘本 JSON 即可交付。
"""


def init_state(book: Path) -> int:
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
    (Path(book) / "log" / "critic").mkdir(parents=True, exist_ok=True)
    readme = sd / INBOX_NAME / "README.md"
    if not readme.exists():
        readme.write_text(INBOX_README, encoding="utf-8")
    common.dump_json(migrations.version_path(book),
                     {"version": migrations.CURRENT_STATE_VERSION,
                      "created_at": datetime.date.today().isoformat()})
    return seeded


def _fill_missing_required(key: str, data: dict) -> dict:
    if key == "lines":
        for arr_key in ("foreshadows", "misunderstandings", "knowledge"):
            if arr_key not in data:
                data[arr_key] = []
    return data


def load_state(book: Path, key: str) -> dict:
    migrations.ensure_state_version(book)  # 懒触发：老书首次读取即迁移到当前状态机版本
    p = state_dir(book) / f"{key}.json"
    if not p.exists():
        raise ValueError(f"状态文件缺失: {p.name}（先运行 studio init）")
    # 加固：拒绝 symlink 状态文件
    if p.is_symlink():
        raise ValueError(f"状态文件 {p.name} 为符号链接，拒绝读取（防外部注入）")
    try:
        if p.resolve() != state_dir(book) / f"{key}.json" and state_dir(book).resolve() not in p.resolve().parents:
            raise ValueError(f"状态文件 {p.name} 越界")
    except OSError:
        pass
    try:
        data = common.load_json(p)
    except OSError as exc:
        # 目录/被占/权限等 IO 故障统一转结构化 ValueError（盲区1 探针发现：
        # 裸 PermissionError 会绕过 apply_proposal 的 ValueError 处理直接炸穿 CLI）
        raise ValueError(f"状态文件不可读: {p.name}（{exc}）") from exc
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
    if p.is_symlink():
        raise ValueError(f"{MARKER_NAME} 为符号链接，拒绝读取")
    marker = common.load_json(p)
    if not isinstance(marker, dict):
        raise ValueError(f"{MARKER_NAME} 必须是对象，实际 {type(marker).__name__}")
    return marker


def _chapter_num(ch: str) -> int | None:
    m = CH_RE.search(ch or "")
    return int(m.group(1)) if m else None


def _canonical_ch(ch: str) -> str:
    """ch_0123 → ch_123：以章号为键的分区（梗概/编年史等）统一三位列，防口径分裂（QA P3-20）。"""
    n = _chapter_num(ch)
    return f"ch_{n:03d}" if n else ch


def _next_id(items: list[dict], id_key: str, prefix: str) -> str:
    maxn = 0
    for it in items:
        m = re.search(prefix + r"-(\d+)", str(it.get(id_key, "")))
        if m:
            maxn = max(maxn, int(m.group(1)))
    return f"{prefix}-{maxn + 1:03d}"


def _norm_target(value) -> tuple[object, str | None]:
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
        m = CH_RE.fullmatch(value)
        if m:
            return int(m.group(1)), None
    return value, (f"target_ch 非法: {value!r}（允许：int 章号如 21 / ch_NNN 三位补零 / \"第N章\" / \"longline\"；"
                   f"字符串数字如 \"21\" 与无补零的 ch_7 均不接受）")


_DAY_NUM_RE = re.compile(r"第\s*([0-9]+|[零一二两三四五六七八九十百]+)\s*[日天]")
_CN_DAY_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9}
_CN_DAY_UNITS = {"十": 10, "百": 100}


def _extract_day_num(text: str) -> int | None:
    """从 current.time 自由文本提取「第N日/天」序数；解析失败返回 None（绝不误报）。"""
    m = _DAY_NUM_RE.search(str(text or ""))
    if not m:
        return None
    s = m.group(1)
    if s.isdigit():
        return int(s)
    total = num = 0
    for ch in s:
        if ch in _CN_DAY_DIGITS:
            num = _CN_DAY_DIGITS[ch]
        elif ch in _CN_DAY_UNITS:
            total += (num or 1) * _CN_DAY_UNITS[ch]
            num = 0
        else:
            return None
    value = total + num
    return value if value > 0 else None


def _warn_time_regression(state: dict, new_val: str, rep: dict) -> None:
    old_day = _extract_day_num(str(state.get("time", "")))
    new_day = _extract_day_num(new_val)
    if old_day is not None and new_day is not None and new_day < old_day:
        rep["warnings"].append(
            f"⏳ 时间线回退：current.time「{state.get('time', '')}」→「{new_val}」"
            f"（第 {old_day} 日 → 第 {new_day} 日）——若为闪回/倒叙章请忽略本提示")


_ATTITUDE_BIG_FLIPS = {("hostile", "allied"), ("hostile", "friendly"),
                       ("allied", "hostile"), ("friendly", "hostile")}


def _guard_entity_transitions(name: str, old: dict, new: dict, rep: dict) -> None:
    """状态迁移守卫（advisory）：可疑迁移只警示不阻断，裁决权归主控。"""
    old_life = str(old.get("life_status") or "").strip().lower()
    new_life = str(new.get("life_status") or "").strip().lower()
    if new_life == "deceased" and old_life != "deceased":
        rep["warnings"].append(f"🚨【高危状态变更】实体「{name}」生命状态变更为【离世 (deceased)】——请核实正文确凿事实")
    if old_life == "deceased" and new_life in ("alive", "missing"):
        rep["warnings"].append(f"🚨【高危状态变更】实体「{name}」由 deceased 复活为 {new_life}——请核实正文确凿事实，或此前死亡系误记")
    old_status = str(old.get("status") or "").strip().lower()
    new_status = str(new.get("status") or "").strip().lower()
    if old_status == "retired" and new_status == "active":
        rep["warnings"].append(f"🚨【高危状态变更】实体「{name}」由 retired（退场）复活为 active——请核实")
    old_att = str(old.get("attitude") or "").strip().lower()
    new_att = str(new.get("attitude") or "").strip().lower()
    if (old_att, new_att) in _ATTITUDE_BIG_FLIPS:
        rep["warnings"].append(f"🔗【立场大翻转】实体「{name}」态度由 {old_att} 转为 {new_att}——若系剧情重大转折请忽略")
    old_charges, new_charges = old.get("charges"), new.get("charges")
    if (isinstance(old_charges, int) and not isinstance(old_charges, bool)
            and isinstance(new_charges, int) and not isinstance(new_charges, bool)
            and new_charges > old_charges):
        rep["warnings"].append(f"🎒 实体「{name}」充能回升（{old_charges} → {new_charges}）——若为正常补充/升级请忽略")


def _index_by(items: list[dict], key: str) -> dict:
    return {str(it.get(key, "")): it for it in items}


def _scan_nulls(node, path: str, out: list[str]) -> None:
    """递归收集显式 null 位置（持久层闸门拒绝 null，提案入口给出明确报错，QA P2-8）。"""
    if node is None:
        out.append(f"{path}: 不接受显式 null（键要么缺席要么为合法值）")
    elif isinstance(node, dict):
        for k, v in node.items():
            _scan_nulls(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_nulls(v, f"{path}[{i}]", out)


def validate_proposal(proposal, expected_chapter: str | None = None) -> tuple[list[str], dict]:
    errors: list[str] = []
    plan: dict[str, str] = {}
    if not isinstance(proposal, dict):
        return ["提案必须是 JSON 对象"], plan

    errors.extend(validator.validate(proposal, _schema("proposal")))
    pydantic_errors = models.validate_with_model("proposal", proposal)
    for pe in pydantic_errors:
        if pe not in errors:
            errors.append(pe)
    for k in proposal:
        if k.startswith("candidate_"):
            errors.append(f"{k}: 候选字段仅供复核，禁止直接进入合并")
    null_hits: list[str] = []
    for sec in ("current", "entities", "lines", "timeline", "ledger", "synopsis"):
        if proposal.get(sec) is not None:
            _scan_nulls(proposal[sec], sec, null_hits)
    errors.extend(null_hits[:10])
    if len(null_hits) > 10:
        errors.append(f"…另有 {len(null_hits) - 10} 处显式 null 未列出")
    if proposal.get("_draft"):
        errors.append("这是草稿提案（_draft:true）：复核补全后另存为正式提案再 sync")
    if not proposal.get("operation_id"):
        errors.append("正式提案必须提供 operation_id（幂等身份）")

    chapter = proposal.get("chapter")
    if expected_chapter is not None and _canonical_ch(chapter) != _canonical_ch(expected_chapter):
        errors.append(f"chapter 与同步目标不一致: {chapter} != {expected_chapter}")

    def _plan(sec, n):
        plan[sec] = f"合并 {sec} × {n}"

    cur = proposal.get("current")
    if isinstance(cur, dict):
        _plan("current", len(cur))
        for k in cur:
            if k not in _schema("current")["properties"]:
                errors.append(f"current 含未知字段: {k}")
        pcs = cur.get("present_characters")
        if pcs is not None and (not isinstance(pcs, list) or any(not isinstance(x, str) for x in pcs)):
            errors.append("current.present_characters 必须是字符串数组")
        if "active_pressures" in cur:
            ap = cur["active_pressures"]
            if not isinstance(ap, list) or any(not isinstance(x, str) for x in ap):
                errors.append("current.active_pressures 必须是字符串数组")
        if "aftershock" in cur and not isinstance(cur["aftershock"], str):
            errors.append("current.aftershock 必须是字符串")

    ents = proposal.get("entities")
    if isinstance(ents, list):
        _plan("entities", len(ents))
        allowed_entity_keys = {"action", "name", "type", "card", "summary", "status", "aliases",
                               "holder", "location", "condition", "quote",
                               "realm", "faction", "life_status", "attitude", "charges", "max_charges",
                               "dossier", "scope", "golden_quote", "relations"}
        for i, e in enumerate(ents):
            if not isinstance(e, dict):
                errors.append(f"entities[{i}] 必须为对象")
                continue
            for k in e:
                if k not in allowed_entity_keys:
                    errors.append(f"entities[{i}] 含未知字段: {k}")
            if e.get("action", "upsert") not in ("upsert", "register", "retire"):
                errors.append(f"entities[{i}].action 必须为 upsert/register/retire（register 为 upsert 别名）")
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
            if "charges" in e and "max_charges" in e:
                try:
                    if int(e["charges"]) > int(e["max_charges"]):
                        errors.append(f"entities[{i}].charges({e['charges']}) 不能大于 max_charges({e['max_charges']})")
                except Exception:
                    pass
            if "type" in e and e["type"] not in _ENTITY_TYPES:
                errors.append(f"entities[{i}].type 非法: {e['type']!r}（合法：{'/'.join(sorted(_ENTITY_TYPES))}）")
            for f in ("card", "summary", "holder", "location", "condition", "realm", "faction", "quote", "dossier", "scope", "golden_quote"):
                if f in e and not isinstance(e[f], str):
                    errors.append(f"entities[{i}].{f} 必须为字符串")
            if "aliases" in e:
                if not isinstance(e["aliases"], list):
                    errors.append(f"entities[{i}].aliases 必须为字符串数组（收到 {type(e['aliases']).__name__}）")
                elif any(not isinstance(a, str) for a in e["aliases"]):
                    errors.append(f"entities[{i}].aliases 的元素必须为字符串")
            if "relations" in e:
                if not isinstance(e["relations"], list):
                    errors.append(f"entities[{i}].relations 必须为数组（收到 {type(e['relations']).__name__}）")
                else:
                    for r_idx, rel in enumerate(e["relations"]):
                        if not isinstance(rel, dict):
                            errors.append(f"entities[{i}].relations[{r_idx}] 必须为对象")
                            continue
                        if not rel.get("target") or not isinstance(rel["target"], str):
                            errors.append(f"entities[{i}].relations[{r_idx}].target 必填且为字符串")
                        if not rel.get("type") or not isinstance(rel["type"], str):
                            errors.append(f"entities[{i}].relations[{r_idx}].type 必填且为字符串")
                        if "desc" in rel and not isinstance(rel["desc"], str):
                            errors.append(f"entities[{i}].relations[{r_idx}].desc 必须为字符串")

    lines = proposal.get("lines")
    if isinstance(lines, list):
        _plan("lines", len(lines))
        for i, g in enumerate(lines):
            if not isinstance(g, dict):
                errors.append(f"lines[{i}] 必须为对象")
                continue
            kind = g.get("kind")
            # 加固：kind 可能是 LLM 产出的未哈希类型（dict/list），直接 .get 会 TypeError 崩闸门
            spec = _LINE_KIND_SPEC.get(kind) if isinstance(kind, str) else None
            if spec is None:
                errors.append(f"lines[{i}].kind 必须为 foreshadow/misunderstanding/knowledge")
                continue
            action = g.get("action", "plant")
            if kind == "knowledge":
                if action not in ("plant", "update", "resolve"):
                    errors.append(f"lines[{i}].action 非法: {action}（knowledge 支持 plant/update/resolve）")
                    continue
            elif action not in ("plant", "update", "remind", "resolve", "escalate"):
                errors.append(f"lines[{i}].action 非法: {action}")
                continue
            if action == "escalate" and kind != "misunderstanding":
                errors.append(f"lines[{i}]: escalate 只适用于 misunderstanding")
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
                if "holders" in g:
                    if kind != "knowledge":
                        errors.append(f"lines[{i}].holders 仅 knowledge（秘密线）支持（知情圈）")
                    elif (not isinstance(g["holders"], list)
                          or any(not isinstance(h, str) or not h.strip() for h in g["holders"])):
                        errors.append(f"lines[{i}].holders 必须为实体名/别名 字符串数组")
                if "target_ch" not in g:
                    errors.append(f"lines[{i}]（plant {kind}）必须提供 target_ch"
                                  f"（int 章号如 21 / ch_NNN 三位补零 / \"第N章\" / \"longline\"；"
                                  f"缺省会静默占用长线配额，故强制显式声明）")
                _, terr = _norm_target(g.get("target_ch"))
                if terr:
                    errors.append(f"lines[{i}]: {terr}")
                pc = g.get("plant_ch")
                if pc is not None and (not isinstance(pc, int) or isinstance(pc, bool) or pc < 1):
                    errors.append(f"lines[{i}].plant_ch 必须为正整数")
                if "requires" in g:
                    if not isinstance(g["requires"], list):
                        errors.append(f"lines[{i}].requires 必须为字符串数组")
                    elif any(not isinstance(r, str) for r in g["requires"]):
                        errors.append(f"lines[{i}].requires 的元素必须为字符串")
            else:
                if "target_ch" in g:
                    _, terr = _norm_target(g["target_ch"])
                    if terr:
                        errors.append(f"lines[{i}]: {terr}")
                # 非 plant 动作同样拒绝未知字段（防拼错字段静默 no-op，审计链缺失）
                if action == "escalate":
                    allowed_nonplant = base_keys | {"requires", "level", "content", "truth",
                                                    "parties", "target_ch"}
                elif action in ("resolve", "remind"):
                    # target_ch 可选携带：回响/回收时顺延或改期回收计划（QA E2E 实测 Reader 需要此语义）
                    allowed_nonplant = base_keys | {"requires", "target_ch"}
                else:  # update：沿用 update_fields 白名单
                    allowed_nonplant = base_keys | set(spec["update_fields"])
                for k in g:
                    if k not in allowed_nonplant:
                        errors.append(f"lines[{i}] 含未知字段: {k}")
                if "requires" in g:
                    if not isinstance(g["requires"], list):
                        errors.append(f"lines[{i}].requires 必须为字符串数组")
                    elif any(not isinstance(r, str) for r in g["requires"]):
                        errors.append(f"lines[{i}].requires 的元素必须为字符串")
                if "holders" in g:
                    if kind != "knowledge":
                        errors.append(f"lines[{i}].holders 仅 knowledge（秘密线）支持（知情圈）")
                    elif (not isinstance(g["holders"], list)
                          or any(not isinstance(h, str) or not h.strip() for h in g["holders"])):
                        errors.append(f"lines[{i}].holders 必须为实体名/别名 字符串数组")
                if not g.get("id"):
                    errors.append(f"lines[{i}]（{action}）必须提供 id")
                if action == "remind" and kind != "foreshadow":
                    errors.append(f"lines[{i}]: remind 只适用于 foreshadow")
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
            if (not isinstance(ev.get("time"), str) or not ev["time"].strip()
                    or not isinstance(ev.get("event"), str) or not ev["event"].strip()):
                errors.append(f"timeline.events[{i}] 必须含非空字符串 time 与 event")
            for k in ev:
                if k not in ("time", "event", "replace", "quote"):
                    errors.append(f"timeline.events[{i}] 含未知字段: {k}")
            if "replace" in ev and (not isinstance(ev["replace"], str) or not ev["replace"].strip()):
                errors.append(f"timeline.events[{i}].replace 必须为非空字符串")
            if "quote" in ev and (not isinstance(ev["quote"], str) or not ev["quote"].strip()):
                errors.append(f"timeline.events[{i}].quote 必须为非空字符串")
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

    led = proposal.get("ledger")
    if isinstance(led, dict):
        txs = led.get("transactions", []) or []
        _plan("ledger", len(txs))
        for k in led:
            if k not in ("pools", "transactions"):
                errors.append(f"ledger 含未知字段: {k}")
        pools = led.get("pools")
        if pools is not None:
            if not isinstance(pools, dict):
                errors.append("ledger.pools 必须为对象")
            else:
                for pid, p in pools.items():
                    if not isinstance(p, dict):
                        errors.append(f"ledger.pools[{pid}] 必须为对象")
                        continue
                    if "current" in p:
                        errors.append(f"ledger.pools[{pid}].current 不接受声明（余额一律由流水重算）")
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
                errors.append(f"ledger.transactions[{i}].subject 必填")
            if "type" in t and t["type"] not in ("income", "expense", "opening_balance", "manual"):
                errors.append(f"ledger.transactions[{i}].type 必须 ∈ ['income', 'expense', 'opening_balance', 'manual']")
            delta = t.get("delta")
            if not isinstance(delta, int) or isinstance(delta, bool):
                errors.append(f"ledger.transactions[{i}].delta 必须为整数")
            else:
                ttype = t.get("type")
                if ttype == "income" and delta < 0:
                    errors.append(f"ledger.transactions[{i}]: type=income 但 delta={delta}")
                if ttype == "expense" and delta > 0:
                    errors.append(f"ledger.transactions[{i}]: type=expense 但 delta={delta}（支出必须为负数）")
            if t.get("chapter") is not None and not re.fullmatch(r"ch_\d{3,}", str(t["chapter"])):
                errors.append(f"ledger.transactions[{i}].chapter 须匹配 ch_NNN")
            for f in ("counterparty", "note", "quote"):
                if f in t and not isinstance(t[f], str):
                    errors.append(f"ledger.transactions[{i}].{f} 必须为字符串")

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
            if not isinstance(chapters, dict):
                errors.append("synopsis.chapters 必须为对象")
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
                            errors.append(f"synopsis.chapters[{c}] 含未知字段: {f}")
                    for f in ("title", "synopsis"):
                        if f in cp and not isinstance(cp[f], str):
                            errors.append(f"synopsis.chapters[{c}].{f} 必须为字符串")
    return errors, plan


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
                rep["warnings"].append("current.present_characters 为空数组，按未提供处理")
                continue
            state["present_characters"] = list(v)
        elif k == "loadout":
            if not isinstance(v, dict):
                rep["errors"].append("current.loadout 必须为对象")
                continue
            cur_ld = state.get("loadout") or {}
            cur_ld.update(v)
            state["loadout"] = cur_ld
        elif k == "active_pressures":
            if not isinstance(v, list):
                rep["errors"].append("current.active_pressures 必须为字符串数组")
                continue
            state["active_pressures"] = [str(x) for x in v if str(x).strip()]
        elif isinstance(v, str):
            if not v:
                rep["warnings"].append(f"current.{k} 为空字符串，按未提供处理")
                continue
            if k == "time":
                _warn_time_regression(state, v, rep)
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
                rep["errors"].append(f"retire 未登记实体「{name}」")
                continue
            ent["status"] = "retired"
            rep["updated"].append(f"🗂️ 实体退役：{name}")
            continue
        ent = idx.get(name)
        etype = e.get("type", "other")
        if etype not in valid_types:
            rep["errors"].append(f"实体「{name}」type 非法: {etype}")
            continue
        if "charges" in e and "max_charges" in e:
            try:
                if int(e["charges"]) > int(e["max_charges"]):
                    rep["errors"].append(f"实体「{name}」charges({e['charges']}) > max_charges({e['max_charges']})")
                    continue
            except Exception:
                pass
        elif ent is not None:
            try:
                if "charges" in e and ent.get("max_charges") is not None:
                    if int(e["charges"]) > int(ent["max_charges"]):
                        rep["errors"].append(f"实体「{name}」charges({e['charges']}) > 既有 max_charges({ent['max_charges']})")
                        continue
                if "max_charges" in e and ent.get("charges") is not None:
                    if int(ent["charges"]) > int(e["max_charges"]):
                        rep["errors"].append(f"实体「{name}」既有 charges({ent['charges']}) > 新 max_charges({e['max_charges']})")
                        continue
            except Exception:
                pass
        if ent is not None:
            _guard_entity_transitions(name, ent, e, rep)
        if ent is None:
            ent = {"name": name, "type": etype, "aliases": [], "card": "", "summary": "", "status": "active"}
            state["entries"].append(ent)
            idx[name] = ent
        for f in ("type", "card", "summary", "holder", "location", "condition",
                  "realm", "faction", "life_status", "attitude", "charges", "max_charges", "dossier",
                  "scope", "golden_quote"):
            if f in e:
                ent[f] = e[f]
        if "status" in e:
            ent["status"] = e["status"]
        if "aliases" in e:
            ent["aliases"] = sorted(set(ent.get("aliases", [])) | {str(a) for a in e["aliases"]})
        if "relations" in e and isinstance(e["relations"], list):
            existing_rels = ent.setdefault("relations", [])
            for new_r in e["relations"]:
                tgt = new_r.get("target")
                found = next((r for r in existing_rels if r.get("target") == tgt), None)
                if found:
                    found.update(new_r)
                else:
                    existing_rels.append(new_r)
        rep["updated"].append(f"🗂️ 实体登记/更新：{name}")


def _same_line_content(kind: str, existing: dict, g: dict, ch_num: int) -> bool:
    """判断重复 plant 的传入内容与既有条目是否逐字段一致（幂等重放判定）。"""
    target, _ = _norm_target(g.get("target_ch"))
    if kind == "foreshadow":
        want = {"name": g["name"], "plant_ch": g.get("plant_ch") or ch_num, "target_ch": target,
                "weight": g.get("weight", 1), "plan": g.get("plan", ""),
                "requires": [str(r) for r in g.get("requires", []) if str(r).strip()]}
    elif kind == "misunderstanding":
        want = {"parties": g["parties"], "content": g["content"], "truth": g.get("truth", ""),
                "level": g.get("level", 1), "target_ch": target,
                "requires": [str(r) for r in g.get("requires", []) if str(r).strip()]}
    else:
        want = {"secret": g["secret"], "plant_ch": g.get("plant_ch") or ch_num, "target_ch": target,
                "weight": g.get("weight", 1), "note": g.get("note", ""),
                "requires": [str(r) for r in g.get("requires", []) if str(r).strip()],
                "holders": [str(h).strip() for h in g.get("holders", []) if str(h).strip()]}
    if kind == "knowledge":
        # 兼容 holders 引入前封存的旧条目（无该键按空知情圈处理）
        return (all(existing.get(k) == v for k, v in want.items() if k != "holders")
                and (existing.get("holders") or []) == want["holders"])
    return all(existing.get(k) == v for k, v in want.items())


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
                # 幂等重放保护：内容逐字段一致 = 崩溃/归档后重放，跳过而非拒收
                if _same_line_content(kind, idx[gid], g, ch_num):
                    rep["warnings"].append(f"{gid} 已存在且内容一致，按幂等跳过（重复 plant）")
                    continue
                rep["errors"].append(f"{gid} 已存在，重复 plant 拒绝")
                continue
            target, terr = _norm_target(g.get("target_ch"))
            if terr:
                rep["errors"].append(f"plant {gid}: {terr}")
                continue
            if kind == "foreshadow":
                open_act_count = sum(1 for item in arr if item.get("status") != "Resolved" and isinstance(item.get("target_ch"), int))
                open_long_count = sum(1 for item in arr if item.get("status") != "Resolved" and item.get("target_ch") == "longline")
                if target != "longline" and open_act_count >= 8:
                    rep["warnings"].append(f"卷内活动伏笔池已达上限（{open_act_count}/8），新伏笔 {gid} 已入库")
                if target == "longline" and open_long_count >= 5:
                    rep["warnings"].append(f"全书长线已达上限（{open_long_count}/5），新长线 {gid} 已入库")
                reqs = [str(r) for r in g.get("requires", []) if str(r).strip()]
                arr.append({"id": gid, "name": g["name"], "plant_ch": g.get("plant_ch") or ch_num,
                            "status": "Planted", "target_ch": target, "weight": g.get("weight", 1),
                            "plan": g.get("plan", ""), "requires": reqs})
                rep["updated"].append(f"🕸️ 埋设伏笔 {gid}《{g['name']}》→ target {target}")
            elif kind == "misunderstanding":
                reqs = [str(r) for r in g.get("requires", []) if str(r).strip()]
                arr.append({"id": gid, "parties": g["parties"], "content": g["content"],
                            "truth": g.get("truth", ""), "level": g.get("level", 1),
                            "target_ch": target, "status": "Active", "requires": reqs})
                rep["updated"].append(f"🎭 新误会 {gid}：{g['content'][:30]}")
            else:
                reqs = [str(r) for r in g.get("requires", []) if str(r).strip()]
                holders = [str(h).strip() for h in g.get("holders", []) if str(h).strip()]
                entry = {"id": gid, "secret": g["secret"], "plant_ch": g.get("plant_ch") or ch_num,
                         "status": "Concealed", "target_ch": target,
                         "weight": g.get("weight", 1), "note": g.get("note", ""), "requires": reqs}
                if holders:
                    entry["holders"] = holders
                arr.append(entry)
                holder_note = f"｜知情圈：{'、'.join(holders)}" if holders else ""
                rep["updated"].append(f"🔒 知识线登记 {gid}《{g['secret'][:24]}》→ 计划揭示 {target}{holder_note}")
            idx[gid] = arr[-1]
            continue
        gid = g.get("id")
        ent = idx.get(gid)
        if ent is None:
            rep["errors"].append(f"{action} 目标 {gid} 不存在")
            continue
        if action == "resolve":
            ent["status"] = spec["resolved"]
            if "target_ch" in g:
                tgt, terr = _norm_target(g["target_ch"])
                if terr:
                    rep["errors"].append(f"resolve {gid}: {terr}")
                    continue
                ent["target_ch"] = tgt
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
            if "target_ch" in g:
                tgt, terr = _norm_target(g["target_ch"])
                if terr:
                    rep["errors"].append(f"remind {gid}: {terr}")
                    continue
                if ent.get("target_ch") != tgt:
                    rep["updated"].append(f"🗓️ {gid} 回收计划改期 → {tgt}")
                ent["target_ch"] = tgt
            rep["updated"].append(f"🔔 {gid} 已回唤")
        elif action == "escalate":
            ent["status"] = "Escalated"
            old_level = ent.get("level") if isinstance(ent.get("level"), int) else None
            if "level" in g and isinstance(g["level"], int):
                ent["level"] = g["level"]
                if old_level is not None and g["level"] < old_level:
                    rep["warnings"].append(
                        f"⚡ {gid} escalate 将强度由 {old_level} 降为 {g['level']}（「激化」语义反向）——请核实")
            elif isinstance(ent.get("level"), int):
                ent["level"] += 1
            if "content" in g and isinstance(g["content"], str):
                ent["content"] = g["content"]
            if "target_ch" in g:
                tgt, terr = _norm_target(g["target_ch"])
                if terr:
                    rep["errors"].append(f"escalate {gid}: {terr}")
                    continue
                ent["target_ch"] = tgt
            rep["updated"].append(f"⚡ {gid} 误会激化（强度等级 {ent.get('level', 1)}）")
        else:
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
                    old_status = ent.get("status")
                    if old_status == spec["resolved"] and v != spec["resolved"]:
                        rep["warnings"].append(
                            f"🔁 {gid} 状态由已闭环 {old_status} 回退为 {v}——若非修订误记请核实")
                    if kind == "knowledge" and old_status == "Revealed" and v == "Concealed":
                        rep["warnings"].append(f"🔁 {gid} 已揭示的知识线被改回保密（Revealed→Concealed）——请核实")
                if k == "requires":
                    v = [str(r) for r in v if str(r).strip()]
                ent[k] = v
            rep["updated"].append(f"🔁 {gid} 已更新")


def _merge_timeline(state: dict, patch: dict, ch: str, rep: dict) -> None:
    existing = {(e.get("time", ""), e.get("event", "")) for e in state["events"]}
    added = replaced = skipped = 0
    for ev in patch.get("events", []) or []:
        key = (ev.get("time", ""), ev.get("event", ""))
        new_text = ev.get("replace")
        if new_text is not None:
            target = next((e for e in state["events"]
                           if (e.get("time", ""), e.get("event", "")) == key), None)
            if target is None:
                rep["errors"].append(f"timeline 事件修订未命中: {key[0]}｜{str(key[1])[:30]}…")
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
            ent["strategy"] = a["strategy"]
            hist = ent.setdefault("strategy_history", [])
            entry = {"chapter": ch, "strategy": a["strategy"]}
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


def _tx_replay_key(t: dict, ch: str) -> tuple:
    """流水内容指纹：崩溃重放/归档重提的同一笔交易判定依据。"""
    try:
        delta = int(t["delta"])
    except (ValueError, TypeError):
        return ("__invalid__",)
    return (str(t.get("chapter") or ch), str(t.get("pool")), delta,
            str(t.get("type") or ("income" if delta >= 0 else "expense")),
            str(t.get("subject", "")), str(t.get("counterparty") or ""), str(t.get("note") or ""))


def _merge_ledger(state: dict, patch: dict, ch: str, rep: dict) -> None:
    pools = state["pools"]
    for pid, p in (patch.get("pools") or {}).items():
        if pid in pools:
            for f in ("name", "unit"):
                if f in p:
                    pools[pid][f] = p[f]
            if "initial" in p:
                try:
                    if int(p["initial"]) != int(pools[pid].get("initial", 0)):
                        rep["errors"].append(f"资源池 '{pid}' 是既有池，禁止修改 initial")
                        return
                except (ValueError, TypeError):
                    rep["errors"].append(f"资源池 '{pid}' initial 必须为整数（收到 {p['initial']!r}）")
                    return
            if any(f in p for f in ("name", "unit")):
                rep["warnings"].append(f"资源池 {pid} 声明已修订")
        else:
            try:
                init_val = int(p.get("initial", 0))
            except (ValueError, TypeError):
                rep["errors"].append(f"新资源池 {pid} initial 必须为整数（收到 {p.get('initial')!r}）")
                return
            pools[pid] = {"name": p.get("name", pid), "unit": p.get("unit", ""),
                          "initial": init_val, "current": init_val}
            rep["updated"].append(f"💱 新资源池 {pid}（{p.get('name', pid)}）")

    running = {}
    for k, v in pools.items():
        try:
            running[k] = int(v.get("initial", 0))
        except (ValueError, TypeError):
            rep["errors"].append(f"资源池 {k} initial 非整数：{v.get('initial')!r}")
            return

    for i, t in enumerate(state["transactions"]):
        pool = t.get("pool")
        if pool not in running:
            rep["errors"].append(f"既有流水 #{i + 1} 引用未声明池 '{pool}'")
            return
        try:
            delta = int(t.get("delta", 0))
        except (ValueError, TypeError):
            rep["errors"].append(f"既有流水 #{i + 1} delta 非整数：{t.get('delta')!r}")
            return
        running[pool] += delta
        rec = t.get("balance_after")
        if rec is not None:
            try:
                if int(rec) != running[pool]:
                    rep["errors"].append(f"既有流水 #{i + 1} balance_after={rec} 与重算值 {running[pool]} 不符")
                    return
            except (ValueError, TypeError):
                rep["errors"].append(f"既有流水 #{i + 1} balance_after 非整数：{rec!r}")
                return

    # 幂等重放保护：与既有流水逐字段一致的重复交易视为崩溃重放，跳过而非双计。
    # 键含 chapter，跨章的同内容交易不受影响；同章同内容若确属两笔独立交易，
    # 请在 subject/note 中加入区分信息。
    replay_budget: dict[tuple, int] = {}
    for t in state["transactions"]:
        k = _tx_replay_key(t, ch)
        replay_budget[k] = replay_budget.get(k, 0) + 1
    replay_used: dict[tuple, int] = {}

    for t in patch.get("transactions", []) or []:
        pool = t["pool"]
        if pool not in pools:
            rep["errors"].append(f"流水引用未声明资源池 '{pool}'")
            continue
        try:
            delta = int(t["delta"])
        except (ValueError, TypeError):
            rep["errors"].append(f"流水 delta 非整数：{t.get('delta')!r}")
            continue
        k = _tx_replay_key(t, ch)
        if k in replay_budget and replay_used.get(k, 0) < replay_budget[k]:
            replay_used[k] = replay_used.get(k, 0) + 1
            rep["warnings"].append(
                f"♻️ 疑似重放流水已跳过（幂等重放保护）：{str(t.get('subject', ''))[:24]}")
            continue
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
            rep["warnings"].append(f"⚠️ {ch} 已有人工梗概，本次提交覆盖之")
        chs[ch] = {"num": _chapter_num(ch) or 0,
                   "title": (patch.get("title") or prev.get("title", "")),
                   "synopsis": patch["text"], "source": "manual"}
        rep["updated"].append(f"📖 章节梗概已登记（{ch}）")
    for c, cp in (patch.get("chapters") or {}).items():
        chs = state.setdefault("chapters", {})
        ent = chs.get(c)
        if ent is None:
            # QA P21：跨章修订通道只认已登记章——指向未注册章整案报错，
            # 不再静默 no-op / 悄悄建占位（修订意图丢失无从追溯）
            rep["errors"].append(
                f"synopsis.chapters.{c} 无既有梗概（跨章修订通道仅支持修订已登记章节；"
                f"正常登记请随该章 sync 走 synopsis.text，待其封存后再用修订通道）")
            continue
        for f in ("title", "synopsis"):
            if f in cp:
                v = cp[f]
                if not v.strip():
                    rep["warnings"].append(f"synopsis.chapters.{c}.{f} 为空白字符串，按未提供处理")
                    continue
                ent[f] = v
                rep["updated"].append(f"📖 {c} {f} 已修订 →「{v[:24]}…」")


def _merge_proposal_into(data: dict, proposal: dict, ch, ch_num, rep: dict) -> None:
    if proposal.get("current"):
        _merge_current(data["current"], proposal["current"], rep)
    if proposal.get("entities"):
        _merge_entities(data["entities"], proposal["entities"], rep)
        # QA P22：退役与同案在场冲突 → 自动从 present 剔除并醒目提示
        # （闪回/补叙章确需在场：请先在同案把该实体 status 改回 active 再声明 present）
        pcs = data["current"].get("present_characters")
        if pcs:
            # 两种退役写法都算：action=retire，或 upsert 携带 status=retired（README 文档口径）
            retired = {str(e.get("name", "")).strip() for e in proposal["entities"]
                       if isinstance(e, dict) and str(e.get("name", "")).strip()
                       and (e.get("action") == "retire" or e.get("status") == "retired")}
            dropped = [n for n in pcs if str(n).strip() in retired]
            if dropped:
                data["current"]["present_characters"] = [n for n in pcs if str(n).strip() not in retired]
                rep["warnings"].append(
                    f"🗂️ 实体{'、'.join(dropped)}本提案内退役，已自动从 present_characters 剔除"
                    f"（「已退役但在场」状态矛盾不再入库；闪回章请先 status=active 再声明在场）")
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
    common.debug(f"gate=validate_proposal: {len(errors)} 错误"
                 + (f"（{errors[0]}）" if errors else ""))
    rep["plan"] = plan
    if errors:
        rep["errors"] = errors
        return rep

    ch = _canonical_ch(proposal["chapter"])
    op = proposal["operation_id"]
    ch_num = _chapter_num(ch)
    proposal_hash = common.canonical_json_hash({k: v for k, v in proposal.items() if k != "operation_id"})
    try:
        marker = _load_marker(book)
    except (ValueError, OSError) as exc:
        rep["errors"].append(f"幂等登记簿损坏，拒绝合并: {exc}")
        return rep
    if op in marker:
        common.debug(f"gate=idempotency: op={op} 命中登记簿（hash={proposal_hash[:16]}… "
                     f"登记 {marker[op][:16]}…）→ {'内容一致跳过' if marker[op] == proposal_hash else '内容冲突拒收'}")
        if marker[op] != proposal_hash:
            rep["errors"].append(f"operation_id {op} 已用于不同内容，拒绝复用")
        else:
            rep["warnings"].append(f"operation_id {op} 已应用过，跳过")
            rep["duplicate"] = True
        return rep
    if proposal_hash in marker.values():
        common.debug(f"gate=idempotency: 内容哈希 {proposal_hash[:16]}… 已应用过（不同 op）→ 跳过")
        rep["warnings"].append("相同内容提案已应用过，跳过")
        rep["duplicate"] = True
        return rep
    common.debug(f"gate=idempotency: 通过（op={op} hash={proposal_hash[:16]}… 未登记）")

    try:
        data = {key: copy.deepcopy(load_state(book, key)) for key in STATE_KEYS}
    except ValueError as exc:
        rep["errors"].append(f"状态 SSOT 不可用，拒绝合并: {exc}")
        return rep
    before_hash = {key: common.canonical_json_hash(data[key]) for key in STATE_KEYS}

    _merge_proposal_into(data, proposal, ch, ch_num, rep)
    common.debug(f"gate=merge: updated={len(rep['updated'])} warnings={len(rep['warnings'])} "
                 f"errors={len(rep['errors'])}"
                 + (f"（{rep['errors'][0]}）" if rep["errors"] else ""))
    if rep["errors"]:
        rep["updated"] = []
        rep["warnings"] = []
        if dry_run:
            rep["dry_run"] = True
        return rep

    verify_errors = verify_data(data)
    common.debug(f"gate=verify_data（写闸门，含前置因果闭环保）: {len(verify_errors)} 错误"
                 + (f"（{verify_errors[0]}）" if verify_errors else ""))
    if verify_errors:
        rep["errors"].extend(verify_errors)
        rep["updated"] = []
        rep["warnings"] = []
        if dry_run:
            rep["dry_run"] = True
        return rep

    rep["changed"] = any(common.canonical_json_hash(data[key]) != before_hash[key]
                         for key in STATE_KEYS)

    if dry_run:
        rep["dry_run"] = True
        return rep

    sd = state_dir(book)
    paths = {key: sd / f"{key}.json" for key in STATE_KEYS}
    marker_path = sd / MARKER_NAME
    backup: dict[Path, bytes] = {}
    existed_marker = marker_path.exists()
    for p in list(paths.values()) + ([marker_path] if existed_marker else []):
        if p.exists():
            try:
                backup[p] = p.read_bytes()
            except OSError:
                pass
    newly_created: list[Path] = [] if existed_marker else [marker_path]

    try:
        for key in STATE_KEYS:
            save_state(book, key, data[key])
        marker[op] = proposal_hash
        common.dump_json(marker_path, marker)
    except Exception as exc:
        # 回滚自身走原子写（tmp+replace），且失败必须上抛——静默吞掉会造成
        # 「宣称已回滚、现场却撕裂」的假安全（QA P2-11）
        restore_fail: list[str] = []
        for p, content in backup.items():
            try:
                common.atomic_write_text(p, content.decode("utf-8"))
            except (OSError, UnicodeDecodeError) as rerr:
                restore_fail.append(f"{p.name}: {rerr}")
        for p in newly_created:
            if p not in backup:
                with contextlib.suppress(OSError):
                    p.unlink()
        rep["errors"].append(f"落盘异常: {exc}")
        if restore_fail:
            rep["errors"].append("回滚自身失败，现场可能处于新旧混合的撕裂态，请检查 state/ 后从快照恢复: "
                                 + "; ".join(restore_fail))
            rep["rollback"] = False
            raise ValueError("; ".join(rep["errors"])) from exc
        rep["errors"].append("已整体回滚")
        rep["rollback"] = True
    return rep


_CH_FILE_RE = re.compile(r"ch_\d{3,}(\.\d+)?\.json")


def _gather(inbox: Path) -> list[Path]:
    if not inbox.exists():
        return []
    out = []
    for p in inbox.glob("*.json"):
        if p.is_symlink():
            continue
        if p.name.endswith(NO_MERGE_SUFFIXES):
            continue
        if not _CH_FILE_RE.fullmatch(p.name):
            continue  # 非提案命名的异物不参与合并（QA P1-5：异物不再阻断 verify+snapshot）
        out.append(p)
    return sorted(out)


def _stray_files(inbox: Path) -> list[str]:
    """收件箱里不像提案的 JSON（警告用，不合并、不归档、不阻断）。"""
    if not inbox.exists():
        return []
    out = []
    for p in sorted(inbox.glob("*.json")):
        if p.is_symlink() or p.name.endswith(NO_MERGE_SUFFIXES):
            continue
        if not _CH_FILE_RE.fullmatch(p.name):
            out.append(p.name)
    return out


def _write_rejection_sidecar(archived: str, errors: list[str],
                             chapter: str | None = None, operation_id: str | None = None) -> None:
    """QA P14：拒收提案归档时附带拒收原因侧车（_<名>.rejection.json）。

    侧车文件名以「_」前缀命名，不匹配 ch_*.json 的合并/捡回正则（_CH_FILE_RE 与
    _failed_candidates 的 glob），永不参与合并；「按报错逐条修复后重跑 sync」的自愈
    流程不再依赖当场 stdout 日志。
    """
    try:
        p = Path(archived)
        side = p.with_name(f"_{p.stem}.rejection.json")
        common.dump_json(side, {
            "chapter": chapter,
            "operation_id": operation_id,
            "reasons": errors,
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "note": "本文件仅记录拒收原因（不是提案）；按 reasons 逐条修复提案后重跑 sync 即可。",
        })
    except (OSError, TypeError, ValueError):
        pass  # 侧车是审计增强，失败不阻断归档主流程


def _archive(pf: Path, dst: Path) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    # 加固：pf 必须在 inbox 内且非 symlink
    if pf.is_symlink():
        raise ValueError(f"提案文件 {pf.name} 为符号链接，拒绝归档")
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
    return _gather(inbox_dir(book))


def apply_inbox(book: Path, expect_chapter: str | None = None, dry_run: bool = False) -> dict:
    inbox = inbox_dir(book)
    overall = {"applied": 0, "failed": 0, "duplicates": 0, "skipped": 0, "results": [], "picked_up": False}

    def _failed_candidates() -> list[Path]:
        fdir = inbox / "failed"
        if not expect_chapter or not fdir.is_dir():
            return []
        cands: list[Path] = []
        exact = fdir / f"{expect_chapter}.json"
        if exact.is_file() and not exact.is_symlink() and not exact.name.endswith(NO_MERGE_SUFFIXES):
            cands.append(exact)
        for p in fdir.glob(f"{expect_chapter}.*.json"):
            if p.is_symlink():
                continue
            if p.name.endswith(NO_MERGE_SUFFIXES):
                continue
            if common.chapter_number_from_name(p.name) == common.chapter_token_to_num(expect_chapter):
                if p.name.startswith(expect_chapter + "."):
                    cands.append(p)
        cands = sorted(set(cands), key=lambda p: p.stat().st_mtime)
        return cands

    with common.file_lock(state_dir(book), name=".state.lock", timeout=30.0):
        files = _gather(inbox)
        if expect_chapter and not (inbox / f"{expect_chapter}.json").exists():
            cands = _failed_candidates()
            if cands and not dry_run:
                c = cands[-1]
                dest = inbox / c.name
                if not dest.exists():
                    c.rename(dest)
                    overall["picked_up"] = True
                    files = _gather(inbox)
            elif cands:
                files = [cands[-1]] + files
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
                    _write_rejection_sidecar(result["archived_to"], result["errors"])
                fn = common.chapter_number_from_name(pf.name)
                tn = common.chapter_token_to_num(expect_chapter) if expect_chapter else None
                if expect_chapter is None or fn is None or fn == tn:
                    break
                result["note"] = "非目标章提案，已归档 failed/ 并继续"
                continue
            ch = proposal.get("chapter") if isinstance(proposal, dict) else None
            if expect_chapter is not None and ch != expect_chapter:
                result["skipped"] = f"提案章节 {ch} ≠ 同步目标 {expect_chapter}"
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
                    _write_rejection_sidecar(rep["archived_to"], rep["errors"],
                                              chapter=ch if isinstance(ch, str) else None,
                                              operation_id=str(proposal.get("operation_id"))
                                              if isinstance(proposal, dict) and proposal.get("operation_id") else None)
                break
            if rep.get("duplicate"):
                overall["duplicates"] += 1
            elif rep.get("changed"):
                overall["applied"] += 1
            else:
                overall["skipped"] += 1
                rep["noop"] = True
                rep["warnings"].append("提案合并后无任何实际变更（no-op）")
            if not dry_run:
                rep["archived_to"] = str(_archive(pf, inbox / "processed"))
    strays = _stray_files(inbox)
    if strays:
        overall["stray_files"] = strays
        overall["results"].append({
            "file": ", ".join(strays),
            "note": "收件箱存在非提案命名的 JSON，已忽略（不合并、不归档、不阻断封存）；如非异物请按 ch_XXX.json 命名",
        })
    return overall


def _prereq_errors(lines: dict) -> list[str]:
    """前置因果闭环保（QA P20：从「仅 check 可见的状态级错误」提升为合并时写闸门）。

    对合并后的 lines 数据构建「线 → requires」图，查两类因果违规：
    - 循环前置依赖（prerequisite_cycle 同语义）
    - 本线已闭环而前置依赖未达成（prerequisite_unmet 同语义）
    返回错误信息列表（空 = 通过）；未知前置 ID 不在此报错（check 层降级 prerequisite_missing 警告）。
    """
    errors: list[str] = []
    resolved_status = {"foreshadows": "Resolved", "misunderstandings": "Resolved", "knowledge": "Revealed"}
    graph: dict[str, dict] = {}
    for arr_key, rstatus in resolved_status.items():
        for item in lines.get(arr_key, []) or []:
            lid = str(item.get("id") or "")
            if not lid:
                continue
            graph[lid] = {"status": str(item.get("status", "")), "resolved": rstatus,
                          "requires": [str(r) for r in (item.get("requires") or [])]}
    for lid, info in graph.items():
        is_resolved = info["status"].lower() == info["resolved"].lower()
        for req_id in info["requires"]:
            req = graph.get(req_id)
            if req is None:
                continue
            if is_resolved and req["status"].lower() != req["resolved"].lower():
                errors.append(f"前置因果冲突：线索 {lid} 已标记完成({info['status']})，"
                              f"但其前置依赖 {req_id} 仍未完成({req['status']})——"
                              f"请将当章 action 改为 remind，或先推进前置线索 {req_id}")
    # 循环依赖检测（迭代式 DFS 三色法，与 checks.run_checks 同语义；报首个成环节点）
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {lid: WHITE for lid in graph}
    found_cycle = None
    for root in graph:
        if found_cycle or color[root] != WHITE:
            continue
        color[root] = GRAY
        stack = [(root, iter(graph[root]["requires"]))]
        while stack:
            node, it = stack[-1]
            advanced = False
            for neighbor in it:
                if neighbor not in graph:
                    continue
                if color[neighbor] == GRAY:
                    found_cycle = neighbor
                    break
                if color[neighbor] == WHITE:
                    color[neighbor] = GRAY
                    stack.append((neighbor, iter(graph[neighbor]["requires"])))
                    advanced = True
                    break
            if found_cycle:
                break
            if not advanced:
                color[node] = BLACK
                stack.pop()
    if found_cycle:
        errors.append(f"前置因果冲突：线索 {found_cycle} 存在循环前置依赖（requires 闭环）——请解除闭环后重提")
    return errors


def verify_data(data: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    for sec in ("current", "entities", "lines", "timeline", "ledger"):
        if sec in data and isinstance(data[sec], dict):
            p_errors = models.validate_with_model(sec, data[sec], prefix=sec)
            for pe in p_errors:
                if pe not in errors:
                    errors.append(pe)

    # QA P20：前置因果闸门并入写闸门——sync 合并时即拦截闭环/未决前置，
    # 不再等独立 check 才暴露（verify_state 的 sync「状态体检」同源覆盖）
    if isinstance(data.get("lines"), dict):
        errors.extend(_prereq_errors(data["lines"]))

    led = data["ledger"]
    running = {}
    for k, v in led.get("pools", {}).items():
        try:
            running[k] = int(v.get("initial", 0))
        except (ValueError, TypeError):
            errors.append(f"资源池 {k} initial 非整数：{v.get('initial')!r}")
            continue
    for i, t in enumerate(led.get("transactions", []), 1):
        pool = t.get("pool")
        if pool not in running:
            errors.append(f"流水 #{i} 引用未声明池 '{pool}'")
            continue
        try:
            delta = int(t.get("delta", 0))
        except (ValueError, TypeError):
            errors.append(f"流水 #{i} delta 非整数：{t.get('delta')!r}")
            continue
        running[pool] += delta
        if t.get("balance_after") is not None:
            try:
                if int(t["balance_after"]) != running[pool]:
                    errors.append(f"流水 #{i} balance_after={t['balance_after']} ≠ 重算 {running[pool]}")
            except (ValueError, TypeError):
                errors.append(f"流水 #{i} balance_after 非整数：{t['balance_after']!r}")
    for k, v in led.get("pools", {}).items():
        try:
            if int(v.get("current", 0)) != running.get(k, 0):
                errors.append(f"资源池 {k} 声明余额 {v.get('current')} ≠ 流水累计 {running.get(k, 0)}")
        except (ValueError, TypeError):
            errors.append(f"资源池 {k} current 非整数：{v.get('current')!r}")

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

    known = set(names)
    deceased_names = set()
    for e in data["entities"].get("entries", []):
        known.update(str(a) for a in e.get("aliases", []) if a)
        if e.get("life_status") == "deceased":
            deceased_names.add(e["name"])
            deceased_names.update(str(a) for a in e.get("aliases", []) if a)
    for name in data["current"].get("present_characters", []):
        if str(name).strip() and str(name) not in known:
            errors.append(f"current.present_characters 引用未登记实体「{name}」")
        elif str(name) in deceased_names:
            errors.append(f"current.present_characters 引用已离世实体「{name}」")

    for e in data["entities"].get("entries", []):
        holder = str(e.get("holder", "")).strip()
        if holder and holder not in known:
            errors.append(f"实体「{e.get('name','')}」的 holder「{holder}」未登记")
        if holder and holder in deceased_names:
            errors.append(f"实体「{e.get('name','')}」的 holder「{holder}」已离世——持有关系悬空")
        try:
            if e.get("charges") is not None and e.get("max_charges") is not None:
                if int(e["charges"]) > int(e["max_charges"]):
                    errors.append(f"实体「{e.get('name','')}」charges({e['charges']}) > max_charges({e['max_charges']})")
        except (ValueError, TypeError):
            pass

    seen_clocks = set()
    for i, clk in enumerate(data["timeline"].get("clocks", []), 1):
        cname = clk.get("name")
        if not cname:
            errors.append(f"时钟 #{i} 缺少 name 名称")
            continue
        if cname in seen_clocks:
            errors.append(f"危机时钟重名: 「{cname}」")
        else:
            seen_clocks.add(cname)
        tch = clk.get("target_ch")
        if not isinstance(tch, int) or isinstance(tch, bool) or tch < 1:
            errors.append(f"时钟「{cname or i}」target_ch 非法: {tch}")
    return errors


def verify_state(book: Path) -> list[str]:
    data: dict[str, dict] = {}
    for key in STATE_KEYS:
        try:
            data[key] = load_state(book, key)
        except (ValueError, FileNotFoundError) as exc:
            return [str(exc)]
    return verify_data(data)
