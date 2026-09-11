"""tests.stress — 长篇一致性压力测试 harness（零 token、确定性、断点可续）。

分层（方案 §0.1）：L1 合成书（generator）｜L2 浸泡（soak）｜L3 故障注入（faults+chaos）
｜度量与判定（metrics/eval/report）｜L4 真 LLM 抽样不在本包（需人批预算，另行执行）。

纪律：
- 本包只调用引擎公开函数/CLI（engine.cli.main 进程内派发），绝不 import 引擎私有逻辑复刻校验；
- 产物全部落在书工作区 log/stress/ 与 state/（快照等），基线文件 tests/stress/baseline.json；
- 生成器唯一真源是 plan_book()（纯函数）：一切落盘与提案都由 plan 驱动，manifest 自检即合同。
"""
