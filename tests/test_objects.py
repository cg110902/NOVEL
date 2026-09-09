"""对象层（registry/envelope/derive）+ v2 加法字段 + 派生封存回归测试。"""
import json
import unittest

from tests._fixtures import TempBook


def _prop(ch="ch_001", op="ch_001.test.01", **kw):
    p = {"schema": "novel-studio.state-mutation/v2", "chapter": ch, "operation_id": op}
    p.update(kw)
    return p


class TestRegistry(unittest.TestCase):
    def test_three_key_resolve(self):
        from engine.objects import build_registry, resolve_ref
        reg = build_registry({"entries": [
            {"id": "p_001", "name": "林牧", "aliases": ["林公子"]},
            {"id": "it_001", "name": "断水剑"},
        ]})
        self.assertEqual(resolve_ref(reg, "p_001")["name"], "林牧")
        self.assertEqual(resolve_ref(reg, "林牧")["id"], "p_001")
        self.assertEqual(resolve_ref(reg, "林公子")["id"], "p_001")
        self.assertIsNone(resolve_ref(reg, "不存在"))
        self.assertIsNone(resolve_ref(reg, ""))
        self.assertEqual(reg["problems"], [])

    def test_problems_reported(self):
        from engine.objects import build_registry
        reg = build_registry({"entries": [
            {"id": "p_001", "name": "林牧", "aliases": ["公子"]},
            {"id": "p_001", "name": "赵莽", "aliases": ["公子"]},
        ]})
        codes = {p["code"] for p in reg["problems"]}
        self.assertEqual(codes, {"id_collision", "alias_multi_owner"})


class TestEnvelope(unittest.TestCase):
    def test_kind_of_id(self):
        from engine.objects import kind_of_id, to_envelope
        self.assertEqual(kind_of_id("p_001"), "person")
        self.assertEqual(kind_of_id("it_002"), "item")
        self.assertEqual(kind_of_id("GUN-001"), "foreshadow")
        self.assertEqual(kind_of_id("EVT-003"), "event")
        self.assertEqual(kind_of_id("LOCK-001"), "lock")
        self.assertEqual(kind_of_id("COG-009"), "belief")
        self.assertEqual(kind_of_id("MS-002"), "milestone")
        self.assertEqual(kind_of_id("xxx"), "unknown")
        env = to_envelope("person", {"id": "p_001", "name": "林牧"})
        self.assertEqual(set(env), {"id", "kind", "status", "asserted", "derived", "prov"})


class TestNewFieldsMerge(unittest.TestCase):
    def test_merge_and_ranges(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person",
                             "injury_level": 3, "injury_desc": "左臂骨折", "renown": 50,
                             "relations": [{"target": "赵莽", "type": "宿敌",
                                            "strength": 5, "status": "active",
                                            "since_ch": "ch_001"}]}],
                current={"time_day": 3, "pov_ref": "p_001", "place_ref": "临江城",
                         "present_refs": ["p_001"]},
                locked=[{"id": "LOCK-001", "fact": "林牧断臂", "kind": "irreversible_action",
                         "note": "红线", "refs": ["p_001"]}],
                cognition=[{"id": "COG-001", "character": "林牧", "content": "剑断了",
                            "truth_ref": "EVT-001"}],
            ))
            # place_ref 指向未登记地点 → 整体拒收（引用校验生效）
            self.assertTrue(rep["errors"], rep)
            self.assertTrue(any("place_ref" in e for e in rep["errors"]), rep["errors"])

            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.02",
                entities=[{"name": "林牧", "id": "p_001", "type": "person",
                             "injury_level": 9}],
            ))
            self.assertTrue(any("injury_level" in e for e in rep["errors"]), rep["errors"])

    def test_unknown_pred_is_advisory(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "type": "person",
                             "relations": [{"target": "赵莽", "type": "宿敌"}]}],
            ))
            self.assertEqual(rep["errors"], [])
            self.assertFalse(any("谓词" in w for w in rep["warnings"]), rep["warnings"])
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.02",
                entities=[{"name": "林牧", "type": "person",
                             "relations": [{"target": "赵莽", "type": "自创关系xyz"}]}],
            ))
            self.assertEqual(rep["errors"], [])
            self.assertTrue(any("谓词" in w for w in rep["warnings"]), rep["warnings"])

    def test_proposal_rejects_derived(self):
        from engine import state
        errs, _ = state.validate_proposal(_prop(derived={"x": 1}))
        self.assertTrue(any("派生" in e for e in errs), errs)


class TestEventsId(unittest.TestCase):
    def test_auto_id_and_revise_by_id(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(
                timeline={"events": [
                    {"time": "第一日", "event": "林牧入城",
                     "participants": ["p_001"], "place": "临江城"}]},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            evs = tb.state("timeline")["events"]
            self.assertEqual(evs[0]["id"], "EVT-001")
            self.assertEqual(evs[0]["participants"], ["p_001"])
            # 按 id 修订文本
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.02",
                timeline={"events": [{"id": "EVT-001", "replace": "林牧夜入临江城"}]},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertEqual(tb.state("timeline")["events"][0]["event"], "林牧夜入临江城")
            # 按 id 补元数据
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.03",
                timeline={"events": [{"id": "EVT-001", "time": "第一日",
                                      "event": "林牧夜入临江城", "causes": ["EVT-000"]}]},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertEqual(tb.state("timeline")["events"][0]["causes"], ["EVT-000"])
            # id 存在但文本不同且不用 replace → 拒收
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.04",
                timeline={"events": [{"id": "EVT-001", "time": "第二日", "event": "篡改"}]},
            ))
            self.assertTrue(rep["errors"])


class TestSceneRefs(unittest.TestCase):
    def test_refs_merged_and_verified(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"},
                            {"name": "临江城", "id": "loc_001", "type": "location"}],
                current={"time_day": 1, "pov_ref": "p_001", "place_ref": "loc_001",
                         "present_refs": ["p_001"]},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            cur = tb.state("current")
            self.assertEqual(cur["time_day"], 1)
            self.assertEqual(cur["present_refs"], ["p_001"])
            # 坏引用 → verify 报错
            bad = tb.state("current")
            bad["pov_ref"] = "不存在的人"
            tb.set_state("current", bad)
            self.assertTrue(any("pov_ref" in e for e in state.verify_state(tb.book)))


class TestDerivedSeal(unittest.TestCase):
    def test_compute_and_determinism(self):
        from engine import state
        from engine.objects import compute_derived, seal_derived
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧拔出断水剑，赵莽冷笑。")
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"},
                            {"name": "断水剑", "id": "it_001", "type": "item",
                             "holder": "林牧"}],
                lines=[{"kind": "foreshadow", "action": "plant", "name": "断水剑的来历",
                        "target_ch": 10}],
                current={"present_characters": ["林牧"]},
                cognition=[{"id": "COG-001", "character": "林牧",
                            "content": "剑是假的", "truth_ref": "GUN-999"}],
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            # 派生层是探测器：直接弄脏现场（模拟离线改动），derive 应指名报出
            cur = tb.state("current")
            cur["present_characters"] = ["林牧", "幽灵"]
            tb.set_state("current", cur)
            items = tb.state("items")
            items["entries"][0]["holder"] = "不存在的人"
            tb.set_state("items", items)
            d1 = compute_derived(tb.book, "ch_001")
            d2 = compute_derived(tb.book, "ch_001")
            for k in ("line_temps", "scene_violations", "holder_orphans",
                      "knowledge_flags", "stats"):
                self.assertEqual(d1[k], d2[k], k)
            self.assertEqual(len(d1["line_temps"]), 1)
            self.assertEqual(d1["line_temps"][0]["id"], "GUN-001")
            codes = {v["code"] for v in d1["scene_violations"]}
            self.assertIn("present_unregistered", codes)
            self.assertEqual(d1["holder_orphans"][0]["reason"], "unregistered")
            self.assertEqual(d1["knowledge_flags"][0]["verdict"], "unresolved")
            s = seal_derived(tb.book, "ch_001")
            self.assertEqual(s["sealed_ch"], "ch_001")
            self.assertEqual(tb.state("derived")["sealed_ch"], "ch_001")

    def test_sync_seals_derived_e2e(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧拔出断水剑。")
            proj = json.loads(tb.read("project.json"))
            proj["audit_mode"] = "off"
            tb.write("project.json", json.dumps(proj, ensure_ascii=False, indent=2))
            tb.write("state/inbox/ch_001.json", json.dumps(_prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"}],
                synopsis={"text": "林牧入城。"},
            ), ensure_ascii=False))
            rc = tb.run("sync", "ch_001")
            self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            self.assertEqual(tb.state("derived")["sealed_ch"], "ch_001")
            self.assertIn("派生已封存", rc.stdout)


class TestMigrationV4V5(unittest.TestCase):
    def test_v4_book_migrates(self):
        from engine import migrations, state
        with TempBook() as tb:
            (tb.book / "state" / "derived.json").unlink()
            stamp = json.loads(tb.read("state/state_schema.json"))
            stamp["version"] = 4
            tb.write("state/state_schema.json", json.dumps(stamp))
            tl = tb.state("timeline")
            tl["events"] = [{"time": "第一日", "event": "旧事件", "chapter": "ch_001"}]
            tb.set_state("timeline", tl)
            migrations._ENSURED.clear()
            d = state.load_state(tb.book, "derived")
            self.assertEqual(d["schema_version"], "novel-studio.derived/v1")
            evs = state.load_state(tb.book, "timeline")["events"]
            self.assertEqual(evs[0]["id"], "EVT-001")
            # 链式迁移 v4→v5→v6：终点为当前版本，四 kind 表就位
            self.assertEqual(json.loads(tb.read("state/state_schema.json"))["version"], 6)
            for _k in ("persons", "items", "factions", "places"):
                self.assertTrue((tb.book / "state" / f"{_k}.json").is_file())


class TestRecomputeCmd(unittest.TestCase):
    def test_recompute_json(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧拔剑。")
            out = tb.run_json("state", "recompute")
            self.assertTrue(out["ok"])
            self.assertEqual(out["sealed_ch"], "ch_001")


class TestPackRefs(unittest.TestCase):
    def test_present_refs_force_include(self):
        from engine import state, pack
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "风声鹤唳。")
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"}],
                current={"present_refs": ["p_001"]},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            payload = pack.build_pack(tb.book, "ch_001")
            names = [e.get("name") for e in (payload["p1"] or {}).get("entities", [])]
            self.assertIn("林牧", names)


class TestSceneViolationLevels(unittest.TestCase):
    """A4+B4：violation 分级 + present 双口径对账。"""

    def test_levels_and_mismatch(self):
        from engine import state
        from engine.objects import compute_derived
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧拔剑，赵莽冷笑。")
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"},
                            {"name": "赵莽", "id": "p_002", "type": "person"}],
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.02",
                current={"present_characters": ["林牧"], "present_refs": ["p_002"]},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            d = compute_derived(tb.book, "ch_001")
            by_code = {v["code"]: v for v in d["scene_violations"]}
            self.assertIn("present_refs_mismatch", by_code)
            mm = by_code["present_refs_mismatch"]
            self.assertEqual(mm["level"], "warning")
            self.assertIn("赵莽", mm["msg"])
            self.assertIn("林牧", mm["msg"])
            # 对齐后 mismatch 消失
            cur = tb.state("current")
            cur["present_refs"] = ["p_001"]
            tb.set_state("current", cur)
            d2 = compute_derived(tb.book, "ch_001")
            self.assertNotIn("present_refs_mismatch",
                             {v["code"] for v in d2["scene_violations"]})
            # 未登记在场是 error 级
            cur["present_characters"] = ["林牧", "幽灵"]
            tb.set_state("current", cur)
            d3 = compute_derived(tb.book, "ch_001")
            by_code3 = {v["code"]: v for v in d3["scene_violations"]}
            self.assertEqual(by_code3["present_unregistered"]["level"], "error")


class TestClosedLineTemps(unittest.TestCase):
    """B3：closed 快照 + stats 故事日/注册表问题数。"""

    def test_closed_snapshot_and_stats(self):
        from engine import state
        from engine.objects import compute_derived
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "剑的来历无人知晓。")
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"}],
                lines=[{"kind": "foreshadow", "action": "plant",
                        "name": "断水剑的来历", "target_ch": 10}],
                current={"time_day": 7},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            ln = tb.state("lines")
            ln["foreshadows"][0]["status"] = "Resolved"
            tb.set_state("lines", ln)
            d = compute_derived(tb.book, "ch_001")
            closed = [r for r in d["line_temps"] if r["temp"] == "closed"]
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0]["id"], "GUN-001")
            self.assertEqual(closed[0]["kind"], "foreshadow")
            self.assertEqual(d["stats"]["lines_closed"], 1)
            self.assertEqual(d["stats"]["lines_open"], 0)
            self.assertEqual(d["stats"]["story_day"], 7)
            self.assertIn("registry_problems", d["stats"])
            self.assertEqual(d["stats"]["registry_problems"], 0)


class TestAnticipationProbe(unittest.TestCase):
    """B2：belief.since_ch 早于真相 EVT 章 → contradicted 穿帮嫌疑。"""

    def test_belief_before_event_flagged(self):
        from engine import state
        from engine.objects import compute_derived
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧进城。")
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"}],
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            rep = state.apply_proposal(tb.book, _prop(
                ch="ch_002", op="ch_002.test.01",
                timeline={"events": [{"time": "第二日", "event": "城门大火"}]},
                cognition=[
                    {"id": "COG-001", "character": "林牧",
                     "content": "城门起了大火", "since_ch": "ch_001",
                     "quote": "火光冲天", "truth_ref": "EVT-001"},
                    {"id": "COG-002", "character": "林牧",
                     "content": "亲眼看见城门大火", "since_ch": "ch_002",
                     "quote": "亲眼所见", "truth_ref": "EVT-001"},
                ],
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            d = compute_derived(tb.book, "ch_002")
            by_cog = {f["cog_id"]: f for f in d["knowledge_flags"]}
            self.assertEqual(by_cog["COG-001"]["verdict"], "contradicted")
            self.assertIn("穿帮嫌疑", by_cog["COG-001"]["detail"])
            self.assertEqual(by_cog["COG-002"]["verdict"], "aligned")


class TestTimeDayRegression(unittest.TestCase):
    """A5：time_day 数字回退告警（warning，不阻断）。"""

    def test_regression_warns(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(current={"time_day": 5}))
            self.assertEqual(rep["errors"], [], rep["errors"])
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.02", current={"time_day": 3}))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertTrue(any("故事日回退" in w for w in rep["warnings"]),
                            rep["warnings"])
            # 前进不告警
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.03", current={"time_day": 6}))
            self.assertFalse(any("故事日回退" in w for w in rep.get("warnings", [])),
                             rep.get("warnings"))


class TestStateSetDerivedBlocked(unittest.TestCase):
    """A1：state set 禁写 derived，正常 set 不受影响。"""

    def test_set_derived_refused(self):
        with TempBook() as tb:
            rc = tb.run("state", "set", "derived.stats", "{}")
            self.assertNotEqual(rc.returncode, 0)
            self.assertIn("派生", rc.stdout + rc.stderr)
            rc = tb.run("state", "set", "current.time", "第三日·晨")
            self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            self.assertEqual(tb.state("current")["time"], "第三日·晨")


class TestStateObjectCmd(unittest.TestCase):
    """B1：state object 包络查询（实体 + 查无）。"""

    def test_object_envelope(self):
        from engine import state
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧拔出断水剑。")
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person",
                             "relations": [{"target": "赵莽", "type": "宿敌"}]},
                            {"name": "赵莽", "id": "p_002", "type": "person"},
                            {"name": "断水剑", "id": "it_001", "type": "item",
                             "holder": "林牧"}],
                current={"present_characters": ["林牧"]},
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            out = tb.run_json("state", "object", "林牧")
            self.assertTrue(out["found"])
            self.assertEqual(out["kind"], "person")
            self.assertEqual(out["derived"]["relations"][0]["target_id"], "p_002")
            self.assertIn("断水剑", out["derived"]["holds"])
            self.assertTrue(out["derived"]["present"])
            out = tb.run_json("state", "object", "p_002")
            self.assertTrue(out["found"])
            self.assertEqual(out["id"], "p_002")
            rc = tb.run("state", "object", "不存在的人")
            self.assertNotEqual(rc.returncode, 0)
            self.assertIn("未找到对象", rc.stdout + rc.stderr)


class TestLockedRefsTraceability(unittest.TestCase):
    """A2：refs 跳过 untraceable 电池 + 并入记忆提词。"""

    def test_refs_skip_battery_and_feed_memory(self):
        from engine import checks, memory, state
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧仗剑而立。")
            rep = state.apply_proposal(tb.book, _prop(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"}],
                locked=[
                    {"id": "LOCK-001", "fact": "那人终于封刀",
                     "kind": "irreversible_action", "refs": ["p_001"],
                     "note": "此后不得再出刀", "quote": "刀已封"},
                    {"id": "LOCK-002", "fact": "风停了雨住了",
                     "kind": "irreversible_action", "note": "天气已变",
                     "quote": "雨住风停"},
                ],
            ))
            self.assertEqual(rep["errors"], [], rep["errors"])
            # 电池：无 refs 的裸 fact 报警，有 refs 的跳过
            mk = lambda fact, refs: {"locked": [{"action": "plant", "id": "LOCK-X",
                                                 "fact": fact, "refs": refs}]}
            codes_bare = {i["code"] for i in
                          checks.verify_candidates(tb.book, "ch_001",
                                                   mk("那人在雨夜封刀", []))["items"]}
            self.assertIn("locked_fact_untraceable", codes_bare)
            codes_refs = {i["code"] for i in
                          checks.verify_candidates(tb.book, "ch_001",
                                                   mk("那人在雨夜封刀", ["p_001"]))["items"]}
            self.assertNotIn("locked_fact_untraceable", codes_refs)
            # 记忆：refs 提词让事实可追踪（last_seen=1），对照组 never
            rows = {r["id"]: r for r in memory.key_fact_memory(tb.book)}
            self.assertEqual(rows["LOCK-001"]["last_seen_ch"], 1)
            self.assertEqual(rows["LOCK-002"]["tier"], "never")


class TestTierParticipantsAnchor(unittest.TestCase):
    """B6：位阶探针事件锚点接受 participants（id 或名）。"""

    def _seed_shift(self, tb):
        tb.write("state/inbox/processed/ch_001.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": "ch_001.reader.t", "entities": [
                {"action": "upsert", "id": "p_002", "name": "张彪",
                 "type": "person", "tier_rank": 3, "tier_name": "炼气三层"}]},
            ensure_ascii=False))
        tb.write("state/inbox/processed/ch_002.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": "ch_002",
            "operation_id": "ch_002.reader.t", "entities": [
                {"action": "upsert", "id": "p_002", "name": "张彪",
                 "tier_rank": 6, "tier_name": "金丹境"}]}, ensure_ascii=False))
        persons = tb.state("persons")
        persons["entries"].append({"id": "p_002", "name": "张彪", "type": "person"})
        tb.set_state("persons", persons)

    def test_participants_anchor_passes(self):
        from engine import checks
        with TempBook() as tb:
            self._seed_shift(tb)
            # 事件文本不含实体名，仅 participants 挂载 → 通过
            tb.set_state("timeline", {"events": [
                {"time": "第二日", "event": "深夜雷劫降临，有人突破至金丹境",
                 "chapter": "ch_002", "participants": ["p_002"]},
            ], "arcs": []})
            out: list = []
            checks._tier_probe(tb.book, out)
            self.assertEqual(out, [])
            # 名形式同样接受
            tl = tb.state("timeline")
            tl["events"][0]["participants"] = ["张彪"]
            tb.set_state("timeline", tl)
            out = []
            checks._tier_probe(tb.book, out)
            self.assertEqual(out, [])
            # 去掉 participants → 恢复告警（旧语义不变）
            tl["events"][0].pop("participants")
            tb.set_state("timeline", tl)
            out = []
            checks._tier_probe(tb.book, out)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["code"], "tier_shift_without_event")


if __name__ == "__main__":
    unittest.main()
