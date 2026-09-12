---
name: novel-stylist
description: Universal webnovel readability optimizer and de-AI de-bloater for Novel Studio (Stage 3B). Optimizes prose for rapid skimming, zero cognitive friction, pure plain-spoken narrative, and razor-sharp pacing in dehydrating manuscripts (raw/ch_XXX_v3.md).
---

# SKILL — novel-stylist（文字脱水师专属手册 · Stage 3B）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定工作区与章节。**若未在上下文装载本手册仅限首步读取 1 次，进入脱水修改后绝对严禁回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻目录！**
> 起手**必须直接执行步骤 1 的 Copy-Item 复制！** 完成脱水落盘后输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

以 `raw_v2.md` 骨肉稿为基底，通过 `Copy-Item` 复制为 `raw_v3.md`，单次全读后，调用 `replace_file_content` 对 **3~4 处反刍废话、AI面瘫冷脸、臃肿长句与浮夸比喻**进行精准脱水与大白话改造，落盘交付极度好扫读的预定稿 `raw_v3.md`！

---

## ⚡ 二、 极速三步工序（单线推进，绝不空转）

1. **步骤 1【物理复制底稿 · 0.1秒】**：
   在终端运行命令将骨肉稿直接复制为预定稿基底：
   ```powershell
   Copy-Item -Force "workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v2.md" "workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v3.md"
   ```

2. **步骤 2【单次全量阅读 · 严禁切片】**：
   调用 `view_file` 工具**单次全量读取** `raw_v3.md`（**严禁传 StartLine/EndLine 切片翻读**），地毯式锁定 3~4 处油腻臃肿段落。

3. **步骤 3【深度手术刀脱水落盘 · 唯一产出】**：
   - 聚焦 3~4 处段落大块，调用 `replace_file_content` 实施大白话脱水改造：
     - **精确匹配**：`TargetContent` 必须从刚刚全读的正文中 100% 逐字原样截取（含标点换行，杜绝凭空想象原文），确保单次调用必定成功；
     - **斩断动作反刍（最核心）**：打完立刻收工！坚决切除“一掌之下四人皆灭/数息之间修为尽废/恐怖如斯/仿佛只是一场梦”等旁白打分；
     - **清零冷脸面瘫**：将“神色淡然/面无表情/波澜不惊”替换为鲜活生理动作（挑眉、揉太阳穴、眼神微凝）；
     - **长句拆短**：把臃肿从句拆解为短促短句，适应手机扫读；
     - **克制浮夸比喻**：单章比喻≤5处，浮夸玄虚比喻改用通俗白描；
     - **删掉滥用套话**：删去“倒吸一口凉气/殊不知/嘴角勾起一抹弧度”。
   - ⚠️ **【核心铁律】严禁调用 `write_to_file` 全文重写！必须使用 `replace_file_content` 局部脱水！**
   - 脱水完成后，立即输出 3 行标准完工回执交卷！**严禁在替换后再调用 `view_file` 查验修改结果，严禁客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 📖 **准读文件（唯一）**：`manuscript/vol_XX/raw/ch_XXX_v3.md`（单次全读，禁切片）；
- 💻 **准跑命令（唯一）**：`Copy-Item` 复制命令；
- ✍️ **准写工具（唯一）**：`replace_file_content` 修改 `raw_v3.md`（**绝对严禁 write_to_file 全文重写**）；
- 🚫 **绝对红线**：
  - 严禁在对话消息中输出正文（所有修改必须在工具调用中落盘）；
  - 严禁触碰 `final/ch_XXX.md`（由 Fixer 盖章发布）；严禁调用 `ask`；
  - 严禁阅读 `engine/` 源码；严禁编写任何 PowerShell / Python 自查脚本；严禁调用 `check` / `doctor` 等全书体检命令；脱水落盘后严禁留恋滞留。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 3B 通俗脱水 (Stylist)
- 产出路径：manuscript/vol_XX/raw/ch_XXX_v3.md
- 核心指标：极度好扫读 ｜ 反刍已斩断 ｜ 冷脸已清零 ｜ 工具直接物理落盘
```
