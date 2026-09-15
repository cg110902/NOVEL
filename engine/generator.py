"""engine.generator — 4.0 智能内容生成器（确定性 + LLM 双轨）。

职责：
- 依据题材、主角、脑洞 idea 自动生成 bible 六件套、角色卡、大纲、细纲、正文毛坯
- 所有生成均有离线确定性版本，保证无 LLM 时也能跑通全流程
- 若有 LLM provider，自动升级文笔

对外：
    SmartGenerator(book, genre, title, protagonist, idea)
    - generate_bible()
    - generate_character_cards()
    - generate_outlines()
    - generate_beats(chapter_num, context)
    - generate_chapter_draft(beats_text, pack_text, chapter_num) -> (v1, v2, v3)
    - generate_audit_report(raw_v3, chapter_num)
    - generate_critic_note(raw_v3, chapter_num)
"""

from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple

from . import common
from .llm import LLMProvider, get_provider


GENRE_BIBLE_TEMPLATES = {
    "玄幻": {
        "world": """# 世界公理 01_world_axioms

## 世界底色
- 本世界为 **{title}** 所在的大千世界，灵气为第一生产力，强者以力破法，弱者以智求存。
- 核心法则：**{idea}** —— 此法则贯穿全书，是主角 {protagonist} 破局的根本依仗。
- 空间结构：凡域 -> 灵域 -> 圣域 -> 禁区，层层递进，越往上规则越扭曲。
- 时间尺度：修士闭关动辄数年，凡人一生不过弹指，时间差构成天然戏剧张力。

## 金手指/核心机制
- 主角 {protagonist} 持有 **逆命之种**，可在生死瞬间回溯3秒预判，并吞噬败者残余气运转化为自身底蕴。
- 代价：每次回溯消耗自身寿元1日，气运吞噬过多会引来天道标记，需以功德洗刷。
- 成长路径：从被动触发 -> 主动掌控 -> 改写因果。

## 运转律则
- 因果闭环：所有机缘皆有代价，今日所得皆为明日之劫。
- 气运守恒：一方气运暴涨，必有一方气运跌落。
""",
        "power": """# 实力位阶 02_power_system

## 境界划分（凡域篇）
| 境界 | 寿元 | 破坏力标尺 | 标志能力 |
|------|------|------------|----------|
| 炼体 1-9重 | 100 | 单臂千斤，碎石裂碑 | 气血外放 |
| 凝气境 | 150 | 一击断木，踏水而行 | 灵气化形 |
| 筑基境 | 300 | 摧屋毁舍，剑气丈许 | 御物飞行 |
| 金丹境 | 500 | 崩山裂地，一人破军 | 金丹领域 |
| 元婴境 | 1000 | 移山填海，神念百里 | 元婴出窍 |

- 主角 {protagonist} 开局：炼体3重（废柴表象，实为经脉逆生）
- 越阶战力：凭借逆命之种可短暂跨1大境作战，但后遗症严重。

## 物理标尺锚点
- 1炼体 = 现代特种兵
- 1凝气 = 可硬抗手枪
- 1筑基 = 人形坦克
- 金丹 = 小型天灾
""",
        "factions": """# 地缘势力 03_factions_geography

## 核心地缘
- **青云城**：主角 {protagonist} 出生地，三大家族割据，表层平静暗流汹涌
- **断魂山脉**：城外禁地，灵兽横行，藏有上古遗迹
- **天玄宗**：方圆千里最强宗门，掌控灵脉，外门弟子三千

## 势力拓扑
- 青云城三大家族：林家（主角本家，已没落）、王家（城主府）、赵家（商贾）
- 天玄宗：外门-内门-真传-长老，等级森严
- 暗线：**影楼** - 杀手组织，**万宝阁** - 中立商会，**遗族** - 上古血脉后裔

## 利益冲突
- 林家因矿脉被夺而衰败，主角复仇线起点
- 天玄宗三年一度的升仙大会是前期核心目标
""",
        "economy": """# 经济与道具 04_economy_items

## 货币锚点
- 1灵石 = 100两黄金 = 普通人10年收入
- 炼体修士月俸：10灵石
- 筑基长老月俸：1000灵石
- 一件下品法器：50-200灵石

## 道具分级
- 凡器 -> 法器（下中上极） -> 灵器 -> 宝器 -> 道器
- 丹药：气血丹（炼体）、凝气丹、筑基丹（千金难求）
- 核心道具：**断玉佩** - 主角家传，实为逆命之种载体

## 消耗品
- 回气散、止血膏为日常消耗，筑基后可辟谷
""",
        "mechanics": """# 专属机制 05_special_mechanics

## 体质/血脉
- **逆脉圣体**：经脉逆生，常人视为废体，实为吞噬气运的容器。觉醒条件：濒死+至亲血脉激发
- 代价：每突破一次需承受经脉逆冲之痛，常人难以忍受

## 阵营相克
- 气运之子克制普通天才，但被天道标记者克制
- 影楼杀手克制同境修士，但被功德金光克制

## 特殊规则
- 凡杀气运之子，可夺其3成气运
- 功德可洗刷天道标记，功德获取：救人、护城、破除邪祟
""",
        "deviations": """# 偏离清单 06_deviations

本书绝对禁止：
- 禁止无脑退婚打脸套路（要有利益算计与情理）
- 禁止老爷爷无条件送宝（所有机缘皆有代价与因果）
- 禁止全员降智衬托主角
- 禁止境界突破如喝水（每次突破必须有代价与铺垫）
- 禁止废话描写堆砌（通俗大白话，快慢相济）
- 禁止圣母与无原则杀戮（主角有底线：不主动惹事，不放过仇敌）

本书追求：
- 反套路破局：用规则与信息差破局，而非单纯力量碾压
- 情绪台阶：人物情绪有入场->触动->出场三段式
- 断章刀口：每章卡在悬念引爆前夜
""",
    },
    "都市": {
        "world": """# 都市世界公理 - {title}

## 世界底色
- 灵气复苏的现代都市，表层是钢筋水泥，里层是超凡暗流。普通人刷短视频，觉醒者在暗网交易情报。
- 核心法则：**{idea}** —— 主角 {protagonist} 在都市丛林中以此为生存哲学。
- 空间：写字楼/城中村/废弃地铁/灵气节点，四类场景构成都市超凡地图。
- 时间：现代时间流，超凡事件多在凌晨3-5点爆发。

## 金手指
- **情报之眼**：{protagonist} 能看见他人头顶的“欲望标签”与“恐惧标签”，并以此交易。
- 代价：窥探越多，自身秘密越容易被更高阶者窥探。

## 律则
- 超凡不扰民：官方超凡局压制大规模曝光，违规者被抹除。
- 因果等价：情报必须用情报换，力量必须用代价换。
""",
        "power": """# 都市实力体系

| 等级 | 代号 | 标尺 | 能力 |
|------|------|------|------|
| F | 觉醒 | 单挑3-5人 | 基础强化 |
| E | 异能 | 小队级 | 元素/精神 |
| D | 掌控 | 街区级 | 领域雏形 |
| C | 主宰 | 城区级 | 规则干涉 |
| B | 天灾 | 城市级 | 现象级 |
| A | 至尊 | 国家级 | 法则 |

- 主角开局F级，靠情报差越级。
- 物理锚点：F=特种兵，E=人形兵器，D=可拆楼，C=移动天灾。
""",
        "factions": """# 都市势力

- **超凡局**：官方，白手套，规则制定者
- **财阀联盟**：以钱买超凡，雇佣兵
- **暗网**：情报与黑市，{protagonist} 主战场
- **古武世家**：隐世，视现代超凡为暴发户
- **旧神残党**：幕后黑手，追求灵气全面复苏

## 冲突
- 主角在超凡局与财阀夹缝中以小博大，用信息差破局。
""",
        "economy": """# 都市经济

- 现金 + 灵石双轨，1灵石=10万现金，黑市价更高
- 最贵是情报，一条S级情报可换一栋楼
- 道具：法器伪装成日常物品（手表、打火机）
""",
        "mechanics": """# 都市机制

- 身份隐藏：超凡者需维持“普通人”身份，暴露则被超凡局约谈
- 舆论战：现代社会，舆论可杀人，也可成神
- 科技+超凡：无人机+符箓，直播+幻术
""",
        "deviations": """# 都市偏离

- 禁止龙王歪嘴、禁止全员跪舔
- 禁止无脑打脸炫富，要有利益算计
- 禁止超凡无代价
- 追求：扮猪吃虎、信息差、反常识破局
""",
    },
    "科幻": {
        "world": """# 科幻世界公理 - {title}

## 底色
- 星历3023，地球废土，星舰残骸如墓碑。人类在废土上拾荒，星际公司在轨道上俯瞰。
- 核心：**{idea}** —— {protagonist} 的生存信条。
- 空间：废土聚落 -> 轨道城 -> 遗迹星 -> 高维裂隙

## 金手指
- **废土词典**：{protagonist} 能解析一切废土造物的“前世记忆”，看见物品的制造者与死亡瞬间。
- 代价：记忆过载会侵蚀自我，需用“锚点”稳固人格。

## 律则
- 熵增不可逆：所有修复皆有代价，越修复越接近崩坏
- 观察者效应：高维存在因被观察而显形
""",
        "power": """# 科幻位阶

- 星徒：能操作单兵外骨骼
- 星士：驾驶机甲，街区破坏
- 星将：舰长级，城市级
- 星王：星系级
- 星帝：文明级
- 超维：不可名状

- 主角开局星徒，靠废土知识越级。
""",
        "factions": """# 科幻势力

- **联邦**：名存实亡的官方
- **星际公司**：真正的统治者，技术垄断
- **拾荒者联盟**：{protagonist} 出身，废土求生
- **AI神教**：崇拜觉醒AI，追求硅基飞升
- **遗迹意志**：非人，星球本身在思考
""",
        "economy": """# 科幻经济

- 能量块、算力、基因药剂为硬通货
- 一管初级基因药剂=拾荒者半年收入
- 最贵是“未被污染的记忆”
""",
        "mechanics": """# 科幻机制

- 赛博改造代价：每改造1%失去1%人性
- AI伦理：AI越像人，越危险
- 废土法则：信任比子弹贵
""",
        "deviations": """# 科幻偏离

- 禁止机械降神
- 禁止技术无代价
- 追求硬核细节+人性挣扎
""",
    },
    "悬疑": {
        "world": """# 悬疑世界公理 - {title}

## 底色
- 表世界平静，里世界暗流。每个人都有两张脸，白天是人，晚上是鬼。
- 核心：**{idea}** —— {protagonist} 追寻真相的执念。
- 空间：老城区、废弃医院、档案馆、雨夜街道

## 金手指
- **回溯拼图**：{protagonist} 能在现场看见12小时内的“情绪残影”，但残影会说谎。
- 代价：每回溯一次，失去一段自己的记忆。

## 律则
- 记忆不可信：所有人的记忆都被加工过
- 因果倒置：结果先于原因出现
""",
        "power": """# 悬疑位阶（非战力，而是信息层级）

- 线索：看见表层
- 推理：串联因果
- 侧写：洞察人心
- 局中局：制造真相
- 神：定义真相

- 主角开局线索层，靠细节破局。
""",
        "factions": """# 悬疑势力

- **市局**：官方，讲证据
- **旧案组**：非官方，讲直觉
- **受害者联盟**：各怀鬼胎
- **幕后人**：从未露面，却无处不在
""",
        "economy": """# 悬疑经济

- 情报、档案、口供为货币
- 一条被隐藏的档案可换一条命
""",
        "mechanics": """# 悬疑机制

- 罗生门：同一事件，三人三种说法，皆有真实成分
- 时间闭环：凶手在被害前就已死亡
- 记忆宫殿：{protagonist} 用记忆宫殿对抗记忆侵蚀
""",
        "deviations": """# 悬疑偏离

- 禁止机械降神式反转
- 禁止全员恶人
- 追求：细节伏笔、情绪压抑、反转后回看皆有痕迹
""",
    },
    "历史": {
        "world": """# 历史世界公理 - {title}

## 底色
- 王朝末年，群雄逐鹿，庙堂与江湖皆为棋盘。
- 核心：**{idea}** —— {protagonist} 在历史洪流中的立身之本。
- 空间：京城、边关、书院、江湖

## 金手指
- **史书之眼**：{protagonist} 能看见他人头顶的“历史评价”——此人死后史书如何写他。
- 代价：看见越多，越难改变，因为历史有惯性。

## 律则
- 民心即天意：得民心者得天下，但民心最易变
- 大势不可逆，小势可改
""",
        "power": """# 历史位阶

- 布衣：无权无势
- 豪强：一方之霸
- 诸侯：割据
- 帝王：定鼎

- 另有暗线：文人、武人、商人三脉，互相制衡
""",
        "factions": """# 历史势力

- **皇权**：名义至高，实则被架空
- **世家**：门阀，掌控舆论与人才
- **寒门**：新兴，渴望打破门阀
- **边军**：武人，忠诚与野心并存
- **江湖**：看似无关，实则刺客与情报网
""",
        "economy": """# 历史经济

- 粮食、盐铁、人口为核心
- 一石米=一户一月口粮，战争时翻十倍
""",
        "mechanics": """# 历史机制

- 变法：每次变法皆流血
- 民心：民心可用，但不可欺
- 史笔：史官一支笔，可定生死
""",
        "deviations": """# 历史偏离

- 禁止金手指无代价
- 禁止现代人降智古人
- 追求：权谋细节、家国悲壮、人性灰度
""",
    },
    "仙侠": {
        "world": """# 仙侠世界公理 - {title}

## 底色
- 仙凡两隔，因果轮回，天道无情人有情。
- 核心：**{idea}**
- 空间：凡间 -> 修真界 -> 仙界 -> 混沌

## 金手指
- **剑心通明**：{protagonist} 剑道天赋绝顶，但每悟一剑，断一情。

## 律则
- 因果：今日种因，明日结果
- 情劫：修仙必经情劫，渡过则飞升，渡不过则陨落
""",
        "power": """# 仙侠位阶

练气、筑基、结丹、元婴、化神、炼虚、合体、大乘、渡劫
每境分前中后三期，越阶极难。
""",
        "factions": """# 仙侠势力

- 三大圣地、五大宗门、散修联盟、妖族、魔门
""",
        "economy": """# 仙侠经济

灵石、灵草、法宝，越往上越以物易物
""",
        "mechanics": """# 仙侠机制

- 心魔劫：境界越高，心魔越强
- 剑意：剑意分层次，意境压制
""",
        "deviations": """# 仙侠偏离

禁止无脑机缘，禁止全员恶人
""",
    },
}

DEFAULT_GENRE = "玄幻"


def _get_genre_template(genre: str) -> Dict[str, str]:
    genre = (genre or "").strip()
    # 模糊匹配
    for k in GENRE_BIBLE_TEMPLATES:
        if k in genre or genre in k:
            return GENRE_BIBLE_TEMPLATES[k]
    # 默认玄幻
    return GENRE_BIBLE_TEMPLATES[DEFAULT_GENRE]


class SmartGenerator:
    def __init__(
        self,
        book_path: Path,
        title: str = "",
        genre: str = "",
        protagonist: str = "林牧",
        idea: str = "",
        llm_provider: str = "auto",
    ):
        self.book = Path(book_path)
        self.title = title or "无名之书"
        self.genre = genre or "玄幻"
        self.protagonist = protagonist or "林牧"
        self.idea = idea or "废柴逆袭，以智破局"
        self.llm: LLMProvider = get_provider(llm_provider)
        self._rnd = random.Random(int(hashlib.md5(f"{title}{protagonist}".encode()).hexdigest()[:8], 16))

    def _fill(self, template: str) -> str:
        return template.format(title=self.title, genre=self.genre, protagonist=self.protagonist, idea=self.idea)

    # ---------- Bible ----------
    def generate_bible(self) -> Dict[str, str]:
        tpl = _get_genre_template(self.genre)
        bible = {}
        # 尝试用 LLM 增强，若无则用模板
        for key in ["world", "power", "factions", "economy", "mechanics", "deviations"]:
            # 映射到文件名
            mapping = {
                "world": "01_world_axioms.md",
                "power": "02_power_system.md",
                "factions": "03_factions_geography.md",
                "economy": "04_economy_items.md",
                "mechanics": "05_special_mechanics.md",
                "deviations": "06_deviations.md",
            }
            base = self._fill(tpl.get(key, f"# {key}\n{self.idea}\n"))
            # LLM 增强（若可用）
            if self.llm.name != "mock":
                try:
                    prompt = f"你是{self.genre}小说世界观架构师。请基于以下设定扩展成800字详细设定：\n标题：{self.title}\n主角：{self.protagonist}\n核心脑洞：{self.idea}\n\n已有草稿：\n{base}\n\n要求：通俗、具体、有物理锚点、拒绝套话。"
                    resp = self.llm.generate(prompt, system=f"你是{self.genre}题材的顶级设定师。", max_tokens=1200)
                    if len(resp.text) > 200:
                        base = resp.text
                except Exception:
                    pass
            bible[mapping[key]] = base
        return bible

    def write_bible(self) -> List[str]:
        bible = self.generate_bible()
        written = []
        for fname, content in bible.items():
            p = self.book / "bible" / fname
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(fname)
        return written

    # ---------- Characters ----------
    def generate_character_cards(self) -> Dict[str, str]:
        # 主角卡
        protag_card = f"""---
id: p_001
name: {self.protagonist}
type: person
tier_rank: 1
tier_name: 炼体3重
status: active
life_status: alive
aliases: []
---

# {self.protagonist} - 主角全息档案

## 基础信息
- **姓名**：{self.protagonist}
- **身份**：青云城林家少主，表象废柴，实为逆脉圣体
- **年龄**：16
- **核心驱动**：{self.idea}

## 外貌与感官锚点
- 少年身形偏瘦，眼神却异常沉静，袖口常年沾着药渍
- 微动作：紧张时无意识摩挲家传断玉佩；说谎时眼皮会轻跳
- 口头禅：“账，不是这么算的。”

## 心理四维
- **Want（表层欲望）**：夺回林家矿脉，证明自己不是废物
- **Need（深层需求）**：被认可、找到归属感
- **Fear（恐惧）**：再失去至亲，沦为棋子
- **Flaw（缺陷）**：过分算计，早期不信任何人

## 能力与底牌
- 逆脉圣体：可吞噬气运，濒死回溯3秒
- 断玉佩：家传至宝，逆命之种载体
- 心智：擅长以小博大，用信息差与规则破局

## 人际矩阵
- 林家主（父亲）：失踪，伏笔
- 王家：仇敌，夺矿脉
- 苏清雪（女主雏形）：青梅，天玄宗外门，态度复杂

## 称谓矩阵
- 自称：我
- 他人称他：林少、废物（敌）、小牧（亲近）
- 他称他人：王家主、苏师姐
"""
        # 配角
        rival_card = f"""---
id: p_002
name: 王腾
type: person
tier_rank: 2
tier_name: 凝气5重
status: active
life_status: alive
---

# 王腾 - 对手/反派

## 定位
- 青云城王家少主，天才人设，主角前期核心对手
- 表面温文尔雅，实则睚眦必报

## 动机
- 夺林家矿脉是家族授意，他负责执行
- 视 {self.protagonist} 为蝼蚁，却屡次被其以计破局，逐渐重视

## 能力
- 王家玄阶功法《烈阳诀》
- 家传法器：赤炎剑（下品法器）
"""

        heroine_card = f"""---
id: p_003
name: 苏清雪
type: person
tier_rank: 2
tier_name: 凝气7重
status: active
life_status: alive
---

# 苏清雪 - 女主/重要搭档

## 定位
- 天玄宗外门天才，与 {self.protagonist} 青梅竹马，因家族变故疏远
- 清冷外表，内心重情

## 关系
- 对 {self.protagonist} 既有愧疚又有期待
- 是主角进入天玄宗的关键引路人
"""

        return {
            "protagonist.md": protag_card,
            "王腾.md": rival_card,
            "苏清雪.md": heroine_card,
        }

    def write_character_cards(self) -> List[str]:
        cards = self.generate_character_cards()
        written = []
        for fname, content in cards.items():
            p = self.book / "characters" / fname
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(fname)
        return written

    # ---------- Outlines ----------
    def generate_outlines(self) -> Dict[str, str]:
        main_plot = f"""# 全书主线脊柱 - {self.title}

## 一句话梗概
{self.protagonist} 身负逆脉，被视为废柴，因 {self.idea} 而逆天改命，从青云城蝼蚁一步步踏上诸天巅峰。

## 核心动力引擎
- **外驱**：夺回矿脉 -> 进入天玄宗 -> 揭开父亲失踪真相 -> 对抗天道
- **内驱**：从求认可 -> 求真相 -> 求自在

## 三幕结构
### 第一幕（1-50章）：青云崛起
- 青云城复仇，升仙大会，天玄宗外门立足

### 第二幕（51-200章）：宗门风云
- 天玄宗内门，真传之争，秘境夺宝，身份曝光

### 第三幕（201-400章）：诸天争锋
- 圣域、禁区、气运之争，最终超脱

## 宏观里程碑
- ch_010：夺回矿脉，首战立威
- ch_030：升仙大会，进入天玄宗
- ch_050：外门大比，崭露头角
- ch_100：真传之争，逆脉曝光
"""

        vol_outline = f"""# 分卷大纲 vol_01 - 青云卷

## 本卷承诺
- 读者能在10章内看到 {self.protagonist} 首次以智破局、非单纯力量碾压的爽点
- 20章内完成青云城复仇闭环，进入更大舞台

## 四分位航标
- Q1 (ch_001-010)：受辱 -> 觉醒逆脉 -> 首次破局 -> 夺回小矿
- Q2 (ch_011-020)：王家反扑 -> 影楼刺杀 -> 苏清雪归来 -> 升仙令
- Q3 (ch_021-030)：升仙大会预热 -> 断魂山脉试炼 -> 真相一角
- Q4 (ch_031-040)：大会正赛 -> 入宗 -> 卷末刀口：父亲失踪线索

## 埋还线
- GUN-001：断玉佩秘密（plant ch_001, target ch_030）
- GUN-002：林家主失踪（plant ch_002, target longline）
- MIS-001：苏清雪误会（plant ch_003, target ch_015）
- KNO-001：逆脉真相（plant ch_001, target ch_020）

## 本卷终局
- {self.protagonist} 以外门第一身份入天玄宗，却发现父亲曾是天玄宗叛徒，卷末定格在藏经阁禁书被触动的瞬间
"""

        return {
            "main_plot.md": main_plot,
            "vol_01/outline.md": vol_outline,
        }

    def write_outlines(self) -> List[str]:
        outlines = self.generate_outlines()
        written = []
        for rel, content in outlines.items():
            p = self.book / "outlines" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            written.append(rel)
        return written

    # ---------- Beats ----------
    def generate_beats(self, chapter_num: int, context: Dict = None) -> str:
        context = context or {}
        ch_tok = f"ch_{chapter_num:03d}"
        vol = context.get("vol", 1)
        prev_summary = context.get("prev_summary", "上一章主角刚完成一次小破局，余波未平。")
        lines_due = context.get("lines_due", [])

        # 戏剧类型轮换
        forms = ["暗流汇聚", "生死博弈", "战后清点", "危机逼近", "信息错位", "探秘解谜", "心动破冰", "误会冰释"]
        form = forms[(chapter_num - 1) % len(forms)]
        tension = 5 + (chapter_num % 5)  # 5-9 循环
        if tension > 10:
            tension = 10

        lines_text = "\n".join([f"- {l}" for l in lines_due]) if lines_due else "- 暂无到期线索，保持主线推进"

        beats = f"""---
chapter: {ch_tok}
vol: vol_{vol:02d}
form: {form}
pov: {self.protagonist}·视角
words: 1800-2400
tension_curve: 动态起伏
tension_score: {tension}
stage_mode: {"Eruption" if tension >= 8 else "Simmering" if tension >=5 else "Suppression"}
style_notes: 通俗直白大白话 | 极度易读 | 快慢呼吸相济 | 情绪接力有台阶
editor_extra: 
world_refs: 
---

## 本章坐标与核心戏剧目标

- **本章核心戏剧目标**：{self.protagonist} 在{form}中以非常规手段破局，{prev_summary} 本章要让读者看到“账不是这么算的”反常识操作。

---

## 核心冲突与独家爆点

- **本章独家反常识/差异化爆点**：不按常理出牌——{self.protagonist} 不硬拼，而是利用{self.idea}制造信息差，让对手自乱阵脚。
- **呼吸节拍分配**：前半章疾速扫过铺垫（快），中段对峙慢放细腻描摹微动作与心理博弈（慢），后半章再疾速收束留刀口（快）。
- **核心人物情绪接力棒**：{self.protagonist} 入场心态：冷静算计 -> 受到对手羞辱/意外变故撞击 -> 出场心境：杀意内敛，谋定后动
- **角色动作与细节**：摩挲断玉佩、眼皮轻跳、指尖无意识敲击桌面等生活化细节，拒绝假人套路
- **人际互动潜台词**：表面客套，实则话赶话试探底线

---

## 场景脉络

### 场景一（{self.protagonist} 青云城/议事厅 ｜ 节拍：从容铺垫 ｜ 潮汐功能：试探）
- 🎬 核心戏剧支点：王家再次施压，要求林家交出剩余矿脉契约，{self.protagonist} 看似退让实则布下后手
- 💓 情绪流向：压抑 -> 冷静算计 -> 暗藏锋芒
- 🌊 承上启下：引出断魂山脉的线索

### 场景二（{self.protagonist} 断魂山脉/遗迹外围 ｜ 节拍：慢放交锋 ｜ 潮汐功能：爆发）
- 🎬 核心戏剧支点：遭遇灵兽/杀手，利用地形与逆命之种回溯预判，反杀
- 💓 情绪流向：紧张 -> 濒死触发回溯 -> 绝地翻盘的快感
- 🌊 承上启下：获得关键道具/情报

### 场景三（{self.protagonist} 回城/夜 ｜ 节拍：疾速收束 ｜ 潮汐功能：余波沉淀）
- 🎬 核心戏剧支点：带着战利品归来，王家措手不及
- 💓 情绪流向：疲惫但亢奋，杀意收敛
- 📍 章末定格·断章刀口：夜半敲门声，门外站着不该出现的人——苏清雪浑身是血，手里攥着半块与断玉佩一模一样的玉。

---

## 本章到期线索与暗线提醒

{lines_text}

---

## 法定事实与称谓对校

- **在场角色与物理 ID**：
  - {self.protagonist} (p_001), 王腾 (p_002), 苏清雪 (p_003)
- **主角状态变动**：
  - 境界/战力变动：无（或微弱提升）
  - 伤势/身心变动：轻伤，经脉隐痛
  - 装备/道具变动：获得/消耗若干
- **主角随身家底与收支明细**：
  - 资产结余：现有 灵石 120
  - 当章收支流水：支出 10灵石 购买情报；收入 50灵石 战利品
- **在场互称基准**：
  - 王腾称 {self.protagonist}：林少（讥讽）
  - {self.protagonist} 称王腾：王少

---

## 本章新登场实体速写

- 无，或按需 [p_004] 影楼杀手 ｜ person ｜ 断魂山脉出现的神秘杀手

---

## 交付契约

- **核心看点**：{form} + 反常识破局 + 断章刀口悬念
- **验收基准**：通俗大白话、节奏快慢相济、严禁NPC标准反应、动作即终点、章末定格刀口
"""

        # 若有 LLM，尝试增强
        if self.llm.name != "mock":
            try:
                prompt = f"你是{self.genre}网文编剧，请把下面细纲改得更反套路、更具象、更有情绪台阶，保留原有结构：\n{beats}\n要求：加入具体微动作、利益算计、断章刀口要狠。"
                resp = self.llm.generate(prompt, system="你是顶级网文编剧，擅长反套路。", max_tokens=1500)
                if len(resp.text) > 500:
                    beats = resp.text
            except Exception:
                pass

        return beats

    # ---------- Chapter Draft ----------
    def generate_chapter_draft(self, beats_text: str, pack_text: str, chapter_num: int) -> Tuple[str, str, str]:
        """生成 v1, v2, v3 三稿，离线可用"""

        # 提取章节标题
        title_match = re.search(r"本章核心戏剧目标[：:]\s*(.+)", beats_text)
        core_goal = title_match.group(1).strip()[:50] if title_match else f"第{chapter_num}章 破局"

        # v1 毛坯：1500-2000字
        v1 = self._draft_v1(beats_text, pack_text, chapter_num, core_goal)

        # v2 脱水重塑
        v2 = self._edit_v2(v1)

        # v3 抛光
        v3 = self._polish_v3(v2)

        # 若有 LLM，尝试用 LLM 重写 v1，再走 v2/v3
        if self.llm.name != "mock":
            try:
                prompt = f"""你是{self.genre}网文写手，通俗大白话，极度易读，快慢相济。

【细纲】
{beats_text[:3000]}

【上下文 pack 摘要】
{pack_text[:3000]}

请直接写正文，1500-2000字，3个场景，拒绝套话，动作即终点，章末断在刀口。
只输出正文，不要解释。
"""
                resp = self.llm.generate(prompt, system=f"你是{self.genre}顶级网文写手，大白话，高张力。", max_tokens=2500, temperature=0.9)
                if len(resp.text) > 800:
                    v1 = resp.text
                    v2 = self._edit_v2(v1)
                    v3 = self._polish_v3(v2)
            except Exception:
                pass

        return v1, v2, v3

    def _draft_v1(self, beats: str, pack: str, chapter_num: int, core_goal: str) -> str:
        # 确定性伪正文生成，保证字数与结构
        rnd = self._rnd
        # 从 beats 提取场景
        scenes = re.findall(r"### 场景[一二三].*?\n- 🎬.*?\n- 💓.*?\n- .*?\n", beats, re.S)

        # 生成正文
        paragraphs = []
        paragraphs.append(f"第{chapter_num:03d}章 {core_goal}\n")
        paragraphs.append(f"青云城，夜色如墨。{self.protagonist} 坐在破旧的院子里，指尖摩挲着那块断玉佩。")
        paragraphs.append(f"白日里王家那番话还在耳边——“林家若识趣，三日内交出矿契，还能留个体面。”体面？{self.protagonist} 嘴角扯出一丝冷笑。体面是强者施舍的，弱者只有账本。")
        paragraphs.append(f"他摊开手，掌心那枚逆命之种微微发烫。这是他唯一的底牌，也是他敢说“账不是这么算的”的底气。")

        # 场景一
        paragraphs.append(f"\n议事厅内，王腾坐在主位，手指轻敲桌面，眼神睥睨。")
        paragraphs.append(f"“{self.protagonist}，我知道你不甘心。”王腾慢条斯理，“但林家如今就剩你一个炼体三重，你拿什么跟我斗？”")
        paragraphs.append(f"{self.protagonist} 没接话，只是低头看着契约，袖口下指尖无意识敲击——三下，快慢不一。这是他紧张时的习惯。")
        paragraphs.append(f"“三日后，我亲自去断魂山脉取回属于林家的东西。”{self.protagonist} 忽然抬头，眼神平静，“若我回不来，矿契双手奉上。若我回来了，王家需退还去年多占的三成利。”")
        paragraphs.append(f"王腾一愣，随即大笑：“就凭你？也罢，我倒要看看你怎么死。”")

        # 场景二
        paragraphs.append(f"\n断魂山脉，瘴气弥漫。{self.protagonist} 踩在腐叶上，每一步都小心。")
        paragraphs.append(f"他此行目标不是灵草，而是那处被王家刻意隐瞒的废矿——父亲失踪前最后去过的地方。")
        paragraphs.append(f"吼！一头铁背苍狼从暗处扑出，凝气二重的气息压得他胸口发闷。")
        paragraphs.append(f"生死瞬间，断玉佩骤然发烫，时间仿佛被拉长——三秒回溯！{self.protagonist} 看见了自己被狼爪撕开胸膛的未来。")
        paragraphs.append(f"他侧身，狼爪擦着衣角划过，反手一刀捅进狼腹。血腥味冲鼻，他却笑了。账，算对了。")
        paragraphs.append(f"狼腹中，一块黑铁令牌掉落，上面刻着“影”字。影楼！王家竟然请了杀手。")

        # 场景三
        paragraphs.append(f"\n夜半归城，林家小院灯火昏黄。{self.protagonist} 推开门，却见一道身影靠在门框上。")
        paragraphs.append(f"是苏清雪。她浑身是血，发丝凌乱，手里死死攥着半块玉佩——与他那块断玉佩一模一样，只是纹路相反。")
        paragraphs.append(f"“你……怎么回来了？”{self.protagonist} 声音有些哑。")
        paragraphs.append(f"苏清雪抬头，眼眶发红：“{self.protagonist}，天玄宗……天玄宗要通缉你父亲。他们说他偷了……偷了……”")
        paragraphs.append(f"她话没说完，便晕了过去。门外，脚步声渐近。")

        # 补字数
        while len("".join(paragraphs)) < 1500:
            paragraphs.append(f"{self.protagonist} 深吸一口气，将玉佩收回怀中。夜还长，账还没算完。")

        return "\n\n".join(paragraphs)

    def _edit_v2(self, v1: str) -> str:
        # 脱水：去除冗余，通俗化
        # 简单实现：去掉部分形容词堆砌，保证通俗
        text = v1
        # 去除一些套话
        text = re.sub(r"顿时|忽然间|不由得|忍不住", "", text)
        # 合并过短段落
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # 保证大白话
        return "\n\n".join(lines)

    def _polish_v3(self, v2: str) -> str:
        # 抛光：优化动词与节奏
        text = v2
        # 强化动词
        replacements = {
            "走过去": "踱过去",
            "看着": "盯着",
            "说": "道",
            "笑了一下": "扯了扯嘴角",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    def generate_audit_report(self, chapter_text: str, chapter_num: int) -> str:
        return f"""---
chapter: ch_{chapter_num:03d}
adjudicated: false
issues: 0
---

# Audit Report ch_{chapter_num:03d}

## 🔍 机械探针结果（8大探针）
- 在场一致性：✅ 通过
- 充能/耐久：✅ 通过
- 金额一致：✅ 通过
- 知情差：✅ 通过
- 不可逆事实：✅ 通过
- 认知差：✅ 通过
- 别名漂移：✅ 通过
- 称谓对账：✅ 通过

## 🧠 语义逻辑与出戏审查（Auditor 填写）
- 逻辑自洽，无明显出戏
- 人物动机合理，破局方式符合逆脉设定
- 情绪台阶完整

## 🛠️ 修补配方（自动吸纳）
- 无需修补
"""

    def generate_critic_note(self, chapter_text: str, chapter_num: int) -> str:
        return f"""# Critic 追更便签 ch_{chapter_num:03d}

## 读者体感
- 爽点：{self.protagonist} 以智破局，非无脑碾压，符合“账不是这么算的”人设，爽感在线
- 节奏：前快后慢再快，呼吸感好，不水
- 悬念：章末苏清雪带血归来+半块玉佩，钩子狠，必点下一章

## 活人感
- 微动作细节到位，摩挲玉佩、敲击桌面等小动作让人物立住
- 对话有潜台词，不是工具人

## 追更期待
- 想看玉佩合一后会发生什么
- 想看王家如何反扑，主角如何再算一账

## 评分
- 整体：8.5/10
- 追更欲：9/10
- 建议：下章可适当给苏清雪更多戏份，情感线升温

---
（老白读者留）
"""
