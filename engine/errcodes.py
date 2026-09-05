"""错误码注册表：Novel Studio 引擎全部体检错误码的机器可读说明书。

定位：这些错误的最终消费者往往是 LLM Agent（主控拿到 `check --json` 后要自助修复），
因此每个码必须有：severity（错误/警告/提示）、description（一句话人话解释）、
remedy（可执行的修复建议）。

单一真源约定：
- `checks.DEFAULT_REMEDIES` 由本注册表派生（`_err` 的 remedy 兜底），禁止在别处再手写 remedy；
- 守卫测试：checks.py 源码中出现的每个 `_err("code"` 字面量
  必须已注册，新增错误码漏注册会当场报警。

severity 为数据驱动：按 run_checks 实际把错误码投递到 errors/warnings/infos 哪条通道归类。
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
    # ---- 提案与候选 ----
    _reg("candidate_leak", "error", "candidate_* 候选字段泄漏进正式数据",
         "将未定命名 candidate_* 替换为具体的角色名或地名。"),
    _reg("latin_residue", "warning", "中文稿正文含拉丁字母残留（起草夹带的英文词）",
         "把正文里的英文词改写成中文；若确属外文专名、品牌或缩写等合法情形，"
         "请用 python studio.py config set latin_allowlist --merge '[\"词\"]' 声明白名单。"),
    # ---- 伏笔暗线 ----
    _reg("plotline_starvation", "warning", "线索长期未推进（伏笔饥饿）",
         "该线索长期未推进，请在当章或后续章节 beats 中安排线索推进（advancement）或提及（remind）。"),
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
    _reg("line_action_missing", "warning", "细纲声明的线索动作类型缺失",
         "细纲中声明的线索动作类型缺失，请明确为 plant/advance/remind/reveal/resolve 之一。"),
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
    # ---- 节奏与字数 ----
    _reg("words_band_crowded", "info", "预计字数区间与整体规划脱节",
         "调整细纲中的预计字数区间，避免与整体规划脱节。"),
    _reg("word_band_deviation", "info", "定稿字数偏离目标字数带（轻度）",
         "字数偏离目标带，精修师 Editor 在润色时可精简冗余或扩充细节。"
         "口径说明：字数按剥离首行章题的正文计 CJK，压线章请多留 5~10 字余量。"),
    _reg("word_band_breach", "warning", "定稿字数显著偏离目标带（低于下限 85% 或高于上限 115%）",
         "定稿字数显著出带：低于下限 15% 以上请扩写核心场景（beats 硬合同口径），高于上限 15% 以上请精简冗余支线。"),
    _reg("beats_words_unmet", "warning", "定稿字数显著偏离**细纲自报**的 words 带（超出 15% 容差）",
         "细纲 front-matter 的 words 带是 Stage 1 对 Stage 2/3 的硬合同：低于下限请扩写核心场景，"
         "高于上限请精简支线；若确属自报带定错，请回 Stage 1 修订自报带并在 form_reason/验收要点写明理由。"),
    _reg("beats_words_drift", "info", "定稿字数落在细纲自报 words 带之外，但在 15% 容差内",
         "轻微出带属正常波动；若持续同向偏离，请核对自报带是否定得不合实际篇幅。"),
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
