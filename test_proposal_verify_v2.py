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

def make_final(book, ch="ch_001", title="第一章 标题", text="主角在档案馆里发现了秘密。"):
    fd=book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd/f"{ch}.md").write_text(f"# {title}\n\n{text}\n", encoding="utf-8")

def make_beats(book, ch="ch_001", text="任务书"):
    bd=book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd/f"{ch}.md").write_text(f"---\nchapter: {ch}\nform: 危机逼近\n---\n\n{text}\n", encoding="utf-8")

def verify(book, ch="ch_001"):
    result=run([PYTHON, STUDIO, "proposal", "verify", ch, "-w", str(book), "--json"])
    try:
        return json.loads(result.stdout)
    except:
        print(result.stdout[:1000])
        return {"verify":{"items":[]}}

def has_code(data, code):
    items=data.get("verify",{}).get("items",[]) or data.get("items",[])
    for it in items:
        if it.get("code")==code:
            return True, it
    return False, None

def test(name, setup_fn, expected_code, ch="ch_001"):
    book=fresh_book()
    try:
        setup_fn(book)
        data=verify(book, ch)
        found, entry = has_code(data, expected_code)
        if found:
            print(f"✅ {name} -> {expected_code}: {entry['msg'][:120]}")
            return True
        else:
            codes=[it.get("code") for it in (data.get("verify",{}).get("items",[]) or [])]
            print(f"❌ {name} -> {expected_code} NOT FOUND, got {codes[:20]}")
            return False
    finally:
        cleanup(book)

def setup_quote_none(book):
    make_final(book, text="主角在档案馆。")
    make_beats(book)
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.qnone","locked":[{"action":"plant","id":"LOCK-001","fact":"灯不能关","kind":"rule","note":"不可逆","quote":"","since_ch":"ch_001"}]}, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_title_absent(book):
    make_final(book, title="", text="内容")
    # final without proper title line? Actually "# " is title, so we need final without "# "?
    fd=book/"manuscript"/"vol_01"/"final"
    (fd/"ch_001.md").write_text("内容没有标题行\n\n正文\n", encoding="utf-8")
    make_beats(book)
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.tabsent"}, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_present_undeclared(book):
    make_final(book, text="主角在档案馆。")
    make_beats(book)
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.pundecl","current":{"present_characters":[]}}, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_amount_by_quote(book):
    make_final(book, text="灵石由100枚变为90枚。")
    make_beats(book)
    # need ledger pool
    lp=book/"state"/"ledger.json"
    data=json.loads(lp.read_text())
    data["pools"]={"test_pool":{"name":"灵石","unit":"枚","initial":100,"current":90}}
    data["transactions"]=[]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.byquote","ledger":{"transactions":[{"chapter":"ch_001","pool":"test_pool","delta":-10,"subject":"买东西","type":"expense","quote":"灵石由100枚变为90枚"}]}}, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_entities_unreadable(book):
    make_final(book, text="主角在档案馆。")
    make_beats(book)
    pp=book/"state"/"persons.json"
    pp.write_text("{ invalid", encoding="utf-8")
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.entunread"}, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_lines_unreadable(book):
    make_final(book, text="主角在档案馆。")
    make_beats(book)
    lp=book/"state"/"lines.json"
    lp.write_text("{ invalid", encoding="utf-8")
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.lineunread"}, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_ledger_unreadable(book):
    make_final(book, text="主角在档案馆。")
    make_beats(book)
    lp=book/"state"/"ledger.json"
    lp.write_text("{ invalid", encoding="utf-8")
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.ledunread"}, ensure_ascii=False, indent=2), encoding="utf-8")

def setup_present_unmentioned_dup(book):
    # already covered but test again
    make_final(book, text="主角独自行动。")
    make_beats(book)
    inbox=book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps({"chapter":"ch_001","operation_id":"ch_001.test.punment","current":{"present_characters":["主角","不存在的角色"]}}, ensure_ascii=False, indent=2), encoding="utf-8")

tests=[
    ("quote_none", setup_quote_none, "quote_none"),
    ("title_absent", setup_title_absent, "title_absent"),
    ("present_undeclared", setup_present_undeclared, "present_undeclared"),
    ("amount_by_quote", setup_amount_by_quote, "amount_by_quote"),
    ("entities_unreadable", setup_entities_unreadable, "entities_unreadable"),
    ("lines_unreadable", setup_lines_unreadable, "lines_unreadable"),
    ("ledger_unreadable", setup_ledger_unreadable, "ledger_unreadable"),
]

for name, setup, code in tests:
    test(name, setup, code)
