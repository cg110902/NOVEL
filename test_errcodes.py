#!/usr/bin/env python3
"""系统性触发每个 errcode，验证 engine 是否按文档预期工作"""
import json, pathlib, shutil, subprocess, sys, os

book = pathlib.Path("workspace/探针实验室")
python = ".venv/bin/python"

def run_check():
    result = subprocess.run([python, "studio.py", "check", "-w", str(book), "--json"],
                            capture_output=True, text=True, cwd="/home/user/NOVEL")
    try:
        data = json.loads(result.stdout)
        return data
    except:
        print("check failed stdout:", result.stdout[:500])
        print("stderr:", result.stderr[:500])
        return {"errors": [], "warnings": [], "infos": []}

def has_code(data, code):
    for bucket in ["errors", "warnings", "infos"]:
        for e in data.get(bucket, []):
            if e.get("code") == code:
                return True, e
    return False, None

def reset_book():
    # 删除 manuscript, outlines/beats, state modifications, keep project.json
    for p in (book / "manuscript").rglob("*.md"):
        p.unlink()
    for p in (book / "outlines" / "vol_01" / "beats").glob("*.md"):
        p.unlink()
    # reset state files to defaults via init? We'll reload from state/*.json and reset
    # For simplicity, re-init state by copying from a fresh template? Instead, use state files as is but clean specific parts
    # We'll just reset ledger, lines, entities to initial valid state
    # Use python to load and fix
    subprocess.run([python, "studio.py", "ledger", "recompute", "-w", str(book)], capture_output=True)

def test_case(name, setup_fn, expected_code, expected_bucket="errors"):
    print(f"\n=== TEST {name} expecting {expected_code} in {expected_bucket} ===")
    reset_book()
    setup_fn()
    data = run_check()
    found, entry = has_code(data, expected_code)
    if found:
        print(f"✅ PASS: found {expected_code}: {entry['msg'][:120]}")
        return True
    else:
        print(f"❌ FAIL: {expected_code} not found. Got errors:{[e['code'] for e in data.get('errors',[])]} warnings:{[w['code'] for w in data.get('warnings',[])]}")
        return False

# ---- individual setups ----

def setup_unfilled_slot():
    beats_dir = book / "outlines" / "vol_01" / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    (beats_dir / "ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\n---\n\n内容 {{slot:test}} 未填\n", encoding="utf-8")

def setup_candidate_leak():
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第一章 测试\n\n正文里有 candidate_123 这种工程痕迹。\n", encoding="utf-8")

def setup_latin_residue():
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第一章 测试\n\n正文里混入英文 hello world 残留。\n", encoding="utf-8")

def setup_manuscript_truncation():
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第一章 测试\n\n正文最后一句以逗号结尾，\n", encoding="utf-8")

def setup_duplicate_final():
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    # two files same chapter same version
    (final_dir / "ch_001.md").write_text("# 第一章 测试\n\n内容一。\n", encoding="utf-8")
    (final_dir / "ch_001_v1.md").write_text("# 第一章 测试\n\n内容二。\n", encoding="utf-8")

def setup_final_gap():
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第一章\n\n内容。\n", encoding="utf-8")
    (final_dir / "ch_003.md").write_text("# 第三章\n\n内容。\n", encoding="utf-8")

def setup_beats_extra_keys():
    beats_dir = book / "outlines" / "vol_01" / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    (beats_dir / "ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\nextra_illegal: 123\n---\n\n正文\n", encoding="utf-8")

def setup_beats_missing_form():
    beats_dir = book / "outlines" / "vol_01" / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    (beats_dir / "ch_001.md").write_text("---\nchapter: ch_001\n---\n\n正文\n", encoding="utf-8")

def setup_beats_form_repeat():
    beats_dir = book / "outlines" / "vol_01" / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    (beats_dir / "ch_001.md").write_text("---\nchapter: ch_001\nform: 生死博弈\n---\n\n正文\n", encoding="utf-8")
    (beats_dir / "ch_002.md").write_text("---\nchapter: ch_002\nform: 生死博弈\n---\n\n正文\n", encoding="utf-8")

def setup_style_notes_copy():
    beats_dir = book / "outlines" / "vol_01" / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    (beats_dir / "ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\nstyle_notes: 通俗直白大白话\n---\n\n正文\n", encoding="utf-8")
    (beats_dir / "ch_002.md").write_text("---\nchapter: ch_002\nform: 暗流汇聚\nstyle_notes: 通俗直白大白话\n---\n\n正文\n", encoding="utf-8")

def setup_alias_conflict():
    # two entities share same alias
    persons_path = book / "state" / "persons.json"
    data = json.loads(persons_path.read_text(encoding="utf-8"))
    data["entries"] = [
        {"id": "p_001", "name": "主角", "type": "person", "aliases": ["老王"], "status": "active"},
        {"id": "p_002", "name": "配角", "type": "person", "aliases": ["老王"], "status": "active"}
    ]
    persons_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_entity_ref_unknown():
    persons_path = book / "state" / "persons.json"
    data = json.loads(persons_path.read_text(encoding="utf-8"))
    data["entries"] = [
        {"id": "p_001", "name": "主角", "type": "person", "status": "active", "faction": "不存在的势力"},
    ]
    persons_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_prerequisite_cycle():
    lines_path = book / "state" / "lines.json"
    data = json.loads(lines_path.read_text(encoding="utf-8"))
    data["foreshadows"] = [
        {"id": "GUN-001", "name": "线A", "plant_ch": 1, "status": "Planted", "target_ch": 5, "requires": ["GUN-002"]},
        {"id": "GUN-002", "name": "线B", "plant_ch": 1, "status": "Planted", "target_ch": 5, "requires": ["GUN-001"]}
    ]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lines_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_ledger_tx_order():
    ledger_path = book / "state" / "ledger.json"
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    data["pools"] = {"standard_currency": {"name": "钱", "unit": "元", "initial": 100, "current": 100}}
    data["transactions"] = [
        {"chapter": "ch_002", "pool": "standard_currency", "delta": -10, "subject": "买东西", "type": "expense", "balance_after": 90},
        {"chapter": "ch_001", "pool": "standard_currency", "delta": -20, "subject": "买东西2", "type": "expense", "balance_after": 70}
    ]
    ledger_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_ledger_arith_broken():
    ledger_path = book / "state" / "ledger.json"
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    data["pools"] = {"standard_currency": {"name": "钱", "unit": "元", "initial": 100, "current": 999}}
    data["transactions"] = [
        {"chapter": "ch_001", "pool": "standard_currency", "delta": -10, "subject": "买东西", "type": "expense", "balance_after": 90}
    ]
    ledger_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_line_never_surfaced():
    lines_path = book / "state" / "lines.json"
    data = json.loads(lines_path.read_text(encoding="utf-8"))
    data["foreshadows"] = [
        {"id": "GUN-001", "name": "从未出现的伏笔", "plant_ch": 1, "status": "Planted", "target_ch": 10}
    ]
    data["misunderstandings"] = []
    data["knowledge"] = []
    lines_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第一章\n\n完全不提那个伏笔的内容。\n", encoding="utf-8")

def setup_tier_shift_without_event():
    persons_path = book / "state" / "persons.json"
    data = json.loads(persons_path.read_text(encoding="utf-8"))
    # create processed proposals to simulate tier shift
    data["entries"] = [
        {"id": "p_001", "name": "主角", "type": "person", "status": "active", "tier_rank": 5, "tier_name": "高阶"}
    ]
    persons_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # create a processed proposal that changes tier
    inbox_processed = book / "state" / "inbox" / "processed"
    inbox_processed.mkdir(parents=True, exist_ok=True)
    # ch_001 proposal that had tier 1
    (inbox_processed / "ch_001.json").write_text(json.dumps({
        "chapter": "ch_001",
        "operation_id": "test.tier.001",
        "entities": [{"action": "upsert", "id": "p_001", "name": "主角", "type": "person", "tier_rank": 1, "tier_name": "低阶"}]
    }, ensure_ascii=False), encoding="utf-8")
    (inbox_processed / "ch_002.json").write_text(json.dumps({
        "chapter": "ch_002",
        "operation_id": "test.tier.002",
        "entities": [{"action": "upsert", "id": "p_001", "name": "主角", "type": "person", "tier_rank": 5, "tier_name": "高阶"}]
    }, ensure_ascii=False), encoding="utf-8")
    # no timeline event for tier shift

# Run tests
tests = [
    ("unfilled_slot", setup_unfilled_slot, "unfilled_slot"),
    ("candidate_leak", setup_candidate_leak, "candidate_leak"),
    ("latin_residue", setup_latin_residue, "latin_residue"),
    ("manuscript_truncation", setup_manuscript_truncation, "manuscript_truncation"),
    ("duplicate_final", setup_duplicate_final, "duplicate_final"),
    ("final_gap_chapters", setup_final_gap, "final_gap_chapters"),
    ("beats_fm_extra_keys", setup_beats_extra_keys, "beats_fm_extra_keys"),
    ("beats_missing_form", setup_beats_missing_form, "beats_missing_form"),
    ("beats_form_repeat_without_reason", setup_beats_form_repeat, "beats_form_repeat_without_reason"),
    ("style_notes_copy", setup_style_notes_copy, "style_notes_copy"),
    ("alias_conflict", setup_alias_conflict, "alias_conflict"),
    ("entity_ref_unknown", setup_entity_ref_unknown, "entity_ref_unknown"),
    ("prerequisite_cycle", setup_prerequisite_cycle, "prerequisite_cycle"),
    ("ledger_tx_order", setup_ledger_tx_order, "ledger_tx_order"),
    ("ledger_arith_broken", setup_ledger_arith_broken, "ledger_arith_broken"),
    ("line_never_surfaced", setup_line_never_surfaced, "line_never_surfaced"),
    ("tier_shift_without_event", setup_tier_shift_without_event, "tier_shift_without_event"),
]

results = []
for name, setup, code in tests:
    try:
        ok = test_case(name, setup, code)
        results.append((name, code, ok))
    except Exception as e:
        print(f"EXCEPTION in {name}: {e}")
        import traceback; traceback.print_exc()
        results.append((name, code, False))

print("\n=== SUMMARY ===")
for name, code, ok in results:
    print(f"{'✅' if ok else '❌'} {name} -> {code}: {'PASS' if ok else 'FAIL'}")

print(f"\nTotal: {sum(1 for _,_,ok in results if ok)}/{len(results)} passed")
