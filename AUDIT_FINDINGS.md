# Novel Studio 审计发现清单（2026-09-02）

> 审计方式：主审逐行精读引擎源码与全部文档/schema；子代理 A 沙箱动态测试（~130 项）、B 文档↔引擎契约审计、C 工作区数据完整性审计（含确定性重放）。所有关键发现均经二次验证，原始目录零改动。
> 状态标记：`[ ]` 待修复 / `[x]` 已修复（2026-09-02 修复波次）/ `[~]` 载体已就绪、随 ch_003 sync 终结。每项附位置与修改思路。

---

## P0 — 数据销毁风险

### [x] P0-1 `init --force` 可 rmtree 任意绝对路径目录
- **位置**：`engine/cli.py:73-87`（`_init_workspace` 对绝对路径原样放行，无 workspace 归属校验）、`engine/cli.py:128-131`（`shutil.rmtree(book)`）
- **影响**：对任意含 `project.json` 的目录执行 `init --force -w <绝对路径>`，目录内容全部静默删除、无备份无确认（沙箱已实测）。且 workspace 外的书对 `list_books` 不可见，成为"隐形书"。
- **修改思路**：在 `cmd_init` 处理 `--force`（以及 `--clean`）前校验 `book.resolve().is_relative_to(common.workspace_root())`，不在 workspace 下即拒绝并返回 rc=2；提示语说明"整本重开仅支持 workspace 内的书"。

---

## P1 — 功能错误 / 契约失真

### [x] P1-1 beats 模板小节标题与引擎解析正则不匹配（线动作检查全线失效，真实数据已坐实）
- **位置**：`templates/beats.md:31` 与真实 beats 均为 `## 伏笔与线索动作（对齐 state/lines.json）`；引擎正则 `^##\s*(?:.*线动作|伏笔与线动作)`（`engine/checks.py:373`、`engine/cli.py:645`）不匹配（"线索动作"无连续子串"线动作"）。实测两章 beats 的线动作节提取 0 行。
- **影响**：`line_action_orphan` 永久失效；到 ch_003（KNO-001/MIS-001 到期）`line_action_missing` 必误报；`proposal auto` 的 lines 提取恒为空。
- **修改思路**：推荐改引擎侧正则为 `r"^##\s*.*线(索)?动作"`（checks.py 与 cli.py 两处同步）——向后兼容已写好的 beats；同时把 templates/README.md 第 26 行的节名清单核对一遍。

### [x] P1-2 `-w` 写在嵌套子命令之前被静默丢弃
- **位置**：`engine/cli.py:1113-1129 / 1143-1161 / 1165-1172`——`snapshot list|create|rollback`、`proposal new|auto|check`、`review new` 的子解析器重复定义 `-w/--workspace/--json`，argparse 子解析用全新 namespace 解析后回拷默认值 `None`，覆盖外层已解析值。
- **影响**：`review -w X new ch_001`、`proposal -w X check ch_001`、`snapshot -w X list` 全部报"未找到书工作区"（X 明确存在），无任何提示；多书场景为功能性错误。
- **修改思路**：给子解析器上重复定义的 `-w/--json` 加 `default=argparse.SUPPRESS`（未提供时不写入 namespace，父级值得以保留；后置写法仍正常）。注意不能简单删除子级定义——`snapshot list -w X` 的后置写法依赖子级存在。

### [x] P1-3 `proposal auto <ch> --write` 无条件覆盖在途提案
- **位置**：`engine/cli.py:769-772`（写盘前无存在性检查）；对照 `proposal new`（cli.py:800-802）与 `review new --write`（cli.py:898-901）均有拒绝覆盖保护。
- **影响**：沙箱实测手工提案被自动草案直接顶掉，手工内容丢失。
- **修改思路**：`--write` 分支写盘前检查 `(inbox / f"{ch}.json").exists()` 或 `failed/` 存在同名，存在则拒绝 rc=1 并提示；如需强覆盖提供显式 `--force` 选项。

### [x] P1-4 校对注记（review_gate）宣称"拦截/拒封存"，实际纯软提示
- **位置**：`engine/checks.py:65-81`（docstring 与消息写"无注记→拦（Stage 5 封存前提）/拒封存"）、`engine/cli.py:482-488`（仅 `print("ℹ️ 提示")`，不影响退出码；注记不存在时 gate 整个跳过）、`engine/README.md:12`（"sync 前置 review_gate"）。
- **影响**：文档让主控相信 sync 会被验收注记卡住，实际跳过注记可无阻封存；整套 review 机制在 AGENTS.md / novel_workflow.md / templates 中零记载。
- **修改思路**（二选一）：A. 真拦截——cmd_sync 无条件调用 review_gate，gate 非空（含"注记不存在"）时 return 1；B. 确认为可选软提示——修改 checks.py docstring 与消息文案（去掉"拦/拒封存"）、engine/README 表述，并在 novel_workflow.md#Stage 5 补记该可选机制。结合 AGENTS.md "极速直通"的现行设计，建议 B。

### [~] P1-5（数据）`current.power_level` 与 ch_002 定稿正文矛盾
- **位置**：`workspace/.../state/current.json.power_level`="凡人（未引气入体…）" vs `final/ch_002.md`"引气入体，涤荡凡尘"、洗髓伐毛；`timeline.json` 亦记引气入体。`abilities` 也未收录《青云养气残篇》。
- **影响**：current 是下一章 pack 的 P0 回温上下文，ch_003 按此起草会直接吃书。
- **修改思路**：主控裁定口径（如"凡人·已借古玉灵气洗髓伐毛，未正式入炼气"），在 ch_003 提案的 current 区刷新 power_level/abilities（走正常提案管道留审计痕迹）。

---

## P2 — 引擎健壮性

### [ ] P2-1 损坏状态文件 → status / evidence / proposal check 裸 traceback
- **位置**：`engine/cli.py:171,189`（`_book_brief` 读 project.json / `.applied_operations.json` 无容错）、`cli.py:342-401`（cmd_evidence 无 try）、`cli.py:568`→`checks.py:155-165`（proposal_cross_facts）；`main()`（cli.py:1179-1187）只捕 KeyboardInterrupt。`common.load_json(default=)` 的 default 只覆盖 FileNotFoundError（common.py:201-211），调用方普遍误读。
- **影响**：任一 JSON 损坏（手改出错、磁盘故障）后，总览与诊断命令全部崩溃，用户失去"看现场"能力。
- **修改思路**：双层修复——(a) `main()` 增加统一兜底 `except (ValueError, TimeoutError) as exc: print(f"❌ {exc}"); return 1`，一处改动消除全部裸 traceback；(b) 精修体验：`_book_brief` 对 marker/project.json 损坏降级为提示行（"登记簿损坏，请回滚快照"）；`proposal check` 把 cross_facts 读取失败放进 `cross_facts.error` 字段。同时修 `common.load_json` docstring 明确 default 语义。

### [ ] P2-2 收件箱里无关章节的坏提案阻断目标章 sync
- **位置**：`engine/state.py:927-937`——`apply_inbox` 先 `load_json` 再按 `expect_chapter` 过滤，解析失败即 `break`。
- **影响**：`sync ch_002` 时 inbox 中损坏的 `ch_001.json` 会让目标章本次不合并且无"请重跑"提示（沙箱实测）。
- **修改思路**：expect_chapter 模式下，解析失败且文件名章号 ≠ 目标章（`common.chapter_number_from_name(pf.name)`）的提案，只警告+归档 failed/ 并 `continue`，不 `break`；目标章自身解析失败才中断。

### [ ] P2-3 杂散大章号使 status 输出爆炸并误报"最新定稿"
- **位置**：`engine/cli.py:190-202`（`horizon = max(...)` 全展开 `range(1, horizon+1)`）。
- **影响**：`final/ch_9999.md` → 输出 10009 行流水、耗时 1s+、"最新 ch_9999"误报；ch_999999 约百万行。
- **修改思路**：对 horizon 设上限（如 `min(horizon, latest + 30)`），或对流水行按"连续无活动区间"折叠显示（如 `ch_005…ch_9998 · `一行）。

### [ ] P2-4 并发锁超时 → 裸 TimeoutError traceback（先卡 30 秒）
- **位置**：`engine/common.py:244-245`、`engine/state.py:919`。
- **影响**：另一进程 sync 中时，用户等 30s 后看到 traceback（沙箱实测）。
- **修改思路**：cmd_sync（或 main() 统一兜底，见 P2-1a）捕 TimeoutError，输出"另一进程正在同步（锁 .state.lock 被占），请稍后重试" rc=1。

### [ ] P2-5 failed/ 重名归档 `.2.json` 后无法被自动捡回
- **位置**：`engine/state.py:889-903`（`_archive` 重名加 `.2/.3` 后缀）vs `state.py:917,920`（捡回只认精确名 `failed/{ch}.json`）。
- **影响**：提案第二次失败后，"就地修复重跑 sync 自动捡回"的承诺静默失效，提案滞留 failed/。
- **修改思路**：捡回逻辑改用 glob：`sorted(failed.glob(f"{expect_chapter}*.json"))`（排除 `NO_MERGE_SUFFIXES` 与 `.2.json` 以外的噪音），存在多份时全部捡回或取最新；dry-run 分支同步修改。

### [ ] P2-6 review_gate 与 review_skeleton 取的 beats 版本不一致
- **位置**：`engine/checks.py:72-76`（gate 用 `beats[0]`＝最低版本）vs `checks.py:116`、`cli.py:624`、`pack.py:33`（均用 `[-1]`＝最高版本）。
- **影响**：一章多版本 beats 时验收条目数对不上，产生假"验收 N 未被回答"。
- **修改思路**：review_gate 统一改用 `beats[-1]`（与全库"版本号最大者"口径一致）。

### [ ] P2-7 pack 超预算硬裁循环对 >25 条 file_index 无效
- **位置**：`engine/pack.py:322`（`render_layer` 只渲染 `file_index[:25]`）vs `pack.py:267-277`（裁剪从列表尾部 pop）。
- **影响**：实测 len>25 时前 N 次 pop 对渲染与预算零影响；预算仍超时静默放行，`trimmed_file_index` 计数误导。
- **修改思路**：裁剪前先 `fi = fi[:25]` 对齐渲染口径，再逐条 pop；循环结束若仍超预算，在 budget_report 增加 `"hard_cap_breached": true` 字段如实上报（P0/P1 不裁是设计，但必须显性化）。

---

## P2 — 小说工作区数据（需主控在 ch_003 提案中裁定修正）

### [~] P2-8 Stage 0 预置数据绕过提案管道，无审计痕迹
- **位置**：`state/entities.json` 中 7 个基础实体（顾长青/赵掌柜/铁蛋/凡人百世书/清泉镇/黑虎帮/青云宗）无对应提案与 marker 记录，且缺 `card` 键（与引擎合并产物形态不一致）；`current.json` 的 5 个字段（abilities/assets/injury/key_relationships/power_level）也无提案来源。重放实验证明裸 init 态 + ch_001 提案会被引擎整体拒绝。
- **影响**：违反"提案=唯一写入口"；状态无法从 init 完整再生，快照 1 之前不可回溯。
- **修改思路**：短期——ch_003 提案"重申式 upsert"这 7 个实体（带 `card:""` 对齐形态）并刷新 current 5 字段，补齐审计痕迹；中期——novel_workflow.md#Stage 0 增补规范"init 后的预置状态必须随 ch_001 提案登记"，或给 init 增加 `--seed <json>` 选项由引擎以提案管道写入。

### [~] P2-9 二十两赠银未入账
- **位置**：`final/ch_002.md`（赵掌柜塞"二十两碎银子"）vs `state/ledger.json.transactions=[]`、`current.assets` 仍"铜钱四十二文、半袋干粮"。
- **修改思路**：ch_003 提案 ledger 补一笔流水（type=income 或 manual）；同时在 Stage 0 约定主通货池（unit=枚）与故事货币（两/文）的折算口径。

### [~] P2-10 timeline 事件照抄任务书，与定稿/实体台账两两矛盾
- **位置**：`state/timeline.json` ch_002 首条"将紫纹岩参**交给**赵掌柜"（抄自 beats）vs 定稿赵掌柜"没有去碰"、`entities.json` 岩参 holder=顾长青。
- **修改思路**：注意引擎缺口——`_merge_timeline` 对 events 只支持追加去重，**无修订通道**。两个选项：(a) 引擎增强：events 支持按 (time,event) 键的 update 动作；(b) 短期以"后续正文明确岩参归属"消解矛盾，并在 ch_003 beats 明确该事实。同时向 Reader 强调"以 final 为源、不照抄 beats"（craft_reader 已写，执行走样，可在 reader SKILL 中加自检步骤）。

### [~] P2-11 章题三方不一致
- **位置**：ch_001 定稿无标题行、synopsis 题≠ch_002 定稿题（`第2章 夜半杀机，连环设伏`）。
- **修改思路**：ch_001 final 手工补标题行（稿件层可手工）；synopsis.title 的修订通道同受引擎限制（`_merge_synopsis` 只写当前章）——短期在 ch_003 起确保 Reader 用定稿题；中期提案 synopsis 区支持指定章修订。

### [~] P2-12 灵根口径全书漂移（五行/四系/下品伪灵根）
- **位置**：`final/ch_001.md`"五行杂灵根" vs ch_002+main_plot+current"四系杂灵根" vs `bible/project_bible.md`"下品伪灵根"。
- **修改思路**：主控裁定唯一口径（建议"四系杂灵根"，三方已一致）→ 写入 bible 偏离清单；ch_001 正文是否回改由主控权衡（已封存章节），ch_003 起统一。

---

## P2 — 文档 ↔ 引擎契约

### [x] P2-13 templates/README.md 实例化表述失实
- **位置**：`templates/README.md:3,9-16` vs `engine/cli.py:43-48` TEMPLATE_MAP（仅 4 份）。
- **修改思路**：表格增加"实例化方式"列（init 自动 / 手工复制）；修正 `character_card.md` 落点为 `characters/protagonist.md`；`volume_outline.md` 注明"开新卷手工复制，注意改标题里的 vol_01"；`reader_review.md` 注明"手工参考模板，落盘需转存为 .json"。

### [x] P2-14 "法定实体字段"清单漏 `card`
- **位置**：`.agents/rules/novel_workflow.md:33`、`.agents/skills/director/SKILL.md:18` vs `entities.schema.json`、`state.py:283,554`、`pack.py:186-193`。
- **修改思路**：两处清单补 `card`（语义：人物卡相对路径，`pack --full` 注入全文用）。

### [x] P2-15 novel_workflow.md#Stage 5 缺失"beats/raw/final 齐"输入合同
- **位置**：`novel_workflow.md:16,58-62` vs `engine/cli.py:453-479`（报错文案还引用该文档作出处）。
- **修改思路**：Stage 5 的 I/O 表输入列与操作指南补四项前置：`beats/ch_XXX.md`、`raw/ch_XXX_v1.md`、`final/ch_XXX.md`、`inbox/ch_XXX.json`；并补"故障恢复"小节（failed/ 捡回、`snapshot list/rollback` 全路径 `state/snapshots/`）。

### [x] P2-16 字数三口径矛盾 + 单位与引擎统计口径不符
- **位置**：`craft_editor.md:27`、`editor SKILL.md:39`（2400~3200**字符**）vs `templates/beats.md:7`、`craft_drafter.md:40`、`drafter SKILL.md:42`、`novel_workflow.md:13`（2400-3500**字**）vs 引擎 `common.cjk_count` 只数汉字不含标点（common.py:267-269）、`cli.py:149` 播种 [2400,3500]。
- **影响**：按"含标点字符数"交稿会被引擎系统性判低约 15%；当前书两章 4980/5050 已双双出带。
- **修改思路**：全书统一为"2400~3500 汉字（引擎 cjk 口径，不含标点）"；editor 两份文档的 3200 上限删除或注明为汉字数并与 project.words_target 的关系说明。

### [x] P2-17 "5 大事实"三种互不兼容的枚举
- **位置**：`AGENTS.md:15`、`novel_workflow.md:15` vs `.agents/rules/craft_reader.md:10-26`（最完整，含 ledger 与 clocks）。
- **修改思路**：以 craft_reader 五分法为准，同步改写 AGENTS.md 与 novel_workflow.md 的枚举，避免 Reader 系统性漏交 ledger 流水与危机时钟。

### [x] P2-18 beats front-matter 合法键（10 键）零文档，超键直接报错
- **位置**：`engine/checks.py:26-27` `_BEATS_FM_KEYS`（chapter/vol/form/pov/words/style_notes/form_reason/guard_extra/editor_extra/tension_curve）；超键报阻断级 `beats_fm_extra_keys`（checks.py:333-337）。
- **修改思路**：在 templates/beats.md 头部注释或 templates/README 增补合法键清单与用途（尤其 `guard_extra`＝章级禁忌词表、`words`＝本章自报字数带、`editor_extra`）；或在 `help` 中输出该契约。

---

## P3 — 低危 / 打磨（27 项）

| # | 问题 | 位置 | 修改思路 |
|---|---|---|---|
| [ ] P3-1 | operation_id schema 模式未锚定 + validator 用 re.search，含空格/中文的 op id 溜过 | `proposal.schema.json`、`validator.py:63` | schema 改 `^[A-Za-z0-9_.-]{1,128}$` |
| [ ] P3-2 | `register` 是未记载的 upsert 别名，报错文案只说 upsert/retire | `state.py:293-294` | 删除 register 或文档补记并改文案 |
| [ ] P3-3 | UTF-8 BOM 提案被拒（记事本常见） | `common.py:205` | 读取改 `encoding="utf-8-sig"`（写保持 utf-8） |
| [ ] P3-4 | GBK 输入：提案报原始解码错误无文件名；GBK 稿件被 errors="replace" 静默吞字无告警 | `common.py:205`、`cli.py:175`、`evidence.py:50` | load_json 捕 UnicodeDecodeError 转成"编码错误 {p.name}"；读取后统计 U+FFFD 占比超阈值在 check 报 warning |
| [ ] P3-5 | proposal auto 同分钟生成相同 operation_id | `cli.py:746-747,803-804` | 精度加秒 `%m%d_%H%M%S` 或缀 `uuid4().hex[:4]` |
| [ ] P3-6 | auto 的"📍 章末卡点"清理正则不识别 `**` 加粗，注释行混入自动梗概 | `cli.py:741` | 正则容忍 `**` 与前置 `-` |
| [ ] P3-7 | 槽位正则不一致：check 认得出 `{{ slot:x }}`、init 填不掉 | `cli.py:20` vs `checks.py:17` | 实例化正则加 `\s*`，两处统一 |
| [ ] P3-8 | `evidence prev` 输出"建议…"措辞，违反 evidence 自我声明的零裁决 | `evidence.py:422` | hook_diversity_notice 移到 status 提醒行或 checks warnings；evidence 只留 recent_hooks 数 |
| [ ] P3-9 | detect_chapter_hook 对末 3 段任意问号判"强钩"，过宽 | `evidence.py:428-440` | 收窄正则（如 `[？！]{2,}`、排除引号内、仅末段），或在使用处注明启发式 |
| [ ] P3-10 | dashboard HTML 不转义书名/实体名/summary | `dashboard.py:122,141-145,157-222` | `html.escape()` 包裹全部插值 |
| [ ] P3-11 | dashboard.py 用绝对导入，与全库相对导入不一致 | `dashboard.py:4` | 改 `from . import common, evidence, state` |
| [ ] P3-12 | export_views 表格遇 `|` 破版 | `pack.py:402-425` | 插值前 `\|` 转义 |
| [ ] P3-13 | 跨卷同章号生成重复 token `ch_001` | `evidence.py:31-52` | token 带 vol 前缀或输出加 vol 字段 |
| [ ] P3-14 | 快照路径文档缺 `state/` 前缀 | `novel_workflow.md:16` | 改 `state/snapshots/<ts>_ch_XXX_done` |
| [ ] P3-15 | `rollback --clean-drafts` 不清理后续章的校对注记与 inbox 提案 | `cli.py:952-967` | 可选增强：一并删 `log/review/ch_*.md`（>base）并提示 inbox 残留提案 |
| [ ] P3-16 | sync 内 create_snapshot 未包 try，竞态异常发生在状态已落盘后 | `cli.py:502` | 包 try：失败输出"状态已合并但快照失败" rc=1 |
| [ ] P3-17 | `_gather` 在 file_lock 之外执行（TOCTOU）；归档 rename 有存在性竞态 | `state.py:916,889-903` | gather 挪进锁内；`_archive` 的 rename 包 try 重试 |
| [ ] P3-18 | file_lock 陈锁抢占 stat→unlink 窗口竞态（低概率双持有） | `common.py:239-243` | unlink 失败重入循环（suppress 已保证不崩）；可加锁内容含 pid 校验 |
| [ ] P3-19 | craft_reader 示例占位 ID `GUN-XXX` 照抄必报错 | `craft_reader.md:73` | 改 `GUN-001` 并注明 plant 可省 id 由引擎自编号 |
| [ ] P3-20 | engine/README 模块职责表归属错（failed/ 归档与幂等登记簿在 state.py；`append` 动作不存在） | `engine/README.md:9-10` | 按实际归属改写 |
| [ ] P3-21 | INBOX_README "processed 永不删改"未注 `--force` 例外；op id 前缀建议 director 与 reader.* 实际用法不统一 | `state.py:102-104` | 补例外说明；口径统一为 `<ch>.<角色>.<序号>` |
| [ ] P3-22 | AGENTS.md "300~600 字简报"与"1~3 句梗概"不自洽 | `AGENTS.md:53` | 改为"以 Reader 提案 JSON 六区事实为准" |
| [ ] P3-23 | craft_drafter 第 5 节空节且引号方向反用 | `craft_drafter.md:33` | 补可执行要求（如"每章『极』≤3 次"，可用 style_guards 机械计数）并修标点 |
| [ ] P3-24 | 版本号 0.1.0 与 git "V2.0" 脱节 | `engine/__init__.py` | 升版本号并考虑让 `--version` 输出构建信息 |
| [ ] P3-25 | status 在 `-w` 指向不存在目录时误报"工作区还没有书" | `cli.py:229-249` | 区分"传入 -w 但不存在"输出明确错误 rc=1 |
| [ ] P3-26 | README 快速上手第 3 步 `pack ch_001` 在 Stage 1 完成前必失败 | `README.md` | 调整顺序或注明前置"需先完成 Stage 1 beats" |
| [ ] P3-27 | no-op 提案被归档 processed 且登记 marker，重试需新 op id（UX 陷阱） | `state.py:956-961`、`cli.py:494-498` | sync 输出中明确提示"提案已归档，如需重提请新 operation_id" |

---

## 验证通过、无需改动的部分

- 提案合并/校验矩阵（约 20 种非法输入逐条精确报错、整体拒绝、归档 failed/）
- 幂等体系（同 id 异内容拒绝、同内容跳过、重复归档不覆盖审计）
- 内存事务 + 字节级回滚；账本余额全量重算；实体闭合（present/holder/deceased）；空提案 no-op 识别
- 快照体系（SHA-256 manifest 防篡改、缺六表拒回滚、pre_rollback 自动备份、marker 随状态回滚）
- 路径越界防护（`--open`/`evidence file` 的 `..` 逃逸、快照名注入、safe_child_path）
- 工作区数据机器层：6 表+2 提案全过 schema、manifest/幂等哈希/账本/交叉引用/时序全绿；"快照1+ch_002 提案"确定性重放与当前 state 完全一致
- CLI 用法错处理、中文路径/全角冒号目录、UTF-8 输出

## 建议修复顺序

1. **立即（代码小改）**：P0-1 → P1-3 → P1-2 → P2-1(a)（main() 统一兜底）
2. **本周**：P1-1 → P2-5 → P2-2 → P2-4 → P2-6 → P2-7 → P1-4（选定 A/B 方案后改文档或代码）
3. **随 ch_003 创作**：P1-5、P2-8~12（全部并入 ch_003 提案 + bible 偏离清单）
4. **契约整改**：P2-13~18 + P3 文档项（建议把 beats 合法键、小节标题、action 词表、字数带收敛为单一契约源，文档引用而非复述）

=================================

好的。【小说工作区数据】问题是什么原因导致的？尤其是JSON数据和原文数据对不上的问题？是模型内容识别和语义理解出了问题吗


问得很准。结论先说：**不全是模型的语义理解问题——每一条数据错位都能追溯到具体的结构性原因。准确归因是三层叠加：引擎“零语义”架构（无兜底网）× 规范契约缺口（模型没被要求做这些事）× 模型在清单外的自然遗漏与生成漂移。** 逐层拆开看：

## 第一层：架构性根因 —— 引擎故意“看不见内容”

这套系统的设计哲学是**引擎零语义**（`evidence.py` 开头自我声明“只数事实、零裁决”）：schema 校验、账本重算、引用闭合、幂等，全部是机械规则。这意味着——

> **正文和 JSON 之间的事实一致性，在整条流水线里没有任何机械兜底，100% 依赖 Reader 子代理的提取质量和主控的审定。**

而主控这边，AGENTS.md 又明确要求“主控轻量化：避免全文读取长篇正文，只依据 Reader 的 300~600 字简报同步”——即**人工复核兜底被设计性地放弃了**（省 token 的权衡）。所以 Reader 提取漏什么，状态机就错什么，且引擎的 `check` 永远是 0 errors（我们实测确实如此：机器层全绿，错的全是“软事实”）。这不是谁犯错，而是风险被架构承接了。

## 第二层：规范契约缺口 —— 模型是在“按规矩”漏报

对照 Reader 的作业规范（craft_reader.md）逐条核对，会发现大部分错位**恰好落在提取清单之外**：

| 数据问题 | 直接原因 | 是模型“理解错”吗 |
|---|---|---|
| **P1-5** power_level/abilities 未刷新（引气入体是本章最大事件却没上状态） | craft_reader 对 `current` 区的提取清单只列了 **region/location/time/present_characters/situation** 五项——power_level、abilities、equipment、assets 根本不在 Reader 的必检清单里。AGENTS.md 的“5 大事实”枚举同样没有这些字段 | 不是理解错，是**合同没要求**；模型照单办事 |
| **P2-9** 二十两银子没入账 | 两个因素叠加：① INBOX_README 纪律“**不确定就不上账**”；② ledger 主通货池 unit=“枚”，正文货币是“两/文”，**无折算约定** → 模型面对“二十两碎银子”无法确定 delta 填多少，按纪律选择了保守 omission。另外现有的机械对照 `amounts_in_final` 只扫“数字×已声明池单位”，单位对不上所以也没提示 | 半个：识别到了银子，但因工具语义缺口+纪律倾向而弃账 |
| **P2-10** timeline 事件照抄 beats（“岩参交给赵掌柜”） | craft_reader 把 **beats 列为 Reader 的合法输入**（用于对照线动作），但没有任何规则强调“事实描述必须逐字以 final 为源、禁止复用 beats 措辞”。Editor 在 Stage 3 改写了场景结局（赵掌柜没碰参），Reader 没有做 beats↔final 差异比对的义务 | **这个是真·模型失误**：源锚定错误（anchoring 到了任务书而非定稿），是典型的大上下文源混淆 |
| **P2-11** 章题不一致 | 两个合同缺口：① craft_editor 只要求“100% 纯正文”，**不要求 final 必须带章题标题行**（ch_001 就没有）；② Reader 无“synopsis.title 必须逐字拷贝定稿标题行”的指令 → 模型自拟了一个 | 各占一半：Editor 漏写标题是生成遗漏；Reader 自拟标题是生成习惯（没被告知要拷贝） |
| **P2-12** 灵根口径漂移（五行/四系/下品伪灵根） | 发生在**创作端**（Stage 2/3 Drafter/Editor），不是提取端：ch_001 面板写“五行”，ch_002 写“四系”，bible 写“下品伪灵根”，三方从一开始就没对齐。灵根这种金手指设定没有登记为实体/线，pack 注入的 bible 内容也没有命中这条规则，全库没有任何角色负责“设定口径审计” | **是，但是生成端的漂移**——典型的 LLM 长程一致性弱点，与“读不懂正文”无关 |
| **P2-8** 种子数据绕过提案管道 | 跟模型完全无关：**框架没有合法的初始状态入口**。init 只播种空表，但 ch_001 提案的 present_characters 闭合校验又要求实体先注册——Stage 0 无路可走，只能手工直写 JSON，于是形态走样（缺 `card` 键）、不可重放 | 不是，是流程/引擎能力缺口 |

## 第三层：模型自身的真实失误（占比最小，但存在）

剥掉上面两层后，纯“语义理解/内容识别”问题只剩三处：P2-10 的**源混淆**（抄了 beats 没比对 final）、P2-11 的**自拟标题**（该拷贝的生成了）、P2-12 的**创作端设定漂移**（该查 bible 的没查）。这三个都是 LLM 的已知弱点——长上下文中的源优先级松弛、生成偏好压过拷贝纪律、跨章细节漂移——**但注意它们全都是“清单没约束到的自由发挥空间”里发生的**。清单内的事项（在场人物、实体登记、伏笔流转、holder 闭合）全部提取正确，闭合校验全绿。

## 怎么根治（对应修复方向）

按“让错误无处发生”的优先级：

1. **补合同**（成本最低、收益最大）：把 Reader 的提取清单扩到 current 全部 12 个字段并标明“本章发生境界/伤势/资产/装备/关系变动时必刷”；加一条硬规则“**所有事实性文字（含 timeline 事件、synopsis 标题）逐字以 final 为源，beats 仅用于对照，禁止复用措辞**”；craft_editor 补“final 必须以章题标题行开头”。
2. **消歧义**：Stage 0 约定货币折算口径（或在 bible 偏离清单写明），让“不确定就不上账”没有触发的土壤。
3. **加密机械网**（把引擎能数的都数起来）：`amounts_in_final` 扫描适配池单位别名；`proposal check` 增加“final 出现的已注册实体属性词 vs current 字段”的软对照；标题逐字对照一行正则就能做。
4. **补引擎能力缺口**：给 init 加 `--seed`（走提案管道写入初始状态，根治 P2-8）；timeline events / synopsis.title 增加修订动作（没有修订通道，错误就永远只能“绕开”而不是“改正”）。
5. **可选的 Stage 4.5**：Reader 交付后加一个机械 diff 报告（“本章 final 新出现但提案未提及的已注册实体/金额表达/标题行”），把主控的审定从“信任”变成“看差异”——这正好不违反主控轻量化原则，因为只看差异不看全文。

一句话总结：**模型的语义能力不是短板，短板是“合同没写到的地方模型必然自由发挥”+“引擎设计上放弃了事实兜底”。把清单补全、把歧义消掉、把能机械化的对照加上，这批问题里 80% 会结构性消失，剩下的才是真正需要主控语义裁定的部分。**

---

## 修复波次记录（2026-09-02）

- `91b3b47` 批次①：P0-1（init 限定 workspace 内）+ P1-2（-w SUPPRESS）+ P1-3（auto 拒绝覆盖）
- `c5a501f` P1-1：线动作节正则改 `.*线(索)?动作`（真实两章 beats 实测恢复提取）
- `ffef2f5` P1-4B：review_gate 语义对齐为可选软提示
- `144be4e` 引擎增强：timeline 事件 `replace` 修订 + synopsis `chapters` 跨章修订（P2-10/P2-11 从此可改正而非绕开）
- `66e0ca8` 批次③：契约文档组 P2-13~18 + Reader 三规则（current 12 字段刷新义务、final 为源、章题拷贝）
- 批次④：bible 偏离清单确立灵根唯一口径（四系杂灵根）与货币口径（文，1两=1000文）
- 批次⑤：`state/inbox/ch_003.draft.json` 数据清账草稿就绪（P1-5、P2-8~12 全部修正项，`_draft:true` 防误同步；
  沙箱对真实状态结构预检 rc=0，全部命中）。**终结动作：ch_003 创作完成后，Reader 以该草稿为底装配正式提案，
  `proposal check ch_003` → `sync ch_003` 一次清账。**
