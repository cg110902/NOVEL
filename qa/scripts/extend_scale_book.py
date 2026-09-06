# -*- coding: utf-8 -*-
"""把 pb60 规模书从 60 章扩到 100 章（只加 beats/raw/final 文件，不动 state/proposals）。

用法: python extend_scale_book.py <book_dir> <start> <end>
只对缺失的章节补文件；已存在的章节跳过（幂等）。
beats 以同书已有章为模板做 token 替换；正文用 conftest_prose 确定性生成，
raw 与 final 同内容（规模书只测只读路径 + 文件级规模，不走 sync 闸门）。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest_prose import prose_block  # noqa: E402

FORMS = ["正面冲突", "暗流汇聚", "余波荡漾"]
SCORES = [5, 6, 7]
STYLE_NOTES = ["冷叙述 | 环境压人", "短句急促 | 对白推进", "平实口语 | 动作收尾", "絮语式 | 算账收口"]

BEATS_TEMPLATE = """---
chapter: {ch_tok}
vol: vol_01
form: {form}
pov: 陆沉舟·视角
words: 2600-3400
tension_curve: 起势 → 试探 → 破局 → 收口
tension_score: {score}
stage_mode: Simmering
style_notes: {snotes}
editor_extra: 打斗最多两回合。
---

## 本章坐标

- **所属阶段**：阶段{phase}（{ch_tok}）
- 当章预定规划：第{n}章推进主线。

## 核心冲突与场景脉络

- **本章核心戏剧目标**：第{n}章主角继续追查。

## 拍点与场景切片

- **场景一：开场**
  - 内容：主角在日常里遇到异常。
- **场景二：交锋**
  - 内容：主角与对手交锋。

## 线动作

- skip GUN-{n:03d}

## 验收要点

- 本章出现一次算账动作。

## 🔒 不可逆事实台账

- LOCK-001（赵七星死于瓮城）：本章提及须为追忆或案件复盘，不得活人登场。
- LOCK-002（瓮城灯楼焚毁）：场景已成废墟，不得如常营业。
"""


def main() -> None:
    if len(sys.argv) < 4:
        print("usage: extend_scale_book.py <book_dir> <start> <end>")
        sys.exit(2)
    book = Path(sys.argv[1])
    start, end = int(sys.argv[2]), int(sys.argv[3])
    beats_dir = book / "outlines" / "vol_01" / "beats"
    raw_dir = book / "manuscript" / "vol_01" / "raw"
    fin_dir = book / "manuscript" / "vol_01" / "final"
    made = skipped = 0
    for n in range(start, end + 1):
        ch_tok = f"ch_{n:03d}"
        if (beats_dir / f"{ch_tok}.md").is_file() and (fin_dir / f"{ch_tok}.md").is_file():
            skipped += 1
            continue
        form = FORMS[(n - 1) % len(FORMS)]
        score = SCORES[(n - 1) % len(SCORES)]
        phase = (n - 1) // 15 + 1
        snotes = STYLE_NOTES[(n - 1) % len(STYLE_NOTES)]
        beats = BEATS_TEMPLATE.format(ch_tok=ch_tok, n=n, form=form, score=score,
                                      phase=phase, snotes=snotes)
        body = prose_block(2800, seed=f"ch_{n:03d}", hero="陆沉舟")
        doc = f"# 第{n}章 灯下{n}\n\n{body}\n"
        (beats_dir / f"{ch_tok}.md").write_text(beats, encoding="utf-8")
        (raw_dir / f"{ch_tok}_v1.md").write_text(doc, encoding="utf-8")
        (fin_dir / f"{ch_tok}.md").write_text(doc, encoding="utf-8")
        made += 1
    print(f"made={made} skipped={skipped} -> {start}..{end} (book: {book})")


if __name__ == "__main__":
    main()
