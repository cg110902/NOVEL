# novel_workflow.md — 小说创作流水线标准 SOP（全题材通用版）

本文档定义 Novel Studio 创作工序（Stage 0–5）的工程标准流程、各工序的**输入输出（I/O）严密契约**与协同规范。

---

## 一、 流水线阶段 I/O 契约全景表

| 阶段 | 负责角色 | 📥 输入物 (Inputs) | ⚙️ 核心工序 (Actions) | 📤 输出物 (Outputs) |
|---|---|---|---|---|
| **Stage 0<br/>设定构想** | **主控<br/>(Director)** | • 书名、题材、核心脑洞与作者创意<br/>• 模板库 `templates/` | 初始化工作区；确立核心法则、语言定调、核心人物卡、分卷大纲；播种状态机真值与初始主角实体。 | • `bible/project_bible.md`<br/>• `characters/*.md`<br/>• `outlines/main_plot.md`<br/>• `outlines/vol_XX/outline.md`<br/>• `state/*.json` (初始状态底座) |
| **Stage 1<br/>细纲装配** | **主控<br/>(Director)** | • 实时状态 `state/current.json`<br/>• 伏笔台账 `state/lines.json`<br/>• 分卷大纲 `vol_XX/outline.md`<br/>• 上章事实与 Critic 建议<br/>• 细纲模板 `templates/beats.md` | 梳理戏剧冲突、叙事比重、物理标的、利益死结与伏笔动作，生成结构化细纲任务书。 | • 当章细纲任务书：<br/>`outlines/vol_XX/beats/ch_XXX.md` |
| **Stage 2<br/>初稿起草** | **起草员<br/>(Drafter)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 上章情境与梗概 (`pack`)<br/>• 章初状态与人物性格 (`pack`)<br/>• 起草指南 `craft_drafter.md` | 承接前章现场，以动作化推进和机锋对白展开冲突，篇幅自由舒展（2000~3000+ 汉字），产出初稿毛坯。 | • 初稿文件：<br/>`manuscript/vol_XX/raw/ch_XXX_v1.md`<br/>• 核心看点简要汇报 |
| **Stage 3<br/>文学重塑** | **精修师<br/>(Editor)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 初稿毛坯 `raw/ch_XXX_v1.md`<br/>• 定稿指南 `craft_editor.md` | 以顺畅读感为唯一导向；全力保留黄金细节，剔除工业废话与心理独白；执行物理刀口收尾，一次精修成型。 | • 纯净定稿文件：<br/>`manuscript/vol_XX/final/ch_XXX.md`<br/>(首行为章题标题行，后为100%纯正文) |
| **Stage 4A<br/>事实审计** | **审计员<br/>(Reader)** | • 定稿正文 `final/ch_XXX.md`<br/>• 当章细纲 `beats/ch_XXX.md`<br/>• 审计规范 `craft_reader.md` | 客观排查 5 大事实变动（角色、时空、道具资源、伏笔动线、新增实体），装配内嵌逐字引文（quote）的增量提案。 | • 标准增量提案文件：<br/>`state/inbox/ch_XXX.json`<br/>(符合 Schema 规范) |
| **Stage 4B<br/>毒舌评测** | **评测员<br/>(Critic)** | • 定稿正文 `final/ch_XXX.md`<br/>• 评测标准 `craft_critic.md` | 模拟十年老白读者，测算毒点、爽点、留存三大指标，输出紧凑评分卡，作为 Director 风控闸门与下章 Drafter 建议。 | • 评测报告文件：<br/>`log/critic/ch_XXX.md`<br/>(300~500 汉字紧凑卡) |
| **Stage 5<br/>裁决与同步** | **主控<br/>(Director)** | • beats + raw + final + inbox JSON<br/>• Critic 评分报告 | 查阅 Critic 报告执行风控裁决（不合格打回重修）；合格后执行 `studio sync` 原子合并真值并封存快照。 | • 状态真值更新：`state/*.json`<br/>• 完整快照：`state/snapshots/<id>_ch_XXX_done`<br/>• 最终成品交付人类作者 |

---

## 二、 各阶段操作指南与通用契约

### Stage 0: 设定构想与立项（主控）
- **初始化工程**：`python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"`；
  - 引擎会自动将主角注册进 `state/entities.json`，并将默认字数带设置为 `[2000, 3000]`。
- **法定实体契约（全题材通用）**：
  - **法定类型**：`['person', 'item', 'faction', 'place', 'other']`；
  - **法定字段**：`name` (唯一标识), `type`, `status` (`'active'`|`'retired'`), `summary` (简介，禁止用 description/bio), `aliases`, `realm` (或职级/代差), `faction`, `holder`, `location`, `condition`, `charges`, `max_charges`, `attitude`, `life_status`, `dossier` (与主角的羁绊备忘), `card` (人物卡相对路径)；
  - **严禁非法字段**：严禁出现 `id`, `category`, `entity_type` 等非法字段。
- **词表供参手势（引擎零预设，由主控按题材注入）**：
  - `python studio.py config guide`：查看引擎可接受参数型号单；
  - `python studio.py config suggest`：让引擎机械统计全书高频短别名与高频泛词；
  - `python studio.py config set <键> '<JSON值>' [--merge]`：动态供参，即时生效随快照封版。

### Stage 1: 细纲构思（主控）
- **脚手架生成**：`python studio.py beats new ch_XXX --write`；
- **核心场景要素**：
  1. 🎯 **物理标的**：争夺的具体标的（合同、证据、秘境玉简、能源核心、晋升提名）；
  2. ⚔️ **利益死结**：双方互不相让的诉求，禁止提前软化妥协；
  3. 🎬 **破局动作**：以角色具体的动作或决策打破僵局；
- **防情绪疲劳规范**：连续 3 章高压决战后，建议配置一章战后清点或爽感兑现章型；连续采用相同 `form` 须在 front-matter 提供 `form_reason`。

### Stage 2: 初稿起草（Drafter · 算力放飞）
- **调度方式**：`invoke_subagent(TypeName="self", Role="Drafter", Model="inherit", Prompt="...")`；
- **执行规范**：
  - 承接前章现场，以行动和对白拉开冲突，严禁原地长篇自问自答；
  - **篇幅彻底放飞**：字数在 **2000~3000+ 汉字**区间完全自由舒展，重在情节饱满；
  - **Tool Budget ≤ 3 次**：读材料 1~2 次 → 原生写 `raw/ch_XXX_v1.md` 1 次 → 汇报 1 次；严禁在终端编写任何指标统计脚本；
- **接力流转**：完稿后主控立即触发 Stage 3，中间不向人类汇报。

### Stage 3: 文学重塑（Editor · 读感优先）
- **调度方式**：`invoke_subagent(TypeName="self", Role="Editor", Model="inherit", Prompt="...")`；
- **执行规范**：
  - **全力精修黄金细节**：压迫感、巧思破局、收获落袋、机锋对白；
  - **坚决剔除工业废话**：出戏科普、套路生理描写、脑内独白、事后哲理感悟；
  - **物理刀口收尾**：定稿首行为章题标题行（`# 第N章 标题`），章末落在具体的动作或悬念瞬间；
  - **一次成型落盘**：使用 `write_to_file` 写入 `final/ch_XXX.md`，严禁在终端跑任何修剪或统计命令；
- **接力流转**：完稿后主控立即单次并发触发 Stage 4 Reader 与 Critic。

### Stage 4: 双轨并行质检（Reader 事实审计 + Critic 毒舌评测）
- **调度方式（Antigravity 单调用并发）**：
  ```json
  {
    "Subagents": [
      { "TypeName": "self", "Role": "Reader", "Model": "inherit", "Prompt": "Stage 4A 事实审计..." },
      { "TypeName": "self", "Role": "Critic", "Model": "inherit", "Prompt": "Stage 4B 毒舌评测..." }
    ]
  }
  ```
- **轨 A·事实审计 (Reader)**：
  - 严格以 final 正文为源，提取时空、在场角色、境界职级、装备资产、资金流水、伏笔动线与新实体；
  - 每条变动**必须携带 `quote`（逐字摘自 final 原句，含标点）**；
  - 直接落盘 `state/inbox/ch_XXX.json`；严禁在子沙箱跑 verify/sync 测试；
- **轨 B·老白毒舌评测 (Critic)**：
  - 测算毒点指数 (0~100)、爽点转化率 (0~100%)、留存抓手 (0~100)；
  - 给出评级（S/A/B/C）与修改建议，紧凑落盘至 `log/critic/ch_XXX.md`（300~500 汉字）。

### Stage 5: 裁决闭环、状态同步与快照封存（主控）
- **风控闸门（Critic Gate）**：
  - 若 Critic 评级为 **C** 或 **毒点指数 > 30**（憋屈不还手、圣母降智）：**主控携带修改建议直接打回 Stage 3 让 Editor 重塑再验**；
  - 若评测合格（A/S 级）：放行进入同步流水线。
- **一键原子同步**：
  - 执行 `python studio.py sync ch_XXX`：引擎自动执行引文校验、账目平账、实体更新、状态验证与快照创建；
  - 全景看板 HTML（`python studio.py dashboard`）默认每 5 章（如 ch_005, ch_010）或用户要求时刷新一次。
- **成品交付**：
  - 主控直接向人类作者呈送定稿成品与核心看点，邀请作者终审验收。
