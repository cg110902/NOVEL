"""书级生命周期命令：init（脚手架）/ status / cockpit（态势）/ config（词表供参）。"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from .. import checks, common, errcodes, evidence, snapshot, state

from ._shared import SLOT_RE, _norm_ch, _resolve_and_validate, print_ws_not_found


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
TEMPLATE_MAP = {
    "project_bible.md": "bible/project_bible.md",
    "main_plot.md": "outlines/main_plot.md",
    "volume_outline.md": "outlines/vol_01/outline.md",
    "character_card.md": "characters/protagonist.md",
}


def _instantiate_templates(book: Path, slots: dict[str, str]) -> list[str]:
    tdir = common.project_root() / "templates"
    done = []
    for tpl, dest_rel in TEMPLATE_MAP.items():
        src = tdir / tpl
        if not src.is_file():
            continue
        text = src.read_text(encoding="utf-8")

        def _sub(m: re.Match) -> str:
            val = slots.get(m.group(1), "")
            return val if val else m.group(0)

        text = SLOT_RE.sub(_sub, text)
        dest = book / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        done.append(dest_rel)
    return done


def _init_workspace(arg: str) -> Path:
    p = Path(arg).expanduser()
    if p.is_absolute():
        resolved = common.resolve_workspace(arg)
        assert resolved is not None
        common.ensure_workspace_inside(resolved)
        return resolved
    rel = p
    if not rel.parts or rel.parts[0] != "workspace":
        rel = Path("workspace") / rel
    if rel.parts == ("workspace",):
        raise ValueError("-w 不能是 workspace 本身：请指定书目录，如 -w workspace/我的书")
    book = common.resolve_workspace(str(rel))
    assert book is not None
    common.ensure_workspace_inside(book)
    return book


def cmd_init(args) -> int:
    if not args.workspace:
        print('❌ init 需要 -w 指定书目录，如 -w workspace/我的书')
        return 2
    try:
        book = _init_workspace(args.workspace)
    except ValueError as exc:
        print(f"❌ {exc}")
        return 2
    _wr = common.workspace_root().resolve()
    if book.resolve() != _wr and _wr not in book.resolve().parents:
        print(f"❌ 书目录必须在 {_wr} 之下: {book}")
        return 2
    if book.exists() and any(book.iterdir()) and not (book / "project.json").exists():
        print(f"⛔ 目标目录非空且不是已登记的书，拒绝写入: {book}")
        return 1

    if (book / "project.json").exists():
        if args.clean:
            import shutil
            cleared = 0
            ms = book / "manuscript"
            wipe_final = bool(getattr(args, "deep", False))
            if ms.exists():
                for vol_dir in sorted(ms.glob("vol_*")):
                    raw_dir = vol_dir / "raw"
                    if raw_dir.exists():
                        shutil.rmtree(raw_dir)
                        (raw_dir).mkdir(parents=True, exist_ok=True)
                        cleared += 1
                    final_dir = vol_dir / "final"
                    if wipe_final and final_dir.exists():
                        shutil.rmtree(final_dir)
                        (final_dir).mkdir(parents=True, exist_ok=True)
                        cleared += 1
            inbox = book / "state" / "inbox"
            if inbox.exists():
                pending = [p for p in inbox.glob("*.json") if not p.name.endswith(state.NO_MERGE_SUFFIXES)]
                for p in pending:
                    p.unlink()
                if pending:
                    cleared += 1
                (inbox / "processed").mkdir(parents=True, exist_ok=True)
                (inbox / "failed").mkdir(parents=True, exist_ok=True)
            (book / "log" / "review").mkdir(parents=True, exist_ok=True)
            (book / "log" / "critic").mkdir(parents=True, exist_ok=True)
            if wipe_final:
                print(f"🧹 已深度清理（raw + final 定稿 + 待办收件箱）: {book}（{cleared} 处）")
                print("   ⚠️ final 定稿（事实唯一源头）已删除而状态六表仍保留——status 中已同步章仍会标绿，"
                      "事实源已分裂；如需连状态一起回退，请用 snapshot rollback。")
            else:
                print(f"🧹 已清理草稿区 raw/ 与待办收件箱（保留 final 定稿、圣经/细纲/状态/审计）: "
                      f"{book}（{cleared} 处）")
                print("   说明：final 是事实唯一源头，默认保留以防「状态绿、正文没了」的事实源分裂；"
                      "确要连同定稿一起重写请用 `init --clean --deep`。")
            return 0
        if args.force:
            import shutil
            trash = common.workspace_root() / ".trash"
            trash.mkdir(parents=True, exist_ok=True)
            dest = trash / f"{common.time_suffix()}_{book.name}"
            print(f"⚠️ --force 整本重开：原书（含 processed/failed 审计）将移出工作区（QA P1-7：不再直接删除）")
            try:
                shutil.move(str(book), str(dest))
            except (OSError, shutil.Error) as exc:
                print(f"❌ 原书移入回收区失败，已中止重开（现场未动）: {exc}")
                print("   请手动处理该书目录后重试，或改用 init --clean。")
                return 1
            print(f"   📦 原书已整体备份至: {dest}（确认无需后可手动删除）")
        else:
            print(f"⛔ 工作区已存在: {book}")
            print("   继续用 status；清稿用 init --clean；确认整本重开用 init --force。")
            return 1

    for d in ("bible", "characters", "outlines/vol_01/beats",
              "manuscript/vol_01/raw", "manuscript/vol_01/final",
              "state/inbox/processed", "state/inbox/failed", "state/snapshots",
              "log/review", "log/critic"):
        (book / d).mkdir(parents=True, exist_ok=True)

    proj = {
        "schema": "novel-studio.project/v1",
        "title": args.title or "",
        "genre": args.genre or "",
        "protagonist": args.protagonist or "",
        "mode": "automatic",
        "words_target": [2000, 3000],
        "lines_cap": {
            "active_foreshadows": 8,
            "longline_foreshadows": 5,
            "active_knowledge": 5,
            "active_misunderstandings": 4
        },
        "state_watch": {},
        "created_at": datetime.date.today().isoformat(),
    }
    common.dump_json(book / "project.json", proj)
    seeded = state.init_state(book)
    if args.protagonist:
        ent_path = book / "state" / "entities.json"
        if ent_path.exists():
            try:
                ents_data = common.load_json(ent_path, default={}) or {}
                entries = ents_data.get("entries", [])
                if not any(e.get("name") == args.protagonist for e in entries):
                    entries.append({
                        "name": args.protagonist,
                        "type": "person",
                        "status": "active",
                        "card": "characters/protagonist.md",
                        "summary": f"本书主角：{args.protagonist}",
                        "aliases": []
                    })
                    ents_data["entries"] = entries
                    state.save_state(book, "entities", ents_data)
            except (ValueError, OSError) as exc:
                # M4 修复：不再静默吞掉异常，至少提示
                print(f"⚠️ 主角实体预置失败（不阻断 init）: {exc}")
    done = _instantiate_templates(book, {"title": args.title or "", "genre": args.genre or "",
                                         "protagonist": args.protagonist or ""})
    print(f"✅ 书工作区已创建: {book}（状态机播种 {seeded} 个 JSON；模板实例化 {len(done)} 份：{', '.join(done)}）")
    print("   下一步（Stage 0）：主控读 AGENTS.md 开局地图，按 templates/模板实例化")
    print("   填实 bible/ characters/ outlines/ 资产（未填的 {{slot:}} 会被 check 拦下）。")
    return 0



# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
def _glob_any(d: Path, pattern: str) -> bool:
    return d.is_dir() and any(d.glob(pattern))


def _book_brief(book: Path) -> dict:
    load_warnings: list[str] = []
    try:
        proj = common.load_json(book / "project.json", default={}) or {}
    except ValueError as exc:
        proj = {}
        load_warnings.append(f"project.json 不可读（status 降级展示）：{exc}")
    final_files = [f for f in common.find_chapter_files(book, "final")
                   if common.chapter_number_from_name(f.name) is not None]
    words = sum(common.cjk_count(f.read_text(encoding="utf-8", errors="replace")) for f in final_files)
    latest = max((common.chapter_number_from_name(f.name) or 0 for f in final_files), default=0)
    inbox = book / "state" / "inbox"
    pending = sorted(p.name for p in inbox.glob("ch_*.json")
                     if not p.name.endswith(state.NO_MERGE_SUFFIXES)) if inbox.is_dir() else []
    snaps = snapshot.list_snapshots(book)
    pipeline = []
    beats = {n for f in common.find_chapter_files(book, "beats")
             if (n := common.chapter_number_from_name(f.name)) is not None}
    raws = {n for f in common.find_chapter_files(book, "raw")
            if (n := common.chapter_number_from_name(f.name)) is not None}
    finals = {common.chapter_number_from_name(f.name) for f in final_files}
    marker_path = book / "state" / ".applied_operations.json"
    try:
        applied = common.load_json(marker_path, default={}) if marker_path.exists() else {}
    except ValueError as exc:
        applied = {}
        load_warnings.append(f".applied_operations.json 不可读（merged 列失真；可用 snapshot rollback 恢复）：{exc}")
    horizon = max((beats | raws | finals | {latest}) | {latest + 1} | {1})
    active = beats | raws | finals
    contiguous = 1
    while contiguous in active:
        contiguous += 1
    display_nums = list(range(1, min(horizon, contiguous) + 1))
    display_nums += sorted(x for x in (active | {latest + 1}) if x > contiguous)
    for n in display_nums:
        tok = f"ch_{n:03d}"
        row = {
            "chapter": tok,
            "beats": n in beats,
            "raw": n in raws,
            "final": n in finals,
            "proposal_pending": _glob_any(inbox, f"{tok}.json"),
            "proposal_merged": any(common.chapter_token_to_num(k) == n for k in applied),
            "snapshot": any(s.endswith(f"{tok}_done") for s in snaps),
        }
        pipeline.append(row)
    return {
        "exists": True,
        "workspace": str(book),
        "title": proj.get("title", ""),
        "genre": proj.get("genre", ""),
        "mode": proj.get("mode", "automatic"),
        "finalized_chapters": len(final_files),
        "latest_finalized": latest,
        "total_words": words,
        "pending_proposals": pending,
        "snapshot_count": len(snaps),
        "load_warnings": load_warnings,
        "pipeline": pipeline,
    }


def _next_actions(brief: dict | None) -> list[str]:
    if brief is None:
        return ['python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"']
    acts = []
    if brief["pending_proposals"]:
        acts.append(f"state/inbox 有 {len(brief['pending_proposals'])} 份待合并提案：python studio.py sync ch_XXX")
    nxt = brief["latest_finalized"] + 1
    acts.append(f"下一章 ch_{nxt:03d}：Stage 1 主控写 beats → Stage 2 drafter → Stage 3 editor → Stage 4 reader/critic 双轨并发质检 → Stage 5 极速同步+快照")
    return acts


def cmd_status(args) -> int:
    book = _resolve_and_validate(args.workspace)
    # 若显式指定 -w 但解析失败（越界或不存在），_resolve_and_validate 已打印越界错误；补充不存在提示
    if args.workspace:
        raw = common.resolve_workspace(args.workspace)
        if raw is not None and not raw.exists():
            books = common.list_books()
            if getattr(args, "json", False):
                print(json.dumps({"exists": False, "reason": "workspace_not_found",
                                  "workspace": str(raw), "books": [str(b) for b in books]},
                                 ensure_ascii=False))
                return 1
            print(f"❌ 指定的书工作区不存在: {raw}")
            if books:
                print("   现有书：" + "、".join(str(b) for b in books))
            return 1
        if book is None:
            # 越界情况已打印，直接返回
            return 1
    if book is None or not book.exists():
        books = common.list_books()
        if args.json:
            hint = ("存在多本书，请 -w 指定" if len(books) > 1
                    else 'python studio.py init -w workspace/<slug> -t "书名"')
            reason = "multiple_books" if len(books) > 1 else "no_books"
            print(json.dumps({"exists": False, "reason": reason,
                              "books": [str(b) for b in books], "next_action": hint},
                             ensure_ascii=False, indent=2))
        else:
            if len(books) > 1:
                print("📚 存在多本书，请用 -w 指定其一：")
                for b in books:
                    print(f"   - {b}")
            else:
                print("（工作区还没有书。开局第一步见下一步提示。）")
                print('👉 python studio.py init -w workspace/<slug> -t "书名" -g "题材"')
        return 0
    brief = _book_brief(book)
    brief["next_actions"] = _next_actions(brief)
    if args.json:
        print(json.dumps(brief, ensure_ascii=False, indent=2))
        return 0
    print("=" * 70)
    for w in brief.get("load_warnings", []):
        print(f" ⚠️ {w}")
    mark = lambda b: "✅" if b else "· "
    latest_str = (f"ch_{brief['latest_finalized']:03d}" if brief["latest_finalized"]
                  else "(未定稿)")
    print(f" 📖 {brief['title'] or '(未命名)'} ｜ {brief['genre'] or '?'} ｜ 模式 {brief['mode']}")
    print(f"    已定稿 {brief['finalized_chapters']} 章（最新 {latest_str}）"
          f" ｜ 共 {brief['total_words']} 字 ｜ 待合并提案 {len(brief['pending_proposals'])}"
          f" ｜ 快照 {brief['snapshot_count']}")
    if brief["pipeline"]:
        print("      章节      beats  raw   final  proposal  merged  snapshot")
        for r in brief["pipeline"]:
            print(f"      {r['chapter']}   " + "  ".join(mark(r[k])
                  for k in ("beats", "raw", "final", "proposal_pending", "proposal_merged", "snapshot")))
    print("    下一步：")
    for a in brief["next_actions"]:
        print(f"      👉 {a}")
    _status_debts(book)
    print("    规则：先读 AGENTS.md 地图，再按 workflow 对应 Stage 节行动；")
    print("=" * 70)
    return 0


def cmd_cockpit(args) -> int:
    book = _resolve_and_validate(args.workspace)
    if book is None or not (book / "project.json").exists():
        print_ws_not_found()
        return 1
    ch = None
    if getattr(args, "chapter", None):
        # QA P3-10：显式传入非法章号直接报用法错（此前被静默吞掉自动推断，
        # 主控拿到错误坐标的驾驶舱报而不知情）
        ch = _norm_ch(args.chapter)
        if ch is None:
            print(f"❌ 无法解析章节号: {args.chapter!r}（示例: 2 或 ch_002；缺省可自动推断活跃章）")
            return 2
    from .. import cockpit
    briefing = cockpit.build_cockpit_briefing(book, ch)
    if args.json:
        print(json.dumps(briefing, ensure_ascii=False, indent=2))
    else:
        cockpit.render_cockpit_terminal(briefing)
    return 0


def _status_debts(book) -> None:
    notes: list[str] = []
    n_fail = len(list((book / "state" / "inbox" / "failed").glob("*.json"))) \
        if (book / "state" / "inbox" / "failed").is_dir() else 0
    if n_fail:
        notes.append(f"🧾 inbox/failed/ 积压 {n_fail} 件——就地修复后 sync 自动捡回")
    try:
        g = evidence.gaps(book)
        cur = g.get("max_final_chapter") or 0
        soon = [x for x in g["foreshadows"] + g["misunderstandings"] + g.get("knowledge", [])
                if isinstance(x.get("target_ch"), int) and x.get("status") not in ("Resolved", "Revealed")
                and 0 <= x["target_ch"] - cur <= 2]
        soon.sort(key=lambda x: (-int(x.get("weight") or x.get("level") or 1),
                                 x["target_ch"] - cur, str(x.get("id", ""))))
        for x in soon[:2]:
            nid = x.get("id", "?")
            left = x["target_ch"] - cur
            notes.append(f"⏳ {nid} 距到期 {left} 章（target ch_{x['target_ch']:03d}）")
        if len(soon) > 2:
            notes.append(f"   （另有 {len(soon) - 2} 条同量级，见 evidence gaps）")
    except Exception:
        pass
    for n in notes:
        print(f"      {n}")



# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
def _merge_param_value(shape: str, old, new):
    if old is None:
        return new
    if shape == "str_list":
        out = [w for w in (old if isinstance(old, list) else []) if isinstance(w, str)]
        for w in new:
            if w not in out:
                out.append(w)
        return out
    if shape in ("hook_tiers", "str_map"):
        out = dict(old) if isinstance(old, dict) else {}
        for k, ws in new.items():
            cur = [w for w in out.get(k, []) if isinstance(w, str)] if isinstance(ws, list) else ws
            if isinstance(ws, list):
                for w in ws:
                    if w not in cur:
                        cur.append(w)
            out[k] = cur
        return out
    return new


def cmd_config(args) -> int:
    book = _resolve_and_validate(args.workspace)
    if book is None or not (book / "project.json").exists():
        print_ws_not_found()
        return 1
    proj_path = book / "project.json"
    try:
        proj = common.load_json(proj_path)
    except (ValueError, OSError) as exc:
        print(f"❌ project.json 解析失败: {exc}")
        return 1
    act = getattr(args, "config_action", None) or "list"
    spec = checks.PARAM_SPEC
    js = getattr(args, "json", False)

    if act == "guide":
        payload = {"kind": "config_guide",
                   "note": "引擎零题材词表：参数由主控按本书题材生成并注入；gap=true 的键缺席时对应启发式停用"
                           "并出 ℹ️ 提示，空表=明确关闭；形状错误会在 check 中报 param_shape_invalid。",
                   "params": {k: {"shape": v["shape"], "gap": v.get("gap", False), "desc": v["desc"],
                                  "example": v["example"]} for k, v in spec.items()}}
        if js:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("=" * 74)
            print(" 🧩 引擎可接受的词表参数型号单（主控按本书题材照此供参）")
            print("=" * 74)
            for k, v in spec.items():
                tag = "缺席即停用" if v.get("gap") else "可选增配"
                print(f" • {k}  [{v['shape']}｜{tag}]")
                print(f"     {v['desc']}")
                print(f"     形状示例: {json.dumps(v['example'], ensure_ascii=False)}")
            print("\n用法: python studio.py config set <键> '<JSON值>' ｜ get <键> ｜ unset <键> ｜ list")
        return 0

    if act == "list":
        rows = [{"key": k, "configured": k in proj, "shape": spec[k]["shape"],
                 "gap": spec[k].get("gap", False), "value": proj.get(k), "desc": spec[k]["desc"]}
                for k in spec]
        if js:
            print(json.dumps({"kind": "config_list", "params": rows}, ensure_ascii=False, indent=2))
        else:
            print("=" * 74)
            print(" 🧩 书级词表参数现状（project.json）")
            print("=" * 74)
            for r_ in rows:
                mark = "✅" if r_["configured"] else ("— 未配置(启发式停用)" if r_["gap"] else "— 可选未配置")
                val = json.dumps(r_["value"], ensure_ascii=False) if r_["configured"] else ""
                print(f" {r_['key']:<22} {mark} {val[:48]}")
        return 0

    if act == "suggest":
        payload = checks.param_suggestions(book)
        if js:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("=" * 74)
            print(f" 🧮 供参候选工作单（机械计数 {payload['final_chapters_scanned']} 章定稿；采纳与否归主控裁决）")
            print("=" * 74)
            for k, items in payload["suggestions"].items():
                print(f" • {k}（{spec[k]['desc']}）")
                if items:
                    for it in items:
                        extra = f"（出自 {it['of_entity']}）" if it.get("of_entity") else ""
                        print(f"     {it['word']} ×{it['count']}{extra}")
                else:
                    print("     （暂无候选）")
            print(f"\n{payload['adopt']}")
        return 0

    key = getattr(args, "key", None)
    if not key:
        print("❌ 请指定参数键（合法键见 `python studio.py config guide`）")
        return 2
    if key not in spec:
        print(f"❌ 未知参数键「{key}」（合法键 {sorted(spec)}）")
        return 2

    if act == "get":
        val = proj.get(key)
        if js:
            print(json.dumps({"key": key, "configured": key in proj, "value": val},
                             ensure_ascii=False, indent=2))
        elif key in proj:
            print(f"{key} = {json.dumps(val, ensure_ascii=False)}")
        else:
            print(f"「{key}」未配置（{'gap 键：对应启发式停用中' if spec[key].get('gap') else '可选增配'}）")
        return 0

    if act == "set":
        raw = getattr(args, "value", None)
        if raw is None:
            print("❌ set 需要提供 JSON 值，如：config set generic_stopwords '[\"掌柜\",\"警官\"]'"
                  "；--merge 并入现有值（供 config suggest 采纳回路使用）")
            return 2
        try:
            val = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"❌ 值必须是合法 JSON 字面量: {exc}")
            return 2
        if getattr(args, "merge", False):
            # QA P1-6：合并前先校验新值形状——此前标量进 merge 会被逐字拆分静默落盘，
            # 且 dict 形状键收到标量会触发裸 TypeError/AttributeError
            pre_err = checks.validate_param_value(key, val)
            if pre_err:
                print(f"❌ 参数形状非法（--merge 前置校验）：project.json.{pre_err}")
                return 2
            val = _merge_param_value(spec[key]["shape"], proj.get(key), val)
        shape_err = checks.validate_param_value(key, val)
        if shape_err:
            print(f"❌ 参数形状非法：project.json.{shape_err}")
            return 1
        proj[key] = val
        common.dump_json(proj_path, proj)
        note = "（空表 = 明确关闭该档）" if val in ([], {}) else ""
        how = "并入现有值" if getattr(args, "merge", False) else "整体替换"
        print(f"✅ project.json.{key} 已更新（{how}）{note}——后续命令即时生效（动态供参，随快照封版）")
        return 0

    if act == "unset":
        if key in proj:
            proj.pop(key)
            common.dump_json(proj_path, proj)
            tail = "gap 键回到未配置态：check 将恢复缺口提示（启发式停用）" if spec[key].get("gap") else "回到未配置态"
            print(f"✅ project.json.{key} 已移除——{tail}")
        else:
            print(f"ℹ️ 「{key}」本就未配置，无需移除")
        return 0

    print(f"❌ 未知动作: {act}（合法: list|guide|get|set|unset）")
    return 2


# ---------------------------------------------------------------------------
# errcodes
# ---------------------------------------------------------------------------
def cmd_errcodes(args) -> int:
    """错误码注册表速查：引擎全部体检码的 severity/人话解释/修复建议（Agent 供 --json）。"""
    items = errcodes.as_list()
    if getattr(args, "json", False):
        print(json.dumps({"schema": "novel-studio.errcodes/v1", "total": len(items),
                          "codes": items}, ensure_ascii=False, indent=2))
        return 0
    icons = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
    print("=" * 70)
    print(f" 📖 [错误码注册表] 共 {len(items)} 个（机器可读: python studio.py errcodes --json）")
    print("=" * 70)
    for item in items:
        print(f" {icons[item['level']]} [{item['code']}] ({item['level']}) {item['description']}")
        if item["remedy"]:
            print(f"    💡 {item['remedy']}")
    print("=" * 70)
    return 0
