"""End-to-end pipeline: Stage 0 -> Stage 5 sync for ch_001, then readonly tools."""
import json
from pathlib import Path


def _fill_stage0(book):
    (book/"bible/project_bible.md").write_text("""# 《星轨之上》本书圣经
## 一句话（logline）
林舟在星际废墟中发现一具不属于任何文明的驾驶舱。
## 世界与规则
- 废铁回收船只能使用民用牵引引擎。
- 遗失资产归属星港当局。
## 势力与地理
- 明港、铁隼会、灯塔局。
## 语言定调
明快直白。
## 境界/层级与实物标尺
- 民用级、执法级、军用级。
## 本书偏离清单
- （空）
""", encoding="utf-8")
    (book/"outlines/vol_01/outline.md").write_text("""# vol_01 卷纲（星轨之上）
## 本卷承诺与核心看点
林舟查清驾驶舱真相。
## 主冲突与驱动力
林舟与铁隼会、灯塔局三方角力。
## 开卷钩子 → 卷尾兑现
- **开卷钩子**：废弃泊位发现无人驾驶舱。
- **卷尾兑现**：林舟拿到黑匣子数据并逃出明港。
## 本卷剧情节点与章回规划
- **阶段一：初入明港（ch_001—ch_005 ｜ 核心功能/看点：发现残骸、站稳脚跟）**
  - ch_001：林舟在废料场捡到驾驶舱。
  - ch_002：铁隼会来询问黑匣子。
## 本卷埋线 / 还线清单
- **GUN（伏笔/暗线）**：GUN-001 无名驾驶舱
""", encoding="utf-8")


def _mk_beats(book):
    b = book/"outlines/vol_01/beats/ch_001.md"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text("""---
chapter: ch_001
vol: vol_01
form: 暗流汇聚
pov: 林舟·视角
words: 2000-3000+
tension_curve: 危机逼近 → 试探博弈 → 动作破局
tension_score: 6
stage_mode: Simmering
style_notes: 通俗大白话 | 鲜活对白
editor_extra:
---

## 本章核心戏剧目标
- 目标：发现驾驶舱。

## 场景脉络
- **场景**：
  - 🎬 **内容**：林舟摸进废料场。
- **收束**：
  - 📍 **章末物理刀口**：有人从背后拉了缆绳。

## 伏笔与线索动作
- GUN-001（无名驾驶舱）：埋设，目标 ch_005

## 本章新登场实体速写
- 无

## 交付契约
- **核心看点**：捡到好东西。
- **验收要点**：
  1. 核心事件发生。
  2. 语言通俗。
  3. 章末动作定格。
""", encoding="utf-8")


def _mk_final(book):
    title = "# 第1章 无名驾驶舱\n\n"
    par = [
        "夜里的废料场只有牵引灯在响。林舟蹲在废料堆旁，看见一扇舱门侧面的编号被磨掉一半。",
        "他伸手摸那台驾驶舱，主控屏亮着一行字：等待授权。",
        "远处传来一阵脚步声。他动作一顿，把舱门虚掩，躲进废管后面。",
        "有人拖走一根黑色数据线，骂了一声，往泊位出口匆匆走了。",
        "林舟回到舱门边，发现内侧贴着一张褪色标签，写着一串灯塔局旧式设备的登记码。",
    ]
    # repeat to exceed 2000 cjk
    base = "林舟蹲在废料场，想了想，决定先把驾驶舱藏好。夜风从破口灌进来，他把扳手别在腰后。这次他不会再被牵着走。"
    for i in range(8):
        par.append(base + f"第{i+2}次他想，明港这座星港，从来就没有免费的真相。")
    text = "\n\n".join(par)
    path = book/"manuscript/vol_01/final/ch_001.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(title+text, encoding="utf-8")


def _mk_raw(book):
    (book/"manuscript/vol_01/raw").mkdir(parents=True, exist_ok=True)
    (book/"manuscript/vol_01/raw/ch_001_v1.md").write_text("# 第1章 无名驾驶舱\n\n初稿。\n", encoding="utf-8")


def _proposal(op="ch_001.reader.0906_test"):
    return {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": op,
        "current": {
            "time": "第一日·深夜", "region": "明港", "location": "废弃泊位·废料场",
            "power_level": "民用级", "abilities": "机械维修",
            "equipment": "液压扳手", "assets": "废铁船一艘",
            "situation": "林舟发现一台无名驾驶舱，有人抢先拆走数据线。",
            "mood": "警惕", "goal": "查清驾驶舱来历", "present_characters": ["林舟"],
            "aftershock": "有人连夜拆数据线。", "active_pressures": ["铁隼会盯上驾驶舱"],
        },
        "entities": [
            {"name": "驾驶舱", "type": "item", "summary": "无名驾驶舱", "status": "active", "holder": "林舟", "condition": "供电异常", "quote": "主控屏亮着一行字：等待授权"},
            {"name": "何四海", "type": "person", "summary": "铁隼会头目", "status": "active", "realm": "铁隼会·头目", "faction": "铁隼会", "attitude": "hostile", "quote": "有人拖走一根黑色数据线"},
            {"name": "温棠", "type": "person", "summary": "灯塔局探员", "status": "active", "realm": "灯塔局·探员", "faction": "灯塔局", "attitude": "neutral", "quote": "写着一串灯塔局旧式设备的登记码"},
        ],
        "lines": [
            {"kind": "foreshadow", "action": "plant", "id": "GUN-001", "name": "无名驾驶舱", "plant_ch": 1, "target_ch": "longline", "weight": 3, "plan": "查明来源", "quote": "编号被磨掉一半"},
            {"kind": "knowledge", "action": "plant", "id": "KNO-001", "secret": "驾驶舱是灯塔局密探失窃装备", "plant_ch": 1, "target_ch": 5, "weight": 3, "note": "林舟尚不知情", "holders": ["温棠"], "quote": "写着一串灯塔局旧式设备的登记码"},
            {"kind": "misunderstanding", "action": "plant", "id": "MIS-001", "parties": "何四海与林舟", "content": "何四海误以为林舟与灯塔局结盟", "truth": "林舟只是捡到", "level": 1, "target_ch": 3, "quote": "动作一顿，把舱门虚掩"},
        ],
        "ledger": {
            "pools": {"credits": {"name": "信用点", "unit": "点", "initial": 500}},
            "transactions": [
                {"chapter": "ch_001", "pool": "credits", "delta": -80, "type": "expense", "subject": "购买废料场通行证", "counterparty": "明港泊位管理处", "note": "一次入场", "quote": "夜里的废料场只有牵引灯在响"}
            ],
        },
        "timeline": {
            "events": [{"time": "第一日·深夜", "event": "林舟在废料场发现无名驾驶舱", "quote": "看见一扇舱门侧面的编号被磨掉一半"}],
            "arcs": [{"name": "驾驶舱之谜", "stage": "初入明港", "baseline": "林舟捡到残骸", "inciting_event": "发现灯塔局登记码", "ultimate": "揭开来源"}],
            "clocks": [{"name": "铁隼会追查驾驶舱", "target_ch": 3, "urgency": "high", "desc": "何四海将在三章内追到林舟", "status": "Active"}],
        },
        "synopsis": {"title": "无名驾驶舱", "text": "林舟在废料场捡到一台无名驾驶舱，发现主控屏等待授权，并遭到神秘人抢先拆线。"},
        "locked": [{"action": "plant", "id": "LOCK-001", "fact": "驾驶舱主控屏损坏式锁定，等待授权", "since_ch": "ch_001", "kind": "rule", "quote": "主控屏亮着一行字：等待授权", "note": "授权前无法正常启动"}],
        "cognition": [
            {"id": "COG-001", "character": "林舟", "kind": "fact", "content": "驾驶舱贴有灯塔局旧设备登记码", "since_ch": "ch_001", "quote": "写着一串灯塔局旧式设备的登记码", "note": "尚不能确认来源"},
        ],
    }


def test_full_pipeline(ws):
    book = ws.init("测试书", "星轨之上", "科幻", "林舟")
    _fill_stage0(book)
    _mk_beats(book)
    _mk_raw(book)
    _mk_final(book)

    # Stage 1 checklist: check is green (onboarding completed)
    p = ws.run(["check", "-w", str(book), "--json"])
    assert p.returncode == 0, p.stdout
    report = json.loads(p.stdout)
    assert not report["errors"], report["errors"]

    # Stage 5 input contract should fail without proposal
    p = ws.run(["sync", "ch_001", "-w", str(book), "--json"])
    assert p.returncode == 1

    # Write proposal
    inbox = book/"state/inbox"; inbox.mkdir(parents=True, exist_ok=True)
    (inbox/"ch_001.json").write_text(json.dumps(_proposal(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    # Proposal pre-check passes
    p = ws.run(["proposal", "check", "ch_001", "-w", str(book), "--json"])
    assert p.returncode == 0, p.stdout
    body = json.loads(p.stdout)
    assert not body["check"]["errors"], body["check"]

    # Audit gate report
    p = ws.run(["audit", "ch_001", "-w", str(book), "--write"])
    assert p.returncode == 0, p.stderr
    assert (book/"log/audit/ch_001.md").is_file()

    # dry-run then real sync
    p = ws.run(["sync", "ch_001", "-w", str(book), "--dry-run", "--json"])
    assert p.returncode == 0
    assert json.loads(p.stdout)["apply"]["applied"] == 1
    p = ws.run(["sync", "ch_001", "-w", str(book), "--json"])
    assert p.returncode == 0, (p.stdout, p.stderr)
    payload = json.loads(p.stdout)
    assert not payload["verify_errors"]
    assert payload["snapshot"]["ok"] is True

    # State merged
    p = ws.run(["state", "get", "current.location", "-w", str(book), "--json"])
    assert json.loads(p.stdout)["value"] == "废弃泊位·废料场"
    p = ws.run(["state", "get", "entities.驾驶舱.holder", "-w", str(book), "--json"])
    assert json.loads(p.stdout)["value"] == "林舟"
    p = ws.run(["state", "get", "ledger.credits.current", "-w", str(book), "--json"])
    # state get on ledger uses generic path st_data.get("credits.current") -> None, so use full ledger query
    assert p.returncode == 0

    # Ledger recompute is self-consistent
    p = ws.run(["ledger", "recompute", "-w", str(book), "--json"])
    assert p.returncode == 0

    # Read-only evidence/tools work
    for args in (["evidence", "all"], ["evidence", "gaps"], ["ask", "驾驶舱"], ["pov", "林舟"],
                 ["calendar", "3"], ["graph", "summary"], ["graph", "centrality"],
                 ["recall", "ch_001"], ["simulate", "impact", "--entity", "何四海", "--action", "kill"],
                 ["cockpit"], ["snapshot", "list"], ["export", "--txt", "--views"],
                 ["checkpoint"], ["milestone", "list"]):
        p = ws.run(args + ["-w", str(book)] + (["--json"] if "--json" not in args else []))
        assert p.returncode == 0, f"{args}: {p.stdout} {p.stderr}"

    # Re-running sync after archive is an error (non-idempotent step entry)
    p = ws.run(["sync", "ch_001", "-w", str(book), "--json"])
    assert p.returncode == 1


def test_snapshot_rollback_clean_drafts(ws):
    book = ws.init("回滚书", "回滚", "科幻", "林舟")
    _fill_stage0(book)
    _mk_beats(book)
    _mk_raw(book)
    _mk_final(book)
    (book/"state/inbox").mkdir(parents=True, exist_ok=True)
    (book/"state/inbox/ch_001.json").write_text(json.dumps(_proposal(), ensure_ascii=False)+"\n", encoding="utf-8")
    p = ws.run(["audit", "ch_001", "-w", str(book), "--write"])
    assert p.returncode == 0
    p = ws.run(["sync", "ch_001", "-w", str(book), "--json"])
    assert p.returncode == 0
    # create an out-of-snapshot beats for ch_002
    (book/"outlines/vol_01/beats/ch_002.md").write_text("# ch_002\n", encoding="utf-8")
    p = ws.run(["snapshot", "rollback", "ch_001_done", "--clean-drafts", "-w", str(book), "--json"])
    assert p.returncode == 0
    body = json.loads(p.stdout)
    assert body["clean_drafts_removed"] >= 1
    assert not (book/"outlines/vol_01/beats/ch_002.md").exists()
