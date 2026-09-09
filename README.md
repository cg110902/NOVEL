# Novel Studio 3.1

Antigravity 原生多智能体中文网络小说创作流水线：**确定性 Python 引擎**（`engine/`，黑盒）
+ **角色协议文档**（`AGENTS.md` 与 `.agents/skills/*/SKILL.md`）+ **模板资产**（`templates/`）。

分工原则：能算的一律由引擎算（状态机、账本重算、事实体检、上下文装配），
需要判断力的才交给子代理（写细纲、写正文、裁决矛盾）。

---

## 一、三十秒上手

```bash
# 1. 安装依赖（Python >= 3.10）
pip install -r requirements.txt

# 2. 建一本书（书目录必须在工作区根之下）
python studio.py init -w workspace/我的书 -t 我的书 -g 仙侠 -p 主角名

# 3. 主控自查：命令目录 / 阶段配方 / 退出码契约的唯一入口
python studio.py help --json

# 4. 态势驾驶舱：当前工序指针 + 下一步该派谁 + 自愈处方
python studio.py cockpit -w workspace/我的书

# 5. 事实体检（有 errors 退出码 1）
python studio.py check -w workspace/我的书
```

工作区根默认是 `<repo>/workspace`；用环境变量 `NOVEL_STUDIO_WORKSPACE_ROOT` 可重定向
（测试与多书并行时用它隔离）。所有命令都用 `-w <书目录>` 指定书，缺省只在「工作区里恰好一本书」时才自动选中。

---

## 二、流水线一图流

```
Stage 0A/0B  Architect   世界观公理 + 人物大纲 + 八表播种（设定层直写）
Stage 1      Director    细纲构思 beats（引擎注入一致性速查 / 资源池键名 / ID 水位线）
Stage 2      Drafter     初稿 raw_v1
Stage 3A     Editor      骨肉重塑 raw_v2
Stage 3B     Stylist     通俗脱水 final（全书唯一法定定稿）
Stage 4A     Reader      事实提案 state/inbox/ch_XXX.json
Stage 4B     Critic      老白催更便签 log/critic/ch_XXX.md
Stage 4C     Auditor     一致性仲裁 log/audit/ch_XXX.md（带 front-matter，Stage 5 硬闸门）
Stage 4D     Librarian   每 10 章长程巡检（近 10 章定稿 vs 四张台账平账）
Stage 5      Director    sync：提案合并 + 八表盖章 + 快照封存
Evolution    Evolver     人类变更诉求的波及面测算与手术刀改版
```

完整流程图、派发令/回执单格式、各角色准读准写清单见 **`AGENTS.md`**；
每个角色的工艺纪律见 **`.agents/skills/<角色>/SKILL.md`**。

---

## 三、目录导航

| 路径 | 内容 |
|---|---|
| `studio.py` | CLI 入口薄壳 |
| `engine/` | 确定性引擎（状态机 / 体检 / 审计探针 / 上下文装配 / 图谱 / 索引） |
| `engine/README.md` | 引擎模块地图与 lore 系列速查说明 |
| `engine/schemas/*.json` | 由 `engine/models/schema_gen.py` 从 Pydantic 模型生成，勿手改 |
| `AGENTS.md` | 主控章程：流水线、角色矩阵、工序协议、目录契约 |
| `.agents/skills/*/SKILL.md` | 10 个角色的技能卡（准读/准写/工艺/回执） |
| `templates/` | 建书脚手架：bible 七表、人物卡、大纲、beats、`project.json` |
| `templates/README.md` | 模板字段逐项说明（与 Pydantic 模型同口径） |
| `tests/` | stdlib `unittest` 回归测试 |
| `requirements.txt` | 运行时依赖（与 `pyproject.toml` 同源） |

书工作区（`workspace/<书名>/`）内的目录契约：

| 路径 | 内容 |
|---|---|
| `project.json` | 书级参数（题材、主角、字数目标带、词表旋钮） |
| `bible/01..07` | 世界圣经七表（公理/战力/势力地理/经济道具/特殊机制/文风宪法/偏离清单） |
| `characters/`、`entities/` | 人物卡与实体卡 |
| `outlines/` | 主线大纲 + 分卷大纲 + `beats/ch_XXX.md` 细纲任务书 |
| `manuscript/vol_XX/{raw,final}/` | 毛坯 `_v1` / 初修 `_v2` / 法定定稿 |
| `state/*.json` | 八表真值：current / entities / lines / timeline / ledger / synopsis / locked / cognition |
| `state/inbox/` | 提案收件箱（`processed/` 为审计留痕，永不删改） |
| `log/{audit,critic,review}/` | 仲裁报告 / 催更便签 / 校对与巡检报告 |
| `snapshots/` | 快照与回滚点 |

---

## 四、八表真值与写入口

`state/*.json` 八张表是机器真值，读写都过 `engine/schemas/` 的声明式校验。

- **章节事实增量的唯一写入口是提案**：Reader 落盘 `state/inbox/ch_XXX.json` →
  主控 `python studio.py sync ch_XXX`（支持 `--dry-run` 预演）→ 过 schema 校验、
  引文柔性接地、幂等登记、复式记账重算四道闸才落盘。
- **设定层例外**：Stage 0 建书播种与跨卷改版由 Architect/Evolver 直接写 `state/*.json`。
- **机械证据**：每次 `sync` 对八表盖章 SHA-256（`state/inbox/processed/state_hashes.json`），
  绕过提案的离线手改由 `check` 的 `state_offline_edit` 档指名报出；
- **事件溯源**：`state/changelog.jsonl` 记录八表字段级变更事件流（谁、哪章、哪个通道、
  把哪个路径从什么改成什么），由引擎在唯一写入咽喉自动派生、离线手改自动补录、
  快照回滚不清空历史——`fold(基线, 事件) == 磁盘` 是其对账不变量。
- **账本口径**：余额永远由流水重算，`balance_after` / `current` 不是可信输入字段。
- **改史留痕**：不可逆事实（locked）与角色认知（cognition）禁止同 ID 静默覆盖——
  幂等重放放行，改写历史需 `action="retire"` 或显式 `"overwrite": true`。

提案字段契约的逐项说明见书工作区内的 `state/inbox/README.md`（由 `init` 生成）。

---

## 五、常用命令

| 场景 | 命令 |
|---|---|
| 命令目录与阶段配方 | `python studio.py help --json` |
| 工作区/工序总览 | `python studio.py status` · `cockpit [ch]` |
| 单章上下文装配 | `python studio.py pack ch_XXX [--lean|--full] [--open 路径 --as 角色]` |
| 只读取证 | `python studio.py ask <关键词>` · `evidence <kind>` · `pov` · `calendar` |
| 细纲与稿件流转 | `beats new ch_XXX --write` · `critic` · `audit ch_XXX --write` · `reconcile vol_XX`（卷末对账） |
| 提案 | `proposal check ch_XXX` · `proposal auto ch_XXX --write` · `sync ch_XXX [--dry-run]` |
| 体检与自愈 | `check`（`doctor` 为其别名；`--trend` 分数曲线 / `--bisect` 快照二分） · `errcodes <码>` |
| 图谱与索引 | `graph <action>` · `index [--rebuild]` · `recall` · `simulate` |
| 台账手术刀 | `state get/set` · `state at <章>`（时点切面）· `state diff <章A> <章B>` · `state blame <表.路径>`（字段级溯源） · `state rollup vol_XX`（卷末态势摘要，pack 前情注入源） · `ledger recompute` · `milestone add/achieve` |
| 快照 | `snapshot create/list/rollback` · `checkpoint` |

`--as <角色>` 的准读清单与各角色 SKILL.md 的准读清单一一对应（单一真源在
`engine/pack.py` 的 `ROLE_DENY` / `ROLE_ALLOW_EXTRA`）；越权读取一律拒绝。

退出码契约：`0` = 正常 / `1` = 阻断（含 `check` 有 errors、`sync` 失败）/ `2` = 用法错 /
`3` = 运行环境缺依赖（会打印缺失模块与安装命令，不抛裸 traceback）。
错误码的机器可读说明书：`python studio.py errcodes <码>`（注册表在 `engine/errcodes.py`）。

---

## 六、测试

```bash
python -m unittest discover -s tests -v
```

测试用 `tempfile` + `NOVEL_STUDIO_WORKSPACE_ROOT` 建隔离书工作区，不碰仓库里的 `workspace/`。
覆盖范围包括：证据统计与候选噪声门控、locked/cognition 防静默覆盖、仲裁报告合并（保留/回落裁决）、
YAML front-matter 引号键解析、引擎不自触发闸门、`type=location` 与 `place` 同等地位、
字数出带判定、角色读权限网关、state 盖章与离线改动检出、驾驶舱 3A/3B/4C 指针、
beats 资源池与 ID 水位线注入、错误码注册表完备性、枚举单一真源。

---

## 七、开发约定

- `engine/schemas/*.json` 由 `python -m engine.models.schema_gen` 生成；改模型后重跑，
  仓库里不应出现漂移。
- 枚举与类型集合一律从 Pydantic 模型派生（如 `LOCATION_TYPES`、`state._ATTITUDE`），
  禁止在校验分支里再手写字面量集合。
- 新增 `check` 错误码必须在 `engine/errcodes.py` 注册（`tests` 会当场报警）。
- 用户可见文案里的数量口径（命令数、状态表数、字段数）改动时，同步更新
  `AGENTS.md` / `engine/README.md` / `templates/README.md`。
