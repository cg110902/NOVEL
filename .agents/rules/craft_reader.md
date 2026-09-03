# craft_reader.md — 事实审计与增量提案装配规范（Reader 专版）

本文档定义 Stage 4 事实审计子代理（Reader）的执行规范。
核心使命：**全权负责从定稿正文中客观提取 5 大事实与高维状态变量，直接装配为标准机器增量提案 JSON，供 Stage 5 主控一键核验与封存！**

---

## 一、 事实审计核心原则（防吃书红线）

1. **源优先级铁律（定稿唯一真值）**：
   - 一切事实性文字（`timeline.events`、`synopsis.text`、`lines` 的动作等）**逐字以定稿 final 为源**；
   - beats 仅用于对照伏笔动作意图，**严禁照抄 beats 措辞**（Editor 往往在 Stage 3 调整了具体对话和现场结果）；
   - 正文没写的事实坚决不上账！
2. **章题逐字拷贝铁律**：
   - `synopsis.title` **必须逐字拷贝 final 首行章题标题行**（`# 第N章 标题` 中的标题部分）；final 若无标题则留空待主控补齐，绝不自拟。
3. **引文接地铁律（0-Token 物理质检）**：
   - 每一条变动（尤其是伏笔与关键事件）必须内嵌 `quote` 字段，**逐字摘自 final 原句（含标点）**。引擎会进行子串与 90% 局部相似度硬校验，编造引文整案阻断。
4. **精益提案直装（零中间草稿）**：
   - **无需生成 `log/facts/*.md` 等中间草稿**，思维反扫后直接一步到位装配落盘 `state/inbox/ch_XXX.json`，立省 2000+ Token。
5. **极简工具预算 (Tool Budget ≤ 4 次)**：
   - 读 final (1次) → 读 beats (1次) → 原生写入 `state/inbox/ch_XXX.json` (1次) → 汇报 (1次)；
   - **严禁在子沙箱运行 `proposal check/verify` 或 `sync` 命令**，所有校验统一由主控在 Stage 5 处理。

---

## 二、 5 大客观事实提取标准

| 事实板块 | 对应状态机分区 | 审计与提取要点 |
|---|---|---|
| **1. 现场快照** | `current` | • 空间：大地图区域 `region`、物理场景 `location`；<br/>• 时间：时间流逝 `time`；<br/>• 在场名单：章末确凿在场的存活角色 `present_characters`（**已阵亡角色严禁在场**）；<br/>• 核心状态必刷：`power_level` (突破/晋升/位阶)、`loadout` (常驻手段与底牌)、`abilities` (新能力)、`injury` (伤势/痊愈)、`equipment` (随身核心装备)、`assets` (非资金资产)。 |
| **2. 实体异动** | `entities` | • 提取新出场人物 (`person`)、关键道具 (`item`)、势力组织 (`faction`)、特殊场景 (`place`)；<br/>• 标注人物阵营、境界/阶位、生死状态 (`life_status: "alive"|"deceased"`)、**与主角恩怨备忘 (`dossier`)**；<br/>• 标注道具持有者 (`holder`)、存放位置 (`location`)、充能与耐久 (`charges`, `condition`)。 |
| **3. 伏笔暗线** | `lines` | • 登记重要伏笔（`GUN-*`）、秘密/情报（`KNO-*`）、认知差/误会（`MIS-*`）；<br/>• 标注生命周期动作：`plant` (初设)、`remind` (回响)、`update` (状态更新)、`escalate` (误会升级)、`resolve` (回收解开)；附带支撑 `quote`。 |
| **4. 资源流水** | `ledger` | • 记录确凿的货币、积分、筹码或硬通货收支流水 (`transactions`)；<br/>• 包含资金池 `pool`、数额变动 `delta`（收入为正/支出为负）、事由 `subject`、对手方 `counterparty`；纯非资金资产登记在 `current.assets`。 |
| **5. 梗概与时钟** | `synopsis`<br/>& `timeline` | • `synopsis.title`: 逐字拷贝 final 首行标题；<br/>• `synopsis.text`: 本章 1~3 句话核心事件梗概；<br/>• `timeline.events`: 宏观主线事件节点；<br/>• `timeline.clocks`: 危机/决战倒计时（目标章、紧迫度、当前状态）。 |

---

## 三、 标准增量提案交付格式 (`state/inbox/ch_XXX.json`)

使用原生 `write_to_file` 工具直接写入 `state/inbox/ch_XXX.json`（设置 `Overwrite: true`）：

```json
{
  "schema": "novel-studio.state-mutation/v2",
  "chapter": "ch_XXX",
  "operation_id": "ch_XXX.reader.0903_2000",
  "current": {
    "present_characters": ["主角名", "配角名"],
    "region": "大地理区域/星区/城市",
    "location": "章末具体物理地点",
    "time": "当前时间锚点",
    "power_level": "当前最新位阶/职级/战力标签",
    "injury": "完好 或 具体伤势进展",
    "situation": "章末局势一句话速写"
  },
  "entities": [
    {
      "action": "upsert",
      "name": "实体全名",
      "type": "person",
      "status": "active",
      "realm": "位阶/阶位",
      "faction": "所属势力",
      "life_status": "alive",
      "summary": "一句话核心简介",
      "aliases": ["常用简称/绰号"]
    },
    {
      "action": "upsert",
      "name": "关键道具名",
      "type": "item",
      "status": "active",
      "holder": "主角名",
      "location": "随身携带",
      "charges": 2,
      "max_charges": 3,
      "condition": "完好",
      "summary": "道具功能与特征"
    }
  ],
  "lines": [
    {
      "action": "plant",
      "kind": "foreshadow",
      "id": "GUN-001",
      "name": "伏笔线索名称",
      "target_ch": 5,
      "plan": "预期回收与爆发规划",
      "quote": "逐字摘自本章 final 正文的物理支撑句"
    }
  ],
  "ledger": {
    "transactions": [
      {
        "pool": "standard_currency",
        "delta": -500,
        "subject": "采购急救药品与干粮",
        "counterparty": "回春堂掌柜",
        "quote": "逐字摘自本章 final 关于花销付钱的原句"
      }
    ]
  },
  "timeline": {
    "events": [
      {
        "time": "时间节点",
        "event": "主线事件进展描述"
      }
    ],
    "arcs": [],
    "clocks": [
      {
        "name": "核心危机/考核倒计时",
        "target_ch": 10,
        "urgency": "high",
        "desc": "期限到达若未达成目标的严重后果",
        "status": "Active"
      }
    ]
  },
  "synopsis": {
    "title": "本章正文字面标题",
    "text": "本章 1~3 句话核心情节梗概。"
  }
}
```
*注：交付后向主控汇报即可，严禁在提案之外输出冗长长篇大论。*
