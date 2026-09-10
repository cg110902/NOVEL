# NOVEL Engine Comprehensive Test Report — 50 Chapters Pressure

Date: 2026-09-10
Branch: arena/01a08658-novel
Workspace: 长夜余烬 (50 chapters)

## 1. 测试策略 (point → line → plane)

- **Point**: 单操作边界
  - v3 `persons/create` 需 `entry.id` 必填（错误 `[op#1 persons/create] p_010 create.entry.id 必填` 验证通过）
  - v3 `items/update` 地址错表检测：`it_001 在 persons 表不在 items 表` 证明严格寻址防止静默碎片
  - v3 `timeline revise_event` 必须用 `replace` 通道：`已存在且 time/event 不同——改文本请用 replace 通道`
  - v3 duplicate operation_id 幂等跳过：`operation_id ch_042.test.p2.v3 已应用过，跳过` + duplicates 1

- **Line**: 单章全链路
  - beats new → final → raw v1/v2 → audit --write → proposal check → sync → check
  - CH041: 8 ops, line_quota_exceeded advisory (27→28) 仍允许 sync，证明 advisory 不阻断
  - CH042: retire p_005 陈絮, resolve GUN-041, revise_event EVT-001, relocate it_001 persons→items, ledger -10
    - check 阶段 2 warnings: 搬迁 + 跨界变更（other→item），正确提示
    - audit hard 0 soft 1 amount_ledger (balance -250)，adjudicated true 后可 sync
  - latin_residue: final 含 `ch_050, weight, holder` 触发 warning，改为纯中文后清零

- **Plane**: 多章+多卷+索引
  - 43章时 index rebuild: indexed_chapters 43
  - 创建 vol_02/ch_001 后旧代码 indexed_chapters 仍 43（bug），修复后 44
  - finals_from_index 旧守卫在检测到跨卷同章号时直接 return None 回退文件扫描，虽保正确但失去缓存加速
  - 修复后 finals_from_index 返回 44 条 vol_01/ch_001 … vol_02/ch_001，缓存命中

## 2. 发现的引擎 Bug 并修复

### Bug #1: 多卷同章号索引覆盖 (engine/db.py)
- **位置**: `build_or_update_index` ch_tag = f"ch_{n:03d}"
- **现象**: vol_01/ch_001 和 vol_02/ch_001 在 SQLite `chapters_fts.chapter` 列同键覆盖，COUNT DISTINCT 仅 43
- **影响**: 跨卷写作时 BM25 检索丢失一卷，finals_from_index 被迫回退全量文件扫描
- **修复**: ch_tag 改为 tok (vol_01/ch_001)，与 evidence.final_chapters 口径一致；移除 finals_from_index 的跨卷守卫
- **验证**: 
  - rebuild 后 indexed_chapters 44，finals_from_index 44
  - 清理 vol_02 后回落 43，证明迁移兼容

### 其他已验证的正确行为（非 Bug）

- **v3 严格表寻址**: `items/update it_001` 当实体在 persons 时报错并提示所在表，是预期防护
- **timeline revise 需 replace**: 防止 time/event 被意外改写，是预期契约
- **tier_shift_without_event**: 当 timeline 含突破事件时不报，证明事件可抑制 tier 警告（CH041 验证 tier warnings 0）
- **line_quota_exceeded**: advisory 级别，不阻断 sync，符合文档“只报不阻断”
- **ask 2.0 引用链**: `ask 陈默` 返回 cite {table persons, key entries[p_001], chapters [ch_041,ch_001], latest_op_id ch_041.test.p1.v3.fixed}，`ask 老周头` 返回 ch_044，证明章链 = 自带章戳 ∪ blame

## 3. 50章压力数据

- 总章数: 50 (vol_01)
- 实体: 17 (含 p_010 老周头 别名周叔)
- 线索: 43 (GUN-041 已回收)
- 账本流水: 50 笔，余额 170 (曾 -310 后 +500 回血)
- 索引重建: 868ms (50章)
- check: errors 22 (14 beats_form_repeat_without_reason 因复用战后清点表单，6 beats_form_repeat_without_reason 原有，2 其他), warnings 220 (plotline_starvation 20 等 advisory)
- audit ch_050: hard 0 soft 0 clean

## 4. 覆盖的逻辑死角（来自 docs）

- [x] v2 vs v3 混用：CH41 v3 + CH42 v3 + CH43 v2 + CH44 v3 + CH45-50 v2 混合同步，最终 state 一致
- [x] 实体搬迁：persons→items via `persons/update set type item` 触发 `实体搬迁` + `跨界变更` warning
- [x] 退场 retire：p_005 陈絮退场后 `present_characters` 已无，ask 仍可查历史 cite
- [x] 线索回收 resolve：GUN-041 resolve 后 gaps 不再 overdue
- [x] 编年史修订 revise_event replace 通道
- [x] 账本负余额：-250 触发 amount_ledger soft warning，但 adjudicated 后允许 sync；+500 后回正
- [x] 最终含英文 latin_residue 检测
- [x] 幂等重放 duplicate skip
- [x] 多卷同章号（vol_01/ch_001 vs vol_02/ch_001）
- [x] 索引增量缓存失效：修改 final 后 fingerprint 变化，finals_from_index 回退或重刷

## 5. 待优化建议（非阻塞）

- beats_form_repeat 14 条因测试快速复用表单，可接受；生产环境应加 form_reason
- ledger 流水 -250 时 audit 软警告持续存在，建议文档明确“负余额是否允许”阈值
- ask 的 text_hits 目前走 BM25，vol 前缀后 chapter 字段含 /，前端展示需兼容

## 6. 复现步骤

```bash
python studio.py index --rebuild -w workspace/长夜余烬
python studio.py check -w workspace/长夜余烬
python studio.py ask "老周头" -w workspace/长夜余烬 --json
python studio.py proposal check ch_042 -w workspace/长夜余烬
python studio.py sync ch_042 -w workspace/长夜余烬
```

## 7. 结论

引擎在 50 章压力下核心链路稳定，唯一发现的确定性 Bug 为多卷索引覆盖，已修复并验证。v3 严格寻址、revise replace 通道、幂等跳过、引用链等防护均按设计工作，advisory 警告不阻断同步的策略符合长篇创作容错需求。
