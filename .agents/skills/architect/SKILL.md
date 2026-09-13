---
name: novel-architect
description: Universal worldbuilding architect and setup generator for Novel Studio (Stage 0). Covers all genres. Builds project bible (Stage 0A), MVU character cards & outlines, initial state tables (Stage 0B), and holographic verification (Stage 0C).
---

# SKILL — novel-architect（全题材开局架构师专属手册 · Stage 0 筑基指南）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定书名、题材、主角名与核心创意。**读取本手册仅限首步 1 次，严禁反复回读倒嚼！严禁漫游目录！**
> 任何题材（都市、科幻、历史、悬疑、玄幻等）皆按本手册通用法则推导。
> 起手**必须直接执行工具操作！** 彻底消灭所有 `{{slot:}}` 占位符与模板 `<!-- ... -->` 注释，
> 交付 MVU 六件套并完成状态机六表通电，以工具物理落盘（**严禁传递 `ArtifactMetadata`**），`check` 0 报错后输出 3 行回执即刻交卷，绝不滞留！

---

## 🎯 一、 你的唯一任务（从 0 到 1 筑基并完全通电）

在独立沙盒中分三步推进，交付全书物理与数据底座：
1. **Stage 0A**：跑 `studio.py init`，依据作者脑洞填实 `bible/` 圣经六表与 `project.json`（消除 `{{slot:}}` 与注释）；
2. **Stage 0B**：交付“冷启动最小可用宇宙 (MVU 六件套)”，完成 `state/` 六表全息通电；
3. **Stage 0C**：跑 `studio.py check` 确保 **0 errors**，大模型三棱镜常识逻辑扫荡，闭环交卷！

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

### 步骤 1：Stage 0A【世界观公理与设定筑基 (Architect-World)】
1. **运行初始化命令**：
   ```powershell
   python studio.py init -w "workspace/<书名>" -t "<书名>" -g "<题材>" -p "<主角名>"
   ```
2. **填实圣经六表与 `project.json`**（消灭所有 `{{slot:}}`，删除模板自带的 `<!-- ... -->` 指南注释）：
   - `bible/01_world_axioms.md`：
     - **Logline**：公式 `[主角身份/处境] 在 [危机背景] 中，依靠 [核心不对称优势]，对抗 [核心阻碍]，实现 [主线目标]`；
     - **空间三层**：基础层（新手舞台） ➔ 中进层（中盘舞台） ➔ 极顶层（终局舞台）；
     - **3~5 条底层公理**：客观物理/社会法则，必须标明破坏法则时的反噬代价；
     - **金手指四要素闭环**：机制原理 + 消耗/代偿代价 + **当前阶段绝对做不到的事（防开局无敌崩张力）** + 升级阶梯。
   - `bible/02_power_system.md`：
     - **Tier 1~5 实力梯阶与实物标尺**：用具体的受力形变、武器防御阈值、调动规模或账户量级说话，**绝对禁止使用“恐怖如斯/深不可测”等空洞形容词**；
     - **越级反杀支点**：写明主角凭借何种确凿物理机制（信息差/克制道具/弱点打击）跨阶克敌，严禁唯心爆种。
   - `bible/03_factions_geography.md`：地理版图；三大核心势力与真实利益冲突（争夺资源/市场/生存/理念），拒绝无脑恶霸。
   - `bible/04_economy_items.md`：
     - **购买力平价 (PPP) 锚定**：锁定 1 单位（底层日常口粮）、100 单位（体面家当/精良装备）、百万/千万级（撬动世界格局的战略极值）的实物比率；
     - **道具五阶与损耗法则**：凡/良/珍/绝/神，明确使用代价、充能上限与持有者唯一性。
   - `bible/05_special_mechanics.md`：题材独家风味机制（如竞业协议/义体排异/宗法礼制/灵异规则/心魔劫等）及负荷代偿。
   - `bible/06_deviations.md`：本书反俗套偏离清单，推翻同题材中最烂俗的 3~5 个套路（起草员创作高压线）。
   - `project.json`：填实必填字段，配置题材专属停用词与悬念钩子词种子。

### 步骤 2：Stage 0B【冷启动 MVU 六件套与状态机通电 (Architect-Story & Energization)】
严禁建 100 张虚无废卡！必须严格交付 **MVU 六件套** 并立即执行 **状态机六表全息通电**：
1. **MVU 六件套交付清单**：
   - 👤 **1. 主角专属卡 (`characters/protagonist.md`)**：Front-matter 规范闭环、心理四维（Want 眼前欲望/Need 灵魂渴求/Fear 致命软肋/Lie 认知谎言）、触碰必死的绝对逆鳞、专属习惯微动作库（去冷脸面瘫）、恒定称谓矩阵；
   - 👥 **2. 关键搭档/女主卡 (`characters/<搭档名>.md`)**：独立生存诉求，锁定与主角的法定互称；
   - 🦹 **3. 首卷核心对手卡 (`characters/<对手名>.md`)**：合理的利益争夺或生存避险动机，拒绝无脑送人头；
   - ⚔️ **4. 核心道具/法宝卡 (`entities/items/<道具名>.md`)**：明确 `holder: "主角名"`、品阶、剩余充能 `charges`、单次代价 `cost_per_use`；
   - 🏰 **5. 核心初始势力卡 (`entities/factions/<势力名>.md`)**：掌权人 `leader`、总部 `headquarters`、危险等级 `danger_level`；
   - 🗺️ **6. 开局场景/地点卡 (`entities/locations/<地名>.md`)**：长宽空间物象、特殊环境法则 `environment_rules`；
   - 📖 **7. 大纲双件套**：`outlines/main_plot.md`（三幕主干脊柱）与 `outlines/vol_01/outline.md`（首卷四分位大纲）。
2. **状态机六表全息通电规约**（卡片写完必须同一轮写入 `state/`，严禁留空）：
   - `persons.json`, `items.json`, `factions.json`, `places.json`：注册对应实体，设好对应属性；
   - `current.json`（开局第一现场）：填实 `time`（开局动笔时刻）、`location`（对齐地点卡）、`situation`（一句话危机处境）、`power_level`（主角初始层级）、`equipment`、`assets`、`present_characters`（第1章开场在场人）、`loadout`（四件套：职业核心、机动手段、对抗招式、绝杀底牌）；
   - `lines.json`：埋设首卷贯穿暗线 `GUN-001`、机密知情差 `KNO-001`、外界认知偏差 `MIS-001`；
   - `locked.json`：登记世界运转或主角身上不可撤销的既定事实 `LOCK-001`；
   - `ledger.json`：在 `pools` 中声明本题材需记账的货币池（如 `"stone": {"name": "下品灵石", "unit": "枚", "initial": 0, "current": 0}`）；
   - 命令行添加首卷破局里程碑：
     ```powershell
     python studio.py milestone add --title "完成开局破局首战" --target-ch 5 --desc "粉碎开局危机，夺回核心主动权"
     ```

### 步骤 3：Stage 0C【全息双轨审查与闭环交卷 (Architect-Inspector)】
1. **第一轨【机器硬闸门 · 必须 0 errors】**：
   - 终端运行：`python studio.py check -w "workspace/<书名>"`；
   - 零容忍项：未填槽位 `unfilled_slot` 必须为 0（彻底消除 `{{slot:...}}` 与 `<!-- ... -->` 注释）；未注册角色 `unregistered_character` 必须为 0；`project.json` 必填项严禁留空。
2. **第二轨【大模型三棱镜常识逻辑扫荡（LLM自带语义识别和内容理解功能）】**：
   - 因果时空尺度自洽、经济购买力平价自洽、人性利益避险与动机自洽。
3. **闭环交卷**：调用 `replace_file_content` 修复微瑕，复跑 `check` 确认 **0 errors**，输出 3 行回执即刻交卷！

---

## 🔒 三、 白名单与绝对红线

- 💻 **准跑命令**：`studio.py init`、`studio.py milestone add`、`studio.py check`；
- 📖 **准读输入**：`templates/*` 模板、`bible/*` 设定、`state/*` 数据；
- ✍️ **准写工具**：调用 `write_to_file` / `replace_file_content` 写入（**严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁在对话框输出长篇大论的世界观设定小说（必须直接调用工具物理落盘）；
  - 严禁擅自编写任何 PowerShell / Python 自查脚本；
  - 严禁窥探或修改 `engine/` 源码；
  - 严禁遗留任何 `{{slot:...}}` 占位符；
  - 严禁建卡不给 `state/` 通电；
  - `check` 0 报错通过后立即交卷，严禁留恋滞留！

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 0 [0A/0B/0C] (Architect)
- 产出路径：workspace/<书名>/[bible/characters/entities/outlines/state]
- 核心指标：MVU六件套落盘 ｜ 状态机六表通电 ｜ 0-slot 0-error 验证通过 ｜ 验收达标无滞留
```
