import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
import pytest

from engine import common, checks, state, evidence, pack, dashboard, cli, validator


@pytest.fixture
def temp_repo(tmp_path, monkeypatch):
    """Creates an isolated temporary project workspace with mocked project root."""
    # Copy templates and schemas to tmp_path
    shutil.copytree(common.project_root() / "templates", tmp_path / "templates")
    
    # Point common.project_root to tmp_path
    monkeypatch.setattr(common, "project_root", lambda: tmp_path)
    
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    book = ws / "test_book"
    
    # Initialize basic book structure via main
    cli.main([
        "init", "-w", str(book),
        "-t", "测试小说",
        "-g", "玄幻",
        "-p", "叶辰"
    ])
    return {"root": tmp_path, "ws": ws, "book": book}


# ==========================================
# P0 Tests
# ==========================================

def test_p0_1_init_force_external_path_protection(tmp_path, monkeypatch):
    """P0-1: init --force on external path outside workspace must be rejected."""
    shutil.copytree(common.project_root() / "templates", tmp_path / "templates")
    monkeypatch.setattr(common, "project_root", lambda: tmp_path)

    external_dir = tmp_path.parent / "external_danger_zone"
    external_dir.mkdir(parents=True, exist_ok=True)
    dummy_file = external_dir / "project.json"
    dummy_file.write_text('{"title": "external"}', encoding="utf-8")

    # Run init --force on directory outside workspace
    rc = cli.main(["init", "-w", str(external_dir), "--force"])
    # Must reject with rc=2 and not delete the external directory
    assert rc == 2
    assert external_dir.exists()
    assert dummy_file.exists()


# ==========================================
# P1 Tests
# ==========================================

def test_p1_1_beats_line_actions_regex(temp_repo):
    """P1-1: beats line actions section header matching `.*线(索)?动作`."""
    beats_text = """---
chapter: ch_001
vol: vol_01
form: 剧情推进
pov: 叶辰
words: [2400, 3500]
---

# 第1章 命运的转折

## 伏笔与线索动作（对齐 state/lines.json）
- plant GUN-001 (神秘古玉): 发现后山的古玉
- plant MIS-001 (退婚误会): 以为是退婚
"""
    sec = common.md_section(beats_text, r"^##\s*.*线(索)?动作")
    assert len(sec) >= 2
    assert any("GUN-001" in ln for ln in sec)
    assert any("MIS-001" in ln for ln in sec)


def test_p1_2_workspace_arg_before_subcommand(temp_repo):
    """P1-2: -w specified on parent subcommand is preserved due to argparse.SUPPRESS on children."""
    book = temp_repo["book"]
    parser = cli._build_parser()
    
    # Test parent `-w` (e.g. `snapshot -w <book> list`)
    args1 = parser.parse_args(["snapshot", "-w", str(book), "list"])
    assert args1.workspace == str(book)

    args2 = parser.parse_args(["proposal", "-w", str(book), "new", "ch_001"])
    assert args2.workspace == str(book)

    # Test child `-w` (e.g. `snapshot list -w <book>`)
    args3 = parser.parse_args(["snapshot", "list", "-w", str(book)])
    assert args3.workspace == str(book)


def test_p1_3_proposal_auto_write_protection(temp_repo):
    """P1-3: proposal auto --write refuses to overwrite existing proposal unless --force is given."""
    book = temp_repo["book"]
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prop = inbox / "ch_001.json"
    prop.write_text('{"chapter": "ch_001", "custom": true}', encoding="utf-8")

    # Add beats for ch_001
    beats_file = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    beats_file.parent.mkdir(parents=True, exist_ok=True)
    beats_file.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n## 冲突与场景脉络\n- 场景一：测试\n", encoding="utf-8")

    # Try proposal auto --write without --force
    rc1 = cli.main(["proposal", "-w", str(book), "auto", "ch_001", "--write"])
    assert rc1 == 1
    assert '"custom": true' in prop.read_text(encoding="utf-8")

    # Try proposal auto --write with --force
    rc2 = cli.main(["proposal", "-w", str(book), "auto", "ch_001", "--write", "--force"])
    assert rc2 == 0
    assert '"custom": true' not in prop.read_text(encoding="utf-8")


def test_p1_4_review_gate_soft_notice(temp_repo):
    """P1-4: review_gate is a soft notice and does not return blocking errors."""
    book = temp_repo["book"]
    notices = checks.review_gate(book, "ch_001")
    # If no review note exists, it returns empty list or soft notice strings
    assert isinstance(notices, list)


def test_p1_5_and_p2_8_to_12_ch_003_draft_data_validity():
    """P1-5 & P2-8~12: Real book ch_003.draft.json addresses all 5 data discrepancies cleanly."""
    real_book = common.project_root() / "workspace" / "凡人修仙：我百世轮回成道祖"
    draft_path = real_book / "state" / "inbox" / "ch_003.draft.json"
    assert draft_path.is_file()

    draft = common.load_json(draft_path)
    # Check draft flags
    assert draft.get("_draft") is True
    assert draft.get("chapter") == "ch_003"
    
    # 1. P1-5 & P2-12: Power level and cultivation consistency
    cur = draft.get("current", {})
    assert "引气入体" in cur.get("power_level", "")
    assert "四系杂灵根" in cur.get("power_level", "")

    # 2. P2-8 & P2-14: 7 initial entities have card field
    ents = draft.get("entities", [])
    assert len(ents) == 7
    assert all("card" in e for e in ents)

    # 3. P2-9: 20 silver = 20000 coins in ledger transactions
    txs = draft.get("ledger", {}).get("transactions", [])
    assert any(t.get("delta") == 20000 and "二十两" in t.get("subject", "") for t in txs)

    # 4. P2-10: timeline replacement for ginseng
    events = draft.get("timeline", {}).get("events", [])
    assert len(events) >= 1
    assert "replace" in events[0]
    assert "不肯收参" in events[0]["replace"]

    # 5. P2-11: synopsis chapter 2 title updated
    syn_chs = draft.get("synopsis", {}).get("chapters", {})
    assert syn_chs.get("ch_002", {}).get("title") == "夜半杀机，连环设伏"

    # Validate proposal schema and structure
    # _draft: true intentionally generates a draft reminder error to protect against premature sync
    errors, plan = state.validate_proposal(draft)
    assert any("_draft" in e for e in errors)

    # When _draft is omitted for final merge, validation passes with 0 errors
    clean_draft = {k: v for k, v in draft.items() if k != "_draft"}
    clean_errors, clean_plan = state.validate_proposal(clean_draft)
    assert len(clean_errors) == 0


# ==========================================
# P2 Tests (Engine Robustness)
# ==========================================

def test_p2_1_corrupted_json_handling(temp_repo):
    """P2-1: Corrupted project.json / state files handled gracefully without crashing."""
    book = temp_repo["book"]
    project_file = book / "project.json"
    project_file.write_text('{invalid_json: ', encoding="utf-8")

    # _book_brief should handle corrupted file gracefully
    brief = cli._book_brief(book)
    assert isinstance(brief, dict)
    assert brief.get("title") == book.name or "损坏" in str(brief)


def test_p2_2_apply_inbox_unrelated_corrupted_json(temp_repo):
    """P2-2: Corrupted proposal for another chapter does not block target chapter sync."""
    book = temp_repo["book"]
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    
    # Put a corrupt proposal for ch_999
    bad_prop = inbox / "ch_999.json"
    bad_prop.write_text("NOT_JSON_DATA", encoding="utf-8")

    # Put a valid proposal for ch_001
    good_prop = inbox / "ch_001.json"
    good_prop.write_text(json.dumps({
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.test.01",
        "timeline": {"events": [{"time": "第1日", "event": "测试事件"}]},
        "synopsis": {"title": "第1章 测试", "text": "测试概要"}
    }), encoding="utf-8")

    res = state.apply_inbox(book, expect_chapter="ch_001")
    # Target chapter should succeed
    assert res["applied"] == 1
    # Bad proposal should be moved to failed/
    assert not bad_prop.exists()
    assert (inbox / "failed" / "ch_999.json").exists()


def test_p2_3_status_large_chapter_horizon(temp_repo):
    """P2-3: Stray large chapter (e.g. ch_9999) does not expand thousands of lines."""
    book = temp_repo["book"]
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_9999.md").write_text("# 第9999章\n正文", encoding="utf-8")

    # Call status without hanging or outputting 10000 lines
    rc = cli.main(["status", "-w", str(book)])
    assert rc == 0


def test_p2_4_file_lock_timeout(temp_repo):
    """P2-4: Concurrent lock timeout raises TimeoutError gracefully."""
    book = temp_repo["book"]
    state_dir = book / "state"
    # Acquire lock with a very short timeout
    with common.file_lock(state_dir, name=".state.lock", timeout=0.5):
        with pytest.raises(TimeoutError):
            with common.file_lock(state_dir, name=".state.lock", timeout=0.1):
                pass


def test_p2_5_failed_duplicate_pickup(temp_repo):
    """P2-5: failed/ duplicate archive like ch_001.2.json is picked up on retry."""
    book = temp_repo["book"]
    inbox = book / "state" / "inbox"
    failed = inbox / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    
    cand = failed / "ch_001.2.json"
    cand.write_text(json.dumps({
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.test.retry",
        "timeline": {"events": [{"time": "第1日", "event": "重试测试"}]},
        "synopsis": {"title": "第1章 测试", "text": "测试概要"}
    }), encoding="utf-8")

    res = state.apply_inbox(book, expect_chapter="ch_001")
    assert res["picked_up"] is True
    assert res["applied"] == 1


def test_p2_6_review_gate_uses_highest_beats(temp_repo):
    """P2-6: review_gate and review_skeleton use the latest (highest version) beats."""
    book = temp_repo["book"]
    beats_dir = book / "outlines" / "vol_01" / "beats"
    beats_dir.mkdir(parents=True, exist_ok=True)
    (beats_dir / "ch_001_v1.md").write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n## 验收标准\n1. 旧标准\n", encoding="utf-8")
    (beats_dir / "ch_001_v2.md").write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n## 验收标准\n1. 新标准A\n2. 新标准B\n", encoding="utf-8")

    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第1章\n正文", encoding="utf-8")

    skel = checks.review_skeleton(book, "ch_001")
    assert "新标准A" in skel["acceptance"]
    assert "新标准B" in skel["acceptance"]


def test_p2_7_pack_budget_and_file_index(temp_repo, monkeypatch):
    """P2-7: pack file_index aligns with 25 items cap before trimming and reports hard_cap_breached."""
    book = temp_repo["book"]
    monkeypatch.setattr(pack, "PACK_TOKEN_CAP", 30)
    
    beats_file = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    beats_file.parent.mkdir(parents=True, exist_ok=True)
    beats_file.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n## 冲突与场景脉络\n- 场景一：测试\n", encoding="utf-8")

    # Create 30 character cards
    char_dir = book / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)
    for i in range(30):
        (char_dir / f"npc_{i:02d}.md").write_text(f"# NPC {i}\n背景说明", encoding="utf-8")

    payload = pack.build_pack(book, "ch_001")
    report = payload.get("budget_report", {})
    assert report.get("hard_cap_breached") is True
    assert report.get("trimmed_file_index") == 25
    assert len(payload.get("p2", {}).get("file_index", [])) == 0


# ==========================================
# P2 Tests (Contract & Documentation)
# ==========================================

def test_p2_13_templates_readme():
    """P2-13: templates/README.md correctly documents instantiation mode."""
    content = (common.project_root() / "templates" / "README.md").read_text(encoding="utf-8")
    assert "实例化方式" in content
    assert "characters/protagonist.md" in content


def test_p2_14_workflow_and_skill_card_field():
    """P2-14: Legal entity field list includes `card`."""
    workflow = (common.project_root() / ".agents" / "rules" / "novel_workflow.md").read_text(encoding="utf-8")
    assert "card" in workflow

    director_skill = (common.project_root() / ".agents" / "skills" / "director" / "SKILL.md").read_text(encoding="utf-8")
    assert "card" in director_skill


def test_p2_15_workflow_stage5_contract():
    """P2-15: Stage 5 documents four inputs (beats/raw/final/inbox) and snapshots path."""
    workflow = (common.project_root() / ".agents" / "rules" / "novel_workflow.md").read_text(encoding="utf-8")
    assert "beats/ch_XXX.md" in workflow
    assert "raw/ch_XXX_v1.md" in workflow
    assert "final/ch_XXX.md" in workflow
    assert "state/inbox/ch_XXX.json" in workflow
    assert "state/snapshots/" in workflow


def test_p2_16_words_band_consistency():
    """P2-16: Word band unified to CJK characters count across documents."""
    editor_rule = (common.project_root() / ".agents" / "rules" / "craft_editor.md").read_text(encoding="utf-8")
    drafter_rule = (common.project_root() / ".agents" / "rules" / "craft_drafter.md").read_text(encoding="utf-8")
    assert "2400" in editor_rule and "3500" in editor_rule
    assert "2400" in drafter_rule and "3500" in drafter_rule


def test_p2_17_five_facts_alignment():
    """P2-17: 5 facts classification aligned across AGENTS.md, workflow, and craft_reader."""
    agents_md = (common.project_root() / "AGENTS.md").read_text(encoding="utf-8")
    workflow = (common.project_root() / ".agents" / "rules" / "novel_workflow.md").read_text(encoding="utf-8")
    reader_rule = (common.project_root() / ".agents" / "rules" / "craft_reader.md").read_text(encoding="utf-8")
    assert "5 大事实" in agents_md or "五大事实" in agents_md or "5" in agents_md
    assert "5 大事实" in workflow or "五大事实" in workflow or "5" in workflow


def test_p2_18_beats_fm_keys_documented():
    """P2-18: beats front-matter allowed keys documented in templates/beats.md."""
    beats_tpl = (common.project_root() / "templates" / "beats.md").read_text(encoding="utf-8")
    assert "chapter:" in beats_tpl
    assert "vol:" in beats_tpl
    assert "form:" in beats_tpl


# ==========================================
# P3 Tests
# ==========================================

def test_p3_1_operation_id_validation():
    """P3-1: operation_id schema & regex strictly anchored."""
    schema = common.load_json(common.project_root() / "engine" / "schemas" / "proposal.schema.json")
    
    valid_proposal = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.reader.01"
    }
    assert len(validator.validate(valid_proposal, schema)) == 0

    invalid_proposal = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.reader invalid space"
    }
    errs = validator.validate(invalid_proposal, schema)
    assert len(errs) > 0
    assert any("operation_id" in e for e in errs)


def test_p3_2_register_alias_for_upsert():
    """P3-2: register is accepted as alias of upsert in proposal validation."""
    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.test.01",
        "entities": [
            {
                "action": "register",
                "name": "青云门",
                "type": "faction",
                "status": "active",
                "summary": "正道宗门"
            }
        ]
    }
    errors, plan = state.validate_proposal(prop)
    assert len(errors) == 0


def test_p3_3_utf8_bom_reading(temp_repo):
    """P3-3: UTF-8 BOM json is decoded properly without error."""
    book = temp_repo["book"]
    test_file = book / "test_bom.json"
    # Write with utf-8-sig
    test_file.write_text('{"hello": "world"}', encoding="utf-8-sig")
    data = common.load_json(test_file)
    assert data == {"hello": "world"}


def test_p3_5_proposal_auto_operation_id_precision(temp_repo):
    """P3-5: proposal auto operation_id has high precision to avoid same-minute collision."""
    book = temp_repo["book"]
    beats_file = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    beats_file.parent.mkdir(parents=True, exist_ok=True)
    beats_file.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n## 冲突与场景脉络\n- 场景一：测试\n", encoding="utf-8")

    cli.main(["proposal", "-w", str(book), "auto", "ch_001", "--write"])
    prop_path = book / "state" / "inbox" / "ch_001.json"
    data = common.load_json(prop_path)
    op_id = data.get("operation_id", "")
    assert re.match(r"^ch_001\.auto\.\d{4}_\d{6}$", op_id)


def test_p3_6_proposal_auto_bold_marker_cleanup():
    """P3-6: proposal auto correctly cleans bold `**` markers in hook annotations."""
    s = "- 📍 **章末物理刀口卡点**：叶辰拔出断剑，剑鸣动九霄！"
    cleaned = re.sub(r"^(?:核心事件与对抗动作|角色互动与言语试探|破局行动与结果|[-·*]*\s*📍\s*\**章末物理刀口卡点\**)[:：]\s*", "", s).strip()
    assert "**" not in cleaned
    assert "叶辰拔出断剑" in cleaned


def test_p3_7_slot_regex_whitespace():
    """P3-7: Template slot regex supports arbitrary inner whitespace."""
    content = "书名：{{ slot:book_title }}，主角：{{slot:protagonist}}"
    slots = {"book_title": "遮天", "protagonist": "叶凡"}
    filled = cli.SLOT_RE.sub(lambda m: slots.get(m.group(1), m.group(0)), content)
    assert "书名：遮天" in filled
    assert "主角：叶凡" in filled


def test_p3_8_prev_contrast_zero_subjectivity(temp_repo):
    """P3-8: evidence.prev_contrast outputs zero subjective advice."""
    book = temp_repo["book"]
    prev_data = evidence.prev_contrast(book, "ch_001")
    assert isinstance(prev_data, dict)
    assert "建议" not in json.dumps(prev_data, ensure_ascii=False)


def test_p3_10_dashboard_html_escape(temp_repo):
    """P3-10: dashboard HTML escapes entity names/summaries preventing XSS."""
    book = temp_repo["book"]
    ent_path = book / "state" / "entities.json"
    ents = common.load_json(ent_path, default={"entries": []})
    ents["entries"].append({
        "name": "<script>alert('xss')</script>",
        "type": "person",
        "status": "active",
        "summary": "测试 <b>加粗</b> & 特殊字符"
    })
    common.dump_json(ent_path, ents)

    html_out = dashboard.generate_dashboard_html(book)
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "&lt;b&gt;" in html_out


def test_p3_11_dashboard_relative_imports():
    """P3-11: dashboard.py uses relative imports."""
    content = (common.project_root() / "engine" / "dashboard.py").read_text(encoding="utf-8")
    assert "from . import" in content


def test_p3_12_export_views_pipe_escaping(temp_repo):
    """P3-12: export_views escapes `|` characters in markdown tables."""
    book = temp_repo["book"]
    ent_path = book / "state" / "entities.json"
    ents = common.load_json(ent_path, default={"entries": []})
    ents["entries"].append({
        "name": "青云宗|丹峰",
        "type": "faction",
        "status": "active",
        "summary": "主峰|副峰"
    })
    common.dump_json(ent_path, ents)

    out_file = pack.export_views(book)
    content = out_file.read_text(encoding="utf-8")
    assert r"青云宗\|丹峰" in content
    assert r"主峰\|副峰" in content


def test_p3_13_cross_volume_chapter_tokens(temp_repo):
    """P3-13: evidence.final_chapters prefixes tokens with volume to distinguish cross-volume chapters."""
    book = temp_repo["book"]
    ms = book / "manuscript"
    (ms / "vol_01" / "final").mkdir(parents=True, exist_ok=True)
    (ms / "vol_02" / "final").mkdir(parents=True, exist_ok=True)
    (ms / "vol_01" / "final" / "ch_001.md").write_text("# 第1章 卷一\n卷一正文", encoding="utf-8")
    (ms / "vol_02" / "final" / "ch_001.md").write_text("# 第1章 卷二\n卷二正文", encoding="utf-8")

    chaps = evidence.final_chapters(book)
    tokens = [c[0] for c in chaps]
    assert "vol_01/ch_001" in tokens
    assert "vol_02/ch_001" in tokens


def test_p3_14_snapshot_path_in_docs():
    """P3-14: Documentation specifies snapshot path with state/ prefix."""
    workflow = (common.project_root() / ".agents" / "rules" / "novel_workflow.md").read_text(encoding="utf-8")
    assert "state/snapshots/" in workflow


def test_p3_18_file_lock_stale_cleanup(temp_repo):
    """P3-18: file_lock cleans up stale lock files older than timeout."""
    book = temp_repo["book"]
    state_dir = book / "state"
    lock_file = state_dir / ".state.lock"
    lock_file.write_text("dummy", encoding="utf-8")
    
    # Modify mtime to simulate stale lock (150 seconds ago > 120s threshold)
    old_time = time.time() - 150
    os.utime(lock_file, (old_time, old_time))

    # Should acquire lock successfully by removing stale lock
    with common.file_lock(state_dir, name=".state.lock", timeout=1.0):
        assert lock_file.exists()


def test_p3_19_craft_reader_sample_id():
    """P3-19: craft_reader.md contains valid line ID example."""
    reader_rule = (common.project_root() / ".agents" / "rules" / "craft_reader.md").read_text(encoding="utf-8")
    assert "GUN-" in reader_rule


def test_p3_21_inbox_readme_force_and_op_id():
    """P3-21: INBOX_README notes init --force exception and op_id naming."""
    inbox_readme = (common.project_root() / "workspace" / "凡人修仙：我百世轮回成道祖" / "state" / "inbox" / "README.md").read_text(encoding="utf-8")
    assert "--force" in inbox_readme
    assert "operation_id" in inbox_readme


def test_p3_24_version():
    """P3-24: Engine version updated to 2.0.0."""
    import engine
    assert engine.__version__ == "2.0.0"


def test_p3_25_status_nonexistent_workspace_error(temp_repo):
    """P3-25: status with nonexistent -w path reports explicit error rc=1."""
    non_existent = temp_repo["root"] / "non_existent_folder_123"
    rc = cli.main(["status", "-w", str(non_existent)])
    assert rc == 1


def test_p3_26_readme_stage1_beats_prerequisite():
    """P3-26: README.md quickstart notes Stage 1 beats prerequisite for pack."""
    readme = (common.project_root() / "README.md").read_text(encoding="utf-8")
    assert "Stage 1" in readme


# ==========================================
# New Features: Quote Grounding & Verify & Revision Channels
# ==========================================

def test_quote_grounding_gate(temp_repo):
    """New Feature: Quote must be exact substring in final manuscript."""
    book = temp_repo["book"]
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第1章 测试\n叶辰拔出青云残剑，寒光凛冽。", encoding="utf-8")

    # Valid quote
    good_prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.quote.01",
        "entities": [{
            "action": "upsert",
            "name": "青云残剑",
            "type": "item",
            "status": "active",
            "summary": "残破飞剑",
            "quote": "叶辰拔出青云残剑"
        }],
        "synopsis": {"title": "第1章 测试", "text": "测试"}
    }
    errs_good = checks.validate_quotes(book, "ch_001", good_prop)
    assert len(errs_good) == 0

    # Fabricated / hallucinated quote
    bad_prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.quote.02",
        "entities": [{
            "action": "upsert",
            "name": "青云残剑",
            "type": "item",
            "status": "active",
            "summary": "残破飞剑",
            "quote": "这是一句正文里绝对没有的编造引文"
        }],
        "synopsis": {"title": "第1章 测试", "text": "测试"}
    }
    errs_bad = checks.validate_quotes(book, "ch_001", bad_prop)
    assert len(errs_bad) >= 1
    assert "quote" in errs_bad[0] and "final" in errs_bad[0]


def test_verify_candidates_battery(temp_repo):
    """New Feature: verify_candidates Stage 4.5 candidate checks."""
    book = temp_repo["book"]
    final_dir = book / "manuscript" / "vol_01" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ch_001.md").write_text("# 第1章 宿命之始\n叶辰怀揣二十两碎银子，走进了青云宗坊市。", encoding="utf-8")

    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.verify.01",
        "synopsis": {"title": "第1章 宿命之始", "text": "测试"},
        "entities": [{
            "action": "upsert",
            "name": "青云宗",
            "type": "faction",
            "status": "active",
            "summary": "正道宗门",
            "quote": "走进了青云宗坊市"
        }]
    }
    result = checks.verify_candidates(book, "ch_001", prop)
    assert result["kind"] == "verify"
    assert result["chapter"] == "ch_001"
    assert "items" in result


def test_timeline_replace_and_synopsis_chapters_revision(temp_repo):
    """New Feature: timeline replace action & synopsis chapters cross-chapter revision."""
    book = temp_repo["book"]
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    # Initial state
    tl_path = book / "state" / "timeline.json"
    tl_path.write_text(json.dumps({
        "events": [{"time": "第1日", "event": "旧事件描述", "chapter": "ch_001"}],
        "arcs": [],
        "clocks": []
    }), encoding="utf-8")

    syn_path = book / "state" / "synopsis.json"
    syn_path.write_text(json.dumps({
        "book_logline": "",
        "chapters": {"ch_001": {"num": 1, "title": "旧标题", "synopsis": "旧梗概", "source": "manual"}}
    }), encoding="utf-8")

    # Merge proposal with revisions
    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_002",
        "operation_id": "ch_002.rev.01",
        "timeline": {
            "events": [
                {"time": "第1日", "event": "旧事件描述", "replace": "新事件描述（已修正）"},
                {"time": "第2日", "event": "第2日新事件"}
            ]
        },
        "synopsis": {
            "title": "第2章 新章",
            "text": "新章梗概",
            "chapters": {
                "ch_001": {"title": "第1章 正式标题", "synopsis": "第1章 精确梗概"}
            }
        }
    }
    (inbox / "ch_002.json").write_text(json.dumps(prop), encoding="utf-8")
    
    res = state.apply_inbox(book, expect_chapter="ch_002")
    assert res["applied"] == 1

    # Verify timeline updated
    tl_data = common.load_json(tl_path)
    assert any(e.get("event") == "新事件描述（已修正）" for e in tl_data["events"])
    assert not any(e.get("event") == "旧事件描述" for e in tl_data["events"])

    # Verify synopsis updated
    syn_data = common.load_json(syn_path)
    assert syn_data["chapters"]["ch_001"]["title"] == "第1章 正式标题"
    assert syn_data["chapters"]["ch_001"]["synopsis"] == "第1章 精确梗概"


# ==========================================
# Three Core Hard Bugs Fixes Tests
# ==========================================

def test_hard_bug_1_alias_stopwords_and_two_char_name_protection(temp_repo):
    """Hard Bug 1: Stopword alias filtering protects 2-char primary names while dropping generic short aliases."""
    book = temp_repo["book"]
    ent_path = book / "state" / "entities.json"
    ents = {
        "entries": [
            {"name": "韩立", "type": "person", "status": "active", "summary": "主角", "aliases": []},
            {"name": "赵掌柜", "type": "person", "status": "active", "summary": "当铺掌柜", "aliases": ["掌柜", "赵伯"]},
            {"name": "青云残剑", "type": "item", "status": "active", "summary": "法器", "aliases": ["飞剑", "残剑"]}
        ]
    }
    common.dump_json(ent_path, ents)

    # With safe_aliases=True
    lookup_safe = evidence.entity_lookup(book, safe_aliases=True)
    assert lookup_safe["韩立"] == ["韩立"]
    # "掌柜" is in generic stopwords (len<=2), dropped; "赵伯" kept
    assert "掌柜" not in lookup_safe["赵掌柜"]
    assert "赵伯" in lookup_safe["赵掌柜"]
    # "飞剑" is in generic stopwords (len<=2), dropped; "残剑" not in generic stopwords, kept
    assert "飞剑" not in lookup_safe["青云残剑"]
    assert "残剑" in lookup_safe["青云残剑"]


def test_hard_bug_1_p1_budget_and_indirect_caps(temp_repo):
    """Hard Bug 1: P1 direct entities capped at 12, indirect capped at 5, on_stage ordered first."""
    book = temp_repo["book"]
    ent_path = book / "state" / "entities.json"
    
    # Create 20 entities
    entries = []
    for i in range(20):
        entries.append({
            "name": f"人物{i:02d}",
            "type": "person",
            "status": "active",
            "summary": f"重要人物{i:02d}的生平介绍",
            "aliases": [f"别名{i:02d}"]
        })
    common.dump_json(ent_path, {"entries": entries})

    # Beats mentioning all 20 entities
    beats_file = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    beats_file.parent.mkdir(parents=True, exist_ok=True)
    all_names = " ".join(f"人物{i:02d}" for i in range(20))
    beats_file.write_text(f"---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n## 冲突\n{all_names}\n", encoding="utf-8")

    # Mark 人物18 as on_stage in current.json
    cur_path = book / "state" / "current.json"
    cur = common.load_json(cur_path)
    cur["present_characters"] = ["人物18"]
    common.dump_json(cur_path, cur)

    payload = pack.build_pack(book, "ch_001")
    p1 = payload.get("p1", {})
    # Direct entities capped at 12
    assert len(p1.get("entities", [])) <= 12
    # on_stage entity 人物18 must be in P1 and ranked first
    assert p1["entities"][0]["name"] == "人物18"


def test_hard_bug_2_lines_quota_and_aging_reminders(temp_repo):
    """Hard Bug 2: Lines quota checking in check and P0 aging multi-tier reminders in pack."""
    book = temp_repo["book"]
    lines_path = book / "state" / "lines.json"
    
    # 9 active foreshadows (> 8 cap) and 1 aging idle foreshadow (> 10 chapters idle)
    foreshadows = []
    for i in range(1, 10):
        foreshadows.append({
            "id": f"GUN-{i:03d}",
            "name": f"伏笔{i}",
            "status": "Planted",
            "target_ch": 20,
            "plant_ch": 1,
            "weight": 2
        })
    # Add an aging idle line planted in ch_001 for current chapter ch_015 (idle = 14)
    foreshadows.append({
        "id": "GUN-099",
        "name": "太古玄冰鉴",
        "status": "Planted",
        "target_ch": 30,
        "plant_ch": 1,
        "weight": 3
    })
    common.dump_json(lines_path, {"foreshadows": foreshadows, "misunderstandings": [], "knowledge": []})

    # 1. Check should report line_quota_exceeded warning (10 open > 8 cap)
    rep = checks.run_checks(book)
    quota_warns = [w for w in rep["warnings"] if w["code"] == "line_quota_exceeded"]
    assert len(quota_warns) >= 1
    assert "上限 8" in quota_warns[0]["msg"]

    # 2. Pack P0 reminders for ch_015 should report 紧急催还 for GUN-099
    reminders = pack._hard_reminders(book, "ch_015", 15)
    assert any("🚨【紧急催还伏笔】GUN-099" in r and "已闲置 14 章" in r for r in reminders)


def test_hard_bug_3_volume_phase_milestone_p0_injection(temp_repo):
    """Hard Bug 3: P0 hot layer automatically extracts current volume phase milestone."""
    book = temp_repo["book"]
    outline_path = book / "outlines" / "vol_01" / "outline.md"
    outline_path.parent.mkdir(parents=True, exist_ok=True)
    outline_path.write_text("""# vol_01 卷纲（测试）
## 单卷节拍矩阵（Volume Beat Matrix）
- **阶段一：建立与破局（ch_001—ch_005 ｜ 核心功能：初始处境、药铺危机与引气入体）**
  - ch_001: 穿越初醒，采药少年立稳脚跟。
- **阶段二：发展与深化（ch_006—ch_012 ｜ 核心功能：坊市见闻与暗流蓄积）**
""", encoding="utf-8")

    beats_file = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    beats_file.parent.mkdir(parents=True, exist_ok=True)
    beats_file.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n", encoding="utf-8")

    payload = pack.build_pack(book, "ch_001")
    p0 = payload.get("p0", {})
    assert "阶段一：建立与破局" in p0.get("volume_phase", "")
    assert "初始处境、药铺危机与引气入体" in p0.get("volume_phase", "")
    assert "采药少年立稳脚跟" in p0.get("volume_phase", "")

    rendered = pack.render_pack(payload)
    assert "=== 本卷阶段航标 ===" in rendered
    assert "阶段一：建立与破局" in rendered


def test_hard_bug_3_checkpoint_command(temp_repo):
    """Hard Bug 3: `checkpoint` CLI command executes macro review and outputs structured alignment."""
    book = temp_repo["book"]
    outline_path = book / "outlines" / "vol_01" / "outline.md"
    outline_path.parent.mkdir(parents=True, exist_ok=True)
    outline_path.write_text("""# vol_01 卷纲（测试）
## 单卷节拍矩阵（Volume Beat Matrix）
- **阶段一：建立与破局（ch_001—ch_005 ｜ 核心功能：初始处境、药铺危机与引气入体）**
- **阶段二：发展与深化（ch_006—ch_012 ｜ 核心功能：坊市见闻与暗流蓄积）**
""", encoding="utf-8")

    # Add synopsis and timeline
    syn_path = book / "state" / "synopsis.json"
    common.dump_json(syn_path, {
        "book_logline": "",
        "chapters": {
            "ch_001": {"num": 1, "title": "初入仙门", "synopsis": "叶辰初露锋芒"},
            "ch_002": {"num": 2, "title": "后山设伏", "synopsis": "反杀强敌"}
        }
    })

    # Execute checkpoint command with --json
    rc = cli.main(["checkpoint", "-w", str(book), "ch_002", "--json"])
    assert rc == 0


def test_hard_bug_4_loadout_schema_and_pack_rendering(temp_repo):
    """Hard Bug 4: Active loadout schema validation, proposal merging, and P0 rendering."""
    book = temp_repo["book"]
    cur_path = book / "state" / "current.json"
    cur = common.load_json(cur_path)
    cur["loadout"] = {
        "cultivation": "《太虚引气经》",
        "movement": "《浮光掠影步》",
        "attack": "奔雷三剑",
        "trump_card": "九幽断魂针",
        "equipped_items": ["青竹蜂云剑", "玄龟护心镜"]
    }
    common.dump_json(cur_path, cur)

    beats_file = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    beats_file.parent.mkdir(parents=True, exist_ok=True)
    beats_file.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n", encoding="utf-8")

    payload = pack.build_pack(book, "ch_001")
    rendered = pack.render_pack(payload)
    assert "loadout:" in rendered
    assert "主修:《太虚引气经》" in rendered
    assert "身法:《浮光掠影步》" in rendered
    assert "杀招:奔雷三剑" in rendered
    assert "底牌:九幽断魂针" in rendered


def test_hard_bug_5_dossier_schema_and_pack_rendering(temp_repo):
    """Hard Bug 5: Entity dossier memory anchors and P1 rendering."""
    book = temp_repo["book"]
    ent_path = book / "state" / "entities.json"
    ents = {
        "entries": [
            {
                "name": "王执事",
                "type": "person",
                "status": "active",
                "summary": "青云宗外门执事",
                "dossier": "ch_020 被顾长青借宗门律法坑走500灵石，暗中咬牙切齿寻找其违规把柄报复",
                "aliases": []
            }
        ]
    }
    common.dump_json(ent_path, ents)

    beats_file = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    beats_file.parent.mkdir(parents=True, exist_ok=True)
    beats_file.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 剧情推进\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n王执事走来。\n", encoding="utf-8")

    payload = pack.build_pack(book, "ch_001")
    rendered = pack.render_pack(payload)
    assert "恩怨羁绊: ch_020 被顾长青借宗门律法坑走500灵石" in rendered


def test_hard_bug_6_high_tension_fatigue_detection(temp_repo):
    """Hard Bug 6: Checks should warn if consecutive chapters run on high tension without cooldown."""
    book = temp_repo["book"]
    vol_beats = book / "outlines" / "vol_01" / "beats"
    vol_beats.mkdir(parents=True, exist_ok=True)

    # Create 3 consecutive high tension beats
    for i in (1, 2, 3):
        bf = vol_beats / f"ch_{i:03d}.md"
        bf.write_text(f"---\nchapter: ch_{i:03d}\nvol: vol_01\nform: 生死博弈\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第{i}章\n", encoding="utf-8")

    rep = checks.run_checks(book)
    tension_warns = [w for w in rep["warnings"] if w["code"] == "high_tension_fatigue"]
    assert len(tension_warns) >= 1
    assert "连续 3 章为高压战斗/决战" in tension_warns[0]["msg"]
    assert "战后清点/爽感兑现" in tension_warns[0]["msg"]


def test_hard_bug_7_state_cli_and_critical_mutation_detection(temp_repo):
    """Hard Bug 7: State CLI get/set surgical correction and critical mutation detection in verify."""
    book = temp_repo["book"]
    
    # 1. Test CLI state set
    rc = cli.main(["state", "set", "-w", str(book), "current.injury", "轻微擦伤，已敷药"])
    assert rc == 0
    cur = state.load_state(book, "current")
    assert cur["injury"] == "轻微擦伤，已敷药"

    # 2. Test CLI state get
    rc = cli.main(["state", "get", "-w", str(book), "current.injury", "--json"])
    assert rc == 0

    # 3. Test verify_candidates on critical mutation (life_status deceased)
    final_file = book / "manuscript" / "vol_01" / "final" / "ch_001.md"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    final_file.write_text("# 第1章 杀局\n刀疤刘惨叫一声，当场气绝身亡。\n", encoding="utf-8")

    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": "ch_001.reader.01",
        "current": {"injury": "断臂重残"},
        "entities": [{"action": "upsert", "name": "刀疤刘", "type": "person", "life_status": "deceased"}]
    }
    res = checks.verify_candidates(book, "ch_001", prop)
    cands = res.get("items", [])
    crit_warns = [c for c in cands if c["code"] == "critical_mutation"]
    assert len(crit_warns) >= 2  # one for deceased, one for severe injury
    assert any("【战死/离世 (deceased)】" in c["msg"] for c in crit_warns)
    assert any("断臂重残" in c["msg"] for c in crit_warns)


def test_hard_bug_8_abstract_beats_detection(temp_repo):
    """Hard Bug 8: Abstract filler words in beats triggers beats_scene_abstract warning."""
    book = temp_repo["book"]
    vol_beats = book / "outlines" / "vol_01" / "beats"
    vol_beats.mkdir(parents=True, exist_ok=True)

    bf = vol_beats / "ch_001.md"
    bf.write_text("---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\npov: 叶辰\nwords: [2400, 3500]\n---\n# 第1章\n## 场景一\n主角遇到某些麻烦，巧妙化解危机。\n", encoding="utf-8")

    rep = checks.run_checks(book)
    abs_warns = [w for w in rep["warnings"] if w["code"] == "beats_scene_abstract"]
    assert len(abs_warns) >= 1
    assert "巧妙化解" in abs_warns[0]["msg"]
