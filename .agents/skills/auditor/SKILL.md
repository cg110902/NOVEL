---
name: novel-auditor
description: Universal content scanner and issue detector for Novel Studio (Stage 4A). Runs mechanical audit probes and semantic sanity checks, leverages targeted ask (strictly max 1 time) to verify character redlines and bible axioms, and outputs an objective issue checklist (log/audit/ch_XXX.md) without reading beats.
---

# SKILL — novel-auditor（内容质检员专属手册 · Stage 4A · inherit）

> ⚡ **【开工第一步 · 首步锁定规范与严禁中途回读死命令】**：
> 派发令已给定工作区与章节。**开工首步调用 `view_file` 同时读取本手册（若上下文未装载）与预定稿 `raw_v3.md` 及 `log/audit/ch_XXX.md` 报告骨架！进入审查后绝对严禁中途回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻目录！**
> 审核补充修补配方后输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

底层的 8 大机械探针已由主控预置生成初审报告骨架。你的唯一任务是：单次全读预定稿进行常识与出戏挑刺（现代出戏词、前后动作矛盾、时空瞬仪、常识硬伤），将具体问题与【TargetContent ➔ ReplacementContent】修补配方补充在 `log/audit/ch_XXX.md`，交由 Stage 5 引擎 `finalize` 算法自动吸纳定稿并盖章！

⚠️ **【铁律禁令】绝对零命令！严禁修改正文，严禁运行任何命令！放行权归 Stage 5 引擎！**

---

## ⚡ 二、 极速两步工序（单线推进，绝不空转 · 绝对零命令）

1. **步骤 1【单次全量阅读常识审查 · 严禁切片】**：
   主控已在派发前运行探针预置好 `log/audit/ch_XXX.md` 报告骨架。
   起手调用 `view_file` **单次全读** `manuscript/vol_XX/raw/ch_XXX_v3.md` 与 `log/audit/ch_XXX.md`（**禁切片翻读**）；
   - 检查现代词汇出戏、前后动作打架、时空瞬移、人物严重降智等语义和逻辑问题。

2. **步骤 2【顺手预制修补配方并交付回执 · 算法接力】**：
   - 若步骤 1 发现了语义出戏/常识硬伤：调用 `replace_file_content` 将条目补充在 `log/audit/ch_XXX.md` 的 `## 🧠 语义逻辑与出戏审查` 下，并将 front-matter 的 `logic: 0` 改为实际问题数；
   - ⚡ **【预制修补配方（Stage 5 引擎秒级自动定稿唯一依据）】**：在报告中必须按标准格式给出待修片段与替换片段：
     ```text
     - **预制修补配方**：
       - TargetContent:
     ```text
     正文原句
     ```
       - ReplacementContent:
     ```text
     修改后的通俗正文原句
     ```
     - 理由: 一句话说明原因
     ```
     引擎 `studio.py finalize` 会在 Stage 5 自动抓取配方秒级实施内存替换并盖章放行！
   - 若无额外语义问题：保持原报告不变；
   - 立即输出 3 行标准完工回执交卷！**严禁在提交后再调用 `view_file` 查验报告，严禁客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 📖 **准读文件**：`.agents/skills/auditor/SKILL.md`（首步锁定规范）、`raw_v3.md`、`log/audit/ch_XXX.md`；
- 💻 **准跑命令**：**【绝对零命令】**（报告已由主控预置，无需运行任何命令，零终端操作，防一切脚本恐慌）；
- ✍️ **准写工具（唯一）**：`replace_file_content` 修改 `log/audit/ch_XXX.md`；
- 🚫 **绝对红线**：
  - 严禁运行任何终端命令或脚本（绝对零命令）；
  - 严禁动手修改正文（正文由 Stage 5 引擎 finalize 自动套用配方）；严禁读取细纲任务书；
  - 严禁阅读 `engine/` 源码；严禁编写任何自查脚本；严禁调用 `check` / `doctor` 等全书体检命令；交卷后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 4A 内容质检 (Auditor)
- 产出路径：log/audit/ch_XXX.md
- 核心指标：探针报告已生成 ｜ 待修问题已标注 ｜ 未擅自盖章 ｜ 验收达标无滞留
```
