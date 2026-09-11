"""新门禁触发测试：纯判定边界（无书）＋ 违规注入 e2e（临时书）。

跑法（仓库根）：`.venv/bin/python -m tests.test_gates`
覆盖：
- longline_stale_findings：边界 gap＝阈值×2 不报 / ×2+1 报 / never 档不报 / int target 不报；
- cold_prereq_findings：冷前置命中 / 新鲜不命中 / 查无此人不命中；
- beats_pov_missing / mood_character_unknown：临时书注入违规后 `check --json` 出现对应码。
（mood_dialogue_flat 需声纹基线长窗，e2e 成本过高未覆盖——逻辑为 level≥4＋声纹稳定直判。）
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import state as state_mod  # noqa: E402
from engine import proposal_v3 as v3_mod  # noqa: E402
from engine.audit import probe_secret_leakage  # noqa: E402
from engine.commands.state_sync import _object_payload  # noqa: E402
from engine import evidence as evidence_mod  # noqa: E402
from engine import memory as memory_mod  # noqa: E402
from engine import checks as checks_mod  # noqa: E402
from engine.checks import (cold_prereq_findings, dangling_ref_findings,  # noqa: E402
                           finding_fp, history_collapse_note,
                           longline_stale_findings, mood_plan_actual_findings,
                           mood_stale_gap, parse_beats_cast_moods,
                           present_track_finding, run_checks, validate_quotes)
from engine.objects.registry import build_registry  # noqa: E402
from test_smoke import MOOD_QUOTE, build_smoke_book, must_ok, run  # noqa: E402

PASS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    assert cond, f"GATES FAIL [{name}] {detail}"
    PASS.append(name)


def _row(**kw) -> dict:
    base = {"id": "GUN-001", "label": "无主空灯", "kind": "foreshadow",
            "target_ch": "longline", "status": "Planted", "plant_ch": 1,
            "weight": 1, "last_seen_ch": 1, "seen_chapters": [1],
            "gap": 51, "tier": "impression", "cold_threshold": 25, "is_cold": True}
    base.update(kw)
    return base


def test_pure_helpers() -> None:
    check("longline_fires", len(longline_stale_findings([_row()])) == 1)
    check("longline_boundary_quiet",
          longline_stale_findings([_row(gap=50)]) == [], "gap=阈值×2 整好不报")
    check("longline_int_target_quiet",
          longline_stale_findings([_row(target_ch=30, gap=99)]) == [])
    check("longline_never_quiet",
          longline_stale_findings([_row(gap=None, tier="never", last_seen_ch=None)]) == [])
    check("longline_fresh_quiet", longline_stale_findings([_row(gap=3, tier="fresh")]) == [])

    ledger = {"foreshadows": [
        {"id": "GUN-002", "status": "Active", "requires": ["GUN-001"]},
        {"id": "GUN-003", "status": "Active", "requires": ["GUN-009"]},
        {"id": "GUN-004", "status": "Active", "requires": []},
    ], "misunderstandings": [], "knowledge": []}
    mem = [_row(id="GUN-001"), _row(id="GUN-009", gap=2, tier="fresh", is_cold=False)]
    hits = cold_prereq_findings(["GUN-002", "GUN-003", "GUN-004", "GUN-404"], ledger, mem)
    check("cold_prereq_hit", len(hits) == 1 and hits[0]["req"] == "GUN-001", f"{hits}")
    check("cold_prereq_fresh_quiet", all(h["req"] != "GUN-009" for h in hits))
    check("cold_prereq_missing_quiet", cold_prereq_findings(["GUN-404"], ledger, mem) == [])


def test_deadlock_reclaim() -> None:
    """孤儿锁回收（2026-09 崩溃压测 FIX-3）：持锁进程被 SIGKILL 后，
    下一个取锁者必须靠 pid 活性检测即时抢占，而不是干等 120s 陈锁阈值。"""
    import subprocess
    import time as _t
    from engine.common import file_lock
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        code = (f"import sys, time; sys.path.insert(0, {str(ROOT)!r}); "
                f"from engine.common import file_lock; "
                f"ctx = file_lock(sys.argv[1]); ctx.__enter__(); time.sleep(60)")
        kid = subprocess.Popen([sys.executable, "-c", code, str(d)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lockf = d / ".engine.lock"
        for _ in range(200):
            if lockf.exists():
                break
            _t.sleep(0.02)
        check("lockfile_created", lockf.exists(), "子进程未建锁")
        kid.kill(); kid.wait()
        t0 = _t.monotonic()
        try:
            with file_lock(d, timeout=5.0):
                got = _t.monotonic() - t0
            check("deadlock_reclaimed_fast", got < 2.0, f"等了 {got:.2f}s 才拿到死锁主的锁")
        except TimeoutError as exc:
            check("deadlock_reclaimed_fast", False, str(exc)[:120])


def test_remind_ch_stamp() -> None:
    """remind 应用须回填 remind_ch（2026-09 压测 FIX-1）：subplot_stall 以
    max(plant_ch, remind_ch) 为最后推进参照，缺回填则对回唤过的线永久误报。"""
    from engine.state import _merge_lines
    st = {"foreshadows": [{"id": "GUN-001", "name": "匣底灯", "plant_ch": 2,
                           "status": "Reminded", "weight": 1}],
          "misunderstandings": [], "knowledge": []}
    rep = {"errors": [], "warnings": [], "updated": [], "applied": 0}
    _merge_lines(st, [{"kind": "foreshadow", "action": "remind", "id": "GUN-001"}], 21, rep)
    ent = st["foreshadows"][0]
    check("remind_ch_written", ent.get("remind_ch") == 21 and not rep["errors"], str(ent))
    # 模型回读兼容（extra=forbid 下未声明字段会在严格校验处炸）
    try:
        from engine.models.lines import LinesState
        LinesState.model_validate({"foreshadows": st["foreshadows"],
                                   "misunderstandings": [], "knowledge": []})
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok = False
        print("   model round-trip:", exc)
    check("remind_ch_model_roundtrip", ok)
    # 幂等：同章重放 remind 不叠加报错、值保持
    _merge_lines(st, [{"kind": "foreshadow", "action": "remind", "id": "GUN-001"}], 21, rep)
    check("remind_ch_idempotent", st["foreshadows"][0].get("remind_ch") == 21 and not rep["errors"])


def test_v3_update_keeps_table() -> None:
    """FIX-4（崩溃恢复演练抓出）：v3 实体表 update 不得静默搬表。

    旧 bug：update 编译成 v2 条目时缺省 type，merge 层「缺省→other→persons」
    把道具静默搬进 persons 且改写 type，零警告。显式 set.type 的搬迁行为保留。
    """
    with tempfile.TemporaryDirectory(prefix="novel_fix4_") as td:
        book, _env = build_smoke_book(Path(td))
        base = {"schema": "novel-studio.state-mutation/v3", "chapter": "ch_002",
                "operation_id": "ch_002.test.fix4"}
        rep = state_mod.apply_proposal(book, {**base, "ops": [
            {"table": "items", "action": "create",
             "entry": {"id": "it_fix4", "name": "压测镇纸", "type": "item"}}]},
            expected_chapter="ch_002")
        check("fix4_create_ok", not rep.get("errors"), str(rep.get("errors"))[:250])
        rep = state_mod.apply_proposal(book, {**base, "operation_id": "ch_002.test.fix4a",
                                              "ops": [
            {"table": "items", "action": "update", "id": "it_fix4",
             "set": {"holder": "陈默"}}]}, expected_chapter="ch_002")
        check("fix4_ops_apply", not rep.get("errors"), str(rep.get("errors"))[:250])
        items1 = json.loads((book / "state" / "items.json").read_text(encoding="utf-8"))
        still = next((e for e in items1["entries"] if e.get("id") == "it_fix4"), None)
        check("fix4_stays_in_items",
              still is not None and still.get("type") == "item"
              and still.get("holder") == "陈默", str(still)[:200])
        persons1 = json.loads((book / "state" / "persons.json").read_text(encoding="utf-8"))
        check("fix4_not_in_persons",
              all(e.get("id") != "it_fix4" for e in persons1["entries"]))
        # 显式 set.type 变更 → 仍搬迁且警告留痕（保留旧契约）
        repb = state_mod.apply_proposal(book, {**base, "operation_id": "ch_002.test.fix4b",
                                               "ops": [{"table": "items", "action": "update",
                                                        "id": "it_fix4", "set": {"type": "person"}}]},
                                        expected_chapter="ch_002")
        check("fix4_explicit_relocate_warns",
              any("搬迁" in w for w in repb.get("warnings", [])), str(repb)[:250])


def test_violation_e2e() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_gates_") as td:
        book, env = build_smoke_book(Path(td))
        beats = next(iter(list(book.glob("outlines/*/beats/ch_001.md"))
                           or list(book.glob("outlines/**/ch_001.md"))))
        orig_beats = beats.read_text(encoding="utf-8")
        try:
            beats.write_text("\n".join(l for l in orig_beats.splitlines()
                                       if not l.startswith("pov:")), encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check no-pov")
            check("beats_pov_missing_fires", '"beats_pov_missing"' in out, out[:1500])
        finally:
            beats.write_text(orig_beats, encoding="utf-8")

        cur_p = book / "state" / "current.json"
        orig_cur = cur_p.read_text(encoding="utf-8")
        try:
            cur = json.loads(orig_cur)
            cur["present_moods"] = {"不存在的人": {"label": "暴怒", "level": 5}}
            cur_p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check unknown-mood")
            check("mood_character_unknown_fires", '"mood_character_unknown"' in out, out[:1500])
        finally:
            cur_p.write_text(orig_cur, encoding="utf-8")


def test_quote_slots() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_quotes_") as td:
        book, _env = build_smoke_book(Path(td))
        bad_mood = {"current": {"present_moods": {
            "陈默": {"label": "隐忍", "quote": "子虚乌有绝不可能命中正文的句子"}}}}
        notes = validate_quotes(book, "ch_001", bad_mood)
        check("mood_quote_grounded", any("present_moods.陈默" in n for n in notes), f"{notes}")
        bad_cog = {"cognition": [{"character": "陈默", "content": "x", "kind": "fact",
                                  "since_ch": "ch_001",
                                  "quote": "同样子虚乌有绝不可能命中的句子"}]}
        notes = validate_quotes(book, "ch_001", bad_cog)
        check("cognition_quote_grounded", any("cognition[0]" in n for n in notes), f"{notes}")
        good = {"current": {"present_moods": {"陈默": {"label": "隐忍", "quote": MOOD_QUOTE}}}}
        notes = validate_quotes(book, "ch_001", good)
        check("mood_quote_hit_silent", not any("present_moods" in n for n in notes), f"{notes}")


def test_silent_create_warns() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_newent_") as td:
        book, _env = build_smoke_book(Path(td))
        base = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_002",
                "operation_id": "ch_002.test.gates"}
        rep = state_mod.apply_proposal(
            book, {**base, "entities": [{"name": "路人甲XYZ", "type": "person"}]},
            expected_chapter="ch_002", dry_run=True)
        check("new_entity_warns", any("新登记" in w for w in rep.get("warnings", [])),
              f"{rep.get('warnings')}")
        rep2 = state_mod.apply_proposal(
            book, {**base, "operation_id": "ch_002.test.gates2",
                   "entities": [{"name": "陈默", "summary": "拾灯人"}]},
            expected_chapter="ch_002", dry_run=True)
        check("update_entity_quiet", not any("新登记" in w for w in rep2.get("warnings", [])),
              f"{rep2.get('warnings')}")


def test_dangling_refs() -> None:
    clean_ents = [{"id": "p_001", "name": "陈默", "aliases": ["拾灯人"],
                   "address_matrix": {"苏老爷": "苏老爷"}},
                  {"id": "p_002", "name": "苏老爷"}]
    ents = [{"id": "p_001", "name": "陈默", "aliases": ["拾灯人"],
             "address_matrix": {"苏老爷": "苏老爷", "幽灵": "喂"}},
            {"id": "p_002", "name": "苏老爷"}]
    current = {"pov_ref": "p_001", "place_ref": "不存在的地",
               "present_refs": ["拾灯人", "路人甲"]}
    locked = {"entries": [{"id": "LOCK-001", "refs": ["陈默", "不存在的人"]}]}
    timeline = {"events": [
        {"id": "EVT-001", "event": "拾灯", "participants": ["p_001", "幽灵"],
         "causes": [], "consequences": ["EVT-002"]},
        {"id": "EVT-002", "event": "赴宴", "participants": [],
         "causes": ["EVT-001", "EVT-999", "不是编号"], "consequences": []},
    ]}
    cognition = {"entries": [
        {"id": "COG-001", "character": "陈默", "truth_ref": "GUN-001"},
        {"id": "COG-002", "character": "幽灵", "truth_ref": "KNO-404"},
        {"id": "COG-003", "character": "陈默", "truth_ref": "瞎写"},
        {"id": "COG-004", "character": "陈默", "truth_ref": "MIS-001"},
    ]}
    lines = {"foreshadows": [{"id": "GUN-001"}], "misunderstandings": [{"id": "MIS-001"}],
             "knowledge": [{"id": "KNO-001", "holders": ["陈默", "幽灵"]}]}
    got = dangling_ref_findings(ents, current, locked, timeline, cognition, lines)
    codes = sorted(c for c, _ in got)
    check("dangling_total", len(got) == 9, f"{got}")
    check("dangling_codes", codes == ["dangling_ref"] * 4 + ["entity_ref_unknown"] * 5,
          f"{codes}")
    msgs = " ".join(m for _, m in got)
    for needle in ("locked[LOCK-001]", "participants",
                   "EVT-999", "不是编号", "character", "KNO-404", "瞎写",
                   "address_matrix", "holders"):
        check(f"dangling_covers_{needle}", needle in msgs, msgs[:500])
    # current 系归 verify_data 硬查，本 helper 必须不重复报（分工留档）
    check("dangling_mis_quiet", "MIS-001" not in msgs, msgs[:500])
    check("dangling_ignores_current",
          dangling_ref_findings(clean_ents, current, {"entries": []},
                                {"events": []}, {"entries": []}, {}) == [])
    # 静默面：id/名/别名三域命中＋空快照
    clean_lines = {"foreshadows": [{"id": "GUN-001"}], "misunderstandings": [],
                   "knowledge": [{"id": "KNO-001", "holders": ["陈默", "p_002"]}]}
    check("dangling_quiet_clean",
          dangling_ref_findings(clean_ents,
                                {"pov_ref": "p_001",
                                 "present_refs": ["陈默", "拾灯人", "p_002"]},
                                {"entries": []}, {"events": []},
                                {"entries": []}, clean_lines) == [])
    check("dangling_quiet_empty",
          dangling_ref_findings([], {}, {}, {}, {}, {}) == [])


def test_dangling_e2e() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_refs_") as td:
        book, env = build_smoke_book(Path(td))
        # warning 路：address_matrix 键悬空 → entity_ref_unknown，rc 0
        persons_p = book / "state" / "persons.json"
        orig = persons_p.read_text(encoding="utf-8")
        try:
            persons = json.loads(orig)
            persons["entries"][0]["address_matrix"] = {"幽灵": "喂"}
            persons_p.write_text(json.dumps(persons, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check dangling-ref")
            check("dangling_e2e_fires", '"entity_ref_unknown"' in out, out[:1500])
        finally:
            persons_p.write_text(orig, encoding="utf-8")
        # error 路：pov_ref 悬空 → verify_data state_inconsistent，rc 1（分工留档）
        cur_p = book / "state" / "current.json"
        orig_cur = cur_p.read_text(encoding="utf-8")
        try:
            cur = json.loads(orig_cur)
            cur["pov_ref"] = "不存在的人"
            cur_p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            cp = run(["check", "--json"], env)
            check("verify_ref_error_path",
                  cp.returncode == 1 and '"state_inconsistent"' in cp.stdout,
                  cp.stdout[:1500])
        finally:
            cur_p.write_text(orig_cur, encoding="utf-8")


def test_match_norm() -> None:
    mn = evidence_mod.match_norm
    check("norm_particle", mn("无主的空灯") == "无主空灯", mn("无主的空灯"))
    check("norm_multi", mn("陈默攥紧了灯柄，吗？") == "陈默攥紧灯柄，？", mn("陈默攥紧了灯柄，吗？"))
    check("norm_keep_name", mn("苏老爷") == "苏老爷")
    check("norm_conservative", "之" in mn("王之影"), mn("王之影"))
    terms = evidence_mod.line_terms_for({"name": "无主空灯", "plan": "陈默的灯"}, "foreshadow", ["陈默"])
    check("norm_terms", terms == ["无主空灯", "陈默"], f"{terms}")
    last, seen = memory_mod._scan_last_seen([("ch_001", 1, "悬着一盏无主的空灯")], ["无主空灯"])
    check("norm_scan_hit", (last, seen) == (1, 1), f"{(last, seen)}")
    last, _ = memory_mod._scan_last_seen([("ch_001", 1, "今夜无灯")], ["无主空灯"])
    check("norm_scan_miss", last is None)


def test_present_track() -> None:
    ents = [{"id": "p_001", "name": "陈默", "aliases": ["拾灯人"]},
            {"id": "p_002", "name": "苏老爷"}]
    check("track_empty_refs_quiet",
          present_track_finding({"present_characters": ["陈默"]}, ents) is None)
    check("track_alias_id_quiet",
          present_track_finding({"present_characters": ["拾灯人"],
                                 "present_refs": ["p_001"]}, ents) is None)
    got = present_track_finding({"present_characters": ["陈默"],
                                 "present_refs": ["p_001", "p_002"]}, ents)
    check("track_mismatch_refs", got is not None and got[0] == "present_refs_mismatch"
          and "苏老爷" in got[1], f"{got}")
    got = present_track_finding({"present_characters": [],
                                 "present_refs": ["p_001"]}, ents)
    check("track_mismatch_empty_chars", got is not None and "仅引用轨有" in got[1], f"{got}")


def test_plan_actual() -> None:
    ents = [{"id": "p_001", "name": "陈默", "aliases": ["拾灯人"]}]
    beats = ("#### 出厂情绪表\n- 陈默：暴怒（5/5）\n- 苏九娘：隐忍（3/5）\n"
             "- 出厂情绪：（无特殊交代写\"无\"）\n")
    plan = parse_beats_cast_moods(beats)
    check("parse_moods", plan == {"陈默": ("暴怒", 5), "苏九娘": ("隐忍", 3)}, f"{plan}")
    check("parse_none", parse_beats_cast_moods("- 出厂情绪：无\n普通行\n") == {})
    moods = {"拾灯人": {"label": "暴怒", "level": 4},
             "苏九娘": {"label": "淡然", "level": 3},
             "路人": {"label": "欢喜", "level": 1}}
    got = mood_plan_actual_findings(beats, moods, ents)
    msgs = " ".join(m for _, m in got)
    check("plan_level_tolerance", not any("烈度" in m for _, m in got), f"{got}")
    check("plan_label_drift", any("淡然" in m for _, m in got), f"{got}")
    check("plan_actual_only", any("路人" in m and "即兴" in m for _, m in got), f"{got}")
    got2 = mood_plan_actual_findings(beats, {"陈默": {"label": "暴怒", "level": 2}}, ents)
    check("plan_level_drift", any("烈度" in m for _, m in got2), f"{got2}")
    check("plan_empty_skip", mood_plan_actual_findings("", moods, ents) == []
          and mood_plan_actual_findings(beats, {}, ents) == [])
    check("stale_gap", mood_stale_gap(1, 5) == 4)
    check("stale_gap_boundary", mood_stale_gap(3, 5) == 2)
    check("stale_gap_none", mood_stale_gap(None, 5) is None
          and mood_stale_gap(1, None) is None)


def test_time_and_track_e2e() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_dual_") as td:
        book, env = build_smoke_book(Path(td))
        cur_p = book / "state" / "current.json"
        orig = cur_p.read_text(encoding="utf-8")
        try:
            cur = json.loads(orig)
            cur["time"] = "第5日黄昏"
            cur["time_day"] = 3
            cur_p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check time-dual")
            check("time_day_mismatch_fires", '"time_day_mismatch"' in out, out[:1200])
        finally:
            cur_p.write_text(orig, encoding="utf-8")
        try:
            cur = json.loads(orig)
            cur["present_characters"] = []
            cur["present_refs"] = ["p_001"]
            cur_p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check present-dual")
            check("present_track_e2e_fires", '"present_refs_mismatch"' in out, out[:1200])
        finally:
            cur_p.write_text(orig, encoding="utf-8")
        # merge 侧双轨对账（dry-run，不落盘）
        rep = state_mod.apply_proposal(
            book, {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_002",
                   "operation_id": "ch_002.test.dual",
                   "current": {"time": "第5日黄昏", "time_day": 3}},
            expected_chapter="ch_002", dry_run=True)
        check("merge_time_cross", any("双轨不一致" in w for w in rep.get("warnings", [])),
              f"{rep.get('warnings')}")


def test_plan_actual_e2e() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_moodpa_") as td:
        book, env = build_smoke_book(Path(td))
        beats = next(iter(list(book.glob("outlines/*/beats/ch_001.md"))
                           or list(book.glob("outlines/**/ch_001.md"))))
        orig = beats.read_text(encoding="utf-8")
        try:
            beats.write_text(orig + "\n- 陈默：暴怒（5/5）\n", encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check plan-actual")
            check("plan_actual_e2e_fires", '"mood_plan_actual_drift"' in out, out[:1200])
            check("stale_quiet_fresh", '"mood_snapshot_stale"' not in out)
        finally:
            beats.write_text(orig, encoding="utf-8")


def test_audit_alias() -> None:
    ents = [{"id": "p_001", "name": "陈默", "aliases": ["拾灯人"]},
            {"id": "p_002", "name": "苏老爷"}]
    holder_canon = {"knowledge": [{"id": "KNO-001", "secret": "空灯藏着灯王信物",
                                    "status": "Active", "holders": ["陈默"]}]}
    holder_alias = {"knowledge": [{"id": "KNO-001", "secret": "空灯藏着灯王信物",
                                   "status": "Active", "holders": ["拾灯人"]}]}
    # 别名开口＋法定名 holders → 不得误标泄密
    t1 = "拾灯人道：“这空灯藏着灯王信物，绝不可外传。”"
    check("audit_alias_speaker_quiet",
          probe_secret_leakage(t1, [t1], holder_canon, ents) == [])
    # 法定名开口＋别名 holders → 反向亦不得误标
    t2 = "陈默道：“这空灯藏着灯王信物，绝不可外传。”"
    check("audit_alias_holder_quiet",
          probe_secret_leakage(t2, [t2], holder_alias, ents) == [])
    # 真泄密仍响：注册在册的非知情人开口
    t3 = "苏老爷道：“空灯藏着灯王信物，满城皆知。”"
    got = probe_secret_leakage(t3, [t3], holder_canon, ents)
    check("audit_true_leak_fires",
          len(got) == 1 and "苏老爷" in got[0].get("title", ""), f"{got}")


def test_v3_moods_roundtrip() -> None:
    row = next(s for t, a, s in v3_mod.V3_OP_SHAPES if t == "current")
    check("v3_shape_docs_dual",
          "time_day" in row and "present_moods" in row, row)
    with tempfile.TemporaryDirectory(prefix="novel_v3mood_") as td:
        book, _env = build_smoke_book(Path(td))
        rep = state_mod.apply_proposal(
            book, {"schema": "novel-studio.state-mutation/v3", "chapter": "ch_002",
                   "operation_id": "ch_002.test.v3moods",
                   "ops": [{"table": "current", "action": "update",
                            "set": {"time": "灯会后一日清晨", "time_day": 2,
                                    "present_moods": {"陈默": {"label": "振奋",
                                                              "level": 2}}}}]},
            expected_chapter="ch_002", dry_run=False)
        check("v3_moods_merge_clean", rep.get("errors") == [], f"{rep}")
        cur = state_mod.load_state(book, "current")
        check("v3_moods_landed",
              (cur.get("present_moods") or {}).get("陈默", {}).get("label") == "振奋"
              and cur.get("time_day") == 2, f"{cur.get('present_moods')}")


def test_object_envelope() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_objenv_") as td:
        book, _env = build_smoke_book(Path(td))
        persons_p = book / "state" / "persons.json"
        persons = json.loads(persons_p.read_text(encoding="utf-8"))
        persons["entries"][0].setdefault("aliases", []).append("拾灯人")
        persons_p.write_text(json.dumps(persons, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        (book / "state" / "cognition.json").write_text(json.dumps(
            {"entries": [{"id": "COG-900", "character": "拾灯人",
                          "kind": "secret_known", "content": "灯底有字",
                          "since_ch": "ch_001", "quote": "灯底有字"}]},
            ensure_ascii=False), encoding="utf-8")
        (book / "state" / "locked.json").write_text(json.dumps(
            {"entries": [{"id": "LOCK-900", "fact": "灯底字只有拾灯一脉能认",
                          "since_ch": "ch_001", "kind": "rule",
                          "quote": "灯底字", "refs": ["拾灯人"]}]},
            ensure_ascii=False), encoding="utf-8")
        (book / "state" / "items.json").write_text(json.dumps(
            {"entries": [{"id": "it_900", "name": "无主空灯", "type": "item",
                          "holder": "拾灯人"}]}, ensure_ascii=False), encoding="utf-8")
        # 以别名查：跨表归一＋ mood 速览
        got = _object_payload(book, "拾灯人")
        check("envelope_found_alias", got.get("found") is True, f"{got.get('ref')}")
        d = got.get("derived", {})
        check("envelope_belief_alias",
              [b["id"] for b in d.get("beliefs", [])] == ["COG-900"], f"{d}")
        check("envelope_mood",
              (d.get("mood") or {}).get("label") == "隐忍"
              and (d.get("mood") or {}).get("level") == 3, f"{d.get('mood')}")
        check("envelope_lock_alias", d.get("locks") == ["LOCK-900"], f"{d.get('locks')}")
        check("envelope_hold_alias", d.get("holds") == ["无主空灯"], f"{d.get('holds')}")
        # 法定名查同一包络（对称）
        got2 = _object_payload(book, "陈默")
        check("envelope_canon_same",
              got2.get("derived", {}).get("mood", {}) == d.get("mood"), f"{got2}")


def test_alias_determinism() -> None:
    reg = build_registry({"entries": [{"name": "陈默"},
                                      {"name": "路人乙", "aliases": ["陈默"]}]})
    check("alias_shadows_detected",
          any(p.get("code") == "alias_shadows_name" for p in reg.get("problems", [])),
          f"{reg.get('problems')}")
    with tempfile.TemporaryDirectory(prefix="novel_alias_") as td:
        book, _env = build_smoke_book(Path(td))
        data = {k: state_mod.load_state(book, k) for k in state_mod.STATE_KEYS}
        data["persons"]["entries"][0].setdefault("aliases", []).append("拾灯人")
        data["persons"]["entries"].append({"id": "p_099", "name": "路人乙", "type": "person",
                                           "status": "active", "aliases": ["拾灯人"]})
        errs = state_mod.verify_data(data)
        check("alias_verify_multi_owner",
              any("别名「拾灯人」被多实体占用" in e for e in errs), f"{errs}")
        persons_p = book / "state" / "persons.json"
        orig = persons_p.read_text(encoding="utf-8")
        try:
            persons = json.loads(orig)
            persons["entries"][0].setdefault("aliases", []).append("拾灯人")
            persons_p.write_text(json.dumps(persons, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            base = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_002"}
            rep = state_mod.apply_proposal(
                book, {**base, "operation_id": "ch_002.test.alias1",
                       "entities": [{"name": "路人丙", "type": "person",
                                     "aliases": ["拾灯人"]}]},
                expected_chapter="ch_002", dry_run=True)
            check("alias_merge_steal",
                  any("已被「陈默」占用" in e for e in rep.get("errors", [])), f"{rep}")
            rep2 = state_mod.apply_proposal(
                book, {**base, "operation_id": "ch_002.test.alias2",
                       "entities": [{"name": "陈默", "aliases": ["拾灯人"]}]},
                expected_chapter="ch_002", dry_run=True)
            check("alias_merge_redeclare_quiet", rep2.get("errors") == [], f"{rep2}")
            rep3 = state_mod.apply_proposal(
                book, {**base, "operation_id": "ch_002.test.alias3",
                       "entities": [{"name": "路人丁", "type": "person",
                                     "aliases": ["陈默"]}]},
                expected_chapter="ch_002", dry_run=True)
            check("alias_merge_shadow_warns",
                  any("重名" in w for w in rep3.get("warnings", []))
                  and rep3.get("errors") == [], f"{rep3}")
            rep4 = state_mod.apply_proposal(
                book, {"schema": "novel-studio.state-mutation/v3", "chapter": "ch_002",
                       "operation_id": "ch_002.test.alias4",
                       "ops": [{"table": "persons", "action": "create",
                                "entry": {"id": "p_100", "name": "路人戊",
                                          "aliases": ["拾灯人"]}}]},
                expected_chapter="ch_002", dry_run=True)
            check("alias_v3_steal",
                  any("已被「陈默」占用" in e for e in rep4.get("errors", [])), f"{rep4}")
        finally:
            persons_p.write_text(orig, encoding="utf-8")


def test_derived_surfacing() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_dersurf_") as td:
        book, env = build_smoke_book(Path(td))
        der_p = book / "state" / "derived.json"
        orig_der = der_p.read_text(encoding="utf-8")
        try:
            der = json.loads(orig_der)
            der["knowledge_flags"] = [{"cog_id": "COG-001", "character": "陈默",
                                       "truth_ref": "MIS-001", "verdict": "contradicted",
                                       "detail": "该误会已澄清，角色仍持旧认知"}]
            der_p.write_text(json.dumps(der, ensure_ascii=False, indent=2), encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check derived-surf")
            check("cognition_conflict_fires", '"cognition_truth_conflict"' in out, out[:800])
            check("derived_stale_fires_on_sealed_edit", '"derived_stale"' in out, out[:800])
        finally:
            der_p.write_text(orig_der, encoding="utf-8")
        out2 = must_ok(run(["check", "--json"], env), "check derived-fresh")
        check("derived_fresh_quiet", '"derived_stale"' not in out2, out2[:800])
        lines_p = book / "state" / "lines.json"
        orig_lines = lines_p.read_text(encoding="utf-8")
        try:
            lines = json.loads(orig_lines)
            lines["foreshadows"].append({"id": "GUN-999", "name": "测试线",
                                         "plant_ch": 1, "status": "Planted"})
            lines_p.write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
            out3 = must_ok(run(["check", "--json"], env), "check derived-stale")
            check("derived_stale_fires_on_state_edit", '"derived_stale"' in out3, out3[:800])
        finally:
            lines_p.write_text(orig_lines, encoding="utf-8")


def test_pool_and_shadow() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_poolsh_") as td:
        book, env = build_smoke_book(Path(td))
        led_p = book / "state" / "ledger.json"
        orig_led = led_p.read_text(encoding="utf-8")
        try:
            led = json.loads(orig_led)
            led.setdefault("pools", {})["lamp_ash"] = {"name": "灯灰", "unit": "钱",
                                                       "initial": 10, "current": -5}
            led["pools"]["debt_owed"] = {"name": "欠款", "unit": "钱",
                                         "initial": 0, "current": -3}
            led.setdefault("transactions", []).extend([
                {"chapter": "ch_001", "pool": "lamp_ash", "delta": -15,
                 "subject": "测试支出", "balance_after": -5},
                {"chapter": "ch_001", "pool": "debt_owed", "delta": -3,
                 "subject": "测试欠款", "balance_after": -3}])
            led_p.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check pool")
            check("pool_overdrawn_fires",
                  '"pool_overdrawn"' in out and "lamp_ash" in out, out[:800])
            check("pool_debt_exempt", "debt_owed" not in out, out[:800])
        finally:
            led_p.write_text(orig_led, encoding="utf-8")
        persons_p = book / "state" / "persons.json"
        orig_p = persons_p.read_text(encoding="utf-8")
        try:
            persons = json.loads(orig_p)
            persons["entries"].append({"id": "p_099", "name": "路人乙", "type": "person",
                                       "status": "active", "aliases": ["陈默"]})
            persons_p.write_text(json.dumps(persons, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            out2 = must_ok(run(["check", "--json"], env), "check shadow")
            check("alias_shadows_fires", '"alias_shadows_name"' in out2, out2[:800])
        finally:
            persons_p.write_text(orig_p, encoding="utf-8")


def test_history_collapse() -> None:
    check("history_note_empty", history_collapse_note({}) == "")
    check("history_note_format",
          history_collapse_note({"word_band_breach": 5, "final_without_raw": 0})
          == "🗂️ 另有 5 条历史 findings 已折叠（回看窗外：word_band_breach×5；check --full 看全量）")
    check("fp_stable", finding_fp("a", "b") == finding_fp("a", "b"))
    check("fp_sensitive", finding_fp("a", "b") != finding_fp("a", "b "))
    # e2e：回看窗压到 1，两章书必折叠最老一章（进程内直调 run_checks 以注入窗宽）
    with tempfile.TemporaryDirectory(prefix="novel_hist_") as td:
        book, _env = build_smoke_book(Path(td))
        srcs = list(book.glob("manuscript/*/final/ch_001*.md"))
        assert srcs, "smoke 书无 ch_001 定稿"
        dst = srcs[0].with_name(srcs[0].name.replace("ch_001", "ch_002"))
        dst.write_bytes(srcs[0].read_bytes())
        proj_p = book / "project.json"
        orig = proj_p.read_text(encoding="utf-8")
        old_win = checks_mod.HISTORY_WINDOW
        try:
            proj = json.loads(orig)
            proj["words_target"] = [10 ** 6, 10 ** 6 + 1]
            proj_p.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
            checks_mod.HISTORY_WINDOW = 1
            r = run_checks(book)
            check("history_collapsed_count",
                  r["stats"].get("history_collapsed_by_code", {}).get("word_band_breach") == 1,
                  json.dumps(r["stats"], ensure_ascii=False))
            codes = [i.get("code") for i in r["narrative_health"]["warnings"]]
            check("history_recent_individual",
                  codes.count("word_band_breach") == 1, f"{codes}")
            r_full = run_checks(book, full=True)
            check("history_full_nocollapse",
                  r_full["stats"].get("history_collapsed") == 0
                  and sum(1 for i in r_full["narrative_health"]["warnings"]
                          if i.get("code") == "word_band_breach") == 2,
                  json.dumps(r_full["stats"], ensure_ascii=False))
        finally:
            checks_mod.HISTORY_WINDOW = old_win
            proj_p.write_text(orig, encoding="utf-8")
            dst.unlink(missing_ok=True)


def test_locked_candidates() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_lockcand_") as td:
        book, env = build_smoke_book(Path(td))
        fact = "灯底刻着师父遗言"
        base = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_002"}
        cand = [{"fact": fact, "kind": "rule", "quote": "灯底刻着", "note": "测试提名"}]
        rep = state_mod.apply_proposal(
            book, {**base, "operation_id": "ch_002.test.cand1",
                   "locked_candidates": cand},
            expected_chapter="ch_002", dry_run=True)
        check("cand_dry_carry",
              rep.get("locked_candidates") == cand
              and any("提名" in u for u in rep.get("updated", [])), f"{rep}")
        check("cand_dry_pure",
              not (book / "log" / "locked_candidates.jsonl").exists())
        rep2 = state_mod.apply_proposal(
            book, {**base, "operation_id": "ch_002.test.cand2",
                   "locked_candidates": cand},
            expected_chapter="ch_002", dry_run=False)
        check("cand_landed",
              rep2.get("errors") == []
              and (book / "log" / "locked_candidates.jsonl").is_file(), f"{rep2}")
        out = must_ok(run(["check", "--json"], env), "check cand-pending")
        check("cand_pending_fires",
              '"locked_candidate_pending"' in out and fact[:6] in out, out[:800])
        lock_p = book / "state" / "locked.json"
        orig_lock = lock_p.read_text(encoding="utf-8")
        try:
            locked = json.loads(orig_lock)
            locked.setdefault("entries", []).append(
                {"id": "LOCK-001", "fact": fact, "since_ch": "ch_001",
                 "kind": "rule", "quote": "灯底刻着"})
            lock_p.write_text(json.dumps(locked, ensure_ascii=False, indent=2), encoding="utf-8")
            out2 = must_ok(run(["check", "--json"], env), "check cand-resolved")
            check("cand_resolved_quiet",
                  '"locked_candidate_pending"' not in out2, out2[:800])
        finally:
            lock_p.write_text(orig_lock, encoding="utf-8")


def test_baseline_flow() -> None:
    with tempfile.TemporaryDirectory(prefix="novel_base_") as td:
        book, env = build_smoke_book(Path(td))
        persons_p = book / "state" / "persons.json"
        orig = persons_p.read_text(encoding="utf-8")
        try:
            persons = json.loads(orig)
            persons["entries"][0]["address_matrix"] = {"幽灵": "喂"}
            persons_p.write_text(json.dumps(persons, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            out = must_ok(run(["check", "--json"], env), "check baseline-seed")
            r = json.loads(out)
            fps = [i["fp"] for i in r["narrative_health"]["warnings"]
                   if i.get("code") == "entity_ref_unknown"]
            check("baseline_seed", len(fps) == 1, out[:600])
            fp = fps[0]
            out_acc = must_ok(run(["check", "--accept", fp], env), "check accept")
            check("baseline_accept_ok", "已确认" in out_acc, out_acc[:400])
            r2 = json.loads(must_ok(run(["check", "--json"], env), "check baseline-hidden"))
            codes2 = [i.get("code") for i in r2["narrative_health"]["warnings"]]
            check("baseline_hidden",
                  "entity_ref_unknown" not in codes2
                  and r2["stats"]["accepted_hidden"] == 1,
                  json.dumps(r2["stats"], ensure_ascii=False))
            out_list = must_ok(run(["check", "--accepted"], env), "check accepted-list")
            check("baseline_listed", fp[:8] in out_list, out_list[:400])
            r3 = json.loads(must_ok(run(["check", "--full", "--json"], env), "check full"))
            codes3 = [i.get("code") for i in r3["narrative_health"]["warnings"]]
            check("baseline_full_reveals", "entity_ref_unknown" in codes3,
                  json.dumps(codes3, ensure_ascii=False))
            must_ok(run(["check", "--unaccept", fp[:8]], env), "check unaccept")
            r4 = json.loads(must_ok(run(["check", "--json"], env), "check baseline-restored"))
            codes4 = [i.get("code") for i in r4["narrative_health"]["warnings"]]
            check("baseline_restored",
                  "entity_ref_unknown" in codes4
                  and r4["stats"]["accepted_hidden"] == 0,
                  json.dumps(r4["stats"], ensure_ascii=False))
        finally:
            persons_p.write_text(orig, encoding="utf-8")
        cur_p = book / "state" / "current.json"
        orig_cur = cur_p.read_text(encoding="utf-8")
        try:
            cur = json.loads(orig_cur)
            cur["pov_ref"] = "不存在的人"
            cur_p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            r5 = json.loads(run(["check", "--json"], env).stdout)
            fp_err = r5["errors"][0]["fp"]
            cp2 = run(["check", "--accept", fp_err], env)
            check("baseline_refuses_errors", "不可确认消音" in cp2.stdout, cp2.stdout[:400])
        finally:
            cur_p.write_text(orig_cur, encoding="utf-8")


def test_activation_proof() -> None:
    # P0 完备性：simulate/reconcile 是真命令（零覆盖→有覆盖），冒烟书上实跑断言。
    with tempfile.TemporaryDirectory(prefix="novel_active_") as td:
        book, env = build_smoke_book(Path(td))
        out = must_ok(run(["simulate", "impact", "-e", "陈默"], env), "simulate impact")
        check("sim_impact_runs", "陈默" in out and ("主线" in out or "波及" in out),
              out[:600])
        out = must_ok(run(["simulate", "branch"], env), "simulate branch")
        check("sim_branch_runs", "假说" in out, out[:600])
        vols = sorted(p.name for p in (book / "outlines").iterdir() if p.is_dir())
        assert vols, "smoke 书无分卷"
        out = must_ok(run(["reconcile", vols[0]], env), "reconcile")
        check("reconcile_runs", "工作单" in out, out[:600])
        out = must_ok(run(["reconcile", vols[0], "--write"], env), "reconcile write")
        check("reconcile_write",
              (book / "log" / "review" / f"reconcile_{vols[0]}.md").is_file(),
              out[:400])
        cp = run(["reconcile", vols[0], "--write"], env)
        check("reconcile_write_refuses", cp.returncode != 0,
              cp.stdout[:300] + cp.stderr[:200])


def test_revision_loop() -> None:
    # 修文闭环：改旧 final→drift（带新哈希）→accept 留痕→静默→再改→换 fp 重报。
    with tempfile.TemporaryDirectory(prefix="novel_revise_") as td:
        book, env = build_smoke_book(Path(td))
        f = next(iter(book.glob("manuscript/*/final/ch_001*.md")))
        orig = f.read_bytes()
        try:
            f.write_text(orig.decode("utf-8") + "\n修订句甲。", encoding="utf-8")
            r = json.loads(must_ok(run(["check", "--json"], env), "check revised"))
            fps = [i["fp"] for i in r["warnings"] if i.get("code") == "final_drift"]
            check("revision_drift_fires", len(fps) == 1, json.dumps(r["stats"]))
            must_ok(run(["check", "--accept", fps[0]], env), "check accept-rev")
            r2 = json.loads(must_ok(run(["check", "--json"], env), "check rev-quiet"))
            check("revision_accepted_quiet",
                  all(i.get("code") != "final_drift" for i in r2["warnings"]))
            f.write_text(orig.decode("utf-8") + "\n修订句乙。", encoding="utf-8")
            r3 = json.loads(must_ok(run(["check", "--json"], env), "check re-revised"))
            fps3 = [i["fp"] for i in r3["warnings"] if i.get("code") == "final_drift"]
            check("revision_refires_new_fp",
                  len(fps3) == 1 and fps3[0] != fps[0], f"{fps} vs {fps3}")
        finally:
            f.write_bytes(orig)


def test_pack_budget() -> None:
    # pack 预算 e2e：P2 先裁 → 阶梯按序 → 豁免字节一致 → 小票重算诚实 → 阶梯用尽 breach。
    import copy
    from engine import common as common_mod
    from engine import pack as pack_mod
    with tempfile.TemporaryDirectory(prefix="novel_packbud_") as td:
        book, env = build_smoke_book(Path(td))
        beats_p = next(iter((book / "outlines").glob("*/beats/ch_001.md")))
        filler = "夜风很凉，远处更鼓三响，陈默独自守灯。"
        (beats_p.parent / "ch_002.md").write_text(
            "# ch_002 beats\n\n陈默" + filler * 40 + "\n", encoding="utf-8")
        syn_p = book / "state" / "synopsis.json"
        syn = json.loads(syn_p.read_text(encoding="utf-8"))
        for n in range(1, 8):
            syn["chapters"][f"ch_{n:03d}"] = {"num": n, "title": f"测{n}", "synopsis": "测"}
        syn_p.write_text(json.dumps(syn, ensure_ascii=False), encoding="utf-8")
        per_p = book / "state" / "persons.json"
        per = json.loads(per_p.read_text(encoding="utf-8"))
        chenmo = next(e for e in per["entries"] if e["name"] == "陈默")
        chenmo["summary"] += "，苏老爷亦在灯市。"
        p2 = copy.deepcopy(chenmo)
        p2["id"] = "p_002"
        p2["name"] = "苏老爷"
        p2["summary"] = "灯市牙人"
        per["entries"].append(p2)
        per_p.write_text(json.dumps(per, ensure_ascii=False), encoding="utf-8")
        base = pack_mod.build_pack(book, "ch_002")
        b0 = base["budget_report"]
        check("packbud_base_builds",
              not b0["over_budget"] and 0 < b0["total"] < b0["cap"],
              json.dumps({k: b0.get(k) for k in ("total", "cap", "over_budget")}))
        arm = {"spine": len(base["p1"]["spine"]),
               "indirect": len(base["p1"].get("indirect", [])),
               "file_index": len(base["p2"]["file_index"]),
               "pointers": len(base["p2"].get("old_chapter_pointers", [])),
               "prev_tail": len(base["p0"].get("prev_tail", ""))}
        check("packbud_fixture_armed",
              arm["spine"] == 7 and arm["indirect"] >= 1 and arm["file_index"] >= 1
              and arm["pointers"] >= 1 and arm["prev_tail"] > 400, json.dumps(arm))
        real_cap = pack_mod.PACK_TOKEN_CAP
        try:
            pack_mod.PACK_TOKEN_CAP = b0["total"] - 1
            r2 = pack_mod.build_pack(book, "ch_002")
            bb = r2["budget_report"]
            check("packbud_p2_first",
                  not bb["over_budget"] and bb.get("trimmed_file_index", 0) >= 1
                  and "compressed" not in bb,
                  json.dumps({k: bb.get(k) for k in ("total", "cap", "trimmed_file_index")}))
            check("packbud_p2_only_shrank",
                  r2["p0"] == base["p0"] and r2["p1"] == base["p1"]
                  and len(r2["p2"]["file_index"]) < len(base["p2"]["file_index"])
                  and r2["p2"].get("old_chapter_pointers") == base["p2"].get("old_chapter_pointers"))
            pack_mod.PACK_TOKEN_CAP = 200
            r3 = pack_mod.build_pack(book, "ch_002")
            b3 = r3["budget_report"]
            check("packbud_ladder_order",
                  b3.get("compressed") == ["裁 P2 旧章指针", "裁 P1 间接关联",
                                            "梗概脊柱收缩至最近 5 章", "上章余温裁至 400 字"],
                  json.dumps(b3.get("compressed"), ensure_ascii=False))
            check("packbud_hard_cap",
                  b3.get("hard_cap_breached") is True and b3["over_budget"]
                  and "压缩阶梯已尽" in (b3.get("trim_note") or ""),
                  json.dumps({k: b3.get(k) for k in ("total", "cap", "hard_cap_breached")}))
            check("packbud_protected_intact",
                  r3["p0"]["beats"] == base["p0"]["beats"]
                  and r3["p0"]["current"] == base["p0"]["current"]
                  and r3["p0"]["hard_reminders"] == base["p0"]["hard_reminders"]
                  and r3["p0"]["world_anchors"] == base["p0"]["world_anchors"]
                  and r3["p1"]["entities"] == base["p1"]["entities"])
            check("packbud_ladder_effects",
                  r3["p1"].get("indirect") == [] and r3["p2"].get("old_chapter_pointers") == []
                  and r3["p2"].get("file_index") == []
                  and r3["p1"]["spine"] == base["p1"]["spine"][-5:]
                  and r3["p0"]["prev_tail"] == base["p0"]["prev_tail"][:400] + "…")
            for layer in ("p0", "p1", "p2"):
                obj = r3[layer]
                recount = common_mod.est_tokens(pack_mod.render_layer(layer, obj)) if obj else 0
                check(f"packbud_honest_{layer}", b3[layer] == recount,
                      f"{layer}: 票={b3[layer]} 重算={recount}")
            check("packbud_honest_total",
                  b3["total"] == b3["p0"] + b3["p1"] + b3["p2"])
        finally:
            pack_mod.PACK_TOKEN_CAP = real_cap
        out = must_ok(run(["pack", "ch_002"], env), "pack ch_002 cli")
        check("packbud_cli_line", "total=" in out and "/20000" in out,
              "\n".join(out.splitlines()[-3:]))


def test_anchor_knob() -> None:
    # 世界锚点旋钮真实性：缺省全给 → 调低逐节截断 → 0 关恒给不断钉住 → 非法值回退。
    from engine import pack as pack_mod
    with tempfile.TemporaryDirectory(prefix="novel_anchor_") as td:
        book, _env = build_smoke_book(Path(td))
        pj = book / "project.json"
        orig = pj.read_text(encoding="utf-8")
        try:
            base = pack_mod._bible_core_anchors(book, None)
            first_sec = base.split("\n\n")[0]
            check("knob_default_full",
                  len(base) > 500 and "按预算截断" not in base and first_sec.startswith("### "))
            proj = json.loads(orig)
            proj["world_anchor_tokens"] = 200
            pj.write_text(json.dumps(proj, ensure_ascii=False), encoding="utf-8")
            cut = pack_mod._bible_core_anchors(book, None)
            check("knob_turndown_truncates",
                  len(cut) < len(base) and "按预算截断" in cut and first_sec in cut
                  and cut.count("### ") == 1, f"{len(cut)} vs {len(base)}")
            proj["world_anchor_tokens"] = 0
            pj.write_text(json.dumps(proj, ensure_ascii=False), encoding="utf-8")
            check("knob_zero_kills_fallback",
                  pack_mod._bible_core_anchors(book, None) == "")
            pinned = pack_mod._bible_core_anchors(book, ["公理"])
            check("knob_zero_keeps_pinned",
                  pinned != "" and "按章取用" in pinned and "公理" in pinned,
                  pinned[:120])
            for bad in (-5, "x", True):
                proj["world_anchor_tokens"] = bad
                pj.write_text(json.dumps(proj, ensure_ascii=False), encoding="utf-8")
                check(f"knob_invalid_{bad!r}_falls_back",
                      pack_mod._bible_core_anchors(book, None) == base)
            proj.pop("world_anchor_tokens", None)
            pj.write_text(json.dumps(proj, ensure_ascii=False), encoding="utf-8")
            miss = pack_mod._bible_core_anchors(book, ["不存在的词xyz"])
            check("knob_refs_miss_names_it",
                  "未命中任何" in miss and "可钉的节" in miss, miss[:150])
            beats = "---\nworld_refs: 战力 境界\n---\n正文"
            check("knob_refs_space_sep",
                  pack_mod._world_refs(beats) == ["战力", "境界"]
                  and pack_mod._world_refs(beats.replace(" ", ",")) == ["战力", "境界"])
        finally:
            pj.write_text(orig, encoding="utf-8")


def main() -> int:
    test_pure_helpers()
    test_match_norm()
    test_present_track()
    test_plan_actual()
    test_dangling_refs()
    test_dangling_e2e()
    test_quote_slots()
    test_silent_create_warns()
    test_v3_update_keeps_table()
    test_time_and_track_e2e()
    test_plan_actual_e2e()
    test_audit_alias()
    test_v3_moods_roundtrip()
    test_object_envelope()
    test_alias_determinism()
    test_derived_surfacing()
    test_pool_and_shadow()
    test_history_collapse()
    test_locked_candidates()
    test_activation_proof()
    test_revision_loop()
    test_pack_budget()
    test_anchor_knob()
    test_baseline_flow()
    test_deadlock_reclaim()
    test_remind_ch_stamp()
    test_violation_e2e()
    print(f"GATES PASS ({len(PASS)}): " + ", ".join(PASS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
