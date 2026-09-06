"""提案命名契约回归：每章在途提案仅一份且文件名恰为 ch_XXX.json。

背景：技能卡曾教 Librarian 产出 `state/inbox/sweep_ch_XXX.json`，而引擎收件箱
是**单文件制**——`sync` 门闸只认 `ch_XXX.json`（inbox 或 failed/ 同名），
`_gather` 也只合并该名（及失败归档产生的 `.N` 变体）。其他命名（含
sweep_ch_*.json）会被引擎静默忽略：不与正式提案并存时不构成提案、门闸拒绝并
给出非规范命名提示；与正式提案并存时也不参与合并。

文档侧已统一回该契约（librarian SKILL / AGENTS.md / director SKILL：修补并入
在途提案；封存章修订并入下一章提案随 sync 合并）。本文件把契约钉进回归，防止
技能侧回潮或引擎侧误放宽。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SCHEMA = "novel-studio.state-mutation/v2"


def _ent_prop(ch: str, op: str, name: str, etype: str = "person") -> dict:
    return {
        "schema": SCHEMA,
        "chapter": ch,
        "operation_id": op,
        "entities": [{"name": name, "type": etype, "summary": "命名契约夹具实体"}],
    }


def _seed(ch1_prop: dict, book: Path, cli, ch: str = "ch_001") -> None:
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{ch}.json").write_text(
        json.dumps(ch1_prop, ensure_ascii=False, indent=2), encoding="utf-8")
    r = cli("sync", ch, "-w", book)
    assert r.code == 0, f"夹具 sync {ch} 失败：{r.out[-600:]}{r.err[-300:]}"


def _load_entries(book: Path) -> list[dict]:
    from engine import state

    return state.load_state(book, "entities")["entries"]


@pytest.fixture
def seed_book(ws_root, cli) -> Path:
    """2 章书 + ch_001 已正常 sync（current 已推到 ch_001）。"""
    from conftest import build_book

    book = build_book(ws_root, "bk_naming", chapters=2)
    _seed({
        "schema": SCHEMA,
        "chapter": "ch_001",
        "operation_id": "ch_001.setup.reg",
        "entities": [{"name": "陆掌柜", "type": "person", "summary": "杂货铺掌柜"}],
        "synopsis": {"title": "第1章 测试标题", "text": "第1章梗概。"},
        "current": {"present_characters": ["陆沉舟"], "situation": "第1章收束。"},
    }, book, cli)
    return book


def test_noncanonical_name_alone_is_rejected_with_hint(seed_book, cli):
    """只有 sweep_ch_002.json 而无 ch_002.json → sync 拒绝并提示规范命名。"""
    inbox = seed_book / "state" / "inbox"
    (inbox / "sweep_ch_002.json").write_text(
        json.dumps(_ent_prop("ch_002", "ch_002.librarian.4d", "灰袍老仆"),
                   ensure_ascii=False, indent=2), encoding="utf-8")
    r = cli("sync", "ch_002", "-w", seed_book)
    assert r.code == 1, "无正式提案时 sync 应业务拒收（1）而非放行"
    assert "ch_002.json" in r.out, f"应提示规范文件名：{r.out[-400:]}"
    assert "sweep_ch_002.json" in r.out, f"应点名非规范命名文件：{r.out[-400:]}"
    assert not any(e["name"] == "灰袍老仆" for e in _load_entries(seed_book)), "被拒提案不应落盘"


def test_noncanonical_name_alongside_formal_is_silently_ignored(seed_book, cli):
    """ch_002.json 正式提案 + 并存 sweep_ch_002.json → 只合并正式提案。

    引擎对非规范命名是静默忽略（不合并、不报错、不归档）；此断言防的是「技能侧
    以为 sweep 文件也生效了」的错觉——不落盘即为真实契约。
    """
    inbox = seed_book / "state" / "inbox"
    (inbox / "ch_002.json").write_text(
        json.dumps({
            "schema": SCHEMA,
            "chapter": "ch_002",
            "operation_id": "ch_002.reader.4c",
            "entities": [{"name": "甲等伙计", "type": "person", "summary": "当章登记"}],
            "synopsis": {"title": "第2章 测试标题", "text": "第2章梗概。"},
            "current": {"present_characters": ["陆沉舟"], "situation": "第2章收束。"},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    (inbox / "sweep_ch_002.json").write_text(
        json.dumps(_ent_prop("ch_002", "ch_002.librarian.4d", "灰袍老仆"),
                   ensure_ascii=False, indent=2), encoding="utf-8")
    r = cli("sync", "ch_002", "-w", seed_book)
    assert r.code == 0, f"正式提案 sync 应放行：{r.out[-400:]}{r.err[-200:]}"
    names = {e["name"] for e in _load_entries(seed_book)}
    assert "甲等伙计" in names, "正式提案实体未落盘"
    assert "灰袍老仆" not in names, "sweep 非规范文件不应被合并"
    assert (inbox / "sweep_ch_002.json").exists(), "非规范文件应原样留在 inbox（静默忽略）"
    assert not (inbox / "ch_002.json").exists(), "正式提案应已归档"
