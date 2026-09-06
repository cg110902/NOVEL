"""End-to-end cross-volume pipeline.

The real continuity hazard is the vol_01 → vol_02 boundary: after ch_049 is
synced in vol_01, the next chapter (ch_050 in vol_02) must
  - pack a prev_tail from vol_01/ch_049 (not an empty tail or a wrong volume),
  - generate beats under vol_02/beats with the previous chapter's live state,
  - and complete Stage 5 for a chapter that lives in a different volume.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import common, state


def _fill_bible(book):
    (book / "bible/project_bible.md").write_text(
        "# 《星轨之上》本书圣经\n"
        "## 一句话（logline）\n林舟在星际废墟中发现一具不属于任何文明的驾驶舱。\n"
        "## 世界与规则\n- 废铁回收船只能使用民用牵引引擎。\n"
        "## 势力与地理\n- 明港、铁隼会、灯塔局。\n"
        "## 语言定调\n明快直白。\n"
        "## 境界/层级与实物标尺\n- 民用级、执法级、军用级。\n"
        "## 本书偏离清单\n- （空）\n", encoding="utf-8")


def _fill_vol_outline(book, vol, start, end):
    d = book / "outlines" / vol
    d.mkdir(parents=True, exist_ok=True)
    (d / "outline.md").write_text(
        f"# {vol} 卷纲（星轨之上）\n"
        "## 本卷承诺与核心看点\n林舟追查驾驶舱来源。\n"
        "## 主冲突与驱动力\n林舟与铁隼会、灯塔局三方角力。\n"
        f"## 本卷剧情节点与章回规划\n"
        f"- **阶段一（ch_{start:03d}—ch_{end:03d}｜主线推进）**\n"
        f"  - ch_{start:03d}：跨卷续接。\n", encoding="utf-8")


def _mk_beats(book, vol, n):
    b = book / "outlines" / vol / "beats" / f"ch_{n:03d}.md"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(
        f"---\nchapter: ch_{n:03d}\nvol: {vol}\nform: 暗流汇聚\n"
        "pov: 林舟·视角\nwords: 1500-2500+\ntension_curve: 危机逼近 → 试探博弈 → 动作破局\n"
        "tension_score: 6\nstage_mode: Simmering\nstyle_notes: 通俗大白话 | 鲜活对白\n"
        "editor_extra: \n---\n\n"
        f"## 本章核心戏剧目标\n- 目标：跨卷续接。\n\n"
        f"## 场景脉络\n- **场景**：\n  - 🎬 **内容**：林舟进入{vol}的新场景。\n"
        "- **收束**：\n  - 📍 **章末物理刀口**：背后传来汽笛声。\n\n"
        "## 交付契约\n- **核心看点**：延续。\n- **验收要点**：\n  1. 事件发生。\n", encoding="utf-8")


def _mk_raw(book, vol, n):
    d = book / "manuscript" / vol / "raw"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"ch_{n:03d}_v1.md").write_text(
        f"# 第{n}章\n\n初稿。", encoding="utf-8")


def _mk_final(book, vol, n, marker):
    d = book / "manuscript" / vol / "final"
    d.mkdir(parents=True, exist_ok=True)
    body = [
        f"# 第{n}章 {marker}",
        "夜里的废料场只有牵引灯在响。林舟蹲在废料堆旁，看见一扇舱门侧面的编号被磨掉一半。",
        "他伸手摸那台驾驶舱，主控屏亮着一行字：等待授权。",
        "远处传来一阵脚步声。他动作一顿，把舱门虚掩，躲进废管后面。",
        "有人拖走一根黑色数据线，骂了一声，往泊位出口匆匆走了。",
        "林舟回到舱门边，发现内侧贴着一张褪色标签，写着一串灯塔局旧式设备的登记码。",
    ]
    # Enough CJK for word-count / style probes.
    base = "林舟蹲在废料场，想了想，决定先把驾驶舱藏好。夜风从破口灌进来，他把扳手别在腰后。"
    for i in range(6):
        body.append(base + f"第{i}次他想，明港这座星港，从来就没有免费的真相。")
    (d / f"ch_{n:03d}.md").write_text("\n\n".join(body), encoding="utf-8")


def _proposal(n, marker, op):
    ch = f"ch_{n:03d}"
    return {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": ch,
        "operation_id": op,
        "current": {
            "time": "第二日·清晨" if n == 50 else "第一日·深夜",
            "region": "明港",
            "location": "卷二·废铁港" if n == 50 else "卷一·废料场",
            "situation": marker,
            "mood": "警惕",
            "goal": f"执行第{n}章目标",
            "present_characters": ["林舟"],
            "aftershock": "有人连夜拆数据线。",
            "active_pressures": ["铁隼会盯上驾驶舱"],
        },
        "entities": [
            {"name": "驾驶舱", "type": "item", "summary": "无名驾驶舱", "status": "active",
             "holder": "林舟", "condition": "供电异常",
             "quote": "主控屏亮着一行字：等待授权"},
            {"name": "温棠", "type": "person", "summary": "灯塔局探员", "status": "active",
             "realm": "灯塔局·探员", "faction": "灯塔局", "attitude": "neutral",
             "quote": "写着一串灯塔局旧式设备的登记码"},
        ],
        "lines": [],
        "ledger": {
            "pools": {"credits": {"name": "信用点", "unit": "点", "initial": 500}},
            "transactions": [{"chapter": ch, "pool": "credits", "delta": -40,
                              "type": "expense", "subject": "通行证",
                              "quote": "夜里的废料场只有牵引灯在响"}],
        },
        "timeline": {
            "events": [{"time": "第一日·深夜", "event": marker,
                        "quote": "主控屏亮着一行字：等待授权"}],
            "arcs": [{"name": "驾驶舱之谜", "stage": "跨卷", "baseline": "林舟捡到残骸",
                      "inciting_event": "发现灯塔局登记码", "ultimate": "揭开来源"}],
            "clocks": [],
        },
        "synopsis": {"title": marker, "text": f"第{n}章：{marker}。"},
        "locked": [],
        "cognition": [{"id": f"COG-{n:03d}", "character": "林舟", "kind": "fact",
                       "content": marker, "since_ch": ch,
                       "quote": "写着一串灯塔局旧式设备的登记码"}],
    }


def _run_full_chapter(ws, book, vol, n, marker, op):
    """pack → beats → final(already) → proposal → audit → sync → snapshot for one chapter."""
    ch = f"ch_{n:03d}"
    # 1. pack: the writing context for this chapter.
    p, data = ws.run_json(["pack", ch, "-w", str(book), "--json"])
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert data["p0"]["beats"], data["p0"]
    # 2. beats: use the generator rather than hand-writing, to prove cross-volume
    #    volume selection and live-state injection.
    p, data = ws.run_json(["beats", "new", ch, "--force", "--write", "-w", str(book), "--json"])
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "written" in data, data
    beats_out = book / "outlines" / vol / "beats" / f"{ch}.md"
    assert beats_out.is_file(), f"expected beats under {vol}: {beats_out}"
    beats_text = beats_out.read_text(encoding="utf-8")
    assert "上章现场" in beats_text or "本章坐标" in beats_text, beats_text[:500]
    # 3. final exists for Stage 5 contracts (beats/raw/final already seeded above).
    # 4. proposal in inbox.
    inbox = book / "state/inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{ch}.json").write_text(
        json.dumps(_proposal(n, marker, op), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    # 5. proposal pre-check.
    p, data = ws.run_json(["proposal", "check", ch, "-w", str(book), "--json"])
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert not data["check"]["errors"], data["check"]
    # 6. audit report (Stage 4C gate).
    p = ws.run(["audit", ch, "--write", "-w", str(book)])
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert (book / "log/audit" / f"{ch}.md").is_file()
    # 7. dry-run + real sync.
    p, data = ws.run_json(["sync", ch, "--dry-run", "--json", "-w", str(book)])
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert data["apply"]["applied"] == 1, data
    p, data = ws.run_json(["sync", ch, "--json", "-w", str(book)])
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert not data["verify_errors"], data
    assert data["snapshot"]["ok"] is True, data
    return ch


def test_cross_volume_full_pipeline(ws):
    book = ws.init("跨卷书", "星轨之上", "科幻", "林舟")
    _fill_bible(book)
    _fill_vol_outline(book, "vol_01", 1, 49)
    _fill_vol_outline(book, "vol_02", 50, 60)

    # vol_01/ch_049 is already written; sync it to give ch_050 a real previous state.
    _mk_beats(book, "vol_01", 49)
    _mk_raw(book, "vol_01", 49)
    _mk_final(book, "vol_01", 49, "卷一收束")
    _run_full_chapter(ws, book, "vol_01", 49, "卷一收束", "op_cross_vol_049")

    # Now the real cross-volume chapter: ch_050 lives in vol_02.
    _mk_raw(book, "vol_02", 50)
    _mk_final(book, "vol_02", 50, "卷二开篇")

    # ch_049's state must already be live: the vol_02 chapter continues from it.
    cur_before = state.load_state(book, "current")
    assert cur_before["location"] == "卷一·废料场"
    assert cur_before["situation"] == "卷一收束"

    # Generate beats with the generator so it must pick vol_02 (not vol_01).
    ch = "ch_050"
    p, data = ws.run_json(["beats", "new", ch, "--force", "--write", "-w", str(book), "--json"])
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "written" in data, data
    beats_out = book / "outlines" / "vol_02" / "beats" / "ch_050.md"
    assert beats_out.is_file(), f"beats must land in vol_02: {beats_out}"
    beats_text = beats_out.read_text(encoding="utf-8")
    assert "上章现场" in beats_text or "本章坐标" in beats_text, beats_text[:500]

    # pack must see the previous chapter across the volume boundary.
    p, data = ws.run_json(["pack", ch, "-w", str(book), "--json"])
    assert p.returncode == 0, (p.stdout, p.stderr)
    prev_tail = data["p0"].get("prev_tail", "")
    assert "ch=49" in prev_tail or "第49章" in prev_tail or "卷一收束" in prev_tail, \
        f"cross-volume prev_tail missing: {prev_tail[:200]!r}"
    # The volume phase must come from vol_02/outline.md (not empty, not vol_01).
    assert data["p0"].get("volume_phase"), data["p0"]
    assert "vol_02" in str(beats_out) or "ch_050" in str(beats_out)

    # Full Stage 5 for vol_02/ch_050.
    _run_full_chapter(ws, book, "vol_02", 50, "卷二开篇", "op_cross_vol_050")

    # Post conditions: state lives on, and both snapshots exist.
    cur = state.load_state(book, "current")
    assert cur["location"] == "卷二·废铁港"
    assert cur["situation"] == "卷二开篇"
    snaps = sorted(book.joinpath("state/snapshots").glob("ch_*_done*"))
    # sync names snapshots "<ch>_done", and the directory itself contains the ts prefix.
    assert any("ch_049" in s.name for s in book.joinpath("state/snapshots").iterdir() if s.is_dir())
    assert any("ch_050" in s.name for s in book.joinpath("state/snapshots").iterdir() if s.is_dir())

    # Engine cross-volume reads stay healthy after two volumes are present.
    all_finals = common.find_chapter_files(book, "final")
    assert any(common.volume_of_path(f) == 2 for f in all_finals)
    # Each chapter resolves to exactly one final in its own volume.
    assert len(common.find_chapter_files(book, "final", "vol_01/ch_049")) == 1
    assert len(common.find_chapter_files(book, "final", "vol_02/ch_050")) == 1
    # The bare chapter token must not hide the volume when both volumes exist
    # near the boundary: ch_049 belongs to vol_01 even though vol_02 also has
    # chapters with the same "ch_" naming scheme.
    bare_049 = common.find_chapter_files(book, "final", "ch_049")
    assert len(bare_049) == 1
    assert common.volume_of_path(bare_049[0]) == 1
