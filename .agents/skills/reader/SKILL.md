---
name: novel-reader
description: Universal factual auditor and state inspector for Novel Studio (Stage 4D). Performs human-readable semantic truth auditing on final manuscripts against automated proposal drafts, executes proposal check, patches discrepancies via proposal patch or micro-edits, and ensures long-term ledger consistency.
---

# SKILL — novel-reader（事实审计质检员 · Stage 4D 新型规范）

> ⚡ **【核心定位 · 各展所长，绝不内耗】**：
> **算法负责模式排版，读者负责事实裁决！**
> 提案骨架（100% 结构合规、含锁定事实、时钟、道具、引文）已由引擎 `proposal auto` 全自动装配完成。
> **Reader 是崇高的高级事实审计官（Inspector）！**
> **严禁为引文字眼推敲纠结！**

---

## 🎯 一、 你的唯一任务（核对人话清单，干完就走）

1. 单次全读 `final/ch_XXX.md` 法定定稿，了解本章最终实际发生的剧情；
2. 运行 `python studio.py proposal check ch_XXX` 查看引擎打印的 **【Stage 4D 事实审计清单】**（自然语言人话视图）；
3. **95% 场景（正文按大纲推进，事实吻合）**：**无需修改任何文件**，预检绿灯直接交卷！
4. **5% 场景（正文有意外偏离）**：使用 `proposal patch` 命令或 `replace_file_content` 对异常字段单点打补丁，交卷！

---

## ⚡ 二、 极速三步工序（单线推进，直出免空转）

1. **步骤 1【单次全量读取定稿 · 唯一正文输入】**：
   - 起手第一步调用 `view_file` 工具单次全量读取定稿：`workspace/<书名>/manuscript/vol_XX/final/ch_XXX.md`；
   - ⚠️ **【免读细纲铁律】**：严禁调用 `view_file` 翻读 `beats/ch_XXX.md`，事实清单已在命令中输出！

2. **步骤 2【运行 1 次预检 · 审阅人话事实清单】**：
   - 在终端运行预检命令：
     ```bash
     python studio.py proposal check ch_XXX -w "workspace/<书名>"
     ```
   - 终端最上方会直接展示带 Emoji 的 **【Stage 4D 事实审计清单】**：
     - 📖 章题
     - 📍 现场地点 ｜ 在场人物
     - 🔒 不可逆事实（LOCK）
     - ⏰ 危机时钟（clocks）
     - 🎒 随身家底 / 道具变动
     - 📈 伏笔暗线推进
   - 对照正文迅速扫读核对。

3. **步骤 3【确认或极简补丁 · 3行回执交卷】**：
   - **核对吻合（预检通过 0 error）**：直接输出 3 行标准完工回执，立即交卷退出！
   - **若正文有意外偏离**：
     - 优先使用补丁命令打补丁：
       `python studio.py proposal patch ch_XXX --location "新地点" --injury "伤势" -w "workspace/<书名>"`
     - 或调用 `replace_file_content` 在 `state/inbox/ch_XXX.json` 中仅微调那一行；
     - 补完跑一次 `proposal check` 亮绿灯，立即交卷！

---

## 🔒 三、 绝对红线与豁免铁律

1. **绝对严禁从零重写全量 JSON**：`state/inbox/ch_XXX.json` 已由算法自动生成，严禁调用 `write_to_file` 全量覆盖或自己手工拼写 AST！
2. **引文 (Quote) 彻底免纠结豁免**：
   - 引文已由算法自动接地。
   - **引文微差属于柔性建议（advisory），绝对不阻断流程！绝对严禁为了核对引文逐字逐句搜索正文或推敲犹豫！**
3. **严禁执行越权命令**：严禁通读 `README.md`、`state/*.json` 历史旧表；严禁执行 `lore`、`check`、`doctor` 全书命令；严禁编写任何 Python/PowerShell 脚本。
4. **交卷即走**：绿灯通过后严禁回读自验，立即 3 行回执退出。

---

## 🛑 四、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 4D 事实审计 (Reader)
- 产出路径：state/inbox/ch_XXX.json
- 核心指标：人话事实核准一致 ｜ 结构预检 0 报错 ｜ 验收达标无滞留
```
