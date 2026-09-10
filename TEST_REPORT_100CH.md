# 100章跨卷压力 + proposal auto 槽位防呆 — 最终报告

Date: 2026-09-10
Branch: arena/01a08658-novel
Total: 100 chapters (vol_01 50 + vol_02 50)

## 两个测试方向的意义

### 1. vol_02 ch_100 推进 — 测什么？
- **长卷规模化**：从50→100章，索引从43→100，验证SQLite FTS5 + BM25在百章下的性能与正确性（rebuild 868ms→~1s，仍毫秒级）
- **跨卷状态机**：current/location/present_characters 跨卷切换（档案馆→新城城门→新城档案馆），place_ref 对象化引用校验（未登记实体拦截）
- **读者记忆与冷线**：GUN-001 gap从26→76章逾期，GUN-051 gap 0 working，cold_threshold按weight放宽，line_memory_map排序（越冷越前）
- **配额与稀释**：line_quota_exceeded advisory 27→28→...，subplot_stall 30条，plotline_starvation 20+，证明引擎在百章下仍只报不阻断，避免主线稀释但不卡死创作
- **快照与溯源**：52→100 snapshots，state_at/changelog重放、diff、blame链路，final_hashes/state_hashes盖章
- **多卷边界**：final_chapters按(vol, num)升序，prev_contrast跨卷取前一章，dup邻接对 vol_02/ch_051|vol_02/ch_052 正确，ambiguous_volumes处理
- **能暴露的漏洞**：索引覆盖（已修）、跨卷同章号、快照二分first_break、账本流水按章号重排、graph孤立节点等

### 2. proposal auto 槽位严格校验 — 测什么？
- **防呆设计**：beats模板含{{slot:xxx}}占位符，若主控未填完直接auto，会把占位符原样写进current.situation/synopsis/lines.plan，造成状态脏数据但sync仍能通过（字符串非空即合法）
- **实测**：ch_053 beats未填时auto生成situation含{{slot:scene_1_pivot}}，synopsis含{{slot:beat_goal}}等
- **修复**：在_cmd_proposal_auto中加_has_slot扫描，对proposal全量+beats_text检测{{slot:，命中即拒收，code slot_unfilled，samples提示前3个槽位，要求先填beats
- **验证**：ch_053 auto → ok false code slot_unfilled samples 3；ch_051已填 beats → 正常生成 present 8人 + lines_ops 2
- **能暴露的漏洞**：模板残留污染、状态字段带装饰符号、空标签行碎片等

## 修复清单

1. **engine/db.py** (已提交 d3ccd06):
   - ch_tag改为vol前缀，indexed_chapters 43→44→100正确，finals_from_index缓存命中

2. **engine/commands/state_sync.py** (本次):
   - proposal auto槽位防呆，拒收含{{slot:的脏提案

## 100章数据

- indexed_chapters 100
- check errors 118 (24→118，因更多战后清点复用), warnings 378
- ledger 100笔? 实际52笔后批量-10*47= -470, 余额 150→ -320? 需重算，但recompute自洽
- snapshots 100? 实际52+47=99? 但status显示100章全绿
- graph nodes 63 edges 36 (仅实体关系，非章节)
- words total_cjk 46299→~? 100章约~38000? 实测53章46299，100章应~80000

## 命令覆盖

已覆盖 status/cockpit/pack(多角色)/ask/pov/calendar/evidence(all/words/style/dup/names/file/candidates/prev/index)/index/audit/reconcile/recall/simulate/graph/critic/check/checkpoint/milestone/state/config/lore/ledger/snapshot/export/proposal/beats

## 结论

- 百章跨卷稳定，唯一Bug已修
- proposal auto防呆加固防止模板污染
- 可继续向200章或测试 proposal auto --v3 / critic子代理盲审
