# AGENTS.md — Novel Studio 核心宪法（极速轻量通用版）

Novel Studio 是通俗商业网文工业流水线框架：**大模型全权掌控创意脑洞、生动情节与通俗叙事；确定性引擎负责事实底座与数据台账；原生 Subagents 极速工序接力与闭环归档。**

> 🏆 **【最高网文语感规范】**：
> **绝不追求虚浮晦涩的所谓“纯文学质感”！读者是来读网文的，不是来啃生涩教材的！**
> **全流程核心准则**：**通俗直白大白话、极度易读、无认知门槛、一口气读完停不下来！**

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
| **总控 Director**<br/>(Stage 1 / 5) | `inherit` | 全局状态、critic便签、cockpit | `outlines/vol_XX/beats/ch_XXX.md` | `cockpit`, `calendar`, `beats new`, `proposal auto`, `sync` | **总制片人**：剧情弧线把控，编制细纲，前置声明事实预期，派发前跑 `proposal auto` 备骨架，Stage 5 单步原子封存（禁写正文、章末正文零回读）。 |
| **起草员 Drafter**<br/>(Stage 2) | `inherit` | **仅读 pack 输出**<br/>（严禁翻读beats） | `raw/ch_XXX_v1.md`<br/>(`write_to_file`) | `pack ch_XXX` | **剧情起草**：依据 pack 装配包展开 1500~2500 字初稿毛坯，pack 数据自完备且 Beats 置顶，严禁二次查验，直接起笔展开，落盘即走。 |
| **精修师 Editor**<br/>(Stage 3) | `inherit` | `editor/SKILL.md`<br/>`raw/ch_XXX_v3.md` | `raw/ch_XXX_v3.md`<br/>(`write_to_file`) | **【绝对零命令】** | **全篇精修与脱水重塑**：总控派发前预置 v3，首步读取手册锁定文风与负面词库后依据脱水铁律调用 `write_to_file` 全篇大白话重写落盘（通俗脱水、去冷脸面瘫与高频词），纯读写零终端，落盘即走。 |
| **审查员 Auditor**<br/>(Stage 4A) | `inherit` | `auditor/SKILL.md`<br/>`raw/ch_XXX_v3.md`<br/>`log/audit/ch_XXX.md` | `log/audit/ch_XXX.md`<br/>(`replace_file_content`) | **【绝对零命令】** | **客观安检**：总控派发前预置探针骨架，首步读取手册与底稿进行常识挑刺，预制修补配方写入报告，纯读写零终端，与 Critic 并发执行。 |
| **催更员 Critic**<br/>(Stage 4B) | `flash` | `critic/SKILL.md`<br/>`raw/ch_XXX_v3.md`<br/>`current.json` | `log/critic/ch_XXX.md`<br/>(`write_to_file`) | **【绝对零命令】** | **老白盲审**：十年老白读者盲审，首步读取手册与底稿输出 300~500 字追更便签供下章细纲参考，纯读写零终端，与 Auditor 并发执行，落盘即走。 |
| **终审封存交付**<br/>(Stage 5 总控/引擎) | `inherit` | 全局状态、成稿 | `final/ch_XXX.md`<br/>`state/inbox/ch_XXX.json` | `finalize`, `proposal auto`, `sync` | **极速三指令原子收口**：Auditor/Critic 并发完成后，总控秒级跑 `finalize`（自动吸纳配方生成 final 并盖章）+ `proposal auto --write`（自动提取变动）+ `sync`（合账封存与快照），彻底砍掉独立 Fixer 与 Reader 子代理（全过程 ≤0.5 秒；突发致命红旗由总控自主派发临时纯认知工排雷后收口）。 |

*(注：Stage 0 架构师 Architect、Stage Evolution 重构师 Evolver、长程巡检 Librarian 详见各自 SKILL.md，日常章节无需载入。)*

---

## 三、 双向极简交互协议（最高执行契约 · 严禁添油加醋）

1. **总控下达 · 标准 4 行工序派发令（严格闭合，零主观说教）**：
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

## 四、 跨角色六大绝对红线（严禁任何形式的违纪内耗）

1. **单步物理落盘与禁传 ArtifactMetadata 铁律**：所有生成/修改正文、报告、便签、提案的子代理，**必须在同一轮直接调用 `write_to_file` 或 `replace_file_content` 完成物理落盘**！调用 `write_to_file` 写入工作区文件时，仅提供 `TargetFile`, `CodeContent`, `Description`, `Overwrite` 4 个核心参数，**绝对严禁传递 `ArtifactMetadata` 参数**（非 Brain Artifact，传错即报 Schema 错误）。
2. **禁发正文聊天与交卷即走铁律**：绝对严禁在对话框发送正文全文或闲聊客套；文件落盘（若有专属验证命令跑通 0 报错）后，立即且仅输出 3 行标准完工回执彻底结束当前轮次！**严禁在落盘后再调用 `view_file` 回读自验刚写的文件**！
3. **零脚本自查与禁过度体检铁律**：所有子代理**绝对严禁编写任何 PowerShell / Python 脚本**去测字数、算正则或自检；**绝对严禁调用全书体检命令（`check` / `doctor`）**；总控 Stage 5 运行 `studio.py sync` 成功即交付，**绝对严禁在封存后再追跑全书 `check`**。
4. **严禁踩点探测与偷看旧章铁律**：子代理启动后**绝对严禁调用 `find_by_name` 或 `list_dir`** 搜寻目录；**绝对严禁调用 `view_file` 偷看其他历史章节**！
5. **专职边界与免多余回读铁律**：
   - **Drafter**：运行 `pack` 获取自完备上下文（Beats 置顶一目了然）后**起手直写**，严禁写脚本、严禁二次查验，直接落盘；
   - **Editor**：单次全读 `raw_v3` 后，依据脱水铁律确定重写策略，调用 `write_to_file` 全篇大白话重写落盘，纯读写零终端，落盘即走；
   - **Fixer 与 Reader 全面算法化**：彻底砍掉独立 Fixer 与 Reader 子代理！由总控在 Stage 5 直接运行 `finalize` 自动吸纳修补配方生成 final，再由 `proposal auto --write` 自动提取入库，彻底免除任何大模型手写或调试的内耗。
6. **总控物理写屏障与 Stage 5 原子收尾铁律**：总控写入权限严格仅限 Stage 1 细纲（`beats/ch_XXX.md`）与卷大纲微调；**总控绝对禁止亲笔撰写或修改小说正文与审查报告**！Stage 5 必须且只能执行三连命令 `python studio.py finalize ch_XXX -w "..." && python studio.py proposal auto ch_XXX --write -w "..." && python studio.py sync ch_XXX -w "..."`，正文绝对零回读，封存完毕即交付。

---

## 五、 协议导航（专职技能卡索引）

各角色深层业务细则与专用模板详见对应技能卡（开工首步读取锁定规范，中途严禁回读倒嚼）：
- 总控统筹：`.agents/skills/director/SKILL.md` ｜ 起草先锋：`.agents/skills/drafter/SKILL.md`
- 骨肉精修：`.agents/skills/editor/SKILL.md` ｜ 审查质检：`.agents/skills/auditor/SKILL.md`
- 读者催更：`.agents/skills/critic/SKILL.md` ｜ 演进重构：`.agents/skills/evolution/SKILL.md`
- 宏观架构：`.agents/skills/architect/SKILL.md` ｜ 长程平账：`.agents/skills/librarian/SKILL.md`
*(注：原 Fixer 终审与 Reader 审计已全面引擎算法化为 `finalize` 与 `proposal auto`，免除独立代理)*
