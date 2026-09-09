#!/usr/bin/env python
"""变异守卫（mutation guard）——「测试自欺检测」的机械化版本。

对本次改造的每个关键实现注入一个手工设计的缺陷（变异），然后跑对应的
测试模块：**变异必须被杀死（测试变红）**，否则说明该特性的测试是自欺的。

用法：
    .venv/bin/python tests/mutation_guard.py          # 全部 12 个变异
    .venv/bin/python tests/mutation_guard.py 3        # 只跑第 3 个

注意：本脚本会临时改写 engine/ 源码（逐个变异、跑完即还原，还原后做
字节级校验）。不要并入默认测试发现（文件名不以 test_ 开头）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# (编号, 名称, 目标文件, 原文→变异, 杀手测试模块)
MUTATIONS = [
    (1, "rollup 裁剪失去保底头行", "engine/rollup.py",
     "while len(lines) > 1 and common.est_tokens",
     "while common.est_tokens"),
    (2, "rollup 未兑线混入已闭环", "engine/rollup.py",
     'if str(g.get("status", "")).strip().lower() == str(spec["resolved"]).lower():\n                continue',
     'if False:\n                continue'),
    (3, "pack 前情卷末态势块消失", "engine/pack.py",
     'lines += ["", "=== 前情卷末态势（远卷摘要，细节用 lore 按需取） ==="]',
     'lines += []'),
    (4, "A5 冷线锚定注入消失", "engine/pack.py",
     'if hints:\n                p0["cold_recall_hints"] = hints',
     'if hints and False:\n                p0["cold_recall_hints"] = hints'),
    (5, "A5 注入上限 2→1", "engine/pack.py",
     "for r in cold[:2]",
     "for r in cold[:1]"),
    # 注：曾设计过「startswith(path) 前缀陷阱」变异，实测为等价变异——
    # 路径语法 key[id] 以 ] 收尾，字符串前缀天然不会越段（test_blame_prefix_trap
    # 仍保留该属性断言）。改用排序反向这一可观察变异。
    (6, "changelog blame 时序反转（新→旧 变 旧→新）", "engine/changelog.py",
     'out.sort(key=lambda e: -int(e.get("seq") or 0))',
     'out.sort(key=lambda e: int(e.get("seq") or 0))'),
    (7, "state_at 永远折叠到最新（时点切面失真）", "engine/changelog.py",
     "seq = seal_seq_for(book, ch_num)",
     "seq = None"),
    (8, "读者记忆冷线阈值忽略 weight 缩放", "engine/memory.py",
     'return tiers["cold_line_base"] + (w - 1) * tiers["cold_line_per_weight"]',
     'return tiers["cold_line_base"]'),
    (9, "voiceprint 说话人归属失效（动词约束移除→乱归属）", "engine/voiceprint.py",
     'if len(after) <= 4 and _SAY_VERB_RE.search(after):',
     'if True:'),
    (10, "voiceprint 漂移误升 warning 通道", "engine/checks.py",
     'infos.append(_err(\n                    "voiceprint_drift"',
     'warnings.append(_err(\n                    "voiceprint_drift"'),
    (11, "A4b 盲区提示消失", "engine/checks.py",
     'if fact and known_names and not any(n in fact for n in known_names):',
     'if fact and known_names and False:'),
    (12, "reconcile 高危字段过滤失效（永远无高危变更）", "engine/commands/reconcile.py",
     'if not any(path == f or path.endswith(f".{f}") for f in _HIGH_RISK_FIELDS):\n                continue',
     'if True:\n                continue'),
]

KILLER = {
    1: "tests.test_rollup", 2: "tests.test_rollup", 3: "tests.test_rollup",
    4: "tests.test_cold_recall", 5: "tests.test_cold_recall",
    6: "tests.test_changelog", 7: "tests.test_changelog",
    8: "tests.test_memory", 9: "tests.test_voiceprint",
    10: "tests.test_voiceprint", 11: "tests.test_cold_recall",
    12: "tests.test_reconcile",
}


def run_module(mod: str) -> int:
    r = subprocess.run([PY, "-m", "unittest", mod], capture_output=True, text=True,
                       cwd=str(ROOT), timeout=600)
    return r.returncode


def main() -> int:
    only = {int(sys.argv[1])} if len(sys.argv) > 1 else None
    results = []
    for num, name, rel, old, new in MUTATIONS:
        if only and num not in only:
            continue
        path = ROOT / rel
        original = path.read_bytes()
        src = original.decode("utf-8")
        if old not in src:
            results.append((num, name, "SKIP", "锚点未找到（实现已变？）"))
            continue
        bak = Path(tempfile.mkstemp(suffix=".bak")[1])
        bak.write_bytes(original)
        try:
            path.write_text(src.replace(old, new, 1), encoding="utf-8")
            rc = run_module(KILLER[num])
            verdict = "KILLED" if rc != 0 else "SURVIVED"
            results.append((num, name, verdict, f"killer={KILLER[num]} rc={rc}"))
        finally:
            restored = bak.read_bytes()
            path.write_bytes(restored)
            bak.unlink(missing_ok=True)
            if path.read_bytes() != original:
                print(f"!! 还原校验失败：{rel}")
                return 2
    print(f"\n{'='*72}")
    print(f"变异守卫报告：{len(results)} 个变异")
    print(f"{'='*72}")
    survived = 0
    for num, name, verdict, note in results:
        mark = {"KILLED": "✅ 被杀死", "SURVIVED": "❌ 存活（测试自欺！）",
                "SKIP": "⏭ 跳过"}[verdict]
        print(f"  [{num:2d}] {mark:24s} {name}")
        print(f"        {note}")
        survived += verdict == "SURVIVED"
    print(f"{'='*72}")
    print(f"结论：{len(results) - survived}/{len(results)} 被杀死"
          + ("——全部变异被捕获，测试无自欺" if not survived else
             f"；{survived} 个存活变异需要补测试！"))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
