# TEST_EFFICIENCY_PLAN — 测试效率与 Token/注意力优化改造清单

> 目标：**用最小的 LLM 开销，最快地抓出引擎与文档（协议）的漏洞。**
> 本文所有数字均来自本机实测（`tests/_stress_book.py` 200 章压力书），非估算。

---

## 〇、先立基线：钱到底花在哪

### 0.1 实测数据（200 章压力书）

| 项目 | 实测值 |
|---|---|
| 建 200 章压力书（走真实提案→封存流水线） | **12.1 秒，0 LLM token** |
| `check` @200 章 | **1.61 秒** |
| `pack` token 增长 | ch_001 **4006** → ch_199 **5621**（+40%，O(1) 摊销成功） |
| `pack` P0 构成 @ch_100 | world_anchors **3314** / prev_tail 735 / hard_reminders 663 / prior_volumes 84 / beats 30 |

> ⚠️ 压力书的 beats 是合成桩（30 tok），**真实 beats 模板 2846 tok**。
> 所以上表的 pack 总量是**下界**，真实值更高。

### 0.2 单章 LLM 成本模型（真实 bible + 真实 beats）

| Stage | 输入 tok | 输出 tok | 备注 |
|---|---:|---:|---|
| Director（beats） | ~6 000 | ~2 800 | cockpit + recall + lore |
| Drafter | ~11 000 | ~1 800 | pack 全量（**含 world_anchors 3~8k**）|
| Editor | ~7 400 | ~2 400 | beats + raw_v1 + bible06 + 角色卡 |
| Stylist | ~6 200 | ~2 400 | beats + raw_v2 + bible06 |
| Reader | ~7 000 | ~1 500 | final + beats + 四表 |
| Critic | ~2 600 | ~500 | |
| Auditor | ~4 000 | ~1 000 | |
| Director（sync） | ~2 000 | ~300 | |
| **合计** | **~46 200** | **~12 700** | 8 次 LLM 调用 |

### 0.3 三个杠杆（按收益排序）

1. **引擎/契约回归根本不需要 LLM** —— 200 章 12 秒 0 token。凡是要靠"写一章"才能测的引擎问题，都是测试基建没做到位。
2. **输出 token 的 52% 是中间稿**（Drafter+Editor+Stylist 共 6.6k，其中 v1/v2 合计 4.2k 是废品）—— 测试模式下合并成一个 Writer 即可。
3. **world_anchors 是单点最大浪费** —— 占 P0 的 61%，逐章重复、无上限、不可裁剪。

---

## 一、分层测试策略（核心架构决策）

**不要做"一个测试模式"，做三层。** 不同层用不同成本模型，混在一起必然两头不讨好。

| 层 | 测什么 | LLM token | 频率 | 现状 |
|---|---|---:|---|---|
| **L0 引擎/契约回归** | 状态机、闸门、账本、幂等、迁移、不变量 | **0** | 每次改动 | ✅ 已有（267 tests + 200 章压力书）|
| **L1 代理协议一致性** | 真实 Agent 照文档走，输出能不能过下一道闸 | **每章 ~3.5k 输出** | 每次改文档/SKILL | ❌ 缺失 |
| **L2 成稿质量** | 文笔、章型、读者体感 | 全量 ~12.7k | **抽样**（每 10 章 1 章）| ❌ 缺失 |

**关键认知**：L0 是 ∞ 倍杠杆（0 成本覆盖 200 章）；L1 才是需要花 token 的地方，且可被压到全量的 ~28%。

---

## 二、改造清单

### P0 — 零成本、立即做

#### ① 补故障注入（负向）测试套件 ★最高价值

- **问题**：267 个测试几乎全是正向。正向只能证明"没坏"，负向才能证明"闸门真的存在"。
- **证据**：`errcodes.py` 注册了 55 个错误码，但多数没有对应的"必须报错"用例。
- **动作**：新增 `tests/test_fault_injection.py`，纯脚本、0 token：

| 注入 | 断言命中 |
|---|---|
| 池键写成 `灵石` 而非 `stone` | `ledger_pool_undeclared` |
| 复用 `LOCK-001` 改写内容 | `locked_entry_id_reuse` |
| 复用 `COG-001` 换角色 | `cognition_entry_id_reuse` |
| 已死角色开口说话 | `probe_locked_facts` |
| 跨章写流水 | `chapter ≠ 提案章` 整案拒收 |
| 新池声明 `current` | 整案拒收 |
| 新池省略 `initial` | 整案拒收 |
| `charges > max_charges` | 整案拒收 |
| 实体 type 写中文未归一 | 拒收或归一（二选一钉死）|
| v3 `create` 已存在 ID | `[op#N]` 点名拒收 |
| `lines.plant` 缺 `target_ch` | 整案拒收 |
| 前置线未闭环就 resolve | `_prereq_errors` 拦截 |
| `balance_after` 手写错误 | `ledger_arith_broken` |
| 离线手改 `state/persons.json` | `state_offline_edit` |

- **收益**：0 token、秒级，且是唯一能证明"文档承诺的闸门真的有效"的手段。
- **成本**：约 300 行测试代码。

#### ② 新增 `studio forensics` —— 批跑后的不变量总断言

- **问题**：现有体检能力很强，但**没有一次跑完、输出机器可读结论的入口**。CI 和批跑脚本用不起来。
- **动作**：新增一个编排命令（复用现有函数，几乎零新逻辑），断言：

```
✓ check errors == 0（除白名单）
✓ changelog.verify(book) == True            # fold(基线,事件) == 磁盘
✓ derived 封存成功（无 error 字段）           # 当前必失败，天然探针
✓ ledger 算术闭合 + tx 章号单调不减
✓ 十一表 SHA-256 盖章无 offline_edit
✓ operation_id 全书唯一
✓ 快照数 == 已封存章数
✓ 幂等：同提案重放 → duplicate 而非二次合并
```

- **收益**：L0/L1 批跑的**验收出口**。没有它，"跑完 10 章"无法判定成功与否。
- **成本**：约 150 行，全部调用现有函数。

#### ③ 修 `derived.json` 封存必失败（已定位）

- **根因**：`schema_gen._strip_null_branches` 规定「Optional 字段拒绝显式 null」，而 `objects/derive.py::_derive_line_temps` 硬编码写 `"last_seen_ch": None, "gap": None`。
- **触发**：存在任意一条零落笔线或已闭环线 → 第十二张表永久为空，且**静默降级**（设计为"派生永不炸封存"）。
- **动作**：`derive.py` 对 None 键**不写**（符合闸门语义），补一条覆盖 None 分支的测试。
- **收益**：第十二张表复活；`state object` / cockpit 统计 / 场景告警全部可用；**且它立刻成为 ① 的一个免费探针**。

#### ④ 把 `mutation_guard` 常态化

- **问题**：`tests/mutation_guard.py` 是好东西（12 个变异，断言测试必须杀死），但**文件名不以 `test_` 开头，不在默认发现里**。
- **动作**：① 接进 CI；② 立规矩——**每修一个 bug 就补一个变异**。
- **收益**：唯一能防止"修过的 bug 悄悄复活"的机制。

---

### P1 — 小成本、高回报

#### ⑤ 给 `world_anchors` 加预算帽 ★Token/注意力双收益  ✅ 已完成

- **问题**：占 P0 的 61%（3314 tok），**无上限、逐章重复、不可裁剪**。真实 bible 写厚后可轻松破 10k，单枪匹马撑爆 `PACK_TOKEN_CAP=18000`（而超预算只裁 P2，P0 保留）。
- **更深的问题**：它违背 pack 自己的设计哲学——P2 明说「本包未装的一律视为你不需要知道」，而 world_anchors 是"每章硬塞"。**恒定内容不该占每章的上下文**。
- **动作**（三选一或组合）：
  1. 加 `MAX_WORLD_ANCHOR_TOKENS`（如 1200），超限按标题优先级截断，尾部提示「完整世界公理用 `studio lore rules` 按需取」；
  2. 只注入**当章 beats 引用到的**世界条目（按实体名/关键词命中）；
  3. 全书首次 + 每卷首次全量注入，其余章节只注入摘要。
- **收益**：Drafter 每章上下文降 40~60%；**同时减少恒定内容对注意力的稀释**（Drafter 会学会忽略逐章不变的内容，等于白占 budget）。

#### ⑥ beats 分角色切片（**注意：待你确认现状**）

- **分歧点**：当前 `.agents/skills/editor|stylist/SKILL.md` 的准读清单**第 1 项就是 beats 全文**。你说"没让它们看 beats 是为了保留注意力"——这若是**目标**，本项成立；若是**现状误记**，请跳过本项。
- **若成立，建议做法**：在 `beats` 模板里用显式标记划分段落，而不是新增引擎逻辑：

```markdown
<!-- SLICE:director -->  本章坐标 / 四步破局心法 / 场景脉络 / 一致性速查
<!-- SLICE:editor   -->  称谓基准 / 前情锚点 / 预期演变 / 情感微澜 / 验收要点
<!-- SLICE:stylist  -->  套路禁区 / 招牌记忆画面 / 验收要点
```

  SKILL 里写死"只读 `SLICE:<自己>` 标记段"，Editor 约 1.0k（vs 全文 2.8k），Stylist 约 0.8k。
- **收益**：Editor/Stylist 输入降 ~65%，**注意力集中在其真正负责的维度上**——正是你要的效果。
- **成本**：纯文档改动，零引擎改动。

#### ⑦ 清理 `project.json` 的死字段 `mode`  ✅ 已完成

- **问题**：`"mode": "automatic"` 被 grep 确认**无任何逻辑消费**，只有 `_book_brief` 回显。
- **已做**：从 `templates/project.json`、`book_setup.py` 的 init 默认值、`_book_brief` 回显三处一并删除。
- **理由**：配置字段没有消费者就是噪声，且会误导 Agent 以为存在"自动模式"。
- **顺带体检的结论（好消息）**：`PARAM_SPEC` 登记的 15 个参数**全部**有真实消费方，
  且 `gap=True` 的词表参数全部在 `templates/project.json` 有初值——配置面本身是自洽的。
  唯一的不自洽在 `engine/vocab.py`（见 §6 F）。

---

### P2 — 测试模式本体（依赖 P0/P1 稳定后再做）

#### ⑧ L1 代理协议测试 harness

- **位置**：`tests/agent_harness/`（**不进 `engine/`**，生产路径零感知；用 `NOVEL_STUDIO_WORKSPACE_ROOT` 隔离）
- **三个正交开关，不用一个 mode 标志**（走环境变量，不进 `project.json`）：

| 开关 | 值 | 理由 |
|---|---|---|
| `STUDIO_SKIP_STAGES` | `stylist`（editor 可选） | 省 1~2 次 LLM 调用 |
| `words_target` | `[200, 400]` | **真正的加速杠杆**——输出 token 大头是字数不是工序 |
| `audit_mode` | **保持 `strict`** | **测试模式下绝不放松闸门**，否则什么都测不出来 |

- **必须守住的红色底线**：

> **跳过工序 ≠ 跳过产物。**

  `sync` 硬要求 `beats + raw + final` 三件齐（实测：缺 raw 直接拒绝封存）。所以：
  - 跳过 Stylist → 必须 `cp raw_v2 → final`
  - 跳过 Editor+Stylist → 必须 `cp raw_v1 → final` **且** `cp raw_v1 → raw/ch_XXX_v2.md`
  - 因为 **final 是事实唯一源**（Reader 提案、audit 探针、字数闸门全以它为输入）

- **"事实等价的最小正文"原则**：测试关心的不是文笔，是"状态变更能不能被正确捕获"。只要正文**包含足够触发状态变更的事实**，200~400 字就够：

  > 必须包含：在场角色、地点/时间、至少一笔金额变动、至少一次道具使用、至少一条线的动作、一句可引用的事实句。

- **验证出口**：跑完 N 章后执行 `studio forensics`（②），机械断言 8 条不变量。

#### ⑨ 追踪：复用 `log/scorecard.jsonl`，不新造轮子

- harness 每章追加一行 `{ts, ch, ok, errors, warnings, by_code, skipped_stages, ...}`
- **收益**：`check --trend` **零改动**直接出 N 章曲线（现有 log 里 `scorecard.jsonl` 是唯一的可观测性落盘，其余 10 类都是审计/溯源）
- harness 自己的命令级 trace 写 `log/trace.jsonl`，不污染生产 log

#### ⑩ 清理：`state blame` 显示 `ch_ch_001`

`engine/commands/state_sync.py:1376` 的 `f"ch_{ev.get('ch')}"` 多套了一层前缀（`ev['ch']` 已是 `ch_001`）。一行修复。

---

## 三、预期收益汇总

| 层 | 改造前 | 改造后 | 倍数 |
|---|---:|---:|---:|
| **L0 引擎/契约（200 章规模）** | 写 200 章（数天）| **12 秒，0 token** | ∞ |
| **L1 代理协议（每章）** | 输入 ~46k / 输出 ~12.7k / 8 次调用 | 输入 **~17k** / 输出 **~3.5k** / **6 次调用** | 综合 **~3.5×** |
| **L2 成稿质量** | 每章全量 | **每 10 章抽样 1 章** | **10×** |
| **Drafter 单章上下文** | ~11 000 tok | **~6 000 tok** | 1.8×（且注意力更集中）|

---

## 四、执行顺序建议

```
Phase 1（0 token，先做）  ③ 修 derived → ① 故障注入 → ② forensics → ④ mutation 常态化
                          └ 这四件做完，引擎侧漏洞基本抓干净，且完全不烧 token
Phase 2（小成本）          ⑤ world_anchors 帽 → ⑦ 清死字段 → ⑥ beats 切片（待确认）
                          └ 这几件做完，生产模式的 token/注意力也降下来
Phase 3（测试模式本体）    ⑧ harness → ⑨ 追踪
                          └ 依赖前两阶段稳定，否则测出来的全是噪声
Phase 4（长期）            ⑩ 等修 bug 时顺手；每修一个 bug 补一个 mutation
```

**为什么这个顺序**：Phase 1 是零成本且立即可验证的，做完就能判断"值不值得继续"。
Phase 2 的 ⑤ 同时惠及生产模式——**它不是测试专用优化，是实打实的降本**。
Phase 3 放最后，因为 harness 跑出来的结果要有可信度，前提是引擎本身干净。

---

## 五、待确认事项

1. **Editor/Stylist 与 beats 的关系**：当前 SKILL 准读清单第 1 项就是 beats 全文。
   你的"不让它俩看 beats"是**想改成的目标**，还是**现状误记**？决定 ⑥ 做不做。
2. **`studio forensics` 的归属**：放 `engine/commands/` 会成为生产 CLI 的一部分
   （虽然只在测试文档里提及），还是放 `tests/` 下作为纯测试入口？
   倾向后者——**测试基建不该出现在生产命令目录里**，`studio.py help --json` 是给 Agent 看的命令目录。
3. **L2 抽样比例**：每 10 章 1 章全量，是否够？还是按卷（每 50 章）跑 3 章？

---

## 六、缺陷猎杀实绩（本轮新增）

> 方法：不猜，先用脚本把可疑处打到真的失败，再改。每条都配了回归测试 +
> `tests/mutation_guard.py` 的变异（把修复撤掉，测试必须红）。

| # | 缺陷 | 症状 | 修复 | 变异 |
|---|---|---|---|---|
| A | `derived` 封存必失败 | 派生表封存时写入 `null` 键，被 schema 拒收 → 每章 `⚠️ 派生封存异常` | `engine/objects/derive.py`：口径改为**省略该键**而非置 null | 13 / 14 |
| B | 变更日志章节键双前缀 | `state/derived.json` 的 `when` 写成 `ch_ch_001`，`blame`/溯源反查不到 | `state_sync.py:1377`：优先取 `ev["ch"]`（该字段本身已是 `ch_NNN`） | — |
| C | **符号链接跳板绕过角色白名单** | `open_file` 用 `os.path.normpath`（不跟随链接）判权限，`safe_child_path` 用 `Path.resolve()`（跟随）。把 `bible/06_style_guidelines.md` 换成指向 `state/ledger.json` 的符号链接，**只有 `bible/` 读权限的 editor 就能读到整本账本** | `engine/pack.py:open_file`：先 resolve，再回推相对路径，用**解析后**的路径过 `deny_reason`——检查你真正打开的那个文件 | 19 |
| D | **正文↔账本算术闸门对大额整段静默** | `checks.py` 的 `amount_arith_unverified` 数字字符集不含 `万/亿`：「灵石由三万变为五万」而账本记 `+30000`，`check` 全程 `ok`。而修仙题材里 灵石 过万才是常态——**这道闸门对绝大多数真实数额是关着的** | `_NUMPAT` 补 `万/亿` 并放宽长度；`_cn2int` 委托 `common.cn_to_int` | 22 |
| E | 中文数字把 `万/亿` 当普通单位扁平累加 | 三处各自为政的解析器：`十二万→20010`、`三十万→10030`、`一千万→11000`、`三亿→100000000` | 统一收敛到 `common.cn_to_int`（万/亿按「节」进位，内嵌阿拉伯数字串按裸数处理）；`audit`/`checks`/`evidence` 三处一律委托 | 21 / 23 / 24 |

| F | `engine/vocab.py` 三份 DEFAULT_* 词表**全无引用**（双份真相） | 注释写着「Checks 某某档的默认值」，但 `checks.py` 走 `proj.get(k)`、取不到就明确提示「未配置，该档已跳过」，**从不回落到 vocab**。真正的默认值住在 `templates/project.json`。其中 `DEFAULT_AI_TELL_WORDS` 是空表（注释「暂时缺省」），且 `PARAM_SPEC` 里根本没有 `ai_tell_words`——**配置面与代码面都不存在**，属未接线功能 | 删除三份死常量，并在 vocab 留下「唯一真相源是 templates/project.json」的说明；`checks` 不回落的行为保持不变（题材词表必须按题材配，套用通用玄幻表反而误报） | — |
| H | **Editor 的 SKILL 准读清单第 4 项 `characters/<在场角色>.md`：文档授权、网关拒收** | `engine/pack.py` 的 `ROLE_DENY["editor"]` 含 `characters/`，Agent 严格照 SKILL 执行必吃 `PermissionError`。且该 SKILL 自己的 §三.1 SOP 写的是「严格对照 **beats** 中的『现场在场角色动态称谓基准』」——三处口径里网关与 SOP 一致，只有准读清单是过期的（与 `bible/06` 同批修漏的那一条） | 按「文档错」修正：准读清单改为 3 项并删去角色卡，禁读清单显式写入 `characters/*`，并注明称谓/Want-Fear 一律以 beats 的称谓对校清单为准（Director 已预提炼，见 `templates/beats.md:88`） | 25 / 26 |
| G | `project.json` 死字段 `mode` | `"mode": "automatic"` 无任何逻辑消费，只有 `_book_brief` 回显，会误导 Agent 以为存在「自动模式」 | 模板 / init 默认值 / 回显三处一并删除 | — |

### 6.1 实测（DEFECT D，修前 → 修后）

| 正文 | 账本净变动 | 修前 | 修后 |
|---|---|---|---|
| 灵石由三十变为五十 | +30（应为 +20） | ✅ 报出 | ✅ 报出 |
| 灵石由三十变为五十 | +20（正确） | ✅ 静默 | ✅ 静默 |
| **灵石由三万变为五万** | **+30000（应为 +20000）** | ⚠️ **静默放行** | ✅ **报出** |
| 灵石由三万变为五万 | +20000（正确） | ⚠️ 静默 | ✅ 静默（非误报） |
| **灵石由一亿变为三亿** | **+300000000** | ⚠️ **静默放行** | ✅ **报出** |

### 6.2 方法论沉淀（踩过的坑，别再踩）

1. **探针权限必须走真入口。** 单独调 `deny_reason` + `safe_child_path` 会绕过网关，
   曾据此误判出一条不存在的「`..` 穿越白名单」漏洞。要用 `pack.open_file`。
2. **绕过测试可能是同义反复。** 变异 19 一度存活：符号链接放在 `bible/evil_link.md`，
   而 editor 的白名单前缀本来就拒 `bible/` 之外的路径——测试绿是因为别的原因。
   绕过类用例必须把恶意对象放在**白名单路径本身**上。
3. **测试产物看着像产品 bug。** 用脚本删掉 `bible/06_style_guidelines.md` 换成链接，
   会让「正常路径仍可读」的断言报 `ValueError`。两本书分开验证。
4. **测试绿了，可能是因为 bug 还在。** `test_sync_emits_proposal_events_and_seal`
   当初通过，正是因为派生封存坏掉、压根没产生派生事件。
5. **文档与代码的契约要双向钉死。** 新增 `tests/test_role_policy.py`：
   一边断言「SKILL 准读清单里的路径网关必须放行」，一边断言「测试表里的字面量在 SKILL 里还在」
   ——任一侧漂移都会红。它刚写完就立刻抓到我自己表里 librarian 的 `ch_{N-9..N}` 写成了 `ch_XXX`。
6. **别手搓变异注入。** 临时 `str.replace` 会静默 no-op，制造假的「已杀死」。
   用 `tests/mutation_guard.py`（锚点找不到会报 `SKIP`，并逐字节校验还原）。
