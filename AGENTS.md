# AGENTS.md — Novel Studio 核心宪法（Antigravity 通俗网文全题材通用版 · AI 向）

Novel Studio 是专为网络小说多智能体协同深度定制的创作流水线框架（全题材通用）。
架构哲学：**大模型全权掌控创意脑洞、生动情节与通俗叙事；确定性引擎负责事实底座与数据台账；原生 Subagents 实现高效工序接力与闭环归档。**

> 🏆 **【最高网文语感规范】**：
> **绝不追求虚浮晦涩的所谓“纯文学质感”！读者是来爽读网文的，不是来啃生涩教材的！**
> 全流程核心准则：**通俗直白大白话、极度易读、极好扫读、无认知门槛、一口气读完停不下来！**

> ⚖️ **【事实与创作分离规范】**：
> 创作可以脑补，事实必须对账——事实唯一源头 = `final` 定稿正文；
> 状态唯一真值 = `state/` 十一表（含不可逆事实表与认知差表）；
> 一致性由引擎机械闸门与 Auditor 三轨核验兜底（机械探针 + 细纲语义清单 + 语义逻辑与出戏审查）。

> 🧰 **【开工前置：运行环境】**：引擎依赖 5 个第三方库，缺失时 `studio.py` 会在启动瞬间
> 打印缺失模块与安装命令并以退出码 `3` 退出（不是业务问题，不要去改书）。
> ```bash
> python -m pip install -r requirements.txt   # pydantic / jieba / networkx / rich / rapidfuzz
> python studio.py --version                   # 自检：应打印 novel-studio 3.x
> ```
> 用虚拟环境时务必用该环境的 python 跑（`.venv/bin/python studio.py …`），
> 否则会拿系统解释器去找依赖。退出码契约：`0` 正常 / `1` 业务阻断 / `2` 用法错 / `3` 环境缺依赖。

---

## 一、 技术底座速览（黑盒边界）

以下能力全部封装在确定性引擎（`engine/`，黑盒）内，各角色只经 CLI 消费、禁知实现源码：

- **强类型状态机**：Pydantic V2 十一表真值（current / persons / items / factions / places / lines / timeline / ledger / synopsis / locked / cognition）；提案（proposal）为**章节事实增量**的唯一写入口，过 schema 校验、引文柔性接地、幂等登记、复式记账重算四道闸（设定层例外：Stage 0 建书播种与跨卷改版由 architect/evolver 直接写 `state/*.json`；每次 sync 会对十一表盖章 SHA-256，绕过提案的离线手改由 `check` 的 `state_offline_edit` 档指名报出）；
- **命令面（31 个命令名 / 30 个处理函数）**：`python studio.py help --json` 是命令目录、阶段配方与退出码契约的唯一自查入口——含 lore 底层词典与实体知识库速查对账、cockpit 态势驾驶舱、check 事实体检、audit 确定性机械探针、recall 残酷四问自证、simulate 剧情推演沙盒、milestone 主线里程碑管理、sync 状态封存、ledger recompute 账本修复、snapshot 回滚、state at/diff/blame 时点切面与字段级溯源、
state rollup 卷末态势摘要（pack 前情注入源）、reconcile 卷末对账大修（机械复扫+投影 diff 工作单）、
check --trend 分数曲线 / --bisect 快照二分等；
- **读者记忆轴（advisory）**：以正文落笔史推导读者印象——线温分层（hot/warm/cold，阈值按 weight 缩放）、
零落笔线（line_never_surfaced）、冷线计划回收提醒（line_recall_cold，pack/beats 侧另有「先锚定再兑现」操作提示）、
关键事实久未重现（locked/已揭示 knowledge）、对白声纹漂移（voiceprint_drift：句长/语气词/口头禅，
只测「怎么说话」不测人设）；全部不阻断，阈值走 `project.json` 的 `reader_memory` / `voiceprint` 键
（PARAM_SPEC 单一真源）；
- **规模经济**：changelog 事件溯源（state at 重放任意章切面 / blame 字段级溯源 / external_edit 自愈补录）、
卷级 rollup（前情态势 ≤1000 token 注入 pack，装配成本 O(当前卷)）、卷末 reconcile 对账大修（投影误差的周期性维护）；
- **装配预算契约**：`pack` 预算 token 总量上限 **2W**；超预算按压缩阶梯由远及近裁
  （P2 冷索引 → P2 旧章指针 → P1 间接关联 → P1 脊柱 → P0 上章余温），**beats 全文 / current / 硬提醒 /
  不可逆事实 / 钉住的世界锚点永不自动裁**；世界锚点支持按章取用（beats front-matter `world_refs`：
  未声明＝恒给、命中＝只装命中节并对漏掉的基础组打 ⚠️、零命中＝回退恒给并列「可钉的节」）；**refs 最多取前 8 个**（`MAX_WORLD_ANCHOR_REFS`，超出忽略并点名——
  钉太多＝恒给，收窄就失去意义）；P2 冷索引按角色准读网关过滤，被禁文件只报数量不报路径（杜绝"提示去 open 必被拒"）；
- **装配包面（Drafter 的全部输入）**：P0＝`current` 块（含 loadout 中文名）＋卷段里程碑＋`world_anchors`＋
  **beats 逐字全文**＋`prev_tail`＋`hard_reminders`＋`aftershock`（上章 `locked` 代价回灌）；
  P1＝`entities`（脊柱＋`trace` 近 3 章）＋`indirect`（图 2-hop）＋`spine`（脊柱尾 3 条）；P2＝`old_chapter_pointers`＋`file_index`；
  `--lean` 只给 P0、`--full` 全三层。**不装**：raw 草稿、`state/` 其余 6 表（ledger/timeline/cognition 等）、`log/` 下所有 .md（bible 只装锚点节）；
  需要"人物当前态"走 5 档只读视图：`state get` / `state at <章>` / `ledger balance` / `pov <人>` / `recall <人>`；
- **强援库**：jieba（专名与词频）、networkx（实体拓扑寻路）、rapidfuzz（引文模糊接地）、rich（终端渲染）、sqlite3（FTS5 检索加速）。

---

## 二、 角色矩阵与权限协同体系

所有 Subagents 独立读取自身 `.agents/skills/<角色>/SKILL.md` 开展作业，主控仅负责下发 4 行派发令并验收 3 行完工回执。

| 角色 | 形式 | 负责阶段 | 核心职责与严格边界 |
|---|---|---|---|
| **主控 (Director)** | 宿主主代理 | 全局统筹 / Stage 1 / Stage 5 | **全局统筹、意图分流、前置事实提炼、双核体检与状态封存**：识别用户意图（开新书派发 Architect 0A/0B，继续写驾驶舱秒接，改设定/改正文定向派发 Evolver，自然语言问诊查账零Token本地CLI秒回或临时沙盒轻重分流）；细纲构思（金牌总编剧四步破局心法）；轻量星形调度流水线；执行 `sync` 状态原子封存。 |
| **架构师 (Architect)** | 原生子代理 | Stage 0A / 0B（仅开新书触发） | **开局世界观与宏观大纲架构师**：纯粹 Greenfield 宏观造物主，开新书时执行双子星阶梯接力（0A 筑基世界公理 `bible/01~07` ➔ 0B 编织人物大纲并完成十一表通电）。独立沙盒运行，落盘即交卷，为主控保持 100% 纯净算力。 |
| **起草员 (Drafter)** | 原生子代理 | Stage 2 | **剧情爆发起草先锋**：放飞算力与想象力；**严格继承细纲预提炼的称谓、前情事实与知情差**，以通俗大白话展开核心场景，将戏剧目标转化为初稿毛坯 `raw/ch_XXX_v1.md`（字数 2000~3000+）。恪守准读清单，落盘即交卷。 |
| **精修师 (Editor)** | 原生子代理 | Stage 3A | **骨肉重塑与事实对账**：以充实剧情血肉为导向；**负责做足剧情加法**（展开场景交锋、丰富人物互动温度、重塑对话潜台词、缝合转折气口；准读在场核心角色卡与 `06_style_guidelines.md`）；产出通俗大白话初修骨肉稿 `raw/ch_XXX_v2.md`。 |
| **脱水师 (Stylist)** | 原生子代理 | Stage 3B | **通俗脱水、去冷脸与扫读优化**：以极度易读、方便扫读、通俗直白为导向；首行规范输出章题；以 `06_style_guidelines.md` 为基线，**负责做足减法与表情动作去僵化**（切除动作后反刍总结、消除主角冷脸与神色淡然套路、比喻脱水白描化、确保遣词造句自然准确），直接落盘全书法定定稿 `final/ch_XXX.md`。 |
| **审计员 (Reader)** | 原生子代理 | Stage 4 (并行轨 A) | **精益事实审计与动态演进提取**：以 final 为唯一事实源，客观提取核心事实（现场在场、动态关系与称谓演进、关键新实体、线索动作、大额收支、不可逆事实），装配严格符合 Pydantic V2/V3 Schema 的标准增量提案 JSON（v2 分区 / v3 寻址 ops 二选一） (`state/inbox/ch_XXX.json`)。 |
| **催更员 (Critic)** | 原生子代理 | Stage 4 (并行轨 B) | **追更老白催更便签（专供下章参考）**：扮演十年老白追更读者盲审 final 正文，评估疲劳度与活人感，输出 200~500 字催更便签 `log/critic/ch_XXX.md`，直供下章细纲构思。落盘即交卷。 |
| **仲裁员 (Auditor)** | 原生子代理 | Stage 4 (并行轨 C) | **三轨一致性仲裁（机械探针 + 细纲语义清单 + 语义逻辑与出戏审查）**：先运行 `python studio.py audit ch_XXX --write` 由引擎生成**带 YAML front-matter（`hard`/`soft`/`logic`/`adjudicated`）的仲裁报告骨架**，再基于 8 大确定性机械探针与细纲预提炼清单逐行对校称谓与修饰词漂移；**并独立执行轨 3**——用 LLM 的语义理解查读者会当场出戏的破绽（世界观类目污染、违背世界公理、人物性格突变、因果与代价断链、现场常识与时空矛盾），这类问题 `check`/`audit` 探针**结构上不可能发现**，只有你能抓。裁决补写至 `log/audit/ch_XXX.md`（缺 front-matter 将被 Stage 5 闸门拒绝封存）。🔴 硬矛盾与 🧠 确凿出戏（`logic>0`）**同闸阻断**：正文层下定向手术刀令给 Stylist，设定层/历史正文层转办 Evolver，严禁自行改 bible；🟡 软性存疑不阻断，但须逐条标 S1/S2/S3 出口后随回执上报。 |
| **图书管理员 (Librarian)** | 原生子代理 | Stage 4D (每10章低频巡查) | **十年长程事实巡检与账目平账**：每 10 章执行一次深度巡检，通读近 10 章定稿，清查遗漏次要实体、法宝道具充能漏扣与生死状态，把修补直接并入当章在途提案 `state/inbox/ch_XXX.json`；卷末跑 `python studio.py reconcile vol_XX --write` 生成对账工作单并按清单裁决（投影 diff：未登记专名 / 零出现实体）。 |
| **重构师 (Evolver)** | 原生子代理 | Stage Evolution (中途随时触发) | **剧情外科主任与演进重构总监**：专职承接人类作者全生命周期中途提出的**任何变更诉求**（改设定、改历史正文段落、改人物设定、改事件因果、开辟新卷地图等）。负责波及面测算、快照先行、跨层手术刀修改与十一表平账（`ledger recompute`, `check`）。独立沙盒运行，落盘即交卷。 |

---

## 三、 创作工序流水线

```mermaid
graph TD
    S0A["Stage 0A: 世界观公理筑基<br/>(Architect-World: project.json + bible/ 冻结底座)"] --> S0B["Stage 0B: 人物大纲编织与通电<br/>(Architect-Story: characters/outlines/state/)"]
    S0B --> S1["Stage 1: 细纲构思与前置事实提炼<br/>(主控: 金牌总编剧四步破局心法)"]
    S1 --> S2["Stage 2: 初稿起草<br/>(Drafter: 场景展开 + 继承事实 -> raw_v1)"]
    S2 --> S3A["Stage 3A: 骨肉重塑<br/>(Editor: 剧情做加法 + 对话/气口/事实对账 -> raw_v2)"]
    S3A --> S3B["Stage 3B: 通俗脱水与扫读优化<br/>(Stylist: 减法去油 + 去冷脸/去反刍/精准白描 -> final)"]
    S3B --> S4A["Stage 4A: 事实审计<br/>(Reader: 增量状态与动态演进提案)"]
    S3B --> S4B["Stage 4B: 催更便签<br/>(Critic: 读者体感+期待)"]
    S3B --> S4C["Stage 4C: 三轨一致性仲裁<br/>(Auditor: 机械探针 + 细纲语义清单 + 🧠 语义逻辑与出戏审查)"]
    S4C -. "🔴 硬矛盾 / 🧠 logic>0 确凿出戏与世界观矛盾" .-> S4Patch["定向手术刀修复<br/>(Stylist: 精准替换冲突单行；设定层冲突转办 Evolver)"]
    S4Patch -. "修复后必须复审：重跑 audit --write<br/>(硬矛盾段落未变则沿用既有 adjudicated)" .-> S4C
    S4Patch --> S4A
    S4A --> S5["Stage 5: 状态同步与动态基准更新<br/>(主控: 原子合并/封存快照/新状态生效)"]
    S5 --> S4D["Stage 4D: 长程事实巡检（每 10 章一次）<br/>(Librarian: 近 10 章定稿 vs 四张台账平账)"]
    S4D -. "遗漏实体/漏扣充能/生死错账并入在途提案" .-> S5
    S4Patch -. "已知取舍：Critic 便签不随手术刀重跑" .-> S4B
    S4B -. "下章参考便签" .-> S1
    S5 --> S6["🎉 最终成品交付: final/ch_XXX.md<br/>(交付作者终审)"]

    UserChange["人类变更诉求<br/>(改设定/改历史正文/改人设/改情感)"] -.-> SEvolution["Stage Evolution: 演进重构总监<br/>(Evolver: 波及面测算 + 手术刀修改 + 十一表平账)"]
    SEvolution -. "平账后无缝对接" .-> S1
```

> 📜 **beats = 当章唯一合同**：由主控写（`beats new` 预填机器事实），Editor / Stylist / Reader / Auditor
> 四路子代理**直读**，Drafter 经 `pack` P0 拿到**逐字全文**，Critic 与 Librarian 明令**禁读**
> （前者要纯读者盲审、后者只对账不读意图）。动机：`state/` 只知"已发生什么"、不知"本章要写什么"，
> beats 把 bible + 台账 + 本意压成 O(1) 的当章快照，让五个下游共享同一基准而不必各翻账本；
> 代价是它同时是最大注入物与最脆单点——**细纲写虚，整条流水线一起歪**，故引擎对其有 5 档 `beats_*`
> 闸门与 `sync` 的"beats 齐"硬合同（`goal`/`hook` 无机械校验，虚写只能靠下游上报）。引擎注入的 `## 本章一致性速查`、`### 💰 资源池与 ID 水位线`、`### 📐 提案通道与键形状` 三节
> 是 Reader 的**唯一**契约来源（其网关禁读 `state/`，故不得要求其阅读 `state/inbox/README.md`）。

---

## 四、 双向极简工序协议（跨角色 · Canonical）

> 💡 **双向极简规范**：主控下发 4 行派发令（严禁拷贝细纲全文或重复背诵工艺规则）；子代理上报 3 行回执单（严禁长篇汇报闲聊，杜绝主控上下文膨胀）。子代理技能卡内的回执细则以本协议为总纲。

- **下达 · 4 行标准工序派发令**（主控发给 Subagent）：
  ```text
  【章节工序派发令】
  - 书籍工作区：workspace/<书名>
  - 分卷与章节：vol_XX / ch_XXX
  - 执行阶段：Stage X (<角色名>: <阶段职责>)
  - 执行纪律：严格按你的 SKILL.md 执行。恪守准读清单与准写路径，落盘即止，严禁自查与编写脚本。
  ```
- **上报 · 3 行标准完工回执单**（Subagent 交卷给主控）：
  ```text
  【章节工序完工回执】
  - 完工阶段：Stage X (<角色名>)
  - 产出路径：[目标文件相对路径]
  - 核心指标：[字数/核心指标/状态] ｜ 零脚本直接落盘 ｜ 验收达标无滞留
  ```

---

## 五、 开工认知与意图分流协议

主控在收到人类作者指令时，按以下认知与意图网关执行分流：

### 1. 🌟 意图 A：【开新书 / 新建项目 / 构思新设定】
- 接收核心脑洞（书名、题材、主角金手指、核心爽点）；
- **启动 Stage 0 双子星阶梯接力**：
  1. 主控下发 **Stage 0A 派发令给 `Architect`**（世界观公理筑基：生成 `project.json` 与 `bible/01~07`，落盘即冻结物理底座）；
  2. Stage 0A 完工唤醒后，主控下发 **Stage 0B 派发令给 `Architect`**（以冻结 bible 为硬基准，生成 `characters/`、`entities/` 与 `outlines/`，并完成状态十一表通电）；
- `Architect` 0B 交卷后，主控运行 `python studio.py check` 与 `cockpit --json` 接入新书驾驶舱，向人类呈现世界观纲要供终审确认。

### 2. 🚀 意图 B：【继续写 / 创作下一章 / 推进工程】
- **核验 `workspace/` 目录**：
  - 若 `workspace/` 为空 ➔ 提示当前尚无工程，引导发起“开新书”；
  - 若存在多部书籍 ➔ 列出所有书名，主动询问作者意向；
  - 若仅有单本书（或已指定） ➔ 运行 `python studio.py cockpit --json` 秒级接入驾驶舱，直通 Stage 1 细纲构思！

### 3. 🛠️ 意图 C：【中途变更与演进重构】
- **触发场景**：人类作者提出任何维度的修改需求（改设定、改历史正文、改人设称谓、改事件因果、开启新地图或引入新核心实体）；
- **派发机制**：主控下达 **Stage Evolution 派发令给 `Evolver`（演进重构师）**；
- **执行闭环**：`Evolver` 独立完成因果研判、防御快照、跨层手术刀修改与十一表平账（`ledger recompute`, `check`）；
- 交卷后主控接入驾驶舱汇报平账明细，无缝推进后续创作。

### 4. 🩺 意图 D：【自然语言问诊、查账与深度研判】
- **零 Token 认知准则**：所有本地确定性命令（`check`, `doctor`, `lore`, `pov`, `calendar`, `cockpit` 等）由本地算法运算，**0 Token 消耗**；
- **分流机制（双层防御，主控大脑绝缘保护）**：
  - ⚡ **Tier 1：轻量即时查账与体检（本地 0-Token 工具秒回）**：主控直接调用本地命令（`check`, `lore`, `pov`, `calendar`），提炼事实后以通俗大白话向人类解答，主控上下文保持纯净；
  - 🔬 **Tier 2：跨章重型研判（临时沙盒物理隔离）**：涉及通读多章历史正文时，**主控严禁在自身上下文通读数万字历史正文**，现场派发临时调研子代理完成研读，交付 300~500 字诊断简报后即刻销毁。

---

## 六、 workspace 文件地图（`<repo>/workspace/<书名>/`）

```text
workspace/<书名>/
├── project.json              # 书配置：标题/题材/主角/字数带/敏感词与启发词/线索配额
├── bible/                    # 设定真理圣经（模块化物理底座，支持 SHA-256 漂移自检）
│   ├── 01_world_axioms.md    # 世界运转公理与空间/金手指法则
│   ├── 02_power_system.md    # 实力/位阶层级与物理破坏力标尺
│   ├── 03_factions_geography.md # 地缘政治分布与核心势力拓扑
│   ├── 04_economy_items.md   # 货币购买力锚点与消耗品分级法则
│   ├── 05_special_mechanics.md  # 题材专属机制/体质/血脉/阵营相克
│   ├── 06_style_guidelines.md   # 通俗大白话语感、微动作去冷脸词库
│   └── 07_deviations.md      # 本书绝对偏离清单（严禁触碰的套路红线）
├── characters/               # 核心人物档案（闭环称谓对校矩阵、微动作、Want/Fear）
│   ├── protagonist.md        # 主角终极档案
│   └── <角色名>.md           # 重要配角/女主/男配/反派标准卡
├── entities/                 # 核心三态实体账册（支持 CLI 穿透寻路与对账）
│   ├── items/                # 法宝/装备/重器卡（损耗/充能/权属生命周期）
│   ├── factions/             # 宗门/组织/集团卡（核心资产/外交敌友态势）
│   └── locations/            # 关节点/据点/场景卡（感官锚点/运转律则/足迹）
├── outlines/
│   ├── main_plot.md          # 全书脊柱（故事引擎与宏观里程碑）
│   └── vol_XX/
│       ├── outline.md        # 分卷大纲（四分位阶段航标；主控可动态修纲）
│       └── beats/ch_XXX.md   # 当章细纲任务书（含法定事实与称谓对校清单）
├── manuscript/vol_XX/
│   ├── raw/
│   │   ├── ch_XXX_v1.md      # 初稿毛坯（Stage 2 Drafter 产出）
│   │   └── ch_XXX_v2.md      # 初修骨肉稿（Stage 3A Editor 产出）
│   └── final/ch_XXX.md       # 定稿（Stage 3B Stylist 产出，事实唯一源头）
├── state/                    # 十一表真值（含 locked/cognition） + inbox/ 提案收件箱 + snapshots/ 快照
├── log/critic/ch_XXX.md      # 老白催更便签（Stage 4B 产出，供下章细纲参考）
├── log/audit/ch_XXX.md       # 一致性仲裁报告（Stage 4C 产出；三轨仲裁，front-matter: hard/soft/logic）
├── log/branches/ch_XXX.md    # 分支参谋单（可选）
├── log/review/               # 校对注记 + Librarian 长程巡检报告 sweep_ch_XXX.md
└── export/                   # 全书编译产物（--txt / --views 状态视图）
```

---

## 七、 跨角色核心红线（任何 Stage 不可逾越）

1. **引擎黑盒规范**：严禁任何角色（agent）读取或修改 `engine/*.py` 源码，也不必读 `engine/schemas/*.json`
   （给引擎读的构建产物；人读等价信息在 `templates/README.md` 第四节，写错字段时 `check`/`sync` 报错会点名）；
   命令用法以 `python studio.py help --json` 为唯一自查入口；
2. **零脚本规范**：子代理严禁编写/运行任何统计、验证或测试脚本；状态同步与体检全权归主控 Stage 5；
   ⚠️ 准读清单的**机械拦截只覆盖 `pack --open`**（越权即拒），子代理自带的文件读写工具不受该网关约束——
   主控派单时不要把"引擎会拦住"当成安全兜底，纪律仍是第一道防线；
3. **防污染原则**：稿件严禁工程痕迹（未填槽位 `{{slot:...}}`、候选字段 `candidate_*`）；
4. **反套路与章型差异化规范**：主控 80%（或更多） 算力锁定在 Stage 1 创意脑洞，执行《金牌总编剧四步破局心法》（扫雷排除平庸套路、三维反差推演、招牌记忆物象、人际情感微澜与互动潜台词），坚决打破流水线套路复读；
5. **Critic 直通规范**：催更便签仅供下章细纲参考（主控参考），当章流水线直通 Stage 5；
6. **动态演进与闭环规范**：正文发生的称谓与关系演变由 Reader 提炼并封存入账，入账后自动成为后续章节新基准，严禁无故随机漂移；
7. **人类终审规范**：全程跑通后，主控向人类作者交付定稿成品与核心看点，最终裁决权 100% 归人类作者；
8. **实体双键与二八分级规范**：全书实体统一采用 `p_XXX` / `it_XXX` / `fac_XXX` / `loc_XXX` 物理 ID 终身绑定，改名重铸不丢状态；核心主配角与关键重器建立 `.md` 全息卡，次要路人小角色仅在四 kind 表（`persons/items/factions/places.json`）留痕入账（`card: ""`），严禁滥建 `.md` 碎片卡造成上下文与文件污染；
9. **全周期变更归 Evolver 规范**：长篇中途任何修改诉求一律由主控派发给专职的 `Evolver`（演进重构师）执行快照先行、波及面测算、跨层手术刀落地与十一表平账（`ledger recompute`、`check`）；严禁单章工匠私改设定与历史正文；
10. **双核体检与主控大脑绝缘规范**：健康体检分为系统工程运行时健康与商业小说叙事健康。人类提出的任何查账问诊意图，轻量级事实直接调取零 Token 本地 CLI 工具，跨章重型研判派发给临时隔离沙盒，**坚决严禁主控在自身主上下文通读多章历史正文**，死守大脑纯净度与构思算力。

---

## 八、 架构分工与协议导航（单 SKILL 强内聚）

所有业务心法、工艺规范与权限清单已 100% 熔炼进各角色的自完备技能卡：
- 主控调度技能：`.agents/skills/director/SKILL.md`（全局统筹、Stage 0A/0B 调度、中途演进派发、细纲破局与状态同步）
- 架构筑基技能：`.agents/skills/architect/SKILL.md`（Stage 0A 世界公理筑基、Stage 0B 人物大纲编织与状态通电）
- 演进重构技能：`.agents/skills/evolution/SKILL.md`（Stage Evolution 剧情外科手术、历史正文 Retcon、设定演进与十一表平账；技能目录名为 `evolution`，角色称谓统一为 **演进重构师 / Evolver**——按目录取技能、按称谓派单）
- 起草先锋技能：`.agents/skills/drafter/SKILL.md`（场景推进、严格继承细纲事实，产出 `raw_v1`）
- 骨肉重塑技能：`.agents/skills/editor/SKILL.md`（剧情做加法、人物交互、气口缝合、事实对账，产出 `raw_v2`）
- 风格雕琢技能：`.agents/skills/stylist/SKILL.md`（通俗脱水、去冷脸活力注入、去反刍说教、比喻脱水、遣词准确、扫读优化，产出 `final`）
- 事实审计技能：`.agents/skills/reader/SKILL.md`（核心事实抓取、动态演变提炼、JSON Schema 提案）
- 读者催更技能：`.agents/skills/critic/SKILL.md`（十年老白纯盲审催更便签）
- 一致性仲裁技能：`.agents/skills/auditor/SKILL.md`（三轨核验：机械探针 + 细纲语义清单 + 🧠 语义逻辑与出戏审查；定向手术刀指令与转办 Evolver）
- 长程巡检技能：`.agents/skills/librarian/SKILL.md`（十年长程事实巡检、词频与实体平账）
