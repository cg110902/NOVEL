"""对白声纹基线与漂移检测（C2）——只测「怎么说话」，不测「说的是否符合人设」（机械不可判）。

方法：每主要角色抽取对白（引号段 + 说话人归属启发式）→ 建立滚动基线
（口头禅 n-gram（jieba 分词）/ 句长分布 / 语气词密度）→ 近窗偏离超阈出 info 级提示。

已知局限（如实记录，防误信）：
- 说话人归属是启发式：对话密集段（连引号互怼）会整段丢弃（宁漏报不误报）；
- 只测「怎么说话」：人设前后矛盾但腔调一致（如温婉角色突然发表暴论）机械不可判；
- 阈值是经验值非实测，全部走 project.json 的 voiceprint 键覆盖（PARAM_SPEC 单一真源）。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, evidence, state

try:  # jieba 已在引擎强援栈内（checks 运行时依赖），此处防御式导入
    import jieba
except ImportError:  # pragma: no cover
    jieba = None

DEFAULTS = {
    "min_lines": 12,      # 角色进入判定的基线最少对白条数（低于=样本不足，报了也是噪声）
    "recent_lines": 4,    # 观察窗内最少对白条数（不足不判）
    "window": 6,          # 近 N 章为观察窗
    "len_shift": 0.45,    # 句长均值相对基线的偏离比例阈值
    "mood_shift": 2.5,    # 语气词密度相对基线的变化倍数阈值
    "sig_min_count": 3,   # 口头禅入选基线的最低出现次数
}

# 单字语气词（对白内）：密度 = 出现次数 / 字数 × 100
MOOD_CHARS = "吧呢嘛哦呀啦咯哼切喂嘿呵咦嘘嗯唔啧欸"

# 引号段：「…」/ “…”/ "…"（2~200 字，跨行不算）
_QUOTE_RE = re.compile(r"「([^」\n]{2,200})」|[“\"]([^”\"\n]{2,200})[”\"]")
# 说话动词（归属启发式用）
_SAY_VERB_RE = re.compile(r"(说|道|问|答|喊|叫|笑|骂|嘀咕|嘟囔|开口|回话|接话|沉声|低声|冷哼)")


def cfg_for(book: Path) -> dict:
    """读取 project.json 的 voiceprint 覆盖值，缺失/非法逐键回落默认。"""
    proj = common.load_json(book / "project.json", default={}) or {}
    cfg = proj.get("voiceprint") or {}
    out = dict(DEFAULTS)
    if isinstance(cfg, dict):
        for k in DEFAULTS:
            v = cfg.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                out[k] = v
    return out


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n+", text) if p.strip()]


def extract_dialogues(book: Path) -> list[tuple[int, str, str]]:
    """全书对白抽取：(章号, 说话人规范名, 对白文本)，升序。

    说话人归属启发式（按优先级，失败即丢弃该段对白——宁漏报不误报）：
    1. 引号前 ~16 字内出现 实体名/别名 + 说话动词（「林牧沉声道：」）；
    2. 段内引号外文本恰好提及唯一实体名。
    """
    lookup = evidence.entity_lookup(book)  # {规范名: [本体名, 别名...]}
    flat: list[tuple[str, str]] = [(n, a) for n, aliases in lookup.items() for a in aliases]
    out: list[tuple[int, str, str]] = []
    for _tok, n, text in evidence.final_chapters(book):
        for para in _paragraphs(text):
            quotes = [m.group(1) or m.group(2) for m in _QUOTE_RE.finditer(para)]
            if not quotes:
                continue
            spans = [m.span() for m in _QUOTE_RE.finditer(para)]
            for qi, (q, (qs, _qe)) in enumerate(zip(quotes, spans)):
                prefix = para[max(0, qs - 16):qs]
                speaker = _attribute(prefix, flat)
                if speaker is None:
                    # 回退：整段引号外文本的唯一实体
                    outside = "".join(para[:qs] + para[spans[-1][1]:])
                    hits = {canon for canon, alias in flat if alias in outside}
                    speaker = hits.pop() if len(hits) == 1 else None
                if speaker is not None:
                    out.append((n, speaker, q))
    return out


def _attribute(prefix: str, flat: list[tuple[str, str]]) -> str | None:
    """引号前缀文本 → 说话人（实体名 + 说话动词紧邻，取最靠后者，长别名优先）。

    2字贪婪修复：别名按长度降序排序，同一位置出现时更长的别名优先（如“陆沉舟”优先于“陆沉”/“沉舟”），
    避免短别名抢占导致误归属。
    """
    # 长别名优先：同位置匹配时更精确
    sorted_flat = sorted(flat, key=lambda x: len(x[1]), reverse=True)
    best_idx, best = -1, None
    best_len = -1
    for canon, alias in sorted_flat:
        if not alias:
            continue
        idx = prefix.rfind(alias)
        while idx >= 0:
            after = prefix[idx + len(alias):]
            if len(after) <= 4 and _SAY_VERB_RE.search(after):
                # 位置更靠后者赢；同位置长度更长者赢（因已按长度降序，首次命中即最长）
                if idx > best_idx or (idx == best_idx and len(alias) > best_len):
                    best_idx, best, best_len = idx, canon, len(alias)
                break
            idx = prefix.rfind(alias, 0, idx)
    return best


def _mood_density(text: str) -> float:
    """每百字语气词次数。"""
    if not text:
        return 0.0
    hits = sum(1 for c in text if c in MOOD_CHARS)
    return hits * 100.0 / max(len(text), 1)


def _signature_words(lines: list[str], min_count: int, top: int = 3) -> list[str]:
    """基线口头禅：jieba 分词后出现 ≥ min_count 次的 ≥2 字词，频次降序取前 N。"""
    if not jieba or not lines:
        return []
    freq: dict[str, int] = {}
    for ln in lines:
        for w in jieba.lcut(ln):
            if len(w) >= 2 and re.match(r"^[\u4e00-\u9fa5]+$", w):
                freq[w] = freq.get(w, 0) + 1
    ranked = sorted((w for w, c in freq.items() if c >= min_count),
                    key=lambda w: -freq[w])
    return ranked[:top]


def voiceprint_report(book: Path) -> dict:
    """全部主要角色的声纹基线与近窗漂移判定。

    返回 {window, characters: [{name, baseline_lines, recent_lines, drift_reasons}]}，
    只含「基线样本充足且近窗有对白」的角色；drift_reasons 空 = 未漂移。
    """
    cfg = cfg_for(book)
    dialogues = extract_dialogues(book)
    if not dialogues:
        return {"window": cfg["window"], "characters": []}
    latest = max(n for n, _, _ in dialogues)
    base_cut = latest - cfg["window"]

    by_char: dict[str, dict[str, list[str]]] = {}
    for n, spk, q in dialogues:
        bucket = by_char.setdefault(spk, {"base": [], "recent": []})
        bucket["recent" if n > base_cut else "base"].append(q)

    chars = []
    for name, b in sorted(by_char.items()):
        if len(b["base"]) < cfg["min_lines"] or len(b["recent"]) < cfg["recent_lines"]:
            continue  # 样本不足：不判定（info 闸门宁漏报不误报）
        reasons: list[str] = []
        base_mean = sum(len(x) for x in b["base"]) / len(b["base"])
        rec_mean = sum(len(x) for x in b["recent"]) / len(b["recent"])
        if base_mean > 0 and abs(rec_mean - base_mean) / base_mean > cfg["len_shift"]:
            reasons.append(f"句长均值 {base_mean:.0f}→{rec_mean:.0f} 字")
        base_mood = sum(_mood_density(x) for x in b["base"]) / len(b["base"])
        rec_mood = sum(_mood_density(x) for x in b["recent"]) / len(b["recent"])
        if base_mood > 0 and (rec_mood / base_mood > cfg["mood_shift"]
                              or rec_mood / base_mood < 1.0 / cfg["mood_shift"]):
            reasons.append(f"语气词密度 {base_mood:.1f}→{rec_mood:.1f} 次/百字")
        sigs = _signature_words(b["base"], cfg["sig_min_count"])
        if sigs and len(b["recent"]) >= max(cfg["recent_lines"], 5):
            joined = "".join(b["recent"])
            vanished = [w for w in sigs if w not in joined]
            if len(vanished) == len(sigs):
                reasons.append("基线口头禅（" + "、".join(sigs) + "）在近窗全部消失")
        chars.append({"name": name, "baseline_lines": len(b["base"]),
                      "recent_lines": len(b["recent"]),
                      "mean_len": [round(base_mean, 1), round(rec_mean, 1)],
                      "mood": [round(base_mood, 1), round(rec_mood, 1)],
                      "signatures": sigs, "drift_reasons": reasons})
    return {"window": cfg["window"], "characters": chars}
