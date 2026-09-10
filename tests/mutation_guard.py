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
    # 13：derived 封存静默失败的元凶。闸门层全局拒绝显式 null，而 derive 若把
    # 零落笔线/闭环线的 last_seen_ch、gap 写成 null，整张派生表**静默降级为空表**
    # （"派生永不炸封存"）。这是最容易被忽略的失效模式——失败不可见。
    # 13/14 锚点随 main 的 derive.py 重写而更新：main 与我们修的是同一个 bug
    # （Optional 键显式写 null → 整张派生表封存静默失败），口径一致（省略而非 null），
    # 且 main 还多修了 status 空串与 line_temps 稳定排序，故直接采用其实现。
    (13, "derived 线温恢复显式 null（派生表封存静默失败）", "engine/objects/derive.py",
     '        if r.get(\"last_seen_ch\") is not None:\n            entry[\"last_seen_ch\"] = r.get(\"last_seen_ch\")\n        if r.get(\"gap\") is not None:\n            entry[\"gap\"] = r.get(\"gap\")',
     '        entry[\"last_seen_ch\"] = r.get(\"last_seen_ch\")\n        entry[\"gap\"] = r.get(\"gap\")'),
    (14, "derived 闭环线快照恢复显式 null", "engine/objects/derive.py",
     '                closed_entry: dict = {\n                    \"id\": str(g.get(\"id\", \"\")),\n                    \"kind\": kind,\n                    \"temp\": \"closed\",\n                }',
     '                closed_entry: dict = {\n                    \"id\": str(g.get(\"id\", \"\")),\n                    \"kind\": kind,\n                    \"temp\": \"closed\",\n                    \"last_seen_ch\": None,\n                    \"gap\": None,\n                }'),
    # ---- 32：state at 未激活事件流时的「不许静默兜底」声明 ----
    # main 把 state_at 改为回退磁盘当前状态（兼容老书），但回退若一声不吭，
    # 就是把"此刻的世界"冒充成"第 N 章的历史切面"。去掉提示 = 重新变成误导。
    (32, "state at 回退后不再声明（静默把当前状态当历史切面）",
     "engine/commands/state_sync.py",
     '        if not changelog.active(book):',
     '        if False:'),
    # ---- 15~18：故障注入套件（tests/test_fault_injection.py）的配套变异 ----
    # 拆除闸门后对应负向用例必须变红，否则该闸门"文档上承诺、实测上不存在"。
    (15, "资源池未知字段闸门失效", "engine/state.py",
     '                        if k not in ("name", "unit", "initial"):\n'
     '                            errors.append(f"ledger.pools[{pid}] 含未知字段: {k}")',
     '                        if False:\n'
     '                            errors.append(f"ledger.pools[{pid}] 含未知字段: {k}")'),
    (16, "locked.note 必填闸门失效", "engine/state.py",
     '                if not str(l.get("note") or "").strip():',
     '                if False:'),
    (17, "前置因果闭环保失效（合并期不再拦）", "engine/state.py",
     '        errors.extend(_prereq_errors(data["lines"]))',
     '        pass'),
    (18, "跨章流水注入闸失效", "engine/state.py",
     '            if (t.get("chapter") is not None and expected_chapter\n'
     '                    and re.fullmatch(r"ch_\\d{3,}", str(t["chapter"]))\n'
     '                    and str(t["chapter"]) != expected_chapter):',
     '            if False:'),
    # ---- 19~20：本轮新修缺陷的配套变异 ----
    # 19：退回「用原始路径过网关」→ 符号链接可把白名单当跳板
    (19, "open_file 退回原始路径过网关（符号链接跳板复活）", "engine/pack.py",
     '    reason = deny_reason(book, rel_checked, role)',
     '    reason = deny_reason(book, rel, role)'),
    # 20：world_anchors 预算帽失效 → 恒定内容重回「占满上下文且无法裁剪」
    (20, "world_anchors 预算帽失效", "engine/pack.py",
     '        if kept and used + t > budget:\n            break',
     '        if False:\n            break'),
    # ---- 21~24：中文数字解析（万/亿 分节）的配套变异 ----
    # 21：万/亿 退回「当普通单位扁平累加」→ 十二万→20010、三十万→10030
    (21, "cn_to_int 万/亿 退回扁平累加", "engine/common.py",
     '            total += ((section + (num or 0)) or 1) * _CN_UNITS_SECTION[ch]',
     '            total += (num or 1) * _CN_UNITS_SECTION[ch]'),
    # 22：正文↔账本算术闸门的字符集退回不含 万/亿 → 大额再次整段静默
    (22, "算术闸门 _NUMPAT 退回不含万/亿", "engine/checks.py",
     r'        _NUMPAT = r"(\d+|[零一二两三四五六七八九十百千万亿]{1,12})"',
     r'        _NUMPAT = r"(\d+|[零一二两三四五六七八九十百千]{1,6})"'),
    # 23：audit 金额探针的字符集退回不含 亿 → 「付了三亿灵石」匹配不上
    (23, "audit 金额正则退回不含亿", "engine/audit.py",
     r'rf"(?:{_verbs_pat})\s*([0-9一二两三四五六七八九十百千万亿]+)\s*({_units_pat})"',
     r'rf"(?:{_verbs_pat})\s*([0-9一二两三四五六七八九十百千万]+)\s*({_units_pat})"'),
    # 24：evidence 不再委托 canonical → 三份实现重新分叉
    (24, "evidence 数字解析退回自带扁平实现（三份实现重新分叉）", "engine/evidence.py",
     '    return common.cn_to_int(s)',
     '    total, num = 0, 0\n'
     '    for ch in s:\n'
     '        if ch in _CN_DIGITS:\n'
     '            num = _CN_DIGITS[ch]\n'
     '        elif ch in _CN_UNITS:\n'
     '            total += (num or 1) * _CN_UNITS[ch]\n'
     '            num = 0\n'
     '        else:\n'
     '            return None\n'
     '    return total + num'),
    # ---- 25~26：SKILL 准读清单 ↔ pack 角色网关 一致性 ----
    # 25：editor 的「文风宪法」白名单例外被拿掉 → 文档授权、网关拒收
    (25, "editor 失去 bible/06 白名单例外（文档授权但网关拒收）", "engine/pack.py",
     '    "editor": ("bible/06_style_guidelines.md",),\n'
     '    "stylist": ("bible/06_style_guidelines.md",),',
     '    "stylist": ("bible/06_style_guidelines.md",),'),
    # 26：SKILL 文档又把「角色卡」列回 editor 的准读清单（网关禁读 characters/）
    (26, "editor SKILL 又把角色卡列为准读（文档授权但网关拒收）",
     ".agents/skills/editor/SKILL.md",
     '  3. `bible/06_style_guidelines.md`（全书文风宪法与微动作词库）。',
     '  3. `bible/06_style_guidelines.md`（全书文风宪法与微动作词库）；\n'
     '  4. `characters/<在场角色>.md`（当章出场的核心角色卡）。'),
    # ---- 27~28：state/inbox/README.md 契约（此前零测试覆盖，改了不会红）----
    # 27：引文接地阈值悄悄改动 → 与 README 写的「≥85% / 60~85%」脱节
    (27, "引文接地阈值与 README 脱节", "engine/checks.py",
     'QUOTE_PASS_RATIO = 85.0', 'QUOTE_PASS_RATIO = 80.0'),
    # 28：README 的 lines.kind 退回「foreshadow/…」，Agent 只能猜三个合法值
    (28, "README 的 lines.kind 退回只写 foreshadow/…", "engine/state.py",
     'foreshadow|misunderstanding|knowledge', 'foreshadow/…'),
    # ---- 29~31：旁白/心理描写知情差泄露（原盲区）----
    # 29：旁白扫描整段关掉 → 盲区复活（本轮最初钉的就是这条）
    (29, "旁白/心理描写知情差扫描关闭（盲区复活）", "engine/audit.py",
     '            if not (pov_name and knower and pov_name not in knower):',
     '            if not (False and knower and pov_name not in knower):'),
    # 30：否定式闸拿掉 → 「他不知道 X」被当成泄密（最尴尬的误报）
    (30, "否定式（他不知道X）被当成泄密", "engine/audit.py",
     '            if any(neg in narration for neg in _NEGATION):\n                continue',
     '            if False:\n                continue'),
    # 31：视角模式被当成角色名 → 群像/全知视角下旁白全成穿帮（误报洪水）
    (31, "视角模式（群像切片）被误当角色名", "engine/audit.py",
     '        if cand and cand in roster:\n            return cand',
     '        if cand:\n            return cand'),
]

KILLER = {
    1: "tests.test_rollup", 2: "tests.test_rollup", 3: "tests.test_rollup",
    4: "tests.test_cold_recall", 5: "tests.test_cold_recall",
    6: "tests.test_changelog", 7: "tests.test_changelog",
    8: "tests.test_memory", 9: "tests.test_voiceprint",
    10: "tests.test_voiceprint", 11: "tests.test_cold_recall",
    12: "tests.test_reconcile",
    13: "tests.test_objects", 14: "tests.test_objects",
    15: "tests.test_fault_injection", 16: "tests.test_fault_injection",
    17: "tests.test_fault_injection", 18: "tests.test_fault_injection",
    19: "tests.test_engine", 20: "tests.test_rollup",
    21: "tests.test_engine", 22: "tests.test_engine",
    23: "tests.test_engine", 24: "tests.test_engine",
    25: "tests.test_role_policy", 26: "tests.test_role_policy",
    27: "tests.test_inbox_contract", 28: "tests.test_inbox_contract",
    29: "tests.test_fault_injection", 30: "tests.test_fault_injection",
    31: "tests.test_fault_injection",
    32: "tests.test_acceptance",
}


def run_module(mod: str) -> int:
    r = subprocess.run([PY, "-m", "unittest", mod], capture_output=True, text=True,
                       cwd=str(ROOT), timeout=600)
    return r.returncode


def main() -> int:
    # 曾只取 argv[1]：`python tests/mutation_guard.py 21 22 23 24` 会静默丢掉后三个，
    # 让人误以为四个变异都验过了。改为接受任意多个编号。
    only = {int(a) for a in sys.argv[1:]} or None
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
    skipped = sum(1 for r in results if r[2] == "SKIP")
    killed = len(results) - survived - skipped
    # ⚠️ SKIP 绝不能算进「被杀死」：锚点没找到意味着这个变异**根本没跑**，
    # 报「N/N 被杀死」会让人以为防线完好。此前正是这么写的，实测把一个 SKIP
    # 与一个真 KILLED 混成「2/2 被杀死」。
    print(f"{'='*72}")
    print(f"结论：{killed} 被杀死 / {survived} 存活 / {skipped} 跳过（共 {len(results)} 个）")
    if survived:
        print(f"  ❌ {survived} 个变异存活——测试自欺，需要补测试！")
    if skipped:
        print("  ⚠️  有变异被跳过（锚点未命中）：这些变异**没有验证任何东西**，"
              "请核对锚点文本后重跑。")
    if not survived and not skipped:
        print("  ✅ 全部变异被捕获，测试无自欺")
    return 1 if (survived or skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
