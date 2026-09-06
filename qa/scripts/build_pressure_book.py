"""Build a 26-chapter pressure book (full pipeline exercised via real syncs).

Phase 1: init + project.json + per-chapter beats/raw/final scaffold.
Phase 2: orchestrated proposals (ch_001..ch_026), each applied by `studio.py sync`
  so every merge gate runs for real. Chapter kinds exercised:
    ch_001  entities(14, aliases) + pools + LOCK death/irreversible + milestones +
            clocks + lines(GUN-001/GUN-003/KNO-001/MIS-001/GUN-901 longline) + events
    ch_002  GUN-003 plant; entity summary updates; ledger tx
    ch_003  GUN-002 plant (requires GUN-003); present_characters; tx; event
    ch_004.. ordinary advance (tx + event + synopsis + time + cognition occasional)
    ch_006  resolve GUN-003; timeline replace-revision of a ch_001 event
    ch_007  MIS-002 plant; entity location update; ledger tx
    ch_009  escalate MIS-001
    ch_010  remind GUN-001 (target stays 20); clock still ticking
    ch_012  resolve GUN-002
    ch_014  resolve KNO-001 (early? target 14 -> same ch ok)
    ch_016  resolve MIS-001
    ch_018  cognition learned; item charges drop 4->3 (max unchanged)
    ch_020  resolve GUN-001 (main foreshadow closes)
    ch_022  resolve KNO-002
    ch_024  resolve MIS-002
    ch_026  final status push + synopsis
After all syncs: assert every chapter applied (rc 0) and `check` errors == 0.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/qa_root")
from conftest_prose import prose_block  # noqa: E402

REPO = Path("/home/user/NOVEL")
PY = "/home/user/.venv-novel/bin/python"
STUDIO = REPO / "studio.py"
ROOT = Path("/tmp/qa_root")
BOOK = ROOT / "pb_book"
GENRE = "悬疑"
SCHEMA = "novel-studio.state-mutation/v2"

ENTITIES = [
    dict(name="陆沉舟", type="person", status="active", life_status="alive",
         aliases=["阿舟"], realm="拾灯人", faction="灯司", attitude="neutral",
         summary="底层拾灯人，靠算账立足", holder="", location="临安城"),
    dict(name="赵六", type="person", status="active", life_status="alive",
         aliases=["老赵"], realm="更夫", faction="灯司", attitude="friendly",
         summary="主角老邻居", location="临安城"),
    dict(name="苏九娘", type="person", status="active", life_status="alive",
         aliases=["九娘"], realm="茶楼掌柜", attitude="friendly",
         summary="茶楼掌柜，消息灵通", location="临安城"),
    dict(name="李捕头", type="person", status="active", life_status="alive",
         aliases=["官差"], realm="捕快", faction="灯司", attitude="neutral",
         summary="负责瓮城命案", location="临安城"),
    dict(name="灯司主簿", type="person", status="active", life_status="alive",
         aliases=["主簿"], realm="主簿", faction="灯司", attitude="hostile",
         summary="灯司账目经手人", location="临安城"),
    dict(name="赵七星", type="person", status="retired", life_status="deceased",
         aliases=["七星"], realm="巡灯使", faction="灯司",
         summary="ch_001 死于瓮城"),
    dict(name="密匣", type="item", status="active", aliases=["匣子"],
         summary="藏着灯司黑账的匣子", holder="陆沉舟", location="陆沉舟身上"),
    dict(name="七星古镜", type="item", status="active", aliases=["古镜"],
         summary="灯司禁物", holder="灯司主簿", location="主簿宅",
         charges=4, max_charges=4),
    dict(name="照夜灯", type="item", status="active", aliases=["灯"],
         summary="无籍之灯", holder="陆沉舟", location="陆沉舟身上"),
    dict(name="临安灯司", type="faction", status="active", aliases=["灯司"],
         summary="掌灯籍的衙门", location="临安城"),
    dict(name="黑煞宗", type="faction", status="active",
         summary="城外暗势力", location="城外"),
    dict(name="城南瓮城", type="place", status="active", aliases=["瓮城"],
         summary="赵七星遇害处", location="临安城南"),
    dict(name="苏记茶楼", type="place", status="active", aliases=["茶楼"],
         summary="九娘的茶楼", location="临安城东市"),
    dict(name="杂货铺", type="place", status="active",
         summary="陆沉舟常去", location="临安城"),
]
ACTIVE_PRESENT = ["陆沉舟", "赵六", "苏九娘", "李捕头", "灯司主簿", "密匣"]


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["NOVEL_STUDIO_WORKSPACE_ROOT"] = str(ROOT)
    env["PYTHONUTF8"] = "1"
    return subprocess.run([PY, str(STUDIO), *[str(a) for a in args]],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=str(REPO))


def prop(ch_num: int, tag: str, **over) -> dict:
    p = {"schema": SCHEMA, "chapter": f"ch_{ch_num:03d}",
         "operation_id": f"ch_{ch_num:03d}.qa.{tag}", "current": {}, "entities": [],
         "lines": [], "timeline": {}, "ledger": {}, "synopsis": {}, "locked": [],
         "cognition_delta": []}
    p.update(over)
    return p


def tx(ch_num: int, delta: int, subject: str, pool: str = "silver",
       note: str = "", type_: str | None = None) -> dict:
    t = {"chapter": f"ch_{ch_num:03d}", "pool": pool, "delta": delta,
         "subject": subject,
         "type": type_ or ("income" if delta >= 0 else "expense")}
    if note:
        t["note"] = note
    return t


def sync_inbox(ch_num: int, p: dict) -> None:
    inbox = BOOK / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    f = inbox / f"ch_{ch_num:03d}.json"
    f.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    r = run_cli("sync", f"ch_{ch_num:03d}", "-w", str(BOOK), "--json")
    if r.returncode != 0:
        print(f"!!! sync ch_{ch_num:03d} rc={r.returncode}")
        print(r.stdout[-2000:])
        print(r.stderr[-500:])
        sys.exit(1)
    print(f"sync ch_{ch_num:03d} ok")


def main() -> None:
    if BOOK.exists():
        shutil.rmtree(BOOK)
    r = run_cli("init", "-w", str(BOOK), "-t", "压力测试书pb", "-g", GENRE, "-p", "陆沉舟")
    assert r.returncode == 0, r.stdout + r.stderr

    pj_path = BOOK / "project.json"
    pj = json.loads(pj_path.read_text(encoding="utf-8"))
    pj["words_target"] = [2400, 3600]
    pj["generic_stopwords"] = ["掌柜", "伙计", "官差", "路人", "行人", "街坊", "邻居", "大人"]
    pj["critical_injury_words"] = ["重伤", "濒死", "断臂", "毒发", "气绝"]
    pj["abstract_phrases"] = ["巧妙化解", "发生争执", "气氛变得紧张", "众人震惊"]
    pj["high_heat_forms"] = ["生死博弈"]
    pj["empty_criteria_words"] = ["读者", "沉浸感", "代入感", "引人入胜"]
    pj["hook_words"] = {"strong": ["动手", "下狱", "报官"], "suspense": ["尾随", "夜半", "对不上"],
                        "anticlimax": ["虚惊一场", "原来没事"]}
    pj["audit_mode"] = "off"
    pj["lines_cap"] = {"active_foreshadows": 8, "longline_foreshadows": 5,
                       "active_knowledge": 5, "active_misunderstandings": 4}
    pj_path.write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")

    vol = BOOK / "outlines" / "vol_01"
    raw = BOOK / "manuscript" / "vol_01" / "raw"
    fin = BOOK / "manuscript" / "vol_01" / "final"
    (vol / "beats").mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    fin.mkdir(parents=True, exist_ok=True)

    forms = ["暗流汇聚", "危机逼近", "正面冲突", "余波荡漾"]
    styles = ["平实口语 | 动作收尾", "短句急促 | 对白推进", "冷叙述 | 环境压人",
              "絮语式 | 算账收口"]
    for n in range(1, 27):
        ch = f"ch_{n:03d}"
        i = (n - 1) % 4
        # mark chapter when a line resolves so line_action_missing stays quiet
        action_note = "- GUN-001（本章未到期，仅推进）\n" if n in (10,) else ""
        fm = (f"---\nchapter: {ch}\nvol: vol_01\nform: {forms[i]}\npov: 陆沉舟·视角\n"
              f"words: 2600-3400\ntension_curve: 起势 → 试探 → 破局 → 收口\n"
              f"tension_score: {5 + (n % 3)}\nstage_mode: Simmering\n"
              f"style_notes: {styles[i]}\neditor_extra: 打斗最多两回合。\n---\n\n"
              f"## 本章坐标\n\n- **所属阶段**：阶段{(n - 1)//6 + 1}（{ch}）\n"
              f"- 当章预定规划：第{n}章推进主线。\n\n"
              f"## 核心冲突与场景脉络\n\n- **本章核心戏剧目标**：第{n}章主角追查黑账再进一步。\n\n"
              f"## 拍点与场景切片\n\n- **场景一：开场**\n  - 内容：主角在日常里遇到异常，开始盘算。\n"
              f"- **场景二：交锋**\n  - 内容：主角与对手交锋，靠算计脱身。\n\n"
              f"## 线动作\n\n{action_note}- skip GUN-{n:03d}\n\n"
              f"## 验收要点\n\n- 本章必须出现一次主角的算账动作与一次灯下场景。\n")
        (vol / "beats" / f"{ch}.md").write_text(fm, encoding="utf-8")
        body = prose_block(2900, seed=f"第{n}章", hero="陆沉舟")
        title = f"第{n}章 灯下{n}"
        (raw / f"{ch}_v1.md").write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        (fin / f"{ch}.md").write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    print("phase1 scaffold ok")

    # ---------------- phase 2: orchestrated syncs ----------------
    p1 = prop(1, "seed", entities=ENTITIES, current={
        "time": "第一日", "location": "临安城", "situation": "赵七星死于瓮城，主角开始查账。",
        "present_characters": ACTIVE_PRESENT},
        ledger={"pools": {"silver": {"name": "现银", "unit": "两", "initial": 50},
                          "copper": {"name": "铜钱", "unit": "文", "initial": 200}}},
        lines=[{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                "name": "灯司黑账", "plant_ch": 1, "target_ch": 20, "weight": 3,
                "plan": "查清主簿经手的黑账"},
               {"kind": "foreshadow", "action": "plant", "id": "GUN-003",
                "name": "换过的灯芯", "plant_ch": 1, "target_ch": 6, "weight": 2,
                "plan": "确认雨夜灯芯被换的线头"},
               {"kind": "knowledge", "action": "plant", "id": "KNO-001",
                "secret": "黑煞宗暗藏七星古镜", "plant_ch": 1, "target_ch": 14,
                "weight": 2, "holders": ["陆沉舟"]},
               {"kind": "misunderstanding", "action": "plant", "id": "MIS-001",
                "parties": "李捕头与陆沉舟", "content": "李捕头认定赵七星死于盗匪",
                "truth": "实为灯司内鬼灭口", "level": 2, "target_ch": 16},
               {"kind": "foreshadow", "action": "plant", "id": "GUN-901",
                "name": "娘留下的灯谱", "plant_ch": 1, "target_ch": "longline",
                "weight": 2, "plan": "长线：灯谱与无籍之灯的秘密"}],
        timeline={"events": [{"time": "第一日", "event": "巡灯使赵七星在城南瓮城被杀"}],
                  "milestones": [{"id": "MS-001", "title": "查清灯司黑账", "target_ch": 20},
                                 {"id": "MS-002", "title": "追回七星古镜", "target_ch": 26}],
                  "clocks": [{"name": "城门换防", "target_ch": 10, "urgency": "high",
                              "desc": "换防后密匣难以运出城"}]},
        locked=[{"id": "LOCK-001", "fact": "赵七星于第一日死于城南瓮城",
                 "kind": "death", "since_ch": "ch_001", "quote": "巡灯使倒在灯楼下"},
                {"id": "LOCK-002", "fact": "瓮城灯楼在命案当夜被焚毁",
                 "kind": "irreversible_action", "since_ch": "ch_001",
                 "quote": "火光照亮半条街"}],
        synopsis={"title": "第1章 灯下1", "text": "第一章：陆沉舟夜闻赵七星死于瓮城。"},
        cognition_delta=[{"character": "陆沉舟", "learned": "赵七星死前换过灯芯"}])
    sync_inbox(1, p1)

    p2 = prop(2, "a", current={"time": "第二日", "situation": "主角去苏记茶楼打探。",
                               "present_characters": ["陆沉舟", "苏九娘", "赵六"]},
              entities=[{"name": "苏九娘", "summary": "茶楼掌柜，消息灵通，与灯司有旧"},
                        {"name": "陆沉舟", "location": "苏记茶楼"}],
              ledger={"transactions": [tx(2, -5, "茶资", note="苏记茶楼")]},
              timeline={"events": [{"time": "第二日", "event": "陆沉舟在苏记茶楼打探消息"}]},
              synopsis={"title": "第2章 灯下2", "text": "第二章：茶楼探听，得知密匣线索。"})
    sync_inbox(2, p2)

    p3 = prop(3, "a", current={"time": "第三日", "situation": "主角夜里摸到主簿宅外。",
                               "present_characters": ["陆沉舟", "密匣", "照夜灯"]},
              lines=[{"kind": "foreshadow", "action": "plant", "id": "GUN-002",
                      "name": "古镜的出处", "plant_ch": 3, "target_ch": 12, "weight": 2,
                      "plan": "古镜从主簿宅流向黑煞宗的路径", "requires": ["GUN-003"]}],
              ledger={"transactions": [tx(3, 12, "卖旧灯油", type_="income")]},
              timeline={"events": [{"time": "第三日", "event": "陆沉舟夜探主簿宅"}]},
              synopsis={"title": "第3章 灯下3", "text": "第三章：夜探主簿宅，发现古镜。"})
    sync_inbox(3, p3)

    # ordinary chapters 4..5 (+ch4 misresolved knowledge guard sanity: nothing)
    for n in (4, 5):
        p = prop(n, "a", current={"time": f"第{('一二三四五六七八九十')[n-1]}日",
                                  "situation": "主角继续盯梢。",
                                  "present_characters": ["陆沉舟", "赵六", "李捕头"]},
                 ledger={"transactions": [tx(n, -3, "饭钱"), tx(n, 8, "代写书信",
                                                               type_="income")]},
                 timeline={"events": [{"time": f"第{('一二三四五六七八九十')[n-1]}日",
                                       "event": f"陆沉舟在临安城继续查访（第{n}日）"}]},
                 synopsis={"title": f"第{n}章 灯下{n}", "text": f"第{n}章：查访推进。"})
        sync_inbox(n, p)

    p6 = prop(6, "a", current={"time": "第六日", "situation": "灯芯线头确认。",
                               "present_characters": ["陆沉舟", "苏九娘"]},
              lines=[{"kind": "foreshadow", "action": "resolve", "id": "GUN-003"}],
              ledger={"transactions": [tx(6, -20, "封口费", note="给更夫")]},
              timeline={"events": [{"time": "第六日", "event": "确认雨夜灯芯被换"}]},
              synopsis={"title": "第6章 灯下6", "text": "第六章：灯芯线头闭环。"})
    sync_inbox(6, p6)

    p7 = prop(7, "a", current={"time": "第七日", "situation": "主簿盯上主角。",
                               "present_characters": ["陆沉舟", "灯司主簿", "照夜灯"]},
              lines=[{"kind": "misunderstanding", "action": "plant", "id": "MIS-002",
                      "parties": "灯司主簿与陆沉舟", "content": "主簿怀疑陆沉舟偷了古镜",
                      "truth": "古镜在黑煞宗手里", "level": 1, "target_ch": 24}],
              ledger={"transactions": [tx(7, -30, "买通门房", note="主簿宅")]},
              timeline={"events": [{"time": "第七日", "event": "主簿开始怀疑陆沉舟"}]},
              synopsis={"title": "第7章 灯下7", "text": "第七章：被主簿盯上。"})
    sync_inbox(7, p7)

    p8 = prop(8, "a", current={"time": "第八日", "situation": "主角托九娘传话。",
                               "present_characters": ["陆沉舟", "苏九娘", "密匣"]},
              cognition_delta=[{"character": "赵六", "learned": "陆沉舟在查灯司的账"}],
              ledger={"transactions": [tx(8, -2, "茶点")]},
              timeline={"events": [{"time": "第八日", "event": "主角托苏九娘传话"}]},
              synopsis={"title": "第8章 灯下8", "text": "第八章：布局。"})
    sync_inbox(8, p8)

    p9 = prop(9, "a", current={"time": "第九日", "situation": "误会升级。",
                               "present_characters": ["陆沉舟", "李捕头", "赵六"]},
              lines=[{"kind": "misunderstanding", "action": "escalate", "id": "MIS-001",
                      "level": 3}],
              ledger={"transactions": [tx(9, -10, "买药")]},
              timeline={"events": [{"time": "第九日", "event": "李捕头与陆沉舟冲突升级"}]},
              synopsis={"title": "第9章 灯下9", "text": "第九章：冲突升级。"})
    sync_inbox(9, p9)

    p10 = prop(10, "a", current={"time": "第十日", "situation": "城门换防在即。",
                                 "present_characters": ["陆沉舟", "密匣"]},
               lines=[{"kind": "foreshadow", "action": "remind", "id": "GUN-001"}],
               ledger={"transactions": [tx(10, -15, "雇驴")]},
               timeline={"events": [{"time": "第十日", "event": "城门换防前夕"}]},
               synopsis={"title": "第10章 灯下10", "text": "第十章：换防前夜。"})
    sync_inbox(10, p10)

    for n in (11, 12):
        lines = []
        if n == 12:
            lines.append({"kind": "foreshadow", "action": "resolve", "id": "GUN-002"})
        p = prop(n, "a", current={"time": f"第十{('一二')[n-11]}日",
                                  "situation": "追踪古镜下落。",
                                  "present_characters": ["陆沉舟", "赵六"]},
                 lines=lines,
                 ledger={"transactions": [tx(n, -4, "盘缠")]},
                 timeline={"events": [{"time": f"第十{('一二')[n-11]}日",
                                       "event": f"古镜线索推进（第{n}章）"}]},
                 synopsis={"title": f"第{n}章 灯下{n}", "text": f"第{n}章：追踪。"})
        sync_inbox(n, p)

    for n in (13, 14):
        lines = []
        if n == 14:
            lines.append({"kind": "knowledge", "action": "resolve", "id": "KNO-001"})
        p = prop(n, "a", current={"time": f"第十{('三四')[n-13]}日",
                                  "situation": "接近黑煞宗。",
                                  "present_characters": ["陆沉舟", "李捕头", "照夜灯"]},
                 lines=lines,
                 ledger={"transactions": [tx(n, -25, "买线人消息")]},
                 timeline={"events": [{"time": f"第十{('三四')[n-13]}日",
                                       "event": f"黑煞宗线索（第{n}章）"}]},
                 synopsis={"title": f"第{n}章 灯下{n}", "text": f"第{n}章：接触黑煞宗。"})
        sync_inbox(n, p)

    for n in (15, 16):
        lines = []
        if n == 16:
            lines.append({"kind": "misunderstanding", "action": "resolve", "id": "MIS-001"})
        p = prop(n, "a", current={"time": f"第十{('五六')[n-15]}日",
                                  "situation": "瓮城真相近在眼前。",
                                  "present_characters": ["陆沉舟", "苏九娘", "灯司主簿"]},
                 lines=lines,
                 ledger={"transactions": [tx(n, -6, "酒钱")]},
                 timeline={"events": [{"time": f"第十{('五六')[n-15]}日",
                                       "event": f"真相逼近（第{n}章）"}]},
                 synopsis={"title": f"第{n}章 灯下{n}", "text": f"第{n}章：真相逼近。"})
        sync_inbox(n, p)

    for n in (17, 18, 19, 20):
        lines, ents = [], []
        if n == 18:
            ents = [{"name": "七星古镜", "charges": 3}]
        if n == 20:
            lines.append({"kind": "foreshadow", "action": "resolve", "id": "GUN-001"})
        p = prop(n, "a", current={"time": f"第十{('七八九十')[n-17]}日",
                                  "situation": "收网阶段。",
                                  "present_characters": ["陆沉舟", "李捕头", "赵六", "密匣"]},
                 lines=lines, entities=ents,
                 ledger={"transactions": [tx(n, -8, "杂用"), tx(n, 5, "卖旧书",
                                                               type_="income")]},
                 timeline={"events": [{"time": f"第十{('七八九十')[n-17]}日",
                                       "event": f"收网推进（第{n}章）"}]},
                 synopsis={"title": f"第{n}章 灯下{n}", "text": f"第{n}章：收网。"})
        sync_inbox(n, p)

    for n in (21, 22):
        lines = []
        if n == 21:
            lines.append({"kind": "knowledge", "action": "plant", "id": "KNO-002",
                          "secret": "黑煞宗买通灯司内应", "plant_ch": 21,
                          "target_ch": 25, "weight": 2, "holders": ["陆沉舟"]})
        p = prop(n, "a", current={"time": f"第二{('一二')[n-21]}日",
                                  "situation": "黑煞宗反扑。",
                                  "present_characters": ["陆沉舟", "苏九娘"]},
                 lines=lines,
                 ledger={"transactions": [tx(n, -12, "雇人看店")]},
                 timeline={"events": [{"time": f"第二{('一二')[n-21]}日",
                                       "event": f"黑煞宗反扑（第{n}章）"}]},
                 synopsis={"title": f"第{n}章 灯下{n}", "text": f"第{n}章：反扑。"})
        sync_inbox(n, p)

    for n in (23, 24, 25):
        lines = []
        if n == 24:
            lines.append({"kind": "misunderstanding", "action": "resolve", "id": "MIS-002"})
        if n == 25:
            lines.append({"kind": "knowledge", "action": "resolve", "id": "KNO-002"})
        p = prop(n, "a", current={"time": f"第二{('三四五')[n-23]}日",
                                  "situation": "决战前夜。",
                                  "present_characters": ["陆沉舟", "李捕头", "灯司主簿"]},
                 lines=lines,
                 ledger={"transactions": [tx(n, -18, "备械")]},
                 timeline={"events": [{"time": f"第二{('三四五')[n-23]}日",
                                       "event": f"决战前夜（第{n}章）"}]},
                 synopsis={"title": f"第{n}章 灯下{n}", "text": f"第{n}章：决战前夜。"})
        sync_inbox(n, p)

    p26 = prop(26, "a", current={"time": "第二十六日", "situation": "黑账大白，真凶伏法。",
                                 "present_characters": ["陆沉舟", "苏九娘", "赵六", "李捕头"]},
               entities=[{"name": "临安灯司", "summary": "黑账清算后重建"},
                         {"name": "灯司主簿", "status": "retired",
                          "summary": "真凶下狱", "life_status": "alive"}],
               timeline={"events": [{"time": "第二十六日",
                                     "event": "灯司黑账大白，主簿下狱"}],
                         "milestones": [{"id": "MS-001", "title": "查清灯司黑账",
                                         "status": "achieved",
                                         "achieved_ch": "ch_026"}]},
               ledger={"transactions": [tx(26, 40, "查案赏银", type_="income")]},
               synopsis={"title": "第26章 灯下26", "text": "终章：黑账大白。"},
               cognition_delta=[{"character": "赵六", "learned": "主簿才是内鬼"}])
    sync_inbox(26, p26)

    r = run_cli("check", "-w", str(BOOK), "--json")
    d = json.loads(r.stdout)
    print(f"\ncheck: errors={d['stats']['errors']} warnings={d['stats']['warnings']} "
          f"infos={d['stats']['infos']}")
    if d["stats"]["errors"]:
        for e in d["errors"]:
            print("E:", e["code"], e["msg"][:150])
        sys.exit(2)
    print("PB-BOOK-READY")


if __name__ == "__main__":
    main()
