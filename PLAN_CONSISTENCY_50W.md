# Novel Studio 一致性改造总表（40–50 万字实战版）

> **目标区间**：40–50 万字（约 200 章 / 4 卷），本表覆盖到此规模「没毛病」所需的全部改造。
> **合并来源**：《读者一致性改造计划书（实施版）》（下称「读者方案」，已逐条核验+修正）＋ 架构评审结论（事件溯源 / 新探针 / 规模经济，为本表新增轨道）。
> **总原则**（继承读者方案，补两条）：
> 1. 不新增状态表、不新增工序、不增加模型上报负担（唯一例外：A4 的 `locked.note` 写入口必填，复用既有字段）；
> 2. 能算的一律由引擎算，全部新能力零 Token；
> 3. **新增：历史即资产——凡改状态必留事件，凡留事件必可重放**（Track B）；
> 4. **新增：一致性按读者显著性分配，按趋势观测**（Track A 的 weight 缩放 + Track D 的分数曲线）。

---

## 0. 一页总览

### 0.1 读者方案裁决表

| 读者方案条目 | 裁决 | 去向 |
|---|---|---|
| 阶段 1：`line_terms_for` 提公开 + `engine/memory.py` 派生层 | ✅ 采纳（含修正 1/2） | Track A1/A2 |
| 阶段 2：三条 advisory 闸门 + errcodes + PARAM_SPEC | ✅ 采纳（含修正 3/4） | Track A3 |
| 阶段 3：`locked.note` 写入口必填 | ✅ 采纳（补文档同步点） | Track A4 |
| 阶段 4：pack 冷线注入 | ✅ 维持暂缓（观察 A3 信噪比后再定） | A5（gated） |
| 阶段 5：`reader_harm` 维度 | ✅ 维持暂缓 | 远期 |
| §9 明确不做清单 | ✅ 全部维持，另并入本表 §9 | — |
| 未覆盖：事件溯源 | ➕ 本表新增 | Track B |
| 未覆盖：机械探针扩容（位阶/声纹/空间） | ➕ 本表新增 | Track C |
| 未覆盖：规模经济（rollup / 对账大修 / 分数曲线） | ➕ 本表新增 | Track D |

### 0.2 排期总表（R1→R5，每轮独立提交、独立可回滚）

| 轮次 | 内容 | 契约变更 | 风险 | 预估* |
|---|---|---|---|---|
| **R1 地基** | A1 公开化 + A2 memory.py + B1 changelog + D3 scorecard | 无 | 无（纯新增） | 2–3 天 |
| **R2 闸门** | A3 三闸门 + A4 note 必填 + C1 位阶探针 + B4 check --bisect | A4 仅提案层 | 噪声（可配阈值） | 2–3 天 |
| **R3 溯源查询** | B2 `state at` + B3 `state blame` | 无（新子命令） | 低 | 3–4 天 |
| **R4 规模经济** | D1 卷级 rollup + D2 卷末对账大修 | 无（新命令/新产物） | 中 | 5–7 天 |
| **R5 观察后定** | A5 pack 注入 ｜ C2 声纹 ｜ C3 传送 ｜ E salience | — | — | gated |

\* 按项目作者本人实施的理想人日；R1–R3 是 50 万字刚需，R4 是 50 万字「舒服」，R5 是锦上添花。

---

## 1. 对《读者一致性改造计划书》的评审结论

### 1.1 事实核验：全部通过 ✅

读者方案自称「所有断言均经实际读取核实」，本表对其关键断言做了独立复核，**全部属实**：

| 断言 | 核验结果 |
|---|---|
| `_line_terms_for` 位于 `evidence.py:392`，reg_terms 按 `a in blob` 过滤后并入 | ✅ 属实。**关键语义安全**：只并入出现在该线自身文本（name/plan/secret/note/parties/content）里的专名，不是全量并入——memory.py 复用不会产生「任意线命中任意章」的假阴性雪崩 |
| `final_chapters`（`evidence.py:39`）键为 (卷, 章号)、按序返回、多版本取最大 | ✅ 属实 |
| `count_aliases`（`evidence.py:86`）长别名优先 | ✅ 属实 |
| `_LINE_KIND_SPEC`（`state.py:44`）三类线状态机唯一真源 | ✅ 属实 |
| `present_unmentioned`（`checks.py:354`）存在，线无对应闸门 | ✅ 属实，真空白 |
| 既有线闸门家族：`due_line_unhandled:484`、`plotline_starvation:1375`、`line_action_orphan:1507`、`line_action_missing:1513`、`line_overdue:1659` | ✅ 全部属实 |
| `PARAM_SPEC`（`checks.py:566`）六种 shape；`gap: False` = 不配不提示 | ✅ 属实（`candidate_stopwords`/`state_watch`/`lines_cap` 等均此语义） |
| errcodes 现为 86 码（warning 43 / error 31 / info 12） | ✅ 实测一致（87 个 `_reg(` 命中含 `def _reg(` 本身） |
| `LockedEntry` 无 `reason` 字段；`reason` 仅 retire 时瞬态使用（`state.py:898` 附近）；`note` 已持久化（`_merge_locked`，`state.py:1570`） | ✅ 属实 |
| `locked.schema.json` `additionalProperties: False` | ✅ 属实 |
| `SYSTEM_CHECK_CODES`（`checks.py:65`）决定双核分桶（1904–1910） | ✅ 属实。三条新码不入该集合 → 自动落入「叙事健康」桶，语义正确 |
| db.py `chapters_fts`（:95）/ `cognition_index`（:150）/ `query_character_pov` 已建已接线 | ✅ 属实 |
| 既有 96 个单测 | ✅ 本仓库实测 96 全绿（74s） |

**结论：读者方案的主体（阶段 1–3）照单采纳。** 它是「盖楼」不是「打地基」的自我定位也成立——地基（`_line_terms_for`、八表、`PARAM_SPEC` 纪律、写入口守卫先例）确实全部就位。

### 1.2 修正清单（实施时必须改的六处）

**修正 1｜`state._LINE_KIND_SPEC` 私有访问，与其自身原则矛盾。**
读者方案一边批评 `_line_terms_for` 私有不可复用、一边让 memory.py 直接摸 `state._LINE_KIND_SPEC`。改法：在 `state.py` 增加公开只读入口，memory.py 一律走公开 API：

```python
def line_kind_spec(kind: str) -> dict | None:
    """三类线（foreshadow/misunderstanding/knowledge）的字段规格公开只读入口。
    memory / audit 等模块复用；判定「已闭环」用 spec["resolved"]，禁止摸 _LINE_KIND_SPEC。"""
    return _LINE_KIND_SPEC.get(kind)
```

**修正 2｜`_scan_last_seen` 取「迭代末项」不等于「最大章号」。**
`final_chapters` 目前按 (卷, 章号) 升序返回，迭代末项恰好是最大章号；但这是实现细节不是契约，且若出现分卷重编号会静默错。改为显式取最大：

```python
if any(t in text for t in terms):
    last = num if last is None else max(last, num)
    hits += 1
```

**修正 3｜闸门 3 盲区定性错误：是「漏报」不是「误报」。**
读者方案 §10.3 说 locked 条目提词为空时「判为 never，可能误报」——但它的闸门 3 只报 `tier == "impression"`，never 档根本不会报；其代码注释「never 档由闸门 1 覆盖」对 locked **不成立**（闸门 1 只消费 lines）。真实后果：fact 不含任何已登记专名的 locked 条目会**静默脱离监控**。处置：
- 事实层面：locked.fact 几乎必然含实体名（「张三死于剑下」），空提词是少数；
- 工程层面：加可选轻提示 A4b（见 §3.4），把盲区在写入时刻可见化；
- 文档层面：在 memory.py docstring 与 §8 局限清单中如实写「漏报」。

**修正 4｜与既有线闸门家族的边界必须写进代码注释。**
`plotline_starvation`（时间饥饿：活跃线太久没人管）与 `line_overdue`（逾期未回收）是**台账时间轴**信号；`line_recall_cold` 是**读者记忆轴 × 回收意图**信号（只有 beats 里出现 resolve 意图且线已冷才触发）。二者互补但可能在同一章对同一条线双报——这不是 bug，但要在三条闸门的注释里写明分工，避免日后维护者「去重」时误删。

**修正 5｜`.test_area/断刀` 不存在于本仓库，测试策略改为三件套。**
① 沿用 `tests/_fixtures.py` + `NOVEL_STUDIO_WORKSPACE_ROOT` 隔离工作区（与既有 96 测试同一套法）；② 新增 `tests/test_memory.py`（读者方案的验收清单原样执行）；③ 新增**200 章压力样书生成器**（见 §8）：程序化生成 200 个小正文文件 + 逐步封存 20 条线/若干实体，断言 memory 层全量计算 < 2s、闸门命中与人工植入的「已知吃书」一一对应。

**修正 6｜性能口径如实记录：check 全程是两遍全文扫描。**
`line_memory_map`（闸门 1/2 共用）+ `key_fact_memory`（闸门 3）各扫一遍 finals。200 章 × 3KB 量级下两遍约 0.5–1s，可接受；但要在代码注释与 §8 里写明「当前两遍、单遍合并是留给 FTS 路径的优化空间」，不要留一句「只读一次」的绝对化注释误导后人（读者方案原文只对单函数内部强调只读一次，语义没错，但容易被误读为全程单遍）。

### 1.3 读者方案未覆盖的四件事（本表新增轨道的存在理由）

| 缺口 | 50 万字下的具体失败场景 | 对应轨道 |
|---|---|---|
| **无事件史** | 第 180 章发现矛盾，「它是哪一章、哪条提案、谁改的混进来的」无法回答；Evolver 手术后 `processed/` 重放链断裂；回忆杀/倒叙需要「第 83 章时的世界」无从取起 | Track B |
| **事实探针不管「梯度」** | 战力通胀（tier_rank 跳变无突破事件）、腔调漂移（角色怎么说话变了）——八表全管「是什么」，不管「怎么变的」 | Track C |
| **上下文与账册线性膨胀** | 第 200 章实体几百个，pack P1/P2 越来越肥；投影误差逐章累积无人对账 | Track D |
| **无趋势观测** | 每次 check 是单点快照，「警告数逐卷爬升」这种漂移曲线看不见 | Track D3 |

---

## 2. 轨道总图

```
Track A 读者记忆层   —— 读者还记得什么（派生，advisory）        [读者方案，修正版]
Track B 事件溯源层   —— 状态怎么变成这样的（changelog/重放/blame）[新增]
Track C 探针扩容     —— 梯度类不一致（位阶/声纹/空间）           [新增，C1 为刚需]
Track D 规模经济     —— 200 章的上下文与投影健康（rollup/对账/分数）[新增]
```

| 轨道 | 工作项 | 优先级 | 失败模式 |
|---|---|---|---|
| A | A1 提词公开化 / A2 memory.py / A3 三闸门 / A4 note 必填 | P0 | 伏笔凭空回收、读者遗忘后兑现无爽感 |
| B | B1 changelog / B2 state at / B3 blame / B4 bisect | B1=P0，B2–B4=P1 | 矛盾无法溯源、改史无据、回忆杀无切面 |
| C | C1 位阶单调性 | P0 | 战力通胀/通缩（网文吃书第一重灾区） |
| C | C2 声纹 / C3 传送 | P2 | 腔调漂移、空间瞬移 |
| D | D3 分数曲线 | P0（极廉价） | 漂移不可见 |
| D | D1 卷级 rollup / D2 卷末对账 | P1 | 上下文膨胀、投影累积误差 |

---

## 3. Track A：读者记忆层（读者方案 · 修正版）

> 本轨道的完整代码骨架以读者方案 §3–§5 为准（其插入点与字段约束已全部核验属实），此处只写**修正差异、补充项与验收补强**，不重复抄录。

### A1 提词与线规格公开化（零行为变更）

- `evidence.py:392`：`_line_terms_for` → `line_terms_for`（docstring 注明 memory.py 依赖与回归责任）；全仓仅 `gaps()` 一个调用点（`evidence.py:521` 附近）随之改名；**不留向后兼容别名**——本仓库无外部消费方，留别名反而让私有名永生（与读者方案不同，它建议留别名，此处裁决：不留，grep 确认零残留即验收）。
- `state.py`：新增 `line_kind_spec(kind)` 公开入口（修正 1）。
- 验收：`grep -rn "_line_terms_for" engine/ tests/` 零命中；96 测试全绿。

### A2 `engine/memory.py` 派生层

按读者方案 §3.2 实装，叠加修正 2（`max` 取章号）与修正 1（`state.line_kind_spec`）。模块定位 docstring 照抄其原文（cognition 管角色、memory 管读者，两本账不可互替）——这段写得好，保留。

- 阈值默认 25/70/25/8，`project.json` 的 `reader_memory` 键可覆盖；
- `finals` 每公开函数入口读一次（模块内允许两遍：line_memory_map 与 key_fact_memory 各一，见修正 6）；
- 验收 = 读者方案 §3.5 全部条目 + **200 章压力样书 < 2s**（§8）。

### A3 三条 advisory 闸门（errcodes 86 → 89）

| 码 | 触发 | 桶 |
|---|---|---|
| `line_never_surfaced` | 线已入账、正文零出现（硬事实，无阈值） | 叙事核 warning |
| `line_recall_cold` | beats 有 resolve 意图 × 线已冷（gap > weight 缩放阈值） | 叙事核 warning |
| `reader_memory_stale` | locked / Revealed knowledge 进入印象区（tier=impression） | 叙事核 warning |

- 插入点照读者方案：画像计算放 beats 循环前（`checks.py` run_checks 内，`plotline_starvation:1375` 一带之前），`planned_resolves` 并入 `planned_plants/planned_skips` 同一循环（`checks.py:1497` 旁）；
- `PARAM_SPEC` 增 `reader_memory`（shape=`mem_map`，`gap: False`），`validate_param_value` 增分支（照读者方案 §4.5，shape 处理在 `checks.py:719` 的 `validate_param_value`）；
- 注释中写明修正 4 的家族分工与修正 3 的漏报定性；
- 三码注册进 `errcodes.py`（受既有注册表完备性测试保护）；**不入 `SYSTEM_CHECK_CODES`**（核实过的分桶语义：进叙事核）。
- 验收：读者方案 §4.6 全部条目 + 回退验证（删闸门代码用例必须变红）。

### A4 `locked.note` 写入口必填（唯一契约变更）

- 插入点：`state.py` `validate_proposal` locked 分支 `act in ("plant","upsert")` 内（`state.py:885` 附近，紧邻 fact 长度校验）；
- 兼容性照读者方案 §5.3：只在写入口拦，不动 `verify_data`/schema required（先例：`param_write_guard` P2-6）；
- **已核验无集成冲突**：`proposal auto` 不生成 locked 条目（grep 证实 `_cmd_proposal_auto` 无 locked 装配），无自动提案被误杀风险；
- **文档同步点（读者方案漏了两处）**：除 AGENTS.md / Reader SKILL.md 外，还须同步 ① `state.py` 的 `INBOX_README` 常量（提案字段契约的机器可读说明书，Reader 落盘时读的就是它）；② `templates/README.md` 若提及 locked 字段口径则一并更新；
- 验收：读者方案 §5.4 全部条目（含存量书不新增 error、`TestSchemaModelSync` 全绿、落盘回读断言）。

**A4b（可选，一小时）**：`locked.fact` 不含任何已登记实体名/别名时，提案校验出一条 advisory 提示「该事实将无法被读者记忆层追踪，建议 fact 中含实体名」。把修正 3 的盲区在写入时刻可见化，不阻断。

### A5 pack 冷线注入（维持暂缓）

照读者方案 §6：只注入「本章 beats 计划回收 × 已冷」的可执行子集（通常 0–2 条），超预算优先裁剪。**上线前置条件：A3 跑满一卷，`line_recall_cold` 人工抽检信噪比 ≥ 3:1（真问题:噪声）。**

---

## 4. Track B：事件溯源层（新增）

### B1 `state/changelog.jsonl` —— 统一事件流（P0，R1 落地）

**设计**：钩在 `save_state`（`state.py:240`）这个全引擎唯一写入咽喉上。已核验所有写入路径均经过它：提案合并（`apply_proposal` → `state.py:1890`）、手术刀（`cmd_state set` → `state_sync.py:1199`）、账本重算（1268/1363）、里程碑（1479/1542）、迁移（`migrations.py:290`）、快照回滚（`snapshot.py:217`）。

```python
# engine/changelog.py（新模块，~150 行）
EVENT_SCHEMA = {
    "seq": int,            # 单调递增（读尾行 +1）
    "ts": "ISO-8601",
    "ch": "ch_007 | null", # 非章节性写入（手术刀/回滚/迁移）为 null
    "source": "proposal | state_set | ledger_recompute | milestone | migration "
              "| snapshot_rollback | external_edit | genesis",
    "op_id": "提案 operation_id 或 null",
    "table": "current | entities | lines | timeline | ledger | synopsis | locked | cognition",
    "path": "entries[p_003].holder",   # 列表按 id（无 id 按 name）寻址
    "op": "set | add | remove",
    "before": "旧值（add/remove 为完整条目）",
    "after": "新值",
}
# 里程碑事件：{"kind": "chapter_sealed", "ch": "ch_007", "seq": N}  ← B2 重放的锚点
```

- `save_state` 落盘前：读旧文件 → 与新数据做结构 diff（列表按 id/name 键寻址，复用 `_index_by` 思路）→ 只对**有变化的路径**追加事件（无变化零噪声）；`common.canonical_json_hash` 已有，做快速相等短路；
- `init_state`（`state.py:184`，直接 `dump_json` 不走 save_state——已核验）追加一条 `genesis` 事件；
- **封旁路**：`load_state` 尾部比对「文件哈希 vs changelog 记录的最后写入哈希」（存 `state/.changelog.meta.json`），不一致即追加 `external_edit` 事件（含 diff）——Evolver/Architect 绕过引擎的手改、以及任何 `dump_json` 直写，从此全部进事件史。与既有 `state_hashes`/`state_offline_edit`（sync 时盖章、check 时检出）分工：那是**篡改检测**，这是**篡改补录**，互补不互替；
- 追加写用 `common.atomic_write_text` 同款保护 + `.engine.lock` 文件锁（`common.file_lock` 已有）；
- 性能：每次 sync 8 表 diff，状态体量 KB 级，<10ms；200 章事件量预估 < 5MB。

**验收**：单测覆盖 set/add/remove 三型事件、无变化零事件、external_edit 补录、崩溃中断后 seq 不重号（尾行残缺时截断重写）；既有 96 测试全绿（save_state 行为对外不变）。

### B2 `state at ch_XXX` —— 时点重放（P1，R3）

- 语义：折叠 `changelog.jsonl` 至 `chapter_sealed(ch_XXX)` 的 seq，物化当时八表，打印或 `--json` 输出；配套 `--diff ch_A ch_B` 两切面对照；
- 边界：changelog 起点之前的历史不可重放，给出人话提示（「本书自 ch_XXX 起才有事件史」）——老书从接入日起积累，新书自 ch_001 完整；
- 落点：`cmd_state`（`state_sync.py:1034`）增 `at` 子动作 + `cli.py` parser/COMMAND_HELP 同步；
- 用途实证（写进 help 文案）：回忆杀取证、倒叙章装配、Evolver 波及面测算的「当时世界」基线。

**验收**：在压力样书上，`state at ch_100` 的八表与「回滚到 ch_100 快照再读」逐字节等值（用快照做金标准交叉验证）；`--diff` 能正确显示两时点间所有事件。

### B3 `state blame <table.path>` —— 字段级溯源（P1，R3）

- 扫 changelog 中 path 前缀命中的事件，按 seq 倒序列出（章、来源、before→after、operation_id）；
- 消费方：Evolver 波及面测算（「改 X 前先看 X 的变更史」）、矛盾取证（定位引入章节=最小手术半径）；
- 验收：压力样书植入一次「中途改 holder」剧情，blame 精确报出该章该提案。

### B4 `check --bisect` —— 快照二分定位（P1，R2 先行）

- 独立于 changelog 即可用：按序遍历 `snapshots/`，逐快照读其八表（`snapshot._state_files`）跑 `state.verify_data`（`state.py:2157`，纯函数已存在），二分/线性定位「不变量首次破坏」的快照区间；
- 口径诚实：只覆盖 **state 级不变量**（结构/算术/引用闭合），叙事类检查需要稿件不在快照内；
- 验收：样书在 ch_50 人为写坏 ledger，bisect 报出首个含错的快照。

---

## 5. Track C：探针扩容（新增）

### C1 `tier_shift_without_event` —— 位阶单调性（P0，R2）

- **失败模式**：tier_rank 跳变（1→9）而 timeline 无对应突破/被废事件——战力通胀是长篇第一重灾区，现有八探针全不管梯度；
- **实现**（零 Token，纯机械）：按章序重放 `state/inbox/processed/*.json`，抽取每实体的 `tier_rank/tier_name` 变更序列；每次变更要求当章（或 ±1 章）timeline.events 存在语义对应事件（关键词：突破/晋升/跃迁/觉醒/加冕/被废/跌境/重创 + bible/02 的 tier_name 词表）。变更无事件 → 叙事核 warning；
- **与 changelog 的关系**：B1 落地后可直接 `blame entities[p_003].tier_rank` 取历史，但 C1 的实现走 processed/ 重放，**对无 changelog 的老书同样可用**，两者互为冗余校验；
- 阈值进 `PARAM_SPEC`（`tier_shift_grace`，默认 1 章，`gap: False`）；
- 验收：压力样书植入「ch_120 无事件跳两阶」→ 必报；「ch_121 有突破事件的 ch_120 跳阶」→ 不报。

### C2 `voiceprint_drift` —— 声纹漂移（P2，R5，gated）

- 每主要角色抽取对白（引号段 + 说话人归属启发式，jieba 已在栈内）→ 口头禅 n-gram / 句长分布 / 语气词分布的滚动基线 → 偏离超阈出 info 级提示；
- 前置条件：A3 信噪比体感建立后再做（同一套「先观察再执法」纪律）；
- 已知局限写明：只测「怎么说话」，不测「说的是否符合人设」（后者机械不可判）。

### C3 空间传送检测（P2，暂缓）

- 依赖 bible/03 的结构化地理矩阵（当前为散文），成本高、且网文读者对赶路时差的容忍度普遍高于战力/称谓——**记录在案，50 万字目标内不做**。廉价替代：`entities[].location` 突变与 timeline 事件对照可复用 C1 同款重放器，若 C1 落地顺手且信噪比好，再评估。

---

## 6. Track D：规模经济（新增）

### D3 `state/scorecard.jsonl` + `check --trend`（P0，R1，~40 行）

- 每次 `check` 追加一行：`{ts, latest_ch, errors, warnings, infos, by_code: {码: 数}}`；
- `check --trend` 打印近 N 次的关键码走势（文本表格即可，不上图形）；
- 意义：**单次 check 是快照，分数曲线才是漂移检测**。50 万字的敌人是缓慢漂移，「warning 数逐卷爬升」必须可见；
- 验收：跑两次 check 后 `--trend` 出两行；`--json` 模式不污染 stdout 契约。

### D1 卷级 rollup —— 上下文经济学（P1，R4）

- 新命令 `python studio.py state rollup vol_XX`（在卷末封存后立即执行）：从**当前**八表确定性生成 `state/rollups/vol_XX.json`——卷末世界态势摘要：活跃/退役实体要点（仅 T1 级字段：id/name/tier/holder/life_status）、未闭环线清单与 target、各资源池余额、卷内 timeline 大事压缩、达成里程碑、活跃时钟；
- `pack.build_pack`（`pack.py:424`）与 `beats new`：目标章属 vol_03 时，注入 vol_01/vol_02 的 rollup「前情卷末态势」块（预算上限 ~500 token，超限优先裁剪，不挤 p0/p1——复用既有 `over_budget` 机制，`pack.py:627`）；
- 原则：**历史越远粒度越粗，pack 装配成本 O(当前卷) 而非 O(全书)**；
- 验收：200 章压力样书上，vol_04 任意章的 pack token 数与 vol_01 章节相当（±20%）；rollup 内容与 `state at` 卷末切面一致性抽查。

### D2 `reconcile vol_XX` —— 卷末对账大修（P1，R4）

- 新命令产出 `log/review/reconcile_vol_XX.md` 骨架，纯机械部分：
  ① 全书 `verify_data` + 全章 audit 探针批量重跑（现有 8 探针目前按章手动触发，这里全量过一遍）；
  ② 读者记忆全图（A2 输出）；
  ③ 本卷 changelog 变更摘要 + 高危字段（tier/holder/life_status/charges）blame 清单；
  ④ **投影 diff 工位**：列出「正文出现 ≥N 次但 entities 未登记」的候选专名（`evidence.candidates` 机制已有）与「台账有、正文全卷零出现」的实体，供 LLM 重提取对账；
- LLM 侧是**仪式不是代码**（遵守引擎黑盒/零脚本宪法）：卷末由主控派发临时沙盒 Reader 重读全卷 final、与八表对账，差异并入当章提案——机械骨架保证它「对着清单裁决」而不是「大海捞针」；
- 节奏：每卷一次（约 50 章），成本可控；这是对「投影必然有损、误差逐章累积」的**周期性维护**，如同数据库的 full rebuild。

---

## 7. 排期与提交切分

| 轮 | 提交 | 内容 | 验收门（全绿才进下一轮） |
|---|---|---|---|
| R1 | c1 | A1 公开化（纯改名） | 96 绿 + grep 零残留 |
| **执行状态（2026-09-09）** | R1✅(325d0b9/918a034/feb8617/d4e54ff) R2✅(3d6bdf8/2e9c4dd/1520b5d/289f365/499f336) R3✅(ae16f13) R4✅(c11 rollup b4e5159 / c12 reconcile fdb8244 / c13 压力样书)——全量 172 测试绿，§8 终局验收达成 | | |
| R1 | c2 | A2 memory.py + 单测 | 读者方案 §3.5 + 压力样书 <2s |
| R1 | c3 | B1 changelog + 单测 | §4.B1 验收 + 96 绿 |
| R1 | c4 | D3 scorecard | §6.D3 验收 |
| R2 | c5 | A3 三闸门 + errcodes | §4.6 + 回退验证 |
| R2 | c6 | A4 note 必填 + 文档四点同步 | §5.4 + proposal auto 无回归 |
| R2 | c7 | C1 位阶探针 | §5.C1 验收 |
| R2 | c8 | B4 check --bisect | §4.B4 验收 |
| R3 | c9–c10 | B2 state at + B3 blame | 快照金标准交叉验证 |
| R4 | c11–c12 | D1 rollup；D2 reconcile | §6 验收 |
| R5 | gated | A5 / C2 / C3 / E | 各自前置条件达成 |

每提交统一纪律：全量单测绿 → 新用例回退验证（临时还原旧实现必须变红）→ 提交信息记录实测证据。

---

## 8. 终局验收：50 万字健康标准（本表的完成定义）

1. **测试**：96 既有 + 新增（预估 test_memory / test_changelog / test_probe_tier / test_state_at / 压力样书 ≈ 30±10 个）全绿；
2. **压力样书**（新增测试夹具，程序化生成）：200 章 × ~800 字正文 + 20 条线（含 5 条故意冷却、2 条故意零落笔）+ 分 4 卷 + 植入五类已知吃书——
   - 无事件跳阶 → C1 报；
   - 冷线被 resolve → `line_recall_cold` 报；
   - 零落笔线 → `line_never_surfaced` 报；
   - 中途手改 state JSON → `external_edit` 事件 + 既有 `state_offline_edit` 报；
   - 中途改 holder → `blame` 精确到章与提案；
   全部命中且无误报（未植入问题的 190+ 章零新增 error）；
3. **性能**：200 章样书 `check` 全程 < 10s（其中 memory 层 < 2s）；`state at` 重放 < 3s；
4. **文档同步**（README §7 开发约定）：`AGENTS.md`（state at/blame/reconcile 新命令与读者记忆段）、`engine/README.md`（memory/changelog 模块行）、`cli.py` COMMAND_HELP、`INBOX_README`（note 必填）、`templates/README.md`（reader_memory 键）；数量口径（命令数、错误码数 86→89+）同步三处 README。

---

## 9. 明确不做（合并两份清单）

1. 不建第 9 张状态表（决策 A 维持）；
2. 不新增工序、不要求 Reader 多填字段（A4 例外已论证：复用既有字段、净负担为负）；
3. 不做阻断级读者记忆闸门（决策 D 维持——派生判定是下界，只配 advisory）；
4. 不做 overfed 复读检测（信噪比预估过低，维持读者方案裁决）；
5. 不做通用回改能力（爆炸半径量化 = `graph` + FTS5 + **新增的 blame**，够用）；
6. 不往八表加字段（瓶颈在检索/排序/历史，不在存储）；
7. **不做离屏演化**（模拟层/渲染层分离的路线对网文性价比低，记录在案）；
8. **不做 bible-as-code 全量公理化**（只取 C1 一条最有性价比的不变量先行；全量待 C1 信噪比验证后再议）；
9. `reader_harm` 维度暂缓（D3 分数曲线是其廉价近似）。

---

## 10. 宪法与开发约定衔接

- 引擎黑盒/零脚本：Track A–D 全部是 engine 侧确定性代码，子代理契约除 A4（note 必填）外零变化；
- 错误码：新增 4 码（三条读者记忆 + `tier_shift_without_event`）全部进 `errcodes.py` 注册表，受既有完备性测试保护；
- 枚举/阈值单一真源：`reader_memory`/`tier_shift_grace` 走 `PARAM_SPEC`，无硬编码散落；
- 迁移纪律：本表全部改动不动 Pydantic 模型与 schema（A4 只动提案层校验），无 `MIGRATIONS` 追加需求；changelog/scorecard/rollup 均为新增产物文件，`load_state` 对旧书无感；
- `--json` 契约：所有新命令/新旗标遵循 stdout 纯 JSON 信封与退出码 0/1/2/3 契约。

---

## 附录：本表对源码的核验记录（对应读者方案附录 A 的同款待遇）

| 断言 | 核验 |
|---|---|
| `_line_terms_for` reg_terms 语义安全（`a in blob` 过滤） | 读 `evidence.py:392-413` |
| `final_chapters` 升序返回、(卷,章号) 键、去标题行 | 读 `evidence.py:39-69` |
| `entity_lookup` 值含本体名+别名、过滤 retired | 读 `evidence.py:97-122` |
| beats 线动作区与解析正则（`plant\s+(ID)`） | 读 `checks.py:1496-1501`、`templates/beats.md:76-77` |
| `PARAM_SPEC` 位置与 `gap` 语义、六 shape | 读 `checks.py:566-612` |
| errcodes 86 码（43w/31e/12i） | grep 实测（87 含 def 行） |
| locked 校验分支、`reason` 仅 retire、`allowed_locked_keys` 含 note | 读 `state.py:871-903` |
| `_merge_locked` 六键落盘 + note 持久化 + 15 条软配额 | 读 `state.py:1570-1626` |
| `proposal auto` 不生成 locked（A4 无集成冲突） | grep `state_sync.py` 全文 |
| `save_state` 为全引擎写入咽喉（7 处调用方） | grep `engine/` 全仓 |
| `init_state` 直接 `dump_json` 不走 save_state（B1 需 genesis 钩子） | 读 `state.py:184-203` |
| `verify_data` 纯函数存在（B4 可行） | 读 `state.py:2157` 签名 |
| snapshot 目录含八表 JSON（B4 金标准可行） | 读 `snapshot.py:28-46` |
| `SYSTEM_CHECK_CODES` 双核分桶（新码入叙事核） | 读 `checks.py:65, 1904-1910` |
| pack `over_budget` 机制（D1 复用可行） | 读 `pack.py:585-627` |
