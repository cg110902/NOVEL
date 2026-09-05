# QA 问题清单 — Novel Studio 引擎 v3.1.0

**测试日期**：2026-09-05
**测试分支**：`arena/01a071d3-novel`（基线 commit `30bc23d`）
**测试方式**：开启调试模式（`NOVEL_STUDIO_DEBUG=1`）→ 新建书《沧澜拾灯》（仙侠）→ 完整跑通 ch_001–ch_003 全五阶段流水线（Stage 0 设定 → Stage 1 细纲 → Stage 2 起草 → Stage 3 精修 → Stage 4A/4B 双轨 → Stage 5 同步封存）→ 在副本"靶场"书上做故障注入。
**执行说明**：本环境无法真正派生 Subagent，5 个角色（Director / Drafter / Editor / Reader / Critic）由我一人分饰，严格按各 SKILL.md 的准读清单与准写路径执行。**为找 bug，我以 QA 身份读取了 `engine/*.py` 源码——这违反"引擎黑盒铁律"，属于本次任务的刻意越界，不是流水线行为。**

**结果统计**：
- 3 章全部 `sync` 成功，`check` 最终 `ok=True`、0 errors / 0 warnings / 0 infos，3 份快照归档。
- 故障注入 45 例：**闸门按预期拦截 41 例**，**4 例暴露真实缺陷**。
- 发现问题 **28 项**：P0 × 2、P1 × 5、P2 × 10、P3 × 11。

---

## P0 — 严重（数据完整性 / 安全边界）

### P0-1 跨章账本注入：任意章提案可改写其他章的账，且无任何告警

- **复现**：`ch_004.json` 提案里写 `ledger.transactions[0].chapter = "ch_001"`，`proposal check` 报 **0 errors**，`sync ch_004` **exit 0**，流水以 `chapter=ch_001, delta=+999` 落盘。
- **实测后果**：
  ```
  ch_001 lamp_ash   delta=  43  balance_after=  43
  ch_002 lamp_ash   delta= -43  balance_after=   0
  ch_003 lamp_debt  delta= -30  balance_after= 217
  ch_001 lamp_ash   delta= 999  balance_after= 999   ← 注入行，排在 ch_003 之后
  ```
  `ledger recompute` 按**列表顺序**（非章节顺序）重算，判定"✅ 账本自洽，无需修复"；`check` 返回 `ok=True, errors=0`。
- **根因**：`LedgerTransaction.chapter` 只有 `^ch_\d{3,}$` 格式校验；`state.py` 合并流水时不校验 `transaction.chapter == proposal.chapter`；`recompute` 不按 `chapter` 排序。
- **影响**：Reader 写错一个章号（极易发生），账本历史被静默改写，且**没有任何一道闸门能发现**——因为"自洽"的定义本身就是列表顺序。
- **建议**：① `validate_proposal` 增加 `ledger.transactions[*].chapter` 必须等于 `proposal.chapter`（跨章修正走 `timeline.events.replace` 那类显式修订通道）；② `recompute` 与 `balance_after` 一律按 `chapter` 号排序后重算；③ `check` 增加"流水章节单调性"档。

### P0-2 `pack --open` 一条命令绕过整个"铁血文件权限网关"

- **复现**（`pack` 是 Drafter 技能卡里**唯一被授权**的命令）：
  ```
  studio.py pack --open state/current.json    → exit 0，输出六表之一的全文
  studio.py pack --open state/lines.json      → 全部伏笔/秘密/误会台账
  studio.py pack --open log/critic/ch_001.md  → Drafter 明令"严禁越级参考"的催更便签
  studio.py pack --open bible/project_bible.md / characters/*.md / manuscript/vol_01/final/ch_001.md
  ```
- **根因**：`engine/pack.py:651 open_file()` 只调 `common.safe_child_path` 防越出工作区根，**无按角色的白名单**；`cli.py:209` 的 `--open` 帮助文本自己写着"取工作区内**任一**文件原文"。
- **影响**：AGENTS.md 第四节把准读/禁读称为"铁血网关""绝对禁止"，但机械层面为零防护。Drafter 可读 `state/*`、Critic 可读 `beats/*`、Reader 可读 `raw/*`——五张禁读清单全部形同虚设。
- **建议**：`--open` 增加子代理角色参数（或按 `pack ch_XXX` 上下文推导），对 `state/`、`log/critic/`、`bible/`、`characters/`、非本章 `raw|final` 直接拒读；或至少在文档里把"铁血网关"改口径为"提示级约定"，避免给出虚假的安全感。

---

## P1 — 高（信号质量：会主动误导主控决策）

### P1-1 `power_level_shift` 每章必报假警（⭐ 最高可见度）

- `checks.py:416`：`if cur_p.get("power_level"): add("info","power_level_shift", f"⭐【境界变动】主角境界更新为「{...}」")` —— **不与存量值比对**。
- **实测**：ch_001 / ch_002 / ch_003 三章的 `power_level` 全是同一串"半盏外灯（未入灯徒）"，`⭐【境界变动】` 连报三次。
- Reader 技能卡明确要求"无变动则维持原样"，于是**照章办事的 Reader 必然每章触发一次最高级别提示**，真突破时反而没人信。
- **建议**：先取 `state.current.power_level` 比对，相同则不报；变化时才报，并附旧值 → 新值。

### P1-2 `_amount_scan` 的 `values` 被截断成"最小的 8 个"，最大金额永不参与对照

- `evidence.py:334`：`"values": sorted({v for v,_ in recs})[:8]`。
- **实测**（ch_003，直接调用函数）：正文含 1/11/12/13/24/30/43/120/**217**/**247**/**300**，返回 `values=[1,11,12,13,24,30,43,120]` —— **217（当前灯债）、247（原灯债）、300（赎金）三个全书最关键的数字被丢弃**。
- **连带**：`checks.py:250 amount_unmatched` 和 `:255 amount_by_quote` 都基于这份被截断的 `values`；金额大于第 8 小的流水会被误判"未被机械扫描命中"。`count: 18` 却只展示 8 个，**无截断标记**。
- **建议**：改为"最小的 4 个 + 最大的 4 个"或全量输出并加 `truncated: true`；至少让 `tx_vals` 的比对绕过截断。

### P1-3 `pov` 把"同章出现过的所有事件"当成该角色"应知"，包含他不在场的私密场景

- **实测** `pov 裴九` 的 `knows.lived_events` 含：
  > ch_002 —「陆沉舟把空灯扣在灶台瓦罐下，试出灯不灭、无声、微温且铜皮刮不出印，门外巡夜脚步停在巷口石碑处」

  这是**陆沉舟独自在家深夜**的场景，裴九不在场。同一份输出里 `on_stage_now: false`。
- **根因**：`pov` 的模型是"该角色登场章节的编年史 = 他应知信息（公开/亲历）"，粒度是**章**而不是**场景**。
- **影响**：`pov` 是 SKILL 里"对手戏必跑"的知情差取证工具，它主动把私密事件标成"他知道"，正好诱导起草员写出吃书对白——与它的设计目的相反。
- **建议**：`lived_events` 至少要区分"本章在场段落"与"本章全量事件"；或在字段名与 note 里把"应知"降级为"同章发生（不保证亲历）"。

### P1-4 一份游离的未来章 beats 会劫持 `cockpit` 指针，且与 `status` 结论矛盾

- **复现**：手滑 `beats new ch_7 --write`（`ch_7` 被静默归一为 `ch_007`），生成了 ch_007 的 beats。此后：
  - `cockpit --json` → `target_chapter = ch_007`，`next_action.command = "python studio.py pack ch_007 --full"`
  - `status` → "👉 下一章 ch_005"
- **影响**：Director 技能卡写的是"主控**严禁猜测工序**，直接执行 `next_action.command`"。照做就会跳过 ch_005、ch_006。两个官方入口对"现在该写哪章"给出不同答案。
- **建议**：`cockpit` 的 `target_chapter` 与 `status` 统一到同一函数（last_final + 1）；游离 beats 只应产生一条 `stray_beats` 告警，不应改变工序指针。

### P1-5 `ask <角色>` 召回缺口：查主角查不到主角自己的核心目标线

- **实测** `ask 陆沉舟` 召回 `GUN-001, GUN-004, MIS-001, KNO-001`，**漏掉 GUN-003「娘的半缕残魂」**——即主角的全书驱动力（赎金三百盏、尚差二百四十七盏）。
- **根因**：线匹配是对 `name/plan/secret/parties/content/note` 做**字面子串**匹配；GUN-003 的 name 与 plan 里都没出现"陆沉舟"三个字。
- **影响**：SKILL 的取证纪律是"凡要落笔一个旧数字且它不在眼前 → 必须先 `ask` 再写"。主控写"赎娘还差多少盏"时按规程查 `ask 陆沉舟`，得到的是**不含这个数字**的结果，于是极可能凭印象编一个数。
- **建议**：线匹配增加"实体 → 关联线"的反向索引（holder / parties / plan 中出现的实体名 / 该线动作发生章的在场名单）；`text_hits` 也应放宽每章 1 条的上限（实测 ch_001 提及 18 次只回 1 句）。

---

## P2 — 中（可用性、假阳性与自伤）

| # | 问题 | 证据 |
|---|---|---|
| P2-1 | **细纲前向引用未 plant 的线 ID 必报 `line_action_orphan`**，而唯一豁免语法（写 `plant GUN-XXX`）在此语境下等于撒谎；"本章不涉及某条线"没有合法写法 | ch_001 写 `MIS-001：本章不 plant` 报警；改成不带 ID 的中文描述才消警。ch_002 同样 |
| P2-2 | **beats「一致性速查」名册过滤掉 `target_ch == "longline"` 的线**（`chapter_flow.py:297` 只收 `isinstance(t,int) and t<=n+3`）→ 全书最重要道具的规范名不出现在名册里 | ch_002 名册只有 陆沉舟 + 裴九（来自卷纲点名），**没有「无主空灯」**；不跑 `pack` 的 Drafter（AGENTS 准读清单允许只读 beats+上章 final）会拿不到道具规范名 |
| P2-3 | **`evidence names` 与 `config suggest` 噪声阈值互不相交，报警无处方可采纳** | names 报 `东西(12) 回湾(4) 周叔(4) 盏灯(5) 那串(3)`；suggest 给 `沉舟说(16) 沉舟把(9) 拾灯人(8) 油纸包(6)`——**零重叠**。真正可执行的"周叔 = 老周头别名"两边都不给 |
| P2-4 | **`mention_not_present` 对任何中途退场的角色每章必报** | ch_002 报裴九（提及 15 次）、ch_003 报沈砚秋（提及 9 次）。`present_characters` 的定义是"章末在场"，二者语义天然不等价 |
| P2-5 | **引擎自带模板触发引擎自己的闸门** | `templates/beats.md:73` `- **核心看点**：<!-- ...读者... -->`；因行首是 `-` 而非 `<`，`acceptance_empty_criterion` 的注释跳过逻辑失效 → 每份未改写的脚手架 beats 必报（实测 ch_004、ch_007） |
| P2-6 | **`state_watch` 单字词在中文里几乎必然误报**，而 `config guide` 的示例与默认引导仍诱导填单字 | 实测 `injury:["断"]` 命中"断了的线头"；`["血"]` 命中"咳血" |
| P2-7 | **`quote_balance` 对 ASCII 引号全盲**（`evidence.py:466` 只数 `「」“”『』`） | 三章定稿共用 96 个 ASCII `"`，`quote_balance` 全 0；无任何闸门提示中文正文应使用全角引号，也未检测 ASCII 引号是否配对 |
| P2-8 | **`amount_unmatched` 不区分"债务总额/他人数字/修辞"与"本章流水"** | ch_003 把 `十一盏`（差额）、`一盏`（老周头差数）、`二十四盏`（瘸子刘）一并报"未对应本章任何流水" |
| P2-9 | **`words_band_crowded` 要求相邻章 words 下限差为 0 或 ≥400** | 2200 → 2400 这种正常微调被判"微调幅度过小"；实际逼主控要么完全不动、要么大幅跳档 |
| P2-10 | **`evidence prev` 的 `must_keep` 残留 markdown 记号并混入标题行** | 实测输出含 `核心看点**：...`、`验收要点**：`（`evidence.py:481` 只 `lstrip("-*· ")`，不清 `**`） |

---

## P3 — 低（文档缺口与契约细节）

| # | 问题 | 证据 |
|---|---|---|
| P3-1 | **资源池（`ledger.pools`）在全部 AI 向文档里只有一行示例**：AGENTS.md / 5 张 SKILL / templates / inbox README 均无"可通过提案新建池""`initial` 必填""`current` 禁止声明""Stage 0 应声明本书资源池"的说明；且 Stage 0 **没有任何 CLI 通道**声明池（`config guide` 不含池键，`state set` 禁登新事实） | 全库 grep `pools` 在 AI 向文档中 0 命中，`standard_currency` 仅出现 1 次（reader SKILL 示例）。本书的"灯烬/灯债"池是我读源码后才敢试出来的 |
| P3-2 | **`timeline.clocks` 字段契约完全未文档化**（正确为 `name/target_ch/urgency/desc/status`，**无 `id`**） | 按常识写 `id` + `deadline_ch` → `含未知字段: id` / `含未知字段: deadline_ch` / `target_ch 必须为 ≥1 的正整数` |
| P3-3 | **同一个 `ch_7` 在两个入口严格度相反**：CLI 静默归一为 `ch_007`（`beats new ch_7` 真的建出了 ch_007 文件），而提案 `target_ch` 明确拒收 `ch_7` | 实测 `beats new ch_7 --write` exit 0；`target_ch:"ch_7"` REJECT |
| P3-4 | **多书歧义时退出码不一致，违反自述契约**：`status` 返回 **0**，`check`/`cockpit`/`sync` 返回 **1** | 实测；README 声明 `1=阻断 / 2=用法错`。按退出码判读的 Agent 会把 `status` 的"什么都没做"当成功 |
| P3-5 | `config set words_target '[2000]'`（形状非法）返回 **1** 而非 **2** | 实测；同类"用法错误"其余均返 2 |
| P3-6 | `cross_facts.lines_ops_in_proposal` 字段名暗示"全部线操作"，实际**按设计排除 `plant`** | `checks.py:723` `... g.get("action","plant") != "plant"`；ch_001 有 4 条线操作，该字段为空 |
| P3-7 | 迁移后 `state/state_schema.json` 丢失 `created_at` 键 | 迁移前 `{created_at, version}` → 迁移后 `{from_version, migrated_at, version}` |
| P3-8 | `cockpit` 的 `dramatic_irony` 输出空尾巴"知情边界："（`cockpit.py:242` 用 `k.get("note","保密中")`，对空串失效；`state.py` 落盘时写的是 `"note": ""`），而 beats 里同一信息用 `or "保密中"`（`chapter_flow.py:332`）显示正常 | 两处默认值写法不一致，同一数据两种呈现 |
| P3-9 | **无任何闸门检测中文稿件里的拉丁残留** | 我在 beats 正文留了 `说这小子比他想的是 harder 谈`，`check` / `evidence residue` 全程无反应（residue 只数 `{{slot:` 与 `candidate_`） |
| P3-10 | `candidate_new_entity` 信噪比接近 0 | ch_002：8 条全噪声（沉舟说/油纸包/沉舟把/笞二十/灯债加半/债加半成/半个饼/那十个）；ch_003：11 条全噪声。虽标注"实验性候选，误报勿理"，但每章十几条纯噪声会稀释真正的告警 |
| P3-11 | **`check` 自称"算术体检"，实际零覆盖跨文档数字闭合** | 我在 ch_003 写出"四十三盏入账，抵本金三十盏，剩下十三盏抵利，债从二百四十七变成**二百三十四**"（正确应为二百一十七），beats 验收要点里也是 234，`check` 全程 `ok=True`。46 个错误码里没有任何 amount/arith 类码 |

---

## 附：实测确认**工作正常**的闸门（不必改）

| 闸门 | 验证结果 |
|---|---|
| `unfilled_slot` / `candidate_leak` | 往 final 塞 `{{slot:...}}` 与 `candidate_*` → 各 1 error，`ok=False` |
| `final_drift` | 封存后改 final → warning，附封存/当前双哈希 |
| `beats_fm_extra_keys` | front-matter 加自定义键 → **error**，列出全部合法键 |
| `beats_form_repeat_without_reason` | 连章同 form 且无 `form_reason` → **error** |
| `style_notes_copy` / `words_band_crowded` / `form_share_over_limit` | 全部按预期触发 |
| `word_band_breach` | 1627 字（< 2000×0.85）→ warning，Editor 返工后消警 |
| `line_action_orphan` 的 `plant XXX` 豁免 | 按文档写法确实豁免 |
| 提案 schema 闸门 | `description`（应为 `summary`）、`type:"character"`、未知字段 `power_level`、未知顶层键、schema 版本错、chapter 无补零 —— 全部 REJECT |
| 线索契约 | GUN plant 缺 `target_ch`、`target_ch:"21"`、`target_ch:"ch_7"`、KNO 缺 `secret`、KNO 用 `remind`、MIS 缺 `parties`、MIS `parties` 写成数组、MIS 用 `remind` —— 全部 REJECT；`"第29章"` 与四位数 ID ACCEPT |
| 幂等 | 同 op 同内容 → `duplicates=1, applied=0, exit 0`；同 op 异内容 → `operation_id 已用于不同内容，拒绝复用`，归档 `failed/` |
| 未登记实体闸门 | `present_characters` 含未注册名 REJECT；`holder` 指向未注册实体 REJECT（实测「官秤」的 holder「灯司」被拦） |
| 引文柔性接地 | 逐字命中报 `exact hit`，我故意多加一个"他"字的报 `fuzzy hit (score=93.3 ≥ 85)`；缺引文只报 `quote_missing` warn，不阻断 |
| 路径穿越 | `--open ../../etc/passwd`、`/etc/passwd`、`evidence file ../../../engine/state.py` 全部 `❌ 路径越界`，exit 1 |
| 迁移器 | 伪造 `version:1` → 自动先快照（`pre_migration_v1`）、迁移、写 `migrations.log`、`version` 回到 2 |
| 快照 | `create` / `list` / `rollback --clean-drafts` 正常，回滚前自动备份 `pre_rollback_*`，清理的稿件进 `workspace/.trash/` |
| Stage 5 输入合同 | 缺 final / 缺 proposal / 缺 beats / 缺 raw 四种情况**逐一被拦**，错误文案与 hint 准确 |
| `ledger.pools` 新建池 | 支持（`initial` 生效、`current` 声明被拒），`lamp_ash`/`lamp_debt` 余额由流水重算正确 |
| `mention_not_present` / `beats_overlap` / `aftermath_opening_miss` / `critical_mutation` | 均真实命中了本次写作中的实际问题（裴九早退、梗概照抄细纲、ch_003 开篇未承接余震、周氏 deceased） |

---

## 附：本次写作流程本身暴露的工艺问题（非引擎 bug）

1. **Editor 环节系统性欠字**：三章初稿（raw，含章题的 CJK 数）为 1700 / 1816 / 1389，**首轮精修后**定稿为 1627 / 1670 / 1333，**三章全部触发 `word_band_breach`**（下限 2000×0.85=1700），逐一返工扩写后才达到 2032 / 2181 / 2157。Editor 技能卡的"大刀阔斧删冗余"与"2000~3000 字"两条指令方向相反，且没有"删完要回补"的动作约束。建议在 Editor 卡里把字数下限写成硬合同并前置到剪枝推演蓝图。
2. **beats `words` 自报带无强制力**：`check` 只按 `project.json.words_target` 判定，细纲自报的 `2200-2800` 从不与定稿实际字数比对——主控可以随便报。
3. **`beats_overlap` 高频触发**：三章 `sync` 的 verify_battery 累计报 **8 次**"疑似照抄任务书"（ch_001 × 1、ch_002 × 1、ch_003 × 6），命中 `synopsis.text` / `lines.plan` / `lines.content` / `lines.truth` / `timeline.events`。闸门是对的，但 Reader 卡里没有"提案文字必须以 final 原句为源、不得复用细纲措辞"的明确禁令，建议补一条。
4. **`state_watch` 词表默认引导危险**：`config guide` 的形状示例 `{"power_level": ["突破","晋升"]}` 是双字词，但没警告不要用单字；我填 `["断"]`/`["血"]` 后每章误报。

---

## 建议修复优先级

1. **立刻**：P0-1（账本跨章注入 + recompute 排序）、P0-2（`--open` 权限）
2. **本迭代**：P1-1（假警）、P1-2（金额截断）、P1-3（pov 知情差）、P1-4（工序指针分裂）、P1-5（ask 召回）
3. **顺手**：P2-5（模板自伤）、P2-2（longline 名册）、P2-3（阈值对齐）、P3-1/P3-2（文档缺口，成本最低收益最直接）

**复现材料**：调试模式全部 stderr trace 与各命令输出保存在 `/home/user/nsqa/logs/`；被污染的靶场书副本在 `/home/user/nsqa/QA靶场_污染样本/`（含注入后的 ledger.json 原样）。正式书《沧澜拾灯》三章定稿 + 六表 + 3 份快照位于 `workspace/沧澜拾灯/`（`workspace/` 已被 `.gitignore` 排除）。
