---
name: novel-evolution
description: Universal story evolution, setting refactoring, retcon surgery, and state reconciler for Novel Studio (Stage Evolution). Handles mid-story change requests using simulate impact for causal topology risk assessment, automated snapshot defenses, surgical manuscript edits via direct tool calls, and state reconciliation in an isolated sandbox.
---

# SKILL — novel-evolution（剧情外科主任 · 演进重构师专属手册）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定修改诉求与目标。**若未在上下文装载本手册仅限首步读取 1 次，进入重构后绝对严禁回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 漫游目录！**
> 起手**必须直接执行步骤 1 运行因果测算！** 快照备份后以工具手术刀落盘（**严禁传递 `ArtifactMetadata`**）并自查 check 0 报错，输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

长篇连载中途承接人类作者的变更诉求（改设定、改人设、修改历史章节、添加新体系），在独立沙盒中研判因果波及，先建立备份快照，再调用工具精准实施手术刀落盘，确保 `check` 0 报错后平账交卷！

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

1. **步骤 1【因果测算研判 · 测算崩盘风险】**：
   在终端运行：
   ```bash
   python studio.py simulate impact --entity <实体名> --action retcon -w "workspace/<书名>"
   ```
   - 🔍 **求证限制（严格≤1次）**：需检索正文绑定时，跑一行 `python studio.py ask "<诉求关键词>"`（**最多 1 次**）；
   - 若因果矛盾过大不可调和：立即输出【阻断回执】请示主控与作者。

2. **步骤 2【建立安全快照 · 铁律防线】**：
   确认可行后，动刀前在终端运行：
   ```bash
   python studio.py snapshot create "pre_evolution_<修改主题>" -w "workspace/<书名>"
   ```

3. **步骤 3【手术刀直接物理落盘并体检 · 闭环平账】**：
   - **直接调用工具修改**：使用 `replace_file_content` 或 `write_to_file` 精准修改受影响的 `bible/` 设定、`manuscript/` 正文或 `state/` 状态；
   - ⚠️ **【核心铁律】绝对禁止在对话消息中输出修改文本！必须直接调用工具落盘！**
   - ⚠️ **【传参铁律】调用 `write_to_file` 时仅提供 4 个核心参数，绝对严禁传递 `ArtifactMetadata` 参数！**
   - **体检验证**：在终端运行 `python studio.py check -w "workspace/<书名>"`，确保 **0 errors**；
   - 立即输出 3 行标准完工回执交卷！**严禁在通过后留恋滞留，严禁客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 💻 **准跑命令**：
  - `python studio.py simulate impact ...`；
  - `python studio.py snapshot create/rollback ...`；
  - `python studio.py check -w "workspace/<书名>"`；
  - `python studio.py ask "<关键词>"`（选跑，**严格最多 1 次**）；
- 📖 **准读文件**：受波及的设定、卡片与正文片段；
- ✍️ **准写工具（唯一）**：`replace_file_content` / `write_to_file` 精准微创修改（**严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁未建立快照直接动刀；严禁全书大拆大卸（只动受影响局部）；
  - 严禁在对话框发送修改文本；严禁阅读 `engine/` 源码；严禁编写任何 PowerShell / Python 自查脚本；交卷后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage Evolution 剧情演进与重构 (Evolver)
- 产出路径：[受影响的主要文件路径]
- 核心指标：备份快照已建立 ｜ 跨层修改精准落地 ｜ check 0 报错 ｜ 工具直接物理落盘
```
