"""pack：单章上下文装配（P0 热 / P1 触发 / P2 冷索引）与 export 全书编译。

 pack 不做任何"相关性判断"——P1 触发 = beats 文本 × 注册别名表的确定性最长匹配；
递归注入只到第 2 层（防膨胀）；每层体积自报（budget_report）。export = 纯拼接/视图渲染。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, evidence, state

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False

PREV_TAIL_CHARS = 1000
SPINE_CAP = 10
POINTER_WINDOW = 10
PACK_TOKEN_CAP = 18000
MAX_P1_ENTITIES = 12
MAX_P1_INDIRECT = 5

FILE_INDEX_AREAS = [
    ("project.json", "书配置：模式/字数带/词表供参参数（见 config guide）"),
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


def _bible_core_anchors(book: Path) -> str:
    """提取 bible/project_bible.md 中的世界规则、战力标尺与核心势力分布（恒常注入 P0）。"""
    p = book / "bible" / "project_bible.md"
    if not p.is_file():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    sections = []
    current_title = None
    current_lines = []
    target_keywords = ("世界与规则", "境界", "标尺", "power scale", "势力与地理", "世界底层", "战力")

    for line in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            if current_title and current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append(f"### {current_title}\n{content}")
            title = m.group(2).strip()
            if any(kw in title.lower() for kw in target_keywords) and "偏离" not in title:
                current_title = title
                current_lines = []
            else:
                current_title = None
                current_lines = []
        elif current_title is not None:
            current_lines.append(line)

    if current_title and current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(f"### {current_title}\n{content}")

    return "\n\n".join(sections)



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
                # 修复：移除 \b 边界，\b 对中文无效，改用更宽松的匹配，兼容“第7章：”等中文写法
                for ln in text.splitlines():
                    if re.search(rf"(?:{re.escape(ch_tok)}|ch_{ch_num}|第\s*{ch_num}\s*章)\s*[:：]", ln):
                        ch_line = re.sub(rf"^[\s\-*·]*(?:{re.escape(ch_tok)}|ch_{ch_num}|第\s*{ch_num}\s*章)\s*[:：]\s*", "", ln).strip()
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
    """纯算术事实：到期/过期/闲置线、未澄清误会、style_guards、偏离清单、form 同款提示。"""
    out: list[str] = []
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
        try:
            plant_ch = int(g.get("plant_ch") or 0)
        except (ValueError, TypeError):
            plant_ch = 0
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
            try:
                plant_ch = int(k.get("plant_ch") or 0)
            except (ValueError, TypeError):
                plant_ch = 0
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
            gid = g.get("id", "LINE")
            gst = g.get("status", "")
            desc = g.get("name") or g.get("secret") or g.get("content") or ""
            desc_str = f"：{str(desc)[:28]}" if desc else ""
            touched.append(f"{gid}({gst}{desc_str})")
    if touched:
        block["lines"] = touched
    for f in ("holder", "location", "condition", "dossier"):
        if e.get(f):
            block[f] = e[f]
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
        "world_anchors": _bible_core_anchors(book),
        "beats": beats,
        "prev_tail": _prev_final_tail(book, ch_num),
        "hard_reminders": _hard_reminders(book, ch, ch_num),
    }
    payload: dict = {"chapter": ch, "lean": lean, "full": full, "p0": p0, "p1": None, "p2": None}

    lookup = evidence.entity_lookup(book, safe_aliases=True)
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
    seen_names = set()
    for name, aliases in lookup.items():
        counts = evidence.count_aliases(beats, aliases)
        total_c = sum(counts.values())
        is_present = name in present_set
        primary_hit = counts.get(name, 0) > 0
        if total_c > 0:
            if ch_num > 5 and name not in recent_entity_mentions and not is_present and not primary_hit:
                continue
            raw_hits.append((is_present, primary_hit, total_c, name))
            seen_names.add(name)
        elif is_present:
            # 强化：现场在场角色即便细纲未显式点名，也强制保底装配人物卡
            raw_hits.append((True, False, 1, name))
            seen_names.add(name)

    # 场景地点强保底：若当前地点包含某注册地点实体，也加入装配
    loc_str = str(cur["current"].get("location", ""))
    if loc_str:
        for name, aliases in lookup.items():
            if name not in seen_names and any(a in loc_str for a in aliases):
                ent = next((e for e in cur["entities"].get("entries", []) if e.get("name") == name), None)
                if ent and ent.get("type") == "place":
                    raw_hits.append((False, True, 1, name))
                    seen_names.add(name)

    raw_hits.sort(key=lambda x: (not x[0], not x[1], -x[2], x[3]))
    hits = [name for _, _, _, name in raw_hits[:MAX_P1_ENTITIES]]

    p1: dict = {"entities": [], "indirect": [], "spine": []}
    if not lean:
        for name in hits:
            p1["entities"].append(_entity_block(book, name, cur, cur["lines"], full))
        injected = " ".join(b["summary"] for b in p1["entities"])
        indirect_cands = []
        hop_added = set()
        if _HAS_NX and cur["entities"].get("entries"):
            G = nx.Graph()
            ent_map = {}
            for e in cur["entities"]["entries"]:
                n_name = e.get("name")
                if not n_name:
                    continue
                ent_map[n_name] = e
                G.add_node(n_name, summary=str(e.get("summary", ""))[:60])
            for n_name, e in ent_map.items():
                holder = e.get("holder")
                if holder and holder in G:
                    G.add_edge(n_name, holder, rel="holder")
                faction = e.get("faction")
                if faction and faction in G:
                    G.add_edge(n_name, faction, rel="faction")
            for h in hits:
                if h in G:
                    for nbr in G.neighbors(h):
                        if nbr not in hits and nbr not in hop_added:
                            hop_added.add(nbr)
                            summary = G.nodes[nbr].get("summary", "")
                            sum_str = f"：{summary}" if summary else ""
                            indirect_cands.append(f"{nbr}（关联）{sum_str}")

        for name in sorted(set(lookup) - set(hits) - hop_added):
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
                if f.is_symlink():
                    continue
                try:
                    # 越界检查
                    if f.resolve() != book and book.resolve() not in f.resolve().parents:
                        continue
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

    # 超预算硬裁：优先裁 P2 冷索引，修复计数失真
    if budget["over_budget"] and payload.get("p2"):
        original_len = len(payload["p2"].get("file_index", []))
        fi = payload["p2"].get("file_index", [])
        # 对齐渲染口径：render 只渲染前25条，超出部分先截断并计入裁剪
        trimmed_due_to_render_cap = 0
        if len(fi) > 25:
            trimmed_due_to_render_cap = len(fi) - 25
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
        total_trimmed = trimmed_due_to_render_cap + trimmed
        if total_trimmed:
            budget["trimmed_file_index"] = total_trimmed
            # 区分两种裁剪来源，信息更准确
            parts = []
            if trimmed_due_to_render_cap:
                parts.append(f"渲染口径对齐截断 {trimmed_due_to_render_cap} 条（>25）")
            if trimmed:
                parts.append(f"超预算硬裁 {trimmed} 条")
            budget["trim_note"] = "；".join(parts) + "（P0/P1 保留）"
            if original_len > 25:
                budget["original_file_index_count"] = original_len
        if budget["over_budget"]:
            budget["hard_cap_breached"] = True
            note = f"冷索引已裁空仍超预算（P0/P1 保留，超出 {budget['total'] - budget['cap']} tok）"
            budget["trim_note"] = f"{budget['trim_note']}；{note}" if budget.get("trim_note") else note

    payload["budget_report"] = budget
    payload["hits"] = sorted(hits)
    return payload


def render_layer(name: str, obj, full: bool = False) -> str:
    if obj is None:
        return ""
    if name == "p0":
        lines = []
        for k, v in obj["current"].items():
            if k == "loadout" and isinstance(v, dict):
                friendly = {"cultivation": "主修", "movement": "身法", "attack": "杀招",
                            "trump_card": "底牌", "equipped_items": "装备"}
                parts = []
                for sk, sv in v.items():
                    if sv in ("", [], None):
                        continue
                    label = friendly.get(sk, sk)
                    val = ",".join(sv) if isinstance(sv, list) else str(sv)
                    parts.append(f"{label}:{val}")
                lines.append(f"loadout: {' | '.join(parts)}")
            else:
                lines.append(f"{k}: {v}")
        if obj.get("volume_phase"):
            lines += ["", "=== 本卷阶段航标 ===", f"- {obj['volume_phase']}"]
        if obj.get("world_anchors"):
            lines += ["", "=== 世界底层与战力标尺 ===", obj["world_anchors"]]
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
    if b.get("trimmed_file_index"):
        out += [f"trim: 已裁 P2 冷索引 {b['trimmed_file_index']} 条（{b.get('trim_note','')}）"]
    if b.get("hard_cap_breached"):
        out += ["⚠️ 冷索引已裁空仍超预算，P0/P1 已保留，超限部分需主控手动精简 beats"]
    return "\n".join(out)


def open_file(book: Path, rel: str) -> dict:
    p = common.safe_child_path(book, rel)
    if not p.is_file():
        raise ValueError(f"--open 目标不存在: {rel}")
    return {"path": rel, "text": p.read_text(encoding="utf-8", errors="replace")}


def _safe_filename(name: str, fallback: str = "book") -> str:
    s = re.sub(r"[\\/<>\"|?*\x00-\x1f]", "_", (name or "").strip())
    s = re.sub(r"\.\.+", "_", s)
    s = re.sub(r"\s+", "_", s).strip("._")
    return s or fallback


def export_txt(book: Path) -> Path:
    proj = common.load_json(book / "project.json", default={}) or {}
    title = proj.get("title") or book.name
    parts = [f"# {title}\n"]
    if proj.get("genre"):
        parts.append(f"> {proj['genre']} · 引擎编译\n")
    ms = book / "manuscript"
    if not ms.is_dir():
        raise ValueError(f"manuscript 目录不存在: {ms}")
    vols = sorted({f.relative_to(ms).parts[0] for f in ms.glob("*/final/ch_*.md") if len(f.relative_to(ms).parts) >= 2})
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
    path = out / f"{_safe_filename(title)}.txt"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def export_views(book: Path) -> Path:
    def _cell(v) -> str:
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
