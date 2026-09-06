# QA 报告：Novel Studio（engine/ 全量体检）

> 范围：`cg110902/NOVEL`（V3.1.0 基线 `4c001ae` 之上的 QA 分支 `arena/01a074b4-novel`）
> 日期：2026-09-06 ｜ 结论：**通过**。门禁级缺陷已全部修复并有回归测试兜底；压力/规模/自愈/CLI 契约四轮测试全绿；全量 pytest **131 passed**。
> 可复现资产：`qa/scripts/`（生成/压测/回归脚本）、`qa/evidence/`（原始报告行）。

---

## 1. 结论摘要

| 维度 | 结果 |
|---|---|
| 全量 pytest（8 模块 2580 行） | **131 passed**（226.5s，2026-09-06 复跑） |
| 修复批次 | 相对基线单一批次 `efb4df0`（+702/−130，8 文件），含 4 组修复 + 2 个测试文件新增 |
| 压力书（26 章真实闸门链） | 26/26 sync 应用，`check` **E0/W0**，22 条命令总 25.3s 全 rc0 |
| 规模炮台（60 章 ≈2.3× 数据） | 耗时 ≈1.8×（亚线性），实体×线交叉扫描无热点，零崩溃 |
| 自愈矩阵（3 类故障注入） | `ledger recompute`/`snapshot rollback`+processed 重放均按预期自愈，无残留错误 |
| CLI 契约回归（21 路径） | 21/21 绿（含错误路径优雅降级），JSON 信封契约成立 |
| 精读复查（pack.py / evidence.py 收尾） | 无新缺陷；审计过的模块均"只出数、零裁决"边界自洽 |

## 2. 修复清单（相对 V3.1 基线，commit `efb4df0`）

### 2.1 audit 探针精度（engine/audit.py）
1. 死者登场探针：豁免"死亡叙述"行（追悼/回忆/验尸语境不再误报死者在场）。
2. 误会线探针：`parties` 以分隔符拆全名后逐名比对（不再因整串不匹配漏报）。
3. 金额探针：改读账本池 `current`/`initial`（原读不存在的 `balance` 键，恒空）。
4. 秘密泄露说话人解析：先对已登记实体规范名/别名，再判泄露（修"说话人是实体别名时误报/漏报"）。

### 2.2 CLI `--json` 信封净化（book_setup / chapter_flow / simulate / state_sync）
- `config set/unset`、`snapshot create/rollback`、`cmd_state`、`cmd_evidence`、`cmd_critic`、`cmd_ledger recompute/pool`、`pack`、`beats`、`review`、`audit`、`simulate impact`：**每条错误路径都输出 JSON 信封**（error/提示入 payload），文本模式与退出码不变；`--json` 下 beats 规范化提示改走 stderr，stdout 纯净可 `json.loads`。

### 2.3 state.apply_proposal 合并闸门（engine/state.py）
- 提案内重复 ledger 行 → warn + skip（杜绝静默双重入账）。
- 崩溃重放幂等去重。
- 实体 type 跨界翻转 → advisory 警告（不拒绝）。
- cognition 空条目 / 对未知实体 retire → warn + skip。

### 2.4 回归与模糊测试固化（tests/）
- `test_consistency_fault_injections.py`：审计回归 10–17 + 早期全系列（+261 行）。
- `test_cli_contracts.py`：CLI JSON 信封契约（+124 行）。
- 55 例确定性变异电池：无崩溃；拒收 → state 字节级不变；接收 → verify_state 干净；同操作/同内容重放去重。

## 3. 精读覆盖与结论

按"是否写状态/是否进对话上下文"分层的精读策略（与主控确认过的口径）：

| 模块 | 方式 | 结论 |
|---|---|---|
| `state.py`（状态机核心） | 深读 | 合并/回滚/重放语义一致；快照不含 final 正文为**设计**（正文经 raw 手改/文件级恢复） |
| `pack.py`（804 行） | 全精读 | P0 恒给/P1 别名触发/P2 预算裁剪（仅裁冷层、硬上限告警）；`--open` 角色禁读网关按 AGENTS 第四节逐角色落地；`export` 卷排序/版本择优正确 |
| `evidence.py`（1373 行） | 全精读 | recall/mentions/gaps/candidates/prev/style/dup/ask/pov/names 全链"只出数、零裁决"；别名→规范名反查（P2-3）、知情圈两档（P1-3/P17）、金额 min4+max4 保序（P1-2）等修正自洽 |
| audit / merge 相关 | 逐处精读（修复时） | 见 §2 |
| 其余（graph/dashboard/critic/export/…） | 黑盒 + 压力 + 契约 | 只产文件不写状态，风险低，测试覆盖充分 |

**收尾精读（pack.py 560–804、evidence.py 全部未读段）未发现新缺陷。**

## 4. 测试矩阵（本分支全量）

### 4.1 压力书（26 章全真闸门）
`qa/scripts/build_pressure_book.py` 构造 26 章完整提案链（实体 14+ 别名、GUN/KNO/MIS 三线、双池流水、锁定事实、cognition、时钟/里程碑、timeline revise），**每章状态推进都走 inbox → sync 真实闸门**；beats 注入 🔒 不可逆台账与字数模板后 `check` 达 E0/W0。
原始证据：`qa/evidence/scale_report.jsonl`（前 22 行 = pb_book 扫描）。

### 4.2 规模炮台（26 → 60 → 100 章）
100 章扩展：`qa/scripts/extend_scale_book.py` 生成 ch_061–100（仅 beats/raw/final，无新
proposal），`qa/scripts/scale_pb100.py` 扫描 27 条命令（原始行见 `qa/evidence/scale_report.jsonl`）。

| 命令 | 26 章 | 60 章 | 100 章 |
|---|---|---|---|
| evidence all | 4.08s | 7.51s | 11.05s |
| evidence style | — | 7.12s | 10.66s |
| evidence names | — | — | 10.04s |
| index / index --rebuild | 1.47s | 1.91s | 1.96s / 2.58s |
| audit / pack / check / recall / pov / ask / cockpit / graph / dashboard / export / milestone / critic / checkpoint / simulate / snapshot | ≤1.6s | ≤1.61s | ≤1.56s |

27/27 全 rc0、零崩溃、零坏 JSON、总耗时 58.7s；数据量 3.85×（26→100 章），
全书级扫描耗时仅 ≈2.7×（近线性偏亚线性），**无交叉平方热点**。
100 章书 `check` 仍 **E0**（唯一 W = milestone_overdue，系合成书 state 停在 ch_026 的假象，
非规模问题；40 个新章全部通过 form 重复/同款检查门禁）。
进程内注射（此前阶段）：实体 14→164（mention 扫描 0.020→0.054s）、+300 条线
（gaps 0.012s）——无交叉平方热点。

### 4.3 自愈链路放大（故障注入 × 修复处方闭环）
1. final 漂移 → `snapshot rollback NAME` + processed 16 章重放（幂等全 rc0）→ E0（残余 W 仅 final_drift，属设计边界：正文不进快照）。
2. 池 current/balance_after 手改错乱（E3）→ `ledger recompute` → E0。
3. 删 `locked/cognition.json`（E1）→ `snapshot rollback` → 文件恢复，E0。

### 4.4 CLI 契约回归（21 路径，2026-09-06 最新）
`qa/scripts/cli_regress.py`（原始报告：`qa/evidence/cli_regress_report.jsonl`）：
recall（默认/ch_013/ch_999）、simulate impact（kill/reveal/未知实体）、simulate branch --write、export --txt/--views、dashboard、critic（默认/ch_010/--write/ch_ABC 错误）、checkpoint（默认/ch_010/ch_999）、index（sync/--rebuild）、errcodes --json、help --json → **21/21**：
- 成功路径 rc=0 + JSON 信封 + 产物落盘校验（export txt 26 章 233KB、dashboard.html、log/branches、log/critic）；
- 错误路径：未知实体 kill → rc0 + `unknown` 全空降级（不崩溃不伪造）；非法章号 → rc=2 usage + JSON 信封；ch_999 属既定哨兵语义；
- 回归后 `check` 复跑仍 E0/W0。

## 5. 已知设计行为（有意为之，记录不改）
- 跨章流水拒收（章号 ≠ 当前推进章）；既有池 `initial` 禁改、池 `current` 禁声明（只能流水推导/`ledger recompute`）。
- ledger 重放与提案内重复行 → warn + skip；状态快照不含 final 正文；final 内容恢复需文件级操作。
- ch_999 哨兵、断连图、cockpit 缺 beats 推断等均有既定语义。
- argparse 用法错误 = usage 文本，但 code==2 且 crashed==False（契约已测试固化）。
- `降到|降到` 正则存在可读性问题（行为正确）。
- evidence/recall/pov/names 等只读命令"未命中 = 合法事实，零裁决"。

## 6. 运行指引
```bash
# 全量测试（约 4 分钟）
cd /home/user/NOVEL && PYTHONUTF8=1 NOVEL_STUDIO_WORKSPACE_ROOT=/tmp/qa_root \
  .venv-novel/bin/python -m pytest tests/ -q -p no:cacheprovider

# 复现 CLI 契约回归
PYTHONUTF8=1 .venv-novel/bin/python qa/scripts/cli_regress.py --write

# 复现压力书构建（产物在 /tmp/qa_root/pb_book；注意提案含时间戳操作 id）
PYTHONUTF8=1 NOVEL_STUDIO_WORKSPACE_ROOT=/tmp/qa_root .venv-novel/bin/python \
  qa/scripts/build_pressure_book.py
```
引擎调用惯例：`studio.py <cmd> -w <书目录> --json`（详见各命令 `--help`）。

## 7. 环境注意事项（工程教训）
- 本沙箱曾整体重克隆：git 本地历史与 `/tmp` QA 区被清空，仅工作树改动幸存 → 全程坚持"每批 commit + push origin arena/01a074b4-novel"；本报告与 `qa/` 资产已入仓以防再失。
- venv 重建配方：`python3.11 -m venv .venv-novel` + 依赖（pydantic 2.13.5 / jieba / networkx / rich / rapidfuzz / pytest）。
- 时间测量用 `resource.getrusage(RUSAGE_CHILDREN)`（`/usr/bin/time` 不存在）。

---

## 8. 终局更新（合并 main 前的最后一次全面复核）

> 本节为追加记录，不改动上文任何历史结论；上文"131 passed"等数字以本节终态为准。

### 8.1 合并到 main 的最终提交链

基线 `4c001ae` 之上共 8 个提交（arena 分支）：

| commit | 内容 |
|---|---|
| `efb4df0` | QA 硬化批次（见 §2 修复清单） |
| `f18f20f` | 本报告 + qa/ 可复现资产入仓 |
| `54ba357` | 60→100 章规模复核（27/27 rc0，§4.2 三点计时表） |
| `4ad5d6d` | locked 门禁对齐 7-kind 枚举；consequences 废弃分区落盘时显式告警（原静默丢弃） |
| `8f3b840` | 文档 ↔ 代码契约对齐：reader SKILL（cognition_delta/locked 七枚举/六大核心事实）、templates 字数相对阈值与双层告警、AGENTS 文件地图、engine README |
| `bbd4559` | （方向性失误，已被 `a2d1482` 回滚）曾给 `_gather` 加 sweep 前缀兼容 |
| `a2d1482` | 收件箱单文件制契约对齐 + evidence 多卷邻前章修复（详见 8.2/8.3） |
| 终局批 | 探针类断言 10 例 + qa/README/evidence 描述修正（详见 8.4） |

### 8.2 收件箱命名契约裁决（文档侧修正，代码仅两处提示/说明增强）

- 引擎真契约（`engine/commands/state_sync.py` 门闸 + `state.py _gather`/failed 捡回共同印证）：
  **每章在途提案仅一份、文件名恰为 `ch_XXX.json`**；"已封存章的修订并入下一章提案随 sync 合并"。
  `sweep_ch_*.json` 等第二文件既过不了 sync 门闸、也无法从 failed/ 自动捡回（捡回逻辑只在
  规范同名时触发）——属文档层发明、引擎从未支持的通道。
- 裁决：**文档统一回引擎**。librarian SKILL / AGENTS.md / director SKILL 全部改为"修补并入当章
  在途提案（4C 已落盘则读回合并），封存章修订并入下一章提案"，并显式声明非规范命名会被忽略。
- 引擎侧配合（小改）：`state_sync` 的非规范命名扫描从"文件名前缀猜"改为解析 inbox 内 *.json
  的 `chapter` 字段点名同章异物——`sweep_ch_002.json` 单独出现时现在会得到明确点名提示而非
  泛泛拒收；`state.py` INBOX_README 补单文件制条款。
- 回归：`tests/test_sweep_naming_contract.py`（单独出现拒收+提示点名；与正式提案并存时静默
  忽略、绝不合并）把契约钉死，防技能侧回潮或引擎侧误放宽。

### 8.3 evidence 多卷邻前章修复（全精读 1373 行后的收尾发现）

- 旧实现按"章号减一 + 列表头/尾"找上一章：分卷各卷独立编号时 `dup ch_005` 会串卷比到
  `vol_01/ch_004`（应比 `vol_02/ch_004`）；`vol_02/ch_001` 直接判"无上一章"，跨卷续写的
  连续性丢失。
- 修复：`dup`/`prev_contrast` 一律按 (卷, 章号) 阅读序取"前一个位置"；pair 名带卷号不混淆；
  目标章 beats 尚未创建（规划期）时保留旧的"章号减一取最新卷"回退。
- 回归：`tests/test_evidence_multivol.py`（两卷夹具：同卷邻对不串卷、卷首 ch_001 的上一章 =
  前卷末章、prev_contrast 字段指纹来自正确文件）。

### 8.4 run_checks 探针类断言（form/words/drift 家族）

- 此前 checks 的 52 个探针代码只有整书级间接断言，无"注入一处 → 精确命中某 code/级别"的
  类级回归。新增 `tests/test_checks_probe_classes.py`（10 例，1.8s）：
  baseline 先验 E0，再逐例注入——`beats_fm_extra_keys`/`beats_missing_form`/
  `beats_form_repeat_without_reason`（含 form_reason 放行对照）/`words_band_crowded`（相对
  阈值 + 实质跳档不误报）/`style_notes_copy`/`word_band_breach`+`beats_words_unmet`/
  `beats_words_drift`（info 级）/`final_gap_chapters`/`encoding_replacement_chars`。
- 死键裁决（三选一定案）：`suppression_factors`/`release_trigger` **保留为白名单建议性键**——
  引擎不消费但放行（兼容存量书），templates 以注释形式呈现且明示"引擎不强制，只做合法键放行"，
  `parse_front_matter` 跳过注释行故模板自身零告警；不删白名单（存量书不破）、不引入消费逻辑
  （无真实语义需求）。
- 命令清单自检：`help --json` 由 argparse parser 动态枚举（29 顶层命令），COMMAND_HELP 29/29
  双向无漂移；STAGE_MAP 未覆盖的 status/cockpit/ask/pov/calendar/index/ledger/review/help/
  errcodes 均为工具/元命令（recipes 已含），属设计。

### 8.5 终态数字

- 全量 pytest：**146 passed**（约 4.5 分钟，`NOVEL_STUDIO_WORKSPACE_ROOT=/tmp/qa_root`）。
- 压力书 pb_book：26 章全真闸门链，check E0/W0；规模书 pb100：100 章 check E0（唯一 W 为
  合成书 milestone_overdue 假象）。
- 交付终态：本报告 + `qa/` 资产在 `arena/01a074b4-novel`，经 PR 合入 `main`。
