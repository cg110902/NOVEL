# NOVEL 引擎黑盒测试报告（长夜余烬 CH10 + 探针实验室）

> 日期：2026-09-09  
> 分支：arena/01a08658-novel  
> 主书：`workspace/长夜余烬`（10 章封存，last_sync ch_010）  
> 探针书：`workspace/探针实验室`  
> 测试方式：点→线→面，跳过 editor/stylist，重点压测提案/封存/事件溯源/一致性检查

## 1. 主线压力测试（10 章）

### 生成路径
- 使用 `gen_chapters.py` 快速生成 ch_004-010 的 beats/final/raw_v1/v2/proposal/audit，beats 含合法 `form`/`style_notes` 变化，final 嵌入 GUN/MIS/KNO 精确术语，proposal 含 lines/events。
- 按序 `studio.py sync ch_00{4..10} -w workspace/长夜余烬`。
- 遇到 `lines[4] 含未知字段: name, plan`（KNO 植物非法字段）→ 修复：剥离为仅允许字段 `secret/target_ch/plant_ch/note/weight/requires/holders`。
- 同步结果：10 个快照 `20260909_143558_624180_ch_001_done` … `20260909_154639_961234_ch_010_done`，`ledger recompute` 自愈，`state at ch_009/ch_010` 可回放，`changelog verify` 最终 **True ok**（修复后）。

### 当前 check 结果（已清理 latin_residue/final_drift/state_offline_edit）
```
errors 0 warnings 13
- line_action_missing x2 (ch_009/010 到期线未在 beats 线动作栏声明)
- milestone_overdue x2 (MS-001 target 8, MS-002 target 9 仍 pending)
- word_band_breach x4 (ch_004-007 778/777/721/672 <1000)
- word_band_deviation x1 (ch_010 874)
- line_overdue x3 (GUN-007/008/009 target 9 <10)
- line_quota_exceeded x1 (10>8)
```
均为业务内容告警，非引擎 bug。

## 2. 发现并修复的引擎 Bug

### Bug 1: `engine/objects/derive.py` null 剥离缺失
- **现象**：`_derive_line_temps` 直接写入 `last_seen_ch=None` / `gap=None` / `status=""`，违反 `schema_gen` 全局规则“显式 null 非法，None 时应省略”。
- **触发**：当 line 的 last_seen_ch 为 None（从未出现）或 status 为空字符串时，落盘的 derived.json 含 null/空串，`check` 报 `param_shape_invalid` 或下游校验失败。
- **修复**：显式判断 `is not None` 再写入，`status` 为空串时省略。
- **验证**：`studio.py state recompute` 后 derived 不再含 null，`check` 无 `param_shape_invalid`。

### Bug 2: `derived.line_temps` 排序不稳定导致 `changelog.verify` 失败
- **现象**：`line_memory_map` 按 gap 降序排序，gap 随章节推进变化，派生表顺序动态变化；`changelog.diff_states` 对带键列表仅处理增删改，不处理重排序，`fold` 后顺序保留旧序，`verify` 哈希不一致。
- **触发**：主书在 ch_009 先于 ch_008 封存（时间戳乱序），gap 变化导致 line_temps 重排，`verify` 报 `derived.json 与事件流折叠结果不一致`。
- **修复**：
  1. `derive.py`：`out.sort(key=id)` + `closed.sort(key=id)`，派生层仅需稳定存储，展示层排序由 `memory.line_memory_map` 负责。
  2. `changelog.py` `_diff_list`：检测 `keys_old != keys_new`，若键集合相同仅顺序不同则直接 `set` 整列表；若增删+重排序混合则先增删 diff 再追加一次整表 `set` 以固化顺序。
- **验证**：修复后 `check_external_edit` 能自愈重排序，`verify` 在强制 external_edit 后恢复 `True ok`，`test_changelog.TestDiffFoldRoundtrip` 仍通过。

### Bug 3: `test_errcodes.py` 中 `duplicate_final` 用例构造错误（非引擎 bug，但影响测试）
- **现象**：`ch_001.md` (v0) + `ch_001_v1.md` (v1) 被视为不同版本，非重复。
- **正确构造**：`ch_001.md` + `ch_001_v0.md` 同为 v0 才触发 `duplicate_final`。
- **引擎逻辑**：正确，`common.find_chapter_files` 按版本去重，重复版本才报错。

## 3. 已验证的检查项（errcode 覆盖）

通过探针实验室 + 主书手动触发，验证 `engine/checks.py` 与 `changelog.py`、`state.py`、`memory.py` 协同：

| errcode | 触发方式 | 结果 |
|---|---|---|
| `unfilled_slot` | beats 含 `{{slot:test}}` 未填 | ✅ PASS |
| `candidate_leak` | final 含 `candidate_123` | ✅ PASS |
| `latin_residue` | final 含英文 `hello` | ✅ PASS（主书已清理） |
| `manuscript_truncation` | final 以逗号结尾 | ✅ PASS |
| `final_gap_chapters` | 仅 ch_001 + ch_003 | ✅ PASS |
| `beats_fm_extra_keys` | beats FM 含 `extra_illegal` | ✅ PASS |
| `beats_missing_form` | beats FM 缺 `form` | ✅ PASS |
| `beats_form_repeat_without_reason` | 连续两章同 `form: 生死博弈` | ✅ PASS |
| `style_notes_copy` | 连续两章同 `style_notes` | ✅ PASS |
| `alias_conflict` | persons 共享 alias `老王` | ✅ PASS |
| `entity_ref_unknown` | person faction 指向不存在势力 | ✅ PASS |
| `prerequisite_cycle` | GUN-001 requires GUN-002 且反向 | ✅ PASS |
| `ledger_tx_order` | tx 章节乱序 ch_002 在 ch_001 前 | ✅ PASS |
| `ledger_arith_broken` | pool current 与交易余额不符 | ✅ PASS（`ledger recompute` 自愈） |
| `line_never_surfaced` | GUN-001 从未在 final 出现 | ✅ PASS（精确术语搜索） |
| `tier_shift_without_event` | 人物 tier_rank 1→5 无 timeline 事件 | ✅ PASS |
| `state_offline_edit` | 手改 `state/current.json` 未走提案 | ✅ PASS（检测 + 提示重跑 sync） |
| `final_drift` | 手改 final 后哈希与 `final_hashes.json` 不一致 | ✅ PASS（检测 + 提示） |
| `duplicate_final` | 同章同版本多文件 | 需 `*_v0.md` 双文件构造，引擎逻辑正确 |
| `ledger` 幂等 | 同内容重复 plant | ✅ warning `已存在且内容一致，按幂等跳过` |
| `ledger` 重复拒绝 | 同 id 不同内容 plant | ✅ error `已存在，重复 plant 拒绝` |
| `changelog.verify` | 派生表重排序后 fold 哈希不一致 | ✅ 修复后自愈 |

未覆盖但已通过代码审查确认的逻辑死角：
- `timeline.events` 无键列表按下标 diff，尾部增删正确；
- `ledger.transactions` 同理；
- `MAX_EVENTS_PER_TABLE=400` 熔断为整表 set，防止事件爆炸；
- `genesis_at_final_ch` 对老书历史不可重放的拒绝；
- `state at` 对超出最新封存的折叠到最新封存。

## 4. 文档与实现一致性

- 文档称 `state/*.json` 法定写入口为提案，`check` 的 `state_offline_edit` 与 `changelog.check_external_edit` 分工：前者盖章篡改检测（check 消费），后者事件流自动补录（fold 追平磁盘），实现符合。
- 文档称 `derived` 不入快照、回滚不清空，实际 `CHANGELOG_FILES` 被快照放行，符合“历史是资产”。
- 文档称 `lines` 的 `requires` 支持跨线种依赖，`prerequisite_cycle` 检测覆盖，符合。
- 文档称 `final` 必须经 `raw` 修订通道，`final_without_raw` 检查存在（探针未触发但代码有）。

## 5. 待优化（非阻塞）

- `gen_chapters.py` 生成的 finals 曾含英文 token，触发 `latin_residue`，已手动清理；建议生成器内置中文校验。
- 快照时间戳乱序（ch_009 早于 ch_008）未被 `final_gap_chapters` 拦截，`check` 仅检查章节号连续性，不检查时间戳顺序；对 `state at` 仍正确（按 seq 最大），但对读者可能困惑，建议 `sync` 时提示“非顺序封存”。
- `test_errcodes.py` 的 `reset_book` 未完全重置 state，导致串扰；建议每用例使用独立临时目录 `tempfile.mkdtemp`。

## 6. 结论

- 引擎核心不变量 `fold(base, events) == 磁盘状态` 在修复排序 bug 后恢复，10 章压力测试下 `verify True`。
- 提案幂等、重复拒绝、账本自愈、离线改动检测、终稿漂移检测均按文档工作。
- 已修复 2 处实现 bug（null 剥离、排序稳定性），均有单测/黑盒验证，无回归。
- 主书 `长夜余烬` 可作为长期运行示例，10 章封存，13 条业务告警（非引擎缺陷），可继续向 20 章扩展。
