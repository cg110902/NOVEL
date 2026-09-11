# 压力基线与阈值校准（Phase-1 首轮实测，2026-09-11）

> 口径约定：一切性能数字只作**相对基线**解读（改动后回归对比用），不对外承诺绝对值。
> 本文数字来自 `stress_full`（300 章 × ~3000 字，seed=42，零 token 剧本）首轮全链 PASS。

## 1. 基线（tests/stress/baseline.json 的 full 槽）

| 指标 | 基线值 | 说明 |
|---|---|---|
| check_p95（s） | 22.4 | 300 章折叠态全量 check，每 cp 一次 |
| sync_sec_mean（s） | 4.45 | 含 materialize 落盘 + 提案 + 全闸门链 |
| state_bytes_last | 195.4 MB | 其中 changelog.jsonl 占 190.1 MB（97%） |
| wall_cp（s） | 660.9 | soak 末段每 10 章窗口墙钟（含 check） |

soak 全程 2285.6s / 295 章 ≈ **7.75s/章**（end-to-end，含每 cp 的 check 与剪枝）。
本轮为 F02/F03 剧本修正后的重确认轮：**10/10 红线 + 17/17 抓雷（无一 N/A）全绿**。

## 2. §7 阈值初值校准建议

- **check 耗时**：实测近线性 0.26s@ch10 → 25.2s@ch300（斜率 ≈0.083s/章）。
  建议红线：`check_p95 > 基线 ×2` 或**超线性拐点**（相邻 cp 斜率连升 3 段）告警。
- **pack 预算**：p0_ratio 0.913–0.952（预算 20000 恒定、内容膨胀靠折叠消化），
  `hard_cap_ratio = 0.0`（300 章从未破硬顶，压缩阶梯全程在 P0–P2 内消化）。
  建议红线：hard_cap 占比 > 0 即红；p0_ratio > 0.98 连超 3 cp 转黄。
- **表增长**：changelog.jsonl 斜率 6.7 MB/10章，是唯一 O(N) 巨表；其余表（ledger 6002 行、
  timeline 2414、lines 601、processed 302）体积均 < 3.1 MB。
  建议观察线：单表（除 changelog）> 50 MB 转黄；changelog 折叠态 > 1 GB 转黄。
- **快照**：保留 3 份 + 剪枝在 300 章尺度下稳定（每次剪 ≤10），无磁盘风险。
- **告警噪声**：良性码 union 峰值 6（milestone_overdue 修剧本后由 8 降至 4–5 常态）。
  建议红线维持「意外码 = 0」不放宽——首轮 FAIL 的 4 项全部证明是**真缺陷**（1 个 harness
  排程 bug、1 个引擎豁免语义缺口、2 个剧本缺口），没有一项该被白名单吞掉。

## 3. 引擎行为观察（压测换来的，非缺陷即注记）

1. `milestone achieve` 等 CLI 正道写 state 后，**幂等重复 sync（duplicates 路径）不会重盖章**
   ——「重跑 sync 即可消除 state_offline_edit」的提示语只对带新提案的 sync 成立。
   harness 对策：卷末里程碑在**本章 sync 之前**核销，让本章封存覆盖（stress 已按此实现）。
2. 位阶「无事件偏移」旗（tier_shift_without_event）只在 replay 见到**先有 rank 再变**时触发：
   单条负向写入（首次即跌）不可见。埋雷必须「有事件升阶 + 无事件掉落」成对。
3. remind op 不回填 remind_ch，而 subplot_stall 依赖 remind_ch → 永久良性告警（模型缺字段，见
   BENIGN 注）；misunderstanding 无 plant_ch 字段 → plan↔actual 只能到 target/status 粒度。
4. 死者持有物会阻断 sync（需死亡章同批移交 op）——剧本已内建，属引擎正确纪律。

## 4. 首轮 FAIL → 修复清单（保留作反例）

| 红线 | 根因 | 处置 |
|---|---|---|
| manifest_diff（GUN-299..302 失踪） | `_spread` 排程步长下溢 → 埋点章号 > N | 排程按 (last-first)/(count-1) 铺 |
| ladder_order | 阶梯可合法跳过空档级，检查却按前缀 | eval 改「单调子序列」判定 |
| milestone_overdue（意外码） | 合成剧本卷末没核销里程碑 | sync_chapter 卷末章前置 achieve |
| fault_capture F04 | 见 §3.1：单次掉落不可见 | generator 成对埋（warm@max(60,·) + fall@N-12）|
| fault_capture F15 | mood_drift 章卡司未含主角（90% 规则跳过注入） | 主角强制进该章卡司 |

## 5. word-hell 基线（200 章 × ~5000 字，2026-09-11，PASS 17/17）

| 指标 | word-hell | full（300×3000，重确认轮） | 读法 |
|---|---|---|---|
| check_p95 | 12.9s | 22.4s | 字数加倍 ≠ 耗时加倍：check 成本主轴是**章数×线数**，正文加厚几乎不涨 |
| sync_sec_mean | 2.88s | 4.45s | 同上（sync 的 verify 扫 finals 是线性项，pack 折叠吸收了膨胀） |
| state_bytes_last | 65.9 MB | 195.4 MB | 全由 changelog 行数驱动（10605 vs 18520 行），与单章字数无关 |
| soak 墙钟 | 1001.8s/195 章（5.1s/章） | 2285.6s/295 章（7.75s/章） | 章均成本随 N 缓增（check@cp 摊入） |

- 硬顶占比 0.0、p0 挤压 0.91–0.94、pack 与 full 同带——**字数地狱不压 pack**（正文不进包，
  进包的是折叠摘要），压的是 audit 扫描；两轴的预算红线应分开盯。
- 本轮抓雷过程固化了两条剧本纪律（harness 侧）：
  ① F02 死线必须铺早期槽位（gap 随 N 线性拉大才稳过 冷阈×2），且死线要保留 plant+2 后
     的正文心跳——longline_stale **明跳 never 档**（归 line_never_surfaced，防双报），
     封成零锚反而灭旗；
  ② F03 前置线必须封到读者画像 never/impression 档，且 **plant op 的 plan 文案不能含
     登记专名**（line_terms_for 把 blob 内出现的实体名并入提词，场地名一旦入 plan，
     全书该场地章都是假回响 → 永不冷）。

## 6. chap-hell（1500 章）执行注记

full 外推 7.9s/章 → 1500 章单程约 3.3h（soak 部分）+ 每 cp check 增长（末段 ~60-90s/次）。
soak 支持 `--from N --resume` 断点续跑，可按会话分段；跨会话续跑勿带 `--fresh`。
建议先跑 ch300→ch600 一段验证「表体积/告警无阶跃」，确认后剩余段为纯时间问题。
