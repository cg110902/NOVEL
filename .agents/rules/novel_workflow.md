# novel_workflow.md — 通用小说创作流水线标准 SOP（2.0 升级版）

本文档定义 Novel Studio 六阶段（Stage 0–4，含 Stage 3.5）通用创作标准流程、各工序的**输入输出（I/O）契约**与协同规范。

---

## 一、 全流水线阶段输入/输出 (I/O) 契约全景表

| 阶段 | 负责角色 | 📥 必须读取的输入物 (Inputs) | ⚙️ 核心工序动作 (Actions) | 📤 必须交付的产出物 (Outputs) |
|---|---|---|---|---|
| **Stage 0<br/>设定构想** | **主控<br/>(Director)** | • 用户书名、题材、核心脑洞与标签<br/>• 模板 `templates/` | 初始化工作区，确立境界力量体系、核心人物设定（含 Voice Profile 声纹锚定）与单卷战役节拍矩阵大纲。 | • `bible/project_bible.md`<br/>• `characters/*.md` (含声纹锚定)<br/>• `outlines/main_plot.md`<br/>• `outlines/vol_XX/outline.md` (含战役节拍矩阵)<br/>• `state/entities.json` (初始实体)<br/>• `state/*.json` (状态机播种) |
| **Stage 1<br/>细纲装配** | **主控<br/>(Director)** | • 当前状态速写 `state/current.json`<br/>• 伏笔台账 `state/lines.json`<br/>• 单卷节拍矩阵 `vol_XX/outline.md`<br/>• 前两章 beats 记录 (查 Form 防雷同)<br/>• 细纲模板 `templates/beats.md` | 执行防雷同三大变轨（指定当章 Form、推动大空间位移、设定当章 S1~S3 场景张力心电标度 1-10、编排伏笔多态动作）。 | • 当章细纲任务书：<br/>`outlines/vol_XX/beats/ch_XXX.md` |
| **Stage 2<br/>初稿起草** | **起草员<br/>(Drafter)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 上章末尾 500~800 字尾声正文 (pack)<br/>• 上章 300 字官方剧情梗概 (pack)<br/>• 章初状态速写 `current.json` (pack)<br/>• 人物卡声纹与工艺 `craft_drafter.md` | 彻底放飞算力，按《起草先锋爆发力手册》推进主线冲突、生动对白与反差，依据张力标度顺畅接戏产出毛坯。 | • 初稿正文文件：<br/>`manuscript/vol_XX/raw/ch_XXX_v1.md`<br/>(纯小说 Markdown，无 Artifact 包装)<br/>• 向主控报告字数与交付状态 |
| **Stage 3<br/>商业重铸** | **总编精修<br/>(Guard)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 章初状态速写 `current.json`<br/>• 初稿毛坯 `raw/ch_XXX_v1.md`<br/>• 定稿指南 `craft_guard.md` | **100% 专注文学与商业爽感重铸**：现代流行商业风深度重写，贯彻**详略得当（非重点一笔带过）**，物理清剿冷峻词汇，依据张力雕琢句式，捍卫人物声纹，卡紧章末悬念。**卸除简报撰写负担**。 | • 纯净定稿正文文件：<br/>`manuscript/vol_XX/final/ch_XXX.md`<br/>(100% 纯正文，零前言后记)<br/>• 向主控报告定稿字数与完成状态 |
| **Stage 3.5<br/>读者评审<br/>& 事实审计** | **毒舌评审<br/>(Reader)** | • 定稿正文 `final/ch_XXX.md`<br/>• 当章细纲 `beats/ch_XXX.md`<br/>• 章初状态 `current.json`<br/>• 评审规范 `craft_reader.md` | **客观盲读评审、去水修剪与事实审计**：<br/>1. 商业体验 5 维雷达评分与水文扫描（专项排查跳出式旁白说明与内心反刍）；<br/>2. **分级自愈修裁**（L1 微瑕顺手修剪定稿，L2 结构缺陷打回 Guard）；<br/>3. **字数豁免原则**（去水导致的字数微缩给予免检豁免）；<br/>4. 独立提取 500~800 字 5 大结构化事实简报供主控同步。 | • 商业网文体验评审报告<br/>• **500~800 字左右结构化事实简报**（时空剧情、人物状态、道具流水、三类线索、新增实体） |
| **Stage 4<br/>状态封存** | **主控<br/>(Director)** | • Reader 交付的 500~800 字结构化事实简报<br/>• 提案规范 `state/inbox/README.md`<br/>(或通过 `python studio.py proposal new ch_XXX`) | 语义翻译：将 Reader 事实简报 1:1 映射为增量变更提案，执行 `studio.py sync` 触发引擎校验并生成原子快照。 | • 增量提案：`state/inbox/ch_XXX.json`<br/>• 机器真值更新：`state/*.json`<br/>• 归档快照：`snapshots/*_ch_XXX_done` |

---

## 二、 各阶段详细操作规范

### Stage 0: 设定构想与立项（主控 · 策划基石）
- **初始化工程**：运行 `python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"`；
- **核心设定三大基石（从源头注入 SOTA 规范）**：
  1. **世界观与文风定调（`bible/project_bible.md`）**：确立升级阶梯与核心法则，在偏离清单中明确“明快爽朗、主角松弛幽默”文风基准，从源头预防 AI 沉闷暗黑病；
  2. **人物声纹口吻锚定（`characters/*.md`）**：为核心人物填实 Want/Fear、句式语速、**绝对语言禁忌（不会说什么）** 与人际语域切换表；
  3. **单卷战役节拍矩阵（`outlines/vol_XX/outline.md`）**：按四阶段商业波峰模型（建立破局 ➔ 积累暗流 ➔ 冲突激化 ➔ 总攻决胜）规划整卷战役节奏；
- **状态机播种**：在 `state/entities.json`、`state/current.json`、`state/lines.json`、`state/ledger.json` 播种初始真值；
- **体检验证**：运行 `python studio.py check` 确保无空槽位与数据硬伤。

### Stage 1: 细纲与任务书装配（主控）
- **依据战役节拍矩阵定位**：对照 `vol_XX/outline.md` 确定本章在卷战役中的波峰位置；
- **变轨一（通用章形态轮转）**：明确指定 `form`，连续 3 章严禁使用相同形态；
- **变轨二（物理场景大位移）**：每 1-2 章推动角色转移空间场景；
- **变轨三（起手与结尾钩子变轨）**：轮转起手切入方式与章末悬念类型；
- **配置张力心电标度**：为 S1~S3 拍点打上 `[张力 1-10]` 梯度，指导后序工序节奏。

### Stage 2: 初稿起草（Drafter 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Drafter", Prompt="...")`，注入细纲与 `studio.py pack ch_XXX` 上下文；
- **输入**：`studio.py pack ch_XXX` 上下文（上章尾声 500~800 字 + 梗概 + 当前状态 + beats）+ `craft_drafter.md`；
- **输出**：`manuscript/vol_XX/raw/ch_XXX_v1.md`。

### Stage 3: 商业网文重铸（Guard 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Guard", Prompt="...")`，注入初稿路径与重铸心法；
- **输入**：`beats` + `current` + `raw` + `craft_guard.md`；
- **动作**：
  - 大刀阔斧重写、删减水文、优化对白与节奏，物理清洗冷峻词汇；
  - **贯彻详略得当**：非重点环境道具一笔带过，集中笔墨精雕核心反杀与破防瞬间，100% 专注文学质量；
- **输出**：`manuscript/vol_XX/final/ch_XXX.md`（100% 纯正文，零前言后记）。

### Stage 3.5: 毒舌读者评审、去水修剪与事实审计（Reader 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Reader", Prompt="...")`；
- **输入**：`final/ch_XXX.md` + `beats` + `current` + `craft_reader.md`；
- **动作与分级自愈修裁**：
  1. **5 维商业打分与去水扫描**：重点扫描跳出式旁白说明、内心反刍与高潮后空洞总结；
  2. **🟢 L1 级微瑕（1-3句多余旁白/微量冷硬词/标点）**：Reader **直接使用 `replace_file_content` 顺手修剪定稿**，直接评为【通过】，秒级放行；
  3. **🔴 L2 级结构缺陷（漏拍点/大段打斗拖沓）**：出具靶向清单打回 Guard 深度重铸；
  4. **字数豁免**：因去水修剪导致的字数微缩直接免检豁免；
  5. **事实审计**：独立提取 500~800 字 5 大结构化事实简报（时空剧情、人物状态、道具流水、三类线索、新增实体）。
- **输出**：商业体验评审报告 + 500~800 字结构化事实简报。

### Stage 4: 极速状态同步与快照封存（主控）
- **输入**：Reader 交付的 500~800 字结构化事实简报；
- **操作流程**：
  1. 将 Reader 简报中的 5 大事实 1:1 映射写入 `state/inbox/ch_XXX.json`；
  2. 运行 `python studio.py proposal check ch_XXX` 进行预检；
  3. 运行 `python studio.py sync ch_XXX` 自动合并状态机并生成归档快照。
