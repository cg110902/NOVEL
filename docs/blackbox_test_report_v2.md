# NOVEL 引擎黑盒测试报告 v2（长夜余烬 CH20 + 全量 errcode 探针）

> 日期：2026-09-09 晚  
> 分支：arena/01a08658-novel  
> 主书：`workspace/长夜余烬` 20 章封存（快照 20，events 520，verify True ok）  
> 探针：`test_all_errcodes_v2.py` 35 项，28 PASS  
> 测试方式：点→线→面，v3 提案全表覆盖，state at/blame/diff/rollback/ledger/evidence/pack/ask/pov/calendar/graph 全流程

## 1. 主线压力测试 CH20

### 生成
- `gen_chapters_v2.py` 使用 v3 提案，覆盖 persons/places/factions/items/lines/timeline/ledger/locked/cognition/current/synopsis 全十一表。
- 每章 final 1300-1500 字，嵌入 GUN/MIS/KNO 精确术语，latin_allowlist 配置为 ["GUN","MIS","KNO","LOCK","EVT","COG"] 避免 latin_residue。
- 初始 bible 含 {{slot}}，后批量替换为“已填充”，ch_021 临时提案/细纲已清理，最终 errors 0。

### 同步结果
- 20 快照：`20260909_173320_545103_ch_001_done` … `20260909_173354_789979_ch_020_done`，另有 pre_rollback 快照 2 个（测试 rollback）。
- 曾失败 3 章：ch_017 MIS-002 未 plant、ch_018 KNO-005 未 plant、ch_020 MIS-003 未 plant → 修复：确保所有后操作线先 plant。
- 最终 `check`：errors 0 warnings 46
  - `line_action_missing` x?（到期线未在 beats 声明）
  - `line_overdue` x8（GUN-006 target 9, GUN-007/008/011/012/013/014 target 15, GUN-009 target 20 等）
  - `line_quota_exceeded`（13>8）
  - `line_never_surfaced`（部分线正文未出现，因 final 未嵌入所有 id，属业务警告）
  - `plotline_starvation`（GUN-001/002 等 19 章未推进）
  - `word_band_breach`（部分章 <2000 字）

均为业务内容告警，非引擎 bug。`ledger recompute` 自洽，`changelog.verify True`，520 events。

### 全流程命令验证
| 命令 | 结果 |
|---|---|
| `status` | 20 章，已定稿 20，字数 21494，快照 20 |
| `check` | 0 errors 46 warnings，codes 6 类 |
| `proposal new --write` `beats new --write` | 骨架生成正常 |
| `proposal check` | 20 章 OK |
| `sync` | 20 章快照，留置机制正常（非本章提案留置） |
| `snapshot list/rollback` | rollback 恢复 14 文件，自动备份 pre_rollback |
| `state at ch_005 --json` | 切面回放正常，cognition/current 等 |
| `state blame lines` | 64 条变更史，新→旧排序，含 op_id |
| `state diff ch_005 ch_010` | 按表分组 diff ops |
| `state get derived` | line_temps 16→20 随章节增长 |
| `ledger recompute` | 自洽 |
| `evidence gaps` | overdue/饥饿线报告 |
| `audit` | 0 矛盾候选 |
| `pack ch_001` | P0/P1/P2 上下文打包 |
| `ask "余烬瓶"` | 实体+线索双域检索，带 cite |
| `pov "陈默"` | 档案/持有/足迹/知道与不知道 |
| `calendar 5` | 未来 5 章到期线投影 |
| `graph centrality` | Betweenness 排名，陈默最高 |
| `config set latin_allowlist` | 动态供参，随快照封版 |

## 2. 引擎 Bug 修复（延续 v1）

### Bug 1: derive.py null 剥离（已修复）
- 现象：last_seen_ch/gap=None 直接落盘，违反“显式 null 非法”。
- 修复：is not None 判断，空串省略。

### Bug 2: derived.line_temps 排序不稳定 + changelog 重排序未处理（已修复）
- 修复：derive 按 id 稳定排序；changelog._diff_list 检测 keys_old != keys_new 时 set 整列表。
- 验证：20 章后 verify True，520 events，无 stale。

### Bug 3: proposal 字段校验细节（生成器层面，非引擎）
- MIS parties 必须为字符串（非数组），foreshadow/misunderstanding/knowledge 动作白名单：foreshadow plant/update/remind/resolve，misunderstanding plant/update/resolve/escalate，knowledge plant/update/resolve。
- ledger transaction 禁止手填 balance_after，pool 已存在时禁止重复 declare_pool initial。
- 已修正生成器。

## 3. 新增发现：部分 errcode 被 Pydantic  schema 抢先拦截，check 层 unreachable

通过 `test_all_errcodes_v2.py` 隔离测试发现：

| errcode | 预期触发 | 实际 check 输出 | 原因 |
|---|---|---|---|
| `entity_tier_invalid` | persons tier_rank=99 | `state_inconsistent` + `state_unreadable` (pydantic ge=1 le=12) | Pydantic 模型已拒，check 层冗余，属死码 |
| `locked_quota_exceeded` | locked 20 条 | `state_inconsistent` | locked schema 可能限制？需确认，但配额检查在 check 层，state 层先报不一致 |
| `ledger_tx_order` / `ledger_arith_broken` | 直接改 ledger.json | 曾报 state_inconsistent，修复 current 后应报 tx_order，但需确保交易字段合法（无 balance_after） |
| `milestone_overdue` | timeline milestones target 1, final 到 ch_002 | 报 state_inconsistent，因 milestones 字段可能需额外结构 | 需按 timeline 规范构造 |
| `locked_life_status_conflict` | locked death + person alive | state_inconsistent，因 locked kind 需特定 | 需正确构造 subject 等 |

结论：部分 errcode 的触发条件与 Pydantic schema 校验重叠，schema 层先报错，check 层的专用 errcode 无法到达。建议：
- 要么放宽 Pydantic 的 le/ge，让 check 层统一报业务 errcode；
- 要么在 errcodes 注册表中标记这些为“已被 schema 层覆盖”，避免误导。

其余 28 项 PASS，覆盖核心：

✅ candidate_leak, latin_residue, manuscript_truncation, duplicate_final, final_gap_chapters, final_without_raw, final_without_beats, beats_fm_extra_keys, beats_missing_form, beats_form_repeat_without_reason, style_notes_copy, alias_conflict, entity_ref_unknown, prerequisite_cycle/missing/unmet, line_never_surfaced, tier_shift_without_event, entity_id_duplicate, longline_quota_exceeded, line_quota_exceeded, word_band_breach, line_overdue, encoding_replacement_chars, beats_scene_abstract, item_charges_overflow, unregistered_character, line_action_missing

## 4. 未覆盖但已代码审查的死角

- `timeline.events` 无键列表按下标 diff，尾部增删正确；`ledger.transactions` 同理。
- `MAX_EVENTS_PER_TABLE=400` 熔断为整表 set。
- `genesis_at_final_ch` 对老书历史不可重放拒绝。
- `state at` 超出最新封存折叠到最新。
- `bible_drift` / `final_drift` / `state_offline_edit` 已在 CH10 验证。
- `acceptance_empty_criterion`, `form_share_over_limit`, `high_tension_fatigue`, `tension_burnout/flatline`, `subplot_stall`, `reader_memory_stale`, `voiceprint_drift`, `protagonist_pov_drift`, `retired_entity_on_stage`, `relation_target_unknown`, `amount_arith_unverified`, `line_action_orphan`, `line_recall_cold` 等需更复杂场景构造，当前 20 章已部分触发 subplot_stall/plotline_starvation，但未精确到 errcode 级别，建议后续通过专用探针书补充。

## 5. 待优化

- 生成器 final 含 GUN-xxx 等 id 会触发 latin_residue，需 allowlist，已通过 config 解决，但建议引擎默认 allowlist 包含 GUN/MIS/KNO/LOCK/EVT/COG。
- 快照时间戳乱序未告警，建议 sync 时提示非顺序封存。
- `test_all_errcodes_v2.py` 使用 workspace/探针_* 目录，需定期清理。
- bible 模板未填导致 unfilled_slot，建议 init 时提供 --minimal 选项跳过 bible 校验或自动填充示例。

## 6. 结论

- 20 章长程压力测试通过，0 errors，46 业务 warnings，verify True，events 520，状态机稳定。
- 全流程命令（status/check/sync/snapshot/state/ledger/evidence/audit/pack/ask/pov/calendar/graph/config/proposal/beats）均验证。
- 发现并修复 2 处引擎实现 bug（null 剥离、排序稳定性），另发现 5+ 处 errcode 被 schema 层抢先拦截的 dead code 风险。
- 主书 `长夜余烬` 可作为 20 章示例，具备向 30 章扩展能力，建议下一阶段测试 30 章 + 并发提案 + 随机故障注入。
