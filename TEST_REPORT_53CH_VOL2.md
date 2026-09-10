# NOVEL Engine Extended Test — 53 Chapters + Vol_02 Cross-Volume + Full Command Coverage

Date: 2026-09-10
Branch: arena/01a08658-novel
Chapters: vol_01 50 + vol_02 3 (ch_051-053) = 53

## 1. 已修复 Bug 汇总

### Bug #1: 多卷同章号索引覆盖 (engine/db.py) — 已修复并推送
- 旧: ch_tag = f"ch_{n:03d}" 导致 vol_01/ch_001 与 vol_02/ch_001 覆盖
- 新: ch_tag = tok (vol_01/ch_001)，DISTINCT 计数正确
- 验证: 创建 vol_02/ch_001 后 indexed_chapters 54 (之前 53)，finals_from_index 54，candidates ambiguous_volumes 正确报告 ['vol_01/ch_001','vol_02/ch_001'] chosen vol_02/ch_001
- 清理后回落 53

## 2. 跨卷功能验证 (vol_02)

### 2.1 卷纲驱动
- beats new 需 outline.md 中含 "ch_051 - ch_100" 范围才识别 vol_02，否则默认 vol_01 并提示已存在
- 创建 outlines/vol_02/outline.md 后 beats new ch_051 → outlines/vol_02/beats/ch_051.md 成功

### 2.2 全流程两章 (ch_051, ch_052)
- ch_051: 
  - beats: 扬威立足，新实体 新城(pl_010)，新伏笔 GUN-051 target 75
  - final: 含跨卷呼应 余烬瓶雾气自己动 等6条必须保留
  - audit hard 0 soft 0
  - v3 ops: current/update, places/create pl_010, lines/plant GUN-051, ledger -10, synopsis/set
  - check: advisory line_quota_exceeded (27→28) 不阻断
  - sync applied 1
- ch_052:
  - beats: 探秘开箱
  - final: 新城档案馆探秘
  - place_ref 引用未登记实体 检测: "current.place_ref 引用未登记实体「新城档案馆」" → 证明对象化引用校验有效
  - 修复: 创建 pl_011 新城档案馆 + place_ref 改为 新城(已存在) → check 0 errors
  - sync applied 1, remind GUN-001 + GUN-051

### 2.3 索引与记忆跨卷
- final_chapters count 52 after ch_051-052, sorted by (vol, chapter)
- GUN-051 memory: plant_ch 51, last_seen 52, gap 0, tier working, not cold
- ask "新城": entities 2 (pl_010 新城 cite ch_051, pl_011 新城档案馆), text_hits 8
- evidence candidates ch_052: present_candidates 正确统计 新城 5, 新城档案馆 1, 陈默 3 等
- evidence prev ch_051: prev = ch_050 (vol_01), prev_tail 来自 vol_01/ch_050，证明跨卷阅读序正确
- evidence dup ch_052: adjacent pair vol_02/ch_051|vol_02/ch_052 shared_shingles 39，正确识别跨卷邻接

## 3. 角色网关 (librarian) 验证
- pack --as librarian --open state/persons.json → ok, opened state/persons.json
- pack --as librarian --open outlines/vol_02/beats/ch_051.md → forbidden, code forbidden, detail "角色「librarian」禁读 outlines/" → 正确
- pack --as reader --open outlines/... → ok (reader 允许读 beats)
- pack --as stylist --open manuscript/.../final → ok
- 证明 ROLE_ALLOW_EXTRA 与禁读清单按 AGENTS 第四节生效

## 4. 全命令覆盖测试

| 命令 | 结果 |
|------|------|
| status | 53章总览，next ch_053 |
| cockpit | JSON keys: schema, book, title, target_chapter, vol, workflow... |
| pack | P0 keys current, volume_phase, world_anchors... P1 entities 9 |
| ask | 2.0 引用链 cite{chapters, latest_op_id} 正常 |
| pov | 正常 |
| calendar | start ch_053 span 5 phase 正常 |
| evidence all/words/style/dup/names/file/candidates/prev/index | 全部正常，words total_cjk 46299, style cjk 380, dup shared_shingles 跨卷正确 |
| index --rebuild | 53 chapters, 50→53 演进 |
| audit | hard 0 soft 0 (或 amount_ledger soft) |
| reconcile vol_01 | verify_data errors 0, changelog ok, 变更2处 tier, 投影diff候选 |
| recall | kind chapter next_chapter story_day character_cognition... |
| simulate impact -e 陈默 -a kill | 警告 "致命主线崩坏风险 唯一主角"，affected_lines MIS-002/003, affected_items 地下二层钥匙/师父笔记 |
| check --bisect | first_break None rows 53 → 所有快照不变量通过 |
| check --trend | trend len 19 |
| snapshot list/create | 52 snapshots + test_snap_52 |
| ledger recompute | ok fixed [] 自洽 |
| export --txt | written export/长夜余烬.txt |
| proposal auto | 生成 skeleton，但需 filled beats 否则含 slot |
| proposal new --v3 | 空 ops 骨架 |
| beats new | vol 识别依赖 outline.md 范围 |
| critic --write | 生成 SKELETON 骨架，前情记忆来自 current 快照 |
| graph summary | nodes 63 edges 36 |
| state get | current.location = 新城档案馆 |
| config list | kind params |
| lore list | kind workspace bible_modules persons... |
| errcodes | 3 categories |
| checkpoint | chapter chapter_num current_phase all_phases... |

## 5. 发现的非Bug但需关注行为

- beats_form_repeat_without_reason 24 errors: 因测试快速复用 战后清点 表单未写 form_reason，属预期校验
- line_quota_exceeded advisory: 入库前27条/建议≤8，入库后28条，仍允许入库，符合"只报不阻断"设计
- dup 高重叠: 因每章强制保留6条相同必保句，导致相邻章 shared_shingles 39，属测试数据特性，非引擎误报
- proposal auto 对未填充 slot 的 beats 会生成含 {{slot:}} 的 skeleton，需主控先填 beats

## 6. 待测/建议

- librarian/evolver 等角色的更多禁读组合可自动化回归
- 跨卷同章号 ambiguous 处理已验证，但 UI 展示层需提示用户 chosen 卷
- 账本负余额 soft warning 在 audit 中持续，文档可明确阈值

## 7. 结论

- 核心Bug仅1个已修复
- 跨卷从 beats 识别、final 存储、索引计数、记忆、ask、candidates、prev、dup 全链路通过
- 角色网关按设计拦截
- 全命令面除 critic 需子代理改写外均可用，check bisect 证明历史快照不变量未破坏
- 53章压力下系统稳定，可继续向 vol_02 ch_100 推进
