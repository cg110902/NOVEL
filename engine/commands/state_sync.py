"""状态与封存命令：sync（Stage 5 闭环）/ proposal / snapshot / checkpoint / state（手术刀纠偏）。"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

from .. import checks, common, evidence, snapshot, state

from ._shared import _norm_ch, ws_gate


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------
def _stamp_final_hash(book: Path, ch: str) -> None:
    """QA P2：封存时对当章 final 定稿盖章 SHA-256 → processed/final_hashes.json。

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


def _append_bible_journal(book: Path, ch: str) -> None:
    """bible 版本盖章：每次成功封存向 state/bible_log.jsonl 追加一条 project_bible.md 哈希。

    用途：日后修订 bible 时可精确定位「哪些章是在旧版世界规则下写成」，回溯修订不瞎猜。
    盖章失败不阻断封存主流程。
    """
    bible = book / "bible" / "project_bible.md"
    sha = hashlib.sha256(bible.read_bytes()).hexdigest()[:16] if bible.is_file() else ""
    entry = {"chapter": ch, "bible_sha": sha,
             "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        with open(book / "state" / "bible_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def cmd_sync(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    ch = _norm_ch(args.chapter)
    if ch is None:
        print(f"❌ 无法解析章节编号: {args.chapter!r}（示例: 6 或 ch_006）")
        return 2

    inbox = book / "state" / "inbox"
    js = bool(getattr(args, "json", False))

    def _fail(msg: str, code: int = 1, hint: str = "", **extra) -> int:
        """统一失败出口：JSON 模式输出结构化错误（QA P3-9），文本模式保留人话+修复指引。"""
        if js:
            print(json.dumps({"chapter": ch, "error": msg, **({"hint": hint} if hint else {}), **extra},
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
                     hint=f"请由 Stage 3 Editor 完成定稿重塑并写入 manuscript/vol_XX/final/{ch}.md")
    if not has_proposal:
        strays = ([p.name for p in inbox.glob(f"{ch}.*") if p.suffix == ".json"
                   and not p.name.endswith(state.NO_MERGE_SUFFIXES)] if inbox.is_dir() else [])
        hint = (f"（发现同章非规范命名：{'、'.join(sorted(strays))}——在途提案每章仅一份，"
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
    # QA P1-2：--json 模式下 advisory 不再打印到 stdout 污染 JSON（数据本就在 payload 中）
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

    dest = book / "log" / "review" / f"{ch}.md"
    if dest.is_file():
        gate = checks.review_gate(book, ch)
        if gate:
            for g in gate:
                print(f"ℹ️ 校对注记提示：{g}")

    common.debug(f"sync {ch}: dry_run={args.dry_run} final={has_manuscript} proposal={proposal_path.name if proposal_path else '无'}")
    overall = state.apply_inbox(book, expect_chapter=ch, dry_run=args.dry_run)
    common.debug(f"apply_inbox: applied={overall.get('applied')} failed={overall.get('failed')} "
                 f"duplicates={overall.get('duplicates')} skipped={overall.get('skipped')} "
                 f"picked_up={overall.get('picked_up')}")
    verify_errors: list[str] = []
    snap_msg, snap_ok = "", True
    applied_now = overall.get("applied", 0)
    no_op = applied_now == 0 and overall.get("duplicates", 0) == 0
    if no_op and not overall.get("failed"):
        noop_hint = ("空提案已归档 processed/：如需重提，请修改内容并换新 operation_id 后放回 state/inbox/"
                     if any(r.get("noop") for r in overall["results"]) else "")
        return _fail("未合入任何变更（提案为错章/被留置/空提案），拒绝封存快照", hint=noop_hint,
                     apply=overall)
    if not args.dry_run and overall["failed"] == 0 and applied_now > 0:
        verify_errors = state.verify_state(book)
        common.debug(f"verify_state（状态体检，含前置因果闸门）: {len(verify_errors)} 错误"
                     + (f"（{verify_errors[0]}）" if verify_errors else ""))
        if not verify_errors:
            # QA P2：封存时刻对当章 final 盖章（漂移检测的事实基线）
            _stamp_final_hash(book, ch)
            try:
                snap_ok, snap_msg = snapshot.create_snapshot(book, f"{ch}_done")
            except Exception as exc:
                snap_ok, snap_msg = False, f"快照创建异常（状态已合并，可用 snapshot create 手动补拍）：{exc}"
            common.debug(f"snapshot: ok={snap_ok} {snap_msg}")
            _append_bible_journal(book, ch)

    payload = {"chapter": ch, "dry_run": args.dry_run, "apply": overall,
               "quote_notes": quote_notes, "verify_battery": battery,
               "verify_errors": verify_errors, "snapshot": {"ok": snap_ok, "name": snap_msg}
               if not args.dry_run and overall["failed"] == 0 and applied_now > 0 else None}
    if verify_errors and not args.dry_run:
        # QA P3-15：合并已落盘但体检失败时的最小恢复指引（此前无任何出口提示）
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
        print(f" 汇总：合并 {overall['applied']} ｜ 重复跳过 {overall['duplicates']} ｜ "
              f"失败 {overall['failed']} ｜ 留置 {overall['skipped']}"
              f"{'（留置 = 非本章提案/空提案，未处理；将由其所属章 sync 时合并）' if overall['skipped'] else ''}")
        if verify_errors:
            print(" ❌ 状态体检未通过（未封存快照）：")
            for e in verify_errors:
                print(f"    {e}")
            print(" ↩️ 恢复指引：修正数据后 `snapshot create <name>` 手动补拍；"
                  "或 `snapshot rollback <上一封存点>` 回退后修复提案重提。")
        elif snap_msg:
            print(f" 📸 快照：{'✅ ' if snap_ok else '❌ '}{snap_msg}")
    if overall["failed"] or verify_errors or (not snap_ok and snap_msg):
        return 1
    return 0



# ---------------------------------------------------------------------------
# proposal
# ---------------------------------------------------------------------------
def _cmd_proposal_check(book: Path, ch: str, args) -> int:
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
        # QA P3：已合并归档的章不再误报「在途提案缺失」，给出准确指向
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
    return 1 if rep["errors"] else 0


def _cmd_proposal_verify(book: Path, ch: str, args) -> int:
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
        # QA P3：已合并归档的章不再误报「在途提案缺失」，给出准确指向
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


def _cmd_proposal_auto(book: Path, ch: str, args) -> int:
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
            # QA P3-14：kind 判定优先以 ID 前缀为准（此前「伏笔」字样优先于 KNO-XXX 前缀，
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
            else:
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

    raw_scenes = common.md_section(beats_text, r"^##\s*(?:.*冲突与场景脉络|.*场景推进|.*场景脉络|.*拍点|拍点与场景切片)")
    beats_scenes = []
    for ln in raw_scenes:
        s = ln.strip().lstrip("-*· ").strip()
        if not s or s.startswith(("#", "<")):
            continue
        if s.startswith("**内容**") or s.startswith("**场景**") or s.startswith("**收束**") :
            continue
        cleaned = re.sub(r"^(?:章末物理刀口|[-·*]*\s*📍\s*\**章末物理刀口卡点\**)[:：]\s*", "", s).strip()
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
        print("   ⚠️ auto 草案的 synopsis/timeline 会与 beats 存在措辞重叠（beats_overlap advisory 属预期噪声），"
              "事实性文字请以 final 为源微调后再 sync。")
        print(f"   主控可按需微调 current 字段后直接运行 `python studio.py sync {ch}`！")
        return 0
    else:
        print(json.dumps(proposal, ensure_ascii=False, indent=2))
        return 0


def cmd_proposal(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
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
    if (inbox / "failed" / f"{ch}.json").is_file():
        # QA P3-13：failed/ 同章旧提案与新建骨架并存易误判（check/verify 双查两处）
        print(f"⚠️ {ch} 在 failed/ 存在失败提案（state/inbox/failed/{ch}.json）——"
              "sync 将优先取 inbox 新骨架；建议核对失败原因后删除或改名旧提案，避免双份混淆")
    from datetime import datetime
    mmdd = datetime.now().strftime("%m%d_%H%M%S")
    skeleton = {
        "schema": "novel-studio.state-mutation/v2", "chapter": ch,
        "operation_id": f"{ch}.director.{mmdd}",
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



# snapshot
# ---------------------------------------------------------------------------
def cmd_snapshot(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
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
        if args.json:
            print(json.dumps({"ok": ok, "snapshot": msg}, ensure_ascii=False))
        else:
            print(("📸 ✅ " if ok else "📸 ❌ ") + msg)
        return 0 if ok else 1
    if action == "rollback":
        try:
            ok, msg, chosen = snapshot.rollback_snapshot(book, args.name)
        except ValueError as e:
            print(f"❌ {e}")
            return 1
        if args.json:
            print(json.dumps({"ok": ok, "snapshot": chosen, "message": msg},
                             ensure_ascii=False))
        else:
            print(("🔄 ✅ " if ok else "🔄 ❌ ") + msg)
        if ok and args.clean_drafts:
            base = snapshot.chapter_of_snapshot(chosen)
            removed = 0
            pending_hint: list[str] = []
            trash = common.workspace_root() / ".trash"
            if base:
                def _quarantine(f, _book=book):
                    # QA P2-5：清理的稿件/细纲/注记不再直接 unlink，而是移入
                    # workspace/.trash/（快照只含 state 六表，稿件一旦误删不可恢复）
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
                print(json.dumps({"ok": ok, "clean_drafts_removed": removed,
                                  "pending_hint": pending_hint}, ensure_ascii=False))
            else:
                print(f"🧹 清理超前于快照的稿件/细纲/注记/评测：{removed} 个文件（已移入 workspace/.trash/ 回收区备份）")
                if pending_hint:
                    print(f"   ↳ 收件箱仍有 {len(pending_hint)} 份超章待办提案未删（保守起见请自行定夺）：{'、'.join(pending_hint[:5])}")
        return 0 if ok else 1
    return 2



def cmd_checkpoint(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1

    ch_arg = getattr(args, "chapter", None)
    if ch_arg:
        ch = _norm_ch(ch_arg)
        if ch is None:
            print(f"❌ 无法解析章节编号: {ch_arg!r}（示例: 5 或 ch_005）")
            return 2
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



def cmd_state(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1

    action = getattr(args, "state_action", "show")
    if not action:
        action = "show"

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

    target = getattr(args, "target", "")
    if not target:
        print("❌ 请指定要查询或修改的字段路径（例如: current.injury 或 entities.林舟.realm）")
        return 2

    parts = target.split(".", 1)
    part_name = parts[0]
    sub_path = parts[1] if len(parts) > 1 else ""

    if part_name not in ("current", "entities", "lines", "timeline", "ledger", "synopsis"):
        print(f"❌ 未知状态分区: {part_name}（合法: current / entities / lines / timeline / ledger / synopsis）")
        return 2

    st_data = state.load_state(book, part_name)

    if action == "get":
        val = None
        if not sub_path:
            val = st_data
        elif part_name == "current":
            val = st_data.get(sub_path)
        elif part_name == "entities":
            ent_parts = sub_path.split(".", 1)
            ename = ent_parts[0]
            ent = next((e for e in st_data.get("entries", []) if e.get("name") == ename), None)
            if ent is None:
                print(f"❌ 实体「{ename}」未注册")
                return 1
            if len(ent_parts) > 1:
                val = ent.get(ent_parts[1])
            else:
                val = ent
        else:
            val = st_data.get(sub_path)

        if getattr(args, "json", False):
            print(json.dumps({"target": target, "value": val}, ensure_ascii=False, indent=2))
        else:
            print(f"{target} = {json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else val}")
        return 0

    if action == "set":
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
                                    # QA P3-12：宽松解析的内层纯数字转 int（此前静默字符串化，
                                    # 对 int 字段纠偏会被写闸门以「类型应为 int」拒回）
                                    if re.fullmatch(r"-?\d+", pv):
                                        pv = int(pv)
                                    obj_dict[pk.strip().strip("'\"")] = pv
                            if obj_dict:
                                val = obj_dict
                                loose_note = True

        if part_name == "current":
            if not sub_path:
                print("❌ 修改 current 必须指定具体字段（例如 current.injury）")
                return 2
            st_data[sub_path] = val
        elif part_name == "entities":
            ent_parts = sub_path.split(".", 1)
            ename = ent_parts[0]
            ent = next((e for e in st_data.get("entries", []) if e.get("name") == ename), None)
            if ent is None:
                print(f"❌ 实体「{ename}」不存在，拒绝猜测（请先注册该实体）")
                return 1
            if len(ent_parts) < 2:
                print(f"❌ 修改实体必须指定属性字段（例如 entities.{ename}.realm）")
                return 2
            ent[ent_parts[1]] = val
        else:
            st_data[sub_path] = val

        # QA P2-10：手术刀纠偏与 sync 合并同样持 state 锁，防并发交错撕裂
        with common.file_lock(state.state_dir(book), name=".state.lock"):
            state.save_state(book, part_name, st_data)
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
def cmd_ledger(args) -> int:
    book = ws_gate(args)  # QA P5：--json 错误路径也出 JSON 信封
    if book is None:
        return 1
    action = getattr(args, "ledger_action", None) or "recompute"
    if action != "recompute":
        print(f"❌ 未知 ledger 动作: {action}（合法: recompute）")
        return 2
    js = bool(getattr(args, "json", False))
    try:
        state.load_state(book, "ledger")
    except ValueError as exc:
        print(f"❌ 账本不可读: {exc}")
        return 1

    def _recompute(led: dict) -> tuple[list[str], list[str], str | None]:
        """返回 (流水修复说明, 池修复说明, 致命错误)。"""
        running: dict[str, int] = {}
        for pid, p in (led.get("pools") or {}).items():
            try:
                running[pid] = int(p.get("initial", 0))
            except (TypeError, ValueError):
                return [], [], f"资源池 {pid} initial 非整数，拒绝重算（先用 state set 修复 initial）"
        tx_fixed: list[str] = []
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

    # QA P2-10：账本重算的「读→算→写」全程持 state 锁——只锁写的话，
    # recompute 基于旧快照的重算结果会静默覆盖 sync 并发提交的新流水
    with common.file_lock(state.state_dir(book), name=".state.lock"):
        led = state.load_state(book, "ledger")
        tx_fixed, pool_fixed, fatal = _recompute(led)
        if fatal:
            print(f"❌ {fatal}")
            return 1
        if not tx_fixed and not pool_fixed:
            if js:
                print(json.dumps({"ok": True, "fixed": [], "note": "账本自洽，无需修复"},
                                 ensure_ascii=False))
            else:
                print("✅ 账本自洽：余额与 balance_after 均等于流水重算值，无需修复")
            return 0
        try:
            state.save_state(book, "ledger", led)
        except ValueError as exc:
            print(f"❌ 修复落盘被闸门拒绝: {exc}")
            return 1
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

