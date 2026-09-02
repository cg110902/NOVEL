"""pack：单章上下文装配（P0 热 / P1 触发 / P2 冷索引）与 export 全书编译。

 pack 不做任何"相关性判断"——P1 触发 = beats 文本 × 注册别名表的确定性最长匹配；
递归注入只到第 2 层（防膨胀）；每层体积自报（budget_report）。export = 纯拼接/视图渲染。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, evidence, state

PREV_TAIL_CHARS = 1000
PREV_TAIL_CHARS = 1000
SPINE_CAP = 10
POINTER_WINDOW = 10
PACK_TOKEN_CAP = 18000
MAX_P1_ENTITIES = 12
MAX_P1_INDIRECT = 5

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


def _volume_phase_milestone(book: Path, ch_num: int) -> str:
    """从 outlines/vol_XX/outline.md 自动提取当前章所属阶段的里程碑与阶段功能（P0 恒常注入）。"""
    outlines = sorted((book / "outlines").glob("*/outline.md"))
    for outline_path in outlines:
        try:
            text = outline_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        phases = re.findall(
            r"-\s*\*\*([^\n*]+?)\s*[（(]\s*(?:ch_?)?(\d+)\s*[—\-–~至到]+\s*(?:ch_?)?(\d+)\s*(?:[｜|]\s*([^\n*]+?))?[)）]\s*\*\*",
            text
        )
        for name, start_s, end_s, feat in phases:
            s_num, e_num = int(start_s), int(end_s)
            if s_num <= ch_num <= e_num:
                feat_str = f" ｜ {feat.strip()}" if feat else ""
                ch_tok = f"ch_{ch_num:03d}"
                ch_line = ""
                for ln in text.splitlines():
                    if re.search(rf"\b(?:{ch_tok}|ch_{ch_num}|第\s*{ch_num}\s*章)\b\s*[:：]", ln):
                        ch_line = re.sub(rf"^[\s\-*·]*\b(?:{ch_tok}|ch_{ch_num}|第\s*{ch_num}\s*章)\b\s*[:：]\s*", "", ln).strip()
                        break
                ch_plan = f"\n  - 当章预定规划：{ch_line}" if ch_line else ""
                return f"{name.strip()}（ch_{s_num:03d}—ch_{e_num:03d}{feat_str}）{ch_plan}"
    return ""


def _form_notice(book: Path, ch: str, ch_num: int) -> list[str]:
    notice = []
    beats_files = common.find_chapter_files(book, "beats", ch)
    if not beats_files:
        return notice
    cur_fm = common.parse_front_matter(beats_files[-1].read_text(encoding="utf-8", errors="replace"))
    prev_files = common.find_chapter_files(book, "beats", ch_num - 1) if ch_num > 1 else []
    if prev_files:
        prev_fm = common.parse_front_matter(prev_files[-1].read_text(encoding="utf-8", errors="replace"))
        if cur_fm.get("form") and cur_fm["form"] == prev_fm.get("form"):
            reason = ("form_reason 已给" if cur_fm.get("form_reason")
                      else "front-matter 缺 form_reason（check 将报错）")
            notice.append(f"form 与上章相同（{cur_fm['form']}）：{reason}")
    return notice


def _hard_reminders(book: Path, ch: str, ch_num: int) -> list[str]:
    """纯算术事实：到期/过期/闲置线、未澄清误会、style_guards、偏离清单、form 同款提示。

    容错说明：这里对 lines 台账损坏显式降级为"空台账"（而非抛错/静默兜底为默认值），
    属于 pack 这层"尽可能把上下文交给子代理"的有意例外——pack 的职责是装配提示，
    台账损坏应由 check/状态体检报错，不让它阻断"还能写的章"。"""
    out: list[str] = []
    # 危机时钟提醒（P0 倒计时压迫感注入）
    try:
        tl = state.load_state(book, "timeline")
        for clk in tl.get("clocks", []):
            if clk.get("status") in ("Defused", "Triggered", "Expired"):
                continue
            tch = clk.get("target_ch")
            if isinstance(tch, int):
                diff = tch - ch_num
                cname = clk.get("name", "未命名时钟")
                cdesc = f"（{clk.get('desc')}）" if clk.get("desc") else ""
                if diff < 0:
                    out.append(f"⏰【时钟逾期】危机「{cname}」已超期 {abs(diff)} 章（目标 ch_{tch:03d}）！{cdesc}")
                elif diff == 0:
                    out.append(f"🔥【时钟引爆】危机「{cname}」将在本章爆发！{cdesc}")
                elif diff <= 5:
                    out.append(f"⏰【时钟紧迫】危机「{cname}」距今仅剩 {diff} 章（将在 ch_{tch:03d} 结算）！{cdesc}")
    except ValueError:
        pass

    try:
        lines = state.load_state(book, "lines")
    except ValueError:
        lines = {"foreshadows": [], "misunderstandings": [], "knowledge": []}

    line_msgs: list[tuple] = []
    for g in lines.get("foreshadows", []):
        if g.get("status") == "Resolved":
            continue
        t = g.get("target_ch")
        plant_ch = int(g.get("plant_ch") or 0)
        idle = (ch_num - plant_ch) if plant_ch else 0
        sk = evidence.line_sort_key(g, "foreshadow")[1]
        gid, gname = g.get("id"), g.get("name", "")
        if isinstance(t, int) and t <= ch_num:
            tag = "🔥【本章引爆】" if t == ch_num else f"🚨【已逾期 {ch_num - t} 章】"
            line_msgs.append((0, sk, f"{tag} 伏笔 {gid}《{gname}》（target ch_{t:03d}，状态 {g.get('status')}）"))
        elif idle >= 10:
            line_msgs.append((1, sk, f"🚨【紧急催还伏笔】{gid}《{gname}》已闲置 {idle} 章未提及！本章 Beats 建议安排回响(remind)或闭环(resolve)"))
        elif isinstance(t, int) and 0 < t - ch_num <= 2:
            line_msgs.append((2, sk, f"⏳【即将到期】伏笔 {gid}《{gname}》距到期仅剩 {t - ch_num} 章（target ch_{t:03d}）"))
        elif idle >= 5:
            line_msgs.append((3, sk, f"🟡【伏笔回响提醒】{gid}《{gname}》已沉寂 {idle} 章，建议安排线索动静"))

    for m in lines.get("misunderstandings", []):
        if m.get("status") != "Resolved":
            t = m.get("target_ch")
            sk = evidence.line_sort_key(m, "misunderstanding")[1]
            if isinstance(t, int) and t <= ch_num:
                tag = "🔥【本章澄清】" if t == ch_num else f"🚨【已逾期 {ch_num - t} 章】"
                line_msgs.append((0, sk, f"{tag} 误会 {m['id']} 未澄清：{m.get('parties','')}（{m.get('content','')[:30]}）"))
            else:
                line_msgs.append((2, sk, f"误会 {m['id']} 未澄清：{m.get('parties','')}（{m.get('content','')[:30]}）"))

    for k in lines.get("knowledge", []):
        if k.get("status") != "Revealed":
            t = k.get("target_ch")
            plant_ch = int(k.get("plant_ch") or 0)
            idle = (ch_num - plant_ch) if plant_ch else 0
            sk = evidence.line_sort_key(k, "knowledge")[1]
            kid, ksecret = k.get("id"), str(k.get("secret", ""))[:24]
            if isinstance(t, int) and t <= ch_num:
                tag = "🔥【本章揭示】" if t == ch_num else f"🚨【已逾期 {ch_num - t} 章】"
                line_msgs.append((0, sk, f"{tag} 知识线 {kid}《{ksecret}》（target ch_{t:03d}，状态 {k.get('status')}）"))
            elif idle >= 10:
                line_msgs.append((1, sk, f"🚨【知识线沉寂】{kid}《{ksecret}》已闲置 {idle} 章"))
            elif isinstance(t, int) and 0 < t - ch_num <= 2:
                line_msgs.append((2, sk, f"⏳【即将揭示】知识线 {kid}《{ksecret}》距揭示仅剩 {t - ch_num} 章"))

    line_msgs.sort(key=lambda x: (x[0], x[1]))
    out.extend(msg for _, _, msg in line_msgs)
    proj = common.load_json(book / "project.json", default={}) or {}
    guards = [x for x in (proj.get("style_guards") or []) if isinstance(x, str) and x]
    if guards:
        out.append("style_guards 红线：" + "、".join(guards))
    out.extend(f"本书偏离：{d}" for d in _deviation_lines(book))
    out.extend(_form_notice(book, ch, ch_num))
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
    
    # 挂载高维实体属性
    for attr in ("realm", "faction", "life_status", "attitude"):
        if e.get(attr):
            block[attr] = e[attr]
    if e.get("charges") is not None:
        max_c = e.get("max_charges")
        block["charges"] = f"{e['charges']}/{max_c}" if max_c else str(e["charges"])

    touched = []
    alias = [name] + list(e.get("aliases", []))
    for g in (lines.get("foreshadows", []) + lines.get("misunderstandings", [])
              + lines.get("knowledge", [])):
        if g.get("status") in ("Resolved", "Revealed"):
            continue
        blob = " ".join(str(g.get(k, "")) for k in
                        ("name", "content", "plan", "parties", "truth", "secret", "note"))
        if any(a and a in blob for a in alias):
            touched.append(f"{g['id']}({g.get('status')})")
    if touched:
        block["lines"] = touched
    for f in ("holder", "location", "condition", "dossier"):
        if e.get(f):
            block[f] = e[f]
    # 随身清单：holder 指向本实体的在役道具（纯分组，物→人反查）
    carried = []
    for it in cur["entities"].get("entries", []):
        if it.get("type") != "item" or it.get("status") == "retired":
            continue
        if str(it.get("holder", "")) in alias:
            meta = [x for x in (it.get("location"), it.get("condition")) if x]
            if it.get("charges") is not None:
                meta.append(f"余{it['charges']}次")
            carried.append(f"{it['name']}（{'·'.join(meta)}）" if meta else str(it["name"]))
    if carried:
        block["carries"] = carried
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
        "volume_phase": _volume_phase_milestone(book, ch_num),
        "beats": beats,
        "prev_tail": _prev_final_tail(book, ch_num),
        "hard_reminders": _hard_reminders(book, ch, ch_num),
    }
    payload: dict = {"chapter": ch, "lean": lean, "full": full, "p0": p0, "p1": None, "p2": None}

    # 启用安全别名查找（停用词过滤副别名）
    lookup = evidence.entity_lookup(book, safe_aliases=True)
    
    # 统计最近 15 章出场的实体，供冷门实体过滤判定
    finals = evidence.final_chapters(book)
    recent_window = [c for c in finals if c[1] < ch_num][-15:]
    recent_entity_mentions = set()
    full_lookup = evidence.entity_lookup(book, safe_aliases=False)
    for _, _, text in recent_window:
        for name, aliases in full_lookup.items():
            if sum(evidence.count_aliases(text, aliases).values()) > 0:
                recent_entity_mentions.add(name)

    present_set = set(cur["current"].get("present_characters", []))
    raw_hits = []
    for name, aliases in lookup.items():
        counts = evidence.count_aliases(beats, aliases)
        total_c = sum(counts.values())
        if total_c > 0:
            is_present = name in present_set
            primary_hit = counts.get(name, 0) > 0
            # 若该实体近 15 章从未出场，且不在 present，且 Beats 未出现其完整主名（仅被别名模糊命中）→ 视为冷门过滤
            if ch_num > 5 and name not in recent_entity_mentions and not is_present and not primary_hit:
                continue
            raw_hits.append((is_present, primary_hit, total_c, name))

    # 排序：在场优先 > 主名命中优先 > 提及频次 > 名字
    raw_hits.sort(key=lambda x: (not x[0], not x[1], -x[2], x[3]))
    hits = [name for _, _, _, name in raw_hits[:MAX_P1_ENTITIES]]

    p1: dict = {"entities": [], "indirect": [], "spine": []}
    if not lean:
        for name in hits:
            p1["entities"].append(_entity_block(book, name, cur, cur["lines"], full))
        # 递归一层：注入内容再命中的新实体 → 只补一行摘要（深度 ≤2，最多 MAX_P1_INDIRECT 条）
        injected = " ".join(b["summary"] for b in p1["entities"])
        indirect_cands = []
        for name in sorted(set(lookup) - set(hits)):
            if sum(evidence.count_aliases(injected, lookup[name]).values()) > 0:
                ent = next((e for e in cur["entities"]["entries"] if e["name"] == name), {})
                indirect_cands.append(f"{name}：{str(ent.get('summary', ''))[:60]}")
        p1["indirect"] = indirect_cands[:MAX_P1_INDIRECT]
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
        # 先对齐渲染口径：render_layer 只渲染前 25 条，>25 的部分先截掉再逐条裁（P2-7，
        # 旧实现从尾部 pop，>25 时前 N 次 pop 对渲染与预算零影响，白裁且计数误导）
        if len(fi) > 25:
            fi = fi[:25]
        payload["p2"]["file_index"] = fi
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
        if budget["over_budget"]:
            # 冷索引裁空仍超限 → 显性标记，绝不静默（P0/P1 不裁是设计，但必须如实上报）
            budget["hard_cap_breached"] = True
            note = f"冷索引已裁空仍超预算（P0/P1 保留，超出 {budget['total'] - budget['cap']} tok）"
            budget["trim_note"] = f"{budget['trim_note']}；{note}" if budget.get("trim_note") else note

    payload["budget_report"] = budget
    payload["hits"] = sorted(hits)
    return payload


def render_layer(name: str, obj, full: bool = False) -> str:
    """预算自报用的确定性纯文本渲染（与 render_pack 同口径的简化版）。"""
    if obj is None:
        return ""
    if name == "p0":
        lines = []
        for k, v in obj["current"].items():
            if k == "loadout" and isinstance(v, dict):
                parts = []
                if v.get("cultivation"): parts.append(f"主修:{v['cultivation']}")
                if v.get("movement"): parts.append(f"身法:{v['movement']}")
                if v.get("attack"): parts.append(f"杀招:{v['attack']}")
                if v.get("trump_card"): parts.append(f"底牌:{v['trump_card']}")
                if v.get("equipped_items"): parts.append(f"装备:{','.join(v['equipped_items'])}")
                lines.append(f"loadout: {' | '.join(parts)}")
            else:
                lines.append(f"{k}: {v}")
        if obj.get("volume_phase"):
            lines += ["", "=== 本卷阶段航标 ===", f"- {obj['volume_phase']}"]
        lines += ["", "=== beats ===", obj["beats"], "", "=== 上章余温 ===", obj["prev_tail"],
                  "", "=== 硬提醒 ==="] + [f"- {m}" for m in obj["hard_reminders"]]
        return "\n".join(lines)
    if name == "p1":
        lines = []
        for b in obj["entities"]:
            extra_tags = []
            if b.get("realm"):
                extra_tags.append(b["realm"])
            if b.get("faction"):
                extra_tags.append(b["faction"])
            if b.get("life_status") and b["life_status"] != "alive":
                extra_tags.append(b["life_status"])
            if b.get("attitude"):
                extra_tags.append(f"立场:{b['attitude']}")
            if b.get("charges"):
                extra_tags.append(f"余{b['charges']}次")
            tag_str = f" | {', '.join(extra_tags)}" if extra_tags else ""
            lines.append(f"[{b['name']}|{b['type']}|{'章末在场' if b['on_stage'] else '章末不在'}{tag_str}] {b['summary']}")
            if b.get("carries"):
                lines.append(f"  随身: {', '.join(b['carries'])}")
            if b.get("lines"):
                lines.append(f"  挂线: {', '.join(b['lines'])}")
            if b.get("dossier"):
                lines.append(f"  恩怨羁绊: {b['dossier']}")
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
    def _cell(v) -> str:
        # markdown 表格单元格转义（P3-12）：竖线与换行会破表
        return str(v).replace("|", "\\|").replace("\n", " ")

    data = {key: state.load_state(book, key) for key in state.STATE_KEYS}
    L = ["# 状态视图（export --views 渲染；真值以 state/*.json 为准）", ""]
    L += ["## current", ""]
    for k, v in sorted(data["current"].items()):
        if v not in ("", [], None):
            L.append(f"- **{k}**: {v}")
    L += ["", "## entities", "", "| name | type | status | summary |", "|---|---|---|---|"]
    for e in data["entities"].get("entries", []):
        L.append(f"| {_cell(e.get('name',''))} | {_cell(e.get('type',''))} | {_cell(e.get('status',''))} | {_cell(e.get('summary',''))} |")
    L += ["", "## lines 台账", "", "| id | name/content | status | target_ch | 权重 |", "|---|---|---|---|---|"]
    for g in data["lines"].get("foreshadows", []):
        L.append(f"| {g['id']} | {_cell(g.get('name',''))} | {g.get('status','')} | {g.get('target_ch','')} | {g.get('weight','-')} |")
    for m in data["lines"].get("misunderstandings", []):
        L.append(f"| {m['id']} | {_cell(str(m.get('content',''))[:30])} | {m.get('status','')} | {m.get('target_ch','')} | {m.get('level','-')} |")
    for k in data["lines"].get("knowledge", []):
        L.append(f"| {k['id']} | {_cell(str(k.get('secret',''))[:30])} | {k.get('status','')} | {k.get('target_ch','')} | {k.get('weight','-')} |")
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
                 f" | {_cell(t.get('subject',''))} | {t.get('balance_after','')} |")
    L += ["", "## synopsis", ""]
    if data["synopsis"].get("book_logline"):
        L.append(f"> {data['synopsis']['book_logline']}")
    entries = data["synopsis"].get("chapters", {})
    for _, tok, v in sorted((v.get("num", 0), k, v) for k, v in entries.items()):
        L.append(f"- {tok}《{_cell(v.get('title','') or '无题')}》：{_cell(v.get('synopsis',''))}")
    out = book / "export" / "views"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "state_view.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path
