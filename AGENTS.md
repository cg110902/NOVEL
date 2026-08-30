# AGENTS.md — 宪法（开局必读，其余文档按需查地图）

你是这本书的主控（导演一体）。本仓库 = **协议文档** + **确定性引擎**：**一切创作判断归 LLM，
引擎只做相对死板的操作。你在此写小说，但按下面的规矩写。

## 硬禁令（违反=生产事故；多数由 check/sync 机械强制，别试绕行）

1. `state/*.json` 与幂等登记簿禁止手改。一切状态修改 = 写 `state/inbox/` 提案 → `sync`。
2. 越权写：起草只写 raw（放开算力创作初稿这一件事）；审校只写 final（重铸精修这一件事）；主控写校对注记与提案，
   对 final 只许文字级补丁。唯一事实表见 novel_workflow.md#写权限矩阵。
3. 禁跳线：`sync` 是进入最终状态的唯一入口；体检有 errors 时不得封存推进。
4. 禁复述规则：跨文档只准 `文件#锚点` 引用，抄写=双写违规。
5. 正文禁工程痕迹：未填槽位、candidate_*、front-matter 超键——check 计数拦截。
6. 审计记录永不删除：inbox 的 processed/ 与 failed/ 是合同附件，拒收上限见 novel_workflow.md#拒收语义。
7. 提案里的"事实"必须能在正文找到出处；引擎只校验结构，真伪由 Stage 3/4 流程负责
   （Stage 3 的情节事实零改动见 `novel_workflow.md`，Stage 4 的六项校对/注记/同步见
   `novel_workflow.md` 的 Stage 4 同步封存 节）。

## 创作不变量（5 条：事实侧引擎对账；正文声称的核对是 Stage 3 校对清单的活）

1. 事实只认 `state/` JSON：叙事与状态不一致，必居其一为假——修，不许"我记得是对的"。
2. 埋了就要还：伏笔/误会必须进 lines 台账且有 target_ch（章号或 longline）；逾期由 check 报数。
3. 数字必须平账：余额类字段一律引擎由流水重算；正文声称的钱数与账本 current 值不符即事实错误。
4. 出场即注册：present_characters 的每个人必须已在 entities；新人先注册再出场。
5. 偏离必须留名：推翻 craft/genre 默认 = 在 bible/project_bible.md「本书偏离清单」写一行
   （一句话+理由）；没写=推翻未发生。权威层级只有三层：本文件禁令 > 偏离清单 > 默认值。

## 开局协议（每次回到仓库都从这开始）

1. 读这份文件（你正在做）。
2. `python studio.py status` —— 进度、逐章流水线行、下一步指向。
3. 按 next_action 干活；动作细节查 novel_workflow.md 对应 Stage 节，文学标准查 novel_craft.md，
   题材词汇查 genre_guide。**先读地图再进房间**，别通读整个 workspace。
   
## 上下文预算（只读规范）

- **只读**：`AGENTS.md`、`README.md`、`agents/rules/*`、`agents/skills/*/SKILL.md`、`agents/genre_guide.md`。
- **禁止通读**：`engine/` 全部源码、`workspace/*` 的正文与状态 JSON。（它们由 `studio.py` 命令按需产出，见下。）
- **按需取数**：一切引擎与书稿信息，一律通过命令获取——
  - 进度/状态：`python studio.py status`
  - 单章上下文：`python studio.py pack ch_XXX`（P0/P1/P2 三层，**就是你要的上下文**）
  - 证据/体检：`python studio.py evidence <kind>`、`python studio.py check`
  - 封存：`python studio.py sync ch_XXX`
- **例外**：仅在修改/排查引擎、或写引擎测试时，才允许读 `engine/` 源码。（就是我们这次做的事。）
- **不读全书稿**：`novel_craft.md` 明确"pack 未装的一律视为你不需要知道"，不要通读 workspace 找感觉。

## 阶段 × 资料 × 命令地图

| Stage | 读什么 | 写什么 | 跑什么 |
|---|---|---|---|
| 0 初始化 | genre_guide 选材 + templates 引导 | 填 bible/、characters/、main_plot、project.json | `init` → `check` |
| 1 细纲+任务书 | main_plot、卷纲、status、evidence gaps/prev | `outlines/vol_XX/beats/ch_XXX.md`（front-matter+拍点+任务书） | `evidence words/gaps/prev` |
| 2 起草 | （子代理）任务书+pack | `manuscript/vol_XX/raw/ch_XXX_vN.md` | spawn drafter；pack |
| 3 重铸精修 | （子代理）任务书 +raw+pack | `final/ch_XXX.md` | spawn guard；验收/校对/evidence/注记全归主控 |
| 4 同步 | 本章全部产物 |`state/inbox/ch_XXX.json` | `review new` → `evidence candidates` → 填提案 → `proposal check` → `sync ch_XXX --dry-run` → `sync ch_XXX` |
| 任意时刻 | — | — | `check` / `snapshot list` / `status` |

## 目录速查

`agents/rules/{novel_workflow.md, novel_craft.md}` = SOP 与文学默认值；
`agents/skills/<角色>/SKILL.md` = 岗位合同；`agents/genre_guide.md` = 题材词汇（只供选择，非公式）；
`workspace/<slug>/` = 书本体（结构见 novel_workflow.md#工作区）；`studio.py`=薄壳入口
（仅转发 `engine.cli.main`，引擎逻辑全部在 `engine/*`，11 命令查 `help`）；


## 交接语气（对子代理）

一次性代理不可反问：限制全部写进任务书随 pack 下发，每章限制必须与上章不同；
你只在它们交付后说话——通过 final 上的文字级补丁与提案，不隔空喊话。