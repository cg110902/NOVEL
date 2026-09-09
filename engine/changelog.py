"""事件溯源层：state/changelog.jsonl —— 八表状态的全量字段级变更事件流。

定位（与既有机制的分工，互补不互替）：
- ``state/inbox/processed/``            提案原文归档（Reader 交付物，按章）；
- ``snapshots/``                        时点快照（粗粒度、按封存点）；
- ``state/inbox/processed/state_hashes.json``   sync 盖章的篡改检测（check 消费）；
- ``changelog.jsonl``（本模块）         字段级变更事件流——谁、在哪章、经什么通道、
                                        把哪个路径从什么改成什么。由 save_state 这个
                                        全引擎唯一写入咽喉自动派生，LLM 零感知、零 Token。

三个产物文件（**均不入快照、回滚不清空**——历史是资产，回滚本身也是事件）：
- ``changelog.jsonl``     追加式事件流（一行一 JSON；尾行残缺容忍并自愈截断）；
- ``changelog_base.json`` 事件流起点时的八表全量基线（重放的折叠底座）；
- ``changelog.meta.json`` ``{seq, head: {表: 规范哈希}}``（外部改动的检测锚）。

自愈性质：状态文件写入与事件追加之间的崩溃窗口，由 load_state 的哈希比对兜底
——不一致即补记 external_edit 事件（含与折叠结果的差异），事件流永远能追平磁盘
现状。``fold(base, events) == 磁盘状态`` 是本模块的核心不变量（verify 消费）。

事件两类：
- 数据事件 ``{seq, ts, ch, source, op_id, table, path, op(set|add|remove), before, after}``
- 标记事件 ``{seq, ts, kind(genesis|chapter_sealed), ...}``（fold 跳过；B2 的重放锚点）

路径语法：``a.b[key].c``——带 id/name 的列表（entities/lines/locked/cognition/
milestones/clocks/arcs）按键寻址；无键列表（timeline.events / ledger.transactions）
按纯数字下标寻址；``/`` 表示整表。约束：路径段不得含 ``.`` ``[`` ``]``
（实体名实践中为中文；无法解析的事件由 verify 报 stale，绝不静默错读）。
"""
from __future__ import annotations

import copy
import datetime
import json
import re
from pathlib import Path
from typing import Any

from . import common

CHANGELOG_NAME = "changelog.jsonl"
CHANGELOG_BASE_NAME = "changelog_base.json"
CHANGELOG_META_NAME = "changelog.meta.json"
# 快照与回滚必须放行的 changelog 基础设施文件（不当作书状态备份/清理）
CHANGELOG_FILES = frozenset({CHANGELOG_NAME, CHANGELOG_BASE_NAME, CHANGELOG_META_NAME})

STATE_LOCK = ".state.lock"
MAX_EVENTS_PER_TABLE = 400  # 单表单次写入的事件数熔断：超过则折叠为一条整表事件
STALE_KEY = "__stale_events__"


def _sd(book: Path) -> Path:
    return Path(book) / "state"


def changelog_path(book: Path) -> Path:
    return _sd(book) / CHANGELOG_NAME


def base_path(book: Path) -> Path:
    return _sd(book) / CHANGELOG_BASE_NAME


def meta_path(book: Path) -> Path:
    return _sd(book) / CHANGELOG_META_NAME


def active(book: Path) -> bool:
    return changelog_path(book).is_file()


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _line(ev: dict) -> str:
    return json.dumps(ev, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 事件流读写（尾行残缺容忍 + 自愈截断）
# ---------------------------------------------------------------------------

def load_events(book: Path) -> list[dict]:
    """读全部事件；末行残缺（崩溃窗口）时截断自愈，中间坏行跳过并计数。"""
    p = changelog_path(book)
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out: list[dict] = []
    for i, ln in enumerate(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
            if isinstance(ev, dict):
                out.append(ev)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                # 尾行残缺：truncate 到前 i 行（尽力而为，失败不致命）
                try:
                    p.write_text("\n".join(lines[:i]) + ("\n" if i else ""), encoding="utf-8")
                except OSError:
                    pass
    return out


def _read_meta(book: Path) -> dict:
    return common.load_json(meta_path(book), default={}) or {}


def _write_meta(book: Path, meta: dict) -> None:
    common.dump_json(meta_path(book), meta)


def _append_locked(book: Path, meta: dict, events: list[dict]) -> None:
    """锁内追加事件并推进 seq（调用方负责写回 meta）。"""
    if not events:
        return
    seq = int(meta.get("seq") or 0)
    with changelog_path(book).open("a", encoding="utf-8") as fh:
        for ev in events:
            seq += 1
            ev["seq"] = seq
            fh.write(_line(ev) + "\n")
    meta["seq"] = seq


def _emit(book: Path, events: list[dict], head_updates: dict[str, str] | None = None) -> None:
    """统一出口：锁内追加事件 + 更新 head 哈希 + 写回 meta。"""
    with common.file_lock(_sd(book), name=STATE_LOCK):
        meta = _read_meta(book)
        _append_locked(book, meta, events)
        meta.setdefault("head", {}).update(head_updates or {})
        _write_meta(book, meta)


def _data_events(table: str, ops: list[dict], *, source: str,
                 ch: str | None, op_id: str | None, ts: str) -> list[dict]:
    return [{"seq": None, "ts": ts, "ch": ch, "source": source, "op_id": op_id,
             "table": table, "path": o["path"], "op": o["op"],
             "before": o.get("before"), "after": o.get("after")}
            for o in ops]


# ---------------------------------------------------------------------------
# 激活（genesis）：事件流起点 = 此刻磁盘八表
# ---------------------------------------------------------------------------

def ensure_changelog(book: Path) -> bool:
    """事件流不存在则激活：基线=此刻磁盘八表 + genesis 标记。

    老书从接入日起积累（此前历史不可重放，由 genesis 事件如实声明）；
    新书在 init 播种后激活，此后全部写入都有事件。
    """
    if active(book):
        return True
    from . import state as state_mod  # 惰性导入避免循环（state 模块级导入本模块）
    sd = _sd(book)
    sd.mkdir(parents=True, exist_ok=True)
    with common.file_lock(sd, name=STATE_LOCK):
        if active(book):  # 双检：并发激活只赢一个
            return True
        base: dict[str, Any] = {}
        head: dict[str, str] = {}
        for k in state_mod.STATE_KEYS:
            p = sd / f"{k}.json"
            if not p.is_file():
                continue
            try:
                data = common.load_json(p)
            except (ValueError, OSError):
                continue
            base[k] = data
            head[k] = common.canonical_json_hash(data)
        ts = _now()
        # 激活时的最新定稿章号：新书为 0（基线=默认表，早于一切章节）；
        # 老书为当前连载进度（基线晚于更早章节，`state at` 据此拒绝越界重放）
        try:
            from . import evidence as _ev
            at_final_ch = max((n for _, n, _ in _ev.final_chapters(book)), default=0)
        except Exception:
            at_final_ch = 0
        common.dump_json(base_path(book), base)
        meta = {"format": 1, "seq": 1, "head": head, "created_at": ts}
        changelog_path(book).write_text(
            _line({"seq": 1, "ts": ts, "kind": "genesis", "ch": None,
                   "at_final_ch": at_final_ch,
                   "note": "事件流起点：基线为此刻磁盘八表，此前历史不可重放"}) + "\n",
            encoding="utf-8")
        _write_meta(book, meta)
    return True


# ---------------------------------------------------------------------------
# 纯函数：结构 diff 与 fold（互为逆运算，单测做往返性质验证）
# ---------------------------------------------------------------------------

def _key_of(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    kid = item.get("id")
    if isinstance(kid, str) and kid.strip():
        return kid
    name = item.get("name")
    if isinstance(name, str) and name.strip():
        return name
    return None


def diff_states(old: Any, new: Any) -> list[dict]:
    """两个状态值的结构 diff → 事件 op 列表（不含 seq/ts 等信封字段）。

    - dict：按键递归；增键 add / 删键 remove / 叶子变 set；
    - 带键列表（元素均有 id/name 且键不重复）：按键寻址增删改；
    - 无键 dict 列表（timeline.events / ledger.transactions）：按下标递归，
      尾部追加 add（下标=旧长）、尾部截断 remove（降序下标，fold 逐个 del 仍正确）；
    - 标量/混合列表：整体 set；
    - 单表事件数超过 MAX_EVENTS_PER_TABLE：熔断为一条整表 set（path=/）。
    """
    ops: list[dict] = []
    if old is None and new is None:
        return ops
    if old is None:
        return [{"op": "add", "path": "/", "before": None, "after": copy.deepcopy(new)}]
    if new is None:
        return [{"op": "remove", "path": "/", "before": copy.deepcopy(old), "after": None}]
    _diff(old, new, "", ops)
    if len(ops) > MAX_EVENTS_PER_TABLE:
        ops = [{"op": "set", "path": "/", "before": copy.deepcopy(old),
                "after": copy.deepcopy(new), "collapsed": True}]
    return ops


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _diff(old: Any, new: Any, path: str, ops: list[dict]) -> None:
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k not in new:
                ops.append({"op": "remove", "path": _join(path, str(k)),
                            "before": copy.deepcopy(old[k])})
        for k in new:
            if k not in old:
                ops.append({"op": "add", "path": _join(path, str(k)),
                            "after": copy.deepcopy(new[k])})
        for k in old:
            if k in new:
                _diff(old[k], new[k], _join(path, str(k)), ops)
        return
    if isinstance(old, list) and isinstance(new, list):
        _diff_list(old, new, path, ops)
        return
    if old != new:
        ops.append({"op": "set", "path": path or "/", "before": old, "after": new})


def _diff_list(old: list, new: list, path: str, ops: list[dict]) -> None:
    if old == new:
        return
    items = old + new
    if items and all(isinstance(x, dict) for x in items):
        keys_old = [_key_of(x) for x in old]
        keys_new = [_key_of(x) for x in new]
        keyable = (all(keys_old) and all(keys_new)
                   and len(set(keys_old)) == len(keys_old)
                   and len(set(keys_new)) == len(keys_new))
        if keyable:
            idx_old = dict(zip(keys_old, old))
            idx_new = dict(zip(keys_new, new))
            for k, item in idx_new.items():
                if k not in idx_old:
                    ops.append({"op": "add", "path": f"{path}[{k}]",
                                "after": copy.deepcopy(item)})
            for k in sorted(k for k in idx_old if k not in idx_new):
                ops.append({"op": "remove", "path": f"{path}[{k}]",
                            "before": copy.deepcopy(idx_old[k])})
            for k in idx_old:
                if k in idx_new:
                    _diff(idx_old[k], idx_new[k], f"{path}[{k}]", ops)
            return
        # 无键 dict 列表：下标寻址（尾部增删，中段递归）
        common_len = min(len(old), len(new))
        for i in range(common_len):
            if old[i] != new[i]:
                if isinstance(old[i], dict) and isinstance(new[i], dict):
                    _diff(old[i], new[i], f"{path}[{i}]", ops)
                else:
                    ops.append({"op": "set", "path": f"{path}[{i}]",
                                "before": old[i], "after": new[i]})
        for i in range(common_len, len(new)):
            ops.append({"op": "add", "path": f"{path}[{i}]",
                        "after": copy.deepcopy(new[i])})
        for i in range(len(old) - 1, common_len - 1, -1):
            ops.append({"op": "remove", "path": f"{path}[{i}]",
                        "before": copy.deepcopy(old[i])})
        return
    # 标量/混合列表：整体替换（元素级寻址对无序语义的代价大于收益）
    ops.append({"op": "set", "path": path, "before": copy.deepcopy(old),
                "after": copy.deepcopy(new)})


_SEG_RE = re.compile(r"^([^\.\[\]]+)(?:\[([^\]]*)\])?$")


def _parse_path(path: str) -> list[tuple[str, str | None]]:
    segs: list[tuple[str, str | None]] = []
    for part in path.split("."):
        m = _SEG_RE.match(part)
        if not m:
            raise ValueError(f"无法解析事件路径: {path!r}")
        segs.append((m.group(1), m.group(2)))
    return segs


def _find_in_list(lst: list, key: str) -> Any:
    if key.isdigit():
        i = int(key)
        if 0 <= i < len(lst):
            return lst[i]
        raise KeyError(key)
    for item in lst:
        if isinstance(item, dict):
            if str(item.get("id") or "") == key or str(item.get("name") or "") == key:
                return item
    raise KeyError(key)


def _descend(node: Any, name: str, key: str | None) -> Any:
    nxt = node[name]  # KeyError → 寻址失败
    if key is not None:
        if not isinstance(nxt, list):
            raise TypeError(f"{name} 不是列表，无法按键寻址")
        nxt = _find_in_list(nxt, key)
    return nxt


def _apply_op(root: Any, path: str, op: str, after: Any) -> None:
    if path == "/":
        if op == "remove":
            root.clear()
        else:
            root.clear()
            root.update(copy.deepcopy(after) if isinstance(after, dict) else {})
        return
    segs = _parse_path(path)
    node = root
    for name, key in segs[:-1]:
        node = _descend(node, name, key)
    last_name, last_key = segs[-1]
    if last_key is not None:
        lst = node[last_name]
        if not isinstance(lst, list):
            raise TypeError(f"{last_name} 不是列表")
        if op == "add":
            if last_key.isdigit():
                i = int(last_key)
                lst.insert(min(i, len(lst)), copy.deepcopy(after))
            else:
                lst.append(copy.deepcopy(after))  # 按键新增 = 追加（键为信息性寻址）
            return
        item = _find_in_list(lst, last_key)
        if op == "remove":
            lst.remove(item)
        elif isinstance(after, dict) and isinstance(item, dict):
            item.clear()
            item.update(copy.deepcopy(after))
        else:
            idx = lst.index(item)
            lst[idx] = copy.deepcopy(after)
        return
    if op == "remove":
        node.pop(last_name, None)
    else:
        node[last_name] = copy.deepcopy(after)


def fold(base: dict, events: list[dict]) -> dict:
    """基线 + 事件流 → 折叠出的状态（重放的核心；verify 的对账底座）。

    无法寻址的事件不中断折叠，收入 ``__stale_events__``（verify 会显式暴露，
    绝不静默错读）。标记事件（kind 非空）跳过。
    """
    result = copy.deepcopy(base) if isinstance(base, dict) else {}
    stale: list[dict] = []
    for ev in events:
        if not isinstance(ev, dict) or ev.get("kind"):
            continue
        table = ev.get("table")
        op = ev.get("op")
        if not table or op not in ("set", "add", "remove"):
            continue
        root = result.setdefault(table, {})
        if not isinstance(root, dict):
            stale.append({"seq": ev.get("seq"), "path": ev.get("path"),
                          "reason": "表基线非对象"})
            continue
        try:
            _apply_op(root, str(ev.get("path") or "/"), op, ev.get("after"))
        except (KeyError, IndexError, TypeError, ValueError):
            stale.append({"seq": ev.get("seq"), "path": ev.get("path"),
                          "reason": "寻址失败"})
    if stale:
        result[STALE_KEY] = stale
    return result


# ---------------------------------------------------------------------------
# 写入咽喉挂钩（save_state / load_state / init_state / 回滚 / 封存）
# ---------------------------------------------------------------------------

def record_save(book: Path, table: str, old_data: Any, new_data: Any, *,
                source: str = "engine", ch: str | None = None,
                op_id: str | None = None) -> None:
    """save_state 落盘后调用：diff 旧新 → 追加数据事件 + 更新 head 哈希。

    无变化零事件零写入（幂等写不产生噪声）。
    """
    if not active(book):
        return
    ops = diff_states(old_data, new_data)
    h = common.canonical_json_hash(new_data)
    if not ops:
        meta = _read_meta(book)
        if meta.get("head", {}).get(table) == h:
            return
        _emit(book, [], {table: h})  # 纯格式差异/崩溃自愈：只修 head，不发事件
        return
    events = _data_events(table, ops, source=source, ch=ch, op_id=op_id, ts=_now())
    _emit(book, events, {table: h})


def check_external_edit(book: Path, table: str, data: dict) -> None:
    """load_state 读取后调用：磁盘哈希 ≠ 引擎最后认知 → 补记 external_edit 事件。

    与 state_offline_edit 检查项分工：那是 sync 盖章篡改检测（check 消费、指名报出），
    这是事件流的自动补录（把绕过 save_state 的改动纳入历史，供 fold 追平磁盘）。
    """
    if not active(book):
        return
    meta = _read_meta(book)
    head = meta.get("head", {})
    h = common.canonical_json_hash(data)
    if table not in head:
        # 激活时该表尚不存在（后补建表）：登记现状即可
        _emit(book, [], {table: h})
        return
    if head[table] == h:
        return
    # 不一致：折叠出引擎最后认知，diff 出外部改动
    old = fold_book(book).get(table)
    ops = diff_states(old, data)
    events = _data_events(table, ops, source="external_edit", ch=None,
                          op_id=None, ts=_now())
    _emit(book, events, {table: h})


def seal_chapter(book: Path, ch: str) -> None:
    """章节封存标记（B2 `state at` 的重放锚点）。"""
    if not active(book):
        return
    _emit(book, [{"seq": None, "ts": _now(), "kind": "chapter_sealed", "ch": ch}], None)


def record_rollback(book: Path, snapshot_name: str,
                    before_states: dict, after_states: dict) -> None:
    """快照回滚的事件化：逐表 diff 回滚前后 → snapshot_rollback 数据事件。

    回滚不删除事件流（历史是资产）：回滚前的世界仍可通过 fold 重放到达。
    """
    if not active(book):
        ensure_changelog(book)  # 老书首次：基线=回滚后现状，无更早历史可记
        return
    ts = _now()
    events: list[dict] = []
    head_updates: dict[str, str] = {}
    tables = sorted(set(before_states) | set(after_states))
    for table in tables:
        old = before_states.get(table)
        new = after_states.get(table)
        ops = diff_states(old, new)
        if ops:
            events.extend(_data_events(table, ops, source="snapshot_rollback",
                                       ch=None, op_id=None, ts=ts))
        if new is not None:
            head_updates[table] = common.canonical_json_hash(new)
    _emit(book, events, head_updates)


# ---------------------------------------------------------------------------
# 对账（verify）与折叠查询
# ---------------------------------------------------------------------------

def fold_book(book: Path) -> dict:
    """整书折叠：base + 全部事件 → 当前应然状态。"""
    base = common.load_json(base_path(book), default={}) or {}
    return fold(base, load_events(book))


def verify(book: Path) -> tuple[bool, str]:
    """核心不变量检查：fold(base, events) 与磁盘八表逐表哈希一致。

    - 老书未激活 → 视为通过（inactive）；
    - 不一致 = 存在尚未被 load_state 补录的外部改动或事件丢失——这正是
      要暴露的事实，不是本模块的错误。
    """
    if not active(book):
        return True, "inactive"
    from . import state as state_mod
    folded = fold_book(book)
    stale = folded.pop(STALE_KEY, [])
    if stale:
        return False, f"事件流含 {len(stale)} 条无法寻址的事件（首条 seq={stale[0].get('seq')}）"
    sd = _sd(book)
    for k in state_mod.STATE_KEYS:
        p = sd / f"{k}.json"
        if not p.is_file():
            if k in folded:
                return False, f"{k}.json 磁盘缺失但事件流中有其状态"
            continue
        try:
            disk = common.load_json(p)
        except (ValueError, OSError) as exc:
            return False, f"{k}.json 不可读: {exc}"
        if common.canonical_json_hash(disk) != common.canonical_json_hash(folded.get(k)):
            return False, (f"{k}.json 与事件流折叠结果不一致"
                           "（存在未被补录的外部改动或事件丢失，跑任意 state 读取可自愈补录）")
    return True, "ok"


# ---------------------------------------------------------------------------
# 溯源查询（B2 state at / B3 blame / 两切面 diff）
# ---------------------------------------------------------------------------

def seal_seq_for(book: Path, ch_num: int) -> int | None:
    """≤ ch_num 的最后一次 chapter_sealed 的 seq（无则 None）。"""
    best: int | None = None
    for ev in load_events(book):
        if ev.get("kind") != "chapter_sealed":
            continue
        n = common.chapter_token_to_num(ev.get("ch"))
        if n and n <= ch_num:
            seq = int(ev.get("seq") or 0)
            if best is None or seq > best:
                best = seq
    return best


def genesis_at_final_ch(book: Path) -> int | None:
    """genesis 事件记录的激活时最新定稿章号（缺失=None，按保守处理）。"""
    for ev in load_events(book):
        if ev.get("kind") == "genesis":
            v = ev.get("at_final_ch")
            return v if isinstance(v, int) and not isinstance(v, bool) else None
    return None


def fold_to_seq(book: Path, seq: int) -> dict:
    """折叠到指定 seq（含）为止的状态。"""
    base = common.load_json(base_path(book), default={}) or {}
    return fold(base, [e for e in load_events(book)
                       if int(e.get("seq") or 0) <= seq])


def state_at(book: Path, ch_num: int) -> tuple[dict | None, str | None]:
    """第 ch_num 章封存后的世界切面。返回 (状态, 错误消息)——二者互斥。

    - ch_num 超出最新封存 → 折叠到最新封存（世界「截至最后一次封存」）；
    - ch_num 早于首次封存且晚于 genesis 基线（老书）→ 拒绝（历史不可重放）；
    - ch_num 早于 genesis 基线（新书默认表）→ 返回基线。
    """
    if not active(book):
        return None, "事件流未激活（本书在 changelog 之前创建，跑任意 sync 后开始积累）"
    seq = seal_seq_for(book, ch_num)
    if seq is not None:
        folded = fold_to_seq(book, seq)
        folded.pop(STALE_KEY, None)
        return folded, None
    # 无 ≤ ch_num 的封存点：判基线是否早于请求章
    at_final = genesis_at_final_ch(book)
    if at_final is not None and at_final > ch_num:
        return None, (f"ch_{ch_num:03d} 早于事件流起点（changelog 激活时已连载至 "
                      f"ch_{at_final:03d}，此前历史不可重放）")
    folded = fold_to_seq(book, 0)
    folded.pop(STALE_KEY, None)
    return folded, None


def blame(book: Path, table: str, path: str = "") -> list[dict]:
    """某表某路径的全部变更事件，新→旧排序。

    匹配规则：event.table == table 且（path 为空 = 全表，或 event.path 按路径段
    前缀命中：`entries[p_003]` 命中 `entries[p_003].holder`，但不命中
    `entries[p_0031]`）。
    """
    out = []
    prefix = f"{table}.{path}" if path else table
    for ev in load_events(book):
        if ev.get("kind") or ev.get("table") != table:
            continue
        ev_path = str(ev.get("path") or "")
        if path:
            hit = ev_path == path or ev_path.startswith(path + ".")
        else:
            hit = True
        if hit:
            out.append(ev)
    out.sort(key=lambda e: -int(e.get("seq") or 0))
    return out


def diff_points(book: Path, ch_a: int, ch_b: int) -> dict:
    """两个时点切面之间的全部差异（按表分组的 diff ops）。"""
    fa, err_a = state_at(book, ch_a)
    fb, err_b = state_at(book, ch_b)
    if err_a or err_b:
        return {"error": err_a or err_b}
    from . import state as state_mod
    out: dict[str, list[dict]] = {}
    for k in state_mod.STATE_KEYS:
        ops = diff_states(fa.get(k), fb.get(k))
        if ops:
            out[k] = ops
    return {"diff": out}
