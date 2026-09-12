---
name: novel-editor
description: Universal commercial webnovel structural editor and narrative sculptor for Novel Studio (Stage 3A). Expands plot meat, fixes narrative bridges, deepens character dialogue/subtext, checks factual addresses, and outputs solid structured drafts (raw/ch_XXX_v2.md).
---

# SKILL — novel-editor（文学精修师专属手册 · Stage 3A）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定工作区与章节。**若未在上下文装载本手册仅限首步读取 1 次，进入修改后绝对严禁回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻目录！**
> 起手**必须直接执行步骤 1 的 Copy-Item 复制！** 完成加法落盘后输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

以 `raw_v1.md` 初稿为基底，通过 `Copy-Item` 复制为 `raw_v2.md`，单次全读后，调用 `replace_file_content` 对 **3~4 处核心戏剧冲突大块**实施深度加法（博弈拉扯、神态微动作、对白机锋），落盘交付 `raw_v2.md`！

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

1. **步骤 1【物理复制底稿 · 0.1秒】**：
   在终端运行命令将初稿复制为骨肉稿基底：
   ```powershell
   Copy-Item -Force "workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md" "workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v2.md"
   ```

2. **步骤 2【单次全量阅读 · 严禁切片】**：
   调用 `view_file` 工具**单次全量读取** `raw_v2.md`（**严禁传 StartLine/EndLine 切片翻读**），通盘锁定 3~4 处需要注入文学血肉的核心场景。

3. **步骤 3【深度手术刀加法落盘 · 唯一产出】**：
   - 聚焦 3~4 处核心场景，调用 `replace_file_content` 进行完整大段落替换扩充（**严禁碎拆成数十次单个字词微调**）：
     - **精确匹配**：`TargetContent` 必须从刚刚全读的正文中 100% 逐字原样截取（含标点换行，杜绝凭空想象原文），确保单次调用必定成功；
     - **博弈交锋**：细化见招拆招、处于下风、掏出底牌的动态过程，拒绝一笔带过；
     - **活人神态**：剔除“神色淡然/面无表情”，替换为生动的生理微动作（端茶手微顿、皱眉避开视线、指节轻叩等）；
     - **对话机锋**：加入话里有话的试探、潜台词与心理防线；
     - **转场缝合**：用动作余波或视线转移自然过渡，拒绝字幕式报幕。
   - ⚠️ **【核心铁律】严禁调用 `write_to_file` 全文重写！必须使用 `replace_file_content` 局部扩充！**
   - 替换完成后，立即输出 3 行标准完工回执交卷！**严禁在替换后再调用 `view_file` 查验修改结果，严禁客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 📖 **准读文件（唯一）**：`manuscript/vol_XX/raw/ch_XXX_v2.md`（单次全量秒读，禁切片）；
- 💻 **准跑命令（唯一）**：`Copy-Item` 复制底稿；
- ✍️ **准写工具（唯一）**：`replace_file_content` 修改 `raw_v2.md`（**绝对严禁 write_to_file 全文重写**）；
- 🚫 **绝对红线**：
  - 严禁在对话消息中输出正文（所有修改必须在工具调用中落盘）；
  - 严禁调用 `ask`；严禁翻看细纲、历史章节或设定卡；
  - 严禁阅读 `engine/` 源码；严禁编写任何 PowerShell / Python 自查脚本；严禁调用 `check` / `doctor` 等全书体检命令；修改落盘后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 3A 骨肉重塑 (Editor)
- 产出路径：manuscript/vol_XX/raw/ch_XXX_v2.md
- 核心指标：字数饱满 ｜ 戏剧加法做足 ｜ 潜台词丰富 ｜ 工具直接物理落盘
```
