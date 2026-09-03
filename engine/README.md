# engine/ — 确定性与图计算引擎（Novel Studio 3.1 基础设施）

入口 `python studio.py <cmd>`（根壳转发 `engine.cli.main`）。
引擎恪守**【各司其职，坚决不越界】**原则：只负责确定性计算、图拓扑剪枝、词法分析、Schema 强校验与终端渲染；坚决不做文学理解与艺术内容裁决，将纯粹的文学创作与戏剧爆发全权交由 LLM（子代理）。

---

## 模块清单与职责划分

| 模块 / 子包 | 核心职责 | 强援技术接入 |
|---|---|---|
| `models/` | 状态机领域对象与语义原子补丁强类型模型 | **Pydantic V2**（严格禁止未知键注入 `extra='forbid'`，支持 `SemanticEntityPatch`） |
| `cli.py` | 18 命令编排、参数解析与现代化终端交互 | **Rich**（高保真圆角面板、彩色 Markdown 渲染、老白读者评分卡与状态流） |
| `graph.py` | 实体拓扑与叙事中介寻路分析（`studio graph`） | **NetworkX**（最短破局链路、中介中心度排名、孤立资产排查） |
| `common.py` | 工作区定位、章节号解析、front-matter、原子写、Windows 并发重试、规范哈希 | 标准库（Windows 重试微退避机制，四层回滚保护） |
| `state.py` | 六表真值管理、语义补丁合并、复式记账重算、幂等登记簿、落盘前一致性体检 | 确定性复式平衡算法与实体关系闭合校验 |
| `validator.py` + `schemas/` | 提案与状态机底层 JSON Schema 机械校验 | JSON Schema Draft 2020-12 |
| `checks.py` | 叙事 AST 编译器体检、伏笔饥饿告警 (`plotline_starvation`)、引文接地柔性容错 | **RapidFuzz**（90% 局部相似度容错放行，消除语气助词漏抄误杀） |
| `evidence.py` | 机械证据（words/style/dup/mentions/gaps/candidates/prev）只出数、零裁决 | **Jieba**（`posseg` 提取专有名词 NER 候选 + `analyse` 关键词口癖雷达） |
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
