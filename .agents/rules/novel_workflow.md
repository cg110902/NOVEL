# novel_workflow.md — 小说创作流水线标准 SOP（全题材通用版）

本文档定义 Novel Studio 创作工序（Stage 0–5）的工程标准流程、各工序的**输入输出（I/O）严密契约**与协同规范。

---

## 🛑 全局纪律：原子化交付准则（单向流转，落盘即止）

1. **严禁冗余自查（No Redundant Introspection）**：写入目标文件后，即视为当前阶段终态，**立即交卷汇报并结束当前任务**，严禁二次回读自检、严禁自我怀疑推翻已交付成果；
2. **严禁职责蔓延（No Scope Creep）**：严格恪守单一职责原则，严禁越权处理非本阶段事务，严禁编写任何非必要的测试/统计脚本；
3. **交付优于完美（Done is Better than Perfect）**：杜绝微观细节上的无边界内耗，保持流水线单向高速推进。

---

## 一、 流水线阶段 I/O 契约全景表

| 阶段 | 负责角色 | 📥 输入物 (Inputs) | ⚙️ 核心工序 (Actions) | 📤 输出物 (Outputs) |
|---|---|---|---|---|
| **Stage 0<br/>设定构想** | **主控<br/>(Director)** | • 书名、题材、核心脑洞与作者创意<br/>• 模板库 `templates/` | 初始化工作区；确立核心法则、语言定调、核心人物卡、分卷大纲；播种状态机真值与初始主角实体。 | • `bible/project_bible.md`<br/>• `characters/*.md`<br/>• `outlines/main_plot.md`<br/>• `outlines/vol_XX/outline.md`<br/>• `state/*.json` (初始状态底座) |
| **Stage 1<br/>细纲装配** | **主控<br/>(Director)** | • 实时状态 `state/current.json`<br/>• 伏笔台账 `state/lines.json`<br/>• 分卷大纲 `vol_XX/outline.md`<br/>• **上章 Critic 催更便签** `log/critic/ch_{前一章}.md`<br/>• 细纲模板 `templates/beats.md` | 梳理戏剧冲突、叙事比重、物理标的、利益死结；**加载并吸纳上章催更便签中的读者期待**，生成结构化细纲任务书。 | • 当章细纲任务书：<br/>`outlines/vol_XX/beats/ch_XXX.md` |
| **Stage 2<br/>初稿起草** | **起草员<br/>(Drafter)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 上章情境与梗概 (`pack`)<br/>• 章初状态与人物性格 (`pack`)<br/>• 起草指南 `craft_drafter.md` | 承接前章现场，放飞算力与脑洞，拉满冲突与男女主生动互动，无修辞禁词约束，一次落盘即交卷。 | • 初稿文件：<br/>`manuscript/vol_XX/raw/ch_XXX_v1.md`<br/>• 核心看点简要汇报 |
| **Stage 3<br/>文学重塑** | **精修师<br/>(Editor)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 初稿毛坯 `raw/ch_XXX_v1.md`<br/>• 定稿指南 `craft_editor.md` | 顶级总编视角重塑；以“连贯丝滑欲罢不能”为唯一指标；砍掉80%无效景物，动态对白，一次落盘即交卷。 | • 纯净定稿文件：<br/>`manuscript/vol_XX/final/ch_XXX.md`<br/>(首行章题，后为100%纯正文) |
| **Stage 4A<br/>事实审计** | **审计员<br/>(Reader)** | • 定稿正文 `final/ch_XXX.md`<br/>• 当章细纲 `beats/ch_XXX.md`<br/>• 审计规范 `craft_reader.md` | 清晰提取 4 大核心事实（现场在场、关键新实体、主线伏笔、大额收支），直接装配标准提案，落盘即交卷。 | • 标准增量提案文件：<br/>`state/inbox/ch_XXX.json`<br/>(符合 Schema 规范) |
| **Stage 4B<br/>读者便签** | **评测员<br/>(Critic)** | • 定稿正文 `final/ch_XXX.md`<br/>• 评测标准 `craft_critic.md` | 扮演十年老白追更读者，输出 150~300 字**老白催更便签**（本章体感 + 下章读者最想看什么 / 最怕踩什么），**供下章参考，当章不阻塞**，落盘即交卷。 | • 催更便签文件：<br/>`log/critic/ch_XXX.md` |
| **Stage 5<br/>同步与交付** | **主控<br/>(Director)** | • beats + final + inbox JSON<br/>• Critic 催更便签 | 执行 `studio sync` 原子合并真值并封存快照；将 Critic 便签留作下章参考；将最终成品交付人类作者验收。 | • 状态真值更新：`state/*.json`<br/>• 完整快照：`state/snapshots/<id>_ch_XXX_done`<br/>• 最终成品交付人类作者 |

---

## 二、 各阶段操作指南与通用契约

### Stage 0: 设定构想与立项（主控）
- **初始化工程**：`python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"`；
- **法定实体契约**：类型为 `person, item, faction, place, other`，法定字段 `name, type, status, summary...`，严禁非法字段。

### Stage 1: 细纲构思与催更便签加载（主控）
- **脚手架生成**：`python studio.py beats new ch_XXX --write`；
- **标准加载流程**：
  1. 第 2 章起，主控必须调用 `view_file` 主动读取上一章的 `log/critic/ch_{前一章}.md`（老白催更便签）；
  2. 提取读者最想看的 1~2 个爽点期待（如战利品落袋、打脸对手、男女主互动）或避坑警告；
  3. 将读者期待直接填入 `outlines/vol_XX/beats/ch_XXX.md` 的“目标”或“验收”条款中；
  4. 确认物理标的、利益死结与伏笔动作就绪，原地调度 Stage 2。

### Stage 2: 初稿起草（Drafter · 算力放飞 · 落盘即走）
- **调度方式**：`invoke_subagent(TypeName="self", Role="Drafter", Model="inherit", Prompt="...")`；
- **执行规范**：
  - 承接前章现场，放飞算力，专心把冲突与男女主互动写精彩，无修辞禁词约束；
  - **篇幅彻底放飞**：字数在 **2000~3000+ 汉字**自由舒展；
  - **Tool Budget ≤ 3 次**：读材料 1~2 次 → 原生写 `raw/ch_XXX_v1.md` 1 次 → 汇报 1 次；
  - **落盘即交卷**：写完直接退出，严禁在终端编写任何指标统计脚本或自查。

### Stage 3: 文学重塑（Editor · 读感至上 · 落盘即走）
- **调度方式**：`invoke_subagent(TypeName="self", Role="Editor", Model="inherit", Prompt="...")`；
- **执行规范**：
  - 顶级商业网文总编视角，以“连贯、丝滑、流畅、欲罢不能”为唯一考核指标；
  - 动态拉高对白（20%~55%），砍掉 80% 无效景物，清剿“极”字口癖与八股套话，章末强钩锁死；
  - **一次成型直接落盘**：定稿首行为章题标题行（`# 第N章 标题`），使用 `write_to_file` 写入 `final/ch_XXX.md`；
  - **落盘即交卷**：写完直接汇报交卷，严禁编写修剪脚本或二次自查。

### Stage 4: 双轨并行质检（Reader 事实审计 + Critic 催更便签）
- **调度方式（Antigravity 单调用并发）**：
  ```json
  {
    "Subagents": [
      { "TypeName": "self", "Role": "Reader", "Model": "inherit", "Prompt": "Stage 4A 事实审计..." },
      { "TypeName": "self", "Role": "Critic", "Model": "inherit", "Prompt": "Stage 4B 催更便签..." }
    ]
  }
  ```
- **轨 A·极简事实审计 (Reader)**：
  - 清晰提取 4 大核心事实：现场在场名单与主角状态、重要新实体、核心伏笔动线、大额收支；
  - 一步到位落盘 `state/inbox/ch_XXX.json`；落盘即交卷，严禁在子沙箱跑任何测试命令；
- **轨 B·老白催更便签 (Critic · 专供下章)**：
  - 输出 150~300 字便签（本章体感 + 下章读者最想看什么 / 最怕踩什么）至 `log/critic/ch_XXX.md`；
  - **纯粹作为建议供下章参考，当章绝不阻塞**；落盘即交卷。

### Stage 5: 状态同步与快照封存（主控）
- **一键原子同步**：
  - 执行 `python studio.py sync ch_XXX`：秒级完成账目平账、实体更新与快照创建；
  - 全景看板（`python studio.py dashboard`）默认每 5 章或作者需要时刷新一次；
- **成品交付**：
  - 向人类作者呈送 final 章节成品与看点摘要，邀请作者终审。
