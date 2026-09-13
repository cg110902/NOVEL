# Novel Studio 3.3

Antigravity 原生多智能体中文网络小说创作工坊：**确定性 Python 引擎**（`engine/`，黑盒）
+ **多智能体角色矩阵**（`AGENTS.md` 与 `.agents/skills/*/SKILL.md`）+ **全题材脚手架模板**（`templates/`）。

架构哲学：**大模型全权掌控创意脑洞、生动情节与通俗叙事；确定性引擎负责事实底座与数据台账；原生 Subagents 实现高效工序接力与闭环归档。**

---

## 一、 三十秒极速上手

```bash
# 1. 安装依赖（Python >= 3.10）
python -m pip install -r requirements.txt

# 2. 开建新书（书目录位于 workspace/ 下）
python studio.py init -w "workspace/我的新书" -t "我的新书" -g "玄幻" -p "林牧"

# 3. 态势驾驶舱：查看当前工序指针、下一步该派谁与态势自检
python studio.py cockpit -w "workspace/我的新书"

# 4. 事实体检：全息一致性扫描（退出码 0 为绿灯）
python studio.py check -w "workspace/我的新书"

# 5. CLI 帮助与阶段配方查阅唯一入口
python studio.py help --json
```

> 💡 **工作区约定**：书目录默认位于 `<repo>/workspace/<书名>` 下。所有 CLI 均使用 `-w "workspace/<书名>"` 指定目标书籍。

---

## 二、 创作工序流水线一图流

全流程实行**极简工业流水线**，各角色分工明确、单步物理落盘、极速咬合：

| 阶段 | 角色 | 算力模型 | 核心职责 | 产出物 |
|---|---|---|---|---|
| **Stage 0** | **Architect** | `inherit` | 开局世界公理筑基 (0A)、人物大纲通电 (0B) 与全息对账 (0C) | `bible/`, `characters/`, `outlines/`, `state/` |
| **Stage 1** | **Director** | `inherit` | 前瞻研判、细纲任务书编织与当章事实变更预期前置声明 | `outlines/vol_XX/beats/ch_XXX.md` |
| **Stage 2** | **Drafter** | `inherit` | 100% 依据 pack 上下文展开，通俗大白话撰写高张力初稿毛坯（仅跑1次pack） | `manuscript/vol_XX/raw/ch_XXX_v1.md` |
| **Stage 3** | **Editor** | `inherit` | 双核手术刀精修与脱水一体化（总控预置底稿，纯读写【绝对零命令】） | `manuscript/vol_XX/raw/ch_XXX_v3.md` |
| **Stage 4A** | **Auditor** | `inherit` | 常识与出戏审查，预制修补配方（总控预置探针骨架，纯读写【绝对零命令】） | `log/audit/ch_XXX.md` |
| **Stage 4B** | **Critic** | `flash` | 资深老白读者纯盲审，评估阅读疲劳度与活人感，输出下章催更便签（【绝对零命令】） | `log/critic/ch_XXX.md` |
| **Stage 5** | **Director / Engine** | `inherit` | 极速三连原子收口：`finalize` 自动定稿盖章 ➔ `proposal auto` 动态事实入账 ➔ `sync` 封存（≤0.5秒） | `final/ch_XXX.md`, `state/*.json` |
| **低频巡检** | **Librarian** | `flash` | 每 10 章事实深层巡检打捞遗漏次要实体；卷末执行对账大修（纯Markdown对账单） | `log/review/` |
| **演进重构** | **Evolver** | `inherit` | 中途随时接诊人类作者变更诉求（改设定/人设/历史正文），快照先行平账 | 全局受控范围 |

---

## 三、 工作区文件地图 (`workspace/<书名>/`)

```text
workspace/<书名>/
├── project.json              # 书级配置：题材/主角/字数带/敏感词与启发词/线索配额
├── bible/                    # 设定真理圣经（模块化物理底座，支持 SHA-256 漂移自检）
│   ├── 01_world_axioms.md    # 世界运转公理与空间/金手指法则
│   ├── 02_power_system.md    # 实力/位阶层级与物理破坏力标尺
│   ├── 03_factions_geography.md # 地缘政治分布与核心势力拓扑
│   ├── 04_economy_items.md   # 货币购买力锚点与消耗品分级法则
│   ├── 05_special_mechanics.md  # 题材专属机制/体质/血脉/阵营相克
│   └── 06_deviations.md      # 本书绝对偏离清单（严禁触碰的套路红线）
├── characters/               # 核心人物档案（闭环称谓对校矩阵、微动作、Want/Fear）
│   ├── protagonist.md        # 主角终极档案 (ID: p_001)
│   └── <角色名>.md           # 重要配角/女主/男配/反派标准卡
├── entities/                 # 核心三态实体账册（支持 CLI 穿透寻路与对账）
│   ├── items/                # 法宝/装备/重器卡（损耗/充能/权属生命周期）
│   ├── factions/             # 宗门/组织/集团卡（核心资产/外交敌友态势）
│   └── locations/            # 关节点/据点/场景卡（感官锚点/运转律则/足迹）
├── outlines/
│   ├── main_plot.md          # 全书脊柱（故事引擎与宏观里程碑）
│   └── vol_XX/
│       ├── outline.md        # 分卷大纲（四分位阶段航标；总控可动态修纲）
│       └── beats/ch_XXX.md   # 当章细纲任务书（含法定事实与预期变更声明）
├── manuscript/vol_XX/
│   ├── raw/
│   │   ├── ch_XXX_v1.md      # 初稿毛坯（Stage 2 Drafter 产出）
│   │   └── ch_XXX_v3.md      # 精修脱水预定稿（Stage 3 Editor 产出，双核加肉脱水一体化）
│   └── final/ch_XXX.md        # 终局法定定稿（Stage 5 finalize 自动定稿并盖章）
├── state/                    # 十一表真值（含 locked/cognition） + inbox/ 提案收件箱 + snapshots/ 快照
│   ├── rollups/              # 卷级态势折叠（vol_XX.json，供跨卷装配）
│   └── inbox/ch_XXX.json     # 章节增量提案（Stage 5 proposal auto 自动提取）
├── log/
│   ├── audit/ch_XXX.md       # 质检仲裁报告（Stage 4A 初评，Stage 5 finalize 自动套用盖章）
│   ├── critic/ch_XXX.md      # 老白催更便签（Stage 4B Critic 产出，供下章细纲参考）
│   ├── branches/ch_XXX.md    # 分支参谋单（可选）
│   └── review/               # 校对注记 + Librarian 长程巡检报告 sweep_ch_XXX.md
└── export/                   # 全书编译产物（--txt / --views 状态视图）
```

---

## 四、 核心原则与状态写入口

1. **事实与创作分离**：
   - 创作可以脑补，事实必须对账。
   - **事实唯一源头** = `final/ch_XXX.md` 定稿正文。
   - **状态唯一真值** = `state/` 十一表真值（current, persons, items, factions, places, lines, timeline, ledger, synopsis, locked, cognition）。
2. **章节事实增量的唯一写入口是提案**：
   - Stage 5 运行 `python studio.py proposal auto ch_XXX --write` 自动抽取增量事实；
   - 运行 `python studio.py sync ch_XXX` 完成原子封存与快照归档。
3. **双键唯一物理 ID 体系**：
   - 角色：`p_001`（主角恒定为 `p_001`）、`p_002`...
   - 物品：`it_001`... ｜ 势力：`fac_001`... ｜ 地点：`loc_001`...
   - 双键合并优先按 `id` 寻址，就地更新属性，绝不分裂实体。
4. **质检闭环与终审定稿**：
   - Stage 4A Auditor 单次全读生成出戏清单与修补配方（纯认知审查，绝对零命令）；
   - Stage 5 运行 `studio.py finalize ch_XXX` 自动在内存中套用配方生成 `final` 并盖章放行；
   - 紧接着单行链式执行 `proposal auto` 提取事实并 `sync` 封存，全过程 <0.5 秒。

---

## 五、 常用核心命令速查 (Cheat Sheet)

详细命令矩阵与子代理权限映射见 [`docs/COMMAND_MATRIX.md`](file:///c:/Users/cg110902/Desktop/NOVEL/docs/COMMAND_MATRIX.md)。

| 场景 | 命令示例 | 核心用途 |
|---|---|---|
| **工序与态势** | `python studio.py cockpit -w "workspace/<书名>"` | 驾驶舱：查看工序指针与下步行动 |
| **状态体检** | `python studio.py check -w "workspace/<书名>"` | 全息双核体检（0 errors 为绿灯） |
| **消音确认** | `python studio.py check --accept <fp> -w "workspace/<书名>"` | 对已知良性 warning 留痕消音备案 |
| **细纲脚手架** | `python studio.py beats new ch_XXX --write -w "workspace/<书名>"` | 生成细纲任务书模板与资源池速查 |
| **上下文装配** | `python studio.py pack ch_XXX --full -w "workspace/<书名>"` | Drafter 起草专用装配包（预算上限 1.5W Token） |
| **事实求证** | `python studio.py ask "<实体名/事件>" -w "workspace/<书名>"` | 全息问书机（穿透真值、正文与圣经，带出处） |
| **排产日历** | `python studio.py calendar 3 -w "workspace/<书名>"` | 查看未来 3 章危机倒计时与伏笔线 |
| **质量预审** | `python studio.py audit ch_XXX --write -w "workspace/<书名>"` | 总控派发 Stage 4A 前预置 8 大探针报告骨架 |
| **自动定稿** | `python studio.py finalize ch_XXX -w "workspace/<书名>"` | Stage 5 自动套用修补配方生成 final 并盖章放行 |
| **事实提取** | `python studio.py proposal auto ch_XXX --write -w "workspace/<书名>"` | Stage 5 自动从定稿抽取增量事实写入提案 |
| **状态同步** | `python studio.py sync ch_XXX -w "workspace/<书名>"` | Stage 5 原子封存快照与状态合账归档（≤0.5秒） |
| **派生重算** | `python studio.py state recompute -w "workspace/<书名>"` | 刷新线温与派生表（消除 derived_stale） |
| **卷末态势** | `python studio.py state rollup vol_XX -w "workspace/<书名>"` | 卷末态势摘要生成（跨卷装配前情源） |
| **备份回滚** | `python studio.py snapshot create/rollback <名> -w "workspace/<书名>"` | 状态与稿件快照备份与一键回滚 |


---

## 六、 退出码契约

CLI 命令设计为确定性机械闸门，退出码具有严格机器语义：
- `0`：正常通过；
- `1`：业务阻断（如 `check` 检出 errors、`sync` 仲裁未放行等）；
- `2`：命令行参数或语法用法错误；
- `3`：环境缺失依赖库（系统会打印缺失库与安装命令）。

