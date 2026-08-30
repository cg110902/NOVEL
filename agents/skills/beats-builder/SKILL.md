# SKILL — beats-builder（主控 Stage 1 细纲作业，不 spawn）

你就是主控。本节是 Stage 1 里「写细纲」的作业清单，不是派出去的一次性代理。
写完拍点不要停：同文件尾部接着写任务书四节（见 novel_workflow.md#任务书合同）。

## 使命

为 ch_XXX 产出一份「下一章非写不可」的细纲：拍点、信息差动作、要埋/唤/还的线——
并带上合法 front-matter，让任务书有结构可装。

## 输入

- `python studio.py status` 的缺口章号；`evidence gaps` 与 `evidence prev`（上章 form/旋钮/
  words 带/必须保留对照）；main_plot 与卷纲；`state/current.json`。
- 标准取自 `novel_craft.md#视角与信息差`、`novel_craft.md#反公式化与拟人化`。
- 线账用 `evidence gaps`，不要通读 `state/lines.json`。

## 动作

1. 定 form：对照 novel_craft.md#反公式化与拟人化 章型库与 `evidence prev` 给出的上一章 form；
   同卷分布数据在 `evidence style` 的 form_distribution——接近饱和的 form 别选；
   选与上章相同必须写 `form_reason`。本书第一章无上一章，不写 form_reason。
2. 拆场景（一到三场）：每场两问——POV 进场知道什么、退场知道什么。
3. 标注线动作：本章 plant/remind/resolve 哪些 GUN/MIS/KNO（remind 只适用伏笔；
   秘密被揭穿=KNO resolve，新确立的秘密/信息差=KNO plant）；**逾期线**若本章不还，写一行
   "顺延理由"（之后抄进提案或下章 beats）。
4. 写 front-matter：只放合法键（见 `novel_craft.md#front-matter 键`），form/pov/words/style_notes 齐全。
5. 章尾方式在 style_notes 里写明（四选一见 `novel_craft.md#钩子与爽感节奏`）。
6. 同文件接着写任务书四节（目标/必须保留/本章禁忌/验收）。限制装配仍是你的活，合同不在本节重复。

## 输出

`outlines/vol_XX/beats/ch_XXX.md`：front-matter + 拍点 + 线动作 + 任务书四节。
不碰 manuscript/ 与 state/。

## 禁区

每出现一个新专名，在拍点行尾标 `[新实体→注册]`（Stage 4 写 entities 提案时用）；
不写正文样句（会传染起草）；不把 novel_craft.md 原文粘进拍点当理由。

## 退回

自交检不过 → 你自己重写（novel_workflow.md Stage 1 退回边）。材料不够就先补 evidence/卷纲再写，
没有「缺语境早退再派」——这里没有第二个你可派。
