# qa/ — QA 可复现资产

本轮全面测试的脚本与原始证据（主报告见 `docs/QA-REPORT.md`）。

## scripts/
| 文件 | 用途 | 产物 |
|---|---|---|
| `build_pressure_book.py` | 生成 26 章压力书（完整 proposal 链，逐章走 inbox→sync 真实闸门） | `/tmp/qa_root/pb_book`（书），`/tmp/qa_root/conftest_prose.py` 由其生成正文 |
| `conftest_prose.py` | 确定性正文生成器（被 build 脚本 import） | — |
| `scale_run.py` | 22 条命令耗时/崩溃扫描（26 章书 + 60 章规模书） | `qa/evidence/scale_report.jsonl` 或 `/tmp/qa_root/scale_report.jsonl` |
| `extend_scale_book.py` | 把规模书从 N 章扩到 M 章（只加 beats/raw/final，幂等可重跑） | `/tmp/qa_root/pb100`（100 章规模书） |
| `scale_pb100.py` | 100 章复核：27 条命令耗时/崩溃/JSON 契约 + 写路径探针（snapshot create、index --rebuild） | 追加行到 `qa/evidence/scale_report.jsonl`（前缀 `pb100 `） |
| `cli_regress.py` | CLI 契约回归：rc + JSON 信封 + 产物落盘（21 路径；`--write` 允许 branch/critic 落盘） | `qa/evidence/cli_regress_report.jsonl` |

## evidence/
- `scale_report.jsonl` — 每行一条命令：`rc / 耗时 / rssΔ / crash / 输出字节 / keys`（pb_book 22 行 + pb60 16 行 + 进程内注射扫描）。
- `cli_regress_report.jsonl` — 21 条 CLI 契约用例结果行。

## 复现前提
- 本机 python3.11 venv（`.venv-novel`）+ pydantic/jieba/networkx/rich/rapidfuzz/pytest。
- 调用约定：`cd /home/user/NOVEL && NOVEL_STUDIO_WORKSPACE_ROOT=/tmp/qa_root PYTHONUTF8=1 .venv-novel/bin/python studio.py <cmd> -w <book> --json`。
- 压力书为合成数据（含时间戳操作 id），重跑生成即可；磁盘上的 pb_book/pb60/pb_heal 为临时书，随时可弃。
