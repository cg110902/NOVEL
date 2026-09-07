# AGENTS.md — Novel Studio 核心宪法（Antigravity 通俗网文全题材通用版 · AI 向）

Novel Studio 是专为 **Google Antigravity** 深度定制的通俗网络小说多智能体创作流水线框架（全题材通用）。
架构哲学：**大模型全权掌控创意脑洞、生动情节与通俗叙事；确定性引擎负责事实底座与数据台账；原生 Subagents 实现高效工序接力与闭环归档。**

> 🏆 **【最高网文语感铁律】**：
> **绝不追求虚浮晦涩的所谓“文学质感”！读者是来爽读网文的，不是来读纯文学的！**
> 全流程核心准则：**通俗直白大白话、极度易读、极好扫读、动词直给、无认知门槛、一口气读完停不下来！**

> **事实与创作分离铁律**：创作可以脑补，事实必须对账——事实唯一源头 = `final` 定稿正文；状态唯一真值 = `state/` 八表（含不可逆事实表与认知差表）；一致性由引擎机械闸门与 Auditor 双轨核验兜底。

---

## 一、技术底座速览（黑盒边界）

以下能力全部封装在确定性引擎（`engine/`，黑盒）内，Agent 只经 CLI 消费、禁知实现：

- **强类型状态机**：Pydantic V2 八表真值（current / entities / lines / timeline / ledger / synopsis / locked / cognition）；提案（proposal）为唯一写入口，过 schema 校验、引文柔性接地、幂等登记、复式记账重算四道闸；
- **命令面（28 个生产指令）**：`python studio.py help --json` 是命令目录、阶段配方与退出码契约的唯一自查入口——含 cockpit 态势驾驶舱、check 事实体检、audit 确定性机械探针、recall 残酷四问自证、simulate 剧情推演沙盒、milestone 主线里程碑管理、sync 状态封存、ledger recompute 账本修复、snapshot 回滚等；
- **强援库**：jieba（专名与词频）、networkx（实体拓扑寻路）、rapidfuzz（引文模糊接地）、rich（终端渲染）、sqlite3（FTS5 检索加速）。

---

## 二、角色矩阵与权限协同体系

| 角色 | 形式 | 负责阶段 | 核心职责与严格边界 |
|---|---|---|---|
| **主控 (Director)** | 宿主主代理 | 全局统筹 / Stage 1 / Stage 5 | **全局统筹、意图分流、前置事实提炼与状态封存**：识别用户意图（【开新书】派发 Architect，【继续写】核验 workspace 智能接入/多书询问）；细纲构思（80% 核心算力：真人总编剧三步破局心法）；轻量调度流水线；一键执行 `sync` 封存快照。 |
| **架构师 (Architect)** | 原生子代理 (`inherit`) | Stage 0 | **世界观筑基与全书脚手架**：承接开书脑洞，独立沙盒运行；产出 `project.json`、`bible/`、`characters/`、`outlines/`、八表状态初始化与主线里程碑播种，资产直接落盘。落盘即交卷，为主控保持 100% 纯净上下文。 |
| **起草员 (Drafter)** | 原生子代理 (`inherit`) | Stage 2 | **剧情爆发起草**：放飞算力与想象力；**严格继承细纲预提炼的称谓与前情事实**，以通俗大白话自由展开核心场景，将戏剧目标转化为初稿毛坯 `raw/ch_XXX_v1.md`（字数 2000~3000+）。恪守准读清单，落盘即交卷。 |
| **精修师 (Editor)** | 原生子代理 (`inherit`) | Stage 3A | **骨肉重塑与事实对账**：以充实剧情血肉为导向；**负责做足剧情加法**（场景展开、人物互动温度、对话潜台词、转折气口缝合）；**严格对照细纲法定清单核查对话称谓与修饰词**，产出通俗大白话初修骨肉稿 `raw/ch_XXX_v2.md`。 |
| **脱水师 (Stylist)** | 原生子代理 (`inherit`) | Stage 3B | **通俗脱水、去面瘫与扫读优化**：以极度易读、好扫读、通俗直白为导向；首行规范输出章题；**负责做足减法与表情动作去僵化**（坚决切除动作后反刍总结、消除主角面瘫与神色淡然套路、比喻脱水白描化、Gemini高频套话置换、确保造句准确与成语自然运用、句式音律变奏），直接落盘法定定稿 `final/ch_XXX.md`。 |
| **审计员 (Reader)** | 原生子代理 (`inherit`) | Stage 4 (并行轨 A) | **精益事实审计与动态演进提取**：以 final 为唯一事实源，清晰提取核心事实（现场在场、**动态关系与称谓突破演进**、关键新实体、主线伏笔、大额收支、不可逆事实），装配严格符合 Pydantic V2 Schema 的标准增量提案 JSON (`state/inbox/ch_XXX.json`)。 |
| **催更员 (Critic)** | 原生子代理 (`inherit`) | Stage 4 (并行轨 B) | **追更老白催更便签（专供下章参考）**：扮演十年老白**追更读者**盲审 final 正文，输出 200~500 字便签 `log/critic/ch_XXX.md`，**仅供下一章细纲构思参考，无一票否决权，当章流水线直通**。落盘即交卷。 |
| **仲裁员 (Auditor)** | 原生子代理 (`inherit`) | Stage 4 (并行轨 C) | **双轨一致性仲裁（机械探针+细纲语义清单）**：基于引擎 `audit` 输出的 7 大机械候选，**并结合细纲预提炼清单逐行对校称谓与修饰词**，输出仲裁报告 `log/audit/ch_XXX.md`。检出 🔴 确凿硬矛盾立即下达定向手术刀修复指令。 |
| **图书管理员 (Librarian)** | 原生子代理 (`inherit`) | Stage 4D (每10章低频巡查) | **十年长程事实巡检与账目平账**：每 10 章执行一次深度巡检，通读近 10 章定稿，清查遗漏登场次要实体、法宝道具充能漏扣、生死状态与词频漂移，把修补**并入当章在途提案** `state/inbox/ch_XXX.json`。 |

---

## 三、创作工序流水线（设定筑基 + 前置提炼 + 骨肉重塑 + 通俗脱水 + 双轨仲裁闭环）

```mermaid
graph TD
    S0["Stage 0: 设定构想与筑基<br/>(Architect 子代理: bible/人物卡/大纲)"] --> S1["Stage 1: 细纲构思与前置事实提炼<br/>(主控: 80%脑力·真人三步破局心法)"]
    S1 --> S2["Stage 2: 初稿起草<br/>(Drafter: 场景展开 + 继承事实 -> raw_v1)"]
    S2 --> S3A["Stage 3A: 骨肉重塑<br/>(Editor: 剧情做加法 + 对话/气口/事实对账 -> raw_v2)"]
    S3A --> S3B["Stage 3B: 通俗脱水与扫读优化<br/>(Stylist: 减法去油 + 去面瘫/去反刍/精准白描 -> final)"]
    S3B --> S4A["Stage 4A: 事实审计<br/>(Reader: 增量状态与动态演进提案)"]
    S3B --> S4B["Stage 4B: 催更便签<br/>(Critic: 读者体感+期待)"]
    S3B --> S4C["Stage 4C: 双轨一致性仲裁<br/>(Auditor: 机械探针+细纲语义清单拦截)"]
    S4C -. "🔴 确凿硬矛盾/称谓漂移" .-> S3Patch["定向手术刀修复<br/>(Stylist/Editor: 仅重写冲突单行)"]
    S3Patch --> S4A
    S4A --> S5["Stage 5: 状态同步与动态基准更新<br/>(主控: 原子合并/封存快照/新状态生效)"]
    S4B -. "下章参考便签" .-> S1
    S5 --> S6["🎉 最终成品交付: final/ch_XXX.md<br/>(人类作者终审验收)"]
```

---

## 四、双向极简工序协议（跨角色 · canonical）

> 💡 **双向极简铁律**：主控下发 4 行派发令（严禁拷贝细纲全文或重复背诵工艺规则）；子代理上报 3 行回执单（严禁长篇汇报闲聊，杜绝主控上下文膨胀）。子代理技能卡内的回执细则以本协议为总纲。

- **下达 · 4 行标准工序派发令**（主控发给 Subagent）：
  ```text
  【章节工序派发令】
  - 书籍工作区：workspace/<书名>
  - 分卷与章节：vol_XX / ch_XXX
  - 执行阶段：Stage X (Architect / Drafter / Editor / Stylist / Reader / Critic / Auditor)
  - 执行纪律：严格按你的 SKILL.md 执行。恪守准读清单与准写路径，落盘即止，严禁自查与编写脚本。
  ```
- **上报 · 3 行标准完工回执单**（Subagent 交卷给主控）：
  ```text
  【章节工序完工回执】
  - 完工阶段：Stage X (Architect / Drafter / Editor / Stylist / Reader / Critic / Auditor)
  - 产出路径：[目标文件相对路径]
  - 核心指标：[字数/规范指标/矛盾指标] ｜ 零脚本直接落盘 ｜ 验收达标无滞留
  ```

---

## 五、开工认知与意图分流协议（开新书 vs 继续写）

主控在收到人类作者指令时，按以下认知与意图网关执行分流：

### 1. 🌟 意图 A：【开新书 / 新建项目 / 构思新设定】（及类似表述）
- 主控接收人类作者的核心脑洞（书名、题材、主角金手指、核心爽点）；
- 主控下发 **Stage 0 派发令给 `Architect` 子代理**；
- `Architect` 在独立的纯净沙盒中完成 `project.json`、`bible/`、`characters/`、`outlines/` 及初始状态与里程碑落盘；
- `Architect` 交卷后，主控运行 `python studio.py cockpit --json` 接入新书驾驶舱，向人类呈现世界观纲要供终审确认。主控上下文实现**零污染**！

### 2. 🚀 意图 B：【继续写 / 创作下一章 / 推进工程】（及类似表述）
- **核验 `workspace/` 目录**：
  - ⚠️ 若 `workspace/` 为空 ➔ 提示用户当前尚无工程，引导发起“开新书”；
  - ❓ 若 `workspace/` 下存在**多本书籍目录** ➔ 列出所有书名，主动询问用户：“检测到当前有以下多部作品：[书名A, 书名B...]，请问您想继续创作哪一本？”
  - ✅ 若 `workspace/` 下仅有**单本书**（或用户已指定书名） ➔ 
    - ❄️ **新窗口冷启动**：依序读底座（`AGENTS.md` → `director/SKILL.md`），执行 `python studio.py cockpit --json` 秒级接入；
    - 🔥 **同会话热启动**：直接运行 `python studio.py cockpit --json`，直通 Stage 1 细纲构思！


---

## 六、workspace 文件地图（`<repo>/workspace/<书名>/`）

```text
workspace/<书名>/
├── project.json              # 书配置：标题/题材/主角/字数带/词表供参/线索配额
├── bible/project_bible.md    # 世界圣经：世界规则·战力标尺·势力地理·语言定调·本书偏离清单
├── characters/               # 人物卡：protagonist.md + 配角卡（Want/Fear/说话风格）
├── outlines/
│   ├── main_plot.md          # 全书脊柱
│   └── vol_XX/
│       ├── outline.md        # 分卷大纲（四分位阶段航标；主控可动态修纲）
│       └── beats/ch_XXX.md   # 当章细纲任务书（含法定事实与称谓对校清单）
├── manuscript/vol_XX/
│   ├── raw/
│   │   ├── ch_XXX_v1.md      # 初稿毛坯（Stage 2 Drafter 产出）
│   │   └── ch_XXX_v2.md      # 初修骨肉稿（Stage 3A Editor 产出）
│   └── final/ch_XXX.md       # 定稿（Stage 3B Stylist 产出，事实唯一源头）
├── state/                    # 八表真值（含 locked/cognition） + inbox/ 提案收件箱 + snapshots/ 快照（引擎管辖）
├── log/critic/ch_XXX.md      # 老白催更便签（Stage 4B 产出，供下章驾驶舱雷达）
├── log/audit/ch_XXX.md       # 一致性仲裁报告（Stage 4C 产出；双轨仲裁）
├── log/branches/ch_XXX.md    # simulate branch 分支参谋单（可选，主控工件）
├── log/review/               # 校对注记 + Librarian 长程巡检报告 sweep_ch_XXX.md（可选，主控工件）
└── export/                   # 全书编译产物（--txt / --views 状态视图）
```

---

## 七、跨角色铁律（任何 Stage 不可逾越）

1. **引擎黑盒铁律**：严禁任何角色读取或修改 `engine/*.py` 源码；命令用法以 `python studio.py help`（`--json` 供 Agent）为唯一自查入口；
2. **零脚本铁律**：子代理严禁编写/运行任何统计、验证或测试脚本；状态同步与体检全权归主控 Stage 5；
3. **防污染原则**：稿件严禁工程痕迹（未填槽位 `{{slot:...}}`、候选字段 `candidate_*`）；
4. **单向推进铁律**：各 Stage 落盘即交卷，严禁回读自查、严禁跨 Stage 停留内耗；
5. **分工不交叉铁律**：Stage 3A Editor 专职做足剧情加法与骨架，Stage 3B Stylist 专职做足通俗脱水与扫读优化；
6. **反套路与章型差异化铁律**：主控 80% 算力死死锁定在 Stage 1 创意脑洞，强制执行《真人总编剧三步破局心法》（扫雷排除平庸套路、三维反差推演、招牌记忆物象），坚决打破概率滑梯与路径依赖，拒绝连续章节套路复读；
7. **Critic 直通铁律**：催更便签仅供下章细纲参考，无一票否决权，当章流水线直通 Stage 5；
8. **动态演进与闭环铁律**：正文发生的称谓与关系演变由 Reader 提炼并封存入账，入账后自动成为后续章节新基准，严禁无故随机漂移；
9. **人类终审铁律**：全程跑通后，主控向人类作者交付定稿成品与本章核心看点，最终裁决权 100% 归人类作者。


---

## 八、架构分工与协议导航（单 SKILL 强内聚）

- **单一真理源**：所有业务心法、工艺规范与权限清单已 100% 熔炼进各角色的自完备技能卡：
  - 主控调度技能：`.agents/skills/director/SKILL.md`（全局统筹、前置事实提炼与状态同步）
  - 设定架构技能：`.agents/skills/architect/SKILL.md`（Stage 0 独立沙盒世界观筑基、人物卡与大纲落盘）
  - 起草先锋技能：`.agents/skills/drafter/SKILL.md`（场景推进、严格继承细纲事实，产出 `raw_v1`）
  - 骨肉重塑技能：`.agents/skills/editor/SKILL.md`（剧情做加法、人物交互、气口缝合、事实对账，产出 `raw_v2`）
  - 风格雕琢技能：`.agents/skills/stylist/SKILL.md`（通俗脱水、去面瘫活力注入、去反刍说教、比喻脱水、遣词准确、扫读优化，产出 `final`）
  - 事实审计技能：`.agents/skills/reader/SKILL.md`（核心事实抓取、动态演变提炼、JSON Schema 提案）
  - 读者催更技能：`.agents/skills/critic/SKILL.md`（十年老白纯盲审催更便签）
  - 一致性仲裁技能：`.agents/skills/auditor/SKILL.md`（双轨核验、机械探针+语义对账、定向手术刀指令）
  - 长程巡检技能：`.agents/skills/librarian/SKILL.md`（十年长程事实巡检、词频与实体平账）

