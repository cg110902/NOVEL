#!/usr/bin/env python3
"""
生成 ch_021-030，延续 ch_001-020 的线，测试更多配额、时钟、里程碑、长线等
"""
import json, pathlib, random

book = pathlib.Path("workspace/长夜余烬")
manuscript_final = book / "manuscript" / "vol_01" / "final"
manuscript_raw = book / "manuscript" / "vol_01" / "raw"
beats_dir = book / "outlines" / "vol_01" / "beats"
inbox = book / "state" / "inbox"
audit_dir = book / "log" / "audit"

# 线定义延续
line_defs = [
    {"id": f"GUN-{i:03d}", "name": f"伏笔{i}", "target": 30 + (i % 10), "weight": 2 + (i % 3)}
    for i in range(16, 31)
]
line_defs += [
    {"id": "MIS-004", "name": "苏见微误会陈默隐瞒", "target": 25, "parties": "陈默、苏见微", "content": "苏见微误会陈默隐瞒芯片真相"},
    {"id": "MIS-005", "name": "老秦误会陈默放弃旧城", "target": 28, "parties": "陈默、老秦", "content": "老秦误会陈默放弃旧城自保"},
    {"id": "KNO-006", "name": "档案馆是活的", "target": 30, "secret": "档案馆本身是活的记忆体"},
    {"id": "KNO-007", "name": "余烬瓶是钥匙", "target": 30, "secret": "余烬瓶是打开深渊最深处的钥匙"},
]

chapters_outline = [
    (21, "档案馆活了", "危机逼近", 7, "档案馆异动 | 墙皮蠕动 | 恐惧 | 动作收束", "档案馆墙皮蠕动，像活的，GUN-016初现"),
    (22, "自保会分裂", "暗流汇聚", 6, "自保会内讧 | 人情 | 分裂 | 动作收束", "自保会因拆迁款分裂，老秦被质疑，MIS-004"),
    (23, "林深的底牌", "心理对弈", 7, "林深底牌 | 星图生物 | 芯片 | 动作收束", "林深展示星图生物底牌，芯片可备份全城，GUN-017"),
    (24, "二次断电", "生死博弈", 8, "断电 | 深渊开启 | 记忆溢出 | 动作收束", "档案馆二次断电，深渊开启，记忆溢出，GUN-018"),
    (25, "余烬瓶钥匙", "真相揭露", 7, "余烬瓶 | 钥匙 | 深渊最深处 | 动作收束", "揭示余烬瓶是钥匙，KNO-007"),
    (26, "全城记忆", "暗流汇聚", 6, "全城记忆 | 备份 | 伦理 | 动作收束", "全城记忆备份真相，GUN-019/020"),
    (27, "老秦的选择", "情感冲击", 6, "老秦 | 选择 | 旧城 | 动作收束", "老秦选择留下守旧城，MIS-005"),
    (28, "守门人最后", "战后清点", 5, "守门人 | 告别 | 半本书 | 动作收束", "守门人最后告别，给完整地图，GUN-021"),
    (29, "灯亮之前最暗", "生死博弈", 9, "最暗时刻 | 灯灭 | 深渊 | 动作收束", "灯灭前最暗，深渊最深处开启，GUN-022-025"),
    (30, "长夜将尽", "战后清点", 4, "收尾 | 清点 | 新开始 | 动作收束", "卷二收尾，长夜将尽，灯亮，GUN-015闭环"),
]

def make_final(num, title, goal, line_ids):
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
    text += f"本章核心：{goal}。\n\n线索：" + "、".join(line_ids[:5]) + "。\n\n"
    filler = "陈默摩挲指腹薄茧，风铃响，没风，自己响。桌上四样齐了，笔记、日志、钥匙、地图。墙里嗡嗡声，停了。门外挖机灯扫进来，余烬瓶亮着，像灯。\n\n"
    while len(text) < 1300:
        text += filler
    must = ["余烬瓶雾气自己动", "档案馆灯不能关", "师父笔记后半本被撕", "值班日志最后一页", "地下二层钥匙", "妹妹芯片三天记忆"]
    for term in must:
        if term not in text:
            text += term + "。\n"
    return text[:2500]

def write_beats(num, form, tension, style, goal, acts):
    tok = f"ch_{num:03d}"
    path = beats_dir / f"{tok}.md"
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
- **所属阶段**：卷二 深渊
- **本章核心戏剧目标**：{goal}

## 场景脉络
### 场景一
- 支点：{goal}
- 锚点：余烬瓶，档案馆

## 伏笔与线索动作
"""
    for a in acts:
        content += f"- {a}\n"
    content += """
## 本章法定事实与称谓对校清单
- 【陈默 -> 苏见微】「苏探员」
- 【苏见微 -> 陈默】「陈老板」
- 档案馆灯不能关，余烬瓶雾气自己动

## 一致性速查
### 💰 资源池
- favor 9份

### 🔒 不可逆事实
- [LOCK-001] 七年前断电

### 实体名册
- [p_001] 陈默
- [p_002] 苏见微

## 交付契约
- **核心看点**：{goal}
"""
    path.write_text(content, encoding="utf-8")

def write_proposal(num, acts):
    tok = f"ch_{num:03d}"
    op_id = f"{tok}.reader.manual.{num:03d}"
    ops = []
    ops.append({"table": "current", "action": "update", "set": {
        "time": f"2026年9月{10+num}日",
        "location": "档案馆" if num % 2 == 0 else "余烬书屋",
        "situation": f"第{num}章推进",
        "goal": "深渊最深处",
        "present_characters": ["陈默", "苏见微", "老秦"],
        "present_refs": ["陈默", "苏见微", "老秦"],
        "pov_ref": "陈默",
        "place_ref": "档案馆" if num % 2 == 0 else "余烬书屋",
        "mood": "紧张",
        "active_pressures": ["档案馆活了", "深渊开启", "全城备份"],
        "aftershock": f"第{num}章余波"
    }})
    ops.append({"table": "synopsis", "action": "set", "title": f"第{num}章", "text": f"第{num}章推进"})
    # lines
    for act in acts:
        parts = act.split()
        if len(parts) < 2:
            continue
        action, lid = parts[0], parts[1]
        ld = next((x for x in line_defs if x["id"] == lid), None)
        # also check previous defs from gen_v2
        if not ld:
            # try generic
            if lid.startswith("GUN-"):
                ld = {"id": lid, "name": f"伏笔{lid}", "target": 35, "weight": 2}
            elif lid.startswith("MIS-"):
                ld = {"id": lid, "name": f"误会{lid}", "target": 30, "parties": "陈默、苏见微", "content": f"{lid}内容"}
            elif lid.startswith("KNO-"):
                ld = {"id": lid, "name": f"秘密{lid}", "target": 35, "secret": f"{lid}秘密", "weight": 2}
        if not ld:
            continue
        kind = "foreshadow" if lid.startswith("GUN-") else ("misunderstanding" if lid.startswith("MIS-") else "knowledge")
        op = {"table": "lines", "action": action, "kind": kind, "id": lid}
        if action == "plant":
            if kind == "foreshadow":
                op["name"] = ld.get("name", lid)
                op["plant_ch"] = num
                op["target_ch"] = ld.get("target", 35)
                op["weight"] = ld.get("weight", 2)
                op["plan"] = f"{ld.get('name', lid)}计划"
            elif kind == "misunderstanding":
                op["parties"] = ld.get("parties", "陈默、苏见微")
                op["content"] = ld.get("content", ld.get("name", lid))
                op["target_ch"] = ld.get("target", 30)
            elif kind == "knowledge":
                op["secret"] = ld.get("secret", ld.get("name", lid))
                op["plant_ch"] = num
                op["target_ch"] = ld.get("target", 35)
                op["weight"] = ld.get("weight", 2)
        ops.append(op)
    # timeline event
    ops.append({"table": "timeline", "action": "append_event", "event": {
        "time": f"2026年9月{10+num}日",
        "event": f"第{num}章事件",
        "participants": ["陈默", "苏见微"],
        "place": "档案馆",
        "causes": [], "consequences": []
    }})
    # ledger
    ops.append({"table": "ledger", "action": "append_transaction", "entry": {
        "chapter": tok,
        "pool": "standard_currency",
        "delta": -5,
        "type": "expense",
        "subject": f"第{num}章花费"
    }})
    # locked every 2 - kind must be in allowed set
    if num % 2 == 1:
        ops.append({"table": "locked", "action": "plant", "id": f"LOCK-{num:03d}", "fact": f"第{num}章事实：陈默在档案馆", "kind": "rule", "note": "不可逆，严禁再次出场", "quote": "灯不能关"})
    # cognition
    if num % 3 == 0:
        ops.append({"table": "cognition", "action": "plant", "character": "陈默", "content": f"第{num}章认知", "kind": "fact", "truth_ref": "GUN-009", "quote": "深渊", "since_ch": f"ch_{num:03d}"})
    # clocks test: add a clock every 5 chapters - correct fields: name, target_ch, urgency, status
    if num % 5 == 0:
        ops.append({"table": "timeline", "action": "append_clock", "clock": {
            "name": f"危机时钟{num}",
            "target_ch": num + 5,
            "urgency": "high",
            "status": "Active"
        }})
    # milestone - correct fields: title, target_ch, status
    if num == 25:
        ops.append({"table": "timeline", "action": "append_milestone", "milestone": {
            "id": "MS-003",
            "title": "进入深渊最深处",
            "target_ch": 30,
            "status": "pending"
        }})

    proposal = {"schema": "novel-studio.state-mutation/v3", "chapter": tok, "operation_id": op_id, "ops": ops}
    (inbox / f"{tok}.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"proposal {tok} {len(ops)} ops")

def write_final(num, title, goal, line_ids):
    tok = f"ch_{num:03d}"
    text = make_final(num, title, goal, line_ids)
    (manuscript_final / f"{tok}.md").write_text(text, encoding="utf-8")
    (manuscript_raw / f"{tok}_v1.md").write_text(text, encoding="utf-8")
    (manuscript_raw / f"{tok}_v2.md").write_text(text, encoding="utf-8")

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
    if num == 21:
        acts = ["plant GUN-016", "remind GUN-009", "remind GUN-015"]
    elif num == 22:
        acts = ["plant MIS-004", "remind GUN-013", "remind GUN-016"]
    elif num == 23:
        acts = ["plant GUN-017", "remind GUN-013", "remind GUN-004"]
    elif num == 24:
        acts = ["plant GUN-018", "remind GUN-002", "remind GUN-014"]
    elif num == 25:
        acts = ["plant KNO-006", "plant KNO-007", "remind GUN-015", "resolve GUN-012"]
    elif num == 26:
        acts = ["plant GUN-019", "plant GUN-020", "remind GUN-015"]
    elif num == 27:
        acts = ["plant MIS-005", "remind GUN-001", "remind GUN-002"]
    elif num == 28:
        acts = ["plant GUN-021", "remind GUN-009", "remind GUN-011"]
    elif num == 29:
        acts = ["plant GUN-022", "plant GUN-023", "plant GUN-024", "plant GUN-025", "remind GUN-015"]
    elif num == 30:
        acts = ["resolve GUN-015", "remind GUN-010", "resolve MIS-004", "resolve MIS-005"]
    else:
        acts = ["remind GUN-001"]
    line_ids = [a.split()[1] for a in acts]
    write_beats(num, form, tension, style, goal, acts)
    write_final(num, title, goal, line_ids)
    write_proposal(num, acts)
    write_audit(num)

print("ch21-30 generated")
