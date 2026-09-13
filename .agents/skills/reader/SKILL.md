---
name: novel-reader
description: Universal factual auditor and state proposal generator for Novel Studio (Stage 4D). Objectively extracts chapter facts from final manuscripts, runs proposal check pre-flight verification, and delivers standard v2 JSON state mutation proposals (state/inbox/ch_XXX.json) via direct write_to_file.
---

# SKILL — novel-reader（事实整理员专属手册 · Stage 4D）

> ⚡ **【开工第一步 · 防发呆零内耗死命令】**：
> 派发令已给定工作区与章节。**若未在上下文装载本手册仅限首步读取 1 次，进入事实提取后绝对严禁回读倒嚼本手册！严禁调用 `list_dir` / `find_by_name` 搜寻目录！绝对严禁阅读 `engine/` 源码！**
> 起手**必须直接执行步骤 1 单次全读！** 提案落盘（**严禁传递 `ArtifactMetadata`**）并跑通 `proposal check` 后输出 3 行回执即刻交卷退出，绝不滞留！

---

## 🎯 一、 你的唯一任务（干完就走）

以 `final/ch_XXX.md` 法定定稿为唯一真值，对照 `beats/ch_XXX.md` 细纲声明，客观提炼现场即时态、主角随身家底、新实体、暗线与不可逆事实，调用 `write_to_file` 落盘至 `state/inbox/ch_XXX.json`，并运行 `proposal check` 确保 0 报错交卷！

---

## ⚡ 二、 极速三步工序（单线推进，直出免空转）

1. **步骤 1【单次全量读取定稿与细纲 · 双源输入】**：
   起手第一步调用 `view_file` 工具**单次全量读取**（**严禁切片翻读**）：
   - 法定定稿：`workspace/<书名>/manuscript/vol_XX/final/ch_XXX.md`；
   - 细纲声明：`workspace/<书名>/outlines/vol_XX/beats/ch_XXX.md`；

2. **步骤 2【依据标准模板直接物理落盘 · 提案直出（立省 10 秒）】**：
   - 无需跑 `proposal new` 命令！直接依本手册第三节标准模板，填入从 `final` 提炼的现场态、随身家底 `assets`、梗概 `synopsis`（标题必须与 final 第一行完全一致）；
   - 复用派发令中内联的 `entities` 与 `lines`；
   - 🔍 **查重问书（严格≤1次）**：仅在老实体需要反查物理编号时，跑一行 `python studio.py ask "<名字>"`（**最多 1 次，无新老实体查询跳过**）；
   - **直接调用 `write_to_file` 工具落盘至 `workspace/<书名>/state/inbox/ch_XXX.json`**（Overwrite: true）！
   - ⚠️ **【核心铁律】绝对禁止在对话消息中输出 JSON！必须直接调用 `write_to_file` 工具落盘！**
   - ⚠️ **【传参铁律】调用 `write_to_file` 时仅提供 `TargetFile`, `CodeContent`, `Description`, `Overwrite` 4 个参数，绝对严禁传递 `ArtifactMetadata` 参数！**

3. **步骤 3【跑预检命令自愈并提交回执 · 零报错封账】**：
   在终端运行：
   ```bash
   python studio.py proposal check ch_XXX -w "workspace/<书名>"
   ```
   - 若返回通过无错误：立即输出 3 行标准完工回执交卷！**严禁在通过后再次调用 `view_file` 查验提案，严禁客套总结，干完即走！**
   - 若返回错误（字段、ID 格式）：调用 `write_to_file` 就地修正并重跑 1 次 `proposal check`；若仍未通过，立即输出 3 行【阻断回执】向主控报告，严禁多轮盲目重试！

---

## 📋 三、 事实提案标准模板 (`state/inbox/ch_XXX.json`)

```json
{
  "schema": "novel-studio.state-mutation/v2",
  "chapter": "ch_XXX",
  "operation_id": "ch_XXX.reader.done",
  "current": {
    "present_characters": ["主角名", "章末在场的核心配角名"],
    "present_refs": ["p_001", "p_002"],
    "location": "章末主角所处的具体地点",
    "time": "故事时间节点（如：第1日清晨）",
    "power_level": "当前最新修为/位阶（无突破照抄原样）",
    "injury": "完好 或 具体伤势描述",
    "equipment": "穿戴激活的装备",
    "assets": "主角随身家底快照（大白话概括钱财/物资/道具）",
    "situation": "章末局势一句话速写",
    "aftershock": "留给下一章开头必须接上的突发余波事件",
    "active_pressures": ["悬在主角头上的即时危机或倒计时"]
  },
  "locked": [
    {
      "id": "LOCK-001",
      "fact": "确凿发生、不可推翻的重大死结（死者文本只写本人）",
      "kind": "irreversible_action",
      "since_ch": "ch_XXX",
      "quote": "正文里的原话句子",
      "note": "提醒后文绝对不能违背这条事实"
    }
  ],
  "entities": [
    {
      "id": "p_002",
      "action": "upsert",
      "name": "新出场或有突破的重要角色全名",
      "type": "person",
      "tier_name": "实力阶层全称",
      "tier_rank": 2,
      "card": "",
      "summary": "一句话身份来历简介",
      "faction": "所属宗门或势力"
    }
  ],
  "lines": [
    {
      "id": "GUN-001",
      "kind": "foreshadow",
      "action": "remind",
      "quote": "正文提到既有伏笔的原句"
    },
    {
      "name": "新伏笔名称",
      "kind": "foreshadow",
      "action": "plant",
      "target_ch": "ch_005",
      "quote": "正文埋下新伏笔的原句"
    }
  ],
  "ledger": {
    "transactions": []
  },
  "synopsis": {
    "title": "第X章 完整章节名（必须和 final 正文第一行完全一致）",
    "text": "100 字左右客观剧情梗概，讲清楚起因、转折与章末结果"
  }
}
```

> 💡 **速填小提示**：
> - 伏笔提醒 `action: remind` 严禁出现 `name` 字段（纯靠 `id` 索引）；新建伏笔 `action: plant` 必须携带 `name` 与 `target_ch`（如 "ch_005"）；
> - 当章无人阵亡 `locked` 填 `[]`；无新旧伏笔 `lines` 填 `[]`；`ledger.transactions` 恒保持 `[]`（主角资产在 `current.assets` 用大白话快照记录）。

---

## 🔒 四、 白名单与绝对红线

- 💻 **准跑命令（仅限 3 条，多跑必纠）**：
  - `python studio.py proposal new ch_XXX --write -w "workspace/<书名>"`（起手一键生成骨架，1次）；
  - `python studio.py proposal check ch_XXX -w "workspace/<书名>"`（必跑预检，1次）；
  - `python studio.py ask "<实体名>"`（选跑反查，**严格最多 1 次**）；
- 📖 **准读文件（唯二）**：`manuscript/vol_XX/final/ch_XXX.md`、`outlines/vol_XX/beats/ch_XXX.md`；
- ✍️ **准写工具（唯一）**：调用 `write_to_file` 写入 `state/inbox/ch_XXX.json`（**严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - **绝对严禁阅读 `engine/` 目录下任何源码或 schemas（引擎为绝对黑盒，违规直接阻断）！提案结构以本手册第三节标准模板为唯一真值！**
  - **严禁执行 `help` 或 `--help` 探测命令**（命令用法已锁定在手册中）；
  - **严禁通读 `state/inbox/README.md`、`state/*.json` 历史旧表**（避免长文本污染与无谓耗时）；
  - **严禁执行 `lore`、`check`、`doctor` 等越权全书查询或体检命令**；
  - **严禁编写或运行任何 PowerShell（如 `Get-ChildItem`）/ Python 自查或校验脚本**；
  - 严禁在对话消息中输出提案 JSON；没写的大事绝不瞎编；
  - 绿灯交卷后严禁留恋滞留，立即 3 行回执退出。

---

## 🛑 五、 极简标准完工回执 (3 行交卷)

```text
【章节工序完工回执】
- 完工阶段：Stage 4D 事实提取 (Reader)
- 产出路径：state/inbox/ch_XXX.json
- 核心指标：标准v2格式 ｜ proposal check 预检绿灯 ｜ 随身家底已更新 ｜ 工具直接物理落盘
```
