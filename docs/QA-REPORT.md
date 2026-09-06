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

### 4.2 规模炮台（26 → 60 章）
| 命令 | 26 章 | 60 章 |
|---|---|---|
| evidence all | 4.08s | 7.51s |
| evidence style | — | 7.12s |
| index | 1.47s | 1.91s |
| audit / pack / graph / dashboard / export / 其余 | ≤1.6s | ≤1.61s |

进程内注射：实体 14→164（mention 扫描 0.020→0.054s）、+300 条线（gaps 0.012s）——**无交叉平方热点**，结论：规模曲线近线性，无崩溃。

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
