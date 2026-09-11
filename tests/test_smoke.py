"""冒烟：临时书完整走一章（init→beats→成稿→提案→审计→sync→check→pack）。

跑法（仓库根）：`.venv/bin/python -m tests.test_smoke`
全程 NOVEL_STUDIO_WORKSPACE_ROOT 隔离，不碰开发者 workspace/。
build_smoke_book() 可被 test_gates.py 复用：建一本已 sync ch_001 的书。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDIO = [sys.executable, "studio.py"]

FINAL_TITLE = "第1章 拾灯人"
MOOD_QUOTE = "陈默攥紧了灯柄，指节发白，却一个字也没说。"
def run(args: list[str], env: dict, timeout: int = 120) -> subprocess.CompletedProcess:
    cp = subprocess.run(STUDIO + args, cwd=ROOT, env=env,
                        capture_output=True, text=True, timeout=timeout)
    return cp


def must_ok(cp: subprocess.CompletedProcess, what: str) -> str:
    assert cp.returncode == 0, (
        f"SMOKE FAIL [{what}] rc={cp.returncode}\n--- stdout ---\n{cp.stdout}\n--- stderr ---\n{cp.stderr}")
    return cp.stdout


def fill_beats_slots(text: str) -> str:
    def _sub(m: re.Match) -> str:
        name, default = m.group(1), m.group(2)
        if default:
            return default
        return {"chapter_id": "ch_001", "vol_id": "vol_01", "protagonist": "陈默"}.get(name, "（已填）")
    text = re.sub(r"\{\{slot:([^}|]+)(?:\|([^}]*))?\}\}", _sub, text)
    text = re.sub(r"^pov:\s*$", "pov: 陈默", text, flags=re.M)
    assert "{{slot:" not in text, "beats 仍有未填槽位"
    return text


def write_manuscript(book: Path) -> None:
    body = (
        "# 第1章 拾灯人\n\n"
        "灯会三更，灯市街口的人潮散了大半，陈默把扁担往肩头紧了紧，独自往回走。\n"
        "巷口的老槐树下悬着一盏无主空灯，灯纸焦黄，火早灭了，随风轻轻打转。\n"
        "陈默认得这盏灯——三年前灯王会上，师父举着它走在最前头，如今师父坟头的草都三尺高了。\n"
        "“谁把灯挂这儿了？”他伸手去摘，指尖刚碰到灯骨，身后传来一声冷笑。\n"
        "“拾灯人陈默，胆子不小。”来人斗笠压得很低，腰间一柄断刀，“这盏灯，是苏老爷点名要的东西。”\n"
        "陈默攥紧了灯柄，指节发白，却一个字也没说。\n"
        "他知道苏老爷要的不是灯，是当年灯王会上输掉的那口气。\n"
        "“灯我先替师父收着。”陈默把空灯摘下来，抱在怀里，“想要，让苏老爷亲自来取。”\n"
        "斗笠客盯着他看了许久，忽然笑了：“有种。三日后，苏府灯宴，恭候大驾。”\n"
        "说罢转身没入夜色，只留下半截断刀的寒光。\n"
        "陈默抱着那盏无主的空灯站在风里，灯纸簌簌作响，像是谁在耳边叹气。\n"
        "他低头看了看灯底——那里刻着一行极小的字：灯灭人不散。\n"
        "陈默的心猛地一沉。这行字，是师父的笔迹。\n"
    )
    raw_v1 = "# 第1章 拾灯人（v1 草稿）\n\n陈默在灯市街口发现无主空灯，与苏府斗笠客对峙，约定三日后灯宴。\n"
    raw_v2 = "# 第1章 拾灯人（v2 重塑）\n\n" + body.split("\n\n", 1)[1]
    (book / "manuscript" / "vol_01" / "raw").mkdir(parents=True, exist_ok=True)
    (book / "manuscript" / "vol_01" / "final").mkdir(parents=True, exist_ok=True)
    (book / "manuscript" / "vol_01" / "raw" / "ch_001_v1.md").write_text(raw_v1, encoding="utf-8")
    (book / "manuscript" / "vol_01" / "raw" / "ch_001_v2.md").write_text(raw_v2, encoding="utf-8")
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text(body, encoding="utf-8")


def fill_proposal(book: Path) -> None:
    p = book / "state" / "inbox" / "ch_001.json"
    prop = json.loads(p.read_text(encoding="utf-8"))
    prop["current"] = {
        "present_characters": ["陈默"],
        "location": "灯市街口老槐树下",
        "time": "灯会夜三更",
        "situation": "陈默拾得无主空灯，与苏府斗笠客定下三日灯宴之约",
        "present_moods": {"陈默": {"label": "隐忍", "level": 3, "quote": MOOD_QUOTE}},
    }
    prop["entities"] = [{
        "id": "p_001", "name": "陈默", "type": "person",
        "summary": "灯市拾灯人，师父旧部，怀抱无主空灯赴三日之约",
        "injury_level": 2, "injury_desc": "左臂刀伤", "renown": 5,
    }]
    prop["lines"] = [{
        "kind": "foreshadow", "action": "plant", "id": "GUN-001",
        "name": "无主空灯", "target_ch": "longline",
        "plan": "灯底师父笔迹牵出三年前灯王会旧案",
    }]
    prop["timeline"] = {"events": [{
        "time": "灯会夜三更",
        "event": "陈默在灯市街口摘下无主空灯，与苏府斗笠客定约三日后灯宴",
        "quote": "“灯我先替师父收着。”陈默把空灯摘下来，抱在怀里",
    }], "arcs": []}
    prop["synopsis"] = {"title": FINAL_TITLE,
                        "text": "陈默拾得师父遗留的无主空灯，与苏府来人定下三日灯宴之约。"}
    p.write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")


def build_smoke_book(wsroot: Path) -> tuple[Path, dict]:
    """建临时书并完整 sync ch_001；返回 (book, env)。失败直接抛 AssertionError。"""
    env = dict(os.environ)
    env["NOVEL_STUDIO_WORKSPACE_ROOT"] = str(wsroot)
    book = wsroot / "demo"
    must_ok(run(["init", "-w", str(book), "-t", "冒烟灯", "-g", "悬疑", "-p", "陈默"], env), "init")
    # Stage 0 槽位填充（真流程由 Architect 写圣经；冒烟用默认值实例化，否则 unfilled_slot 阻断）
    for pat in ("bible/*.md", "characters/*.md", "outlines/*.md", "outlines/*/outline.md"):
        for f in book.glob(pat):
            f.write_text(fill_beats_slots(f.read_text(encoding="utf-8")), encoding="utf-8")
    must_ok(run(["beats", "new", "ch_001", "--write"], env), "beats new")
    beats_files = list(book.glob("outlines/*/beats/ch_001.md")) or list(book.glob("outlines/**/ch_001.md"))
    assert beats_files, "beats new 未落盘 ch_001"
    bp = beats_files[0]
    bp.write_text(fill_beats_slots(bp.read_text(encoding="utf-8")), encoding="utf-8")
    write_manuscript(book)
    must_ok(run(["proposal", "new", "ch_001", "--write"], env), "proposal new")
    fill_proposal(book)
    must_ok(run(["proposal", "check", "ch_001"], env), "proposal check")
    must_ok(run(["audit", "ch_001", "--write"], env), "audit")
    must_ok(run(["sync", "ch_001"], env), "sync")
    return book, env


def main() -> int:
    passed = []
    with tempfile.TemporaryDirectory(prefix="novel_smoke_") as td:
        book, env = build_smoke_book(Path(td))
        passed.append("full_cycle_ch001")

        out = must_ok(run(["check"], env), "check")
        passed.append("check_rc0")

        out = must_ok(run(["pack", "ch_001"], env), "pack")
        # P0 current 块自动带 present_moods ＋ P1 实体块 mood 行（半角冒号缩进为 P1 专有标记）
        assert "present_moods" in out, f"pack P0 未带 present_moods\n{out[:2000]}"
        assert "\n  心境: 隐忍·3/5" in out, f"pack P1 未渲染情绪行\n{out[:2000]}"
        assert "\n  伤势: Lv2：左臂刀伤" in out, f"pack P1 未渲染伤势行\n{out[:2000]}"
        assert "\n  声望: 5" in out, f"pack P1 未渲染声望行\n{out[:2000]}"
        passed.append("pack_mood_injected")

        out = must_ok(run(["beats", "new", "ch_002"], env), "beats new ch_002")
        assert "心境" in out and "隐忍" in out, f"beats 速查未带心境基线\n{out[:2000]}"
        passed.append("beats_mood_baseline")

        out = must_ok(run(["calendar"], env), "calendar")
        assert '"longlines"' in out and "GUN-001" in out, f"calendar 缺长线节\n{out[:2000]}"
        passed.append("calendar_longlines")

        out = must_ok(run(["state", "get", "current.present_moods"], env), "state get moods")
        assert "陈默" in out and "隐忍" in out, f"present_moods 未落盘\n{out[:2000]}"
        passed.append("moods_persisted")

    print("SMOKE PASS (%d): %s" % (len(passed), ", ".join(passed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
