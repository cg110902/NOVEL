# ARCHITECTURE_BRIEF — Novel Studio 3.1 系统全景解读

> 本文是「读代码的人」视角的架构说明书，回答四个问题：**系统分成几层**、**数据怎么流**、
> **每个字段为什么存在**、**每个设计决定想防什么事故**。
> 与 `README.md`（上手）/ `AGENTS.md`（主控宪法）/ `engine/README.md`（模块地图）/
> `docs/OBJECT_MODEL.md`（对象层）互补，不重复其命令行细节。

---

## 〇、一句话定位

**Novel Studio 是一个「把长篇网络小说的事实底座交给确定性程序、把创意与文笔交给大模型」的分层流水线框架。**

它不是一个写作机器人，而是一台 **长篇连载的事实对账机器**。它要解决的核心事故只有一个：

> LLM 写到第 80 章时，会忘记第 3 章死掉的人、花掉的钱、断掉的刀、说过的秘密。

整个系统的每一处设计，几乎都能追溯到某一类具体的「吃书事故」。理解这一点，后面所有字段就有了锚。

---

## 一、三层架构与分工原则

```
┌──────────────────────────────────────────────────────────────┐
│ 协议层（人/Agent 读，不执行）                                   │
│   AGENTS.md                主控宪法：流水线、角色矩阵、红线      │
│   .agents/skills/*/SKILL.md  10 个角色的技能卡（准读/准写/工艺） │
│   templates/               建书脚手架（bible 七表 / 人物卡 / 大纲）│
└──────────────────────────────────────────────────────────────┘
                            ↓ 通过 CLI 消费
┌──────────────────────────────────────────────────────────────┐
│ 引擎层（确定性 Python，黑盒）  engine/  ~21.7k 行               │
│   cli.py → commands/（6 个命令实现模块）                        │
│   state.py        十一表真值 + 提案合并（唯一写入咽喉）          │
│   checks.py       双核体检（55 个错误码）                       │
│   pack.py         三层上下文装配 + 角色读权限网关                │
│   audit/checks/evidence/graph/memory/rollup/voiceprint/        │
│   changelog/migrations/snapshot/db/objects/proposal_v3         │
└──────────────────────────────────────────────────────────────┘
                            ↓ 读写
┌──────────────────────────────────────────────────────────────┐
│ 数据层  workspace/<书名>/                                      │
│   manuscript/   raw_v1 → raw_v2 → final（事实唯一源头）         │
│   state/        十一表断言真值 + derived 派生表 + inbox 提案箱    │
│   log/          audit/critic/review（三轨留痕）                 │
│   bible/ + characters/ + entities/ + outlines/   设定层        │
└──────────────────────────────────────────────────────────────┘
```

**分工原则（写进代码注释的第一行）**：
> 能算的一律由引擎算（状态机、账本重算、事实体检、上下文装配）；
> 需要判断力的才交给子代理（写细纲、写正文、裁决矛盾）。

引擎的自律边界（`engine/README.md` 开头）：**只做确定性计算、图拓扑、词法分析、Schema 强校验、终端渲染；
坚决不做文学理解与艺术裁决。**

---

## 二、两组关键数字：十一表 + 十二张

### 2.1 十二张状态表（`state/*.json`）

| # | 表 | 定位 | 一句话 |
|---|---|---|---|
| 1 | `current.json` | **现场断面** | 「此刻」世界长什么样：时间、地点、在场者、主角状态、上章余震、头顶危机 |
| 2 | `persons.json` | 人物台账 | `p_XXX` 实体 |
| 3 | `items.json` | 道具台账 | `it_XXX` 实体（充能/持有/完损） |
| 4 | `factions.json` | 势力台账 | `fac_XXX` 实体（外交拓扑） |
| 5 | `places.json` | 地点台账 | `loc_XXX` 实体（危险度/环境律则） |
| 6 | `lines.json` | **暗线生命周期** | 伏笔 `GUN-`／误会 `MIS-`／秘密 `KNO-` 三条线 |
| 7 | `timeline.json` | **时空因果轴** | events 大事记 `EVT-` / arcs 大弧 / clocks 危机时钟 / milestones 主线航标 |
| 8 | `ledger.json` | **复式账本** | 多资源池 + 流水；余额**由流水重算** |
| 9 | `synopsis.json` | 梗概 | 全书 logline + 分章梗概 |
| 10 | `locked.json` | **不可逆事实** | `LOCK-` 死亡/毁损/规则/承诺——写作红线 |
| 11 | `cognition.json` | **角色认知边界** | `COG-` 每个角色知道/怀疑/误解/掌握什么 |
| 12 | `derived.json` | **纯派生缓存** | 第 12 张表，唯一写者是引擎，删了能重算 |

> **v6 拆表**：2~5 号在 v5 及之前是单张 `entities.json`，按 `kind` 物理拆成四表。
> 读时 `load_state("entities")` 返回四表合并视图（兼容），`save_state("entities")` 拒绝写入。

### 2.2 为什么是「表」而不是「文档」

十一表是**断言层**：每条记录都是「某章正文说了什么」的机器可读断言。
它们回答「记了什么」，不回答「世界现在是什么样」——后者由**对象层**（`engine/objects/`）拼装：

```
Object Envelope = {id, kind, status, asserted, derived, prov}
                                     ↑十一表原文  ↑纯函数算  ↑出处(since_ch/quote/op_id)
```

注册表 `registry.build_registry()` 提供**三键寻址**：`by_id` / `by_name` / `alias_to_name`。
pack / derive / verify 统一走它，替代散落的各写一遍的寻址逻辑。

---

## 三、字段逐类解析：每个字段在防什么事故

### 3.1 `current.json` — 现场断面

| 字段 | 作用 | 防什么 |
|---|---|---|
| `time` / `time_day` | 时间；`time_day` 是数值孪生（≥1 整数） | 时间回退（引擎出 advisory 警示：闪回章可忽略） |
| `region` / `location` / `place_ref` | 大地图 / 具体地点 / **地点实体引用** | `place_ref` 让「地点」可机械寻址，不再靠字符串模糊匹配 |
| `pov_ref` / `present_characters` / `present_refs` | 视角角色 / 在场名单（字符串） / 在场名单（**实体引用**） | 双口径并存：`present_refs` 供精确装配，`present_characters` 供人类可读；`derived` 还会做**双口径对账**（`present_refs_mismatch`） |
| `power_level` / `injury` / `abilities` | 主角即时战力态 | 防止「上一章断了胳膊、这章满血单挑」 |
| `equipment` / `assets` / `loadout` | 随身物 / 非资金资源 / 常驻作战体系 | `loadout` 五件套（功法/身法/杀招/底牌/佩戴法宝）防战斗体系漂移 |
| `situation` / `mood` / `goal` | 处境 / 情绪 / 目标一句话 | 给下章 Drafter 的连续性格言 |
| `aftershock` | **上章戏剧余震** | 强制下章开篇先接刀口，防「每章都重新开局」 |
| `active_pressures` | 悬在头顶的危机 | 配合 `timeline.clocks` 自动生成「⏳倒计时仅剩 N 章」 |

> **空值语义**：`current` 里空串／空数组 = **不修改**（引擎跳过），不是清空。
> 这是刻意设计——LLM 补不全整张表，只写增量才不会误清档。

### 3.2 四张实体表 — 双键寻址（Dual-Key Indexing）

**物理 ID 编码**：`p_001`（主角恒为 `p_001`）/ `it_001` / `fac_001` / `loc_001`。

**合并解析策略**（`state._merge_entities`）：
1. 先按 `id` 命中 → 即便中文名变了（「断水剑」重铸为「断水龙吟剑」）也**就地更新**，绝不裂变成两个实体；
2. `id` 未给 → 降级按 `name` 寻址，并把既有 `id` **继承**给新条目；
3. 都未命中 → 全新入册。

这条规则直接解决长篇三大癌症：**同名实体**、**改名重铸**、**别名多写**。

**实体字段分组与用途**：

| 分组 | 字段 | 设计目的 |
|---|---|---|
| 标尺 | `tier_rank`(1-12) / `tier_name` / `power_benchmark` | 跨题材可比较的**数值化战力标尺**，防战力通胀；`tier_shift_without_event` 探针要求位阶变更必须有 timeline 事件支撑 |
| 记忆点 | `sensory_anchor` / `micro_actions` / `golden_quote` | 感官物象 + 微动作库 + 首次高光切片——给 LLM 具体的「怎么写这个人」，防抽象脸谱 |
| 称谓 | `address_matrix` {目标名: 我称呼对方} | **闭环称谓矩阵**，全书恒定。Auditor 的 `address_mismatch` 探针逐行对校 |
| 生命/阵营 | `life_status`(alive/deceased/missing) / `attitude`(hostile…allied) / `faction` | 死亡后不得再出场（`probe_locked_facts`）；立场大翻转出 advisory |
| 道具 | `holder` / `charges` / `max_charges` / `cost_per_use` / `durability` / `condition` / `location` | **充能必须扣**：`charges > max_charges` 是硬错；`item_charges_exhausted` 探针抓「已耗尽的道具却在用」 |
| 势力 | `scale_tier` / `core_assets` / `diplomacy`{势力名:态度} | 势力外交拓扑，供 `graph` 寻路 |
| 地点 | `danger_tier` / `environment_rules` | 场景律则 |
| 关系 | `relations[]{target,type,desc,strength(1-5),status,since_ch}` | 动态张力图。`type` 是**开放谓词**（中文「宿敌」合法），未知谓词只 advisory 提示不拒收 |
| 对象化 | `injury_level`(0-5) / `injury_desc` / `renown`(声望/悬赏，可负) | v2 加法字段：把「读者在意的可算属性」变成可计算量，供 pack 注入 / recall 桥接 |

> **`type=location` 与 `place` 同等地位**这一条曾是 bug：`LOCATION_TYPES` 单一真源在 `models/entities.py`，
> 任何「是不是地点」的判定必须走它，禁止手写字面量。

### 3.3 `lines.json` — 暗线生命周期（三类线）

| 线种 | ID | 状态机 | 动作 |
|---|---|---|---|
| 伏笔 foreshadow | `GUN-NNN` | Planted → Reminded → Resolved | plant / update / remind / resolve |
| 误会 misunderstanding | `MIS-NNN` | Active → Escalated → Resolved | plant / update / escalate / resolve |
| 秘密 knowledge | `KNO-NNN` | Concealed → Revealed | plant / update / resolve |

关键字段：

- **`target_ch`**：预定回收章。四选一取值 `int章号` / `ch_NNN`（三位补零）/ `"第N章"` / `"longline"`。
  **plant 必填**——因为缺省会静默占用长线配额（长线配额只有 5 条，被无声吃掉是隐性的主线稀释）。
- **`requires`**：前置依赖线 ID 数组 → 构成**因果图**。写闸门 `_prereq_errors` 拦两类违规：
  ① 本线已闭环但前置未完成（`prerequisite_unmet`，硬错）；② 循环依赖（`prerequisite_cycle`，三色 DFS）。
- **`weight`**(1-N)：权重。**同时是读者记忆阈值缩放因子**——`cold_threshold = base + per_weight × weight`，
  重要线容忍更长的空窗期。
- **`holders`**（仅 knowledge）：**知情圈**。声明后 `pov` 推导对圈内角色不再误标「不应知情」。缺省 = 全员不知情。

### 3.4 `timeline.json` — 时空因果轴

- `events[]`：`{time, event, chapter, id(EVT-), participants[], place, causes[], consequences[]}`。
  事件是**可引用对象**——`cognition.truth_ref` 挂它，`simulate` 遍历它。
  修订通道：`{"id":"EVT-003","replace":"新描述"}` 按 id 改写，**不改章节归属**，留审计痕迹。
- `clocks[]`：危机倒计时。**只有五个合法字段** `name/target_ch(int!)/urgency/desc/status`，
  按 `name` 去重（改名 = 新建）。`pack` 会把它渲染成「⏳倒计时仅剩 N 章 / 🚨已逾期 N 章」注入 P0。
- `arcs[]`：叙事大弧（baseline/stage/inciting_event/strategy/ultimate + `strategy_history`）。
- `milestones[]`：`MS-NNN` 主线航标（target_ch + status:pending/achieved/abandoned）。

### 3.5 `ledger.json` — 复式账本（**最硬的机械约束**）

```
pools: { 池键: {name, unit, initial} }        ← 只有三个键，多一个拒收
transactions: [{chapter, pool, delta(带符号), type, subject, counterparty, note, balance_after}]
```

三条铁律：
1. **余额永远由流水重算**——`pools.current` 与 `balance_after` 都**不是 AI 可信输入字段**，引擎重算后写回；
   提案里声明 `current` 直接整案拒收。
2. **新池必须显式 `initial`**——省略会被当成 0，而欠账/存量类资源池恰恰不从 0 开始。键名拼错（如 `intial`）同样拒收。
3. **流水只能记在本章**——`chapter ≠ 提案所属章` 整案拒收（防跨章改账）。

两条算术闸门（在 `check` 里）：
- `ledger_arith_broken`：`balance_after` 必须 = `initial + 累计 delta`；`pools.current` 必须 = 全部流水重算值。
- `ledger_tx_order`：流水章号必须单调不减——否则 `balance_after` 与编年史互相矛盾，而 recompute 按列表顺序重算会判定「自洽」，无人能发现。
- `amount_arith_unverified`（warning）：**跨文档**闭合——正文写「由 247 变成 234」，必须等于本章该池净变动。

> 实测典故：某章正文写「债从二百四十七变成二百三十四」（正确应为二百一十七），
> beats 验收要点里也是 234，`check` 全程 `ok=True`。现在这条被机械拦住。

### 3.6 `locked.json` — 不可逆事实（写作红线）

```
{id: LOCK-NNN, fact, since_ch, kind, quote, note, refs[]}
```

- `kind` 七类：`death` / `destruction` / `disbandment` / `irreversible_action` / `rule` / `promise` / `pact`
- **`note` 提案层必填**：「不可逆事实的约束力来自『后续写作不得如何』，只记 fact 不记红线，
  日后判断能否绕过时将无据可依。」
- **防静默改史**：复用既有 LOCK ID 改写内容 → `locked_entry_id_reuse` **硬拒**。
  要改史必须 `action="retire"` 留痕后另立新 ID；确认要覆写需显式 `"overwrite": true`。
- **软配额 15 / 硬上限 50**：两个数字刻意不同——15 是「控上下文膨胀」的 advisory 阈值，
  50 是 Pydantic 层真正拒绝写入的天花板。
- 恒定注入 beats 与 pack P0（防吃书硬闸门）。

### 3.7 `cognition.json` — 角色认知边界（**杀上帝视角**）

```
{id: COG-NNN, character, kind, content, since_ch, quote, note, truth_ref}
```

`kind` 四类：`fact`（确凿获知）/ `suspicion`（心生怀疑）/ `misunderstanding`（深信不疑的误区）/ `secret_known`（知晓机密）。

**这是整套系统里最"反 LLM 天性"的一张表**：LLM 天然是全知叙述者，而网文的张力恰恰来自
「读者知道 A，角色 B 不知道 A」。`cognition` 把每个角色的认知边界显式记账，
`probe_secret_leakage` / `probe_cognition_stubs` 两个探针专门抓「知情差穿帮」。

`truth_ref`（挂 `GUN-`/`KNO-`/`EVT-`/`LOCK-`）让引擎能机械判定认知与真相是否冲突，
`derived.knowledge_flags` 输出 `aligned / contradicted / unresolved`，
其中 `contradicted` 含 **B2 穿帮探针**：`belief.since_ch` 早于真相 EVT 章 → 「穿帮嫌疑」。

### 3.8 `derived.json` — 第十二张表（纯派生）

四节 + stats，**全是纯函数 `f(十一表 + final)`**：

| 节 | 内容 |
|---|---|
| `line_temps[]` | 每条线的读者记忆温度 `hot/warm/cold/never/closed` + last_seen_ch + gap |
| `scene_violations[]` | `present_unregistered` / `present_deceased` / `ref_unresolved` / `present_refs_mismatch` |
| `holder_orphans[]` | 道具持有者未登记或已死（持有关系悬空） |
| `knowledge_flags[]` | 认知-真相挂旗（含 B2 穿帮） |
| `stats{}` | 实体数/线数/事件数/活跃时钟/story_day/registry_problems |

**写口径纪律**：sync 封存自动 seal（`verify` 通过后、盖章快照前）；`state recompute` 手动重算；
**提案与手术刀禁写**（`state set derived.*` 直接拒绝）；check 的 `state_offline_edit` 跳过它（缓存语义：重算即合法变更）。

**诚实注记（值得学习的工程态度）**：`derived.scene_violations` 与 `checks` 的在场/已故探针
**逻辑不同、互不蕴含**——前者是「快照判定」，后者是「跨章重放」。
项目明确**不断言两者等价，也不设等价性测试**。

---

## 四、全流程图：一章是怎么出生的

```
Stage 0A  Architect  bible/01~07 世界观公理          [仅开新书]
Stage 0B  Architect  characters/ + outlines/ + 十一表通电
   ↓
Stage 1   Director   beats new ch_XXX --write
                     ← 引擎自动注入：一致性速查 / 💰资源池与ID水位线 / 实体名册
   ↓                 ← pack / ask / pov / calendar / recall / simulate 取证
Stage 2   Drafter    raw/ch_XXX_v1.md      （pack ch_XXX 装配上下文）
Stage 3A  Editor     raw/ch_XXX_v2.md      （剧情做加法）
Stage 3B  Stylist    final/ch_XXX.md       （做减法脱水；★全书唯一法定定稿）
   ↓
Stage 4A  Reader     state/inbox/ch_XXX.json     ← 事实增量提案（v2 分区 / v3 寻址）
Stage 4B  Critic     log/critic/ch_XXX.md        ← 老白催更便签（供下章细纲）
Stage 4C  Auditor    audit ch_XXX --write → log/audit/ch_XXX.md（带 front-matter）
                     hard>0 未裁定 → Stage 5 硬闸门拒绝封存
   ↓                 🔴 硬矛盾 → 定向手术刀修复 → 重跑 audit
Stage 5   Director   sync ch_XXX  （见下方七道闸）
   ↓
Stage 4D  Librarian  每 10 章：近 10 章定稿 vs 四张台账平账（并入在途提案）
          卷末 reconcile vol_XX --write → 对账工作单
```

### `sync ch_XXX` 的七道闸（`commands/state_sync.py::cmd_sync`）

| # | 闸门 | 失败后果 |
|---|---|---|
| 1 | **输入合同**：final + beats + raw 三件齐 | 拒绝空同步（逐件点名缺哪个） |
| 2 | 提案存在且 `chapter` 字段 == 目标章 | 拒收；会扫描非规范命名（`sweep_ch_XXX.json`）并提示 |
| 3 | **引文柔性接地**（RapidFuzz）+ **Stage 5 机械对照电池** | advisory，只出提示（≥85 命中 / 60~85 近似 / <60 存疑） |
| 4 | **Stage 4C 仲裁闸门**（`audit_mode`: strict/advisory/off） | strict 下缺报告 / 缺 front-matter / `hard>0 且 adjudicated=false` → 阻断 |
| 5 | **apply_inbox**：信封校验 → v3 编译 → 幂等登记 → 内存合并（任一分区报错整体不写）→ `verify_data`（写闸门，含前置因果闭环保）→ 落盘（字节级备份 + 失败整体回滚） | 失败归档 `inbox/failed/` + 侧车 |
| 6 | **verify_state** 状态体检 | 通过才派生封存 → final 盖章 → 十一表 SHA-256 盖章 → 快照 `<ch>_done` → `changelog.seal_chapter` |
| 7 | 增量更新 SQLite FTS5 索引 | 异常静默降级 |

**写入时序的崩溃安全设计**（`apply_proposal` 注释里写得极清楚）：
> 状态文件先写、幂等登记簿后写。崩溃窗口 = 状态已写但登记簿未写 → 重启后提案被重放。
> 安全前提：所有 `_merge_*` 函数对同一提案的重放必须幂等。

对应的幂等手段：`transactions` 按 `_tx_replay_key` 去重；`cognition` 按内容指纹去重；
`lines` 按 `_same_line_content` 去重；`entities/timeline/locked` 按 key upsert。

---

## 五、提案机制：章节事实增量的唯一写入口

### 5.1 为什么是「提案」而不是「直接改状态」

`state/*.json` 是机器真值。如果任何 Agent 都能直接写，四件事会失控：
审计链断裂、账本算术被破坏、改史无痕、并发撕裂。

所以设计成：**Reader 只落盘提案 JSON → 主控跑 `sync` → 引擎四道闸 → 落盘**。

### 5.2 v2 分区 vs v3 寻址

| | v2 | v3 |
|---|---|---|
| schema | `novel-studio.state-mutation/v2` | `novel-studio.state-mutation/v3` |
| 形状 | 按表分区（`entities[]`/`lines[]`/`ledger{}`…） | `ops[]` 数组，每元素 `{table, action, …载荷}` |
| 实体寻址 | id 优先、名次之（**名字写错 = 静默新建碎片**） | **严格寻址**：create 要求 id/名双不存在；update 要求 id 存在且归属表一致 |
| 定位 | 语义直观 | **防错**：寻址失败整案拒收，错误带 `[op#N table/action]` |

`proposal_v3.compile_ops()` 是**纯函数**，把 v3 ops 编译成 v2 等价提案，然后走**完全相同的下游管线**
——「语义对齐 by construction」。登记簿存 **v3 原文哈希**（登记簿恒为「输入原文」语义）。

一个精巧细节：**v3 预门**。编译的存在性检查必须跑在幂等登记簿主门**之前**——
否则 create 类提案崩溃重放会先撞「已存在」而永远到不了门。所以同字节/同 op 重放在编译前短路为干净 skip。

### 5.3 四道闸

1. **信封 schema**（`validator.validate` + `models.validate_with_model`）
   —— Pydantic `extra="forbid"`，未知键一律拒（防拼错字段静默 no-op）。
2. **业务规则**（`state.validate_proposal`）
   —— 白名单字段名、枚举取值、数值区间、跨字段一致性（charges ≤ max_charges、income 必须 delta>0）、
   同提案重名/别名冲突、跨章账本注入。
3. **幂等登记**（`.applied_operations.json`）
   —— 同 id 同内容 = 跳过；同 id 异内容 = **拒收**（防复用 id 悄悄改内容）。
4. **写闸门 `verify_data`**
   —— 落盘前对**合并后的全量副本**再校验：模型合法性 + 账本重算闭合 + 编号唯一 + 引用闭合
   + **前置因果闭环保**。`derived` 分区提案禁写。

内存事务：先全量 `deepcopy` 到副本，任一分区报错则**整体不写**（`rep["updated"]` 清空）。
落盘阶段带字节级备份，写失败即整体回滚；**回滚自身失败必须上抛**（静默吞掉会造成「宣称已回滚、现场却撕裂」的假安全）。

---

## 六、校验体系：单一真源链

```
engine/models/*.py  (Pydantic V2)
        │  唯一真源：字段/类型/枚举/约束
        ↓  python -m engine.models.schema_gen
engine/schemas/*.json  (构建产物，禁手改)
        │  + _gate_patch：落盘必完整（台账条目必带 status，顶层键必填）
        │  + _strip_null_branches：全局摘除 anyOf 的 null 分支
        ↓
validator.validate()   ← 读写闸门（load/save 都过）
```

**纪律**：枚举与类型集合一律**从 Pydantic 模型派生**（`state._ENTITY_STATUS`、`_LIFE_STATUS`、`_ATTITUDE`
全部来自模型枚举），禁止在校验分支里再手写字面量。否则模型漂移时「只有模型会赢，校验层却仍按旧词表放行」。

闸门补丁层是**有意比模型更严**的持久层完整性闸门：
> 全部 Optional 字段拒绝显式 null —— Optional 键要么缺席、要么为合法值。

这条规则防的是 `e.get("type", "person")` 在「键存在但值为 None」时静默失效。

---

## 七、体检体系（`check` / `doctor`）

**双核体检**：

- **内核一 · 系统工程运行时健康**：依赖缺失、工作区权限、正文截断（末句标点/连接词/引号失衡）、
  project.json 完整性、状态机一致性、账本算术与顺序。
- **内核二 · 商业小说叙事健康**：伏笔饥饿/逾期/零落笔、线配额、章型占比与连续高压疲劳、
  主角视角失焦、声纹漂移、字数出带、里程碑逾期、支线停滞。

**55 个错误码**注册在 `engine/errcodes.py`（单一真源），每个码带 `level / description / remedy`，
`--json` 供 Agent 自助修复。`checks.DEFAULT_REMEDIES` 由它派生，禁止别处再手写 remedy；
新增错误码漏注册，**测试当场报警**。

设计原则很明确：**errors 只允许事实级**（吃书/算术/引用断裂）；风格与节奏类一律 warning/info。
新书 Stage 0 未填的 `{{slot:}}` 出 `stage0_onboarding` **info，不阻断**，开写后恢复硬闸门。

---

## 八、上下文装配（`pack`）与角色读权限网关

### 8.1 三层装配

| 层 | 内容 | 特点 |
|---|---|---|
| **P0 热** | current 现场 / 卷阶段 / 世界锚点 / beats / 上章 tail 1000 字 / 硬提醒 / 前情卷末态势(rollup ≤500tok) / 冷线回收锚定提示 / 场景张力 / 信息差机锋 | 每章必装 |
| **P1 触发** | 实体卡（≤12）+ 1-hop 间接关联（≤5）+ 近 10 章梗概脊梁 | 按 beats 提及 / 在场 / 近 15 章出现触发 |
| **P2 冷索引** | 全书文件索引（路径+token 估算）+ 近 10 章实体出现频次指针 | 只给「去哪取」，不给内容 |

**预算硬裁**：`PACK_TOKEN_CAP = 18000`，超了优先裁 P2 冷索引，P0/P1 保留；裁空仍超则标 `hard_cap_breached`。

**智能剪枝**：
- **分卷视界隔离**：实体若 `scope` 指向其他卷且不在场、未被 beats 点名 → 休眠冷备。
- **近期热度门**：`ch_num > 5` 时，近 15 章没出现过、不在场、beats 没点名的实体不装配。
- **地点强保底**：当前 `location` 字符串里含已注册地点名 → 强制装配该地点卡。

### 8.2 角色读权限网关（`pack --open <路径> --as <角色>`）

`ROLE_DENY`（前缀禁）+ `ROLE_DENY_SEGMENT`（段级禁，如 `/raw/`）+ `ROLE_ALLOW_EXTRA`（精确单文件白名单）。

| 角色 | 禁读 |
|---|---|
| director / evolver | （全量） |
| drafter / editor | state/ bible/ characters/ log/（editor 例外：bible/06 文风宪法） |
| stylist | state/ bible/ characters/ entities/ log/（例外：bible/06） |
| reader | state/ bible/ characters/ + `/raw/`（例外：实体四表，仅用于核对 ID 防撞） |
| critic | outlines/ bible/ characters/ state/ log/ + `/raw/`（例外：state/current.json） |
| auditor | state/ bible/ characters/ entities/ + `/raw/`（例外：locked/current/实体四表） |
| librarian | state/ outlines/ bible/ characters/ entities/ log/（例外：实体四表+lines+locked+ledger） |

安全细节：路径先 `normpath` 消解 `.`/`..`/反斜杠再匹配，防 `manuscript/../bible/style.md` 绕过；
`ROLE_ALLOW_EXTRA` 必须**精确相等**（防 `state/current.json.bak`）；越界 `..` 由 `safe_child_path` 兜底；
未知角色按最严格处理。

> 设计意图：**Reader 禁读账本，却必须知道池键名和已用 ID 水位线**。
> 解法是让引擎在 `beats new` 时把「💰 资源池与 ID 水位线」小节注入细纲——
> 不破坏权限边界，又消灭了「猜键名」这个必错环节。这是很漂亮的工程妥协。

---

## 九、辅助子系统

| 模块 | 职责 | 关键设计 |
|---|---|---|
| `changelog.py` | **事件溯源**：`state/changelog.jsonl` 字段级变更事件流 | 不变量 `fold(基线, 事件) == 磁盘`；供 `state at`(时点切面) / `state diff` / `state blame`(字段级溯源)；快照回滚**不清空历史**而是记为事件 |
| `migrations.py` | 状态机版本化（当前 v6） | 老书首次读取：先快照 → 迁移 → 闸门预验 → 落盘；只修结构不碰事实 |
| `snapshot.py` | 快照 create/list/rollback | `--clean-drafts` 清理超前稿件；sync 自动 `<ch>_done` |
| `rollup.py` | 卷级态势摘要 | 装配成本 O(当前卷)；远卷只给 ≤500 token 摘要。与 snapshot（精确回滚点）/changelog（字段级史）三分 |
| `memory.py` | 读者记忆派生 | `working/fuzzy/impression/never` 四档 tier；阈值 `cold_base + per_weight × weight` 按权重缩放 |
| `voiceprint.py` | 对白声纹漂移 | 只测「怎么说话」不测人设；info 级不阻断 |
| `audit.py` | **8 大确定性探针** | locked 违背 / 在场与死亡 / 道具充能 / 金额一致 / 知情差泄露 / 认知差冲突 / 别名漂移 / 称谓与修饰词对账 |
| `evidence.py` | 只读取证（零裁决） | ask 2.0：每条命中带 `cite{table,key,chapters}`；pov 角色视角包 |
| `graph.py` | NetworkX 实体拓扑 | path / neighbors / isolated / centrality / 场景张力提取 |
| `db.py` | SQLite 双平面投影 + FTS5 | 增量缓存：定稿指纹 `finals_fp` + 按章内容哈希 `fts_ch_hash`（改稿才重刷）；FTS 只当缓存不当召回器 |
| `recall.py` | 知乎残酷四问 | 0 Token 自证：主要人物知道什么 / 哪三条不能改 / 伏笔未兑现 / 下章红线 |
| `simulate.py` | 剧情推演沙盒 | `impact` 因果链波及测算（模拟杀角色/毁道具/揭密）/`branch` 多走向参谋 |
| `reconcile.py` | 卷末对账大修（Stage 4D） | 机械复扫 + 本卷 8 探针重跑 + 高危字段变更史 + 投影 diff（未登记专名/零出现实体）→ LLM 对账工作单 |
| `cockpit.py` | 主控态势驾驶舱 | 工作流导航（当前工序指针 + 下一步派谁）+ 戏剧动力学 + 伏笔雷达 + 角色活跃度 + 自愈处方 |

---

## 十、设计取舍清单（值得抄的部分）

1. **事实与创作分离**：创作可以脑补，事实必须对账。事实唯一源 = `final` 定稿；状态唯一真值 = 十一表。
2. **余额不可信**：`balance_after` / `pools.current` 一律重算，AI 声明即拒收。
3. **引文柔性接地，绝不阻断**：`quote` 相似度 ≥85 命中 / 60~85 近似 / <60 存疑。
   「摘录严禁逐字抠字眼浪费算力；但战死/退役等高危变更强烈建议附引文」——算力与可审计性的平衡点。
4. **advisory 文化**：高危状态迁移（复活/退场反转/立场大翻转/充能回升）与时间线回退**只出警示、绝不阻断**，
   裁决权归主控。引擎不替作者做艺术决定。
5. **空值语义显式化**：`current` 空串 = 不修改；闸门层显式 null = 非法（键要么缺席要么合法值）。
6. **分层门**：信封错 → 先修信封；寻址错 → `[op#N]` 点名；字段错 → 沿用 v2 措辞。
   结构坏了就不跑业务，错误信息一次给全而不是一个个蹦。
7. **崩溃窗口被显式命名**：状态先写、登记簿后写，安全前提是所有 merge 幂等。
8. **不断言自己没验证的东西**：`derived` 快照判定与 `checks` 历时审计「逻辑不同、互不蕴含」，
   **不设等价性测试**。这种诚实注记比强行统一更有价值。
9. **单一真源成瘾**：枚举派生自 Pydantic、remedy 派生自 errcodes、版本戳驱动迁移、
   `LOCATION_TYPES` 唯一真源、schema 为构建产物——几乎每种「两处写同一件事」都被消灭了。

---

## 十一、实测发现的问题（跑通一遍流水线时撞到）

### 11.1 `derived.json` 封存必失败（功能性缺陷，中高优先）

**现象**：`sync` 成功但打印 `⚠️ 派生封存异常（不阻断）：ValueError: 拒绝写入非法 derived.json:
$.line_temps[0].last_seen_ch: 类型应为 integer，实际 null; $.line_temps[0].gap: 类型应为 integer，实际 null`。
`state recompute` 同样失败。第十二张表**永远是空表**。

**根因**：两条规则打架。
- `schema_gen._strip_null_branches` 的全局闸门规则：**任何 Optional 字段拒绝显式 null**（键要么缺席要么合法值）。
- `objects/derive.py::_derive_line_temps` 却显式写 `"last_seen_ch": None, "gap": None`
  （① 闭环线快照分支硬编码；② `memory.line_memory_map` 对「零落笔线」返回 `last_seen_ch=None`）。

**触发条件**：只要存在**任意一条** `never` 温度的线或**任意一条已闭环**的线 → 派生封存必失败。
这几乎是所有正常连载到中后期的书。

**为什么测试没抓到**：`tests/test_objects.py` 用的夹具里线都在 final 正文中出现过（`last_seen_ch` 是整数），
**从未走过 None 分支**（`tests/test_memory.py:119` 断言了 `last_seen_ch is None`，但那是 memory 层，不进 derived）。

**影响**：`derived` 是「第十二张表」——`state object` 的挂旗速览、cockpit 的统计、
场景合法性告警全部失效。因为设计成「派生永不炸封存」，失败是静默降级，很容易长期不被发现。

**建议修法**（二选一，倾向前者）：
- `derive.py` 里对 `None` 值的键**直接不写**（`if v is not None`），符合「键要么缺席要么合法值」的闸门语义；
- 或在 `schema_gen._gate_patch` 里给 `derived.line_temps` 两个键开 null 白名单（不推荐，破全局规则的一致性）。
- 同时补一个「含零落笔线 + 含闭环线」的 fixture 测试，钉住 `seal_derived` 不抛异常。

### 11.2 `state blame` 章号显示重复前缀（展示层小瑕疵）

`engine/commands/state_sync.py:1376`：
```python
when = f"ch_{ev.get('ch')}" if ev.get("ch") else ...
```
`ev["ch"]` 已是 `"ch_001"` → 渲染成 `ch_ch_001`。改为 `ev.get("ch")` 即可。

---

## 附：读代码的推荐路径

1. `README.md` → `AGENTS.md`（宪法与角色矩阵）
2. `studio.py`（薄壳，看退出码 3 的处理）→ `engine/cli.py::COMMAND_HELP / STAGE_MAP / RECIPES`
3. `engine/models/`（**十二张表的字段真源，逐字段带 description**）
4. `engine/state.py::validate_proposal`（业务规则全集）→ `_merge_*`（合并语义）→ `apply_proposal`（事务与回滚）→ `verify_data`（写闸门）
5. `engine/checks.py::run_checks`（双核体检）+ `engine/errcodes.py`（55 码说明书）
6. `engine/pack.py::build_pack`（三层装配）+ `ROLE_DENY`（权限网关）
7. `docs/OBJECT_MODEL.md` + `engine/objects/`（对象层与派生）
8. 任选一个 `.agents/skills/*/SKILL.md` 对照看角色契约如何落地
