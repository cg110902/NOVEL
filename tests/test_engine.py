"""引擎回归测试：覆盖 REVIEW_V3.1 修复项的真实代码路径。

每个用例都跑真实函数/真实 CLI，不用替身实现。
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import checks, common, evidence, graph, state, validator  # noqa: E402
from engine import errcodes  # noqa: E402
from engine.commands import chapter_flow, state_sync  # noqa: E402
from engine.commands._shared import parse_audit_frontmatter  # noqa: E402
from engine.models.entities import LOCATION_TYPES, EntityEntry  # noqa: E402
from engine.pack import ROLE_ALLOW_EXTRA, ROLE_DENY, deny_reason  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402


# ---------------------------------------------------------------------------
# P0-1 evidence._stats_one 的 cjk 统计（此前 NameError 打崩 evidence all/style/file）
# ---------------------------------------------------------------------------
class TestEvidenceStats(unittest.TestCase):
    def test_stats_one_reports_cjk_count(self):
        text = "林牧推门进屋，屋里点着灯。ABC 123"
        stats = evidence._stats_one(text)
        self.assertEqual(stats["cjk"], common.cjk_count(text))
        self.assertGreater(stats["cjk"], 0)

    def test_evidence_file_cli_exits_zero(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧推门进屋，屋里点着一盏灯。" * 40)
            payload = tb.run_json("evidence", "file", "manuscript/vol_01/final/ch_001.md")
            self.assertNotIn("error", payload)
            self.assertGreater(payload.get("cjk", 0), 0)


# ---------------------------------------------------------------------------
# P2-5 candidate_new_entity 噪声：POS 门控后普通名词不再冒充新专名
# ---------------------------------------------------------------------------
class TestProperNounGate(unittest.TestCase):
    def test_proper_noun_tokens_filters_common_nouns(self):
        tokens = evidence.proper_noun_tokens("林牧推开木门，看着远处的山峦和灯火。")
        self.assertIn("林牧", tokens)
        for noise in ("木门", "山峦", "灯火"):
            self.assertNotIn(noise, tokens)

    def test_verify_candidates_no_noise_on_clean_chapter(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧推门进屋，屋里点着一盏灯。掌柜抬头看了他一眼。" * 30)
            payload = tb.run_json("proposal", "check", "ch_001") if (
                tb.path("state/inbox/ch_001.json").is_file()) else {}
            # 无提案时 proposal check 会报缺失；这里直接调底层电池，确保走真实实现
            codes = _candidate_codes(tb.book)
            self.assertEqual(codes.get("candidate_new_entity", 0), 0,
                             f"干净章节仍产出候选噪声: {codes}")


def _candidate_codes(book: Path) -> dict:
    """直接跑 checks.verify_candidates（真实实现），统计各 code 命中次数。"""
    proposal = {"chapter": "ch_001", "entities": [], "lines": [],
                "ledger": {"transactions": []}, "timeline": {"events": [], "arcs": []},
                "synopsis": {"title": "x", "text": "y"}}
    out = checks.verify_candidates(book, "ch_001", proposal)
    counts: dict[str, int] = {}
    for item in out.get("items", []):
        counts[item.get("code", "")] = counts.get(item.get("code", ""), 0) + 1
    return counts


# ---------------------------------------------------------------------------
# P1-6 locked / cognition 防静默覆盖
# ---------------------------------------------------------------------------
class TestOverwriteGuard(unittest.TestCase):
    def _data(self):
        return {"current": {}, "entities": {}, "lines": {}, "timeline": {},
                "ledger": {}, "synopsis": {}, "locked": {"entries": []},
                "cognition": {"entries": []}}

    def _rep(self):
        return {"updated": [], "warnings": [], "errors": []}

    def test_locked_rewrite_refused_and_data_intact(self):
        data, rep = self._data(), self._rep()
        seed = {"locked": [{"action": "plant", "id": "LOCK-001", "fact": "灯铺被烧毁",
                            "kind": "destruction", "quote": "q"}]}
        state._merge_proposal_into(data, seed, "ch_002", 2, rep)
        self.assertEqual(rep["errors"], [])

        rep2 = self._rep()
        tamper = {"locked": [{"action": "plant", "id": "LOCK-001", "fact": "改写后的假历史",
                              "kind": "destruction", "quote": "q"}]}
        state._merge_proposal_into(data, tamper, "ch_002", 2, rep2)
        self.assertTrue(any("禁止静默覆盖" in e for e in rep2["errors"]), rep2["errors"])
        self.assertEqual(data["locked"]["entries"][0]["fact"], "灯铺被烧毁")

    def test_locked_idempotent_replay_not_duplicated(self):
        data, rep = self._data(), self._rep()
        seed = {"locked": [{"action": "plant", "id": "LOCK-001", "fact": "灯铺被烧毁",
                            "kind": "destruction", "quote": "q"}]}
        state._merge_proposal_into(data, seed, "ch_002", 2, rep)
        rep2 = self._rep()
        state._merge_proposal_into(data, seed, "ch_002", 2, rep2)
        self.assertEqual(rep2["errors"], [])
        self.assertEqual(len(data["locked"]["entries"]), 1)
        self.assertTrue(any("幂等" in u for u in rep2["updated"]))

    def test_locked_explicit_overwrite_allowed(self):
        data, rep = self._data(), self._rep()
        state._merge_proposal_into(data, {"locked": [
            {"action": "plant", "id": "LOCK-001", "fact": "旧事实",
             "kind": "destruction", "quote": "q"}]}, "ch_002", 2, rep)
        rep2 = self._rep()
        state._merge_proposal_into(data, {"locked": [
            {"action": "upsert", "id": "LOCK-001", "fact": "新事实",
             "kind": "destruction", "quote": "q", "overwrite": True}]}, "ch_002", 2, rep2)
        self.assertEqual(rep2["errors"], [])
        self.assertEqual(data["locked"]["entries"][0]["fact"], "新事实")

    def test_cognition_owner_change_refused(self):
        data, rep = self._data(), self._rep()
        state._merge_proposal_into(data, {"cognition": [
            {"action": "plant", "id": "COG-001", "character": "林牧",
             "content": "掌柜在等他松口", "kind": "fact", "quote": "q"}]}, "ch_002", 2, rep)
        rep2 = self._rep()
        state._merge_proposal_into(data, {"cognition": [
            {"action": "upsert", "id": "COG-001", "character": "掌柜", "content": "x",
             "kind": "fact", "quote": "q", "overwrite": True}]}, "ch_002", 2, rep2)
        self.assertTrue(any("认知归属不可覆盖" in e for e in rep2["errors"]), rep2["errors"])
        self.assertEqual(data["cognition"]["entries"][0]["character"], "林牧")


# ---------------------------------------------------------------------------
# P1-5.3 audit --write 合并：保住人工裁决痕迹
# ---------------------------------------------------------------------------
class TestAuditReportMerge(unittest.TestCase):
    OLD = """---
audit_chapter: ch_001
hard: 1
soft: 0
adjudicated: true
---

# ch_001 事实一致性仲裁报告

## 🔴 确凿硬矛盾（必须定向修复或核实排除）
- 候选一：称谓漂移

## ✅ 交叉核实排除（误报归档）
- [人工核实] 属回忆插叙，排除。
"""

    def _new_report(self, hard_body: str) -> str:
        return f"""---
audit_chapter: ch_001
hard: 1
soft: 0
adjudicated: false
---

# ch_001 事实一致性仲裁报告

## 🔴 确凿硬矛盾（必须定向修复或核实排除）
{hard_body}

## ✅ 交叉核实排除（误报归档）
<!-- 模板注释 -->
"""

    def test_unchanged_hard_block_preserves_adjudication(self):
        new_md, notes = chapter_flow._merge_audit_report(
            self.OLD, self._new_report("- 候选一：称谓漂移"))
        self.assertEqual(parse_audit_frontmatter(new_md)["adjudicated"], True)
        self.assertTrue(any("沿用既有 adjudicated" in n for n in notes), notes)
        self.assertIn("属回忆插叙，排除。", new_md)

    def test_changed_hard_block_resets_adjudication(self):
        new_md, notes = chapter_flow._merge_audit_report(
            self.OLD, self._new_report("- 候选一：称谓漂移\n- 候选二：死人复活"))
        self.assertEqual(parse_audit_frontmatter(new_md)["adjudicated"], False)
        self.assertTrue(any("回落 false" in n for n in notes), notes)
        self.assertIn("属回忆插叙，排除。", new_md)

    def test_first_write_has_no_notes(self):
        new_md, notes = chapter_flow._merge_audit_report(
            None, self._new_report("- 候选一"))
        self.assertEqual(notes, [])
        self.assertEqual(parse_audit_frontmatter(new_md)["adjudicated"], False)


# ---------------------------------------------------------------------------
# P1-8 YAML front-matter 引号键（{{slot:…}} 里的冒号曾把键截断）
# ---------------------------------------------------------------------------
class TestYamlFrontMatter(unittest.TestCase):
    FM = """---
id: p_001
name: "林牧"
address_matrix:
  "{{slot:target_char_1|核心搭档名}}": "{{slot:addr_to_target_1|对方称呼}}"
  "苏九娘": "公子"
---
"""

    def test_quoted_key_with_colon_not_garbled(self):
        fm = common.parse_yaml_front_matter(self.FM)
        self.assertEqual(fm["id"], "p_001")
        self.assertIn("{{slot:target_char_1|核心搭档名}}", fm["address_matrix"])
        self.assertEqual(fm["address_matrix"]["苏九娘"], "公子")
        self.assertNotIn("{{slot", fm["address_matrix"])

    def test_split_key_value_plain_and_quoted(self):
        self.assertEqual(common.split_key_value("a: b"), ("a", " b"))
        self.assertEqual(common.split_key_value('"x:y": z'), ("x:y", " z"))
        self.assertIsNone(common.split_key_value("no colon here"))

    def test_real_protagonist_template_parses(self):
        tmpl = (Path(__file__).resolve().parents[1]
                / "templates/characters/protagonist.md").read_text(encoding="utf-8")
        fm = common.parse_yaml_front_matter(tmpl)
        self.assertNotIn("{{slot", fm.get("address_matrix", {}))


# ---------------------------------------------------------------------------
# P1-8 引擎不得用自己的模板触发自己的闸门
# ---------------------------------------------------------------------------
class TestSelfInflictedGates(unittest.TestCase):
    def test_unfilled_slot_not_flagged_but_real_empty_criterion_is(self):
        with TempBook() as tb:
            tb.run("beats", "new", "ch_001", "--write", "--force")
            warns = _codes(tb, "warnings")
            self.assertEqual(warns.get("acceptance_empty_criterion", 0), 0,
                             "未填 {{slot:}} 兜底文案被当成主控写的空判据")

            beats = tb.path("outlines/vol_01/beats/ch_001.md")
            text = beats.read_text(encoding="utf-8")
            self.assertIn("核心事件发生并取得实质推进", text)  # 夹具自检：目标行必须存在
            beats.write_text(text.replace("核心事件发生并取得实质推进；",
                                          "读者情绪拉满，整体氛围到位；"),
                             encoding="utf-8")
            warns2 = _codes(tb, "warnings")
            self.assertGreaterEqual(warns2.get("acceptance_empty_criterion", 0), 1,
                                    "真空判据未被检出（闸门失效）")


def _codes(tb: TempBook, channel: str) -> dict:
    payload = tb.run_json("check")
    counts: dict[str, int] = {}
    for item in payload.get(channel, []):
        counts[item["code"]] = counts.get(item["code"], 0) + 1
    return counts


# ---------------------------------------------------------------------------
# P1-7 type=location 与 type=place 同为地点（此前 location 不上图、不注入）
# ---------------------------------------------------------------------------
class TestLocationTypeParity(unittest.TestCase):
    def test_location_types_ssot(self):
        self.assertEqual(LOCATION_TYPES, {"place", "location"})

    def test_location_entity_gets_located_in_edge(self):
        with TempBook() as tb:
            ents = tb.state("entities")
            ents["entries"] = [
                {"id": "p_001", "name": "林牧", "type": "person", "status": "active",
                 "summary": "主角", "location": "青石巷灯铺"},
                {"id": "loc_001", "name": "青石巷", "type": "location", "status": "active",
                 "summary": "老巷子"},
            ]
            tb.set_state("entities", ents)
            g = graph.build_narrative_graph(tb.book)
            edges = {(u, v) for u, v, d in g.edges(data=True)
                     if d.get("relation") == "located_in"}
            self.assertIn(("林牧", "青石巷"), edges)
            self.assertGreater(g.degree("青石巷"), 0)


# ---------------------------------------------------------------------------
# P1-9 word_band_deviation / word_band_breach 真正落地
# ---------------------------------------------------------------------------
class TestWordBand(unittest.TestCase):
    def test_short_final_reports_breach(self):
        with TempBook() as tb:
            tb.write("project.json", json.dumps(
                {**json.loads(tb.read("project.json")), "words_target": [2000, 3000]},
                ensure_ascii=False, indent=2))
            tb.seed_chapter("ch_001", "林牧推门进屋。" * 40)  # 约 240 字，远低于下限
            warns = _codes(tb, "warnings")
            self.assertGreaterEqual(warns.get("word_band_breach", 0), 1,
                                    "严重出带未被检出")

    def test_small_undershoot_reports_deviation_not_breach(self):
        with TempBook() as tb:
            tb.write("project.json", json.dumps(
                {**json.loads(tb.read("project.json")), "words_target": [2000, 3000]},
                ensure_ascii=False, indent=2))
            # 1800 字 vs 下限 2000：缺 200 = 10%，落在 20% 容差内 → deviation 而非 breach
            tb.seed_chapter("ch_001", "字" * 1800)
            warns = _codes(tb, "warnings")
            self.assertGreaterEqual(warns.get("word_band_deviation", 0), 1,
                                    "容差内出带未报 deviation")
            self.assertEqual(warns.get("word_band_breach", 0), 0,
                             "容差内出带被误升级为 breach")

    def test_in_band_final_is_quiet(self):
        with TempBook() as tb:
            tb.write("project.json", json.dumps(
                {**json.loads(tb.read("project.json")), "words_target": [100, 3000]},
                ensure_ascii=False, indent=2))
            tb.seed_chapter("ch_001", "林牧推门进屋。" * 40)
            warns = _codes(tb, "warnings")
            self.assertEqual(warns.get("word_band_deviation", 0), 0)
            self.assertEqual(warns.get("word_band_breach", 0), 0)


# ---------------------------------------------------------------------------
# P0-3 角色读权限网关：合法角色不再被拒，白名单例外生效
# ---------------------------------------------------------------------------
class TestRoleGateway(unittest.TestCase):
    def test_all_v31_roles_known(self):
        for role in ("architect", "director", "drafter", "editor", "reader", "critic",
                     "stylist", "auditor", "librarian", "evolver"):
            self.assertIn(role, ROLE_DENY, f"{role} 不在读权限网关角色表内")

    def test_unknown_role_message_lists_real_roles(self):
        reason = deny_reason(Path("/tmp/book"), "bible/x.md", "不存在的角色")
        self.assertIsNotNone(reason)
        for role in ("stylist", "auditor", "librarian", "evolver"):
            self.assertIn(role, reason)

    def test_auditor_whitelist_and_denials(self):
        book = Path("/tmp/book")
        self.assertIsNone(deny_reason(book, "state/locked.json", "auditor"))
        self.assertIsNone(deny_reason(book, "state/entities.json", "auditor"))
        self.assertIsNotNone(deny_reason(book, "state/ledger.json", "auditor"))
        self.assertIsNotNone(deny_reason(book, "manuscript/vol_01/raw/ch_001_v1.md", "auditor"))

    def test_stylist_and_librarian_scopes(self):
        book = Path("/tmp/book")
        self.assertIsNone(deny_reason(book, "bible/06_style_guidelines.md", "stylist"))
        self.assertIsNotNone(deny_reason(book, "state/locked.json", "stylist"))
        self.assertIsNone(deny_reason(book, "state/ledger.json", "librarian"))
        self.assertIsNotNone(deny_reason(book, "outlines/vol_01/beats/ch_001.md", "librarian"))
        self.assertIn("state/ledger.json", ROLE_ALLOW_EXTRA["librarian"])

    def test_report_p13_table_document_authorized_files_readable(self):
        """报告 P1-3 表格逐行复核：SKILL 准读清单授权的文件，机械层必须放行。

        此前只修了 Stylist/Critic 两行，Reader/Editor 两行仍被拒——
        「双层防御」名不副实：真按网关走，Editor 连文风宪法都拿不到。
        """
        book = Path("/tmp/book")
        for role, allowed in (
            ("reader", ["state/entities.json"]),
            ("editor", ["bible/06_style_guidelines.md"]),
            ("stylist", ["bible/06_style_guidelines.md"]),
            ("critic", ["state/current.json"]),
        ):
            for path in allowed:
                self.assertIsNone(deny_reason(book, path, role),
                                  f"{role} 的文档授权文件 {path} 仍被禁读")

    def test_whitelist_does_not_leak_siblings(self):
        """白名单是精确单文件，不得顺带放行同目录的其它状态表/圣经表。"""
        book = Path("/tmp/book")
        for role, denied in (
            ("reader", ["state/ledger.json", "state/lines.json", "state/locked.json"]),
            ("editor", ["bible/01_world_axioms.md", "bible/02_power_system.md"]),
            ("critic", ["state/entities.json", "state/synopsis.json"]),
        ):
            for path in denied:
                self.assertIsNotNone(deny_reason(book, path, role),
                                     f"{role} 越权读取 {path} 未被拦截")

    def test_cli_as_choices_derive_from_gateway(self):
        with TempBook() as tb:
            proc = tb.run("pack", "--help")
            for role in ("stylist", "auditor", "librarian", "evolver"):
                self.assertIn(role, proc.stdout)


# ---------------------------------------------------------------------------
# P1-4 state 盖章 + state_offline_edit；驾驶舱 3A/3B/4C
# ---------------------------------------------------------------------------
class TestStateProvenance(unittest.TestCase):
    def test_stamp_then_offline_edit_is_named(self):
        with TempBook() as tb:
            state_sync._stamp_state_hashes(tb.book, "ch_001")
            stamp = json.loads(tb.read("state/inbox/processed/state_hashes.json"))
            self.assertEqual(stamp["last_sync_chapter"], "ch_001")
            self.assertEqual(len(stamp["states"]), len(state.STATE_KEYS))

            self.assertEqual(_codes(tb, "warnings").get("state_offline_edit", 0), 0)

            cog = tb.state("cognition")
            cog["entries"].append({"id": "COG-001", "character": "林牧", "kind": "fact",
                                   "content": "离线手改", "since_ch": "ch_001", "quote": "q"})
            tb.set_state("cognition", cog)
            warns = _codes(tb, "warnings")
            self.assertGreaterEqual(warns.get("state_offline_edit", 0), 1)

    def test_cockpit_splits_stage3_and_tracks_audit(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001")
            wf = tb.run_json("cockpit", "ch_001")["workflow"]
            self.assertIn("raw_v2", wf["status"])
            self.assertIn("audit_state", wf["status"])
            self.assertEqual(wf["current_stage"], "Stage 4 (三轨并发质检)")
            self.assertIn("Auditor", wf["next_action"]["actor"])

            # 只留 raw_v1 → 应指向 Stage 3A Editor
            tb.path("manuscript/vol_01/raw/ch_001_v2.md").unlink()
            wf2 = tb.run_json("cockpit", "ch_001")["workflow"]
            self.assertEqual(wf2["current_stage"], "Stage 3A (骨肉重塑)")
            self.assertEqual(wf2["next_action"]["actor"], "Editor")

            # 补回 v2、删 final → 应指向 Stage 3B Stylist
            tb.write("manuscript/vol_01/raw/ch_001_v2.md", "# v2\n\n林牧推门进屋。\n")
            tb.path("manuscript/vol_01/final/ch_001.md").unlink()
            wf3 = tb.run_json("cockpit", "ch_001")["workflow"]
            self.assertEqual(wf3["current_stage"], "Stage 3B (通俗脱水与扫读优化)")
            self.assertEqual(wf3["next_action"]["actor"], "Stylist")


# ---------------------------------------------------------------------------
# P1-5 beats 注入资源池键名与 LOCK/COG 水位线
# ---------------------------------------------------------------------------
class TestBeatsInjection(unittest.TestCase):
    def test_pool_keys_and_id_watermarks_injected(self):
        with TempBook() as tb:
            ledger = tb.state("ledger")
            # 落盘态的池带引擎重算的 current（schema 必填），与提案里的 initial-only 写法不同
            ledger["pools"] = {"spirit_stone": {"name": "灵石", "unit": "块",
                                                "initial": 10, "current": 10}}
            tb.set_state("ledger", ledger)
            locked = tb.state("locked")
            # quote 受模型 min_length=2 约束，写单字符会让 load_state 抛错并被静默跳过
            locked["entries"] = [{"id": "LOCK-001", "fact": "灯铺被烧毁",
                                  "kind": "destruction", "quote": "门口站着一个人",
                                  "since_ch": "ch_001"}]
            tb.set_state("locked", locked)
            # 夹具自检：状态必须真能读回来，否则本用例测的是空注入而不是注入逻辑
            self.assertEqual(len(tb.state("locked")["entries"]), 1)
            self.assertIn("spirit_stone", tb.state("ledger")["pools"])
            tb.run("beats", "new", "ch_002", "--write", "--force")
            text = tb.read("outlines/vol_01/beats/ch_002.md")
            self.assertIn("资源池与 ID 水位线", text)
            self.assertIn("`spirit_stone`", text)
            self.assertIn("LOCK-001", text)


# ---------------------------------------------------------------------------
# P0-2 Stage 5 仲裁闸门端到端：hard>0 未裁定拒封 / 已裁定放行 / 放行后盖章
# ---------------------------------------------------------------------------
_AUDIT_REPORT = """---
audit_chapter: ch_001
hard: 2
soft: 0
adjudicated: {adj}
---

# ch_001 事实一致性仲裁报告

## 🔴 确凿硬矛盾（必须定向修复或核实排除）
- 候选一：称谓漂移
- 候选二：死人复活
"""


class TestStage5AuditGate(unittest.TestCase):
    def _seed(self, tb: TempBook, adjudicated: bool) -> None:
        tb.seed_chapter("ch_001", "林牧推门进屋，屋里点着一盏灯。" * 100)
        tb.write("log/audit/ch_001.md", _AUDIT_REPORT.format(
            adj="true" if adjudicated else "false"))
        tb.write("state/inbox/ch_001.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": "ch_001.gate.test",
            "synopsis": {"text": "主角拿到账册并当众揭穿造假。"}},
            ensure_ascii=False, indent=2))

    def test_unadjudicated_hard_conflicts_block_sync(self):
        with TempBook() as tb:
            self._seed(tb, adjudicated=False)
            out = tb.run_json("sync", "ch_001")
            self.assertFalse(out.get("ok", True))
            self.assertIn("事实一致性仲裁未通过", out.get("error", ""))
            self.assertIsNone(out.get("snapshot"))

    def test_adjudicated_hard_conflicts_pass_and_stamp(self):
        with TempBook() as tb:
            self._seed(tb, adjudicated=True)
            out = tb.run_json("sync", "ch_001")
            self.assertEqual(out.get("verify_errors"), [])
            self.assertTrue(out["snapshot"]["ok"], out)
            # 放行即盖章：八表 SHA-256 落盘，供 state_offline_edit 档比对
            stamp = json.loads(tb.read("state/inbox/processed/state_hashes.json"))
            self.assertEqual(stamp["last_sync_chapter"], "ch_001")
            self.assertEqual(len(stamp["states"]), len(state.STATE_KEYS))

    def test_missing_report_blocks_sync_in_strict_mode(self):
        with TempBook() as tb:
            self._seed(tb, adjudicated=True)
            tb.path("log/audit/ch_001.md").unlink()
            out = tb.run_json("sync", "ch_001")
            self.assertFalse(out.get("ok", True))
            self.assertIn("仲裁报告", out.get("error", ""))


# ---------------------------------------------------------------------------
# P2 杂项：indexed_chapters 语义 / state get 八表 / 冷索引措辞 / 软配额措辞
# ---------------------------------------------------------------------------
class TestMiscFixes(unittest.TestCase):
    def test_index_reports_total_and_new(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧推门进屋，屋里点着一盏灯。" * 40)
            first = tb.run_json("index")
            self.assertEqual(first["indexed_chapters"], 1)
            self.assertEqual(first["indexed_chapters_new"], 1)
            again = tb.run_json("index")
            self.assertEqual(again["indexed_chapters"], 1)
            self.assertEqual(again["indexed_chapters_new"], 0)

    def test_state_get_covers_all_eight_tables(self):
        with TempBook() as tb:
            for key in state.STATE_KEYS:
                proc = tb.run("state", "get", key)
                self.assertEqual(proc.returncode, 0, f"state get {key} 失败: {proc.stdout}")
                self.assertNotIn("未知状态分区", proc.stdout)

    def test_state_get_missing_field_not_python_none(self):
        with TempBook() as tb:
            proc = tb.run("state", "get", "current.不存在的字段")
            self.assertNotIn("= None", proc.stdout)
            self.assertIn("不存在", proc.stdout)

    def test_cold_index_window_wording(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧推门进屋，屋里点着一盏灯。" * 40)
            payload = tb.run_json("pack", "ch_001")
            pointers = payload.get("p2", {}).get("old_chapter_pointers", [])
            for line in pointers:
                self.assertNotIn("近10章未出现", line)

    def test_foreshadow_quota_wording_is_self_consistent(self):
        data = {"foreshadows": [
            {"id": f"GUN-{i:03d}", "name": f"线{i}", "status": "Planted", "target_ch": 20,
             "plant_ch": 1, "weight": 1, "plan": "", "requires": []} for i in range(1, 9)],
            "misunderstandings": [], "knowledge": []}
        rep = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(data, [{"kind": "foreshadow", "action": "plant", "id": "GUN-009",
                                   "name": "第九条线", "target_ch": 30}], 2, rep)
        self.assertEqual(len(data["foreshadows"]), 9)
        self.assertTrue(rep["warnings"])
        msg = rep["warnings"][0]
        self.assertIn("advisory", msg)
        self.assertNotIn("已达上限（8/8），新伏笔 GUN-009 已入库", msg)

    def test_milestone_achieve_labels_inferred_chapter(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧推门进屋。" * 40)
            tb.run("milestone", "add", "--title", "探针", "--target-ch", "20")
            out = tb.run_json("milestone", "achieve", "MS-001")
            self.assertTrue(out["achieved_ch_inferred"])
            self.assertIn("推断值", out["note"])


# ---------------------------------------------------------------------------
# P2-6 errcodes 注册表完备性
# ---------------------------------------------------------------------------
# 文档里用反引号标注、但不是错误码的合法 token（字段名/命令名/路径片段）
_NON_CODE_TOKENS = {
    "spirit_stone", "standard_currency", "locked_entry_id_reuse",
    "kind_set", "action_retire", "overwrite_true",
}


class TestErrcodeRegistry(unittest.TestCase):
    def test_every_emitted_code_is_registered(self):
        src = (Path(__file__).resolve().parents[1] / "engine/checks.py").read_text(encoding="utf-8")
        emitted = set(re.findall(r'_err\(\s*"([a-z0-9_]+)"', src))
        emitted |= set(re.findall(r'add\(\s*"(?:error|warn|info)"\s*,\s*"([a-z0-9_]+)"', src))
        emitted |= set(re.findall(r'_err\(\s*\n?\s*"([a-z0-9_]+)"', src))
        missing = sorted(c for c in emitted if c not in errcodes.REGISTRY)
        self.assertEqual(missing, [], f"checks.py 产出但未注册的错误码: {missing}")

    def test_codes_referenced_in_docs_and_injection_actually_exist(self):
        """文档/注入文案里点名的错误码必须真实存在。

        本次修复中我自己犯过这个错：把 `locked_entry_id_reuse` 写进 beats 注入
        与 Reader SKILL，但注册表里没有这个码，守卫报错也不带码名——
        Agent 照着 `errcodes` 查不到，等于给了个假线索。
        """
        root = Path(__file__).resolve().parents[1]
        # 1) state.py 里 [code] 前缀的报错必须注册
        src = (root / "engine/state.py").read_text(encoding="utf-8")
        prefixed = set(re.findall(r'f?"\[([a-z][a-z0-9_]+)\]', src))
        for code in prefixed:
            self.assertIn(code, errcodes.REGISTRY, f"报错前缀 [{code}] 未注册")
        self.assertIn("locked_entry_id_reuse", prefixed)
        self.assertIn("cognition_entry_id_reuse", prefixed)

        # 2) beats 注入小节与 Reader SKILL 点名的码必须注册
        cf = (root / "engine/commands/chapter_flow.py").read_text(encoding="utf-8")
        block = cf[cf.index("资源池与 ID 水位线"):cf.index("不可逆事实台账")]
        skill = (root / ".agents/skills/reader/SKILL.md").read_text(encoding="utf-8")
        named = set(re.findall(r"`([a-z][a-z0-9_]{5,})`", block)) | \
                set(re.findall(r"`([a-z][a-z0-9_]{5,})`", skill))
        for token in named:
            # 只校验长得像错误码的（含下划线、非字段名/命令名）
            if "_" not in token:
                continue
            if token in _NON_CODE_TOKENS:
                continue
            self.assertIn(token, errcodes.REGISTRY,
                          f"文档点名 `{token}` 但注册表里没有这个错误码")

    def test_registry_entries_well_formed(self):
        for code, entry in errcodes.REGISTRY.items():
            self.assertEqual(entry.code, code)
            self.assertIn(entry.level, errcodes.LEVELS)
            self.assertTrue(entry.description.strip(), f"{code} 缺 description")
            self.assertTrue(entry.remedy.strip(), f"{code} 缺 remedy")


# ---------------------------------------------------------------------------
# P2-17 枚举单一真源 + 悬空引用检查
# ---------------------------------------------------------------------------
class TestEnumSSOTAndDanglingRefs(unittest.TestCase):
    def test_enum_literals_derived_from_models(self):
        self.assertEqual(set(state._ENTITY_STATUS), {"active", "retired"})
        self.assertEqual(set(state._LIFE_STATUS),
                         {"alive", "deceased", "missing"})
        self.assertEqual(set(state._ATTITUDE),
                         {"hostile", "neutral", "friendly", "allied"})
        # 与模型枚举严格一致（模型改了，这里必须跟着变）
        self.assertEqual(set(state._ENTITY_STATUS),
                         {s.value for s in __import__("engine.models.entities", fromlist=["EntityStatus"]).EntityStatus})

    def test_clock_and_ledger_enums_also_derived(self):
        # 报告 五.2 列了 5 组手写字面量；这 3 组（时钟紧迫度/时钟状态/流水类型）
        # 此前漏改，现必须与模型严格一致
        from engine.models.ledger import TransactionType
        from engine.models.timeline import ClockStatus, ClockUrgency
        self.assertEqual(set(state._CLOCK_URGENCY), {u.value for u in ClockUrgency})
        self.assertEqual(set(state._CLOCK_STATUS), {s.value for s in ClockStatus})
        self.assertEqual(set(state._TX_TYPES), {x.value for x in TransactionType})
        self.assertEqual(set(state._CLOCK_URGENCY), {"low", "medium", "high", "critical"})
        self.assertEqual(set(state._CLOCK_STATUS),
                         {"Active", "Triggered", "Defused", "Expired"})

    def test_id_regex_single_source(self):
        # 报告 五.4：LOCK_ID_RE/COG_ID_RE 曾在 models 与 state.py 各定义一遍
        from engine.models.cognition import COG_ID_RE
        from engine.models.locked import LOCK_ID_RE
        self.assertIs(state.LOCK_ID_RE, LOCK_ID_RE)
        self.assertIs(state.COG_ID_RE, COG_ID_RE)

    def test_dangling_faction_and_location_flagged(self):
        with TempBook() as tb:
            ents = tb.state("entities")
            ents["entries"] = [
                {"id": "p_001", "name": "林牧", "type": "person", "status": "active",
                 "summary": "主角", "faction": "不存在的势力", "location": "某个没建卡的地方"},
            ]
            tb.set_state("entities", ents)
            warns = _codes(tb, "warnings")
            self.assertGreaterEqual(warns.get("entity_ref_unknown", 0), 2)

    def test_entity_field_count_documented(self):
        # 文档改口径为「33 个字段」，模型漂移时此断言会先红
        self.assertEqual(len(EntityEntry.model_fields), 33)


# ---------------------------------------------------------------------------
# 深读 engine/audit.py 发现的探针缺陷（此前 656 行探针内核从未通读）
# ---------------------------------------------------------------------------
class TestAuditProbes(unittest.TestCase):
    """探针 3/4 曾是死代码：单位正则被短词遮蔽、池键硬编码、枚举字面量非法。"""

    def test_amount_probe_resolves_unit_and_pool(self):
        from engine import audit
        cases = [
            ("付了九十块灵石", {"spirit_stone": {"name": "灵石", "unit": "块", "current": 10}}, True),
            ("付了九十两银子", {"silver": {"name": "白银", "unit": "两", "current": 10}}, True),
            ("付了九十两白银", {"silver": {"name": "白银", "unit": "两", "current": 10}}, True),
            ("花了三枚极品灵石", {"lingshi": {"name": "极品灵石", "unit": "枚", "current": 1}}, True),
            ("付了五十两黄金", {"gold": {"name": "黄金", "unit": "两", "current": 5}}, True),
        ]
        for line, pools, should_fire in cases:
            out = audit.probe_amount_ledger(line, [line], {"pools": pools})
            self.assertEqual(bool(out), should_fire, f"{line} 触发情况不符")

    def test_amount_probe_no_false_positive(self):
        from engine import audit
        # 正文「九十文」不得误挂到名叫「文献阁」的池（匹配方向必须是 token in unit）
        out = audit.probe_amount_ledger("付了九十文", ["付了九十文"],
                                        {"pools": {"wenge": {"name": "文献阁", "unit": "座", "current": 1}}})
        self.assertEqual(out, [])
        # 余额充足不应报警
        out2 = audit.probe_amount_ledger("付了十块灵石", ["付了十块灵石"],
                                         {"pools": {"spirit_stone": {"name": "灵石", "unit": "块", "current": 100}}})
        self.assertEqual(out2, [])

    def test_charges_probe_uses_legal_enum_and_condition(self):
        from engine import audit
        ents = [
            {"name": "断刀", "type": "item", "charges": 0, "status": "active"},
            {"name": "青玉瓶", "type": "item", "charges": 3, "status": "active",
             "condition": "灵性尽失，瓶身碎裂"},
            {"name": "旧符", "type": "item", "charges": 2, "status": "retired"},
            {"name": "完好剑", "type": "item", "charges": 5, "status": "active",
             "condition": "完好无损"},
            {"name": "林牧", "type": "person", "charges": 0, "status": "active"},
        ]
        lines = ["他祭出断刀。", "他催动青玉瓶。", "他祭起旧符。", "他拔出完好剑。", "林牧祭出灵气。"]
        out = audit.probe_charges_possession("\n".join(lines), lines, ents, {})
        flagged = {c["title"].split("「")[1].split("」")[0] for c in out}
        self.assertEqual(flagged, {"断刀", "青玉瓶", "旧符"})
        self.assertNotIn("完好剑", flagged)   # charges>0 且 condition 完好
        self.assertNotIn("林牧", flagged)     # person 类型不参与道具探针

    def test_probe_flag_codes_all_registered(self):
        """探针里 also_flagged_by 指向的码必须真实存在（曾出现 3 个幽灵码）。"""
        from engine import audit
        src = (Path(__file__).resolve().parents[1] / "engine/audit.py").read_text(encoding="utf-8")
        codes = set(re.findall(r'"also_flagged_by":\s*"([a-z0-9_]+)"', src))
        self.assertTrue(codes, "未扫到任何 also_flagged_by，扫描正则可能失效")
        for code in codes:
            self.assertIn(code, errcodes.REGISTRY, f"探针引用了不存在的错误码 {code}")
        for ghost in ("amount_unmatched", "item_charges_zero"):
            self.assertNotIn(ghost, codes, f"幽灵码 {ghost} 又出现了")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestMigrationSafety(unittest.TestCase):
    """迁移是会改用户数据的代码路径，必须有回归锁（审查阶段仅手工验证过，未落测试）。"""

    def setUp(self):
        from engine import migrations
        migrations._ENSURED.clear()

    def tearDown(self):
        from engine import migrations
        migrations._ENSURED.clear()

    @staticmethod
    def _set_version(tb, v: int) -> None:
        from engine import migrations
        tb.write(f"state/{migrations.VERSION_FILE}",
                 json.dumps({"version": v, "created_at": "2020-01-01"}, ensure_ascii=False))

    def test_higher_version_refuses_and_keeps_data(self):
        """书的状态版本高于引擎支持版本 → 必须拒绝，且不得改动任何 state 文件。"""
        from engine import migrations
        with TempBook(title="迁移高版本") as tb:
            self._set_version(tb, migrations.CURRENT_STATE_VERSION + 1)
            before = {k: tb.state(k) for k in state.STATE_KEYS}
            with self.assertRaises(ValueError) as ctx:
                migrations.ensure_state_version(tb.book)
            self.assertIn("高于当前引擎支持", str(ctx.exception))
            for k in state.STATE_KEYS:
                self.assertEqual(tb.state(k), before[k], f"拒绝高版本时不应改动 state/{k}.json")

    def test_migration_creates_rollback_snapshot(self):
        """v0 遗留书必须逐级迁到当前版本，且迁移前落可回滚快照。"""
        from engine import migrations, snapshot
        with TempBook(title="迁移快照") as tb:
            self._set_version(tb, migrations.LEGACY_VERSION)
            res = migrations.ensure_state_version(tb.book)
            self.assertTrue(res.get("migrated"), f"v0 应触发迁移，实际 {res}")
            names = snapshot.list_snapshots(tb.book)  # 返回快照名字符串列表
            self.assertTrue(any("pre_migration_v0" in n for n in names),
                            f"应存在迁移前快照，实际 {names}")
            self.assertEqual(res.get("to"), migrations.CURRENT_STATE_VERSION)
            self.assertEqual(migrations.read_version(tb.book), migrations.CURRENT_STATE_VERSION)
            # 迁移后八张表仍须通过 load_state 的分区校验（非法会抛 ValueError）
            for k in state.STATE_KEYS:
                try:
                    state.load_state(tb.book, k)
                except ValueError as exc:
                    self.fail(f"迁移后 state/{k}.json 应仍合法，实际: {exc}")

    def test_uninitialized_book_not_seeded(self):
        """空书（无 state 文件）不得被迁移逻辑播种出 state 分区。"""
        from engine import migrations
        with TempBook(title="迁移空书") as tb:
            (tb.book / "state").mkdir(parents=True, exist_ok=True)
            for k in state.STATE_KEYS:
                (tb.book / "state" / f"{k}.json").unlink(missing_ok=True)
            self.assertEqual(migrations.ensure_state_version(tb.book), {"migrated": False})
            self.assertFalse((tb.book / "state" / "entities.json").exists(),
                             "迁移不应给未初始化的书播种 state 分区")


class TestValidatorKeywords(unittest.TestCase):
    """mini 校验器自述支持的关键字必须与实现一致（曾漏列 7 个）。"""

    _IMPL = ("additionalProperties", "anyOf", "const", "enum", "items", "maxItems",
             "maxLength", "maximum", "minItems", "minLength", "minimum", "pattern",
             "properties", "required", "type")

    def test_docstring_lists_every_implemented_keyword(self):
        import inspect
        doc = inspect.getdoc(validator) or ""
        for kw in self._IMPL:
            self.assertIn(kw, doc, f"模块自述漏列已实现的关键字 {kw}")

    def test_each_keyword_actually_enforced(self):
        """每个自述关键字都真能拦下非法值（防「列了但没实现」）。"""
        cases = [
            ({"type": "string"}, 5, "type"),
            ({"enum": ["a", "b"]}, "c", "enum"),
            ({"const": "x"}, "y", "const"),
            ({"anyOf": [{"type": "integer"}, {"type": "boolean"}]}, "s", "anyOf"),
            ({"type": "string", "pattern": r"^\d+$"}, "abc", "pattern"),
            ({"type": "string", "minLength": 3}, "ab", "minLength"),
            ({"type": "string", "maxLength": 2}, "abc", "maxLength"),
            ({"type": "integer", "minimum": 5}, 1, "minimum"),
            ({"type": "integer", "maximum": 5}, 9, "maximum"),
            ({"type": "array", "items": {"type": "integer"}}, [1, "x"], "items"),
            ({"type": "array", "minItems": 2}, [1], "minItems"),
            ({"type": "array", "maxItems": 1}, [1, 2], "maxItems"),
            ({"type": "object", "properties": {"a": {"type": "integer"}},
              "required": ["a"]}, {}, "required"),
            ({"type": "object", "properties": {"a": {"type": "integer"}},
              "additionalProperties": False}, {"a": 1, "b": 2}, "additionalProperties"),
        ]
        for schema, bad, kw in cases:
            errs = validator.validate(bad, schema)
            self.assertTrue(errs, f"关键字 {kw} 应能拦下非法值 {bad!r}，实际放行")
