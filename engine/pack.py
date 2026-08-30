"""pack：单章上下文装配（P0 热 / P1 触发 / P2 冷索引）与 export 全书编译。

 pack 不做任何"相关性判断"——P1 触发 = beats 文本 × 注册别名表的确定性最长匹配；
递归注入只到第 2 层（防膨胀）；每层体积自报（budget_report）。export = 纯拼接/视图渲染。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, evidence, state

PREV_TAIL_CHARS = 600
SPINE_CAP = 40
POINTER_WINDOW = 10
PACK_TOKEN_CAP = 12000

FILE_INDEX_AREAS = [
    ("project.json", "书配置：模式/字数带/style_guards"),
    ("bible", "圣经与世界（自由文本）"),
    ("characters", "人物卡（自由文本）"),
    ("outlines/main_plot.md", "全书脊柱")
]


# ---------------------------------------------------------------------------
# 素材小件
# ---------------------------------------------------------------------------
def _beats_text(book: Path, ch: str) -> str:
    files = common.find_chapter_files(book, "beats", ch)
    if not files:
        raise ValueError(f"未找到 {ch} 的 beats（Stage 1 未完成，pack 无的放矢）")
    return files[-1].read_text(encoding="utf-8", errors="replace")


def _prev_final_tail(book: Path, ch_num: int) -> str:
    if ch_num <= 1:
        return ""
    files = common.find_chapter_files(book, "final", ch_num - 1)
    if not files:
        return ""
    text = files[-1].read_text(encoding="utf-8", errors="replace")
    return text[-PREV_TAIL_CHARS:]


def _deviation_lines(book: Path) -> list[str]:
    """bible/project_bible.md 的「本书偏离清单」小节 bullet 行（权威层级的中间层，恒注入）。"""
    p = book / "bible" / "project_bible.md"
    if not p.exists():
        return []
    out, inside = [], False
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^#{1,4}\s", ln):
            if "偏离清单" in ln:
                inside = True
                continue
            if inside:
                break
        elif inside and ln.strip().startswith(("-", "*")):
            item = ln.strip().lstrip("-* ").strip()
            if item and item not in {"（空）", "(空)", "（空节）"}:
                out.append(item)
    return out


def _form_notice(book: Path, ch: str, ch_num: int) -> list[str]:
    notice = []
    cur_fm = common.parse_front_matter(_beats_text(book, ch))
    prev_files = common.find_chapter_files(book, "beats", ch_num - 1) if ch_num > 1 else []
    if prev_files:
        prev_fm = common.parse_front_matter(prev_files[-1].read_text(encoding="utf-8", errors="replace"))
        if cur_fm.get("form") and cur_fm["form"] == prev_fm.get("form"):
            reason = ("form_reason 已给" if cur_fm.get("form_reason")
                      else "front-matter 缺 form_reason（check 将报错）")
            notice.append(f"form 与上章相同（{cur_fm['form']}）：{reason}")
    return notice


def _hard_reminders(book: Path, ch_num: int) -> list[str]:
    """纯算术事实：到期/过期线、未澄清误会、style_guards、偏离清单、form 同款提示。

    容错说明：这里对 lines 台账损坏显式降级为"空台账"（而非抛错/静默兜底为默认值），
    属于 pack 这层"尽可能把上下文交给子代理"的有意例外——pack 的职责是装配提示，
    台账损坏应由 check/状态体检报错，不让它阻断"还能写的章"。"""
    out: list[str] = []
    try:
        lines = state.load_state(book, "lines")
    except ValueError:
        lines = {"foreshadows": [], "misunderstandings": []}
    for g in lines.get("foreshadows", []):
        t = g.get("target_ch")
        if isinstance(t, int) and g.get("status") != "Resolved" and t <= ch_num:
            tag = "本章引爆" if t == ch_num else f"已逾期 {ch_num - t} 章"
            out.append(f"线 {g['id']}《{g.get('name','')}》target_ch={t} → {tag}（状态 {g.get('status')}）")
    for m in lines.get("misunderstandings", []):
        if m.get("status") != "Resolved":
            out.append(f"误会 {m['id']} 未澄清：{m.get('parties','')}（{m.get('content','')[:30]}）")
    proj = common.load_json(book / "project.json", default={}) or {}
    guards = [x for x in (proj.get("style_guards") or []) if isinstance(x, str) and x]
    if guards:
        out.append("style_guards 红线：" + "、".join(guards))
    out.extend(f"本书偏离：{d}" for d in _deviation_lines(book))
    return out


# ---------------------------------------------------------------------------
# P1 触发装配
# ---------------------------------------------------------------------------
def _entity_block(book: Path, name: str, cur: dict, lines: dict, full: bool) -> dict:
    ents = {e["name"]: e for e in cur["entities"].get("entries", [])}
    e = ents.get(name, {})
    block = {"name": name, "type": e.get("type", "other"), "summary": e.get("summary", ""),
             "status": e.get("status", "active"),
             "on_stage": name in cur["current"].get("present_characters", [])}
    touched = []
    alias = [name] + list(e.get("aliases", []))
    for g in lines.get("foreshadows", []) + lines.get("misunderstandings", []):
        if g.get("status") == "Resolved":
            continue
        blob = " ".join(str(g.get(k, "")) for k in ("name", "content", "plan", "parties", "truth"))
        if any(a and a in blob for a in alias):
            touched.append(f"{g['id']}({g.get('status')})")
    if touched:
        block["lines"] = touched
    if full:
        card = str(e.get("card", "")).strip()
        if card:
            try:
                p = common.safe_child_path(book, card)
                block["card_text"] = p.read_text(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                block["card_text"] = f"（卡文件缺失或越界: {card}）"
    return block


# ---------------------------------------------------------------------------
# 主装配
# ---------------------------------------------------------------------------
def build_pack(book: Path, ch: str, lean: bool = False, full: bool = False) -> dict:
    ch_num = common.chapter_token_to_num(ch)
    if not ch_num:
        raise ValueError(f"非法章号: {ch!r}")
    beats = _beats_text(book, ch)
    cur = {key: state.load_state(book, key) for key in ("current", "entities", "lines", "synopsis", "timeline")}

    p0 = {
        "current": {k: v for k, v in cur["current"].items() if v not in ("", [], None)},
        "beats": beats,
        "prev_tail": _prev_final_tail(book, ch_num),
        "hard_reminders": _hard_reminders(book, ch_num),
    }
    payload: dict = {"chapter": ch, "lean": lean, "full": full, "p0": p0, "p1": None, "p2": None}

    lookup = evidence.entity_lookup(book)
    hits = [name for name, aliases in lookup.items()
             if sum(evidence.count_aliases(beats, aliases).values()) > 0]
    p1: dict = {"entities": [], "indirect": [], "spine": []}
    if not lean:
        for name in sorted(hits):
            p1["entities"].append(_entity_block(book, name, cur, cur["lines"], full))
        # 递归一层：注入内容再命中的新实体 → 只补一行摘要（深度 ≤2）
        injected = " ".join(b["summary"] for b in p1["entities"])
        for name in sorted(set(lookup) - set(hits)):
            if sum(evidence.count_aliases(injected, lookup[name]).values()) > 0:
                ent = next((e for e in cur["entities"]["entries"] if e["name"] == name), {})
                p1["indirect"].append(f"{name}：{str(ent.get('summary', ''))[:60]}")
        chapters = cur["synopsis"].get("chapters", {})
        spine = sorted(((v.get("num", 0), k, v) for k, v in chapters.items()))[-SPINE_CAP:]
        p1["spine"] = [f"{k}《{v.get('title','') or '无题'}》：{v.get('synopsis','')}" for _, k, v in spine]
        payload["p1"] = p1

        p2: dict = {"file_index": [], "old_chapter_pointers": [], "open_hint":
                    "需要原文（旧章全文/圣经细则）：python studio.py pack 同章 --open <相对路径>；"
                    "本包未装的一律视为'你不需要知道'。"}
        for rel, desc in FILE_INDEX_AREAS:
            p = book / rel
            targets = [p] if p.is_file() else sorted(p.rglob("*.md")) if p.is_dir() else []
            for f in targets[:80]:
                try:
                    p2["file_index"].append({"path": str(f.relative_to(book)),
                                             "tokens": common.est_tokens(
                                                 f.read_text(encoding="utf-8", errors="replace")),
                                             "desc": desc})
                except OSError:
                    continue
        finals = evidence.final_chapters(book)
        window = [c for c in finals if c[1] < ch_num][-POINTER_WINDOW:]
        for name in sorted(hits):
            marks = []
            for tok, _, text in window:
                c = sum(evidence.count_aliases(text, lookup[name]).values())
                if c:
                    marks.append(f"{tok}×{c}")
            p2["old_chapter_pointers"].append(f"{name}: " + (", ".join(marks) if marks else "近10章未出现"))
        payload["p2"] = p2

    texts = {layer: payload[layer] for layer in ("p0", "p1", "p2")}
    rendered = {k: (render_layer(k, v, full=full) if v else "") for k, v in texts.items()}
    budget = {k: common.est_tokens(v) for k, v in rendered.items()}
    budget["total"] = sum(budget.values())
    budget["cap"] = PACK_TOKEN_CAP
    budget["over_budget"] = budget["total"] > PACK_TOKEN_CAP

    # 超预算硬裁（engine/README.md 契约）：优先裁 P2 冷索引（file_index），
    # P0 热层 / P1 温层是写作所需的活性上下文，尽最大可能保留；裁剪后重算预算并如实上报。
    if budget["over_budget"] and payload.get("p2"):
        fi = payload["p2"].get("file_index", [])
        trimmed = 0
        while budget["over_budget"] and fi:
            fi.pop()
            trimmed += 1
            payload["p2"]["file_index"] = fi
            r = render_layer("p2", payload["p2"], full=full)
            budget["p2"] = common.est_tokens(r)
            budget["total"] = budget["p0"] + budget.get("p1", 0) + budget["p2"]
            budget["over_budget"] = budget["total"] > budget["cap"]
        if trimmed:
            budget["trimmed_file_index"] = trimmed
            budget["trim_note"] = f"超预算按优先级硬裁 P2 冷索引 {trimmed} 条（P0/P1 保留）"

    payload["budget_report"] = budget
    payload["hits"] = sorted(hits)
    return payload


def render_layer(name: str, obj, full: bool = False) -> str:
    """预算自报用的确定性纯文本渲染（与 render_pack 同口径的简化版）。"""
    if obj is None:
        return ""
    if name == "p0":
        lines = [f"{k}: {v}" for k, v in obj["current"].items()]
        lines += ["", "=== beats ===", obj["beats"], "", "=== 上章余温 ===", obj["prev_tail"],
                  "", "=== 硬提醒 ==="] + [f"- {m}" for m in obj["hard_reminders"]]
        return "\n".join(lines)
    if name == "p1":
        lines = []
        for b in obj["entities"]:
            lines.append(f"[{b['name']}|{b['type']}|{'在场' if b['on_stage'] else '缺席'}] {b['summary']}")
            if b.get("lines"):
                lines.append(f"  挂线: {', '.join(b['lines'])}")
            if b.get("card_text"):
                card = b["card_text"] if full else b["card_text"][:400]
                lines.append(f"  卡全文: {card}")
        lines += [f"[间接] {s}" for s in obj["indirect"]]
        lines += ["--- 梗概脊柱 ---"] + obj["spine"]
        return "\n".join(lines)
    lines = [f"{f['path']} (~{f['tokens']}tok) {f['desc']}" for f in obj["file_index"][:25]]
    lines += ["--- 相关旧章指针 ---"] + obj["old_chapter_pointers"] + [obj["open_hint"]]
    return "\n".join(lines)


def render_pack(payload: dict) -> str:
    b = payload["budget_report"]
    out = [f"# pack {payload['chapter']}" + (" [lean]" if payload["lean"] else "")
           + (" [full]" if payload["full"] else ""), "",
           "## P0 热层（恒给）", render_layer("p0", payload["p0"], full=payload["full"])]
    if payload["p1"] is not None:
        out += ["", "## P1 温层（别名触发）", render_layer("p1", payload["p1"], full=payload["full"])]
    if payload["p2"] is not None:
        out += ["", "## P2 冷层（索引）", render_layer("p2", payload["p2"], full=payload["full"])]
    out += ["", f"budget: p0={b['p0']} p1={b.get('p1', 0)} p2={b.get('p2', 0)} "
                f"total={b['total']}/{b['cap']} tokens（超预算={b['over_budget']}）"]
    return "\n".join(out)


def open_file(book: Path, rel: str) -> dict:
    p = common.safe_child_path(book, rel)
    if not p.is_file():
        raise ValueError(f"--open 目标不存在: {rel}")
    return {"path": rel, "text": p.read_text(encoding="utf-8", errors="replace")}


# ---------------------------------------------------------------------------
# export：全书编译（final 纯净正文直接可用；视图按需渲染，非常态义务）
# ---------------------------------------------------------------------------
def _safe_filename(name: str, fallback: str = "book") -> str:
    """把书名净化成可安全用于文件名的字符串（剥离路径分隔符/控制字符/越界点段）。"""
    s = re.sub(r"[\\/<>:\"|?*\x00-\x1f]", "_", (name or "").strip())
    s = re.sub(r"\.\.+", "_", s)          # 防止 ".." 路径越界
    s = re.sub(r"\s+", "_", s).strip("._")
    return s or fallback


def export_txt(book: Path) -> Path:
    proj = common.load_json(book / "project.json", default={}) or {}
    title = proj.get("title") or book.name
    parts = [f"# {title}\n"]
    if proj.get("genre"):
        parts.append(f"> {proj['genre']} · 引擎编译\n")
    ms = book / "manuscript"
    vols = sorted({f.relative_to(ms).parts[0] for f in ms.glob("*/final/ch_*.md")})
 
    # 与 evidence.final_chapters 同口径：同章多版本只取版本号最大者（v10 > v2）；
    # key 用 (卷, 章号)，避免跨卷同章号互相覆盖（vol_02/ch_001 不被 vol_01/ch_001 顶掉）。
    chosen: dict[tuple[str, int], tuple[str, Path]] = {}
    for vol in vols:
        vfiles = sorted((ms / vol / "final").glob("ch_*.md"), key=common.natural_chapter_sort_key)
        for f in vfiles:
            n = common.chapter_number_from_name(f.name)
            if n is None:
                continue
            key = (vol, n)
            cur = chosen.get(key)
            if cur is None or common.chapter_version_from_name(f.name) > common.chapter_version_from_name(cur[1].name):
                chosen[key] = (vol, f)
    for vol in vols:
        body = [f.read_text(encoding="utf-8", errors="replace").strip() + "\n"
                for (v, n), (_, f) in sorted(chosen.items()) if v == vol]
        if body:
            parts.append(f"\n\n# {vol}\n")
            parts.extend(body)
    out = book / "export"
    out.mkdir(parents=True, exist_ok=True)
    # 文件名用净化过的书名（safe_child_path 纪律：不把可控输入直接拼进路径）
    path = out / f"{_safe_filename(title)}.txt"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def export_views(book: Path) -> Path:
    data = {key: state.load_state(book, key) for key in state.STATE_KEYS}
    L = ["# 状态视图（export --views 渲染；真值以 state/*.json 为准）", ""]
    L += ["## current", ""]
    for k, v in sorted(data["current"].items()):
        if v not in ("", [], None):
            L.append(f"- **{k}**: {v}")
    L += ["", "## entities", "", "| name | type | status | summary |", "|---|---|---|---|"]
    for e in data["entities"].get("entries", []):
        L.append(f"| {e.get('name','')} | {e.get('type','')} | {e.get('status','')} | {e.get('summary','')} |")
    L += ["", "## lines 台账", "", "| id | name/content | status | target_ch |", "|---|---|---|---|"]
    for g in data["lines"].get("foreshadows", []):
        L.append(f"| {g['id']} | {g.get('name','')} | {g.get('status','')} | {g.get('target_ch','')} |")
    for m in data["lines"].get("misunderstandings", []):
        L.append(f"| {m['id']} | {m.get('content','')[:30]} | {m.get('status','')} | {m.get('target_ch','')} |")
    L += ["", "## timeline", ""]
    for ev in data["timeline"].get("events", []):
        L.append(f"- {ev.get('time','')}｜{ev.get('event','')}（{ev.get('chapter','')}）")
    for a in data["timeline"].get("arcs", []):
        L.append(f"- 弧 {a.get('name','')}: {a.get('stage','')}"
                 + (f" ｜当前策略: {a.get('strategy')}" if a.get("strategy") else ""))
    L += ["", "## ledger", ""]
    for pid, p in sorted(data["ledger"].get("pools", {}).items()):
        L.append(f"- {p.get('name', pid)}（{pid}）: {p.get('initial', 0)}"
                 f" → **{p.get('current', 0)}** {p.get('unit','')}")
    L += ["", "| ch | pool | delta | subject | balance |", "|---|---|---|---|---|"]
    for t in data["ledger"].get("transactions", []):
        L.append(f"| {t.get('chapter','')} | {t.get('pool','')} | {t.get('delta','')}"
                 f" | {t.get('subject','')} | {t.get('balance_after','')} |")
    L += ["", "## synopsis", ""]
    if data["synopsis"].get("book_logline"):
        L.append(f"> {data['synopsis']['book_logline']}")
    entries = data["synopsis"].get("chapters", {})
    for _, tok, v in sorted((v.get("num", 0), k, v) for k, v in entries.items()):
        L.append(f"- {tok}《{v.get('title','') or '无题'}》：{v.get('synopsis','')}")
    out = book / "export" / "views"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "state_view.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path
