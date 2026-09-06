# novel-studio（Novel Studio 3.1）

Antigravity 原生多智能体长篇商业小说创作流水线框架（全题材通用）：
**大模型全权掌控创意与文学重塑；确定性引擎（`engine/`）负责事实底座与数据台账；
原生子代理（`.agents/skills/`）实现工序接力与闭环归档。**

## 快速开始

```bash
python3.11 -m venv .venv-novel && .venv-novel/bin/pip install -e ".[dev]"
.venv-novel/bin/python studio.py init -w /path/to/book -t 书名 -g 题材 -p 主角   # 脚手架 + 5 份模板实例化
.venv-novel/bin/python studio.py help          # 阶段配方与全部命令速查
.venv-novel/bin/python studio.py help --json   # 命令目录机器可读（Agent 首选）
.venv-novel/bin/python studio.py check -w /path/to/book   # 事实体检（E0 = 全绿）
```

全部命令需在书目录所在工作区内运行：`-w <书目录>` 指定目标书（单书可省）。
退出码契约：`0` 成功 ｜ `1` 业务阻断 ｜ `2` 用法错误。

## 文档体系（各司其职）

| 文档 | 受众 | 内容 |
|---|---|---|
| `AGENTS.md` | AI 主控 + 全部角色 | 核心宪法：角色矩阵、工序流水线（Stage 0–5）、准读/禁读清单、状态写入纪律 |
| `.agents/skills/` | 各子代理 | 岗位自完备技能卡（reader / drafter / editor / critic / auditor / librarian / director） |
| `engine/README.md` | 引擎开发者 | 模块职责、输出契约、幂等语义、校验单一真源（Pydantic 模型 → schema 构建产物） |
| `docs/QA-REPORT.md` | 维护者 | 全面 QA 报告：修复清单、压力/规模/自愈/CLI 契约矩阵、已知设计行为、运行指引 |
| `qa/README.md` + `qa/scripts/` | 维护者 | 可复现 QA 资产：压力书生成、规模炮台、CLI 契约回归脚本与原始证据 |

## 核心机制一句话

- **事实与创作分离**：事实唯一源头 = `manuscript/*/final/ch_XXX.md` 定稿正文；状态唯一真值 = `state/` 八表；二者经 Stage 4 审计提案 → Stage 5 `sync` 原子合并。
- **提案单文件制**：每章在途提案仅一份 `state/inbox/ch_XXX.json`（`novel-studio.state-mutation/v2`）；过 schema 校验、引文柔性接地、幂等登记、复式记账重算四道闸后落盘。
- **只读取证三件套**：`studio ask` / `pov` / `calendar`——写作前取证严禁凭记忆脑补。

## 测试

```bash
PYTHONUTF8=1 NOVEL_STUDIO_WORKSPACE_ROOT=/tmp/qa_root .venv-novel/bin/python -m pytest tests/ -q
# 146 passed（约 4.5 分钟；用例经 subprocess 调 studio.py，慢属正常）
```

## 结构速览

```
AGENTS.md             # AI 宪法（入口文档）
engine/               # 确定性引擎（cli 薄壳 + commands/ + 状态机 + 图/检索/审计）
templates/            # init 实例化的创作模板（project_bible / style / main_plot / volume_outline / character_card / beats / reader_review）
tests/                # 全量回归（146 passed，含 CLI 契约 / 提案 schema / 审计注入 / 探针类断言 / 多卷邻前章）
qa/                   # QA 可复现资产（脚本 + 原始报告）
docs/QA-REPORT.md     # 全面测试报告
```
