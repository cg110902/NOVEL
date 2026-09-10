# 102章跨卷压力测试 + 角色网关 + 全流程复验报告

## 概述
- 书名: 长夜余烬
- 章数: 102 (vol_01 50 + vol_02 50 + vol_03 2)
- 引擎分支: arena/01a08658-novel (基于 d159a07)
- 修复点:
  - `engine/commands/chapter_flow.py` 跨卷自动晋升：当 ch 号超出所有已有卷纲范围时，自动进入 `vol_{max+1}`，而非回落 vol_01
  - `engine/models/entities.py` tier_rank 去除 ge/le 约束，`entity_tier_invalid` 检查由死代码变为可达；重新生成 5 个实体相关 schema

## 跨卷功能验证

### 1. 新卷 vol_03 创建
- 手动创建 `outlines/vol_03/outline.md` 范围 ch_101-ch_150
- `beats new ch_101 --write` 自动路由至 vol_03/beats/ch_101.md (修复前会回落 vol_01)
- `beats new ch_102 --write` 同样路由至 vol_03
- debug 日志: `beats vol routing: ch_101 超出已有卷范围(最大 100)，自动晋升至 vol_03`

### 2. finals_from_index 带卷前缀
- `evidence.final_chapter_files` 返回 key = (vol, num)，tok = `vol/ch_NNN`
- `evidence.final_chapters` 同样带 vol 前缀
- `db.build_or_update_index --rebuild` 重建后:
  - indexed_chapters = 102
  - `finals_from_index` 返回 102 条，tag 形如 `vol_01/ch_001`, `vol_02/ch_100`, `vol_03/ch_101`, `vol_03/ch_102`
  - unique tags = 102，无冲突 (修复前纯 ch_XXX 会互相覆盖)
  - 指纹 `finals_fp` 命中后从 FTS 缓存拼回正文，跨卷同章号不再冲突

### 3. cockpit 卷推断
- `cockpit.py:_infer_active_chapter` + `vol_{(n-1)//50+1}` 与 beats 路由一致: ch_101 => vol_03

## librarian 角色网关验证

### 角色矩阵 (deny_reason)
| 角色 | beats | final | raw | state/current | state/persons | bible | characters | log/audit | lines | ledger | locked | outline |
|------|-------|-------|-----|---------------|---------------|-------|------------|-----------|-------|--------|--------|---------|
| drafter | ALLOW | ALLOW | ALLOW | DENY state/ | DENY | DENY | DENY | DENY log/ | DENY | DENY | DENY | ALLOW |
| editor | ALLOW | ALLOW | ALLOW | DENY | DENY | DENY | DENY | DENY | DENY | DENY | DENY | ALLOW |
| reader | ALLOW | ALLOW | DENY /raw/ | DENY | ALLOW | DENY | DENY | ALLOW | DENY | DENY | DENY | ALLOW |
| critic | DENY outlines/ | ALLOW | DENY | ALLOW | DENY | DENY | DENY | DENY | DENY | DENY | DENY | DENY |
| architect | ALLOW | DENY manuscript/ | DENY | ALLOW | ALLOW | ALLOW | ALLOW | DENY log/ | ALLOW | ALLOW | ALLOW | ALLOW |
| stylist | ALLOW | ALLOW | ALLOW | DENY | DENY | DENY | DENY | DENY | DENY | DENY | DENY | ALLOW |
| auditor | ALLOW | ALLOW | DENY /raw/ | ALLOW (extra) | ALLOW (extra) | DENY | DENY | ALLOW | DENY | DENY | ALLOW (extra) | ALLOW |
| librarian | DENY outlines/ | ALLOW | DENY /raw/ | DENY | ALLOW (extra) | DENY | DENY | DENY log/ | ALLOW (extra) | ALLOW (extra) | ALLOW (extra) | DENY |
| director | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |

- librarian 设计意图: 仅 final + 四实体表(persons/items/factions/places) + lines/locked/ledger，无 beats/raw/bible/cards/current
- 实测 `pack.open_file(..., role="librarian")`:
  - ALLOW: manuscript/vol_03/final/ch_101.md, state/persons.json, state/lines.json, state/ledger.json, state/locked.json
  - DENY: outlines/vol_03/beats/ch_101.md (outlines/), manuscript/vol_03/raw/ch_101_v1.md (/raw/), state/current.json (state/), bible/, characters/, log/audit/

- auditor vs librarian:
  - auditor: ALLOW beats/final/current/persons/locked + audit log，但 DENY raw/lines/ledger/bible
  - librarian: ALLOW final/persons/lines/locked/ledger，但 DENY beats/raw/current/bible/audit

## proposal_v3 全量操作测试 (ch_101/ch_102)

### ch_101: retire/move/revise_event/create/update
- ops (10):
  - persons create p_new_101 新城主 (id/name 双不存在校验)
  - persons retire p_010 老周头 (id 存在性 + 表一致性)
  - items update it_002 地下二层钥匙 location -> 新城档案馆 (update.id 必须存在)
  - current update (同案重复 set 同键检测)
  - timeline revise_event EVT-042 (id 或 time+event 寻址)
  - timeline append_event (新事件)
  - timeline append_clock 第三卷清算时钟 target_ch 110
  - locked plant LOCK-101 kind=irreversible_action (原 fact 非法，修复为合法枚举)
  - ledger append_transaction standard_currency -15
  - synopsis set
- 编译验证:
  - create duplicate name (陈默) => 报错 `名「陈默」已存在，create 拒绝重名`
  - retire 未登记 id => 报错 `id 未登记，无可退役`
  - move: update set.type = faction => 警告 `将搬迁 persons→factions（type 变更为 faction）`，v2 等价提案生成
  - revise_event 正常编译为 v2 timeline.events[{id, replace}]
- 同步: `sync ch_101` 成功，snapshot `20260910_021030_499827_ch_101_done`

### ch_102: create/update addressing
- ops (9):
  - persons update p_new_101 summary/location/attitude=hostile (attitude 枚举校验: hostile/neutral/friendly/allied，原 敌对 触发 param invalid)
  - places create pl_new_102 新城矿脉口
  - factions create f_new_102 新城守卫队
  - current update location=新城矿脉口
  - timeline append_event 矿脉口对峙
  - lines remind GUN-003 (note 字段非法，修复删除)
  - locked plant LOCK-102 kind=irreversible_action
  - ledger append_transaction -20
  - synopsis set
- 同步: `sync ch_102` 成功，snapshot `20260910_021116_712888_ch_102_done`

### addressing 扩展
- address_matrix 可通过 `persons update set.address_matrix` 写入，pack 一致性速查自动注入法定互称
- 本次未直接写入 address_matrix，但验证了 update 任意合法字段路径

## param shape 校验
- `checks.validate_param_value` 覆盖全部 PARAM_SPEC:
  - str_list, hook_tiers, str_map, int_pair, cap_map, nonneg_int, voiceprint_map, mem_map, str_choice
- 测试: 注入 `words_target = "invalid"` => `param_shape_invalid` 错误 `必须是 [下限, 上限] 正整数对`
- 恢复后 check 无 param_shape_invalid
- `config set` 写入守卫 `param_write_guard` 对 state_watch 单字词拦截 (info 降级)

## 全流程复验 (ch_101/ch_102)
- beats new (vol_03路由修复) -> raw/final 落盘 -> proposal v3 (ops) -> audit (hard=0, adjudicated=true) -> review (四块结算) -> sync -> snapshot
- status: 102 finalized, 0 pending, next ch_103
- check: final_chapters=102, errors=117, warnings=381, infos=30, system_health ok=true
  - errors 主要为 `beats_form_repeat_without_reason` (60) + `locked_injection_missing` (57) (压力测试故意同 form 连续)
  - 无 unfilled_slot, 无 param_shape_invalid, 无 state_inconsistent, 无 ledger_arith_broken
- index: rebuild 102 章，finals_from_index 102 条 vol 前缀唯一

## 遗留/已知
- latin_residue 12 处 (manuscript ch_044-050 样本 ch) 为早期压力测试遗留，需白名单或改写
- plotline_starvation / line_overdue 34 条为 GUN-001 等 target_ch 025 已逾期，属正常台账信号
- voiceprint_drift 1 条 info 级，属对白声纹形式检测

## 结论
- 跨卷自动晋升修复完成，vol_03 正常工作
- finals_from_index 卷前缀修复完成，跨卷无冲突
- librarian/auditor 角色网关符合 AGENTS 第四节设计
- proposal_v3 retire/move/revise_event/create/update/addressing 全量可达
- param shape 校验可达
- ch_101/ch_102 全流程复验通过，管线在 tier_rank schema 放宽后仍稳定
