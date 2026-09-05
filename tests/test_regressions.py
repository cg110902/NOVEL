"""本会话修复的缺陷的回归锚定测试。

这些用例的存在理由不是「覆盖功能」，而是「钉住具体某次修复」。每条都写明它对应哪个
缺陷编号、缺陷当时是什么表现——因为这类 bug 的共同点是修完之后看起来理所当然，
一旦有人「顺手重构」把它改回去，没有任何痕迹提示那是回归。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import build_book


# ---------------------------------------------------------------------------
# P2-12：proposal auto 的场景过滤分支是死代码，** 残留漏进状态字段
# ---------------------------------------------------------------------------
@pytest.fixture
def book_scenes(ws_root) -> Path:
    """带真实场景结构的书：被读取的那个 section 里同时有空标签行与 ** 包裹的正文行。

    注意必须写进「## 核心冲突与场景脉络」这一节，而不是新起一节——
    `common.md_section` 遇到第一个匹配标题就开始收集、遇到下一个 `##` 即 break，
    所以追加在其后的新节根本不会被读到（我第一版就是这么写错的，测试测了个空）。
    """
    book = build_book(ws_root, "bk_scenes", chapters=1)
    beats = book / "outlines" / "vol_01" / "beats" / "ch_001.md"
    text = beats.read_text(encoding="utf-8")
    anchor = "- **本章核心戏剧目标**：第1章把主角的算盘和底线立住。\n"
    assert anchor in text, "夹具锚点未命中，_beats 模板已变"
    text = text.replace(anchor, anchor + (
        "- **场景脉络**：\n"
        "  - **场景一：灶台前验灯**\n"
        "    - 🎬 **内容**：天刚亮，陆沉舟蹲在灶台前，把灯翻过来看灯底。\n"
    ), 1)
    beats.write_text(text, encoding="utf-8")
    return book


def test_proposal_auto_strips_bold_markers(cli, book_scenes):
    """P2-12 主断言：current.situation 里不得残留 ** 粗体标记。

    缺陷成因：_cmd_proposal_auto 里 `ln.strip().lstrip("-*· ")` 的字符集含 `*`，
    会把行首 ** 一并吃掉，于是紧随其后的 `s.startswith("**内容")` 永远不可能命中
    ——该过滤分支自始即是死代码。后果是尾部 ** 漏进状态字段，实测产出过
    situation = "本章核心戏剧目标**：把「无主空灯」…"。
    """
    r = cli("proposal", "auto", "ch_001", "-w", book_scenes, "--json")
    assert not r.crashed, r.err[-400:]
    assert r.code == 0, r.out[-400:]
    d = r.json()
    situation = d["current"]["situation"]
    assert "**" not in situation, f"situation 残留粗体标记：{situation!r}"


def test_proposal_auto_drops_empty_label_lines(cli, book_scenes):
    """P2-12 连带缺口：空标签行（冒号后无内容）不得被当成场景正文收进来。

    修复前细纲里的 `- **场景脉络**：` 会被收进 beats_scenes，在 situation 尾部
    留下「；场景脉络：」这样的碎片。
    """
    r = cli("proposal", "auto", "ch_001", "-w", book_scenes, "--json")
    assert r.code == 0, r.out[-400:]
    situation = r.json()["current"]["situation"]
    assert not situation.rstrip().endswith(("：", ":")), f"尾部残留空标签碎片：{situation!r}"
    assert "场景脉络：" not in situation, f"空标签被当成正文：{situation!r}"


def test_proposal_auto_keeps_real_scene_prose(cli, book_scenes):
    """P2-12 的反向保护：修死代码时不得把真正的场景正文一起删掉。

    细纲里 `- 🎬 **内容**：天刚亮，陆沉舟蹲在灶台前…` 恰恰是真正的场景正文。
    把死代码「复活」成一个按前缀整行跳过的过滤器，会让 situation 丢掉实际内容
    ——那是无人要求的行为变更，比原缺陷更糟。
    """
    r = cli("proposal", "auto", "ch_001", "-w", book_scenes, "--json")
    assert r.code == 0, r.out[-400:]
    situation = r.json()["current"]["situation"]
    assert "陆沉舟" in situation, f"场景正文被误删：{situation!r}"


# ---------------------------------------------------------------------------
# P2-3：别名建议必须指向规范实体名，否则给出的手势执行即失败
# ---------------------------------------------------------------------------
def test_alias_suggestion_points_at_canonical_entity(cli, book):
    """P2-3 后续修正：evidence.names 的 known 集混装规范名与别名，host 可能落到别名上。

    缺陷表现：「周叔」被判给「周大年」，而「周大年」只是「老周头」的别名，据此建议的
    `state set 'entities.周大年.aliases'` 会被引擎正确拒绝（实体不存在，拒绝猜测）。
    那等于把「无处方可采纳」修成了「有处但跑不通」，比原缺陷更具误导性。

    注册实体走提案通道而非 `state set`——后者对不存在的实体拒绝猜测，那是正确行为。
    """
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001", "operation_id": "ch_001.test.alias",
        "entities": [{"name": "老周头", "type": "person",
                      "summary": "夹具实体", "aliases": ["周大年"]}],
    }
    p = inbox / "ch_001.json"
    p.write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        r = cli("sync", "ch_001", "-w", book)
        assert r.code == 0, f"夹具 sync 失败：{r.out[-500:]}"
    finally:
        p.unlink(missing_ok=True)

    # 台账里 周大年 是别名、老周头 是规范名
    # state get --json 的信封是 {"target": ..., "value": {...}}，实体在 value.entries 里
    ents = cli("state", "get", "entities", "-w", book, "--json")
    assert ents.code == 0, ents.out[-300:]
    entries = ents.json()["value"]["entries"]
    registered = {e["name"] for e in entries}
    assert "老周头" in registered, registered
    assert "周大年" not in registered, "周大年 应为别名而非规范实体名"

    out = cli("evidence", "names", "-w", book, "--json")
    assert out.code == 0, out.out[-300:]
    for v in out.json()["known_variants"]:
        for host in v["of"]:
            assert host in registered, (
                f"变体 {v['name']!r} 被指向 {host!r}，但它不是规范实体名"
                f"（已注册：{sorted(registered)}）")


# ---------------------------------------------------------------------------
# P0-3：资源池键名打错必须拒收（不能静默按 0 处理）
# ---------------------------------------------------------------------------
def test_pool_typo_is_rejected_not_silently_zeroed(cli, book):
    """P0-3 核心：initial 打成 intial 必须整案拒收。

    为什么是 P0 而非 P3：资源池的 initial 是整本书账本的初始条件。一处键名笔误
    就等于悄悄改掉全书余额基准，且 ledger recompute 也查不出来——它只校验余额与
    流水是否吻合，不校验期初本身是否写错。
    """
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prop = {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001", "operation_id": "ch_001.test.typo",
        "ledger": {"pools": {"typo_pool": {"name": "笔误池", "unit": "个",
                                           "intial": 247}}},
    }
    p = inbox / "ch_001.json"
    p.write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        r = cli("proposal", "check", "ch_001", "-w", book)
        assert r.code != 0, "键名打错被静默接受——账本基准会被悄悄污染"
        assert "未知字段" in r.out or "initial" in r.out, r.out[-400:]
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# P1-4：cockpit 与 status 对「下一章」必须同口径
# ---------------------------------------------------------------------------
def test_cockpit_and_status_agree_on_next_chapter(cli, book):
    """P1-4：一份游离的未来章 beats 曾会劫持 cockpit 指针，且与 status 结论矛盾。"""
    ck = cli("cockpit", "-w", book, "--json")
    assert ck.code == 0, ck.out[-300:]
    target = ck.json()["target_chapter"]

    st = cli("status", "-w", book)
    assert st.code == 0, st.out[-300:]
    assert target in st.out, (
        f"cockpit 指向 {target}，但 status 未提及；两入口口径不一致")


def test_stray_future_beats_does_not_hijack_pointer(cli, book):
    """P1-4 主断言：游离的未来章 beats 不得改变 cockpit 的推进指针。"""
    before = cli("cockpit", "-w", book, "--json").json()["target_chapter"]
    # 写一份远超当前进度的细纲（ch_099），它不应劫持指针
    stray = book / "outlines" / "vol_01" / "beats" / "ch_099.md"
    stray.write_text(
        "---\nchapter: ch_099\nvol: vol_01\nform: 余波荡漾\npov: 陆沉舟·视角\n"
        "words: 600-900\ntension_curve: 起 → 收\ntension_score: 5\n"
        "stage_mode: Simmering\nstyle_notes: 冷叙述\neditor_extra: 无。\n---\n\n"
        "## 核心冲突与场景脉络\n\n- 游离细纲，不应劫持指针。\n",
        encoding="utf-8")
    try:
        after = cli("cockpit", "-w", book, "--json")
        assert after.code == 0, after.out[-300:]
        assert after.json()["target_chapter"] == before, (
            f"游离 ch_099 劫持了指针：{before} → {after.json()['target_chapter']}")
    finally:
        stray.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# PI-2：细纲自报字数带必须有强制力
# ---------------------------------------------------------------------------
def test_beats_words_drift_reported(cli, book):
    """PI-2：定稿字数落在细纲自报带之外时，check 必须报出来（而非静默通过）。

    这是「beats 自报字数带无强制力」的修复。修复前 Editor 系统性欠字三章而无人察觉。
    """
    final = book / "manuscript" / "vol_01" / "final" / "ch_001.md"
    original = final.read_text(encoding="utf-8")
    try:
        # 把定稿削到远低于自报带 [600,900] 的长度
        final.write_text("# 第1章 测试标题\n\n陆沉舟把灯收了。\n", encoding="utf-8")
        r = cli("check", "-w", book, "--json")
        assert not r.crashed, r.err[-300:]
        codes = [x["code"] for x in r.json()["errors"] + r.json()["warnings"]
                 + r.json()["infos"]]
        assert "beats_words_unmet" in codes or "beats_words_drift" in codes, (
            f"定稿严重欠字却未报字数偏差：{codes}")
    finally:
        final.write_text(original, encoding="utf-8")


def test_clean_book_reports_no_drift(cli, book):
    """反向保护：字数达标时不得误报。"""
    r = cli("check", "-w", book, "--json")
    assert r.code == 0, r.out[-300:]
    codes = [x["code"] for x in r.json()["errors"] + r.json()["warnings"]
             + r.json()["infos"]]
    assert "beats_words_unmet" not in codes and "beats_words_drift" not in codes, codes


# ---------------------------------------------------------------------------
# 基线不变量
# ---------------------------------------------------------------------------
def test_fresh_book_check_is_clean(cli, book):
    """夹具书必须 check 全绿——否则后续所有断言都分不清是代码回归还是夹具不干净。"""
    r = cli("check", "-w", book, "--json")
    assert not r.crashed, r.err[-400:]
    assert r.code == 0, r.out[-600:]
    d = r.json()
    assert d["stats"]["errors"] == 0
    assert d["stats"]["warnings"] == 0
    assert d["stats"]["infos"] == 0, [x["code"] for x in d["infos"]]


def test_errcodes_registry_has_new_codes(cli):
    """本会话新增的 6 个错误码必须都在注册表里（漏注册 = 闸门报了码但查不到释义）。"""
    r = cli("errcodes", "--json")
    assert r.code == 0, r.out[-300:]
    d = r.json()
    registered = {c["code"] for c in d["codes"]}
    for code in ("ledger_tx_order", "ledger_arith_broken", "amount_arith_unverified",
                 "latin_residue", "beats_words_unmet", "beats_words_drift"):
        assert code in registered, f"{code} 未注册"
