# engine/ — 确定性与图计算引擎（Novel Studio 3.1 基础设施）

入口 `python studio.py <cmd>`（根壳转发 `engine.cli.main`）。
引擎恪守**【各司其职，坚决不越界】**原则：只负责确定性计算、图拓扑剪枝、词法分析、Schema 强校验与终端渲染；坚决不做文学理解与艺术内容裁决，将纯粹的文学创作与戏剧爆发全权交由 LLM（子代理）。

---

## 模块清单与职责划分

| 模块 / 子包 | 核心职责 | 强援技术接入 |
|---|---|---|
| `models/` | 状态机领域对象与语义原子补丁强类型模型 | **Pydantic V2**（严格禁止未知键注入 `extra='forbid'`，支持 `SemanticEntityPatch`） |
| `cli.py` | 24 命令薄壳调度：参数解析 + help 目录 + `main`（命令实现下沉至 `commands/`） | argparse |
| `commands/` | 命令实现层三模块：`book_setup`（init/status/cockpit/config/errcodes）、`chapter_flow`（pack/beats/evidence/check/review/critic/graph/export/dashboard + ask/pov/calendar 只读取证）、`state_sync`（sync/proposal/snapshot/checkpoint/state/ledger）；共享助手在 `_shared` | **Rich**（高保真圆角面板、彩色 Markdown 渲染、老白读者评分卡与状态流） |
| `cockpit.py` | 主控态势驾驶舱：工作流导航、戏剧动力学（余震/悬顶危机/信息差机锋）、伏笔暗线分类雷达、角色活跃度与自愈处方 | 确定性聚合（0.1 秒出报） |
| `migrations.py` | 状态机版本化与迁移器：`state/state_schema.json` 版本戳；老书首次读取自动迁移（迁移前强制快照 + 闸门预验 + JSONL 审计日志 `migrations.log`）；只修结构不碰事实 | 快照回滚双保险 |
| `errcodes.py` | 错误码注册表：全部体检码的 severity/人话解释/修复建议（`python studio.py errcodes`，--json 供 Agent 自助修复）；`checks.DEFAULT_REMEDIES` 由它派生 | 单一真源 + 守卫测试 |
| `graph.py` | 实体拓扑与叙事中介寻路分析（`studio graph`） | **NetworkX**（最短破局链路、中介中心度排名、孤立资产排查） |
| `common.py` | 工作区定位、章节号解析、front-matter、原子写、Windows 并发重试、规范哈希 | 标准库（Windows 重试微退避机制，四层回滚保护） |
| `state.py` | 六表真值管理、语义补丁合并、复式记账重算、幂等登记簿、落盘前一致性体检、高危状态迁移守卫与时间线回退警示（advisory） | 确定性复式平衡算法与实体关系闭合校验 |
| `validator.py` + `schemas/` | mini JSON Schema 子集机械校验器（load/save 读写闸门 + 提案顶层）；`schemas/*.json` 为**构建产物**，由 `models/schema_gen.py` 从 Pydantic 模型生成（`python -m engine.models.schema_gen`），anyOf 失败时报告最接近分支的具体错误 | 模型唯一真源 + 闸门补丁层（落盘必完整） |
| `checks.py` | 叙事 AST 编译器体检、伏笔饥饿告警 (`plotline_starvation`)、引文接地柔性容错（分级 advisory，≥85% 命中 / 60~85% 近似 / <60% 存疑，永不阻断）、MIS/KNO 配额执法、bible 版本盖章对照 (`bible_drift`) | **RapidFuzz**（引文模糊接地，消除语气助词偏差误报） |
| `evidence.py` | 机械证据（words/style/dup/mentions/gaps/candidates/prev/names）与 ask 全书检索、pov 角色视角包（只读取证）只出数、零裁决 | **Jieba**（`posseg` 提取专有名词 NER 候选 + `analyse` 关键词口癖雷达） |
| `pack.py` | 三层上下文装配（P0 现场 / P1 动态触发 / P2 冷索引） | **NetworkX**（全书实体持有与归属拓扑图，1-Hop 强相关子图动态剪枝） |
| `snapshot.py` | 快照管理（create / list / rollback，支持 `--clean-drafts` 清理超前稿件） | 原子目录快照与事务安全 |
| `dashboard.py` | 全景可视化看板 HTML 导出（人物关系图谱、伏笔看板、情绪心电图） | 静态单文件 HTML 独立运行 |

---

## 输出契约与退出码

- **输出契约**：数据类命令与 Agent 交互首选 `--json`；常规模式由 Rich 呈现易读彩色终端。
- **退出码**：
  - `0` = 成功 (OK)；
  - `1` = 业务阻断（体检 errors、数据校验失败、硬闸门拦截）；
  - `2` = 用法错误（参数不合法、非法章号）。

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
2. `engine/schemas/*.json` 是构建产物，**禁止手改**（守卫测试会拦下不一致）；
3. 闸门补丁层（`schema_gen._gate_patch` + `_strip_null_branches`）显式保留「落盘必完整」类约束
   （台账条目必带 `status`、顶层 `pools/transactions/events/arcs/chapters` 必填、**全部 Optional
   字段拒绝显式 null**——生成器级全局规则）——这是有意比模型更严的持久层完整性闸门，勿删；
4. 提案信封保持浅层（schema 只看容器类型），分区深校验归 `models.validate_with_model`，
   跨字段业务规则归 `state.validate_proposal`；
5. **状态机演进纪律**：改动数据模型/闸门导致老书文件不兼容时，必须在
   `migrations.MIGRATIONS` 追加迁移函数并把 `CURRENT_STATE_VERSION` +1——老书首次读取
   会自动迁移（先快照、后迁移、闸门预验、最后落盘），只修结构、绝不碰事实。
