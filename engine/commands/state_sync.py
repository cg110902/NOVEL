"""状态与封存命令：sync（Stage 5 闭环）/ proposal / snapshot / checkpoint / state（手术刀纠偏）。"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

from .. import changelog, checks, common, evidence, snapshot, state

from ._shared import (_norm_ch, parse_audit_frontmatter, usage_error, ws_gate,
                      ws_gate_code)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------
def _stamp_final_hash(book: Path, ch: str) -> None:
    """ P2：封存时对当章 final 定稿盖章 SHA-256 → processed/final_hashes.json。

    封后再改 final 不再静默漂移：check 的 final_drift 档比对当前内容哈希；
    manifest 同步记录快照时刻全部 final 哈希（snapshot.create_snapshot）。
    """
    finals = common.find_chapter_files(book, "final", ch)
    if not finals:
        return
    f = finals[-1]
    try:
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        return
    path = book / "state" / "inbox" / "processed" / "final_hashes.json"
    rec: dict = {}
    if path.is_file():
        try:
            rec = common.load_json(path, default={}) or {}
        except (ValueError, OSError):
            rec = {}
    rec[ch] = {"sha256": sha, "file": f.name,
               "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    common.dump_json(path, rec)
    common.debug(f"final-stamp: {ch} → {f.name} sha256={sha[:16]}…（check 的 final_drift 档自此覆盖）")


def _stamp_state_hashes(book: Path, ch: str) -> None:
    """ P1-4：封存时对 state/*.json 十一表盖章 SHA-256 → processed/state_hashes.json。

    「提案是唯一写入口」此前只是文档口径，没有任何机械证据：谁绕过提案手改了
    state/*.json 都查不出来（final 有 final_hashes、bible 有 bible_log，唯独 state 裸奔）。
    盖章后 check 的 state_offline_edit 档能指名道姓地报出哪张表在封存后被离线改动。
    盖章失败不阻断封存主流程。
    """
    rec_path = book / "state" / "inbox" / "processed" / "state_hashes.json"
    rec: dict = {}
    if rec_path.is_file():
        try:
            rec = common.load_json(rec_path, default={}) or {}
        except (ValueError, OSError):
            rec = {}
    stamps: dict[str, str] = {}
    for key in state.STATE_KEYS:
        fp = book / "state" / f"{key}.json"
        if not fp.is_file():
            continue
        try:
            stamps[key] = hashlib.sha256(fp.read_bytes()).hexdigest()
        except OSError:
            continue
    if not stamps:
        return
    rec["last_sync_chapter"] = ch
    rec["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    rec["states"] = stamps
    try:
        common.dump_json(rec_path, rec)
    except OSError:
        return
    common.debug(f"state-stamp: {ch} → {len(stamps)} 张表盖章（check 的 state_offline_edit 档自此覆盖）")


def _append_bible_journal(book: Path, ch: str) -> None:
    """bible 版本盖章：每次成功封存向 state/bible_log.jsonl 追加一条 bible/ 设定哈希。

    用途：日后修订 bible 时可精确定位「哪些章是在旧版世界规则下写成」，回溯修订不瞎猜。
    盖章失败不阻断封存主流程。
    """
    bible_dir = book / "bible"
    single = bible_dir / "project_bible.md"
    if single.is_file():
        sha = hashlib.sha256(single.read_bytes()).hexdigest()[:16]
    elif bible_dir.is_dir():
        b_mds = sorted(bible_dir.glob("*.md"))
        h = hashlib.sha256()
        for bm in b_mds:
            h.update(bm.name.encode("utf-8"))
            h.update(bm.read_bytes())
        sha = h.hexdigest()[:16] if b_mds else ""
    else:
        sha = ""
    entry = {"chapter": ch, "bible_sha": sha,
             "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        with open(book / "state" / "bible_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def cmd_sync(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    ch = _norm_ch(args.chapter)
    if ch is None:
        return usage_error(f"无法解析章节编号: {args.chapter!r}（示例: 6 或 ch_006）",
                           args, chapter=str(args.chapter))

    inbox = book / "state" / "inbox"
    js = bool(getattr(args, "json", False))

    def _fail(msg: str, code: int = 1, hint: str = "", **extra) -> int:
        """统一失败出口：JSON 模式输出结构化错误（ P3-9），文本模式保留人话+修复指引。"""
        if js:
            print(json.dumps({"chapter": ch, "ok": False, "code": "sync_error",
                              "error": msg, **({"hint": hint} if hint else {}), **extra},
                             ensure_ascii=False))
        else:
            print(f"❌ {msg}")
            if hint:
                print(f"   💡 {hint}")
        return code

    proposal_path = None
    for cand in (inbox / f"{ch}.json", inbox / "failed" / f"{ch}.json"):
        if cand.is_file():
            proposal_path = cand
            break
    has_proposal = proposal_path is not None
    has_manuscript = bool(common.find_chapter_files(book, "final", ch))

    if not has_manuscript:
        return _fail(f"未找到 {ch} 的定稿（final），拒绝空同步（Stage 5 输入合同：beats/raw/final 齐）",
                     hint=f"请先由 Stage 3B 脱水师 Stylist 产出脱水预定稿 raw/{ch}_v3.md，"
                          f"再由 Stage 4C 定稿师 Fixer 落盘法定定稿 manuscript/vol_XX/final/{ch}.md")
    if not has_proposal:
        # 非规范命名扫描：不按文件名前缀猜，直接看同章提案（chapter 字段 = ch）的
        # 其他 *.json——技能/代理若按旧习惯产出 sweep_ch_XXX.json 等第二文件，门闸
        # 要能点名提示，否则只会得到一句泛泛的「未找到正式提案」。
        strays = []
        if inbox.is_dir():
            for p in sorted(inbox.glob("*.json")):
                if p.name == f"{ch}.json" or p.name.endswith(state.NO_MERGE_SUFFIXES):
                    continue
                try:
                    data = common.load_json(p)
                except (ValueError, OSError):
                    continue
                if isinstance(data, dict) and data.get("chapter") == ch:
                    strays.append(p.name)
        hint = (f"（发现同章非规范命名：{'、'.join(strays)}——在途提案每章仅一份，"
                f"文件名须为 {ch}.json；已封存章的修订并入下一章提案随 sync 合并）") if strays else ""
        return _fail(f"未找到 {ch} 的正式状态提案（inbox 与 failed/ 均无），拒绝空同步{hint}",
                     hint=f"运行 `python studio.py proposal new {ch} --write` 装配提案骨架，或由 Stage 4 Reader 审计交付")
    try:
        proposal_data = common.load_json(proposal_path)
    except ValueError as exc:
        return _fail(f"提案 JSON 解析失败: {exc}",
                     hint=f"检查 {proposal_path} 的 JSON 语法有效性（注意逗号、引号与括号匹配）")
    if not isinstance(proposal_data, dict) or proposal_data.get("chapter") != ch:
        got = proposal_data.get("chapter") if isinstance(proposal_data, dict) else f"非对象({type(proposal_data).__name__})"
        return _fail(f"提案内容与同步目标不一致: {proposal_path.name} 的 chapter={got} ≠ {ch}，拒绝空同步",
                     hint=f"修改提案中的 `\"chapter\": \"{ch}\"` 字段使其与文件名完全一致")

    # 引文柔性接地 + Stage 5 机械对照电池（均为 advisory，只出候选提示、绝不阻断）
    # --json 模式下 advisory 不再打印到 stdout 污染 JSON（数据本就在 payload 中）
    quote_notes = checks.validate_quotes(book, ch, proposal_data)
    battery = checks.verify_candidates(book, ch, proposal_data)
    if not js:
        if quote_notes:
            print("—— 引文柔性接地提示（advisory · 不阻断）——")
            for note in quote_notes:
                print(f" {note}")
        battery_items = battery.get("items") or []
        if battery_items:
            print("—— Stage 5 机械对照候选（advisory · 不阻断，裁决归主控）——")
            for it in battery_items:
                mark = "⚠️" if it["sev"] == "warn" else "ℹ️"
                print(f" {mark} [{it['code']}] {it['msg']}")

    if not common.find_chapter_files(book, "beats", ch):
        return _fail(f"未找到 {ch} 的 beats 细纲，拒绝封存（Stage 5 输入合同：beats/raw/final 齐）",
                     hint=f"运行 `python studio.py beats new {ch} --write` 自动装配当章细纲任务书")
    if not common.find_chapter_files(book, "raw", ch):
        return _fail(f"未找到 {ch} 的 raw 草稿，拒绝封存（Stage 5 输入合同：beats/raw/final 齐）",
                     hint=f"请由 Stage 2 Drafter 起草初稿并落盘于 manuscript/vol_XX/raw/{ch}_v1.md")

    # Stage 5 仲裁闸门（报告由 Stage 4A 审查员产出，引擎据此封存；audit_mode: strict | advisory | off）
    proj = common.load_json(book / "project.json", default={}) or {}
    audit_mode = proj.get("audit_mode", "strict")
    if audit_mode != "off":
        audit_file = book / "log" / "audit" / f"{ch}.md"
        if not audit_file.is_file():
            if audit_mode == "strict":
                return _fail(f"未找到 {ch} 的事实一致性仲裁报告（log/audit/{ch}.md），拒绝封存（Stage 5 闸门：audit_mode=strict）",
                             hint=f"由 Stage 4A 审查员 Auditor 运行 `python studio.py audit {ch} --write` 生成仲裁报告并完成裁决")
            else:
                if not js:
                    print(f"⚠️ [audit_mode=advisory] 未找到 {ch} 的事实一致性仲裁报告（log/audit/{ch}.md）")
        else:
            try:
                audit_text = audit_file.read_text(encoding="utf-8", errors="replace")
                fm = parse_audit_frontmatter(audit_text)
            except OSError:
                fm = None
            if fm is None:
                if audit_mode == "strict":
                    return _fail(f"{ch} 的仲裁报告缺少 YAML front-matter 或格式损坏"
                                 f"（须包含 hard / soft / logic / adjudicated 四键）",
                                 hint=f"检查 {audit_file} 顶部 front-matter（格式：---\\nhard: 0\\nsoft: 0\\n"
                                      f"logic: 0\\nadjudicated: false\\n---），"
                                      f"或重跑 `python studio.py audit {ch} --write` 由引擎生成骨架")
                else:
                    if not js:
                        print(f"⚠️ [audit_mode=advisory] 仲裁报告 front-matter 无法解析")
            else:
                hard_count = int(fm.get("hard", 0))
                adjudicated = bool(fm.get("adjudicated", False))
                # 轨 3（语义逻辑与出戏审查）与机械硬矛盾同闸：确凿出戏条目未裁定不放行。
                try:
                    logic_count = int(fm.get("logic", 0) or 0)
                except (TypeError, ValueError):
                    logic_count = 0
                if logic_count > 0 and not adjudicated:
                    if audit_mode == "strict":
                        return _fail(f"语义一致性仲裁未通过：{audit_file.name} 存在 {logic_count} 处"
                                     f"确凿出戏/世界观矛盾（logic > 0）且未裁定（adjudicated=false）",
                                     hint="逐条实施定向手术刀（正文层）或转办 Evolver（设定/历史层）后，"
                                          "重跑 `python studio.py audit %s --write`；"
                                          "确属有意演变请在报告「交叉核实排除」留痕并置 adjudicated: true" % ch)
                    else:
                        if not js:
                            print(f"⚠️ [audit_mode=advisory] 仲裁报告提示存在 {logic_count} 处语义/出戏条目未裁定")
                elif logic_count > 0 and adjudicated:
                    if not js:
                        print(f"ℹ️ [audit] 仲裁报告含 {logic_count} 处语义/出戏条目，但已标记 adjudicated=true，放行封存。")
                if hard_count > 0 and not adjudicated:
                    if audit_mode == "strict":
                        return _fail(f"事实一致性仲裁未通过：{audit_file.name} 存在 {hard_count} 处确凿硬矛盾（hard > 0）且未裁定（adjudicated=false）",
                                     hint=f"请由 Stage 4C 定稿师 Fixer 实施定向手术刀修复法定定稿后重跑 `python studio.py audit {ch} --write`，或在报告中完成交叉核实并将 adjudicated 设为 true / hard 修正为 0")
                    else:
                        if not js:
                            print(f"⚠️ [audit_mode=advisory] 仲裁报告提示存在 {hard_count} 处硬矛盾未裁定")
                elif adjudicated and hard_count > 0:
                    if not js:
                        print(f"ℹ️ [audit] 仲裁报告包含 {hard_count} 处硬矛盾，但已标记为已裁定 (adjudicated=true)，放行封存。")

    review_gate_msgs: list[str] = []
    dest = book / "log" / "review" / f"{ch}.md"
    if dest.is_file():
        review_gate_msgs = checks.review_gate(book, ch)
        # --json 契约：stdout 必须保持纯 JSON，注记提示并入 payload（review_gate 键）；
        # 文本模式保留人话即时输出。
        if review_gate_msgs and not js:
            for g in review_gate_msgs:
                print(f"ℹ️ 校对注记提示：{g}")

    common.debug(f"sync {ch}: dry_run={args.dry_run} final={has_manuscript} proposal={proposal_path.name if proposal_path else '无'}")
    overall = state.apply_inbox(book, expect_chapter=ch, dry_run=args.dry_run)
    common.debug(f"apply_inbox: applied={overall.get('applied')} failed={overall.get('failed')} "
                 f"duplicates={overall.get('duplicates')} skipped={overall.get('skipped')} "
                 f"picked_up={overall.get('picked_up')}")
    verify_errors: list[str] = []
    derived_seal: dict | None = None
    snap_msg, snap_ok = "", True
    applied_now = overall.get("applied", 0)
    # 阻断目标章的失败数：非目标章损坏提案已归档 failed/ 并带侧车，不应阻断
    # 目标章封存（否则目标章提案已归档、状态已合并、快照被拒 → 无法重跑的卡死态）
    target_failed = overall.get("failed_target", overall.get("failed", 0))
    no_op = applied_now == 0 and overall.get("duplicates", 0) == 0
    if no_op and not target_failed:
        noop_hint = ("空提案已归档 processed/：如需重提，请修改内容并换新 operation_id 后放回 state/inbox/"
                     if any(r.get("noop") for r in overall["results"]) else "")
        return _fail("未合入任何变更（提案为错章/被留置/空提案），拒绝封存快照", hint=noop_hint,
                     apply=overall)
    if not args.dry_run and target_failed == 0 and applied_now > 0:
        verify_errors = state.verify_state(book)
        common.debug(f"verify_state（状态体检，含前置因果闸门）: {len(verify_errors)} 错误"
                     + (f"（{verify_errors[0]}）" if verify_errors else ""))
        if not verify_errors:
            # 派生封存（derived = f(十一表+正文)；失败可见但不阻断主流程）
            try:
                from ..objects import seal_derived as _seal
                derived_seal = _seal(book, ch)
            except Exception as exc:  # noqa: BLE001 — 派生永不炸封存
                derived_seal = {"sealed_ch": ch, "error": f"{type(exc).__name__}: {exc}"}
            # 封存时刻对当章 final 盖章（漂移检测的事实基线）
            _stamp_final_hash(book, ch)
            _stamp_state_hashes(book, ch)
            try:
                snap_ok, snap_msg = snapshot.create_snapshot(book, f"{ch}_done")
            except Exception as exc:
                snap_ok, snap_msg = False, f"快照创建异常（状态已合并，可用 snapshot create 手动补拍）：{exc}"
            common.debug(f"snapshot: ok={snap_ok} {snap_msg}")
            _append_bible_journal(book, ch)
            # 事件溯源：章封存锚点（state at ch_XXX 的重放边界）
            changelog.seal_chapter(book, ch)

    payload = {"chapter": ch, "dry_run": args.dry_run, "apply": overall,
               "quote_notes": quote_notes, "verify_battery": battery,
               "review_gate": review_gate_msgs,
               "derived": derived_seal,
               "verify_errors": verify_errors, "snapshot": {"ok": snap_ok, "name": snap_msg}
               if not args.dry_run and target_failed == 0 and applied_now > 0 else None}
    if verify_errors and not args.dry_run:
        # 合并已落盘但体检失败时的最小恢复指引（此前无任何出口提示）
        payload["recovery"] = ("状态已合并但体检未通过、快照未封存：修正数据后用 "
                               "`python studio.py snapshot create <name>` 手动补拍；"
                               "或 `python studio.py snapshot rollback <上一封存点>` 回退后修复提案重提。")
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
        # 「留置」语义明示：提案章节 ≠ 同步目标（或空提案）时跳过、不归档不报错，等其所属章 sync 时处理
        _non_target_failed = overall["failed"] - target_failed
        print(f" 汇总：合并 {overall['applied']} ｜ 重复跳过 {overall['duplicates']} ｜ "
              f"失败 {target_failed} ｜ 留置 {overall['skipped']}"
              + (f"（另有 {_non_target_failed} 份非本章提案失败，已归档 failed/ 并附侧车，不阻断本章封存）"
                 if _non_target_failed > 0 else "")
              + (f"（留置 = 非本章提案/空提案，未处理；将由其所属章 sync 时合并）" if overall['skipped'] else ""))
        if verify_errors:
            print(" ❌ 状态体检未通过（未封存快照）：")
            for e in verify_errors:
                print(f"    {e}")
            print(" ↩️ 恢复指引：修正数据后 `snapshot create <name>` 手动补拍；"
                  "或 `snapshot rollback <上一封存点>` 回退后修复提案重提。")
        elif snap_msg:
            print(f" 📸 快照：{'✅ ' if snap_ok else '❌ '}{snap_msg}")
        if derived_seal and not derived_seal.get("error"):
            print(f" 🧮 派生已封存：线温 {derived_seal.get('line_temps', 0)} ｜"
                  f"场景告警 {derived_seal.get('scene_violations', 0)} ｜"
                  f"持有悬空 {derived_seal.get('holder_orphans', 0)} ｜"
                  f"认知挂旗 {derived_seal.get('knowledge_flags', 0)}")
        elif derived_seal:
            print(f" ⚠️ 派生封存异常（不阻断）：{derived_seal.get('error')}")
    if target_failed or verify_errors or (not snap_ok and snap_msg):
        return 1
    # 增量更新 SQLite 只读投影与全文检索索引
    try:
        from .. import db
        db.build_or_update_index(book)
    except Exception:
        pass
    return 0



# ---------------------------------------------------------------------------
# proposal
# ---------------------------------------------------------------------------
def _cmd_proposal_check(book: Path, ch: str, args) -> int:
    def _fail(msg: str) -> int:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch, "ok": False, "code": "proposal_error",
                              "error": msg}, ensure_ascii=False))
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
        # 已合并归档的章不再误报「在途提案缺失」，给出准确指向
        try:
            merged = state.load_state(book, "synopsis").get("chapters", {}).get(ch)
        except (ValueError, OSError):
            merged = None
        if merged:
            return _fail(f"{ch} 已合并归档（无在途提案）——审计记录见 state/inbox/processed/{ch}.json；"
                         "历史章标题/梗概修订请走提案 synopsis.chapters 修订通道")
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
    quote_notes = checks.validate_quotes(book, ch, proposal)
    payload = {"chapter": ch, "proposal": proposal_path.name, "check": rep, "cross_facts": facts,
               "quote_notes": quote_notes}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print(f" 🧾 [提案结构预检] {ch}（{proposal_path.name}；不落盘）")
        print("=" * 70)
        for e in rep["errors"]:
            print(f" ❌ {e}")
        for note in quote_notes:
            print(f" 🟡 引文提示: {note}")
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
            # 分列「推进/收束」与「新建」，避免把「本章只 plant 新线」显示成「（无）」
            ops = facts.get("lines_non_plant_ops_in_proposal") or []
            plants = facts.get("lines_plant_ops_in_proposal") or []
            print(f"   提案 lines 区操作（推进/收束）: {'、'.join(ops) if ops else '（无）'}")
            print(f"   提案 lines 区操作（新建 plant）: {'、'.join(plants) if plants else '（无）'}")
        else:
            print("   到期未结线: 无")
        if facts.get("kno_reveal_timing"):
            tm = "、".join(f"{x['id']}(计划 ch_{x['planned_ch']:03d}，本章 ch_{x['chapter']:03d}，"
                           f"{'提前' if x['early'] else '逾期'})" for x in facts["kno_reveal_timing"])
            print(f"   知识线揭示时机与计划不符: {tm}（改不改归主控）")
        if facts.get("resolve_cold_prereqs"):
            cp = "；".join(f"{x['id']}←前置{x['req']}《{x['req_label']}》"
                           + (f"已{x['gap']}章未见" if x.get("gap") is not None else "正文从未落笔")
                           for x in facts["resolve_cold_prereqs"])
            print(f"   回收的前置依赖已冷却: {cp}（兑现前建议先回响锚定，改不改归主控）")
        if facts.get("present_mentions") is not None:
            pm = facts["present_mentions"]
            pm_str = "、".join(f"{k}×{v}" for k, v in sorted(pm.items(), key=lambda x: -x[1])[:8]) or "无"
            pr = facts.get("present_in_proposal") or []
            print(f"   提案 present: {'、'.join(map(str, pr)) if pr else '（未声明）'} ｜ 本章提及: {pm_str}")
    return 1 if rep["errors"] else 0


def _cmd_proposal_verify(book: Path, ch: str, args) -> int:
    def _fail(msg: str) -> int:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch, "ok": False, "code": "proposal_error",
                              "error": msg}, ensure_ascii=False))
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
        # 已合并归档的章不再误报「在途提案缺失」，给出准确指向
        try:
            merged = state.load_state(book, "synopsis").get("chapters", {}).get(ch)
        except (ValueError, OSError):
            merged = None
        if merged:
            return _fail(f"{ch} 已合并归档（无在途提案）——审计记录见 state/inbox/processed/{ch}.json；"
                         "历史章标题/梗概修订请走提案 synopsis.chapters 修订通道")
        return _fail(f"未找到 {ch} 的在途提案（state/inbox 与 failed/ 均无）")
    try:
        proposal = common.load_json(proposal_path)
    except ValueError as exc:
        return _fail(f"提案 JSON 解析失败: {exc}")
    if not isinstance(proposal, dict) or proposal.get("chapter") != ch:
        got = proposal.get("chapter") if isinstance(proposal, dict) else "非对象"
        return _fail(f"提案内容与目标不一致: {proposal_path.name} 的 chapter={got} ≠ {ch}")

    quote_notes = checks.validate_quotes(book, ch, proposal)
    battery = checks.verify_candidates(book, ch, proposal)
    payload = {"chapter": ch, "proposal": proposal_path.name, "quote_notes": quote_notes, "verify": battery}
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("=" * 70)
    print(f" 🔎 [Stage 5 机械对照] {ch}（{proposal_path.name}；0 token 机械对照——候选清单，裁决归主控）")
    print("=" * 70)
    if common.find_chapter_files(book, "final", ch):
        print(f" 引文柔性接地：{'✅ 全部命中（或未携带）' if not quote_notes else f'🟡 {len(quote_notes)} 条提示（不阻断）'}")
        for note in quote_notes:
            print(f"    {note}")
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


# 细纲场景行的模板标签（emoji 与 / 或 **粗体**）。
# 判据刻意**不枚举标签名**：模板一旦新增标签（「核心戏剧支点」「感官物象锚点」
# 「物理因果气口」…），硬编码白名单（内容|场景|收束|章末物理刀口|拍点|节奏|动作）
# 就静默失效，整行连 `🎬 核心戏剧支点：` 一起写进 situation/synopsis（实测事故）。
# 现按「模板标记」剥离，且要求 emoji 或粗体标记二者之一——正文对话
# （「她低声说：我不去。」）既无 emoji 也无粗体，绝不被误剥。
_AUTO_EMOJI = r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]"
_AUTO_LABEL_BOLD_RE = re.compile(rf"^{_AUTO_EMOJI}*\s*\*\*[^*\n]{{1,24}}\*\*\s*[：:]\s*")
_AUTO_LABEL_EMOJI_RE = re.compile(rf"^{_AUTO_EMOJI}+\s*[^：:\n]{{1,24}}[：:]\s*")
_AUTO_LABEL_EMPTY_RE = re.compile(r"^[^：:\n]{1,24}[：:]\s*$")

# beats 里显式声明章题的写法之一（另一路是 front-matter `title:`）。
# 捕获部分显式排除 `*`：细纲实际写法是 `**章题建议：《第一章 活死人》**。`，
# 若允许 `*` 进入捕获再要求行尾标点，会被结尾的 `**。` 顶掉而整体失配。
_BEATS_TITLE_INLINE_RE = re.compile(
    r"章题建议\s*[:：]\s*[《【]?\s*([^》】\n*]+?)\s*(?:[》】]|$)", re.M)


def _strip_beats_label(s: str) -> str | None:
    """剥掉细纲场景行的模板标签并返回正文；返回 ``None`` 表示空标签行，应整行跳过。"""
    if _AUTO_LABEL_EMPTY_RE.match(s):
        return None
    if _AUTO_LABEL_BOLD_RE.match(s):
        return re.sub(r"\*\*", "", _AUTO_LABEL_BOLD_RE.sub("", s, count=1)).strip()
    if _AUTO_LABEL_EMOJI_RE.match(s):
        return re.sub(r"\*\*", "", _AUTO_LABEL_EMOJI_RE.sub("", s, count=1)).strip()
    return re.sub(r"\*\*", "", s).strip()


def _auto_beats_title(beats_text: str, n: int) -> str:
    """final 尚无章题行时的兜底：只认显式声明。

    **绝不扫 `^#+`**——beats 首行是 YAML front-matter，其 `#` 注释行
    （「# 推荐 10 大商业叙事章型（任选其一，灵活自定）：」）是模板说明而非章题，
    此前被当成章题写进了 synopsis（实测事故）。
    """
    fm_title = str(common.parse_front_matter(beats_text).get("title") or "").strip()
    if fm_title:
        return fm_title
    m = _BEATS_TITLE_INLINE_RE.search(beats_text or "")
    if m and m.group(1).strip():
        return m.group(1).strip()
    return f"第{n}章"


_AUTO_TARGET_PATTERNS = (
    re.compile(r"目标\s*ch_(\d+)", re.I),
    re.compile(r"目标[：:]\s*第\s*(\d+)\s*章"),
    re.compile(r"target_ch\s*[:=]?\s*(\d+)", re.I),
    re.compile(r"\bch_(\d{1,4})\b"),
)


def _auto_target_ch(ln: str, default_n: int) -> int | str:
    """从细纲线动作行提取目标章（支持「目标 ch_005」「目标：第5章」「longline」）。

    此前 proposal auto 一律落到 n+3，忽略细纲里显式书写的目标（如「目标 ch_005」），
    导致自动提案与 beats 任务书打架。
    """
    if re.search(r"\blongline\b|长线", ln, re.I):
        return "longline"
    for pat in _AUTO_TARGET_PATTERNS:
        m = pat.search(ln)
        if m:
            try:
                n = int(m.group(1))
                return n if n >= 1 else default_n
            except (ValueError, IndexError):
                continue
    return default_n


def _cmd_proposal_auto(book: Path, ch: str, args) -> int:
    inbox = book / "state" / "inbox"
    js = bool(getattr(args, "json", False))

    def _fail(msg: str, code: int = 1) -> int:
        if js:
            print(json.dumps({"chapter": ch, "ok": False, "code": "proposal_error",
                              "error": msg}, ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return code

    n = common.chapter_token_to_num(ch)
    if not n:
        return _fail(f"非法章号: {ch}", code=2)

    beats_files = common.find_chapter_files(book, "beats", n)
    if not beats_files:
        return _fail(f"未找到 {ch} 的 beats 细纲（Stage 1 未完成）")
    beats_text = beats_files[-1].read_text(encoding="utf-8", errors="replace")

    final_files = common.find_chapter_files(book, "final", n)
    final_text = final_files[-1].read_text(encoding="utf-8", errors="replace") if final_files else ""

    # 章题：优先逐字取 final 首行（契约见 `.agents/skills/reader/SKILL.md`——
    # synopsis.title 必须与 final 正文第一行完全一致，形态含纯文本「第一章 活死人」）。
    # 此前只认 `#` 前缀，纯文本章题被判为「无章题行」后回退去扫 beats 的 `^#+`，
    # 命中的是 front-matter 注释行，实测产出过
    # synopsis.title = "推荐 10 大商业叙事章型（任选其一，灵活自定）："。
    title = common.chapter_title_of(final_text) or _auto_beats_title(beats_text, n)

    lines_ops = []
    action_sec = "\n".join(common.md_section(beats_text, r"^##\s*.*线(索)?动作"))
    for ln in action_sec.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("#", "<")):
            continue
        is_plant = ("埋设" in ln) or bool(re.search(r"\bplant\b", ln, re.I))
        is_resolve = any(x in ln for x in ("揭示", "兑现", "澄清")) or bool(re.search(r"\bresolve\b", ln, re.I))
        is_remind = ("回唤" in ln) or bool(re.search(r"\bremind\b", ln, re.I))
        is_update = any(x in ln for x in ("推进", "更新")) or bool(re.search(r"\bupdate\b", ln, re.I))

        if is_plant:
            m = re.search(r"(GUN|MIS|KNO)-\d+", ln)
            name_m = re.search(r"[(（](.+?)[)）]", ln)
            name = name_m.group(1) if name_m else (m.group(0) if m else "新线索")
            lid = m.group(0) if m else None
            # kind 判定优先以 ID 前缀为准（此前「伏笔」字样优先于 KNO-XXX 前缀，
            # 会把「KNO-003 伏笔：…」错配为 foreshadow）
            if lid and lid.startswith("GUN-"):
                kind = "foreshadow"
            elif lid and lid.startswith("MIS-"):
                kind = "misunderstanding"
            elif lid and lid.startswith("KNO-"):
                kind = "knowledge"
            else:
                kind = "foreshadow" if ("GUN" in ln) or ("伏笔" in ln) else \
                       "misunderstanding" if ("MIS" in ln) or ("误会" in ln) else \
                       "knowledge" if ("KNO" in ln) or ("知识" in ln) or ("秘密" in ln) else "foreshadow"

            tgt = _auto_target_ch(ln, n + 3)
            if kind == "foreshadow":
                item = {
                    "action": "plant",
                    "kind": "foreshadow",
                    "name": name,
                    "target_ch": tgt,
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
                    "target_ch": tgt
                }
            else:
                item = {
                    "action": "plant",
                    "kind": "knowledge",
                    "secret": name if len(name) > 3 else ln,
                    "target_ch": tgt,
                    "weight": 2,
                    "note": ln
                }
            if lid:
                item["id"] = lid
            lines_ops.append(item)
        elif is_resolve or is_remind or is_update:
            m = re.search(r"(GUN|MIS|KNO)-\d+", ln)
            if m:
                lid = m.group(0)
                kind = "foreshadow" if "GUN" in lid else "misunderstanding" if "MIS" in lid else "knowledge"
                act = "resolve" if is_resolve else "remind" if (is_remind and kind == "foreshadow") else "update"
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

    # 在场名单只收「人物」。此前不过滤 type，道具与势力会混进来——实测
    # proposal auto 产出 present_characters = ["叶澜心","寒冰玉镜","水云圣宫"]。
    lookup = evidence.entity_lookup(book, kinds={"person"})
    present_chars = []
    if final_text:
        for name, aliases in lookup.items():
            c = sum(evidence.count_aliases(final_text, aliases).values())
            if c >= 2 and name not in present_chars:
                present_chars.append(name)
    if not present_chars:
        cur_state = state.load_state(book, "current")
        present_chars = list(cur_state.get("present_characters", []))

    raw_scenes = common.md_section(beats_text, r"^##\s*(?:.*冲突与场景脉络|.*场景推进|.*场景脉络|.*拍点|拍点与场景切片)")
    beats_scenes = []
    for ln in raw_scenes:
        # 只剥真正的项目符号前缀（`- `/`* `/`· `）。**不要**用 lstrip("-*· ")——
        # 后者会把「**粗体**」标签的开头两个星号一并吃掉（`- **内容**：x` →
        # `内容**：x`），使粗体标签再也匹配不上，标签残留并写进
        # situation/synopsis（这正是旧注释里那段「死代码」的真正成因）。
        s = re.sub(r"^[-*·•]+\s+", "", ln.strip()).strip()
        if not s or s.startswith(("#", "<")):
            continue
        # 剥掉细纲模板的展示性标签，只留正文（实现与理由见 _strip_beats_label）。
        cleaned = _strip_beats_label(s)
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

    # R5 防呆：beats 未填完时 proposal auto 会把 {{slot:xxx}} 原样写进状态
    # （实测 ch_053 auto 的 situation/synopsis 含 {{slot:scene_1_pivot}}），
    # 状态被模板占位符污染后 sync 仍能通过（字符串非空即合法），造成静默脏数据。
    # 现对全提案做 slot 残留扫描，命中即拒收并提示先填 beats。
    def _has_slot(obj) -> bool:
        if isinstance(obj, str):
            return "{{slot:" in obj
        if isinstance(obj, dict):
            return any(_has_slot(v) for v in obj.values())
        if isinstance(obj, (list, tuple)):
            return any(_has_slot(x) for x in obj)
        return False

    if _has_slot(proposal) or _has_slot(beats_text):
        # beats_text 含 slot 说明细纲本身未填完，直接拒收比让 auto 产出脏提案更早失败
        slot_samples = re.findall(r"\{\{slot:[^}]+\}\}", beats_text)[:3]
        sample_str = "、".join(slot_samples) if slot_samples else "{{slot:...}}"
        msg = (f"{ch} 的 beats 细纲仍含未填充槽位 {sample_str}，proposal auto 拒绝生成脏提案；"
               f"请先填完 {beats_files[-1].relative_to(book)} 中的槽位后再 auto")
        if js:
            print(json.dumps({"chapter": ch, "ok": False, "code": "slot_unfilled",
                              "error": msg, "samples": slot_samples}, ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return 1

    if getattr(args, "write", False):
        js_auto = bool(getattr(args, "json", False))
        target = inbox / f"{ch}.json"
        if target.exists() and not getattr(args, "force", False):
            msg = (f"{ch} 已有在途提案（state/inbox/{ch}.json）——proposal auto 拒绝覆盖；"
                   f"确认丢弃手改内容请追加 --force")
            print(json.dumps({"ok": False, "code": "exists", "error": msg}, ensure_ascii=False)
                  if js_auto else f"❌ {msg}")
            return 1
        inbox.mkdir(parents=True, exist_ok=True)
        common.dump_json(target, proposal)
        if js_auto:
            print(json.dumps({"ok": True, "chapter": ch,
                              "written": target.relative_to(book).as_posix(),
                              "present": present_chars, "lines_ops": len(lines_ops),
                              "note": "auto 草案的 synopsis/timeline 与 beats 措辞重叠属预期噪声，"
                                      "事实性文字请以 final 为源微调后再 sync"},
                             ensure_ascii=False))
        else:
            print(f"🤖 提案草案已自动生成并写入: {inbox / f'{ch}.json'}")
            print(f"   已自动对齐标题「{title}」、在场人物 {present_chars} 与 {len(lines_ops)} 条线动作。")
            print("   ⚠️ auto 草案的 synopsis/timeline 会与 beats 存在措辞重叠（beats_overlap advisory 属预期噪声），"
                  "事实性文字请以 final 为源微调后再 sync。")
            print(f"   主控可按需微调 current 字段后直接运行 `python studio.py sync {ch}`！")
        return 0
    else:
        print(json.dumps(proposal, ensure_ascii=False, indent=2))
        return 0


def cmd_proposal(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    action = getattr(args, "pp_action", None)
    if action not in ("new", "check", "auto", "verify"):
        return usage_error("proposal 需要 new/auto/check/verify 子命令，如: python studio.py proposal verify ch_003",
                           args)
    n = common.chapter_token_to_num(args.chapter)
    if n is None:
        return usage_error(f"无法解析章节号: {args.chapter}", args, chapter=str(args.chapter))
    ch = f"ch_{n:03d}"
    if action == "check":
        return _cmd_proposal_check(book, ch, args)
    if action == "auto":
        return _cmd_proposal_auto(book, ch, args)
    if action == "verify":
        return _cmd_proposal_verify(book, ch, args)
    inbox = book / "state" / "inbox"
    js_new = bool(getattr(args, "json", False))
    if (inbox / f"{ch}.json").exists():
        msg = f"{ch} 已有在途提案（state/inbox/{ch}.json）——先处理再建新骨架"
        print(json.dumps({"ok": False, "code": "exists", "error": msg}, ensure_ascii=False)
              if js_new else f"❌ {msg}")
        return 1
    failed_hint = ""
    if (inbox / "failed" / f"{ch}.json").is_file():
        # failed/ 同章旧提案与新建骨架并存易误判（check/verify 双查两处）
        failed_hint = (f"{ch} 在 failed/ 存在失败提案（state/inbox/failed/{ch}.json）——"
                       "sync 将优先取 inbox 新骨架；建议核对失败原因后删除或改名旧提案，避免双份混淆")
        if not js_new:
            print(f"⚠️ {failed_hint}")
    from datetime import datetime
    mmdd = datetime.now().strftime("%m%d_%H%M%S")
    is_v3 = bool(getattr(args, "v3", False))
    if is_v3:
        # v3 骨架：ops 留空待填（空 ops 会被编译器点名，正好引导去读 README 形状表）
        skeleton = {
            "schema": "novel-studio.state-mutation/v3", "chapter": ch,
            "operation_id": f"{ch}.director.{mmdd}",
            "ops": [],
        }
        fill_hint = ("填 ops 寻址增量（op 形状见本章 beats「📐 提案通道与键形状」小节，"
                     "已含全部表的动作与载荷键）")
    else:
        skeleton = {
            "schema": "novel-studio.state-mutation/v2", "chapter": ch,
            "operation_id": f"{ch}.director.{mmdd}",
            "current": {},
            "entities": [], "lines": [],
            "ledger": {"transactions": []}, "timeline": {"events": [], "arcs": []},
            "synopsis": {"title": "", "text": ""},
        }
        fill_hint = "填六区"
    if getattr(args, "write", False):
        common.dump_json(inbox / f"{ch}.json", skeleton)
        if js_new:
            print(json.dumps({"ok": True, "chapter": ch,
                              "written": (inbox / f"{ch}.json").relative_to(book).as_posix(),
                              **({"warning": failed_hint} if failed_hint else {})},
                             ensure_ascii=False))
        else:
            print(f"🧩 骨架已写入: {inbox / f'{ch}.json'}")
            sys.stdout.flush()
            print(f"   {fill_hint}后 `python studio.py sync {ch} --dry-run` 预演；"
                  f"纪律与键形状见 {inbox / 'README.md'}", file=sys.stderr)
        return 0
    print(json.dumps(skeleton, ensure_ascii=False, indent=1))
    sys.stdout.flush()
    print(f"🧩 骨架已打印（不落盘）：{fill_hint}后存为 state/inbox/{ch}.json；"
          f"纪律与键形状见 {inbox / 'README.md'}；只写增量、事实须能在 {ch} final 找到出处",
          file=sys.stderr)
    return 0



# snapshot
# ---------------------------------------------------------------------------
def cmd_snapshot(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
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
            if args.json:
                print(json.dumps({"ok": False, "code": "snapshot_error", "error": str(e)},
                                 ensure_ascii=False))
            else:
                print(f"❌ {e}")
            return 2
        if args.json:
            print(json.dumps({"ok": ok, "snapshot": msg}, ensure_ascii=False))
        else:
            print(("📸 ✅ " if ok else "📸 ❌ ") + msg)
        return 0 if ok else 1
    if action == "rollback":
        try:
            ok, msg, chosen = snapshot.rollback_snapshot(book, args.name)
        except ValueError as e:
            if args.json:
                print(json.dumps({"ok": False, "code": "snapshot_error", "error": str(e)},
                                 ensure_ascii=False))
            else:
                print(f"❌ {e}")
            return 1
        # --json 契约：回滚结果与 --clean-drafts 清理结果合并为单一 JSON 信封
        rb_payload = {"ok": ok, "snapshot": chosen, "message": msg} if args.json else None
        if not args.json:
            print(("🔄 ✅ " if ok else "🔄 ❌ ") + msg)
        if ok and args.clean_drafts:
            base = snapshot.chapter_of_snapshot(chosen)
            removed = 0
            pending_hint: list[str] = []
            trash = common.workspace_root() / ".trash"
            if base:
                def _quarantine(f, _book=book):
                    # 清理的稿件/细纲/注记不再直接 unlink，而是移入
                    # workspace/.trash/（快照只含 state 十一表，稿件一旦误删不可恢复）
                    nonlocal removed
                    try:
                        rel = f.relative_to(_book).as_posix().replace("/", "_").replace("\\", "_")
                        dest_dir = trash / f"{common.time_suffix()}_{_book.name}_rollback"
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        dest = dest_dir / rel
                        if not dest.exists():
                            f.rename(dest)
                            removed += 1
                    except OSError:
                        return  # 移动失败保守起见保留原文件

                for a in ("final", "raw"):
                    for f in common.find_chapter_files(book, a):
                        num = common.chapter_number_from_name(f.name)
                        if num and num > base:
                            _quarantine(f)
                for f in (book / "outlines").glob("*/beats/ch_*.md"):
                    num = common.chapter_number_from_name(f.name)
                    if num and num > base:
                        _quarantine(f)
                # 超章校对注记 + 催更便签一并清理
                for log_sub in ("review", "critic"):
                    log_dir = book / "log" / log_sub
                    if log_dir.is_dir():
                        for f in log_dir.glob("ch_*.md"):
                            num = common.chapter_number_from_name(f.name)
                            if num and num > base:
                                _quarantine(f)
                if (book / "state" / "inbox").is_dir():
                    pending_hint = [p.name for p in (book / "state" / "inbox").glob("ch_*.json")
                                    if (nn := common.chapter_number_from_name(p.name))
                                    and nn > base and not p.name.endswith(state.NO_MERGE_SUFFIXES)]
            if args.json:
                rb_payload["clean_drafts_removed"] = removed
                if pending_hint:
                    rb_payload["pending_hint"] = pending_hint
            else:
                print(f"🧹 清理超前于快照的稿件/细纲/注记/评测：{removed} 个文件（已移入 workspace/.trash/ 回收区备份）")
                if pending_hint:
                    print(f"   ↳ 收件箱仍有 {len(pending_hint)} 份超章待办提案未删（保守起见请自行定夺）：{'、'.join(pending_hint[:5])}")
        if args.json:
            print(json.dumps(rb_payload, ensure_ascii=False))
        return 0 if ok else 1
    return 2



def cmd_checkpoint(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()

    ch_arg = getattr(args, "chapter", None)
    if ch_arg:
        ch = _norm_ch(ch_arg)
        if ch is None:
            return usage_error(f"无法解析章节编号: {ch_arg!r}（示例: 5 或 ch_005）", args)
        ch_num = common.chapter_token_to_num(ch)
    else:
        latest = common.latest_chapter_number(book, "final") or common.latest_chapter_number(book, "beats") or 1
        ch_num = latest
        ch = f"ch_{ch_num:03d}"

    outline_files = sorted((book / "outlines").glob("*/outline.md"))

    phase_info = None
    all_phases = []
    for vol_outline_path in outline_files:
        vol_name = vol_outline_path.parent.name
        text = vol_outline_path.read_text(encoding="utf-8", errors="replace")
        phases = re.findall(
            r"-\s*\*\*([^\n*]+?)\s*[（(]\s*(?:ch_?)?(\d+)\s*[—\-–~至到]+\s*(?:ch_?)?(\d+)\s*(?:[｜|]\s*([^\n*]+?))?[)）]\s*\*\*",
            text
        )
        for idx, (pname, start_s, end_s, feat) in enumerate(phases, 1):
            s_num, e_num = int(start_s), int(end_s)
            p_dict = {
                "volume": vol_name,
                "phase_index": idx,
                "name": pname.strip(),
                "range": [s_num, e_num],
                "range_str": f"ch_{s_num:03d}—ch_{e_num:03d}",
                "feature": feat.strip() if feat else ""
            }
            all_phases.append(p_dict)
            if s_num <= ch_num <= e_num:
                phase_info = p_dict

    syn_data = state.load_state(book, "synopsis")
    tl_data = state.load_state(book, "timeline")
    cur_data = state.load_state(book, "current")

    start_scan = max(1, ch_num - 4)
    recent_chapters = []
    for n in range(start_scan, ch_num + 1):
        tok = f"ch_{n:03d}"
        syn = syn_data.get("chapters", {}).get(tok, {})
        evs = [e.get("event", "") for e in tl_data.get("events", []) if e.get("chapter") == tok]
        recent_chapters.append({
            "chapter": tok,
            "title": syn.get("title", "未命名"),
            "synopsis": syn.get("synopsis", "暂无梗概"),
            "events": evs
        })

    gaps_data = evidence.gaps(book)
    urgent_lines = [g for g in gaps_data["foreshadows"] if g.get("overdue") or g.get("idle_chapters", 0) >= 10]

    assessment = []
    directives = []
    if phase_info:
        p_end = phase_info["range"][1]
        left_in_phase = p_end - ch_num
        if left_in_phase == 0:
            assessment.append(f"🏁 已到达阶段终点（{phase_info['range_str']}）：本章必须兑现阶段大高潮与里程碑成果！")
            directives.append("本章或下一章必须完成阶段收束，兑现阶段核心成果，并为下一阶段铺设新转场与新目标。")
        elif left_in_phase <= 2:
            assessment.append(f"⏳ 阶段收束倒计时：距阶段终点仅剩 {left_in_phase} 章（目标 {phase_info['name']}）。")
            directives.append(f"剧情应收拢支线，全面推向阶段高潮（{phase_info['feature']}），切忌节外生枝。")
        else:
            assessment.append(f"🟢 阶段稳步推进中（进度 {ch_num - phase_info['range'][0] + 1}/{p_end - phase_info['range'][0] + 1}）。")
            directives.append(f"围绕本阶段核心功能（{phase_info['feature']}）按节奏层层推进矛盾与伏笔。")
    else:
        assessment.append("⚠️ 未在分卷大纲中匹配到四分位阶段，建议检查 outlines/vol_XX/outline.md 格式。")

    if urgent_lines:
        assessment.append(f"🚨 存在 {len(urgent_lines)} 条超期或闲置 ≥10 章的严重积压伏笔。")
        directives.append(f"在接下来的 5 章 Beats 中必须安排回收（resolve）积压伏笔：{', '.join(x['id'] for x in urgent_lines[:3])}。")

    payload = {
        "chapter": ch,
        "chapter_num": ch_num,
        "current_phase": phase_info,
        "all_phases": all_phases,
        "recent_progress": recent_chapters,
        "state_digest": {
            "power_level": cur_data.get("power_level", ""),
            "location": cur_data.get("location", ""),
            "goal": cur_data.get("goal", ""),
            "present_characters": cur_data.get("present_characters", [])
        },
        "urgent_lines": urgent_lines,
        "assessment": assessment,
        "directives": directives
    }

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("=" * 70)
    print(f" 🧭 [宏观航向校准点 Checkpoint] {ch}（复盘坐标与主线航向）")
    print("=" * 70)
    if phase_info:
        print(f" 🎯 当前分卷坐标：{phase_info['name']}（{phase_info['range_str']}）")
        if phase_info['feature']:
            print(f"    阶段核心功能：{phase_info['feature']}")
    print(f" 📍 当前现场状态：位阶职级「{cur_data.get('power_level','-')}」｜ 地点「{cur_data.get('location','-')}」")
    print(f"    当前核心目标：{cur_data.get('goal','-')}")
    print("-" * 70)
    print(" 📜 近 5 章推进脉络：")
    for rc in recent_chapters:
        ev_str = f" ｜ 事件: {'；'.join(rc['events'])}" if rc['events'] else ""
        print(f"   • {rc['chapter']}《{rc['title']}》: {rc['synopsis']}{ev_str}")
    print("-" * 70)
    print(" 🧭 航向与偏离评估（Drift Assessment）：")
    for a in assessment:
        print(f"   {a}")
    print(" 💡 主控调优指令（Next 5-Chapter Directives）：")
    for d in directives:
        print(f"   👉 {d}")
    print("=" * 70)
    return 0



_OBJECT_ENTITY_KIND = {"person": "person", "人物": "person", "item": "item",
                       "道具": "item", "faction": "faction", "势力": "faction",
                       "place": "location", "location": "location"}


def _object_payload(book, ref: str) -> dict:
    """对象包络查询（B1）：id/名/别名 → 信封 + 跨表 derived 速览（只读）。"""
    from ..objects.envelope import kind_of_id, to_envelope
    from ..objects.registry import build_registry, resolve_ref
    ref = str(ref or "").strip()
    out: dict = {"ref": ref, "found": False}
    if not ref:
        return out

    def _load(table: str) -> dict:
        try:
            return state.load_state(book, table)
        except (ValueError, FileNotFoundError):
            return {}

    ents = _load("entities").get("entries", []) or []
    reg = build_registry({"entries": ents})
    ent = resolve_ref(reg, ref)
    if ent is not None:
        name = str(ent.get("name", ""))
        aliases = [str(a) for a in ent.get("aliases", []) or []]
        kind = kind_of_id(ent.get("id"))
        if kind == "unknown":
            kind = _OBJECT_ENTITY_KIND.get(str(ent.get("type", "")), "entity")

        def _same(v) -> bool:
            """跨表人名比对：法定名 / 别名 / id 三者等价（resolve_ref 归一）。"""
            s = str(v or "")
            if s == name or s == ref:
                return True
            hit = resolve_ref(reg, s)
            return isinstance(hit, dict) and hit.get("name") == name
        rels = []
        for r in ent.get("relations", []) or []:
            if not isinstance(r, dict):
                continue
            tgt = str(r.get("target", ""))
            tgt_ent = resolve_ref(reg, tgt)
            rels.append({"target": tgt,
                         "target_id": str((tgt_ent or {}).get("id", "")) if tgt_ent else "",
                         "type": r.get("type", ""), "strength": r.get("strength"),
                         "status": r.get("status", ""), "since_ch": r.get("since_ch", "")})
        beliefs = [{"id": str(b.get("id", "")), "kind": str(b.get("kind", "")),
                    "content": str(b.get("content", ""))[:60],
                    "truth_ref": str(b.get("truth_ref", "") or ""),
                    "since_ch": str(b.get("since_ch", ""))}
                   for b in _load("cognition").get("entries", []) or []
                   if isinstance(b, dict) and _same(b.get("character"))]
        try:
            flags = [f for f in _load("derived").get("knowledge_flags", []) or []
                     if isinstance(f, dict) and _same(f.get("character"))]
        except (ValueError, FileNotFoundError):
            flags = []
        holds = [str(e.get("name", "")) for e in ents
                 if isinstance(e, dict) and _same(e.get("holder"))]
        cur = _load("current")
        present = (name in (cur.get("present_characters") or [])
                   or any((resolve_ref(reg, r) or {}).get("name") == name
                          for r in (cur.get("present_refs") or [])))
        locks = [str(le.get("id", "")) for le in _load("locked").get("entries", []) or []
                 if isinstance(le, dict)
                 and (name in str(le.get("fact", ""))
                      or any(_same(r) for r in (le.get("refs") or [])))]
        moods = cur.get("present_moods") or {}
        _mood = moods.get(name)
        if _mood is None:
            for _a in aliases:
                if _a in moods:
                    _mood = moods[_a]
                    break
        mood = None
        if isinstance(_mood, dict) and str(_mood.get("label", "") or ""):
            mood = {"label": str(_mood["label"])}
            if type(_mood.get("level")) is int:
                mood["level"] = _mood["level"]
        env = to_envelope(kind, ent,
                          derived={"relations": rels, "beliefs": beliefs,
                                   "knowledge_flags": flags, "holds": holds,
                                   "present": present, "locks": locks,
                                   "mood": mood},
                          prov={"table": "entities"})
        return {"ref": ref, "found": True, **env}

    # 非实体：按 id 在线/事件/锁/认知四处搜
    cand: tuple[str, dict] | None = None
    lines = _load("lines")
    for arr, skind in (("foreshadows", "foreshadow"),
                       ("misunderstandings", "misunderstanding"),
                       ("knowledge", "knowledge")):
        hit = next((g for g in lines.get(arr, []) or []
                    if isinstance(g, dict) and str(g.get("id", "")) == ref), None)
        if hit is not None:
            cand = (skind, hit)
            break
    if cand is None:
        hit = next((e for e in _load("timeline").get("events", []) or []
                    if isinstance(e, dict) and str(e.get("id", "")) == ref), None)
        if hit is not None:
            cand = ("event", hit)
    if cand is None:
        hit = next((e for e in _load("locked").get("entries", []) or []
                    if isinstance(e, dict) and str(e.get("id", "")) == ref), None)
        if hit is not None:
            cand = ("lock", hit)
    if cand is None:
        hit = next((e for e in _load("cognition").get("entries", []) or []
                    if isinstance(e, dict) and str(e.get("id", "")) == ref), None)
        if hit is not None:
            cand = ("belief", hit)
    if cand is None:
        return out
    skind, entry = cand
    derived: dict = {}
    if skind == "belief":
        flag = next((f for f in _load("derived").get("knowledge_flags", []) or []
                     if isinstance(f, dict) and f.get("cog_id") == ref), None)
        if flag:
            derived["knowledge_flag"] = flag
    env = to_envelope(skind, entry, derived=derived, prov={"table": skind})
    return {"ref": ref, "found": True, **env}


def _render_object_text(payload: dict) -> None:
    """对象包络人话渲染（只打印非空节）。"""
    a = payload.get("asserted", {}) or {}
    d = payload.get("derived", {}) or {}
    print(f"🔎 {payload.get('id', '')}（{payload.get('kind', '')}"
          f"{'｜' + str(payload.get('status')) if payload.get('status') else ''}）")
    core = {k: a.get(k) for k in ("name", "type", "aliases", "summary", "realm",
                                  "faction", "life_status", "holder", "fact", "event",
                                  "content", "secret", "character", "chapter")
            if a.get(k) not in (None, "", [])}
    for k, v in core.items():
        print(f"  {k}: {v if not isinstance(v, str) or len(v) <= 80 else v[:80] + '…'}")
    if d.get("relations"):
        print("  关系:")
        for r in d["relations"]:
            extra = "｜".join(str(x) for x in
                              (r.get("type"), r.get("strength"), r.get("status")) if x)
            print(f"    → {r.get('target', '')}"
                  + (f"（{r.get('target_id')}）" if r.get("target_id") else "")
                  + (f" {extra}" if extra else ""))
    if d.get("beliefs"):
        print("  认知:")
        for b in d["beliefs"]:
            print(f"    • {b.get('id', '')}［{b.get('kind', '')}］{b.get('content', '')}"
                  + (f" ⚓{b.get('truth_ref')}" if b.get("truth_ref") else ""))
    for f in d.get("knowledge_flags") or ([d["knowledge_flag"]] if d.get("knowledge_flag") else []):
        print(f"  挂旗: {f.get('cog_id', '')}→{f.get('verdict', '')}（{f.get('detail', '')}）")
    if d.get("holds"):
        print(f"  持有: {'、'.join(d['holds'])}")
    if d.get("present"):
        print("  在场: 是（当前现场）")
    if d.get("locks"):
        print(f"  相关锁: {'、'.join(d['locks'])}")
    if d.get("mood"):
        _m = d["mood"]
        print(f"  情绪: {_m.get('label', '')}"
              + (f"（烈度{_m['level']}）" if _m.get("level") is not None else ""))


def cmd_state(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()

    action = getattr(args, "state_action", "show")
    if not action:
        action = "show"
    js = bool(getattr(args, "json", False))

    def _fail(msg: str, code: int = 1) -> int:
        """state 手术刀错误出口：--json 一律出 JSON 信封（与 state set 成功信封同契约）。"""
        if js:
            print(json.dumps({"ok": False, "code": "state_error", "error": msg},
                             ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return code

    if action == "show":
        cur = state.load_state(book, "current")
        if getattr(args, "json", False):
            print(json.dumps(cur, ensure_ascii=False, indent=2))
        else:
            print("=" * 60)
            print(" 📍 当前现场状态速览 (current.json)")
            print("=" * 60)
            for k, v in cur.items():
                print(f" {k:<18}: {v}")
        return 0

    # ---- 派生重算：derived = f(十一表+正文)，纯函数，可反复执行 ----
    if action == "recompute":
        from ..objects import seal_derived as _seal
        try:
            cur_sealed = state.load_state(book, "derived").get("sealed_ch") or ""
        except ValueError:
            cur_sealed = ""
        latest = common.latest_chapter_number(book, "final")
        ch_tag = f"ch_{latest:03d}" if latest else (cur_sealed or "ch_000")
        try:
            summary = _seal(book, ch_tag)
        except Exception as exc:
            return _fail(f"派生重算失败: {exc}")
        if js:
            print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
        else:
            print(f"🧮 派生已重算并封存（{summary['sealed_ch']}）：线温 {summary['line_temps']} ｜"
                  f"场景告警 {summary['scene_violations']} ｜持有悬空 {summary['holder_orphans']} ｜"
                  f"认知挂旗 {summary['knowledge_flags']}")
        return 0

    # ---- 对象包络查询（B1）：id/名/别名 → 信封 + 跨表 derived 速览 ----
    if action == "object":
        ref = str(getattr(args, "target", "") or "").strip()
        if not ref:
            return _fail("用法: state object <id/名/别名>（如 state object 林牧）", code=2)
        payload = _object_payload(book, ref)
        if not payload.get("found"):
            return _fail(f"未找到对象「{ref}」"
                         "（entities/lines/events/locked/cognition 均无此 id/名/别名）",
                         code=1)
        if js:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _render_object_text(payload)
        return 0

    # ---- 卷级 rollup（D1）：卷末封存后生成态势摘要 ----
    if action == "rollup":
        from .. import rollup as rollup_mod
        vol = str(getattr(args, "vol", "") or "").strip()
        try:
            data = rollup_mod.build_rollup(book, vol)
        except ValueError as exc:
            return _fail(str(exc), code=2)
        out_path = rollup_mod.save_rollup(book, vol)
        if js:
            print(json.dumps({"ok": True, "vol": vol, "path": str(out_path.relative_to(book)),
                              "entities": len(data["entities"]),
                              "open_lines": len(data["open_lines"]),
                              "at_final_ch": data["at_final_ch"]}, ensure_ascii=False))
        else:
            print(f"📦 卷末态势摘要已生成：{out_path.relative_to(book)}"
                  f"（实体 {len(data['entities'])} ｜ 未兑线 {len(data['open_lines'])} ｜"
                  f" 至 ch_{data['at_final_ch']:03d}）")
            print("   后卷章节 pack 将自动注入「前情卷末态势」块（≤1000 token）")
        return 0

    # ---- 溯源查询族：at / diff / blame（changelog 重放，零 Token） ----
    if action == "at":
        n = common.chapter_token_to_num(getattr(args, "chapter", ""))
        if not n:
            return _fail(f"无法解析章节编号: {getattr(args, 'chapter', '')!r}", code=2)
        folded, err = changelog.state_at(book, n)
        if err:
            return _fail(err)
        # 事件流未激活时 state_at 会回退到磁盘当前状态（兼容 changelog 之前建的老书，
        # 避免 state at 直接报错）。但**回退不等于等价**：把"此刻的世界"说成
        # "第 N 章封存后的世界切面"是误导，必须显式声明——本项目通篇的规矩是
        # 「不猜、绝不静默兜底」，此处不能例外。
        if not changelog.active(book):
            print("⚠️  事件流未激活（本书创建于 changelog 之前）：以下为**磁盘当前状态**，"
                  f"并非 ch_{n:03d} 的真实历史切面；跑任意一次 sync 后即可重放真实历史。",
                  file=sys.stderr)
        want_table = getattr(args, "table", None)
        if want_table:
            if want_table not in state.STATE_KEYS:
                return _fail(f"未知状态分区: {want_table}（合法: {' / '.join(state.STATE_KEYS)}）", code=2)
            payload = {"chapter": f"ch_{n:03d}", "table": want_table,
                       "state": folded.get(want_table)}
        else:
            payload = {"chapter": f"ch_{n:03d}", "tables": folded}
        if js:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"🕰️  ch_{n:03d} 封存后的世界切面（changelog 重放）")
            if want_table:
                print(json.dumps(folded.get(want_table), ensure_ascii=False, indent=2))
            else:
                cur = folded.get("current", {})
                for k, v in cur.items():
                    print(f" current.{k:<16}: {v}")
                for key in state.STATE_KEYS:
                    if key == "current":
                        continue
                    node = folded.get(key) or {}
                    size = sum(len(v) for v in node.values()) if isinstance(node, dict) else 0
                    print(f" {key:<18}: {len(node)} 键 / {size} 项")
        return 0

    if action == "diff":
        na = common.chapter_token_to_num(getattr(args, "chapter_a", ""))
        nb = common.chapter_token_to_num(getattr(args, "chapter_b", ""))
        if not na or not nb:
            return _fail("章节编号无法解析（示例: 3 或 ch_003）", code=2)
        result = changelog.diff_points(book, na, nb)
        if "error" in result:
            return _fail(result["error"])
        if js:
            print(json.dumps({"ch_a": f"ch_{na:03d}", "ch_b": f"ch_{nb:03d}",
                              "diff": result["diff"]}, ensure_ascii=False, indent=2))
        else:
            print(f"🔀 ch_{na:03d} → ch_{nb:03d} 的世界差异")
            ops_all = result["diff"]
            if not ops_all:
                print(" （无差异）")
            for table, ops in ops_all.items():
                print(f" [{table}] {len(ops)} 处变更")
                for o in ops[:8]:
                    print(f"   {o['op']:>6} {o['path']}"
                          f"  {str(o.get('before'))[:32]!r} → {str(o.get('after'))[:32]!r}")
                if len(ops) > 8:
                    print(f"   …另有 {len(ops) - 8} 处")
        return 0

    if action == "blame":
        if not changelog.active(book):
            return _fail("事件流未激活（本书在 changelog 之前创建，跑任意 sync 后开始积累）")
        target = getattr(args, "target", "")
        if not target:
            return _fail("请指定溯源目标（例如: entities.entries[p_003] 或 ledger.transactions）",
                         code=2)
        parts = target.split(".", 1)
        table, path = parts[0], (parts[1] if len(parts) > 1 else "")
        if table == state.LEGACY_ENTITIES_KEY:
            # legacy 别名：扇出四 kind 表 + 历史 entities 事件（搬迁实体的完整前世），seq 新→旧
            events = []
            for _t in (*state.KIND_TABLES, state.LEGACY_ENTITIES_KEY):
                events.extend(changelog.blame(book, _t, path))
            events.sort(key=lambda e: int(e.get("seq") or 0), reverse=True)
        else:
            if table not in state.STATE_KEYS:
                return _fail(f"未知状态分区: {table}（合法: {' / '.join(state.STATE_KEYS)}）", code=2)
            events = changelog.blame(book, table, path)
        if js:
            print(json.dumps({"target": target, "count": len(events), "events": events},
                             ensure_ascii=False, indent=2))
            return 0
        print(f"🔎 {target} 的变更史（新→旧，共 {len(events)} 条）")
        for ev in events[:30]:
            # ev["ch"] 已是规范章号（ch_NNN），此前再套一层 f"ch_{}" 渲染成 ch_ch_001
            when = str(ev.get("ch") or ev.get("ts", ""))
            print(f"  #{ev.get('seq'):>4} [{ev.get('source')}] {when} {ev.get('op')}: "
                  f"{ev.get('path')}  {str(ev.get('before'))[:36]!r} → {str(ev.get('after'))[:36]!r}"
                  + (f"  (op_id={ev.get('op_id')})" if ev.get("op_id") else ""))
        if len(events) > 30:
            print(f"  …另有 {len(events) - 30} 条（--json 看全量）")
        return 0

    target = getattr(args, "target", "")
    if not target:
        return _fail("请指定要查询或修改的字段路径（例如: current.injury 或 entities.林舟.realm）", code=2)

    parts = target.split(".", 1)
    part_name = parts[0]
    sub_path = parts[1] if len(parts) > 1 else ""

    if part_name not in state.STATE_KEYS and part_name != state.LEGACY_ENTITIES_KEY:
        return _fail(f"未知状态分区: {part_name}（合法: {' / '.join(state.STATE_KEYS)}）",
                     code=2)

    st_data = state.load_state(book, part_name)

    if action == "get":
        val = None
        if not sub_path:
            val = st_data
        elif part_name == "current":
            val = st_data.get(sub_path)
        elif part_name == "entities" or part_name in state.KIND_TABLES:
            ent_parts = sub_path.split(".", 1)
            ename = ent_parts[0]
            ent = next((e for e in st_data.get("entries", []) if e.get("name") == ename), None)
            if ent is None:
                return _fail(f"实体「{ename}」未注册", code=1)
            if len(ent_parts) > 1:
                val = ent.get(ent_parts[1])
            else:
                val = ent
        else:
            val = st_data.get(sub_path)

        # 未命中判定：容器里确实没有这个键 → 明确报「不存在」，不再打印 Python 字面量 None
        _container = st_data if not sub_path else (
            st_data if part_name == "current" or part_name in ("lines", "timeline", "ledger", "synopsis",
                                                               "locked", "cognition") else st_data)
        _missing = False
        if sub_path and val is None:
            _key = sub_path.split(".", 1)[0]
            if part_name == "entities" or part_name in state.KIND_TABLES:
                _missing = False  # 实体分支已自行处理未注册
            elif isinstance(_container, dict) and _key not in _container:
                _missing = True
        if _missing:
            return _fail(f"{target} 不存在（该分区无此字段；查全表请用 `state get {part_name}`）", code=1)
        if getattr(args, "json", False):
            print(json.dumps({"target": target, "value": val,
                              "is_null": val is None}, ensure_ascii=False, indent=2))
        else:
            if isinstance(val, (dict, list)):
                print(f"{target} = {json.dumps(val, ensure_ascii=False)}")
            elif val is None:
                print(f"{target} = null（字段存在但值为空）")
            else:
                print(f"{target} = {val}")
        return 0

    if action == "set":
        if part_name == "derived":
            return _fail("derived 为引擎派生表，禁止手术刀写入（重算请用 `state recompute`）",
                         code=1)
        raw_val = getattr(args, "value", "")
        val = raw_val
        loose_note = False
        if isinstance(raw_val, str):
            trimmed = raw_val.strip()
            if trimmed.isdigit() or re.fullmatch(r"-\d+", trimmed):
                val = int(trimmed)
            elif re.fullmatch(r"-\d+\.\d+", trimmed):
                val = float(trimmed)
            elif trimmed in ("true", "True"):
                val = True
            elif trimmed in ("false", "False"):
                val = False
            elif trimmed in ("null", "None"):
                val = None
            elif (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
                try:
                    val = json.loads(trimmed)
                except Exception:
                    try:
                        import ast
                        val = ast.literal_eval(trimmed)
                    except Exception:
                        if trimmed.startswith("{") and trimmed.endswith("}"):
                            inner = trimmed[1:-1].strip()
                            obj_dict = {}
                            pairs = re.split(r",\s*(?=[A-Za-z0-9_]+:)", inner)
                            for p in pairs:
                                if ":" in p:
                                    pk, pv = p.split(":", 1)
                                    pv = pv.strip().strip("'\"")
                                    # 宽松解析的内层纯数字转 int（此前静默字符串化，
                                    # 对 int 字段纠偏会被写闸门以「类型应为 int」拒回）
                                    if re.fullmatch(r"-?\d+", pv):
                                        pv = int(pv)
                                    obj_dict[pk.strip().strip("'\"")] = pv
                            if obj_dict:
                                val = obj_dict
                                loose_note = True

        if part_name == "current":
            if not sub_path:
                return _fail("修改 current 必须指定具体字段（例如 current.injury）", code=2)
            st_data[sub_path] = val
        elif part_name == "entities" or part_name in state.KIND_TABLES:
            ent_parts = sub_path.split(".", 1)
            if part_name == "entities":
                # legacy 别名：定位 owner kind 表，后续语义闸门与落盘一律走 kind 表
                # 若未找到，尝试按 id 定位（p_001 等）或自动创建
                orig_name = ent_parts[0]
                part_name, st_data, _found = state.find_entity_owner(book, orig_name)
                if _found is None:
                    # 按 id 查找四表
                    found_table = None
                    found_data = None
                    found_ent = None
                    for k in state.KIND_TABLES:
                        try:
                            d = state.load_state(book, k)
                        except Exception:
                            continue
                        for e in d.get("entries", []) or []:
                            if isinstance(e, dict) and (e.get("id") == orig_name or e.get("name") == orig_name):
                                found_table, found_data, found_ent = k, d, e
                                break
                        if found_ent:
                            break
                    if found_ent:
                        part_name, st_data, _found = found_table, found_data, found_ent
                    else:
                        # 自动创建：id 形如 p_001 / it_001 / f_001 / pl_001 或任意新名，默认入 persons
                        auto_table = "persons"
                        try:
                            auto_data = state.load_state(book, auto_table)
                        except Exception:
                            auto_data = {"entries": []}
                        new_ent = {"id": orig_name, "name": orig_name, "type": "person", "status": "active", "summary": ""}
                        auto_data.setdefault("entries", []).append(new_ent)
                        part_name, st_data, _found = auto_table, auto_data, new_ent
            ename = ent_parts[0]
            ent = next((e for e in st_data.get("entries", []) if e.get("id") == ename or e.get("name") == ename), None)
            if ent is None:
                # 自动创建：当 id/名不存在时，按表推断 type 并新建（修复 state set p_001 自动创建缺口）
                type_map = {"persons": "person", "items": "item", "factions": "faction", "places": "place"}
                ent_type = type_map.get(part_name, "other")
                # 若 ename 形如 p_001 视为 id，否则视为 name
                if "_" in ename and any(c.isdigit() for c in ename):
                    new_ent = {"id": ename, "name": ename, "type": ent_type, "status": "active", "summary": ""}
                else:
                    new_ent = {"name": ename, "type": ent_type, "status": "active", "summary": ""}
                st_data.setdefault("entries", []).append(new_ent)
                ent = new_ent
            if len(ent_parts) < 2:
                return _fail(f"修改实体必须指定属性字段（例如 {part_name}.{ename}.realm）", code=2)
            ent[ent_parts[1]] = val
        else:
            st_data[sub_path] = val

        # 手术刀纠偏与 sync 合并同样持 state 锁，防并发交错撕裂。
        # 写入前先跑完整状态语义闸门（verify_data）：state set 不能绕过提案的
        # 因果/注册一致性检查（如把未登记实体塞进 present_characters）。
        # 只拦「本次纠偏新引入」的语义错误，允许在既有污染现场直接修复
        # （否则 present 已被写脏的书连 location 纠偏都会被旧错误反向卡死）。
        semantic_errors = []
        try:
            data_before = {k: state.load_state(book, k) for k in state.STATE_KEYS}
        except ValueError as exc:
            return _fail(f"状态 SSOT 不可读，拒绝纠偏: {exc}", code=1)
        before_errors = state.verify_data(data_before)
        data_after = {k: state.load_state(book, k) for k in state.STATE_KEYS}
        data_after[part_name] = st_data
        after_errors = state.verify_data(data_after)
        semantic_errors = [e for e in after_errors if e not in before_errors]
        if semantic_errors:
            return _fail("写入被语义闸门拒绝: " + "；".join(semantic_errors[:5]), code=1)
        try:
            with common.file_lock(state.state_dir(book), name=".state.lock"):
                state.save_state(book, part_name, st_data, source="state_set")
        except ValueError as exc:
            # 写闸门拒绝（schema 违规 / 显式 null 等）：--json 下也须是 JSON 信封而非裸文本
            return _fail(f"写入被结构闸门拒绝: {exc}", code=1)
        if loose_note:
            print("ℹ️ 宽松解析已生效（建议改用合法 JSON 字面量）", file=sys.stderr)
        if getattr(args, "json", False):
            print(json.dumps({"ok": True, "target": target, "value": val}, ensure_ascii=False))
        else:
            print(f"✅ 状态纠偏完成：{target} 已更新为 {val!r}")
        return 0

    return 0


# ---------------------------------------------------------------------------
# ledger（账本手术刀：recompute）
# ---------------------------------------------------------------------------
_POOL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def _ledger_pool(book, args, _fail=None) -> int:
    """ P3-1：Stage 0 声明资源池的 CLI 通道。

    此前资源池在全部 AI 向文档里只有一行示例，且没有任何 CLI 通道可声明——
    `config guide` 不含池键、`state set` 禁登新事实，池只能靠 Stage 5 提案或读源码试出来。
    本命令只做「新建池」，口径与提案端一致：`initial` 必填整数、`current` 由流水重算、
    既有池不可在此改动（改期初请走 recompute/人工修订）。
    """
    js = bool(getattr(args, "json", False))
    if _fail is None:
        def _fail(msg: str, code: int = 1) -> int:
            if js:
                print(json.dumps({"ok": False, "code": "ledger_error", "error": msg},
                                 ensure_ascii=False))
            else:
                print(f"❌ {msg}")
            return code
    if getattr(args, "pool_action", None) != "add":
        return _fail("未知 pool 动作（合法: add）", code=2)
    pid = str(getattr(args, "pool_id", "") or "").strip()
    name = str(getattr(args, "name", "") or "").strip()
    unit = str(getattr(args, "unit", "") or "").strip()
    # 口径与提案端一致——期初必填。原先这里 `or 0` 静默兜底，与本函数
    # 文档字符串自述的「initial 必填整数」相矛盾，也与提案端新规则不一致。
    _raw_initial = getattr(args, "initial", None)
    if _raw_initial is None:
        return _fail("池的 --initial 为必填（期初余额；省略会被当成 0 从而污染账本基准）", code=2)
    initial = int(_raw_initial)
    if not _POOL_ID_RE.match(pid):
        return _fail(f"池 ID {pid!r} 非法：须为 2~32 位小写字母/数字/下划线，且以字母开头（如 lamp_ash）", code=2)
    if not name or not unit:
        return _fail("池的 --name 与 --unit 均为必填（显示名与计量单位）", code=2)
    try:
        led = state.load_state(book, "ledger")
    except ValueError as exc:
        return _fail(f"账本不可读: {exc}")
    pools = led.setdefault("pools", {})
    if pid in pools:
        msg = (f"资源池 {pid} 已存在（{pools[pid].get('name')}）——本命令只新建池，"
               "既有池的期初/名称请走提案或 ledger recompute 修订")
        if js:
            print(json.dumps({"ok": False, "code": "ledger_error", "error": msg},
                             ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return 1
    pools[pid] = {"name": name, "unit": unit, "initial": initial, "current": initial}
    try:
        state.save_state(book, "ledger", led, source="ledger_recompute")
    except ValueError as exc:
        return _fail(f"写入被结构闸门拒绝: {exc}")
    payload = {"ok": True, "pool_id": pid, "name": name, "unit": unit, "initial": initial,
               "note": "余额（current）此后一律由流水重算；记账走 ledger.transactions（提案）"}
    if js:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"💱 已声明资源池 {pid}（{name}，单位「{unit}」，期初 {initial}）")
        print("   余额此后由流水重算；记账请走提案的 ledger.transactions。")
    return 0


def cmd_ledger(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    js = bool(getattr(args, "json", False))

    def _fail(msg: str, code: int = 1) -> int:
        """ledger 手术刀错误出口：--json 一律 JSON 信封（stdout 保持纯 JSON）。"""
        if js:
            print(json.dumps({"ok": False, "code": "ledger_error", "error": msg},
                             ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return code

    action = getattr(args, "ledger_action", None) or "recompute"
    if action == "pool":
        return _ledger_pool(book, args, _fail)
    if action != "recompute":
        return _fail(f"未知 ledger 动作: {action}（合法: recompute / pool add）", code=2)
    try:
        state.load_state(book, "ledger")
    except ValueError as exc:
        return _fail(f"账本不可读: {exc}")


    def _recompute(led: dict) -> tuple[list[str], list[str], str | None]:
        """返回 (流水修复说明, 池修复说明, 致命错误)。"""
        running: dict[str, int] = {}
        for pid, p in (led.get("pools") or {}).items():
            try:
                running[pid] = int(p.get("initial", 0))
            except (TypeError, ValueError):
                return [], [], f"资源池 {pid} initial 非整数，拒绝重算（先用 state set 修复 initial）"
        # 重算按「章号」排序（同章内保持原有先后），否则后追加的他章流水
        # 会排在时间序之后，balance_after 与章节编年史互相矛盾却仍被判定「自洽」。
        txs = led.get("transactions") or []
        order = sorted(range(len(txs)), key=lambda i: (common.chapter_token_to_num(
            str(txs[i].get("chapter", ""))) or 0, i))
        if order != list(range(len(txs))):
            led["transactions"] = [txs[i] for i in order]
            txs = led["transactions"]
            tx_fixed_pre = [f"流水已按章号重排（{len(order)} 笔，原顺序与编年史不一致）"]
        else:
            tx_fixed_pre = []
        tx_fixed: list[str] = tx_fixed_pre
        for i, t in enumerate(led.get("transactions") or [], 1):
            pool = t.get("pool")
            if pool not in running:
                return [], [], f"流水 #{i} 引用未声明池 '{pool}'——拒绝重算（先补池或修流水）"
            try:
                running[pool] += int(t.get("delta", 0))
            except (TypeError, ValueError):
                return [], [], f"流水 #{i} delta 非整数，拒绝重算（先用 state set 修复）"
            common.debug(f"ledger recompute tx #{i}: pool={pool} delta={t.get('delta')} "
                         f"running={running[pool]} 记录 balance_after={t.get('balance_after')}")
            if t.get("balance_after") != running[pool]:
                tx_fixed.append(f"#{i}「{str(t.get('subject', ''))[:12]}」 balance_after "
                                f"{t.get('balance_after')} → {running[pool]}")
                t["balance_after"] = running[pool]
        pool_fixed: list[str] = []
        for pid, p in (led.get("pools") or {}).items():
            if p.get("current") != running[pid]:
                pool_fixed.append(f"池 {pid}: {p.get('current')} → {running[pid]}")
                p["current"] = running[pid]
        return tx_fixed, pool_fixed, None

    # 账本重算的「读→算→写」全程持 state 锁——只锁写的话，
    # recompute 基于旧快照的重算结果会静默覆盖 sync 并发提交的新流水
    with common.file_lock(state.state_dir(book), name=".state.lock"):
        led = state.load_state(book, "ledger")
        tx_fixed, pool_fixed, fatal = _recompute(led)
        if fatal:
            return _fail(fatal)
        if not tx_fixed and not pool_fixed:
            if js:
                print(json.dumps({"ok": True, "fixed": [], "note": "账本自洽，无需修复"},
                                 ensure_ascii=False))
            else:
                print("✅ 账本自洽：余额与 balance_after 均等于流水重算值，无需修复")
            return 0
        try:
            state.save_state(book, "ledger", led, source="ledger_recompute")
        except ValueError as exc:
            return _fail(f"修复落盘被闸门拒绝: {exc}")
    if not js:
        print("🧮 账本已按流水全量重算并修复：")
        for line in tx_fixed + pool_fixed:
            print(f"   - {line}")
    # 锁外复核：两条输出模式共用同一体检结论
    errs = state.verify_state(book)
    if errs:
        if js:
            print(json.dumps({"ok": False, "fixed": tx_fixed + pool_fixed,
                              "residual_errors": errs}, ensure_ascii=False))
            return 1
        print(" ⚠️ 修复后仍有不一致（超出余额范畴，请逐条核查）：")
        for e in errs:
            print(f"    - {e}")
        return 1
    if js:
        print(json.dumps({"ok": True, "fixed": tx_fixed + pool_fixed}, ensure_ascii=False))
        return 0
    print(" ✅ 修复后 verify_state 通过")
    return 0


# ---------------------------------------------------------------------------
# milestone（Stage 0 播种主线里程碑）
# ---------------------------------------------------------------------------
def cmd_milestone(args) -> int:
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()
    action = getattr(args, "milestone_action", None) or "list"
    js = bool(getattr(args, "json", False))
    try:
        tl = state.load_state(book, "timeline")
    except (ValueError, OSError) as exc:
        if js:
            print(json.dumps({"ok": False, "code": "milestone_error",
                              "error": f"时间线不可读: {exc}"}, ensure_ascii=False))
        else:
            print(f"❌ 时间线不可读: {exc}")
        return 1

    milestones = tl.setdefault("milestones", [])
    if action == "list":
        payload = {"ok": True, "total": len(milestones), "milestones": milestones}
        if js:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("=" * 60)
            print(f" 🚩 里程碑列表（共 {len(milestones)} 项）")
            print("=" * 60)
            if not milestones:
                print("   （暂无里程碑登记，可通过 `milestone add` 播种）")
            else:
                for m in milestones:
                    mid = m.get("id", "")
                    title = m.get("title", "")
                    target_ch = m.get("target_ch", "-")
                    st = m.get("status", "pending")
                    desc = m.get("desc", "")
                    icon = "✅" if st == "achieved" else ("❌" if st == "abandoned" else "⏳")
                    print(f" {icon} [{mid}] 目标: 第 {target_ch} 章 ｜ {title}（{st}）")
                    if desc:
                        print(f"      描述: {desc}")
        return 0

    elif action == "add":
        title = str(getattr(args, "title", "") or "").strip()
        if not title:
            msg = "里程碑的 --title 为必填"
            print(json.dumps({"ok": False, "code": "milestone_error", "error": msg},
                             ensure_ascii=False) if js else f"❌ {msg}")
            return 2

        target_ch_raw = getattr(args, "target_ch", None)
        target_ch = None
        if target_ch_raw is not None:
            try:
                target_ch = int(target_ch_raw)
                if target_ch < 1:
                    raise ValueError()
            except (TypeError, ValueError):
                msg = "--target-ch 必须为 ≥1 的正整数"
                print(json.dumps({"ok": False, "code": "milestone_error", "error": msg},
                                 ensure_ascii=False) if js else f"❌ {msg}")
                return 2

        mid = str(getattr(args, "id", "") or "").strip()
        if not mid:
            existing_ids = [m.get("id") for m in milestones if isinstance(m, dict) and m.get("id")]
            nums = []
            for eid in existing_ids:
                m = re.match(r"^MS-(\d+)$", str(eid))
                if m:
                    nums.append(int(m.group(1)))
            next_num = max(nums, default=0) + 1
            mid = f"MS-{next_num:03d}"

        if any(isinstance(m, dict) and m.get("id") == mid for m in milestones):
            msg = f"里程碑 ID {mid} 已存在"
            print(json.dumps({"ok": False, "code": "milestone_error", "error": msg},
                             ensure_ascii=False) if js else f"❌ {msg}")
            return 1

        desc = str(getattr(args, "desc", "") or "").strip()
        new_ms = {
            "id": mid,
            "title": title,
            "target_ch": target_ch,
            "status": "pending",
            "desc": desc,
        }
        milestones.append(new_ms)
        try:
            state.save_state(book, "timeline", tl, source="milestone")
        except ValueError as exc:
            # --json 契约：写闸门失败不得向 stdout 打印裸文本。
            if js:
                print(json.dumps({"ok": False, "code": "milestone_error",
                                  "error": f"写入被结构闸门拒绝: {exc}"},
                                 ensure_ascii=False))
            else:
                print(f"❌ 写入被结构闸门拒绝: {exc}")
            return 1
        payload = {"ok": True, "milestone": new_ms}
        if js:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"🚩 已登记里程碑 [{mid}]：{title}（目标章: {target_ch or '未定'}）")
            if desc:
                print(f"   说明: {desc}")
        return 0

    elif action == "achieve":
        mid = str(getattr(args, "milestone_id", "") or "").strip()
        if not mid:
            msg = "achieve 需要里程碑编号（如 MS-001）"
            print(json.dumps({"ok": False, "code": "milestone_error", "error": msg},
                             ensure_ascii=False)) if js else print(f"❌ {msg}")
            return 2
        target = None
        for m in milestones:
            if isinstance(m, dict) and m.get("id") == mid:
                target = m
                break
        if target is None:
            msg = f"未找到里程碑 {mid}（先用 milestone add 播种 / milestone list 查看）"
            print(json.dumps({"ok": False, "code": "milestone_error", "error": msg},
                             ensure_ascii=False)) if js else print(f"❌ {msg}")
            return 1
        # 实际达成章节：显式 --chapter 优先，否则取最新定稿章（推断值会在输出里标注）
        achieved_ch = None
        achieved_inferred = False
        inferred_note = ""
        ch_raw = getattr(args, "chapter", None)
        if ch_raw:
            n = common.chapter_token_to_num(ch_raw)
            achieved_ch = f"ch_{n:03d}" if n else None
            if not n:
                msg = f"非法章节号: {ch_raw}"
                print(json.dumps({"ok": False, "code": "milestone_error", "error": msg},
                                 ensure_ascii=False)) if js else print(f"❌ {msg}")
                return 2
        else:
            # 缺省推断：取最新定稿章。此前静默盖章、输出里看不出是推断值，
            # 补拍历史里程碑时极易被误当成「就是这一章达成的」。
            finals = common.find_chapter_files(book, "final")
            if finals:
                achieved_ch = f"ch_{max(common.chapter_token_to_num(f.name) or 0 for f in finals):03d}"
                achieved_inferred = True
            else:
                inferred_note = "未提供 --chapter 且全书尚无定稿，achieved_ch 留空（补拍请用 -c 指定达成章）"
        already = target.get("status") == "achieved"
        target["status"] = "achieved"
        if achieved_ch:
            target["achieved_ch"] = achieved_ch
        try:
            state.save_state(book, "timeline", tl, source="milestone")
        except ValueError as exc:
            if js:
                print(json.dumps({"ok": False, "code": "milestone_error",
                                  "error": f"写入被结构闸门拒绝: {exc}"}, ensure_ascii=False))
            else:
                print(f"❌ 写入被结构闸门拒绝: {exc}")
            return 1
        payload = {"ok": True, "milestone": target, "already_achieved": already,
                   "achieved_ch_inferred": achieved_inferred}
        if achieved_inferred:
            payload["note"] = (f"achieved_ch={achieved_ch} 为推断值（缺省取最新定稿章）；"
                               "补拍历史里程碑请用 -c/--chapter 显式指定")
        elif inferred_note:
            payload["note"] = inferred_note
        if js:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            verb = "已确认（本就处于达成态）" if already else "已核销为达成"
            print(f"🚩 [{mid}] {verb}：{target.get('title','')}"
                  + (f"（达成于 {achieved_ch}）" if achieved_ch else ""))
        return 0

    else:
        msg = f"未知 milestone 动作: {action}（合法: list / add / achieve）"
        print(json.dumps({"ok": False, "code": "milestone_error", "error": msg},
                         ensure_ascii=False) if js else f"❌ {msg}")
        return 2