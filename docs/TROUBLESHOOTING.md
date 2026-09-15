# Novel Studio 实战避坑与故障自愈手册 (Troubleshooting & FAQ)

本文档整理了人类作者与主控在日常连载、无人值守巡航及工程环境配置中，最常遇到的典型问题、底层原因与秒级自愈方案。

---

## 目录
- [一、 环境与依赖类故障](#一-环境与依赖类故障)
- [二、 创作流水线与体检阻断](#二-创作流水线与体检阻断)
- [三、 剧情写偏与快照安全回滚](#三-剧情写偏与快照安全回滚)
- [四、 账目与底层索引修复](#四-账目与底层索引修复)
- [五、 无人值守中断与断点续写](#五-无人值守中断与断点续写)

---

## 一、 环境与依赖类故障

### 1. 启动报错并返回退出码 3（缺少依赖库）
- **错误现象**：
  ```text
  ❌ 运行环境缺少依赖，引擎无法启动。
     缺失模块：pydantic（或其他模块名）
  ```
- **底层原因**：当前使用的 Python 解释器尚未安装依赖，或者使用了未激活的虚拟环境。
- **一秒修复**：
  在终端执行以下命令，确保依赖完整安装至当前解释器：
  ```powershell
  python -m pip install -r requirements.txt
  ```
  *(注：Python 版本要求必须为 `>= 3.10`；`sqlite3` 为 Python 内置库，请勿通过 pip 安装)*。

### 2. Windows PowerShell 脚本禁止运行报错
- **错误现象**：
  ```text
  File ... cannot be loaded because running scripts is disabled on this system.
  ```
- **底层原因**：Windows 系统的 PowerShell 默认安全策略限制了本地脚本执行权限。
- **一秒修复**：在 PowerShell 窗口中运行以下命令开放当前用户权限：
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```

### 3. Windows 控制台字符或 Emoji 编码报错
- **错误现象**：`UnicodeEncodeError: 'gbk' codec can't encode character...`
- **底层原因**：Windows 历史遗留的 cmd / PowerShell 默认代码页可能为 GBK (cp936)。
- **已内置保护**：`studio.py` 内部已强制注入 `PYTHONUTF8=1` 与 UTF-8 输出重配置。如果手动在终端交互，建议在终端中先执行：
  ```powershell
  chcp 65001
  ```
  推荐使用现代化的 **Windows Terminal** 或 IDE 内置终端。

---

## 二、 创作流水线与体检阻断

### 1. 运行 check 或 sync 退出码为 1（业务硬阻断）
- **错误现象**：`check` 扫描出 `errors: [E...]`，或 `sync` 提示仲裁未放行。
- **底层原因**：触发了事实一致性机械硬闸门（如主角位阶与公理不符、人物 Want/Fear 未补齐、存在未定义的幽灵实体等）。
- **一秒自愈**：
  1. 查看终端打印的错误代码（如 `E101`）；
  2. 运行错误码字典查询具体处方：
     ```powershell
     python studio.py errcodes -w "workspace/<书名>"
     ```
  3. 按照提示补充缺失的卡片（如 `characters/<角色>.md`）或调整数值，然后重新运行即可放行。

### 2. 遇到良性警告（Warning）如何消音备案？
- **场景**：部分特殊情节（如特定过渡章节字数略短、故意留长线伏笔暂不兑现）引发了系统的良性警告，但剧情完全合理。
- **一秒消音**：
  运行带 `--accept` 参数将该警告特征码记录至白名单：
  ```powershell
  python studio.py check --accept <fingerprint> -w "workspace/<书名>"
  ```
  消音备案后，该警告不再影响后续流程。

---

## 三、 剧情写偏与快照安全回滚

### 1. 章节写偏、人设崩塌或剧情冲突，如何彻底推倒重来？
- **核心机制**：Novel Studio 每章在 Stage 5 原子封存时都会自动打物理快照。
- **恢复步骤**：
  1. **查看历史快照清单**：
     ```powershell
     python studio.py snapshot list -w "workspace/<书名>"
     ```
  2. **一键回滚到目标章节（同时清除错误的草稿）**：
     ```powershell
     python studio.py snapshot rollback <快照名> --clean-drafts -w "workspace/<书名>"
     ```
  3. 执行后，状态机真值表与大纲瞬间恢复至指定快照点，且未封存的冲突草稿会被干净抹除。

---

## 四、 账目与底层索引修复

### 1. 金额流水、贡献点或资产计算存疑
- **场景**：多次修改正文后，角色的货币余额或道具数量显示异常。
- **一秒平账**：
  运行账本重算命令：
  ```powershell
  python studio.py ledger recompute -w "workspace/<书名>"
  ```
  引擎会沿着历史所有法定定稿流水，重新校验每一笔出入账，全量重算并修复 `balance_after`。

### 2. 全文问书检索或实体拓扑异常
- **场景**：使用 `ask` 问书或 `graph` 查人际链路时报错或搜不到已知正文。
- **一秒重建**：
  运行底层 SQLite3 FTS5 全文索引重建：
  ```powershell
  python studio.py index --rebuild -w "workspace/<书名>"
  ```
  缓存将在 1 秒内全量重建完毕。

---

## 五、 无人值守中断与断点续写

### 1. 无人值守连写时触发 API 额度上限（429 报错）
- **完全不用慌**：
  - Novel Studio 实行**逐章原子封存**机制；
  - 只要前一章输出了 `✅ [无人值守心跳] 第 XX 章已封存`，该章的定稿正文、状态机台账、快照就已经 100% 物理安全写入磁盘；
  - 额度耗尽仅中断当前正在起草的半成品，绝不会污染历史已完成章节。
- **断点续跑**：
  等 API 额度刷新（或第二天限额重置）后，**直接在聊天框输入：`无人值守继续写`**，主控会自动读取 `cockpit` 识别最新进度，无缝从中断点继续推进！
