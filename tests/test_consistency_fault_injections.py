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


# ---------------------------------------------------------------------------
# 回归 10~13：audit 探针口径修复（QA 深度审读发现）
#   10. 死亡当章正文本身带死亡叙事（尸体/被刺）不再误报「已亡角色活跃出场」；
#   11. 误解 parties 在 v2 schema 是字符串，探针须按整名解析而非逐字切片；
#   12. 账本余额键是 current（非 balance），余额内的正常支出不得误报超额；
#   13. secret_leakage 说话人解析应落到注册实体/别名（「老赵拍着桌子道」→ 老赵）。
# ---------------------------------------------------------------------------

def test_audit_no_false_positive_on_death_chapter(consistency_book):
    """注入 10：死亡当章正文 = 死亡叙事（含 尸体/被刺），audit 不得报 hard。"""
    book = consistency_book
    locked_st = {
        "entries": [
            {
                "id": "LOCK-001",
                "fact": "陆掌柜已于 ch_001 在城南瓮城被杀身亡",
                "kind": "death",
                "since_ch": "ch_001",
                "quote": "陆掌柜倒在灯楼下",
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

    # 死亡当章：正文在报道死亡本身（尸体/被刺 同句出现）
    f1 = book / "manuscript" / "vol_01" / "final" / "ch_001.md"
    orig = f1.read_text(encoding="utf-8")
    f1.write_text(orig + "\n\n陆掌柜是灯司的巡灯使，昨夜在城南瓮城被刺，尸体倒在灯楼之下。\n",
                  encoding="utf-8")

    res = audit.run_audit(book, "ch_001")
    assert res["hard_count"] == 0, f"死亡当章误报硬矛盾: {res['candidates']}"

    # 后一章若死者真“活人登场”（无死亡叙事词），仍必须报 hard
    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    f2.write_text(orig + "\n\n陆掌柜大步流星走进酒肆，端起酒碗一饮而尽。\n", encoding="utf-8")
    res2 = audit.run_audit(book, "ch_002")
    assert res2["hard_count"] >= 1, f"死亡后活人出场未检出: {res2['candidates']}"


def test_audit_misunderstanding_parties_string_semantics(consistency_book):
    """注入 11：parties 为字符串「张彪与李玄」时按整名取双方，描述不得出现单字。"""
    book = consistency_book
    lines_st = state.load_state(book, "lines")
    lines_st["misunderstandings"] = [
        {
            "id": "MIS-001",
            "parties": "张彪与李玄",
            "content": "张彪误以为李玄是内鬼",
            "truth": "李玄是清白的",
            "target_ch": 6,
            "level": 1,
            "status": "Active"
        }
    ]
    common.atomic_write_text(book / "state" / "lines.json", json.dumps(lines_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n张彪与李玄并肩作战，将贼人挡在山门之外。\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    hits = [c for c in res["candidates"] if c["probe"] == "cognition_stubs"]
    assert hits, f"未检出误解协同: {res['candidates']}"
    desc = hits[0]["description"]
    assert "张彪" in desc and "李玄" in desc, f"parties 未按整名解析: {desc}"
    assert "角色「张」与「彪」" not in desc, f"parties 仍被逐字切片: {desc}"


def test_audit_amount_uses_pool_current_balance(consistency_book):
    """注入 12：池余额读 current（初始 100 / 现 50）：50 内支出不报，500 报。"""
    book = consistency_book
    led_st = state.load_state(book, "ledger")
    led_st["pools"] = {
        "silver": {"name": "现银", "initial": 100, "current": 50, "unit": "两"}
    }
    common.atomic_write_text(book / "state" / "ledger.json", json.dumps(led_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    f2.write_text(orig + "\n\n陆沉舟掏出三十两银子付了房钱，又花了五百两银子买马。\n",
                  encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    hits = [c for c in res["candidates"] if c["probe"] == "amount_ledger"]
    assert len(hits) == 1, f"余额内支出被误报或漏报: {hits}"
    assert "500" in hits[0]["title"], f"应只报 500 两超额: {hits[0]['title']}"


def test_audit_secret_leakage_speaker_is_entity_alias(consistency_book):
    """注入 13：泄露台词说话人解析到实体别名（老赵），而不是「老赵拍着桌子」。"""
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
    ents_st = state.load_state(book, "entities")
    ents_st["entries"].append({
        "name": "赵六",
        "type": "person",
        "status": "active",
        "aliases": ["老赵"],
        "summary": "路人甲"
    })
    common.atomic_write_text(book / "state" / "entities.json", json.dumps(ents_st, ensure_ascii=False))

    f2 = book / "manuscript" / "vol_01" / "final" / "ch_002.md"
    orig = f2.read_text(encoding="utf-8")
    tampered = orig + "\n\n老赵拍着桌子道：“黑煞宗暗藏七星古镜，这件事满城皆知！”\n"
    f2.write_text(tampered, encoding="utf-8")

    res = audit.run_audit(book, "ch_002")
    hits = [c for c in res["candidates"] if c["probe"] == "secret_leakage"]
    assert hits, f"未检出泄露: {res['candidates']}"
    title = hits[0]["title"]
    assert "老赵" in title, f"说话人应解析为别名「老赵」: {title}"
    assert "拍着桌子" not in title, f"说话人混入动作描写: {title}"


# ---------------------------------------------------------------------------
# 回归 14~17：state.apply_proposal 合并闸门语义（QA 深读 engine/state.py 发现）
#   14. 单提案内两条逐字段相同流水 = 重复，第二条跳过并告警（禁止静默双计）；
#   15. 崩溃重放：与既有流水同内容的提案重提 = 跳过，余额不变；
#   16. 既有实体 type 被跨界改写（person→item）→ advisory 警告（不再静默）；
#   17. cognition 空内容条目/未知条目退役 → 警告跳过，绝不落盘空行（不静默吞）。
# ---------------------------------------------------------------------------

SCHEMA_V2 = "novel-studio.state-mutation/v2"


def _prop(ch: str, op: str, **over) -> dict:
    p = {"schema": SCHEMA_V2, "chapter": ch, "operation_id": op, "current": {},
         "entities": [], "lines": [], "timeline": {}, "ledger": {},
         "synopsis": {}, "locked": [], "cognition": []}
    p.update(over)
    return p


def _silver_tx(ch: str, delta: int, subject: str, note: str = "") -> dict:
    tx = {"chapter": ch, "pool": "silver", "delta": delta, "type": "expense",
          "subject": subject}
    if note:
        tx["note"] = note
    return tx


def _seed_silver_pool(book: Path, initial: int = 100) -> None:
    led = state.load_state(book, "ledger")
    led["pools"]["silver"] = {"name": "现银", "unit": "两", "initial": initial,
                              "current": initial}
    state.save_state(book, "ledger", led)


def _balance(book: Path) -> int:
    return state.load_state(book, "ledger")["pools"]["silver"]["current"]


def test_ledger_intra_proposal_duplicate_tx_not_double_counted(consistency_book):
    """注入 14：同提案两条逐字段相同流水 → 第二条跳过（♻️ 告警），余额只扣一次。"""
    book = consistency_book
    _seed_silver_pool(book)
    prop = _prop("ch_002", "op.dup14", ledger={"transactions": [
        _silver_tx("ch_002", -20, "买情报", "城西"),
        _silver_tx("ch_002", -20, "买情报", "城西"),
    ]})
    rep = state.apply_proposal(book, prop)
    assert not rep["errors"], rep["errors"][:3]
    assert any("重复" in w or "重放" in w for w in rep["warnings"]), rep["warnings"]
    assert _balance(book) == 80, f"双计了：{_balance(book)}"
    txs = state.load_state(book, "ledger")["transactions"]
    assert sum(1 for t in txs if t.get("subject") == "买情报") == 1


def test_ledger_crash_replay_identical_tx_keeps_balance(consistency_book):
    """注入 15：已入账流水的同内容提案重提（崩溃重放）→ 跳过，余额与笔数不变。"""
    book = consistency_book
    _seed_silver_pool(book)
    first = _prop("ch_002", "op.first15", ledger={"transactions": [
        _silver_tx("ch_002", -20, "买情报", "城西")]})
    assert not state.apply_proposal(book, first)["errors"]
    assert _balance(book) == 80

    replay = _prop("ch_002", "op.replay15", ledger={"transactions": [
        _silver_tx("ch_002", -20, "买情报", "城西")]})
    rep = state.apply_proposal(book, replay)
    assert not rep["errors"], rep["errors"][:3]
    # 内容哈希幂等（op 不同但内容同）先于流水级重放保护命中
    assert any(k in w for w in rep["warnings"] for k in ("重复", "重放", "已应用过")), rep["warnings"]
    assert _balance(book) == 80
    assert len(state.load_state(book, "ledger")["transactions"]) == 1


def test_ledger_same_amount_distinct_note_applies_twice(consistency_book):
    """注：同金额同 subject 但只要 note 不同即视为两笔独立交易——都入账。"""
    book = consistency_book
    _seed_silver_pool(book)
    prop = _prop("ch_002", "op.two16", ledger={"transactions": [
        _silver_tx("ch_002", -5, "买茶", "东市"),
        _silver_tx("ch_002", -7, "买茶", "西市"),
    ]})
    rep = state.apply_proposal(book, prop)
    assert not rep["errors"]
    assert not rep["warnings"], f"误杀独立交易：{rep['warnings']}"
    assert _balance(book) == 88


def test_entity_type_flip_emits_advisory_warning(consistency_book):
    """注入 16：既有实体 type 跨界改写（人→器物）出 warning，不再静默。"""
    book = consistency_book
    ents = state.load_state(book, "entities")
    ents["entries"].append({"name": "甲掌柜", "type": "person", "status": "active",
                            "summary": "人"})
    state.save_state(book, "entities", ents)
    prop = _prop("ch_002", "op.flip17", entities=[
        {"name": "甲掌柜", "type": "item", "summary": "器物？"}])
    rep = state.apply_proposal(book, prop)
    assert not rep["errors"], rep["errors"][:2]
    assert any("类别" in w for w in rep["warnings"]), rep["warnings"]
    ents2 = state.load_state(book, "entities")
    got = next(e for e in ents2["entries"] if e["name"] == "甲掌柜")
    assert got["type"] == "item"


def test_cognition_empty_entries_and_unknown_retire_noop_with_warning(consistency_book):
    """注入 17：cognition 空内容条目/未知条目退役 → 警告跳过，台账不落空行。"""
    book = consistency_book
    prop = _prop("ch_002", "op.cog18", cognition=[
        {"id": "COG-777", "action": "retire", "character": "查无此人"},
        {"id": "COG-778", "character": "陆沉舟", "content": "   ", "kind": "fact"},
        {"id": "COG-779", "character": "陆沉舟", "kind": "fact",
         "content": "陆沉舟怀疑甲掌柜", "since_ch": "ch_002"},
    ])
    rep = state.apply_proposal(book, prop)
    assert not rep["errors"], rep["errors"][:2]
    warns = " | ".join(rep["warnings"])
    assert "退役忽略" in warns or "不存在" in warns, warns
    assert "无效跳过" in warns, warns
    cog = state.load_state(book, "cognition")["entries"]
    ids = [e.get("id") for e in cog]
    assert "COG-777" not in ids and "COG-778" not in ids
    assert "COG-779" in ids and [e for e in cog if e["id"] == "COG-779"][0]["content"]
