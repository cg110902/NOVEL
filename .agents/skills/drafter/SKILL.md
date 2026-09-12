---
name: novel-drafter
description: Universal plot drafting and creative narrative generator for Novel Studio (Stage 2). Unchains full creative compute to produce high-tension raw story drafts (raw/ch_XXX_v1.md) across any genre, strictly inheriting beat facts and character matrices.
---

# SKILL — novel-drafter（起草先锋专属手册 · Stage 2）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定工作区与章节。**若未在上下文装载本手册仅限首步读取 1 次，进入正文生产后绝对严禁回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻工程！**
> 起手**必须直接执行步骤 1 跑 pack 取包！** 撰写正文后直接调用 `write_to_file` 落盘（**严禁附带 `ArtifactMetadata`**），输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

运行 `studio.py pack ch_XXX --full` 获取装配包（细纲与世界锚点已自完备），放飞顶级文学想象力与通俗叙事，撰写 1500~2000 字高张力初稿毛坯，直接调用 `write_to_file` 工具写入 `raw/ch_XXX_v1.md`！

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

1. **步骤 1【跑命令获取装配包 · 唯一输入】**：
   在终端运行命令获取当章细纲全文与核心锚点：
   ```bash
   python studio.py pack ch_XXX --full -w "workspace/<书名>"
   ```

2. **步骤 2【撰写并直接物理落盘 · 唯一产出】**：
   100% 依据 pack 内容展开场景，写出情节跌宕、人物鲜活的初稿正文（1500~2000 字）：
   - **开头直接进戏**：紧接上章余波或以突发冲突开篇，拒绝长篇天气写景废话；
   - **动作一招一式**：打斗交锋具象展开，拒绝“大战三百回合”的大纲式概括；
   - **主角有血有肉**：有正常生理与心理反应，拒绝冷脸装逼木头人；
   - **章末物理刀口**：结尾定格在动作爆发、悬念坠落处，严禁跳出旁白发表长篇感悟；
   - ⚠️ **【核心铁律】绝对禁止在对话聊天中输出小说正文！必须直接调用 `write_to_file` 工具写入 `manuscript/vol_XX/raw/ch_XXX_v1.md`！**
   - ⚠️ **【传参铁律】调用 `write_to_file` 时仅提供 `TargetFile`, `CodeContent`, `Description`, `Overwrite` 4 个参数，绝对严禁传递 `ArtifactMetadata` 参数（工作区草稿绝非 Brain Artifact，传错直接导致 Schema 报错中断）！**

3. **步骤 3【提交 3 行回执 · 即刻退出】**：
   文件落盘完成后，立即输出 3 行标准完工回执交卷！**严禁在落盘后再调用 `view_file` 查验刚写的文件，严禁发表客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 💻 **准跑命令（唯一）**：`python studio.py pack ch_XXX --full -w "workspace/<书名>"`；
- 📖 **准读输入（唯一）**：`pack` 命令返回的内容（**严禁回读外部卡片与历史章节**）；
- ✍️ **准写工具（唯一）**：调用 `write_to_file` 写入 `manuscript/vol_XX/raw/ch_XXX_v1.md`（**严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁在对话框发送正文文本；严禁调用 `ask`；
  - 严禁编写任何 PowerShell / Python 自查或字数统计脚本（字数大致在 1500~2000 字区间即可，绝不死抠精确字数）；
  - 严禁调用 `check` / `doctor` 等全书体检命令；严禁阅读 `engine/` 源码；落盘后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 2 初稿起草 (Drafter)
- 产出路径：manuscript/vol_XX/raw/ch_XXX_v1.md
- 核心指标：字数 [N] 字 ｜ 工具直接物理落盘 ｜ 冲突充分展开 ｜ 刀口定格交卷
```
