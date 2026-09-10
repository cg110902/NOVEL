"""文档 ↔ 引擎口径对账（doc parity）。

动机：本仓库的用户可见文案里散落着大量**数量口径**（命令数、状态表数、探针数、字段数、
预算、错误码数、审计 front-matter 键数……）。代码改了而文档没跟上，子代理就会照过期协议干活——
`errcodes <码>` 曾被文档写明却根本没实现（跑出来是 argparse 退出码 2）就是同一类事故。

本测试只做两件事：
1. **代码侧真值**由引擎自己回答（`COMMAND_HELP` / `errcodes.REGISTRY` / `STATE.STATE_KEYS` / …）；
2. **文档侧声明**用正则从 README.md / AGENTS.md / engine/README.md / templates/README.md 与
   `.agents/skills/*/SKILL.md` 里抠出来，逐个比对；抠不到该声明时记 **skip**（允许文档不提这个数），
   抠到且不一致记 **fail**。

运行：
    python -m tests.test_docs_parity          # 人读报告，失败退出码 1
    python -m pytest tests/test_docs_parity.py  # 有 pytest 时（可选依赖）
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None

DOCS: dict[str, pathlib.Path] = {
    "README": ROOT / "README.md",
    "AGENTS": ROOT / "AGENTS.md",
    "engine/README": ROOT / "engine" / "README.md",
    "templates/README": ROOT / "templates" / "README.md",
}
SKILL_DIR = ROOT / ".agents" / "skills"


def _doc_texts() -> dict[str, str]:
    out = {k: p.read_text(encoding="utf-8") for k, p in DOCS.items()
           if p.is_file()}
    for sk in sorted(SKILL_DIR.glob("*/SKILL.md")):
        out[f"skills/{sk.parent.name}"] = sk.read_text(encoding="utf-8")
    return out


def _hits(pat: str, docs: dict[str, str]) -> list[str]:
    """返回包含该模式的文档名。"""
    rx = re.compile(pat)
    return [name for name, text in docs.items() if rx.search(text)]


def _find(pat: str, docs: dict[str, str]) -> list[tuple[str, int]]:
    """返回 [(文档名, 捕获到的整数)]。"""
    rx = re.compile(pat)
    hits: list[tuple[str, int]] = []
    for name, text in docs.items():
        for m in rx.finditer(text):
            hits.append((name, int(m.group(1))))
    return hits


def _doc_allowed(docs: dict[str, str], tok: str) -> str:
    """空挂白名单：确实不属于引擎、但文档合法引用的名字（改这里必须写理由）。"""
    allowed = {
        "entity_patch",       # 通道名（changelog/文档用语，非引擎符号）
        "state_watch",        # project.json 配置键（引擎读取，但键名以字面量出现）
        "hard_facts",         # 细纲正文小节里的口语标签，非结构字段
        "state_hashes", "final_hashes",  # processed/ 下的留痕文件名
        "book_db",            # .index/ 检索库文件名
        "bible_log",          # bible 版本盖章日志文件名
        "applied_operations", # 幂等登记表文件名
        "test_docs_parity",   # 本测试模块名
    }
    return tok if tok in allowed else ""


def _engine_source() -> str:
    return "\n".join(
        f.read_text(encoding="utf-8", errors="replace")
        for f in sorted((ROOT / "engine").rglob("*.py"))
        if "__pycache__" not in str(f))


class _FakeArgs:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _errcodes_cli_works() -> bool:
    """直接调 cmd_errcodes：单码查询必须返回 0，未知码必须返回 2。"""
    import io
    from contextlib import redirect_stdout
    from engine.commands.book_setup import cmd_errcodes
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_known = cmd_errcodes(_FakeArgs(code="state_offline_edit", json=True, level=None))
            rc_unknown = cmd_errcodes(_FakeArgs(code="__no_such_code__", json=True, level=None))
        out = buf.getvalue()
    except Exception:  # noqa: BLE001  未实现时会走 argparse 之外的路径，直接判失败
        return False
    return rc_known == 0 and rc_unknown == 2 and "state_offline_edit" in out


# ---------------------------------------------------------------- 各条对账
def checks() -> list[tuple[str, str, str]]:
    """返回 [(检查名, 状态, 详情)]，状态 ∈ ok / fail / skip。"""
    from engine import checks as eng_checks
    from engine import errcodes, pack, proposal_v3, state
    from engine.cli import COMMAND_HELP
    from engine.models.entities import EntityEntry
    from engine.commands import book_setup, chapter_flow

    docs = _doc_texts()
    res: list[tuple[str, str, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        res.append((name, "ok" if ok else "fail", detail))

    def match_or_skip(name: str, pat: str, truth: int, unit: str) -> None:
        hits = _find(pat, docs)
        if not hits:
            res.append((name, "skip", f"文档未声明「{unit}」（无需同步）"))
            return
        bad = [(d, n) for d, n in hits if n != truth]
        add(name, not bad,
            f"文档 {hits} ＝ 代码 {truth}" if not bad
            else f"{unit} 漂移：" + "；".join(f"{d} 写 {n}、实际 {truth}" for d, n in bad))

    # 1) 命令数（AGENTS「N 个命令名」）+ 每条命令都有帮助文案（子代理只靠 help 自查）
    match_or_skip("命令数", r"(\d+) 个命令名", len(COMMAND_HELP), "命令数")
    empty_help = sorted(k for k, v in COMMAND_HELP.items() if not (v or "").strip())
    add("每条命令都有帮助文案", not empty_help,
        f"COMMAND_HELP 共 {len(COMMAND_HELP)} 条，无空帮助" if not empty_help
        else f"帮助文案为空：{empty_help}")

    # 2) 错误码注册表
    n_codes = len(errcodes.REGISTRY)
    match_or_skip("错误码数", r"(\d+) 条闸门码", n_codes, "错误码数")
    src = _engine_source()
    phantom = [c for c in errcodes.REGISTRY
               if f'"{c}"' not in src and f"'{c}'" not in src]
    add("错误码无空挂（每个码在引擎里都有字面量）", not phantom,
        f"{n_codes} 码全部有出处" if not phantom else f"注册了但引擎未引用：{phantom}")
    bad_meta = [c for c, e in errcodes.REGISTRY.items()
                if e.level not in errcodes.LEVELS
                or not (e.description or "").strip()
                or not (e.remedy or "").strip()]
    add("错误码元数据完整（level/说明/处方）", not bad_meta,
        "全部齐备" if not bad_meta else f"缺字段：{bad_meta[:5]}")

    # 3) 状态表口径：十一表 + derived 第十二张；project.json 不占表号
    add("STATE_KEYS/ASSERTED_KEYS 口径",
        len(state.STATE_KEYS) == 12 and len(state.ASSERTED_KEYS) == 11
        and state.STATE_KEYS[:11] == state.ASSERTED_KEYS and state.STATE_KEYS[-1] == "derived",
        f"STATE_KEYS={len(state.STATE_KEYS)} ASSERTED={len(state.ASSERTED_KEYS)}（derived 为第十二张）")
    bad_tbl = [d for d, t in docs.items() if re.search(r"第\s*13\s*张表|第十三张表", t)]
    add("表号口径（project.json 不占表号）", not bad_tbl,
        "无「第十三张表」式误称" if not bad_tbl else f"需改写为「不占表号」：{bad_tbl}")
    doc_state_n = _find(r"`state/` (\d+) 张表", docs) + _find(r"(\d+) 个 JSON 状态文件", docs)
    for d, n in doc_state_n:
        add(f"状态表数（{d}）", n in (11, 12), f"文中写 {n}，允许 11（台账）或 12（含 derived）")

    # 4) EntityEntry 字段数（templates/README「N 个字段」）
    match_or_skip("EntityEntry 字段数", r"EntityEntry 共 (\d+) 个字段",
                  len(EntityEntry.model_fields), "EntityEntry 字段数")

    # 5) 机械探针数（「N大探针」）
    n_probe = len(re.findall(r"^def probe_", (ROOT / "engine" / "audit.py")
                             .read_text(encoding="utf-8"), re.M))
    match_or_skip("机械探针数", r"[：:]?\s*\*\*(\d+)大探针\*\*", n_probe, "探针数")

    # 6) pack 预算与世界锚点帽
    add("pack 总量预算 = 2W", pack.PACK_TOKEN_CAP == 20000,
        f"PACK_TOKEN_CAP={pack.PACK_TOKEN_CAP}")
    has_2w = any("2W" in t for t in docs.values())
    add("文档写明 2W 预算", has_2w, "AGENTS/README/templates/README 至少一处提到「2W」"
        if has_2w else "文档未提到 2W 装配预算")
    add("世界锚点帽 = 10000（代码）", pack.MAX_WORLD_ANCHOR_TOKENS == 10000,
        f"MAX_WORLD_ANCHOR_TOKENS={pack.MAX_WORLD_ANCHOR_TOKENS}")
    pspec = eng_checks.PARAM_SPEC.get("world_anchor_tokens", {})
    add("PARAM_SPEC 口径与代码一致", pspec.get("example") == pack.MAX_WORLD_ANCHOR_TOKENS
        and str(pack.MAX_WORLD_ANCHOR_TOKENS) in pspec.get("desc", ""),
        f"example={pspec.get('example')}，desc 含 {pack.MAX_WORLD_ANCHOR_TOKENS}"
        if pspec else "PARAM_SPEC 缺 world_anchor_tokens")
    add("pack 支持按章取锚（world_refs）", hasattr(pack, "_world_refs")
        and hasattr(pack, "_bible_core_anchors"),
        "_world_refs / _bible_core_anchors 均在位")
    add("world_refs 是 beats 合法 front-matter 键", "world_refs" in eng_checks._BEATS_FM_KEYS,
        f"_BEATS_FM_KEYS={sorted(eng_checks._BEATS_FM_KEYS)}")

    # 7) beats 模板 front-matter ↔ 引擎白名单
    tpl = (ROOT / "templates" / "beats.md").read_text(encoding="utf-8")
    fm_block = re.match(r"^---\n(.*?)\n---", tpl, re.S)
    if fm_block:
        keys = [m.group(1) for m in re.finditer(r"^#?\s*([a-z_][a-z0-9_]*):", fm_block.group(1), re.M)]
        unknown = [k for k in keys if k not in eng_checks._BEATS_FM_KEYS]
        add("beats 模板键全部被引擎认识", not unknown,
            f"模板键 {keys}" if not unknown else f"引擎不认的键（会触发 beats_fm_extra_keys）：{unknown}")
        add("beats 模板声明 world_refs（可注释态）", "world_refs" in keys or "world_refs" in tpl,
            "模板内含 world_refs 提示行")
    else:
        res.append(("beats 模板 front-matter", "skip", "模板顶部无 front-matter 块"))

    # 8) 提案形状表（beats 📐 的单一真源）
    shapes = getattr(proposal_v3, "V3_OP_SHAPES", [])
    def _tables_ok(row) -> bool:
        return all(t in state.STATE_KEYS or t == "entities" for t in str(row[0]).split("/"))
    bad_rows = [r[0] for r in shapes if not _tables_ok(r)]
    add("V3_OP_SHAPES 表名合法", bool(shapes) and not bad_rows,
        f"{len(shapes)} 行全部落在 STATE_KEYS 内" if not bad_rows else f"非法表名：{bad_rows}")
    add("V3 动作集与引擎一致", set(re.findall(r'"([a-z_]+)"', " ".join(str(r[1]) for r in shapes)))
        <= (set(proposal_v3._ENTITY_ACTIONS) | {"set", "patch", "add", "remove", "retire",
                                               "upsert", "update", "create", "append"}),
        f"_ENTITY_ACTIONS={sorted(proposal_v3._ENTITY_ACTIONS)}")
    add("beats 注入器在位", hasattr(chapter_flow, "_proposal_shapes_section"),
        "chapter_flow._proposal_shapes_section")
    add("v3 不可用时的降级清单在位", isinstance(getattr(proposal_v3, "V3_UNAVAILABLE_V2_ONLY", None), tuple),
        f"V3_UNAVAILABLE_V2_ONLY={proposal_v3.V3_UNAVAILABLE_V2_ONLY}")

    # 9) 准读网关 ↔ 技能卡
    role_dir = {"evolver": "evolution"}  # 技能目录名与角色称谓的历史差异（AGENTS 第八节已注明）
    no_skill = [r for r in pack.ROLE_DENY
                if not (SKILL_DIR / role_dir.get(r, r) / "SKILL.md").is_file()]
    add("ROLE_DENY 角色都有技能卡", not no_skill,
        f"{len(pack.ROLE_DENY)} 个角色全部对得上 .agents/skills/*/SKILL.md"
        if not no_skill else f"这些网关角色没有技能卡：{no_skill}")
    gate = "state_offline_edit"
    add(f"离线手改码已注册（{gate}）", gate in errcodes.REGISTRY,
        f"level={errcodes.REGISTRY[gate].level if gate in errcodes.REGISTRY else '-'}")

    # 10) 审计 front-matter 四键（报告生成 / 闸门 / 驾驶舱 / 技能卡口径必须同口径）
    keys4 = ("hard", "soft", "logic", "adjudicated")
    render_src = (ROOT / "engine" / "commands" / "chapter_flow.py").read_text(encoding="utf-8")
    seg = render_src[render_src.find("def _render_audit_md"):]
    seg = seg[:seg.find("\ndef ")] if "\ndef " in seg else seg
    missing = [k for k in keys4 if f"{k}:" not in seg]
    add("audit 报告骨架含四键", not missing,
        "hard/soft/logic/adjudicated 全部输出" if not missing else f"骨架缺键：{missing}")
    sync_src = (ROOT / "engine" / "commands" / "state_sync.py").read_text(encoding="utf-8")
    add("sync 闸门读 logic", 'fm.get("logic"' in sync_src or "fm.get('logic'" in sync_src,
        "cmd_sync 对 logic>0 设闸")
    add("sync 报错文案含四键提示", "logic / adjudicated 四键" in sync_src,
        "缺 front-matter 的报错会把 logic 一并列出")
    cockpit_src = (ROOT / "engine" / "cockpit.py").read_text(encoding="utf-8")
    add("cockpit 透传 logic", "logic" in cockpit_src, "驾驶舱 audit_state 含 logic")
    sk = docs.get("skills/auditor", "")
    add("Auditor 技能卡写明四键与三轨", "四键" in sk and "🧠" in sk and "logic" in sk,
        "auditor SKILL 需同时提到 三轨 / 🧠 / logic / 四键")
    for role in ("stylist", "director"):
        t = docs.get(f"skills/{role}", "")
        if role == "stylist":
            add("Stylist 承接 🧠 手术刀", "🧠" in t, "stylist SKILL 需说明 logic 条目同样归它修")
        else:
            add("Director 写明 logic 阻断", "logic" in t, "director SKILL 需写明 hard/logic 双阻断")

    # 10b) 题材词表：文档说的张数必须等于 checks.WORDLIST_SPEC，且每键都有真实读取方
    wl = list(eng_checks.WORDLIST_SPEC)
    cn = {"一": 1, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    alltext = "\n".join(docs.values())
    claims = [(m.group(0), int(m.group(1)) if m.group(1).isdigit() else cn[m.group(1)])
              for m in re.finditer(r"(\d+|[一两三四五六七八九十])\s*张题材词表", alltext)]
    bad_claims = [txt for txt, n in claims if n != len(wl)]
    add("题材词表张数与代码一致", not bad_claims,
        f"{len(claims)} 处声明全部＝{len(wl)} 键（checks.WORDLIST_SPEC）" if not bad_claims
        else f"文档写了 {bad_claims}，实际 {len(wl)} 张——改文档")
    wl_dead = [k for k in wl if f'get("{k}"' not in src]
    add("题材词表键都有读取方", not wl_dead,
        f"{len(wl)} 键全部被引擎读取" if not wl_dead else f"无人读取的死旋钮：{wl_dead}")

    # 11) templates/project.json：顶层键数 + 无死旋钮
    pj = json.loads((ROOT / "templates" / "project.json").read_text(encoding="utf-8"))
    match_or_skip("project.json 顶层键数", r"(\d+) 个顶层键", len(pj), "project.json 键数")
    # 11a) 能力兜底闸：脚手架必须自带「六张题材词表 + state_watch」（删掉它们＝新书开箱即停用这些启发式）
    need = list(eng_checks.WORDLIST_SPEC) + ["state_watch"]
    missing_tpl = [k for k in need if k not in pj]
    add("脚手架自带七张词表（新书开箱即有能力）", not missing_tpl,
        f"{len(need)} 键齐备（种子跨题材，由 Architect 按本书题材重写）" if not missing_tpl
        else f"模板缺键：{missing_tpl}——这些档会在所有新书上静默停用，恢复种子而不是改测试")
    dead = [k for k, v in pj.items()
            if not isinstance(v, dict) and f'"{k}"' not in src]
    add("模板键在引擎里都有读取方（无死旋钮）", not dead,
        f"{len(pj)} 个顶层键全部被引用" if not dead else f"引擎从不读取的键：{dead}")
    for grp, sub in ((k, v) for k, v in pj.items() if isinstance(v, dict)):
        d2 = [k for k in (sub or {}) if f'"{k}"' not in src]
        add(f"{grp} 子键被引擎读取", not d2,
            f"{len(sub)} 个字典项" if not d2 else f"未读取：{d2}")

    # 11b) pack 到底装几张表：文档写的数字必须等于源码里 load_state 的键元组
    pack_src = (ROOT / "engine" / "pack.py").read_text(encoding="utf-8")
    m = re.search(r"cur = \{key: state\.load_state\(book, key\) for key in \(([^)]*)\)", pack_src, re.S)
    if m:
        loaded = re.findall(r'"([a-z_]+)"', m.group(1))
        claims = _find(r"pack`? 只装 (\d+) 张表", docs) + _find(r"装 (\d+) 张表", docs)
        bad = [(d, n) for d, n in claims if n != len(loaded)]
        add("pack 装载表数", not bad,
            f"源码装 {len(loaded)} 张（{'/'.join(loaded)}），文档声明 {claims or '未声明'}"
            if not bad else f"表数漂移：" + "；".join(f"{d} 写 {n}、实际 {len(loaded)}" for d, n in bad))
    else:
        res.append(("pack 装载表数", "skip", "pack 源码结构变更，请更新本测试的正则"))

    # 11c) 锚点诊断与文档同轨：五组基础组名至少三组要出现在细纲模板/模板词典里
    groups = [g for g, _ in getattr(pack, "_ANCHOR_CORE_GROUPS", ())]
    shown = sum(1 for g in groups
                if g in docs.get("templates/README", "") + (ROOT / "templates" / "beats.md")
                    .read_text(encoding="utf-8"))
    add("基础组名进了 beats 模板/模板词典", shown >= 3,
        f"{shown}/{len(groups)} 组可见（{groups}）——文档必须教主控「常驻哪几组」")

    # 11d) 防旧口径复辟：任何提到「恒常注入」的模板文件必须同时说明 world_refs 可收窄
    stale = []
    for f in sorted((ROOT / "templates").rglob("*.md")):
        t = f.read_text(encoding="utf-8")
        if "恒常注入" in t and "world_refs" not in t:
            stale.append(str(f.relative_to(ROOT)))
    add("模板「恒常注入」口径已同步按章取用", not stale,
        "无残留旧口径" if not stale else f"这些文件还在说恒常注入：{stale}")

    # 12) audit_mode 取值
    modes = {"strict", "advisory", "off"}
    doc_modes = set(re.findall(r"`(strict|advisory|off)`", docs.get("AGENTS", "") + docs.get("README", "")))
    add("audit_mode 取值同口径", not doc_modes or doc_modes == modes,
        f"文档提及 {sorted(doc_modes)}，引擎 {sorted(modes)}")
    add("audit_mode 在引擎判定", all(m in sync_src for m in ("strict", "advisory", "off")),
        "cmd_sync 三档齐")

    # 13) errcodes 单码查询（曾被文档写明但未实现）
    add("`errcodes <码>` 单码查询可用（实测）", _errcodes_cli_works(),
        "cmd_errcodes 实测：已知码退出 0 并回说明，未知码退出 2（文档曾承诺而未实现，此为回归闸）")
    doc_single = _hits(r"errcodes <码>", docs)
    add("文档写明单码查询", bool(doc_single), f"{len(doc_single)} 份文档提到 `errcodes <码>`")

    # 13b) 文档里的命令/子命令/参数必须真实存在（in-process 解析 argparse，不起子进程）
    import argparse as _ap
    from engine.cli import _build_subparsers
    _root = _ap.ArgumentParser(prog="studio")
    _sub = _root.add_subparsers(dest="command")
    _build_subparsers(_sub)
    _cmdopts: dict[tuple[str, str | None], set[str]] = {}
    for name, par in _sub.choices.items():
        def _opts(pr):
            got = {o for act in pr._actions for o in act.option_strings if o.startswith("-")}
            return {o.lstrip("-") for o in got}
        _cmdopts[(name, None)] = _opts(par) | {"w", "workspace", "json"}
        for act in par._actions:
            if isinstance(act, _ap._SubParsersAction):
                for sc, sp in act.choices.items():
                    _cmdopts[(name, sc)] = _opts(sp) | _opts(par) | {"w", "workspace", "json"}
    CMD_RE = re.compile(r"studio\.py\s+([a-z][a-z0-9_-]*)(?:\s+([a-z][a-z0-9_-]*))?")
    bad_cmd, bad_sub, bad_flag = [], [], []
    for dname, text in docs.items():
        for ln, line in enumerate(text.splitlines(), 1):
            found = set()
            for m in CMD_RE.finditer(line):
                c, nxt = m.group(1), m.group(2)
                if c not in _sub.choices:
                    bad_cmd.append(f"{dname}:{ln} `studio.py {c}`")
                    continue
                sc = None
                if nxt:
                    key2 = (c, nxt)
                    if key2 in _cmdopts:
                        sc = nxt
                    elif not re.match(r"^(ch_|vol_|[0-9-]|\$|<)", nxt) and any(
                            k[0] == c and k[1] for k in _cmdopts):
                        bad_sub.append(f"{dname}:{ln} `{c} {nxt}`（该命令无此子命令）")
                found.add((c, sc))
            if len(found) == 1:
                key = found.pop()
                valid = _cmdopts.get(key) or _cmdopts.get((key[0], None)) or set()
                for flag in re.findall(r"--([a-z][a-z0-9-]*)", line):
                    if flag not in valid:
                        bad_flag.append(f"{dname}:{ln} `{key[0]}{' ' + (key[1] or '')}` 无 --{flag}")
    add("文档中的命令名都存在", not bad_cmd,
        "命令引用全部有效" if not bad_cmd else "失效命令：" + "; ".join(bad_cmd[:4]))
    add("文档中的子命令都存在", not bad_sub,
        "子命令引用全部有效" if not bad_sub else "失效子命令：" + "; ".join(bad_sub[:4]))
    add("文档中的参数都存在", not bad_flag,
        "参数引用全部有效" if not bad_flag else "失效参数：" + "; ".join(bad_flag[:4]))

    # 13c) 文档反引号里的英文标识符必须在引擎里真实存在（抓「文档写了个不存在的字段/码名」）
    KNOWN_EXT = {"package", "additionalProperties", "requirements", "pyproject", "pytest",
                 "node", "sqlite", "fts5", "bm25", "ner", "llm", "json", "yaml", "utf", "api"}
    ghosts = []
    for dname, text in docs.items():
        for ln, line in enumerate(text.splitlines(), 1):
            for m in re.finditer(r"`([a-z][a-z0-9]*_[a-z0-9_]+)`", line):
                tok = m.group(1)
                if tok in KNOWN_EXT or len(tok) < 6:
                    continue
                if re.fullmatch(r"(?:it|fac|loc|p|ms|gun|kno|evt|lock|mis)_\d+", tok):
                    continue  # 实体/条目 ID 示例（p_001 / it_002 / KNO-001 等），不是引擎符号
                if re.search(r"严禁|禁止|不要|勿", line) and re.search(r"字段|键|illegal|不允许", line):
                    continue  # 反面示例（如「严禁写字典字段 bound_to」）——故意引用不存在的名字
                if tok in src or tok in errcodes.REGISTRY or tok in state.STATE_KEYS \
                        or tok in eng_checks.PARAM_SPEC or tok in eng_checks.WORDLIST_SPEC \
                        or tok in _doc_allowed(docs, tok):
                    continue
                ghosts.append(f"{dname}:{ln} `{tok}`")
    add("文档里的标识符无空挂（防臆造字段/码名）", not ghosts,
        "全部可追溯到引擎" if not ghosts else "引擎查无此名：" + "; ".join(ghosts[:6]))

    # 13d) `beats_*` 闸门档数声明与注册表一致
    n_beats = sum(1 for k in errcodes.REGISTRY if k.startswith("beats_"))
    claims = [n for _, n in _find(r"(\d+) 档 `beats_\*`", docs)]
    add("beats 闸门档数口径", all(n == n_beats for n in claims),
        f"文档 {claims or '未声明'}，注册表 {n_beats} 档")

    # 14) 技能卡 front-matter
    bad_sk = [d.name for d in SKILL_DIR.glob("*/SKILL.md")
              if not re.match(r"^---\nname:\s*\S+\n[\s\S]*?^description:", d.read_text(encoding="utf-8"), re.M)]
    add("技能卡 front-matter 合规", not bad_sk,
        "全部含 name/description" if not bad_sk else f"缺 front-matter：{bad_sk}")
    match_or_skip("技能卡数量", r"(\d+) 个角色的技能卡", len(list(SKILL_DIR.glob("*/SKILL.md"))),
                  "角色技能卡数")
    return res


def test_docs_parity() -> None:
    bad = [r for r in checks() if r[1] == "fail"]
    assert not bad, "文档与引擎口径漂移：\n" + "\n".join(f"  - {n}: {d}" for n, _, d in bad)


def main() -> int:
    rows = checks()
    w = max(len(n) for n, _, _ in rows)
    icon = {"ok": "✔", "fail": "✘", "skip": "·"}
    for name, st, detail in rows:
        print(f"{icon[st]} {name.ljust(w)}  {detail}")
    n_fail = sum(1 for _, s, _ in rows if s == "fail")
    n_skip = sum(1 for _, s, _ in rows if s == "skip")
    print(f"\n共 {len(rows)} 项：{len(rows) - n_fail - n_skip} 通过 / {n_fail} 失败 / {n_skip} 文档未声明")
    if n_fail:
        print("修法：以代码为真源改文档（`engine/README.md`「数量口径同步」条）；"
              "确需改代码则一并更新本测试的期望值。")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
