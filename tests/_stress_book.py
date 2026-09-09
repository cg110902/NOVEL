"""程序化生成 200 章压力样书（PLAN_CONSISTENCY_50W.md §8 终局验收 / R4 验收门）。

- 200 章 × ~800 字正文，分 4 卷（vol_01..vol_04 各 50 章），全程走真实流水线
  （提案 → apply_inbox → verify → 盖章 → 快照 → seal），非伪造 state；
- 20 条线：13 常规（按 target 兑现或保持活跃）+ 5 故意冷却（早前提及后断联）+
  2 故意零落笔（正文从未出现）；
- 植入五类已知吃书（见 IMPLANTS 注释），终局断言「全部命中且无误报」；
- 构建一次，模块级缓存共享（同一测试会话内多测试复用同一本书）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import changelog, rollup, snapshot, state  # noqa: E402
from engine.commands.state_sync import (  # noqa: E402
    _append_bible_journal, _stamp_final_hash, _stamp_state_hashes)

PY = sys.executable

CAST = [  # (id, name, type, extra)
    ("p_lm", "林牧", "person", {"tier_rank": 3, "tier_name": "聚气境"}),
    ("p_zm", "赵莽", "person", {"tier_rank": 3, "tier_name": "聚气境"}),
    ("p_sw", "苏婉", "person", {"tier_rank": 2, "tier_name": "引气境"}),
    ("p_xyz", "玄阳子", "person", {"tier_rank": 8, "tier_name": "化神境"}),
    ("it_ds", "断水剑", "item", {"holder": "林牧"}),
    ("f_qy", "青云宗", "faction", {}),
    ("f_hm", "黑水盟", "faction", {}),
    ("lo_lm", "临江城", "location", {}),
]

# 20 条线：GUN-001..013 常规；GUN-014..018 冷却；GUN-019/020 零落笔
# (id, name, plant_ch, target, resolve_ch, touch_from, touch_until, touch_gap)
LINES = [
    ("GUN-001", "断水剑的来历", 1, 45, 45, 1, 44, 6),
    ("GUN-002", "青云宗的密卷", 2, 90, 90, 2, 89, 6),
    ("GUN-003", "黑水盟的阴谋", 3, 135, 135, 3, 134, 6),
    ("GUN-004", "苏婉的身世", 4, 180, 180, 4, 179, 6),
    ("GUN-005", "玄阳子的旧伤", 5, 195, 195, 5, 194, 6),
    ("GUN-006", "城主府的地契", 6, 260, None, 6, 200, 6),
    ("GUN-007", "山中的古阵", 7, 280, None, 7, 200, 6),
    ("GUN-008", "北地的商路", 8, 300, None, 8, 200, 6),
    ("GUN-009", "师兄的嘱托", 9, 320, None, 9, 200, 6),
    ("GUN-010", "断剑的重铸", 10, 340, None, 10, 200, 6),
    ("GUN-011", "宗门大比", 10, 60, 60, 10, 59, 6),
    ("GUN-012", "临江城的水患", 10, 240, None, 10, 200, 6),
    ("GUN-013", "灵田的租约", 10, 260, None, 10, 200, 6),
    ("GUN-014", "古矿的封条", 2, 300, None, 5, 7, 1),   # 冷却：早前密集提及后断联
    ("GUN-015", "旧盟书的下落", 3, 300, None, 6, 8, 1),  # 冷却：ch_130 细纲计划回收（植入②）
    ("GUN-016", "药圃的怪病", 4, 300, None, 7, 9, 1),   # 冷却
    ("GUN-017", "沉船的货物", 4, 300, None, 8, 9, 1),   # 冷却
    ("GUN-018", "石桥的裂痕", 5, 300, None, 9, 9, 1),   # 冷却
    ("GUN-019", "北荒古灯", 3, 400, None, None, None, 0),  # 零落笔（植入③）
    ("GUN-020", "无名骨笛", 3, 400, None, None, None, 0),  # 零落笔（植入③）
]

# IMPLANTS：五类已知吃书（§8.2）——全部必须被命中，其余章节零新增 error
# ① ch_120 无事件跳阶（tier 3→7，无 timeline 事件）→ tier_shift_without_event
# ② ch_130 细纲计划回收冷却线 GUN-015（上次提及 ch_008、仍开放）→ line_recall_cold
# ③ GUN-019/020 全书正文零出现 → line_never_surfaced
# ④a ch_100 封存后离线手改 entities.json → 下一章 load 补记 external_edit 事件
# ④b ch_200 全部封存后再次手改 → check 的 state_offline_edit 指名报出
# ⑤ ch_150 断水剑 holder 林牧→赵莽 → changelog blame 精确到章与 operation_id

_AUDIT = "---\nhard: 0\nadjudicated: false\n---\n\n# 仲裁\n\n机械对照无硬矛盾。\n"


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _proposal(ch: str, n: int, *, entities=None, lines=None) -> dict:
    prop = {
        "schema": "novel-studio.state-mutation/v2", "chapter": ch,
        "operation_id": f"{ch}.reader.r",
        "synopsis": {"text": f"第{n}章：林牧一行在临江城推进各自的事项。"},
        "entities": entities or [],
        "lines": lines or [],
    }
    return prop


def _sync(book: Path, ch: str) -> None:
    overall = state.apply_inbox(book, expect_chapter=ch, dry_run=False)
    if overall.get("failed"):
        raise RuntimeError(f"{ch} apply_inbox 失败: {overall}")
    errs = state.verify_state(book)
    if errs:
        raise RuntimeError(f"{ch} verify_state 失败: {errs[:3]}")
    _stamp_final_hash(book, ch)
    _stamp_state_hashes(book, ch)
    ok, msg = snapshot.create_snapshot(book, f"{ch}_done")
    if not ok:
        raise RuntimeError(f"{ch} 快照失败: {msg}")
    _append_bible_journal(book, ch)
    changelog.seal_chapter(book, ch)


def _fill_bible(book: Path) -> None:
    """世界圣经填到真实体量（p0 world_anchors 的规模决定 ±20% 验收口径）。"""
    body = ("九洲大地灵气自西向东递减，宗门林立，散修如萍。修行者纳灵入体，"
            "以心境定上限、以资源定速度；灵石为通货，丹药分九品，法器依炼材分凡、玄、地、天四阶。"
            "修士之间立契需以神识烙印，违契者遭反噬；宗门大比每十年一届，夺魁者得入秘境修行三载。"
            "凡人王朝依附宗门而存，税赋以灵石折算；妖族盘踞北荒，与人间以古约相隔，"
            "古约之力渐衰，边境摩擦逐年增多。海外有仙山传说，千年无人得见。")
    detail = ("修行九境，每境三重：引气、聚气、筑基、金丹、元婴、化神、炼虚、合体、大乘；"
              "越境挑战须借地利与法器之便，同境之争则看功法品阶与临机应变。"
              "宗门势力以山门为界：青云宗居中州，掌东陆灵脉三成；黑水盟行商走私，暗桩遍布沿江九埠；"
              "北地剑阁守古约北门，轻易不下山。散修依坊市而聚，坊市由商会与宗门共治，"
              "灵石、丹药、符箓、炼材四市各有行价，季末结算。"
              "法器认主需滴血开锋，认主后随主修为共长；断剑重铸须寻上古炉火，"
              "炉火三处：火山腹地、深海热泉、雷暴之巅。契约类术法一诺千金，"
              "违誓者道基受损，重则修为倒卷。秘境名额按大比名次分配，"
              "前三甲各携两名亲传入内，境内一年外界十日。") * 2
    for i, (name, title) in enumerate([
            ("01_world_axioms.md", "世界与规则"),
            ("02_power_system.md", "境界与战力标尺"),
            ("03_factions_geography.md", "势力与地理"),
            ("04_economy_items.md", "经济通货与灵材"),
            ("05_special_mechanics.md", "特异机制")], start=1):
        _write(book / "bible" / name, f"# {title}\n\n{body}\n\n{detail}\n")


def _chapter_text(n: int, due_lines: list[str]) -> str:
    """~800 字正文：提及在场角色 + 到期线名；不含任何数字金额/未登记专名。"""
    present = [CAST[i % 4][1] for i in range(4)]  # 林牧/赵莽/苏婉/玄阳子
    paras = [f"第{n}章 风起临江", ""]
    frames = [
        "{a}立在城头，望着江面上未散的晨雾，心中默数着这些日子的得失。",
        "{b}从街角走来，肩上还沾着练功房的尘土，远远便招呼众人集合。",
        "{c}翻开随身的册子，把近日打探到的消息一条条念给众人听。",
        "{a}与{b}对练了一场，剑意与拳风在院中交错，惊起檐下宿鸟。",
        "{c}为众人把脉，皱眉说连日赶路，气血亏空，须得静养数日。",
        "入夜，{a}独自登楼远眺，江风扑面，往事与眼前事在心头翻涌。",
    ]
    for i, f in enumerate(frames):
        paras.append(f.format(a=present[0], b=present[1], c=present[2]))
    for name in due_lines:
        paras.append(f"席间有人重提{name}，众人议了几句，都觉此事未完，须再寻头绪。")
    while sum(len(p) for p in paras) < 800:
        paras.append("次日清晨，江雾又起，林牧照旧第一个起身练剑，城中一切如旧。")
    return "\n\n".join(paras)


def run_cli(book: Path, *args: str) -> subprocess.CompletedProcess:
    """CLI 子进程（工作区根重定向到样书所在临时目录）。"""
    import os
    env = {**os.environ, "NOVEL_STUDIO_WORKSPACE_ROOT": str(book.parent),
           "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([PY, str(ROOT / "studio.py"), *args, "-w", str(book)],
                          capture_output=True, text=True, timeout=300, env=env)


def build_stress_book(book: Path) -> dict:
    """构建压力样书，返回植入清单与计时。"""
    t0 = time.time()
    rc = run_cli(book, "init", "-t", "压力样书", "-g", "东方玄幻", "-p", "林牧")
    if rc.returncode != 0:
        raise RuntimeError(f"init 失败: {rc.stdout[-400:]} {rc.stderr[-400:]}")
    _fill_bible(book)
    proj = json.loads((book / "project.json").read_text(encoding="utf-8"))
    proj["words_target"] = [400, 1400]
    (book / "project.json").write_text(json.dumps(proj, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    _write(book / "characters" / "protagonist.md",
           "# 林牧\n\n青云宗外门弟子，持断水剑，性坚忍，重然诺。\n")
    _write(book / "outlines" / "main_plot.md",
           "# 主线梗概\n\n- **核心主角**：林牧\n- **规划体量**：4 卷 ｜ 预估总字数：16 万字\n\n"
           "林牧自临江城起步，历经宗门大比、黑水盟之乱，逐步揭开断水剑与青云宗密卷的旧事，"
           "终成一代宗师。\n")
    _write(book / "outlines" / "vol_01" / "outline.md",
           "# 第一卷 卷纲\n\n林牧入青云宗，结怨黑水盟，宗门大比夺魁。\n")

    plant_ch: dict[str, int] = {}
    last_touch: dict[str, int] = {}
    for lid, name, p_ch, _t, _r, tf, tu, _g in LINES:
        plant_ch[lid] = p_ch
        last_touch[lid] = tf if tf else 0

    for n in range(1, 201):
        ch = f"ch_{n:03d}"
        vol = f"vol_{(n - 1) // 50 + 1:02d}"
        # 细纲/草稿/定稿/仲裁（Stage 5 输入合同）
        form = ["推进", "对峙", "揭秘", "爆发", "休整"][(n - 1) % 5]
        action_sec = ""
        if n == 130:  # 植入②触发器：细纲线动作栏计划回收冷却线 GUN-015
            action_sec = "\n## 线动作\n\n- resolve GUN-015\n"
        _write(book / "outlines" / vol / "beats" / f"{ch}.md",
               f"---\nchapter: {ch}\nvol: {vol}\nform: {form}\n---\n\n"
               f"## 目标\n\n- 林牧推进当章事项，场面落地\n{action_sec}")
        _write(book / "manuscript" / vol / "raw" / f"{ch}_v1.md",
               f"# 第{n}章 初稿\n\n占位初稿，情节与定稿一致。\n")
        due = [name for (lid, name, _p, _tg, _rs, tf, tu, tg) in LINES
               if tf and tf <= n <= tu and last_touch[lid]
               and (n == tf or n - last_touch[lid] >= tg)]
        _write(book / "manuscript" / vol / "final" / f"{ch}.md", _chapter_text(n, due))
        for name in due:
            for (lid, nm, *_r) in LINES:
                if nm == name:
                    last_touch[lid] = n
        _write(book / "log" / "audit" / f"{ch}.md", _AUDIT)

        # 提案：每章至少一条实体变更（苏婉 summary 滚动）+ 到期线操作
        entities = [{"action": "upsert", "id": "p_sw", "name": "苏婉",
                     "type": "person", "summary": f"第{n}章在场，记录当章动向。"}]
        lines_ops = []
        for lid, name, p_ch2, target, resolve_ch, _tf, _tu, _g in LINES:
            if p_ch2 == n:
                lines_ops.append({"kind": "foreshadow", "action": "plant", "id": lid,
                                  "name": name, "target_ch": target, "weight": 2,
                                  "plan": "按计划推进"})
            elif resolve_ch == n:
                lines_ops.append({"kind": "foreshadow", "action": "resolve", "id": lid})
        if n == 1:  # 全员建档（首见基线）
            entities = [{"action": "upsert", "id": i, "name": nm, "type": tp,
                         "summary": f"建档于第1章。", **extra}
                        for i, nm, tp, extra in CAST]
        if n == 120:  # 植入①：无事件跳阶
            entities.append({"action": "upsert", "id": "p_lm", "name": "林牧",
                             "type": "person", "tier_rank": 7, "tier_name": "金丹境",
                             "summary": "第120章强行突破。"})
        if n == 150:  # 植入⑤：中途改 holder
            entities.append({"action": "upsert", "id": "it_ds", "name": "断水剑",
                             "type": "item", "holder": "赵莽", "summary": "第150章易主。"})
        _write(book / "state" / "inbox" / f"{ch}.json",
               json.dumps(_proposal(ch, n, entities=entities, lines=lines_ops),
                          ensure_ascii=False, indent=1))
        _sync(book, ch)

        # 植入④a：ch_100 封存后离线手改（绕过 save_state）
        if n == 100:
            ents = json.loads((book / "state" / "entities.json").read_text(encoding="utf-8"))
            for e in ents["entries"]:
                if e.get("id") == "p_lm":
                    e["summary"] = "离线手改的假履历（植入④a）"
            (book / "state" / "entities.json").write_text(
                json.dumps(ents, ensure_ascii=False, indent=2), encoding="utf-8")
        # 卷末 rollup（真实工序：卷末封存后立即生成前情态势）
        if n % 50 == 0 and n < 200:
            rollup.save_rollup(book, f"vol_{n // 50:02d}")

    # 植入④b：全部封存后再次手改 → check 的 state_offline_edit 必须指名报出
    ents = json.loads((book / "state" / "entities.json").read_text(encoding="utf-8"))
    for e in ents["entries"]:
        if e.get("id") == "p_lm":
            e["summary"] = "卷末离线手改（植入④b）"
    (book / "state" / "entities.json").write_text(
        json.dumps(ents, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"book": book, "build_seconds": round(time.time() - t0, 2),
            "chapters": 200, "lines": len(LINES)}


_CACHE: dict[str, object] = {}


def stress_book() -> tuple[Path, dict]:
    """会话级单例：构建一次，多个测试共享。"""
    if "book" not in _CACHE:
        _CACHE["book"] = Path(tempfile.mkdtemp(prefix="novel_stress_"))
        _CACHE["manifest"] = build_stress_book(_CACHE["book"])
    return _CACHE["book"], _CACHE["manifest"]
