"""CLI 薄壳：12 命令、参数解析与编排。业务逻辑一律在 engine/*。

status / init / pack / evidence / check / sync / snapshot / export / dashboard / proposal / review / help。
退出码：0=ok / 1=阻断（含 check errors、sync 失败）/ 2=用法错。
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

from . import __version__, checks, common, evidence, snapshot, state, dashboard
from . import pack as pack_mod

 

SLOT_RE = re.compile(r"\{\{\s*slot:(\w+)(?:\|[^}]*)?\s*\}\}")


def _norm_ch(token: str) -> str | None:
    """'7'/'ch_007' → 'ch_007'；非法返回 None（调用方转退出码 2）。"""
    if isinstance(token, str) and re.fullmatch(r"ch_\d{3,}", token):
        return token
    n = common.chapter_token_to_num(token)
    return f"ch_{n:03d}" if n and n >= 1 else None


def _add_common_opts(p: argparse.ArgumentParser, json_flag: bool = True) -> None:
    p.add_argument("-w", "--workspace", help="书工作区目录（如 workspace/我的书）；仅一本书时可省略")
    if json_flag:
        p.add_argument("--json", action="store_true", help="结构化 JSON 输出（Agent 首选用例）")





# ---------------------------------------------------------------------------
# init（脚手架 + 状态播种 + 模板槽位实例化）
# ---------------------------------------------------------------------------
TEMPLATE_MAP = {
    "project_bible.md": "bible/project_bible.md",
    "main_plot.md": "outlines/main_plot.md",
    "volume_outline.md": "outlines/vol_01/outline.md",
    "character_card.md": "characters/protagonist.md",
}


def _instantiate_templates(book: Path, slots: dict[str, str]) -> list[str]:
    """templates/*.md → 工作区文件；已知槽位纯替换，未提供的保留 {{slot:…}} 由 check 督着填。"""
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
    """init 的书目录归一化：相对路径若未指向 workspace/，自动归位到 workspace/<arg>，
    避免用户在仓库根目录建书（如 `init -w 我的书` 误建到仓库根）。"""
    p = Path(arg).expanduser()
    if p.is_absolute():
        return common.resolve_workspace(arg)
    rel = p
    if not rel.parts or rel.parts[0] != "workspace":
        rel = Path("workspace") / rel
    if rel.parts == ("workspace",):
        # 裸 workspace 会把书建在仓库 workspace/ 根——list_books 只扫其子目录，这本书会"隐形"
        raise ValueError("-w 不能是 workspace 本身：请指定书目录，如 -w workspace/我的书")
    book = common.resolve_workspace(str(rel))
    assert book is not None
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
    # 书的家是 workspace/：list_books 只扫描其子目录，workspace 外的书对 status "隐形"；
    # 尤其禁止 --force/--clean 触及 workspace 之外的任意目录（防误删非书目录）。
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
            # 只清 manuscript 与收件箱里的待办提案；processed/failed 是审计记录，永不删除（审计记录只增不删原则）。
            if (book / "manuscript").exists():
                shutil.rmtree(book / "manuscript")
                (book / "manuscript" / "vol_01" / "raw").mkdir(parents=True, exist_ok=True)
                (book / "manuscript" / "vol_01" / "final").mkdir(parents=True, exist_ok=True)
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
            print(f"🧹 已清理草稿区与待办收件箱（保留圣经/细纲/状态；审计记录 processed/failed 保留）: "
                  f"{book}（{cleared} 处）")
            print("   说明：state/（6 JSON + .applied_operations.json）与快照已保留，"
                  "所以 status 里已合并/已快照的章仍会标绿；若要连同状态一起清，请用 `init --force` 整本重开。")
            return 0
        if args.force:
            import shutil
            print("⚠️ --force 整本重开：processed/failed 审计记录将随目录一并删除（整本重置的唯一例外）")
            shutil.rmtree(book)
        else:
            print(f"⛔ 工作区已存在: {book}")
            print("   继续用 status；清稿用 init --clean；确认整本重开用 init --force。")
            return 1

    for d in ("bible", "characters", "outlines/vol_01/beats",
              "manuscript/vol_01/raw", "manuscript/vol_01/final",
              "state/inbox/processed", "state/inbox/failed", "state/snapshots",
              "log/review"):
        (book / d).mkdir(parents=True, exist_ok=True)

    proj = {
        "schema": "novel-studio.project/v1",
        "title": args.title or "",
        "genre": args.genre or "",
        "protagonist": args.protagonist or "",
        "mode": "automatic",
        "words_target": [2400, 3500],
        "style_guards": [],
        "state_watch": {},
        "created_at": datetime.date.today().isoformat(),
    }
    common.dump_json(book / "project.json", proj)
    seeded = state.init_state(book)
    done = _instantiate_templates(book, {"title": args.title or "", "genre": args.genre or "",
                                         "protagonist": args.protagonist or ""})
    print(f"✅ 书工作区已创建: {book}（状态机播种 {seeded} 个 JSON；模板实例化 {len(done)} 份：{', '.join(done)}）")
    print("   下一步（Stage 0）：主控读 AGENTS.md 开局地图，按 templates/模板实例化")
    print("   填实 bible/ characters/ outlines/ 资产（未填的 {{slot:}} 会被 check 拦下）。")
    return 0


# ---------------------------------------------------------------------------
# status（进度 + 逐章流水线行； ）
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
    # 过滤无章号的杂散文件（如 ch_notes.md）：None 混进 horizon 的 max() 会 TypeError 崩掉 status
    final_files = [f for f in common.find_chapter_files(book, "final")
                   if common.chapter_number_from_name(f.name) is not None]
    words = sum(common.cjk_count(f.read_text(encoding="utf-8", errors="replace")) for f in final_files)
    latest = max((common.chapter_number_from_name(f.name) or 0 for f in final_files), default=0)
    inbox = book / "state" / "inbox"
    # 与 state._gather 同口径：draft/template/sample 不参与合并，所以不算"待合并提案"。
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
    # P2-3: 杂散大章号（如 ch_9999.md）不得让流水表按 1..horizon 全量展开——
    # 只展开连续活跃段 1..contiguous，断档后的散章/下一章逐个追加为独立行。
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
    acts.append(f"下一章 ch_{nxt:03d}：Stage 1 主控写 beats → Stage 2 drafter → Stage 3 editor → Stage 4 reader → Stage 5 极速同步+快照")
    return acts


def cmd_status(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if args.workspace and (book is None or not book.exists()):
        # 显式指定 -w 却不存在：明确报错，而非误入"还没有书"的兜底话术（P3-25）
        print(f"❌ 指定的书工作区不存在: {book}")
        books = common.list_books()
        if books:
            print("   现有书：" + "、".join(str(b) for b in books))
        return 1
    if book is None or not book.exists():
        books = common.list_books()
        if args.json:
            hint = ("存在多本书，请 -w 指定" if len(books) > 1
                    else 'python studio.py init -w workspace/<slug> -t "书名"')
            # exists=False 表示"未解析到唯一选中书"，而非"没有任何书"；用 reason 显式说明歧义来源。
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
    mark = lambda b: "✅" if b else "· "  # noqa: E731
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


def _status_debts(book) -> None:
    """账上提醒（纯数出来的事实）：快到期/已逾期的线 + failed/ 积压。"""
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
    except Exception:  # noqa: BLE001 —— 提醒行永不压垮 status
        pass
    for n in notes:
        print(f"      {n}")


# ---------------------------------------------------------------------------
# pack：单章上下文三层装配 
# ---------------------------------------------------------------------------
def cmd_pack(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "project.json").exists():
        print("❌ 未找到书工作区或其 project.json（先运行 init）")
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
# evidence：机械证据（纯 JSON 输出；空结果=合法事实 rc 0；用法错 rc 2）
# ---------------------------------------------------------------------------
def cmd_evidence(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "project.json").exists():
        print("❌ 未找到书工作区或其 project.json（先运行 init）")
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
    else:  # dup | style
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
# check：结构/schema/算术体检（errors→rc1 阻断；warnings 只报数不阻断）
# ---------------------------------------------------------------------------
def cmd_check(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "project.json").exists():
        print("❌ 未找到书工作区或其 project.json（先运行 init）")
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
        for w in report["warnings"]:
            print(f" ⚠️ [{w['code']}] {w['msg']}")
        if not report["errors"] and not report["warnings"]:
            print(" ✅ 无事实级问题")
        print(f" 汇总：errors {len(report['errors'])} ｜ warnings {len(report['warnings'])}"
              f" ｜ 定稿章数 {report['stats'].get('final_chapters', 0)}")
    return 0 if report["ok"] else 1


# ---------------------------------------------------------------------------
# sync：提案合并 → 状态体检 → 快照（Stage 5 闭环）
# ---------------------------------------------------------------------------
def cmd_sync(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "project.json").exists():
        print("❌ 未找到书工作区或其 project.json（先运行 init）")
        return 1
    ch = _norm_ch(args.chapter)
    if ch is None:
        print(f"❌ 无法解析章节编号: {args.chapter!r}（示例: 6 或 ch_006）")
        return 2

    inbox = book / "state" / "inbox"
    proposal_path = None
    for cand in (inbox / f"{ch}.json", inbox / "failed" / f"{ch}.json"):
        if cand.is_file():
            proposal_path = cand
            break
    has_proposal = proposal_path is not None
    has_manuscript = bool(common.find_chapter_files(book, "final", ch))

    # 前置闸门（dry-run 与正式一致）：定稿必须存在；提案必须存在且内容对应本章。
    if not has_manuscript:
        print(f"❌ 未找到 {ch} 的定稿（final），拒绝空同步（Stage 5 输入合同：beats/raw/final 齐）")
        return 1
    if not has_proposal:
        strays = ([p.name for p in inbox.glob(f"{ch}.*") if p.suffix == ".json"
                   and not p.name.endswith(state.NO_MERGE_SUFFIXES)] if inbox.is_dir() else [])
        hint = (f"（发现同章非规范命名：{'、'.join(sorted(strays))}——在途提案每章仅一份，"
                f"文件名须为 {ch}.json；已封存章的修订并入下一章提案随 sync 合并）") if strays else ""
        print(f"❌ 未找到 {ch} 的正式状态提案（inbox 与 failed/ 均无），拒绝空同步{hint}")
        return 1
    try:
        proposal_data = common.load_json(proposal_path)
    except ValueError as exc:
        print(f"❌ 提案 JSON 解析失败: {exc}")
        return 1
    if not isinstance(proposal_data, dict) or proposal_data.get("chapter") != ch:
        got = proposal_data.get("chapter") if isinstance(proposal_data, dict) else f"非对象({type(proposal_data).__name__})"
        print(f"❌ 提案内容与同步目标不一致: {proposal_path.name} 的 chapter={got} ≠ {ch}，拒绝空同步")
        return 1

    # 引文接地闸门（0 token）：quote 必须逐字见于当章 final——编造/改写引文物理上无法过闸。
    quote_errors = checks.validate_quotes(book, ch, proposal_data)
    if quote_errors:
        for e in quote_errors:
            print(f"❌ 引文校验: {e}")
        return 1

    # 前置闸门：Stage 5 输入合同 beats/raw/final 齐（novel_workflow.md#Stage 5）。
    # 无 beats 细纲不得封存——防止"无细纲、零更新"的章被空提案推进（配合空提案 no-op 识别）。
    if not common.find_chapter_files(book, "beats", ch):
        print(f"❌ 未找到 {ch} 的 beats 细纲，拒绝封存（Stage 5 输入合同：beats/raw/final 齐）")
        return 1
    if not common.find_chapter_files(book, "raw", ch):
        print(f"❌ 未找到 {ch} 的 raw 草稿，拒绝封存（Stage 5 输入合同：beats/raw/final 齐）")
        return 1

    # 校对注记（可选机制：若存在则做软性提示，未创建则直通跳过以极速节省 Token）
    dest = book / "log" / "review" / f"{ch}.md"
    if dest.is_file():
        gate = checks.review_gate(book, ch)
        if gate:
            for g in gate:
                print(f"ℹ️ 校对注记提示：{g}")

    overall = state.apply_inbox(book, expect_chapter=ch, dry_run=args.dry_run)
    verify_errors: list[str] = []
    snap_msg, snap_ok = "", True
    applied_now = overall.get("applied", 0)
    # 只有真正应用/重复通过才算有效同步；错章/空转（skipped>0 且 applied=0）拒绝。
    no_op = applied_now == 0 and overall.get("duplicates", 0) == 0
    if no_op and not overall.get("failed"):
        print("❌ 未合入任何变更（提案为错章/被留置/空提案），拒绝封存快照")
        if any(r.get("noop") for r in overall["results"]):
            print("   ↳ 空提案已归档 processed/：如需重提，请修改内容并换新 operation_id 后放回 state/inbox/")
        return 1
    if not args.dry_run and overall["failed"] == 0 and applied_now > 0:
        verify_errors = state.verify_state(book)
        if not verify_errors:
            try:
                snap_ok, snap_msg = snapshot.create_snapshot(book, f"{ch}_done")
            except Exception as exc:  # noqa: BLE001 —— 状态已合并，快照失败须显性化而非裸崩（P2-4/P3-16）
                snap_ok, snap_msg = False, f"快照创建异常（状态已合并，可用 snapshot create 手动补拍）：{exc}"

    payload = {"chapter": ch, "dry_run": args.dry_run, "apply": overall,
               "verify_errors": verify_errors, "snapshot": {"ok": snap_ok, "name": snap_msg}
               if not args.dry_run and overall["failed"] == 0 and applied_now > 0 else None}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print(f" 🔄 [Stage 5 同步流水线] {ch}" + ("  [DRY-RUN]" if args.dry_run else ""))
        print("=" * 70)
        for r in overall["results"]:
            print(f" 📄 {r.get('file','?')}")
            for line in r.get("updated", []):
                print(f"    {line}")
            for line in r.get("warnings", []):
                print(f"    ⚠️ {line}")
            for line in r.get("errors", []):
                print(f"    ❌ {line}")
            if r.get("note"):
                print(f"    ℹ️ {r['note']}")
            if r.get("skipped"):
                print(f"    ⏭️ {r['skipped']}")
            if r.get("archived_to"):
                print(f"    📦 归档 → {Path(r['archived_to']).parent.name}/{Path(r['archived_to']).name}")
        if overall["picked_up"]:
            print(" ↩️ 已从 failed/ 捡回本章提案重试")
        print(f" 汇总：合并 {overall['applied']} ｜ 重复跳过 {overall['duplicates']} ｜ "
              f"失败 {overall['failed']} ｜ 留置 {overall['skipped']}")
        if verify_errors:
            print(" ❌ 状态体检未通过（未封存快照）：")
            for e in verify_errors:
                print(f"    {e}")
        elif snap_msg:
            print(f" 📸 快照：{'✅ ' if snap_ok else '❌ '}{snap_msg}")
    if overall["failed"] or verify_errors or (not snap_ok and snap_msg):
        return 1
    return 0


# ---------------------------------------------------------------------------
# proposal：new——骨架生成（结构预填，内容留白；引擎不判断该不该上账）
# ---------------------------------------------------------------------------
def _cmd_proposal_check(book: Path, ch: str, args) -> int:
    """在途提案结构预检 + 三方事实对照（不落盘；不要求 final/注记在场——那是 sync 的闸门）。"""
    def _fail(msg: str) -> int:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch, "error": msg}, ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return 1

    inbox = book / "state" / "inbox"
    proposal_path = None
    for cand in (inbox / f"{ch}.json", inbox / "failed" / f"{ch}.json"):
        if cand.is_file():
            proposal_path = cand
            break
    if proposal_path is None:
        return _fail(f"未找到 {ch} 的在途提案（state/inbox 与 failed/ 均无）")
    try:
        proposal = common.load_json(proposal_path)
    except ValueError as exc:
        return _fail(f"提案 JSON 解析失败: {exc}")
    if not isinstance(proposal, dict) or proposal.get("chapter") != ch:
        got = proposal.get("chapter") if isinstance(proposal, dict) else "非对象"
        return _fail(f"提案内容与目标不一致: {proposal_path.name} 的 chapter={got} ≠ {ch}")
    rep = state.apply_proposal(book, proposal, expected_chapter=ch, dry_run=True)
    facts = checks.proposal_cross_facts(book, ch, proposal)
    quote_errors = checks.validate_quotes(book, ch, proposal)
    payload = {"chapter": ch, "proposal": proposal_path.name, "check": rep, "cross_facts": facts,
               "quote_errors": quote_errors}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print(f" 🧾 [提案结构预检] {ch}（{proposal_path.name}；不落盘）")
        print("=" * 70)
        for e in rep["errors"]:
            print(f" ❌ {e}")
        for e in quote_errors:
            print(f" ❌ 引文校验: {e}")
        for w in rep.get("warnings", []):
            print(f" ⚠️ {w}")
        if not rep["errors"]:
            for u in rep.get("updated", []):
                print(f"   {u}")
        if rep["errors"]:
            print(" 汇总：结构未过（正式 sync 同样会被整体拒绝）")
        elif rep.get("duplicate"):
            print(" 汇总：幂等重复（operation_id 已应用过，sync 会跳过）")
        else:
            print(" 汇总：结构通过（正式预演仍走 sync ch_XXX --dry-run）")
        print(" 三方对照（事实，是否上账归主控）：")
        if facts.get("amounts_in_final") is not None:
            amt = "、".join(f"{a['samples'][0]}×{a['count']}（{a['pool']}）" for a in facts["amounts_in_final"]) or "无"
            print(f"   final 金额表达: {amt} ｜ 提案 ledger 交易: {facts.get('ledger_tx_in_proposal', 0)} 笔")
        if facts.get("due_lines"):
            dl = "、".join(f"{d['id']}(target ch_{d['target_ch']:03d})" for d in facts["due_lines"])
            print(f"   到期未结线: {dl}")
            ops = facts.get("lines_ops_in_proposal") or []
            print(f"   提案 lines 区操作: {'、'.join(ops) if ops else '（无）'}")
        else:
            print("   到期未结线: 无")
        if facts.get("kno_reveal_timing"):
            tm = "、".join(f"{x['id']}(计划 ch_{x['planned_ch']:03d}，本章 ch_{x['chapter']:03d}，"
                           f"{'提前' if x['early'] else '逾期'})" for x in facts["kno_reveal_timing"])
            print(f"   知识线揭示时机与计划不符: {tm}（改不改归主控）")
        if facts.get("present_mentions") is not None:
            pm = facts["present_mentions"]
            pm_str = "、".join(f"{k}×{v}" for k, v in sorted(pm.items(), key=lambda x: -x[1])[:8]) or "无"
            pr = facts.get("present_in_proposal") or []
            print(f"   提案 present: {'、'.join(map(str, pr)) if pr else '（未声明）'} ｜ 本章提及: {pm_str}")
    return 1 if (rep["errors"] or quote_errors) else 0


def _cmd_proposal_verify(book: Path, ch: str, args) -> int:
    """算法版 Stage 4.5（0 token）：提案×final×状态 全机械对照电池。

    只数差异、只出候选清单（warn/info），零裁决、不阻断——是否处理归主控。
    """
    def _fail(msg: str) -> int:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch, "error": msg}, ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return 1

    inbox = book / "state" / "inbox"
    proposal_path = None
    for cand in (inbox / f"{ch}.json", inbox / "failed" / f"{ch}.json"):
        if cand.is_file():
            proposal_path = cand
            break
    if proposal_path is None:
        return _fail(f"未找到 {ch} 的在途提案（state/inbox 与 failed/ 均无）")
    try:
        proposal = common.load_json(proposal_path)
    except ValueError as exc:
        return _fail(f"提案 JSON 解析失败: {exc}")
    if not isinstance(proposal, dict) or proposal.get("chapter") != ch:
        got = proposal.get("chapter") if isinstance(proposal, dict) else "非对象"
        return _fail(f"提案内容与目标不一致: {proposal_path.name} 的 chapter={got} ≠ {ch}")

    quote_errors = checks.validate_quotes(book, ch, proposal)
    battery = checks.verify_candidates(book, ch, proposal)
    payload = {"chapter": ch, "proposal": proposal_path.name, "quote_errors": quote_errors, "verify": battery}
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("=" * 70)
    print(f" 🔎 [算法版 Stage 4.5] {ch}（{proposal_path.name}；0 token 机械对照——候选清单，裁决归主控）")
    print("=" * 70)
    if common.find_chapter_files(book, "final", ch):
        print(f" 引文校验：{'✅ 全部逐字命中 final' if not quote_errors else f'❌ {len(quote_errors)} 条未命中'}")
        for e in quote_errors:
            print(f"    ❌ {e}")
    else:
        print(" ℹ️ 引文校验跳过（final 缺失）")
    for it in battery.get("items", []):
        mark = "⚠️" if it["sev"] == "warn" else "ℹ️"
        print(f" {mark} [{it['code']}] {it['msg']}")
    if not battery.get("items") and not battery.get("error"):
        print(" ✅ 八项机械对照均无差异候选")
    stats = battery.get("stats") or {}
    if stats:
        print(f" 汇总：候选 {len(battery.get('items', []))} 条 ｜ {stats}")
    if battery.get("error"):
        print(f" ❌ {battery['error']}")
    return 0


def _cmd_proposal_auto(book: Path, ch: str, args) -> int:
    """自动基于 beats 与 final 生成高精准度状态提案草案（严格保证合法 schema 与增量数据）。"""
    inbox = book / "state" / "inbox"
    n = common.chapter_token_to_num(ch)
    if not n:
        print(f"❌ 非法章号: {ch}")
        return 1
    
    beats_files = common.find_chapter_files(book, "beats", n)
    if not beats_files:
        print(f"❌ 未找到 {ch} 的 beats 细纲（Stage 1 未完成）")
        return 1
    beats_text = beats_files[-1].read_text(encoding="utf-8", errors="replace")
    
    final_files = common.find_chapter_files(book, "final", n)
    final_text = final_files[-1].read_text(encoding="utf-8", errors="replace") if final_files else ""
    
    # 提取标题
    title = ""
    if final_text:
        m = re.search(r"^#\s*(?:第\s*[0-9零一二三四五六七八九十百千]+\s*章|ch_\d+)\s*(.+)$", final_text, re.M)
        if m:
            title = m.group(1).strip()
        else:
            m = re.search(r"^#\s*(.+)$", final_text, re.M)
            if m:
                title = m.group(1).strip()
    if not title:
        m = re.search(r"^#+\s*(.+)$", beats_text, re.M)
        title = m.group(1).strip() if m else f"第{n}章"

    # 提取线动作
    lines_ops = []
    action_sec = "\n".join(common.md_section(beats_text, r"^##\s*.*线(索)?动作"))
    for ln in action_sec.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("#", "<")):
            continue
        if "埋设" in ln:
            m = re.search(r"(GUN|MIS|KNO)-\d+", ln)
            name_m = re.search(r"[(（](.+?)[)）]", ln)
            name = name_m.group(1) if name_m else (m.group(0) if m else "新线索")
            lid = m.group(0) if m else None
            kind = "foreshadow" if (lid and "GUN" in lid) or ("GUN" in ln) or ("伏笔" in ln) else \
                   "misunderstanding" if (lid and "MIS" in lid) or ("MIS" in ln) or ("误会" in ln) else \
                   "knowledge" if (lid and "KNO" in lid) or ("KNO" in ln) or ("知识" in ln) or ("秘密" in ln) else "foreshadow"
            
            if kind == "foreshadow":
                item = {
                    "action": "plant",
                    "kind": "foreshadow",
                    "name": name,
                    "target_ch": n + 3,
                    "weight": 2,
                    "plan": ln
                }
            elif kind == "misunderstanding":
                parties = name if any(x in name for x in ("↔", "与", "和", "对")) else f"主角与{name}"
                item = {
                    "action": "plant",
                    "kind": "misunderstanding",
                    "parties": parties,
                    "content": ln,
                    "truth": "",
                    "level": 1,
                    "target_ch": n + 3
                }
            else:  # knowledge
                item = {
                    "action": "plant",
                    "kind": "knowledge",
                    "secret": name if len(name) > 3 else ln,
                    "target_ch": n + 3,
                    "weight": 2,
                    "note": ln
                }
            if lid:
                item["id"] = lid
            lines_ops.append(item)
        elif "推进" in ln or "更新" in ln or "揭示" in ln or "兑现" in ln or "澄清" in ln or "回唤" in ln:
            m = re.search(r"(GUN|MIS|KNO)-\d+", ln)
            if m:
                lid = m.group(0)
                kind = "foreshadow" if "GUN" in lid else "misunderstanding" if "MIS" in lid else "knowledge"
                is_resolve = ("揭示" in ln or "兑现" in ln or "澄清" in ln)
                is_remind = ("回唤" in ln and kind == "foreshadow")
                act = "resolve" if is_resolve else "remind" if is_remind else "update"
                if act in ("resolve", "remind"):
                    lines_ops.append({
                        "action": act,
                        "kind": kind,
                        "id": lid
                    })
                else:
                    up_item = {
                        "action": "update",
                        "kind": kind,
                        "id": lid
                    }
                    if kind == "knowledge":
                        up_item["note"] = ln
                    elif kind == "foreshadow":
                        up_item["plan"] = ln
                    elif kind == "misunderstanding":
                        up_item["content"] = ln
                    lines_ops.append(up_item)

    # 提取在场人物
    lookup = evidence.entity_lookup(book)
    present_chars = []
    if final_text:
        for name, aliases in lookup.items():
            c = sum(evidence.count_aliases(final_text, aliases).values())
            if c >= 2 and name not in present_chars:
                present_chars.append(name)
    if not present_chars:
        cur_state = state.load_state(book, "current")
        present_chars = list(cur_state.get("present_characters", []))

    # 生成梗概草稿
    raw_scenes = common.md_section(beats_text, r"^##\s*(?:.*冲突与场景脉络|.*场景推进|.*场景脉络|.*拍点|拍点与场景切片)")
    beats_scenes = []
    for ln in raw_scenes:
        s = ln.strip().lstrip("-*· ").strip()
        if not s or s.startswith(("#", "<")):
            continue
        if s.startswith("**本章核心矛盾死结**") or s.startswith("场景一") or s.startswith("场景二") or s.startswith("场景三"):
            continue
        # 清理前缀如 核心事件与对抗动作：或 📍 **章末物理刀口卡点**：（容忍加粗与列表符，P3-6）
        cleaned = re.sub(r"^(?:核心事件与对抗动作|角色互动与言语试探|破局行动与结果|[-·*]*\s*📍\s*\**章末物理刀口卡点\**)[:：]\s*", "", s).strip()
        if cleaned and not cleaned.startswith(("<", "<!--")):
            beats_scenes.append(cleaned)
    synopsis_text = "；".join(beats_scenes[:3]) if beats_scenes else f"完成第{n}章主线剧情推进。"

    from datetime import datetime
    mmdd = datetime.now().strftime("%m%d_%H%M%S")
    proposal = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": ch,
        "operation_id": f"{ch}.auto.{mmdd}",
        "current": {
            "present_characters": present_chars,
            "situation": synopsis_text[:100]
        },
        "entities": [],
        "lines": lines_ops,
        "ledger": {"transactions": []},
        "timeline": {
            "events": [{"time": f"第{n}日", "event": synopsis_text[:60]}],
            "arcs": []
        },
        "synopsis": {
            "title": title,
            "text": synopsis_text
        }
    }
    
    if getattr(args, "write", False):
        target = inbox / f"{ch}.json"
        if target.exists() and not getattr(args, "force", False):
            print(f"❌ {ch} 已有在途提案（state/inbox/{ch}.json）——proposal auto 拒绝覆盖；"
                  f"确认丢弃手改内容请追加 --force")
            return 1
        inbox.mkdir(parents=True, exist_ok=True)
        common.dump_json(target, proposal)
        print(f"🤖 提案草案已自动生成并写入: {inbox / f'{ch}.json'}")
        print(f"   已自动对齐标题「{title}」、在场人物 {present_chars} 与 {len(lines_ops)} 条线动作。")
        print(f"   主控可按需微调 current 字段后直接运行 `python studio.py sync {ch}`！")
        return 0
    else:
        print(json.dumps(proposal, ensure_ascii=False, indent=2))
        return 0


def cmd_proposal(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "state").is_dir():
        print("❌ 未找到书工作区状态目录（先运行 init）")
        return 1
    action = getattr(args, "pp_action", None)
    if action not in ("new", "check", "auto", "verify"):
        print("❌ proposal 需要 new/auto/check/verify 子命令，如: python studio.py proposal verify ch_003")
        return 2
    n = common.chapter_token_to_num(args.chapter)
    if n is None:
        print(f"❌ 无法解析章节号: {args.chapter}")
        return 2
    ch = f"ch_{n:03d}"
    if action == "check":
        return _cmd_proposal_check(book, ch, args)
    if action == "auto":
        return _cmd_proposal_auto(book, ch, args)
    if action == "verify":
        return _cmd_proposal_verify(book, ch, args)
    inbox = book / "state" / "inbox"
    if (inbox / f"{ch}.json").exists():
        print(f"❌ {ch} 已有在途提案（state/inbox/{ch}.json）——先处理再建新骨架")
        return 1
    from datetime import datetime
    mmdd = datetime.now().strftime("%m%d_%H%M%S")
    skeleton = {
        "schema": "novel-studio.state-mutation/v2", "chapter": ch,
        "operation_id": f"{ch}.director.{mmdd}",
        # current 只写增量（键清单见 engine/schemas/current.schema.json）；不预填空值——
        # 空串曾把上一章的现场速写整体清掉，未填骨架应当保持 no-op 而不是清档
        "current": {},
        "entities": [], "lines": [],
        "ledger": {"transactions": []}, "timeline": {"events": [], "arcs": []},
        "synopsis": {"title": "", "text": ""},
    }
    if getattr(args, "write", False):
        common.dump_json(inbox / f"{ch}.json", skeleton)
        print(f"🧩 骨架已写入: {inbox / f'{ch}.json'}")
        sys.stdout.flush()
        print(f"   填六区后 `python studio.py sync {ch} --dry-run` 预演；"
              f"纪律与键形状见 {inbox / 'README.md'}", file=sys.stderr)
        return 0
    print(json.dumps(skeleton, ensure_ascii=False, indent=1))
    sys.stdout.flush()
    print(f"🧩 骨架已打印（不落盘）：填六区后存为 state/inbox/{ch}.json；"
          f"纪律与键形状见 {inbox / 'README.md'}；只写增量、事实须能在 {ch} final 找到出处",
          file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# review：校对注记骨架（预填验收条目与机器数据；结果与证据仍由主控填写）
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
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "project.json").exists():
        print("❌ 未找到书工作区或其 project.json（先运行 init）")
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
# snapshot：list / create / rollback（--clean-drafts 清理超前稿件）
# ---------------------------------------------------------------------------
def cmd_snapshot(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "state").is_dir():
        print("❌ 未找到书工作区状态目录（先运行 init）")
        return 1
    action = getattr(args, "snap_action", None)
    if action in (None, "list"):
        names = snapshot.list_snapshots(book)
        if args.json:
            print(json.dumps({"snapshots": names}, ensure_ascii=False, indent=2))
        elif not names:
            print("（暂无快照）")
        else:
            print("📂 历史快照：")
            for n in names:
                print(f"   - {n}")
        return 0
    if action == "create":
        try:
            ok, msg = snapshot.create_snapshot(book, args.name)
        except ValueError as e:
            print(f"❌ {e}")
            return 2
        print(("📸 ✅ " if ok else "📸 ❌ ") + msg)
        return 0 if ok else 1
    if action == "rollback":
        try:
            ok, msg, chosen = snapshot.rollback_snapshot(book, args.name)
        except ValueError as e:
            print(f"❌ {e}")
            return 1
        print(("🔄 ✅ " if ok else "🔄 ❌ ") + msg)
        if ok and args.clean_drafts:
            base = snapshot.chapter_of_snapshot(chosen)
            removed = 0
            pending_hint: list[str] = []
            if base:
                for a in ("final", "raw"):
                    for f in common.find_chapter_files(book, a):
                        num = common.chapter_number_from_name(f.name)
                        if num and num > base:
                            f.unlink()
                            removed += 1
                for f in (book / "outlines").glob("*/beats/ch_*.md"):
                    num = common.chapter_number_from_name(f.name)
                    if num and num > base:
                        f.unlink()
                        removed += 1
                # P3-15: 超章校对注记一并清理；超章待办提案只提示不删（保住可能仍有价值的工作）
                rev = book / "log" / "review"
                if rev.is_dir():
                    for f in rev.glob("ch_*.md"):
                        num = common.chapter_number_from_name(f.name)
                        if num and num > base:
                            f.unlink()
                            removed += 1
                if (book / "state" / "inbox").is_dir():
                    pending_hint = [p.name for p in (book / "state" / "inbox").glob("ch_*.json")
                                    if (nn := common.chapter_number_from_name(p.name))
                                    and nn > base and not p.name.endswith(state.NO_MERGE_SUFFIXES)]
            print(f"🧹 清理超前于快照的稿件/细纲/注记：{removed} 个文件")
            if pending_hint:
                print(f"   ↳ 收件箱仍有 {len(pending_hint)} 份超章待办提案未删（保守起见请自行定夺）：{'、'.join(pending_hint[:5])}")
        return 0 if ok else 1
    return 2


# ---------------------------------------------------------------------------
# export：全书编译（--txt 拼接 / --views 状态视图渲染）
# ---------------------------------------------------------------------------
def cmd_export(args) -> int:
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "project.json").exists():
        print("❌ 未找到书工作区或其 project.json（先运行 init）")
        return 1
    if not args.txt and not args.views:
        args.txt = args.views = True  # 无标记 = 全量
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
    book = common.resolve_workspace(args.workspace)
    if book is None or not (book / "project.json").exists():
        print("❌ 未找到书工作区或其 project.json（先运行 init）")
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
        print(f"    可直接在浏览器打开预览人物关系网、伏笔看板与情绪心电图！")
    return 0


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------
COMMAND_HELP = {
    "status": "进度总览 + 逐章流水线 + 下一步指向",
    "init": "创建/清理书工作区（脚手架+状态播种+模板槽位实例化）",
    "pack": "单章上下文三层装配（P0 热 / P1 别名触发 / P2 冷索引）",
    "evidence": "机械证据：all|mentions|gaps|dup|style|words|file|candidates|prev（纯 JSON，零裁决）",
    "check": "结构/schema/算术体检（errors 只允许事实级；有 errors 退出码 1）",
    "sync": "提案合并 → 状态体检 → 快照（Stage 5 闭环，可 --dry-run）",
    "snapshot": "快照 list / create NAME / rollback NAME [--clean-drafts]",
    "export": "全书编译：--txt 拼接正文，--views 渲染状态视图",
    "proposal": "提案：new 骨架 ｜ auto 自动装配 ｜ check 结构预检+三方事实对照 ｜ verify 算法版Stage4.5机械对照",
    "dashboard": "生成交互式全景看板 HTML（人物关系网/伏笔看板/情绪心电图）",
    "review": "校对注记：new <章节>（骨架预填验收条目+机器数据，--write 写 log/review/）",
    "help": "本命令目录（--json 供宿主解析）",
}


def cmd_help(args) -> int:
    parser = _build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    names = list(subs.choices)
    if args.json:
        payload = {"version": __version__, "exit_codes": {"0": "ok", "1": "blocked", "2": "usage"},
                   "commands": [{"name": n, "help": COMMAND_HELP.get(n, "")} for n in names]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"Novel Studio 引擎 v{__version__}（创作规则见 AGENTS.md）")
    for n in names:
        print(f"  {n:<9} {COMMAND_HELP.get(n, '')}")
    print("退出码：0=ok ｜ 1=阻断 ｜ 2=用法错。Agent 首选各命令的 --json。")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="studio", description="Novel Studio 确定性引擎（薄壳）")
    p.add_argument("--version", action="version", version=f"novel-studio {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    _build_subparsers(sub)
    return p


def _build_subparsers(sub: argparse._SubParsersAction) -> None:
    q = sub.add_parser("status", help="进度总览 + 逐章流水线 + 下一步指向")
    _add_common_opts(q)
    q.set_defaults(func=cmd_status)

    q = sub.add_parser("init", help="创建/清理书工作区（脚手架+状态播种+模板槽位实例化）")
    _add_common_opts(q, json_flag=False)
    q.add_argument("-t", "--title", help="书名")
    q.add_argument("-g", "--genre", help="题材（如 仙侠/悬疑/科幻）")
    q.add_argument("-p", "--protagonist", help="主角名")
    q.add_argument("--clean", action="store_true",
                   help="清稿重来（清 manuscript 与待办提案；保留 processed/failed 审计与状态）")
    q.add_argument("--force", action="store_true",
                   help="整本重开（仅限已登记书目录；危险：连 processed/failed 审计记录一并删除，"
                        "需保留审计请用 --clean）")
    q.set_defaults(func=cmd_init)

    q = sub.add_parser("pack", help="单章上下文打包（P0 热/P1 触发/P2 冷索引）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", help="目标章节（如 7 或 ch_007）")
    q.add_argument("--lean", action="store_true", help="只给 P0")
    q.add_argument("--full", action="store_true", help="P1 命中实体附卡全文")
    q.add_argument("--open", dest="open_path", help="取工作区内任一文件原文（相对路径）")
    q.set_defaults(func=cmd_pack)

    q = sub.add_parser("evidence", help="机械证据：all|mentions|gaps|dup|style|words|file|candidates|prev")
    _add_common_opts(q)
    q.add_argument("kind", choices=["all", "mentions", "gaps", "dup", "style", "words", "file",
                                    "candidates", "prev"])
    q.set_defaults(func=cmd_evidence)  # file 接受第二参（章节号）
    q.add_argument("args", nargs="*", help="kind 参数（名字/章节等）")
    q.set_defaults(func=cmd_evidence)

    q = sub.add_parser("check", help="结构/schema/算术体检（errors 只允许事实级）")
    _add_common_opts(q)
    q.set_defaults(func=cmd_check)

    q = sub.add_parser("sync", help="提案合并 → 状态体检 → 快照（Stage 5 闭环）")
    _add_common_opts(q)
    q.add_argument("chapter", help="目标章节（如 7 或 ch_007）")
    q.add_argument("--dry-run", action="store_true", help="只校验预演不写入")
    q.set_defaults(func=cmd_sync)

    q = sub.add_parser("snapshot", help="快照：list（默认）| create NAME | rollback NAME")
    _add_common_opts(q)
    snap = q.add_subparsers(dest="snap_action")
    r = snap.add_parser("list", help="快照列表（默认动作）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_snapshot)
    r = snap.add_parser("create", help="创建具名快照")
    r.add_argument("name")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_snapshot)
    r = snap.add_parser("rollback", help="回滚到匹配名称的最新快照")
    r.add_argument("name")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--clean-drafts", action="store_true", help="一并清理该快照之后的孤立章节/细纲")
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_snapshot)
    q.set_defaults(func=cmd_snapshot)

    q = sub.add_parser("export", help="全书编译：--txt 拼接正文，--views 渲染状态视图")
    _add_common_opts(q)
    q.add_argument("--txt", action="store_true", help="导出 export/<书名>.txt")
    q.add_argument("--views", action="store_true", help="导出 export/views/state_view.md")
    q.set_defaults(func=cmd_export)

    q = sub.add_parser("dashboard", help="全景可视化看板：导出 HTML 交互式人物图谱与伏笔看板")
    _add_common_opts(q)
    q.set_defaults(func=cmd_dashboard)

    q = sub.add_parser("proposal", help="提案：new 骨架 ｜ auto 自动装配 ｜ check 结构预检+三方对照")
    _add_common_opts(q)
    pp = q.add_subparsers(dest="pp_action")
    r = pp.add_parser("new", help="生成最小合法骨架（schema/chapter/operation_id 预填）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.add_argument("--write", action="store_true", help="直接写入 state/inbox/ch_XXX.json（默认只打印）")
    r.set_defaults(func=cmd_proposal)
    r = pp.add_parser("auto", help="基于 beats 与 final 自动装配高精准度提案草案")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.add_argument("--write", action="store_true", help="直接写入 state/inbox/ch_XXX.json（默认只打印）")
    r.add_argument("--force", action="store_true", help="已有在途提案时强制覆盖（谨慎）")
    r.set_defaults(func=cmd_proposal)
    r = pp.add_parser("check", help="在途提案结构预检 + 三方事实对照（不落盘）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_proposal)
    r = pp.add_parser("verify", help="算法版 Stage 4.5：0 token 机械对照电池（候选清单，不阻断）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_proposal)
    q.set_defaults(func=cmd_proposal)

    q = sub.add_parser("review", help="校对注记骨架：new <章节>（预填验收条目+机器数据）")
    _add_common_opts(q)
    rv = q.add_subparsers(dest="rev_action")
    r = rv.add_parser("new", help="生成注记骨架（默认打印；--write 写 log/review/ch_XXX.md）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.add_argument("--write", action="store_true", help="写入 log/review/ch_XXX.md（已存在则拒绝）")
    r.set_defaults(func=cmd_review)
    q.set_defaults(func=cmd_review)

    q = sub.add_parser("help", help="命令目录")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_help)


def main(argv: list[str] | None = None) -> int:
    common.reconfigure_utf8()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\n⏸ 已中断（状态文件有原子写保护，重跑 status 看现场）")
        return 130
    except (ValueError, TimeoutError) as exc:
        # 统一兜底：引擎以 ValueError/TimeoutError 表达业务拒绝（状态损坏/编码错误/锁超时等），
        # 打一行可读错误而非裸 traceback（P2-1/P2-4）。
        print(f"❌ {exc}")
        return 1
