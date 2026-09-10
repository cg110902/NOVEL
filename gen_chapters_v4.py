#!/usr/bin/env python3
"""
Generate ch_031-040 to test quota, milestone overdue, clock overdue, etc.
"""
import json, pathlib, random
book = pathlib.Path("workspace/长夜余烬")
manuscript_final = book / "manuscript" / "vol_01" / "final"
manuscript_raw = book / "manuscript" / "vol_01" / "raw"
beats_dir = book / "outlines" / "vol_01" / "beats"
inbox = book / "state" / "inbox"
audit_dir = book / "log" / "audit"

chapters_outline = [
    (31, "灯塔", "危机逼近", 7, "灯塔 | 余烬瓶 | 指引", "灯塔出现，余烬瓶指引方向"),
    (32, "旧城最后", "暗流汇聚", 6, "旧城 | 最后 | 拆迁", "旧城最后一天，拆迁队来了"),
    (33, "星图生物真面目", "真相揭露", 8, "星图 | 生物 | 真面目", "星图生物真面目揭露，是活的记忆体"),
    (34, "守门人遗产", "战后清点", 5, "遗产 | 地图 | 半本书", "守门人遗产，完整地图和半本书"),
    (35, "深渊最深处", "生死博弈", 9, "深渊 | 最深处 | 备份", "进入深渊最深处，全城备份在那里"),
    (36, "全城记忆之战", "决战爆发", 9, "记忆之战 | 全城 | 备份", "全城记忆之战，备份争夺"),
    (37, "灯灭", "生死博弈", 9, "灯灭 | 最暗 | 绝望", "灯灭，最暗时刻，陈默濒死"),
    (38, "余烬瓶碎", "高潮突破", 8, "余烬瓶 | 碎 | 钥匙", "余烬瓶碎，钥匙出现"),
    (39, "长夜将尽前", "战后清点", 4, "清点 | 战利品 | 情感", "战后清点，情感收束"),
    (40, "灯亮", "战后清点", 3, "灯亮 | 新开始 | 余烬", "灯亮，长夜结束，新开始"),
]

def make_final(num, title, goal):
    base = f"# 第{num}章 {title}\n\n"
    scenes = [
        "余烬瓶雾气自己动，转得快，像是回应档案馆的嗡嗡声。陈默盯着瓶子，瓶子裂纹里有光。",
        "档案馆墙皮烫手，嗡嗡声大，像是活的，墙里有东西在动，苏见微手腕疤发烫。",
        "老秦敲锣，声音大，余烬散了，但墙里声音更大，旧城区自保会的人在门口吵。",
        "林深笑，西装，冷却液蓝的，说星图生物想要全城记忆备份，芯片三天记忆。",
        "深渊守门人站在二楼，手里没书了，对陈默挥手，地图在手里，指向最深处。",
        "全城记忆备份在深渊最深处，备份是活的，会自己动，像余烬瓶雾气。",
    ]
    text = base
    for _ in range(6):
        text += random.choice(scenes) + "\n\n"
    text += f"本章核心：{goal}。\n\n"
    filler = "陈默摩挲指腹薄茧，风铃响，没风，自己响。桌上四样齐了，笔记、日志、钥匙、地图。墙里嗡嗡声，停了。门外挖机灯扫进来，余烬瓶亮着，像灯。\n\n"
    while len(text) < 1300:
        text += filler
    must = ["余烬瓶雾气自己动", "档案馆灯不能关", "师父笔记后半本被撕", "值班日志最后一页", "地下二层钥匙", "妹妹芯片三天记忆"]
    for term in must:
        if term not in text:
            text += term + "。\n"
    return text[:2500]

def write_beats(num, form, tension, style, goal):
    tok = f"ch_{num:03d}"
    path = beats_dir / f"{tok}.md"
    # deliberately make form same for 31-35 to test form_share_over_limit
    # and tension high for 35-37 to test burnout
    if num in (35,36,37):
        form = "生死博弈"
        tension = 9
    elif num in (31,32,33,34,35):
        form = "危机逼近"
    content = f"""---
chapter: {tok}
vol: vol_01
form: {form}
pov: 陈默·视角
words: 1000-3000
tension_curve: 日常 → 异常 → 动作
tension_score: {tension}
stage_mode: Simmering
style_notes: {style}
editor_extra:
---

## 本章坐标与核心戏剧目标
- **所属阶段**：卷三 终局
- **本章核心戏剧目标**：{goal}

## 场景脉络
### 场景一
- 支点：{goal}
- 锚点：余烬瓶，档案馆

## 伏笔与线索动作
- remind GUN-001
- remind GUN-015

## 本章法定事实与称谓对校清单
- 【陈默 -> 苏见微】「苏探员」
- 档案馆灯不能关

## 一致性速查
### 💰 资源池
- standard_currency 钱

### 🔒 不可逆事实
- [LOCK-001] 七年前断电

## 交付契约
- **核心看点**：{goal}
"""
    path.write_text(content, encoding="utf-8")

def write_proposal(num):
    tok = f"ch_{num:03d}"
    op_id = f"{tok}.reader.manual.{num:03d}"
    ops = []
    ops.append({"table": "current", "action": "update", "set": {
        "time": f"2026年9月{10+num}日",
        "location": "档案馆",
        "situation": f"第{num}章推进",
        "goal": "终局",
        "present_characters": ["陈默", "苏见微", "老秦"],
        "present_refs": ["陈默", "苏见微", "老秦"],
        "pov_ref": "陈默",
        "place_ref": "档案馆",
        "mood": "紧张",
        "active_pressures": ["终局", "灯亮", "余烬"],
        "aftershock": f"第{num}章余波"
    }})
    ops.append({"table": "synopsis", "action": "set", "title": f"第{num}章", "text": f"第{num}章推进"})
    ops.append({"table": "timeline", "action": "append_event", "event": {
        "time": f"2026年9月{10+num}日",
        "event": f"第{num}章事件",
        "participants": ["陈默", "苏见微"],
        "place": "档案馆",
        "causes": [], "consequences": []
    }})
    ops.append({"table": "ledger", "action": "append_transaction", "entry": {
        "chapter": tok,
        "pool": "standard_currency",
        "delta": -5,
        "type": "expense",
        "subject": f"第{num}章花费"
    }})
    # every chapter add a locked to exceed quota (15)
    ops.append({"table": "locked", "action": "plant", "id": f"LOCK-{num:03d}", "fact": f"第{num}章不可逆事实：陈默在档案馆", "kind": "rule", "note": f"第{num}章确立不可逆", "quote": "灯不能关", "since_ch": tok})
    # every 2 chapters add a new foreshadow to exceed line quota
    if num % 2 == 1:
        ops.append({"table": "lines", "action": "plant", "kind": "foreshadow", "id": f"GUN-{num:03d}", "name": f"新伏笔{num}", "plant_ch": num, "target_ch": num+10, "weight": 2, "plan": "计划"})
    # milestone overdue: MS-003 target 30 pending, now we are 31+ should trigger overdue
    # clock overdue: create clock target 32, then at 35 it overdue
    if num == 31:
        ops.append({"table": "timeline", "action": "append_clock", "clock": {"name": "旧城拆迁时钟", "target_ch": 32, "urgency": "high", "status": "Active"}})
    proposal = {"schema": "novel-studio.state-mutation/v3", "chapter": tok, "operation_id": op_id, "ops": ops}
    (inbox / f"{tok}.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"proposal {tok} {len(ops)} ops")

def write_final(num, title, goal):
    tok = f"ch_{num:03d}"
    text = make_final(num, title, goal)
    (manuscript_final / f"{tok}.md").write_text(text, encoding="utf-8")
    (book / "manuscript" / "vol_01" / "raw" / f"{tok}_v1.md").write_text(text, encoding="utf-8")
    (book / "manuscript" / "vol_01" / "raw" / f"{tok}_v2.md").write_text(text, encoding="utf-8")

def write_audit(num):
    tok = f"ch_{num:03d}"
    (audit_dir / f"{tok}.md").write_text(f"""---
hard: 0
soft: 0
adjudicated: false
---

# 仲裁报告 {tok}

无矛盾。
""", encoding="utf-8")

for num, title, form, tension, style, goal in chapters_outline:
    write_beats(num, form, tension, style, goal)
    write_final(num, title, goal)
    write_proposal(num)
    write_audit(num)

print("ch31-40 generated")
