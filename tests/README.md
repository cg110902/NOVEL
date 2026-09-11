# tests/ — 引擎门禁测试地图（零依赖，改引擎必跑）

## 一、怎么跑

```bash
# 前置：依赖装在某解释器环境里（仓库惯例用 .venv）
.venv/bin/python -m pip install -r requirements.txt

# 一条命令跑全门禁（带逐项耗时与总 verdict）
.venv/bin/python -m tests.run_all            # 全量 ≈ 9 分钟（含 stress 自测与崩溃恢复）
.venv/bin/python -m tests.run_all --only parity smoke   # 快档 ≈ 15 秒
.venv/bin/python -m tests.run_all --list

# 也可按 README 第六节逐件单跑
.venv/bin/python -m tests.test_docs_parity
.venv/bin/python -m tests.test_smoke
.venv/bin/python -m tests.test_gates
```

约定：无 pytest、纯 stdlib；每个模块自带 `main()`，断言失败抛 `AssertionError`；
所有建书类测试都在 `tempfile` 临时目录 + `NOVEL_STUDIO_WORKSPACE_ROOT` 隔离，绝不碰 `workspace/`。

## 二、三件套各自锁什么

| 套件 | 唯一真源 | 锁住的口径 |
|---|---|---|
| `test_docs_parity` | `COMMAND_HELP` / `STATE_KEYS` / `REGISTRY` / Pydantic 模型 | README·AGENTS 里全部数字声明（31 命令 / 30 处理函数 / 11+1 表 / 106 码 / 36 字段 / 20 配置键）、错误码正反注册表、`schemas/*.json` 新鲜度、v3 op 形状代码真源 |
| `test_smoke` | 临时书全链 | `build_smoke_book`：init→beats→raw/final→proposal→audit→sync→check→pack 闭环 rc=0；pack 注入 present_moods/伤势/声望；beats 心境基线；calendar 长线 |
| `test_gates` | `build_smoke_book` + 违规注入 | 24 组场景 142 项断言：读者记忆档位边界、悬空引用三档分工、双轨对账、别名确定性、derived 封存/失鲜、账本透支与豁免、历史折叠、locked 提名、pack 压缩阶梯与预算小票、锚点旋钮、确认消音基线、修订闭环重报、v3 心境回环、孤儿锁抢占回收、v3 update 防静默搬表等 |
| `test_stress_smoke` | `tests/stress/` 生成器 | 压力 harness 自测（30 章 smoke 书全链）：plan 确定性指纹、build→soak 逐章真 sync、manifest plan↔actual diff 空、L3 live 雷现场注入全抓且还原清账、eval 红线全绿。规模档（full/chap-hell/word-hell）不进 CI，按 §6.3 铁律人工分批跑：`python studio.py stress all --scale full` |
| `test_crash_recovery` | `tests/stress/` 生成器 + 真 `engine.cli` 子进程 | 崩溃恢复：ch6..15（含死亡章）逐章在 sync 写入窗 SIGKILL 真实子进程，重跑必须 ≤4 次收敛；断言 check E=0、changelog 无撕裂尾行、manifest plan↔actual 对账到已同步章、inbox 无残卷。专抓锁残留/半程落盘/重放不幂等（2026-09 由它抓出 file_lock 孤儿锁与 FIX-4 静默搬表两个引擎级 bug） |

复用点：`test_smoke.build_smoke_book(wsroot) -> (book, env)` 是全部临时书的单一脚手架，新增 e2e 一律从它出发，不要另建书。

## 三、当前覆盖地图（缺口即待办）

**覆盖强**：sync 闸门链（beats/raw/final/audit front-matter/空变更/verify_state）、check 各码触发、
pack 预算与准读网关（部分）、state 合并语义（别名/幂等/双轨/retire）、账本算术。

**零或近零直接测试的子系统**（2026-09 基线巡检 32 探针全绿＝功能可用，但无回归网）：

| 缺口 | 建议测试要点（可低成本复用 build_smoke_book） |
|---|---|
| `snapshot create/list/rollback --clean-drafts` | manifest SHA-256 逐文件校验；损坏快照拒绝回滚；回滚后 changelog 不清空且补录事件；inbox/processed 不被触碰 |
| changelog 事件溯源 | `fold(基线, 事件) == 磁盘` 不变量；`state at/diff/blame` 三视图一致性；外部手改自动补录 |
| `state/rollups` + pack 前情注入 | rollup 幂等（重跑字节一致）；prior digest ≤1000 token 与尾部裁剪优先级 |
| `migrations` | 版本戳缺失=遗留格式首读自动迁移；迁移前快照+闸门预验；版本高于引擎→拒绝；只修结构不碰事实 |
| `index` / `db.py` FTS5 | 双跑增量（finals_fp 指纹新鲜免重刷）；删库重建等价；损坏降级不阻断 check |
| `voiceprint` / `memory` 深档 | 对白归属启发式（连引号互怼丢弃）；line_recall_cold/line_never_surfaced 阈值随 weight 缩放 |
| `audit` 其余 7 探针 | 现仅 `probe_secret_leakage` 被点测；locked 违背/在场死亡/充能/金额/认知差/别名漂移/称谓对账 各补正反例 |
| `graph` / `lore` / `ask` / `pov` / `recall` / `export` / `checkpoint` / `milestone` / `review` / `config set --merge` / `evidence <kind>` | CLI 面 smoke 级：rc=0 + `--json` 可 loads + 关键字段存在（本次已人工验证 32 探针全绿，落进测试即锁死） |
| `pack --open` 网关 | 每角色 × 每禁读前缀的拒/放行矩阵；`../` 与软链绕过、`state/current.json.bak` 类白名单前缀混淆（deny_reason 已修，需回归钉住） |
| `proposal --v3` 寻址严格性 | create 撞名/双不存在、update 表错位、retire 不存在——编译期报错带 [op#N]；同效异写不吞 |
| 并发/锁 | `file_lock` 重入与陈旧锁抢占（>120s）、并发 sync 互斥、崩溃窗口（状态已写登记簿未写→重放幂等） |

优先级建议：**回归风险高 × 引擎承诺强**的先补：changelog fold 不变量、快照回滚、pack 网关绕过矩阵、audit 七探针；
其次 migrations 与 index 缓存失配回退；CLI 面 smoke 可合一件「tests/test_cli_surface」批量锁 rc/JSON 契约。

## 四、加测试的纪律

1. 不新增第三方依赖（pytest 也不进 requirements）；要并行/选择性跑用 `tests/run_all.py`；
2. 断言口径引用唯一真源（枚举从 `models`/`state` 派生），测试里不手抄字面量集合——同引擎纪律；
3. 新增 check 码须同步 `errcodes.REGISTRY`（`test_docs_parity` 会拦）；文档数字声明改动由 parity 对账；
4. 违规注入类测试遵守「try/finally 还原现场」惯例（见 test_gates），临时书放 `tempfile`，产物不落仓库。
