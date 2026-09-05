"""章节流转命令：pack / beats / evidence / check / review / critic / graph / export / dashboard。"""
from __future__ import annotations

import json
import re
import sys

from .. import checks, common, evidence, state, dashboard
from .. import pack as pack_mod
from .. import graph as graph_mod
from .. import cockpit as cockpit_mod

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    _HAS_RICH = True
    console = Console()
except ImportError:
    _HAS_RICH = False
    console = None

from ._shared import _norm_ch, ws_gate


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------
def cmd_pack(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    ch = None
    if args.chapter:
        ch = _norm_ch(args.chapter)
        if ch is None:
            print(f"❌ 无法解析章节编号: {args.chapter!r}（示例: 6 或 ch_006）")
            return 2
    try:
        if ch is None and not args.open_path:
            print("❌ pack 需要章节号（如 pack ch_006），或仅 --open <相对路径> 取原文")
            return 2
        payload = pack_mod.build_pack(book, ch, lean=args.lean, full=args.full) if ch else {"chapter": None}
        if args.open_path:
            payload["opened"] = pack_mod.open_file(book, args.open_path)
    except ValueError as exc:
        print(f"❌ {exc}")
        return 1
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if ch is None:
            o = payload["opened"]
            print(f"📂 {o['path']}\n\n{o['text']}")
        else:
            print(pack_mod.render_pack(payload))
    return 0



# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------
def cmd_evidence(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    kind, rest = args.kind, list(args.args or [])
    if kind == "all":
        if rest:
            print("❌ evidence all 不接受参数（聚合全书五件套）")
            return 2
        payload = {"kind": "all", "words": evidence.words(book), "style": evidence.style(book),
                   "form": evidence.form_distribution(book), "dup": evidence.dup(book),
                   "gaps": evidence.gaps(book)}
    elif kind == "file":
        if len(rest) not in (1, 2):
            print("❌ evidence file 需要 <相对路径> [章节号(并入该章 editor_extra)]")
            return 2
        if len(rest) == 2 and _norm_ch(rest[1]) is None:
            print(f"❌ 无法解析章节编号: {rest[1]!r}（示例: 6 或 ch_006）")
            return 2
        payload = evidence.file_stats(book, rest[0], rest[1] if len(rest) == 2 else None)
        if payload.get("error"):
            print(f"❌ {payload['error']}")
            return 1
    elif kind in ("gaps", "words"):
        if rest:
            print(f"❌ evidence {kind} 不接受参数，收到: {rest}")
            return 2
        payload = evidence.gaps(book) if kind == "gaps" else evidence.words(book)
    elif kind == "names":
        if rest:
            print(f"❌ evidence names 不接受参数，收到: {rest}")
            return 2
        payload = evidence.names(book)
    elif kind in ("candidates", "prev"):
        if len(rest) != 1 or _norm_ch(rest[0]) is None:
            print(f"❌ evidence {kind} 需要章节号（如: evidence {kind} ch_007）")
            return 2
        ch = _norm_ch(rest[0])
        payload = evidence.candidates(book, ch) if kind == "candidates" \
            else evidence.prev_contrast(book, ch)
        if payload.get("error"):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
    elif kind == "mentions":
        if len(rest) > 1:
            print("❌ evidence mentions 至多一个实体名（省略=注册表总览）")
            return 2
        payload = evidence.mentions(book, rest[0] if rest else None)
        if payload.get("unknown"):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
    else:
        if len(rest) > 1:
            print(f"❌ evidence {kind} 至多一个章节参数")
            return 2
        ch = None
        if rest:
            ch = _norm_ch(rest[0])
            if ch is None:
                print(f"❌ 无法解析章节编号: {rest[0]!r}（示例: 6 或 ch_006）")
                return 2
        payload = evidence.dup(book, ch) if kind == "dup" else evidence.style(book, ch)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0



# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
def cmd_check(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    report = checks.run_checks(book)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print(f" 🩺 [体检] {book.name}")
        print("=" * 70)
        for e in report["errors"]:
            print(f" ❌ [{e['code']}] {e['msg']}")
            if e.get("remedy"):
                print(f"    💡 [自愈方案] {e['remedy']}")
        for w in report["warnings"]:
            print(f" ⚠️ [{w['code']}] {w['msg']}")
            if w.get("remedy"):
                print(f"    💡 [建议处理] {w['remedy']}")
        for i in report.get("infos", []):
            print(f" ℹ️ [{i['code']}] {i['msg']}")
        if report.get("onboarding"):
            print(" 📋 新书 Stage 0 待办：填实 bible/ 与 outlines/ 中的 {{slot:}} 后体检自动转绿"
                  "（开写后未填槽位将恢复阻断）")
        if not report["errors"] and not report["warnings"]:
            print(" ✅ 无事实级问题")
        print(f" 汇总：errors {len(report['errors'])} ｜ warnings {len(report['warnings'])}"
              f" ｜ infos {len(report.get('infos', []))}"
              f" ｜ 定稿章数 {report['stats'].get('final_chapters', 0)}")
    return 0 if report["ok"] else 1



# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------
def _render_review_md(d: dict) -> str:
    qb = d["quote_balance"]
    names = "；".join(f"{e['name']}（别名：{'、'.join(e['aliases'])}）" if e["aliases"] else e["name"]
                     for e in d["proper_names"]) or "（注册表为空）"
    bal = "、".join(f"{p.get('name', pid)}（{pid}）: {p.get('current', 0)} {p.get('unit', '')}".rstrip()
                   for pid, p in sorted(d["ledger_now"].items())) or "（无池）"
    L = [f"# {d['chapter']} 校对注记", ""]
    L += ["<!-- 骨架由 `studio review new` 生成：机器数据已预填，结果与证据由主控填写。",
          "     每条结论要证据：正文引文片段，或 evidence 输出（字段名+数值）——无证据的打钩=未审。",
          "     -->", ""]
    L += ["## editor 回话", "", "<!-- 粘贴 editor 交付回话（重铸了什么/为什么，三到五行） -->", ""]
    L += ["## 六项机械核对", ""]
    L += ["### 1. 错别字", "- 结果：", ""]
    L += ["### 2. 标点配对",
          f"- 机器计数：「={qb['「']} 」={qb['」']} “={qb['“']} ”={qb['”']} 『={qb['『']} 』={qb['』']}"
          "（全章计数；是否配对由人判）",
          "- 结果：", ""]
    L += ["### 3. 专名与 entities 写法一致",
          f"- 专名表：{names}",
          f"- 章末仍在场（current）：{'、'.join(d['present']) if d['present'] else '（未声明）'}",
          "- 结果：", ""]
    L += ["### 4. 数字与 ledger current 相符",
          f"- 当前余额：{bal}",
          "- 结果：", ""]
    L += ["### 5.「必须保留」在位"]
    if d["must_keep"]:
        L += ["- 本章清单（自 beats 提取）："]
        L += [f"  - {s}" for s in d["must_keep"]]
    else:
        L += ["- 本章清单（自 beats 提取）：（beats 无「必须保留」节内容）"]
    L += ["- 结果：", ""]
    L += ["### 6. 格式残留",
          f"- 机器扫描：{{{{slot}}}}={d['residue']['slot']} ｜ candidate_*={d['residue']['candidate']}",
          "- 结果：", ""]
    L += ["## 验收", ""]
    if d["acceptance"]:
        L += ["<!-- 逐条回答，格式：N. ✓/✗ + 证据（正文引文「…」或 evidence 字段=数值，如 total=2、cjk=3120） -->"]
        for i, item in enumerate(d["acceptance"], 1):
            L.append(f"{i}. {item} ")
        L.append("")
    else:
        L += ["（beats 无「验收」节——review_gate 不拦，但建议补验收条目）", ""]
    return "\n".join(L) + "\n"


def cmd_review(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    if getattr(args, "rev_action", None) != "new":
        print("❌ review 需要 new 子命令，如: python studio.py review new ch_007")
        return 2
    n = common.chapter_token_to_num(args.chapter)
    if n is None:
        print(f"❌ 无法解析章节号: {args.chapter}")
        return 2
    ch = f"ch_{n:03d}"
    try:
        data = checks.review_skeleton(book, ch)
    except ValueError as exc:
        print(f"❌ {exc}")
        return 1
    md = _render_review_md(data)
    if getattr(args, "write", False):
        dest = book / "log" / "review" / f"{ch}.md"
        if dest.exists():
            print(f"❌ {dest} 已存在——注记是主控工件，拒绝覆盖（请手工编辑）")
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md, encoding="utf-8")
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch, "written": str(dest.relative_to(book))}, ensure_ascii=False))
        else:
            print(f"🧾 校对注记骨架已写入: {dest}")
            print("   填写「六项核对」结果与「## 验收」逐条 ✓/✗+证据后，再组装提案并 sync。", file=sys.stderr)
        return 0
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(md)
    return 0



# ---------------------------------------------------------------------------
# beats
# ---------------------------------------------------------------------------
def _consistency_section(book, n: int, cur: dict, ents: list[dict], lines_st: dict,
                         plan_line: str = "") -> str:
    """beats「本章一致性速查」：实体名册（含既有别名）+ KNO 知情差边界（引擎自动注入）。

    beats 是唯一同时被 Drafter / Editor / Reader 准读的文件——把账本记忆投递进 beats，
    即可在不动权限网关的前提下修复 Reader 的实体盲区（防别名分裂/另立新名），并防知情差穿帮。
    名册来源：主角 + 章末在场 + 到期线涉及实体 + 卷纲「当章预定规划」点名实体（防大纲回归角色漏网）。
    """
    proj = common.load_json(book / "project.json", default={}) or {}
    protagonist = str(proj.get("protagonist", "")).strip()
    ent_map = {}
    for e in ents or []:
        if isinstance(e, dict) and e.get("name"):
            ent_map[str(e["name"])] = e

    def _resolve(name: str):
        e = ent_map.get(name)
        if e:
            return e
        for ent in ent_map.values():
            if name and name in [str(a) for a in (ent.get("aliases") or [])]:
                return ent
        return None

    roster: list[dict] = []
    seen: set[str] = set()

    def _push(ent):
        if ent and ent.get("name") not in seen and len(seen) < 15:
            seen.add(ent["name"])
            roster.append(ent)

    _push(ent_map.get(protagonist))
    for name in (cur.get("present_characters") or []):
        _push(_resolve(str(name)))
    for arr in ("foreshadows", "misunderstandings", "knowledge"):
        for g in (lines_st or {}).get(arr, []):
            if str(g.get("status", "")).strip().lower() in ("resolved", "revealed"):
                continue
            t = g.get("target_ch")
            if not (isinstance(t, int) and t <= n + 3):
                continue
            blob = " ".join(str(g.get(k, "")) for k in
                            ("name", "content", "plan", "parties", "secret", "note"))
            for ename, ent in ent_map.items():
                if ename in seen:
                    continue
                if ename in blob or any(a and a in blob for a in (ent.get("aliases") or [])):
                    _push(ent)
    if plan_line:
        for ename, ent in ent_map.items():
            if ename in seen:
                continue
            if ename in plan_line or any(a and a in plan_line for a in (ent.get("aliases") or [])):
                _push(ent)

    kno_list = [k for k in (lines_st or {}).get("knowledge", [])
                if str(k.get("status", "")).strip().lower() != "revealed"]
    kno_list.sort(key=lambda k: -(k.get("weight") if isinstance(k.get("weight"), int) else 1))
    if not roster and not kno_list:
        return ""
    out = ["## 本章一致性速查（引擎自动注入 · 主控可增删）", ""]
    if roster:
        out += ["### 实体名册（含既有别名——正文沿用既有写法，严禁另立新名碎片化实体）", ""]
        for ent in roster:
            aliases = "、".join(str(a) for a in (ent.get("aliases") or []) if a)
            name_part = f"{ent['name']}（别名：{aliases}）" if aliases else str(ent["name"])
            # QA P2-15：截断统一带省略号（无省略号硬截断会丢关键信息且像坏句）
            summary = _clip(str(ent.get("summary", "") or ""), 60)
            out.append(f"- {name_part} ｜ {ent.get('type', 'other')} ｜ {summary}")
        out.append("")
    if kno_list:
        out += ["### 知情差边界（KNO 未揭示——对手戏严防「不该知道却说漏」穿帮）", ""]
        for k in kno_list[:6]:
            secret = _clip(str(k.get("secret", "")), 60)
            note = _clip(str(k.get("note", "") or "保密中"), 60)
            out.append(f"- [{k.get('id', 'KNO')}] 秘密：{secret} ｜ 知情边界：{note}")
        out.append("")
    return "\n".join(out)


def _clip(s: str, n: int) -> str:
    """定长截断并带省略号（QA P2-15）。"""
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def cmd_beats(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    ch = getattr(args, "chapter", None)
    if not ch:
        latest = common.latest_chapter_number(book, "final") or 0
        ch = f"ch_{latest + 1:03d}"
    n = common.chapter_token_to_num(ch)
    if not n:
        print(f"❌ 无法解析章节号: {ch!r}")
        return 2
    tok = f"ch_{n:03d}"

    vol_str = "vol_01"
    for vdir in sorted((book / "outlines").glob("vol_*")):
        otext = (vdir / "outline.md").read_text(encoding="utf-8", errors="ignore") if (vdir / "outline.md").is_file() else ""
        m = re.findall(r"ch[_\-](\d{1,4})", otext)
        if m and int(m[0]) <= n <= int(m[-1]):
            vol_str = vdir.name
            break

    beats_path = book / "outlines" / vol_str / "beats" / f"{tok}.md"
    if getattr(args, "write", False) and beats_path.exists() and not getattr(args, "force", False):
        print(f"❌ {tok} beats 细纲已存在: {beats_path}（覆盖请加 --force）")
        return 1
    if getattr(args, "write", False) and common.find_chapter_files(book, "final", tok):
        print(f"⚠️ 该章已有定稿（manuscript/*/final/{tok}.md）——本次写入/覆盖细纲后，"
              f"正文与任务书可能版本漂移；若为回溯修订，请同步核对 final 与提案修订通道（timeline 事件修订 / synopsis 跨章修订）")

    proj = common.load_json(book / "project.json", default={}) or {}
    protagonist = proj.get("protagonist", "主角名")

    # QA P8：form 默认值不再硬编码——上一章用了默认章型时切换推荐值，
    # 防「连续同章型无理由」在脚手架阶段就已埋雷
    default_form = "暗流汇聚"
    if n > 1:
        for pf in common.find_chapter_files(book, "beats", n - 1):
            prev_fm = common.parse_front_matter(pf.read_text(encoding="utf-8", errors="replace"))
            prev_form = str(prev_fm.get("form", "")).strip()
            if prev_form:
                for alt in ("危机逼近", "生死博弈", "战后清点", "暗流汇聚"):
                    if alt != prev_form:
                        default_form = alt
                        break
            break

    milestone = pack_mod._volume_phase_milestone(book, n)

    try:
        cur = state.load_state(book, "current")
    except (ValueError, OSError):
        cur = {}  # 现场快照不可用：脚手架相关注入留空
    sit = cur.get("situation", "")

    try:
        lines_st = state.load_state(book, "lines")
    except (ValueError, OSError):
        lines_st = {}  # 线索账本不可用：到期区留默认占位
    try:
        ents_st = state.load_state(book, "entities").get("entries", [])
    except (ValueError, OSError):
        ents_st = []  # 实体账本不可用：名册留空

    due_lines_str = ""
    try:
        lines_st = state.load_state(book, "lines")
        due_items = []
        for g in lines_st.get("foreshadows", []):
            if str(g.get("status", "")).lower() != "resolved" and g.get("target_ch") == n:
                due_items.append(f"- {g.get('id')}（{g.get('name','')}）：本章到期，安排回收或回响")
        for m in lines_st.get("misunderstandings", []):
            if str(m.get("status", "")).lower() != "resolved" and m.get("target_ch") == n:
                due_items.append(f"- {m.get('id')}（{m.get('content','')[:24]}）：本章到期，安排澄清或激化")
        for k in lines_st.get("knowledge", []):
            if str(k.get("status", "")).lower() != "revealed" and k.get("target_ch") == n:
                due_items.append(f"- {k.get('id')}（{k.get('secret','')[:24]}）：本章计划揭示")
        if due_items:
            due_lines_str = "\n".join(due_items)
    except (ValueError, OSError):
        pass  # 线索账本不可用：到期区留默认占位
    if not due_lines_str:
        due_lines_str = "- （根据大纲按需 plant 新线或维持现状）"

    tmpl_path = common.project_root() / "templates" / "beats.md"
    if not tmpl_path.is_file():
        print(f"❌ 细纲模板缺失: {tmpl_path}")
        return 1

    text = tmpl_path.read_text(encoding="utf-8")
    text = text.replace("{{slot:chapter_id}}", tok)
    text = text.replace("{{slot:vol_id}}", vol_str)
    text = text.replace("{{slot:form|暗流汇聚}}", default_form)
    text = text.replace("{{slot:protagonist|主角名}}", protagonist)
    text = text.replace("{{slot:tension_curve|动态起伏}}", "危机逼近 → 试探博弈 → 动作破局")
    text = text.replace("{{slot:tension_score|6}}", "6")
    text = text.replace("{{slot:stage_mode|Simmering}}", "Simmering")
    # QA P7：「所属阶段 + 上章现场」注入——此前 replace 的模板标记不存在，属静默 no-op 死代码；
    # 现在模板补了标记，并保留锚点回退，任何路径注入失败都走 stderr 警告（绝不静默）
    coord_block = (f"- **所属阶段**：{milestone or '（未匹配到分卷阶段，请核对 outlines/*/outline.md）'}\n"
                   f"- **上章现场**：{str(sit).strip() or '（暂无现场快照，按首章/转场处理）'}")
    coord_marker = "<!-- 双方不可退让的核心诉求与冲突点 -->"
    if coord_marker in text:
        text = text.replace(coord_marker, coord_block)
    elif "- **本章核心戏剧目标**：" in text:
        # 旧模板（无标记）回退：锚定「本章核心戏剧目标」行上方注入
        text = text.replace("- **本章核心戏剧目标**：",
                            coord_block + "\n- **本章核心戏剧目标**：", 1)
    else:
        # 兜底：frontmatter 之后的正文独立块 + stderr 明示（QA P7：注入失败必须可见）。
        # 不能 prepend 到最顶——frontmatter 的 --- 必须保持首行
        block = f"## 本章坐标（引擎自动注入 · 可改）\n\n{coord_block}\n\n"
        fm_close = text.find("\n---", 3) if text.startswith("---") else -1
        insert_at = text.find("\n## ", fm_close + 1 if fm_close > 0 else 0)
        if insert_at > 0:
            text = text[:insert_at] + "\n" + block + text[insert_at:]
        else:
            text = block + text
        print("⚠️ beats 脚手架「所属阶段/上章现场」注入：模板标记与锚点均缺失，"
              "已回退到 frontmatter 后独立块——请人工核对位置", file=sys.stderr)
    text = re.sub(r"- GUN-XXX[^\n]*\n- KNO-XXX[^\n]*\n- MIS-XXX[^\n]*", due_lines_str, text)

    # 一致性速查注入：实体名册（含别名，含卷纲规划行点名实体）+ KNO 知情差边界
    plan_line = ""
    m_plan = re.search(r"当章预定规划[:：](.+)", milestone or "")
    if m_plan:
        plan_line = m_plan.group(1).strip()
    cons_section = _consistency_section(book, n, cur, ents_st, lines_st, plan_line=plan_line)
    if cons_section:
        text = text.replace("## 本章新登场实体速写", cons_section.rstrip() + "\n\n## 本章新登场实体速写")

    algo_str = ""
    try:
        algo_items = cockpit_mod.get_algorithmic_guidance(book, n)
        if algo_items:
            algo_str = "<!-- ⚙️ [确定性算法引擎动态制导胶囊]\n" + "\n".join(f"     - {item}" for item in algo_items) + "\n-->\n\n"
        else:
            algo_str = "<!-- ⚙️ [确定性算法制导] 角色登场密度均衡，张力波浪处于健康区间。 -->\n\n"
    except (ValueError, OSError):
        algo_str = ""  # 制导胶囊不可用：留静态占位

    if algo_str:
        target_marker = "<!-- 明确本章核心事件与矛盾推进，全篇采用直白好懂的大白话推进 -->"
        text = text.replace(target_marker, f"{algo_str}{target_marker}")

    if getattr(args, "write", False):
        beats_path.parent.mkdir(parents=True, exist_ok=True)
        common.atomic_write_text(beats_path, text)
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "written": beats_path.relative_to(book).as_posix()},
                             ensure_ascii=False))
        else:
            print(f"✅ 已生成 {tok} 细纲任务书脚手架：{beats_path.relative_to(book).as_posix()}")
        return 0
    else:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "scaffold": text}, ensure_ascii=False, indent=2))
        else:
            print(f"# === {tok} 细纲任务书脚手架（加 --write 直接落盘）===\n")
            print(text)
        return 0



# ---------------------------------------------------------------------------
# critic
# ---------------------------------------------------------------------------
def cmd_critic(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    ch_arg = getattr(args, "chapter", None)
    if not ch_arg:
        latest = common.latest_chapter_number(book, "final") or 1
        ch_arg = f"ch_{latest:03d}"
    n = common.chapter_token_to_num(ch_arg)
    if not n:
        print(f"❌ 无法解析章节号: {ch_arg!r}")
        return 2
    tok = f"ch_{n:03d}"
    critic_file = book / "log" / "critic" / f"{tok}.md"

    if critic_file.is_file():
        text = critic_file.read_text(encoding="utf-8", errors="ignore")
        # QA P2-7：骨架明示为「未评测」，不再以正式报告的口吻回显
        is_skeleton = "SKELETON" in text[:400]
        panel_title = (f"🧐 [催更便签骨架 · 未评测（Stage 4B 待 Critic 子代理改写）] {tok}"
                       if is_skeleton else f"🧐 [老白读者催更便签] {tok}")
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "skeleton": is_skeleton, "report": text},
                             ensure_ascii=False))
        elif _HAS_RICH and console:
            console.print(Panel(
                Markdown(text),
                title=f"[bold gold1]{panel_title}[/bold gold1]",
                border_style="cyan",
                padding=(1, 2)
            ))
        else:
            print("======================================================================")
            print(f" {panel_title}")
            print("======================================================================")
            print(text)
        return 0

    final_files = common.find_chapter_files(book, "final", n)
    if not final_files:
        print(f"❌ 未找到 {tok} 的定稿（final），无法进行读者评测（需先由 Editor 定稿）")
        return 1

    final_text = final_files[-1].read_text(encoding="utf-8", errors="ignore")
    words = common.cjk_count(final_text)
    hook_info = evidence.detect_chapter_hook(final_text, evidence.hook_words(book))

    # 前情记忆（追更老白脑中）：取当前现场快照（Stage 4 跑在 sync 前 = 上一章末状态）
    memory_lines = []
    try:
        cur = state.load_state(book, "current")

        def _mem(label, key, sep="；"):
            v = cur.get(key)
            if isinstance(v, str) and v.strip():
                memory_lines.append(f"- **{label}**：{v.strip()[:40]}")
            elif isinstance(v, list) and v:
                memory_lines.append(f"- **{label}**：{sep.join(str(x) for x in v)[:60]}")

        where = "｜".join(x for x in (str(cur.get("time") or "").strip(),
                                      str(cur.get("location") or "").strip()) if x)
        if where:
            memory_lines.append(f"- **时地**：{where[:60]}")
        _mem("伤势", "injury")
        _mem("处境", "situation")
        _mem("心境", "mood")
        _mem("目标", "goal")
        _mem("悬顶危机", "active_pressures")
        _mem("上章余震", "aftershock")
        _mem("在场角色", "present_characters")
    except (ValueError, FileNotFoundError):
        memory_lines = ["- （暂无前情记忆：现场快照不可用，按首章读者处理）"]
    memory_block = "\n".join(memory_lines) if memory_lines else "- （无显著前情记忆）"

    skeleton = f"""# 第{n}章 老白读者催更便签（SKELETON 未评测 · 引擎预填骨架）

<!-- ⚠️ SKELETON：本文件由引擎预填机械数据与前情记忆，所有「（待评）」字段必须由
     Stage 4B Critic 子代理盲审后改写；在 Critic 交卷前，本文件不视为正式便签，
     cockpit 也不将其计为 Stage 4B 完成。 -->

- 💬 **本章体感**：（待评）
- 🌊 **阅读疲劳度**：（待评——紧绷/松弛？下章该爆发/蓄水还是日常清点缓冲？）
- 🔍 **伏笔与信息差**：（待评——暗线透光度如何？是否藏太深快被读者遗忘？）
- 🌡️ **主角活人感**：（待评——有无松弛幽默的活人味？有无滑向冷酷装逼/说教AI的苗头？）
- 💖 **角色路人缘**：（待评——女主/重要配角/反派的真实路人缘与好感度走向）
- 🚩 **连续性红旗**：（待评——若有：与前情记忆冲突的断戏感，最多 2 条且必须引用下方记忆字段值）

## 🧠 前情记忆（追更老白脑中 · 来自 state/current.json 快照）
{memory_block}

## 📊 机械参考数据（引擎只出数，零裁决）
- **评测章节**：{tok}
- **字数统计**：{words} 汉字
- **章末钩子**：{hook_info.get('type', '普通收尾')}（{hook_info.get('detail', '')[:30]}）
"""
    if getattr(args, "write", False):
        critic_file.parent.mkdir(parents=True, exist_ok=True)
        common.atomic_write_text(critic_file, skeleton)
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "skeleton": True,
                              "written": critic_file.relative_to(book).as_posix()},
                             ensure_ascii=False))
        else:
            print(f"✅ 催更便签骨架（SKELETON）已落盘: {critic_file.relative_to(book).as_posix()}")
            print("   ⚠️ 骨架不替代 Stage 4B 评审：请派发 Critic 子代理盲审改写后再进下章细纲（cockpit 不把骨架计为已完成）。")
        return 0
    else:
        print(f"ℹ️ {tok} 尚未执行老白读者评测。")
        print("   正道：主控在 Stage 4 派发子代理 `Role: 'Critic'` 并行评审（零脚本、盲审便签）。")
        print(f"   引擎辅助：python studio.py critic {tok} --write 可落盘预填骨架（SKELETON，供子代理改写，不计完成）。")
        return 0



# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------
def cmd_graph(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    return graph_mod.run_graph(
        book,
        getattr(args, "graph_action", None),
        as_json=bool(getattr(args, "json", False)),
        source=getattr(args, "source", ""),
        target=getattr(args, "target", ""),
        name=getattr(args, "name", ""),
        depth=getattr(args, "depth", 1),
    )


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def cmd_export(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    if not args.txt and not args.views:
        args.txt = args.views = True
    written = []
    try:
        if args.txt:
            written.append(pack_mod.export_txt(book))
        if args.views:
            written.append(pack_mod.export_views(book))
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ 导出失败: {exc}")
        return 1
    if args.json:
        print(json.dumps({"written": [str(p.relative_to(book)) for p in written]}, ensure_ascii=False))
    else:
        for p in written:
            size = len(p.read_text(encoding="utf-8"))
            print(f"📦 已导出: {p.relative_to(book)}（{size} 字符）")
    return 0


def cmd_dashboard(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    try:
        out_file = dashboard.export_dashboard(book)
    except Exception as exc:
        print(f"❌ 看板生成失败: {exc}")
        return 1
    if getattr(args, "json", False):
        print(json.dumps({"dashboard": str(out_file.relative_to(book)), "url": str(out_file.resolve())}, ensure_ascii=False))
    else:
        print("=" * 70)
        proj = common.load_json(book / "project.json", default={})
        print(f" 📊 [全景交互看板] 《{proj.get('title','')}》")
        print("=" * 70)
        print(f" 🌐 看板 HTML 文件已生成: {out_file.resolve()}")
        print("    可直接在浏览器打开预览人物关系网、伏笔看板与情绪心电图！")
        return 0


# ---------------------------------------------------------------------------
# ask / pov / calendar（只读取证三件套：写作前先问书，严禁凭记忆脑补）
# ---------------------------------------------------------------------------
def cmd_ask(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    query = str(getattr(args, "query", "") or "").strip()
    payload = evidence.ask(book, query)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if payload.get("error") else 0


def cmd_pov(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    payload = evidence.pov(book, str(getattr(args, "name", "") or ""))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if payload.get("error") else 0


def _calendar_payload(book, span: int) -> dict:
    """未来 N 章排产日历：到期线/危机时钟/阶段里程碑投影（advisory）。"""
    target = cockpit_mod._infer_active_chapter(book)
    start = common.chapter_token_to_num(target) or 1
    out: dict = {"kind": "calendar", "start": f"ch_{start:03d}", "span": span, "chapters": []}
    try:
        lines = state.load_state(book, "lines")
    except (ValueError, FileNotFoundError):
        lines = {}
    try:
        tl = state.load_state(book, "timeline")
    except (ValueError, FileNotFoundError):
        tl = {}
    resolved_status = {"foreshadows": "resolved", "misunderstandings": "resolved",
                       "knowledge": "revealed"}

    def _desc(g):
        return str(g.get("name") or g.get("content") or g.get("secret") or "")[:36]

    overdue = []
    for arr, kind in (("foreshadows", "伏笔"), ("misunderstandings", "误会"), ("knowledge", "知识线")):
        for g in lines.get(arr, []):
            t = g.get("target_ch")
            if (isinstance(t, int) and t < start
                    and str(g.get("status", "")).strip().lower() != resolved_status[arr]):
                overdue.append({"id": g.get("id"), "kind": kind, "target_ch": t, "desc": _desc(g)})
    if overdue:
        out["overdue_lines"] = overdue
    clocks_overdue = [{"name": c.get("name"), "target_ch": c.get("target_ch"),
                       "desc": str(c.get("desc", ""))[:40]}
                      for c in tl.get("clocks") or []
                      if str(c.get("status", "")).lower() == "active"
                      and isinstance(c.get("target_ch"), int) and c["target_ch"] < start]
    if clocks_overdue:
        out["overdue_clocks"] = clocks_overdue

    for n in range(start, start + span):
        tok = f"ch_{n:03d}"
        row: dict = {"chapter": tok,
                     "beats_planned": bool(common.find_chapter_files(book, "beats", tok))}
        phase = pack_mod._volume_phase_milestone(book, n)
        if phase:
            row["phase"] = phase
        due = []
        for arr, kind in (("foreshadows", "伏笔"), ("misunderstandings", "误会"), ("knowledge", "知识线")):
            for g in lines.get(arr, []):
                if (g.get("target_ch") == n
                        and str(g.get("status", "")).strip().lower() != resolved_status[arr]):
                    due.append({"id": g.get("id"), "kind": kind, "desc": _desc(g)})
        if due:
            row["due_lines"] = due
        clocks = [{"name": c.get("name"), "desc": str(c.get("desc", ""))[:40]}
                  for c in tl.get("clocks") or []
                  if str(c.get("status", "")).lower() == "active" and c.get("target_ch") == n]
        if clocks:
            row["clocks"] = clocks
        out["chapters"].append(row)
    out["notes"] = ["排产参考（advisory）：due_lines=预定本章结算的线；phase=卷阶段航标；兑付节奏归主控裁决。"]
    return out


def cmd_calendar(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    try:
        span = int(getattr(args, "span", None) or 5)
    except (TypeError, ValueError):
        span = 5
    span = max(1, min(span, 12))
    print(json.dumps(_calendar_payload(book, span), ensure_ascii=False, indent=2))
    return 0
