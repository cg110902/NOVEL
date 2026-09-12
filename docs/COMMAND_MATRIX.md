# Engine 31 核心命令与多智能体矩阵映射全景图 (Command Matrix)

> 🏆 **【系统核心设计哲学：动静分离与绝缘区】**
> - **命令绝非“雨露均沾”**：网络小说最忌讳“机械查表感”。纯文学岗与读者岗**绝对禁止碰任何命令**，唯有彻底隔离数据库思维，才能保证正文的顶级活人感、大白话易读性与真实的读者追更体验。
> - **单工序单闭环**：流水线子代理只开放与其核心职责绑定的 **1~2 条专属命令**，恪守准读准写，用完即走。
> - **宏观与外科掌控**：宏观战略官（Director）、架构师（Architect）、剧情外科（Evolver）与长程巡检（Librarian）作为 31 项命令的深度调度者。

---

## 一、 子代理专属命令分配矩阵 (Agent Command Matrix)

| 角色 (Agent) | 负责阶段 | 专属命令清单 | 核心场景与使用指南 |
|---|---|---|---|
| **主控 (Director)** | 全局统筹<br/>Stage 1 / 5 | `cockpit`<br/>`calendar [N]`<br/>`simulate branch`<br/>`graph path/neighbors`<br/>`lore compare/entity`<br/>`ask 2.1` / `pov`<br/>`recall`<br/>`beats new`<br/>`sync`<br/>`state rollup`<br/>`check --trend/--bisect` | **总制片人四大实战武器库**：<br/>1. 每章动笔前跑 `cockpit` 与 `calendar 3` 研判态势与危机时钟；<br/>2. 剧情卡点时跑 `simulate branch --write` 生成走向参谋单；<br/>3. 需借力打力时跑 `graph path` 拓扑寻路；<br/>4. Stage 5 跑 `sync` 完成原子状态封存与卷末 `state rollup`。 |
| **架构师 (Architect)** | Stage 0A / 0B<br/>（仅开新书） | `init`<br/>`milestone add`<br/>`check` | **创世播种双门禁**：<br/>1. `init` 初始化脚手架与物理底座；<br/>2. `milestone add` 播种主线里程碑与达成章节；<br/>3. `check` 确保 Stage 0 结束时 0 errors 通电交卷。 |
| **起草员 (Drafter)** | Stage 2 | `pack` (资料获取) | **100% 依靠装配包起草**：<br/>仅跑一行 `pack` 获取当章全部写作资料包。杜绝分心与心流打断，把 100% 算力倾注在初稿爆发上。 |
| **精修师 (Editor)** | Stage 3A | **【绝对零命令】** | **纯文学骨肉做加法**：<br/>不读 beats，不跑命令。专心丰富人物互动潜台词、场景博弈与情绪温差。 |
| **脱水师 (Stylist)** | Stage 3B | **【绝对零命令】** | **大白话脱水与去冷脸**：<br/>不读 beats，不跑命令。纯粹遣词脱水、消除反刍总结、确保极度通俗易扫读。 |
| **审查员 (Auditor)** | Stage 4A | `audit ch_XXX --write`<br/>`ask 2.1` | **确定性探针与逆鳞质检**：<br/>1. 跑 `audit ch_XXX --write` 运行 8 大机械探针；<br/>2. 通读遇人设疑点，必跑 `ask "<角色名>"` 调阅角色卡逆鳞与心理四维，拒绝瞎猜。 |
| **催更员 (Critic)** | Stage 4B | **【绝对零命令】** | **老白读者纯盲审**：<br/>模拟坐在手机前追更的十年老白读者，纯读者视角盲审预定稿，给出追更心理便签，绝不上帝视角查库。 |
| **定稿师 (Fixer)** | Stage 4C | `ask 2.1` | **争议靶向对账定稿**：<br/>针对 Auditor 提出的争议清单，跑 `ask` 秒查角色原定称谓与专属微动作，精准微调出法定定稿 `final/ch_XXX.md`。 |
| **审计员 (Reader)** | Stage 4D | `ask 2.1`<br/>`proposal check ch_XXX` | **查重与提案只读秒级预检**：<br/>1. 提取实体前跑 `ask` 查重已有物理 ID，防 ID 碰撞；<br/>2. 保存 JSON 提案后，跑 `proposal check ch_XXX` 进行 0-Token 纯只读预检，确保引文与 Schema 100% 正确，Stage 5 封存零失败。 |
| **图书管理员 (Librarian)** | 每10章巡检<br/>卷末对账 | `evidence candidates`<br/>`lore list`<br/>`reconcile vol_XX`<br/>`ledger recompute`<br/>`ask 2.1` | **长程实体打捞与大修平账**：<br/>1. 跑 `evidence candidates ch_XXX` 自动打捞频繁出场但未登记的活跃龙套与道具；<br/>2. 跑 `lore list` 校验全书实体名册；<br/>3. 卷末跑 `reconcile vol_XX --write` 出具对账单；<br/>4. 账目存疑时跑 `ledger recompute` 一键修复。 |
| **演进重构师 (Evolver)** | Stage Evolution<br/>（中途变更） | `simulate impact`<br/>`snapshot create/rollback`<br/>`state at/diff/blame`<br/>`ask 2.1`<br/>`check` | **剧情外科手术雷达**：<br/>1. 动刀前跑 `simulate impact --entity <实体> --action <动作>` 拓扑测算连锁因果波及；<br/>2. 动刀前跑 `snapshot create` 强制备份，遇阻用 `snapshot rollback` 一秒撤销；<br/>3. 用 `state at` 与 `state diff` 对校历史时点切面与改动前后差异。 |

---

## 二、 Engine 31 命令按能力分层详表

### 分层 1：宏观大局、剧情排产与推演沙盒 (6)
| 命令 | 完整调用范例 | 核心功能与参数说明 | 典型消费角色 |
|---|---|---|---|
| `cockpit` | `python studio.py cockpit -w "..." [--json]` | 主控态势驾驶舱：全剧工作流进度、大纲四分位航标、余震/危机时钟、伏笔雷达、催更雷达 | Director |
| `calendar` | `python studio.py calendar [N] -w "..."` | 未来 N 章排产日历：预判未来 N 章的到期伏笔、危机倒计时与里程碑投影（Stage 1 动笔前必查） | Director |
| `recall` | `python studio.py recall -w "..."` | 知乎残酷四问 0-Token 机械自证（主角知道什么/哪三条不能改/伏笔未兑现/下章红线），防平庸俗套 | Director |
| `simulate` | `python studio.py simulate branch [ch_XXX] --write`<br/>`python studio.py simulate impact --entity <ID> --action kill` | 剧情推演沙盒：`branch` 自动推演 3 条分支假说并生成 `log/branches/` 参谋单；`impact` 测算实体死亡/改动的拓扑因果波及 | Director<br/>Evolver |
| `checkpoint` | `python studio.py checkpoint -w "..."` | 宏观航向校准点：每 5 章复盘一次分卷四分位里程碑与主线偏航情况 | Director |
| `status` | `python studio.py status -w "..."` | 进度总览：当前卷、最新章节流转阶段与下一步操作指向 | Director |

### 分层 2：实体拓扑、全息知识与角色认知 (4)
| 命令 | 完整调用范例 | 核心功能与参数说明 | 典型消费角色 |
|---|---|---|---|
| `ask` | `python studio.py ask "<关键词/实体/线索>" -w "..."` | 全书事实问书机 (2.1)：覆盖十一表真值、定稿正文原句、角色全息卡（Want/Fear/逆鳞/微动作）、世界圣经，带精确出处 | Director / Auditor<br/>Fixer / Reader<br/>Librarian / Evolver |
| `lore` | `python studio.py lore list`<br/>`python studio.py lore entity <ID/名>`<br/>`python studio.py lore compare <A> <B>` | 底层词典与实体对账：`list` 列出全书 ID；`entity` 穿透 36 字段全息档案；`compare` 比对两角色位阶差距与法定互称 | Director<br/>Librarian |
| `graph` | `python studio.py graph path <A> <B>`<br/>`python studio.py graph neighbors <实体>`<br/>`python studio.py graph centrality` | 实体拓扑与叙事中介寻路：计算两人间最短人脉中介链路、宗门外交敌友网络、世界核心权力枢纽 | Director |
| `pov` | `python studio.py pov "<角色名>" -w "..."` | 角色视角包：调阅该角色持有法宝、人际关系、他知道与不知道的信息（知情边界，防透视开挂） | Director |

### 分层 3：工序流水、装配与单章质检闸门 (5)
| 命令 | 完整调用范例 | 核心功能与参数说明 | 典型消费角色 |
|---|---|---|---|
| `beats` | `python studio.py beats new ch_XXX --write -w "..."` | Stage 1 细纲任务书脚手架生成（智能注入字数预算与情绪蓄水槽） | Director |
| `pack` | `python studio.py pack ch_XXX -w "..."` | 单章上下文三层装配（P0 现场 / P1 别名触发 / P2 冷索引），为 Drafter 生成写作上下文包 | Director (或自动触发) |
| `audit` | `python studio.py audit ch_XXX --write -w "..."` | 8 大确定性机械探针（在场/充能/金额/KNO/不可逆/认知差/别名漂移/称谓对账），生成问题清单骨架 | Auditor |
| `proposal` | `python studio.py proposal check ch_XXX -w "..."`<br/>`python studio.py proposal new ch_XXX` | 提案工具：`check` 为 0-Token 纯只读预检（自查 Schema、引文接地、ID 冲突）；`new` 生成空骨架 | Reader |
| `sync` | `python studio.py sync ch_XXX -w "..."` | Stage 5 状态原子封存：提案合并 → 状态体检 → 快照归档（全书推进核心写咽喉） | Director |

### 分层 4：演进重构、长程巡检与账本维护 (6)
| 命令 | 完整调用范例 | 核心功能与参数说明 | 典型消费角色 |
|---|---|---|---|
| `reconcile` | `python studio.py reconcile vol_XX --write -w "..."` | 卷末对账大修：全书不变量复扫 + 8 探针批量重跑 + 投影差异候选，产出对账工作单 | Librarian |
| `evidence` | `python studio.py evidence candidates ch_XXX`<br/>`python studio.py evidence all` | 机械证据：`candidates` 自动打捞正文中高频出现但未登记的角色/物品候选池；`all` 提取全书词频与文风数据 | Librarian<br/>Director |
| `snapshot` | `python studio.py snapshot list`<br/>`python studio.py snapshot create <NAME>`<br/>`python studio.py snapshot rollback <NAME> --clean-drafts` | 快照事务安全：建立安全备份点，或一键干净回滚至上一稳定版本（支持清理超前稿件） | Evolver<br/>Director |
| `state` | `python studio.py state at <章号>`<br/>`python studio.py state diff <章A> <章B>`<br/>`python studio.py state blame <表.路径>`<br/>`python studio.py state rollup <卷>` | 状态时空机器：`at` 取历史章时点切面；`diff` 两时点差额；`blame` 字段溯源责任人；`rollup` 生成卷末态势注入下卷 pack | Director<br/>Evolver |
| `ledger` | `python studio.py ledger recompute -w "..."` | 账本手术刀：余额与 `balance_after` 按历史流水全量重算修复（流水平账） | Director / Evolver<br/>Librarian |
| `checkpoint` | 同分层 1，兼具宏观航向校准功能 | - | Director |

### 分层 5：创世播种、配置与系统体检 (10)
| 命令 | 完整调用范例 | 核心功能与参数说明 | 典型消费角色 |
|---|---|---|---|
| `init` | `python studio.py init -w "..." -t "书名" -g "题材" -p "主角"` | 创建新书工作区：生成目录脚手架、模板槽位实例化与状态初始化播种 | Architect |
| `milestone` | `python studio.py milestone add --title "..." --target-ch N` | 主线里程碑管理：播种宏观主线阶段目标与预期达成章节 | Architect |
| `config` | `python studio.py config get/set <KEY> <VAL>` | 书级参数手术刀：动态查看或调整 `project.json` 配置项（如字数带、线索配额等） | Director |
| `check` | `python studio.py check -w "..." [--trend] [--bisect]` | 结构/Schema/算术体检：退出码 0 为健康，1 为硬阻断；`--trend` 监控分数曲线防慢烂；`--bisect` 快照二分排查破坏点 | 全员验收<br/>Director 核心监控 |
| `doctor` | `python studio.py doctor` | `check` 的同义别名，输出完全相同 | Director |
| `errcodes` | `python studio.py errcodes [--json]` | 错误码字典速查：查询所有体检报错码的含义与自愈处方 | 开发者 / Director |
| `index` | `python studio.py index --rebuild` | 重建 SQLite3 FTS5 全文检索引擎与拓扑缓存 | 引擎底层 / 维护 |
| `export` | `python studio.py export --txt [--views]` | 全书编译：将各卷章节拼接输出为完整单行本 txt，或渲染全书状态视图 | Director / 人类作者 |
| `review` | `python studio.py review new ch_XXX --write` | 生成校对注记模板骨架（供人工精校注记） | 人类作者 / 校对员 |
| `critic` | `python studio.py critic ch_XXX` | 查看 Stage 4B 催更便签或生成骨架 | Director 查看 |

---
