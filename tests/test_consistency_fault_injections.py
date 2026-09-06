"""tests/test_consistency_fault_injections.py: 一致性机械探针与硬闸门异常注入测试。

涵盖：
1. 已死角色活跃对话 → audit 探针抓出 candidate_hard；
2. 已摧毁地点如常运转 → audit 探针抓出 candidate_hard；
3. 0 充能法宝被再次祭出 → audit 探针抓出 candidate_hard；
4. 支出金额超出账本余额 → audit 探针抓出 candidate_soft；
5. KNO 未公开秘密由不知情者在对话中道出 → audit 探针抓出 candidate_soft；
6. 形近实体名另立新名 → alias_drift 抓出 candidate_soft；
7. 不可逆事实超出 15 条配额 → checks 报警 locked_quota_exceeded；
8. locked 死亡但实体 life_status 为 alive → checks 报错 locked_life_status_conflict；
9. 存在前文生效 locked 事实但 beats 缺少不可逆小节 → checks 报错 locked_injection_missing。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import build_book
from engine import audit, checks, common, state


@pytest.fixture
def consistency_book(ws_root) -> Path:
    """创建包含 2 章的基准测试工作区。"""
    book = build_book(ws_root, "bk_consistency", chapters=2)
    return book


def test_audit_locked_deceased_appearance(consistency_book):
    """注入 1：已死角色在正文中活跃发言 → audit 探针抓出 candidate_hard。"""
    book = consistency_book
    locked_st = {
        "entries": [
            {
                "id": "LOCK-001",
                "fact": "陆掌柜已于 ch_001 确认身亡，不可复活出场",
                "kind": "death",
                "since_ch": "ch_001",
                "quote": "陆掌柜咽下最后一口气",
            }
        ]
    }
    common.atomic_write_text(book / "state" / "locked.json", json.dumps(locked_st, ensure_ascii=False))

    ents_st = state.load_state(book, "entities")
    ents_st["entries"].append({
        "name": "陆掌柜",
        "type": "person",
        "status": "retired",
        "life_status": "deceased",
        "summary": "原杂货铺掌柜"
    })
    common.atomic_write_text(book / "state" / "entities.json", json.dumps(ents_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n陆掌柜冷笑道：“我偏要出场，看谁能拦我！”\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    assert res["hard_count"] >= 1
    found = any(c["probe"] == "locked_facts" and "陆掌柜" in c["title"] for c in res["candidates"])
    assert found, f"探针未检出已死角色活跃出场: {res['candidates']}"


def test_audit_locked_destroyed_location(consistency_book):
    """注入 2：已摧毁地点如常运转 → audit 探针抓出 candidate_hard。"""
    book = consistency_book
    locked_st = {
        "entries": [
            {
                "id": "LOCK-002",
                "fact": "栖凤楼已于 ch_001 化为一片废墟焦土",
                "kind": "destruction",
                "since_ch": "ch_001",
                "quote": "大火将栖凤楼烧成白地",
            }
        ]
    }
    common.atomic_write_text(book / "state" / "locked.json", json.dumps(locked_st, ensure_ascii=False))

    ents_st = state.load_state(book, "entities")
    ents_st["entries"].append({
        "name": "栖凤楼",
        "type": "place",
        "status": "active",
        "summary": "昔日酒楼"
    })
    common.atomic_write_text(book / "state" / "entities.json", json.dumps(ents_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n众人走进栖凤楼，找了一张空桌坐下，店小二热情地上前倒茶。\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    assert res["hard_count"] >= 1
    found = any(c["probe"] == "locked_facts" and "栖凤楼" in c["title"] for c in res["candidates"])
    assert found, f"探针未检出已摧毁地点运转: {res['candidates']}"


def test_audit_charges_exhausted_use(consistency_book):
    """注入 3：0 充能道具被再次祭出 → audit 探针抓出 candidate_hard。"""
    book = consistency_book
    ents_st = state.load_state(book, "entities")
    ents_st["entries"].append({
        "name": "辟邪玉佩",
        "type": "item",
        "status": "active",
        "charges": 0,
        "summary": "防身玉佩，灵气已尽"
    })
    common.atomic_write_text(book / "state" / "entities.json", json.dumps(ents_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n危急关头，陆沉舟毫不犹豫祭出辟邪玉佩，玉佩泛起温润清光震退强敌。\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    assert res["hard_count"] >= 1
    found = any(c["probe"] == "charges_possession" and "辟邪玉佩" in c["title"] for c in res["candidates"])
    assert found, f"探针未检出耗尽道具使用: {res['candidates']}"


def test_audit_amount_exceeds_pool(consistency_book):
    """注入 4：支出金额超过账本余额 → audit 探针抓出 candidate_soft。"""
    book = consistency_book
    led_st = state.load_state(book, "ledger")
    led_st["pools"] = {
        "silver": {"name": "现银", "initial": 100, "current": 50, "unit": "两"}
    }
    common.atomic_write_text(book / "state" / "ledger.json", json.dumps(led_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n陆沉舟当场掏出五百两银子，买下了这本古籍。\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    assert res["soft_count"] >= 1
    found = any(c["probe"] == "amount_ledger" and "500" in c["title"] for c in res["candidates"])
    assert found, f"探针未检出超额支出: {res['candidates']}"


def test_audit_secret_leakage(consistency_book):
    """注入 5：KNO 未公开秘密由不知情者在对话中道出 → audit 探针抓出 candidate_soft。"""
    book = consistency_book
    lines_st = state.load_state(book, "lines")
    lines_st["knowledge"] = [
        {
            "id": "KNO-001",
            "secret": "黑煞宗暗藏七星古镜",
            "holders": ["陆沉舟"],
            "plant_ch": 1,
            "target_ch": 3,
            "status": "Concealed"
        }
    ]
    common.atomic_write_text(book / "state" / "lines.json", json.dumps(lines_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n赵六冷声道：“黑煞宗暗藏七星古镜，这件事满城皆知！”\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    assert res["soft_count"] >= 1
    found = any(c["probe"] == "secret_leakage" and "KNO-001" in c["title"] for c in res["candidates"])
    assert found, f"探针未检出知情差泄露: {res['candidates']}"


def test_audit_alias_drift(consistency_book):
    """注入 6：正文出现与既有实体形近的新名且未注册别名 → alias_drift 探针抓出 candidate_soft。"""
    book = consistency_book
    ents_st = state.load_state(book, "entities")
    ents_st["entries"].append({
        "name": "陆九渊",
        "type": "person",
        "status": "active",
        "summary": "剑阁长老"
    })
    common.atomic_write_text(book / "state" / "entities.json", json.dumps(ents_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n陆九远负手而立，神色凝重。陆九远沉思片刻，缓缓拔剑出鞘。\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    assert res["soft_count"] >= 1
    found = any(c["probe"] == "alias_drift" and "陆九远" in c["title"] for c in res["candidates"])
    assert found, f"探针未检出别名漂移: {res['candidates']}"


def test_checks_locked_quota_exceeded(consistency_book):
    """注入 7：不可逆事实超出 15 条配额 → checks 报警 locked_quota_exceeded。"""
    book = consistency_book
    entries = []
    for i in range(1, 17):
        entries.append({
            "id": f"LOCK-{i:03d}",
            "fact": f"测试不可逆事实第 {i} 条",
            "kind": "irreversible_action",
            "since_ch": "ch_001",
            "quote": "测试原文佐证"
        })
    common.atomic_write_text(book / "state" / "locked.json", json.dumps({"entries": entries}, ensure_ascii=False))

    report = checks.run_checks(book)
    warnings = [w["code"] for w in report["warnings"]]
    assert "locked_quota_exceeded" in warnings, f"未触发 locked_quota_exceeded: {warnings}"


def test_checks_locked_life_status_conflict(consistency_book):
    """注入 8：locked 死亡事实但实体 life_status 为 alive → checks 报错 locked_life_status_conflict。"""
    book = consistency_book
    locked_st = {
        "entries": [
            {
                "id": "LOCK-001",
                "fact": "陆掌柜已确认死亡",
                "kind": "death",
                "since_ch": "ch_001",
                "quote": "陆掌柜断气"
            }
        ]
    }
    common.atomic_write_text(book / "state" / "locked.json", json.dumps(locked_st, ensure_ascii=False))

    ents_st = state.load_state(book, "entities")
    ents_st["entries"].append({
        "name": "陆掌柜",
        "type": "person",
        "status": "active",
        "life_status": "alive",
        "summary": "活着"
    })
    common.atomic_write_text(book / "state" / "entities.json", json.dumps(ents_st, ensure_ascii=False))

    report = checks.run_checks(book)
    errors = [e["code"] for e in report["errors"]]
    assert "locked_life_status_conflict" in errors, f"未触发 locked_life_status_conflict: {errors}"


def test_checks_locked_injection_missing(consistency_book):
    """注入 9：已生效 locked 事实但 beats 缺少不可逆事实小节 → checks 报错 locked_injection_missing。"""
    book = consistency_book
    locked_st = {
        "entries": [
            {
                "id": "LOCK-001",
                "fact": "第一章老掌柜死亡",
                "kind": "death",
                "since_ch": "ch_001",
                "quote": "老掌柜双目圆睁气绝"
            }
        ]
    }
    common.atomic_write_text(book / "state" / "locked.json", json.dumps(locked_st, ensure_ascii=False))

    # ch_002 beats 不包含不可逆事实台账
    b2 = book / "outlines" / "vol_01" / "beats" / "ch_002.md"
    text = b2.read_text(encoding="utf-8")
    assert "LOCK" not in text and "不可逆事实" not in text

    report = checks.run_checks(book)
    errors = [e["code"] for e in report["errors"]]
    assert "locked_injection_missing" in errors, f"未触发 locked_injection_missing: {errors}"
