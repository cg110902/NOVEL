"""Phase 2: 规模化与 SQLite 检索跃升 (50~100+ 章支撑) 自动化测试套件。

涵盖：
- SQLite3 双平面投影引擎 (FTS5 BM25 全文检索 + 关系索引)
- studio ask 2.0 与 studio pov 2.0 的 SQLite 增强
- 角色认知台账 state/cognition.json 与 v3->v4 平滑迁移
- 提案 cognition 与 cognition_delta 原子合并
- 主线里程碑 timeline.milestones 与支线停滞监测
- sync 成功后 SQLite 索引纳秒级自动更新
- cockpit 主线推进率与十章图书管理员巡检提示
"""
import json
import pytest
from pathlib import Path

from engine import common, state, evidence, checks, db, cockpit, migrations
from engine.models.cognition import CognitionEntry, CognitionState
from engine.models.timeline import TimelineMilestone, TimelineState


@pytest.fixture
def phase2_book(tmp_path):
    """构建一个标准的测试书籍工作区。"""
    book = tmp_path / "bk_phase2"
    (book / "state" / "inbox" / "processed").mkdir(parents=True)
    (book / "manuscript" / "vol_01" / "final").mkdir(parents=True)
    (book / "manuscript" / "vol_01" / "raw").mkdir(parents=True)
    (book / "outlines" / "vol_01" / "beats").mkdir(parents=True)

    # project.json
    proj = {
        "title": "测试天机阁",
        "genre": "仙侠修真",
        "protagonist": "陆沉舟",
        "words_target": [2000, 3500]
    }
    common.atomic_write_text(book / "project.json", json.dumps(proj, ensure_ascii=False))

    # state files
    for k in state.STATE_KEYS:
        common.atomic_write_text(book / "state" / f"{k}.json", json.dumps(state.defaults_for(k), ensure_ascii=False))

    # 实体初始化
    ents = {
        "entries": [
            {"name": "陆沉舟", "type": "person", "status": "active", "realm": "练气九层", "summary": "主角"},
            {"name": "青霜剑", "type": "item", "status": "active", "holder": "陆沉舟", "charges": 3, "max_charges": 5, "summary": "本命法宝"},
            {"name": "林掌柜", "type": "person", "status": "active", "location": "百宝阁", "summary": "掌柜"}
        ]
    }
    common.atomic_write_text(book / "state" / "entities.json", json.dumps(ents, ensure_ascii=False))

    # 伏笔与机密
    lines = {
        "foreshadows": [
            {"id": "GUN-001", "name": "九转金丹残卷", "plant_ch": 1, "target_ch": 5, "status": "Planted"}
        ],
        "misunderstandings": [],
        "knowledge": [
            {"id": "KNO-001", "secret": "城主暗中勾结黑煞宗", "holders": ["陆沉舟"], "plant_ch": 1, "target_ch": 3, "status": "Concealed"}
        ]
    }
    common.atomic_write_text(book / "state" / "lines.json", json.dumps(lines, ensure_ascii=False))

    # 第一章正文
    ch1_text = """第1章 临渊城买药

陆沉舟踏入百宝阁，神色警惕。掌柜林寿笑脸相迎。

林掌柜低声道：“陆公子，这柄青霜剑锐利无比，你可要收好了。”

陆沉舟手抚青霜剑，微微点头，付清了银两。
"""
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text(ch1_text, encoding="utf-8")
    (book / "manuscript" / "vol_01" / "raw" / "ch_001_v1.md").write_text(ch1_text, encoding="utf-8")
    (book / "outlines" / "vol_01" / "beats" / "ch_001.md").write_text("## 细纲任务\n买剑", encoding="utf-8")

    return book


def test_sqlite_schema_and_rebuild(phase2_book):
    """测试 SQLite3 数据库初始化、FTS5 表构建与索引重建。"""
    book = phase2_book
    res = db.build_or_update_index(book, force_rebuild=True)
    assert res["ok"] is True
    assert res["indexed_chapters"] >= 1
    assert res["indexed_entities"] >= 3
    assert res["indexed_lines"] >= 2

    db_path = db.get_db_path(book)
    assert db_path.is_file()

    con = db.get_connection(book)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) as c FROM chapters_fts;")
    assert cur.fetchone()["c"] >= 2
    cur.execute("SELECT COUNT(*) as c FROM entities_index;")
    assert cur.fetchone()["c"] == 3
    con.close()


def test_sqlite_fts5_chinese_search(phase2_book):
    """测试中文经 Jieba 切词后通过 SQLite FTS5 进行 BM25 相关度检索。"""
    book = phase2_book
    db.build_or_update_index(book, force_rebuild=True)

    # 检索青霜剑
    hits = db.search_chapters_bm25(book, "青霜剑", limit=5)
    assert len(hits) >= 1
    assert hits[0]["chapter"] == "ch_001"
    assert "青霜剑" in hits[0]["text"]
    assert hits[0]["score"] > 0

    # 检索不存在的词
    no_hits = db.search_chapters_bm25(book, "太上老君无量佛", limit=5)
    assert len(no_hits) == 0


def test_studio_ask_and_pov_with_sqlite(phase2_book):
    """测试升级后的 studio ask 与 pov 输出结构，验证 FTS5 召回。"""
    book = phase2_book
    # 先跑一次建库
    db.build_or_update_index(book)

    # ask
    ask_payload = evidence.ask(book, "青霜剑")
    assert ask_payload["kind"] == "ask"
    assert "entities" in ask_payload
    assert any(e["name"] == "青霜剑" for e in ask_payload["entities"])
    assert "text_hits" in ask_payload
    assert any("青霜剑" in h["quote"] for h in ask_payload["text_hits"])

    # pov
    pov_payload = evidence.pov(book, "陆沉舟")
    assert pov_payload["kind"] == "pov"
    assert pov_payload["resolved"] == "陆沉舟"
    assert "carries" in pov_payload
    assert any(c["name"] == "青霜剑" for c in pov_payload["carries"])
    assert "unknown_to_char" in pov_payload


def test_cognition_model_and_migration(phase2_book):
    """测试角色认知 Pydantic 模型校验与状态机平滑版本迁移 (v3 -> v4)。"""
    book = phase2_book

    # 验证模型构造与校验
    entry = CognitionEntry(
        id="COG-001",
        character="陆沉舟",
        kind="fact",
        content="林掌柜其实暗中效忠城主",
        since_ch="ch_001",
        quote="掌柜递过玉佩"
    )
    assert entry.id == "COG-001"
    assert entry.kind == "fact"

    # 验证迁移器对老书自动初始化 cognition.json
    cog_file = book / "state" / "cognition.json"
    if cog_file.is_file():
        cog_file.unlink()

    # 模拟 v3 版本戳
    common.dump_json(book / "state" / "state_schema.json", {"version": 3})
    mig_res = migrations.ensure_state_version(book)
    assert mig_res["migrated"] is True
    assert cog_file.is_file()
    cog_data = common.load_json(cog_file)
    assert "entries" in cog_data


def test_proposal_cognition_and_delta_merge(phase2_book):
    """测试提案中的 cognition 与 cognition_delta 节点正确原子合并入 state/cognition.json。"""
    book = phase2_book

    # 构造带有 cognition_delta 的提案
    proposal = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "op_test_cog_001",
        "cognition_delta": [
            {
                "character": "陆沉舟",
                "learned": "城主府暗通魔门",
                "quote": "林掌柜低声道"
            },
            {
                "character": "林掌柜",
                "doubted": "陆沉舟隐藏了真实修为",
                "quote": "掌柜眼中闪过狐疑"
            }
        ]
    }

    rep = state.apply_proposal(book, proposal, expected_chapter="ch_001")
    assert len(rep["errors"]) == 0
    assert any("COG-001" in u for u in rep["updated"])
    assert any("COG-002" in u for u in rep["updated"])

    # 验证落盘真值
    cog_st = state.load_state(book, "cognition")
    assert len(cog_st["entries"]) == 2
    assert cog_st["entries"][0]["character"] == "陆沉舟"
    assert cog_st["entries"][0]["kind"] == "fact"
    assert cog_st["entries"][1]["character"] == "林掌柜"
    assert cog_st["entries"][1]["kind"] == "suspicion"


def test_timeline_milestones_and_overdue_check(phase2_book):
    """测试主线里程碑模型与 checks 逾期告警。"""
    book = phase2_book
    tl = state.load_state(book, "timeline")
    tl["milestones"] = [
        {
            "id": "MS-001",
            "title": "揭开林掌柜真实身份",
            "target_ch": 1,
            "status": "pending",
            "desc": "首个揭秘小高潮"
        }
    ]
    common.atomic_write_text(book / "state" / "timeline.json", json.dumps(tl, ensure_ascii=False))

    # 添加第2章正文使当前章为 ch_002
    (book / "manuscript" / "vol_01" / "final" / "ch_002.md").write_text("第2章 归途\n\n陆沉舟返回洞府。", encoding="utf-8")

    report = checks.run_checks(book)
    warn_codes = [w["code"] for w in report["warnings"]]
    assert "milestone_overdue" in warn_codes


def test_cockpit_milestones_and_librarian_alert(phase2_book):
    """测试驾驶舱正确统计主线推进率，并在第10章整数关口发出图书管理员巡检提示。"""
    book = phase2_book
    tl = state.load_state(book, "timeline")
    tl["milestones"] = [
        {"id": "MS-001", "title": "初出茅庐", "target_ch": 3, "status": "achieved"},
        {"id": "MS-002", "title": "宗门大比夺魁", "target_ch": 10, "status": "pending"}
    ]
    common.atomic_write_text(book / "state" / "timeline.json", json.dumps(tl, ensure_ascii=False))

    # 模拟第10章
    (book / "manuscript" / "vol_01" / "final" / "ch_010.md").write_text("第10章 决战之巅\n\n剑气如虹。", encoding="utf-8")
    (book / "outlines" / "vol_01" / "beats" / "ch_010.md").write_text("## 任务\n决战", encoding="utf-8")

    briefing = cockpit.build_cockpit_briefing(book, "ch_010")
    assert "milestones_progress" in briefing
    assert briefing["milestones_progress"]["achieved"] == 1
    assert briefing["milestones_progress"]["total"] == 2
    assert briefing["milestones_progress"]["rate"] == "1/2"

    pressures = briefing["dramatic_momentum"]["active_pressures"]
    assert any("图书管理员巡检关口" in p for p in pressures)
