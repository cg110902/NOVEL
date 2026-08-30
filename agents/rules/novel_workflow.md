# novel_workflow.md — 流水线剧本（Stage 0–4 唯一 SOP）

本文件是"什么时候、谁、做什么、产物交到哪"的唯一权威；文学标准在 `novel_craft.md`
（引用写法示例：`novel_craft.md#视角与信息差`），禁令与权威层级在 `AGENTS.md`。每阶段四件事：
输入合同 → 动作 → 输出合同 → 退回边。**上一阶段输出合同不齐，不得开始本阶段**——这句话本身也只在这里说。

## 阶段总览

Stage 0 初始化 → Stage 1 细纲+任务书（主控）→ Stage 2 起草（一次性子代理）→
Stage 3 重铸精修（一次性子代理）→ Stage 4 同步封存（主控）。同一章走 1→2→3→4；
退回边总是"回上一站"，没有跳站捷径（Stage 3 拒收回 Stage 2，例外由主控亲自代笔时才算例外）。

## 工作区

```
workspace/<slug>/
  project.json        # 书配置：title/genre/protagonist/mode/words_target/style_guards
  bible/              # 圣经+世界+势力；必有「本书偏离清单」一节（覆盖唯一合法通道）
  characters/         # 人物卡（自由文本；机器字段在 state/entities.json，卡上无格式义务）
  outlines/main_plot.md + vol_XX/outline.md + vol_XX/beats/ch_XXX.md
  manuscript/vol_XX/raw/ch_XXX_vN.md | final/ch_XXX.md
  state/              # 6 个 JSON + inbox/{processed,failed,README.md} + snapshots（schema 见 engine/schemas/）
  log/review/         # 主控审校注记：ch_XXX.md（init 自动创建；sync 的 review_gate 依此核对）
```

## 状态字段口径（state/current.json + synopsis）

`current.json` 是"主角/场景此刻"的速写，仅供 pack 的 P0 提示上下文，不要求与正文逐字一致
（正文才是叙事真值；不一致属事实错误，需修）。字段含义：

- `time` / `location`：此刻时间（用 timeline 历法口径）与地点。
- `power_level` / `abilities`：能力/修为阶梯摘要（阶梯里程碑在 `timeline.arcs`）。
- `injury` / `equipment` / `assets`：当前伤势、随身装备、非资金类资源。
- `situation`：一句话处境（便于下一章 pack 快速回温）。
- `key_relationships`：当前主要关系速写（软状态，引擎不校验；如"沈拓↔赵四：敌对未明"）。
  关系没动可不写；动了就更新——它只进 pack 的 P0 回温，不是真值。
- `present_characters`：本章/当前在场角色名（必须已注册在 `state/entities.json`，sync 强制闭合）。

`synopsis.json`：`book_logline`（全书一句话）+ `chapters`（每章 `num/title/synopsis/source=manual`）。
梗概只记录"发生了什么"，不记录"写得怎么样"。

## 术语约定（全仓库唯一口径）

> **章节号口径（重要）**：`ch_NNN` 是**全书连续**的全局章号身份（lines 的 `target_ch`、sync 的目标、
> 状态流水线行一律用它）。卷 `vol_XX` **只是文件系统分组目录**——某一章只出现在一个卷里，
> 且**跨卷不允许同号**（同一个 `ch_NNN` 不应既在 vol_01 又在 vol_02）。引擎为防文件误移，
> 在 `check`/`export`/`evidence.final_chapters` 内部用 `(卷, 章号)` 作文件叠代键（跨卷同号互不覆盖），
> 这是**容错实现**，不是"允许跨卷同号"的语义约定。凡真值数据（lines、ledger、synopsis、current）
> 一律只认全局 `ch_NNN`。

- **事实（两义）**：① **提案事实** = 提案里提交给状态机的每一条增量，能在本章 final 正文找到出处
  （AGENTS 禁令 7）；② **情节事实** = 场序、动机、事件因果、数字与专名，修改它们属内容级改动，
  只能回 raw 重走 Stage 3（见本文件#文字级边界）。上下文出现"事实"时按上述分义读取。
- **lines 台账** = `state/lines.json` 的三线登记簿：伏笔 `GUN-*`、误会 `MIS-*`、知识线 `KNO-*`
  （秘密/信息账：secret 一句话 + 计划揭示章 target_ch，状态 Concealed/Revealed）。
  三类都有 target_ch（章号或 longline），逾期由 check 报数；**揭没揭由你判断**，引擎只记账。
- **ledger 账本** = `state/ledger.json` 的资金/资源池流水，余额由引擎重算，"账本 current 值"指这里。
- **越界知情** = 角色的言行使他表现出尚未通过剧情获得的信息；判定标准见 `novel_craft.md#知识是资产`。

## 写权限矩阵

| 角色 | 读 | 写 |
|---|---|---|
| 主控（导演/编排一体） | 一切 | `project.json`、`bible/`、`outlines/`、`state/inbox/` 提案、final 的文字级终检补丁 |
| 起草 Agent | 一切 | 仅 `manuscript/vol_XX/raw/` (放飞算力，自由创作)|
| 审校 Agent | 一切 | `manuscript/vol_XX/final/`（重铸精修，仅此一件） |
| 引擎 | 一切 | `state/*.json`、快照、processed/failed、evidence 输出 |

## Stage 0 初始化（主控）

- 输入合同：题材与书名（用户没说就问一次，拿到后写进 project.json，不再问）。
- 动作：
  1. `python studio.py init -w workspace/<slug> -t <书名> -g <题材> -p <主角名>`；
  2. 读 `agents/genre_guide.md` 对应题材节，**做选择题**：字数带、钩子习性、可玩词汇，
     选中的抄进 bible 与 project.json，没选中的不解释；
  3. 按 templates/ 引导注释填 `bible/project_bible.md`（含「本书偏离清单」，开局可为空节）、
     `characters/` 主要角色卡、`outlines/main_plot.md`（全书脊柱：开局状态→终局→中继点）；
  4. 跑 `check`，确认无 unfilled_slot / project 字段错误。
- 输出合同：`check` 零 errors。退回边：check 红 → 继续填，不进 Stage 1。

## Stage 1 细纲+任务书（由主控亲自完成）

- 输入合同：`status` 流水线行 + `evidence gaps`（哪些线快到期/已逾期）+ `evidence prev`
  （上章 form/旋钮/words 带/必须保留对照卡；pack 的旧章指针只覆盖近 10 章，更早的章节
  指针用 `evidence mentions <名字>` 查全章出现处）+ `state/current.json` + main_plot 与卷纲。
- 动作：
  1. 选章 = 流水线第一个缺口章号（禁止跳章写，除非用户明说，见下文#模式与控制）；
  2. 掷 form 骰（`novel_craft.md#反公式化与拟人化`）：同卷统计与连章重复约束由 check 机械兜底；
  3. 写 beats 正文：场景切分、信息差动作（`novel_craft.md#视角与信息差`）、本章要埋/唤/还的线；
  4. 在 beats 尾部写任务书（见#任务书合同）——限制装配是你的核心工作：每章的禁忌、
     必须保留、验收都不同，这是灵活性的来源而不是负担；禁忌节里可机械计数的词同步写进
     front-matter `guard_extra`；
  5. 自交检：「验收」每条能对着正文核查吗？出现形容词判据 = 重写该条；words 带是否与相邻章
     按 `novel_craft.md#反公式化与拟人化` 的方差条错开；人物卡上的承诺（称谓/记号/知识边界）是否已回写进
     "线动作"栏——没写的承诺=不存在。
- 输出合同：beats 文件含合法 front-matter 六键（`novel_craft.md#front-matter 键`）+ 任务书五节齐全。
- 退回边：主控自写 beats（含细纲与任务书）若不过自交检 → 重写。
- 自交检通过标准（同时满足，缺一即回退）：①「验收」每条都能对着正文给出"动词+可指认名词"判据，
  出现形容词判据 = 未过；② words 带与相邻章区间下限错开 ≥600 字；③ 人物卡上的承诺（称谓/记号/
  知识边界）已回写进"线动作"栏；④ front-matter 六键齐全且与上一章的 form/旋钮不整组重复。
  其中机械部分由 check 报数（`acceptance_empty_criterion` / `words_band_crowded` /
  `style_notes_copy` / `line_action_orphan` / `line_action_missing`），主控看数裁决，不必自己记着查。

## 任务书合同

beats 文件尾部的固定五节 + front-matter，pack 的 P0 整块投递给子代理：

```
---
chapter: ch_007
vol: vol_01
form: 双线剪辑            # 章型（novel_craft.md#反公式化与拟人化 章型库）
pov: 林逐夜·贴身第三人称    # 本章视角
words: 2200-4500          # 目标带，仅参照（反均匀见 craft）
style_notes: 短句急雨 | 章首中间开始 | 章尾弱收   # 三旋钮
---
## 目标        # 本章必须达成什么，可核查条目（推进了什么、兑现了什么线）；
               # 目标带上沿 >2000 字时按场分条：`S1 入册 | 字数建议（非强制）| 立规矩与禁手`
## 必须保留     # 事实不变量（起草与审校都不得违反），如：主角至章末仍不知 B 的身份
## 本章禁忌     # 本书 style_guards 相关条目 + 主控针对本章追加的特定禁忌
## 验收        # 主控写给审校的逐条判据：不超过 6 条，每条可在正文中核查，禁形容词
```

「限制与上章相同」是自检义务：连续两章的禁忌/验收/风格旋钮逐字相同 = Stage 1 未完成。

## Stage 2 起草（spawn drafter，一次性）

- 输入合同（主控组装派发包）：任务书全文 + pack P0/P1（P2 索引由 drafter 按需）+
  `agents/skills/drafter/SKILL.md` 路径 + 输出路径。宿主负责 spawn/隔离/回收。
- 动作：起草独立成稿写 `raw/ch_XXX_vN.md`（N=现有最大版本+1，永不覆盖旧版——审计留痕）。
  任务书「目标」带 >2000 字时按场分块写作、合成单文件 raw（防单次输出截断；合稿=删场名，
  每场收束动作直接接上场开手，接缝不许留"话说两头"式过渡套话）。
- 输出合同：raw 存在且无「缺语境」标记。子代理不可反问；真写不动 → 在 raw 头部写一行
  `缺语境：<缺什么>` 即交付，主控按退回边处理。
- 退回边：缺语境标记 → 先补 pack/beats 再重派（新 v，不改旧文件）。
- 主控中间验收（进 Stage 3 的闸门，主控亲跑）：`evidence file`（字数带、guard 命中）+
  对照任务书「目标/必须保留」逐条核 raw；过 → 派 guard，不过 → 按#拒收语义 处理。
  核查权全在主控——drafter 不自检、不跑 evidence，交付即退出。

## Stage 3 重铸精修（spawn guard，一次性）

审校只干一件事：把 raw 重铸&精修成定稿——表达层全权重写，事实层零权；质量标准见 `novel_craft.md#打磨与校对`。

- 输入合同：任务书 + raw 最新版 + pack P0。
- 动作：
  1. 重铸：按照商业网文标准来——AI 味少、丝滑连贯、读取起来爽。；句子/段落/节奏/对话切分/
     首尾全部可推翻；风格旋钮按 front-matter 执行；此外，AI高频词汇也需要重点检查。
  2. 情节纪律：场序、动机、事件因果不动，数字与专名不改值不改名；发现**确定的**情节级
     硬伤（越界知情/数字异值/改动事实）→ 停机报告不写 final（重铸破布是浪费）；
     越界知情判定：对照该 POV 当前已知清单，只有在他"尚未获得信息渠道"就说出/表现出来时才算；
     作者旁白单独向读者揭示 ≠ 角色越界（见 `novel_craft.md#知识是资产`）；
  3. 交付即退：不写注记、不跑 evidence（都是主控的工位）；回话带「重铸了什么/为什么」
     三到五行，供主控注记录用。
- 输出合同：`final/ch_XXX.md`（纯净正文，零工程注记）。仅此一件。
- 退回边：主控校对不过（guard 词命中未消/「必须保留」破/引入事实错）→ 重派 guard 重铸
  （final 覆盖重写，raw 才是审计线）；重派与拒收共用上限，见#拒收语义。

### 拒收语义

拒收判定权全在主控：Stage 2 中间验收判 raw 不可救，不派 guard。同章拒收 ≤2 次；第 3 次
主控亲自改写，或"升级问人"——即向用户/宿主报告本卡点并暂停该章流水线，等用户指令后再继续；
两者都由主控在同一章内处理，**禁止无界循环改稿**。它与`novel_workflow.md#模式与控制`中的
"暂停/继续"自然语言控制同义，主控不自行编造指令。

## Stage 4 同步封存（主控；轻输出，文书活）

- 输入合同：本章 beats/raw/final 齐 + guard 回话 + 主控对状态 diff 的整理。
- 动作：
  1. 校对与注记（主控亲笔，进提案前完成）：六项机械核对逐项过（错别字／标点配对／专名与
     entities 写法一致／数字与 ledger current 相符／「必须保留」在位／格式残留），
     evidence style/dup/file 按需自跑；注记正文写入 `log/review/ch_XXX.md`（init 已自动创建
     该目录），其中必须含 `## 验收` 节，逐条回答 beats 任务书「验收」并带证据；无注记会被
     sync 的 review_gate 拒绝。骨架可用 `python studio.py review new ch_XXX --write` 生成
     （验收条目自 beats 预填，引号配对/余额/专名表/必须保留清单等机器数据逐项就位，
     只填「结果」与证据）；
  2. `python studio.py proposal new ch_XXX` 打印骨架（schema/chapter/operation_id 已预填，
     不落盘；加 `--write` 可直接存 `state/inbox/ch_XXX.json`），按 `state/inbox/README.md`
     的样例纪律填实六区 → 存 `state/inbox/ch_XXX.json`
     （schema: `engine/schemas/proposal.schema.json`；operation_id = `<ch>.<作者>.<序号>`）。
     组装前跑 `python studio.py evidence candidates ch_XXX`：线名命中/金额串/新实体标记行/
     在场提及计数/状态摘要的机器对照——只出数，是否上账归主控；
  3. `python studio.py proposal check ch_XXX`（结构预检+三方事实对照，不落盘、不要求注记在场）
     → `python studio.py sync ch_XXX --dry-run` 预演（校验结构+列出合并计划）；
  4. 去 dry-run 正式 `sync`：审校合同闸门 → 引擎合并 → 体检 → 快照 `<ch>_done` 一气呵成
     （注记未答完验收会被闸门拒绝且不落半成品状态，改完注记重跑即可）；
  5. sync 失败 → 提案自动进 failed/：读报错改文件，再 sync（引擎自动捡回）。
     反复失败 = 事实冲突，回到"修正文还是修状态"二选一，**禁止编造提案迎合体检**。
- 输出合同：status 流水线行该章五格全绿。下一章从 Stage 1 开始。

## 文字级边界（主控对 final 的终检尺度）

- 允许直接改：错别字、标点配对、markdown 残留、占位符残留、工程标记泄漏进正文。
- 一律回 raw 重走 Stage 3：情节、事实、人物、关系、数字的任何改动；风格性重写。
- 速判口诀：**改动影响"读者能知道什么" → 内容级**。

## 卷末（最后一章 sync 之后）

- 主控三件套：`check` 收卷 → `export --txt --views`  。
- 卷文本有实质硬伤才动旧章：`snapshot rollback` 回退到该章前，重走 Stage 3（见#回退与恢复）。

## 模式与控制

- `project.json.mode = automatic`：主控循环 Stage 1–4 不停；唯二暂停点 = check 出现
  errors、同章拒收用尽（见#拒收语义）。`manual`：每 Stage 输出先回报，等"继续"。
- 自然语言控制（宿主转述用户指令，主控不猜）：暂停；继续；重写本章（回 Stage 2，v+1）；
  跳到 ch_N（仅限用户明说——状态机不阻止超前，但 status 流水线会标缺口；
  sync 前置闸门要求 final + 对应提案，错章/无定稿不封存，故不会产生半合并）； 
- 回退与恢复：`snapshot list` 选点 → `snapshot rollback <名>` 回滚 state（回滚前引擎自动
  留 pre_rollback_ 存档；`--clean-drafts` 清掉晚于该点的稿件）。final 正文不在快照内——归 git。
  回退已封存章 = 回滚后该章从 Stage 3 重走，禁止直接编辑已封存 final 再 sync。


## 宿主交接协议

流水线岗位 spawn 时主控传递恰好五样：岗位 SKILL.md 路径、任务书全文、pack（P0/P1）、
可写路径清单、退出码约定（0=交付；2=缺语境报告后停机）。多传一个字都算违反
"一次性、限制随任务书"的原则；隔离、回收、 由宿主实现，本仓库不定义机制。

宿主无 spawn 能力时的降级模式：主动向用户报告。