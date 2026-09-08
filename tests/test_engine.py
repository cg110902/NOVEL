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

from engine import checks, common, evidence, graph, state  # noqa: E402
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
class TestErrcodeRegistry(unittest.TestCase):
    def test_every_emitted_code_is_registered(self):
        src = (Path(__file__).resolve().parents[1] / "engine/checks.py").read_text(encoding="utf-8")
        emitted = set(re.findall(r'_err\(\s*"([a-z0-9_]+)"', src))
        emitted |= set(re.findall(r'add\(\s*"(?:error|warn|info)"\s*,\s*"([a-z0-9_]+)"', src))
        emitted |= set(re.findall(r'_err\(\s*\n?\s*"([a-z0-9_]+)"', src))
        missing = sorted(c for c in emitted if c not in errcodes.REGISTRY)
        self.assertEqual(missing, [], f"checks.py 产出但未注册的错误码: {missing}")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
