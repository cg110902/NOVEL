"""命令实现层：book_setup（书级）/ chapter_flow（章节流转）/ state_sync（状态封存）。

由 engine.cli 薄壳调度；共享助手在 ._shared。本包只做参数后处理、合同校验与终端呈现，
确定性业务逻辑仍在 state/checks/evidence/pack 等底层引擎模块。"""
