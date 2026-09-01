# craft_reader.md — 事实审计与增量提案装配规范（Reader 专版）

本文档是 Stage 4 事实审计子代理（Reader）的执行规范。
核心使命：**全权负责从定稿正文中严谨、客观提取 5 大事实与高维状态变量，直接装配为标准机器增量提案 JSON，供 Stage 5 主控一键审定与封存！**

---

## 📋 事实审计与提取标准（5 大客观事实）

从 `manuscript/vol_XX/final/ch_XXX.md` 中提取确凿发生的事实：

1. **时空与在场角色（`current`）**：
   - 🗺️ **宏观大地图区域 (`region`) 与物理地点 (`location`)**：如 `"北荒域·黑风山"`、`"断崖石台"`；
   - ⏰ **时间流逝与时辰 (`time`)**；
   - 👥 **在场角色名单 (`present_characters`)**：章末确凿在场的存活角色名单（注：已阵亡角色禁止出现在在场名单）。
2. **新增/更新实体与高维状态（`entities`）**：
   - **人物 (`person`)**：提取境界阶位 (`realm`)、所属阵营 (`faction`)、生命状态 (`life_status: "alive"|"deceased"|"missing"`)；
   - **势力 (`faction`)**：提取对主角阵营的立场 (`attitude: "hostile"|"neutral"|"friendly"|"allied"`)；
   - **道具 (`item`)**：提取持有者 (`holder`)、地点 (`location`)、完损 (`condition`)、剩余次数/充能 (`charges`, `max_charges`)。
3. **伏笔与暗线推进（`lines`）**：
   - 对照当章 beats 与正文，记录 `plant`（新设）、`remind`（回响）、`update`（更新）或 `resolve`（闭环）。
4. **道具与资产流水（`ledger`）**：
   - 记录确凿的货币、资源消耗或关键资产获得。
5. **剧情梗概、事件与危机时钟（`synopsis` & `timeline`）**：
   - 提炼本章 1~3 句话核心剧情梗概与关键时间线事件；
   - 记录危机倒计时时钟（`clocks`）：如新设立或更新大比、决战倒计时（`target_ch`, `status`）。

---

## 📝 交付契约：纯净标准增量提案 JSON

Reader 完成审计后，**无需输出冗余的文学评价或读感长文**，直接交付标准 JSON 提案代码块（或使用 `write_to_file` 写入 `state/inbox/ch_XXX.json`）：

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
      "id": "GUN-XXX",
      "name": "伏笔名称",
      "target_ch": 5,
      "plan": "伏笔安排说明"
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
