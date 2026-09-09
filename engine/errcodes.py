"""错误码注册表：Novel Studio 引擎全部体检错误码的机器可读说明书。

定位：这些错误的最终消费者往往是 LLM Agent（主控拿到 `check --json` 后要自助修复），
因此每个码必须有：level（error/warning/info，决定投递到哪条通道）、
description（一句话人话解释）、
remedy（可执行的修复建议）。

单一真源约定：
- `checks.DEFAULT_REMEDIES` 由本注册表派生（`_err` 的 remedy 兜底），禁止在别处再手写 remedy；
- checks.py 源码中出现的每个 `_err("code"` 字面量
  必须已注册，新增错误码漏注册会当场报警。

level 为数据驱动：按 run_checks 实际把错误码投递到 errors/warnings/infos 哪条通道归类。
（字段名是 level，不是 severity——`errcodes --json` 输出的键就是 level/description/
remedy/code 四个；audit 候选里的 severity=candidate_hard/soft 是另一套东西，勿混。）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrCode:
    code: str
    level: str            # error（阻断）/ warning（建议处理）/ info（提示）
    description: str      # 一句话人话解释
    remedy: str           # 修复建议（checks._err 的兜底文案同源）


def _reg(code: str, level: str, description: str, remedy: str) -> ErrCode:
    return ErrCode(code=code, level=level, description=description, remedy=remedy)


REGISTRY: dict[str, ErrCode] = {c.code: c for c in (
    # ---- 项目底座 ----
    _reg("project_missing", "error", "书工作区缺失或没有 project.json（未初始化）",
         "运行 python studio.py init <书名> 初始化项目工作区。"),
    _reg("project_corrupt", "error", "project.json 损坏（JSON 语法错误等）",
         "检查 project.json 的 JSON 语法并修正，或从 snapshots 快照目录恢复。"),
    _reg("project_field_empty", "error", "project.json 缺少必填字段设定",
         "在 project.json 中补齐缺失的字段设定（如 title, genre, protagonist 等）。"),
    _reg("project_field_type", "error", "project.json 字段类型不符（如 words_target）",
         "将 project.json 中的 words_target 修正为二元整数数组 [min, max]。"),
    _reg("wordlist_unconfigured", "info", "书级词表参数未配置，对应启发式检查档已跳过",
         "运行 python studio.py config suggest 获取推荐词表并根据需要配置。"),
    _reg("param_shape_invalid", "error", "词表参数的形状不符合型号单要求",
         "检查 project.json 配置项格式，确保符合规范规范要求。"),
    # ---- 状态机 ----
    _reg("state_inconsistent", "error", "状态数据不一致（如账本余额与流水对不上）",
         "运行 python studio.py ledger recompute 重新核对账本，或手动平账。"),
    _reg("ledger_tx_order", "error", "账本流水的章节顺序错乱（他章流水插在本章之后），"
                                    "balance_after 已与编年史矛盾",
         "运行 python studio.py ledger recompute——重算会先按章号重排流水再重算余额与 "
         "balance_after；重排后仍有倒序说明存在非法跨章流水，请核对是哪一章的提案写错了 chapter。"),
    _reg("ledger_arith_broken", "error", "账本算术不闭合（balance_after 与 initial+累计流水矛盾，"
                                        "或 pools.current 与全部流水重算结果不符）",
         "运行 python studio.py ledger recompute 按流水重算余额与 balance_after；"
         "若重算后仍不闭合，说明某笔 delta 本身写错，请核对该章提案的金额。"),
    _reg("amount_arith_unverified", "warning", "正文声称的余额变动与账本本章净变动不闭合",
         "正文里的「由 X 变为 Y」必须与本章该资源池的流水净变动一致；"
         "请改正文数字，或补一条 ledger 流水，使跨文档算术闭合。"),
    _reg("state_unreadable", "error", "状态文件缺失或损坏无法读取",
         "检查 state 目录下的 JSON 文件语法并修复，或从快照回滚。"),
    _reg("unregistered_character", "error", "登场人物未在实体注册表登记（吃书风险）",
         "由 Reader 提案登记新实体（Stage 4 提案 entities 段，action=upsert，见 state/inbox/README.md），"
         "或修正提案 present_characters/正文中的拼写。严禁手改 state/entities.json——提案是唯一写入口。"),
    _reg("retired_entity_on_stage", "warning", "已退场/离世的实体再次登场",
         "该实体已标记退场/阵亡；若重新出场请先在 entities.json 中更新状态或更名。"),
    _reg("entity_id_duplicate", "error", "多个实体共用相同 ID（唯一主键冲突）",
         "检查 state/entities.json 中重复的实体 ID，确保每个实体拥有全书唯一的业务标识。"),
    # ---- 章节文件结构 ----
    _reg("duplicate_final", "error", "同章存在多份定稿（真理源不唯一）",
         "清理重复的 final 文件，保持同章唯一的单一真理源。"),
    _reg("final_gap_chapters", "error", "章号断档（章节序列有缺口）",
         "检查分卷目录下的章号顺序，补齐遗漏章节或修正文件名。"),
    _reg("final_without_raw", "warning", "有定稿但没有对应初稿毛坯（审计链缺失）",
         "流程完整性建议：运行工序时留存 raw 草稿毛坯记录以备审计。"),
    _reg("final_without_beats", "warning", "有定稿但没有对应细纲（流程完整性缺失）",
         "流程完整性建议：运行 python studio.py beats new ch_XXX 补充细纲。"),
    _reg("unfilled_slot", "error", "模板中存在未填充的 {{slot:...}} 占位符（Stage 0 未完成）",
         "修改 beats 细纲或世界观文件，将 {{slot:...}} 占位符替换为具体剧情或设定内容。"),
    _reg("encoding_replacement_chars", "warning", "正文检测到编码替换字符（乱码迹象）",
         "检测到编码替换字符（如 \\ufffd），请使用 utf-8 重新保存受影响的文件。"),
    _reg("runtime_dependency_missing", "error", "运行环境缺失关键依赖库（如 pydantic, jieba, networkx, rapidfuzz, rich）",
         "请在当前 Python 环境运行 pip install -r requirements.txt 安装必要运行时依赖。"),
    _reg("manuscript_truncation", "error", "正文段落异常截断或未闭合（末尾未完句、引号失衡等）",
         "检查正文末尾是否因生成中断被强行截断，补全未完语句或闭合双引号。"),
    _reg("workspace_permission_error", "error", "工作区目录无写入权限或磁盘写入受阻",
         "检查 workspace 目录及子目录的读写权限，确保进程有权创建与修改文件。"),
    # ---- 提案与候选 ----
    _reg("candidate_leak", "error", "candidate_* 候选字段泄漏进正式数据",
         "将未定命名 candidate_* 替换为具体的角色名或地名。"),
    _reg("latin_residue", "warning", "中文稿正文含拉丁字母残留（起草夹带的英文词）",
         "把正文里的英文词改写成中文；若确属外文专名、品牌或缩写等合法情形，"
         "请用 python studio.py config set latin_allowlist --merge '[\"词\"]' 声明白名单。"),
    # ---- 伏笔暗线 ----
    _reg("plotline_starvation", "warning", "线索长期未推进（伏笔饥饿）",
         "该线索长期未推进，请在当章或后续章节 beats 中安排线索推进（advancement）或提及（remind）。"),
    _reg("line_never_surfaced", "warning", "线索已登记入账，但正文中从未真正出现过",
         "该线只存在于台账、读者从未读到。请先在正文中把它写实（哪怕一句侧写），"
         "否则日后回收等于凭空兑现。若确不打算写，请用 resolve/retire 收掉该条。"),
    _reg("locked_fact_untraceable", "info",
        "locked 新条目的 fact 不含任何已登记实体名/别名，读者记忆层无法追踪（闸门 3 盲区）",
        "把相关实体名写进 fact（如「张三」而非「那人」）；若确为无实体全局事件，可忽略本提示"),
    _reg("line_recall_cold", "warning", "计划回收的线索在正文中久未重现，读者可能已遗忘",
         "建议本章先 remind 回响一次（提案 lines 里带 "
         "{\"action\":\"remind\",\"id\":\"<线ID>\"}），或把回收改期到回响之后。"),
    _reg("reader_memory_stale", "warning", "关键事实（不可逆事实/已揭示秘密）久未在正文重现",
         "读者可能已忘记这条设定。建议在后续章节安排一次自然回响（借对话或场景侧写带出），"
         "不要等到要用它时才重新解释。"),
    _reg("tier_shift_without_event", "warning", "实体位阶变更无对应 timeline 事件（战力通胀/通缩风险）",
         "位阶（tier_rank/tier_name）变更应有突破/晋升/被废/跌境等剧情事件支撑。"
         "请在提案 timeline.events 补记该事件（既有事件修订走 replace 通道），"
         "或修正 entities 的 tier 值。"),
    _reg("prerequisite_missing", "warning", "线索声明的依赖项在台账中不存在",
         "在 state/lines.json 中补齐前置线索定义，或修正该线索的 requires 依赖项。"),
    _reg("prerequisite_unmet", "error", "前置线索未达成就尝试收网/揭晓",
         "该线索依赖的前置线索尚未达成！请将当章 action 改为 remind，或先推进前置线索，待前置线索达成后方可收网/揭晓。"),
    _reg("prerequisite_cycle", "error", "线索依赖关系形成闭环",
         "检查并解除线索依赖闭环，破除循环 requires 拓扑。"),
    _reg("line_action_orphan", "warning", "细纲声明了线索动作但台账中无对应线索",
         "细纲中声明了线索动作但未在 lines.json 找到对应线索，请核对线索 ID 或在 lines 中登记。"
         "两种豁免写法：计划本章 plant 的新线写「plant GUN-XXX」；本章明确不推进的未登记线写"
         "「skip GUN-XXX」（也接受 hold / defer / 不涉及 / 不推进 / 顺延）。"),
    _reg("lines_state_unreadable", "warning", "lines 账本不可读，因果依赖守卫降级",
         "检查 state/lines.json 的 JSON 语法并修复，修复后重跑 python studio.py check。"),
    _reg("alias_conflict", "warning", "同一别名被多个实体共享（在场推断/提及统计将产生歧义）",
         "在 state/entities.json 中把冲突别名改为唯一，或改用 aliases 归并到同一实体名下。"),
    _reg("relation_target_unknown", "warning", "实体关系指向未登记的实体（关系图悬空边）",
         "在 state/entities.json 补登目标实体，或修正 relations.target 的名称拼写。"),
    _reg("entity_ref_unknown", "warning", "实体的 faction/holder/location 指向未登记实体（悬空引用）",
         "补登被指向的实体（势力用 type=faction、地点用 type=place/location），或修正字段里的名称拼写；"
         "location 若只是临时场景描述而非固定地点，可忽略本提示。"),
    _reg("entity_card_missing", "warning", "实体登记的卡片文件不存在（建议补齐卡片或修正路径）",
         "检查实体登记的卡片路径，创建对应卡片文件或在 entities.json 中修正 card 字段。"),
    _reg("entity_tier_invalid", "error", "实体的实力位阶 tier_rank 超出合法区间 [1, 12]",
         "将实体的 tier_rank 修正为 1 到 12 之间的整数。"),
    _reg("item_charges_exhausted", "error", "账本记为耗尽/损毁/退场的道具，正文却出现使用动作",
         "核对道具是否已在前章消耗完毕：若为新获取的同名道具或残存灵力，请在正文明确交代；"
         "否则属硬性吃书，需定向修复。判定来源＝charges==0 / status=retired / condition 明示损毁。"),
    _reg("item_charges_overflow", "error", "道具剩余充能 charges 超出设定的上限 max_charges",
         "核实道具充能数值，确保 charges <= max_charges。"),
    _reg("line_action_missing", "warning", "到期/逾期线未在细纲「线动作」栏登记",
         "该线已到/已过 target_ch 且仍未闭环，但 beats 未在「线动作」栏给出处理。"
         "请在 beats 写明其动作（plant/advance/remind/reveal/resolve）或写明顺延理由，归主控 Stage 1 裁决。"),
    _reg("line_quota_exceeded", "warning", "活跃线索数量超出配额（主线被稀释）",
         "当前活跃线索过多，建议在后续章节逐步收网已成熟的伏笔，保持主线清爽。"),
    _reg("line_overdue", "warning", "线索已逾期（target_ch 小于已定稿章数，仍未收束）",
         "在当章或下一章 beats 线动作栏安排回收/回响（resolve/remind），或正式顺延 target_ch 并写明理由。"),
    _reg("stage0_onboarding", "info", "新书 Stage 0 待办：模板槽位未填（暂不阻断，开写后恢复硬闸门）",
         "按 Stage 0 流程填实 bible/characters/outlines 中的 {{slot:}} 后，check 自动转绿。"),
    _reg("longline_quota_exceeded", "warning", "跨卷长线伏笔超出上限",
         "跨卷长线伏笔超出上限，建议精简或收束部分跨卷暗线。"),
    # ---- 细纲（beats）----
    _reg("beats_fm_extra_keys", "error", "beats front-matter 含非标准字段",
         "移除 beats 文件 front-matter 中的非标准字段。"),
    _reg("beats_missing_form", "error", "beats front-matter 缺少 form 章型字段",
         "在 beats 细纲的 front-matter 中补充 form 字段（如 form: 危机建构 / 生死博弈等）。"),
    _reg("beats_form_repeat_without_reason", "error", "连续同章型且未说明理由（读者疲劳风险）",
         "更改当章 form 章型，避免连续同章型疲劳；若确需连续，需在 front-matter 补充 form_reason 说明原因。"),
    _reg("beats_scene_abstract", "warning", "细纲场景描述假大空（缺具体动作/对白/冲突）",
         "细纲中包含假大空短语，请用具体的动作、对白或冲突置换抽象描述。"),
    _reg("style_notes_copy", "warning", "style_notes 疑似复制模板文本",
         "针对本章特色编写独有的 style_notes，避免完全复制模板文本。"),
    _reg("acceptance_empty_criterion", "warning", "验收标准是空判词（无具体事实信息点）",
         "细纲验收标准（acceptance）必须包含具体的剧情动作或事实信息点，避免假大空。"),
    _reg("form_share_over_limit", "warning", "单一章型全书占比超限（>40%；统计自该卷第 5 章起，小样本不计数）",
         "该章型在全书中占比超过 40%（≥5 章样本才参与统计），建议在后续章节丰富其他类型的叙事章型。"),
    _reg("final_drift", "warning", "已封存章节的 final 定稿在 sync 后被改动（内容哈希漂移）",
         "final 是事实唯一源头但状态台账已按旧版封存：有意修订请走提案修订通道（synopsis/timeline）后重跑 sync 重封，"
         "无意改动请用 snapshot rollback 恢复到封存时点。"),
    _reg("high_tension_fatigue", "warning", "连续高压章型导致读者情绪疲劳",
         "连续高压章型导致情绪疲劳，下一章建议安排松弛缓冲型章型。"),
    _reg("tension_flatline", "warning", "连续低张力章节（情绪平淡）",
         "连续低张力章节，下一章建议引入突发危机或外部强冲突打破平淡。"),
    _reg("tension_burnout", "warning", "连续极高张力章节（读者紧绷疲劳）",
         "连续极高张力章节，下一章建议安排战后清点或战利品兑现，让读者情绪适度舒缓释放。"),
    _reg("protagonist_pov_drift", "warning", "主角视角失焦（出场比重/核心动作弱）",
         "主角视角失焦，下一章强化主角出场比重与核心破局动作。"),
    # ---- 世界圣经版本 ----
    _reg("bible_drift", "info", "世界圣经（project_bible.md）自上次封存后发生改动",
         "有意修订则忽略本提示；涉及世界规则/战力标尺的修订建议在后续 beats 注明适用范围，回溯旧章时对照 state/bible_log.jsonl。"),
    _reg("ledger_pool_undeclared", "error", "流水引用了未声明的资源池键（账本无此池）",
         "先建池再记流水：本章合法池键名见 beats 的「💰 资源池与 ID 水位线」小节，"
         "流水 pool 必须逐字等于其中一个键；确需新池请在提案 ledger.pools 里声明"
         "（name/unit/initial 三项必填，严禁写 current）。"),
    _reg("locked_entry_id_reuse", "error", "提案复用既有 LOCK ID 改写不可逆事实（静默改史被拦）",
         "不可逆事实禁止就地覆写：改写历史请用 action=\"retire\" 留痕后另立新 ID；"
         "同 ID 同事实属幂等重放会自动跳过；确认要就地覆写请在该条目显式加 \"overwrite\": true。"),
    _reg("cognition_entry_id_reuse", "error", "提案复用既有 COG ID 改写他人/旧认知（静默覆盖被拦）",
         "认知修正请另立新 COG ID 保留认知演进链（或直接省略 id 让引擎自动编号）；"
         "换角色归属一律拒绝；确认要就地覆写请在该条目显式加 \"overwrite\": true。"),
    # ---- 不可逆事实台账 ----
    _reg("locked_injection_missing", "error", "beats 任务书缺少不可逆台账注入小节（防吃书硬闸门）",
         "运行 python studio.py beats new 重新生成细纲脚手架，或手动在 beats 正文中补充「🔒 不可逆事实台账」小节。"),
    _reg("locked_quota_exceeded", "warning", "不可逆事实超出 15 条配额（防上下文膨胀）",
         "不可逆事实台账条目已超 15 条配额，请通过提案使用 action=retire 淘汰已履行的旧承诺或合并次要条目。"),
    _reg("locked_life_status_conflict", "error", "locked 死亡事实与实体 life_status 矛盾",
         "locked 声明了角色死亡，但 entities 中该角色的 life_status 不是 deceased（或相反）；请核对两者一致性。"),
    # ---- 主线里程碑与支线健康度 ----
    _reg("milestone_overdue", "warning", "主线里程碑目标章节已过但仍未达成（pending）",
         "核查主线里程碑进展；若已完成请在提案更新 status=achieved，若已调整大纲请更新 target_ch。"),
    _reg("subplot_stall", "info", "支线伏笔超过 15 章未有任何推进/提醒",
         "该伏笔/误解已连续 15 章未触碰，建议在后续章节安排提醒（remind_ch）或回收（resolve_ch），防主线跑焦。"),
    # ---- 定稿字数出带（config guide 承诺的字数闸门）----
    _reg("word_band_deviation", "warning", "定稿中文字数落在 project.json.words_target 目标带之外（20% 容差内）",
         "定稿字数出带属可接受偏移：需要严格达标请让 Stylist 在 Stage 3B 增删内容，"
         "或按本书实际节奏用 python studio.py config set words_target --merge '[下限, 上限]' 校准目标带。"),
    _reg("word_band_breach", "warning", "定稿中文字数偏离目标带超过 20% 容差（严重出带）",
         "严重出带会影响读者节奏预期：请让 Stylist 回 Stage 3B 补足/删减到目标带内，"
         "或确认目标带本身过时后用 config set words_target 校准。字数口径＝中文字符数（与 evidence 一致）。"),
    _reg("state_offline_edit", "warning", "state 八表在上次封存后被离线改动（绕过提案写入口）",
         "state/*.json 的法定写入口是提案（sync 合并）：请核对该表改动来源，"
         "属手改请改走提案通道重跑 sync；属有意修订则重跑 sync 重新盖章消除提示，"
         "或 snapshot rollback 回到封存时点。"),
    # ---- proposal verify / sync 前置建议电池（advisory battery）----
    _reg("quote_missing", "warning", "提案条目缺 quote 原文引证（无法回证到定稿）",
         "提案的事实条目请补 quote 字段，逐字摘录 final 定稿原句（引擎按引证回校，缺证视为不可核验）。"),
    _reg("quote_none", "warning", "提案写了 quote 但内容为空或占位",
         "把 quote 填成 final 定稿中的真实原句，不要用「无」或空串占位。"),
    _reg("title_mismatch", "warning", "提案 title 与细纲/上一章承接的章标题不一致",
         "核对 beats 与提案的 title 是否同一章口径；有意改标题请同步更新 beats front-matter。"),
    _reg("title_absent", "info", "提案未提供 title（引擎将沿用既有章标题）",
         "如需改标题请在提案补 title；沿用原标题可忽略本提示。"),
    _reg("beats_overlap", "warning", "提案 synopsis/正文与 beats 细纲措辞高度重叠（疑似抄任务书）",
         "synopsis 应记录本章实际发生的事实，而不是复制 beats 任务书原句；请改写为成稿事实陈述。"),
    _reg("due_line_unhandled", "warning", "本章到期线索在提案中没有对应动作",
         "到期线必须给出处置：在提案 lines 里写 advance/remind/resolve，或在 beats 线动作栏写明顺延理由。"),
    _reg("candidate_new_entity", "info", "定稿中出现疑似新专名，但未在 entities 建卡",
         "若确为新实体请在提案 entities 建卡（含 type/summary）；若是误报可忽略，"
         "或在 state/entities.json 用 aliases 归并到既有实体，避免实体碎片化。"),
    _reg("critical_mutation", "warning", "提案触发了关键字段的重大变更（如生死/位阶/归属）",
         "关键状态变更请确认与 beats「预期演变声明」一致，并同步核对 locked 台账与称谓矩阵。"),
    _reg("state_watch_hit", "info", "提案触碰了受监控的状态字段（watch 名单命中）",
         "属知情提示：确认该字段变更是本章剧情本意即可；误改请修正提案后重跑 proposal verify。"),
    _reg("amount_unsupported", "warning", "提案金额变动在定稿中找不到对应引证",
         "账目流水必须能回证到正文：补 quote 原句，或删掉这笔无出处的流水。"),
    _reg("amount_by_quote", "info", "金额变动由引证原句推得（引擎按原句读数）",
         "属知情提示：核对引擎从原句读出的数额与提案 delta 是否一致（中文数字易被读成多笔）。"),
    _reg("mention_not_present", "info", "正文提及的实体未列入 present_characters",
         "若该实体确实在场请补进 present_characters；仅被提及/回忆则忽略本提示。"),
    _reg("present_unmentioned", "warning", "present_characters 声明在场的角色在正文中一次都没出现",
         "在场名单必须与正文一致：删掉未出场的角色，或在正文补上其在场动作。"),
    _reg("present_undeclared", "info", "正文有台词/动作的角色未声明在场",
         "把该角色补进 present_characters（在场是称谓对校与 POV 判定的输入）。"),
    _reg("power_level_shift", "info", "提案改动了实体位阶/战力标尺",
         "位阶变更请对齐 bible 战力标尺与 locked 台账，防止战力通胀。"),
    _reg("aftermath_opening_miss", "info", "上一章章末刀口在本章开头未被承接",
         "本章开头建议先承接上章物理刀口的余波，再展开新事件（读者连续性）。"),
    _reg("entities_unreadable", "warning", "entities 状态不可读，提案建议电池相关项已跳过",
         "检查 state/entities.json 的 JSON 语法并修复后重跑 proposal verify。"),
    _reg("lines_unreadable", "warning", "lines 状态不可读，线索相关建议项已跳过",
         "检查 state/lines.json 的 JSON 语法并修复后重跑 proposal verify。"),
    _reg("ledger_unreadable", "warning", "ledger 状态不可读，账目建议项已跳过",
         "检查 state/ledger.json 的 JSON 语法并修复，或运行 python studio.py ledger recompute。"),
)}

LEVELS = ("error", "warning", "info")


def get(code: str) -> ErrCode | None:
    return REGISTRY.get(code)


def describe(code: str) -> ErrCode:
    """未注册码返回兜底条目（绝不抛，保证消费方永远拿得到可展示数据）。"""
    return REGISTRY.get(code) or ErrCode(
        code=code, level="error", description=f"未注册错误码: {code}", remedy="")


def as_list() -> list[dict]:
    """按 level 分组排序的注册表列表（CLI --json 输出契约）。"""
    order = {lv: i for i, lv in enumerate(LEVELS)}
    return [{"code": c.code, "level": c.level, "description": c.description,
             "remedy": c.remedy}
            for c in sorted(REGISTRY.values(), key=lambda c: (order[c.level], c.code))]
