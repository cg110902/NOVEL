# OBJECT_MODEL — 对象层设计（v2，状态机 v6）

> 一句话：十一表仍是真值（断言层），对象层是其上的统一视图 + 派生计算。
> 若干个 Object 的实时值拼起来就是当前状态；`derived.json` 是第十二张表（纯派生缓存）。

## 1. 为什么要对象层

十一表是"台账"（断面记录），不是"对象"（身份 + 生命周期 + 行为）。
台账回答"记了什么"，对象层回答"这些记录拼起来，世界现在是什么样"。
三类消费者：Agent 装配（pack 精确查询）、机械仲裁（audit/verify 图查询）、
人类问书（ask/pov 零 Token 秒回）。

纪律：

- 对象层不存真值：registry/envelope 是内存视图；唯一落盘的是 derived（可删可重算）；
- 对象层不写断言：一切写入仍走提案通道；derive 只读十一表 + final；
- 派生节独立：单节异常只记 `stats["section_error:<节>"]`，不阻断 sync。

## 2. 对象包络（Envelope）

```python
{id, kind, status, asserted, derived, prov}
```

- `kind`：person / item / faction / place / foreshadow / misunderstanding /
  knowledge / event / clock / lock / belief / milestone（`envelope.kind_of_id` 按前缀判定）；
- `asserted`：十一表原文（LLM 断言 + 引擎合并）；
- `derived`：本对象派生值（只读）；
- `prov`：出处（since_ch / quote / op_id）。

## 3. 注册表（Registry，三键寻址）

`engine/objects/registry.py`：`build_registry(entities)` → by_id / by_name /
alias_to_name + problems（id 碰撞 / 别名多主）。
`resolve_ref(reg, ref)`：id → 法定名 → 别名，命中返回 entry，否则 None。
pack / derive / verify 统一走这里，替代散落的各写一遍的寻址逻辑。

## 4. v2 新增字段清单（全选填，全加法）

| 位置 | 字段 | 口径 | 供什么算 |
|---|---|---|---|
| current | time_day | ≥1 整数 | 天数差、时间回退判定 |
| current | pov_ref / place_ref / present_refs | 实体 id 或法定名 | pack 精确装配、在场合法性 |
| entities[]（提案分区；落盘按 kind 进四表） | injury_level / injury_desc | 0~5 + 文字 | pack 实体卡注入、recall 问二桥接 |
| entities[] | renown | 整数 | pack 实体卡注入 |
| relations[] | strength / status / since_ch | 1~5 / active/resolved / ch_NNN | 张力权重 |
| relations[].type | 未知谓词 | advisory 警告 | 拼写引导（宿敌等中文谓词合法） |
| locked[] | refs | 实体引用数组 | 记忆层精确追踪（修盲区） |
| cognition[] | truth_ref | GUN-/KNO-/EVT-/LOCK- | 认知-真相挂载判定 |
| timeline.events[] | id / participants / place / causes / consequences | EVT-编号（缺省自动分配） | 因果图、simulate 真遍历 |

修订事件：`{"id": "EVT-00X", "replace": "..."}` 按 id 修订文本；
补元数据：`{"id": "EVT-00X", "participants": [...]}`（time/event 必须与既有一致）。

## 5. 派生表 derived.json（第十二张表）

四节（`engine/objects/derive.py`，纯函数 f(十一表 + final)）：

- `line_temps[]`：{id, kind, temp: hot/warm/cold/never/closed, last_seen_ch, gap, status}，
  未闭环线源自 `memory.line_memory_map` 的 tier 映射（working→hot…），
  已闭环线逐条快照（temp=closed，不参与温度排序，供 seal/回放读"当时已闭环"）；
- `scene_violations[]`：{code, level: error/warning, msg, refs}，code ∈
  present_unregistered / present_deceased / ref_unresolved / present_refs_mismatch
  （末者= refs 解析名集合 vs present_characters 名集合双口径对账，warning）；
- `holder_orphans[]`：{item, holder, reason: unregistered/deceased}；
- `knowledge_flags[]`：{cog_id, character, truth_ref, verdict:
  aligned/contradicted/unresolved, detail}；其中 contradicted 含 B2 穿帮探针
  （belief.since_ch 早于真相 EVT 章 → detail 注明"穿帮嫌疑"）；
- `stats{}`：entities / lines_open / lines_closed / events / clocks_active /
  beliefs / locks / story_day（current.time_day，0=未声明）/
  registry_problems（注册表 id 碰撞/别名多主计数，供 cockpit 问书速查）。

写口径：sync 封存自动 seal（verify 通过后、盖章快照前）；
`state recompute` 手动重算；提案/手术刀禁写（`state set derived.*` 直接拒绝）；
check 的 state_offline_edit 跳过它；`sealed_at` 仅审计用，不参与一致性比对。

诚实注记（A3）：derived.scene_violations 与 checks 的已=在场/已故探针**逻辑不同、
互不蕴含**——前者是在场引用 × 注册表/生死的快照判定，后者是跨章重放探针；
本工程**不断言两者等价**，也不设等价性测试。derived 是"当时快照"，
checks 是"历时审计"，各归其位。

读口径：`state object <id/名/别名>` 输出对象包络（asserted 断言 +
relations/beliefs/knowledge_flags/holds/present/locks 跨表速览，`--json` 供 Agent）。

## 6. 状态机版本

v4 → v5（`migrations.MIGRATIONS[4]`）：补 derived 默认 + 存量事件按序分配 EVT 编号，
末尾沿惯例全表清洗。老书首次读取自动迁移（先快照、可回滚）。

v5 → v6（R1 拆表，`MIGRATIONS[5]`）：entities 按 kind 物理拆为
persons / items / factions / places 四表（STATE_KEYS 9→12，derived 为第十二张表）。
路由：person→persons、item→items、faction→factions、place/location→places、
other/缺省→persons；中文 人物/道具/势力/组织/地点 自动归一，未知 type 提案硬错、
迁移兜底 persons+记账。`entities.json` 改名 `entities.json.v5bak` 留档。
读兼容：`load_state("entities")` 返回四表合并视图；`save_state("entities")` 拒绝。
事件溯源：新事件按 kind 表记账；fold 遇 legacy `entities` 基线/事件时——
kind 键已存在则丢弃 stale 视图，否则按 type 切分（`state blame entities.X` 扇出四表+历史）。
pack 角色网关白名单同步为四表（reader/auditor/librarian）。

## 7. 后续路线

已完成：R0（v2 裸字段消费补齐：伤/名望→pack、strength→graph/simulate、time_day+伤势桥接→recall）、
R1（本节 §6 v5→v6 拆表）、
R4（proposal v3 寻址式提案：ops 编译到 v2 后走同一管线，语义对齐 by construction；
编译器见 engine/proposal_v3.py，op 形状见 state/inbox/README.md「v3 寻址式提案」节）、
R2（问书 2.0：ask 每条命中自带 cite{table, key, chapters[]}，章链=章戳∪blame，见 evidence.ask）、
R3（增量索引：memory 读 SQLite text 缓存，指纹新鲜才用、失配回退；增量 build 改按章内容
哈希比对（旧按章名跳过，改稿后重刷静默沿用旧文）；FTS 只当缓存不当召回器，阈值免校准）。
- （已决策不做）checks 的 alias_conflict / entity_id_duplicate 不改写走注册表：
  消息文案有测试钉住，改写收益不及兼容风险，checks 仍是身份问题的权威口径；
  pov 不注入 knowledge_flags：pov 承诺"只读推导、永不依赖 seal 缓存"，
  查挂旗请用 `state object`。
