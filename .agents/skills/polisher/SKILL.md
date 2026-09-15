---
name: novel-polisher
description: Universal prose polisher and sentence flow enhancer for Novel Studio (Stage 3B). Optimizes verbs and sentence order to achieve seamless, natural narrative flow without adding superfluous decoration, maintaining virtually even word count.
---

# SKILL — novel-polisher（全题材抛光润色师专属手册 · Stage 3B）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定工作区与章节。**起手直接调用 `view_file` 读取重塑稿 `manuscript/vol_XX/raw/ch_XXX_v2.md`！规范已在技能中锁定，绝对严禁开工调用 `view_file` 回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻目录！**
> 完成任务，直接调用 `write_to_file` 物理落盘至 `manuscript/vol_XX/raw/ch_XXX_v3.md`（**绝对严禁传递 `ArtifactMetadata`**），输出 3 行标准完工回执即刻交卷退出（**绝对严禁在对话框发送正文**），绝不滞留！

---

## 🎯 一、 你的核心使命与提示词契约

你的唯一核心宗旨【任务目标】是：
- **【优化动词与语序，追求丝滑连贯（流畅自然）；字数保持基本持平即可。】**;
- **保留 v2 大白话感，不额外增加阅读成本**；
- **通经活络、让文字如水流般自然顺滑**！


---

## ⚡ 二、 极速三步工序（单线推进，绝不空转 · 绝对零命令）

1. **步骤 1【单次全量阅读 · 锁定语流堵点】**：
   起手直接调用 `view_file` 工具**单次全量读取**重塑稿 `manuscript/vol_XX/raw/ch_XXX_v2.md`（**严禁切片翻读，严禁回读手册**）。

2. **步骤 2【全篇顺滑重塑落盘 · 唯一产出】**：
   - 完成任务后直接在 `write_to_file` 参数中输出产出的正文！
   - 直接调用 `write_to_file` 工具物理落盘至 `manuscript/vol_XX/raw/ch_XXX_v3.md`（⚠️ **调用 `write_to_file` 时仅传 TargetFile、CodeContent、Description、Overwrite: true 这 4 个核心参数，绝对严禁传递 `ArtifactMetadata` 参数！**）。

3. **步骤 3【提交 3 行回执 · 即刻退出】**：
   落盘完成后，立即且仅输出 3 行标准完工回执交卷！**严禁在对话框发送正文全文，严禁在提交后再调用 `view_file` 查验结果，严禁客套总结，干完即走！**

---

## 🔒 三、 白名单与绝对红线

- 📖 **准读文件**：`manuscript/vol_XX/raw/ch_XXX_v2.md`（单次全读，禁切片；严禁回读手册）；
- 💻 **准跑命令**：**【绝对零命令】**（零终端操作，无需运行任何命令）；
- ✍️ **准写工具（唯一）**：`write_to_file` 写入 `manuscript/vol_XX/raw/ch_XXX_v3.md`（⚠️ **严禁传递 `ArtifactMetadata`**）；

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 3B 抛光润色 (Polisher)
- 产出路径：manuscript/vol_XX/raw/ch_XXX_v3.md
- 核心指标：动词语序已优化 ｜ 语流丝滑无多余修饰 ｜ 字数基本持平 [N] 字 ｜ write_to_file 直接物理落盘
```
