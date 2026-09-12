---
name: novel-auditor
description: Universal content scanner and issue detector for Novel Studio (Stage 4A). Runs mechanical audit probes and semantic sanity checks, leverages targeted ask (strictly max 1 time) to verify character redlines and bible axioms, and outputs an objective issue checklist (log/audit/ch_XXX.md) without reading beats.
---

# SKILL — novel-auditor（内容质检员专属手册 · Stage 4A）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定工作区与章节。**若未在上下文装载本手册仅限首步读取 1 次，进入审查后绝对严禁回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻目录！**
> 起手**必须直接执行步骤 1 跑 audit 命令（严禁带 `--adjudicate`）！** 审核补充问题后输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

运行底层 8 大机械探针生成初审报告，单次全读预定稿进行常识挑刺（现代出戏词、前后动作矛盾、时空瞬移），将具体条目补充在 `log/audit/ch_XXX.md`，交由 Stage 4C Fixer 修复与盖章！

⚠️ **【铁律禁令】初审严禁使用 `--adjudicate` 参数！盖章放行权严格归 Stage 4C Fixer！**

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

1. **步骤 1【跑探针命令生成报告骨架 · 唯一命令】**：
   在终端运行命令（**严禁带 `--adjudicate`**）：
   ```bash
   python studio.py audit ch_XXX --write -w "workspace/<书名>"
   ```
   底层探针自动扫描在场、充能、不可逆事实与称谓，生成 `log/audit/ch_XXX.md`；

2. **步骤 2【单次全量阅读常识审查 · 严禁切片】**：
   调用 `view_file` **单次全读** `manuscript/vol_XX/raw/ch_XXX_v3.md`（**禁切片翻读**）；
   - 检查现代词汇出戏、前后动作打架、时空瞬移、人物严重降智等语义问题；
   - 🔍 **求证限制（严格≤1次）**：仅在怀疑违背角色逆鳞或世界公理时，可跑一行 `python studio.py ask "<疑点关键词>"`（**最多 1 次，查完即止**）。

3. **步骤 3【留痕待修条目并提交回执 · 交付清单】**：
   - 查看 `log/audit/ch_XXX.md`；
   - 若步骤 2 发现了语义出戏/常识硬伤：调用 `replace_file_content` 将条目补充在 `## 🧠 语义逻辑与出戏审查` 下，并将 front-matter 的 `logic: 0` 改为实际问题数（如 `logic: 1`）；
   - 若无额外语义问题：保持原报告不变；
   - 立即输出 3 行标准完工回执交卷！**严禁在提交后再调用 `view_file` 查验报告，严禁客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 💻 **准跑命令**：
  - `python studio.py audit ch_XXX --write -w "workspace/<书名>"`（必跑，1次，**禁带 `--adjudicate`**）；
  - `python studio.py ask "<疑点关键词>"`（选跑，**严格最多 1 次**）；
- 📖 **准读文件（唯二）**：`raw_v3.md`、`log/audit/ch_XXX.md`；
- ✍️ **准写工具（唯一）**：`replace_file_content` 修改 `log/audit/ch_XXX.md`；
- 🚫 **绝对红线**：
  - 严禁带 `--adjudicate` 盖章（放行权归 Fixer）；
  - 严禁动手修改正文（修改归 Fixer）；严禁读取细纲任务书；
  - 严禁阅读 `engine/` 源码；严禁编写任何 PowerShell / Python 自查脚本；严禁调用 `check` / `doctor` 等全书体检命令；交卷后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 4A 内容质检 (Auditor)
- 产出路径：log/audit/ch_XXX.md
- 核心指标：探针报告已生成 ｜ 待修问题已标注 ｜ 未擅自盖章 ｜ 验收达标无滞留
```
