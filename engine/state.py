"""状态机核心（SSOT + 提案确定性合并）。

全部「死板」操作：
- 8 个 JSON 状态文件（STATE_KEYS）为机器真值；读写都过 engine/schemas/ 的声明式校验，引擎自身也不写非法数据。
- 提案 = 章节事实增量的唯一写入口：信封 schema + 分区规则校验 → 全部通过才落盘（内存事务：先全量合并到副本，
  任一分区报错则整体不写）；落盘阶段再带字节级备份，写失败即整体回滚。
  （边界说明：Stage 0 建书播种与跨卷改版由 architect/evolver 直接写 state/*.json，属设定层写入；
   封存时 sync 会对十一表盖章 SHA-256，绕过提案的离线手改由 check 的 state_offline_edit 档指名报出。）
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

from . import changelog, common, migrations, proposal_v3, validator, models

MUTATION_SCHEMA = "novel-studio.state-mutation/v2"
STATE_DIR_NAME = "state"
INBOX_NAME = "inbox"
MARKER_NAME = ".applied_operations.json"
STATE_KEYS = ("current", "persons", "items", "factions", "places", "lines", "timeline", "ledger", "synopsis", "locked", "cognition", "derived")
# 十一表真值（断言层）：Agent 可写；derived 为第十二张派生表，唯一写者是引擎（sync 封存/recompute）。
# v6 起 entities 按 kind 物理拆为 persons/items/factions/places 四表；"entities" 键仅保留
# 兼容读视图（load_state 合并返回）与提案分区名，save_state("entities") 拒绝写入。
ASSERTED_KEYS = ("current", "persons", "items", "factions", "places", "lines", "timeline", "ledger", "synopsis", "locked", "cognition")
KIND_TABLES = ("persons", "items", "factions", "places")
LEGACY_ENTITIES_KEY = "entities"
TYPE_TO_TABLE = {"person": "persons", "item": "items", "faction": "factions",
                 "place": "places", "location": "places", "other": "persons"}
TYPE_ALIASES = {"人物": "person", "道具": "item", "势力": "faction",
                "组织": "faction", "地点": "place"}

CH_RE = re.compile(r"ch_(\d{3,})$")
GUN_ID_RE = re.compile(r"GUN-\d{3,}")
MIS_ID_RE = re.compile(r"MIS-\d{3,}")
KNO_ID_RE = re.compile(r"KNO-\d{3,}")
# ID 正则单一真源在 models/locked.py 与 models/cognition.py（此前 state.py 各自
# 再定义一遍，三处并存；改格式时漏改一处就会让校验与落盘口径分裂）。
from .models.cognition import COG_ID_RE  # noqa: E402
from .models.locked import LOCK_ID_RE  # noqa: E402
from .models.timeline import EVT_ID_RE  # noqa: E402
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
                  # holders = 知情圈（知情方实体名/别名列表，选填）——
                  # POV 推导对 holders 内角色不再误标「不应知情」，防吃书
                  "plant_fields": {"secret", "target_ch", "plant_ch", "note", "weight", "requires", "holders"},
                  "plant_need": ("secret",), "update_str": ("secret", "note"),
                  "update_fields": {"status", "target_ch", "secret", "note", "weight", "requires", "holders"}},
}


def line_kind_spec(kind: str) -> dict | None:
    """三类线（foreshadow / misunderstanding / knowledge）字段规格的公开只读入口。

    单一真源仍是模块级 _LINE_KIND_SPEC；memory / checks / audit 等外部模块
    需要判定「已闭环状态字面量」「plant 必填字段」等规格时一律走本函数，
    禁止跨模块摸 _LINE_KIND_SPEC 私有名（2025 一致性改造 R1-c1）。
    """
    return _LINE_KIND_SPEC.get(kind)


def _schema(name: str) -> dict:
    if name not in _SCHEMA_CACHE:
        p = Path(__file__).resolve().parent / "schemas" / f"{name}.schema.json"
        _SCHEMA_CACHE[name] = json.loads(p.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[name]


_ENTITY_TYPES = frozenset(t.value for t in models.EntityType)  # 唯一真源：Pydantic 枚举
# 同理：以下枚举一律从 Pydantic 模型派生，禁止在校验分支里再手写字面量集合
# （此前 status/life_status/attitude 各写一份字面量，与模型漂移时只有模型会赢，
#   校验层却仍按旧词表放行/拒绝，是典型的「双真源」隐患）。
_ENTITY_STATUS = tuple(s.value for s in models.EntityStatus)
_LIFE_STATUS = tuple(s.value for s in models.LifeStatus)
_ATTITUDE = tuple(s.value for s in models.FactionAttitude)
_ENTITY_ACTIONS = ("upsert", "register", "retire")  # register 为 upsert 别名（非模型枚举）
_CLOCK_URGENCY = tuple(u.value for u in models.ClockUrgency)
_CLOCK_STATUS = tuple(s.value for s in models.ClockStatus)
_TX_TYPES = tuple(x.value for x in models.TransactionType)


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
    if key == "entities" or key in KIND_TABLES:
        return {"entries": []}
    if key == "lines":
        return {"foreshadows": [], "misunderstandings": [], "knowledge": []}
    if key == "timeline":
        return {"events": [], "arcs": [], "clocks": [], "milestones": []}
    if key == "ledger":
        return {"note": "复式多资源池账本：余额一律由流水重算，禁止手改",
                "pools": {"standard_currency": {"name": "主通货", "unit": "枚", "initial": 0, "current": 0}},
                "transactions": []}
    if key == "synopsis":
        return {"book_logline": "", "chapters": {}}
    if key == "locked":
        return {"schema_version": "novel-studio.locked/v1", "entries": []}
    if key == "cognition":
        return {"schema_version": "novel-studio.cognition/v1", "entries": []}
    if key == "derived":
        return {"schema_version": "novel-studio.derived/v1", "sealed_ch": "", "sealed_at": "",
                "line_temps": [], "scene_violations": [], "holder_orphans": [],
                "knowledge_flags": [], "stats": {}}
    raise KeyError(f"未知状态键: {key}")


INBOX_README = """# state/inbox — 提案收件箱（Stage 4 Reader 交付 / Stage 5 主控审定工位）

一切状态修改从这里进：每章一个 `ch_XXX.json`（填提案以本 README 样例为准，
业务规则见 `AGENTS.md` 与 `.agents/skills/reader/SKILL.md`）。processed/ = 已应用的审计记录（永不删改；
唯一例外：`init --force` 整本重开）；failed/ = 失败提案，就地处修复后重跑 `sync`，
引擎自动捡回（含重名归档的 .2/.3 变体）。

正式提案必须带 operation_id（建议 `<ch>.<角色>.<时间戳/序号>`，如 ch_007.director.0829a、
ch_007.reader.0901_2125）；`*.draft.json`/`*.template.json`/`*.sample.json` 不参与合并，
可放这里当草稿。entities.action 支持 upsert/register/retire（register 为 upsert 别名）。

收件箱**单文件制**：每章在途提案仅一份、文件名恰为 `ch_XXX.json`；修补封存章的修订
并入下一章在途提案随 sync 合并。`sweep_ch_*.json`、`ch_XXX.*.json` 等非规范命名一律
不参与合并（与正式提案并存时被静默忽略、单独出现时 sync 拒收并给出规范命名提示）。
 

写提案的纪律：只写增量；事实必须能在本章 final 正文找到出处；不确定就不上账。
locked 不可逆事实的 note 为必填（写作红线执行提示，如「严禁再次出场，回忆除外」）——
只记 fact 不记红线，日后判断能否绕过时将无据可依；缺 note 整案拒收。
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
ledger.pools 资源池口径（ P3-1：此前全部 AI 向文档零说明，池只能读源码试出来）：
  ⚠️ Stage 0 就应在 bible/04 定死池键名、首章提案建池（灵石/银两/寿元/功勋…），不要等写到有账目才补。
  新建池：{"pools": {"my_pool": {"name": "灵石", "unit": "块", "initial": 0}}}
    · name/unit/initial 三项均必填：name/unit 为非空字符串，initial 为整数。
      省略 initial 即整案拒收——期初余额是账本的基准，省略会被当成 0，
      而欠账/存量类资源池恰恰不是从 0 开始的（键名打错如 intial 同样拒收）；
    · 池对象只接受 name/unit/initial 三键，多出任何键即「含未知字段」拒收；
    · ❌ 严禁声明 "current"——余额一律由流水重算，声明即整案拒收；
    · 既有池禁止修改 initial（改动 = 拒收）；对既有池声明 name/unit 只出「声明已修订」提示；
    · 流水 transactions[].pool 引用未声明的池 → 拒收（「流水引用未声明资源池」），
      所以**先建池、再记流水**；`proposal check` 与 `sync` 都会跑这道账本试算，
      提案校验期即可暴露（此前本文档写「提案校验期不拦这一条」，与实测相反）；
      本章合法池键名与 LOCK/COG 已用 ID 水位线已由引擎注入 beats 的「💰 资源池与 ID 水位线」小节；
    · standard_currency（主通货）为引擎内置池，无需声明即可直接用。
  记流水：{"ledger": {"transactions": [{"chapter": "ch_007", "pool": "my_pool", "delta": -30,
           "type": "expense", "subject": "发生了什么", "counterparty": "对手方(选填)",
           "note": "备注(选填)", "quote": "本章 final 支撑句(选填)"}]}}
    · chapter 必须等于提案自身的 chapter（跨章写账 = 整案拒收，见 ledger_tx_order）；
    · delta 用带符号整数（收入正、支出负）；balance_after 由引擎重算，不必手写。
timeline.clocks 危机时钟口径（ P3-2：此前字段契约完全未文档化，按常识写 id/deadline_ch 必被拒）：
  合法字段仅五个，多一个即「含未知字段」整案拒收：
    · name（字符串，必填）：时钟名，如「灯债半年滚利」；
    · target_ch（整数，必填，≥1）：目标爆发/结算章号——⚠️ 只收 int，不收 "ch_012"/"第12章"/"longline"；
    · urgency（选填）：low | medium | high | critical；
    · desc（选填，字符串）：危机内容与超时后果；
    · status（选填，默认 "Active"）：Active | Triggered | Defused | Expired（首字母大写）。
  ❌ 没有 id 字段，也没有 deadline_ch——时钟按 name 去重，改名等于新建。
引文柔性接地（建议携带，绝不阻断）：各条目（entities/lines/ledger.transactions/timeline.events/timeline.clocks/synopsis）
  可携带 "quote": "凭印象摘录的本章 final 支撑句"——引擎模糊接地：相似度 ≥85% 视为命中；
  60~85% 提示「近似命中」；更低仅提示「存疑」。全程只出提示、绝不阻断 sync，
  摘录严禁逐字抠字眼浪费算力；但战死/退役等高危变更强烈建议附引文，便于日后回溯审计。
对象化引用字段（v2，均选填；填了即享精确装配与机械校验）：
  current.time_day（正整数故事日计数）/ pov_ref / place_ref / present_refs（实体 id 或法定名）；
  entities[].injury_level（0~5）/ injury_desc / renown（整数声望）；
  entities[].relations[] 可带 strength（1~5）/ status（active/resolved）/ since_ch（ch_NNN）；
  locked[].refs（关联实体引用，免记忆盲区）；cognition[].truth_ref（GUN-/KNO-/EVT-/LOCK-编号）；
  timeline.events[] 可带 id（EVT-编号，缺省自动分配）/ participants / place / causes / consequences。
  按 id 修订事件：{"id": "EVT-003", "replace": "新描述"}；补元数据：{"id": "EVT-003", "participants": [...]}。
v3 寻址式提案（schema novel-studio.state-mutation/v3；与 v2 二选一，同一文件禁止混写）：\n  取 `proposal new --v3` 骨架；ops 数组每元素 = {table, action, …载荷}，寻址全十一表：\n  · persons/items/factions/places（严格寻址——v3 核心价值：名写错不再静默新建碎片）：\n    create {\"table\":\"persons\",\"action\":\"create\",\"entry\":{\"id\":\"…\",\"name\":\"…\",…}}——\n      id/名必须双不存在；type 缺省按寻址表推断（persons→person…），与地址表矛盾则拒收；\n    update {\"table\":\"items\",\"action\":\"update\",\"id\":\"…\",\"set\":{…}}——id 须存在且归属表一致，\n      set 非空、禁 name/id（改名走手术刀），set.type 变 kind 触发搬迁（警告留痕）；\n    retire {\"table\":\"places\",\"action\":\"retire\",\"id\":\"…\"}——id 须存在且归属表一致。\n    寻址失败（id 不存在/表错位/重名）整案拒收，错误带 [op#N table/action] 定位。\n  · current：{\"table\":\"current\",\"action\":\"update\",\"set\":{要刷新的字段}}（同案重复 set 同键拒收）。\n  · lines：{\"table\":\"lines\",\"action\":\"plant/remind/resolve/…\",\"kind\":\"foreshadow|misunderstanding|knowledge\",…余同 v2 条目字段}（kind 必填，只认这三个值，漏填整案拒收）。\n  · timeline：append_event {\"event\":{…}} / revise_event {\"id\":\"EVT-…\",\"replace\":\"…\"} /\n    append_clock {\"clock\":{…五字段…}} / append_arc {\"arc\":{…}} / append_milestone {\"milestone\":{…}}。\n  · locked/cognition：{\"table\":\"locked\",\"action\":\"plant/upsert/retire\",…余同 v2 条目字段}。\n  · ledger：append_transaction {\"entry\":{…流水…}} / declare_pool {\"pool\":\"池键名\",\"spec\":{\"name\",\"unit\",\"initial\"}}。\n  · synopsis：{\"table\":\"synopsis\",\"action\":\"set\",…余同 v2 synopsis 字段}。\n  分层门：信封错→先修信封；寻址错→[op#N]点名；字段错→沿用 v2 措辞。\n  locked_candidates/consequences 无 v3 op（要用请写 v2 提案）。\n注：提案写入后由 Stage 5 主控统一运行 `python studio.py sync ch_XXX` 校验并合并（支持 --dry-run 预演）。
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
    # 事件溯源：播种完成即激活（基线=十一张默认表），此后一切写入都有事件
    changelog.ensure_changelog(book)
    return seeded


def _fill_missing_required(key: str, data: dict) -> dict:
    if key == "lines":
        for arr_key in ("foreshadows", "misunderstandings", "knowledge"):
            if arr_key not in data:
                data[arr_key] = []
    return data


def load_state(book: Path, key: str) -> dict:
    migrations.ensure_state_version(book)  # 懒触发：老书首次读取即迁移到当前状态机版本
    if key == LEGACY_ENTITIES_KEY:
        # v6 兼容读视图：四表合并（类数据库视图；只读，写请走 kind 表）。
        # 各 kind 表走正常闸门（schema 校验 + 外部改动补录），此处只做拼接。
        merged: list = []
        for k in KIND_TABLES:
            merged.extend(load_state(book, k).get("entries", []) or [])
        return {"entries": merged}
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
    # 事件溯源：磁盘哈希 ≠ 引擎最后认知 → 补记 external_edit 事件（fold 追平磁盘）
    changelog.check_external_edit(book, key, data)
    return data


def save_state(book: Path, key: str, data: dict, *, source: str = "engine",
               ch: str | None = None, op_id: str | None = None) -> None:
    """状态唯一写入咽喉：schema 校验 → 落盘 → changelog 事件化。

    source 取值（事件溯源的通道标签）：proposal（提案合并）/ state_set（手术刀）/
    ledger_recompute / milestone / migration / snapshot_rollback / init / engine（兜底）。
    """
    if key == LEGACY_ENTITIES_KEY:
        raise ValueError("entities 表已在 v6 拆分为 persons/items/factions/places 四表"
                         "（读可用 load_state 兼容视图，写必须走 kind 表）")
    errors = validator.validate(data, _schema(key))
    if errors:
        raise ValueError(f"拒绝写入非法 {key}.json: " + "; ".join(errors[:5]))
    p = state_dir(book) / f"{key}.json"
    # 写前旧值（事件 diff 的 before）；必要时激活 changelog（基线=写前世界）
    old_raw = None
    if p.is_file():
        try:
            old_raw = common.load_json(p)
        except (ValueError, OSError):
            old_raw = None
    changelog.ensure_changelog(book)
    common.dump_json(p, data)
    changelog.record_save(book, key, old_raw, data, source=source, ch=ch, op_id=op_id)


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
    """ch_0123 → ch_123：以章号为键的分区（梗概/编年史等）统一三位列，防口径分裂（ P3-20）。"""
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
    old_type = str(old.get("type") or "").strip().lower()
    new_type = str(new.get("type") or "").strip().lower()
    if new_type and old_type and new_type != old_type:
        rep["warnings"].append(
            f"🏷️ 实体「{name}」类别由 {old_type} 变更为 {new_type}"
            "——跨界变更（person↔item/place/faction）会改变在场/充能等探针口径，请核实剧情语义")
    old_charges, new_charges = old.get("charges"), new.get("charges")
    if (isinstance(old_charges, int) and not isinstance(old_charges, bool)
            and isinstance(new_charges, int) and not isinstance(new_charges, bool)
            and new_charges > old_charges):
        rep["warnings"].append(f"🎒 实体「{name}」充能回升（{old_charges} → {new_charges}）——若为正常补充/升级请忽略")


def canonical_entity_type(t) -> str | None:
    """实体 type 归一：中文别名→法定枚举；缺省→other；未知→None（调用方决定硬错或兜底）。"""
    if t is None or (isinstance(t, str) and not t.strip()):
        return "other"
    s = TYPE_ALIASES.get(str(t).strip(), str(t).strip())
    return s if s in TYPE_TO_TABLE else None


def split_entities_entries(entries: list) -> dict[str, list]:
    """纯函数：实体条目按归一化 type 切分到四表（迁移/changelog 折叠/旧快照体检共用）。

    附带把 entry["type"] 改写为法定枚举（中文→英文、缺省→other、未知→other）。
    调用方须持有数据所有权（迁移/折叠/体检三处均为深拷贝或新 dict，安全）。
    """
    out: dict[str, list] = {k: [] for k in KIND_TABLES}
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        t = canonical_entity_type(e.get("type")) or "other"
        e["type"] = t
        out[TYPE_TO_TABLE[t]].append(e)
    return out


def merged_entities_view(data: dict) -> list[dict]:
    """合并实体视图：kind 四表优先；无 kind 键时回退 legacy data["entities"]（直调 verify 兼容）。"""
    if any(isinstance(data.get(k), dict) for k in KIND_TABLES):
        out: list[dict] = []
        for k in KIND_TABLES:
            t = data.get(k)
            if isinstance(t, dict):
                out.extend(e for e in (t.get("entries") or []) if isinstance(e, dict))
        return out
    leg = data.get("entities")
    if isinstance(leg, dict):
        return [e for e in (leg.get("entries") or []) if isinstance(e, dict)]
    return []


def find_entity_owner(book, name: str) -> tuple:
    """手术刀 legacy 别名：按名定位实体归属 (kind 表, 表数据, 条目)，未找到返回 (None, None, None)。"""
    for k in KIND_TABLES:
        try:
            d = load_state(book, k)
        except (ValueError, OSError):
            continue
        for e in d.get("entries", []) or []:
            if isinstance(e, dict) and e.get("name") == name:
                return k, d, e
    return None, None, None


def _index_by(items: list[dict], key: str) -> dict:
    return {str(it.get(key, "")): it for it in items}


def _scan_nulls(node, path: str, out: list[str]) -> None:
    """递归收集显式 null 位置（持久层闸门拒绝 null，提案入口给出明确报错， P2-8）。"""
    if node is None:
        out.append(f"{path}: 不接受显式 null（键要么缺席要么为合法值）")
    elif isinstance(node, dict):
        for k, v in node.items():
            _scan_nulls(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_nulls(v, f"{path}[{i}]", out)


def normalize_proposal_aliases(proposal: Any) -> Any:
    """柔性归一化提案字段别名（Aliasing Normalizer）。

    容忍大模型常见的同义或习惯性键名漂移，将其无损映射为系统法定规范字段：
    - current:
      current_location -> location, place -> location, current_time -> time
    - entities[]:
      current_location -> location, place -> location
      current_owner -> holder, owner -> holder
      disposition -> attitude, stance -> attitude
      tier -> tier_name, level -> tier_name, rank -> tier_rank
      charge_state -> charges, remaining_charges -> charges
    - lines[]:
      target -> target_ch, due_ch -> target_ch
    - locked[]:
      type -> kind
    """
    if not isinstance(proposal, dict):
        return proposal

    # 1. 归一化 current
    cur = proposal.get("current")
    if isinstance(cur, dict):
        cur_map = {
            "current_location": "location",
            "place": "location",
            "current_time": "time",
            "pressures": "active_pressures",
        }
        for old_k, new_k in cur_map.items():
            if old_k in cur and new_k not in cur:
                cur[new_k] = cur.pop(old_k)

    # 2. 归一化 entities（含 type 中文别名→法定枚举的值归一）
    ents = proposal.get("entities")
    if isinstance(ents, list):
        ent_map = {
            "current_location": "location",
            "place": "location",
            "current_owner": "holder",
            "owner": "holder",
            "disposition": "attitude",
            "stance": "attitude",
            "charge_state": "charges",
            "remaining_charges": "charges",
        }
        for e in ents:
            if isinstance(e, dict):
                for old_k, new_k in ent_map.items():
                    if old_k in e and new_k not in e:
                        e[new_k] = e.pop(old_k)
                if isinstance(e.get("type"), str) and e["type"].strip() in TYPE_ALIASES:
                    e["type"] = TYPE_ALIASES[e["type"].strip()]
                if "tier" in e and "tier_name" not in e:
                    val = e.pop("tier")
                    if isinstance(val, int) and "tier_rank" not in e:
                        e["tier_rank"] = val
                    else:
                        e["tier_name"] = str(val)

    # 3. 归一化 lines
    lines = proposal.get("lines")
    if isinstance(lines, list):
        for g in lines:
            if isinstance(g, dict):
                if "target" in g and "target_ch" not in g:
                    g["target_ch"] = g.pop("target")
                if "due_ch" in g and "target_ch" not in g:
                    g["target_ch"] = g.pop("due_ch")

    # 4. 归一化 locked
    locked = proposal.get("locked")
    if isinstance(locked, list):
        for l in locked:
            if isinstance(l, dict):
                if "type" in l and "kind" not in l:
                    l["kind"] = l.pop("type")

    return proposal


def _validate_v3(proposal: dict, expected_chapter: str | None,
                 book: Path | None) -> tuple[list[str], dict]:
    """v3 寻址提案校验（分层门：信封 → 编译 → v2 深校验逐层放行）。

    - 信封层（本函数前半）：schema 容器 + Pydantic 信封 + _draft/operation_id/
      chapter 三检查；信封坏则直接返回，编译不跑（编译需要结构完整的 ops）。
    - 编译层：book 给定时跑 compile_ops，存在性/表一致性错误并入 errors；
      编译 warnings 由 apply_proposal 收集（本函数签名只回 errors+plan）。
    - v2 深层：apply 编译出 v2 等价提案后重走 validate_proposal 全量 v2 校验，
      字段级错误沿用 v2 措辞（单真源）。
    """
    errors: list[str] = []
    plan: dict[str, str] = {}
    errors.extend(validator.validate(proposal, _schema("proposal_v3")))
    for pe in models.validate_with_model("proposal_v3", proposal):
        if pe not in errors:
            errors.append(pe)
    if errors:
        return errors, plan
    if proposal.get("_draft"):
        errors.append("这是草稿提案（_draft:true）：复核补全后另存为正式提案再 sync")
    if not proposal.get("operation_id"):
        errors.append("正式提案必须提供 operation_id（幂等身份）")
    chapter = proposal.get("chapter")
    if expected_chapter is not None and _canonical_ch(chapter) != _canonical_ch(expected_chapter):
        errors.append(f"chapter 与同步目标不一致: {chapter} != {expected_chapter}")
    if errors:
        return errors, plan
    if book is not None:
        _, compile_errors, _ = proposal_v3.compile_ops(book, proposal)
        errors.extend(compile_errors)
    counts: dict[str, int] = {}
    for op in proposal.get("ops", []) or []:
        if isinstance(op, dict) and op.get("table"):
            counts[op["table"]] = counts.get(op["table"], 0) + 1
    for t in sorted(counts):
        plan[t] = f"寻址 {t} × {counts[t]}"
    return errors, plan


def validate_proposal(proposal, expected_chapter: str | None = None,
                      book: Path | None = None) -> tuple[list[str], dict]:
    errors: list[str] = []
    plan: dict[str, str] = {}
    if not isinstance(proposal, dict):
        return ["提案必须是 JSON 对象"], plan
    if proposal.get("schema") == proposal_v3.V3_SCHEMA:
        return _validate_v3(proposal, expected_chapter, book)

    # 提案进入强类型校验前，先行做柔性别名归一化
    normalize_proposal_aliases(proposal)

    errors.extend(validator.validate(proposal, _schema("proposal")))
    pydantic_errors = models.validate_with_model("proposal", proposal)
    for pe in pydantic_errors:
        if pe not in errors:
            errors.append(pe)
    for k in proposal:
        if k.startswith("candidate_"):
            errors.append(f"{k}: 候选字段仅供复核，禁止直接进入合并")
    if "derived" in proposal:
        errors.append("derived 为引擎派生表（sync 自动封存），提案禁止写入")
    null_hits: list[str] = []
    for sec in ("current", "entities", "lines", "timeline", "ledger", "synopsis", "locked", "locked_candidates", "cognition", "cognition_delta"):
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
        if "time_day" in cur and (not isinstance(cur["time_day"], int)
                                  or isinstance(cur["time_day"], bool) or cur["time_day"] < 1):
            errors.append("current.time_day 必须为 ≥1 的整数（故事日计数）")
        for _rf in ("pov_ref", "place_ref"):
            if _rf in cur and (not isinstance(cur[_rf], str) or not cur[_rf].strip()):
                errors.append(f"current.{_rf} 必须为非空字符串（实体 id 或法定名）")
        if "present_refs" in cur:
            _pr = cur["present_refs"]
            if not isinstance(_pr, list) or any(not isinstance(x, str) or not x.strip() for x in _pr):
                errors.append("current.present_refs 必须为实体引用字符串数组")

    ents = proposal.get("entities")
    if isinstance(ents, list):
        _plan("entities", len(ents))
        allowed_entity_keys = {
            "action", "id", "name", "type", "card", "summary", "status", "aliases",
            "holder", "location", "condition", "quote",
            "realm", "faction", "life_status", "attitude", "charges", "max_charges",
            "cost_per_use", "durability", "scale_tier", "core_assets", "diplomacy",
            "danger_tier", "environment_rules", "tier_rank", "tier_name",
            "power_benchmark", "sensory_anchor", "micro_actions", "address_matrix",
            "dossier", "scope", "golden_quote", "relations",
            "injury_level", "injury_desc", "renown"
        }
        for i, e in enumerate(ents):
            if not isinstance(e, dict):
                errors.append(f"entities[{i}] 必须为对象")
                continue
            for k in e:
                if k not in allowed_entity_keys:
                    errors.append(f"entities[{i}] 含未知字段: {k}")
            if e.get("action", "upsert") not in _ENTITY_ACTIONS:
                errors.append(f"entities[{i}].action 必须为 {'/'.join(_ENTITY_ACTIONS)}（register 为 upsert 别名）")
            if not str(e.get("name", "")).strip():
                errors.append(f"entities[{i}].name 必填")
            if "status" in e and e["status"] not in _ENTITY_STATUS:
                errors.append(f"entities[{i}].status 必须 ∈ {list(_ENTITY_STATUS)}，收到 {e['status']!r}")
            if "life_status" in e and e["life_status"] not in _LIFE_STATUS:
                errors.append(f"entities[{i}].life_status 必须 ∈ {list(_LIFE_STATUS)}，收到 {e['life_status']!r}")
            if "attitude" in e and e["attitude"] not in _ATTITUDE:
                errors.append(f"entities[{i}].attitude 必须 ∈ {list(_ATTITUDE)}，收到 {e['attitude']!r}")
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
            if "injury_level" in e and (not isinstance(e["injury_level"], int)
                    or isinstance(e["injury_level"], bool)
                    or not 0 <= e["injury_level"] <= 5):
                errors.append(f"entities[{i}].injury_level 必须为 0~5 的整数（0=无伤，5=濒死）")
            if "renown" in e and (not isinstance(e["renown"], int) or isinstance(e["renown"], bool)):
                errors.append(f"entities[{i}].renown 必须为整数（声望/悬赏值）")
            if "type" in e and e["type"] not in _ENTITY_TYPES:
                errors.append(f"entities[{i}].type 非法: {e['type']!r}（合法：{'/'.join(sorted(_ENTITY_TYPES))}）")
            for f in ("card", "summary", "holder", "location", "condition", "realm", "faction", "quote", "dossier", "scope", "golden_quote", "injury_desc"):
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
                        for _rk in rel:
                            if _rk not in ("target", "type", "desc", "strength", "status", "since_ch"):
                                errors.append(f"entities[{i}].relations[{r_idx}] 含未知字段: {_rk}")
                        if "strength" in rel and (not isinstance(rel["strength"], int)
                                or isinstance(rel["strength"], bool)
                                or not 1 <= rel["strength"] <= 5):
                            errors.append(f"entities[{i}].relations[{r_idx}].strength 必须为 1~5 的整数")
                        if "status" in rel and rel["status"] not in ("active", "resolved"):
                            errors.append(f"entities[{i}].relations[{r_idx}].status 必须为 active/resolved")
                        if "since_ch" in rel and (not isinstance(rel["since_ch"], str)
                                or not re.fullmatch(r"ch_\d{3,}", rel["since_ch"])):
                            errors.append(f"entities[{i}].relations[{r_idx}].since_ch 须匹配 ch_NNN")
        # 同一提案内同名单/别名重复 upsert 目前会被 _merge_entities 静默折叠成一条
        # （后写覆盖先写），容易让不同 summary/type 的登记数据凭空丢失；改为显式拒收。
        _ent_names = [str(e.get("name", "")).strip() for e in ents if isinstance(e, dict)]
        _ent_dups = sorted({n for n in _ent_names if n and _ent_names.count(n) > 1})
        if _ent_dups:
            errors.append(f"entities 同提案存在重名实体: {_ent_dups}（请合并为一条 upsert）")
        _ent_aliases: dict[str, list[str]] = {}
        for e in ents:
            if not isinstance(e, dict):
                continue
            en = str(e.get("name", "")).strip()
            for a in (e.get("aliases") or []):
                if isinstance(a, str) and a.strip():
                    _ent_aliases.setdefault(a.strip(), []).append(en)
        _alias_dups = sorted((a, ns) for a, ns in _ent_aliases.items() if len(ns) > 1)
        if _alias_dups:
            errors.append(f"entities 同提案别名被多实体占用: {_alias_dups}")

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
                    # target_ch 可选携带：回响/回收时顺延或改期回收计划（ E2E 实测 Reader 需要此语义）
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
        n = len(tl.get("events", []) or []) + len(tl.get("arcs", []) or []) + len(tl.get("clocks", []) or []) + len(tl.get("milestones", []) or [])
        _plan("timeline", n)
        for k in tl:
            if k not in ("events", "arcs", "clocks", "milestones"):
                errors.append(f"timeline 含未知字段: {k}")
        for i, ev in enumerate(tl.get("events", []) or []):
            if not isinstance(ev, dict):
                errors.append(f"timeline.events[{i}] 必须为对象")
                continue
            if "id" in ev and (not isinstance(ev["id"], str) or not EVT_ID_RE.match(ev["id"])):
                errors.append(f"timeline.events[{i}].id 非法: {ev.get('id')!r}（必须符合 ^EVT-\\d{{3,}}$）")
            if "id" not in ev and (not isinstance(ev.get("time"), str) or not ev["time"].strip()
                    or not isinstance(ev.get("event"), str) or not ev["event"].strip()):
                errors.append(f"timeline.events[{i}] 必须含非空字符串 time 与 event（按 id 修订时可省略）")
            for k in ev:
                if k not in ("time", "event", "replace", "quote", "id",
                             "participants", "place", "causes", "consequences"):
                    errors.append(f"timeline.events[{i}] 含未知字段: {k}")
            for _lf in ("participants", "causes", "consequences"):
                if _lf in ev and (not isinstance(ev[_lf], list)
                        or any(not isinstance(x, str) or not x.strip() for x in ev[_lf])):
                    errors.append(f"timeline.events[{i}].{_lf} 必须为引用字符串数组")
            if "place" in ev and (not isinstance(ev["place"], str) or not ev["place"].strip()):
                errors.append(f"timeline.events[{i}].place 必须为非空字符串")
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
            if "urgency" in c and c["urgency"] not in _CLOCK_URGENCY:
                errors.append(f"timeline.clocks[{i}].urgency 必须 ∈ ['low', 'medium', 'high', 'critical']")
            if "status" in c and c["status"] not in _CLOCK_STATUS:
                errors.append(f"timeline.clocks[{i}].status 必须 ∈ ['Active', 'Triggered', 'Defused', 'Expired']")
        for i, m in enumerate(tl.get("milestones", []) or []):
            if not isinstance(m, dict):
                errors.append(f"timeline.milestones[{i}] 必须为对象")
                continue
            for k in m:
                if k not in ("id", "title", "target_ch", "status", "desc", "achieved_ch", "quote", "action"):
                    errors.append(f"timeline.milestones[{i}] 含未知字段: {k}")
            if not m.get("title") or not str(m["title"]).strip():
                errors.append(f"timeline.milestones[{i}].title 必填")
            tch = m.get("target_ch")
            if tch is not None and (not isinstance(tch, int) or isinstance(tch, bool) or tch < 1):
                errors.append(f"timeline.milestones[{i}].target_ch 必须为 ≥1 的正整数")
            st = m.get("status")
            if st is not None and st not in ("pending", "achieved", "abandoned"):
                errors.append(f"timeline.milestones[{i}].status 必须 ∈ ['pending', 'achieved', 'abandoned']")

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
                    # 资源池此前只校验「字段类型」，不校验「字段名」也不校验
                    # 「必填与否」，与同一分区内 transactions 的严格度不一致——后者对未知键
                    # 一律拒收。后果实测：把 initial 打成 intial（探针 E）会被静默接受，
                    # 起始余额默默落为 0，账本从源头被污染且全程无任何提示。
                    # 池是账本的初始条件，写错一个键名即等于悄悄改掉整本书的余额基准。
                    for k in p:
                        if k not in ("name", "unit", "initial"):
                            errors.append(f"ledger.pools[{pid}] 含未知字段: {k}")
                    if "current" in p:
                        errors.append(f"ledger.pools[{pid}].current 不接受声明（余额一律由流水重算）")
                    # 新池必须显式给出起始余额：省略等同于声明「从 0 开始」，
                    # 而绝大多数资源池（欠账、存量）恰恰不是从 0 开始的。
                    if "initial" not in p:
                        errors.append(f"ledger.pools[{pid}].initial 必填（新池须显式声明起始余额，"
                                      f"省略会被当成 0 从而污染账本基准）")
                    elif not isinstance(p["initial"], int) or isinstance(p["initial"], bool):
                        errors.append(f"ledger.pools[{pid}].initial 必须为整数")
                    for f in ("name", "unit"):
                        if f not in p:
                            errors.append(f"ledger.pools[{pid}].{f} 必填")
                        elif not isinstance(p[f], str) or not str(p[f]).strip():
                            errors.append(f"ledger.pools[{pid}].{f} 必须为非空字符串")
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
            if "type" in t and t["type"] not in _TX_TYPES:
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
            # 跨章账本注入闸——流水只能记在提案所属章，禁止改写其他章的账。
            # 既有流水的修订走 ledger recompute / 显式修订通道，不走新提案追加。
            if (t.get("chapter") is not None and expected_chapter
                    and re.fullmatch(r"ch_\d{3,}", str(t["chapter"]))
                    and str(t["chapter"]) != expected_chapter):
                errors.append(
                    f"ledger.transactions[{i}].chapter={t['chapter']} ≠ 提案所属章 {expected_chapter}"
                    "（流水只能记在本章；跨章修正请走 `ledger recompute` 或新章提案，禁止改写他章账目）")
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

    locked = proposal.get("locked")
    if isinstance(locked, list):
        _plan("locked", len(locked))
        allowed_locked_keys = {"action", "id", "fact", "since_ch", "kind", "quote", "note", "reason", "refs"}
        for i, l in enumerate(locked):
            if not isinstance(l, dict):
                errors.append(f"locked[{i}] 必须为对象")
                continue
            for k in l:
                if k not in allowed_locked_keys:
                    errors.append(f"locked[{i}] 含未知字段: {k}")
            lid = l.get("id")
            if not lid or not LOCK_ID_RE.match(str(lid)):
                errors.append(f"locked[{i}].id 非法: {lid!r}（必须符合 ^LOCK-\\d{{3,}}$）")
            act = l.get("action", "plant")
            if act not in ("plant", "upsert", "retire"):
                errors.append(f"locked[{i}].action 必须 ∈ ['plant', 'upsert', 'retire']")
            if act in ("plant", "upsert"):
                fact = l.get("fact")
                if not fact or len(str(fact).strip()) < 4:
                    errors.append(f"locked[{i}].fact 至少需要 4 字有效陈述")
                # note 必填（2025 一致性改造 R2-c6）：不可逆事实的约束力来自
                # 「后续写作不得如何」，只记 fact 不记红线，日后判断能否绕过时无据可依。
                # 仅提案层（写入口）强制；存量书与 schema 不动（先例：param_write_guard P2-6）。
                if not str(l.get("note") or "").strip():
                    errors.append(
                        f"locked[{i}].note 必填（写作红线执行提示）：不可逆事实的约束力来自"
                        f"「后续写作不得如何」，只记 fact 不记红线，日后判断能否绕过时将无据可依。"
                        f"示例：「严禁再次出场，回忆除外」")
                kind = l.get("kind")
                # 与 models.locked.LockedKind / schemas/locked.schema.json 全量对齐（7 类），
                # 此前闸门只放行 4 类，destruction/disbandment/pact 被误杀
                if kind not in ("death", "destruction", "disbandment", "irreversible_action",
                                "rule", "promise", "pact"):
                    errors.append(f"locked[{i}].kind 必须 ∈ ['death', 'destruction', 'disbandment', "
                                  "'irreversible_action', 'rule', 'promise', 'pact']")
            elif act == "retire":
                if not l.get("reason"):
                    errors.append(f"locked[{i}] 归档退役必须提供 reason")
            if "refs" in l and (not isinstance(l["refs"], list)
                    or any(not isinstance(x, str) or not x.strip() for x in l["refs"])):
                errors.append(f"locked[{i}].refs 必须为对象引用字符串数组")

    cog_full = proposal.get("cognition")
    if isinstance(cog_full, list):
        _plan("cognition", len(cog_full))
        allowed_cog_full = {"action", "id", "character", "kind", "content", "since_ch", "quote", "note", "truth_ref"}
        for i, item in enumerate(cog_full):
            if not isinstance(item, dict):
                errors.append(f"cognition[{i}] 必须为对象")
                continue
            for k in item:
                if k not in allowed_cog_full:
                    errors.append(f"cognition[{i}] 含未知字段: {k}")
            if not item.get("character") or not str(item.get("character")).strip():
                errors.append(f"cognition[{i}].character 必填")
            cid = item.get("id")
            if cid and not COG_ID_RE.match(str(cid)):
                errors.append(f"cognition[{i}].id 非法: {cid!r}（必须符合 ^COG-\\d{{3,}}$）")
            if "truth_ref" in item and (not isinstance(item["truth_ref"], str)
                    or not item["truth_ref"].strip()):
                errors.append(f"cognition[{i}].truth_ref 必须为非空字符串（GUN-/KNO-/EVT-/LOCK-编号）")

    cog = proposal.get("cognition_delta")
    if isinstance(cog, list):
        _plan("cognition_delta", len(cog))
        allowed_cog_keys = {"character", "learned", "misread", "doubted", "quote"}
        for i, item in enumerate(cog):
            if not isinstance(item, dict):
                errors.append(f"cognition_delta[{i}] 必须为对象")
                continue
            for k in item:
                if k not in allowed_cog_keys:
                    errors.append(f"cognition_delta[{i}] 含未知字段: {k}")
            if not item.get("character") or not str(item.get("character")).strip():
                errors.append(f"cognition_delta[{i}].character 必填")

    cons = proposal.get("consequences")
    if isinstance(cons, list):
        # 历史遗留分区：仅校验提示、不落盘（无对应状态表；合并时另有显式降级警告）
        plan["consequences"] = f"提示不落盘 × {len(cons)}（已废弃：因果后果请走 cognition_delta / timeline）"
        allowed_cons_keys = {"subject", "change", "irreversible", "quote"}
        for i, item in enumerate(cons):
            if not isinstance(item, dict):
                errors.append(f"consequences[{i}] 必须为对象")
                continue
            for k in item:
                if k not in allowed_cons_keys:
                    errors.append(f"consequences[{i}] 含未知字段: {k}")

    lc = proposal.get("locked_candidates")
    if isinstance(lc, list):
        _plan("locked_candidates", len(lc))
        for i, item in enumerate(lc):
            if not isinstance(item, dict):
                errors.append(f"locked_candidates[{i}] 必须为对象")
                continue
            for k in item:
                if k not in ("fact", "kind", "quote", "note"):
                    errors.append(f"locked_candidates[{i}] 含未知字段: {k}")
            if not item.get("fact") or len(str(item["fact"]).strip()) < 4:
                errors.append(f"locked_candidates[{i}].fact 至少需要 4 字有效陈述")

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
        elif k == "time_day":
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                rep["errors"].append("current.time_day 必须为 ≥1 的整数")
                continue
            old_day = state.get("time_day")
            if (isinstance(old_day, int) and not isinstance(old_day, bool)
                    and v < old_day):
                rep["warnings"].append(
                    f"⏳ 故事日回退：current.time_day {old_day} → {v}"
                    "——若为闪回/倒叙章请忽略本提示")
            state["time_day"] = v
        elif k == "present_refs":
            if not isinstance(v, list):
                rep["errors"].append("current.present_refs 必须为字符串数组")
                continue
            if not v:
                rep["warnings"].append("current.present_refs 为空数组，按未提供处理")
                continue
            state["present_refs"] = [str(x) for x in v if str(x).strip()]
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


def _merge_entities(data: dict, items: list[dict], rep: dict) -> None:
    """v6：entities[] 提案按 type 路由到 persons/items/factions/places 四表。

    - 查找跨四表（id 优先、名次之，last-wins——与单表时代 _index_by 语义一致）；
    - 既有实体 type 变更导致归属表变化时整条搬迁（搬迁记 updated）；
    - 缺 type → other → persons（与单表时代缺省一致，静默）；
    - 中文 type 已在 normalize_proposal_aliases 归一；此处复算 canonical，未知=硬错。
    """
    tables: dict[str, dict] = {}
    for k in KIND_TABLES:
        t = data.get(k)
        if not isinstance(t, dict):
            t = data[k] = {"entries": []}
        if not isinstance(t.get("entries"), list):
            t["entries"] = []
        tables[k] = t
    id_idx: dict[str, tuple[str, dict]] = {}
    name_idx: dict[str, tuple[str, dict]] = {}
    for k in KIND_TABLES:
        for ent in tables[k]["entries"]:
            if not isinstance(ent, dict):
                continue
            if ent.get("id"):
                id_idx[str(ent["id"])] = (k, ent)
            if ent.get("name"):
                name_idx[str(ent["name"])] = (k, ent)
    valid_types = _ENTITY_TYPES
    for e in items:
        action, name = e.get("action", "upsert"), e["name"]
        eid = e.get("id")
        hit = None
        if eid and str(eid) in id_idx:
            hit = id_idx[str(eid)]
        elif name in name_idx:
            hit = name_idx[name]

        if action == "retire":
            if hit is None:
                rep["errors"].append(f"retire 未登记实体「{name}」")
                continue
            hit[1]["status"] = "retired"
            rep["updated"].append(f"🗂️ 实体退役：{name}")
            continue
        raw_type = e.get("type", "other")
        etype = canonical_entity_type(raw_type)
        if etype is None or etype not in valid_types:
            rep["errors"].append(f"实体「{name}」type 非法: {raw_type}")
            continue
        ent = hit[1] if hit else None
        owner = hit[0] if hit else None
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
        dest = TYPE_TO_TABLE[etype]
        if ent is None:
            ent = {"name": name, "type": etype, "aliases": [], "card": "", "summary": "", "status": "active"}
            if eid:
                ent["id"] = eid
                id_idx[str(eid)] = (dest, ent)
            tables[dest]["entries"].append(ent)
            name_idx[name] = (dest, ent)
        else:
            if eid:
                ent["id"] = eid
            if owner != dest:
                tables[owner]["entries"].remove(ent)
                tables[dest]["entries"].append(ent)
                if eid:
                    id_idx[str(eid)] = (dest, ent)
                name_idx[name] = (dest, ent)
                rep["updated"].append(f"🗂️ 实体搬迁：{name}（{owner}→{dest}，type 变更为 {etype}）")
                owner = dest
            elif eid:
                id_idx[str(eid)] = (owner, ent)
        for f in ("id", "type", "card", "summary", "holder", "location", "condition",
                  "realm", "faction", "life_status", "attitude", "charges", "max_charges", "dossier",
                  "scope", "golden_quote", "tier_rank", "tier_name", "power_benchmark", "sensory_anchor",
                  "cost_per_use", "durability", "scale_tier", "danger_tier",
                  "injury_level", "injury_desc", "renown"):
            if f in e and e[f] is not None:
                ent[f] = e[f]
        ent["type"] = etype  # 落盘恒为法定枚举（中文别名不进库）
        if "status" in e:
            ent["status"] = e["status"]
        if "aliases" in e:
            ent["aliases"] = sorted(set(ent.get("aliases", [])) | {str(a) for a in e["aliases"]})
        if "address_matrix" in e and isinstance(e["address_matrix"], dict):
            ent.setdefault("address_matrix", {}).update({str(k): str(v) for k, v in e["address_matrix"].items()})
        if "micro_actions" in e and isinstance(e["micro_actions"], list):
            ent["micro_actions"] = sorted(set(ent.get("micro_actions", [])) | {str(a) for a in e["micro_actions"]})
        if "core_assets" in e and isinstance(e["core_assets"], list):
            ent["core_assets"] = sorted(set(ent.get("core_assets", [])) | {str(a) for a in e["core_assets"]})
        if "diplomacy" in e and isinstance(e["diplomacy"], dict):
            ent.setdefault("diplomacy", {}).update({str(k): str(v) for k, v in e["diplomacy"].items()})
        if "environment_rules" in e and isinstance(e["environment_rules"], list):
            ent["environment_rules"] = sorted(set(ent.get("environment_rules", [])) | {str(a) for a in e["environment_rules"]})
        for _rel in (e.get("relations") or []):
            if isinstance(_rel, dict):
                _pred = str(_rel.get("type", "")).strip()
                if _pred and _pred not in models.KNOWN_RELATION_PREDS:
                    rep["warnings"].append(
                        f"🕸️ 实体「{name}」关系谓词「{_pred}」不在已知表——已入库"
                        "（advisory；建议用 ally/rival/宿敌/师徒 等常规谓词）")
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
            gid = g.get("id")
            if not gid:
                # 无显式 ID 时先做内容指纹查重，命中则复用既有 ID（幂等重放保护）
                for eid, eent in idx.items():
                    if _same_line_content(kind, eent, g, ch_num):
                        gid = eid
                        break
            if not gid:
                gid = _next_id(arr, "id", spec["prefix"])
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
                # 软配额提示：措辞此前自相矛盾（「已达上限（8/8），新伏笔 GUN-009 已入库」），
                # 读着像「拒绝入库」又像「已入库」。改为显式说明是 advisory、条目照常入库、
                # 并给出入库后的实际计数与下一步动作。
                if target != "longline" and open_act_count >= 8:
                    rep["warnings"].append(
                        f"卷内活动伏笔已超软配额（入库前 {open_act_count} 条 / 建议 ≤8，入库后 {open_act_count + 1} 条）——"
                        f"新伏笔 {gid} 仍已入库（本项为 advisory 不阻断）；"
                        "建议尽快 resolve/remind 收束成熟伏笔，防主线稀释（另见 check 的 line_quota_exceeded）")
                if target == "longline" and open_long_count >= 5:
                    rep["warnings"].append(
                        f"全书长线伏笔已超软配额（入库前 {open_long_count} 条 / 建议 ≤5，入库后 {open_long_count + 1} 条）——"
                        f"新长线 {gid} 仍已入库（本项为 advisory 不阻断）；建议收束部分跨卷暗线")
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
            # 与 update 路径同口径：已闭环线索被 remind 静默重开，必须出警示（advisory）
            if str(ent.get("status", "")) == spec["resolved"]:
                rep["warnings"].append(
                    f"🔁 {gid} 已闭环（{ent.get('status')}）又被 remind 重开为 Reminded"
                    "——若为有意回响/续线请核实，否则请保持 Resolved")
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
            # 与 update 路径同口径：已澄清误会又被 escalate 静默重开，必须出警示（advisory）
            if str(ent.get("status", "")) == spec["resolved"]:
                rep["warnings"].append(
                    f"🔁 {gid} 已澄清（Resolved）又被 escalate 重开为 Escalated"
                    "——若为新一轮误会请核实，否则请保持 Resolved")
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
    by_id = {str(e.get("id")): e for e in state["events"] if e.get("id")}
    added = replaced = skipped = 0
    for ev in patch.get("events", []) or []:
        key = (ev.get("time", ""), ev.get("event", ""))
        new_text = ev.get("replace")
        eid = ev.get("id")
        if new_text is not None:
            target = by_id.get(str(eid)) if eid else next(
                (e for e in state["events"]
                 if (e.get("time", ""), e.get("event", "")) == key), None)
            if target is None:
                rep["errors"].append(
                    f"timeline 事件修订未命中: {eid or key[0] + '｜' + str(key[1])[:30] + '…'}")
                continue
            target["event"] = new_text
            replaced += 1
            rep["updated"].append(f"📜 编年史修订：{key[0]}「{str(key[1])[:20]}…」→「{new_text[:32]}…」")
            continue
        if eid and str(eid) in by_id:
            target = by_id[str(eid)]
            if key != (target.get("time", ""), target.get("event", "")) and (ev.get("time") or ev.get("event")):
                rep["errors"].append(
                    f"timeline 事件 {eid} 已存在且 time/event 不同——改文本请用 replace 通道")
                continue
            for _mf in ("participants", "place", "causes", "consequences"):
                if _mf in ev:
                    target[_mf] = ev[_mf]
            rep["updated"].append(f"📜 编年史元数据更新：{eid}")
            continue
        if key in existing:
            skipped += 1
            continue
        entry = {"time": ev["time"], "event": ev["event"], "chapter": ch,
                 "id": str(eid) if eid else _next_id(state["events"], "id", "EVT")}
        for _mf in ("participants", "place", "causes", "consequences"):
            if _mf in ev:
                entry[_mf] = ev[_mf]
        state["events"].append(entry)
        by_id[entry["id"]] = entry
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

    milestones = state.setdefault("milestones", [])
    m_idx = {str(m.get("id")): m for m in milestones if m.get("id")}
    m_title_idx = {str(m.get("title")): m for m in milestones if m.get("title")}
    max_ms_id = 0
    for m in milestones:
        mid_str = str(m.get("id", ""))
        if mid_str.startswith("MS-"):
            try:
                num = int(mid_str.split("-")[1])
                if num > max_ms_id:
                    max_ms_id = num
            except (IndexError, ValueError):
                pass

    for m in patch.get("milestones", []) or []:
        mid = m.get("id")
        title = m.get("title", "")
        # 与 _merge_entities 同口径：ID 未命中时按 title 回退，而不是二选一。
        # 原写法 `m_idx.get(mid) if mid else m_title_idx.get(title)` 在「提案带了一个
        # 尚不存在的 ID + 一个已登记的 title」时只看 ID，于是把同一里程碑静默新建成
        # 第二条——实测 MS-001「夺取断刀」pending 与 MS-009「夺取断刀」achieved 并存，
        # 全程无告警：主控本想标记达成，结果里程碑凭空多了一条还停在 pending。
        ment = m_idx.get(str(mid)) if mid else None
        if ment is None and title:
            ment = m_title_idx.get(str(title))
            if ment is not None and mid and str(mid) != str(ment.get("id", "")):
                rep["warnings"].append(
                    f"🚩 里程碑「{title}」已登记为 {ment.get('id')}，提案给的 id={mid} 未登记"
                    f"——按 title 归并到 {ment.get('id')}（不新建重复里程碑；"
                    f"若确为另一条里程碑请改用不同 title）")
        if ment is None:
            max_ms_id += 1
            if not mid:
                mid = f"MS-{max_ms_id:03d}"
            ch_num = _chapter_num(ch) or 1
            ment = {
                "id": mid,
                "title": title,
                "target_ch": m.get("target_ch", ch_num),
                "status": m.get("status", "pending"),
                "desc": m.get("desc", ""),
            }
            if m.get("achieved_ch"):
                ment["achieved_ch"] = m["achieved_ch"]
            milestones.append(ment)
            m_idx[mid] = ment
            rep["updated"].append(f"🚩 新增主线里程碑「{title}」({mid}) → target ch_{ment['target_ch']:03d}")
        else:
            for f in ("title", "target_ch", "status", "desc", "achieved_ch"):
                if f in m:
                    ment[f] = m[f]
            # title 被改过时同步 title 索引，防同提案后续条目按旧 title 找不到
            m_title_idx[str(ment.get("title", ""))] = ment
            rep["updated"].append(f"🚩 主线里程碑「{ment['title']}」已更新（状态: {ment.get('status')}）")


def _tx_replay_key(t: dict, ch: str) -> tuple:
    """流水内容指纹：崩溃重放/归档重提的同一笔交易判定依据。

    ch 必须参与指纹兜底：省略 chapter 键的入账流水落盘时会回填提案所属章
    （_merge_ledger 的 t.get("chapter", ch)），崩溃重放时若指纹仍算作
    "__legacy__"，与已入库行的指纹（chapter=ch）错配，幂等去重失效 → 同一笔
    流水双计。故 chapter 缺席时以当前提案章号为指纹口径，与存储口径一致。
    """
    try:
        delta = int(t["delta"])
    except (ValueError, TypeError):
        return ("__invalid__",)
    tx_ch = t.get("chapter") or ch
    chapter_key = str(tx_ch) if tx_ch else "__legacy__"
    return (chapter_key, str(t.get("pool")), delta,
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
    applied_in_patch: dict[tuple, int] = {}

    def _skip_dup(subject: str, pool: str, delta) -> None:
        """重复流水统一出口：与已入账流水（或本提案内先行的同内容流水）逐字段一致
        = 按「重复/重放」跳过并明示，绝不静默双计。

        幂等保护必然带一个代价：同章两笔**合法**的同价同货交易（如「买符纸」买两次）
        会被并成 1 笔，账就少记一次。原告警只说「已跳过」，不说跳过了多少钱、也不说
        怎么才能两笔都留下——钱少了而使用者以为记上了。故告警须带池名与金额，并给出
        区分办法（在 subject/note 里写清差异，指纹就不同了）。"""
        unit = str((pools.get(pool) or {}).get("unit") or "").strip()
        amt = f"{int(delta):+}{unit}" if unit else f"{int(delta):+}"
        rep["warnings"].append(
            f"♻️ 疑似重复/重放流水已跳过（幂等保护）：{subject[:24]}"
            f"（{pool} {amt}，本次未入账）——若确属崩溃重放/归档重提，忽略本条即可；"
            f"若这是本章两笔独立的同价交易，请在 subject 或 note 里写清差异"
            f"（如「买符纸·第二批」），指纹不同即两笔都入账")

    for t in patch.get("transactions", []) or []:
        pool = t["pool"]
        if pool not in pools:
            rep["errors"].append(f"[ledger_pool_undeclared] 流水引用未声明资源池 '{pool}'")
            continue
        try:
            delta = int(t["delta"])
        except (ValueError, TypeError):
            rep["errors"].append(f"流水 delta 非整数：{t.get('delta')!r}")
            continue
        k = _tx_replay_key(t, ch)
        existing_n = replay_budget.get(k, 0)
        if existing_n > 0 and replay_used.get(k, 0) < existing_n:
            # 与既有流水逐字段一致：崩溃重放/重复归档重提 → 跳过（只允许与既有行同数）
            replay_used[k] = replay_used.get(k, 0) + 1
            _skip_dup(str(t.get("subject", "")), pool, delta)
            continue
        if applied_in_patch.get(k, 0) >= 1 or existing_n > 0:
            # 本提案内第二条同内容流水（前一条已生效），或既有同内容流水数量已耗尽
            # 重放配额后仍出现同内容行——均为重复，跳过而非双计。
            _skip_dup(str(t.get("subject", "")), pool, delta)
            continue
        applied_in_patch[k] = 1
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
            # 跨章修订通道只认已登记章——指向未注册章整案报错，
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


def _merge_locked(state: dict, patch: list, ch: str, rep: dict) -> None:
    if not isinstance(patch, list):
        rep["errors"].append("locked 分区必须为列表")
        return
    entries = state.setdefault("entries", [])
    entry_map = {e["id"]: e for e in entries if isinstance(e, dict) and "id" in e}
    for item in patch:
        if not isinstance(item, dict):
            continue
        action = item.get("action", "plant")
        iid = item.get("id")
        if not iid or not LOCK_ID_RE.match(str(iid)):
            rep["errors"].append(f"locked 条目 ID 非法: {iid!r}（必须符合 ^LOCK-\\d{{3,}}$）")
            return
        if action in ("plant", "upsert"):
            fact = item.get("fact", "")
            kind = item.get("kind", "irreversible_action")
            new_entry = {
                "id": str(iid),
                "fact": str(fact).strip(),
                "since_ch": str(item.get("since_ch") or ch),
                "kind": str(kind),
                "quote": str(item.get("quote") or "").strip(),
            }
            if item.get("note"):
                new_entry["note"] = str(item.get("note")).strip()
            if item.get("refs"):
                new_entry["refs"] = [str(r).strip() for r in item["refs"] if str(r).strip()]
            if iid in entry_map:
                old_entry = entry_map[iid]
                old_fact = str(old_entry.get("fact", "")).strip()
                # 防静默改史：不可逆事实一旦入账，同 ID 重写必须显式表态。
                # 此前 .update() 直接吞掉旧事实（sync 仍报 ok），是无声数据丢失。
                if old_fact == new_entry["fact"]:
                    if new_entry.get("refs") and new_entry["refs"] != (old_entry.get("refs") or []):
                        old_entry["refs"] = new_entry["refs"]
                        rep["updated"].append(f"🔒 不可逆事实 {iid} 关联引用已补（事实一致，仅补 refs）")
                    else:
                        rep["updated"].append(
                            f"🔒 不可逆事实 {iid} 与既有条目一致（幂等重放，不重复入账）")
                    continue
                if action == "plant" or not item.get("overwrite"):
                    rep["errors"].append(
                        f"[locked_entry_id_reuse] locked 条目 {iid} 已存在且事实不同（旧：{old_fact[:24]}… → 新：{new_entry['fact'][:24]}…）——"
                        "不可逆事实禁止静默覆盖：改写历史请改用 action=\"retire\" 留痕后另立新 ID，"
                        "确认要就地覆写请在该条目显式加 \"overwrite\": true")
                    return
                old_entry.update(new_entry)
                rep["updated"].append(
                    f"🔒 覆写不可逆事实 {iid}（overwrite=true 显式授权；旧事实 {old_fact[:24]}… 已替换）")
            else:
                entries.append(new_entry)
                entry_map[iid] = new_entry
                rep["updated"].append(f"🔒 新增不可逆事实 {iid}（{fact[:20]}…）")
        elif action == "retire":
            reason = item.get("reason")
            if iid in entry_map:
                entries[:] = [e for e in entries if e.get("id") != iid]
                entry_map.pop(iid, None)
                rep["updated"].append(f"🔓 退役不可逆事实 {iid}（原因: {reason}）")
            else:
                rep["warnings"].append(f"locked 条目 {iid} 不存在，退役忽略")
    if len(entries) > 15:
        rep["warnings"].append(f"🔒 不可逆事实已达 {len(entries)} 条（超出 15 条配额），建议退役过时承诺")


def _merge_cognition(state: dict, patch: list, ch: str, rep: dict) -> None:
    if not isinstance(patch, list):
        rep["errors"].append("cognition 分区必须为列表")
        return
    entries = state.setdefault("entries", [])
    entry_map = {e["id"]: e for e in entries if isinstance(e, dict) and "id" in e}

    max_id = 0
    for e in entries:
        m = COG_ID_RE.match(str(e.get("id", "")))
        if m:
            try:
                num = int(m.group(0).split("-")[1])
                if num > max_id:
                    max_id = num
            except (IndexError, ValueError):
                pass

    for item in patch:
        if not isinstance(item, dict):
            continue
        iid = item.get("id")
        action = item.get("action", "plant")
        if not iid:
            char = str(item.get("character", "")).strip()
            content = str(item.get("learned") or item.get("doubted") or item.get("misread") or item.get("content") or "").strip()
            kind = "fact" if item.get("learned") else ("suspicion" if item.get("doubted") else ("misunderstanding" if item.get("misread") else "fact"))
            if not char or not content:
                # 空认知条目（character 之外的字段全缺/全空）不落盘——静默吞掉会让
                # 主控以为已登记，实际查无此条。显式警告后跳过，绝不写空行。
                rep["warnings"].append(
                    f"🧠 cognition 条目缺内容（character={char or '∅'}），按无效跳过——"
                    "learned/doubted/misread/content 至少提供一个非空值")
                continue
            # 内容指纹去重：崩溃重放/归档重提时同一认知条目会再次出现，
            # 但因无显式 ID 会生成新 COG-### → 重复认知条目。
            # 以 (character, kind, content) 为指纹查既有条目，命中则 upsert。
            existing = next((e for e in entries
                             if isinstance(e, dict)
                             and e.get("character") == char
                             and e.get("kind") == kind
                             and e.get("content") == content), None)
            if existing:
                iid = existing["id"]
            else:
                max_id += 1
                iid = f"COG-{max_id:03d}"
            quote = str(item.get("quote") or "").strip()
            note = str(item.get("note") or "").strip()
            new_entry = {
                "id": iid,
                "character": char,
                "kind": kind,
                "content": content,
                "since_ch": str(item.get("since_ch") or ch),
                "quote": quote or f"始于 {ch}",
            }
            if item.get("truth_ref"):
                new_entry["truth_ref"] = str(item.get("truth_ref")).strip()
            if note:
                new_entry["note"] = note
            if existing:
                existing.update(new_entry)
                rep["updated"].append(f"🧠 角色认知 {iid} 已更新「{char}」（{content[:20]}…）")
            else:
                entries.append(new_entry)
                entry_map[iid] = new_entry
                rep["updated"].append(f"🧠 新增角色认知 {iid}「{char}」（{content[:20]}…）")
            continue

        if not COG_ID_RE.match(str(iid)):
            rep["errors"].append(f"cognition 条目 ID 非法: {iid!r}（必须符合 ^COG-\\d{{3,}}$）")
            return
        if action in ("plant", "upsert"):
            char = str(item.get("character", "")).strip()
            content = str(item.get("content", "")).strip()
            if not char or not content:
                # 显式 ID 的条目同样禁止空内容落盘：写空行会让下游以空串当真值。
                rep["warnings"].append(
                    f"🧠 cognition 条目 {iid} 缺 character/content，按无效跳过（不落盘、不覆盖）")
                continue
            kind = str(item.get("kind", "fact"))
            new_entry = {
                "id": str(iid),
                "character": char,
                "kind": kind,
                "content": content,
                "since_ch": str(item.get("since_ch") or ch),
                "quote": str(item.get("quote") or f"始于 {ch}").strip(),
            }
            if item.get("truth_ref"):
                new_entry["truth_ref"] = str(item.get("truth_ref")).strip()
            if item.get("note"):
                new_entry["note"] = str(item.get("note")).strip()
            if iid in entry_map:
                old_entry = entry_map[iid]
                old_char = str(old_entry.get("character", "")).strip()
                old_content = str(old_entry.get("content", "")).strip()
                if old_char and char and old_char != char:
                    # 认知条目以「谁的认知」为身份：换人就换条，绝不覆盖他人认知。
                    rep["errors"].append(
                        f"[cognition_entry_id_reuse] cognition 条目 {iid} 属于「{old_char}」，提案却写成「{char}」——"
                        "认知归属不可覆盖，请为新角色另立新 COG ID")
                    return
                if old_content == new_entry["content"]:
                    rep["updated"].append(
                        f"🧠 角色认知 {iid} 与既有条目一致（幂等重放，不重复入账）")
                    continue
                if action == "plant" or not item.get("overwrite"):
                    rep["errors"].append(
                        f"[cognition_entry_id_reuse] cognition 条目 {iid} 已存在且内容不同（旧：{old_content[:24]}… → 新：{new_entry['content'][:24]}…）——"
                        "禁止静默覆盖：认知修正请另立新 COG ID 保留认知演进链，"
                        "确认要就地覆写请在该条目显式加 \"overwrite\": true")
                    return
                old_entry.update(new_entry)
                rep["updated"].append(
                    f"🧠 覆写角色认知 {iid}（overwrite=true 显式授权；旧内容 {old_content[:24]}… 已替换）")
            else:
                entries.append(new_entry)
                entry_map[iid] = new_entry
                rep["updated"].append(f"🧠 新增角色认知 {iid}「{char}」（{content[:20]}…）")
        elif action == "retire":
            if iid in entry_map:
                entries[:] = [e for e in entries if e.get("id") != iid]
                entry_map.pop(iid, None)
                rep["updated"].append(f"🧠 退役角色认知 {iid}")
            else:
                # 与 locked.retire 未知条目口径一致：警告而非静默（也不报错阻断）
                rep["warnings"].append(f"cognition 条目 {iid} 不存在，退役忽略")


def _merge_proposal_into(data: dict, proposal: dict, ch, ch_num, rep: dict) -> None:
    if proposal.get("current"):
        _merge_current(data["current"], proposal["current"], rep)
    if proposal.get("entities"):
        _merge_entities(data, proposal["entities"], rep)
        # 退役与同案在场冲突 → 自动从 present 剔除并醒目提示
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
    if proposal.get("locked"):
        if "locked" not in data or not isinstance(data["locked"], dict):
            data["locked"] = defaults_for("locked")
        _merge_locked(data["locked"], proposal["locked"], ch, rep)
    cog_patch = proposal.get("cognition") or proposal.get("cognition_delta")
    if cog_patch:
        if "cognition" not in data or not isinstance(data["cognition"], dict):
            data["cognition"] = defaults_for("cognition")
        _merge_cognition(data["cognition"], cog_patch, ch, rep)
    if proposal.get("locked_candidates"):
        rep["updated"].append(f"🔒 记录 {len(proposal['locked_candidates'])} 条不可逆事实提名（待主控审定入账）")


def apply_proposal(book: Path, proposal: dict, expected_chapter: str | None = None,
                   dry_run: bool = False) -> dict:
    rep: dict = {"updated": [], "warnings": [], "errors": [],
                 "chapter": proposal.get("chapter") if isinstance(proposal, dict) else None}
    plan_override: dict | None = None
    hash_src = proposal  # v3 亦按原文哈希（v2equiv 只走合并，不进登记簿）
    if isinstance(proposal, dict) and proposal.get("schema") == proposal_v3.V3_SCHEMA:
        # v3 头：预门 → 信封校验 → 编译为 v2 等价提案 → 下方 v2 管线原样跑。
        # 预门（v3 专属）：编译的存在性检查跑在登记簿主门之前，若无预门，
        # create 类提案重提（crash-retry）将先撞「已存在」而永不到门。
        # 故同字节/同 op 重放在编译前短路为干净 skip；同效异写则落到编译，
        # 如实报存在性错误（正是 typo-guard 的职责），不静默吞掉。
        # 登记簿存 v3 原文哈希（v2 存 v2 原文：登记簿恒为「输入原文」语义，
        # 无版本分支），v2equiv 只走合并、不进登记簿。
        try:
            _pre_marker = _load_marker(book)
        except (ValueError, OSError):
            _pre_marker = None  # 主门会如实报错，此处不抢戏
        if _pre_marker is not None:
            _raw_hash = common.canonical_json_hash(
                {k: v for k, v in proposal.items() if k != "operation_id"})
            _op = proposal.get("operation_id")
            if _op in _pre_marker:
                if _pre_marker[_op] != _raw_hash:
                    rep["errors"] = [f"operation_id {_op} 已用于不同内容，拒绝复用"]
                    return rep
                rep["warnings"].append(f"operation_id {_op} 已应用过，跳过")
                rep["duplicate"] = True
                return rep
            if _raw_hash in _pre_marker.values():
                rep["warnings"].append("相同内容提案已应用过，跳过")
                rep["duplicate"] = True
                return rep
        # compile_ops 纯函数，此处与 _validate_v3 各调一次（各取所需：彼取
        # errors，此取 v2equiv+warnings），开销可忽略。
        v3_errors, v3_plan = validate_proposal(proposal, expected_chapter, book=book)
        if v3_errors:
            rep["errors"] = v3_errors
            rep["plan"] = v3_plan
            return rep
        v2equiv, compile_errors, compile_warnings = proposal_v3.compile_ops(book, proposal)
        if compile_errors:
            rep["errors"] = compile_errors
            rep["plan"] = v3_plan
            return rep
        rep["warnings"].extend(compile_warnings)
        proposal = v2equiv
        plan_override = v3_plan
        rep["chapter"] = proposal.get("chapter")
    errors, plan = validate_proposal(proposal, expected_chapter)
    common.debug(f"gate=validate_proposal: {len(errors)} 错误"
                 + (f"（{errors[0]}）" if errors else ""))
    rep["plan"] = plan_override if plan_override is not None else plan
    if errors:
        rep["errors"] = errors
        return rep

    ch = _canonical_ch(proposal["chapter"])
    op = proposal["operation_id"]
    ch_num = _chapter_num(ch)
    proposal_hash = common.canonical_json_hash({k: v for k, v in hash_src.items() if k != "operation_id"})
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
        # 写入时序：状态文件先写、幂等登记簿后写。
        # 崩溃窗口 = 状态已写但登记簿未写 → 重启后提案被重放。
        # 安全前提：所有 _merge_* 函数对同一提案的重放须幂等
        # （transactions: _tx_replay_key 去重；cognition: 内容指纹去重；
        #  lines: _same_line_content 去重；entities/timeline/locked: by-key upsert）。
        # 事务批处理：十一表变更合并为一次 changelog 追加，减少 fsync 次数与 seq 碎片。
        changelog._begin_transaction()
        try:
            for key in STATE_KEYS:
                save_state(book, key, data[key], source="proposal", ch=ch, op_id=op)
            changelog._commit_transaction(book)
        except Exception:
            changelog._abort_transaction()
            raise
        marker[op] = proposal_hash
        common.dump_json(marker_path, marker)
    except Exception as exc:
        # 回滚自身走原子写（tmp+replace），且失败必须上抛——静默吞掉会造成
        # 「宣称已回滚、现场却撕裂」的假安全（ P2-11）
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
            continue  # 非提案命名的异物不参与合并（ P1-5：异物不再阻断 verify+snapshot）
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
    """ P14：拒收提案归档时附带拒收原因侧车（_<名>.rejection.json）。

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
    # failed = 全部失败数（含非目标章的损坏提案）；failed_target = 阻断目标章本次
    # 同步的失败数——非目标章损坏提案已归档 failed/ 并带侧车，不应阻断目标章封存，
    # 否则「目标章已合并、提案已归档、快照被拒」会造成无法重跑的卡死态（ 实测）。
    overall = {"applied": 0, "failed": 0, "failed_target": 0, "duplicates": 0, "skipped": 0,
               "results": [], "picked_up": False}

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
                    overall["failed_target"] += 1
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
                overall["failed_target"] += 1
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
    """前置因果闭环保（ P20：从「仅 check 可见的状态级错误」提升为合并时写闸门）。

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
    for sec in STATE_KEYS:
        if sec in data and isinstance(data[sec], dict):
            p_errors = models.validate_with_model(sec, data[sec], prefix=sec)
            for pe in p_errors:
                if pe not in errors:
                    errors.append(pe)

    # 前置因果闸门并入写闸门——sync 合并时即拦截闭环/未决前置，
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
    ent_entries = merged_entities_view(data)
    names = [str(e.get("name", "")) for e in ent_entries]
    dup = sorted({x for x in names if names.count(x) > 1})
    if dup:
        errors.append(f"实体注册表重名: {dup}")

    known = set(names)
    deceased_names = set()
    for e in ent_entries:
        known.update(str(a) for a in e.get("aliases", []) if a)
        if e.get("life_status") == "deceased":
            deceased_names.add(e["name"])
            deceased_names.update(str(a) for a in e.get("aliases", []) if a)
    for name in data["current"].get("present_characters", []):
        if str(name).strip() and str(name) not in known:
            errors.append(f"current.present_characters 引用未登记实体「{name}」")
        elif str(name) in deceased_names:
            errors.append(f"current.present_characters 引用已离世实体「{name}」")
    from .objects.registry import build_registry
    from .objects.registry import resolve_ref as _reg_resolve
    _reg = build_registry({"entries": ent_entries})

    def _resolve_ref(ref: str):
        return _reg_resolve(_reg, ref)

    for ref in data["current"].get("present_refs", []) or []:
        ent = _resolve_ref(ref)
        if ent is None:
            errors.append(f"current.present_refs 引用未登记实体「{ref}」")
        elif str(ent.get("life_status") or "") == "deceased":
            errors.append(f"current.present_refs 引用已离世实体「{ref}」")
    for _rf in ("pov_ref", "place_ref"):
        _v = (data["current"].get(_rf) or "")
        if str(_v).strip() and _resolve_ref(_v) is None:
            errors.append(f"current.{_rf} 引用未登记实体「{_v}」")
    _evt_ids = [str(e.get("id", "")) for e in data["timeline"].get("events", []) if e.get("id")]
    _dup_evt = sorted({x for x in _evt_ids if _evt_ids.count(x) > 1})
    if _dup_evt:
        errors.append(f"编年史事件重复编号: {_dup_evt}")

    # 跨表 ID 唯一（单表时代由 EntitiesState.check_unique_ids 承担；拆表后按合并视图补回）
    _ids = [str(e.get("id")) for e in ent_entries if e.get("id")]
    _dup_ids = sorted({x for x in _ids if _ids.count(x) > 1})
    if _dup_ids:
        errors.append(f"实体 ID 跨表重复: {_dup_ids}（persons/items/factions/places 四表内 id 必须全书唯一）")
    for e in ent_entries:
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

    if "timeline" in data and isinstance(data["timeline"], dict):
        ms_entries = data["timeline"].get("milestones", [])
        ms_ids = [str(m.get("id", "")) for m in ms_entries]
        dup_ms = sorted({x for x in ms_ids if ms_ids.count(x) > 1})
        if dup_ms:
            errors.append(f"主线里程碑重复编号: {dup_ms}")

    if "cognition" in data and isinstance(data["cognition"], dict):
        cog_entries = data["cognition"].get("entries", [])
        cog_ids = [str(e.get("id", "")) for e in cog_entries]
        dup_cog = sorted({x for x in cog_ids if cog_ids.count(x) > 1})
        if dup_cog:
            errors.append(f"角色认知台账重复编号: {dup_cog}")
        bad_cog = [x for x in cog_ids if not COG_ID_RE.fullmatch(x)]
        if bad_cog:
            errors.append(f"角色认知台账非法编号: {bad_cog[:5]}")

    if "locked" in data and isinstance(data["locked"], dict):
        locked_entries = data["locked"].get("entries", [])
        locked_ids = [str(e.get("id", "")) for e in locked_entries]
        dup_locked = sorted({x for x in locked_ids if locked_ids.count(x) > 1})
        if dup_locked:
            errors.append(f"不可逆事实台账重复编号: {dup_locked}")
        bad_locked = [x for x in locked_ids if not LOCK_ID_RE.fullmatch(x)]
        if bad_locked:
            errors.append(f"不可逆事实台账非法编号: {bad_locked[:5]}")
        for le in locked_entries:
            if le.get("kind") == "death":
                fact_text = str(le.get("fact", ""))
                for ent in ent_entries:
                    ename = ent.get("name", "")
                    if ename and ename in fact_text:
                        if ent.get("life_status") not in ("deceased", None):
                            errors.append(
                                f"locked 事实声明角色「{ename}」死亡({le.get('id')})，"
                                f"但 entities 中其 life_status={ent.get('life_status')!r}（矛盾）"
                            )
    return errors


def verify_state(book: Path) -> list[str]:
    data: dict[str, dict] = {}
    for key in STATE_KEYS:
        try:
            data[key] = load_state(book, key)
        except (ValueError, FileNotFoundError) as exc:
            return [str(exc)]
    return verify_data(data)