"""提案（proposal）schema 契约测试：写通道 state/inbox/ 的收/拒边界。

覆盖来源：仓库外的故障注入套件 fi_b.py（27 例）移植进仓库。

判定口径
--------
`proposal check <章>` 退出码非 0 = 拒收（REJECT），0 = 放行（ACCEPT）。
每条用例都断言精确的收/拒方向——提案是 AI 写状态的唯一合法通道，这里放宽一格，
下游账本与线索台账就会被污染，而污染往往要到很多章之后才显形。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SCHEMA = "novel-studio.state-mutation/v2"


@pytest.fixture
def book4(ws_root) -> Path:
    """四章的书。用 ch_004 作提案章，好让「流水记到 ch_001」这类跨章注入有意义。"""
    from conftest import build_book
    return build_book(ws_root, "bk_prop", chapters=4)


@pytest.fixture
def registered(book4, cli):
    """先把 ch_001 落盘，使 synopsis 里存在「已注册章」，好测跨章梗概修订的放行侧。

    不 sync 的话 synopsis.chapters 是空的，「改已注册章」这条就只能测拒收侧，
    等于只验证了一半。
    """
    inbox = book4 / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prop = {
        "schema": SCHEMA, "chapter": "ch_001", "operation_id": "ch_001.test.reg",
        "entities": [{"name": "测试甲", "type": "person", "summary": "夹具实体"}],
        "synopsis": {"title": "第1章 测试标题", "text": "第1章梗概。"},
        "current": {"present_characters": ["陆沉舟"], "situation": "第1章收束。"},
    }
    (inbox / "ch_001.json").write_text(
        json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
    r = cli("sync", "ch_001", "-w", book4)
    assert r.code == 0, f"夹具 sync ch_001 失败：{r.out[-600:]}{r.err[-300:]}"
    return book4


def check(cli, book, proposal: dict, name: str = "ch_004.json"):
    """写提案到 inbox 后跑 proposal check，返回 CliResult。用完即删，避免用例互相污染。"""
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    p = inbox / name
    p.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        ch = proposal.get("chapter", name.split(".")[0])
        return cli("proposal", "check", ch, "-w", book)
    finally:
        p.unlink(missing_ok=True)


def base(ch: str = "ch_004") -> dict:
    return {"schema": SCHEMA, "chapter": ch, "operation_id": f"{ch}.test.base"}


# ---------------------------------------------------------------------------
# 1. 实体字段契约
# ---------------------------------------------------------------------------
def test_entity_rejects_description_field(cli, book4):
    """合法字段是 summary，不是 description。"""
    d = base()
    d["entities"] = [{"name": "测试甲", "type": "person", "description": "用了 description"}]
    assert check(cli, book4, d).code != 0


def test_entity_rejects_illegal_type(cli, book4):
    """type ∈ person|place|faction|item|other，character 不合法。"""
    d = base()
    d["entities"] = [{"name": "测试甲", "type": "character", "summary": "非法 type"}]
    assert check(cli, book4, d).code != 0


def test_entity_rejects_unknown_field(cli, book4):
    """实体对象是 extra=forbid，多一个键即整案拒收。"""
    d = base()
    d["entities"] = [{"name": "测试甲", "type": "person",
                      "summary": "带未知字段", "power_level": "灯徒"}]
    assert check(cli, book4, d).code != 0


def test_entity_accepts_minimal(cli, book4):
    d = base()
    d["entities"] = [{"name": "测试甲", "type": "person"}]
    assert check(cli, book4, d).code == 0


# ---------------------------------------------------------------------------
# 2. current 未登记实体闸门
# ---------------------------------------------------------------------------
def test_current_rejects_unregistered_character(cli, book4):
    d = base()
    d["current"] = {"present_characters": ["根本不存在的人"]}
    assert check(cli, book4, d).code != 0


def test_current_accepts_registered_character(cli, registered):
    d = base()
    d["current"] = {"present_characters": ["测试甲"]}
    assert check(cli, registered, d).code == 0


# ---------------------------------------------------------------------------
# 3. lines 动作 / 字段契约
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("line,why", [
    ({"id": "GUN-900", "kind": "foreshadow", "action": "plant", "name": "无target"},
     "GUN plant 必须给 target_ch"),
    ({"id": "GUN-900", "kind": "foreshadow", "action": "plant",
      "name": "字符串数字", "target_ch": "21"},
     "target_ch 不接受裸字符串数字"),
    ({"id": "GUN-900", "kind": "foreshadow", "action": "plant",
      "name": "无补零", "target_ch": "ch_7"},
     "账本字段只收规范 ch_NNN，ch_7 须先归一"),
    ({"id": "KNO-900", "kind": "knowledge", "action": "plant", "target_ch": 9},
     "KNO plant 必须给 secret"),
    ({"id": "KNO-900", "kind": "knowledge", "action": "remind",
      "target_ch": 9, "secret": "x"},
     "KNO 只支持 plant/update/resolve，无 remind"),
    ({"id": "MIS-900", "kind": "misunderstanding", "action": "plant",
      "content": "缺parties", "target_ch": 9},
     "MIS plant 必须给 parties"),
    ({"id": "MIS-900", "kind": "misunderstanding", "action": "plant",
      "parties": ["甲", "乙"], "content": "parties写成数组", "target_ch": 9},
     "parties 是字符串，不是数组"),
    ({"id": "MIS-900", "kind": "misunderstanding", "action": "remind",
      "target_ch": 9, "parties": "甲与乙", "content": "x"},
     "MIS 只支持 plant/escalate/resolve，无 remind"),
])
def test_line_contract_rejections(cli, book4, line, why):
    d = base()
    d["lines"] = [line]
    assert check(cli, book4, d).code != 0, why


def test_line_accepts_chinese_chapter_token(cli, book4):
    """target_ch 接受「第29章」这类写法（内部归一），与裸字符串数字不同。"""
    d = base()
    d["lines"] = [{"id": "GUN-900", "kind": "foreshadow", "action": "plant",
                   "name": "中文章号", "target_ch": "第29章"}]
    assert check(cli, book4, d).code == 0


def test_line_accepts_four_digit_id(cli, book4):
    d = base()
    d["lines"] = [{"id": "GUN-9999", "kind": "foreshadow", "action": "plant",
                   "name": "四位数ID", "target_ch": 9}]
    assert check(cli, book4, d).code == 0


# ---------------------------------------------------------------------------
# 4. ledger 闸门（含 QA P0-1 / P0-3）
# ---------------------------------------------------------------------------
def test_pool_rejects_declared_current(cli, book4):
    """余额一律由流水重算，不接受声明 current。"""
    d = base()
    d["ledger"] = {"pools": {"qa_pool": {"name": "QA池", "unit": "个",
                                         "initial": 0, "current": 5}}}
    assert check(cli, book4, d).code != 0


def test_pool_rejects_missing_initial(cli, book4):
    """P0-3：省略 initial 等于声明「从 0 开始」，会悄悄改掉账本基准，故必填。"""
    d = base()
    d["ledger"] = {"pools": {"qa_pool": {"name": "QA池", "unit": "个"}}}
    assert check(cli, book4, d).code != 0


def test_pool_rejects_misspelled_key(cli, book4):
    """P0-3 的核心用例：键名把 initial 打成 intial，必须拒收而非静默按 0 处理。

    修复前这条会静默放行，起始余额默默变成 0，而欠账类池恰恰不是从 0 开始的；
    且 ledger recompute 查不出来（它只校验余额与流水是否吻合，不校验期初）。
    """
    d = base()
    d["ledger"] = {"pools": {"qa_pool": {"name": "QA池", "unit": "个", "intial": 247}}}
    r = check(cli, book4, d)
    assert r.code != 0, "键名打错被静默接受——账本基准会被悄悄污染"


def test_pool_rejects_unknown_key(cli, book4):
    d = base()
    d["ledger"] = {"pools": {"qa_pool": {"name": "QA池", "unit": "个",
                                         "initial": 0, "power_level": "灯徒"}}}
    assert check(cli, book4, d).code != 0


def test_pool_accepts_explicit_initial(cli, book4):
    d = base()
    d["ledger"] = {"pools": {"qa_pool": {"name": "QA池", "unit": "个", "initial": 247}}}
    assert check(cli, book4, d).code == 0


def test_transaction_rejects_undeclared_pool(cli, book4):
    d = base()
    d["ledger"] = {"transactions": [{"chapter": "ch_004", "pool": "不存在的池",
                                    "delta": 1, "type": "income", "subject": "x"}]}
    assert check(cli, book4, d).code != 0


def test_transaction_rejects_misspelled_delta(cli, book4):
    """流水侧对未知键严格（delt 打错即拒）——池侧 P0-3 修复前却没有这层，两侧口径现已对齐。"""
    d = base()
    d["ledger"] = {"transactions": [{"chapter": "ch_004", "pool": "standard_currency",
                                    "delt": 1, "type": "income", "subject": "x"}]}
    assert check(cli, book4, d).code != 0


def test_transaction_rejects_cross_chapter_injection(cli, book4):
    """P0-1：流水只能记在提案所属章，禁止借新提案改写其他章的账。"""
    d = base()
    d["ledger"] = {"transactions": [{"chapter": "ch_001", "pool": "standard_currency",
                                    "delta": 1, "type": "income",
                                    "subject": "章节与提案不符"}]}
    r = check(cli, book4, d)
    assert r.code != 0, "跨章账本注入未被拒"


# ---------------------------------------------------------------------------
# 5. 顶层信封
# ---------------------------------------------------------------------------
def test_rejects_unknown_top_level_key(cli, book4):
    d = base()
    d["未知顶层键"] = 1
    assert check(cli, book4, d).code != 0


def test_requires_operation_id(cli, book4):
    """operation_id 是幂等去重的依据，缺失必须拒收。"""
    d = base()
    d.pop("operation_id")
    assert check(cli, book4, d).code != 0


def test_rejects_wrong_schema_version(cli, book4):
    d = base()
    d["schema"] = "novel-studio.state-mutation/v1"
    assert check(cli, book4, d).code != 0


def test_rejects_unpadded_chapter(cli, book4):
    """提案文件名与 chapter 字段都必须是规范 ch_NNN。"""
    d = base()
    d["chapter"] = "ch_04"
    assert check(cli, book4, d).code != 0


def test_rejects_chapter_filename_mismatch(cli, book4):
    """文件名 ch_005.json 而 chapter=ch_004，必须拒收（防提案投错章）。"""
    d = base()
    assert check(cli, book4, d, name="ch_005.json").code != 0


# ---------------------------------------------------------------------------
# 6. 跨章梗概修订 / timeline 修订
# ---------------------------------------------------------------------------
def test_synopsis_rejects_unregistered_chapter(cli, registered):
    d = base()
    d["synopsis"] = {"chapters": {"ch_099": {"title": "改未注册章", "synopsis": "x"}}}
    assert check(cli, registered, d).code != 0


def test_synopsis_accepts_registered_chapter(cli, registered):
    d = base()
    d["synopsis"] = {"chapters": {"ch_001": {"title": "第1章 改名", "synopsis": "改梗概"}}}
    assert check(cli, registered, d).code == 0


def test_timeline_rejects_unmatched_replace(cli, book4):
    d = base()
    d["timeline"] = {"events": [{"time": "不存在的时间", "event": "不存在的事件",
                                 "replace": "改"}]}
    assert check(cli, book4, d).code != 0
