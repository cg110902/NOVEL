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
| **Stage 2** | **Drafter** | `inherit` | 100% 依据 pack 上下文展开，通俗大白话撰写高张力初稿毛坯 | `manuscript/vol_XX/raw/ch_XXX_v1.md` |
| **Stage 3A** | **Editor** | `flash` | 结构继承式全篇手术刀加法（深度充实戏剧博弈、神态微动作与潜台词） | `manuscript/vol_XX/raw/ch_XXX_v2.md` |
| **Stage 3B** | **Stylist** | `flash` | 结构继承式全篇手术刀脱水（切除反刍总结、清零冷脸面瘫词、长句拆短） | `manuscript/vol_XX/raw/ch_XXX_v3.md` |
| **Stage 4A** | **Auditor** | `flash` | 8 大机械探针初审（禁带 `--adjudicate`）+ 常识出戏审查，输出待修清单 | `log/audit/ch_XXX.md` |
| **Stage 4B** | **Critic** | `flash` | 资深老白读者纯盲审，评估阅读疲劳度与活人感，输出下章催更便签 | `log/critic/ch_XXX.md` |
| **Stage 4C** | **Fixer** | `flash` | 复制预定稿至 final，依据 audit 报告靶向微调，跑 `--adjudicate` 盖章放行 | `manuscript/vol_XX/final/ch_XXX.md` |
| **Stage 4D** | **Reader** | `flash` | 以 final 为唯一法定事实源提取客观增量，提交提案并通过预检 | `state/inbox/ch_XXX.json` |
| **Stage 5** | **Director** | 宿主主代理 | 执行 `studio.py sync` 原子封存状态快照，向人类作者交付定稿 | `state/*.json` 封存 |
| **低频巡检** | **Librarian** | `flash` | 每 10 章事实深层巡检打捞遗漏次要实体；卷末执行对账大修 | `log/review/`, `state/inbox/` |
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
│       ├── outline.md        # 分卷大纲（四分位阶段航标；主控可动态修纲）
│       └── beats/ch_XXX.md   # 当章细纲任务书（含法定事实与预期变更声明）
├── manuscript/vol_XX/
│   ├── raw/
│   │   ├── ch_XXX_v1.md      # 初稿毛坯（Stage 2 Drafter 产出）
│   │   ├── ch_XXX_v2.md      # 初修骨肉稿（Stage 3A Editor 产出）
│   │   └── ch_XXX_v3.md      # 通俗脱水预定稿（Stage 3B Stylist 产出）
│   └── final/ch_XXX.md        # 终局法定定稿（Stage 4C Fixer 修复并发布）
├── state/                    # 十一表真值（含 locked/cognition） + inbox/ 提案收件箱 + snapshots/ 快照
│   ├── rollups/              # 卷级态势折叠（vol_XX.json，供跨卷装配）
│   └── inbox/ch_XXX.json     # 章节增量提案（Stage 4D Reader 产出）
├── log/
│   ├── audit/ch_XXX.md       # 质检仲裁报告（Stage 4A 初评，Stage 4C 裁决盖章）
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
   - Reader 将增量事实物理落盘至 `state/inbox/ch_XXX.json`；
   - 运行 `python studio.py proposal check ch_XXX` 完成 0-error 预检；
   - 主控在 Stage 5 运行 `python studio.py sync ch_XXX` 完成原子封存。
3. **双键唯一物理 ID 体系**：
   - 角色：`p_001`（主角恒定为 `p_001`）、`p_002`...
   - 物品：`it_001`... ｜ 势力：`fac_001`... ｜ 地点：`loc_001`...
   - 双键合并优先按 `id` 寻址，就地更新属性，绝不分裂实体。
4. **质检闭环三轨硬闸门**：
   - Stage 4A Auditor 运行 `audit ch_XXX --write` 生成问题清单（**严禁带 `--adjudicate`**）；
   - Stage 4C Fixer 实施手术刀修补，运行 `audit ch_XXX --write --adjudicate` 盖上绿灯通行章；
   - 未消除硬伤与语义出戏点或未盖章的章节，Stage 5 `sync` 机械阻断封存。

---

## 五、 常用核心命令速查 (Cheat Sheet)

详细命令矩阵与子代理权限映射见 [`docs/COMMAND_MATRIX.md`](file:///c:/Users/cg110902/Desktop/NOVEL/docs/COMMAND_MATRIX.md)。

| 场景 | 命令示例 | 核心用途 |
|---|---|---|
| **工序与态势** | `python studio.py cockpit -w "workspace/<书名>"` | 驾驶舱：查看工序指针与下步行动 |
| **状态体检** | `python studio.py check -w "workspace/<书名>"` | 事实一致性体检（0 errors 为绿灯） |
| **细纲脚手架** | `python studio.py beats new ch_XXX --write -w "workspace/<书名>"` | 生成细纲任务书模板与资源池速查 |
| **上下文装配** | `python studio.py pack ch_XXX --full -w "workspace/<书名>"` | Drafter 起草专用装配包（预算 2W Token） |
| **事实求证** | `python studio.py ask "<实体名/事件>" -w "workspace/<书名>"` | 全息问书机（穿透真值、正文与圣经，带出处） |
| **排产日历** | `python studio.py calendar 3 -w "workspace/<书名>"` | 查看未来 3 章危机倒计时与伏笔线 |
| **质量仲裁** | `python studio.py audit ch_XXX --write -w "workspace/<书名>"` | Auditor 运行 8 大探针初检 |
| **定稿盖章** | `python studio.py audit ch_XXX --write --adjudicate -w "workspace/<书名>"` | Fixer 修复后盖章放行 |
| **提案预检** | `python studio.py proposal check ch_XXX -w "workspace/<书名>"` | Reader 提交提案前 0-error 验证 |
| **状态同步** | `python studio.py sync ch_XXX -w "workspace/<书名>"` | Stage 5 原子封存快照与状态合并 |
| **卷末态势** | `python studio.py state rollup vol_XX -w "workspace/<书名>"` | 卷末态势摘要生成（跨卷装配前情源） |
| **备份回滚** | `python studio.py snapshot create/rollback <名> -w "workspace/<书名>"` | 状态与稿件快照备份与一键回滚 |

---

## 六、 退出码契约

CLI 命令设计为确定性机械闸门，退出码具有严格机器语义：
- `0`：正常通过；
- `1`：业务阻断（如 `check` 检出 errors、`sync` 仲裁未放行等）；
- `2`：命令行参数或语法用法错误；
- `3`：环境缺失依赖库（系统会打印缺失库与安装命令）。

