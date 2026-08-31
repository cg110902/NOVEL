# novel_workflow.md — 通用小说创作流水线标准 SOP

本文档定义 Novel Studio 5 阶段（Stage 0–4）通用创作标准流程、各工序的**输入输出（I/O）契约**与协同规范。

---

## 一、 全流水线阶段输入/输出 (I/O) 契约全景表

| 阶段 | 负责角色 | 📥 必须读取的输入物 (Inputs) | ⚙️ 核心工序动作 (Actions) | 📤 必须交付的产出物 (Outputs) |
|---|---|---|---|---|
| **Stage 0<br/>设定构想** | **主控<br/>(Director)** | • 用户书名、题材、核心脑洞与标签<br/>• 模板 `templates/` | 初始化工作区，确立境界力量体系、核心人物设定与四卷主线大纲。 | • `bible/project_bible.md`<br/>• `characters/*.md`<br/>• `outlines/main_plot.md`<br/>• `outlines/vol_XX/outline.md`<br/>• `state/entities.json` (初始实体) |
| **Stage 1<br/>细纲装配** | **主控<br/>(Director)** | • 当前状态速写 `state/current.json`<br/>• 伏笔台账 `state/lines.json`<br/>• 前两章 beats 记录 (查 Form 防雷同)<br/>• 细纲模板 `templates/beats.md` | 执行防雷同三大变轨（指定当章 Form、推动大空间位移、设定当章 S1~S3 拍点与强钩）。 | • 当章细纲任务书：<br/>`outlines/vol_XX/beats/ch_XXX.md` |
| **Stage 2<br/>初稿起草** | **起草员<br/>(Drafter)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 上章末尾 500~800 字左右尾声正文 (pack)<br/>• 上章 300 字左右官方剧情梗概 (pack)<br/>• 章初状态速写 `current.json` (pack)<br/>• 出场人物极简卡摘要 (pack P1) | 彻底放飞算力，无禁词束缚，专注推进主线冲突、塑造生动对白与反差、顺畅接戏，产出毛坯初稿。 | • 初稿正文文件：<br/>`manuscript/vol_XX/raw/ch_XXX_v1.md`<br/>(纯小说 Markdown，无 Artifact 包装)<br/>• 向主控报告字数与交付状态 |
| **Stage 3<br/>商业重铸** | **总编精修<br/>(Guard)** | • 当章细纲 `beats/ch_XXX.md`<br/>• 章初状态速写 `current.json`<br/>• 初稿毛坯 `raw/ch_XXX_v1.md`<br/>• 定稿指南 `.agents/rules/craft_guard.md` | 深度重写与精修（2026 番茄现代风），去无效景物，润色对白机锋，清剿“极”字与套话，卡紧章末悬念。 | • 纯净定稿正文文件：<br/>`manuscript/vol_XX/final/ch_XXX.md`<br/>(100% 纯正文，零前言后记)<br/>• 交付 **500~800 字左右结构化事实简报** |
| **Stage 4<br/>状态封存** | **主控<br/>(Director)** | • Guard 交付的 500~800 字左右结构化事实简报<br/>• 提案样例规范 `state/inbox/README.md`<br/>(或通过 `python studio.py proposal new ch_XXX` 自动装配骨架) | 语义翻译：将简报 1:1 映射为增量变更提案，执行 `studio.py sync` 触发引擎校验并生成原子快照。 | • 增量提案：`state/inbox/ch_XXX.json`<br/>• 机器真值更新：`state/*.json`<br/>• 归档快照：`snapshots/*_ch_XXX_done` |

---

## 二、 各阶段详细操作规范

### Stage 0: 设定构想与立项（主控）
- 运行 `python studio.py init -w workspace/<slug> -t "书名" -g "题材" -p "主角名"`；
- 填充 `bible/`、`characters/` 与 `outlines/`；
- 运行 `python studio.py check` 确保无空槽与数据硬伤。

### Stage 1: 细纲与任务书装配（主控）
- **变轨一（通用章形态轮转）**：明确指定 `form`，连续 3 章严禁使用相同形态；
- **变轨二（物理场景大位移）**：每 1-2 章推动角色转移空间场景；
- **变轨三（起手与结尾钩子变轨）**：轮转起手切入方式与章末悬念类型。

### Stage 2: 初稿起草（Drafter 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Drafter", Prompt="...")`，注入细纲与 `studio.py pack ch_XXX` 上下文；
- **输入**：`studio.py pack ch_XXX` 提供的上下文（上章尾声 500~800 字左右 + 梗概 + 当前状态 + beats）；
- **输出**：`manuscript/vol_XX/raw/ch_XXX_v1.md`。

### Stage 3: 商业网文重铸（Guard 子代理）
- **调度方式**：主控调用 `invoke_subagent(TypeName="self", Role="Guard", Prompt="...")`，注入初稿路径与重铸心法；
- **输入**：`beats` + `current` + `raw` + `craft_guard.md`；
- **输出**：
  1. `manuscript/vol_XX/final/ch_XXX.md`（100% 纯正文）；
  2. 500~800 字左右结构化事实简报（时空剧情、人物状态、道具流水、三类线索、新增实体 5 大项）。

### Stage 4: 极速状态同步与快照封存（主控）
- **输入**：Guard 500~800 字左右结构化事实简报；
- **操作流程**：
  1. 运行 `python studio.py proposal new ch_XXX`（或 `auto ch_XXX`）生成标准增量骨架；
  2. 将 Guard 简报中的 5 大事实 1:1 映射写入 `state/inbox/ch_XXX.json`；
  3. 运行 `python studio.py proposal check ch_XXX` 进行预检；
  4. 运行 `python studio.py sync ch_XXX` 自动合并状态机并生成归档快照。
