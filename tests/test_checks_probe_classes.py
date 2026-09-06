"""run_checks 探针类断言（直接注入、逐码判定）。

覆盖来源：QA 收尾清单「form 探针类断言未做」——此前对 checks 的 form/words/
drift 家族只有「整书干净」的间接断言，没有「注入一处 → 精确命中某 code」的
类级回归。本文件给每支探针一个最小扰动：基准书先验 E0（errors/warnings 全
干净），每次只改一个维度，断言命中且只命中预期的 code/级别（errors vs
warnings vs infos），防止探针漂移或误报面扩大。
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from engine import checks

# run_checks 输出键 → 期望级别
CLASS = {"errors": "errors", "warnings": "warnings", "infos": "infos"}


def _codes(report: dict, level: str) -> set[str]:
    return {e["code"] for e in report[level]}


@pytest.fixture(scope="module")
def probe_base(ws_root) -> Path:
    from conftest import build_book

    return build_book(ws_root, "bk_probe_cls", chapters=3, words=(600, 900))


@pytest.fixture
def book(probe_base, ws_root) -> Path:
    """每用例从干净基准整树拷贝，互不污染。"""
    target = ws_root / f"bk_probe_run_{next(_cnt)}"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(probe_base, target)
    return target


_cnt = iter(range(1000))


def _beat(book: Path, n: int) -> Path:
    return book / "outlines" / "vol_01" / "beats" / f"ch_{n:03d}.md"


def _final(book: Path, n: int) -> Path:
    return book / "manuscript" / "vol_01" / "final" / f"ch_{n:03d}.md"


def _patch_fm(book: Path, n: int, pat: str, repl: str) -> None:
    p = _beat(book, n)
    txt = p.read_text(encoding="utf-8")
    new, cnt = re.subn(pat, repl, txt, count=1, flags=re.M)
    assert cnt == 1, f"未命中 {pat!r} in {p.name}"
    p.write_text(new, encoding="utf-8")


def test_baseline_clean(book):
    rep = checks.run_checks(book)
    assert rep["ok"] is True, f"基准书应干净：{rep['errors']}{rep['warnings']}"
    assert not _codes(rep, "errors") and not _codes(rep, "warnings")


def test_beats_fm_extra_keys_is_error(book):
    _patch_fm(book, 1, r"^vol: vol_01$", "vol: vol_01\nbogus_audit_key: 2026-09-06")
    rep = checks.run_checks(book)
    assert "beats_fm_extra_keys" in _codes(rep, "errors")
    assert "bogus_audit_key" in str(rep["errors"])


def test_beats_missing_form_is_error(book):
    _patch_fm(book, 2, r"^form: .*$", "form: ")
    rep = checks.run_checks(book)
    assert "beats_missing_form" in _codes(rep, "errors")


def test_beats_form_repeat_without_reason(book):
    # ch_002 抄 ch_001 的 form 且不给 form_reason → error
    _patch_fm(book, 2, r"^form: .*$", "form: 暗流汇聚")
    rep = checks.run_checks(book)
    codes = _codes(rep, "errors")
    assert "beats_form_repeat_without_reason" in codes
    # 给了 form_reason 即放行（同 form 重复本身合法，缺解释才拦）
    _patch_fm(book, 2, r"^form: 暗流汇聚$", "form: 暗流汇聚\nform_reason: 承上章余波，正面摊牌")
    rep = checks.run_checks(book)
    assert "beats_form_repeat_without_reason" not in _codes(rep, "errors")


def test_words_band_crowded_relative_threshold(book):
    # ch_002 下限 600 → 610：Δ10 < max(50, 上一章下限 5% = 30) → 提示（P2-9 相对阈值）
    _patch_fm(book, 2, r"^words: 600-900$", "words: 610-900")
    rep = checks.run_checks(book)
    assert "words_band_crowded" in _codes(rep, "warnings")
    # 实质跳档（600 → 700）不再误报
    _patch_fm(book, 2, r"^words: 610-900$", "words: 700-900")
    rep = checks.run_checks(book)
    assert "words_band_crowded" not in _codes(rep, "warnings")


def test_style_notes_copy_is_warning(book):
    from engine import common

    # 让 ch_003 的 style_notes 与上一章 ch_002 完全相同（动态取，防样式表变更失配）
    v2 = common.parse_front_matter(_beat(book, 2).read_text(encoding="utf-8"))["style_notes"]
    _patch_fm(book, 3, r"^style_notes: .*$", f"style_notes: {v2}")
    rep = checks.run_checks(book)
    assert "style_notes_copy" in _codes(rep, "warnings")


def test_word_band_breach_and_beats_words_unmet(book):
    # final ch_001 砍到 300 字：显著低于 project words_target 下带 15% 容差 + 细纲自报带
    p = _final(book, 1)
    p.write_text("# 第1章 测试标题\n\n陆沉舟抬头看了看天，没说话。\n", encoding="utf-8")
    rep = checks.run_checks(book)
    w = _codes(rep, "warnings")
    assert "word_band_breach" in w, f"warnings={w}"
    assert "beats_words_unmet" in w, f"细纲自报带失守未报：warnings={w}"


def test_beats_words_drift_info_only(book):
    # 细纲自报带收窄到 500-700（project 带仍 600-900）：final 759 字在自报带外 15% 内 → info
    _patch_fm(book, 1, r"^words: 600-900$", "words: 500-700")
    rep = checks.run_checks(book)
    assert "beats_words_drift" in _codes(rep, "infos")
    assert "word_band_breach" not in _codes(rep, "warnings")


def test_final_gap_chapters_detected(book):
    # 删掉 final ch_002 → 封存链断裂提示（不删 beats，聚焦 final 侧缺口）
    p = _final(book, 2)
    p.unlink()
    rep = checks.run_checks(book)
    codes = _codes(rep, "warnings") | _codes(rep, "errors")
    assert "final_gap_chapters" in codes, f"缺章未检出：{codes}"


def test_encoding_replacement_chars_detected(book):
    p = _final(book, 3)
    txt = p.read_text(encoding="utf-8")
    p.write_text(txt + "\n\u00ef\u00bf\u00bd\ufffd坏字符\n", encoding="utf-8")
    rep = checks.run_checks(book)
    assert "encoding_replacement_chars" in _codes(rep, "warnings")
