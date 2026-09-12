# AGENTS.md — Novel Studio 核心宪法（Antigravity 通俗网文全题材通用版 · AI 向）

Novel Studio 是专为网络小说多智能体协同深度定制的创作流水线框架（全题材通用）。
架构哲学：**大模型全权掌控创意脑洞、生动情节与通俗叙事；确定性引擎负责事实底座与数据台账；原生 Subagents 实现高效工序接力与闭环归档。**

> 🏆 **【最高网文语感规范】**：
> **绝不追求虚浮晦涩的所谓“纯文学质感”！读者是来爽读网文的，不是来啃生涩教材的！**
> 全流程核心准则：**通俗直白大白话、极度易读、极好扫读、无认知门槛、一口气读完停不下来！**

> ⚖️ **【事实与创作分离规范】**：
> 创作可以脑补，事实必须对账——事实唯一源头 = `final` 定稿正文；
> 状态唯一真值 = `state/` 十一表（含不可逆事实表与认知差表）；
> 一致性由引擎机械闸门与 Auditor、Fixer、Reader 闭环兜底。

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

- **强类型状态机**：
  1. Pydantic V2 十一表真值（current / persons / items / factions / places / lines / timeline / ledger / synopsis / locked / cognition）；
  2. 提案（proposal）为**章节事实增量**的唯一写入口，过 schema 校验、引文柔性接地、幂等登记、复式记账重算四道闸（设定层例外：Stage 0 建书播种与跨卷改版由 architect/evolver 直接写 `state/*.json`；
  3. 每次 sync 会对十一表盖章 SHA-256，绕过提案的离线手改由 `check` 的 `state_offline_edit` 档指名报出）；

- **双键联合寻址机制（Dual-Key Indexing & Canonical IDs）**：
  为彻底解决长篇小说由于实体同名、别名多、重铸改名导致的状态断裂与生命周期丢失问题，全书所有实体均拥有全生命周期不可变唯一物理 ID：
  - 角色：`p_001`, `p_002`...（`p_001` 恒定为主角）
  - 物品/法宝：`it_001`, `it_002`...
  - 势力/门派：`fac_001`, `fac_002`...
  - 地点/场景：`loc_001`, `loc_002`...
  `_merge_entities` 双键合并解析优先按 `id` 寻址，就地更新属性，绝不分裂实体。

- **确定性命令面（31 项命令）**：
  `python studio.py help --json` 为阶段配方与退出码契约自查入口；完整命令与智能体映射见 [`docs/COMMAND_MATRIX.md`](file:///c:/Users/cg110902/Desktop/NOVEL/docs/COMMAND_MATRIX.md)；涵盖驾驶舱（cockpit）、事实体检（check/audit）、推演沙盒（simulate）、关系图谱（graph）、时点切面（state at/blame）及状态封存（sync）等闭环武器。

- **读者记忆轴与声纹监测（advisory 提示）**：
  基于落笔史推导读者印象（线温分层、冷线召回、关键事实重现度、语气词/句长声纹漂移），在 `pack` 与 `check` 中提供温和提示，阈值由 `project.json` 单一真源控制，不机械阻断。

- **上下文装配与世界锚点裁剪 (World Anchors Pruning)**：
  装配包（`pack`）严格执行 **20,000 Token** 预算红线；细纲通过 `world_refs` 精准按需抓取圣经小节；beats 全文、当前现场、不可逆事实与钉住的锚点永不被裁。

- **黑盒强援库**：底层内嵌 jieba（专名与分词）、networkx（实体拓扑寻路）、rapidfuzz（引文模糊接地）、rich（终端渲染）与 sqlite3（FTS5 检索加速）。

---

## 二、 角色矩阵与权限协同体系

所有 Subagents 独立读取自身 `.agents/skills/<角色>/SKILL.md` 开展作业，主控仅负责下发与验收。
除主控、架构师与起草员使用顶级模型（`inherit`）放飞文学创意与宏观架构外，其余所有执行工序（精修、脱水、安检、催更、定稿、记账）全员统一锁定高效中核 `Model: "flash"`（双层极速高精架构），兼具数百 token/秒极速吞吐与精准代码/JSON 契约，彻底杜绝小模型格式报错与返工。

| 角色 | 形式 | 负责阶段 | 准读文件 | 准写工具/目标 | 准跑命令 | 核心职责与严格边界 |
|---|---|---|---|---|---|---|
| **主控 (Director)** | 宿主主代理 | 全局统筹<br/>Stage 1 / 5 | 全局状态、critic 便签、cockpit | `outlines/vol_XX/beats/ch_XXX.md` | `cockpit`, `calendar`, `beats new`, `sync`, `check`, `state rollup` | **总制片人、首席主笔与全局统筹**：全书叙事弧线与节奏把控；态势研判；前置声明当章事实变更预期；驱动流水线与 Stage 5 原子封存。 |
| **架构师 (Architect)** | 原生子代理 | Stage 0A / 0B<br/>（仅开新书触发） | `templates/` | `bible/`, `characters/`, `outlines/` | `init`, `milestone add`, `check` | **开局世界观与宏观大纲架构师**：Greenfield 宏观造物主，完成世界公理筑基 (0A)、人物大纲编织与状态通电 (0B)、全息对账与 0-error 通电交卷 (0C)。 |
| **起草员 (Drafter)** | 原生子代理 | Stage 2 | 仅读 `pack` 返回 | `raw/ch_XXX_v1.md`<br/>(`write_to_file`) | `pack ch_XXX` | **剧情爆发起草先锋**：放飞顶级算力与想象力，以通俗大白话展开核心场景，将戏剧目标转化为初稿毛坯 `raw/ch_XXX_v1.md`（字数 2000~3000+）。100% 依靠 pack 展开，落盘即交卷。 |
| **精修师 (Editor)** | 原生子代理 | Stage 3A | `raw/ch_XXX_v2.md` | `raw/ch_XXX_v2.md`<br/>(`replace_file_content`) | **【绝对零命令】** | **全篇深度手术刀加法**：以 Copy-Item 复制 v1 为基底，地毯式巡视核心节拍，调用 `replace_file_content` 对 3~4 处关键博弈交锋、对白潜台词与微动作实施深度扩充（严禁全文重写），产出初修骨肉稿 `raw/ch_XXX_v2.md`。 |
| **脱水师 (Stylist)** | 原生子代理 | Stage 3B | `raw/ch_XXX_v3.md` | `raw/ch_XXX_v3.md`<br/>(`replace_file_content`) | **【绝对零命令】** | **全篇深度手术刀脱水**：以 Copy-Item 复制 v2 为基底，地毯式扫描语感，调用 `replace_file_content` 对 3~4 处反刍总结、冷脸面瘫词、臃肿长句与浮夸比喻实施深度大白话脱水改造（严禁全文重写），产出脱水预定稿 `raw/ch_XXX_v3.md`。 |
| **审查员 (Auditor)** | 原生子代理 | Stage 4A<br/>(并发安检) | `raw/ch_XXX_v3.md` | `log/audit/ch_XXX.md`<br/>(`audit --write`+补充) | `audit ch_XXX --write`<br/>`ask` (≤1次) | **客观内容审查与探针初审**：运行底层 8 大机械探针（**严禁带 `--adjudicate`**），配合常识审查出戏点，输出待修问题清单 `log/audit/ch_XXX.md`（含 hard/soft/logic 条目）。 |
| **催更员 (Critic)** | 原生子代理 | Stage 4B<br/>(并发便签) | `raw/ch_XXX_v3.md` | `log/critic/ch_XXX.md`<br/>(`write_to_file`) | **【绝对零命令】** | **追更老白催更便签（专供下章参考）**：扮演十年老白读者盲审 `raw_v3` 稿件，纯读者体验不跑命令，评估疲劳度与活人感，输出 300~500 字催更便签 `log/critic/ch_XXX.md`，直供下章细纲构思。落盘即交卷。 |
| **定稿师 (Fixer)** | 原生子代理 | Stage 4C | `raw/ch_XXX_v3.md`<br/>`log/audit/ch_XXX.md`<br/>`outlines/vol_XX/beats/ch_XXX.md` | `final/ch_XXX.md`<br/>(`replace_file_content`) | `audit ch_XXX --write --adjudicate`<br/>`ask` (≤1次) | **争议手术刀修复与法定定稿发布**：以 Copy-Item 将 `raw_v3` 复制为 `final/ch_XXX.md`；针对 `log/audit/ch_XXX.md` 中的硬矛盾与出戏点实施靶向替换；修复完毕后运行 `audit ch_XXX --write --adjudicate` 盖章打上通行标记。 |
| **审计员 (Reader)** | 原生子代理 | Stage 4D | `manuscript/vol_XX/final/ch_XXX.md`<br/>`outlines/vol_XX/beats/ch_XXX.md` | `state/inbox/ch_XXX.json`<br/>(`write_to_file`) | `proposal check ch_XXX`<br/>`ask` (≤1次) | **增量事实对账与提案交付**：以 final 为唯一法定事实源，对照 beats 预期，客观提取核心事实（现场即时态、主角随身家底、新实体、暗线、不可逆事实），装配标准 JSON 提案；交卷前必跑 `proposal check` 确保 0 error。 |
| **图书管理员 (Librarian)** | 原生子代理 | 每10章低频巡查<br/>卷末对账 | `final/` 正文、十一表 | `state/inbox/` | `evidence candidates`<br/>`lore list`<br/>`reconcile vol_XX --write` | **十年长程事实巡检与账目平账**：每 10 章深度巡检，打捞活跃但未入册实体；卷末对账大修出具对账单，补齐充能与关系差账。 |
| **重构师 (Evolver)** | 原生子代理 | Stage Evolution<br/>(中途随时触发) | 全局受控范围 | 受控修改 | `simulate impact`<br/>`snapshot create/rollback`<br/>`state at/diff/blame`<br/>`check` | **剧情外科主任与演进重构总监**：专职承接人类作者全生命周期中途提出的任何变更诉求（改设定、改历史正文、改人设）。先行测算波及面，实施快照防御与十一表平账。 |

---

## 三、 创作工序流水线（闭环 8 步极速咬合）

```mermaid
graph TD
    S0A["Stage 0A: 世界观公理筑基<br/>(Architect-World)"] --> S0B["Stage 0B: 人物大纲编织与通电<br/>(Architect-Story)"]
    S0B --> S0C["Stage 0C: 全息对账与闭环修复<br/>(Architect-Inspector: check 0-error)"]
    S0C --> S1["Stage 1: 细纲编织与契约声明<br/>(Director: beats new + cockpit + 声明当章事实变更预期)"]
    S1 --> S2["Stage 2: 初稿起草<br/>(Drafter: 100% 依据 pack 展开 -> raw_v1)"]
    S2 --> S3A["Stage 3A: 骨肉重塑做加法<br/>(Editor: 剧情加法/微动作/潜台词 -> raw_v2 · 零命令)"]
    S3A --> S3B["Stage 3B: 通俗脱水做减法<br/>(Stylist: 去冷脸/斩断反刍/短句扫读 -> raw_v3 · 零命令)"]
    S3B --> S4A["Stage 4A: 机械安检初审<br/>(Auditor: audit --write 查硬伤 -> log/audit/ch_XXX.md)"]
    S3B --> S4B["Stage 4B: 老白催更便签<br/>(Critic: 读者盲审 -> log/critic/ch_XXX.md)"]
    S4A --> S4C["Stage 4C: 靶向微调与放行盖章<br/>(Fixer: 复制raw_v3到final ➔ 依据audit修复 ➔ audit --write --adjudicate 盖章)"]
    S4C --> S4D["Stage 4D: 增量事实对账与提案<br/>(Reader: 以final对账beats ➔ 产出提案 ➔ proposal check 0-error)"]
    S4D --> S5["Stage 5: 状态同步与原子封存<br/>(Director: studio.py sync 原子封存快照 + 卷末 state rollup)"]
    S5 --> S6["🎉 最终成品交付: final/ch_XXX.md<br/>(交付作者终审)"]
    S4B -. "下章参考便签" .-> S1

    UserChange["人类变更诉求<br/>(改设定/改历史正文)"] -.-> SEvolution["Stage Evolution: 演进重构总监<br/>(Evolver: 波及面测算 + 手术刀平账)"]
    SEvolution -. "平账后无缝对接" .-> S1
```

---

## 四、 双向极简工序协议与子代理执行铁律（跨角色 · Canonical）

> 💡 **双向极简规范**：主控下发 4 行标准派发令（必须带准读、准写与执行步骤）；子代理上报 3 行回执单（严禁长篇汇报闲聊，杜绝主控上下文膨胀）。
>
> ⚡ **【派发算力契约（双层极速架构）】**：主控调用 `invoke_subagent` 时实施算力精准分级：
> - **顶级创意层**（`director`、`architect`、`drafter`）：锁定 `Model: "inherit"` 确保全书构思与文学场景爆发；
> - **工业执行层**（`editor`、`stylist`、`auditor`、`critic`、`fixer`、`reader`）：全员统一锁定 `Model: "flash"`，具备数百 token/秒极速生成能力与零幻觉精准 JSON/代码编辑契约，杜绝小模型重试返工！

### 🚫 子代理十大执行铁律（Subagent Execution Redlines · 杜绝一切发呆与内耗）
1. **单次装载与免倒嚼铁律 (One-Shot Boot & Zero Mid-flight Re-reading)**：子代理若未在上下文装载本手册，起手仅允许首步单次全量阅读；进入正文生产与修改后，**绝对严禁再次调用 `view_file` 反复回读倒嚼自身 `SKILL.md` 手册**！派发令步骤清晰完备时更应直接开工；
2. **单步物理落盘与禁传 ArtifactMetadata 铁律 (Direct Tool-Call Writing & Zero ArtifactMetadata · 最核心)**：所有生成/修改正文、报告、便签、提案或配置的子代理，**必须在同一轮生成中直接调用 `write_to_file` 或 `replace_file_content` 工具完成物理落盘**！
   - ⚠️ **调用 `write_to_file` 写入工作区文件时，仅提供 `TargetFile`, `CodeContent`, `Description`, `Overwrite` 4 个参数，绝对严禁传递 `ArtifactMetadata` 参数（工作区项目文件绝非 Brain Artifact，传错直接导致 Schema 报错中断与侧边栏污染）**！
   - ⚠️ **绝对严禁在对话消息中输出正文/报告全文或任何闲聊客套！落盘后只输出 3 行标准完工回执**！
3. **零脚本自查与禁越权体检 (Zero Self-Scripting & No Unauthorized Check)**：工序子代理（起草、精修、脱水、审查、催更、定稿、审计）**绝对严禁编写任何 PowerShell / Python 脚本去统计字数、正则检查、测试 JSON 或验证格式**！字数大致在区间即可，绝不死抠精确字符数；**绝对严禁调用 `check` 或 `doctor` 全书体检命令**！每个角色严格受限于派发令中的 1~2 条专属命令（无准跑命令的一律零命令），落盘即交卷；
4. **落盘即完工与零留恋铁律 (Write and Terminate · 杜绝完工后发呆)**：文件物理落盘完成（若有专属验证命令跑完无阻断）后，立即且仅输出 3 行标准完工回执并彻底结束当前轮次！**绝对严禁在落盘后出于“不放心”再次调用 `view_file` 查验自身刚写的文件，严禁调用 `manage_task`，严禁在对话框发表感悟总结或向人类发问**！干完就走，绝不滞留；
5. **`replace_file_content` 逐字大块替换铁律 (Verbatim Chunk Replacement · 杜绝编辑报错)**：针对 Editor、Stylist、Fixer 等执行编辑任务的子代理，必须单次全读目标文件，在 `TargetContent` 中 100% 逐字复制原文代码片段（含空格换行），且聚焦于 3~4 个关键戏剧/脱水大块进行手术刀级替换，**严禁切分成数十处碎片微调（极易行号错位失败），严禁全篇推倒重写**；
6. **`ask` 严格限用 1 次 (Max-1 Targeted Ask · 严禁空转)**：仅在遇到真正的核心疑点、实体 ID 查重或人设称谓争议时允许调用，**单次工序全生命周期严格限制调用最多 1 次（0~1次）**，查完即用，严禁连续多轮问书空转；
7. **严禁踩点探测与偷看旧章 (No Directory Exploration & Zero Old Chapter Peeking)**：子代理启动后**绝对严禁调用 `find_by_name` 或 `list_dir` 搜寻文件或探测目录**；**绝对严禁调用 `view_file` 偷看其他历史章节（如 `ch_001.md` 等）**！派发令已给定准读白名单，清单之外的文件一个字都不准碰；
8. **单次全量读取铁律 (One-Shot Full File Reading)**：调用 `view_file` 读取正文或清单时，**严禁添加 StartLine/EndLine 分页切片翻读**！单章小说（≤500行）必须单次全量秒读完毕，杜绝多次往返；
9. **Drafter 严禁重复回读 (Drafter Zero-Reread)**：Drafter 运行 `studio.py pack` 获取装配包后，直接依据 pack 展开正文，**严禁再次回头重复读取 `characters/` 或 `bible/` 卡片**；
10. **绝对禁读源码与遇阻即报 (Black-box Engine Zero-Read & Escalate on Blocker)**：**严禁阅读 `engine/` 下任何 Python 源码**！严格遵循【读输入 ➔ 落盘 ➔ 验命令 ➔ 3行回执交卷】；遇阻力立即输出 3 行阻断回执向主控报告！

- **下达 · 4 行标准工序派发令**（主控发给 Subagent）：
  ```text
  【章节工序派发令（免读技能卡直接开工）】
  - 书籍工作区：workspace/<书名> ｜ 分卷章节：vol_XX / ch_XXX
  - 执行阶段：Stage X (<角色名>) ｜ 算力级别：[inherit / flash]
  - 核心输入/待修清单：[内联核心数据，免查多余文件]
  - 执行指令：起手直接执行[第1步动作] ➔ 准写=[调用工具直接落盘（禁传ArtifactMetadata）] ➔ 执行[验证命令] ➔ 3行回执交卷（禁倒嚼/禁发正文聊天/禁写脚本/落盘即走）
  ```
- **上报 · 3 行标准完工回执单**（Subagent 交卷给主控）：
  ```text
  【章节工序完工回执】
  - 完工阶段：Stage X (<角色名>)
  - 产出路径：[目标文件相对路径]
  - 核心指标：[字数/核心指标/状态] ｜ 工具直接物理落盘 ｜ 验收达标无滞留
  ```

---

## 五、 workspace 文件地图（`<repo>/workspace/<书名>/`）

```text
workspace/<书名>/
├── project.json              # 书配置：标题/题材/主角/字数带/敏感词与启发词/线索配额
├── bible/                    # 设定真理圣经（模块化物理底座，支持 SHA-256 漂移自检）
│   ├── 01_world_axioms.md    # 世界运转公理与空间/金手指法则
│   ├── 02_power_system.md    # 实力/位阶层级与物理破坏力标尺
│   ├── 03_factions_geography.md # 地缘政治分布与核心势力拓扑
│   ├── 04_economy_items.md   # 货币购买力锚点与消耗品分级法则
│   ├── 05_special_mechanics.md  # 题材专属机制/体质/血脉/阵营相克
│   └── 06_deviations.md      # 本书绝对偏离清单（严禁触碰的套路红线）
├── characters/               # 核心人物档案（闭环称谓对校矩阵、微动作、Want/Fear）
│   ├── protagonist.md        # 主角终极档案 (ID: p_001)
│   └── <角色名>.md           # 重要配角/女主/男配/反派标准卡
├── entities/                 # 核心三态实体账册（支持 CLI 穿透寻路与对账）
│   ├── items/                # 法宝/装备/重器卡（损耗/充能/权属生命周期）
│   ├── factions/             # 宗门/组织/集团卡（核心资产/外交敌友态势）
│   └── locations/            # 关节点/据点/场景卡（感官锚点/运转律则/足迹）
├── outlines/
│   ├── main_plot.md          # 全书脊柱（故事引擎与宏观里程碑）
│   └── vol_XX/
│       ├── outline.md        # 分卷大纲（四分位阶段航标；主控可动态修纲）
│       └── beats/ch_XXX.md   # 当章细纲任务书（含法定事实与预期变更声明）
├── manuscript/vol_XX/
│   ├── raw/
│   │   ├── ch_XXX_v1.md      # 初稿毛坯（Stage 2 Drafter 产出）
│   │   ├── ch_XXX_v2.md      # 初修骨肉稿（Stage 3A Editor 产出）
│   │   └── ch_XXX_v3.md      # 通俗脱水预定稿（Stage 3B Stylist 产出）
│   └── final/ch_XXX.md        # 终局法定定稿（Stage 4C Fixer 修复并发布）
├── state/                    # 十一表真值（含 locked/cognition） + inbox/ 提案收件箱 + snapshots/ 快照
│   ├── rollups/              # 卷级态势折叠（vol_XX.json，供跨卷装配）
│   └── inbox/ch_XXX.json     # 章节增量提案（Stage 4D Reader 产出）
├── log/
│   ├── audit/ch_XXX.md       # 质检仲裁报告（Stage 4A 初评，Stage 4C 裁决盖章）
│   ├── critic/ch_XXX.md      # 老白催更便签（Stage 4B Critic 产出，供下章细纲参考）
│   ├── branches/ch_XXX.md    # 分支参谋单（可选）
│   └── review/               # 校对注记 + Librarian 长程巡检报告 sweep_ch_XXX.md
└── export/                   # 全书编译产物（--txt / --views 状态视图）
```

---

## 六、 跨角色核心红线（任何 Stage 不可逾越）

1. **引擎黑盒规范**：严禁任何角色读取或修改 `engine/*.py` 源码，也不必读 `engine/schemas/*.json`；命令用法以 `python studio.py help --json` 为唯一自查入口；
2. **防污染原则**：稿件严禁工程痕迹（未填槽位 `{{slot:...}}`、候选字段 `candidate_*`）；
3. **质量闭环原则**：Stage 4A 发现的问题必须经由 Stage 4C 修复并盖章，严禁在未修复时私自打上 `--adjudicate` 放行；
4. **提案预检原则**：Stage 4D Reader 在交付提案前必须通过 `proposal check ch_XXX` 0 报错验证，确保 Stage 5 封存零故障；
5. **全周期变更归 Evolver 规范**：长篇中途任何修改诉求一律由主控派发给专职的 `Evolver`（演进重构师）执行快照先行、波及面测算、跨层手术刀落地与状态对齐（确保 `check` 0 报错）；严禁单章工匠私改设定与历史正文；
6. **双核体检与主控大脑绝缘规范**：主控坚决严禁在自身主上下文通读多章历史正文，事实查询调取 CLI（`lore`, `ask`, `calendar`, `cockpit`），死守构思算力。

---

## 七、 主控物理写屏障红线（Director Write-Barrier · 绝对禁止主控越权写入）

主控（Director）的物理写入权限严格仅限于：
- ① Stage 1 细纲任务书（`outlines/vol_XX/beats/ch_XXX.md`）；
- ② 卷大纲微调（经人类作者同意后更新 `outlines/vol_XX/outline.md`）；
- ③ 运行引擎管理命令（如 `init`, `milestone`, `sync`, `beats new`, `state rollup` 等）。

**主控绝对禁止在宿主主进程中直接调用 `write_to_file` 或 `replace_file_content` 亲笔撰写或修改正文、报告或提案！**
进入 Stage 0、Stage 2、Stage 3、Stage 4 时，主控**必须且只能**通过 `invoke_subagent` 将任务以标准 4 行派发令下达给专职子代理在独立沙盒中完成落盘！

### ⚡ Stage 5 极速原子封存三大铁律（严格 3 秒极限闭环）
1. **唯一准跑命令**：必须且只能执行单行命令 `python studio.py sync ch_XXX -w "workspace/<书名>"`（到期里程碑使用 `&&` 链式执行；卷末追加 `python studio.py state rollup vol_XX`）；
2. **绝对禁止查语法**：严禁在生产时调用 `--help` 探测命令用法；
3. **正文绝对零回读**：严禁调用 `view_file` 翻读 `final/` 成稿正文（定稿由 Fixer 盖章，梗概由 Reader 提取，主控死守大脑纯净）；封存完毕直接在聊天中以极简卡片对人类交付。

---

## 八、 架构分工与协议导航（单 SKILL 强内聚）

所有业务心法、工艺规范与权限清单已 100% 熔炼进各角色的自完备技能卡：
- 引擎命令图谱：[`docs/COMMAND_MATRIX.md`](file:///c:/Users/cg110902/Desktop/NOVEL/docs/COMMAND_MATRIX.md)（Engine 31 核心命令与多智能体矩阵映射全景图）
- 主控调度技能：`.agents/skills/director/SKILL.md`（总制片人、前瞻研判、细纲前置声明、四大实战武器库、流水线统筹与状态封存）
- 架构筑基技能：`.agents/skills/architect/SKILL.md`（Stage 0A 世界公理筑基、Stage 0B 人物大纲编织与状态通电）
- 演进重构技能：`.agents/skills/evolution/SKILL.md`（Stage Evolution 剧情外科手术、历史正文 Retcon、设定演进与十一表平账）
- 起草先锋技能：`.agents/skills/drafter/SKILL.md`（场景推进、严格继承细纲事实，产出 `raw_v1`）
- 骨肉重塑技能：`.agents/skills/editor/SKILL.md`（全篇深度手术刀加法：人物机锋、博弈微动作、气口缝合，产出 `raw_v2`）
- 风格雕琢技能：`.agents/skills/stylist/SKILL.md`（全篇深度手术刀脱水：去冷脸活力注入、切除反刍说教、扫读短句化，产出 `raw_v3`）
- 审查安检技能：`.agents/skills/auditor/SKILL.md`（客观三轨初核：8大机械探针 + 常识出戏审查，产出 `log/audit/ch_XXX.md` 待修清单）
- 读者催更技能：`.agents/skills/critic/SKILL.md`（十年老白纯盲审催更便签，直供下章细纲参考）
- 终审定稿技能：`.agents/skills/fixer/SKILL.md`（复制 raw_v3 ➔ 依据 audit 清单手术刀修补 ➔ 跑 `audit --adjudicate` 盖章放行，交付法定定稿 `final`）
- 事实审计技能：`.agents/skills/reader/SKILL.md`（核心事实对账提取、JSON 提案入箱、`proposal check` 0 报错验证）
- 长程巡检技能：`.agents/skills/librarian/SKILL.md`（十年长程事实巡检、次要实体打捞与账目大修）
