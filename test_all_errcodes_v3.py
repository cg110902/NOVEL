#!/usr/bin/env python3
"""
Second batch: remaining check errcodes not covered in v2
"""
import json, pathlib, shutil, subprocess, os, uuid

PYTHON = "/tmp/venv/bin/python"
STUDIO = "studio.py"
BASE = pathlib.Path("/home/user/NOVEL")

def run(cmd, cwd=BASE):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))

def check_book(book_path):
    result = run([PYTHON, STUDIO, "check", "-w", str(book_path), "--json"])
    try:
        data = json.loads(result.stdout)
        return data
    except Exception as e:
        print(f"check failed {book_path}: {e}\n{result.stdout[:500]}")
        return {"errors":[], "warnings":[], "infos":[]}

def has_code(data, code):
    for bucket in ["errors","warnings","infos"]:
        for entry in data.get(bucket, []):
            if entry.get("code")==code:
                return True, entry
    return False, None

def fresh_book():
    name = f"探针_{uuid.uuid4().hex[:8]}"
    tmp = BASE / "workspace" / name
    run([PYTHON, STUDIO, "init", "-w", str(tmp), "-t", "探针书", "-g", "悬疑", "-p", "主角"])
    return tmp

def cleanup(p):
    try:
        shutil.rmtree(p)
    except:
        pass

def test(name, setup_fn, expected_code):
    book = fresh_book()
    try:
        setup_fn(book)
        data = check_book(book)
        found, entry = has_code(data, expected_code)
        if found:
            print(f"✅ {name} -> {expected_code}: {entry['msg'][:120]}")
            return True
        else:
            all_codes=[]
            for b in ["errors","warnings","infos"]:
                all_codes.extend([e['code'] for e in data.get(b,[])])
            print(f"❌ {name} -> {expected_code} NOT FOUND, got {all_codes[:30]}")
            return False
    except Exception as e:
        print(f"💥 {name} exception: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        cleanup(book)

# ---- setups ----

def setup_retired_entity_on_stage(book):
    p = book/"state"/"persons.json"
    data=json.loads(p.read_text(encoding="utf-8"))
    data["entries"]=[{"id":"p_001","name":"主角","type":"person","status":"active"},
                     {"id":"p_002","name":"老王","type":"person","status":"retired"}]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    cur = book/"state"/"current.json"
    cdata=json.loads(cur.read_text(encoding="utf-8"))
    cdata["present_characters"]=["老王"]
    cur.write_text(json.dumps(cdata, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_relation_target_unknown(book):
    p = book/"state"/"persons.json"
    data=json.loads(p.read_text(encoding="utf-8"))
    data["entries"]=[{"id":"p_001","name":"主角","type":"person","status":"active","relations":[{"target":"不存在的实体","type":"friend"}]}]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_entity_card_missing(book):
    p = book/"state"/"persons.json"
    data=json.loads(p.read_text(encoding="utf-8"))
    data["entries"]=[{"id":"p_001","name":"主角","type":"person","status":"active","card":"characters/nonexist.md"}]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_lines_state_unreadable(book):
    lp = book/"state"/"lines.json"
    lp.write_text("{ invalid json", encoding="utf-8")

def setup_state_unreadable(book):
    pp = book/"state"/"persons.json"
    pp.write_text("{ invalid", encoding="utf-8")

def setup_plotline_starvation(book):
    # need finals up to ch_005, line target_ch=1
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    for i in range(1,6):
        (fd/f"ch_{i:03d}.md").write_text(f"# 第{i}章\n\n内容{i}\n", encoding="utf-8")
    lp = book/"state"/"lines.json"
    data=json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"]=[{"id":"GUN-001","name":"饥饿线","plant_ch":1,"status":"Planted","target_ch":1}]
    data["misunderstandings"]=[]; data["knowledge"]=[]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_line_action_orphan(book):
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd/"ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\n---\n\n## 线索动作\n- GUN-999 本章推进\n", encoding="utf-8")
    lp = book/"state"/"lines.json"
    data=json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"]=[]; data["misunderstandings"]=[]; data["knowledge"]=[]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_acceptance_empty_criterion(book):
    # need empty_criteria_words configured, and beats containing that word in acceptance section
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text(encoding="utf-8"))
    proj["empty_criteria_words"]=["读者","沉浸感"]
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd/"ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\n---\n\n## 目标\n- 让读者感到沉浸感\n\n## 验收\n1. 读者沉浸感强\n", encoding="utf-8")

def setup_form_share_over_limit(book):
    # need 5+ chapters same form
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    for i in range(1,7):
        (bd/f"ch_{i:03d}.md").write_text(f"---\nchapter: ch_{i:03d}\nform: 危机逼近\n---\n\n正文{i}\n", encoding="utf-8")

def setup_final_drift(book):
    # need final_hashes.json with wrong sha
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd/"ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    proc_dir = book/"state"/"inbox"/"processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir/"final_hashes.json").write_text(json.dumps({"ch_001":{"sha256":"0"*64,"file":"ch_001.md"}}), encoding="utf-8")

def setup_high_tension_fatigue(book):
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text(encoding="utf-8"))
    proj["high_heat_forms"]=["生死博弈"]
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    for i in range(1,4):
        (bd/f"ch_{i:03d}.md").write_text(f"---\nchapter: ch_{i:03d}\nform: 生死博弈\n---\n\n正文\n", encoding="utf-8")

def setup_tension_flatline(book):
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    for i in range(1,4):
        (bd/f"ch_{i:03d}.md").write_text(f"---\nchapter: ch_{i:03d}\nform: 危机逼近\ntension_score: 2\n---\n\n正文\n", encoding="utf-8")

def setup_tension_burnout(book):
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    for i in range(1,5):
        (bd/f"ch_{i:03d}.md").write_text(f"---\nchapter: ch_{i:03d}\nform: 生死博弈\ntension_score: 9\n---\n\n正文\n", encoding="utf-8")

def setup_protagonist_pov_drift(book):
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text(encoding="utf-8"))
    proj["protagonist"]="主角"
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    for i in range(1,4):
        (fd/f"ch_{i:03d}.md").write_text(f"# 第{i}章\n\n配角甲在巷口等待，配角乙从暗处走出，两人交换了情报。\n\n配角丙在屋顶观察，手里握着一把短刀，眼神冷峻。\n\n整个夜晚，只有配角们在行动。\n", encoding="utf-8")

def setup_bible_drift(book):
    bible_dir = book/"bible"
    bible_dir.mkdir(parents=True, exist_ok=True)
    (bible_dir/"01_world_axioms.md").write_text("新版圣经内容", encoding="utf-8")
    # create bible_log.jsonl with old sha
    log_path = book/"state"/"bible_log.jsonl"
    log_path.write_text(json.dumps({"chapter":"ch_001","bible_sha":"deadbeef12345678"})+"\n", encoding="utf-8")

def setup_ledger_pool_undeclared(book):
    # need ledger with transaction referencing undeclared pool, but this is checked in state.verify_state? Actually ledger_pool_undeclared is check? Search: it's not in checks, it's in state? Let's see errcodes: ledger_pool_undeclared error about pool not declared. It's checked via state verification? We'll try to trigger via proposal? Actually check for ledger_pool_undeclared is not in checks.py grep earlier. Let's search again.
    lp = book/"state"/"ledger.json"
    data=json.loads(lp.read_text(encoding="utf-8"))
    data["pools"]={"standard_currency":{"name":"钱","unit":"元","initial":100,"current":100}}
    data["transactions"]=[{"chapter":"ch_001","pool":"unknown_pool","delta":-10,"subject":"买东西","type":"expense","balance_after":90}]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_locked_injection_missing(book):
    # need locked entries and beats without lock section
    lp = book/"state"/"locked.json"
    data=json.loads(lp.read_text(encoding="utf-8"))
    data["entries"]=[{"id":"LOCK-001","fact":"主角不能离开档案馆","kind":"rule","note":"不可逆","quote":"灯不能关","since_ch":"ch_001"}]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd/"ch_002.md").write_text("---\nchapter: ch_002\nform: 危机逼近\n---\n\n正文无锁注入\n", encoding="utf-8")

def setup_subplot_stall(book):
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    for i in range(1,18):
        (fd/f"ch_{i:03d}.md").write_text(f"# 第{i}章\n\n内容\n", encoding="utf-8")
    lp = book/"state"/"lines.json"
    data=json.loads(lp.read_text(encoding="utf-8"))
    data["foreshadows"]=[{"id":"GUN-001","name":"停滞线","plant_ch":1,"status":"Planted"}]
    data["misunderstandings"]=[]; data["knowledge"]=[]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_word_band_deviation(book):
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text(encoding="utf-8"))
    proj["words_target"]=[2000,3000]
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    # 1800 chars is within 20% below 2000 (400 tolerance) -> deviation not breach
    (fd/"ch_001.md").write_text("# 第一章\n\n"+"字"*1800+"\n", encoding="utf-8")

def setup_state_offline_edit(book):
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd/"ch_001.md").write_text("# 第一章\n\n内容\n", encoding="utf-8")
    proc_dir = book/"state"/"inbox"/"processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    # state_hashes with old hash for persons
    import hashlib
    persons_path = book/"state"/"persons.json"
    old_hash = "0"*64
    cur_hash = hashlib.sha256(persons_path.read_bytes()).hexdigest()
    # we write old hash to trigger offline edit detection, but current file is different from stored
    (proc_dir/"state_hashes.json").write_text(json.dumps({"last_sync_chapter":"ch_001","states":{"persons":old_hash}}), encoding="utf-8")

def setup_amount_arith_unverified(book):
    # need ledger pool and transaction, and final with "由 X 变为 Y" mismatch
    lp = book/"state"/"ledger.json"
    data=json.loads(lp.read_text(encoding="utf-8"))
    data["pools"]={"test_pool":{"name":"灵石","unit":"枚","initial":100,"current":90}}
    data["transactions"]=[{"chapter":"ch_001","pool":"test_pool","delta":-10,"subject":"买东西","type":"expense","balance_after":90}]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd/"ch_001.md").write_text("# 第一章\n\n灵石由100枚变为80枚。\n", encoding="utf-8")

def setup_param_shape_invalid(book):
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text(encoding="utf-8"))
    proj["words_target"]="invalid"
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_project_field_empty(book):
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text(encoding="utf-8"))
    proj["title"]=""
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_wordlist_unconfigured(book):
    # fresh book already has some unconfigured? The check for wordlist_unconfigured is info when not configured.
    # To trigger, ensure project.json missing some keys. But fresh book already triggers? Let's test.
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text(encoding="utf-8"))
    # remove optional keys
    for k in list(proj.keys()):
        if k not in ("title","genre","protagonist"):
            proj.pop(k, None)
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")

tests = [
    ("retired_entity_on_stage", setup_retired_entity_on_stage, "retired_entity_on_stage"),
    ("relation_target_unknown", setup_relation_target_unknown, "relation_target_unknown"),
    ("entity_card_missing", setup_entity_card_missing, "entity_card_missing"),
    ("lines_state_unreadable", setup_lines_state_unreadable, "lines_state_unreadable"),
    ("state_unreadable", setup_state_unreadable, "state_unreadable"),
    ("plotline_starvation", setup_plotline_starvation, "plotline_starvation"),
    ("line_action_orphan", setup_line_action_orphan, "line_action_orphan"),
    ("acceptance_empty_criterion", setup_acceptance_empty_criterion, "acceptance_empty_criterion"),
    ("form_share_over_limit", setup_form_share_over_limit, "form_share_over_limit"),
    ("final_drift", setup_final_drift, "final_drift"),
    ("high_tension_fatigue", setup_high_tension_fatigue, "high_tension_fatigue"),
    ("tension_flatline", setup_tension_flatline, "tension_flatline"),
    ("tension_burnout", setup_tension_burnout, "tension_burnout"),
    ("protagonist_pov_drift", setup_protagonist_pov_drift, "protagonist_pov_drift"),
    ("bible_drift", setup_bible_drift, "bible_drift"),
    # ledger_pool_undeclared is proposal-level, not check-level; skip here
    ("locked_injection_missing", setup_locked_injection_missing, "locked_injection_missing"),
    ("subplot_stall", setup_subplot_stall, "subplot_stall"),
    ("word_band_deviation", setup_word_band_deviation, "word_band_deviation"),
    ("state_offline_edit", setup_state_offline_edit, "state_offline_edit"),
    ("amount_arith_unverified", setup_amount_arith_unverified, "amount_arith_unverified"),
    ("param_shape_invalid", setup_param_shape_invalid, "param_shape_invalid"),
    ("project_field_empty", setup_project_field_empty, "project_field_empty"),
    ("wordlist_unconfigured", setup_wordlist_unconfigured, "wordlist_unconfigured"),
]

results=[]
for name, setup, code in tests:
    ok=test(name, setup, code)
    results.append((name, code, ok))

print("\n=== SUMMARY V3 ===")
for name, code, ok in results:
    print(f"{'✅' if ok else '❌'} {name} -> {code}: {'PASS' if ok else 'FAIL'}")
print(f"\nTotal: {sum(1 for _,_,ok in results if ok)}/{len(results)} passed")
