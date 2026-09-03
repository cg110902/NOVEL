# craft_reader.md — 极简事实审计规范（Reader 专版）

本文档定义 Stage 4 事实审计子代理（Reader）的执行规范。
核心使命：**以极简、清晰的准则通读定稿正文，客观提取 4 大核心事实，直接装配为标准增量提案 JSON，落盘即交卷！**

> 🛑 **【原子化交付】**：单向推进，写入 `state/inbox/ch_XXX.json` 后立即汇报交卷退出，严禁在子沙箱运行测试命令。

---

## 一、 4 大核心事实提取清单（说清楚要什么，不纠缠鸡毛蒜皮）

只抓对连载长篇真正关键的事实，彻底剔除鸡毛蒜皮的琐碎闲话：

| 核心提取板块 | 对应 JSON 分区 | 明确提取要点（只记关键，不瞎编） |
|---|---|---|
| **1. 现场与主角状态** | `current` | • **在场存活名单** `present_characters`：章末确凿在场的角色名单（**已阵亡角色严禁在场**）；<br/>• **地点与时间** `location`, `time`：章末具体物理地点与当前时间锚点；<br/>• **主角核心质变**：实质突破位阶 (`power_level`)、重伤或痊愈 (`injury`)、重大招式领悟 (`abilities`)；若本章无变动则留空或维持原样。 |
| **2. 重要新实体** | `entities` | • **新登场核心角色** (`person`)、**核心重要道具/法宝** (`item`)、**新势力** (`faction`)；<br/>• 必须是有名字、有明确剧情作用的核心实体，**杂兵喽啰路人甲乙丙丁坚决不建实体**！若无新实体，直接保持 `entities: []`。 |
| **3. 核心主线伏笔** | `lines` | • 登记主线重要伏笔（`GUN-*`）、核心秘密（`KNO-*`）、重大误会（`MIS-*`）；<br/>• 标注动作：`plant` (初设)、`remind` (回响)、`resolve` (回收解开)；<br/>• **只抓主线大线索**，琐碎闲聊坚决不强插伏笔！若无变动，直接保持 `lines: []`。 |
| **4. 大额收支与梗概** | `ledger` & `synopsis` | • **大额收支 (`ledger.transactions`)**：只记大笔资金流水、重大宝物交易（买茶水买馒头等日常开销坚决不记！无大额交易直接 `[]`）；<br/>• **章题 (`synopsis.title`)**：逐字拷贝 final 首行章题标题；<br/>• **核心梗概 (`synopsis.text`)**：1~2 句话说清当章核心剧情。 |

---

## 二、 标准增量提案交付格式 (`state/inbox/ch_XXX.json`)

使用原生 `write_to_file` 工具直接写入 `state/inbox/ch_XXX.json`（设置 `Overwrite: true`）：

```json
{
  "schema": "novel-studio.state-mutation/v2",
  "chapter": "ch_XXX",
  "operation_id": "ch_XXX.reader.done",
  "current": {
    "present_characters": ["主角名", "核心在场配角名"],
    "location": "章末具体物理地点",
    "time": "当前时间锚点",
    "power_level": "突破后的最新境界/无变动则维持原样",
    "injury": "完好 或 具体伤势描述",
    "situation": "章末局势一句话速写"
  },
  "entities": [
    {
      "action": "upsert",
      "name": "新出场重要人物/新获得重要法宝",
      "type": "person",
      "status": "active",
      "faction": "所属阵营",
      "summary": "一句话核心简介"
    }
  ],
  "lines": [
    {
      "action": "plant",
      "kind": "foreshadow",
      "id": "GUN-001",
      "name": "关键伏笔线索名称",
      "target_ch": 5,
      "plan": "预期回收规划"
    }
  ],
  "ledger": {
    "transactions": []
  },
  "timeline": {
    "events": [
      {
        "time": "时间节点",
        "event": "主线关键事件推进"
      }
    ],
    "arcs": [],
    "clocks": []
  },
  "synopsis": {
    "title": "本章正文字面标题",
    "text": "1~2 句话核心情节梗概。"
  }
}
```

---

## 三、 极简工具预算 (Tool Budget ≤ 3 次)

1. 读 final 正文 (1次)；
2. 读 beats 细纲 (1次)；
3. 原生写入 `state/inbox/ch_XXX.json` (1次)；
4. 立即向主控交卷汇报（1次）。**落盘即走，绝不纠缠！**
