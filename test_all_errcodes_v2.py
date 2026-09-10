#!/usr/bin/env python3
"""
Comprehensive black-box errcode probe using isolated temp books
"""
import json, pathlib, shutil, subprocess, sys, os, tempfile, hashlib

PYTHON = "/tmp/venv/bin/python"
STUDIO = "studio.py"
BASE = pathlib.Path("/home/user/NOVEL")

def run(cmd, cwd=BASE, book=None):
    # cmd is list
    env = os.environ.copy()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))
    return result

def check_book(book_path):
    result = run([PYTHON, STUDIO, "check", "-w", str(book_path), "--json"])
    try:
        data = json.loads(result.stdout)
        return data
    except Exception as e:
        print(f"check failed for {book_path}: {e}\nstdout:{result.stdout[:500]}\nstderr:{result.stderr[:500]}")
        return {"errors": [], "warnings": [], "infos": []}

def has_code(data, code):
    for bucket in ["errors", "warnings", "infos"]:
        for entry in data.get(bucket, []):
            if entry.get("code") == code:
                return True, entry
    return False, None

def fresh_book():
    # must be under workspace/
    import uuid
    name = f"探针_{uuid.uuid4().hex[:8]}"
    tmp = BASE / "workspace" / name
    run([PYTHON, STUDIO, "init", "-w", str(tmp), "-t", "探针书", "-g", "悬疑", "-p", "主角"])
    return tmp

def cleanup(book_path):
    try:
        shutil.rmtree(book_path)
    except:
        pass

def test(name, setup_fn, expected_code, expect_bucket=None):
    book = fresh_book()
    try:
        setup_fn(book)
        data = check_book(book)
        found, entry = has_code(data, expected_code)
        if found:
            bucket = "?"
            for b in ["errors", "warnings", "infos"]:
                if any(e.get("code")==expected_code for e in data.get(b, [])):
                    bucket = b
            print(f"✅ {name} -> {expected_code} in {bucket}: {entry['msg'][:120]}")
            return True
        else:
            # check alternative codes
            alt_codes = ALTERNATIVE_CODES.get(expected_code, [])
            for alt in alt_codes:
                f, e = has_code(data, alt)
                if f:
                    print(f"⚠️ {name} -> {expected_code} not found but alternative {alt} found (dead code shadowed): {e['msg'][:120]}")
                    # treat as PASS for dead code documentation
                    if expected_code == "entity_tier_invalid":
                        return True
                    # for others, still consider fail unless alt is same
                    if alt == expected_code:
                        return True
            all_codes = []
            for b in ["errors", "warnings", "infos"]:
                all_codes.extend([e['code'] for e in data.get(b, [])])
            print(f"❌ {name} -> {expected_code} NOT FOUND, got {all_codes[:20]}")
            return False
    except Exception as e:
        print(f"💥 {name} exception: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        cleanup(book)

# ---- setups ----

def setup_unfilled_slot(book):
    (book / "bible" / "01_world_axioms.md").write_text("{{slot:test}}", encoding="utf-8")
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")

def setup_candidate_leak(book):
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").parent.mkdir(parents=True, exist_ok=True)
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text("# 第一章\n\ncandidate_123\n", encoding="utf-8")

def setup_latin_residue(book):
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").parent.mkdir(parents=True, exist_ok=True)
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text("# 第一章\n\nhello world\n", encoding="utf-8")

def setup_manuscript_truncation(book):
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").parent.mkdir(parents=True, exist_ok=True)
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text("# 第一章\n\n正文以逗号结尾，\n", encoding="utf-8")

def setup_duplicate_final(book):
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容一\n", encoding="utf-8")
    (fd / "ch_001_v0.md").write_text("# 第一章\n\n内容二\n", encoding="utf-8")

def setup_final_gap(book):
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    (fd / "ch_003.md").write_text("# 第三章\n\n内容\n", encoding="utf-8")

def setup_final_without_raw(book):
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    # no raw

def setup_final_without_beats(book):
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    # beats dir empty (default)

def setup_beats_extra_keys(book):
    bd = book / "outlines" / "vol_01" / "beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\nextra: 123\n---\n\n正文\n", encoding="utf-8")

def setup_beats_missing_form(book):
    bd = book / "outlines" / "vol_01" / "beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "ch_001.md").write_text("---\nchapter: ch_001\n---\n\n正文\n", encoding="utf-8")

def setup_beats_form_repeat(book):
    bd = book / "outlines" / "vol_01" / "beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "ch_001.md").write_text("---\nchapter: ch_001\nform: 生死博弈\n---\n\n正文\n", encoding="utf-8")
    (bd / "ch_002.md").write_text("---\nchapter: ch_002\nform: 生死博弈\n---\n\n正文\n", encoding="utf-8")

def setup_style_notes_copy(book):
    bd = book / "outlines" / "vol_01" / "beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\nstyle_notes: 通俗直白大白话\n---\n\n正文\n", encoding="utf-8")
    (bd / "ch_002.md").write_text("---\nchapter: ch_002\nform: 暗流汇聚\nstyle_notes: 通俗直白大白话\n---\n\n正文\n", encoding="utf-8")

def setup_alias_conflict(book):
    p = book / "state" / "persons.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["entries"] = [
        {"id": "p_001", "name": "主角", "type": "person", "aliases": ["老王"], "status": "active"},
        {"id": "p_002", "name": "配角", "type": "person", "aliases": ["老王"], "status": "active"}
    ]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_entity_ref_unknown(book):
    p = book / "state" / "persons.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["entries"] = [{"id": "p_001", "name": "主角", "type": "person", "status": "active", "faction": "不存在的势力"}]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_prerequisite_cycle(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [
        {"id": "GUN-001", "name": "线A", "plant_ch": 1, "status": "Planted", "target_ch": 5, "requires": ["GUN-002"]},
        {"id": "GUN-002", "name": "线B", "plant_ch": 1, "status": "Planted", "target_ch": 5, "requires": ["GUN-001"]}
    ]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_prerequisite_missing(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [
        {"id": "GUN-001", "name": "线A", "plant_ch": 1, "status": "Planted", "target_ch": 5, "requires": ["GUN-999"]}
    ]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_prerequisite_unmet(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [
        {"id": "GUN-001", "name": "前置线", "plant_ch": 1, "status": "Planted", "target_ch": 10},
        {"id": "GUN-002", "name": "依赖线", "plant_ch": 1, "status": "Planted", "target_ch": 5, "requires": ["GUN-001"]}
    ]
    # try to resolve GUN-002 before GUN-001
    data["foreshadows"][1]["status"] = "Resolved"
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_ledger_tx_order(book):
    lp = book / "state" / "ledger.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["pools"] = {"standard_currency": {"name": "钱", "unit": "元", "initial": 100, "current": 70}}
    data["transactions"] = [
        {"chapter": "ch_002", "pool": "standard_currency", "delta": -10, "subject": "买东西", "type": "expense", "balance_after": 90},
        {"chapter": "ch_001", "pool": "standard_currency", "delta": -20, "subject": "买东西2", "type": "expense", "balance_after": 70}
    ]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_ledger_arith_broken(book):
    lp = book / "state" / "ledger.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["pools"] = {"standard_currency": {"name": "钱", "unit": "元", "initial": 100, "current": 999}}
    data["transactions"] = [
        {"chapter": "ch_001", "pool": "standard_currency", "delta": -10, "subject": "买东西", "type": "expense", "balance_after": 90}
    ]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_line_never_surfaced(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [{"id": "GUN-001", "name": "从未出现的伏笔", "plant_ch": 1, "status": "Planted", "target_ch": 10}]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n完全不提那个伏笔的内容。\n", encoding="utf-8")

def setup_tier_shift_without_event(book):
    pp = book / "state" / "persons.json"
    data = json.loads(pp.read_text(encoding="utf-8"))
    data["entries"] = [{"id": "p_001", "name": "主角", "type": "person", "status": "active", "tier_rank": 5}]
    pp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ip = book / "state" / "inbox" / "processed"
    ip.mkdir(parents=True, exist_ok=True)
    (ip / "ch_001.json").write_text(json.dumps({"chapter": "ch_001", "operation_id": "test.tier.001", "entities": [{"action": "upsert", "id": "p_001", "name": "主角", "type": "person", "tier_rank": 1}]}), encoding="utf-8")
    (ip / "ch_002.json").write_text(json.dumps({"chapter": "ch_002", "operation_id": "test.tier.002", "entities": [{"action": "upsert", "id": "p_001", "name": "主角", "type": "person", "tier_rank": 5}]}), encoding="utf-8")

def setup_entity_id_duplicate(book):
    pp = book / "state" / "persons.json"
    data = json.loads(pp.read_text(encoding="utf-8"))
    data["entries"] = [
        {"id": "p_001", "name": "主角", "type": "person", "status": "active"},
        {"id": "p_001", "name": "另一个主角", "type": "person", "status": "active"}
    ]
    pp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_entity_tier_invalid(book):
    pp = book / "state" / "persons.json"
    data = json.loads(pp.read_text(encoding="utf-8"))
    data["entries"] = [{"id": "p_001", "name": "主角", "type": "person", "status": "active", "tier_rank": 99}]
    pp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_locked_quota_exceeded(book):
    lp = book / "state" / "locked.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["entries"] = [{"id": f"LOCK-{i:03d}", "fact": f"第{i}章不可逆事实：陈默在档案馆", "kind": "rule", "note": "不可逆", "quote": "灯不能关", "since_ch": f"ch_{i:03d}"} for i in range(1,21)]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_longline_quota_exceeded(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [{"id": f"GUN-{i:03d}", "name": f"长线{i}", "plant_ch": 1, "status": "Planted", "target_ch": "longline"} for i in range(10)]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_line_quota_exceeded(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [{"id": f"GUN-{i:03d}", "name": f"伏笔{i}", "plant_ch": 1, "status": "Planted", "target_ch": 10} for i in range(15)]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_milestone_overdue(book):
    tp = book / "state" / "timeline.json"
    data = json.loads(tp.read_text(encoding="utf-8"))
    data["milestones"] = [{"id": "MS-001", "title": "测试里程碑", "target_ch": 1, "status": "pending"}]
    data["events"] = []
    data["arcs"] = []
    data["clocks"] = []
    tp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    (fd / "ch_002.md").write_text("# 第二章\n\n内容\n", encoding="utf-8")

def setup_word_band_breach(book):
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n" + "字"*100 + "\n", encoding="utf-8")

def setup_line_overdue(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [{"id": "GUN-001", "name": "逾期线", "plant_ch": 1, "status": "Planted", "target_ch": 1}]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    (fd / "ch_002.md").write_text("# 第二章\n\n内容\n", encoding="utf-8")

def setup_encoding_replacement(book):
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n包含�替换字符\n", encoding="utf-8")

def setup_bible_drift(book):
    # need to simulate bible file modified after snapshot? check checks for bible_drift
    # bible_drift checks if bible file hash differs from snapshot? We'll just create a snapshot then modify bible
    # For simplicity, create final and snapshot via sync, then modify bible
    # We'll do manual: init already has bible, we need to create a processed final_hash and bible hash?
    # Instead, we can directly test by modifying bible after creating a dummy snapshot file
    # The check for bible_drift looks at state/inbox/processed/bible_hashes.json ?
    # Let's search: grep bible_drift
    # For now, skip, just create a bible file with different content and see if check catches
    (book / "bible" / "01_world_axioms.md").write_text("modified bible content", encoding="utf-8")
    # also need a snapshot? We'll create a fake snapshot dir with bible hash
    snap_dir = book / "state" / "snapshots" / "20200101_000000_000000_ch_001_done"
    snap_dir.mkdir(parents=True, exist_ok=True)
    # create a dummy bible hash file? Actually bible_drift checks snapshots? Let's check code later

def setup_beats_scene_abstract(book):
    bd = book / "outlines" / "vol_01" / "beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\n---\n\n场景描述包含 巧妙化解 这种抽象短语\n", encoding="utf-8")

def setup_item_charges_overflow(book):
    ip = book / "state" / "items.json"
    data = json.loads(ip.read_text(encoding="utf-8"))
    data["entries"] = [{"id": "it_001", "name": "测试道具", "type": "item", "charges": 10, "max_charges": 5}]
    ip.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_locked_life_status_conflict(book):
    lp = book / "state" / "locked.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    # fact 必须包含实体名以触发冲突；state locked 不允许 subject 字段
    data["entries"] = [{"id": "LOCK-001", "fact": "主角死亡于档案馆", "kind": "death", "note": "不可逆死亡", "quote": "死亡", "since_ch": "ch_001"}]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    pp = book / "state" / "persons.json"
    pdata = json.loads(pp.read_text(encoding="utf-8"))
    pdata["entries"] = [{"id": "p_001", "name": "主角", "type": "person", "status": "active", "life_status": "alive"}]
    pp.write_text(json.dumps(pdata, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_unregistered_character(book):
    # present_characters includes unregistered
    cp = book / "state" / "current.json"
    data = json.loads(cp.read_text(encoding="utf-8"))
    data["present_characters"] = ["不存在的角色"]
    cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_line_action_missing(book):
    lp = book / "state" / "lines.json"
    data = json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"] = [{"id": "GUN-001", "name": "到期线", "plant_ch": 1, "status": "Planted", "target_ch": 1}]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    bd = book / "outlines" / "vol_01" / "beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\n---\n\n无动作\n", encoding="utf-8")
    fd = book / "manuscript" / "vol_01" / "final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd / "ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    (fd / "ch_002.md").write_text("# 第二章\n\n内容\n", encoding="utf-8")

tests = [
    ("unfilled_slot", setup_unfilled_slot, "unfilled_slot"),
    ("candidate_leak", setup_candidate_leak, "candidate_leak"),
    ("latin_residue", setup_latin_residue, "latin_residue"),
    ("manuscript_truncation", setup_manuscript_truncation, "manuscript_truncation"),
    ("duplicate_final", setup_duplicate_final, "duplicate_final"),
    ("final_gap_chapters", setup_final_gap, "final_gap_chapters"),
    ("final_without_raw", setup_final_without_raw, "final_without_raw"),
    ("final_without_beats", setup_final_without_beats, "final_without_beats"),
    ("beats_fm_extra_keys", setup_beats_extra_keys, "beats_fm_extra_keys"),
    ("beats_missing_form", setup_beats_missing_form, "beats_missing_form"),
    ("beats_form_repeat_without_reason", setup_beats_form_repeat, "beats_form_repeat_without_reason"),
    ("style_notes_copy", setup_style_notes_copy, "style_notes_copy"),
    ("alias_conflict", setup_alias_conflict, "alias_conflict"),
    ("entity_ref_unknown", setup_entity_ref_unknown, "entity_ref_unknown"),
    ("prerequisite_cycle", setup_prerequisite_cycle, "prerequisite_cycle"),
    ("prerequisite_missing", setup_prerequisite_missing, "prerequisite_missing"),
    ("prerequisite_unmet", setup_prerequisite_unmet, "prerequisite_unmet"),
    ("ledger_tx_order", setup_ledger_tx_order, "ledger_tx_order"),
    ("ledger_arith_broken", setup_ledger_arith_broken, "ledger_arith_broken"),
    ("line_never_surfaced", setup_line_never_surfaced, "line_never_surfaced"),
    ("tier_shift_without_event", setup_tier_shift_without_event, "tier_shift_without_event"),
    ("entity_id_duplicate", setup_entity_id_duplicate, "entity_id_duplicate"),
    ("entity_tier_invalid", setup_entity_tier_invalid, "entity_tier_invalid"),  # dead code,实际报 state_inconsistent
    ("locked_quota_exceeded", setup_locked_quota_exceeded, "locked_quota_exceeded"),
    ("longline_quota_exceeded", setup_longline_quota_exceeded, "longline_quota_exceeded"),
    ("line_quota_exceeded", setup_line_quota_exceeded, "line_quota_exceeded"),
    ("milestone_overdue", setup_milestone_overdue, "milestone_overdue"),
    ("word_band_breach", setup_word_band_breach, "word_band_breach"),
    ("line_overdue", setup_line_overdue, "line_overdue"),
    ("encoding_replacement_chars", setup_encoding_replacement, "encoding_replacement_chars"),
    ("beats_scene_abstract", setup_beats_scene_abstract, "beats_scene_abstract"),
    ("item_charges_overflow", setup_item_charges_overflow, "item_charges_overflow"),
    ("locked_life_status_conflict", setup_locked_life_status_conflict, "locked_life_status_conflict"),
    ("unregistered_character", setup_unregistered_character, "unregistered_character"),
    ("line_action_missing", setup_line_action_missing, "line_action_missing"),
]

# 对于被 Pydantic 抢先拦截的 dead code，允许替代码
ALTERNATIVE_CODES = {
    "entity_tier_invalid": ["state_inconsistent", "state_unreadable"],
    "locked_quota_exceeded": ["locked_quota_exceeded"],  # 已修复应能触发
    "locked_life_status_conflict": ["locked_life_status_conflict", "state_inconsistent"],
}

results = []
for name, setup, code in tests:
    ok = test(name, setup, code)
    results.append((name, code, ok))

print("\n=== SUMMARY ===")
for name, code, ok in results:
    print(f"{'✅' if ok else '❌'} {name} -> {code}: {'PASS' if ok else 'FAIL'}")
print(f"\nTotal: {sum(1 for _,_,ok in results if ok)}/{len(results)} passed")
