---
name: novel-architect
description: Universal worldbuilding architect and setup generator for Novel Studio (Stage 0). Covers all genres. Comprises 3 discrete subagent relay stages: Stage 0A (Architect-World), Stage 0B (Architect-Story), and Stage 0C (Architect-Inspector).
---

# SKILL — novel-architect（全题材开局架构师专属手册 · Stage 0 筑基指南）

> ⚡ **【主控派发契约 · 三子智能体接力流水线】**：
> Stage 0 是全书物理与数据底座的奠基阶段。**主控（Director）必须严格分三次依次唤起 3 个独立的 Subagent 专职子智能体，执行工序接力，严禁单 Agent 大包大揽！**
> 1. **第一棒 ➔ Subagent 1 (Stage 0A: Architect-World)**：执行 `init` 初始化，填实 **`bible/` 设定圣经六表** 与 `project.json`；
> 2. **第二棒 ➔ Subagent 2 (Stage 0B: Architect-Story)**：依据圣经交付 **MVU 六件套与双大纲**，全息通电 **`state/` 六表** 并添加首卷里程碑；
> 3. **第三棒 ➔ Subagent 3 (Stage 0C: Architect-Inspector)**：独立沙盒运行 `check` 机器硬闸门与常识因果扫荡，确保 **0 errors** 闭环交付。
>
> ⚡ **【子代理开工死命令】**：读取本手册仅限首步 1 次，严禁反复回读！起手必须直接调用工具物理落盘（**严禁传递 `ArtifactMetadata`**），交卷即走，绝不滞留！

---

## 🎯 一、 专职三子智能体工序细则

### 🛠️ 子智能体 1：Stage 0A【世界观公理与设定筑基 (Architect-World)】

- **核心职责**：初始化书籍工作区，依据作者给定的书名、题材与核心脑洞，填实设定真理底座；
- **执行工序**：
  1. 终端执行初始化命令：
     ```powershell
     python studio.py init -w "workspace/<书名>" -t "<书名>" -g "<题材>" -p "<主角名>"
     ```
  2. 填实 `bible/` 六表与 `project.json`（消灭所有 `{{slot:}}` 占位符，删除模板自带的 `<!-- ... -->` 指南注释）：
     - `bible/01_world_axioms.md`：核心 Logline、空间/圈层三级划分、2~3条不可违背客观公理、核心优势/金手指机制（原理+代价+当前上限+成长阶梯）；
     - `bible/02_power_system.md`：Tier 1~5 阶层梯阶与表现力/破坏力实物标尺（严防战力/财富通胀）；
     - `bible/03_factions_geography.md`：首发舞台与宏观进阶舞台地缘、三大核心势力矩阵与利益冲突网；
     - `bible/04_economy_items.md`：货币体系与购买力平价锚点（PPP 对账表）、物资道具五阶分类；
     - `bible/05_special_mechanics.md`：题材专属特异机制、专长/体质相生相克矩阵、负荷代偿法则；
     - `bible/06_deviations.md`：本书反套路偏离清单与核心创作红线；
     - `project.json`：配置书级参数与题材专属词表。
- **准跑命令**：`python studio.py init`；
- **准写工具**：`write_to_file` / `replace_file_content` 写入 `bible/*.md` 与 `project.json`（**严禁传递 `ArtifactMetadata`**）；
- **完工标准**：`bible/` 六表与 `project.json` 槽位消除率 100%，输出 3 行 0A 回执即刻交卷。

---

### 👤 子智能体 2：Stage 0B【商业故事宇宙筑基与状态机通电 (Architect-Story)】

- **核心职责**：以 `bible/` 设定为绝对真理，交付**高度商业化、高留存、高期待感**的最小可用宇宙（MVU 六件套与双大纲），全息通电 `state/` 六表；
- **商业网文故事筑基四大硬核法则（注意事项）**：
  1. 🎯 **一卷一绝活（核心商业卖点与读者承诺）**：
     - 首卷必须确立明确的**核心爽点与脑洞兑现机制**（如：*反向薅修仙宗门羊毛/假装绝世高人靠脑补通关/全网剧透逼反派当保镖*）；
     - 第一阶段（Phase 1）必须直接引爆核心爽点，**严禁慢热**！前三章必须让读者体验到第一次极具反常识的爽快破局。
  2. ⚡ **拒绝流水账大纲 · 章节绑定【反常识戏眼 + 断章刀口】**：
     - 在 `outlines/vol_01/outline.md` 的章节规划（Chapter Breakdown）中，**严禁写成“去某地买药”、“回宗门修炼”等无聊对账流水账**！
     - 每一条章节规划必须标明：`ch_XXX：【核心行动推进/反常识骚操作/戏剧反差】+【章末悬念刀口（Cliffhanger）】`，确保每一章自带让读者欲罢不能的追读拉力！
  3. 🎭 **对手与配角去工具化（利益独立与人情世故）**：
     - 首卷对手绝不写单纯无脑嘲讽送经验的降智 NPC，其行动必须建立在真实的利益算计、宗门地位或自保本能之上；
     - 关键搭档必须具备独立诉求与性格毛刺，绝非无脑倒贴的提线木偶。
  4. 💣 **商业线索网高能布设（GUN / KNO / MIS）**：
     - `state/lines.json` 中的首卷线索必须具备极高戏剧张力：`GUN-001`（迫在眉睫的危机倒计时或暴利资源）、`KNO-001`（足以致命的惊天信息差）、`MIS-001`（带来巨大反差感的外界认知偏差）。
- **执行工序**：
  1. **MVU 六件套与大纲物理落盘**（消灭所有 `{{slot:}}` 与注释）：
     - `characters/protagonist.md`：主角专属卡（Front-matter 属性闭环、心理四维 Want/Need/Fear/Lie、微动作库、恒定称谓矩阵）；
     - `characters/<搭档名>.md`：关键搭档/男/女主卡（独立动机与法定互称矩阵）；
     - `characters/<对手名>.md`：首卷核心对手卡（合理利益博弈动机与互称）；
     - `entities/items/<道具名>.md`：核心道具/信物卡（明确 `holder`、品阶与使用消耗）；
     - `entities/factions/<势力名>.md`：核心初始势力卡（掌权人 `leader`、总部 `headquarters`）；
     - `entities/locations/<地名>.md`：开局场景卡（空间物象与环境法则）；
     - `outlines/main_plot.md`：全书主线三幕脊柱与长程里程碑；
     - `outlines/vol_01/outline.md`：首卷商业分卷大纲（明确商业卖点、阶段反常识破局与章末断章刀口）。
  2. **状态机六表全息通电**（卡片落盘后必须在同一轮写入 `state/`，严禁留空）：
     - `state/persons.json`, `items.json`, `factions.json`, `places.json`：注册对应实体；
     - `state/current.json`：填实开局第一现场（时间、地点、处境、主角状态、在场人、初始 loadout 四件套）；
     - `state/lines.json`：埋设首卷高张力长线 `GUN-001`、机密知情差 `KNO-001`、外界认知偏差 `MIS-001`；
     - `state/locked.json`：登记不可逆既定事实 `LOCK-001`；
     - `state/ledger.json`：在 `pools` 中声明本题材货币池（如灵石、银两或积分）；
     - 终端执行添加首卷破局里程碑：
       ```powershell
       python studio.py milestone add --title "标题" --target-ch 5 --desc "描述" -w "workspace/<书名>"
       ```
- **准跑命令**：`python studio.py milestone add`；
- **准写工具**：`write_to_file` / `replace_file_content` 写入 `characters/`, `entities/`, `outlines/`, `state/`（**严禁传递 `ArtifactMetadata`**）；
- **完工标准**：商业大纲与 MVU 六件套落盘，状态机六表通电完毕，输出 3 行 0B 回执即刻交卷。

---

### 🩺 子智能体 3：Stage 0C【全息双轨审查与语义逻辑深审 (Architect-Inspector)】

- **核心职责**：以纯净第三方总编视角对全书底座进行机器硬闸门体检与 **LLM 深度语义理解、故事张力诊断与叙事逻辑推演**，输出详尽审查报告，消除一切逻辑漏洞与微瑕，确保 0 errors 闭环交付；
- **执行工序**：
  1. **第一轨【机器硬闸门 · 必须 0 errors】**：
     - 终端运行体检命令：
       ```powershell
       python studio.py check -w "workspace/<书名>"
       ```
     - 零容忍硬指标：未填槽位 `unfilled_slot` 必须为 0；未登记角色 `unregistered_character` 必须为 0；实体 ID 冲突必须为 0；`project.json` 必填项严禁留空；
  2. **第二轨【大模型七大语义理解与叙事逻辑深度推演】**（全权调用 LLM 认知与文学理解，逐项深度推演并输出深度分析）：
     - ① **金手指（如有）与机制逻辑闭环**：深度审视核心脑洞，推演是否存在逻辑悖论（如：可能出现的意外情况？）；
     - ② **爽感张力与冲突推演**：装逼打脸的节奏是否自然可信？
     - ③ **人物心理四维与独立活人感**：主角与配角（如主角A、配角B）是否具备真实独立诉求与性格软肋，绝不沦为提线木偶与降智工具人；
     - ④ **长线叙事弧光与分卷大纲节奏**：主线三幕脊柱与首卷各阶段的篇幅与节奏是否张弛有度，伏笔（GUN/KNO/MIS）埋设是否精巧；
     - ⑤ **因果与时空尺度自洽**：地理地缘（`bible/03`、`locations/`）与时间线跨度、行动耗时是否严密自洽；
     - ⑥ **经济与战力实物标尺**：货币购买力对账表（`bible/04`）、期初资产（`state/ledger.json`）与各阶层破坏力标尺（`bible/02`）是否稳定；
     - ⑦ **创作红线与偏离清单遵从**：核验全书设定是否严格遵守 `bible/06_deviations.md` 声明的创作红线。
  3. **产出《Stage 0 开局全息语义与叙事逻辑审查报告》并物理落盘**：
     - 调用 `write_to_file` 将详尽的审查分析报告写入 `log/review/stage_0_audit.md`（包含七大维度打分、深度推演逻辑、潜在隐患与修补建议；**严禁传递 `ArtifactMetadata`**）；
  4. **针对性修复与闭环确认**：
     - 若发现任何设定缺陷或逻辑矛盾，调用 `replace_file_content` 进行精准修复；
     - 终端复跑 `python studio.py check -w "workspace/<书名>"` 确认 **0 errors 放行通过**。
- **准跑命令**：`python studio.py check`；
- **准写工具**：`write_to_file` 写入 `log/review/stage_0_audit.md`，`replace_file_content` 针对性修正（**严禁传递 `ArtifactMetadata`**）；
- **完工标准**：报告物理落盘，机器硬闸门 0 errors 且七大语义逻辑 100% 达标，输出 3 行 0C 回执即刻交卷。

---

## 📋 二、 主控标准派发令模板 (Director Orders)

主控（Director）派发时必须使用以下标准指令唤起对应的 Subagent：

### 1. Stage 0A 派发令：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 阶段：Stage 0A (Architect-World)
- 核心输入：书名《<书名>》、题材<题材>、主角<主角名>、核心脑洞与金手指
- 执行指令：读取技能卡 ➔ 执行 studio.py init ➔ 填实 bible/ 六表与 project.json（消除所有 {{slot:}} 与注释） ➔ 物理直接落盘（禁传 ArtifactMetadata） ➔ 3 行回执交卷
```

### 2. Stage 0B 派发令：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 阶段：Stage 0B (Architect-Story)
- 核心输入：bible/ 设定真值、主角名<主角名>
- 执行指令：读取技能卡与 bible/ ➔ 交付 MVU 六件套与商业高能双大纲（强化核心卖点、反常识破局与章末断章刀口） ➔ 全息通电 state/ 六表 ➔ 运行 studio.py milestone add ➔ 物理直接落盘（禁传 ArtifactMetadata） ➔ 3 行回执交卷
```

### 3. Stage 0C 派发令：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 阶段：Stage 0C (Architect-Inspector)
- 核心输入：全书设定、卡片、双大纲与 state/ 状态数据
- 执行指令：读取技能卡 ➔ 运行 studio.py check ➔ 全面调用大模型语义理解与推理能力，深入核验七大语义与故事逻辑 ➔ 调用 write_to_file 输出详尽的《Stage 0 开局全息语义与叙事逻辑审查报告》落盘至 log/review/stage_0_audit.md（禁传 ArtifactMetadata） ➔ 针对性修复微瑕 ➔ 确认 0 errors ➔ 3 行回执交卷
```

---

## 🛑 三、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 0C (Architect-Inspector)
- 产出路径：workspace/<书名>/log/review/stage_0_audit.md
- 核心指标：七大语义逻辑深审达标 ｜ 审查报告物理落盘 ｜ 机器硬闸门 0 errors ｜ 验收达标无滞留
```


