# Novel Studio (Antigravity Edition)

专为 **Google Antigravity** 深度定制的现代化小说创作多智能体流水线框架（通用于玄幻、都市、悬疑、科幻、言情、武侠、无限流等全题材）。
全面适配 Gemini  Flash 系列模型 认知特性，发挥算力与长上下文优势，打造高创意、强张力、流畅好读的商业级优质作品。

> 📖 **核心宪法指引**：`AGENTS.md`  
> 🛠️ **创作工艺总纲**：`.agents/rules/novel_craft.md`  
> 🔄 **流水线执行标准 (SOP)**：`.agents/rules/novel_workflow.md`  
> 🧐 **老白读者评测标准**：`.agents/rules/craft_critic.md`

---

## 🌟 核心特色 (Novel Studio 3.1)

1. **原生多智能体流转合并（一步到位全自动流水线）**：
   - **Director（主控 · Stage 0 / 1 / 5）**：全局统筹世界观与分卷主线；端到端自动化连续调度 Drafter → Editor → Reader/Critic；依据 Critic 评测做风控闸门（**不合格直接打回 Editor 重做**）；审定提案并闭环封存状态机。
   - **Drafter（起草子代理 · Stage 2）**：彻底松绑想象力与算力，承接上章情境与上章 Critic 剧情建议，篇幅在 2000~6000+ 汉字自由舒展，以鲜活的对白音色与微波澜小拉扯起草高能毛坯初稿 `raw/`。
   - **Editor（精修重塑子代理 · Stage 3）**：文学重塑与定稿总笔，拒绝机械截肢，在 2000~6000+ 汉字自由舒展，实施“物理刀口截断”，产出极具阅读爽感的纯净定稿 `final/`。
   - **Reader（事实审计子代理 · Stage 4 轨A）**：严谨提炼 5 大客观事实，直接装配标准增量提案 JSON (`state/inbox/`)。
   - **Critic（老白毒舌评测子代理 · Stage 4 轨B）**：扮演十年老白书虫，与 Reader **并发运行（零时延重叠）**，产出 `log/critic/` 专供 Director 自闭环裁决（**人类作者免打扰，仅负责最终 final 终审**）。
2. **强类型数据模型与确定性引擎（Pydantic V2 + 语义原子补丁）**：
   - 采用 Pydantic V2 构建严格的领域实体、复式记账与时空线索模型，支持语义原子补丁（SemanticEntityPatch），彻底规避数组下标漂移。
3. **轻量强援赋能本地 Engine（各司其职，坚决不越界）**：
   - **`jieba`**：词性标注抽取专有名词候选（人名/地名/门派）与单章高频词口癖雷达；
   - **`networkx`**：构建实体关系拓扑与叙事中介中心度分析，实现 1-Hop 强相关子图动态剪枝与破局路径寻路（`studio graph`）；
   - **`rapidfuzz`**：90% 局部相似度柔性引文接地容错，消除模型漏抄语气助词导致的硬拦截假阳性；
   - **`rich`**：终端渲染高保真圆角面板、彩色老白评分卡与状态流程表。

---

## 🚀 常用生产指令 (CLI)

```bash
# 1. 初始化新书（Stage 0）
python studio.py init -w workspace/我的小说 -t "书名" -g "题材" -p "主角名"

# 2. 查看当前创作进度与各章状态
python studio.py status

# 3. 智能生成当章细纲任务书脚手架（Stage 1：自动注入阶段目标、上章现场、到期伏笔与情绪蓄水模式）
python studio.py beats new ch_003 --write

# 4. 准备当章上下文（P0现场 + P1基于NetworkX拓扑剪枝的触发实体 + P2冷索引）
python studio.py pack ch_003

# 5. 实体拓扑沙盘与破局寻路（NetworkX 强力赋能）
python studio.py graph path 李玄 赵管事     # 计算两实体间最短破局跳板/人情链路
python studio.py graph isolated             # 一键排查全书孤立/边缘资产（防人物与宝物烂尾）
python studio.py graph centrality           # 计算全书角色与线索的剧情中介枢纽度排名
python studio.py graph neighbors 李玄       # 探查任意实体的 1-Hop/2-Hop 关联网络

# 6. 辅助证据与样式雷达（词频口癖分析、线索缺口、字数统计）
python studio.py evidence style
python studio.py evidence gaps

# 7. 查看老白读者毒舌评测评分卡（Stage 4 并行质检）
python studio.py critic ch_001

# 8. 全书与状态健康体检（伏笔饥饿告警、Schema 校验、章号断档检查）
python studio.py check

# 9. 审定提案并一键状态同步归档（Stage 5）
python studio.py sync ch_001

# 10. 生成全景交互看板 HTML（人物关系网/伏笔看板/情绪心电图）
python studio.py dashboard

# 11. 全书编译与正文导出
python studio.py export --txt --views
```

---

## 📂 项目结构概览

```
NOVEL/
├── AGENTS.md                  # 核心宪法（定义 5 大角色分工与 Stage 0-5 双轨工序）
├── studio.py                  # CLI 薄壳入口（共 18 个生产指令）
├── pyproject.toml             # 工程配置与环境依赖（pydantic, jieba, networkx, rich, rapidfuzz）
├── engine/                    # 状态机与确定性校验引擎
│   ├── models/                # Pydantic V2 强类型领域模型包
│   ├── cli.py                 # CLI 编排与 Rich 现代化终端呈现
│   ├── graph.py               # 实体拓扑与叙事破局寻路（studio graph）
│   ├── dashboard.py           # 交互式全景看板 HTML 导出
│   ├── common.py              # 原子写保护、Windows重试与路径安全
│   ├── checks.py              # 叙事 AST 编译器断言与引文接地容错
│   ├── pack.py                # 上下文装配与 NetworkX 1-Hop 依赖图剪枝
│   ├── evidence.py            # 机械证据与 Jieba 专名/词频分析
│   └── state.py               # 复式账本校验与状态原子合并
├── templates/                 # 设定、大纲与动态细纲模板库
│   └── beats.md               # 包含情绪流体力学与感官预算的细纲模板
├── .agents/                   # Antigravity 工作区定制
│   ├── rules/                 # 核心工作流与角色工艺规范 (craft_drafter, craft_editor, craft_critic...)
│   └── skills/                # 智能体技能卡 (Director, Drafter, Editor, Reader, Critic)
└── workspace/<书名>/          # 小说书稿工作区（设定、草稿、定稿与状态真值）
```