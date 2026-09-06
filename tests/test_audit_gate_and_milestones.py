"""Unit tests for Stage 4C audit gate, milestone seeding, and snapshot rollback compatibility."""
import json
import shutil
from pathlib import Path

import pytest
from conftest import CliResult, build_book


def test_milestone_cli_lifecycle(tmp_path, cli, ws_root):
    """测试 milestone add 与 milestone list 命令行生命周期。"""
    book = build_book(ws_root, "bk_ms_test")

    # 1. 初始里程碑为空
    res = cli("milestone", "list", "-w", str(book), "--json")
    assert res.code == 0
    data = res.json()
    assert data["ok"] is True
    assert data["total"] == 0

    # 2. 播种第一个里程碑（自动分配 MS-001）
    res = cli("milestone", "add", "-t", "查明账目黑洞", "-c", "5", "-d", "查清灯司各坊私设小金库",
              "-w", str(book), "--json")
    assert res.code == 0
    data = res.json()
    assert data["ok"] is True
    assert data["milestone"]["id"] == "MS-001"
    assert data["milestone"]["target_ch"] == 5
    assert data["milestone"]["status"] == "pending"

    # 3. 播种第二个里程碑（自定义 ID）
    res = cli("milestone", "add", "-t", "斩杀巡察使", "-c", "10", "--id", "MS-099",
              "-w", str(book), "--json")
    assert res.code == 0
    assert res.json()["milestone"]["id"] == "MS-099"

    # 4. 重复 ID 拦截
    res = cli("milestone", "add", "-t", "冲突里程碑", "--id", "MS-099",
              "-w", str(book), "--json")
    assert res.code == 1
    assert "已存在" in res.json()["error"]

    # 5. 列出全部里程碑
    res = cli("milestone", "list", "-w", str(book), "--json")
    assert res.code == 0
    data = res.json()
    assert data["total"] == 2
    ids = [m["id"] for m in data["milestones"]]
    assert "MS-001" in ids and "MS-099" in ids


def test_audit_write_and_gate_strict_mode(tmp_path, cli, ws_root):
    """测试 audit --write 生成报告，以及 sync 在 strict 模式下的阻断与放行机制。"""
    book = build_book(ws_root, "bk_audit_gate")
    ch = "ch_001"

    # 开启 strict 模式
    pj_file = book / "project.json"
    pj = json.loads(pj_file.read_text(encoding="utf-8"))
    pj["audit_mode"] = "strict"
    pj_file.write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")

    # 准备合法的 proposal
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "operation_id": "op_test_gate_001",
        "chapter": ch,
        "current": {"power_level": "九品", "location": "灯司西院", "time": "宣和三年秋"},
    }
    (inbox / f"{ch}.json").write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")

    # 1. 未生成 audit 报告时，sync 拒绝
    audit_file = book / "log" / "audit" / f"{ch}.md"
    if audit_file.exists():
        audit_file.unlink()

    res = cli("sync", ch, "-w", str(book), "--json")
    assert res.code == 1
    assert "未找到 ch_001 的事实一致性仲裁报告" in res.json()["error"]

    # 2. 运行 audit --write 生成报告
    res = cli("audit", ch, "--write", "-w", str(book), "--json")
    assert res.code == 0
    assert audit_file.is_file()
    audit_content = audit_file.read_text(encoding="utf-8")
    assert "---" in audit_content
    assert "audit_chapter: ch_001" in audit_content
    assert "hard: 0" in audit_content

    # 3. 报告中 hard=0，sync 成功放行
    res = cli("sync", ch, "-w", str(book), "--json")
    assert res.code == 0
    assert res.json()["chapter"] == ch


def test_audit_gate_hard_contradiction_blocking(tmp_path, cli, ws_root):
    """测试存在未裁定硬矛盾时 strict 模式阻断，标记已裁定或 advisory 模式时放行。"""
    book = build_book(ws_root, "bk_audit_hard")
    ch = "ch_001"

    pj_file = book / "project.json"
    pj = json.loads(pj_file.read_text(encoding="utf-8"))
    pj["audit_mode"] = "strict"
    pj_file.write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")

    # 准备提案
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "operation_id": "op_test_gate_002",
        "chapter": ch,
        "current": {"power_level": "九品", "location": "灯司西院", "time": "宣和三年秋"},
    }
    (inbox / f"{ch}.json").write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")

    # 写入带硬矛盾的 audit 报告 (hard: 2, adjudicated: false)
    audit_dir = book / "log" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / f"{ch}.md"
    audit_file.write_text(
        "---\n"
        f"audit_chapter: {ch}\n"
        "hard: 2\n"
        "soft: 1\n"
        "adjudicated: false\n"
        "---\n\n"
        f"# {ch} 事实一致性仲裁报告\n\n"
        "## 🔴 确凿硬矛盾\n"
        "- [AUDIT-001] 角色已故但登场\n",
        encoding="utf-8"
    )

    # 1. strict 模式下阻断
    res = cli("sync", ch, "-w", str(book), "--json")
    assert res.code == 1
    assert "存在 2 处确凿硬矛盾" in res.json()["error"]

    # 2. 标记 adjudicated: true，放行
    audit_file.write_text(
        "---\n"
        f"audit_chapter: {ch}\n"
        "hard: 2\n"
        "soft: 1\n"
        "adjudicated: true\n"
        "---\n\n"
        f"# {ch} 事实一致性仲裁报告\n\n"
        "## ✅ 交叉核实排除\n"
        "- 已核实属于回忆语境\n",
        encoding="utf-8"
    )
    res = cli("sync", ch, "-w", str(book), "--json")
    assert res.code == 0
    assert res.json()["chapter"] == ch


def test_audit_gate_advisory_mode(tmp_path, cli, ws_root):
    """测试 advisory 模式下存在硬矛盾或缺少报告不阻断 sync。"""
    book = build_book(ws_root, "bk_audit_adv")
    ch = "ch_001"

    pj_file = book / "project.json"
    pj = json.loads(pj_file.read_text(encoding="utf-8"))
    pj["audit_mode"] = "advisory"
    pj_file.write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")

    # 准备提案
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "operation_id": "op_test_gate_003",
        "chapter": ch,
        "current": {"power_level": "九品", "location": "灯司西院", "time": "宣和三年秋"},
    }
    (inbox / f"{ch}.json").write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")

    # 缺少 audit 报告，但在 advisory 模式下应该放行
    res = cli("sync", ch, "-w", str(book), "--json")
    assert res.code == 0
    assert res.json()["chapter"] == ch


def test_snapshot_rollback_legacy_compatibility(tmp_path, cli, ws_root):
    """测试快照回滚对旧版缺失 locked/cognition 表的向下兼容性。"""
    book = build_book(ws_root, "bk_snap_compat")

    # 1. 创建快照
    res = cli("snapshot", "create", "v1_legacy", "-w", str(book), "--json")
    assert res.code == 0

    # 找到创建的快照目录
    snap_dirs = list((book / "state" / "snapshots").glob("*_v1_legacy"))
    assert len(snap_dirs) == 1
    snap_dir = snap_dirs[0]

    # 模拟旧版快照：删除 locked.json 与 cognition.json，并更新 manifest.json
    for del_file in ("locked.json", "cognition.json"):
        f = snap_dir / del_file
        if f.is_file():
            f.unlink()

    from engine import common
    m_file = snap_dir / "manifest.json"
    if m_file.is_file():
        mf = json.loads(m_file.read_text(encoding="utf-8"))
        for del_file in ("locked.json", "cognition.json"):
            mf.get("files", {}).pop(del_file, None)
        mf["hash"] = common.canonical_json_hash(mf.get("files", {}))
        m_file.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. 回滚到该旧版快照
    res = cli("snapshot", "rollback", "v1_legacy", "-w", str(book), "--json")
    assert res.code == 0
    assert res.json()["ok"] is True

    # 3. 回滚后状态六表以及新表均存在且合法
    assert (book / "state" / "current.json").is_file()
    assert (book / "state" / "locked.json").is_file()
    assert (book / "state" / "cognition.json").is_file()

    # check 体检依然全绿
    res = cli("check", "-w", str(book), "--json")
    assert res.code == 0
