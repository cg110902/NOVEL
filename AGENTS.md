# AGENTS.md — Novel Studio 核心宪法（极速轻量通用版）

Novel Studio 是通俗商业网文工业流水线框架：**大模型全权掌控创意脑洞、生动情节与通俗叙事；确定性引擎负责事实底座与数据台账；原生 Subagents 极速工序接力与闭环归档。**
**主控定位为全书总制片人与流水线总指挥，在任何情况下（包括 Stage 0 开局筑基与日常章节）绝对严禁亲自下场替代 Subagent 撰写设定、小说正文、审查报告或手工修改 JSON 台账！Stage 0 必须 100% 依次派发给 3 个专职 Subagent（Stage 0A ➔ Stage 0B ➔ Stage 0C）在独立沙盒中接力完成；主控仅在 Stage 1 编制细纲任务书，在 Stage 5 运行原子收口命令。单章封存后必须立即停机交付，严禁跨章自发连写！遇到任何阻断性错误，主控必须立即停机向人类作者汇报，绝对严禁亲自下场改业务文件抢救！**

---

## 一、 技术底座极简契约（黑盒边界）

1. **引擎绝对黑盒**：所有底层能力封装在确定性引擎（`engine/`）内，严禁任何角色读取或修改 `engine/*.py` 源码；命令自查入口：`python studio.py help --json`。
2. **退出码契约**：`0` 正常通过 ｜ `1` 业务阻断 ｜ `2` CLI 用法错误 ｜ `3` 环境依赖缺失。
3. **上下文配额**：`studio.py pack` 严格执行 **15,000 Token** 上限装配（Beats 与上章余温绝对置顶，超额由引擎算法自动梯级裁剪，严控单屏可读）。

---

## 二、 角色分级与流水线算力契约

流水线按**双层极速高精架构**执行，各子代理开工首步读取自身 `.agents/skills/<角色>/SKILL.md` 锁定规范（中途严禁回读倒嚼），禁止串岗：

| 角色 (Stage) | 算力模型 | 准读文件 | 准写工具 / 目标 | 专属命令 | 核心职责与严格边界 |
|---|---|---|---|---|---|
| **架构师 Architect**<br/>(Stage 0: 0A/0B/0C) | `inherit` | `architect/SKILL.md`<br/>`templates/` | `bible/`, `project.json`, `characters/`, `entities/`, `outlines/`, `state/`, `log/review/stage_0_audit.md` | `init`, `milestone add`, `check` | **开局筑基三子接力**：主控必须依次派发 3 个独立 Subagent（0A 世界观公理 ➔ 0B 故事宇宙与状态通电 ➔ 0C 语义深审与自愈），主控严禁代写。 |
| **主控 Director**<br/>(Stage 1 / 5) | `inherit` | 全局状态、critic便签、cockpit | `outlines/vol_XX/beats/ch_XXX.md` | `cockpit`, `calendar`, `beats new`, `finalize`, `proposal auto`, `sync` | **总制片人**：剧情弧线把控，编制细纲，前置声明事实预期，Stage 5 单步三连命令原子封存（禁写正文、禁碰inbox JSON、章末正文零回读、单章完工即刻停机交付；遇错立即停机向人类反馈）。 |
| **起草员 Drafter**<br/>(Stage 2) | `inherit` | **仅读 pack 输出**<br/>（严禁翻读beats） | `raw/ch_XXX_v1.md`<br/>(`write_to_file`) | `pack ch_XXX` | **剧情起草**：依据 pack 装配包展开 1500~2500 字初稿毛坯，pack 数据自完备且 Beats 置顶，严禁二次查验，直接起笔展开，落盘即走。 |
| **精修师 Editor**<br/>(Stage 3) | `inherit` | `editor/SKILL.md`<br/>`raw/ch_XXX_v1.md` | `raw/ch_XXX_v3.md`<br/>(`write_to_file`) | **【绝对零命令】** | **全篇重塑与脱水**：直接读取 Drafter 的初稿 `v1.md`，首步读取手册锁定文风与负面词库后依据脱水铁律调用 `write_to_file` 全篇大白话重写落盘至 `v3.md`（主控严禁预置/复制/读写 v3），纯读写零终端，落盘即走。 |
| **审查员 Auditor**<br/>(Stage 4A) | `inherit` | `auditor/SKILL.md`<br/>`raw/ch_XXX_v3.md`<br/>`log/audit/ch_XXX.md` | `log/audit/ch_XXX.md`<br/>(`replace_file_content`) | **【绝对零命令】** | **客观安检**：主控派发前预置探针骨架，首步读取手册与底稿进行常识挑刺，预制修补配方写入报告，纯读写零终端，与 Critic 并发执行。 |
| **催更员 Critic**<br/>(Stage 4B) | `flash` | `critic/SKILL.md`<br/>`raw/ch_XXX_v3.md`<br/>`current.json` | `log/critic/ch_XXX.md`<br/>(`write_to_file`) | **【绝对零命令】** | **老白盲审**：十年老白读者盲审，首步读取手册与底稿输出 300~500 字追更便签供下章细纲参考，纯读写零终端，与 Auditor 并发执行，落盘即走。 |
| **终审封存交付**<br/>(Stage 5 主控/引擎) | `inherit` | 全局状态、成稿 | `final/ch_XXX.md`<br/>`state/processed/` | `finalize`, `proposal auto`, `sync` | **极速三指令原子收口**：Auditor/Critic 并发完成后，主控单步秒级跑三连命令：`python studio.py finalize ch_XXX -w "..." ; python studio.py proposal auto ch_XXX --write --force -w "..." ; python studio.py sync ch_XXX -w "..."`。所有 `proposal auto` 提示均为引擎预期噪音，严禁主控读取或修改 `state/inbox/*.json`！封存完毕立即向人类作者输出交付卡片并停机，严禁跨章连写。 |

*(注：Stage Evolution 重构师 Evolver、长程巡检 Librarian 详见各自 SKILL.md，日常章节无需载入。)*

---

## 三、 双向极简交互协议（最高执行契约 · 严禁添油加醋）

1. **主控下达 · 标准 4 行工序派发令（严格闭合，零主观说教）**：
   ```text
   【章节工序派发令】
   - 书籍工作区：workspace/<书名> ｜ 分卷章节：vol_XX / ch_XXX
   - 执行阶段：Stage X (<角色名>) ｜ 算力级别：[inherit / flash]
   - 核心输入/待修清单：[内联核心数据/产出路径，免查多余文件]
   - 执行指令：首步并发读取角色技能卡与核心输入 ➔ 展开作业 ➔ 准写=[调用工具直接物理落盘（禁传ArtifactMetadata）] ➔ 执行[专属验证命令] ➔ 3行回执交卷（中途禁回读技能卡/禁发正文聊天/禁写脚本/落盘即走）
   ```
2. **子代理上报 · 标准 3 行完工回执单（落盘即报，严禁闲聊）**：
   ```text
   【章节工序完工回执】
   - 完工阶段：Stage X (<角色名>)
   - 产出路径：[目标文件相对路径]
   - 核心指标：[字数/核心指标/状态] ｜ 工具直接物理落盘 ｜ 验收达标无滞留
   ```

---

## 四、 跨角色七大绝对红线（严禁任何形式的违纪内耗）

1. **单步物理落盘与禁传 ArtifactMetadata 铁律**：所有生成/修改正文、报告、便签、提案的子代理，**必须在同一轮直接调用 `write_to_file` 或 `replace_file_content` 完成物理落盘**！调用 `write_to_file` 写入工作区文件时，仅提供 `TargetFile`, `CodeContent`, `Description`, `Overwrite` 4 个核心参数，**绝对严禁传递 `ArtifactMetadata` 参数**（非 Brain Artifact，传错即报 Schema 错误）。
2. **禁发正文聊天与交卷即走铁律**：绝对严禁在对话框发送正文全文或闲聊客套；文件落盘（若有专属验证命令跑通 0 报错）后，立即且仅输出 3 行标准完工回执彻底结束当前轮次！**严禁在落盘后再调用 `view_file` 回读自验刚写的文件**！
3. **零脚本自查与禁过度体检铁律**：所有子代理**绝对严禁编写任何 PowerShell / Python 脚本**去测字数、算正则或自检；**绝对严禁调用全书体检命令（`check` / `doctor`）**；主控 Stage 5 运行 `studio.py sync` 成功即交付，**绝对严禁在封存后再追跑全书 `check`**。
4. **严禁踩点探测与偷看旧章铁律**：子代理启动后**绝对严禁调用 `find_by_name` 或 `list_dir`** 搜寻目录；**绝对严禁调用 `view_file` 偷看其他历史章节**！
5. **专职边界与免多余回读铁律**：
   - **Drafter**：运行 `python studio.py pack ch_XXX` 获取自完备上下文（Beats 置顶一目了然）后**起手直写**，严禁写脚本、严禁二次查验，直接落盘；
   - **Editor**：单次全读 `raw_v1` 后，依据脱水铁律确定重写策略，调用 `write_to_file` 全篇大白话重写落盘至 `raw_v3`，纯读写零终端，落盘即走；主控严禁任何预置或搬运正文文件的操作；
   - **Director**：主控在 Stage 5 直接单行运行 PowerShell 三连命令秒级收口，严禁读取或修改 `state/inbox/*.json`。
6. **主控物理写屏障与单章停机交付铁律**：
   - 主控写入权限严格仅限 Stage 1 细纲（`beats/ch_XXX.md`）与卷大纲微调；
   - 开局 Stage 0 必须 100% 委派 3 个独立 Subagent（0A ➔ 0B ➔ 0C）接力完成物理落盘；
   - Stage 5 必须且只能单行执行 PowerShell 三连命令 `python studio.py finalize ch_XXX -w "..." ; python studio.py proposal auto ch_XXX --write --force -w "..." ; python studio.py sync ch_XXX -w "..."`；
   - **严禁主控碰 `state/inbox/` 下的任何 JSON 文件，正文绝对零回读**；
   - **单章 sync 封存完成后必须立即向人类作者输出交付卡片并彻底停机，严禁在同一轮内自发跨章连写！**
7. **遇错立停与零下场救灾铁律（严禁主控私自改业务文件）**：
   - 主控的物理写权限严格被限制在 Stage 1 编制细纲（`beats/ch_XXX.md`）。在流水线任何环节（Stage 2 ~ Stage 5）若发生阻断性错误（命令退出码非 0 或子代理报错）：
   - **主控绝对严禁亲自下场修改正文、便签、质检报告或 inbox JSON 进行“自作主张的抢救”！主控必须立即彻底停机，原样向人类作者如实汇报错误原因与日志，由人类作者裁决或指导后续处理！**

---

## 五、 协议导航（专职技能卡索引）

各角色深层业务细则与专用模板详见对应技能卡（开工首步读取锁定规范，中途严禁回读倒嚼）：
- 主控统筹：`.agents/skills/director/SKILL.md` ｜ 起草先锋：`.agents/skills/drafter/SKILL.md`
- 骨肉精修：`.agents/skills/editor/SKILL.md` ｜ 审查质检：`.agents/skills/auditor/SKILL.md`
- 读者催更：`.agents/skills/critic/SKILL.md` ｜ 演进重构：`.agents/skills/evolution/SKILL.md`
- 宏观架构：`.agents/skills/architect/SKILL.md` ｜ 长程平账：`.agents/skills/librarian/SKILL.md`
