# Novel Studio V3.1 深度审查报告（文档 × 架构 × 代码 交叉核验）

> **状态说明（提交时补记）**：本报告是审查阶段的快照，正文按「发现问题时」的口吻陈述。
> 报告列出的 P0/P1/P2 各项**已在本分支全部实施修复**，回归锁定在 `tests/test_engine.py`
> （38 个用例，`python -m unittest discover -s tests`）。阅读时请把每条结论当作
> 「修复前的事实」；修复后的口径以代码、`AGENTS.md`、`README.md` 与本报告第七节的修复顺序为准。

审查对象：`cg110902/NOVEL` @ `f9ae899`（分支 `arena/01a08184-novel`，工作树未改动）
审查方式：**不靠通读印象，全部结论都在沙箱里跑出来**。

复现环境：Python 3.11.2；`python -m venv .venv && .venv/bin/pip install pydantic jieba networkx rich rapidfuzz`
（pydantic 2.13.5 / networkx 3.6.1 / rapidfuzz 3.14.6）。
测试书工作区：`NOVEL_STUDIO_WORKSPACE_ROOT=$PWD/.test_area`，`init -t 断刀 -g 仙侠 -p 林牧`，
随后完整跑通 `beats → raw → final → proposal → audit → sync → check/cockpit/ask/pov/…` 全流程。
`git status` 干净；`.venv/`、`.test_area/` 均在 `.gitignore` 内。

**先说好的（这些都实测通过，不是纸面声明）：**

| 结论 | 验证方式 |
|---|---|
| `engine/schemas/*.json` 与 Pydantic 模型**零漂移** | `python -m engine.models.schema_gen` 后 `git diff -- engine/schemas` 为空 |
| 老书迁移链 v0→v4 真的能跑 | 删掉 `state_schema.json`+`locked/cognition`、注入未知键与显式 null，`status` 懒触发迁移：`from 0 → to 4`，快照 `pre_migration_v0` 落地，`migrations.log` 记录「裁掉未知字段 / 丢弃显式 null / 初始化第七、八表」 |
| 幂等契约成立 | 同 `operation_id` 同内容 → `duplicate: True` 跳过；同 id 异内容 → 「已用于不同内容，拒绝复用」 |
| `errcodes` 注册表与 `checks.py` 实际产出的 58 个 `_err()` 码**一一对应**，无漏注册 | 脚本比对（仅 `stage0_onboarding` 走 `e["code"]=` 赋值路径，也已注册） |
| 账本「余额只由流水重算」在 `verify_data` 里是真闸门 | 读 `state.py:2074+`，并实测 `ledger pool add` 拒绝 `current` |

下面是问题。按「会不会当场把流水线卡死」排序。

---

## 一、阻断级（P0）：跑起来就炸 / 顺着文档走必被拦

### P0-1 `evidence` 与 `review` 两个命令**直接崩溃**（`NameError: name 'cjk' is not defined`）

`engine/evidence.py:755` 的 `_stats_one()` 算了 `total_chars`，却在 `engine/evidence.py:785` 返回 `"cjk": cjk` —— 这个局部变量从来没被定义过。

实测炸掉的命令面（`NOVEL_STUDIO_DEBUG=1` 的堆栈一致指向 `evidence.py:785`）：

```
$ studio.py evidence all      -w <书>   → exit 1  ❌ 引擎内部错误（NameError）: name 'cjk' is not defined
$ studio.py evidence style    -w <书>   → exit 1  同上
$ studio.py evidence file manuscript/vol_01/final/ch_001.md  → exit 1  同上
$ studio.py review new ch_001 --write   → exit 1  同上（checks.py:851 → evidence.style）
```

其余 kind 正常：`words / dup / gaps / names / mentions / index` 都 exit 0。

影响面不是小事：`evidence` 是 `STAGE_MAP["Stage 4"]` 的列名命令、AGENTS.md 明列的命令面之一，
`librarian/SKILL.md` 更直接要求图书管理员「可运行 `python studio.py evidence mentions`」；
`review` 是 `log/review/ch_XXX.md` 校对注记的唯一生成入口（`sync` 里还有 `review_gate` 消费它）。
一行修复：`"cjk": common.cjk_count(text)`。

### P0-2 Auditor 的技能卡模板**不满足 `sync` 的硬闸门** —— 按文档写报告，Stage 5 必然被封死

`state_sync.py:200-215`：`project.json` 默认 `audit_mode: "strict"`（`templates/project.json` 就是这么播种的），
此时 `log/audit/ch_XXX.md` **必须**带 YAML front-matter 且含 `hard` / `adjudicated`，否则 `sync` 直接 `exit 1`。

而 `.agents/skills/auditor/SKILL.md`「四、仲裁报告标准模板」给出的是纯 Markdown（`# 第X章 一致性双轨仲裁报告` 起头），
**没有 front-matter，全文也没出现 `hard` / `adjudicated` / `audit --write` 任何一处**。

实测：把 SKILL 模板原样落成 `log/audit/ch_001.md`，`sync ch_001` 输出

```
❌ ch_001 的仲裁报告缺少 YAML front-matter 或格式损坏（须包含 hard 与 adjudicated）
   💡 检查 …/log/audit/ch_001.md 顶部 front-matter（格式：---\nhard: 0\nadjudicated: false\n---）
exit=1
```

改用 `studio.py audit ch_001 --write`（`chapter_flow.py:342 _render_audit_md` 才会吐出 `hard/soft/adjudicated`）后，`sync` 才通。

**这个契约只在 `config guide` 的 `audit_mode` 说明和 sync 报错提示里出现过**，
AGENTS.md 的 Auditor 行、auditor/SKILL.md 都没写。新書第一次跑到 Stage 5 就会撞上，且撞上的角色（Auditor）
被明令「严禁编写脚本」、只被授权跑 `audit --json`。

### P0-3 `pack --as architect` 是合法 CLI 选项，但读网关把它当「未知角色」拒绝一切

`cli.py` 的 `--as` choices 是 `architect/director/drafter/editor/reader/critic` 六个；
`pack.py:757 ROLE_DENY` 只定义了 `director/drafter/editor/reader/critic` 五个。实测：

```
$ studio.py pack ch_001 --open state/current.json --as architect
⛔ 未知角色「architect」（合法: critic/director/drafter/editor/reader）  exit=1
$ … --as stylist   → exit=2 argparse invalid choice
$ … --as auditor   → exit=2 argparse invalid choice
```

10 个角色里 5 个（architect / stylist / auditor / librarian / evolver）在机械网关里根本不存在，
其中 architect 还是「能选但必被拒」的最坏形态。

---

## 二、架构与流水线设计（P1）

### P1-1 「提案是唯一写入口」这条宪法，被自己的角色矩阵推翻

- `AGENTS.md` 一/七节：「提案（proposal）为唯一写入口」「状态同步与体检全权归主控 Stage 5」。
- `state.py:1-11` 模块 docstring：「提案 = 唯一写入口」。
- 但 `architect/SKILL.md` 准写清单明写 `state/*.json`（八表初始化真值），
  `evolution/SKILL.md` 准写清单明写「状态表」、Phase 3「修正 `state/` 八表真值」。

也就是说 Stage 0 与 Stage Evolution 两条主路径**绕开**了：schema 闸门之外的业务规则、
`operation_id` 幂等登记、双键实体合并、引文接地、账本重算。而引擎对此**没有任何检测手段**：
`bible/` 有 SHA-256 盖章（`bible_drift` + `state/bible_log.jsonl`），`final/` 有 `final_hashes.json`，
**唯独 `state/*.json` 没有来源/哈希留痕**——手改过的状态表和提案合并出来的状态表在引擎眼里完全一样。
要么给 state 也上盖章+`state set` 审计流水，要么在 AGENTS.md 里把「唯一写入口」限定为「章节增量事实」。

### P1-2 Reader 的「准读清单」与它的「交付义务」互相矛盾，实测第一笔账就会被拒

`reader/SKILL.md`：准读只有 3 个文件（final / beats / `state/entities.json`），
禁读清单明写「严禁读取其余账本（lines/ledger/timeline 等）」，且「严禁执行任何终端命令行」。
可它的提案模板要求写 `ledger.transactions[].pool`、`lines[].id`（GUN/MIS/KNO）、`locked[].id`、`cognition[].id`。

后果实测（我完全按 SKILL 模板写的提案）：

```
$ studio.py proposal check ch_001
 ❌ 流水引用未声明资源池 'spirit_stone'
```

资源池清单既不在 beats 注入里（`chapter_flow.py:_consistency_section` 只注入 locked / 实体名册 / KNO），
也不在 Reader 的准读范围内，Reader 只能靠猜——而猜错就是整案拒收。

更糟的是显式 ID：Reader 读不到 `locked.json` / `cognition.json`，却按模板写 `"id": "LOCK-005"` / `"id": "COG-002"`。
`state.py:_merge_locked` / `_merge_cognition` 对已存在的 ID 是 `entry_map[iid].update(new_entry)` —— **静默覆盖**。实测：

```
BEFORE cognition: [{"id":"COG-001","character":"灯铺掌柜","content":"掌柜看出断刀裂口不寻常",…}]
提案:  {"id":"COG-001","character":"林牧","content":"林牧察觉有人跟踪他"}
AFTER  cognition: [{"id":"COG-001","character":"林牧","content":"林牧察觉有人跟踪他",…}]   ← 另一个角色的认知被抹掉
AFTER  locked   : LOCK-001 由「断刀付定金修补」被改写成「灯铺在开灯节夜里被烧毁」
```

回执里只有一句「🔒 更新不可逆事实 LOCK-001」，**没有任何「fact/character 已变」的守卫提示**
（实体侧反倒有 `_guard_entity_transitions` 那套 advisory）。
建议：显式 ID 命中既有条目但 `fact`/`character`/`kind` 变了 → 至少出 warning；
Reader 侧改为推荐无 ID 写法（引擎本来就有自动编号 + 内容指纹去重，`state.py:1596-1620`）。

### P1-3 机械读网关与 SKILL 白名单**对不上**，而且方向是「比文档更严」

`pack.py:757-777` 注释自称「按 AGENTS 禁读清单逐角色落地」，但只落了前缀级黑名单，
`ROLE_ALLOW_EXTRA`（单文件白名单）只给 critic 开了 `state/current.json`。实测：

| 角色 | SKILL 准读清单里的文件 | `pack --open --as <角色>` 结果 |
|---|---|---|
| Reader | `state/entities.json`（第 3 条，用于核对物理 ID 防碰撞） | ⛔ 禁读 `state/` |
| Editor | `bible/06_style_guidelines.md`（第 3 条） | ⛔ 禁读 `bible/` |
| Stylist | `bible/06_style_guidelines.md`（第 3 条） | 角色不存在（exit 2） |
| Critic | `state/current.json` | ✅ 唯一开了例外的 |

即：文档授权的两个关键文件，机械层一律拒绝。子代理平时用自己的读文件工具，所以不至于当场瘫痪，
但「双层防御」的说法不成立——真按网关走，Editor 拿不到文风宪法。

### P1-4 驾驶舱（cockpit）还停在 V3.0 的三段式，`help` 配方也是

AGENTS.md 是 Stage 2 → 3A(Editor→raw_v2) → 3B(Stylist→final) → 4A/4B/4C。代码里：

- `cockpit.py:623-630`：`curr_stage = "Stage 3 (文学重塑)"`，actor 直接是 `Editor`，
  指令「向精修师 Editor 下达 Stage 3 标准工序派发令…成型定稿」，`target_file` 就是 `final/ch_XXX.md`。
  工作流只跟踪 `beats/raw/final` 三个信号，**raw_v2 与 Stylist 在驾驶舱里完全不存在**。
- `cockpit.py:631`：Stage 4 的闸门是 `not status["proposal"] or not status["critic"]` —— **Auditor(4C) 不在关卡里**，
  而 `sync` 在 strict 模式下却强制要 `log/audit/ch_XXX.md`。顺着驾驶舱的「下一步」走，一定在 sync 撞墙（见 P0-2）。
- `cli.py:102`（`help` 的 RECIPES，AGENTS.md 称之为「命令目录、阶段配方与退出码契约的唯一自查入口」）：
  `"# (Stage 3 Editor 精修 final/ch_XXX.md)"` —— 配方里根本没有 Stylist。
- 另有 3 处用户可见提示仍写「Stage 3 Editor 定稿」：
  `chapter_flow.py:854`、`chapter_flow.py:857`（"需先由 Editor 定稿"）、`state_sync.py:136`、
  `state_sync.py:220`（硬矛盾修复派给「Stage 3 Editor」，而 AGENTS.md 派给 Stylist）。

驾驶舱是主控唯一的导航仪，它和宪法讲的不是同一条流水线。

### P1-5 流水线图缺两个环节，且 `audit --write` 会抹掉裁决

1. AGENTS.md 的 mermaid 里没有 Stage 4D（Librarian），只在角色矩阵里有；
   引擎侧 4D 仅以 `cockpit.py:710` 的一句 active_pressure 文本存在（第 10 章整数关口）。
2. 图里 `S3Patch → S4A` 只回 Reader，**没有 `S3Patch → S4C` 的复审回路**。
   但手术刀改完 final 后，`log/audit/ch_XXX.md` 里的 `hard` 仍是旧值：不复审就得手改 front-matter，
   复审又踩到下一条。
3. `chapter_flow.py:428-433`：`audit --write` 是**无条件 `write_text` 覆盖**，
   `_render_audit_md` 恒定写 `adjudicated: false`。所以「Auditor 完成轨 2 语义裁决 → Stylist 动刀 → 重新 audit」
   这一步会把轨 2 的人工裁决内容整份抹掉，并把 `adjudicated` 打回 false。
   同一角色还被要求「设置 Overwrite: true」写报告，两个覆盖动作互相踩。
4. Critic(4B) 在 patch 之前读 final，patch 之后不重跑，`log/critic/ch_XXX.md` 与定稿就此脱钩（AGENTS.md 红字「Critic 直通」，属于已知取舍，但图里没标）。

### P1-6 `words_target` 是**空头承诺**：字数带没有任何机械执法

`config guide` 对 `words_target` 的说明（`checks.py:576`）写着
「定稿字数目标带 [下限, 上限]（**check word_band_deviation / word_band_breach** 判定依据）」。

全仓库搜索 `word_band`：**只有这一行说明本身**，没有实现、没有 errcode 注册。
实测：定稿 1553 字（下限 2000），`check` 零相关告警，`sync` 一路绿灯。
Drafter「2000~3000+」、Editor「2200~3500」全成了纯口头纪律——对以「字数带」为商业硬指标的项目来说，
这是文档承诺与实现落差最大的一处。

---

## 三、字段与代码对不上（P1/P2）

| # | 文档说的 | 代码/实测 | 证据 |
|---|---|---|---|
| 1 | `templates/README.md:109`：`charges`「`int >= 0`，**-1 表示非计数型**」 | `-1` 被拒，且一次报**两条**重叠错误 | `entities[0].charges: 数值超出允许下限` + `必须为 ≥0 的整数`；模型 `models/entities.py:76 ge=0` |
| 2 | `type` 枚举含 `location` 与 `place`（`templates/README.md`、AGENTS.md 的 `loc_XXX` 前缀都指向 location） | 两者**行为不等价**：`graph.py:71`、`pack.py:513` 只认 `place` | 同一 `location:"青石巷灯铺"`，`graph neighbors 断刀` 只连出 `灯铺(place)`；`type=location` 的「青石巷」被 `graph isolated` 判为**完全孤立节点**；`state set current.location 青石巷` 后 `pack` 不注入该地点卡，改成「灯铺」立刻注入 |
| 3 | `diplomacy` 值域：模型描述 `ally/hostile/neutral`（`models/entities.py:84`），README 写 `allied/hostile/neutral` | 两处不一致；且 **`diplomacy` 全仓库只在 `state.py:1055` 被写入，没有任何读取方**——graph 不建边、check 不校验、pack 不注入 | `grep -rn diplomacy --include=*.py engine` 仅 4 处命中，全是模型定义与合并 |
| 4 | 命令数：AGENTS.md「**29** 个生产指令」、`engine/README.md`「29 命令」 | 实际 **30 个子命令名 / 29 个处理函数**（`check` 与 `doctor` 共用 `cmd_check`） | `help --json` 列出 30 条；`cli.py:1` docstring 自称「**28** 命令」，其命令清单也确实漏了 `doctor` 和 `lore` |
| 5 | `doctor` = 「全息双核体检与问诊…**含自愈处方**」；`check` = 「结构/schema/算术体检」（`cli.py:33,36`） | 两者是**纯别名**：文本输出 3266 字节逐字节相同，`--json` 7277 字节也相同 | `diff` 两份输出为空 |
| 6 | 八表真值（AGENTS.md / README / 各 SKILL） | 引擎里 **8 处仍写「六表」**，含用户可见的 `ask` 帮助文本「六表+final 原句双域」（实际返回 locked/cognition 命中）与 `state.py:4`「6 个 JSON 状态文件为机器真值」 | `cli.py:38,111,218,236`、`book_setup.py:123`、`state_sync.py:846`、`evidence.py:899`、`snapshot.py:92`、`state.py:4` |
| 7 | `checks.py:939` / `errcodes.py:82`：「请运行 `pip install -r requirements.txt`」 | 仓库**没有 requirements.txt**（只有 pyproject.toml）；且 `RUNTIME_DEPENDENCIES` 把 stdlib 的 `sqlite3` 也列进「待安装依赖」 | `ls | grep -i requirement` 空 |
| 8 | `errcodes` = 「**全部**体检码的机器可读说明书」（README/AGENTS 都称 Agent 自助修复入口） | `proposal verify`/`sync` 那套 advisory 电池的 **19 个码不在注册表**：`quote_missing`、`title_mismatch`、`beats_overlap`、`due_line_unhandled`、`candidate_new_entity`、`critical_mutation`、`state_watch_hit`… | 脚本比对 `add(sev, code)` 字面量 vs `errcodes.REGISTRY` |
| 9 | `reader/SKILL.md`：「客观提取 **6 大**核心事实」 | 括号里实际列了 **5** 组（现场/实体关系/线索/财务与梗概/不可逆与认知） | 同一行文本 |
| 10 | `templates/README.md`：`lore entity` 调阅「**13 大**物理属性」 | `EntityEntry` 有 33 个字段，`lore entity` 实际渲染 5~8 行 | 实测输出 |
| 11 | `index` 的 JSON 契约 | `indexed_chapters` 语义随路径漂移：增量路径报「本次新增章数」，`--rebuild` 报「总章数」 | 库里 `chapters_fts` 实有 `ch_001`（15 行），`studio index` 仍报 `indexed_chapters: 0`，`--rebuild` 报 1 |
| 12 | `state/inbox/README`（`state.py:144`）：「流水引用未声明的池 → `sync` 合并期拒收…**提案校验期不拦这一条**」 | `proposal check` **确实拦**（实测第一行就是这条错） | 文档已过期，会让 Agent 误判 check 通过即安全 |
| 13 | `models/locked.py:4,13`：「全书活跃条目上限 **15** 条」 | 模型实际 `max_length=50`，15 只是 warning 级软配额（`checks.py:1470`、`state.py:1564`） | 两处数字打架，容易让 Architect 以为是硬闸门 |

---

## 四、引擎用自己的模板触发自己的闸门（P1）

这类问题最阴险：新书 `init` 完就是「不健康」的，Agent 会去改根本不该改的东西。

**4.1 `beats new` 生成的细纲，必被 `check` 判为叙事不健康**

`checks.py:1415-1423` 有一段注释专门讲「引擎自带模板触发自己闸门」的老 bug，修法是剥掉 HTML 注释。
但 `templates/beats.md:132` 现在是 `{{slot:beat_deliverable_point|明确本章必须呈现给读者的核心爽点与看点}}`——
槽位兜底文案里带「读者」这个空判据词，剥注释的修法失效了。实测：

```
$ studio.py check → warnings: ['ch_001.md: 目标/验收含空判据词 读者…']   （acceptance_empty_criterion）
```

只把那一个 slot 填掉，warning 立刻消失（已实测）。同一类回归。

**4.2 `protagonist.md` 模板让 `lore` 的称谓矩阵变成垃圾**

`common.py:313 parse_yaml_front_matter` 用 `partition(":")` 切键值，不认引号/花括号。
`templates/characters/protagonist.md:13` 是：

```yaml
address_matrix:
  "{{slot:target_char_1|核心搭档或第一女配名}}": "{{slot:addr_to_target_1|对方称呼}}"
```

`init` 只替换 title/genre/protagonist/created_at 四个槽，这行原样留下，解析结果实测为：

```json
"address_matrix": {"{{slot": "target_char_1|核心搭档或第一女配名}}\": \"{{slot:addr_to_target_1|对方称呼}}"}
```

于是 `lore entity 林牧` 打出：

```
- 称呼「{{slot」为: target_char_1|核心搭档或第一女配名}}": "{{slot:addr_to_target_1|对方称呼}}
```

而 `lore address` / `lore compare` 正是 director/SKILL.md（Stage 1 准备）和 auditor/SKILL.md（称谓对账）
指定要跑的「法定互称矩阵」来源。填实卡片后即恢复正常（我用自造 `characters/苏九娘.md` 验证过：
`tier_rank` 正确解析成 int 9、矩阵正常），但**每本新书在 Stage 0 完成前，主角的称谓对账都是废的**。
根因是解析器不认引号 + 模板把冒号写进键名。

---

## 五、一致性校验的空白点（P2）

1. **悬空引用只查一半。** `relations[].target` 指向未登记实体 → `check` 出 `relation_target_unknown` 警告（已实测）；
   但 `faction` / `location` 两个字符串字段**全仓库没有任何检查**（`grep` 无 `faction_unknown`/`location_unknown`），
   而 `graph.py:60-71` 恰恰只在这两个名字命中已登记实体时才建边。
   实测：给「张三」写 `faction:"不存在的宗门"`、`location:"根本不存在的地方"`，`validate_proposal`、
   `apply_proposal`、`verify_state`、`check` **全部静默通过**，图上就是个孤岛。
2. **枚举真源有三份。** 项目自称「`engine/models/*` 是字段结构、类型、枚举与约束的唯一真源」，
   但 `state.validate_proposal` 里把 `alive/deceased/missing`、`active/retired`、
   `low/medium/high/critical`、`Active/Triggered/Defused/Expired`、
   `income/expense/opening_balance/manual` 全部**手写字面量**再校验一遍；
   只有 `_ENTITY_TYPES` 是从模型推导的（`state.py:70`）。这个分裂已经出过事故——
   `state.py` 里那段注释自陈「此前闸门只放行 4 类 kind，`destruction/disbandment/pact` 被误杀」。
   既然有 `_ENTITY_TYPES` 的正确写法，其余五组没有理由不照做。
3. **`locked` / `cognition` 的身份变更无守卫**（见 P1-2）。实体有 `_guard_entity_transitions`，
   这两张「不可逆事实 / 认知」表反而没有——而它们才是防吃书的核心表。
4. **`ID` 正则与常量重复定义**：`LOCK_ID_RE`/`COG_ID_RE` 在 `models/locked.py`、`models/cognition.py`、
   `state.py:34-35` 各定义一遍。
5. **`candidate_new_entity` 探针噪声极大**：4 字滑窗把同一句话切成一堆候选。
   实测一章里刷出 12 条 `「断刀放在」/「刀放在柜」/「放在柜台」/「裂口正对」…` 的「疑似新实体」。
   虽是 advisory，但 `sync` 每次都把它们打到 stdout，Agent 侧信噪比很差。
6. **`pack` 的 P2「近 N 章」在首章恒为假**：`pack.py:604` 的窗口是 `c[1] < ch_num`（严格早于本章），
   ch_001 时窗口为空，于是所有实体都被标成「近10章未出现」——包括刚刚在本章出场 29 次的。

---

## 六、工程质量（P2）

1. **仓库里没有任何测试。** 77 个受版本控制文件中 0 个测试文件；`.gitignore` 却写着
   「`.test_area/` 测试隔离区（…回归脚本）」，`schema_gen.py:10` 也自称「现状语义，**测试锁定**」，
   `errcodes.py:9-10` 说「新增错误码漏注册会**当场报警**」——这三处承诺都没有可执行的落点。
   P0-1 那种 `NameError` 只要有一条 smoke test（每个命令跑一次 `--json`）就能挡住。
2. **没有根 README，也没有安装说明。** 我进仓库第一件事就是 `studio.py --version` →
   `ModuleNotFoundError: No module named 'pydantic'` 的**裸 traceback**，退出码 1
   （与「业务阻断」同码，`engine/README.md` 定义的 2=用法错也没用上）。
   `cli.main` 的四层兜底救不了 import 期崩溃，AGENTS.md 全篇不讲环境准备。
3. **`state get` 输出 Python 字面量**：`state get entities.林牧.realm` → `entities.林牧.realm = None`
   （不是 `null` 也不是空串），对 `--json` 之外的消费方不友好。
4. `milestone achieve` 省略 `-c` 时静默取「最新定稿章」核销：实测把 `target_ch: 12` 的里程碑
   核销在 `ch_001`，只有一行回显，无任何「早于目标章」提示。
5. `ledger pool add` 的 merge 警告口径别扭：「卷内活动伏笔池已达上限（8/8），新伏笔 GUN-009 已入库」
   ——计数用的是插入前的值，读起来像自相矛盾。

---

## 七、建议的修复顺序

**P0（今天就能修，都是一两行）**
1. `evidence.py:785`：`"cjk": common.cjk_count(text)`；顺手给每个命令加一条 `--json` smoke test。
2. `auditor/SKILL.md`：把报告模板换成带 front-matter 的版本，并明写「先 `studio audit ch_XXX --write` 生成骨架，
   再补轨 2 裁决，硬矛盾清零或 `adjudicated: true`」；AGENTS.md 的 Auditor 行同步补一句。
   （或反过来：让 `sync` 在报告无 front-matter 时按 `hard=0` 放行 + 出 warning，二选一，别两边都不认。）
3. `pack.py`：`ROLE_DENY` 补 `architect/stylist/auditor/librarian/evolver`，或把 `--as` 的 choices 收敛到已实现的 5 个。

**P1（一致性主战场）**
4. cockpit 工作流补 3A/3B 与 4C：跟踪 `raw_v2`、把 `log/audit/ch_XXX.md` 纳入 Stage 4 关卡；
   同步修 `cli.py:102` 配方与 4 处「Stage 3 Editor 定稿」提示。
5. 给 Reader 一条合法取证通道：在 beats 注入里加「资源池清单 + 现有 GUN/MIS/KNO/LOCK/COG 编号水位」，
   或在 SKILL 里改成「一律不写显式 ID」；同时给 `locked/cognition` 显式 ID 覆盖加守卫。
6. 读网关补单文件白名单：`reader → state/entities.json`、`editor/stylist → bible/06_style_guidelines.md`。
7. 实现 `word_band_deviation` / `word_band_breach`，否则把 `config guide` 的说明删掉。
8. 统一 `type`：把 `place` 收敛成 `location`（或反之），`graph.py:71` / `pack.py:513` 同时认两者，
   并给存量数据加一条迁移。
9. `parse_yaml_front_matter` 支持引号内冒号（或模板改成不带冒号的占位键）。
10. 把「六表」8 处、「28/29/30 命令」、「-1 表示非计数型」、`indexed_chapters` 语义、
    inbox README 的过期说明一并对齐；补 `requirements.txt` 或在提示里改成 `pip install -e .`。

**P2**
11. 补 `faction`/`location` 悬空引用检查；把 5 组枚举字面量改成从模型推导；`errcodes` 收录 19 个 advisory 码；
    `candidate_new_entity` 换成 jieba 名词短语而非 4 字滑窗；`pack` 的窗口改成 `<= ch_num` 或改文案。
12. 加根 README（安装 / 快速开始 / 退出码），并给 `state/*.json` 上来源盖章，让 P1-1 的宪法可验证。

---

### 附：本次审查跑过的命令（可逐条复现）

```bash
python -m venv .venv && .venv/bin/pip install pydantic jieba networkx rich rapidfuzz
export NOVEL_STUDIO_WORKSPACE_ROOT=$PWD/.test_area
.venv/bin/python studio.py init -w $PWD/.test_area/断刀 -t 断刀 -g 仙侠 -p 林牧
.venv/bin/python -m engine.models.schema_gen && git diff --stat -- engine/schemas   # 空
.venv/bin/python studio.py help --json | jq '.commands | length'                    # 30
.venv/bin/python studio.py beats new ch_001 --write -w <书>
# 落 raw/ch_001_v1.md、raw/ch_001_v2.md、final/ch_001.md（首行「# 第1章 灯铺里的断刀」）
.venv/bin/python studio.py ledger pool add spirit_stone --name 灵石 --unit 块 --initial 100 -w <书>
.venv/bin/python studio.py proposal check ch_001 -w <书>       # 第一次：流水引用未声明资源池
.venv/bin/python studio.py sync ch_001 -w <书>                 # SKILL 模板报告 → exit 1（front-matter）
.venv/bin/python studio.py audit ch_001 --write -w <书> && .venv/bin/python studio.py sync ch_001 -w <书>  # 通过
.venv/bin/python studio.py evidence all|style|file|review …    # NameError
.venv/bin/python studio.py pack ch_001 --open state/entities.json --as reader -w <书>   # ⛔
.venv/bin/python studio.py graph isolated / graph neighbors 断刀 -w <书>                # place vs location
```
