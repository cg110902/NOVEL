"""引擎门禁测试（stdlib only：`python -m tests.test_docs_parity` / `python -m tests.test_smoke`）。

跑法（仓库根目录）：`.venv/bin/python -m tests.test_docs_parity`
设计成无 pytest 也能跑：每个 test_* 是一个 main()，断言失败抛 AssertionError，
最后打印 PASS 摘要。挂 CI 时同样零依赖。
"""
