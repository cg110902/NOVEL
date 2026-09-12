"""书级生命周期命令：init（脚手架）/ status / cockpit（态势）/ config（词表供参）。"""
from __future__ import annotations

import copy
import datetime
import json
import re
from pathlib import Path

from .. import checks, common, errcodes, evidence, snapshot, state

from ._shared import (SLOT_RE, _norm_ch, _resolve_and_validate, resolve_note_shown, usage_error,
                      ws_gate, ws_gate_code)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
TEMPLATE_MAP = {
    # 模块化全书底层世界观与公理词典库（v2 核心）
    "bible/01_world_axioms.md": "bible/01_world_axioms.md",
    "bible/02_power_system.md": "bible/02_power_system.md",
    "bible/03_factions_geography.md": "bible/03_factions_geography.md",
    "bible/04_economy_items.md": "bible/04_economy_items.md",
    "bible/05_special_mechanics.md": "bible/05_special_mechanics.md",
    "bible/06_deviations.md": "bible/06_deviations.md",
    # 核心角色全息档案
    "characters/protagonist.md": "characters/protagonist.md",
    # 核心剧情大纲与首卷大纲
    "outlines/main_plot.md": "outlines/main_plot.md",
    "outlines/volume_outline.md": "outlines/vol_01/outline.md",
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
                print("   ⚠️ final 定稿（事实唯一源头）已删除而状态十一表仍保留——status 中已同步章仍会标绿，"
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
            print(f"⚠️ --force 整本重开：原书（含 processed/failed 审计）将移出工作区（ P1-7：不再直接删除）")
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

    for d in ("bible", "characters", "entities/items", "entities/factions", "entities/locations",
              "outlines/vol_01/beats", "manuscript/vol_01/raw", "manuscript/vol_01/final",
              "state/inbox/processed", "state/inbox/failed", "state/snapshots",
              "log/review", "log/critic", "log/audit"):
        (book / d).mkdir(parents=True, exist_ok=True)

    today_str = datetime.date.today().isoformat()
    tpl_proj = common.project_root() / "templates" / "project.json"
    if tpl_proj.is_file():
        text = tpl_proj.read_text(encoding="utf-8")
        slots = {"title": args.title or "", "genre": args.genre or "",
                 "protagonist": args.protagonist or "", "created_at": today_str}
        def _sub(m: re.Match) -> str:
            val = slots.get(m.group(1), "")
            return val if val else m.group(0)
        text = SLOT_RE.sub(_sub, text)
        try:
            proj = json.loads(text)
        except json.JSONDecodeError:
            proj = {}
    else:
        proj = {}

    if not proj:
        # 兜底路径（模板缺失/损坏才会走到）刻意只给最小集：不复制词表，避免与 templates/project.json
        # 形成第二真源。后果是六张词表与 state_watch 缺席＝对应启发式停用，`check` 会以
        # wordlist_unconfigured（info）逐键提醒主控补配——属设计内行为，勿在此硬编码词表。
        proj = {
            "schema": "novel-studio.project/v1",
            "title": args.title or "",
            "genre": args.genre or "",
            "protagonist": args.protagonist or "",
            "audit_mode": "strict",
            "words_target": [2000, 3000],
            "lines_cap": {
                "active_foreshadows": 8,
                "longline_foreshadows": 5,
                "active_knowledge": 5,
                "active_misunderstandings": 4
            },
            "created_at": today_str,
        }
    common.dump_json(book / "project.json", proj)
    seeded = state.init_state(book)
    if args.protagonist:
        try:
            persons_data = state.load_state(book, "persons")
            entries = persons_data.get("entries", [])
            if not any(e.get("name") == args.protagonist for e in entries):
                entries.append({
                    "id": "p_001",
                    "name": args.protagonist,
                    "type": "person",
                    "status": "active",
                    "card": "characters/protagonist.md",
                    "summary": f"本书主角：{args.protagonist}",
                    "aliases": []
                })
                state.save_state(book, "persons", persons_data, source="init")
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
        # audit_mode 是真实生效的 Stage 5 闸门口径（strict/advisory/off）；
        # mode 为历史字段（模板已不再播种），仅在书里确实存在时才展示，缺省不出现在输出里。
        "audit_mode": str(proj.get("audit_mode", "strict")),
        **({"mode": str(proj.get("mode"))} if proj.get("mode") else {}),
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
    acts.append(f"下一章 ch_{nxt:03d}：Stage 1 主控写 beats → Stage 2 Drafter 毛坯 raw_v1 → "
                f"Stage 3A Editor 骨肉稿 raw_v2 → Stage 3B Stylist 脱水预定稿 raw_v3 → "
                f"Stage 4A/4B 并发（Auditor 问题清单 ‖ Critic 催更便签）→ "
                f"Stage 4C Fixer 落盘法定定稿 final → Stage 4D Reader 增量事实提案 → "
                f"Stage 5 sync 封存+快照")
    return acts


def cmd_status(args) -> int:
    # --json 模式解析层不打文本（stdout 只出 JSON 信封）
    js = bool(getattr(args, "json", False))
    book = _resolve_and_validate(args.workspace, suppress_text=js)
    # 若显式指定 -w 但解析失败（越界或不存在），_resolve_and_validate 已打印越界错误；补充不存在提示
    if args.workspace:
        raw = common.resolve_workspace(args.workspace)
        if raw is not None and not raw.exists():
            books = common.list_books()
            if js:
                print(json.dumps({"exists": False, "reason": "workspace_not_found",
                                  "workspace": str(raw), "books": [str(b) for b in books]},
                                 ensure_ascii=False))
                return 1
            print(f"❌ 指定的书工作区不存在: {raw}")
            if books:
                print("   现有书：" + "、".join(str(b) for b in books))
            return 1
        if book is None:
            # 越界情况：文本模式已由 _resolve_and_validate 打印；--json 模式
            # suppress_text 生效，此处必须补 JSON 信封（否则 stdout 静默空、契约违约）
            if js:
                print(json.dumps({"exists": False, "reason": "workspace_out_of_bounds",
                                  "workspace": str(raw),
                                  "books": [str(b) for b in common.list_books()]},
                                 ensure_ascii=False))
            return 1
    if book is None or not book.exists():
        books = common.list_books()
        if js:
            hint = ("存在多本书，请 -w 指定" if len(books) > 1
                    else 'python studio.py init -w workspace/<slug> -t "书名"')
            reason = "multiple_books" if len(books) > 1 else "no_books"
            print(json.dumps({"exists": False, "reason": reason,
                              "books": [str(b) for b in books], "next_action": hint},
                             ensure_ascii=False, indent=2))
        else:
            if len(books) > 1:
                # 解析层已打印过多书清单时不再二次打印
                if not resolve_note_shown():
                    print("📚 存在多本书，请用 -w 指定其一：")
                    for b in books:
                        print(f"   - {b}")
            else:
                print("（工作区还没有书。开局第一步见下一步提示。）")
                print('👉 python studio.py init -w workspace/<slug> -t "书名" -g "题材"')
        # 此处原为 `return 0`，与 check/cockpit/sync 的 1 互相矛盾，且违反
        # engine/README.md 自述的退出码契约——按退出码判读的 Agent 会把「什么都没做」
        # 当成功。现统一：多书歧义（调用缺 -w，属用法错误）→ 2；未初始化 → 1。
        return 2 if len(books) > 1 else 1
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
    print(f" 📖 {brief['title'] or '(未命名)'} ｜ {brief['genre'] or '?'}"
          f" ｜ 审计闸门 {brief['audit_mode']}"
          + (f" ｜ 模式 {brief['mode']}" if brief.get("mode") else ""))
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
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    ch = None
    if getattr(args, "chapter", None):
        # 显式传入非法章号直接报用法错（此前被静默吞掉自动推断，
        # 主控拿到错误坐标的驾驶舱报而不知情）
        ch = _norm_ch(args.chapter)
        if ch is None:
            return usage_error(
                f"无法解析章节号: {args.chapter!r}（示例: 2 或 ch_002；缺省可自动推断活跃章）",
                args, chapter=str(args.chapter))
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
                # 上界 2 = 倒计时展示窗口；不设下界——逾期线（target < cur）必须全部入列，
                # 逾期越久越是最高优先级债务（此前 0 <= diff 会把逾期 ≥2 章的线整个吞掉）
                and x["target_ch"] - cur <= 2]
        soon.sort(key=lambda x: (-int(x.get("weight") or x.get("level") or 1),
                                 x["target_ch"] - cur, str(x.get("id", ""))))
        for x in soon[:2]:
            nid = x.get("id", "?")
            # 复用 cockpit 雷达口径——基准取「下一章」（已定稿章数+1），
            # 逾期/本章引爆/倒计时三分措辞，不再出现「距到期 0 章」的含糊表述
            left = x["target_ch"] - (cur + 1)
            if left < 0:
                notes.append(f"🚨 {nid} 已逾期 {-left} 章待收束（target ch_{x['target_ch']:03d}）")
            elif left == 0:
                notes.append(f"🔥 {nid} 下一章预定引爆（target ch_{x['target_ch']:03d}）")
            else:
                notes.append(f"⏳ {nid} 距引爆 {left} 章（target ch_{x['target_ch']:03d}）")
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
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    proj_path = book / "project.json"
    act = getattr(args, "config_action", None) or "list"
    spec = checks.PARAM_SPEC
    js = getattr(args, "json", False)

    def _cfg_err(msg: str, code: int = 2, key: str = "") -> int:
        """config 手术刀错误出口：--json 一律 JSON 信封（与 config get 未知键信封同契约）。"""
        if js:
            payload: dict = {"ok": False, "code": "config_error", "error": msg}
            if key:
                payload["key"] = key
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return code

    try:
        proj = common.load_json(proj_path)
    except (ValueError, OSError) as exc:
        return _cfg_err(f"project.json 解析失败: {exc}", code=1)

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
            # alias_suggestions 是派生建议、不是 PARAM_SPEC 里的配置键，
            # 直接 spec[k] 会 KeyError（实测崩在文本渲染路径）。分开渲染。
            for k, items in payload["suggestions"].items():
                if k not in spec:
                    continue
                print(f" • {k}（{spec[k]['desc']}）")
                if items:
                    for it in items:
                        extra = f"（出自 {it['of_entity']}）" if it.get("of_entity") else ""
                        print(f"     {it['word']} ×{it['count']}{extra}")
                else:
                    print("     （暂无候选）")
            _aliases = payload["suggestions"].get("alias_suggestions") or []
            print(" • alias_suggestions（高频写法疑似既有实体的别名——挂别名还是建新实体归主控裁决）")
            if _aliases:
                for it in _aliases:
                    tgt = it.get("suggest_alias_of")
                    print(f"     {it['word']} ×{it['count']} → "
                          + (f"建议挂到「{tgt}」" if tgt else "无法自动归属，请人工判断"))
            else:
                print("     （暂无候选）")
            print(f"\n{payload['adopt']}")
        return 0

    key = getattr(args, "key", None)
    if not key:
        if js:
            print(json.dumps({"ok": False, "code": "usage", "hint": "请指定参数键（合法键见 config guide）"},
                             ensure_ascii=False))
        else:
            print("❌ 请指定参数键（合法键见 `python studio.py config guide`）")
        return 2
    if key not in spec:
        if js:
            print(json.dumps({"ok": False, "code": "unknown_param_key", "key": key,
                              "valid_keys": sorted(spec)}, ensure_ascii=False))
        else:
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
            return _cfg_err('set 需要提供 JSON 值（示例：config set generic_stopwords ["掌柜","警官"]）；'
                            "--merge 并入现有值（供 config suggest 采纳回路使用）")
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            # 区间类键容忍裸字符串 "2000,3000"（避免让主控先学 JSON 语法再谈形状）
            val = None
            if spec[key]["shape"] == "int_pair":
                parts = [x for x in re.split(r"[,，\s]+", raw.strip()) if x]
                if len(parts) == 2 and all(p.lstrip("-").isdigit() for p in parts):
                    val = [int(parts[0]), int(parts[1])]
            if val is None:
                return _cfg_err('值必须是合法 JSON 字面量（区间类键如 words_target 也可裸写 "2000,3000"）')
        if getattr(args, "merge", False):
            # 合并前先校验新值形状——此前标量进 merge 会被逐字拆分静默落盘，
            # 且 dict 形状键收到标量会触发裸 TypeError/AttributeError
            pre_err = checks.validate_param_value(key, val)
            if pre_err:
                return _cfg_err(f"参数形状非法（--merge 前置校验）：project.json.{pre_err}")
            val = _merge_param_value(spec[key]["shape"], proj.get(key), val)
        shape_err = checks.validate_param_value(key, val)
        if shape_err:
            # 形状非法是**用法错误**，不是被闸门阻断的作业。同一函数里
            # 「值必须是合法 JSON」与 --merge 前置校验都返 2，只有这里返 1，
            # 与 README 自述的「1=阻断 / 2=用法错」矛盾，按退出码判读的 Agent 会误判。
            return _cfg_err(f"参数形状非法：project.json.{shape_err}")
        # 写入入口的质量守卫（单字守望词等）。只拦新写入，不影响存量配置体检。
        guard_err = checks.param_write_guard(key, val)
        if guard_err:
            return _cfg_err(f"参数值不可用：project.json.{guard_err}")
        proj[key] = val
        common.dump_json(proj_path, proj)
        note = "（空表 = 明确关闭该档）" if val in ([], {}) else ""
        how = "并入现有值" if getattr(args, "merge", False) else "整体替换"
        if js:
            print(json.dumps({"ok": True, "key": key, "value": val,
                              "merged": bool(getattr(args, "merge", False))}, ensure_ascii=False))
        else:
            print(f"✅ project.json.{key} 已更新（{how}）{note}——后续命令即时生效（动态供参，随快照封版）")
        return 0

    if act == "unset":
        if key in proj:
            proj.pop(key)
            common.dump_json(proj_path, proj)
            tail = "gap 键回到未配置态：check 将恢复缺口提示（启发式停用）" if spec[key].get("gap") else "回到未配置态"
            if js:
                print(json.dumps({"ok": True, "removed": key, "was_configured": True,
                                  "note": tail}, ensure_ascii=False))
            else:
                print(f"✅ project.json.{key} 已移除——{tail}")
        else:
            if js:
                print(json.dumps({"ok": True, "removed": key, "was_configured": False,
                                  "note": "本就未配置，无需移除"}, ensure_ascii=False))
            else:
                print(f"ℹ️ 「{key}」本就未配置，无需移除")
        return 0

    return _cfg_err(f"未知动作: {act}（合法: list|guide|get|set|unset）")


# ---------------------------------------------------------------------------
# errcodes
# ---------------------------------------------------------------------------
def cmd_errcodes(args) -> int:
    """错误码注册表速查：引擎全部体检码的 level/人话解释/修复建议（Agent 供 --json）。"""
    code = str(getattr(args, "code", "") or "").strip()
    if code:
        hit = errcodes.get(code)
        if hit is None:
            near = [k for k in errcodes.REGISTRY if code in k or k in code][:6]
            msg = (f"未知错误码「{code}」（全表 {len(errcodes.REGISTRY)} 码，"
                   f"用 `errcodes --json` 取机器可读版）")
            if near:
                msg += f"；相近码：{'、'.join(near)}"
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "code": "unknown_errcode", "error": msg,
                                  "queried": code, "near": near}, ensure_ascii=False))
            else:
                print(f"❌ {msg}")
            return 2
        item = {"code": hit.code, "level": hit.level,
                "description": hit.description, "remedy": hit.remedy}
        if getattr(args, "json", False):
            print(json.dumps({"schema": "novel-studio.errcode/v1", **item},
                             ensure_ascii=False, indent=2))
        else:
            icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}[hit.level]
            print(f"{icon} [{item['code']}] ({item['level']})")
            print(f"  说明：{item['description']}")
            if item["remedy"]:
                print(f"  💡 修复：{item['remedy']}")
        return 0
    items = errcodes.as_list()
    level = str(getattr(args, "level", "") or "").strip()
    if level:
        items = [x for x in items if x["level"] == level]
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


# ---------------------------------------------------------------------------
# lore: 世界观与实体词典对账检索
# ---------------------------------------------------------------------------
def _find_lore_target(book: Path, query: str) -> Path | None:
    q = query.strip().lower()
    short_map = {
        "axioms": "01_world_axioms.md", "world": "01_world_axioms.md", "公理": "01_world_axioms.md", "世界": "01_world_axioms.md",
        "power": "02_power_system.md", "scale": "02_power_system.md", "战力": "02_power_system.md", "境界": "02_power_system.md", "标尺": "02_power_system.md",
        "factions": "03_factions_geography.md", "geo": "03_factions_geography.md", "势力": "03_factions_geography.md", "地理": "03_factions_geography.md",
        "economy": "04_economy_items.md", "items": "04_economy_items.md", "经济": "04_economy_items.md", "货币": "04_economy_items.md",
        "mechanics": "05_special_mechanics.md", "special": "05_special_mechanics.md", "机制": "05_special_mechanics.md", "体质": "05_special_mechanics.md",
        "deviations": "06_deviations.md", "偏离": "06_deviations.md", "红线": "06_deviations.md",
    }
    bdir = book / "bible"
    if q in short_map:
        target = bdir / short_map[q]
        if target.is_file():
            return target
        if q in ("deviations", "偏离", "红线"):
            legacy = bdir / "07_deviations.md"
            if legacy.is_file():
                return legacy
    if bdir.is_dir():
        for p in bdir.glob("*.md"):
            if q in p.name.lower():
                return p
    # 主角特殊匹配
    try:
        proj = common.load_json(book / "project.json", default={}) or {}
        pname = str(proj.get("protagonist", "")).strip().lower()
        if (q == pname or q in ("protagonist", "主角")) and (cdir / "protagonist.md").is_file():
            return cdir / "protagonist.md"
    except Exception:
        pass
    cdir = book / "characters"
    if cdir.is_dir():
        for p in cdir.glob("*.md"):
            if q in p.stem.lower():
                return p
    edir = book / "entities"
    if edir.is_dir():
        for p in edir.rglob("*.md"):
            if q in p.stem.lower():
                return p
    # 从实体四表（兼容读视图）中按 ID、别名或卡片路径查找
    try:
        ents_st = state.load_state(book, "entities")
        for e in ents_st.get("entries", []):
            eid = str(e.get("id", "")).lower()
            ename = str(e.get("name", "")).lower()
            aliases = [str(a).lower() for a in e.get("aliases", [])]
            if q == eid or q == ename or q in aliases:
                card = e.get("card")
                if card and (book / card).is_file():
                    return book / card
    except Exception:
        pass
    if (bdir / "project_bible.md").is_file() and q in ("bible", "project_bible"):
        return bdir / "project_bible.md"
    return None


def _extract_address_from_markdown(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """从卡片 Markdown 正文中提取对他人称谓以及他人对本角色的称谓（作为 Front-matter 的保底）。"""
    self_to_others: dict[str, str] = {}
    others_to_self: dict[str, str] = {}
    if not text:
        return self_to_others, others_to_self

    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("-") or line.startswith("*")):
            continue
        # 1. 匹配: - 对[xxx]：「yyy」 或 「yyy」 或 yyy
        m_self = re.search(r"^[-*]\s*(?:\*\*)?对([^：:\n（(]+)(?:\*\*)?[：:]\s*(.+)", line)
        if m_self:
            target = m_self.group(1).strip().strip("*").strip()
            rest = m_self.group(2).strip()
            if any(w in target for w in ("关键人物", "他人", "所有人", "自我", "自称")):
                continue
            # 剥离括号内的限制说明（如：（唯一指定称谓！严禁出现“主人”等））
            main_part = re.sub(r"（[^）]*）|\([^\)]*\)", "", rest).strip()
            quotes = common.iter_dialogues(main_part)
            if quotes:
                clean_quotes = [q.strip() for q in quotes if not any(kw in q for kw in ("严禁", "唯一", "指定", "称谓"))]
                if clean_quotes:
                    self_to_others[target] = " / ".join(clean_quotes)
                elif quotes:
                    self_to_others[target] = quotes[0].strip()
            else:
                val = main_part.strip().strip("*").strip()
                if val and len(val) < 30:
                    self_to_others[target] = val

        # 2. 匹配: - [xxx]称呼本角色：「yyy」 或 [xxx]称呼：...
        m_other = re.search(r"^[-*]\s*(?:\*\*)?([^：:\n（(]+)称呼(?:本角色)?[：:]\s*(.+)", line)
        if m_other:
            speaker = m_other.group(1).strip().strip("*").strip()
            rest = m_other.group(2).strip()
            if any(w in speaker for w in ("他人", "自我", "自称")):
                continue
            # 剥离括号内的限制说明
            main_part = re.sub(r"（[^）]*）|\([^\)]*\)", "", rest).strip()
            quotes = common.iter_dialogues(main_part)
            if quotes:
                clean_quotes = [q.strip() for q in quotes if not any(kw in q for kw in ("严禁", "唯一", "指定", "称谓"))]
                if clean_quotes:
                    others_to_self[speaker] = " / ".join(clean_quotes)
                elif quotes:
                    others_to_self[speaker] = quotes[0].strip()
            else:
                val = main_part.strip().strip("*").strip()
                if val and len(val) < 30:
                    others_to_self[speaker] = val

    return self_to_others, others_to_self


def _resolve_mutual_address(from_prof: dict, to_prof: dict) -> str:
    """解析 from_prof 称呼 to_prof 的法定称谓，支持别名、模糊穿透与反向登记交叉校验。"""
    if not from_prof or not to_prof:
        return "(未登记)"
    to_name = to_prof.get("name", "")
    to_aliases = to_prof.get("aliases", [])
    targets = [to_name] + [a for a in to_aliases if a]

    from_matrix = from_prof.get("address_matrix") or {}
    if isinstance(from_matrix, dict):
        for tgt in targets:
            if tgt in from_matrix:
                return from_matrix[tgt]
        for k, v in from_matrix.items():
            if any(k == t or (k and k in t) or (t and t in k) for t in targets):
                return v

    to_passive = to_prof.get("passive_address_matrix") or {}
    if isinstance(to_passive, dict):
        from_name = from_prof.get("name", "")
        from_aliases = from_prof.get("aliases", [])
        from_targets = [from_name] + [a for a in from_aliases if a]
        for ft in from_targets:
            if ft in to_passive:
                return to_passive[ft]
        for k, v in to_passive.items():
            if any(k == ft or (k and k in ft) or (ft and ft in k) for ft in from_targets):
                return v

    return "(未在卡片登记)"


def _get_entity_full_profile(book: Path, query_name: str) -> dict | None:
    """提取实体的结构化全息档案（融合实体四表 + 卡片 YAML Front-matter + 正文关键小节）。"""
    if not query_name:
        return None
    q = query_name.strip().lower()
    ents_st = {}
    try:
        ents_st = state.load_state(book, "entities") or {}
    except Exception:
        pass

    entries = ents_st.get("entries", [])
    matched_entry = None
    for e in entries:
        eid = str(e.get("id", "")).strip().lower()
        en = str(e.get("name", "")).strip().lower()
        al = [str(a).strip().lower() for a in e.get("aliases", [])]
        if q == eid or q == en or q in al:
            matched_entry = copy.deepcopy(e)
            break

    card_path = None
    if matched_entry and matched_entry.get("card"):
        cp = book / matched_entry["card"]
        if cp.is_file():
            card_path = cp

    if not card_path:
        target = _find_lore_target(book, query_name)
        if target and target.is_file() and target.suffix == ".md":
            card_path = target

    fm = {}
    body_sections = {}
    txt_self_addr = {}
    txt_other_addr = {}
    card_raw_text = ""
    if card_path and card_path.is_file():
        card_raw_text = card_path.read_text(encoding="utf-8", errors="replace")
        fm = common.parse_yaml_front_matter(card_raw_text)
        txt_self_addr, txt_other_addr = _extract_address_from_markdown(card_raw_text)
        for sec_name, pat in (
            ("psychology", r"^##\s.*(?:心理|动机|欲望|Want|Fear)"),
            ("power_benchmark", r"^##\s.*(?:实力|战力|标尺|实物标尺|Power)"),
            ("sensory_details", r"^##\s.*(?:感官|外貌|材质|Sensory)"),
            ("address_section", r"^##\s.*(?:称谓|人际矩阵|Address)"),
            ("rules_section", r"^##\s.*(?:法则|环境|防御|Rules)"),
        ):
            sec_lines = common.md_section(card_raw_text, pat)
            if sec_lines:
                body_sections[sec_name] = "\n".join(sec_lines).strip()

    if not matched_entry and not fm and not card_raw_text:
        return None

    res = matched_entry or {}
    for k, v in fm.items():
        if v is not None and v != "":
            if k not in res or res[k] is None or res[k] == "":
                res[k] = v

    if card_path:
        res["card_file"] = card_path.relative_to(book).as_posix()
    if body_sections:
        res["sections"] = body_sections

    res.setdefault("name", query_name)
    if card_path:
        cp_str = str(card_path).replace("\\", "/")
        if "characters/" in cp_str:
            res.setdefault("type", "person")
        elif "items/" in cp_str:
            res.setdefault("type", "item")
        elif "factions/" in cp_str:
            res.setdefault("type", "faction")
        elif "locations/" in cp_str:
            res.setdefault("type", "place")
        else:
            res.setdefault("type", "other")
    else:
        res.setdefault("type", "other")

    if "tier_rank" not in res and fm.get("tier_rank") is not None:
        res["tier_rank"] = fm["tier_rank"]
    if "tier_name" not in res:
        res["tier_name"] = fm.get("tier_name") or res.get("realm") or fm.get("tier")
    if not res.get("tier_name") and card_raw_text:
        m_tier = re.search(r"[-*]\s*(?:\*\*)?(?:当前境界|境界|实力位阶|位阶|层级)(?:\*\*)?[：:]\s*([^\n（(]+)", card_raw_text)
        if m_tier:
            res["tier_name"] = m_tier.group(1).strip().strip("*").strip()
    if "power_benchmark" not in res and fm.get("power_benchmark"):
        res["power_benchmark"] = fm["power_benchmark"]
    if "sensory_anchor" not in res and fm.get("sensory_anchor"):
        res["sensory_anchor"] = fm["sensory_anchor"]

    res["passive_address_matrix"] = txt_other_addr
    merged_addr = {}
    if txt_self_addr:
        merged_addr.update(txt_self_addr)
    if fm.get("address_matrix") and isinstance(fm["address_matrix"], dict):
        merged_addr.update(fm["address_matrix"])
    if res.get("address_matrix") and isinstance(res["address_matrix"], dict):
        merged_addr.update(res["address_matrix"])
    res["address_matrix"] = merged_addr

    return res


def cmd_lore(args) -> int:
    """底层词典与实体知识库速查对账工具。"""
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()
    js = getattr(args, "json", False)
    act = getattr(args, "lore_action", None) or "list"

    if act == "list":
        b_files = [f.name for f in sorted((book / "bible").glob("*.md"))] if (book / "bible").is_dir() else []
        ents_st = {}
        try:
            ents_st = state.load_state(book, "entities") or {}
        except Exception:
            pass

        registered_names = set()
        all_profiles = []
        for e in ents_st.get("entries", []):
            name = e.get("name")
            if name:
                registered_names.add(name)
                prof = _get_entity_full_profile(book, name)
                if prof:
                    all_profiles.append(prof)

        # 扫描未在实体四表注册但存在于卡片目录中的实体
        for sub_dir, fallback_type in (("characters", "person"),
                                       ("entities/items", "item"),
                                       ("entities/factions", "faction"),
                                       ("entities/locations", "place")):
            p_dir = book / sub_dir
            if p_dir.is_dir():
                for f in p_dir.glob("*.md"):
                    if f.name.endswith(".example.md"):
                        continue
                    stem = f.stem
                    if stem not in registered_names and stem != "character_card_standard":
                        prof = _get_entity_full_profile(book, stem)
                        if prof:
                            pname = prof.get("name") or stem
                            if pname not in registered_names:
                                all_profiles.append(prof)
                                registered_names.add(pname)

        persons = [p for p in all_profiles if p.get("type") == "person"]
        items = [p for p in all_profiles if p.get("type") == "item"]
        factions = [p for p in all_profiles if p.get("type") == "faction"]
        places = [p for p in all_profiles if p.get("type") in ("place", "location")]

        if js:
            payload = {
                "kind": "lore_catalog",
                "workspace": str(book),
                "bible_modules": b_files,
                "persons": persons,
                "items": items,
                "factions": factions,
                "places": places
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("=" * 72)
            print(" 📚 [底层词典与实体全景知识库]")
            print("=" * 72)
            print(" 📖 世界观公理与体系（bible/）：")
            for bf in b_files:
                print(f"     • {bf}")
            if not b_files and (book / "bible" / "project_bible.md").is_file():
                print("     • project_bible.md (单文件世界观)")

            print("\n 👤 核心人物名册（characters/）：")
            if persons:
                for p in persons:
                    id_str = f"[{p['id']}] " if p.get('id') else ""
                    tr = f"Tier {p.get('tier_rank', '?')}" if p.get('tier_rank') is not None else "Tier ?"
                    tname = p.get('tier_name') or p.get('realm') or '未定境界'
                    fac = p.get('faction') or '无势力'
                    stat = p.get('status') or 'active'
                    print(f"     • {id_str}{p.get('name')} [{tr}: {tname} ｜ 阵营: {fac} ｜ 状态: {stat}]")
            else:
                print("     （暂无登记人物卡）")

            print("\n 🗡️ 关键资产与法宝道具（entities/items/）：")
            if items:
                for it in items:
                    id_str = f"[{it['id']}] " if it.get('id') else ""
                    tr = f"Tier {it.get('tier_rank', '?')}" if it.get('tier_rank') is not None else ""
                    tname = it.get('tier_name') or '未定品阶'
                    h = it.get('holder') or '无持有者'
                    c = f"充能: {it.get('charges')}" if it.get('charges') is not None and it.get('charges') >= 0 else ""
                    extra = f" ｜ {c}" if c else ""
                    print(f"     • {id_str}{it.get('name')} [{tr} {tname} ｜ 持有者: {h}{extra}]")
            else:
                print("     （暂无登记道具卡）")

            print("\n 🏰 地缘势力与组织网络（entities/factions/）：")
            if factions:
                for fac in factions:
                    id_str = f"[{fac['id']}] " if fac.get('id') else ""
                    sc = f"规模Tier {fac.get('scale_tier', '?')}" if fac.get('scale_tier') is not None else ""
                    tname = fac.get('tier_name') or '宗门/财阀'
                    ldr = fac.get('leader') or '掌权者未知'
                    print(f"     • {id_str}{fac.get('name')} [{sc} {tname} ｜ 领袖: {ldr}]")
            else:
                print("     （暂无登记势力卡）")

            print("\n 📍 核心地标与关节点（entities/locations/）：")
            if places:
                for pl in places:
                    id_str = f"[{pl['id']}] " if pl.get('id') else ""
                    dt = f"危险Tier {pl.get('danger_tier', '?')}" if pl.get('danger_tier') is not None else ""
                    ctrl = pl.get('controlling_faction') or '中立/无主'
                    print(f"     • {id_str}{pl.get('name')} [{dt} ｜ 管辖: {ctrl}]")
            else:
                print("     （暂无登记地点卡）")

            print("\n" + "-" * 72)
            print(" 💡 快捷命令:")
            print("   • 查实体全息档案: python studio.py lore entity <角色/道具/势力名>")
            print("   • 查具体字段属性: python studio.py lore query <实体名> <字段名>")
            print("   • 两实体对校比对: python studio.py lore compare <角色A> <角色B>")
            print("   • 查世界战力标尺: python studio.py lore scale")
            print("   • 查世界底层公理: python studio.py lore rules")
        return 0

    if act == "entity":
        target_name = getattr(args, "name", None) or getattr(args, "topic", "") or ""
        prof = _get_entity_full_profile(book, target_name)
        if not prof:
            if js:
                print(json.dumps({"ok": False, "error": f"未找到实体「{target_name}」的卡片或台账记录",
                                  "query": target_name}, ensure_ascii=False))
            else:
                print(f"❌ 未找到实体「{target_name}」的卡片或台账记录（请检查拼写或运行 python studio.py lore list）")
            return 1
        if js:
            print(json.dumps({"ok": True, "profile": prof}, ensure_ascii=False, indent=2))
        else:
            print("=" * 72)
            print(f" 📇 [实体全息档案] {prof.get('name')} ({prof.get('type')})")
            print("=" * 72)
            tr = prof.get('tier_rank')
            tname = prof.get('tier_name') or prof.get('realm') or '无'
            print(f" • 实力位阶: Tier {tr if tr is not None else '?'} [{tname}]")
            if prof.get('power_benchmark'):
                print(f" • 破坏力标尺: {prof.get('power_benchmark')}")
            if prof.get('sensory_anchor'):
                print(f" • 视觉物象: {prof.get('sensory_anchor')}")
            if prof.get('faction'):
                print(f" • 所属阵营: {prof.get('faction')}")
            if prof.get('holder'):
                print(f" • 当前持有者: {prof.get('holder')}")
            if prof.get('charges') is not None and prof.get('charges') >= 0:
                print(f" • 充能状态: 剩余 {prof.get('charges')} 次 (上限 {prof.get('max_charges', '?')})")
            if prof.get('cost_per_use'):
                print(f" • 催动代价: {prof.get('cost_per_use')}")
            if prof.get('scale_tier') is not None:
                print(f" • 势力规模: Tier {prof.get('scale_tier')}")
            if prof.get('core_assets'):
                print(f" • 王牌资产: {', '.join(prof.get('core_assets'))}")
            if prof.get('danger_tier') is not None:
                print(f" • 危险等级: Tier {prof.get('danger_tier')}")
            if prof.get('environment_rules'):
                print(f" • 环境法则: {'; '.join(prof.get('environment_rules'))}")
            addrs = prof.get('address_matrix')
            if addrs and isinstance(addrs, dict):
                print(" • 法定称谓对账表:")
                for tgt, addr in addrs.items():
                    print(f"     - 称呼「{tgt}」为: {addr}")
            rels = prof.get('relations')
            if rels and isinstance(rels, list):
                print(" • 动态人际张力:")
                for r in rels:
                    print(f"     - 对「{r.get('target')}」: [{r.get('type')}] {r.get('desc', '')}")
            print(f" • 数据来源卡片: {prof.get('card_file', '无独立卡文件')}")
        return 0

    if act == "query":
        target_name = getattr(args, "name", None) or ""
        field = getattr(args, "field", None) or ""
        prof = _get_entity_full_profile(book, target_name)
        if not prof:
            if js:
                print(json.dumps({"ok": False, "error": f"未找到实体「{target_name}」", "name": target_name}, ensure_ascii=False))
            else:
                print(f"❌ 未找到实体「{target_name}」")
            return 1

        val = None
        if field.startswith("address_to:") or field.startswith("address:"):
            sub_target = field.split(":", 1)[1].strip()
            target_prof = _get_entity_full_profile(book, sub_target)
            if target_prof:
                val = _resolve_mutual_address(prof, target_prof)
            else:
                val = (prof.get("address_matrix") or {}).get(sub_target, "(未登记)")
        elif field in ("address", "addresses"):
            val = prof.get("address_matrix")
        else:
            val = prof.get(field)
            if val is None:
                # 兼容字段别名
                if field in ("tier", "realm"):
                    val = prof.get("tier_name") or prof.get("realm")
                elif field in ("rank", "tier_rank"):
                    val = prof.get("tier_rank")
                elif field in ("anchor", "sensory"):
                    val = prof.get("sensory_anchor")
                elif field in ("actions", "micro_action"):
                    val = prof.get("micro_actions")

        if js:
            print(json.dumps({"ok": True, "name": target_name, "field": field, "value": val}, ensure_ascii=False, indent=2))
        else:
            if val is not None:
                if isinstance(val, (dict, list)):
                    print(json.dumps(val, ensure_ascii=False, indent=2))
                else:
                    print(str(val))
            else:
                print(f"⚠️ 实体「{target_name}」未登记属性「{field}」（可用属性: {', '.join(k for k, v in prof.items() if v is not None)}）")
                return 1
        return 0

    if act == "compare":
        char_a = getattr(args, "char_a", None) or ""
        char_b = getattr(args, "char_b", None) or ""
        prof_a = _get_entity_full_profile(book, char_a)
        prof_b = _get_entity_full_profile(book, char_b)
        if not prof_a:
            print(f"❌ 未找到实体 A: 「{char_a}」", file=sys.stderr)
            return 1
        if not prof_b:
            print(f"❌ 未找到实体 B: 「{char_b}」", file=sys.stderr)
            return 1

        tier_a = prof_a.get("tier_rank")
        tier_b = prof_b.get("tier_rank")
        delta = None
        if isinstance(tier_a, int) and isinstance(tier_b, int):
            delta = tier_a - tier_b

        addr_a_to_b = _resolve_mutual_address(prof_a, prof_b)
        addr_b_to_a = _resolve_mutual_address(prof_b, prof_a)

        name_a = prof_a.get('name')
        name_b = prof_b.get('name')
        rels_a = prof_a.get('relations') or []
        rel_a_to_b = next((r for r in rels_a if isinstance(r, dict) and r.get('target') == name_b), None)
        rels_b = prof_b.get('relations') or []
        rel_b_to_a = next((r for r in rels_b if isinstance(r, dict) and r.get('target') == name_a), None)
        relations_dict = {}
        if rel_a_to_b:
            relations_dict[f"{name_a} -> {name_b}"] = rel_a_to_b
        if rel_b_to_a:
            relations_dict[f"{name_b} -> {name_a}"] = rel_b_to_a

        comp = {
            "entity_a": {"name": name_a, "tier_rank": tier_a, "tier_name": prof_a.get("tier_name"),
                         "faction": prof_a.get("faction"), "power_benchmark": prof_a.get("power_benchmark")},
            "entity_b": {"name": name_b, "tier_rank": tier_b, "tier_name": prof_b.get("tier_name"),
                         "faction": prof_b.get("faction"), "power_benchmark": prof_b.get("power_benchmark")},
            "tier_delta": delta,
            "address": {
                f"{name_a} -> {name_b}": addr_a_to_b,
                f"{name_b} -> {name_a}": addr_b_to_a
            }
        }
        if relations_dict:
            comp["relations"] = relations_dict

        if js:
            print(json.dumps({"ok": True, "comparison": comp}, ensure_ascii=False, indent=2))
        else:
            print("=" * 72)
            print(f" ⚖️ [实体侧对侧对校] {name_a} vs {name_b}")
            print("=" * 72)
            print(f" • 实体 A: {name_a} [Tier {tier_a if tier_a is not None else '?'}: {prof_a.get('tier_name') or '未定'}] (阵营: {prof_a.get('faction', '无')})")
            print(f" • 实体 B: {name_b} [Tier {tier_b if tier_b is not None else '?'}: {prof_b.get('tier_name') or '未定'}] (阵营: {prof_b.get('faction', '无')})")
            if delta is not None:
                if delta > 0:
                    print(f" • 位阶对比: {name_a} 高出 {delta} 个位阶（战力压制绝对优势）")
                elif delta < 0:
                    print(f" • 位阶对比: {name_a} 低于对方 {abs(delta)} 个位阶（跨阶交锋必须依靠核心金手指/特殊底牌，严防违规爆种吃书）")
                else:
                    print(" • 位阶对比: 同阶对决（胜负取决于底牌法宝、战斗美学与心智计谋）")
            print("-" * 72)
            print(" • 法定互称矩阵:")
            print(f"     - {name_a} 称呼 {name_b}: {addr_a_to_b}")
            print(f"     - {name_b} 称呼 {name_a}: {addr_b_to_a}")
            if relations_dict:
                print("-" * 72)
                print(" • 动态人际张力:")
                if rel_a_to_b:
                    print(f"     - {name_a} ➔ {name_b} [{rel_a_to_b.get('type')}]: {rel_a_to_b.get('desc', '')}")
                if rel_b_to_a:
                    print(f"     - {name_b} ➔ {name_a} [{rel_b_to_a.get('type')}]: {rel_b_to_a.get('desc', '')}")
        return 0

    if act == "scale":
        p_file = book / "bible" / "02_power_system.md"
        is_fallback = False
        if not p_file.is_file():
            p_file = book / "bible" / "project_bible.md"
            is_fallback = True
        if not p_file.is_file():
            print("❌ 未找到战力体系设定文件 (bible/02_power_system.md)", file=sys.stderr)
            return 1
        text = p_file.read_text(encoding="utf-8", errors="replace")
        if is_fallback:
            sec_lines = common.md_section(text, r"^##\s.*(?:境界|层级|实力|战力|标尺|Power)")
            if sec_lines:
                text = "\n".join(sec_lines).strip()
        if js:
            print(json.dumps({"ok": True, "file": p_file.name, "content": text}, ensure_ascii=False, indent=2))
        else:
            print("=" * 72)
            print(" ⚡ [全书战力阶层与物理破坏力实物标尺]")
            print("=" * 72)
            print(text)
        return 0

    if act == "rules":
        r_file = book / "bible" / "01_world_axioms.md"
        is_fallback = False
        if not r_file.is_file():
            r_file = book / "bible" / "project_bible.md"
            is_fallback = True
        if not r_file.is_file():
            print("❌ 未找到世界运转公理设定文件 (bible/01_world_axioms.md)", file=sys.stderr)
            return 1
        text = r_file.read_text(encoding="utf-8", errors="replace")
        if is_fallback:
            sec_lines = common.md_section(text, r"^##\s.*(?:世界|规则|公理|运转|法则|Axiom)")
            if sec_lines:
                text = "\n".join(sec_lines).strip()
        if js:
            print(json.dumps({"ok": True, "file": r_file.name, "content": text}, ensure_ascii=False, indent=2))
        else:
            print("=" * 72)
            print(" 📜 [世界底层不可违背客观公理]")
            print("=" * 72)
            print(text)
        return 0

    if act == "address":
        char_a = getattr(args, "topic", "") or ""
        char_b = getattr(args, "extra", "") or ""
        cdir = book / "characters"
        res = {"char_a": char_a, "char_b": char_b, "addresses": {}}
        proj = {}
        try:
            proj = common.load_json(book / "project.json", default={}) or {}
        except Exception:
            pass
        pname = str(proj.get("protagonist", "")).strip().lower()

        for name in (char_a, char_b):
            if not name:
                continue
            prof = _get_entity_full_profile(book, name)
            if prof and prof.get("address_matrix"):
                res["addresses"][name] = prof["address_matrix"]
            else:
                res["addresses"][name] = f"（未找到人物卡或未定义称谓: characters/{name}.md）"

        if char_a and char_b:
            prof_a = _get_entity_full_profile(book, char_a)
            prof_b = _get_entity_full_profile(book, char_b)
            if prof_a and prof_b:
                addr_a_to_b = _resolve_mutual_address(prof_a, prof_b)
                addr_b_to_a = _resolve_mutual_address(prof_b, prof_a)
                res["mutual"] = {
                    f"{char_a} -> {char_b}": addr_a_to_b,
                    f"{char_b} -> {char_a}": addr_b_to_a
                }
        if js:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print("=" * 72)
            print(f" 📇 [法定称谓对校速查] {char_a} ↔ {char_b}")
            print("=" * 72)
            if "mutual" in res:
                print("【定向互称对账】:")
                for k, v in res["mutual"].items():
                    print(f"   • {k}: {v}")
                print("-" * 72)
            for cname, mat in res["addresses"].items():
                print(f"【{cname} 称谓矩阵】：")
                if isinstance(mat, dict):
                    for tgt, addr in mat.items():
                        print(f"   称呼「{tgt}」: {addr}")
                else:
                    print(mat if mat else "（未定义称谓矩阵）")
                print("-" * 40)
        return 0

    if act == "get":
        target = _find_lore_target(book, topic)
        if not target or not target.is_file():
            if js:
                print(json.dumps({"ok": False, "error": f"未找到与「{topic}」相关的词典模块或卡片",
                                  "query": topic}, ensure_ascii=False))
            else:
                print(f"❌ 未找到与「{topic}」相关的词典模块或卡片（可用 python studio.py lore list 查看清单）")
            return 1
        content = target.read_text(encoding="utf-8", errors="replace")
        if js:
            print(json.dumps({"ok": True, "file": target.relative_to(book).as_posix(),
                              "content": content}, ensure_ascii=False, indent=2))
        else:
            print(f"📖 [{target.relative_to(book).as_posix()}]\n")
            print(content)
        return 0

    print(f"❌ 未知 lore 动作: {act}（合法: list | entity | query | compare | scale | rules | address | get）")
    return 2


