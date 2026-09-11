"""L1 合成书生成器：确定性 plan → 落盘（final/raw/beats）→ v3 提案 → 真 sync。

三条铁律（方案 §2.2）：
1. 确定性：plan_book() 是纯函数，同 (scale, seed) 字节级同构（canon_hash 可验）；
2. 引用织入：假正文按引用计划织入实体名、线标签、时间词与对白（引号「」＋"名+道："），
   使 dangling / alias / voiceprint / memory-scan / 引文接地 全链路真实吃到内容；
3. manifest 即 ground truth：plan（该发生什么）与 actual（state 里发生了什么）
   的 diff 必须为空——漂移 = harness 有 bug，先修 harness 再谈引擎结论。

规模差异不写死：全部档位参数来自 SCALES；生成密度（线/流水/事件/locked）按章数摊平。
"""
from __future__ import annotations

import random
import re
from datetime import date

from .common import (SCALES, ch_token, vol_token, write_json, load_json)

import sys
from pathlib import Path
if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import common as engc   # noqa: E402  (CJK 计数/原子写口径与引擎一致)

# ---------------------------------------------------------------------------
# 词库（确定性取样；题材中性，避免与引擎启发式词表撞车）
# ---------------------------------------------------------------------------
SURNAMES = "林沈顾苏陆叶秦江韩白周郑唐冯袁许傅钟温岑"
GIVEN = ("澈 屿 昭 衡 岚 烬 棠 铸 翎 渡 宴 深 川 岫 野 樵 鲤 萤 酌 桥 洲 烛 砚 汀 楼 笛 衣 声 让 岩 禾"
         .split())
ITEM_ADJ = "冷 锈 残 古 玄 青 赤 素 灵 影 寒 霞 焦 湿 铜 木".split()
ITEM_NOUN = "刀 剑 灯 印 镜 符 匣 链 幡 钟 图 笔 棋 伞 钩 环 钉 卷 牌 秤 壶 鞭 尺 梳 轮 锁 弓 盾 梭".split()
PLACE_A = "雾 潮 星 石 雪 沙 云 月 竹 苇 铁 盐".split()
PLACE_B = "渡 崖 墟 泽 关 台 巷 桥 林 窟 城 门 坞 渡".split()
FAC_A = "玄 青 赤 白 金 雷 影 潮 灯 秤 砂 隼".split()
FAC_B = "灯行 刀盟 钱庄 书院 卫所 世家 商号 塔 舵局 印房".split()
LINE_ADJ = "无主 半截 旧时 无字 倒悬 三寸 染血 带缺 双生 逆刻 上锁 浸油 褪色 连枝".split()
LINE_NOUN = ("空灯 残页 木匣 铜印 名单 地契 欠条 香灰 骨笛 账册 船票 锁匙 血书 信物 半碑 井图 药方 "
             "棋谱 嫁妆 遗言 路引 田册 钥匙 当票 契约 牌位 木鱼 皮影 铜镜 灯笼 竹牌 瓦当 石敢当 帆角 磨心".split())
MOOD_LABELS = "隐忍 戒备 怅然 振奋 疑心 平静 急切 压火".split()
TODAY_SLOTS = "五更 正午 黄昏 子夜".split()
FORMS = ["暗流汇聚", "危机逼近", "战后清点", "生死博弈", "爽感兑现", "疑云压境"]
# 高压章型（与模板 high_heat_forms 对齐的两个）
HIGH_HEAT = {"危机逼近", "生死博弈"}
TIER_NAMES = ["凝气一层", "凝气三层", "凝气五层", "筑基初境", "筑基中境", "金丹在望", "金丹初凝",
              "金丹稳固", "元婴一线", "元婴得势"]

SHORT_LINES = ["先记着。", "不急。", "走。", "东西留下。", "我只问一遍。", "这话到此为止。", "天亮前别动。",
               "数到三。", "他不敢动手。", "规矩改了。", "记住这张脸。", "回去等话。"]
MID_LINES = ["这单生意做到这一步，谁都没了退路吧。", "账可以慢慢对，人不能久留在这里。",
             "你要的东西在我手里，可我还没打算给呢。", "先把门关上，屋里说话不方便啊。",
             "当年他欠下的，今日连本带利都得认吧。", "别拿老规矩压我，这一回不一样了。"]
LONG_LINES = ("账上的数目一夜之间翻了上去，可铺子里的存货一件也没见多，这样的进项撑不了三天，"
              "更撑不过一个雨季；我劝你今夜就把后路想清楚，莫要等到门口围满了人再喊冤。",
              "当年灯会上的规矩是三家共议、一人一票，如今倒好，票箱换了锁，钥匙只有一把，"
              "还在最不该拿着它的人手里攥着，这样的场面诸位也都看见了，往后谁还敢把身家性命押在议桌上。")

# 正文句模（占位符填充）
_OPENERS = ["更漏敲过，{place}的灯笼又矮了一截。", "{a}在{place}的台阶上站了半夜，谁也没先开口。",
            "天亮之前，{place}只有风在动。", "{a}把斗笠压低半寸，从{place}侧门进去。",
            "{b}到的时候，{place}的灯还亮着三盏。", "{place}今夜不设宴，只设一张条案。"]
_MIDS = ["{a}把{label}挪到左手，眼睛没离开{b}。", "名册翻到第三页，{b}忽然停住了手。",
         "{a}只说了三个字，对面的脸色就变了。", "条案上摆着三样东西，缺的那一样谁都知道是什么。",
         "{b}把封条验了两遍，确认火漆没有动过。", "{a}数了数人手，不够，于是把刀收回鞘里。",
         "街口的人散得很快，只剩巡夜的灯笼还挂在原处。", "{b}临走时留下一句：三日后，老地方。"]
_CLOSERS = ["直到天亮，{place}都没有人来。", "{a}吹熄了最后一盏灯，转身走进雾里。",
            "这件事到此只能收住，往后的账往后算。", "风把门带上，屋里只剩算盘的响声。"]
_MENTION = ["众人嘴上不提，心里都记着{label}这四个字。", "{a}问起{label}，{b}沉默了三息。",
            "{label}的下落，今夜必须在{place}问出个准数。"]
_MOOD_LINE = {"隐忍": "这话我记下了，别急。", "戒备": "你退后半步，我们有的谈。",
              "怅然": "当年要是有今天就好了。", "振奋": "今日之后，规矩得改。",
              "疑心": "这句话，你再说一遍。", "平静": "慌什么，天塌不下来。",
              "急切": "现在就要答复，过了今夜不作数。", "压火": "我数到三，你最好已经决定了。"}

FACT_WORDS = ["灯下之约只认灯不认人", "旧闸三年一修今年逾期", "渡口改姓只此一回", "秤星换过不得外传",
              "三盏灯的债压给下任", "封条落款必须是活印", "井图出阁必配铜钥", "碑文改一字赔一座桥"]


def line_label(plan: dict, lid: str) -> str:
    """线在正文中必须可扫的标签名：foreshadow=name，mis=content，kno=secret（引擎按整串扫描）。"""
    l = plan["lines"].get(lid) or {}
    return str(l.get("name") or l.get("content") or l.get("secret") or lid)


def _chinese_len(s: str) -> int:
    return engc.cjk_count(s)


# ---------------------------------------------------------------------------
# 计划
# ---------------------------------------------------------------------------

def plan_book(scale: str, seed: int | None = None) -> dict:
    cfg = dict(SCALES[scale])
    seed = cfg["seed_default"] if seed is None else seed
    rng = random.Random(seed)
    n_total = cfg["chapters"]
    vols = cfg["vols"]

    vol_size = n_total // vols
    vol_plan = []
    start = 1
    for i in range(1, vols + 1):
        end = n_total if i == vols else start + vol_size - 1
        vol_plan.append({"name": vol_token(i), "start": start, "end": end})
        start = end + 1

    # ---- 实体名册（id/名唯一，别名唯一——撞名留给 chaos F07）----
    def _unique_names(k, pool_fn):
        out, seen = [], set()
        guard = 0
        while len(out) < k and guard < k * 60:
            guard += 1
            nm = pool_fn(rng)
            if nm and nm not in seen:
                seen.add(nm)
                out.append(nm)
        return out

    def person_name(r):
        return r.choice(SURNAMES) + r.choice(GIVEN)

    def item_name(r):
        return r.choice(ITEM_ADJ) + r.choice(ITEM_NOUN)

    def place_name(r):
        return r.choice(PLACE_A) + r.choice(PLACE_B)

    def fac_name(r):
        return r.choice(FAC_A) + r.choice(FAC_B)

    n_p = max(12, int(cfg["entities"] * 0.24))
    n_it = max(8, int(cfg["entities"] * 0.36))
    n_fa = max(4, int(cfg["entities"] * 0.16))
    n_pl = max(6, int(cfg["entities"] * 0.24))
    persons = _unique_names(n_p, person_name)
    items = _unique_names(n_it, item_name)
    places = _unique_names(n_pl, place_name)
    factions = _unique_names(n_fa, fac_name)

    entities = []
    eid = {"persons": 2, "items": 1, "factions": 1, "places": 1}
    prefix = {"persons": "p", "items": "it", "factions": "fac", "places": "loc"}
    # 主角在 init 已入 p_001
    entities.append({"id": "p_001", "name": "主角", "table": "persons", "rank": 0, "create_ch": 1})
    for i, nm in enumerate(persons[1:]):
        entities.append({"id": f"p_{eid['persons']:03d}", "name": nm, "table": "persons",
                         "rank": i + 1, "create_ch": 1 if i < 11 else min(n_total, 2 + (i // 24))})
        eid["persons"] += 1
    for i, nm in enumerate(items):
        chrg = 3 + i % 9 if i < 8 else None
        entities.append({"id": f"it_{eid['items']:03d}", "name": nm, "table": "items", "rank": i + 30,
                         "create_ch": 1 if i < 10 else min(n_total, 3 + (i // 22)),
                         "charges": chrg, "max_charges": (chrg or 0) + 2 or None,
                         "holder_ch1": persons[1 + i % max(1, len(persons) - 1)] if i < 10 else None})
        eid["items"] += 1
    for i, nm in enumerate(factions):
        entities.append({"id": f"fac_{eid['factions']:03d}", "name": nm, "table": "factions", "rank": i + 60,
                         "create_ch": 1})
        eid["factions"] += 1
    for i, nm in enumerate(places):
        entities.append({"id": f"loc_{eid['places']:03d}", "name": nm, "table": "places", "rank": i + 90,
                         "create_ch": 1 if i < 6 else min(n_total, 4 + (i // 18))})
        eid["places"] += 1
    places_core = [e for e in entities if e["table"] == "places" and e["create_ch"] == 1]
    persons_core = [e for e in entities if e["table"] == "persons" and e["create_ch"] == 1]
    # Zipf 权重（长尾龙套）
    for e in entities:
        e["weight"] = 1.0 / (e["rank"] + 3)
    # 别名：给部分中层角色挂别名（全书唯一）
    alias_pool = _unique_names(min(24, len(persons) + len(items)), lambda r: r.choice(GIVEN) + r.choice("客老生少"))
    ai = 0
    for e in entities:
        if e["rank"] in (4, 7, 12, 18, 25, 34, 41, 55) and ai < len(alias_pool):
            e["alias"] = alias_pool[ai]
            ai += 1

    # ---- 线的排程 ----
    L = cfg["lines_total"]
    lfa = int(L * 0.6)
    lmi = int(L * 0.2)
    lkn = L - lfa - lmi
    line_slots = _spread(lfa, 3, max(4, n_total - max(1, n_total // 14)))
    mis_slots = _spread(lmi, 5, n_total - 6)
    kno_slots = _spread(lkn, 7, n_total - 6)
    label_pool = _unique_labels(max(lfa + 8, 40))

    lines: dict[str, dict] = {}
    gid = mid_ = kid = 0
    dead_n = max(1, int(lfa * 0.05))
    # 死线占最前 5% 槽位：正文自 plant+2 起封口，gap 随 N 线性拉大，
    # 「正文章距 > 冷阈×2」在任意 N≥114 下确定成立（F02 判据可移植）
    dead_slots = line_slots[:dead_n]                # 死线铺在早期槽位：gap 随 N 线性拉大
    for i, pc in enumerate(line_slots):
        gid += 1
        lid = f"GUN-{gid:03d}"
        kind_tier = rng.choices(["hot", "warm", "cold"], weights=[20, 50, 25])[0]
        if i < dead_n:
            pc = dead_slots[i]
            kind_tier = "dead"
        delay = {"hot": rng.randint(4, 10), "warm": rng.randint(12, 50), "cold": rng.randint(55, 150)}
        if kind_tier in ("dead",):
            target, recall = "longline", None
        else:
            recall = min(n_total - 1, pc + delay[kind_tier])
            target = recall
            if recall - pc < 3:
                target, recall = "longline", None      # 尾段来不及回收的长线（不入到期账）
                kind_tier = "cold"
        lines[lid] = {"kind": "foreshadow", "id": lid, "name": label_pool[i % len(label_pool)],
                      "plant_ch": pc, "target": target, "recall_ch": recall,
                      "tier": kind_tier, "weight": {"hot": 3, "warm": 2, "cold": 1, "dead": 1}[kind_tier],
                      "last_mention": pc}
    for i, pc in enumerate(mis_slots):
        mid_ += 1
        lid = f"MIS-{mid_:03d}"
        recall = min(n_total - 1, pc + rng.randint(8, 40))
        lines[lid] = {"kind": "misunderstanding", "id": lid, "plant_ch": pc, "target": recall,
                      "recall_ch": recall if recall - pc >= 3 else None, "tier": "warm", "weight": 1,
                      "parties": [persons_core[i % len(persons_core)]["name"],
                                 persons_core[(i + 3) % len(persons_core)]["name"]],
                      "content": f"第{i + 1}号旧账被认成了{FACT_WORDS[i % len(FACT_WORDS)]}",
                      "truth": "账房新抄的流水可以作证"}
        if lines[lid]["recall_ch"] is None:
            lines[lid].update(target="longline")
    for i, pc in enumerate(kno_slots):
        kid += 1
        lid = f"KNO-{kid:03d}"
        recall = min(n_total - 1, pc + rng.randint(20, 90))
        if recall - pc < 4:
            lines[lid] = {"kind": "knowledge", "id": lid, "plant_ch": pc, "target": "longline",
                          "recall_ch": None, "tier": "cold", "weight": 2}
        else:
            lines[lid] = {"kind": "knowledge", "id": lid, "plant_ch": pc, "target": recall,
                          "recall_ch": recall, "tier": "warm", "weight": 2}
        lines[lid].update(secret=f"渡口改契的内情第{i + 1}节",
                          holders=[persons_core[(i + 1) % len(persons_core)]["name"]])
    # F16 跨卷旧线（vols≥2）：卷1埋、卷2/3收——必须不被 longline_stale 点名
    f16_ids = []
    if vols >= 2:
        cand = [l for l in lines.values() if l["kind"] == "foreshadow" and l["tier"] in ("warm", "cold")
                and l["plant_ch"] <= vol_plan[0]["end"] - 10
                and isinstance(l.get("target"), int) and l.get("recall_ch") and l["recall_ch"] > vol_plan[1]["start"]]
        for l in cand[:3]:
            f16_ids.append(l["id"])
    # F03 冷前置对（deadline A ← 冷线 child B）
    f03 = None
    dl = [l for l in lines.values() if l["tier"] == "dead"]
    if dl:
        a = dl[0]
        b_plant = min(n_total - 2, a["plant_ch"] + max(35, n_total // 6))
        gid += 1
        bid = f"GUN-{gid:03d}"
        lines[bid] = {"kind": "foreshadow", "id": bid, "name": label_pool[len(label_pool) - 1],
                      "plant_ch": b_plant, "target": "longline", "recall_ch": None,
                      "tier": "dead", "weight": 1, "last_mention": b_plant, "requires": [a["id"]],
                      "f03_child": True}
        f03 = {"child": bid, "prereq": a["id"], "plant_ch": b_plant, "resolve_ch": n_total}
    _f03_pre = f03["prereq"] if f03 else None   # F03 前置线：正文只留 plant/回收两处锚

    # ---- 埋进 script 的全局轨迹 ----
    tier_up_steps = [c for c in range(40, n_total - 12, 40)]
    tier_fall_target_pre = "p_008" if (n_total >= 80 and n_p > 8) else None
    tier_fall_ch = (n_total - 12) if tier_fall_target_pre else None
    tier_fall_warm_ch = max(60, (tier_fall_ch - 1) // 2 * 2) if tier_fall_ch else None
    if tier_fall_warm_ch and tier_fall_ch and tier_fall_warm_ch >= tier_fall_ch - 1:
        tier_fall_warm_ch = tier_fall_ch - 20
    tier_fall_name = next((e["name"] for e in entities if e["id"] == "p_008"), "") if tier_fall_target_pre else ""
    tier_fall_target = tier_fall_target_pre
    style_shift = None
    if n_total >= 150:
        ws = 200 if n_total <= 320 else 1000
        style_shift = {"who": persons_core[4]["name"], "start": ws, "end": ws + 6}
    freeze_start = max(5, n_total - 3)
    overdraft = {"pool": "oil", "start": max(20, (n_total * 5) // 6 // 10 * 10), "recover_after": 8}
    mood_drift_ch = 20 if n_total >= 30 else None   # F15 埋点（beats 表 vs 实际情绪）

    # ---- 逐章日程表 ----
    chapters: dict[int, dict] = {}
    day = 0
    by_ch_plant: dict[int, list] = {}
    by_ch_resolve: dict[int, list] = {}
    for l in lines.values():
        by_ch_plant.setdefault(l["plant_ch"], []).append(l)
        if l.get("recall_ch"):
            by_ch_resolve.setdefault(l["recall_ch"], []).append(l)
    created: dict[int, list] = {}
    for e in entities:
        created.setdefault(e["create_ch"], []).append(e)
    locked_next = 1
    retired: list[str] = []
    active_locks: list[str] = []
    lock_events: dict[int, list] = {}
    alive = {e["name"] for e in entities if e["table"] == "persons"}
    deaths = []
    if len(persons_core) >= 6:
        deaths = [({"who": persons_core[3]["name"], "ch": max(9, int(n_total * 0.45))}),
                  ({"who": persons_core[5]["name"], "ch": max(12, int(n_total * 0.62))})]
    death_by_ch: dict[int, list] = {}
    for d in deaths:
        death_by_ch.setdefault(d["ch"], []).append(d)
    tx_bal = {"stone": 5000, "ticket": 300, "oil": 800}
    remind_sched: dict[int, list] = {}
    for lid, l in lines.items():
        if l["kind"] != "foreshadow":
            continue
        end = l.get("recall_ch") or n_total + 1
        k = l["plant_ch"] + 8
        while k < end:
            remind_sched.setdefault(k, []).append(lid)
            k += 8

    ledger_replay: dict[str, list] = {"stone": [], "ticket": [], "oil": []}
    roster_ready = {"persons": {e["name"] for e in entities if e["table"] == "persons" and e["create_ch"] == 1},
                    "items": {e["name"] for e in entities if e["table"] == "items" and e["create_ch"] == 1},
                    "places": {e["name"] for e in entities if e["table"] == "places" and e["create_ch"] == 1},
                    "factions": {e["name"] for e in entities if e["table"] == "factions" and e["create_ch"] == 1}}
    injury_trace, renown_trace = [], []
    for n in range(1, n_total + 1):
        for e in created.get(n, []):
            roster_ready[e["table"]].add(e["name"])
        day += rng.choices([0, 1, 1, 1, 2, 3], weights=[12, 52, 24, 8, 3, 1])[0]
        vol = next(v for v in vol_plan if v["start"] <= n <= v["end"])
        form = FORMS[(n + (n // (vol_size or 1))) % len(FORMS)]
        # 避免与上一章同 form（beats_form_repeat_without_reason 是 error 档）
        prev_form = chapters.get(n - 1, {}).get("form")
        if form == prev_form:
            form = next(f for f in FORMS if f != form)
        if form in HIGH_HEAT and chapters.get(n - 1, {}).get("form") in HIGH_HEAT \
                and chapters.get(n - 2, {}).get("form") in HIGH_HEAT:
            form = "战后清点" if prev_form != "战后清点" else "暗流汇聚"
        dead_here = [d["who"] for d in death_by_ch.get(n, [])]
        pool = [x for x in roster_ready["persons"] if x in alive and x not in dead_here]
        weights = [max(e["weight"] for e in entities if e["name"] == x) for x in pool]
        k = rng.randint(4, 12) if len(pool) > 6 else len(pool)
        cast: list[str] = []
        if "主角" in pool and rng.random() < 0.9:
            cast.append("主角")
        while len(cast) < min(k, len(pool)):
            nm = rng.choices([x for x in pool if x not in cast],
                             weights=[w for x, w in zip(pool, weights) if x not in cast])[0]
            cast.append(nm)
        if mood_drift_ch == n and "主角" not in cast:      # F15 埋点必须生效
            cast.insert(0, "主角")
        cast_places = [x for x in roster_ready["places"]]
        place = cast_places[n % len(cast_places)]
        mentions = []

        def _label(l: dict) -> str:
            return str(l.get("name") or l.get("content") or l.get("secret") or "旧账")

        for lid, l in lines.items():
            if l.get("recall_ch") == n:      # 本章回收：回收句自带线名
                mentions.append(_label(l))
                l["last_mention"] = n
                continue
            if lid == _f03_pre:
                l["last_mention"] = n
                continue          # F03 前置线：mentions 全程封口（含 plant 章），防 terms 污染
            if l["plant_ch"] < n <= (l.get("recall_ch") or n_total + 9):
                gap_ok = (n - l.get("last_mention", l["plant_ch"])) >= 4
                if gap_ok or rng.random() < 0.18:
                    if l["tier"] == "dead" and n > l["plant_ch"] + 2:
                        continue  # 死线正文封口（plant+2 后），gap 拉满 → longline_stale
                    mentions.append(_label(l))
                    l["last_mention"] = n
        moods: dict[str, dict] = {}
        if n > freeze_start:
            moods = {}                      # F17 冻结窗：情绪快照停止上账
        else:
            for who in cast[:6]:
                lab = rng.choice(MOOD_LABELS)
                moods[who] = {"label": lab, "level": rng.randint(1, 4), "quote": _MOOD_LINE[lab]}
        beats_moods = {w: dict(v) for w, v in moods.items()}
        if mood_drift_ch == n and "主角" in cast:
            beats_moods["主角"] = {"label": "暴怒", "level": 5}   # F15：表里写暴怒，账上记隐忍
            if "主角" in moods:
                moods["主角"] = {"label": "隐忍", "level": 2, "quote": _MOOD_LINE["隐忍"]}
        events = []
        for i in range(cfg["ev_per_ch"]):
            a = cast[i % len(cast)]
            b = cast[(i + 2) % len(cast)]
            ev_place = cast_places[(n * 3 + i) % len(cast_places)]
            events.append({"time": f"第{day}日{TODAY_SLOTS[i % 4]}",
                           "event": f"第{n}回{a}押{ev_place}文书过所，与{b}交割{i + 1}号防务，画押三遍",
                           "participants": [a, b], "place": ev_place})
        if tier_fall_target_pre and n == tier_fall_warm_ch:
            events.append({"time": f"第{day}日正午", "participants": [tier_fall_name],
                           "event": f"第{n}回{tier_fall_name}当众力劈石锁，突破凝气四层，名册添一笔",
                           "place": place})
        if n in tier_up_steps:
            k_th = tier_up_steps.index(n) + 1
            events.append({"time": f"第{day}日正午", "participants": ["主角"],
                           "event": f"第{n}回主角于{place}闭关三日突破{rng.choice(TIER_NAMES)}，关口灯火齐亮",
                           "place": place})
        txs = []
        pools = [("stone", "支出", -1), ("ticket", "收入", 1), ("stone", "收入", 1)]
        for i in range(cfg["tx_per_ch"]):
            pid, kind_s, sign = pools[i % 3]
            sign = rng.choice([-1, 1]) if kind_s == "支出" else 1
            amt = rng.randint(5, 60) * sign
            if pid == "oil" or (n in range(overdraft["start"], overdraft["start"] + overdraft["recover_after"])
                               and i == cfg["tx_per_ch"] - 1):
                pass
            txs.append({"pool": pid, "delta": int(amt),
                        "type": "expense" if amt < 0 else "income",
                        "subject": f"第{n}回{kind_s}第{i + 1}笔"})
            txs[-1]["balance"] = tx_bal[pid] + int(amt)
            tx_bal[pid] += int(amt)
        # 超支窗口：一笔把 oil 池打穿（baked F05，pool_overdrawn 必报）
        if n == overdraft["start"]:
            txs.append({"pool": "oil", "delta": -(tx_bal["oil"] + 600), "type": "expense",
                        "subject": f"第{n}回油行逼债一次结清", "balance": -600})
            tx_bal["oil"] = -600
        if n == overdraft["start"] + overdraft["recover_after"]:
            txs.append({"pool": "oil", "delta": 700, "type": "income",
                        "subject": f"第{n}回义仓回赠油资", "balance": tx_bal["oil"] + 700})
            tx_bal["oil"] += 700
        for pid in tx_bal:
            ledger_replay[pid].append({"ch": n, "balance": tx_bal[pid]})
        for p in ledger_replay:
            pass
        locked_ops, retire_ops = [], []
        if n % max(6, min(12, n_total // 8)) == 5 and len(active_locks) < 13:
            lid = f"LOCK-{locked_next:03d}"
            locked_next += 1
            fact = FACT_WORDS[(locked_next + n) % len(FACT_WORDS)] + f"（第{n}回立）"
            kind = "rule" if n % 3 else "promise"
            locked_ops.append({"id": lid, "fact": fact, "kind": kind, "note": f"红线：第{n}回旧约不得复述改口",
                              "quote": f"「{fact}」，老朝奉把话钉死在案上。", "refs": [cast[0] if cast else "主角"],
                              "ch": n})
            active_locks.append(lid)
            lock_events.setdefault(n, []).append(locked_ops[-1])
        if len(active_locks) >= 13:
            old = active_locks.pop(0)
            retire_ops.append({"id": old, "reason": f"第{n}回销案：旧约并入新册", "ch": n})
            retired.append(old)
        cog = []
        if cast:
            who = cast[1] if len(cast) > 1 else cast[0]
            kno_ids = sorted(l for l, v in lines.items() if v["kind"] == "knowledge" and v["plant_ch"] < n)
            if kno_ids:
                tref = kno_ids[n % len(kno_ids)]
                content = f"{who}确认{lines[tref]['secret']}尚属属实"
                cog.append({"character": who, "kind": "fact", "content": content,
                            "quote": f"{who}承认：{content}", "truth_ref": tref})
        ops_ch = {
            "n": n, "vol": vol["name"], "form": form, "day": day,
            "slot": TODAY_SLOTS[n % 4],
            "place": place, "cast": cast, "mentions": mentions, "moods": moods,
            "beats_moods": beats_moods, "events": events, "txs": txs,
            "plants": [l["id"] for l in by_ch_plant.get(n, [])],
            "resolves": [l["id"] for l in by_ch_resolve.get(n, [])],
            "create_ch": [e["id"] for e in created.get(n, [])],
            "locked_ops": locked_ops, "retire_ops": retire_ops, "cog": cog,
            "deaths": dead_here, "injury_at": n in (max(6, n_total // 5),),
            "injury_clear": n in (max(10, n_total // 2),),
            "reminds": remind_sched.get(n, []),
            "tier_fall_warm": bool(tier_fall_target_pre) and n == tier_fall_warm_ch,
            "tier_up": n in tier_up_steps, "tier_fall": tier_fall_ch == n,
            "style_shift": bool(style_shift and style_shift["start"] <= n <= style_shift["end"]),
            "style_who": style_shift["who"] if style_shift else None,
            "title": f"第{n}章 压力纪事{n:03d}",
        }
        if ops_ch["injury_at"]:
            injury_trace.append([n, 2])
        if ops_ch["injury_clear"]:
            injury_trace.append([n, 0])
        renown = 0
        if n > 30:
            renown = 1 + (n - 30) // 50
            renown_trace.append([n, renown])
        ops_ch["renown"] = renown
        for pid in ("stone", "ticket", "oil"):
            pass
        chapters[n] = ops_ch
        for d in dead_here:
            alive.discard(d)
        for i, l in enumerate(txs):
            pass

    # F04 埋点：一次无事件支撑的位阶跌落（p_004 铁肩）——必须被抓

    faults_baked = []
    for l in lines.values():
        if l["tier"] == "dead" and not l.get("f03_child"):
            faults_baked.append({"fault_id": "F02", "type": "dead_line", "inject_ch": l["plant_ch"],
                                 "expect_code": "longline_stale", "target": l["id"]})
    faults_baked.append({"fault_id": "F04", "type": "tier_fall_no_event", "inject_ch": tier_fall_ch or 0,
                         "expect_code": "tier_shift_without_event", "target": tier_fall_target or ""})
    faults_baked.append({"fault_id": "F05", "type": "pool_overdrawn", "inject_ch": overdraft["start"],
                         "expect_code": "pool_overdrawn", "target": "oil"})
    if mood_drift_ch:
        faults_baked.append({"fault_id": "F15", "type": "mood_plan_actual", "inject_ch": mood_drift_ch,
                             "expect_code": "mood_plan_actual_drift", "target": "ch"})
    faults_baked.append({"fault_id": "F17", "type": "mood_freeze", "inject_ch": freeze_start,
                         "expect_code": "mood_snapshot_stale", "target": "current"})
    if style_shift:
        faults_baked.append({"fault_id": "F14", "type": "voice_shift", "inject_ch": style_shift["start"],
                             "expect_code": "voiceprint_drift", "target": style_shift["who"]})
    if f03:
        faults_baked.append({"fault_id": "F03", "type": "cold_prereq_script", "inject_ch": f03["plant_ch"],
                             "expect_code": None, "target": f03["child"], "note": "stdout 信号（proposal check）"})

    plan = {
        "schema": "novel-studio.stress-manifest/v1", "stage": "plan",
        "scale": scale, "seed": seed, "chapters": n_total,
        "band": cfg["band"], "words_mu": cfg["words_mu"], "words_sd": cfg["words_sd"],
        "words_min": cfg["words_min"], "words_max": cfg["words_max"],
        "bible_chars": cfg["bible_chars"], "tx_per_ch": cfg["tx_per_ch"],
        "vols": vol_plan, "protagonist": "主角",
        "entities": [{"id": e["id"], "name": e["name"], "table": e["table"], "create_ch": e["create_ch"],
                      "alias": e.get("alias", ""), "holder0": e.get("holder_ch1", ""),
                      "max_charges": e.get("max_charges")} for e in entities],
        "lines": {lid: {k: v for k, v in l.items() if k != "last_mention"} for lid, l in lines.items()},
        "chapter_meta": {n: {k: v for k, v in ch.items() if k in
                             ("n", "day", "place", "cast", "form", "vol", "moods", "beats_moods", "events",
                              "txs", "plants", "resolves", "create_ch", "locked_ops", "retire_ops",
                              "cog", "deaths", "renown", "injury_at", "injury_clear", "tier_up", "reminds", "tier_fall_warm",
                              "tier_fall", "style_shift", "style_who", "title", "mentions", "slot")}
                         for n, ch in chapters.items()},
        "ledger_replay": ledger_replay,
        "clock_trace": [{"ch": n, "time_day": ch["day"]} for n, ch in chapters.items()],
        "entities_trace": {"injury": injury_trace, "renown": renown_trace, "deaths": deaths,
                           "tier_up_steps": tier_up_steps, "tier_fall_ch": tier_fall_ch,
                           "tier_fall_id": tier_fall_target, "tier_fall_warm_ch": tier_fall_warm_ch},
        "moods_last_update_ch": freeze_start - 1,
        "f03": f03, "f16_ids": f16_ids, "overdraft": overdraft,
        "style_shift": style_shift, "freeze_start": freeze_start,
        "faults": faults_baked,
    }
    return plan


def _spread(count: int, first: int, last: int) -> list[int]:
    if count <= 0:
        return []
    last = max(first, last)
    step = (last - first) / max(1, count - 1) if count > 1 else 0.0
    out = []
    cur = first
    for i in range(count):
        out.append(int(cur))
        cur += step
    # 去重：同章多条 plant 保序聚合（v3 允许一提案多 op）
    return out


def _unique_labels(k: int) -> list[str]:
    out, seen = [], set()
    for a in LINE_ADJ:
        for n in LINE_NOUN:
            nm = f"{a}{n}"
            if nm not in seen:
                seen.add(nm)
                out.append(nm)
                if len(out) >= k:
                    return out
    return out


# ---------------------------------------------------------------------------
# 落盘（build 与 soak 共用）
# ---------------------------------------------------------------------------

def _final_text(plan: dict, n: int) -> str:
    ch = plan["chapter_meta"][n]
    rng = random.Random((plan["seed"] * 100003) ^ (n * 7919))
    target = max(plan["words_min"], min(plan["words_max"],
                                        int(rng.gauss(plan["words_mu"], plan["words_sd"]))))
    lines_of_ch = plan["lines"]
    parts = [f"# {ch['title']}", ""]
    body: list[str] = []

    def fmt(t: str, *, who=None, label=None) -> str:
        cast = ch["cast"] or ["主角"]
        a = who or cast[rng.randrange(len(cast))]
        b = cast[(rng.randrange(len(cast)) + 1) % len(cast)] if len(cast) > 1 else a
        if label is None:
            ms = ch["mentions"]
            label = ms[rng.randrange(len(ms))] if ms else "旧账"
        return t.format(a=a, b=b, place=ch["place"], label=label)

    body.append(fmt(rng.choice(_OPENERS)))
    para = []
    # 1200 段迭代上限 = 字数地狱档（words_mu 5000+）要真注到带内；
    # 普通书靠 target 提前 break，输出与旧版逐字一致（canon 不含正文，互不污染）
    for i in range(1200):
        if sum(_chinese_len(x) for x in body + para) >= target:
            break
        if ch["mentions"] and i < len(ch["mentions"]) * 2 and i % 2 == 0:
            lbl = ch["mentions"][(i // 2) % len(ch["mentions"])]
            para.append(fmt(rng.choice(_MENTION), label=lbl))
        elif i % 7 == 3 and ch["cast"]:
            who = ch["cast"][(i // 7) % len(ch["cast"])]
            if ch.get("style_shift") and who == ch.get("style_who"):
                para.append(f'{who}道：“{LONG_LINES[i % len(LONG_LINES)]}”')
            else:
                pool = MID_LINES if who != "主角" else SHORT_LINES
                q = rng.choice(pool)
                para.append(f'{who}道：“{q}”')
        else:
            para.append(fmt(rng.choice(_MIDS)))
        if len(para) >= 4:
            body.append("".join(para))
            para = []
    # 情绪 quote 必须以对白形式在正文出现（引文柔性接地要求逐字命中）
    for who, mv in ch["moods"].items():
        body.append(f'{who}道：“{mv["quote"]}”')
    # 回收句/埋点句：线标签全串入正文（memory 扫描按 name|content|secret 整串命中）。
    # F03 前置线例外：正文永不落笔（保证读者画像停 in never/impression 档，
    # 「回收的前置依赖已冷却」信号在任意 N 下确定命中；其提案 op 照常注册不受影响）。
    _f03_pre = (plan.get("f03") or {}).get("prereq")
    for lid in ch["resolves"] + ch["plants"]:
        if lid == _f03_pre and n != plan["lines"][lid]["plant_ch"]:
            continue  # 前置线只留 plant 章一次锚（gap=N-plant 必冷），后续章零回响
        body.append(fmt("当夜清点，{label}物归原主，这一节算是翻了过去。", label=line_label(plan, lid)))
    # locked 引用句（fact 原文入正文，quote 字段即此句）
    for lk in ch["locked_ops"]:
        body.append(lk["quote"])
    for c in ch["cog"]:
        body.append(c["quote"])
    if para:
        body.append("".join(para))
    if ch["cast"]:
        body.append(fmt(rng.choice(_CLOSERS)))
    out = "\n\n".join(body).replace("“", "“").replace("”", "”")
    if not out.endswith(("。", "！", "？", "……")):
        out += "。"
    return parts[0] + "\n\n" + out + "\n"


def _beats_text(plan: dict, n: int) -> str:
    ch = plan["chapter_meta"][n]
    fm = ["---", f"chapter: {ch_token(n)}", f"vol: {ch['vol']}", f"form: {ch['form']}",
          f"pov: {plan['protagonist']}", f"words: {plan['words_mu']}", "---"]
    md = list(fm)
    md.append("\n## 本章目标\n")
    first_label = ch["mentions"][0] if ch["mentions"] else "本回交割单"
    md.append(f"- 目标：在{ch['place']}完成第{n}回交割，落定{first_label}的归属并画押。")
    if ch["resolves"]:
        md.append(f"- 目标：把{'、'.join(ch['resolves'])}对应的事项当场结清。")
    md.append("\n## 线动作\n")
    for lid in ch["resolves"]:
        md.append(f"- resolve: {lid}")
    for lid in ch["plants"]:
        md.append(f"- plant {lid}")
    md.append("\n## 场景脉络\n")
    for si in range(3):
        who = ch["cast"][si % max(1, len(ch["cast"]))] if ch["cast"] else "主角"
        md.append(f"### 场景{si + 1}：{ch['place']}侧厅\n"
                  f"{who}与对方清点{si + 1}号箱封，登记簿逐页过目，缺页当场补签。")
    if ch["beats_moods"]:
        md.append("\n#### 出厂情绪表")
        for who, mv in ch["beats_moods"].items():
            md.append(f"- {who}：{mv['label']}（{mv['level']}/5）")
        if not ch["moods"]:
            md.append('- 出厂情绪：（无特殊交代写"无"）')
    lock_now: list[str] = []
    for m in range(1, n + 1):
        cm = plan["chapter_meta"][m]
        lock_now.extend(lk["id"] for lk in cm["locked_ops"])
        for rt in cm["retire_ops"]:
            if rt.get("id") in lock_now:
                lock_now.remove(rt["id"])
        if cm["deaths"]:
            lock_now.append(f"death:ch{m:03d}")
    if lock_now:
        md.append("\n## 不可逆事实台账（LOCK）\n")
        for x in lock_now[-8:]:
            md.append(f"- {x}：既成事实，后续章节不得回跳。")
    md.append("\n## 交付契约\n")
    md.append(f"- **必须落地**：第{n}回交割清单三页齐全，封条不得破损。")
    md.append(f"- **禁止回跳**：{ch['place']}不得写成其他渡口。")
    return "\n".join(md) + "\n"


def _proposal_ops(plan: dict, n: int) -> dict:
    ch = plan["chapter_meta"][n]
    ops: list[dict] = []
    # 1) 实体创建（routed by create_ch；p_001 主角由 init 登记，create 会撞 id——跳过）
    for eid in ch["create_ch"]:
        if eid == "p_001":
            continue
        ent = next(e for e in plan["entities"] if e["id"] == eid)
        table = ent["table"]
        entry: dict = {"id": ent["id"], "name": ent["name"]}
        if ent["alias"]:
            entry["aliases"] = [ent["alias"]]
        if table == "persons":
            entry.update({"type": "person", "status": "active"})
            if ent["id"] == "p_001":
                entry["card"] = "characters/protagonist.md"
        elif table == "items":
            entry.update({"type": "item", "status": "active"})
            src = next(e for e in plan["entities"] if e["id"] == ent["id"])
            if src.get("holder0"):
                entry["holder"] = src["holder0"]
            if src.get("max_charges"):
                entry.update({"charges": max(0, src["max_charges"] - 1), "max_charges": src["max_charges"],
                              "cost_per_use": "每动一次，折灯油一盏"})
        elif table == "factions":
            entry.update({"type": "faction", "status": "active"})
        else:
            entry.update({"type": "place", "status": "active"})
        ops.append({"table": table, "action": "create", "entry": entry})
    # 2) 现场
    cur: dict = {"time": f"第{ch['day']}日·{ch['slot']}", "time_day": ch["day"],
                 "location": ch["place"],
                 "situation": f"第{n}回交割进行中",
                 "pov_ref": "p_001", "place_ref": ch["place"],
                 "present_characters": ch["cast"], "present_refs": [
                     e["id"] for e in plan["entities"] if e["name"] in ch["cast"]]}
    if plan["chapter_meta"][n]["tier_up"]:
        cur["power_level"] = TIER_NAMES[min(len(TIER_NAMES) - 1, 1 + tier_steps_idx(plan, n))]
    if ch["moods"]:
        cur["present_moods"] = ch["moods"]
    ops.append({"table": "current", "action": "update", "set": cur})
    # 3) 人物状态：同案多 op 会被引擎按重名整案拒收——每 id 合并为一条 update
    person_sets: dict[str, dict] = {}

    def _pset(pid: str, patch: dict) -> None:
        person_sets.setdefault(pid, {}).update(patch)

    if ch["tier_up"]:
        k = tier_steps_idx(plan, n)
        _pset("p_001", {"tier_rank": k + 1,
                        "tier_name": TIER_NAMES[min(len(TIER_NAMES) - 1, k + 1)]})
    if ch["injury_at"]:
        _pset("p_001", {"injury_level": 2, "injury_desc": "左臂鞭痕未愈"})
    if ch["injury_clear"]:
        _pset("p_001", {"injury_level": 0, "injury_desc": "结痂"})
    if ch["renown"] and (n - 30) % 50 == 0:
        _pset("p_001", {"renown": ch["renown"]})
    for d in ch["deaths"]:
        ent = next((e for e in plan["entities"] if e["name"] == d), None)
        if ent:
            _pset(ent["id"], {"life_status": "deceased", "status": "retired"})
            # 引擎不变量：死者名下不得留有持有物（verify 直接阻断 sync）——死亡章当场移交主角
            for it in plan["entities"]:
                if it["table"] == "items" and it.get("holder0") == d and it["create_ch"] <= n:
                    ops.append({"table": "items", "action": "update", "id": it["id"],
                                "set": {"holder": "主角", "condition": "物归公册，柜上代管"}})
    if ch.get("tier_fall_warm") and plan["entities_trace"]["tier_fall_id"]:
        _pset(plan["entities_trace"]["tier_fall_id"], {"tier_rank": 4, "tier_name": "凝气四层"})
    if ch["tier_fall"] and plan["entities_trace"]["tier_fall_id"]:
        _pset(plan["entities_trace"]["tier_fall_id"], {"tier_rank": 1, "tier_name": "跌境初期"})
    for pid, patch in person_sets.items():
        ops.append({"table": "persons", "action": "update", "id": pid, "set": patch})
    # 4) 线
    _pre = (plan.get("f03") or {}).get("prereq")
    for lid in ch["plants"]:
        l = plan["lines"][lid]
        if l["kind"] == "foreshadow":
            op = {"table": "lines", "action": "plant", "kind": "foreshadow", "id": lid,
                  "name": l["name"], "target_ch": l["target"], "weight": l["weight"],
                  # F03 前置线 plan 文案去专名：line_terms_for 会把 blob 里的登记名并进
                  # 提词，place 若入 plan，正文所有该场地章都成假回响 → 冷旗永不触发
                  "plan": (f"第{ch['n']}回埋，凭旧库封条兑现" if lid == _pre
                           else f"第{ch['n']}回埋，凭{ch['place']}封条兑现")}
            if l.get("requires"):
                op["requires"] = list(l["requires"])
            ops.append(op)
    for lid in ch["resolves"]:
        l = plan["lines"][lid]
        if l["kind"] == "foreshadow":
            ops.append({"table": "lines", "action": "resolve", "kind": "foreshadow", "id": lid})
        elif l["kind"] == "misunderstanding":
            ops.append({"table": "lines", "action": "resolve", "kind": "misunderstanding", "id": lid})
        else:
            ops.append({"table": "lines", "action": "resolve", "kind": "knowledge", "id": lid})
    for lid in ch.get("reminds", []):
        ops.append({"table": "lines", "action": "remind", "kind": "foreshadow", "id": lid})
    # 只在 plant 章给 mis/kno 挂 plant op（name 字段由 content/secret 承担）
    for lid, l in plan["lines"].items():
        if l["plant_ch"] == n and l["kind"] != "foreshadow":
            if l["kind"] == "misunderstanding":
                ops.append({"table": "lines", "action": "plant", "kind": "misunderstanding", "id": lid,
                            "parties": "、".join(l["parties"]), "content": l["content"], "truth": l["truth"],
                            "level": 2, "target_ch": l["target"]})
            else:
                ops.append({"table": "lines", "action": "plant", "kind": "knowledge", "id": lid,
                            "secret": l["secret"], "target_ch": l["target"], "holders": l["holders"],
                            "weight": 2})
            if lid not in ch["plants"]:
                pass
    # 5) timeline
    for ev in ch["events"]:
        ops.append({"table": "timeline", "action": "append_event", "event": dict(ev)})
    if n in (ch["vol"],):
        pass
    if ch["n"] == plan["vols"][[v["name"] for v in plan["vols"]].index(ch["vol"])]["start"]:
        vidx = [v["name"] for v in plan["vols"]].index(ch["vol"])
        vend = plan["vols"][vidx]["end"]
        ops.append({"table": "timeline", "action": "append_clock",
                    "clock": {"name": f"{ch['vol']}交割限期", "target_ch": max(n + 1, vend - 1),
                              "urgency": "medium", "desc": f"逾期未结则{ch['place']}封箱充公",
                              "status": "Active"}})
        ops.append({"table": "timeline", "action": "append_arc",
                    "arc": {"name": f"{ch['vol']}主弧", "baseline": "旧规压人", "stage": "开局",
                            "inciting_event": f"第{n}回封条验讫", "strategy": "逐笔对账",
                            "ultimate": "新约落印"}})
    # 6) locked
    for lk in ch["locked_ops"]:
        entry = {k: v for k, v in lk.items() if k in ("id", "fact", "kind", "note", "quote", "refs")}
        entry["since_ch"] = ch_token(n)
        ops.append({"table": "locked", "action": "plant", **entry})
    for rt in ch["retire_ops"]:
        ops.append({"table": "locked", "action": "retire", "id": rt["id"], "reason": rt["reason"]})
    # 7) cognition
    for c in ch["cog"]:
        ops.append({"table": "cognition", "action": "plant", "character": c["character"],
                    "kind": c["kind"], "content": c["content"], "quote": c["quote"],
                    "since_ch": ch_token(n), "truth_ref": c["truth_ref"]})
    # 8) ledger（第一章先立池）
    if n == 1:
        for pid, nm, unit, ini in (("stone", "行会现银", "两", 5000), ("ticket", "渡船票", "张", 300),
                                   ("oil", "灯油", "盏", 800)):
            ops.append({"table": "ledger", "action": "declare_pool", "pool": pid,
                        "spec": {"name": nm, "unit": unit, "initial": ini}})
    for tx in ch["txs"]:
        entry = {"chapter": ch_token(n), "pool": tx["pool"], "delta": tx["delta"],
                 "type": tx["type"], "subject": tx["subject"]}
        ops.append({"table": "ledger", "action": "append_transaction", "entry": entry})
    # 9) synopsis
    ops.append({"table": "synopsis", "action": "set", "title": ch["title"],
                "text": f"第{n}回交割：{ch['place']}侧厅过箱封，{'、'.join(ch['cast'][:3])}画押。"})
    return {"schema": "novel-studio.state-mutation/v3", "chapter": ch_token(n),
            "operation_id": f"stress.{plan['scale']}.ch{n:03d}", "ops": ops}


def tier_steps_idx(plan: dict, n: int) -> int:
    steps = plan["entities_trace"]["tier_up_steps"]
    return steps.index(n) if n in steps else 0


def materialize_chapter(book: Path, plan: dict, n: int) -> tuple[Path, Path, Path, Path]:
    """落一章的 final/raw_v1/raw_v2 与 inbox 提案（v3）。返回四路径。"""
    ch = plan["chapter_meta"][n]
    vol = ch["vol"]
    final = book / "manuscript" / vol / "final" / f"{ch_token(n)}.md"
    raw_v1 = book / "manuscript" / vol / "raw" / f"{ch_token(n)}_v1.md"
    raw_v2 = book / "manuscript" / vol / "raw" / f"{ch_token(n)}_v2.md"
    beats = book / "outlines" / vol / "beats" / f"{ch_token(n)}.md"
    prop = book / "state" / "inbox" / f"{ch_token(n)}.json"
    text = _final_text(plan, n)
    engc.atomic_write_text(final, text)
    engc.atomic_write_text(raw_v1, f"# {ch['title']}（v1 毛坯）\n\n"
                                   f"第{n}回{ch['place']}交割初拟：{'、'.join(ch['cast'][:4])}到场，"
                                   f"{'、'.join(ch['mentions'][:2]) or '账目'}先行。\n")
    engc.atomic_write_text(raw_v2, f"# {ch['title']}（v2 重塑）\n\n" + text.split("\n\n", 1)[1])
    engc.atomic_write_text(beats, _beats_text(plan, n))
    write_json(prop, _proposal_ops(plan, n))
    return final, raw_v1, raw_v2, beats


def write_project_tweaks(book: Path, plan: dict) -> None:
    """压力书的项目配置：字数带 / 配额放宽 / audit advisory / 拉丁白名单。"""
    pj = load_json(book / "project.json", default={}) or {}
    pj["words_target"] = plan["band"]
    pj["audit_mode"] = "advisory"          # soak 不逐章仲裁；闸门链其余全真
    pj["lines_cap"] = {"active_foreshadows": max(50, plan["chapters"] * 2),
                       "longline_foreshadows": max(30, plan["chapters"]),
                       "active_knowledge": max(50, plan["chapters"]),
                       "active_misunderstandings": max(50, plan["chapters"])}
    pj["latin_allowlist"] = ["gun", "mis", "kno", "lock", "evt", "cog", "oil", "id"]
    pj["world_anchor_tokens"] = 10000
    write_json(book / "project.json", pj)


def synth_bible(book: Path, plan: dict) -> None:
    """加厚 bible（full-scale 每文件 ~8000 字），驱动 pack 恒给锚点的预算压力。"""
    target = plan.get("bible_chars", 0)
    if not target:
        return
    specs = [
        ("01_world_axioms.md", "世界底色与运转公理", ("公理", "底层规则", "金手指"),
         "行会规矩由三老共议，一笔一画皆有存照"),
        ("02_power_system.md", "战力与境界标尺", ("战力", "境界", "标尺"),
         "凝气一层可提三十斤石锁，筑基可断马鞭"),
        ("03_factions_geography.md", "势力与地理拓扑", ("势力", "地理", "口岸"),
         "十二渡口分属四行，换防须提前三日知会"),
        ("04_economy_items.md", "经济与品阶体系", ("经济", "品阶", "物价"),
         "灯油一市钱二两，封条火漆每道五十文"),
        ("05_special_mechanics.md", "特殊机制与代偿", ("机制", "代偿", "血脉"),
         "违契者一夜之间失声三日，账房称之为哑偿"),
        ("06_style_guidelines.md", "通俗文风宪法", ("文风", "扫读"), "大白话，短句，动作先行"),
        ("07_deviations.md", "本书偏离清单", ("偏离", "红线"), "不写金手指无代价变强"),
    ]
    heavy = {"01_world_axioms.md", "02_power_system.md", "03_factions_geography.md",
             "04_economy_items.md", "05_special_mechanics.md"}
    rng = random.Random(plan["seed"] + 555)
    for fname, title, heads, anchor_line in specs:
        lines = [f"# {title}", "", anchor_line, ""]
        if fname in heavy:
            need = max(0, target - sum(len(x) for x in lines))
            sec = 0
            while sum(len(x) for x in lines) < need:
                sec += 1
                head = heads[sec % len(heads)]
                lines.append(f"## {title}·{head}第{sec}节")
                lines.append("")
                for k in range(6):
                    lines.append(
                        f"{head}细则{sec}-{k + 1}：{rng.choice(FACT_WORDS)}之例，"
                        f"行会按{rng.randint(1, 9)}成折算，逾期加罚{rng.randint(1, 5)}成，"
                        f"存照归档于{rng.choice(PLACE_A)}口{rng.choice(PLACE_B)}side仓。".replace("side", ""))
                    lines.append("")
        (book / "bible" / fname).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_book(book: Path, plan: dict, sync_through: int | None = None,
               quiet: bool = True) -> dict:
    """init → 槽位/大纲/bible → 配置 → 里程碑 → 逐章 pipeline 到 sync_through。

    返回 {"book":…, "synced": n}。sync 走真闸门链（schema/幂等/verify/封存）。
    """
    from .common import engine_cli
    book = Path(book)
    rc, out = engine_cli(["init", "-w", str(book), "-t", f"压力书-{plan['scale']}",
                          "-g", "悬疑", "-p", plan["protagonist"]])
    if rc != 0:
        raise RuntimeError(f"init 失败 rc={rc}:\n{out[-800:]}")
    # 模板槽位实例化（与 test_smoke 同法）
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from test_smoke import fill_beats_slots  # noqa: E402
    for pat in ("bible/*.md", "characters/*.md", "outlines/*.md", "outlines/*/outline.md"):
        for f in book.glob(pat):
            f.write_text(fill_beats_slots(f.read_text(encoding="utf-8")), encoding="utf-8")
    # 分卷大纲（卷路由 + plan_start 证据）
    for v in plan["vols"]:
        d = book / "outlines" / v["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "outline.md").write_text(
            f"# {v['name']} 分卷大纲\n\n本卷覆盖 ch_{v['start']:03d}—ch_{v['end']:03d}。\n\n"
            f"## 四分位阶段\n- 开局：立约与验封\n- 加压：债主上门\n- 转折：名单倒查\n- 兑现：交割落印\n",
            encoding="utf-8")
        (d / "beats").mkdir(parents=True, exist_ok=True)
    (book / "outlines" / "main_plot.md").write_text(
        "# 全书主线\n\n压力书脊柱：十二渡口交割账，一笔一笔对到底。\n", encoding="utf-8")
    write_project_tweaks(book, plan)
    synth_bible(book, plan)
    # 里程碑（pack P0 卷段引用源）
    for i, v in enumerate(plan["vols"], 1):
        engine_cli(["milestone", "add", "-w", str(book), "--id", f"MS-{i:03d}",
                    "-t", f"结清{v['name']}交割案", "-c", str(v["end"])])
    upto = plan["chapters"] if sync_through is None else min(sync_through, plan["chapters"])
    for n in range(1, upto + 1):
        r = sync_chapter(book, plan, n)
        if not r["ok"]:
            raise RuntimeError(f"ch{n:03d} sync 失败：{r['stderr_tail'] or r['out_tail']}")
    return {"book": book, "synced": upto}


def sync_chapter(book: Path, plan: dict, n: int) -> dict:
    """一章的完整流水线：卷末核销 → 落盘 → 提案 → sync（真闸门链）。

    卷末章 sync 前核销里程碑（走 CLI 正道；改动会被本章 sync 的封存盖章覆盖，
    不留 state_offline_edit 尾巴——重复 sync 不会重新盖章，实测 2026-09）。
    """
    from .common import timed_engine_cli
    for i, v in enumerate(plan["vols"], 1):
        if n == v["end"]:
            timed_engine_cli(["milestone", "achieve", f"MS-{i:03d}", "-c", str(n), "-w", str(book)])
            break
    materialize_chapter(book, plan, n)
    rc, out, dt = timed_engine_cli(["sync", ch_token(n), "-w", str(book), "--json"])
    return {"ok": rc == 0, "rc": rc, "sec": round(dt, 3),
            "out_tail": out[-400:], "stderr_tail": "" if rc == 0 else out[-900:]}


def manifest_finalize_actual(book: Path, plan: dict) -> dict:
    """从落盘 state 反向投影 actual（与 plan 同形，供 diff）。"""
    from engine import state as st
    actual: dict = {"schema": "novel-studio.stress-manifest/v1", "stage": "actual",
                    "scale": plan["scale"], "seed": plan["seed"], "chapters": plan["chapters"]}
    lines_st = st.load_state(book, "lines")
    got_lines: dict[str, dict] = {}
    for arr, kind in (("foreshadows", "foreshadow"), ("misunderstandings", "misunderstanding"),
                      ("knowledge", "knowledge")):
        for g in lines_st.get(arr, []) or []:
            got_lines[str(g.get("id"))] = {"kind": kind, "id": g.get("id"),
                                           "plant_ch": g.get("plant_ch"),
                                           "target": g.get("target_ch"),
                                           "weight": g.get("weight", 1),
                                           "status": g.get("status")}
    actual["lines"] = got_lines
    led = st.load_state(book, "ledger")
    actual["pools"] = {k: {"initial": v.get("initial"), "current": v.get("current")}
                       for k, v in (led.get("pools") or {}).items()}
    tx_chain: dict[str, list] = {}
    for t in led.get("transactions", []) or []:
        tx_chain.setdefault(str(t.get("pool")), []).append(
            {"ch": int(re.sub(r"\D", "", str(t.get("chapter")))), "ba": t.get("balance_after")})
    actual["ledger_tx_chain"] = tx_chain
    cur = st.load_state(book, "current")
    actual["current"] = {"time": cur.get("time"), "time_day": cur.get("time_day"),
                         "location": cur.get("location"),
                         "moods": {k: {"label": v.get("label"), "level": v.get("level")}
                                   for k, v in (cur.get("present_moods") or {}).items()}}
    ents = st.load_state(book, "entities")
    ent_rows = {str(e.get("id")): {"id": e.get("id"), "name": e.get("name"),
                                   "tier_rank": e.get("tier_rank"), "tier_name": e.get("tier_name"),
                                   "injury_level": e.get("injury_level"), "renown": e.get("renown"),
                                   "life_status": e.get("life_status"), "charges": e.get("charges")}
                for e in ents.get("entries", [])}
    actual["entities"] = [ent_rows[k] for k in sorted(ent_rows)]
    lk = st.load_state(book, "locked")
    actual["locked"] = sorted(str(e.get("id")) for e in lk.get("entries", []))
    syn = st.load_state(book, "synopsis")
    actual["synopsis_chapters"] = sorted(syn.get("chapters", {}).keys())
    tl = st.load_state(book, "timeline")
    actual["timeline_events"] = len(tl.get("events", []) or [])
    # changelog 里线状态首次 →Resolved 的章（actual_recall_ch）
    recall_at: dict[str, int] = {}
    from engine import changelog
    try:
        for ev in changelog.load_events(book):
            if ev.get("table") != "lines":
                continue
            path = str(ev.get("path", ""))
            if path.endswith(".status") and ev.get("op") in (None, "set", "replace") \
                    and str(ev.get("new")) in ("Resolved", "Revealed"):
                m = re.search(r"(GUN|MIS|KNO)-\d{3,}", str(ev.get("old")) + path + str(ev.get("note", "")))
                chn = engc.chapter_token_to_num(str(ev.get("ch", "")))
                if m and chn:
                    recall_at.setdefault(m.group(0), chn)
    except (ValueError, OSError):
        pass
    actual["recall_at"] = recall_at
    return actual


def manifest_diff(plan: dict, actual: dict) -> list[str]:
    """plan 与 actual 的确定性对照；返回漂移列表（空 = harness 与引擎同轨）。"""
    problems: list[str] = []
    for lid, l in plan["lines"].items():
        a = actual["lines"].get(lid)
        if a is None:
            problems.append(f"线 {lid} 未入账")
            continue
        if a.get("plant_ch") is not None and a.get("plant_ch") != l["plant_ch"]:
            problems.append(f"{lid} plant_ch 漂移：plan {l['plant_ch']} vs 账上 {a.get('plant_ch')}")
        # misunderstanding 在引擎模型无 plant_ch 字段（extra-forbid）：无账面证据可比
        if a.get("target") != l.get("target"):
            problems.append(f"{lid} target 漂移：plan {l.get('target')} vs 账上 {a.get('target')}")
        if l.get("recall_ch"):
            ok_status = a.get("status") in ("Resolved", "Revealed")
            if not ok_status:
                problems.append(f"{lid} 应已于 ch_{l['recall_ch']:03d} 回收，账上状态 {a.get('status')}")
    # 时间轴单调（actual 侧）
    days = [c["time_day"] for c in plan["clock_trace"]]
    if any(b < a for a, b in zip(days, days[1:])):
        problems.append("clock_trace 非单调（plan 侧就错了）")
    if actual["current"].get("time_day") != days[-1]:
        problems.append(f"末章 time_day 漂移：plan {days[-1]} vs 账上 {actual['current'].get('time_day')}")
    # 账本链 vs plan 重放
    for pid, expect in plan["ledger_replay"].items():
        chain = actual["ledger_tx_chain"].get(pid, [])
        # 每池逐章合并（一章多笔时按最后余额比）
        exp_by_ch: dict[int, int] = {}
        for row in expect:
            exp_by_ch[row["ch"]] = row["balance"]
        got_by_ch: dict[int, int] = {}
        for row in chain:
            got_by_ch[row["ch"]] = row["ba"]
        for cnum, bal in exp_by_ch.items():
            if got_by_ch.get(cnum) is not None and got_by_ch[cnum] != bal:
                problems.append(f"ledger {pid} ch{cnum:03d} 余额漂移：plan {bal} vs 账上 {got_by_ch[cnum]}")
        fin = actual["pools"].get(pid, {}).get("current")
        if fin != days and fin is None:
            pass
        if fin is not None and expect and fin != expect[-1]["balance"]:
            problems.append(f"ledger {pid} 期末余额：plan {expect[-1]['balance']} vs 账上 {fin}")
    # locked 活跃集合 = plants - retires
    expect_locks = set()
    for n, ch in plan["chapter_meta"].items():
        for lk in ch["locked_ops"]:
            expect_locks.add(lk["id"])
        for rt in ch["retire_ops"]:
            expect_locks.discard(rt["id"])
    got_locks = set(actual["locked"])
    if got_locks != expect_locks:
        problems.append(f"locked 活跃集漂移：差 {sorted(expect_locks ^ got_locks)[:6]}")
    # synopsis 完整
    if len(actual["synopsis_chapters"]) != plan["chapters"]:
        problems.append(f"synopsis 缺章：{plan['chapters'] - len(actual['synopsis_chapters'])} 章未登记")
    return problems


def canon_manifest(plan: dict) -> str:
    from .common import canon_hash
    slim = {k: plan[k] for k in ("scale", "seed", "chapters", "vols", "entities", "lines",
                                 "ledger_replay", "clock_trace", "faults", "overdraft",
                                 "freeze_start", "f16_ids", "band")}
    slim["chapter_meta"] = {str(n): {k: v for k, v in ch.items() if k != "title"}
                            for n, ch in plan["chapter_meta"].items()}
    return canon_hash(slim)
