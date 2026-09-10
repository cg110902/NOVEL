#!/usr/bin/env python3
import json, pathlib, subprocess, uuid
PYTHON="/tmp/venv/bin/python"
STUDIO="studio.py"
BASE=pathlib.Path("/home/user/NOVEL")

def run(cmd, cwd=BASE):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))

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

def test_locked_reuse():
    book=fresh_book()
    try:
        # create existing locked entry
        lp=book/"state"/"locked.json"
        data=json.loads(lp.read_text())
        data["entries"]=[{"id":"LOCK-001","fact":"主角不能离开档案馆","kind":"rule","note":"不可逆","quote":"灯不能关","since_ch":"ch_001"}]
        lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # create final and beats
        fd=book/"manuscript"/"vol_01"/"final"
        fd.mkdir(parents=True, exist_ok=True)
        (fd/"ch_001.md").write_text("# 第一章\n\n主角在档案馆。\n", encoding="utf-8")
        bd=book/"outlines"/"vol_01"/"beats"
        bd.mkdir(parents=True, exist_ok=True)
        (bd/"ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\n---\n正文\n", encoding="utf-8")
        inbox=book/"state"/"inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        # proposal tries to reuse LOCK-001 with different fact
        prop={"schema":"novel-studio.state-mutation/v2","chapter":"ch_001","operation_id":"ch_001.test.reuse","locked":[{"action":"plant","id":"LOCK-001","fact":"不同的事实","kind":"rule","note":"不可逆规则","quote":"不同的","since_ch":"ch_001"}]}
        (inbox/"ch_001.json").write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
        result=run([PYTHON, STUDIO, "proposal", "check", "ch_001", "-w", str(book), "--json"])
        data=json.loads(result.stdout)
        errs=data.get("check",{}).get("errors",[])
        print("locked reuse check errors:", errs[:3])
        found=any("locked_entry_id_reuse" in e for e in errs)
        print("✅ locked_entry_id_reuse" if found else "❌ locked_entry_id_reuse FAIL")
        return found
    finally:
        cleanup(book)

def test_cognition_reuse():
    book=fresh_book()
    try:
        cp=book/"state"/"cognition.json"
        data=json.loads(cp.read_text())
        data["entries"]=[{"id":"COG-001","character":"主角","kind":"fact","content":"以为灯是安全的","truth_ref":"LOCK-001","since_ch":"ch_001","quote":"灯是安全的"}]
        cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        fd=book/"manuscript"/"vol_01"/"final"
        fd.mkdir(parents=True, exist_ok=True)
        (fd/"ch_001.md").write_text("# 第一章\n\n主角在档案馆。\n", encoding="utf-8")
        bd=book/"outlines"/"vol_01"/"beats"
        bd.mkdir(parents=True, exist_ok=True)
        (bd/"ch_001.md").write_text("---\nchapter: ch_001\nform: 危机逼近\n---\n正文\n", encoding="utf-8")
        inbox=book/"state"/"inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        prop={"schema":"novel-studio.state-mutation/v2","chapter":"ch_001","operation_id":"ch_001.test.cogreuse","cognition":[{"action":"plant","id":"COG-001","character":"主角","kind":"fact","content":"不同的认知","truth_ref":"LOCK-001","since_ch":"ch_001","quote":"不同的认知"}]}
        (inbox/"ch_001.json").write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
        result=run([PYTHON, STUDIO, "proposal", "check", "ch_001", "-w", str(book), "--json"])
        data=json.loads(result.stdout)
        errs=data.get("check",{}).get("errors",[])
        print("cognition reuse errors:", errs[:3])
        found=any("cognition_entry_id_reuse" in e for e in errs)
        print("✅ cognition_entry_id_reuse" if found else "❌ cognition_entry_id_reuse FAIL")
        return found
    finally:
        cleanup(book)

test_locked_reuse()
test_cognition_reuse()
