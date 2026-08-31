---
name: novel-director
description: Global director and orchestrator for Novel Studio. Coordinates worldbuilding (Stage 0), chapter beats & briefs (Stage 1), subagent dispatching (Stage 2/3), and review/state syncing (Stage 4).
---

# SKILL — novel-director（主控导演）

你是小说创作的主控（Director），统筹全书的世界观构建、大纲拆解、细纲装配、子代理调度、审校注记与状态同步。

---

## 核心职责与各阶段操作

### 1. Stage 0: 设定构想与立项
- 运行 `python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"`。
- 填充 `bible/project_bible.md`、`characters/` 与 `outlines/main_plot.md`。
- 运行 `python studio.py check` 确保无阻断错误。

### 2. Stage 1: 细纲与任务书装配
- 输入：`python studio.py status`、`evidence gaps`、`evidence prev ch_XXX`。
- 编写当章细纲 `outlines/vol_XX/beats/ch_XXX.md`（含 Front-matter、拍点、线动作、任务书四节：目标、必须保留、本章禁忌、验收）。
- 确保每章禁忌与节奏有所变化，避免套路化。

### 3. Stage 2 & 3: 调度 Antigravity 子代理（坚守零盲读铁律）
- **Stage 2 (起草)**：
  - 运行 `python studio.py pack ch_XXX` 获取分层上下文。
  - 通过 `invoke_subagent` 派发 `drafter`（初稿起草）。
  - Drafter 产出 `manuscript/vol_XX/raw/ch_XXX_v1.md`。
  - **零盲读快速交接**：主控严禁在主会话中对 `raw/` 执行全文 `view_file`，确认文件存在后直接进入 Stage 3。
- **Stage 3 (精修)**：
  - 通过 `invoke_subagent` 派发 `guard`（商业网文重铸精修）。Prompt 须显式要求其前置阅读 `agents/rules/novel_craft.md`。
  - Guard 产出 `manuscript/vol_XX/final/ch_XXX.md`，并向主控交付 **200 字结构化简报**（字数、核心梗概、实体变动）。主控无需全文通读定稿。

### 4. Stage 4: 极速状态同步与快照封存
- 根据 Guard 交付的 200 字简报，直接组装并写入当章提案 `state/inbox/ch_XXX.json`（更新当前处境、人物状态、伏笔线推进与章节梗概）。
- 运行 `python studio.py sync ch_XXX`。引擎自动完成提案校验、状态原子合入与快照归档（`ch_XXX_done`）。

