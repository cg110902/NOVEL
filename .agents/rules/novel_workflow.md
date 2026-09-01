# novel_workflow.md — 通用小说创作流水线标准 SOP（2.0 通用升级版）

本文档定义 Novel Studio 六大创作工序（Stage 0–4，含 Stage 3.5 评审与事实审计）通用创作标准流程、各工序的**输入输出（I/O）契约**与协同规范。

---

## 一、 全流水线阶段输入/输出 (I/O) 契约全景表

| 阶段 | 负责角色 | 📥 必须读取的输入物 (Inputs) | ⚙️ 核心工序动作 (Actions) | 📤 必须交付的产出物 (Outputs) |
|---|---|---|---|---|
| **Stage 0<br/>设定构想** | **主控<br/>(Director)** | • 用户书名、题材、核心脑洞与标签<br/>• 模板库 `templates/` | 初始化工作区，确立世界观/力量体系、核心人物设定（含 Voice Profile 声纹锚定）、单卷节拍矩阵大纲及状态机初始真值。 | • `bible/project_bible.md`<br/>• `characters/*.md` (核心人物声纹)<br/>• `outlines/main_plot.md`<br/>• `outlines/vol_XX/outline.md` (单卷四阶段大纲)<br/>• `state/*.json` (状态机初始真值) |
| **Stage 1<br/>细纲装配** | **主控<br/>(Director)** | • 当前状态速写 `state/current.json`<br/>• 伏笔台账 `state/lines.json`<br/>• 单卷节拍矩阵 `vol_XX/outline.md`<br/>• 前章 Reader 事实简报与 beats 记录<br/>• 细纲模板 `templates/beats.md` | 执行全题材防雷同变轨，组装 2~4 个动态场景切片（Scene Beats），配置多元张力波形与伏笔生命周期，形成高密度交付契约。 | • 当章细纲任务书：<br/>`outlines/vol_XX/beats/ch_XXX.md` |
| **Stage 2<br/>初稿起草** | **起草员<br/>(Drafter)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 上章末尾 500~800 字尾声正文 (pack)<br/>• 上章 300 字剧情梗概 (pack)<br/>• 章初状态速写 `current.json` (pack)<br/>• 人物声纹与实战手册 `craft_drafter.md` | 彻底放飞算力，紧密承接上章尾声，按张力波形推进 2~4 个场景切片，拉满冲突、对白与情绪反差，产出情节饱满的初稿毛坯。 | • 初稿正文文件：<br/>`manuscript/vol_XX/raw/ch_XXX_v1.md`<br/>(纯小说 Markdown，约 2400~3500 字)<br/>• 向主控汇报交付状态 |
| **Stage 3<br/>商业重铸** | **总编精修<br/>(Guard)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 章初状态速写 `current.json`<br/>• 初稿毛坯 `raw/ch_XXX_v1.md`<br/>• 定稿心法 `craft_guard.md` | **100% 专注文学与商业质感重铸**：现代流行商业风深度重写，贯彻**详略得当（高光精描，次要一笔带过）**，物理清剿冷硬词汇与 AI 套话，雕琢句式呼吸感，卡紧章末钩子。 | • 纯净定稿正文文件：<br/>`manuscript/vol_XX/final/ch_XXX.md`<br/>(100% 纯正文，零前言后记)<br/>• 向主控汇报定稿完成情况 |
| **Stage 3.5<br/>读者评审<br/>& 事实审计** | **毒舌评审<br/>(Reader)** | • 定稿正文 `final/ch_XXX.md`<br/>• 当章细纲 `beats/ch_XXX.md`<br/>• 章初状态 `current.json`<br/>• 评审规范 `craft_reader.md` | **客观盲读评审、去水修剪与事实审计**：<br/>1. 商业体验 **5 维雷达打分**（爽点、留钩、声纹、反暗黑、毒点逻辑）；<br/>2. **分级自愈修裁**（L1 微瑕顺手修剪放行，L2 结构缺陷打回 Guard）；<br/>3. **去水字数豁免**（微缩免检）；<br/>4. 客观提取 300~600 字 5 大结构化事实简报。 | • 商业网文体验评审报告<br/>• **300~600 字客观事实简报**（时空剧情、人物状态、道具流水、三类线索、新增实体） |
| **Stage 4<br/>状态封存** | **主控<br/>(Director)** | • Reader 交付的 300~600 字结构化事实简报<br/>• 提案规范 `state/inbox/README.md`<br/>(或通过 `python studio.py proposal new ch_XXX`) | 语义翻译：将 Reader 事实简报 1:1 映射写入增量变更提案 `state/inbox/ch_XXX.json`，运行 `studio.py sync` 触发校验并生成原子快照。 | • 增量提案：`state/inbox/ch_XXX.json`<br/>• 机器真值更新：`state/*.json`<br/>• 归档快照：`snapshots/*_ch_XXX_done` |

---

## 二、 各阶段详细操作规范与推导方法论

### Stage 0: 设定构想与立项（主控 · 策划基石）
- **初始化工程**：运行 `python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"`；
- **核心设定三大基石**：
  1. **世界观与文风定调（`bible/project_bible.md`）**：确立核心法则与题材规则，在语言定调中明确“明快爽朗、主角松弛清朗”文风基准，从源头预防 AI 沉闷暗黑病；
  2. **人物声纹口吻锚定（`characters/*.md`）**：为主要核心角色建立人物卡，填实 Want/Fear、句式语速、**绝对语言禁忌（不会说什么）** 与人际语域切换表；
  3. **单卷节拍矩阵（`outlines/vol_XX/outline.md`）**：依据四阶段通用戏剧结构（建立破局 ➔ 发展深化 ➔ 激化转折 ➔ 高潮兑现）自适应规划整卷总章数与阶段跨度（如 10~30+ 章，划分为 `ch_001—ch_N1` 等动态区间）；
- **状态机播种与两账分离原则**：
  - **单卷大纲记规划**：在 `outlines/vol_XX/outline.md` 中预先规划全卷涉及的伏笔清单（如 GUN-001~GUN-003、KNO-001 等）；
  - **状态机记落盘真值**：开局时 `state/lines.json` 保持初始空账本（`{"foreshadows": [], "misunderstandings": [], "knowledge": []}`），伏笔随着单章推进在 Stage 4 提案中逐章执行 `plant` 入库；
  - **Schema 严格对齐**：`current.json` 严禁多余字段（`key_relationships` 与 `time` 必须为字符串）；`entities.json` 实体简介必须使用 `summary` 字段；`ledger.json` 通货池使用 `initial` 与 `current`（严禁 `balance`）；
- **体检验证**：运行 `python studio.py check` 确保无空槽位与数据硬伤。

### Stage 1: 细纲与任务书装配（主控 · 方法论）
- **Beats 组装推导链路**：
  1. **承接上下文**：读取上一章 Reader 事实简报，确认角色当前物理位置、伤势资源、在场名单与最新知情差；
  2. **定位单卷节拍**：对照 `vol_XX/outline.md` 确定本章在卷节拍中的阶段功能与波峰位置；
  3. **选定章形态与张力波形**：选择合适的 Form（对抗破局、获取养成、人际推拉、探索转场、高潮兑现或题材复合型），指定本章张力波形类型（如爬坡型、高开余波型、智斗波浪型、蓄势型）；
  4. **划分 2~4 个动态场景切片（Scene 切片）**：为每个切片分配具体场景地点、张力标度（1-10）与核心行动冲突；
  5. **编排伏笔多态生命周期**：明确本章涉及的 `GUN-*` / `KNO-*` / `MIS-*` 动作（plant / echo / misdirect / trigger / resolve）；
  6. **确立交付契约**：明确本章核心情绪体验、避坑禁忌与 Reader 验收标准，写入 `outlines/vol_XX/beats/ch_XXX.md`。

### Stage 2: 初稿起草（Drafter 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Drafter", Prompt="...")`，注入细纲与 `studio.py pack ch_XXX` 上下文；
- **输入**：`studio.py pack ch_XXX` 上下文（上章尾声 500~800 字 + 梗概 + 当前状态 + beats）+ `craft_drafter.md`；
- **动作**：
  - 毫秒级承接上章尾声场景，动作、视线与情绪无缝顺延；
  - 依据 Scene 1~N 切片与张力标度推进冲突，严守人物 Voice Profile 声纹口吻；
- **输出**：`manuscript/vol_XX/raw/ch_XXX_v1.md`（纯小说 Markdown，字数约 2400~3500 字）。

### Stage 3: 商业网文重铸（Guard 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Guard", Prompt="...")`，注入初稿路径与重铸心法；
- **输入**：`beats` + `current` + `raw` + `craft_guard.md`；
- **动作**：
  - 大刀阔斧重写、删减水文、优化对白与节奏，物理清洗冷峻词汇与 AI 八股；
  - **贯彻详略得当**：非重点环境道具三五个字一笔带过，集中笔墨精雕高光冲突；
  - 卡紧章末悬念钩子，100% 专注文学与商业爽感；
- **输出**：`manuscript/vol_XX/final/ch_XXX.md`（100% 纯正文，零前言后记）。

### Stage 3.5: 读者评审、去水修剪与事实审计（Reader 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Reader", Prompt="...")`；
- **输入**：`final/ch_XXX.md` + `beats` + `current` + `craft_reader.md`；
- **动作与分级自愈修裁**：
  1. **5 维商业打分与水文扫描**：重点排查跳出式旁白说明、内心反刍与高潮后空洞总结；
  2. **🟢 L1 级微瑕（1-3句多余旁白/微量冷硬词）**：Reader **直接使用 `replace_file_content` 顺手修剪定稿**，直接评为【通过/顺手修剪放行】；
  3. **🔴 L2 级结构缺陷（遗漏核心拍点/重大剧情毒点）**：出具靶向清单打回 Guard 深度重铸；
  4. **字数豁免**：因去水修剪导致的字数微缩直接免检豁免；
  5. **事实审计**：客观提取 300~600 字 5 大结构化事实简报（时空剧情、人物状态、道具流水、三类线索、新增实体）。
- **输出**：商业网文体验评审报告 + 300~600 字结构化事实简报。

### Stage 4: 极速状态同步与快照封存（主控）
- **输入**：Reader 交付的 300~600 字结构化事实简报；
- **实体生命周期分流**：
  - 若为**核心常驻角色**，主控在 `characters/` 补齐人物卡；
  - 若为**次要/临时实体（物品/地点/杂兵）**，直接在 `state/inbox/ch_XXX.json` 的 `entities` 字段声明即可；
- **伏笔与线条动作（Lines Action）规范**：
  - `plant`：仅在正文首次埋设某条线时使用（GUN/MIS/KNO 均支持，重复 plant 会被引擎拒绝）；
  - `remind`：仅用于伏笔回响（**只适用于 `foreshadow`**，KNO/MIS 未揭示/澄清前保持现状即可，无需动作）；
  - `update`：用于更新字段（如修改目标章号 `target_ch` 或权重 `weight`）；
  - `resolve`：用于伏笔回收、秘密揭示或误会澄清；
- **操作流程**：
  1. 将 Reader 简报中的 5 大事实 1:1 映射写入 `state/inbox/ch_XXX.json`；
  2. 运行 `python studio.py proposal check ch_XXX` 进行预检；
  3. 运行 `python studio.py sync ch_XXX` 自动合并状态机真值并生成归档快照。
