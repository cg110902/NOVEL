#!/usr/bin/env python3
"""
Proposal verify battery: quote_missing, title_mismatch, beats_overlap, etc.
"""
import json, pathlib, shutil, subprocess, os, uuid

PYTHON = "/tmp/venv/bin/python"
STUDIO = "studio.py"
BASE = pathlib.Path("/home/user/NOVEL")

def run(cmd, cwd=BASE):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))

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

def make_final(book, ch="ch_001", title="第一章 标题", text="主角在档案馆里发现了秘密。"):
    fd = book/"manuscript"/"vol_01"/"final"
    fd.mkdir(parents=True, exist_ok=True)
    (fd/f"{ch}.md").write_text(f"# {title}\n\n{text}\n", encoding="utf-8")

def make_beats(book, ch="ch_001", text="任务书内容"):
    bd = book/"outlines"/"vol_01"/"beats"
    bd.mkdir(parents=True, exist_ok=True)
    (bd/f"{ch}.md").write_text(f"---\nchapter: {ch}\nform: 危机逼近\n---\n\n{text}\n", encoding="utf-8")

def make_proposal(book, ch="ch_001", proposal_dict=None):
    inbox = book/"state"/"inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    if proposal_dict is None:
        proposal_dict = {"chapter": ch, "operation_id": f"{ch}.test.001", "synopsis": {"title": "第一章 标题", "text": "主角在档案馆里发现了秘密。"}}
    else:
        proposal_dict.setdefault("chapter", ch)
        proposal_dict.setdefault("operation_id", f"{ch}.test.{uuid.uuid4().hex[:4]}")
    (inbox/f"{ch}.json").write_text(json.dumps(proposal_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    return proposal_dict

def verify_book(book, ch="ch_001"):
    result = run([PYTHON, STUDIO, "proposal", "verify", ch, "-w", str(book), "--json"])
    try:
        data = json.loads(result.stdout)
        return data
    except Exception as e:
        print(f"verify failed {book}: {e}\nstdout:{result.stdout[:1000]}\nstderr:{result.stderr[:500]}")
        return {"verify": {"items": []}, "quote_notes": []}

def has_verify_code(data, code):
    items = data.get("verify", {}).get("items", []) if isinstance(data.get("verify"), dict) else data.get("items", [])
    # also top-level items?
    if not items and "verify" in data and isinstance(data["verify"], dict):
        items = data["verify"].get("items", [])
    # fallback: data itself might be verify dict
    if not items and "items" in data:
        items = data["items"]
    for it in items:
        if it.get("code")==code:
            return True, it
    return False, None

def test(name, setup_fn, expected_code):
    book = fresh_book()
    try:
        setup_fn(book)
        data = verify_book(book, "ch_001")
        found, entry = has_verify_code(data, expected_code)
        if found:
            print(f"✅ {name} -> {expected_code}: {entry['msg'][:150]}")
            return True
        else:
            codes = [it.get("code") for it in (data.get("verify",{}).get("items",[]) or data.get("items",[]))]
            print(f"❌ {name} -> {expected_code} NOT FOUND, got {codes[:30]}")
            # debug full
            # print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
            return False
    except Exception as e:
        print(f"💥 {name} exception: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        cleanup(book)

# ---- setups ----

def setup_quote_missing(book):
    make_final(book, text="主角在档案馆里发现了秘密，灯不能关。")
    make_beats(book, text="任务书")
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.quote_missing",
        "locked":[{"action":"plant","id":"LOCK-001","fact":"灯不能关","kind":"rule","quote":"","since_ch":"ch_001"}]
    })

def setup_title_mismatch(book):
    make_final(book, title="第一章 正确标题", text="内容")
    make_beats(book, text="任务书")
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.title_mismatch",
        "synopsis":{"title":"错误标题","text":"内容"}
    })

def setup_beats_overlap(book):
    final_text = "主角在档案馆里发现了秘密，灯不能关，档案馆的灯光昏暗。"
    make_final(book, text=final_text)
    make_beats(book, text=final_text)  # same text to cause overlap
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.overlap",
        "synopsis":{"title":"第一章 标题","text":final_text}
    })

def setup_locked_fact_untraceable(book):
    make_final(book, text="主角在档案馆里")
    make_beats(book)
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.untraceable",
        "locked":[{"action":"plant","id":"LOCK-001","fact":"那件事发生了","kind":"rule","quote":"那件事","since_ch":"ch_001"}]
    })

def setup_due_line_unhandled(book):
    # need lines with target_ch=1 and final mentioning it
    make_final(book, text="主角想起了那把无主空灯，灯光摇曳。")
    make_beats(book)
    # setup lines
    lp = book/"state"/"lines.json"
    data=json.loads(lp.read_text())
    data["foreshadows"]=[{"id":"GUN-001","name":"无主空灯","plant_ch":1,"status":"Planted","target_ch":1}]
    data["misunderstandings"]=[]; data["knowledge"]=[]
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.due",
        "lines":[]  # no handling
    })

def setup_candidate_new_entity(book):
    make_final(book, text="主角遇到了神秘的青铜古灯，古灯散发光芒。青铜古灯出现了三次。青铜古灯很重要。")
    make_beats(book)
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.candidate"
    })

def setup_critical_mutation(book):
    make_final(book, text="主角死亡了。")
    make_beats(book)
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.critical",
        "entities":[{"action":"upsert","id":"p_001","name":"主角","type":"person","life_status":"deceased","quote":"主角死亡了"}]
    })

def setup_state_watch_hit(book):
    make_final(book, text="主角断骨了，血流不止。")
    make_beats(book)
    proj_path = book/"project.json"
    proj=json.loads(proj_path.read_text())
    proj["state_watch"]={"injury":["断骨","血流"]}
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.watch",
        "current":{"injury":"完好"}
    })

def setup_amount_unsupported(book):
    make_final(book, text="主角有钱。")
    make_beats(book)
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.amount_unsupported",
        "ledger":{"transactions":[{"chapter":"ch_001","pool":"standard_currency","delta":-100,"subject":"买东西","type":"expense"}]}
    })

def setup_mention_not_present(book):
    make_final(book, text="主角和配角甲一起行动。配角甲说了一句话。")
    make_beats(book)
    # need entity lookup: add配角甲 to persons
    p = book/"state"/"persons.json"
    data=json.loads(p.read_text())
    data["entries"]=[{"id":"p_001","name":"主角","type":"person","status":"active"},{"id":"p_002","name":"配角甲","type":"person","status":"active"}]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.mention",
        "current":{"present_characters":["主角"]}
    })

def setup_present_unmentioned(book):
    make_final(book, text="主角独自行动。")
    make_beats(book)
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.present_unmentioned",
        "current":{"present_characters":["主角","不存在的角色"]}
    })

def setup_power_level_shift(book):
    make_final(book, text="主角突破了。")
    make_beats(book)
    cur = book/"state"/"current.json"
    cdata=json.loads(cur.read_text())
    cdata["power_level"]="筑基"
    cur.write_text(json.dumps(cdata, ensure_ascii=False, indent=2), encoding="utf-8")
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.power",
        "current":{"power_level":"金丹"}
    })

def setup_aftermath_opening_miss(book):
    # need current.aftershock and final head not containing it
    make_final(book, text="新的一天开始了，主角走在街上。")
    make_beats(book)
    cur = book/"state"/"current.json"
    cdata=json.loads(cur.read_text())
    cdata["aftershock"]="上一章爆炸了，火光冲天"
    cur.write_text(json.dumps(cdata, ensure_ascii=False, indent=2), encoding="utf-8")
    make_proposal(book, proposal_dict={
        "chapter":"ch_002",
        "operation_id":"ch_002.test.aftermath",
        "current":{}
    })
    # need ch_002 final, not ch_001
    # recreate for ch_002
    fd = book/"manuscript"/"vol_01"/"final"
    (fd/"ch_001.md").unlink(missing_ok=True)
    (fd/"ch_002.md").write_text("# 第二章\n\n新的一天开始了，主角走在街上。\n", encoding="utf-8")
    # proposal already for ch_002, but our verify_book uses ch_001 by default; we need special handling
    # We'll override in test function for this case

def setup_ledger_pool_undeclared(book):
    make_final(book, text="内容")
    make_beats(book)
    make_proposal(book, proposal_dict={
        "chapter":"ch_001",
        "operation_id":"ch_001.test.pool",
        "ledger":{"transactions":[{"chapter":"ch_001","pool":"unknown_pool","delta":-10,"subject":"买东西","type":"expense"}]}
    })

# Custom test for aftermath which needs ch_002
def test_aftermath():
    book = fresh_book()
    try:
        make_final(book, ch="ch_002", text="新的一天开始了，主角走在街上。")
        make_beats(book, ch="ch_002", text="任务书")
        cur = book/"state"/"current.json"
        cdata=json.loads(cur.read_text())
        cdata["aftershock"]="上一章爆炸了，火光冲天"
        cur.write_text(json.dumps(cdata, ensure_ascii=False, indent=2), encoding="utf-8")
        inbox = book/"state"/"inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox/"ch_002.json").write_text(json.dumps({"chapter":"ch_002","operation_id":"ch_002.test.aftermath","current":{}}, ensure_ascii=False, indent=2), encoding="utf-8")
        result = run([PYTHON, STUDIO, "proposal", "verify", "ch_002", "-w", str(book), "--json"])
        data=json.loads(result.stdout)
        items = data.get("verify",{}).get("items",[])
        found = any(it.get("code")=="aftermath_opening_miss" for it in items)
        if found:
            print(f"✅ aftermath_opening_miss -> PASS")
            return True
        else:
            print(f"❌ aftermath_opening_miss NOT FOUND, got {[it.get('code') for it in items]}")
            return False
    finally:
        cleanup(book)

tests = [
    ("quote_missing", setup_quote_missing, "quote_missing"),
    ("title_mismatch", setup_title_mismatch, "title_mismatch"),
    ("beats_overlap", setup_beats_overlap, "beats_overlap"),
    ("locked_fact_untraceable", setup_locked_fact_untraceable, "locked_fact_untraceable"),
    ("due_line_unhandled", setup_due_line_unhandled, "due_line_unhandled"),
    ("candidate_new_entity", setup_candidate_new_entity, "candidate_new_entity"),
    ("critical_mutation", setup_critical_mutation, "critical_mutation"),
    ("state_watch_hit", setup_state_watch_hit, "state_watch_hit"),
    ("amount_unsupported", setup_amount_unsupported, "amount_unsupported"),
    ("mention_not_present", setup_mention_not_present, "mention_not_present"),
    ("present_unmentioned", setup_present_unmentioned, "present_unmentioned"),
    ("power_level_shift", setup_power_level_shift, "power_level_shift"),
]

results=[]
for name, setup, code in tests:
    ok=test(name, setup, code)
    results.append((name, code, ok))

# aftermath special
ok_after = test_aftermath()
results.append(("aftermath_opening_miss","aftermath_opening_miss", ok_after))

# ledger_pool_undeclared is proposal check, not verify; test via proposal check command
def test_ledger_pool():
    book = fresh_book()
    try:
        make_final(book, text="内容")
        make_beats(book)
        inbox = book/"state"/"inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox/"ch_001.json").write_text(json.dumps({"schema":"novel-studio.state-mutation/v2","chapter":"ch_001","operation_id":"ch_001.test.pool","ledger":{"transactions":[{"chapter":"ch_001","pool":"unknown_pool","delta":-10,"subject":"买东西","type":"expense"}]}}, ensure_ascii=False, indent=2), encoding="utf-8")
        result = run([PYTHON, STUDIO, "proposal", "check", "ch_001", "-w", str(book), "--json"])
        data=json.loads(result.stdout)
        # check errors
        errs = data.get("check",{}).get("errors",[])
        found = any("ledger_pool_undeclared" in e for e in errs)
        if found:
            print(f"✅ ledger_pool_undeclared (proposal check) -> PASS: {errs[0][:120]}")
            return True
        else:
            print(f"❌ ledger_pool_undeclared NOT FOUND, got {errs[:5]}")
            return False
    finally:
        cleanup(book)

ok_pool = test_ledger_pool()
results.append(("ledger_pool_undeclared","ledger_pool_undeclared", ok_pool))

print("\n=== SUMMARY PROPOSAL VERIFY ===")
for name, code, ok in results:
    print(f"{'✅' if ok else '❌'} {name} -> {code}: {'PASS' if ok else 'FAIL'}")
print(f"\nTotal: {sum(1 for _,_,ok in results if ok)}/{len(results)} passed")
