# engine/ — 确定性与图计算引擎（Novel Studio 3.1 基础设施）

入口 `python studio.py <cmd>`（根壳转发 `engine.cli.main`）。
引擎恪守**【各司其职，坚决不越界】**原则：只负责确定性计算、图拓扑剪枝、词法分析、Schema 强校验与终端渲染；坚决不做文学理解与艺术内容裁决，将纯粹的文学创作与戏剧爆发全权交由 LLM（子代理）。

---

## 模块清单与职责划分

| 模块 / 子包 | 核心职责 | 强援技术接入 |
|---|---|---|
| `models/` | 状态机领域对象与语义原子补丁强类型模型 | **Pydantic V2**（严格禁止未知键注入 `extra='forbid'`，支持 `SemanticEntityPatch`） |
| `cli.py` | 31 命令名（30 个处理函数，`check`/`doctor` 共用 `cmd_check`）薄壳调度：参数解析 + help 目录 + `main`（命令实现下沉至 `commands/`） | argparse |
| `commands/` | 命令实现层六模块：`book_setup`（init/status/cockpit/config/errcodes/lore）、`chapter_flow`（pack/beats/evidence/check/review/critic/graph/export/audit/index + ask/pov/calendar 只读取证）、`state_sync`（sync/proposal/snapshot/checkpoint/state/ledger/milestone）、`recall`（残酷四问自证）、`simulate`（剧情推演沙盒）、`reconcile`（卷末对账大修：机械复扫+探针重跑+投影diff）；共享助手在 `_shared` | **Rich**（高保真圆角面板、彩色 Markdown 渲染、老白读者评分卡与状态流） |
| `cockpit.py` | 主控态势驾驶舱：工作流导航、戏剧动力学（余震/悬顶危机/信息差机锋）、伏笔暗线分类雷达、角色活跃度与自愈处方 | 确定性聚合（秒级出报） |
| `audit.py` | 确定性机械审计探针：**8大探针**（不可逆事实违背/在场与死亡/道具充能/金额一致/知情差泄露/认知差冲突/别名漂移/称谓与修饰词对账 `address_mismatch`）；**轨 3 是 LLM 的活**——`audit --write` 生成的报告含 `## 🧠 语义逻辑与出戏审查` 骨架与 `logic: 0` 键，重跑时 `_merge_audit_report` 保留 🧠 正文与 `logic` 计数 | 确定性跨域比对算法（语义判断不在此列，故交 Auditor） |
| `db.py` | SQLite3 双平面投影与 FTS5 检索加速：BM25 段落级语义召回与角色 POV 聚合（支持优雅降级）；R3 增量缓存：定稿指纹 finals_fp + 按章内容哈希 fts_ch_hash（改稿才重刷） | **sqlite3**（FTS5 全文索引）+ **jieba**（专名切词） |
| `migrations.py` | 状态机版本化与迁移器：`state/state_schema.json` 版本戳；老书首次读取自动迁移（迁移前强制快照 + 闸门预验 + JSONL 审计日志 `state/migrations.log`）；只修结构不碰事实 | 快照回滚双保险 |
| `errcodes.py` | 错误码注册表：全部体检码的 level/人话解释/修复建议（`python studio.py errcodes` 全表、`errcodes <码>` 单码详解、`--level error` 过滤、`--json` 供 Agent 自助修复，含 `entity_id_duplicate` 探针）；`checks.DEFAULT_REMEDIES` 由它派生 | 单一真源 |
| `graph.py` | 实体拓扑与叙事中介寻路分析（`studio graph`） | **NetworkX**（最短破局链路、中介中心度排名、孤立资产排查） |
| `common.py` | 工作区定位、章节号解析、front-matter、原子写、Windows 并发重试、规范哈希 | 标准库（Windows 重试微退避机制，四层回滚保护） |
| `state.py` | 十一表真值管理（含 locked/cognition）、**双键实体寻址合并（ID优先）**、语义补丁合并、复式记账重算、幂等登记簿、落盘前一致性体检、高危状态迁移守卫与时间线回退警示（advisory） | 确定性复式平衡算法与实体关系闭合校验 |
| `proposal_v3.py` | 寻址式提案编译器：v3 ops（全十一表寻址）→ 编译为 v2 等价提案后走同一管线；实体寻址严格性（防重名/表错位）+ 编译前幂等预门 | 纯函数（可反复调用），与 v2 语义对齐 by construction |
| `memory.py` | 读者记忆派生：未闭环线/关键事实的 last_seen/gap/tier 画像（checks advisory 消费）；R3 起正文优先读 SQLite 增量缓存（指纹新鲜才用，失配回退文件扫），匹配语义恒为子串 | 缓存命中 ms 级，阈值免校准 |
| `rollup.py` | 卷级态势摘要层：`state/rollups/vol_XX.json` 从当前十一表确定性派生（零 Token 纯算术）；`prior_volumes_digest` 供 pack p0 注入「前情卷末态势」（≤500 token，超限按优先级尾部裁剪），装配成本 O(当前卷)；与 snapshot（精确回滚点）/changelog（字段级事件史）三分：rollup 是写作上下文用粗粒度态势 | 标准库 |
| `voiceprint.py` | 对白声纹层：引号段抽取 + 说话人归属启发式（宁漏报不误报）→ 每主要角色滚动基线（口头禅 n-gram（jieba）/ 句长 / 语气词密度）→ 近窗偏离出 `voiceprint_drift`（info，只测「怎么说话」不测人设）；阈值走 PARAM_SPEC `voiceprint` 键 | jieba（已在栈内） |
| `changelog.py` | 事件溯源层：`state/changelog.jsonl` 字段级变更事件流（save_state 唯一写入咽喉自动派生；外部改动 load 时自动补录；快照回滚不清空历史而是记为事件）；`fold(base, events) == 磁盘` 核心不变量供 verify 对账；`state at <章>`（时点切面）/ `state diff` / `state blame`（字段级溯源）由本模块直接供底 | 标准库（追加式 JSONL + 规范哈希） |
| `validator.py` + `schemas/` | mini JSON Schema 子集机械校验器（load/save 读写闸门 + 提案顶层）；`schemas/*.json` 为**构建产物**，由 `models/schema_gen.py` 从 Pydantic 模型生成（`python -m engine.models.schema_gen`），anyOf 失败时报告最接近分支的具体错误 | 模型唯一真源 + 闸门补丁层（落盘必完整） |
| `checks.py` | 叙事 AST 编译器体检、伏笔饥饿告警 (`plotline_starvation`)、引文接地柔性容错、MIS/KNO 配额执法、bible 版本盖章对照 (`bible_drift`)、实体 ID 重复校验 (`entity_id_duplicate`) | **RapidFuzz**（引文模糊接地，消除语气助词偏差误报） |
| `evidence.py` | 机械证据（all 汇总 / words / style / file / dup / mentions / gaps / candidates / prev / names / index）与 ask 全书检索（2.0 引用链：每条命中带 cite{table,key,chapters}）、pov 角色视角包（只读取证）只出数、零裁决 | **Jieba**（`posseg` 提取专有名词 NER 候选 + `analyse` 关键词口癖雷达） |
| `pack.py` | 三层上下文装配（P0 现场 / P1 动态触发 / P2 冷索引），自动注入实体唯一物理 ID（`[ID: p_001]`）与称谓对校矩阵；**预算 2W token**（`PACK_TOKEN_CAP`），超量走压缩阶梯（P2 冷索引 → P2 旧章指针 → P1 间接关联 → P1 脊柱 → P0 上章余温，`hard_reminders`/beats/不可逆事实永不裁）；`world_anchors` 按细纲 front-matter `world_refs` 取用（缺省＝恒给；命中＝只装命中节，若 `_ANCHOR_CORE_GROUPS` 五组里有组存在于 bible 却未被覆盖 → 包里打 ⚠️ 点名缺哪组；零命中＝回退恒给并列出可钉节名）；`ROLE_DENY` / `ROLE_ALLOW_EXTRA` 是准读网关单一真源，子代理 `file_index` 只列可读文件 | **NetworkX**（全书实体持有与归属拓扑图，1-Hop 强相关子图动态剪枝） |
| `snapshot.py` | 快照管理（create / list / rollback，支持 `--clean-drafts` 清理超前稿件与旧版表补齐） | 原子目录快照与事务安全 |
| `objects/` | 对象层：`registry` 三键寻址索引 / `envelope` 统一包络视图（`state object` 消费）/ `derive` 派生计算（derived.json 唯一写口） | 纯内存视图 + 纯函数（单节故障不污染他节） |

---

## 输出契约与退出码

- **输出契约**：数据类命令与 Agent 交互首选 `--json`；常规模式由 Rich 呈现易读彩色终端。
- **封账闸门链（Stage 5 顺序不可交换）**：`audit <ch> --write` → `sync <ch>` → `check <ch>`。
  `cmd_sync` 的拒绝顺序即输入合同顺序：① 定稿存在 ② 提案存在且可解析、`chapter` 与目标一致
  ③ beats + raw 齐（缺 beats 直接点名 `beats new --write`）④ **Stage 4C 仲裁闸门**：报告必须存在、
  front-matter 四键可解析，且 `hard > 0` **或** 🧠 `logic > 0` 时须 `adjudicated: true`
  （`audit_mode: advisory` 全部降级为提示，`off` 整段跳过）⑤ 空变更拒封 ⑥ `verify_state` 前置因果闸门。
  台账指纹不在 `sync` 阻断——离线手改由 `check` 的 `state_offline_edit` 报出（warning + changelog 留痕）。
- **退出码**：
  - `0` = 成功 (OK)；
  - `1` = 业务阻断（体检 errors、数据校验失败、硬闸门拦截）；
  - `2` = 用法错误（参数不合法、非法章号）；
  - `3` = 运行环境缺依赖（引擎 import 期即失败；`studio.py` 会打印缺失模块与
    安装命令，不再抛裸 traceback——环境问题必须与业务阻断区分开）。

---
 

## 幂等与重提语义（重要）

- `operation_id` 登记于 `state/.applied_operations.json`：同 id 同内容 = 幂等跳过；同 id 异内容 = 拒收；
- **修正重提必须换新 operation_id**；对已 plant 的线索 ID 重提「内容逐字一致」的 plant 会被幂等跳过
  （崩溃重放保护），内容不一致才拒收；
- `ledger` 流水按（chapter/pool/delta/type/subject/counterparty/note）指纹做重放去重——同章同内容的
  两笔独立交易请在 subject/note 中加入区分信息；
- lines 的 `plant` 必填 `target_ch`（正整数章号 / ch_NNN / 「第N章」/ "longline"）——缺省会静默占用
  长线配额，故已强制显式声明。

---

## 校验体系单一真源（重要）

`engine/models/*`（Pydantic）是字段结构、类型、枚举与约束的**唯一真源**：

1. **改模型后必须重新生成**：`python -m engine.models.schema_gen`；
2. `engine/schemas/*.json` 是构建产物，**禁止手改**；**子代理也不必读它**——给 Agent 的合同面是
   `beats new` 注入的 `### 📐 提案通道与键形状` 小节（v2 键名 + v3 形状，运行时从本表派生）与
   `templates/README.md` 第四节白名单，人读文档与 Schema 同源、冲突时以 Schema 生成结果为准；
3. 闸门补丁层（`schema_gen._gate_patch` + `_strip_null_branches`）显式保留「落盘必完整」类约束
   （台账条目必带 `status`、顶层 `pools/transactions/events/arcs/chapters` 必填、**全部 Optional
   字段拒绝显式 null**——生成器级全局规则）——这是有意比模型更严的持久层完整性闸门，勿删；
4. 提案信封保持浅层（schema 只看容器类型），分区深校验归 `models.validate_with_model`，
   跨字段业务规则归 `state.validate_proposal`；
5. **状态机演进纪律**：改动数据模型/闸门导致老书文件不兼容时，必须在
   `migrations.MIGRATIONS` 追加迁移函数并把 `CURRENT_STATE_VERSION` +1——老书首次读取
   会自动迁移（先快照、后迁移、闸门预验、最后落盘），只修结构、绝不碰事实。

---

## 统一实体 ID 与双键寻址机制 (Dual-Key Indexing & Canonical IDs)

为彻底解决长篇小说由于实体同名、别名多、重铸改名导致的状态断裂与生命周期丢失问题，引擎实施**双键联合寻址机制**：

1. **唯一物理 ID 编码规范**：
   - 角色：`p_001`, `p_002`...（`p_001` 恒定为主角）
   - 物品/法宝：`it_001`, `it_002`...
   - 势力/门派：`fac_001`, `fac_002`...
   - 地点/场景：`loc_001`, `loc_002`...
2. **`_merge_entities` 双键合并解析策略**：
   - 合并 Reader 提案时，引擎跨 persons/items/factions/places 四表优先检查 `item.id`（ID 索引）；
   - 若 `id` 命中已有实体，即便中文 `name` 发生变更（如“断水剑”被重铸为“断水龙吟剑”），也会精准就地更新该实体的属性与演化轨迹，绝不裂变为两个实体；
   - 若 `item.id` 未指定，则降级按 `item.name` 寻址，并将已有实体的 `id` 继承给更新条目；
   - 若 ID 与 Name 均未命中，则作为全新实体入册。
3. **机械防重与体检闸门**：
   - `models/entities.py`: Pydantic V2 模型校验器 `check_unique_ids` 拦截单表文件内重复 ID，跨表重复由 `state` 落盘体检（「实体 ID 跨表重复」）补回；
   - `checks.py`: 体检探针 `entity_id_duplicate` 机械扫描十一表，杜绝 ID 碰撞。
4. **物理通用字段标准（与 Pydantic 模型完全一致）**：
   - `id`, `name`, `type`, `tier_rank`, `tier_name`, `power_benchmark`, `status`, `life_status`, `card`, `location`, `faction`, `attitude`, `holder`, `charges`, `max_charges`, `cost_per_use`, `durability`, `sensory_anchor`, `address_matrix`, `aliases`，外加对象化字段 `injury_level` / `injury_desc` / `renown` 与 relations 的 `strength` / `status` / `since_ch`。

---

## 底层词典速查指令集 (studio lore CLI)

`studio lore` 系列命令为人类作者与各 Stage 子代理（Director, Drafter, Editor, Auditor）提供零成本的秒级设定对账与事实检索能力：

```bash
python studio.py lore list [-w BOOK]                         # 全量查看已注册实体 ID、名称与卡片状态
python studio.py lore entity <id/name> [-w BOOK]             # 穿透调阅实体全息档案（位阶/标尺/物象/阵营/称谓矩阵…）与关联卡片
python studio.py lore compare <idA/nameA> <idB/nameB>        # 秒级对校两实体阶梯差距与法定互称矩阵
python studio.py lore scale [-w BOOK]                        # 查看战力/实力位阶实物破坏力标尺
python studio.py lore rules [-w BOOK]                        # 查看世界运转物理与逻辑公理
python studio.py lore address <角色名> [-w BOOK]             # 提取该角色对外与被叫的完整称谓矩阵
python studio.py lore query <实体> <属性名> [-w BOOK]        # 提取实体的单项字段（如 charges, tier 等）
python studio.py lore get <主题/实体/文件> [-w BOOK]         # 模糊检索或直接提取对应设定全文
```

