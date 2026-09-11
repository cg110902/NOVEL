"""L3 雷库（方案 §4.1）：F01~F17，每条自带期望信号、触发门槛、注入与还原。

判定口径（方案 §4.1 注）：
- channel="code"   → `check --full --json` 的 code 集合（--full 免历史折叠遮蔽）；
- channel="stdout" → F03 的裸奔 print（`proposal check` 输出文本，非 REGISTRY 码）；
- channel="field"  → F13 的 pack budget_report 旗标；
- channel="absent" → F16 负例（不得被 longline_stale 点名）；
- baked=True 的雷由 generator 编入剧本（死线/超支窗/声纹窗等），eval 从「浸泡期检出并集」
  判定；live 雷由 chaos 现场注入→断言→还原（--keep 保留）。
方案与实现的偏差已按「以 REGISTRY + 实现为准」校准：F03 走 proposal check stdout、
F04 用位阶跌落（伤级回退是 merge 期 advisory，非 check 码）、F08 幽灵编号打在 cognition.truth_ref
（final 正文不扫编号，且拉丁残留闸会先咬人）、F09 以 current 情绪表未知名为准。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import ch_token, engine_cli, load_json, write_json


def collect_codes(book: Path) -> tuple[dict[str, list[str]], dict]:
    """跑 check --full --json，返回 ({code: [msg...]}, 原始报告)。"""
    rc, out = engine_cli(["check", "--full", "--json", "-w", str(book)])
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        return {"__harness_error__": [f"rc={rc} out[:300]={out[:300]}"]}, {}
    codes: dict[str, list[str]] = {}

    def walk(node):
        if isinstance(node, dict):
            c = node.get("code")
            m = str(node.get("msg", ""))
            if isinstance(c, str) and c:
                codes.setdefault(c, []).append(m)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    if rc == 0 or report:
        walk(report)
    if rc not in (0, 1):     # 其它 rc 属于 harness/引擎崩了
        codes.setdefault("__engine_rc__", [f"rc={rc}"])
    return codes, report


# ---------------------------------------------------------------------------
# live 雷：注入器返回 restore()
# ---------------------------------------------------------------------------

def _f01_old_final(book: Path) -> tuple:
    srcs = sorted((book / "manuscript").glob("*/final/ch_*.md"))
    target = srcs[len(srcs) // 4]
    orig = target.read_bytes()

    def apply():
        target.write_bytes(orig + "\n有人翻动过旧页，末尾多出一行修订句。\n".encode("utf-8"))

    def restore():
        target.write_bytes(orig)

    return apply, restore, {"expect_code": "final_drift", "target": target.name}


def _f03_cold_prereq(book: Path, plan: dict) -> tuple:
    f03 = plan.get("f03") or {}
    child = f03.get("child")
    nxt = plan["chapters"] + 1

    def apply():
        prop = {"schema": "novel-studio.state-mutation/v3", "chapter": ch_token(nxt),
                "operation_id": f"stress.f03.{nxt}",
                "ops": [{"table": "lines", "action": "resolve", "kind": "foreshadow", "id": child}]}
        write_json(book / "state" / "inbox" / f"{ch_token(nxt)}.json", prop)

    def restore():
        p = book / "state" / "inbox" / f"{ch_token(nxt)}.json"
        if p.exists():
            p.unlink()

    return apply, restore, {"needle": "回收的前置依赖已冷却", "child": child}


def _f06_time_dual(book: Path, plan: dict) -> tuple:
    cur_p = book / "state" / "current.json"
    orig = cur_p.read_bytes()
    day = (load_json(cur_p) or {}).get("time_day") or 1

    def apply():
        cur = json.loads(orig.decode("utf-8"))
        cur["time"] = f"第{day + 5}日·黄昏"        # 与 time_day 双轨错位
        write_json(cur_p, cur)

    def restore():
        cur_p.write_bytes(orig)

    return apply, restore, {"expect_code": "time_day_mismatch"}


def _f07_alias_shadow(book: Path) -> tuple:
    per_p = book / "state" / "persons.json"
    orig = per_p.read_bytes()

    def apply():
        d = json.loads(orig.decode("utf-8"))
        ents = d.get("entries", [])
        victim = next((e for e in ents if str(e.get("id")) != "p_001"), None)
        if victim is not None:
            victim.setdefault("aliases", [])
            if "主角" not in victim["aliases"]:
                victim["aliases"].append("主角")
            write_json(per_p, d)

    def restore():
        per_p.write_bytes(orig)

    return apply, restore, {"expect_code": "alias_shadows_name"}


def _f08_ghost_ref(book: Path) -> tuple:
    cog_p = book / "state" / "cognition.json"
    orig = cog_p.read_bytes()

    def apply():
        d = json.loads(orig.decode("utf-8"))
        ent = next((e for e in (d.get("entries") or []) if isinstance(e, dict)), None)
        who = (ent or {}).get("character", "主角")
        d.setdefault("entries", []).append({
            "id": "COG-900", "character": who, "kind": "fact",
            "content": "幽灵编号压力测试：指向不存在的真相锚点", "since_ch": "ch_001",
            "quote": "压力测试", "truth_ref": "GUN-9999"})
        write_json(cog_p, d)

    def restore():
        cog_p.write_bytes(orig)

    return apply, restore, {"expect_code": "dangling_ref"}


def _f09_mood_unknown(book: Path) -> tuple:
    cur_p = book / "state" / "current.json"
    orig = cur_p.read_bytes()

    def apply():
        cur = json.loads(orig.decode("utf-8"))
        cur.setdefault("present_moods", {})["查无此人甲"] = {"label": "暴怒", "level": 5}
        write_json(cur_p, cur)

    def restore():
        cur_p.write_bytes(orig)

    return apply, restore, {"expect_code": "mood_character_unknown"}


def _f10_derived_stale(book: Path) -> tuple:
    ln_p = book / "state" / "lines.json"
    orig = ln_p.read_bytes()

    def apply():
        d = json.loads(orig.decode("utf-8"))
        d.setdefault("foreshadows", []).append({
            "id": "GUN-998", "name": "派生过期探针线", "plant_ch": 1, "status": "Planted"})
        write_json(ln_p, d)

    def restore():
        ln_p.write_bytes(orig)

    return apply, restore, {"expect_code": "derived_stale"}


def _f11_cognition_conflict(book: Path) -> tuple:
    cog_p = book / "state" / "cognition.json"
    lines = load_json(book / "state" / "lines.json", default={}) or {}
    resolved_mis = next((str(g.get("id")) for g in (lines.get("misunderstandings") or [])
                        if str(g.get("status", "")).lower() == "resolved"), None)
    orig = cog_p.read_bytes()

    def apply():
        d = json.loads(orig.decode("utf-8"))
        ent = next((e for e in (d.get("entries") or []) if isinstance(e, dict)), None)
        who = (ent or {}).get("character", "主角")
        d.setdefault("entries", []).append({
            "id": "COG-901", "character": who, "kind": "misunderstanding",
            "content": "仍深信已被澄清的旧误会（压力探针）", "since_ch": "ch_001",
            "quote": "压力测试", "truth_ref": resolved_mis})
        write_json(cog_p, d)
        engine_cli(["state", "recompute", "-w", str(book)])

    def restore():
        cog_p.write_bytes(orig)
        engine_cli(["state", "recompute", "-w", str(book)])

    return apply, restore, {"expect_code": "cognition_truth_conflict",
                            "skip_if": resolved_mis is None}


def _f12_pov_missing(book: Path) -> tuple:
    bts = sorted((book / "outlines").glob("*/beats/ch_*.md"))
    target = bts[len(bts) // 3]
    orig = target.read_text(encoding="utf-8")

    def apply():
        target.write_text("\n".join(l for l in orig.splitlines() if not l.startswith("pov:")) + "\n",
                          encoding="utf-8")

    def restore():
        target.write_text(orig, encoding="utf-8")

    return apply, restore, {"expect_code": "beats_pov_missing", "target": target.name}


def _f13_budget_breach(book: Path) -> tuple:
    bts = sorted((book / "outlines").glob("*/beats/ch_*.md"))
    target = bts[-1]
    orig = target.read_text(encoding="utf-8")
    filler = "夜雨敲篷，帐中各人守着各自的账，谁也没有先掀帘子。"

    def apply():
        target.write_text(orig + "\n" + filler * 900 + "\n", encoding="utf-8")

    def restore():
        target.write_text(orig, encoding="utf-8")

    m = re.search(r"ch_(\d+)", target.name)
    pack_ch = ch_token(int(m.group(1))) if m else target.stem
    return apply, restore, {"field": "hard_cap_breached", "pack_ch": pack_ch}


LIVE_FAULTS = {"F01": _f01_old_final, "F06": _f06_time_dual, "F07": _f07_alias_shadow,
               "F08": _f08_ghost_ref, "F09": _f09_mood_unknown, "F10": _f10_derived_stale,
               "F11": _f11_cognition_conflict, "F12": _f12_pov_missing, "F13": _f13_budget_breach}

# 门槛：低于章数/卷数门槛的雷在该档 N/A（不算 FAIL；full-scale 必须全量过）
FAULT_GATE = {
    "F02": {"min_chapters": 60},   # 死线 gap>2×25 → 需要足够章距
    "F03": {"min_chapters": 45},   # child plant + 冷化
    "F04": {"min_chapters": 80},   # 位阶升阶+跌落成对埋点，需要前后两段窗口
    "F05": {"min_chapters": 20},
    "F14": {"min_chapters": 150},   # 声纹长窗
    "F16": {"min_vols": 2},
    "F15": {"min_chapters": 25},
    "F17": {"min_chapters": 8},
}

FAULT_META = {
    "F01": "旧稿篡改→final_drift（指纹漂移，历史巨厚时还稳吗）",
    "F02": "死线埋而不收→longline_stale（阈值×2 在 300 章下仍准）",
    "F03": "冷前置直接回收→proposal check stdout「回收的前置依赖已冷却」（裸奔信号通道）",
    "F04": "位阶跌落无事件→tier_shift_without_event（伤级回退是 merge advisory，改按位阶校准）",
    "F05": "有限池超支→pool_overdrawn（debt_ 前缀豁免为对照组）",
    "F06": "time 与 time_day 双轨错位→time_day_mismatch",
    "F07": "新实体撞旧别名→alias_shadows_name（250 实体生日悖论区）",
    "F08": "cognition 幽灵编号→dangling_ref（final 不扫编号，按实现改道 state）",
    "F09": "current 情绪表未知名→mood_character_unknown",
    "F10": "离线改 lines 不更 derived→derived_stale",
    "F11": "误会已澄清仍深信→cognition_truth_conflict（派生挂旗）",
    "F12": "beats 缺 pov→beats_pov_missing",
    "F13": "超长 beats 压爆预算→pack budget_report.hard_cap_breached（非码信号）",
    "F14": "对白声纹骤变→voiceprint_drift（长基线下灵敏度）",
    "F15": "出厂情绪表 vs 实际落笔差≥2→mood_plan_actual_drift",
    "F16": "跨卷旧线按时回收→longline_stale 必须不点名 + rollup 可见（负例）",
    "F17": "情绪快照冻结 4 章→mood_snapshot_stale",
}


def run_chaos(book: Path, plan: dict, only: list[str] | None = None,
              keep: bool = False, quiet: bool = False) -> dict:
    """live 雷现场注入→断言→还原。返回 {fid: {"ok":..,"detail":..}}。"""
    book = Path(book)
    results: dict[str, dict] = {}
    want = only or sorted(set(LIVE_FAULTS) | {"F03"})
    for fid in want:
        if fid not in LIVE_FAULTS and fid != "F03":
            continue  # F03 不在 LIVE 表：走 proposal check stdout needle 的专用分支
        gate = FAULT_GATE.get(fid, {})
        if plan["chapters"] < gate.get("min_chapters", 0):
            results[fid] = {"ok": None, "detail": "scale N/A"}
            continue
        if fid == "F01":
            apply, restore, meta = _f01_old_final(book)
        elif fid == "F03":
            apply, restore, meta = _f03_cold_prereq(book, plan)
        elif fid == "F06":
            apply, restore, meta = _f06_time_dual(book, plan)
        else:
            apply, restore, meta = LIVE_FAULTS[fid](book)
        if meta.get("skip_if"):
            results[fid] = {"ok": None, "detail": "前置不足（无已澄清误会）"}
            continue
        detail = ""
        ok = False
        try:
            apply()
            if fid == "F03":
                rc, out = engine_cli(["proposal", "check", ch_token(plan["chapters"] + 1),
                                      "-w", str(book)])
                ok = meta["needle"] in out
                detail = f"rc={rc} needle_hit={ok}"
            elif fid == "F13":
                from engine import pack as pack_mod
                rep = pack_mod.build_pack(book, meta["pack_ch"])
                b = rep.get("budget_report", {})
                ok = bool(b.get("hard_cap_breached")) and bool(b.get("compressed"))
                detail = json.dumps({k: b.get(k) for k in ("total", "cap", "hard_cap_breached",
                                                            "compressed")}, ensure_ascii=False)
            else:
                codes, _ = collect_codes(book)
                code = meta["expect_code"]
                ok = code in codes
                detail = f"expect={code} seen={len(codes)} codes; msg={ (codes.get(code) or [''])[0][:120] }"
        finally:
            if not keep:
                restore()
        results[fid] = {"ok": ok, "detail": detail, "restored": not keep}
        if not quiet:
            print(f"  {'✅' if ok else ('➖' if ok is None else '❌')} chaos {fid}: {detail[:160]}")
    return results
