# Novel Studio (Antigravity Edition)

专为 **Google Antigravity** 深度定制的现代化网络小说多智能体创作框架。

> 📖 **核心宪法指引**：`AGENTS.md`  
> 🛠️ **创作技巧指南**：`agents/rules/novel_craft.md`  
> 🔄 **流水线执行标准**：`agents/rules/novel_workflow.md`

---

## 🌟 核心特色

1. **Antigravity 原生多智能体协同**：
   - **Director（主控）**：把控全局大纲、单章细纲与状态封存。
   - **Drafter（起草子代理）**：通过 `invoke_subagent` 独立沙箱起草情节自洽的初稿。
   - **Guard（重铸子代理）**：专业网文级全文精修重铸，消解 AI 味，拉满剧情张力。
2. **确定性状态机与防吃书机制**：
   - 人物图谱（`entities.json`）、伏笔/线索追踪（`lines.json`）、时间线（`timeline.json`）保障长篇连载不崩坏、不吃书。
3. **极速顺滑的创作流**：
   - 分层上下文打包（`pack`）、机械证据校验（`evidence`）、一键状态封存（`sync`）。

---

## 🚀 快速上手指令

```bash
# 1. 初始化新书（Stage 0）
python studio.py init -w workspace/我的小说 -t "书名" -g "题材" -p "主角名"

# 2. 查看当前进度与待办任务
python studio.py status

# 3. 准备当章上下文（自动聚合核心状态、实体与历史线索）
python studio.py pack ch_001

# 4. 辅助证据查询（线索缺口、字数统计、上一章约束对照）
python studio.py evidence gaps
python studio.py evidence words
python studio.py evidence prev ch_002

# 5. 全书与状态健康体检
python studio.py check

# 6. 一键状态同步与封存（Stage 4）
python studio.py sync ch_001

# 7. 全书导出与编译
python studio.py export --txt --views
```

---

## 📂 项目结构概览

```
NOVEL/
├── AGENTS.md                  # 核心宪法与智能体协同约定
├── studio.py                  # CLI 薄壳入口
├── engine/                    # 状态机与确定性校验引擎（纯 Python 标准库）
├── templates/                 # 设定、大纲、细纲模板库
├── agents/
│   ├── rules/
│   │   ├── novel_workflow.md  # 5 阶段工作流标准 SOP
│   │   └── novel_craft.md     # 商业网文技巧、反公式化与去 AI 味指南
│   ├── skills/                # Antigravity 标准技能（Director / Drafter / Guard）
│   └── genre_guide.md         # 题材类型与元素参考库
└── workspace/<书名>/          # 小说书稿工作区（大纲、设定、分卷草稿与状态真值）
```

 