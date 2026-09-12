---
name: novel-architect
description: Universal worldbuilding architect and setup generator for Novel Studio (Stage 0). Builds project bible (Stage 0A) and character profiles, outlines, initial state tables, milestones (Stage 0B) in an isolated sandbox, followed by holographic cross-reconciliation (Stage 0C).
---

# SKILL — novel-architect（开局架构师专属手册 · Stage 0）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定书名、题材、主角与核心脑洞。**若未在上下文装载本手册仅限首步读取 1 次，进入创世架构后绝对严禁回读倒嚼本手册！严禁漫游目录！**
> 起手**必须直接执行对应子阶段工具操作！** 消除所有占位槽位，以工具物理落盘（**严禁传递 `ArtifactMetadata`**）后输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

专注于全书从 0 到 1 的顶层创世架构搭建（Stage 0），在独立沙盒中分三步执行，消除所有 `{{slot:}}` 占位符，直接调用工具将设定、卡片、大纲与状态表物理落盘，确保 `check` 0 报错！

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

### 阶段一：Stage 0A【世界观公理筑基 (Architect-World)】
1. **初始化工作区**：在终端运行 `python studio.py init -w "workspace/<书名>" -t "<书名>" -g "<题材>" -p "<主角名>"`；
2. **直接调用工具填实圣经六表与 `project.json`**（消除所有 `{{slot:}}`）：
   - `01_world_axioms.md`（Logline、空间地理尺度、底层法则公理、金手指代偿）；
   - `02_power_system.md`（1~12 级常量梯阶与破坏力标尺）；
   - `03_factions_geography.md`（地图骨架与核心势力拓扑）；
   - `04_economy_items.md`（货币购买力与道具品阶）；
   - `05_special_mechanics.md`（题材专属机制与阵营相克）；
   - `06_deviations.md`（绝对偏离清单，严禁触碰的套路红线）；
3. **物理落盘交卷**：调用 `write_to_file` 或 `replace_file_content` 写入（仅传 4 个核心参数，**严禁传递 `ArtifactMetadata`**），提交 0A 回执。

### 阶段二：Stage 0B【人物大纲编织与状态通电 (Architect-Story)】
1. **直接调用工具生成卡片与大纲**：
   - `characters/protagonist.md`（主角档案：Want/Fear/逆鳞/称谓/微动作）；
   - `characters/<角色名>.md`（首卷核心配角/女主/反派卡）；
   - `entities/`（核心法宝、宗门、地标卡）；
   - `outlines/main_plot.md`（全书故事脊柱）与 `outlines/vol_01/outline.md`（第 1 卷四分位大纲）；
2. **状态表初始化**：
   - 登记 `state/persons.json`, `items.json`, `factions.json`, `places.json`（实体名册四表）；
   - 登记 `state/lines.json`（首卷核心伏笔 GUN-001 与秘密 KNO-001）；
   - 登记 `state/current.json`（开局现场、主角初始随身家底 assets 与装备 equipment）；
   - 登记 `state/locked.json`（不可逆事实 LOCK-001 起号）；
   - 运行 `python studio.py milestone add --title "..." --target-ch N --desc "..."` 登记首卷里程碑；
3. **物理落盘交卷**：调用工具落盘后提交 0B 回执。

### 阶段三：Stage 0C【全息对账与体检闭环 (Architect-Inspector)】
1. **七维拉通核查**：称谓矩阵两两互称无漏水、战力阶级咬合、道具权属无冲突、时间线自洽；
2. **直接工具纠偏**：发现不一致调用 `replace_file_content` 修改对齐；
3. **逻辑纠偏**：利用 LLM 的语义识别能力挖掘并修复暗伤；
4. **体检验证**：在终端运行 `python studio.py check -w "workspace/<书名>"` 确保 **0 errors**（warnings 均为创作参考，无需清零）；
5. 提交 0C 完工回执！**严禁在通过后留恋滞留！**

---

## 🔒 三、 白名单与绝对红线

- 💻 **准跑命令**：`studio.py init`、`studio.py milestone add`、`studio.py check`；
- 📖 **准读输入**：`templates/*` 模板、`bible/*` 设定；
- ✍️ **准写工具**：调用 `write_to_file` / `replace_file_content` 写入文件（**严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁在对话框输出长文本设定（必须工具落盘）；
  - 严禁写小说正文；严禁阅读 `engine/` 源码；严禁编写任何 PowerShell / Python 自查脚本；交卷后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 0 [0A/0B/0C] (Architect)
- 产出路径：workspace/<书名>/[bible/characters/outlines/state]
- 核心指标：设定填实通电 ｜ 0-error 验证通过 ｜ 工具直接物理落盘 ｜ 验收达标无滞留
```
