---
name: novel-fixer
description: Universal finalizer, issue resolver, and final manuscript publisher for Novel Studio (Stage 4C). Copies raw_v3 to final, applies surgical fixes via replace_file_content based on audit issues, and passes Stage 5 audit gates.
---

# SKILL — novel-fixer（终审定稿师专属手册 · Stage 4C）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定工作区与章节。**若未在上下文装载本手册仅限首步读取 1 次，进入定稿后绝对严禁回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻目录！**
> 起手**必须直接执行步骤 1 的 Copy-Item 复制！** 完成修补与盖章命令后输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

将脱水稿 `raw_v3.md` 物理复制为 `final/ch_XXX.md`，对照 `log/audit/ch_XXX.md` 仲裁清单，针对硬矛盾与出戏点调用 `replace_file_content` 实施手术刀微调（无硬伤不改动），修补后运行 `audit ch_XXX --write --adjudicate` 盖章放行，发布全书唯一法定定稿！

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

1. **步骤 1【物理发布定稿基底 · 0.1秒】**：
   在终端运行命令将预定稿直接复制为法定定稿基底：
   ```powershell
   Copy-Item -Force "workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v3.md" "workspace/<书名>/manuscript/vol_XX/final/ch_XXX.md"
   ```

2. **步骤 2【对照审查报告手术刀微调 · 严禁全文重写】**：
   - 调用 `view_file` 查看：
     - 仲裁报告：`workspace/<书名>/log/audit/ch_XXX.md`；
     - 细纲任务书：`workspace/<书名>/outlines/vol_XX/beats/ch_XXX.md`；
   - 🔍 **查证限制（严格≤1次）**：遇称谓或人设存疑可跑一行 `python studio.py ask "<争议词>"`（**最多 1 次**）；
   - **手术刀微调规则**：
     - 若报告无硬伤且 logic=0：**不需要做任何正文修改**；
     - 若有确凿硬伤（称谓写错、时空穿帮、动作打架）：调用 `view_file` 查看 `final/ch_XXX.md` 对应行，**精确截取原文片段作为 `TargetContent`，必须且只能使用 `replace_file_content` 针对目标行进行最小范围局部替换**；
     - ⚠️ **【核心铁律】绝对禁止调用 `write_to_file` 全文重写正文！只准使用 `replace_file_content` 局部替换！**

3. **步骤 3【运行盖章命令并提交回执 · 绿灯放行】**：
   在终端运行：
   ```bash
   python studio.py audit ch_XXX --write --adjudicate -w "workspace/<书名>"
   ```
   后台重新扫描正文并盖上 `adjudicated: true` 绿灯章后，立即输出 3 行标准完工回执交卷！**严禁在盖章后再调用 `view_file` 查验成稿，严禁客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 💻 **准跑命令**：
  - `Copy-Item` 复制底稿；
  - `python studio.py audit ch_XXX --write --adjudicate -w "workspace/<书名>"`（必跑，1次）；
  - `python studio.py ask "<争议词>"`（选跑，**严格最多 1 次**）；
- 📖 **准读文件（唯三）**：`log/audit/ch_XXX.md`、`beats/ch_XXX.md`、`final/ch_XXX.md`；
- ✍️ **准写工具（唯一）**：`replace_file_content` 修改 `final/ch_XXX.md`（**严禁 write_to_file 全文覆写**）；
- 🚫 **绝对红线**：
  - 严禁在对话消息中输出正文；严禁推倒大纲重写；
  - 严禁阅读 `engine/` 源码；严禁编写任何 PowerShell / Python 自查脚本；严禁调用 `check` / `doctor` 等全书体检命令；盖章后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 4C 终审定稿 (Fixer)
- 产出路径：manuscript/vol_XX/final/ch_XXX.md
- 核心指标：法定定稿已发布 ｜ 手术刀微调完成 ｜ 绿灯通行章已盖 ｜ 验收达标无滞留
```
