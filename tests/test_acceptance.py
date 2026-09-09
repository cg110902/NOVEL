"""验收强化三件套（c17）——回应「只跑几个自欺欺人的 test 不太行」：

1. TestPipelineE2E：真实创作流水线全流程（只经 CLI 公开面，零私有函数）——
   init → beats new → raw → final → proposal new+填充 → audit → sync →
   rollup → reconcile → check --trend → snapshot 手术与回滚 → export。
   覆盖此前只有子进程/私有助手路径的集成缝隙（changelog 激活、回滚入账、sync 闸门链）。
2. TestChaosSweep：12 种损坏注入 × 10 条命令的健壮性矩阵——
   任何损坏都不得引发未捕获 Traceback，退出码必须落在 0/1/2/3 契约内。
3. TestLegacyBook：changelog 之前创建的老书（无事件流）全命令优雅降级。
"""
from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._fixtures import TempBook  # noqa: E402

_AUDIT_OK = "---\nhard: 0\nadjudicated: false\n---\n\n# 仲裁\n"

_CH1 = ("林牧背着断水剑进了临江城，在茶棚落脚。赵莽赶来报信，说城中当铺来了批来路不明的"
        "古物，其中一柄旧剑的形制与断水剑同源。两人约定夜里去当铺查探。林牧摸了摸剑鞘，"
        "想起师父临终的话，心头一沉。入夜，两人翻墙进当铺后院，在库房外听见有人低声议事，"
        "声音听着耳熟。林牧按住赵莽的肩，示意莫动。")
_CH2 = ("翌日，林牧再去当铺，掌柜的换了副嘴脸，一口咬定库房里没有旧剑。林牧不动声色，"
        "只说要当一件祖传的玉佩。掌柜的验货时手抖了一下，林牧看在眼里。回程路上，赵莽说起"
        "断水剑的来历，两人越说越觉得此事背后有人布局。夜里，林牧把师父留下的信物取出来，"
        "对着灯火端详良久，信物上刻着一个古字，他从未见过。")


class _E2EBook(TempBook):
    """带全流程助手的 E2E 书。"""

    def fill_templates(self):
        bible_body = ("市井即江湖：当铺通赃、镖行吃黑白两道；情报靠茶棚闲话与账房耳目。"
                      "武行分三等：把式（打熬筋骨）、暗劲（内息伤人）、宗师（一人镇一城）。"
                      "信物认主不认人，古字铭刻者可溯源旧朝匠监。当铺三年一拍卖，"
                      "黑货过三手即洗白；衙门按例抽查，打点钱分四层。")
        for i in range(1, 8):
            self.write(f"bible/0{i}_{'world_axioms' if i == 1 else 'misc'}.md",
                       f"# 第{i}章设定\n\n{bible_body}\n")
        for p in sorted((self.book / "bible").glob("*.md")):
            if "{{slot" in p.read_text(encoding="utf-8"):
                p.write_text(f"# 设定\n\n{bible_body}\n", encoding="utf-8")
        self.write("characters/protagonist.md", "# 林牧\n\n青云宗外门弟子，持断水剑。\n")
        self.write("outlines/main_plot.md",
                   "# 主线梗概\n\n- **核心主角**：林牧\n- **规划体量**：2 卷\n\n"
                   "林牧追查断水剑来历，牵出当铺背后的布局。\n")
        self.write("outlines/vol_01/outline.md", "# 第一卷 卷纲\n\n临江城当铺疑云。\n")
        r = self.run("config", "set", "words_target", "400,1400")
        assert r.returncode == 0, r.stdout + r.stderr

    def seal(self, n: int, text: str, prop: dict, form: str = "推进") -> dict:
        ch = f"ch_{n:03d}"
        r = self.run("beats", "new", ch, "--write")
        assert r.returncode == 0, f"beats new 失败: {r.stdout[-300:]}{r.stderr[-300:]}"
        # 章型轮换（防 form_repeat error）+ 模拟 Stage 1 主控填掉全部槽位
        beats_p = None
        for p in (self.book / "outlines").rglob(f"{ch}.md"):
            beats_p = p
        raw = beats_p.read_text(encoding="utf-8")
        raw = raw.replace("form: 推进", f"form: {form}")
        import re as _re
        raw = _re.sub(r"\{\{slot:[^|}]*\|([^}]*)\}\}", r"\1", raw)
        beats_p.write_text(raw, encoding="utf-8")
        vol = beats_p.parent.parent.name
        self.write(f"manuscript/{vol}/raw/{ch}_v1.md", f"# 第{n}章 初稿\n\n{text}\n")
        self.write(f"manuscript/{vol}/final/{ch}.md", f"# 第{n}章 当铺疑云\n\n{text}\n")
        r = self.run("audit", ch, "--write")
        assert r.returncode == 0, f"audit 失败: {r.stdout[-300:]}{r.stderr[-300:]}"
        r = self.run("proposal", "new", ch, "--write")
        assert r.returncode == 0, f"proposal new 失败: {r.stdout[-200:]}{r.stderr[-200:]}"
        prop = {"schema": "novel-studio.state-mutation/v2", "chapter": ch,
                "operation_id": f"{ch}.reader.r", **prop}
        self.write(f"state/inbox/{ch}.json", json.dumps(prop, ensure_ascii=False, indent=1))
        out = self.run_json("sync", ch)
        assert out.get("snapshot", {}).get("ok"), (
            f"sync {ch} 失败: {json.dumps(out, ensure_ascii=False)[:800]}")
        return out


def _make_e2e_book() -> _E2EBook:
    tb = _E2EBook(title="端到端书", genre="悬疑")
    tb.__enter__()
    tb.fill_templates()
    tb.seal(1, _CH1, {
        "synopsis": {"text": "林牧进城，当铺疑云起。", "title": "当铺疑云"},
        "entities": [
            {"action": "upsert", "id": "p_001", "name": "林牧", "type": "person",
             "summary": "主角，持断水剑。"},
            {"action": "upsert", "id": "p_002", "name": "赵莽", "type": "person",
             "summary": "林牧同伴。"}],
        "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                   "name": "断水剑的来历", "target_ch": 8, "weight": 2, "plan": "查当铺"}],
        "locked": [{"action": "plant", "id": "LOCK-001", "kind": "irreversible_action",
                    "since_ch": "ch_001",
                    "fact": "林牧的师父临终留下一枚刻古字的信物", "note": "身世线锚点",
                    "quote": "想起师父临终的话，心头一沉。"}],
    }, form="推进")
    tb.seal(2, _CH2, {
        "synopsis": {"text": "掌柜露破绽，信物现古字。", "title": "古字信物"},
        "entities": [{"action": "upsert", "id": "p_001", "name": "林牧", "type": "person",
                      "summary": "查当铺，得古字线索。"}],
    }, form="对峙")
    return tb


class TestPipelineE2E(unittest.TestCase):
    """真实流水线全流程：只走 CLI 公开面（子进程），覆盖集成缝隙。"""

    @classmethod
    def setUpClass(cls):
        cls.tb = _make_e2e_book()

    @classmethod
    def tearDownClass(cls):
        cls.tb.__exit__(None, None, None)

    def test_01_beats_has_line_action_section(self):
        beats = (self.tb.book / "outlines" / "vol_01" / "beats" / "ch_001.md").read_text(encoding="utf-8")
        self.assertIn("线索动作", beats)
        self.assertIn("伏笔与线索动作", beats)

    def test_02_audit_report_has_frontmatter(self):
        rep = (self.tb.book / "log" / "audit" / "ch_001.md").read_text(encoding="utf-8")
        head = "\n".join(rep.splitlines()[:8])
        self.assertIn("hard:", head)
        self.assertIn("adjudicated:", head)

    def test_03_state_and_changelog_consistent(self):
        from engine import changelog, state as st
        ok, msg = changelog.verify(self.tb.book)
        self.assertTrue(ok, msg)
        ents = st.load_state(self.tb.book, "entities")
        self.assertEqual(len(ents["entries"]), 2)

    def test_04_state_at_and_blame_via_cli(self):
        out = self.tb.run_json("state", "at", "1")
        self.assertIn("persons", json.dumps(out)[:2000])
        out = self.tb.run_json("state", "blame", "entities.entries[p_001].summary")
        blob = json.dumps(out, ensure_ascii=False)
        self.assertIn("entries[p_001].summary", blob)

    def test_05_rollup_and_reconcile(self):
        out = self.tb.run_json("state", "rollup", "vol_01")
        self.assertTrue(out.get("ok"), out)
        self.assertTrue((self.tb.book / "state" / "rollups" / "vol_01.json").is_file())
        r = self.tb.run("reconcile", "vol_01", "--write")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tb.book / "log" / "review" / "reconcile_vol_01.md").is_file())
        again = self.tb.run("reconcile", "vol_01", "--write")
        self.assertEqual(again.returncode, 1, "对账工作单不得覆盖")

    def test_06_pack_renders_blocks(self):
        r = self.tb.run("pack", "ch_002")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("硬提醒", r.stdout)
        self.assertIn("LOCK-001", r.stdout)          # locked 注入（防吃书）
        self.assertIn("上章余温", r.stdout)          # 前章承接
        self.assertIn("不可逆事实台账", r.stdout)    # beats 一致性速查注入
        self.assertNotIn("前情卷末态势", r.stdout)   # 同卷无 rollup 注入

    def test_07_check_clean_and_trend(self):
        out = self.tb.run_json("check")
        self.assertEqual(out.get("errors", []), [], json.dumps(out.get("errors", [])[:3], ensure_ascii=False))
        r = self.tb.run("check", "--trend")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("分数曲线", r.stdout)
        self.assertRegex(r.stdout, r"定稿章?\s*2")  # 曲线含最新定稿章号

    def test_08_snapshot_surgery_rollback_roundtrip(self):
        from engine import changelog, state as st
        r = self.tb.run("snapshot", "create", "e2e_mark")
        self.assertEqual(r.returncode, 0, r.stderr)
        # 手术刀：位阶直改（经 save_state → changelog 入账）
        r = self.tb.run("state", "set", "entities.林牧.tier_rank", "6")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(st.load_state(self.tb.book, "entities")["entries"][0].get("tier_rank"), 6)
        # 回滚 → 状态还原 + 回滚作为事件入账（changelog.verify 仍成立）
        r = self.tb.run("snapshot", "rollback", "e2e_mark")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout[-400:])
        ok, msg = changelog.verify(self.tb.book)
        self.assertTrue(ok, f"回滚后事件流与磁盘不一致: {msg}")
        ents = st.load_state(self.tb.book, "entities")
        tier = next((e.get("tier_rank") for e in ents["entries"] if e.get("name") == "林牧"), None)
        self.assertIsNone(tier, "回滚后手术刀改动必须被撤销")

    def test_09_export_txt(self):
        r = self.tb.run("export", "--txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        files = list((self.tb.book / "export").glob("*.txt"))
        self.assertTrue(files)


class TestChaosSweep(unittest.TestCase):
    """损坏注入 × 命令矩阵：任何损坏不得引发未捕获 Traceback / 契约外退出码。"""

    @classmethod
    def setUpClass(cls):
        cls.tb = _make_e2e_book()

    @classmethod
    def tearDownClass(cls):
        cls.tb.__exit__(None, None, None)

    # (名字, 对好书的破坏动作)
    CORRUPTIONS = [
        ("entities_truncated", lambda b: (b / "state/persons.json").write_text('{"entries": [{"id"', encoding="utf-8")),
        ("entities_wrong_type", lambda b: (b / "state/persons.json").write_text("[]", encoding="utf-8")),
        ("lines_missing_bucket", lambda b: (b / "state/lines.json").write_text('{"misunderstandings": [], "knowledge": []}', encoding="utf-8")),
        ("rollup_garbage", lambda b: (b / "state/rollups/vol_01.json").write_text("<<<不是json>>>", encoding="utf-8")),
        ("rollup_bad_schema", lambda b: (b / "state/rollups/vol_01.json").write_text('{"schema": "evil/v9"}', encoding="utf-8")),
        ("rollup_type_confusion", lambda b: (b / "state/rollups/vol_01.json").write_text('{"schema": "novel-studio.rollup/v1", "entities": "一根字符串"}', encoding="utf-8")),
        ("changelog_truncated_line", lambda b: (b / "state/changelog.jsonl").write_text((b / "state/changelog.jsonl").read_text(encoding="utf-8")[:-40], encoding="utf-8")),
        ("changelog_garbage_line", lambda b: (b / "state/changelog.jsonl").write_text('{"seq": 1, "broken"\n', encoding="utf-8")),
        ("scorecard_garbage", lambda b: (b / "log/scorecard.jsonl").write_text("garbage-line\n", encoding="utf-8")),
        ("project_invalid_json", lambda b: (b / "project.json").write_text("{broken", encoding="utf-8")),
        ("inbox_broken", lambda b: (b / "state/inbox/ch_003.json").write_text('{"chapter": ', encoding="utf-8")),
        ("snapshot_corrupted", lambda b: _corrupt_latest_snapshot(b)),
    ]

    COMMANDS = [
        ("status",), ("cockpit",), ("check",), ("doctor",),
        ("pack", "ch_002"), ("state", "get", "current"),
        ("state", "at", "1"), ("state", "blame", "entities"),
        ("state", "rollup", "vol_01"), ("reconcile", "vol_01"),
        ("recall", "ch_002"), ("graph",),
    ]
    # 这些命令承诺 stdout 纯 JSON 信封（P3-9 契约）
    JSON_ENVELOPE_CMDS = {"check", "cockpit", "status", "state", "reconcile", "recall"}

    def test_no_crash_under_any_corruption(self):
        from engine import common
        failures = []
        for cname, corrupt in self.CORRUPTIONS:
            backups = {}
            targets = {
                "persons": self.tb.book / "state" / "persons.json",
                "lines": self.tb.book / "state" / "lines.json",
                "rollup": self.tb.book / "state" / "rollups" / "vol_01.json",
                "changelog": self.tb.book / "state" / "changelog.jsonl",
                "scorecard": self.tb.book / "log" / "scorecard.jsonl",
                "project": self.tb.book / "project.json",
                "inbox": self.tb.book / "state" / "inbox" / "ch_003.json",
            }
            for key, p in targets.items():
                if p.is_file():
                    backups[key] = p.read_bytes()
                    backups[f"{key}__path"] = p
            snaps = sorted((self.tb.book / "state" / "snapshots").glob("*e2e*")) \
                if (self.tb.book / "state" / "snapshots").is_dir() else []
            snap_bak = snaps[-1].read_bytes() if snaps else None
            try:
                corrupt(self.tb.book)
                for cmd in self.COMMANDS:
                    r = self.tb.run(*cmd, "--json")
                    tag = f"[{cname} × {' '.join(cmd)}]"
                    if "Traceback (most recent call last)" in r.stderr:
                        failures.append(f"{tag} 未捕获异常:\n{r.stderr.strip()[-400:]}")
                    if r.returncode not in (0, 1, 2, 3):
                        failures.append(f"{tag} 契约外退出码 {r.returncode}")
                    if cmd[0] in self.JSON_ENVELOPE_CMDS and r.returncode != 2:
                        try:
                            json.loads(r.stdout)
                        except json.JSONDecodeError:
                            failures.append(f"{tag} --json 但 stdout 非 JSON: {r.stdout[:120]!r}")
            finally:
                for key, p in list(backups.items()):
                    if key.endswith("__path"):
                        continue
                    p = backups[f"{key}__path"]
                    p.write_bytes(backups[key])
                if snap_bak is not None and snaps:
                    snaps[-1].write_bytes(snap_bak)
        self.assertEqual(failures, [], "混沌扫描发现 %d 处崩溃/违约:\n%s"
                         % (len(failures), "\n---\n".join(failures[:8])))


def _corrupt_latest_snapshot(book: Path) -> None:
    snaps = sorted(p for p in (book / "state" / "snapshots").iterdir() if p.is_dir())
    if snaps:
        (snaps[-1] / "persons.json").write_text('{"entries": "坏了"', encoding="utf-8")


class TestLegacyBook(unittest.TestCase):
    """changelog 之前创建的老书（无事件流）：全命令优雅降级、不崩。"""

    @classmethod
    def setUpClass(cls):
        cls.tb = _E2EBook(title="老书", genre="悬疑")
        cls.tb.__enter__()
        cls.tb.fill_templates()
        cls.tb.seal(1, _CH1, {
            "synopsis": {"text": "开局。"},
            "entities": [{"action": "upsert", "id": "p_001", "name": "林牧",
                          "type": "person", "summary": "主角。"}],
        })
        # 模拟「changelog 之前创建的书」：删除事件流三件套
        for p in ("state/changelog.jsonl", "state/changelog_base.json",
                  "state/changelog_meta.json"):
            f = cls.tb.book / p
            if f.is_file():
                f.unlink()

    @classmethod
    def tearDownClass(cls):
        cls.tb.__exit__(None, None, None)

    def test_state_at_refuses_with_human_message(self):
        r = self.tb.run("state", "at", "1")
        self.assertIn("事件流未激活", r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_blame_refuses_gracefully(self):
        r = self.tb.run("state", "blame", "entities")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 1)

    def test_check_and_pack_still_work(self):
        out = self.tb.run_json("check")
        self.assertIn("errors", out)
        r = self.tb.run("pack", "ch_001")
        self.assertEqual(r.returncode, 0, r.stderr[-300:])

    def test_reconcile_works_without_changelog(self):
        r = self.tb.run("reconcile", "vol_01")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(r.returncode, 0)

    def test_z_new_sync_reactivates_changelog(self):
        # 老书继续写作：下一次 sync 重新激活事件流（基线=现状），从此可溯源
        self.tb.seal(2, _CH2, {"synopsis": {"text": "续写。"}})
        from engine import changelog
        self.assertTrue(changelog.active(self.tb.book))
        ok, msg = changelog.verify(self.tb.book)
        self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()
