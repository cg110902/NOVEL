# 《拾荒剑仙》全流程 QA 问题清单（调试模式）

> **测试对象**：Novel Studio 引擎 v3.1.0（Python 3.11.2）
> **测试方式**：新书《拾荒剑仙》（玄幻）全流程 Stage 0 → 3×[Stage 1→5] 实跑 + 全命令面（24 命令）/错误路径/退出码/回滚/拒收自愈/污染闸门白盒验证
> **级别**：🔴 阻断级（流水线卡死或数据损坏）｜🟡 功能性（行为与文档不符/有坑）｜🔵 体验/文档瑕疵
> **日期**：2026-09-05
>
> ⚠️ **重建说明（2026-09-05 Phase 2）**：本文件在标注修复状态时曾因脚本缺陷丢失部分正文，当日内依据会话记录与逐项复测重建。P1–P6 为原文逐字保留，其余条目按 Phase 1 测试记录还原（现象/复现均与修复后引擎行为逐项复核一致）；全部 25 项的修复与实证见文末第七节。

## 一、问题列表（18 项）

### P1 🔴 errcode 修复指令引用不存在的命令 `entity add`
- **现象**：`unregistered_character` 错误码的 remedy 写「运行 `python studio.py entity add <实体名>` 登记入 state/entities.json」；实际命令注册表（24 个）中**不存在 `entity` 子命令**，执行报 `invalid choice`，退出码 2。
- **影响**：Agent 按错误码 remedy 自愈时必然失败；且该指令诱导直接手写 entities.json，违反「提案是唯一写入口」铁律。
- **复现**：`python studio.py entity add 测试人物`
- **建议**：remedy 改为「由 Reader 提案登记新实体（Stage 4A 提案 entities 段）」或提供真实登记通道。
- **✅ 已修复（2026-09-05）**：`errcodes.py` 的 `unregistered_character` remedy 改为「由 Reader 提案登记新实体（Stage 4 提案 entities 段，action=upsert）……严禁手改 entities.json」；`checks.get_self_healing_remedies` 中解析 `entity add` 的自愈指令分支一并移除。验证：`errcodes --json` 注册表全文无 `entity` 命令引用。

### P2 🟡 sync 归档/快照未绑定 final 定稿内容哈希
- **现象**：`state/inbox/processed/ch_XXX.json` 仅含提案本体，无 final 内容哈希、无时间戳；`snapshots/*/manifest.json` 只对 6 表 + 操作记录做 SHA-256，不含定稿正文。
- **影响**：sync 封存之后再修订 final（本次 ch_001 补字数、ch_002 补段落，均为同步后修订），状态台账与「事实唯一源头」之间静默漂移，无机械检测。
- **复现**：`sync ch_001` → 修改 `final/ch_001.md` → `check`/`snapshot list` 均无漂移告警。
- **建议**：sync 时对当章 final 计算 SHA-256 记入 processed 归档与 manifest；`check` 比对当前 final 哈希，漂移即报。
- **✅ 已修复（2026-09-05）**：sync 封存时 `_stamp_final_hash()` 对当章 final 盖 SHA-256 → `state/inbox/processed/final_hashes.json`（{sha256, file, ts}）；`snapshot.create_snapshot` 的 manifest 新增 `final_hashes`（快照时刻全部 final 哈希）；`check` 新增 `final_drift` 档（封存哈希 vs 当前内容，漂移即 warning，含「final 已删除」分支）。验证：scratch 书 sync 后改 final → `check` 报 `final_drift`（封存 d07b34…/当前 5afd…）；manifest 哈希与印章一致。注意：存量书（如拾荒剑仙 ch_001–005）从下次 sync 起逐步纳入检测。

### P3 🟡 候选实体探测输出大量 2 字碎片误报
- **现象**：sync 机械对照的 `candidate_new_entity` 输出大量纯语法碎片：「了半」「樵把」「了一 ×13」「来的」「的声」「站在」「不卖」等；`config suggest` 同样把「了一 ×35」「灵通 ×21」当候选停用词。
- **影响**：虽标注「实验性候选，误报勿理」，但每章 8~12 条，持续消耗主控注意力；碎片随章节累积。
- **建议**：候选最小长度提为 3，或接 jieba 分词按词性/名词短语过滤（引擎已依赖 jieba）。
- **✅ 已修复（2026-09-05）**：`evidence.py` 新增 `is_generic_locutive_noise()`（语法助词 的了着过 / 普通地名首字 / ≤3 字方位尾字 脚口边旁里外沿顶底下上），接入 `is_candidate_noise`；`names()` 的 n-gram 退化路径最小长度提至 3 且 L=(3,4)；账本池名（实体/主角/ledger 池）精确匹配过滤。验证：3 章合成书 `evidence names` 候选仅剩「太师椅/安静」两条真实词，零方位碎片；「山脚/水口/脚下/走了」全部判噪。

### P4 🔵 字数契约为软约束（info 级），与 beats 硬合同存在落差
- **现象**：beats 合同 `words: 2000-3000+`，但 `word_band_deviation` 注册为 info 级，check 不阻断。ch_001 第一版 1453 字（CJK）sync 照过，靠人肉发现后扩写。
- **建议**：定稿低于带下限 15% 升 warning；或 project.json 提供 `words_hard_gate` 开关。
- **✅ 已修复（2026-09-05）**：`check` 字数带改双层判定——出带 15% 容差内 = `word_band_deviation`（info，口径注明「剥离首行章题计 CJK，压线章多留 5~10 字」）；显著出带（<下限 85% 或 >上限 115%）= 新增 `word_band_breach`（warning，beats 硬合同口径）。验证：551 字 → breach；1714 字（带 [2000,3000] 下限 85%~100% 区间）→ deviation info。

### P5 🔵 `--json` 契约在错误路径不完整
- **现象**：未 init 书时 `python studio.py cockpit --json` 输出纯文本「❌ 未找到书工作区…」（退出码 1），而非 JSON 错误信封，Agent 按 --json 解析会失败。
- **建议**：--json 模式下所有错误路径也输出 `{"ok": false, "code": "project_missing", ...}`。
- **✅ 已修复（2026-09-05）**：`_shared.py` 新增 `ws_gate(args)`（JSON 模式错误路径零文本、只出 JSON 信封；`_resolve_and_validate` 增加 `suppress_text` 防多书清单重复打印）；全部入口命令（status/cockpit/config/check/beat/pack/ask/pov/calendar/evidence/…12×chapter_flow 守卫 + state_sync 6 命令）统一走 ws_gate；config 的用法错/未知键也出 JSON 信封。验证：两书并存 `status --json`（无 -w）→ 纯 JSON `{exists:false, reason: multiple_books, books:[…], next_action}`；`-w` 不存在 → `{reason: workspace_not_found}` 且退出码 1；`--json` 下 stderr 干净。

### P6 🟡 Critic 催更雷达标签匹配过严且静默失败
- **现象**：`cockpit.py` 按固定关键词匹配便签行（`本章体感`/`连续性红旗`/`疲劳度`/`信息差`/`活人感`/`路人缘`/`最想看`/`最怕踩`）。ch_001 便签用了变体标签「体感」（规范为「本章体感」）→ `vibe` 静默为空、无告警；未按模板写的段落整体丢失。
- **影响**：宪法宣称「雷达为准、免翻原文」，雷达漏提时主控制假「无反馈」而不再回读——催更情报静默丢失。ch_002 起改用规范模板后 8 字段全部提取成功（对照实验成立）。
- **建议**：便签存在但字段全空时输出 warn「格式疑似偏离模板，请回读原文」；关键词加变体容错。
- **✅ 已修复（2026-09-05）**：`_FIELD_KWS` 每字段加关键词变体元组（体感/阅读体感/本章体感、连续性红旗/连续性/红旗、疲劳度变体、信息差、活人感、路人缘；最想看/迫切期待）；便签存在且非骨架（无 SKELETON/待评标记）、内容行 ≥3、8 字段全空 → `format_warning` 明示「格式疑似偏离规范模板，请回读原文核对；雷达不作『无反馈』解读」，终端 cockpit 以 🚨 红色行渲染。验证：自由格式便签（3 内容行）→ JSON `critic_radar.format_warning` 命中 + 终端 🚨 行可见。

### P7 🔴 beats 脚手架「上章现场/所属阶段」注入为死代码（模板标记不匹配）
- **现象**：`cmd_beats` 用 `text.replace("<模板标记>", coord_block)` 注入「所属阶段/上章现场」，但该标记字符串在 `templates/beats.md` 中**不存在** → replace 静默 no-op，脚手架从未带出阶段坐标与上章现场。
- **影响**：主控 Stage 1 写细纲时看不到「本章属于哪个分卷阶段 + 上章停在哪」，必须人肉翻上章 final 与 state 拼坐标；注入逻辑形同虚设。
- **复现**：`beats new ch_NNN --write` → 生成文件中无「所属阶段/上章现场」两行。
- **建议**：模板补标记段；注入失败必须可见（stderr），不允许静默。
- **✅ 已修复（2026-09-05）**：`templates/beats.md` 新增「## 本章坐标（引擎自动注入 · 可改）」段与标记 `<!-- 双方不可退让的核心诉求与冲突点 -->`；`cmd_beats` 把死代码 replace 改为「标记替换 → 锚点（本章核心戏剧目标）上方注入 → frontmatter 后独立块」三级回退，任何路径失败都打 stderr ⚠️，绝不静默。验证：scratch 书 `beats new ch_002 --write` 生成文件含注入段（所属阶段/上章现场两行），frontmatter 完好。

### P8 🔵 beats 脚手架 form 默认值硬编码「暗流汇聚」，连续同章型陷阱
- **现象**：脚手架 `form: {{slot:form|暗流汇聚}}` 默认值写死；上一章也用了该值时脚手架照旧给同一章型。
- **影响**：连续同章型（`beats_form_repeat_without_reason` 检查项）从脚手架阶段就埋雷，主控不留意就触发。
- **建议**：读上一章 form，与默认值相同则切换到推荐章型清单的下一个值。
- **✅ 已修复（2026-09-05）**：`default_form` 读上一章 beats front-matter 的 `form`，若上一章用了默认值则切换到推荐清单（危机逼近/生死博弈/战后清点/暗流汇聚）中的第一个异值。验证：ch_001 form=暗流汇聚 → ch_002 脚手架 `form: 危机逼近`。

### P9 🔵 state_watch 关键词无上下文消歧（同词重载误报）
- **现象**：`state_watch` 守望档按纯字符串命中，无上下文消歧——同词多义（如境界名与道具名同字）时对未变动的 current 字段也出警示。
- **建议**：参数口径注明「纯字符串命中、无消歧」，供参时拆分词表或限定词形。
- **✅ 已修复（2026-09-05）**：`PARAM_SPEC.state_watch` 的 desc 显式注明「守望按纯字符串命中、无上下文消歧——同词多义（如境界名与道具名同字）请拆分词表或限定词形，防误报」；`config guide/list` 随规格单呈现该口径。

### P10 🔵 mention_not_present 对「中场退场」角色每章报警
- **现象**：角色本章提及 2~3 次（叙事中段退场属常态）但未列入 present_characters → 每章 warn 一次，与 present_unmentioned 一样消耗注意力。
- **建议**：提及 2~3 次降为 info；≥4 次才大概率真在场、保留 warn。
- **✅ 已修复（2026-09-05）**：`mention_not_present` 分级——提及 2~3 次（中段退场常态）= info；≥4 次才 warn。验证：林樵本章提及 3 次未列入 present → 仅 `ℹ️ [mention_not_present]`。

### P11 🔵 字数带判定口径不含首行章题（文档未注明）
- **现象**：`check` 的字数带按「剥离首行章题的正文」计 CJK，文档/模板均未注明；压线章主控按全文计数以为在带内、实为出带。
- **建议**：beats 模板 words 行与 `word_band_deviation` 文案注明口径与压线余量建议。
- **✅ 已修复（2026-09-05）**：`templates/beats.md` 的 words 行上注释口径「check 按剥离首行章题的正文计 CJK——压线章请在 bands 下限上多留 5~10 字余量（低于下限 15% 会触发 word_band_breach 警告）」；`word_band_deviation` 的 errcode remedy 同步注明口径。

### P12 🔵 多书歧义提示重复打印两次
- **现象**：多书并存且未给 `-w` 时，`status` 的解析层打印一次书清单、cmd_status 兜底分支再打印一次。
- **建议**：解析层已提示时兜底分支去重。
- **✅ 已修复（2026-09-05）**：`_resolve_and_validate` 打印多书清单时置 `resolve_note_shown()` 标记，`cmd_status` 文本/JSON 分支在标记已置时不再二次打印。验证：两书并存文本 `status`（无 -w）→ 书名清单恰好出现 1 次。

### P13 🔵 `graph path` 终点缺失时退出码为 0
- **现象**：`graph path`/`neighbors` 节点缺失或无连通路径时打印 ❌/⚠️ 但进程退出码仍 0；Agent 按退出码判成败会漏检。
- **建议**：advisory 命令放宽为退出码 1（非 2，避免与用法错误混淆）。
- **✅ 已修复（2026-09-05）**：`graph.py` 的 `cmd_path`/`cmd_neighbors` 返回 int，节点缺失/无路径 → 1，成功 → 0；`run_graph` 透传。验证：`graph path 不存在 林樵` → 1；`graph neighbors 不存在` → 1；连通 path → 0。

### P14 🔵 failed/ 归档不嵌入拒收原因
- **现象**：提案被拒收后归档 `failed/ch_XXX.json` 仅含提案原文；拒收原因只存在于当时 stdout。Agent 事后重跑 sync 做「报错→修复→重跑」自愈时原因已丢失，只能盲猜。
- **建议**：归档时同步写拒收原因侧车（结构化 reasons 列表）。
- **✅ 已修复（2026-09-05）**：`state.py` 新增 `_write_rejection_sidecar()`——拒收归档时同步写 `_<名>.rejection.json`（下划线前缀，不匹配 ch_*.json 合并/捡回正则），含 {chapter, operation_id, reasons, ts, note}；JSON 解析失败与 apply 错误两条归档分支都挂接。验证：实体 type 非法/前置冲突/循环依赖三次拒收，侧车均含逐条 reasons；「按 reasons 逐条修复后重跑 sync 自愈」不再依赖 stdout。

### P15 🔵 state 子命令文档与实际语法不符
- **现象**：`state` 帮助写「show/get/set current/entities」之类，实际语法是 `get <表.字段>` / `set <表.字段> <值>`；主控照文档首次执行即 usage 错误。
- **建议**：帮助与命令面说明改为真实语法 + 示例。
- **✅ 已修复（2026-09-05）**：`cli.py` 的 COMMAND_HELP 与 argparse help 改为真实语法「state show ｜ get <表.字段> ｜ set <表.字段> <值>（如 state get current.time）」。验证：`state --help` 与 `help` 输出一致可用。

### P16 🔵 status 与 cockpit 对同一条线的措辞不一致
- **现象**：同一条到期/逾期线，status 说「距到期 N 章」（含「0 章」歧义表述），cockpit 雷达说「imminent/下一章引爆/逾期」——同线两种口径，且 status 与 cockpit 数字基准不同（已定稿章数 vs 下一章）。
- **建议**：status 债务行复用 cockpit 雷达口径（基准=下一章），统一逾期/引爆/倒计时措辞。
- **✅ 已修复（2026-09-05）**：`_status_debts` 复用 cockpit 雷达口径（基准 = 已定稿章数+1），三分措辞：🚨 已逾期 N 章待收束 / 🔥 下一章预定引爆 / ⏳ 距引爆 N 章，并补「另有 N 条同量级，见 evidence gaps」溢出提示。验证：同书同章 status 出现三档措辞（含 🚨 已逾期 2 章 / 🔥 下一章引爆 / ⏳ 距引爆 1 章 及溢出提示），与 cockpit 雷达不再矛盾。注：初版实现曾漏「逾期 ≥2 章」的线（过滤条件 `0 <= target-cur` 把它们吞掉），全套复验中查出并修复（见第七节附带修复 4）。

### P17 🟡 KNO（秘密线）无「知情圈」字段，POV 推导误标
- **现象**：knowledge 线只有自由文本 `note` 描述保密边界；`pov` 推导把「账本未揭示 = 该角色不应知情」机械套用，对知情圈内的角色（如主角本人知道自己剑灵会醒）也标「不应知情」——起草员据此写出「主角不知道自己剑灵醒了」的吃书句。
- **影响**：秘密线的知情边界只能靠 note 人读，POV 参考卡系统性误标。
- **建议**：KNO 增加选填 `holders`（知情圈实体名/别名数组）；pov 对圈内角色剔除误标；文档同步。
- **✅ 已修复（2026-09-05）**：`models.lines.Knowledge` 新增选填 `holders: list[str]`（知情圈，schemas 已重新生成）；提案校验限定仅 knowledge 线支持；`evidence.pov()` 的 `unknown_to_char` 对 holders 内角色（含别名互含）不再标「不应知情」，items 回显 holders；INBOX README 与 reader SKILL 文档同步。验证：KNO plant 携带 holders=[林樵] → `pov 林樵` unknown_to_char 为空、`pov 赵七星` 仍列该秘密。

### P18 🔵 evidence names 把普通名词当未注册候选
- **现象**：`names` 的 n-gram 退化路径（jieba 缺失时）把 2 字碎片与普通方位名词（山脚/水口/石边一类）列入 unregistered 候选。
- **建议**：同 P3——最小长度 3 + 普通方位词过滤 + 账本池名过滤。
- **✅ 已修复（2026-09-05）**：同 P3——`is_generic_locutive_noise` 接入 names 候选与 config suggest 共用过滤；「普通名词当候选」收敛为低频真实词（合成书仅剩太师椅/安静）。

### P20 🟡 sync 的「状态体检」与完整 check 电池不一致（前置闸门不在合并时拦截）
- **现象**：`prerequisite_cycle`/`prerequisite_unmet` 只在独立 `check` 可见；sync 的合并前「状态体检」不查前置因果——一个把「线已闭环但前置未达成」或「requires 成环」的状态合进台账的提案照样放行，因果违规作为既成事实落库。
- **影响**：状态机最硬的因果约束在最危险的入口（合并）缺席。
- **建议**：两类前置因果检查提升为写闸门（verify_data），合并时即拦截。
- **✅ 已修复（2026-09-05，行为变更）**：`state.verify_data`（写闸门）并入 `_prereq_errors`——合并时即拦截「本线已闭环而前置未达成」与「requires 循环依赖」，不再等独立 check。验证：同案 plant+resolve 且前置未回收 → sync 拒收「已标记完成(Resolved)，但其前置依赖 GUN-001 仍未完成(Planted)」；双 requires 互指 → 拒收「存在循环前置依赖（requires 闭环）」。注意：此修复把原「advisory 可合入」的边界套件判定改为硬拒收（有意的行为变更）。

### P21 🔵 跨章 synopsis 修订对未注册章静默 no-op
- **现象**：`synopsis.chapters` 指向未登记章节时，合并静默跳过、提案照常归档 processed、快照照常封存——主控以为历史章梗概已修订，实际从未落库。
- **建议**：指向未注册章整案拒收并给路（正常登记随该章 sync 走 synopsis.text）。
- **✅ 已修复（2026-09-05）**：`_merge_synopsis` 对 `synopsis.chapters` 指向未登记章节由静默 no-op 改为整案拒收，错误文案指路「正常登记请随该章 sync 走 synopsis.text」。验证：ch_002 未登记时修订通道 → 拒收；ch_001 已登记后同案「ch_002 登记 + ch_001 修订」→ 正常合并且 ch_001 梗概更新为修订版。

### P22 🔵 退役实体仍可出现在 present_characters（仅高危警告不拒收）
- **现象**：同案把实体 retire 且 present_characters 仍含该实体 → 只打 🚨 高危警告，「已退役但在场」的矛盾状态照常入库（下章 present 又带着退役角色走）。
- **建议**：合并时自动从 present 剔除 + 醒目提示（闪回章显式先转 active）。
- **✅ 已修复（2026-09-05）**：`apply_proposal` 合并 entities 后自动把「本提案内退役（action=retire 或 upsert 携带 status=retired）」的实体从 present_characters 剔除并打醒目警告（闪回章请先 status=active）。验证：upsert status=retired + present 含该实体 → 合并且 present 清空、警告可见，矛盾状态不再入库。

### P23 🔵 form_share_over_limit 有 5 章最小样本门槛（文档未注明）
- **现象**：单一章型占比 >40% 的检查实际统计自该卷第 5 章起（小样本不计数），errcode 与文档均未注明——主控在前 4 章用同一章型时不报，误以为阈值没生效。
- **建议**：errcode 描述注明样本门槛。
- **✅ 已修复（2026-09-05）**：`form_share_over_limit` 的 errcode 描述与 remedy 注明「统计自该卷第 5 章起（≥5 章样本才参与统计），小样本不计数」。

### P24 🔵 words_target 无 config 通道
- **现象**：`words_target`/`lines_cap` 只能手改 project.json；`config set/get` 不认这两个键（「未知参数键」），无形状校验——写坏只能事后被 check 的 `project_field_type` 抓到。
- **建议**：纳入 PARAM_SPEC + `config set` 前置形状校验 + 文档口径。
- **✅ 已修复（2026-09-05）**：`PARAM_SPEC` 纳入 `words_target`（int_pair）与 `lines_cap`（cap_map）；`validate_param_value` 对 int_pair 容忍字符串形态（"2000,3000"/JSON/中文逗号）；`config set` 区间键裸字符串回退解析 + 形状前置校验（含 hi<lo、cap_map 键白名单）；`config` 帮助与 cli 命令面说明同步。验证：`config set words_target '1600,2400'` 成功；`[3000,1000]` 拒「下限不能大于上限」；`lines_cap {"active_foreshadows": "many"}` 拒并附合法键清单。

### P25 🔵 target_ch 文档措辞与实现有落差（字符串数字被拒）
- **现象**：文档/示例给「target_ch 接受章号」的宽口径，实现只认四选一：int / `ch_NNN`（三位补零）/ `"第N章"` / `"longline"`；字符串数字 `"21"` 与无补零 `ch_7` 均被拒收——提案被拒后 Agent 需反复试错才摸出合法形态。
- **建议**：四选一口径写入 INBOX README 与 reader SKILL，拒收文案给全合法形态。
- **✅ 已修复（2026-09-05）**：target_ch 四选一口径（int / ch_NNN 三位补零 / "第N章" / "longline"；字符串数字与无补零 ch_N 均拒）写入 INBOX README、reader SKILL.md（含取值示例与 plant 必填说明）；拒收文案同步给出全部合法形态。验证：`"4"` → 拒收（文案含四选一全表）；`ch_009`/`"第11章"` → 正常入账 target 9/11。

## 二、能力缺口（用户请求预设存在、实际缺失）

### G1 引擎无调试/诊断模式
- **现象**：用户开局指令含「开启调试模式」，但引擎无任何 debug 开关——闸门逐层判定、幂等哈希比对、引文接地相似度、账本重算明细、cockpit 各节耗时全部黑盒；排查只能改源码加 print。
- **建议**：提供 env 级调试通道，诊断信息走 stderr（不污染 --json stdout）。
- **✅ 已修复（2026-09-05）**：`common.debug_enabled()/debug()`（env `NOVEL_STUDIO_DEBUG=1`，全部走 stderr、不污染 --json stdout）；接入点：sync 流水线（sync 入口/apply_inbox 汇总/verify 闸门/快照结果）、写闸门逐层 trace（validate_proposal/幂等哈希比对）、引文接地相似度分值、ledger 重算逐笔明细、cockpit 四分节耗时（state_load/workflow_momentum/radars_guidance/health_remedies，开启时入 JSON 的 `debug_timing_ms`）。验证：`NOVEL_STUDIO_DEBUG=1 sync` stderr 出现 `[DEBUG]` 逐层行（quote exact hit / 幂等 hash 比对 / apply_inbox 汇总）；`--json` stdout 仍为纯 JSON。

## 三、测试矩阵与结果

### 3.1 全流程（Stage 0 → 5×[1→5]）✅
- 《拾荒剑仙》（玄幻）init → Stage 0 模板实例化 → 5 个完整工序循环（beats → raw → final → reader/critic 双轨 → sync+快照）。
- 定稿 5 章共 10452 CJK；ch_005 单章 2063 CJK（带内）；ledger 资源池 balance +15 对账平；快照 7 个（含 pre_rollback 备份）。
- 在途活扣（live check 码）：`plotline_starvation` / `line_action_missing` / `line_overdue` 三条同指 MIS-001（target_ch=3 逾期未收束）——属剧情决策项，非引擎缺陷。

### 3.2 命令面（24 命令全部可调用）✅
- status / cockpit / init / pack / ask / pov / calendar / evidence / check / checkpoint / state / config / sync / snapshot / ledger / export / dashboard / proposal / review / beats / critic / graph / help / errcodes —— 全部 rc=0 出正常输出（用法错误路径 rc=2 符合 argparse 契约）。

### 3.3 错误路径与闸门 ✅（除 P1/P5/P13 外行为符合契约）
- 损坏 state/project.json → check 报 state_unreadable/project_corrupt 并退出 1；
- 同 operation_id 同内容重放 → 幂等跳过；同 id 异内容 → 整案拒收（身份冒用）；
- `candidate_*` 工程痕迹字段 → 污染闸门整案拒收；
- `snapshot rollback --clean-drafts` → 状态回滚 + 超前稿件移入 workspace/.trash 回收区（不直接删）；
- `pack` 无 beats 章 → 明确拒并退出 1。

### 3.4 第二轮合成边界测试（临时书 4 章脚手架，全部可复现）
**拒收（符合契约）**：实体 type 枚举越界、ledger 引用未声明池、current 字段拼写错、提案顶层未知键、line ID 格式错、target_ch 字符串数字/无补零章号、跨章修订指向未登记章。
**放行（符合契约）**：timeline/synopsis 修订通道（已登记章）、别名 ask、clocks 登记、「第N章」/ch_NNN 章号归一化、损坏 state 恢复后重跑。
（临时书与 .trash 测试后已删；Phase 2 修复验证所用 scratch 书《验证测试》同样验证后已删。）

## 四、正向验证（做得好的）
- 提案是唯一写入口：一切状态变更走 inbox → sync → processed 审计链，无后门；
- 幂等与身份冒用双闸门（operation_id → canonical hash），重复 sync 安全；
- 引文柔性接地（≥85% 命中 / 60~85% 近似 / 更低存疑）全程只提示、绝不阻断——接地机制与放行效率解耦；
- advisory（候选/机械对照）与硬闸门（写闸门/枚举/形状）职责分离清晰；
- errcode 单一真源 + 守卫测试（未注册码当场报警）；
- 快照 = 状态六表 + 操作记录 SHA-256，回滚前自动 pre_rollback 备份；
- ledger recompute 逐笔重算 + balance_after 机械对账；
- 回收区设计：清理/回滚的稿件永不 unlink，全部落 workspace/.trash；
- 模板槽位 `{{slot:}}` 硬闸门（Stage 0 未完成不给开写）。

## 五、流程侧记录（本次执行中的工序问题，非引擎缺陷）
- 主控侧 bash 助手缺 `"$@"` 透传导致 JSON 参数被拆碎（已改走 heredoc 写盘）；
- `config set` 未带 `-w` 在多书环境静默 no-op（引擎按「单书自动选中」口径走，属口径设计；Phase 2 起 config 入口已统一 ws_gate 提示）；
- ch_001 草稿首版 1453 字低于带下限 15%（P4 修复前仅 info 级，靠人肉扩写发现）；
- 一次嵌套引文调用格式错误（调用方问题，引擎按 JSON 解析失败正常拒收）；
- P14 命名陷阱：侧车若用 `ch_XXX.rejection.json` 命名会被合并/捡回正则误认（已改用 `_` 前缀规避）；
- P17 新增字段必须重新生成 schemas（schema_gen），否则模型校验与 JSON Schema 双轨不一致。

## 六、修复优先级建议
1. 🔴 P1（自愈指令指向不存在命令）、P7（脚手架死代码）——先修；
2. 🟡 P2（定稿漂移无检测）、P3/P18（候选噪声）、P6（雷达静默丢情报）、P17（知情圈）、P20（前置闸门不在合并时拦截）——核心功能补齐；
3. 🔵 P4–P5、P8–P16、P21–P25——体验/文档/契约一致性批；
4. G1（调试模式）——用户预设能力，随批交付。

## 七、修复实施总览（2026-09-05，Phase 2）

> 用户指令：修复问题清单上的所有问题（24 项 + G1），其他错误一并修复。25 项全部修复并逐项实证（scratch 书《验证测试》4 章合成流程 + 真书《拾荒剑仙》回归），scratch 产物验证后已删。

**改动面（17 个文件）**：
- `engine/common.py`：debug 开关与 stderr 通道（G1）；`find_chapter_files` 路径风格修复（见下「附带修复」）
- `engine/commands/_shared.py`：`ws_gate` / `suppress_text` / `resolve_note_shown`（P5/P12）
- `engine/errcodes.py`：P1/P23 remedy 更正，新增 `word_band_breach`、`final_drift`，P4/P9/P11/P24 口径文案
- `engine/checks.py`：band 双层判定（P4）、final_drift 档（P2）、P10 分级、mention 阈值、PARAM_SPEC 扩键（P9/P23/P24）、`validate_param_value` 字符串形态（P24）、引文分值 debug（G1）、自愈分支清理（P1）
- `engine/state.py`：holders 校验（P17）、前置因果写闸门 `_prereq_errors`（P20）、synopsis 未注册拒收（P21）、退役-present 自动剔除（P22）、拒收侧车 `_write_rejection_sidecar`（P14）、target_ch 口径文案（P25）、INBOX README 更新（P17/P21/P25）、幂等/闸门 debug（G1）
- `engine/models/lines.py` + `engine/schemas/lines.schema.json`：`Knowledge.holders`（P17，schemas 已重新生成）
- `engine/evidence.py`：`is_generic_locutive_noise`（P3/P18）、names L=(3,4) 与账本池过滤（P3/P18）、pov holders 剔除与回显（P17）
- `engine/cockpit.py`：雷达变体关键词 + format_warning（P6）、四分节耗时（G1）
- `engine/commands/book_setup.py`：status/cockpit/config 走 ws_gate（P5）、多书去重（P12）、债务三分措辞（P16）、config 裸字符串/形状校验（P24）
- `engine/commands/chapter_flow.py`：12× 守卫走 ws_gate（P5）、`default_form`（P8）、坐标注入三级回退（P7）
- `engine/commands/state_sync.py`：final 印章 `_stamp_final_hash`（P2）、留置语义文案、6 命令 ws_gate（P5）、sync/ledger debug（G1）
- `engine/snapshot.py`：manifest `final_hashes`（P2）
- `engine/graph.py`：path/neighbors 退出码（P13）
- `engine/cli.py`：state/config 帮助真实语法（P15/P24）
- `templates/beats.md`：本章坐标段与标记（P7）、words 口径注释（P11）
- `.agents/skills/reader/SKILL.md`：target_ch 四选一口径 + holders 供参说明与示例（P25/P17）

**修复过程中附带发现并修复的其他错误（4 处）**：
1. `common.find_chapter_files` 内部 `resolve()` 使返回路径恒为绝对，调用方持相对 `book` 时 `relative_to` 抛 ValueError（cockpit/check 在库调用场景崩溃）——改为与入参同路径风格、安全检查仍在 resolved 上进行；
2. P22 原实现只识别 `action: "retire"`，未覆盖 README 文档口径的 `status: "retired"` upsert 写法——两种写法现均触发自动剔除；
3. `beats` 坐标注入兜底分支原会 prepend 到文件最顶、破坏 frontmatter（`---` 必须在首行）——改为插到 frontmatter 之后；
4. `_status_debts` 初版过滤条件 `0 <= target_ch - cur` 把「逾期 ≥2 章」的线整个排除（逾期越久越不显示）——去掉下界，逾期线全部入列（全套复验第 45 项断言中查出）。

**实证覆盖（scratch 书，验证后删除）**：
- 正向：init → beats（P7/P8 注入）→ 提案 sync（实体/伏笔/KNO holders/梗概/修订通道）→ 快照 → 4 章滚动
- 闸门：P20 未决前置与循环依赖拒收、P21 未注册章修订拒收 + 已登记章修订放行、P22 退役-present 剔除、P25 字符串数字拒收 + ch_NNN/第N章 放行、污染闸门（candidate_* 拒收）、身份冒用拒收、幂等重放
- 审计：P14 侧车 ×3、P2 印章 + manifest 哈希 + final_drift 实证、P4 breach/deviation 双档、P16 三分措辞、P6 format_warning 终端 🚨
- 回归（真书《拾荒剑仙》5 章）：check 0 errors（仅既有 4 warnings）、status --json 纯净、cockpit 渲染、24 命令面全绿、rollback --clean-drafts → workspace/.trash 回收区（10 文件保全）
- **全套复验（最终代码状态，45 项自动断言）**：全部改动落定后，用全新 scratch 书把 25 项功能 + 闸门 + 审计 + 文档口径 + 真书回归一次性重跑，45/45 绿；复验即查出上述附带修复 4（P16 逾期过滤）并已修复回归

**有意的行为变更（1 处，需周知）**：P20 修复后，前置循环/未决前置的提案由「可合入、check 后见警告」改为 **sync 即拒收**（错误信息含修复指引，failed/ 侧车留痕）。这是修复目标本身（写闸门前置），但依赖旧「宽松合入」行为的流程需要调整。
