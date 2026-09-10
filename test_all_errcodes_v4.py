#!/usr/bin/env python3
import json, pathlib, shutil, subprocess, uuid
PYTHON="/tmp/venv/bin/python"
STUDIO="studio.py"
BASE=pathlib.Path("/home/user/NOVEL")

def run(cmd, cwd=BASE):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))

def check_book(book_path):
    result = run([PYTHON, STUDIO, "check", "-w", str(book_path), "--json"])
    try:
        return json.loads(result.stdout)
    except:
        print(result.stdout[:500])
        return {"errors":[],"warnings":[],"infos":[]}

def has_code(data, code):
    for b in ["errors","warnings","infos"]:
        for e in data.get(b,[]):
            if e.get("code")==code:
                return True, e
    return False, None

def fresh_book():
    name=f"探针_{uuid.uuid4().hex[:8]}"
    tmp=BASE/"workspace"/name
    run([PYTHON, STUDIO, "init", "-w", str(tmp), "-t", "探针书", "-g", "悬疑", "-p", "主角"])
    return tmp

def cleanup(p):
    import shutil
    try:
        shutil.rmtree(p)
    except:
        pass

def test(name, setup_fn, expected_code):
    book=fresh_book()
    try:
        setup_fn(book)
        data=check_book(book)
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

def setup_voiceprint_drift(book):
    fd=book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    text_ch1="# 第一章\n\n"
    for i in range(12):
        text_ch1+=f'主角说：「好。」\n\n'
    (fd/"ch_001.md").write_text(text_ch1, encoding="utf-8")
    (fd/"ch_002.md").write_text("# 第二章\n\n主角说：「好。」\n\n主角说：「行。」\n", encoding="utf-8")
    for ch in [3,4,5,6]:
        (fd/f"ch_{ch:03d}.md").write_text(f"# 第{ch}章\n\n内容。\n", encoding="utf-8")
    for ch in [7,8]:
        txt=f"# 第{ch}章\n\n"
        for i in range(4):
            txt+=f'主角说：「这件事情的来龙去脉我已经全部都弄清楚了，从一开始的档案馆灯光到后来的所有线索，每一个细节我都记得清清楚楚，绝对不会有任何遗漏的地方。」\n\n'
        (fd/f"ch_{ch:03d}.md").write_text(txt, encoding="utf-8")

def setup_line_recall_cold(book):
    lp=book/"state"/"lines.json"
    data=json.loads(lp.read_text())
    data["foreshadows"]=[{"id":"GUN-001","name":"冷线测试","plant_ch":1,"status":"Planted","target_ch":30,"weight":1}]
    data["misunderstandings"]=[]; data["knowledge"]=[]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fd=book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd/"ch_001.md").write_text("# 第一章\n\n出现了冷线测试的内容。\n", encoding="utf-8")
    for i in range(2,31):
        (fd/f"ch_{i:03d}.md").write_text(f"# 第{i}章\n\n其他内容，没有提到那条线。\n", encoding="utf-8")
    bd=book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd/"ch_030.md").write_text("---\nchapter: ch_030\nform: 危机逼近\n---\n\n## 线索动作\n- resolve GUN-001\n", encoding="utf-8")

def setup_reader_memory_stale(book):
    lp=book/"state"/"locked.json"
    data=json.loads(lp.read_text())
    data["entries"]=[{"id":"LOCK-001","fact":"主角不能离开档案馆","kind":"rule","note":"不可逆","quote":"灯不能关","since_ch":"ch_001"}]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fd=book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd/"ch_001.md").write_text("# 第一章\n\n主角不能离开档案馆，灯不能关。\n", encoding="utf-8")
    for i in range(2,80):
        (fd/f"ch_{i:03d}.md").write_text(f"# 第{i}章\n\n其他内容，没有提到档案馆。\n", encoding="utf-8")

def setup_project_missing(book):
    # use non-existing path: we test via direct run, not via fresh_book
    pass

def setup_project_corrupt(book):
    proj=book/"project.json"
    proj.write_text("{ invalid json", encoding="utf-8")

def setup_project_field_type(book):
    proj_path=book/"project.json"
    proj=json.loads(proj_path.read_text())
    proj["words_target"]=[1, "invalid"]
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_stage0_onboarding(book):
    # fresh book with no finals/beats/raw and with unfilled slots -> should convert to onboarding info
    # fresh book already has unfilled slots in bible templates
    # Ensure no finals
    pass

def setup_runtime_dependency_missing(book):
    # Hard to trigger without uninstalling deps; skip
    pass

tests=[
    ("voiceprint_drift", setup_voiceprint_drift, "voiceprint_drift"),
    ("line_recall_cold", setup_line_recall_cold, "line_recall_cold"),
    ("reader_memory_stale", setup_reader_memory_stale, "reader_memory_stale"),
    ("project_corrupt", setup_project_corrupt, "project_corrupt"),
    ("project_field_type", setup_project_field_type, "project_field_type"),
    ("stage0_onboarding", setup_stage0_onboarding, "stage0_onboarding"),
]

results=[]
for name, setup, code in tests:
    if name in ("project_missing","runtime_dependency_missing"):
        continue
    ok=test(name, setup, code)
    results.append((name, code, ok))

# special tests for project_missing
def test_project_missing():
    fake = BASE/"workspace"/f"不存在_{uuid.uuid4().hex[:6]}"
    result = run([PYTHON, STUDIO, "check", "-w", str(fake), "--json"])
    try:
        data=json.loads(result.stdout)
        found = any(e.get("code")=="project_missing" for e in data.get("errors",[]))
        print(f"{'✅' if found else '❌'} project_missing -> {'PASS' if found else 'FAIL'}")
        return found
    except:
        print("project_missing parse fail")
        return False

ok_missing = test_project_missing()
results.append(("project_missing","project_missing", ok_missing))

print("\n=== SUMMARY V4 ===")
for name, code, ok in results:
    print(f"{'✅' if ok else '❌'} {name} -> {code}: {'PASS' if ok else 'FAIL'}")
print(f"\nTotal: {sum(1 for _,_,ok in results if ok)}/{len(results)} passed")
