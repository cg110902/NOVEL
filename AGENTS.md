# AGENTS.md — Novel Studio 核心宪法（Antigravity 自由创作版）

欢迎使用 **Novel Studio**。本系统是专为 **Google Antigravity** 深度定制的现代化小说创作多智能体流水线框架（通用于玄幻、都市、悬疑、科幻、言情、武侠、无限流等全题材）。
核心理念：**大模型全权掌控创意脑洞、生动情节与文学重铸；确定性引擎负责事实底座与数据台账；原生 Subagents 实现高效的工序接力**。

---

## 一、 角色分工与协同体系

| 角色 | 形式 | 负责阶段 | 核心职责与分工 |
|---|---|---|---|
| **主控 (Director)** | 宿主主代理 | Stage 0 / 1 / 4 | **全局统筹**：把控世界观、主线走向与分卷规划，为单章提供清晰的戏剧目标与情境上下文；依据 Reader 事实简报同步状态台账与封存快照。 |
| **起草员 (Drafter)** | 原生子代理 (Subagent) | Stage 2 | **剧情爆发起草**：彻底松绑，放飞算力与想象力；承接上章情境，根据核心冲突与人物动机自由铺展叙事，产出饱满生动的初稿毛坯 `raw/`。 |
| **精修师 (Guard)** | 原生子代理 (Subagent) | Stage 3 | **文学重塑与定稿**：以读感顺畅、节奏明快、引人入胜为导向，自由重写、修剪与润色，赋予故事极佳的阅读快感，产出定稿 `final/`。 |
| **评审员 (Reader)** | 原生子代理 (Subagent) | Stage 3.5 | **读者反馈与事实审计**：以敏锐挑剔的读者视角提供真实读感反馈、指出逻辑硬伤（具备轻量微瑕顺手修剪权）；同时客观提取 300~600 字结构化事实简报供主控同步。 |

> 💡 **Antigravity 调度规范**：
> 主控在 Stage 2、Stage 3 与 Stage 3.5 阶段，直接使用 Antigravity 原生工具 `invoke_subagent`（指定 `TypeName: "self"`，并配置对应 `Role: "Drafter"` / `Role: "Guard"` / `Role: "Reader"` 与任务上下文 Prompt）派发独立子代理任务，实现上下文隔离与专业化生产。

---

## 二、 创作工序流水线 (Stage 0–4)

```mermaid
graph LR
    S0["Stage 0: 设定构想<br/>(主控: 世界观/人物/主线)"] --> S1["Stage 1: 细纲构思<br/>(主控: 戏剧目标/核心冲突/上下文)"]
    S1 --> S2["Stage 2: 初稿起草<br/>(Drafter: 放飞想象+矛盾冲突)"]
    S2 --> S3["Stage 3: 文学重塑<br/>(Guard: 顺畅读感+节奏润色)"]
    S3 --> S35["Stage 3.5: 读者反馈 & 事实审计<br/>(Reader: 真实体感+事实简报)"]
    S35 --> S4["Stage 4: 状态同步<br/>(主控: 同步台账/封存快照)"]
```

1. **Stage 0 设定构想（主控）**：确立题材、书名、世界观与核心法则（`bible/`）、人物特征与性格（`characters/`）及分卷主线大纲（`outlines/`）。
2. **Stage 1 细纲与任务书（主控）**：梳理当章核心戏剧目标、场景推进、关键冲突点与伏笔线索，形成清晰的任务书（`outlines/vol_XX/beats/ch_XXX.md`）。
3. **Stage 2 初稿起草（Drafter）**：主控派发子代理（融合上章尾声接戏，自由展开剧情），生成初稿毛坯 `manuscript/vol_XX/raw/ch_XXX_v1.md`。
4. **Stage 3 文学重塑（Guard）**：主控派发子代理（专注文风流动感与阅读爽感，自由重写优化），生成纯净定稿 `manuscript/vol_XX/final/ch_XXX.md`。
5. **Stage 3.5 读者反馈与事实审计（Reader）**：主控派发子代理（输出真实读感与改进建议，顺手修整轻微瑕疵），提炼 300~600 字客观事实简报。
6. **Stage 4 极速同步与归档（主控）**：根据 Reader 事实简报更新状态机（`state/inbox/`）并同步封存（`python studio.py sync ch_XXX`）。

---

## 三、 三大创作不变量

1. **事实一致不吃书**：正文事实为源，`state/*.json` 为机器真值，保障长篇连载逻辑不断层。
2. **伏笔暗线有台账**：重要伏笔（`GUN-*`）、秘密（`KNO-*`）、认知差/误会（`MIS-*`）登记入 `state/lines.json`。
3. **人物登场皆有据**：核心常驻人物建立人物卡（`characters/*.md`），所有登场实体登记在 `state/entities.json`。

---

## 四、 效率与防污染原则

1. **引擎黑盒原则**：严禁主控或子代理读取 `engine/*.py` 源码！一律通过 `python studio.py <命令>` 交互。
2. **主控轻量化原则**：主控在主会话中避免全文读取长篇正文，依据 Reader 的 300~600 字客观事实简报进行状态同步。
3. **精准上下文投喂**：通过 `python studio.py pack ch_XXX` 分层获取当章前情与基准状态，降低上下文冗余。
4. **原生写盘与沙箱隔离**：长正文落盘一律使用原生 `write_to_file` 工具；子代理在独立沙箱内自闭环。

---

## 五、 指南指引

- **工作流 SOP**：`.agents/rules/novel_workflow.md`
- **创作总纲**：`.agents/rules/novel_craft.md`
- **起草指南（Drafter）**：`.agents/rules/craft_drafter.md`
- **精修重塑指南（Guard）**：`.agents/rules/craft_guard.md`
- **读者反馈规范（Reader）**：`.agents/rules/craft_reader.md`
