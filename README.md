# Novel Studio 4.0 — 一键成书全自动引擎

Antigravity 原生多智能体中文网络小说创作工坊 **4.0 全面升级**：
**确定性 Python 超级引擎**（`engine/`，4.0 含 autopilot / generator / llm / healer / super_engine）+ **多智能体角色矩阵**（`AGENTS.md` 与 `.agents/skills/*/SKILL.md`）+ **全题材脚手架模板**（`templates/`）。

架构哲学 4.0：**一条命令从零到成书；引擎负责事实底座、自愈与数据台账；生成器负责创意脑洞与通俗叙事；全流程零人工干预。**

> 🎯 **核心升级**：3.x 需要 7 步手动接力（beats → pack → draft → edit → polish → audit → finalize → proposal → sync），4.0 只需 **1 条命令**。

---

## 🚀 一、 三十秒极速上手（4.0 一键成书）

```bash
# 1. 安装依赖（Python >= 3.10）
python -m pip install -r requirements.txt

# 2. 【超级命令】一条命令从零到成书 10 章（全自动）
python studio.py novel "我的新书" -g 玄幻 -p 林牧 --idea "废柴逆袭，以智破局" --chapters 10

# 3. 【极简开书】只开书不写（自动生成 bible/角色/大纲）
python studio.py create "我的新书" -g 都市 -p 陈凡 --idea "都市异能，扮猪吃虎"

# 4. 【单章全自动】已有书，单章全流程全自动
python studio.py write ch_001 -w "workspace/我的新书"

# 5. 【批量全自动】已有书，批量续写 N 章
python studio.py auto -w "workspace/我的新书" --chapters 5

# 6. 【智能运行】自动判断新书/续写
python studio.py run -t "我的新书" -g 玄幻 -p 林牧 --chapters 5
python studio.py run -w "workspace/我的新书" --chapters 5

# 7. 【零参数向导】直接双击或无参启动
python studio.py
# -> 进入交互式向导，问你书名/题材/主角/脑洞，确认后一键成书

# 8. 态势与体检（4.0 兼容 3.x 全量命令）
python studio.py status -w "workspace/我的新书"
python studio.py cockpit -w "workspace/我的新书"
python studio.py check -w "workspace/我的新书"
python studio.py heal -w "workspace/我的新书"   # 一键自愈
python studio.py help --json   # 全部命令 JSON
```

> 💡 **工作区约定**：书目录默认 `workspace/<书名>`。4.0 的 `novel`/`one`/`create`/`run` 会自动创建；`status` 单本书时可省略 `-w`。

---

## 🧠 二、 4.0 超级引擎架构

### 新增核心模块（engine/）

| 模块 | 职责 | 技术 |
|---|---|---|
| `autopilot.py` | 全自动驾驶：smart_init + run_chapter + run_batch + one_command，失败自愈重试 | 确定性编排 + 自愈 |
| `generator.py` | 智能内容生成器：6 题材 bible 模板、角色卡、大纲、细纲、正文 v1/v2/v3、audit/critic | 模板 + LLM 双轨 |
| `llm.py` | 可插拔 LLM 后端：auto 检测 OPENAI/ANTHROPIC，缺失则 Mock 离线生成，保证全流程可跑 | OpenAI / Anthropic / Mock |
| `healer.py` | 自愈引擎：派生表重算、账本校验、孤立提案清理、索引刷新、快照保护 | 零 Token 纯确定性 |
| `super_engine.py` | 超级引擎聚合：SuperEngine 类统一入口，one_command/auto_write/heal/status/export | Facade 模式 |
| `commands/autopilot.py` | 4.0 CLI 命令：novel/one/create/write/auto/run | CLI 层 |

### 4.0 命令全景（新增 7 个超级命令）

```text
🚀 4.0 一键成书
  novel "书名" -g 玄幻 -p 主角 --idea 脑洞 --chapters 10   # 从零到成书
  one   同 novel 别名
  create "书名" -g 玄幻 -p 主角 --idea 脑洞                # 极简开书
  write ch_001 -w 书目录                                    # 单章全自动
  auto -w 书目录 --chapters 5                               # 批量全自动
  run -t 书名 -g 玄幻 --chapters 5                          # 智能运行
  heal -w 书目录 --deep                                     # 一键自愈
```

### 3.x 兼容命令（31 个原有命令 100% 保留）

`status` / `init` / `cockpit` / `pack` / `ask` / `pov` / `calendar` / `evidence` / `index` / `check` / `doctor` / `checkpoint` / `state` / `config` / `sync` / `snapshot` / `export` / `proposal` / `review` / `beats` / `critic` / `graph` / `errcodes` / `help` / `audit` / `finalize` / `recall` / `simulate` / `milestone` / `lore` / `reconcile`

---

## 📖 三、 创作流水线（4.0 双模式）

### 模式 A：4.0 一键成书（推荐，新手）

```mermaid
flowchart LR
    User[一句话] --> Novel[python studio.py novel 书名 --chapters 10]
    Novel --> Init[smart_init: bible+角色+大纲]
    Init --> Loop[run_batch: 批量全自动]
    Loop --> Beats[beats 自动]
    Beats --> Pack[pack 自动]
    Pack --> Draft[draft v1/v2/v3 自动]
    Draft --> Audit[audit+critic 自动]
    Audit --> Final[finalize+proposal+sync 自动]
    Final --> Export[export 自动]
    Export --> Done[成书]
```

**全程 1 条命令，中间零人工干预，失败自愈重试。**

### 模式 B：3.x 精雕流水线（兼容，专家）

| 阶段 | 角色 | 职责 | 产出 |
|---|---|---|---|
| Stage 0 | Architect | 筑基 | bible/, characters/, outlines/, state/ |
| Stage 1 | Director | 细纲 | beats + pack.md |
| Stage 2 | Drafter | 毛坯 | raw v1 |
| Stage 3A | Editor | 脱水 | raw v2 |
| Stage 3B | Polisher | 抛光 | raw v3 |
| Stage 4A/4B | Auditor/Critic | 双并发质检 | audit + critic |
| Stage 5 | Director/Engine | 原子收口 | final + proposal + sync + 快照 |

---

## 🗂️ 四、 工作区文件地图

```text
workspace/<书名>/
├── project.json              # 含 idea 字段（4.0 新增）
├── pack.md
├── bible/                    # 6 份，4.0 按题材智能生成
├── characters/               # 3+ 份，含 Want/Fear/微动作
├── entities/
├── outlines/
│   ├── main_plot.md
│   └── vol_XX/outline.md + beats/ch_XXX.md（4.0 自动生成）
├── manuscript/vol_XX/
│   ├── raw/ch_XXX_v1/v2/v3.md
│   └── final/ch_XXX.md
├── state/                    # 十一表 + 快照
├── log/audit/ + critic/
└── export/<书名>.txt         # 4.0 自动导出
```

---

## ⚙️ 五、 4.0 核心原则

1. **一条命令成书**：`novel`/`one`/`run` 从零到成书，无需手动 beats/pack/finalize。
2. **功能强大，使用简单**：引擎内部自愈、重算、索引、导出全自动；外部接口极简。
3. **离线可用，LLM 可插拔**：无 API Key 时 Mock 生成器保证跑通；有 OPENAI_API_KEY 自动升级文笔。
4. **事实与创作分离**：final 为源头，state 为真值，提案为唯一写入口，双键 ID 防分裂。
5. **自愈与自检**：`heal` 一键修复派生表/账本/索引/孤立提案；`check` 0 errors 放行。

---

## 📚 六、 命令速查（Cheat Sheet 4.0）

| 场景 | 4.0 命令 | 说明 |
|---|---|---|
| 一键成书 | `novel "书名" -g 玄幻 -p 林牧 --idea "脑洞" --chapters 10` | 从零到 10 章 |
| 极简开书 | `create "书名" -g 都市 -p 陈凡 --idea "异能"` | 只筑基 |
| 单章全自动 | `write ch_001 -w workspace/书名` | 单章全流程 |
| 批量续写 | `auto -w workspace/书名 --chapters 5` | 批量 N 章 |
| 智能运行 | `run -t "书名" -g 玄幻 --chapters 5` | 自动判断 |
| 零参数向导 | `python studio.py` | 交互式 |
| 自愈 | `heal -w workspace/书名 --deep` | 一键修复 |
| 状态 | `status -w workspace/书名` | 进度总览 |
| 驾驶舱 | `cockpit -w workspace/书名` | 态势 + 伏笔 |
| 体检 | `check -w workspace/书名` | 0 errors 放行 |
| 问书 | `ask "关键词" -w workspace/书名` | 事实检索 |
| 导出 | `export --txt -w workspace/书名` | 导出 txt |

3.x 全量命令见 `docs/COMMAND_MATRIX.md`，实战配方见 `python studio.py help`。

---

## 🔧 七、 LLM 配置（可选）

```bash
# OpenAI（自动检测）
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o-mini   # 可选

# Anthropic
export ANTHROPIC_API_KEY=...

# 无 Key 时自动 Mock，离线可跑
python studio.py novel "测试书" --chapters 2   # Mock 也能成书
```

---

## 🛡️ 八、 退出码契约

- `0` 正常通过
- `1` 业务阻断（check errors / sync 失败 / 成书未完全）
- `2` 用法错误
- `3` 环境缺依赖

---

## 📄 九、 许可

MIT License，见 LICENSE。

---

## 🎉 十、 4.0 升级亮点总结

- **从 7 步到 1 步**：`novel` 一条命令完成 init + bible + 角色 + 大纲 + N 章正文 + 导出
- **从手动到全自动**：beats/pack/draft/edit/polish/audit/critic/finalize/proposal/sync 全自动
- **从易错到自愈**：heal 自动修复，batch 失败自动重试
- **从单一到全题材**：玄幻/都市/科幻/悬疑/历史/仙侠 6 套模板
- **从在线到离线**：Mock 离线可跑，LLM 在线升级
- **从复杂到极简**：`python studio.py` 零参数向导，小白也能成书
