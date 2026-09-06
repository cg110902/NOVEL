"""tests/test_phase3_style_recall_simulate.py

Phase 3 自动化测试套件：
1. test_style_baseline_and_ai_tell_words：文风基线计算、AI 俗套词汇检测与漂移度比对
2. test_style_template_instantiation：init 命令自动实例化 bible/style.md
3. test_cmd_recall_four_ruthless_questions：知乎残酷四问 0 Token 机械自证全维度断言
4. test_cmd_simulate_impact：因果链波及测算（主角击杀警示、道具与伏笔关联）
5. test_cmd_simulate_branch：多分支走向假说沙盘生成与文件落盘隔离性验证
"""
import json
import pytest
from pathlib import Path

from engine import common, evidence, state
from engine.commands.book_setup import cmd_init
from engine.commands.recall import run_recall
from engine.commands.simulate import simulate_impact, simulate_branch


@pytest.fixture
def phase3_book(ws_root: Path) -> Path:
    book = ws_root / "test_p3_book"
    book.mkdir(parents=True, exist_ok=True)
    for d in ("bible", "characters", "outlines/vol_01/beats",
              "manuscript/vol_01/raw", "manuscript/vol_01/final",
              "state/inbox/processed", "state/inbox/failed", "state/snapshots",
              "log/review", "log/critic", "log/branches"):
        (book / d).mkdir(parents=True, exist_ok=True)

    proj = {
        "schema": "novel-studio.project/v1",
        "title": "长生仙途",
        "genre": "仙侠修真",
        "protagonist": "叶长生",
        "mode": "automatic",
        "words_target": [2000, 3000],
        "lines_cap": {
            "active_foreshadows": 8,
            "longline_foreshadows": 5,
            "active_knowledge": 5,
            "active_misunderstandings": 4
        },
        "ai_tell_words": ["嘴角微微上扬", "深吸一口气", "眼神一凝", "倒吸一口凉气"],
        "state_watch": {}
    }
    common.dump_json(book / "project.json", proj)
    state.init_state(book)

    # 填充 entities
    ents = {
        "entries": [
            {
                "name": "叶长生",
                "type": "person",
                "status": "active",
                "life_status": "alive",
                "summary": "主角，青云门外门弟子",
                "aliases": ["长生", "小叶"]
            },
            {
                "name": "青衣老者",
                "type": "person",
                "status": "retired",
                "life_status": "deceased",
                "summary": "传功长老，在第一章死于魔修暗算",
                "aliases": ["老长老"]
            },
            {
                "name": "柳如霜",
                "type": "person",
                "status": "active",
                "life_status": "alive",
                "summary": "内门师姐",
                "aliases": ["如霜"]
            },
            {
                "name": "赤炎剑",
                "type": "item",
                "status": "active",
                "holder": "柳如霜",
                "charges": 3,
                "max_charges": 5,
                "summary": "上品灵剑"
            }
        ]
    }
    state.save_state(book, "entities", ents)

    # 填充 locked
    locked = {
        "entries": [
            {
                "id": "LOCK-001",
                "kind": "death",
                "fact": "青衣老者在宗门大殿已正式咽气并下葬",
                "since_ch": "ch_001",
                "quote": "青衣老者双目合拢，气息全无。"
            },
            {
                "id": "LOCK-002",
                "kind": "rule",
                "fact": "筑基丹三年内仅开炉一次，不可补发",
                "since_ch": "ch_001",
                "quote": "丹阁长老冷言道：三年一炉，过时不候。"
            }
        ]
    }
    state.save_state(book, "locked", locked)

    # 填充 lines
    lines_data = {
        "foreshadows": [
            {
                "id": "GUN-001",
                "name": "后山石室的隐秘禁制",
                "plant_ch": 1,
                "target_ch": 2,
                "weight": 2,
                "status": "Planted",
                "plan": "柳如霜发现禁制残卷"
            },
            {
                "id": "GUN-002",
                "name": "魔宗探子的卧底密信",
                "plant_ch": 1,
                "target_ch": 5,
                "weight": 1,
                "status": "Planted",
                "requires": ["GUN-001"]
            }
        ],
        "misunderstandings": [
            {
                "id": "MIS-001",
                "parties": "叶长生、柳如霜",
                "content": "柳如霜误以为是叶长生私藏了灵药",
                "target_ch": 2,
                "level": 2,
                "status": "Active"
            }
        ],
        "knowledge": [
            {
                "id": "KNO-001",
                "secret": "叶长生身怀太古金丹残篇",
                "holders": ["叶长生"],
                "plant_ch": 1,
                "target_ch": 10,
                "status": "Concealed"
            }
        ]
    }
    state.save_state(book, "lines", lines_data)

    # 填充 cognition
    cogs = {
        "entries": [
            {
                "id": "COG-001",
                "character": "柳如霜",
                "kind": "fact",
                "content": "目睹后山有黑影掠过",
                "since_ch": "ch_001",
                "quote": "如霜掠上树梢，亲眼见黑影遁入后山。"
            },
            {
                "id": "COG-002",
                "character": "柳如霜",
                "kind": "suspicion",
                "content": "怀疑叶长生修为深藏不露",
                "since_ch": "ch_001",
                "quote": "这外门杂役的步法，竟比她还轻盈三分？"
            }
        ]
    }
    state.save_state(book, "cognition", cogs)

    # 填充 timeline
    tl = {
        "events": [],
        "arcs": [],
        "clocks": [
            {
                "name": "宗门外门大比倒计时",
                "target_ch": 3,
                "status": "Active",
                "desc": "逾期未报名者将被逐出山门"
            }
        ],
        "milestones": [
            {
                "id": "MS-001",
                "title": "破获后山禁制线索，取得柳如霜信任",
                "target_ch": 2,
                "status": "pending",
                "desc": "完成第一阶段身份反转"
            }
        ]
    }
    state.save_state(book, "timeline", tl)

    # 填充 ledger
    led = {
        "pools": {
            "spirit_stones": {
                "name": "下品灵石",
                "unit": "块",
                "current": 450,
                "initial": 500
            }
        },
        "transactions": []
    }
    state.save_state(book, "ledger", led)

    # 填充 current
    cur = {
        "time": "正德三年七月十五深夜",
        "location": "青云门外门药园",
        "present_characters": ["叶长生", "柳如霜"],
        "injury": "内息略有震荡，皮肉轻伤",
        "situation": "后山黑影遁走，药园药草失窃，外门戒严",
        "goal": "洗清嫌疑，顺藤摸瓜排查禁制",
        "active_pressures": ["三日后大比报名截止", "执法堂戒严随时搜身"]
    }
    state.save_state(book, "current", cur)

    # 写入两章定稿
    ch1_text = """# 第1章 药园惊变，黑影遁空

夜雨滂沱，青云门外门药园的篱笆被狂风撕开一道大口子。
叶长生握着药铲，站在雨幕中，冷眼看着那道黑影掠向后山。
柳如霜提剑飞身而至，目光锐利：“是谁在药园？”
“弟子叶长生，方才见有人潜入后山。”叶长生沉声应答，将药铲立在身旁。
柳如霜扫视四周，见药架七零八落，脸色微微发沉：“宗门大比在即，执法堂随时会搜查此地，你好自为之。”
"""
    (book / "manuscript" / "vol_01" / "final" / "ch_001.md").write_text(ch1_text, encoding="utf-8")

    ch2_text = """# 第2章 禁制微澜，各怀心思

清晨雾气迷蒙，后山禁制石门前落满枯叶。
叶长生嘴角微微上扬，深吸一口气，眼神一凝，看着石门缝隙中渗出的幽光。
柳如霜倒吸一口凉气：“这禁制竟被动过！”
叶长生心中暗叹，此女虽然警惕，却不知真正的危机早已在脚下蔓延。
两人各怀心思，石门缓缓轰鸣开启。
"""
    (book / "manuscript" / "vol_01" / "final" / "ch_002.md").write_text(ch2_text, encoding="utf-8")

    return book


def test_style_baseline_and_ai_tell_words(phase3_book: Path):
    """测试文风基线计算与 AI 俗套词汇检测。"""
    st = evidence.style(phase3_book, "ch_002")
    assert st["kind"] == "style"
    assert st["chapter"] == "vol_01/ch_002"

    stats = st["stats"]
    assert stats["cjk"] > 100
    assert stats["ai_tell_total"] == 4  # 命中：嘴角微微上扬、深吸一口气、眼神一凝、倒吸一口凉气
    assert len(stats["ai_tell_hits"]) == 4

    hits_words = {h["word"] for h in stats["ai_tell_hits"]}
    assert "嘴角微微上扬" in hits_words
    assert "深吸一口气" in hits_words
    assert "眼神一凝" in hits_words
    assert "倒吸一口凉气" in hits_words

    # 验证漂移计算
    drift = st["drift"]
    assert "len_mean_delta" in drift
    assert "dialogue_ratio_delta" in drift
    assert drift["ai_tell_total"] == 4
    assert drift["ai_tell_density"] > 0


def test_style_template_instantiation(ws_root: Path, monkeypatch: pytest.MonkeyPatch):
    """测试 studio init 时正确实例化 bible/style.md 模板。"""
    monkeypatch.setenv("NOVEL_STUDIO_WORKSPACE_ROOT", str(ws_root))
    target = ws_root / "new_book"
    class Args:
        workspace = str(target)
        title = "星际修仙指南"
        genre = "科幻修仙"
        protagonist = "韩立"
        clean = False
        deep = False
        force = False

    ret = cmd_init(Args)
    assert ret == 0
    style_path = target / "bible" / "style.md"
    assert style_path.is_file()

    content = style_path.read_text(encoding="utf-8")
    assert "《星际修仙指南》文风与语感基线" in content
    assert "叙事视角与人称（POV）" in content
    assert "禁用词表与 AI 味黑名单" in content


def test_cmd_recall_four_ruthless_questions(phase3_book: Path):
    """测试知乎残酷四问 0 Token 机械自证全维度断言。"""
    recall_data = run_recall(phase3_book, "ch_002")
    assert recall_data["kind"] == "recall"
    assert recall_data["chapter"] == "ch_002"
    assert recall_data["next_chapter"] == "ch_003"

    # 问 1：主要人物认知
    cog = recall_data["character_cognition"]
    assert "叶长生" in cog
    assert "柳如霜" in cog

    # 叶长生持有太古金丹机密
    ycs_secrets = [s["id"] for s in cog["叶长生"]["secrets_held"]]
    assert "KNO-001" in ycs_secrets
    assert len(cog["叶长生"]["unknown_secrets_boundary"]) == 0

    # 柳如霜不应知晓太古金丹机密，必须被列入知情红线
    lrs_unknown = [u["id"] for u in cog["柳如霜"]["unknown_secrets_boundary"]]
    assert "KNO-001" in lrs_unknown
    # 柳如霜确知黑影与心中疑窦
    assert any("黑影" in f["content"] for f in cog["柳如霜"]["known_facts"])
    assert any("深藏不露" in sp["content"] for sp in cog["柳如霜"]["suspicions"])

    # 问 2：绝对不可违背的不可逆事实
    irrev = recall_data["irreversible_facts"]
    assert len(irrev["locked_rules_and_events"]) == 2
    assert irrev["locked_rules_and_events"][0]["id"] == "LOCK-001"
    # 青衣老者已阵亡
    assert any(dc["name"] == "青衣老者" for dc in irrev["deceased_characters"])

    # 问 3：未兑现伏笔
    lines = recall_data["pending_lines"]
    assert any(f["id"] == "GUN-001" for f in lines["foreshadows"])
    assert any(m["id"] == "MIS-001" for m in lines["misunderstandings"])
    assert any(c["name"] == "宗门外门大比倒计时" for c in lines["clocks"])
    assert any(ms["id"] == "MS-001" for ms in lines["milestones"])

    # 问 4：下一章红线边界
    bound = recall_data["next_chapter_boundaries"]
    assert bound["target_chapter"] == "ch_003"
    assert any("青衣老者" in fb for fb in bound["strictly_forbidden"])
    assert any("KNO" in fb or "机密" in fb for fb in bound["strictly_forbidden"])
    assert "spirit_stones" in bound["allowed_and_encouraged"]["available_resources"]


def test_cmd_simulate_impact(phase3_book: Path):
    """测试因果链波及测算功能。"""
    # 1. 模拟击杀主角：必须发出致命警告
    res_protagonist = simulate_impact(phase3_book, entity="叶长生", action="kill")
    assert any("主角" in w and "瓦解" in w for w in res_protagonist["warnings"])
    assert any(al["id"] == "KNO-001" for al in res_protagonist["affected_lines"])

    # 2. 模拟击杀关键配角柳如霜：核查道具与伏笔波及
    res_lrs = simulate_impact(phase3_book, entity="柳如霜", action="kill")
    assert len(res_lrs["warnings"]) == 0
    # 赤炎剑是柳如霜携带，将变为无主物
    assert any(it["name"] == "赤炎剑" for it in res_lrs["affected_items"])
    # 涉及伏笔与误会
    assert any(al["id"] in ("GUN-001", "MIS-001") for al in res_lrs["affected_lines"])
    # 涉及主线里程碑 MS-001
    assert any(ms["id"] == "MS-001" for ms in res_lrs["affected_milestones"])

    # 3. 模拟线索解决：解锁后置因果链 (GUN-002 requires GUN-001)
    res_line = simulate_impact(phase3_book, line_id="GUN-001", action="resolve")
    assert any(ul["id"] == "GUN-002" for ul in res_line["unblocked_lines"])


def test_cmd_simulate_branch(phase3_book: Path):
    """测试多分支沙盘走向生成与文件落盘隔离性。"""
    # 生成 3 条假说分支并写入
    res = simulate_branch(phase3_book, ch="ch_002", count=3, write=True)
    assert res["kind"] == "simulate_branch"
    assert res["anchor_chapter"] == "ch_002"
    assert res["next_chapter"] == "ch_003"
    assert res["branches_count"] == 3
    assert len(res["branches"]) == 3

    # 验证落盘文件
    branch_file = phase3_book / "log" / "branches" / "ch_003.md"
    assert branch_file.is_file()
    text = branch_file.read_text(encoding="utf-8")
    assert "走向 A：激进摊牌" in text
    assert "走向 B：暗流迂回" in text
    assert "走向 C：意外变数" in text
    assert "【绝不写入正史】" in text

    # 验证正史状态零污染
    cur_st = state.load_state(phase3_book, "current")
    assert cur_st["location"] == "青云门外门药园"  # current 状态保持原状，未被修改
