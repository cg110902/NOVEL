"""evidence dup / prev_contrast 多卷邻前章回归。

背景：分卷各卷独立编号（vol_01 与 vol_02 都有 ch_001…）时，旧实现按
「章号减一 + 列表头」找上一章会串卷——dup ch_005 比到 vol_01/ch_004 而非
vol_02/ch_004；vol_02/ch_001 则因 n-1 = 0 直接判「无上一章」，跨卷续写的
连续性（其上一章是 vol_01 末章）整个丢失。修复后一律按 (卷, 章号) 阅读序取
「前一个位置」，pair 名带卷号不混淆。

夹具语义（用不同标记尾句制造确定性共享 shingle）：
- vol_01：ch_004 与 ch_005 共享尾句 S1（同卷邻对）
- vol_01：ch_005 还含 S2，且 S2 与 vol_02/ch_001 相同 → 卷界连续性
- vol_02：ch_004 与 ch_005 共享尾句 S4（S4 ≠ S1 → 旧实现串卷必现形）
"""
from __future__ import annotations

from pathlib import Path

import pytest

S1 = "陆沉舟把那串铜钱数了三遍，数目和账上对不上的地方，他决定先按下不提。"
S2 = "风灯在檐下晃了晃，陆沉舟觉得这一夜怕是安静不了，远处隐约传来犬吠声。"
S4 = "陆沉舟把刀鞘往桌上一搁，灯花噼啪一声炸开，满屋的影子都跟着抖了一下。"


def _final_text(seed: str, *tails: str) -> str:
    from conftest import _prose

    body = _prose(700, seed).rstrip()
    if tails:
        body += "\n\n" + "\n\n".join(tails)
    return f"# 第N章 测试标题\n\n{body}\n"


def _beats_text(form: str, note: str) -> str:
    return (f"---\nchapter: ch_001\nvol: vol_01\nform: {form}\npov: 陆沉舟\n"
            f"words: 600-900\n---\n\n## 必须保留\n\n- {note}\n\n"
            "## 核心冲突\n\n- 场景：测试场景。\n")


@pytest.fixture
def two_vol(ws_root) -> Path:
    from conftest import build_book

    book = build_book(ws_root, "bk_2vol", chapters=5)
    f01 = book / "manuscript" / "vol_01" / "final"
    (f01 / "ch_004.md").write_text(_final_text("一四", S1), encoding="utf-8")
    (f01 / "ch_005.md").write_text(_final_text("一五", S1, S2), encoding="utf-8")

    bdir = book / "outlines" / "vol_02" / "beats"
    v2f = book / "manuscript" / "vol_02" / "final"
    bdir.mkdir(parents=True, exist_ok=True)
    v2f.mkdir(parents=True, exist_ok=True)
    for n in range(1, 6):
        (bdir / f"ch_{n:03d}.md").write_text(
            _beats_text(f"卷2形{n}", f"vol_02 第{n}章"), encoding="utf-8")
    # vol_02 正文：ch_001 带 S2（卷界共享）；ch_004/ch_005 带 S4（同卷邻对）
    for n in range(1, 6):
        tails = {"1": [S2], "4": [S4], "5": [S4]}.get(str(n), [])
        (v2f / f"ch_{n:03d}.md").write_text(
            _final_text(f"二{n}", *tails), encoding="utf-8")
    return book


def test_dup_chapter_compares_same_volume_previous(two_vol):
    """dup ch_005：vol_02 的邻前章是 vol_02/ch_004，不许串到 vol_01/ch_004。"""
    from engine import evidence

    res = evidence.dup(two_vol, "ch_005")
    labels = [p["pair"] for p in res["adjacent_pairs"]]
    assert "vol_01/ch_004|vol_01/ch_005" in labels, f"vol_01 内部邻对缺失：{labels}"
    assert "vol_02/ch_004|vol_02/ch_005" in labels, f"vol_02 内部邻对被串卷：{labels}"
    assert not any("vol_01/ch_004|vol_02/ch_005" in l for l in labels), (
        f"旧实现会把 vol_02/ch_005 比到 vol_01/ch_004：{labels}")


def test_dup_chapter_boundary_uses_prev_volume_last(two_vol):
    """dup ch_001（vol_02 卷首）：邻前章是 vol_01 末章 ch_005，不是「无」。"""
    from engine import evidence

    res = evidence.dup(two_vol, "ch_001")
    labels = [p["pair"] for p in res["adjacent_pairs"]]
    assert "vol_01/ch_005|vol_02/ch_001" in labels, (
        f"卷界连续性丢失（旧实现 n-1=0 直接判无上一章）：{labels}")


def test_prev_contrast_boundary_returns_prev_volume_fields(two_vol):
    """prev ch_001（vol_02 卷首）：prev 应为 vol_01 末章 beats/final，而非空。"""
    from engine import evidence

    res = evidence.prev_contrast(two_vol, "ch_001")
    assert res["prev"] is not None, "卷首 prev 应为前卷末章，而不是无"
    prev_final = two_vol / "manuscript" / "vol_01" / "final" / "ch_005.md"
    assert res["prev_tail"] == prev_final.read_text(encoding="utf-8")[-300:], (
        "prev_tail 应对应 vol_01 末章 final 尾段")
    # prev 必须来自 vol_01/ch_005 的 beats（同一章号在 vol_02 也有——旧实现按号取
    # 会误判「无上一章」，这里用 vol_01 ch_005 beats 的 form 指纹验证取对文件）
    b01_5 = two_vol / "outlines" / "vol_01" / "beats" / "ch_005.md"
    from engine import common

    expect_form = common.parse_front_matter(b01_5.read_text(encoding="utf-8")).get("form")
    assert res["prev"]["form"] == expect_form, "prev 未取到 vol_01/ch_005"
