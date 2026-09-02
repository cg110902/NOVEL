# craft_reader.md — 事实审计与增量提案装配规范（Reader 专版）

本文档是 Stage 4 事实审计子代理（Reader）的执行规范。
核心使命：**全权负责从定稿正文中严谨、客观提取 5 大事实与高维状态变量，直接装配为标准机器增量提案 JSON，供 Stage 5 主控一键审定与封存！**

---

## 📋 事实审计与提取标准（5 大客观事实）

从 `manuscript/vol_XX/final/ch_XXX.md` 中提取确凿发生的事实：

> 🚨 **源优先级铁律**：所有事实性文字（`timeline.events` 的事件描述、`synopsis.title/text`、`lines` 的 plan 等）**逐字以定稿 final 为源**。beats 仅用于对照伏笔动作是否完成——**禁止复用 beats 措辞**（Editor 在 Stage 3 常改写场景结局，任务书版本不作数）。拿不准是否发生 → 查 final；final 没写 → 不上账。

> 📛 **章题拷贝铁律**：`synopsis.title` 必须**逐字拷贝 final 首行章题标题行**（`# 第N章 标题` 中的标题部分）；final 无标题行时留待主控补题（勿自拟，自拟会造成状态库与目录/导出三处章题失联）。

1. **时空与在场角色（`current`）——章末现场快照，12 字段刷新义务**：
   - 🗺️ **宏观大地图区域 (`region`) 与物理地点 (`location`)**：如 `"北荒域·黑风山"`、`"断崖石台"`；
   - ⏰ **时间流逝与时辰 (`time`)**；
   - 👥 **在场角色名单 (`present_characters`)**：章末确凿在场的存活角色名单（注：已阵亡角色禁止出现在在场名单）。
   - 🔄 **以下字段凡本章发生变动必刷，最常漏刷**：
     - `power_level`：境界/位阶突破或变化（如引气入体、晋阶）——**本章的核心突破事件尤其不能漏**；
     - `loadout`：主角当前常驻作战体系（主修功法、身法、招牌杀招、保命底牌）；
     - `abilities`：新习得功法/技能/能力；
     - `injury`：受伤/痊愈变化（痊愈也要写"伤势已愈"，而非留旧文）；
     - `equipment`：装备/道具的获得、消耗、移交（消失要有去向）；
     - `assets`：非资金类资产变动（**资金一律走 `ledger` 流水，勿写进 assets**）；
     - `mood` / `goal` / `key_relationships` / `situation`：心境、目标、关系、处境随剧情演进。
2. **新增/更新实体与高维状态（`entities`）**：
   - **人物 (`person`)**：提取境界阶位 (`realm`)、所属阵营 (`faction`)、生命状态 (`life_status: "alive"|"deceased"|"missing"`)、**与主角的历史恩怨备忘 (`dossier`)**；
   - **势力 (`faction`)**：提取对主角阵营的立场 (`attitude: "hostile"|"neutral"|"friendly"|"allied"`)；
   - **道具 (`item`)**：提取持有者 (`holder`)、地点 (`location`)、完损 (`condition`)、剩余次数/充能 (`charges`, `max_charges`)。
3. **伏笔与暗线推进（`lines`）**：
   - 对照当章 beats 与正文，记录 `plant`（新设）、`remind`（回响）、`update`（更新）或 `resolve`（闭环）。
4. **道具与资产流水（`ledger`）**：
   - 记录确凿的货币、资源消耗或关键资产获得——**馈赠/拾获/赌博赢输等任何所有权转移都算**；货币单位与折算口径以 bible 为准。
5. **剧情梗概、事件与危机时钟（`synopsis` & `timeline`）**：
   - 提炼本章 1~3 句话核心剧情梗概与关键时间线事件（事件描述逐字以 final 为源）；
   - 记录危机倒计时时钟（`clocks`）：如新设立或更新大比、决战倒计时（`target_ch`, `status`）。

---

## ⚙️ 工序：三段式（引文先行，防压缩惯性）

> 原理：提取是"召回型"任务，遗漏没有信号，单遍生成必然退化成压缩摘要。三段式把语义风险收敛到事实表一层，且"先拷贝后结论"让最省力的路径恰好是忠实的路径。

**第一遍·提取事实表**（落盘 `log/facts/ch_XXX.md`，逐条：先引文后结论）：

| # | 分区 | 结论（将写入提案的值） | 引文（逐字摘自 final） |
|---|---|---|---|
| 1 | current.power_level | 凡人·已引气入体… | 「灵气自百会穴涌入，引气入体，涤荡凡尘」 |

- **引文必须逐字拷贝 final 原句**（含标点）——引擎会机械校验引文是 final 的子串，编造/改写引文整案拒绝；
- 一条结论找不到引文 → 删掉这条结论（不确定就不上账的机械版）。

**第二遍·清单反扫**（补"无信号的遗漏"，逐段过 final，8 项固定清单）：
钱动了吗？境界动了吗？伤势变了吗？装备进出吗？资产变了吗？在场名单对吗？线动作（GUN/KNO/MIS）动了吗？有新实体吗？——每项答"有/无"，"有"则回填事实表。

**第三遍·照表组装**：把事实表机械搬运成提案 JSON——**只许使用事实表中已存在的条目，禁止新增**；每条变更的 `quote` 字段照抄事实表引文列。

## 📝 交付契约：纯净标准增量提案 JSON

Reader 完成审计后，**无需输出冗余的文学评价或读感长文**，直接交付标准 JSON 提案代码块（或使用 `write_to_file` 写入 `state/inbox/ch_XXX.json`）。提案交付后主控会运行 `python studio.py proposal verify ch_XXX`（0 token 机械对照）出差异候选清单，按需配合修订。

```json
{
  "schema": "novel-studio.state-mutation/v2",
  "chapter": "ch_XXX",
  "operation_id": "ch_XXX.reader.MMDD_HHMM",
  "current": {
    "present_characters": ["主角名", "在场配角名"],
    "region": "大地图区域（如北荒域）",
    "location": "章末场景地点",
    "time": "当前时辰或日期",
    "situation": "章末局势一句话速写"
  },
  "entities": [
    {
      "action": "upsert",
      "name": "新角色名",
      "type": "person",
      "realm": "练气三层",
      "faction": "青云宗",
      "life_status": "alive",
      "summary": "一句话实体简介",
      "aliases": ["别名1"]
    },
    {
      "action": "upsert",
      "name": "天雷子",
      "type": "item",
      "holder": "主角名",
      "location": "随身储物袋",
      "charges": 2,
      "max_charges": 3,
      "condition": "完好",
      "summary": "一次性大威力雷属性暗器"
    }
  ],
  "lines": [
    {
      "action": "plant",
      "kind": "foreshadow",
      "id": "GUN-001",
      "name": "伏笔名称",
      "target_ch": 5,
      "plan": "伏笔安排说明",
      "quote": "逐字摘自本章 final 的支撑句（引擎机械校验：必须是 final 的子串）"
    }
  ],
  "ledger": {
    "transactions": []
  },
  "timeline": {
    "events": [
      {
        "time": "时间锚点",
        "event": "核心事件进展描述"
      }
    ],
    "arcs": [],
    "clocks": [
      {
        "name": "宗门外门大比",
        "target_ch": 10,
        "urgency": "high",
        "desc": "若未进入前三将被剥夺内门考核资格",
        "status": "Active"
      }
    ]
  },
  "synopsis": {
    "title": "本章标题",
    "text": "本章核心剧情一句话梗概。"
  }
}
```
