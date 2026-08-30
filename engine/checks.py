"""check：结构 + schema + 算术体检（吸收旧 doctor/verify/audit；errors 只允许事实级）。

语义红线 ：
- errors：可机械判定必须修复的事实——schema 违规、引用未登记实体、章号断档、占位符未填、
  同 form 无理由、账本重算不符（state.verify_state）。
- warnings：算术数出来的偏离事实（字数出带、线逾期、tics 命中、form 占比超 40%）——只报数，
  是否修、怎么修由主控/审校决定。
- 两个桶里都不许出现「建议/疑似/不宜」等判断词；本模块零写入。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, evidence, state

SLOT_RE = re.compile(r"\{\{\s*slot:")
CANDIDATE_RE = re.compile(r"candidate_[0-9A-Za-z_*]")
FORM_SHARE_LIMIT = 0.40


def _err(code: str, msg: str) -> dict:
    return {"code": code, "msg": msg}


_BEATS_FM_KEYS = {"chapter", "vol", "form", "pov", "words", "style_notes", "form_reason",
                  "guard_extra"}


def _numbered_items(lines: list[str]) -> dict[int, str]:
    """`N.`/`N、`起头的行 → {序号: 整行}（跳空行，只认节内）。"""
    out: dict[int, str] = {}
    for ln in lines:
        m = re.match(r"^(\d+)[.、]\s*(.*)$", ln.strip())
        if m:
            out[int(m.group(1))] = ln.strip()
    return out


def _section(md_text: str, title_pat: str) -> list[str]:
    """取 "## <title>" 小节正文（到下一个 ## 或文件尾）。"""
    lines, inside = [], False
    for ln in md_text.splitlines():
        if re.match(r"^##\s", ln):
            if inside:
                break
            inside = bool(re.match(title_pat, ln))
            continue
        if inside:
            lines.append(ln)
    return lines


def review_gate(book: Path, ch: str) -> list[str]:
    """Stage 3/4 合同（机械层）：审校注记「验收打钩」节必须逐条答完任务书「验收」。

    只数行与符号：beats 无「验收」节 → 不拦（无清单可对照）；beats 有「验收」而注记缺失 →
    拦（Stage 3 校对/注记/回话是封存前提，不允许主控代笔静默放行）；注记存在 → 缺答/缺✓✗/
    ✓而短于证据线 = 拒绝封存。
    """
    beats = [f for f in common.find_chapter_files(book, "beats")
             if common.chapter_number_from_name(f.name) == common.chapter_token_to_num(ch)]
    k = 0
    if beats:
        acc = _section(beats[0].read_text(encoding="utf-8", errors="replace"), r"^##\s*验收")
        k = max(_numbered_items(acc), default=0)
    if k == 0:
        return []
    rev = book / "log" / "review" / f"{ch}.md"
    if not rev.is_file():
        return [f"beats「验收」共 {k} 条，但审校注记 {ch}.md 不存在（Stage 3 未留审计；拒封存）"]
    items = _numbered_items(_section(rev.read_text(encoding="utf-8", errors="replace"),
                                     r"^##\s*验收"))
    issues: list[str] = []
    missing = [n for n in range(1, k + 1) if n not in items]
    if missing:
        issues.append(f"验收 {missing} 未被审校注记回答（共 {k} 条，须逐条 N. ✓/✗+证据）")
    # 证据判定（novel_craft.md#打磨与校对）：每条结论必须带证据——正文引文，或 evidence 字段名+数值。
    # 不再用"整行 ≥24 字符"的任意长阈值（会误伤语句精炼但已给引文/数值的证据）。
    EVIDENCE_QUOTE_RE = re.compile(r"[「“\"'『]")          # 引号 = 正文引文
    EVIDENCE_FIELD_RE = re.compile(r"[A-Za-z_][\w]*[:：]\s*[\d.]+|[A-Za-z_]+\s*=\s*[\d.]+")  # 字段:值
    for n, line in sorted(items.items()):
        if not re.search(r"[✓✗×√]", line):
            issues.append(f"验收 {n} 无 ✓/✗ 判定符")
        elif not (EVIDENCE_QUOTE_RE.search(line) or EVIDENCE_FIELD_RE.search(line)):
            issues.append(f"验收 {n} 打了判定符但无证据（须含正文引文或 evidence 字段名+数值）")
    return issues

def word_band_gate(book: Path, ch: str) -> list[str]:
    """Stage 4 闸门：目标章 final 字数必须在 project.json.words_target 带内。

    把 '达字数带' 从 warning 升级为封存前硬门槛：超带 → 拒绝 sync 封存。
    口径与 evidence.final_chapters 一致（同章多版本取版本号最大者、字数剔除标题行）。
    """
    proj = common.load_json(book / "project.json", default={}) or {}
    band = proj.get("words_target")
    if not (isinstance(band, list) and len(band) == 2
            and all(isinstance(x, int) for x in band)):
        return []  # 未配置字数带，不拦
    lo, hi = band
    want = common.chapter_token_to_num(ch)
    if want is None:
        return []
    for tok, num, text in evidence.final_chapters(book):
        if num == want:
            c = common.cjk_count(text)
            if c < lo or c > hi:
                return [f"{tok}: final 字数 {c} 不在目标带 [{lo}, {hi}] 内，拒绝封存（Stage 4 硬门槛）"]
            return []
    return []
    
def run_checks(book: Path) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    stats: dict = {}

    # ---- project.json ----
    proj_path = book / "project.json"
    proj: dict = {}
    if not proj_path.exists():
        errors.append(_err("project_missing", f"缺 project.json: {book}（先运行 init）"))
    else:
        try:
            proj = common.load_json(proj_path)
        except (ValueError, OSError) as exc:
            errors.append(_err("project_corrupt", f"project.json 解析失败: {exc}"))
    for field in ("title", "genre"):
        if proj and not str(proj.get(field, "")).strip():
            errors.append(_err("project_field_empty", f"project.json.{field} 为空"))
    band = proj.get("words_target")
    band_ok = isinstance(band, list) and len(band) == 2 and all(isinstance(x, int) for x in band)
    if proj and "words_target" in proj and not band_ok:
        errors.append(_err("project_field_type", "project.json.words_target 必须是 [下限, 上限] 整数对"))

    # ---- 状态层（schema + 账本重算 + 唯一性，sync 前同款体检） ----
    for msg in state.verify_state(book):
        errors.append(_err("state_inconsistent", msg))

    # ---- 实体引用闭合（current.present_characters ∈ 注册表名/别名） ----
    try:
        ents = state.load_state(book, "entities")["entries"]
        known = set()
        for e in ents:
            known.add(str(e.get("name", "")))
            known.update(str(a) for a in e.get("aliases", []) if a)
        cur = state.load_state(book, "current")
        for name in cur.get("present_characters", []):
            if str(name).strip() and str(name) not in known:
                errors.append(_err("unregistered_character",
                                   f"current.present_characters 引用未登记实体「{name}」"
                                   "（先在 entities 提案注册，名字须与卡一致）"))
    except (ValueError, FileNotFoundError) as exc:
        errors.append(_err("state_unreadable", str(exc)))

     # ---- 稿件结构：final 章号断档 / 同版本号重复（一章多版本是合法溯源，只取版本最大者）----
    # 分组键 = (卷, 章号, 版本号)：跨卷同章号互不覆盖（vol_02/ch_001 合法），
    # 仅同卷、同章号、同版本号出现多份定稿 = 真正重复。
    final_files = common.find_chapter_files(book, "final")
    ver_by_ch: dict[tuple[str, int], dict[int, list[Path]]] = {}
    for f in final_files:
        n = common.chapter_number_from_name(f.name)
        if n is not None:
            try:
                vol = f.relative_to(book / "manuscript").parts[0]
            except ValueError:
                vol = ""
            v = common.chapter_version_from_name(f.name)
            ver_by_ch.setdefault((vol, n), {}).setdefault(v, []).append(f)
    per_ch: dict[tuple[str, int], Path] = {}
    for (vol, n), vers in sorted(ver_by_ch.items()):
        # 同一版本号出现多个文件 = 真正重复；不同版本号 = 审计留痕（v2/v10），取版本号最大者。
        dup = [f for fs in vers.values() if len(fs) > 1 for f in fs]
        if dup:
            errors.append(_err("duplicate_final",
                               f"{vol} 第{n}章同版本号有多份定稿: {', '.join(f.name for f in dup)}"))
        top = max(vers)
        per_ch[(vol, n)] = vers[top][0]
    # 断档按卷检查：只对已有定稿的卷判断连续区间，避免把卷间间隙误判。
    vol_nums: dict[str, list[int]] = {}
    for (vol, n) in per_ch:
        vol_nums.setdefault(vol, []).append(n)
    for vol, nums in sorted(vol_nums.items()):
        missing = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
        if missing:
            errors.append(_err("final_gap_chapters",
                               f"{vol} final 章号断档: {missing}（第 {min(nums)} 与 {max(nums)} 章之间无定稿）"))
    stats["final_chapters"] = len(per_ch)

    # ---- 占位符：槽位未实例化禁止入流水线 ----
    slot_hits = []
    for md in sorted(book.rglob("*.md")):
        try:
            if SLOT_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                slot_hits.append(str(md.relative_to(book)))
        except OSError:
            continue
    for rel in slot_hits:
        errors.append(_err("unfilled_slot", f"{rel} 存在未填充槽位 {{{{slot:...}}}}（Stage 0 未完成）"))

    # ---- 禁令6：稿件禁工程痕迹（candidate_* 泄漏进 manuscript）----
    ms = book / "manuscript"
    if ms.is_dir():
        for md in sorted(ms.rglob("*.md")):
            try:
                if CANDIDATE_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                    errors.append(_err("candidate_leak",
                        f"{md.relative_to(book)} 含 candidate_* 工程痕迹（AGENTS 禁令6：禁入稿件）"))
            except OSError:
                continue

    # ---- beats 协议（机械部分）：同 form 连章必须给理由；form 缺失；超键拦截 ----
    beats = sorted(common.find_chapter_files(book, "beats"),
                   key=lambda p: (p.parts[-3] if len(p.parts) > 2 else "",
                                  common.chapter_number_from_name(p.name) or 0))
    prev_form_by_vol: dict[str, tuple[int, str]] = {}
    for f in beats:
        fm = common.parse_front_matter(f.read_text(encoding="utf-8", errors="replace"))
        vol = f.relative_to(book / "outlines").parts[0]
        extra = set(fm) - _BEATS_FM_KEYS
        if extra:
            errors.append(_err("beats_fm_extra_keys",
                               f"{f.name}: front-matter 含未定义键 {sorted(extra)}"
                               f"（合法键 {sorted(_BEATS_FM_KEYS)}；工程痕迹禁入稿——AGENTS 禁令6）"))
        num = common.chapter_number_from_name(f.name) or 0
        form = fm.get("form", "")
        if not form:
            errors.append(_err("beats_missing_form", f"{f.name}: front-matter 缺 form 字段（Stage 1 未选章型）"))
        else:
            last = prev_form_by_vol.get(vol)
            if last and last[1] == form and num == last[0] + 1 and not fm.get("form_reason"):
                errors.append(_err("beats_form_repeat_without_reason",
                                   f"{f.name}: 与上一章同 form「{form}」但 front-matter 未写 form_reason"))
            prev_form_by_vol[vol] = (num, form)

    # ---- 流程事实（warn 级）：final 无 raw / 无 beats ----
    # 与 final 的 per_ch 同口径，按 (卷, 章号) 键控：跨卷同章号互不覆盖，
    # 避免 vol_02/ch_001 的缺口被 vol_01/ch_001 的原料"顶掉"而漏报。
    def _vol_nums(area: str) -> set[tuple[str, int]]:
        out = set()
        for f in common.find_chapter_files(book, area):
            n = common.chapter_number_from_name(f.name)
            if n is None:
                continue
            base = book / ("outlines" if area == "beats" else "manuscript")
            try:
                vol = f.relative_to(base).parts[0]
            except ValueError:
                vol = ""
            out.add((vol, n))
        return out

    raw_nums = _vol_nums("raw")
    beats_nums = _vol_nums("beats")
    for (vol, n) in sorted(per_ch):
        tok = f"ch_{n:03d}"
        if (vol, n) not in raw_nums:
            warnings.append(_err("final_without_raw", f"{tok}: 有定稿但无 raw 草稿（流程事实，供核对）"))
        if (vol, n) not in beats_nums:
            warnings.append(_err("final_without_beats", f"{tok}: 有定稿但无 beats 细纲（流程事实，供核对）"))

    # ---- 字数带偏离（只报数：封存拦截归 sync 的 word_band_gate，这里不阻断） ----
    if band_ok:
        lo, hi = band
        for tok, _, text in evidence.final_chapters(book):
            c = common.cjk_count(text)
            if c < lo or c > hi:
                warnings.append(_err("word_band_deviation", f"{tok}: 字数 {c} 在目标带 [{lo}, {hi}] 之外"))


    # ---- 线逾期（算术事实） ----
    try:
        g = evidence.gaps(book)
        for item in g["foreshadows"] + g["misunderstandings"]:
            if item["overdue"]:
                warnings.append(_err(
                    "line_overdue",
                    f"{item['id']}: target_ch={item['target_ch']} < 已定稿 "
                    f"{g['max_final_chapter']} 章"))
    except (ValueError, FileNotFoundError) as exc:
        errors.append(_err("state_unreadable", f"lines 不可读: {exc}"))

    # ---- tics 命中（project.style_guards × 定稿正文，纯计数） ----
    guards = [x for x in (proj.get("style_guards") or []) if isinstance(x, str) and x]
    if guards:
        for tok, _, text in evidence.final_chapters(book):
            for gtxt in guards:
                c = text.count(gtxt)
                if c:
                    warnings.append(_err("style_guard_hit",
                                         f"{tok}: 「{gtxt}」出现 {c} 次"))

    # ---- form 占比（>40% 卷内，数出来供主控调整） ----
    for vol, rec in evidence.form_distribution(book).items():
        for form, share in rec.get("shares", {}).items():
            if share > FORM_SHARE_LIMIT:
                warnings.append(_err("form_share_over_limit",
                                     f"{vol}: form「{form}」占比 {share:.0%} > {FORM_SHARE_LIMIT:.0%}"))
    stats["errors"] = len(errors)
    stats["warnings"] = len(warnings)
    return {"schema": "novel-studio.check/v1", "ok": not errors,
            "errors": errors, "warnings": warnings, "stats": stats}
