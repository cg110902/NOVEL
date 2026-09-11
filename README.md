# Novel Studio 3.1

Antigravity 原生多智能体中文网络小说创作流水线：**确定性 Python 引擎**（`engine/`，黑盒）
+ **角色协议文档**（`AGENTS.md` 与 `.agents/skills/*/SKILL.md`）+ **模板资产**（`templates/`）。

分工原则：能算的一律由引擎算（状态机、账本重算、事实体检、上下文装配），
需要判断力的才交给子代理（写细纲、写正文、裁决矛盾）。

---

## 一、三十秒上手

```bash
# 1. 安装依赖（Python >= 3.10）
pip install -r requirements.txt

# 2. 建一本书（书目录必须在工作区根之下）
python studio.py init -w workspace/我的书 -t 我的书 -g 仙侠 -p 主角名

# 3. 主控自查：命令目录 / 阶段配方 / 退出码契约的唯一入口
python studio.py help --json

# 4. 态势驾驶舱：当前工序指针 + 下一步该派谁 + 自愈处方
python studio.py cockpit -w workspace/我的书

# 5. 事实体检（有 errors 退出码 1）
python studio.py check -w workspace/我的书
```

工作区根默认是 `<repo>/workspace`；用环境变量 `NOVEL_STUDIO_WORKSPACE_ROOT` 可重定向
（测试与多书并行时用它隔离）。所有命令都用 `-w <书目录>` 指定书，缺省只在「工作区里恰好一本书」时才自动选中。

---

## 二、流水线一图流

```
Stage 0A/0B  Architect   世界观公理 + 人物大纲 + 十一表播种（设定层直写）
Stage 1      Director    细纲构思 beats（引擎注入一致性速查 / 资源池键名+ID 水位线 / 提案键形状）
Stage 2      Drafter     初稿 raw_v1
Stage 3A     Editor      骨肉重塑 raw_v2
Stage 3B     Stylist     通俗脱水 final（全书唯一法定定稿）
Stage 4A     Reader      事实提案 state/inbox/ch_XXX.json
Stage 4B     Critic      老白催更便签 log/critic/ch_XXX.md
Stage 4C     Auditor     三轨一致性仲裁 log/audit/ch_XXX.md（front-matter: hard/soft/logic，Stage 5 硬闸门）
Stage 4D     Librarian   每 10 章长程巡检（近 10 章定稿 vs 四张台账平账）
Stage 5      Director    sync：提案合并 + 十一表盖章 + 快照封存
Evolution    Evolver     人类变更诉求的波及面测算与手术刀改版
```

完整流程图、派发令/回执单格式、各角色准读准写清单见 **`AGENTS.md`**；
每个角色的工艺纪律见 **`.agents/skills/<角色>/SKILL.md`**。

> 📜 **beats 是当章唯一合同**：
> `outlines/vol_XX/beats/ch_XXX.md` 由主控写，
> Editor / Stylist / Reader / Auditor
> 四路子代理**直读**，
> Drafter 经 `pack` P0 拿到**逐字全文**，
> Critic 与 Librarian 明令**禁读**（前者要纯读者
> 盲审、后者只对账不读意图）。
> 动机：`state/` 只知"已发生什么"、不知"本章要写什么"，
> beats 把 bible + 台账 + 本意压成 O(1) 当章快照，让五个下游共享同一基准而不必各翻账本；
> 代价是它同时是最大注入物与最脆单点——细纲写虚整条流水线一起歪，故引擎对其有 5 档
> `beats_*` 闸门（`beats_missing_form`／`beats_fm_extra_keys`／`beats_scene_abstract`／`beats_overlap`／`beats_form_repeat_without_reason`）
> 与 `sync` 的"beats 齐"硬合同；
> 注意 `goal`/`hook` **没有**机械校验，
> 细纲写虚只能靠下游角色上报——这是 Editor/Auditor 负有"基准缺失即上报"义务的原因。

---

## 三、目录导航

| 路径 | 内容 |
|---|---|
| `studio.py` | CLI 入口薄壳 |
| `engine/` | 确定性引擎（状态机 / 体检 / 审计探针 / 上下文装配 / 图谱 / 索引） |
| `engine/README.md` | 引擎模块地图与 lore 系列速查说明 |
| `engine/schemas/*.json` | 由 `engine/models/schema_gen.py` 从 Pydantic 模型生成，勿手改 |
| `AGENTS.md` | 主控章程：流水线、角色矩阵、工序协议、目录契约 |
| `.agents/skills/*/SKILL.md` | 10 个角色的技能卡（准读/准写/工艺/回执） |
| `templates/` | 建书脚手架：bible 七表、人物卡、大纲、beats、`project.json` |
| `templates/README.md` | 模板字段逐项说明（与 Pydantic 模型同口径） |
| `requirements.txt` | 运行时依赖（与 `pyproject.toml` 同源） |

书工作区（`workspace/<书名>/`）内的目录契约：

| 路径 | 内容 |
|---|---|
| `project.json` | 书级参数（题材、主角、字数目标带、词表旋钮） |
| `bible/01..07` | 世界圣经七表（公理/战力/势力地理/经济道具/特殊机制/文风宪法/偏离清单） |
| `characters/`、`entities/` | 人物卡与实体卡 |
| `outlines/` | 主线大纲 + 分卷大纲 + `beats/ch_XXX.md` 细纲任务书 |
| `manuscript/vol_XX/{raw,final}/` | 毛坯 `_v1` / 初修 `_v2` / 法定定稿 |
| `state/*.json` | 十一表真值：current / persons / items / factions / places / lines / timeline / ledger / synopsis / locked / cognition |
| `state/inbox/` | 提案收件箱（`processed/` 为审计留痕，永不删改） |
| `log/{audit,critic,review}/` | 仲裁报告 / 催更便签 / 校对与巡检报告 |
| `snapshots/` | 快照与回滚点 |

---

## 四、十一表真值与写入口

`state/*.json` 十一张表是机器真值，读写都过 `engine/schemas/` 的声明式校验。

- **章节事实增量的唯一写入口是提案**：Reader 落盘 `state/inbox/ch_XXX.json` →
  主控 `python studio.py sync ch_XXX`（支持 `--dry-run` 预演）→ 过 schema 校验、
  引文柔性接地、幂等登记、复式记账重算四道闸才落盘。
- **设定层例外**：Stage 0 建书播种与跨卷改版由 Architect/Evolver 直接写 `state/*.json`。
- **机械证据**：每次 `sync` 对十一表盖章 SHA-256（`state/inbox/processed/state_hashes.json`），
  绕过提案的离线手改由 `check` 的 `state_offline_edit` 档指名报出；
- **事件溯源**：`state/changelog.jsonl` 记录十一表字段级变更事件流（谁、哪章、哪个通道、
  把哪个路径从什么改成什么），由引擎在唯一写入咽喉自动派生、离线手改自动补录、
  快照回滚不清空历史——`fold(基线, 事件) == 磁盘` 是其对账不变量。
- **派生封存**：`state/derived.json` 是第十二张表（纯派生缓存，删了可重算）：每次 `sync`
  自动 seal（线温 / 场景告警 / 持有悬空 / 认知挂旗四节），`state recompute` 可随时手动重算；
  提案与手术刀禁止写入，`check` 的离线改动检出跳过它。
- **账本口径**：余额永远由流水重算，`balance_after` / `current` 不是可信输入字段。
- **改史留痕**：不可逆事实（locked）与角色认知（cognition）禁止同 ID 静默覆盖——
  幂等重放放行，改写历史需 `action="retire"` 或显式 `"overwrite": true`。
- **审计三轨硬闸门**：`audit <章> --write` 生成带 front-matter 的仲裁骨架，`sync` 据此放行——
  `hard > 0`（机械矛盾）或 🧠 `logic > 0`（语义出戏）且未 `adjudicated: true` 一律拒封
  （`audit_mode: advisory` 降为提示）。🧠 轨是 **Auditor 的 LLM 专属判断**：世界观类目污染 / 违背世界公理 /
  性格突变 / 因果与代价断链 / 现场常识与时空矛盾，这类"读者当场出戏"的问题 `check` **结构上查不出来**
  （引擎没有散文语义能力），所以做成第三轨而不是第四张探针清单；处置三选一：改正文（Stylist 手术刀）/
  转办 Evolver（设定层）/ 降级为 🟡 存疑（不计入 `logic`）。
- **装配预算契约**（`pack`）：总量上限 **2W TOKEN**；超预算按**压缩阶梯**由远及近裁
  （P2 冷索引 → P2 旧章指针 → P1 间接关联 → P1 脊柱 → P0 上章余温），而**细纲全文 / current 块 / 硬提醒 /
  不可逆事实 / 钉住的世界锚点永不自动裁**，裁尽仍超则如实报 `hard_cap_breached` 交主控取舍。
  `world_anchors` 按细纲 front-matter 的 `world_refs:`（逗号/顿号分隔、**须用设定原文用词**）取用——
  命中 `bible` 的哪些 `##`/`###` 小节就只装那些（**最多取前 8 个 refs**，超出忽略并在包里点名）；
  缺省＝恒给（旧书零改动）；声明了却零命中 → 回退恒给并
  回列「可钉的节」；命中但漏掉基础组（世界公理 / 战力标尺 / 势力地理 / 经济品阶 / 特殊机制）→ 包里
  打印 ⚠️ 点名缺哪组（引擎不擅自扩大注入，避免"收窄"变成"偷偷多给"）。
  `pack --open` 与子代理的 `file_index` 同过准读网关（`ROLE_DENY` / `ROLE_ALLOW_EXTRA`）：被禁文件只报数量不报路径。
- **书级配置真源**：`project.json` 共 **20 个顶层键**——建档元数据（`schema` `title` `genre` `protagonist` `created_at`）
  ＋引擎旋钮（`words_target` `lines_cap` `audit_mode` `tier_shift_grace` `voiceprint` `reader_memory` `state_watch`）
  ＋取证词表（`candidate_stopwords` `latin_allowlist`）＋**六张题材词表**（`generic_stopwords`
  `critical_injury_words` `abstract_phrases` `high_heat_forms` `empty_criteria_words` `hook_words`）；
  六张词表脚手架给的是**跨题材兜底种子**（保证新书开箱即有启发式可跑），Architect 的职责是按本书题材
  **重写/增删**而不是填空；**语义三分**：键缺席＝该档停用（`check` 报 `wordlist_unconfigured` info 逐键提醒）、
  显式 `[]`＝明确关闭（不报，须在 `bible/06` 留理由）、非空＝按题材生效。
  以 `templates/project.json` 为唯一真源（逐键注释就写在该文件里，语义说明见 `templates/README.md` 第一节）；
  它是 STATE_KEYS **之外**的配置表（不参与提案、指纹与留痕），只由 `config set` 与用户手改写入；
  `status` / `check` 报出的键名缺失都以此文件为基准。

提案字段契约的逐项说明见书工作区内的 `state/inbox/README.md`（由 `init` 生成）；子代理（Reader）不必读它，
其键形状由 `beats new` 注入的 `📐 提案通道与键形状` 一节就地给出。

---

## 五、常用命令

| 场景 | 命令 |
|---|---|
| 命令目录与阶段配方 | `python studio.py help --json` |
| 工作区/工序总览 | `python studio.py status` · `cockpit [ch]` |
| 单章上下文装配 | `python studio.py pack ch_XXX [--lean／--full] [--open 路径 --as 角色]`（2W token 预算，超量自动压缩） |
| 只读取证 | `python studio.py ask <关键词>`（2.0 引用链：每条命中带 cite 出处） · `evidence <kind>` · `pov` · `calendar` |
| 细纲与稿件流转 | `beats new ch_XXX --write`（注入一致性速查 / 资源池 / ID 水位线 / 提案键形状，并支持 `world_refs` 按章取设定） · `critic` · `audit ch_XXX --write`（三轨仲裁） · `reconcile vol_XX`（卷末对账） |
| 提案 | `proposal new [--v3] ch_XXX`（骨架；--v3 为寻址式防错版） · `proposal check ch_XXX` · `proposal auto ch_XXX --write` · `sync ch_XXX [--dry-run]` |
| 体检与自愈 | `check`（`doctor` 为其别名；`--trend` 分数曲线 / `--bisect` 快照二分 / `--full` 全量 / `--accept` 确认消音） · `errcodes <码>` |
| 图谱与索引 | `graph <action>` · `index [--rebuild]` · `recall` · `simulate` |
| 台账手术刀 | `state get/set` · `state at <章>`（时点切面）· `state diff <章A> <章B>` · `state blame <表.路径>`（字段级溯源） · `state rollup vol_XX`（卷末态势摘要，pack 前情注入源） · `ledger recompute` · `milestone add/achieve` |
| 快照 | `snapshot create/list/rollback` · `checkpoint` |

`--as <角色>` 的准读清单与各角色 SKILL.md 的准读清单一一对应（单一真源在
`engine/pack.py` 的 `ROLE_DENY` / `ROLE_ALLOW_EXTRA`）；越权读取一律拒绝。

退出码契约：`0` = 正常 / `1` = 阻断（含 `check` 有 errors、`sync` 失败）/ `2` = 用法错 /
`3` = 运行环境缺依赖（会打印缺失模块与安装命令，不抛裸 traceback）。
错误码的机器可读说明书：`python studio.py errcodes <码>` 查单码（含义 / 触发条件 / 处置处方，`--json` 机读），
`python studio.py errcodes` 看全表（当前 106 条闸门码，`--level error` 过滤）；注册表在 `engine/errcodes.py`，
新增体检码必须在此注册（文档里的码数由 `tests/test_docs_parity.py` 与本表实时对账）。

---


## 六、开发约定

- `engine/schemas/*.json` 由 `python -m engine.models.schema_gen` 生成；改模型后重跑，
  仓库里不应出现漂移。
- 枚举与类型集合一律从 Pydantic 模型派生（如 `LOCATION_TYPES`、`state._ATTITUDE`），
  禁止在校验分支里再手写字面量集合。
- 新增 `check` 错误码必须在 `engine/errcodes.py` 注册。
- 门禁三件套（改引擎必跑，全绿才算完）：
  `python -m tests.test_docs_parity`（文档数字对账）＋
  `python -m tests.test_smoke`（临时书整章冒烟）＋
  `python -m tests.test_gates`（温度判定边界＋违规注入触发）。
- 压力/浸泡测试（规模档判引擎在千章量级下是否仍守约定；零 token 剧本驱动）：
  `python studio.py stress all --scale smoke`（harness 自测档）；`--scale full|chap-hell|word-hell`
  为规模档，闸门按 Phase 推进（上一 Phase 不绿不开下一 Phase），首跑只建基线不判性能。
  设计真源见 `tests/stress/`（common/generator/soak/faults/eval/report/cli）。
- 用户可见文案里的数量口径（命令数、状态表数、字段数）改动时，同步更新
  `AGENTS.md` / `engine/README.md` / `templates/README.md`——这些口径由 `python -m tests.test_docs_parity`
  自动比对（命令数 = `len(COMMAND_HELP)`、状态表数 = `len(STATE_KEYS)`、错误码数 = `len(REGISTRY)`），
  跑不过就回去改文档，不要反过来把数字改小。
- 状态表口径的唯一说法：**十一表** = 11 张断言表（`ASSERTED_KEYS`，Agent 可写）；
  **第十二张表** = `derived.json` 派生缓存（`STATE_KEYS` = 十一表 + derived）；
  `project.json` 是 STATE_KEYS 之外的书级配置表，**不占表号**（表号只编到第十二张）。
