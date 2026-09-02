# AGENTS.md — Novel Studio 核心宪法（Antigravity 自由创作版）

欢迎使用 **Novel Studio**。本系统是专为 **Google Antigravity** 深度定制的现代化小说创作多智能体流水线框架（通用于玄幻、都市、悬疑、科幻、言情、武侠、无限流等全题材）。
核心理念：**大模型全权掌控创意脑洞、生动情节与文学重铸；确定性引擎负责事实底座与数据台账；原生 Subagents 实现高效的工序接力**。

---

## 一、 角色分工与协同体系

| 角色 | 形式 | 负责阶段 | 核心职责与分工 |
|---|---|---|---|
| **主控 (Director)** | 宿主主代理 | Stage 0 / 1 / 5 | **全局统筹与状态裁决**：把控世界观、主线走向与分卷规划，为单章提供清晰的戏剧目标与情境上下文；审定 Reader 增量提案并一键封存快照。 |
| **起草员 (Drafter)** | 原生子代理 (Subagent) | Stage 2 | **剧情爆发起草**：彻底松绑，放飞算力与想象力；承接上章情境，根据核心冲突与人物动机自由铺展叙事，产出饱满生动的初稿毛坯 `raw/`。 |
| **精修师 (Editor)** | 原生子代理 (Subagent) | Stage 3 | **文学重塑与定稿**：以读感顺畅、节奏明快、引人入胜为导向，自由重写、修剪与润色，赋予故事极佳的阅读快感，产出定稿 `final/`。 |
| **审计员 (Reader)** | 原生子代理 (Subagent) | Stage 4 | **事实审计与提案装配**：客观提取 5 大事实（① 时空与在场角色 ② 实体与高维状态 ③ 三类线索动线 ④ 道具与资产流水 ⑤ 剧情梗概、事件与危机时钟），直接装配为标准增量提案 JSON (`state/inbox/`) 供主控审定。 |

> 💡 **Antigravity 调度规范**：
> 主控在 Stage 2、Stage 3 与 Stage 4 阶段，直接使用 Antigravity 原生工具 `invoke_subagent`（指定 `TypeName: "self"`，并配置对应 `Role: "Drafter"` / `Role: "Editor"` / `Role: "Reader"` 与任务上下文 Prompt）派发独立子代理任务，实现上下文隔离与专业化生产。

---

## 二、 创作工序流水线 (Stage 0–5)

```mermaid
graph LR
    S0["Stage 0: 设定构想<br/>(主控: 世界观/人物/主线)"] --> S1["Stage 1: 细纲构思<br/>(主控: 戏剧目标/核心冲突/上下文)"]
    S1 --> S2["Stage 2: 初稿起草<br/>(Drafter: 放飞想象+矛盾冲突)"]
    S2 --> S3["Stage 3: 文学重塑<br/>(Editor: 顺畅读感+节奏润色)"]
    S3 --> S4["Stage 4: 事实审计 & 提案装配<br/>(Reader: 5 大事实+JSON 提案)"]
    S4 --> S5["Stage 5: 状态同步<br/>(主控: 审定提案/封存快照)"]
```

1. **Stage 0 设定构想（主控）**：确立题材、书名、世界观与核心法则（`bible/`）、人物特征与性格（`characters/`）及分卷主线大纲（`outlines/`）。
2. **Stage 1 细纲与任务书（主控）**：梳理当章核心戏剧目标、场景推进、关键冲突点与伏笔线索，形成清晰的任务书（`outlines/vol_XX/beats/ch_XXX.md`）。
3. **Stage 2 初稿起草（Drafter）**：主控派发子代理（融合上章尾声接戏，自由展开剧情），生成初稿毛坯 `manuscript/vol_XX/raw/ch_XXX_v1.md`。
4. **Stage 3 文学重塑（Editor）**：主控派发子代理（拥有完全重塑定稿权，专注文风流动感与阅读爽感，自由重写优化），生成纯净定稿 `manuscript/vol_XX/final/ch_XXX.md`。
5. **Stage 4 事实审计与提案装配（Reader）**：主控派发子代理（客观提取 5 大事实），直接装配标准增量提案 `state/inbox/ch_XXX.json`。
6. **Stage 5 极速同步与归档（主控）**：主控审定 Reader 交付的增量提案并一键封存快照（`python studio.py sync ch_XXX`）。

---

## 三、 三大创作不变量

1. **事实一致不吃书**：正文事实为源，`state/*.json` 为机器真值，保障长篇连载逻辑不断层。
2. **伏笔暗线有台账**：重要伏笔（`GUN-*`）、秘密（`KNO-*`）、认知差/误会（`MIS-*`）登记入 `state/lines.json`。
3. **人物登场皆有据**：核心常驻人物建立人物卡（`characters/*.md`），所有登场实体登记在 `state/entities.json`。

---

## 四、 效率与防污染原则

1. **引擎黑盒原则**：严禁主控或子代理读取 `engine/*.py` 源码！一律通过 `python studio.py <命令>` 交互。
2. **主控轻量化原则**：主控在主会话中避免全文读取长篇正文，依据 Reader 的增量提案 JSON 与 `proposal verify` 差异候选清单进行**验证式**状态同步（不读正文全文）。
3. **精准上下文投喂**：通过 `python studio.py pack ch_XXX` 分层获取当章前情与基准状态，降低上下文冗余。
4. **原生写盘与沙箱隔离**：长正文落盘一律使用原生 `write_to_file` 工具；子代理在独立沙箱内自闭环。

---

## 五、 指南指引

- **工作流 SOP**：`.agents/rules/novel_workflow.md`
- **创作总纲**：`.agents/rules/novel_craft.md`
- **起草指南（Drafter）**：`.agents/rules/craft_drafter.md`
- **精修重塑指南（Editor）**：`.agents/rules/craft_editor.md`
- **事实审计与提案装配规范（Reader）**：`.agents/rules/craft_reader.md`
