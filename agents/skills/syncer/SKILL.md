# SKILL — syncer（主控 Stage 4 同步作业，不 spawn）

你就是主控。本节是 Stage 4 里「组提案 → sync」的作业清单，不是派出去的岗位。
校对与注记也是你写的（先注记后提案）。不要对自己「交付即销毁」或「回报主控」。

## 使命

产出并跑通 `state/inbox/ch_XXX.json`：让 6 个状态文件与 final 正文严丝合缝，快照封存，
流水线绿。读 final、写校对注记、组装六区提案、跑 sync、封存快照——都是你自己做。

## 输入

- 本章 beats / raw / final + 你写的 `log/review/ch_XXX.md`。
- 当前状态用命令取（`status` / `evidence` / `pack`），不要通读 `state/*.json`。
- 提案样例照抄 `state/inbox/README.md`（不要为填提案去读 engine 源码）。

## 动作

1. 提事实清单：位置/时间/在场人物变化（`present_characters` = 章末仍在场的人）；
   POV 心境/当下动机变没变（mood/goal，没变不写）；
   实体增改（新专名对照 beats 里的 `[新实体→注册]`；重要道具的持有者/所在/完损变没变——
   holder 必须是已注册人名，没注册先在同一提案里注册）；线动作（plant/remind/resolve——正文没写的回收
   不许进提案；秘密被揭穿=knowledge resolve，新确立的秘密/信息差=knowledge plant，
   target_ch 写计划揭示章；新 plant 顺手给权重 weight 1-3，越该优先还/揭的越大；误会线字段名是 `level`）；
   编年事件与 arc 阶梯；每笔钱的进出；本章梗概（两三句，写"发生了什么"不写"感觉如何"）。
   `evidence candidates ch_XXX` 出机器对照（线名命中/金额串/新实体标记行/在场提及计数/状态摘要）
   ——只出数，是否上账归你裁决。
2. 组装提案：只写增量，不复制全量；operation_id = `ch_XXX.director.<序号>`；
   数字与正文逐字核对（账本 delta 是整数，正收负支）。
3. `proposal check ch_XXX`：结构预检 + 三方事实对照（final 金额×提案交易、到期线×提案操作、
   present×提及、KNO 揭示时机×计划章）→ `sync ch_XXX --dry-run`：看计划里每个分区条数对不对。
   对照出"揭示时机提前/逾期"时，把数记进注记再由你定夺，不要为了体检改 target 或撤 resolve 去凑绿。
4. 正式 `sync`（引擎自动：合并→体检→快照 `<ch>_done`）。
5. 失败处理：读 failed/ 里的报错 → **改提案文件**（事实本身有歧义时，改前先读正文定夺）→
   重跑 sync 自动捡回。反复两次仍红 = 事实冲突：修正文（情节层回 Stage 2）或修提案，不许编数字凑平。

## 输出

- `state/inbox/ch_XXX.json`（一份，只写增量）。
- `sync` 成功会把提案归档到 `state/inbox/processed/`、生成 `state/snapshots/<ts>_<ch>_done`；
  `status` 该章 beats/raw/final 齐、已合并、已快照即完成。`failed/` 里有提案 = 未完成，读报错后改提案再 sync。

## 禁区

不手改 state JSON（唯一写入通道是 inbox→sync）；错别字级问题按 novel_workflow.md#文字级边界
直接补丁，不要列给另一个自己；不改 processed/failed 历史；
不猜冲突（引擎报"已存在/引用未登记"时，正确动作是读正文找到事实出处再改提案）。

## 退回

final 自身有事实硬伤导致无法建模（如人物无因知晓）→ 不造提案掩盖。
情节硬伤回 Stage 2；仅表达层问题才同 raw 重派 guard。这是 Stage 3 验收漏网，不是用提案圆过去的活。
