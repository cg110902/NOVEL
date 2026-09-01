# novel_workflow.md — 小说创作流水线标准 SOP

本文档定义 Novel Studio 创作工序（Stage 0–4）的标准流程、各工序的**输入输出（I/O）契约**与协同规范。

---

## 一、 全流水线阶段输入/输出 (I/O) 契约全景表

| 阶段 | 负责角色 | 📥 必须读取的输入物 (Inputs) | ⚙️ 核心工序动作 (Actions) | 📤 必须交付的产出物 (Outputs) |
|---|---|---|---|---|
| **Stage 0<br/>设定构想** | **主控<br/>(Director)** | • 用户书名、题材、核心脑洞与创意要求<br/>• 模板库 `templates/` | 初始化工作区，确立世界观/力量法则、文风红线（禁止冷峻阴暗逼仄，全篇直白大白话）、核心人物特征与人设、分卷主线大纲及状态机初始真值。 | • `bible/project_bible.md`<br/>• `characters/*.md`<br/>• `outlines/main_plot.md`<br/>• `outlines/vol_XX/outline.md`<br/>• `state/*.json` (初始状态) |
| **Stage 1<br/>细纲装配** | **主控<br/>(Director)** | • 当前状态 `state/current.json`<br/>• 伏笔台账 `state/lines.json`<br/>• 分卷大纲 `vol_XX/outline.md`<br/>• 前章事实简报与情境<br/>• 细纲模板 `templates/beats.md` | 梳理当章核心矛盾死结、场景推进脉络、关键冲突与伏笔线索，组装高清晰度、低阅读成本的细纲任务书。 | • 当章细纲任务书：<br/>`outlines/vol_XX/beats/ch_XXX.md` |
| **Stage 2<br/>初稿起草** | **起草员<br/>(Drafter)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 上章尾声情境与梗概 (pack)<br/>• 章初状态 `current.json` (pack)<br/>• 核心人物人设与起草指南 `craft_drafter.md` | 充分发挥想象力，承接前章余温，**禁止冷峻阴暗逼仄文风，全篇使用通俗直白大白话**，以动作化推进和对白机锋产出高能初稿毛坯。 | • 初稿正文文件：<br/>`manuscript/vol_XX/raw/ch_XXX_v1.md`<br/>(纯小说 Markdown，约 2400~3500 字)<br/>• 向主控汇报完稿概况 |
| **Stage 3<br/>文学重塑** | **精修师<br/>(Guard)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 初稿毛坯 `raw/ch_XXX_v1.md`<br/>• 定稿指南 `craft_guard.md` | **专注于文学质感与阅读快感**：彻底清除冷峻压抑调性，全篇以接地气大白话重写润色，剪除冗长内心戏，执行物理刀口截断，打磨顺滑定稿。 | • 纯净定稿正文文件：<br/>`manuscript/vol_XX/final/ch_XXX.md`<br/>(100% 纯正文)<br/>• 向主控汇报定稿情况 |
| **Stage 3.5<br/>读者反馈<br/>& 事实审计** | **评审员<br/>(Reader)** | • 定稿正文 `final/ch_XXX.md`<br/>• 当章细纲 `beats/ch_XXX.md`<br/>• 审计规范 `craft_reader.md` | **真实读感与客观事实审计**：<br/>1. 输出真实读者反馈（把关文风明快度与大白话通俗度）；<br/>2. 顺手修整轻微语病、说教或阴暗字眼；<br/>3. 客观提炼 300~600 字 5 大结构化事实简报。 | • 读者读感与反馈报告<br/>• **300~600 字客观事实简报**（剧情时空、人物状态、道具流水、三类线索、新增实体） |
| **Stage 4<br/>状态封存** | **主控<br/>(Director)** | • Reader 交付的 300~600 字结构化事实简报<br/>• 提案规范 `state/inbox/README.md` | 将 Reader 事实简报 1:1 映射写入增量提案 `state/inbox/ch_XXX.json`，运行 `studio.py sync` 触发校验并生成原子快照。 | • 增量提案：`state/inbox/ch_XXX.json`<br/>• 机器真值更新：`state/*.json`<br/>• 归档快照：`snapshots/*_ch_XXX_done` |

---

## 二、 各阶段操作指南与数据规范

### Stage 0: 设定构想与立项（主控）
- **初始化工程**：运行 `python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"`；
- **核心设定落地**：
  1. **世界观与核心法则（`bible/project_bible.md`）**：明确题材规则、力量体系与文风基调（禁止冷峻阴暗逼仄，全篇直白大白话）；
  2. **人物设定（`characters/*.md`）**：为主要角色建立人物卡，明确 Want/Fear、性格特征与说话风格；
  3. **分卷大纲（`outlines/vol_XX/outline.md`）**：规划分卷主要情节走向、核心高潮与预期伏笔清单；
- **状态机与两账分离**：
  - **大纲记规划**：在卷大纲中预先构思全卷伏笔；
  - **状态机记落盘真值**：开局 `state/lines.json` 保持初始空账本，伏笔随章节推进逐章 `plant` 入库；
  - **Schema 规范**：`current.json` 中 `key_relationships` 与 `time` 为字符串；`entities.json` 实体简介字段为 `summary`；`ledger.json` 通货使用 `initial` 与 `current`。

### Stage 1: 细纲构思（主控）
- 依据前章事实简报与分卷大纲，确立当章核心戏剧目标、场景发展脉络、核心冲突与关键伏笔动作，写入 `outlines/vol_XX/beats/ch_XXX.md`。

### Stage 2: 初稿起草（Drafter）
- **调度**：主控调用 `invoke_subagent(TypeName="self", Role="Drafter", Prompt="...")`；
- **动作**：承接上章情境，放飞想象力展开叙事，以直白大白话和动作化推进拉满冲突与对白；
- **输出**：`manuscript/vol_XX/raw/ch_XXX_v1.md`（使用原生 `write_to_file` 工具）。

### Stage 3: 文学重塑（Guard）
- **调度**：主控调用 `invoke_subagent(TypeName="self", Role="Guard", Prompt="...")`；
- **动作**：以直白通俗读感与明快节奏为导向，自由重写与润色，彻底清洗冷峻阴暗逼仄调性，物理刀口截断；
- **输出**：`manuscript/vol_XX/final/ch_XXX.md`（使用原生 `write_to_file` 工具）。

### Stage 3.5: 读者反馈与事实审计（Reader）
- **调度**：主控调用 `invoke_subagent(TypeName="self", Role="Reader", Prompt="...")`；
- **动作**：提供真实读者反馈与文风把关（顺手修整轻微瑕疵/说教）；客观提炼 300~600 字 5 大事实简报；
- **输出**：反馈报告 + 5 大客观事实简报。

### Stage 4: 极速状态同步与快照封存（主控）
- **实体分流**：核心常驻角色在 `characters/` 建卡；次要/临时实体直接在 `state/inbox/ch_XXX.json` 声明即可；
- **同步闭环**：
  1. 将 Reader 简报事实写入 `state/inbox/ch_XXX.json`；
  2. 运行 `python studio.py proposal check ch_XXX` 预检；
  3. 运行 `python studio.py sync ch_XXX` 合并真值并生成快照。
