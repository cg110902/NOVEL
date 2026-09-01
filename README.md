# Novel Studio (Antigravity Edition)

专为 **Google Antigravity** 深度定制的现代化小说创作多智能体流水线框架（通用于玄幻、都市、悬疑、科幻、言情、武侠、无限流等全题材）。
全面适配 Gemini 认知特性，发挥算力与长上下文优势，打造高创意、强张力、流畅好读的优质作品。

> 📖 **核心宪法指引**：`AGENTS.md`  
> 🛠️ **创作工艺指南**：`.agents/rules/novel_craft.md`  
> 🔄 **流水线执行标准**：`.agents/rules/novel_workflow.md`

---

## 🌟 核心特色

1. **Gemini 深度适配与原生多智能体协同**：
   - **Director（主控）**：全局统筹世界观、分卷主线，装配当章核心利益死结与细纲任务，闭环管理状态机。
   - **Drafter（起草子代理 · Stage 2）**：彻底放飞算力与想象力，无缝承接前章情境，以“动作化推进（Action First）”和“生动对白机锋”起草高能毛坯初稿 `raw/`。
   - **Guard（重铸子代理 · Stage 3）**：文学重塑与定稿总笔，剪裁冗长脑内反思，实施“物理刀口截断（坚决阻断事后说教升华）”，产出极具阅读爽感的纯净定稿 `final/`。
   - **Reader（评审与审计子代理 · Stage 3.5）**：真实读者读感反馈与微瑕修剪，利用强大长上下文提取力客观提炼 300~600 字结构化事实简报。
2. **确定性状态机与防吃书机制**：
   - 实体图谱（`entities.json`）、伏笔多态台账（`lines.json`）、现场状态（`current.json`）保障长篇连载不崩坏、不吃书。
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
├── templates/                 # 设定、大纲、动态细纲模板库
├── .agents/                   # Antigravity 工作区级智能体定制目录
│   ├── rules/
│   │   ├── novel_workflow.md  # 创作流水线标准 SOP
│   │   ├── novel_craft.md     # Gemini 深度适配创作工艺总纲
│   │   ├── craft_drafter.md   # 初稿起草指南（Drafter 专版）
│   │   ├── craft_guard.md     # 文学重塑与定稿指南（Guard 专版）
│   │   └── craft_reader.md    # 读者反馈与事实审计规范（Reader 专版）
│   ├── skills/                # Antigravity 标准技能（Director / Drafter / Guard / Reader）
│
└── workspace/<书名>/          # 小说书稿工作区（大纲、设定、分卷草稿与状态真值）
```