"""R4 v3 寻址式提案：编译严格性 / 类型推断·搬迁 / 全表落地 /
v2·v3 等价 / inbox sync e2e / 位阶探针重放 / 骨架有效性。
"""
import json
import unittest

from tests._fixtures import TempBook


def _v3(ch="ch_001", op="ch_001.test.v3", ops=(), **kw):
    p = {"schema": "novel-studio.state-mutation/v3", "chapter": ch,
         "operation_id": op, "ops": list(ops)}
    p.update(kw)
    return p


def _seed_person(tb, eid="p_001", name="林牧", **kw):
    from engine import state
    e = {"id": eid, "name": name, "type": "person"}
    e.update(kw)
    rep = state.apply_proposal(tb.book, {
        "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
        "operation_id": f"seed.{eid}", "entities": [dict(e, action="upsert")]})
    assert rep["errors"] == [], rep["errors"]
    return e


class TestV3Strictness(unittest.TestCase):
    def test_table_literal_matches_asserted_keys(self):
        # V3OpModel.table 与 state.ASSERTED_KEYS 刻意重复（防循环导入），漂移即失败
        from engine import state
        from engine.models.patch import V3OpModel
        lit = set(V3OpModel.model_fields["table"].annotation.__args__)
        self.assertEqual(lit, set(state.ASSERTED_KEYS))

    def test_create_duplicate_id_rejected(self):
        from engine import state
        with TempBook() as tb:
            _seed_person(tb)
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "persons", "action": "create",
                 "entry": {"id": "p_001", "name": "冒名者"}}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("[op#0", rep["errors"][0])
            self.assertIn("已存在", rep["errors"][0])

    def test_create_duplicate_name_rejected(self):
        from engine import state
        with TempBook() as tb:
            _seed_person(tb)
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "persons", "action": "create",
                 "entry": {"id": "p_999", "name": "林牧"}}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("重名", rep["errors"][0])

    def test_update_unknown_id_rejected(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "persons", "action": "update", "id": "p_404",
                 "set": {"summary": "幽灵"}}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("未登记", rep["errors"][0])

    def test_update_wrong_table_rejected(self):
        from engine import state
        with TempBook() as tb:
            _seed_person(tb)
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "items", "action": "update", "id": "p_001",
                 "set": {"summary": "表错位"}}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("地址表错", rep["errors"][0])

    def test_retire_unknown_id_rejected(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "places", "action": "retire", "id": "loc_404"}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("无可退役", rep["errors"][0])

    def test_mixed_v2_section_rejected(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _v3(
                ops=[{"table": "current", "action": "update",
                      "set": {"location": "临江城"}}],
                entities=[{"action": "upsert", "name": "混写者"}]))
            self.assertTrue(rep["errors"], rep)

    def test_update_set_name_forbidden(self):
        from engine import state
        with TempBook() as tb:
            _seed_person(tb)
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "persons", "action": "update", "id": "p_001",
                 "set": {"name": "林大侠"}}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("手术刀", rep["errors"][0])

    def test_current_duplicate_set_key_rejected(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "current", "action": "update", "set": {"location": "甲"}},
                {"table": "current", "action": "update", "set": {"location": "乙"}}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("重复 set", rep["errors"][0])


class TestV3InferenceAndMove(unittest.TestCase):
    def test_create_type_inferred_from_table(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "items", "action": "create",
                 "entry": {"id": "it_001", "name": "断水剑"}}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            got = tb.state("items")["entries"][0]
            self.assertEqual(got["type"], "item")

    def test_create_type_table_mismatch_rejected(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "items", "action": "create",
                 "entry": {"id": "p_002", "name": "张彪", "type": "person"}}]))
            self.assertTrue(rep["errors"], rep)
            self.assertIn("不一致", rep["errors"][0])

    def test_update_type_change_moves_with_warning(self):
        from engine import state
        with TempBook() as tb:
            _seed_person(tb, eid="p_007", name="石像")
            rep = state.apply_proposal(tb.book, _v3(ops=[
                {"table": "persons", "action": "update", "id": "p_007",
                 "set": {"type": "item"}}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertTrue(any("搬迁" in w for w in rep["warnings"]),
                            rep["warnings"])
            self.assertEqual(tb.state("persons")["entries"], [])
            self.assertEqual(tb.state("items")["entries"][0]["name"], "石像")


class TestV3AllTablesLand(unittest.TestCase):
    def test_all_tables_land(self):
        from engine import state
        with TempBook() as tb:
            _seed_person(tb)
            ops = [
                {"table": "current", "action": "update",
                 "set": {"location": "临江城"}},
                {"table": "persons", "action": "create",
                 "entry": {"id": "p_002", "name": "张彪"}},
                {"table": "items", "action": "create",
                 "entry": {"id": "it_001", "name": "断水剑", "holder": "林牧"}},
                {"table": "factions", "action": "create",
                 "entry": {"id": "f_001", "name": "青云门"}},
                {"table": "places", "action": "create",
                 "entry": {"id": "loc_001", "name": "临江城"}},
                {"table": "persons", "action": "update", "id": "p_001",
                 "set": {"summary": "灯铺少主"}},
                {"table": "lines", "action": "plant", "kind": "foreshadow",
                 "id": "GUN-001", "name": "断刀来历", "target_ch": 30},
                {"table": "timeline", "action": "append_event",
                 "event": {"id": "EVT-001", "time": "正午", "event": "林牧拔刀"}},
                {"table": "timeline", "action": "append_clock",
                 "clock": {"name": "灯债", "target_ch": 9}},
                {"table": "timeline", "action": "append_arc",
                 "arc": {"name": "复仇线"}},
                {"table": "timeline", "action": "append_milestone",
                 "milestone": {"id": "MS-001", "title": "夺刀", "target_ch": 5,
                               "status": "pending", "desc": ""}},
                {"table": "ledger", "action": "declare_pool",
                 "pool": "stone", "spec": {"name": "灵石", "unit": "块",
                                           "initial": 100}},
                {"table": "ledger", "action": "append_transaction",
                 "entry": {"chapter": "ch_001", "pool": "stone", "delta": -30,
                           "type": "expense", "subject": "买刀"}},
                {"table": "locked", "action": "plant", "id": "LOCK-001",
                 "fact": "林牧之刀断于江边", "kind": "destruction",
                 "note": "断刀不可复原", "quote": "咔嚓一声"},
                {"table": "cognition", "action": "plant", "character": "张彪",
                 "content": "他知道刀已断裂", "kind": "fact", "quote": "刀断了"},
                {"table": "synopsis", "action": "set", "title": "第一章 拔刀",
                 "text": "林牧拔刀，刀断。"},
            ]
            rep = state.apply_proposal(tb.book, _v3(ops=ops))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertEqual(tb.state("current")["location"], "临江城")
            self.assertEqual(len(tb.state("persons")["entries"]), 2)
            self.assertEqual(tb.state("items")["entries"][0]["holder"], "林牧")
            self.assertEqual(tb.state("factions")["entries"][0]["name"], "青云门")
            self.assertEqual(tb.state("places")["entries"][0]["name"], "临江城")
            self.assertEqual(tb.state("lines")["foreshadows"][0]["id"], "GUN-001")
            tl = tb.state("timeline")
            self.assertEqual(tl["events"][0]["id"], "EVT-001")
            self.assertEqual(tl["clocks"][0]["name"], "灯债")
            self.assertEqual(tl["arcs"][0]["name"], "复仇线")
            self.assertEqual(tl["milestones"][0]["id"], "MS-001")
            led = tb.state("ledger")
            self.assertIn("stone", led["pools"])
            self.assertEqual(led["transactions"][-1]["subject"], "买刀")
            self.assertEqual(tb.state("locked")["entries"][0]["id"], "LOCK-001")
            cog = tb.state("cognition")["entries"]
            self.assertEqual(len(cog), 1)
            self.assertTrue(cog[0]["id"].startswith("COG-"))
            self.assertEqual(
                tb.state("synopsis")["chapters"]["ch_001"]["title"], "第一章 拔刀")

    def test_revise_event_op(self):
        from engine import state
        with TempBook() as tb:
            seed = state.apply_proposal(tb.book, _v3(op="ch_001.test.seed", ops=[
                {"table": "timeline", "action": "append_event",
                 "event": {"id": "EVT-009", "time": "夜", "event": "旧描述"}}]))
            self.assertEqual(seed["errors"], [], seed["errors"])
            rep = state.apply_proposal(tb.book, _v3(op="ch_001.test.revise", ops=[
                {"table": "timeline", "action": "revise_event",
                 "id": "EVT-009", "replace": "新描述"}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertEqual(tb.state("timeline")["events"][0]["event"], "新描述")


class TestV3Equivalence(unittest.TestCase):
    def test_v2_v3_same_end_state(self):
        from engine import state
        v2 = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
              "operation_id": "eq.v2",
              "current": {"location": "临江城"},
              "entities": [
                  {"action": "upsert", "id": "p_001", "name": "林牧",
                   "type": "person", "summary": "灯铺少主"},
                  {"action": "upsert", "id": "it_001", "name": "断水剑",
                   "type": "item", "holder": "林牧"}],
              "timeline": {"events": [{"time": "正午", "event": "林牧拔刀"}]},
              "ledger": {"pools": {"stone": {"name": "灵石", "unit": "块",
                                             "initial": 100}},
                         "transactions": [
                             {"chapter": "ch_001", "pool": "stone", "delta": -30,
                              "type": "expense", "subject": "买刀"}]},
              "synopsis": {"title": "第一章", "text": "拔刀。"}}
        v3ops = [
            {"table": "current", "action": "update", "set": {"location": "临江城"}},
            {"table": "persons", "action": "create",
             "entry": {"id": "p_001", "name": "林牧", "type": "person",
                       "summary": "灯铺少主"}},
            {"table": "items", "action": "create",
             "entry": {"id": "it_001", "name": "断水剑", "holder": "林牧"}},
            {"table": "timeline", "action": "append_event",
             "event": {"time": "正午", "event": "林牧拔刀"}},
            {"table": "ledger", "action": "declare_pool", "pool": "stone",
             "spec": {"name": "灵石", "unit": "块", "initial": 100}},
            {"table": "ledger", "action": "append_transaction",
             "entry": {"chapter": "ch_001", "pool": "stone", "delta": -30,
                       "type": "expense", "subject": "买刀"}},
            {"table": "synopsis", "action": "set", "title": "第一章",
             "text": "拔刀。"},
        ]
        with TempBook() as a, TempBook() as b:
            ra = state.apply_proposal(a.book, v2)
            rb = state.apply_proposal(b.book, _v3(op="eq.v3", ops=v3ops))
            self.assertEqual(ra["errors"], [], ra["errors"])
            self.assertEqual(rb["errors"], [], rb["errors"])
            for key in state.STATE_KEYS:
                if key == "derived":
                    continue  # 派生表含时间戳/哈希指纹，逐键比对
                self.assertEqual(a.state(key), b.state(key),
                                 f"表 {key} v2/v3 终态不一致")

    def test_idempotency_by_raw_bytes(self):
        # 幂等按 v3 原文：同文件重提干净跳过；同效异写如实报存在性错误
        from engine import state
        with TempBook() as tb:
            entry = {"id": "p_001", "name": "林牧", "type": "person"}
            mk = lambda op, e=entry: _v3(op=op, ops=[
                {"table": "persons", "action": "create", "entry": dict(e)}])
            r1 = state.apply_proposal(tb.book, mk("w.first"))
            self.assertEqual(r1["errors"], [], r1["errors"])
            r2 = state.apply_proposal(tb.book, mk("w.retry"))
            self.assertEqual(r2["errors"], [], r2["errors"])
            self.assertTrue(r2.get("duplicate"), r2)
            r3 = state.apply_proposal(tb.book, mk("w.respell",
                                                  {k: v for k, v in entry.items()
                                                   if k != "type"}))
            self.assertTrue(r3["errors"], r3)
            self.assertIn("已存在", r3["errors"][0])


class TestV3SyncE2E(unittest.TestCase):
    def test_inbox_sync_v3(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧推门进屋，屋里点着一盏灯。" * 30)
            tb.write("log/audit/ch_001.md",
                     "---\nhard: 0\nadjudicated: false\n---\n\n# 仲裁报告\n\n机械探针零命中。\n")
            tb.write("state/inbox/ch_001.json", json.dumps(_v3(
                op="ch_001.e2e.01", ops=[
                    {"table": "persons", "action": "create",
                     "entry": {"id": "p_001", "name": "林牧"}},
                    {"table": "current", "action": "update",
                     "set": {"location": "临江城"}}]), ensure_ascii=False))
            out = tb.run_json("sync", "ch_001")
            self.assertTrue(out.get("snapshot", {}).get("ok"), out)
            self.assertEqual(tb.state("persons")["entries"][0]["name"], "林牧")
            self.assertTrue((tb.book / "state/inbox/processed/ch_001.json").is_file())

    def test_proposal_check_v3(self):
        with TempBook() as tb:
            tb.write("state/inbox/ch_001.json", json.dumps(_v3(
                op="ch_001.chk.01", ops=[
                    {"table": "persons", "action": "update", "id": "p_404",
                     "set": {"summary": "幽灵"}}]), ensure_ascii=False))
            out = tb.run_json("proposal", "check", "ch_001")
            self.assertFalse(out.get("ok"), out)
            self.assertIn("未登记", json.dumps(out, ensure_ascii=False))


class TestV3TierProbeReplay(unittest.TestCase):
    def test_v3_shift_without_event_warns(self):
        from engine import checks
        with TempBook() as tb:
            _seed_person(tb, eid="p_002", name="张彪",
                         tier_rank=3, tier_name="炼气三层")
            tb.write("state/inbox/processed/ch_001.json", json.dumps(_v3(
                op="ch_001.reader.t", ops=[
                    {"table": "persons", "action": "create",
                     "entry": {"id": "p_002", "name": "张彪",
                               "tier_rank": 3, "tier_name": "炼气三层"}}]),
                ensure_ascii=False))
            tb.write("state/inbox/processed/ch_005.json", json.dumps(_v3(
                ch="ch_005", op="ch_005.reader.t", ops=[
                    {"table": "persons", "action": "update", "id": "p_002",
                     "set": {"tier_rank": 6, "tier_name": "金丹境"}}]),
                ensure_ascii=False))
            out: list = []
            checks._tier_probe(tb.book, out)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["code"], "tier_shift_without_event")
            self.assertIn("张彪", out[0]["msg"])


class TestV3Skeleton(unittest.TestCase):
    def test_new_v3_skeleton_shape(self):
        with TempBook() as tb:
            proc = tb.run("proposal", "new", "ch_007", "--v3")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            skel = json.loads(proc.stdout)
            self.assertEqual(skel["schema"], "novel-studio.state-mutation/v3")
            self.assertEqual(skel["chapter"], "ch_007")
            self.assertTrue(skel["operation_id"])
            self.assertEqual(skel["ops"], [])

    def test_skeleton_one_step_from_valid(self):
        from engine import state
        with TempBook() as tb:
            proc = tb.run("proposal", "new", "ch_007", "--v3")
            skel = json.loads(proc.stdout)
            errs, _ = state.validate_proposal(skel, "ch_007", book=tb.book)
            self.assertEqual(len(errs), 1, errs)  # 仅空 ops 一条
            skel["ops"].append(
                {"table": "current", "action": "update",
                 "set": {"location": "临江城"}})
            rep = state.apply_proposal(tb.book, skel)
            self.assertEqual(rep["errors"], [], rep["errors"])


class TestV3VerifyPreamble(unittest.TestCase):
    def test_as_v2_proposal_compiles(self):
        from engine import checks
        with TempBook() as tb:
            _seed_person(tb)
            v2 = checks._as_v2_proposal(tb.book, _v3(ops=[
                {"table": "persons", "action": "update", "id": "p_001",
                 "set": {"summary": "灯铺少主"}},
                {"table": "ledger", "action": "declare_pool", "pool": "stone",
                 "spec": {"name": "灵石", "unit": "块", "initial": 0}}]))
            self.assertEqual(v2["schema"], "novel-studio.state-mutation/v2")
            self.assertEqual(v2["entities"][0]["name"], "林牧")
            self.assertIn("stone", v2["ledger"]["pools"])

    def test_as_v2_proposal_falls_back_on_bad_compile(self):
        from engine import checks
        with TempBook() as tb:
            bad = _v3(ops=[{"table": "persons", "action": "update",
                             "id": "p_404", "set": {"summary": "幽灵"}}])
            self.assertIs(checks._as_v2_proposal(tb.book, bad), bad)


if __name__ == "__main__":
    unittest.main()
