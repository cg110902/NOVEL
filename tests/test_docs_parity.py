"""文档↔代码口径对账（README/AGENTS 里的数字声明 vs 引擎唯一真源）。

README.md 承诺「文档里的码数由 tests/test_docs_parity.py 与本表实时对账」——
就是本文件。跑法（仓库根）：`.venv/bin/python -m tests.test_docs_parity`
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import errcodes, state  # noqa: E402
from engine.cli import COMMAND_HELP  # noqa: E402
from engine.models import schema_gen  # noqa: E402
from engine.models.entities import EntityEntry  # noqa: E402
from engine import proposal_v3  # noqa: E402

PASS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    assert cond, f"PARITY FAIL [{name}] {detail}"
    PASS.append(name)


def main() -> int:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    # ---- 1. 命令数：COMMAND_HELP 唯一真源 ----
    check("commands_help_count", len(COMMAND_HELP) == 31, f"len={len(COMMAND_HELP)}")
    m = re.search(r"(\d+)\s*个命令名", agents)
    check("agents_commands_claim", bool(m) and int(m.group(1)) == len(COMMAND_HELP),
          f"AGENTS 声明 {m.group(1) if m else '?'} vs 实际 {len(COMMAND_HELP)}")
    cli_src = (ROOT / "engine" / "cli.py").read_text(encoding="utf-8")
    distinct_funcs = set(re.findall(r"set_defaults\(func=(cmd_\w+)\)", cli_src))
    check("commands_distinct_funcs", len(distinct_funcs) == 30, f"{len(distinct_funcs)}")

    # ---- 2. 状态表数 ----
    check("state_keys_count", len(state.STATE_KEYS) == 12, f"{state.STATE_KEYS}")
    check("asserted_keys_count", len(state.ASSERTED_KEYS) == 11, f"{state.ASSERTED_KEYS}")

    # ---- 3. 错误码数：REGISTRY 唯一真源 ----
    m = re.search(r"当前\s*(\d+)\s*条闸门码", readme)
    check("readme_errcode_count", bool(m) and int(m.group(1)) == len(errcodes.REGISTRY),
          f"README 声明 {m.group(1) if m else '?'} vs REGISTRY {len(errcodes.REGISTRY)}")

    # ---- 4a. 正向：checks.py 引用的码必须已注册 ----
    checks_src = (ROOT / "engine" / "checks.py").read_text(encoding="utf-8")
    err_refs = set(re.findall(r'_err\(\s*"([a-z0-9_]+)"', checks_src))
    err_refs |= set(re.findall(r'add\(\s*"[a-z]+"\s*,\s*"([a-z0-9_]+)"', checks_src))
    check("checks_codes_registered", err_refs <= set(errcodes.REGISTRY),
          f"未注册: {sorted(err_refs - set(errcodes.REGISTRY))}")

    # ---- 4b. 逆向：注册的码必须在引擎内有引用（防僵尸码） ----
    engine_text = ""
    for p in list((ROOT / "engine").glob("*.py")) + list((ROOT / "engine" / "commands").glob("*.py")):
        if p.name == "errcodes.py":
            continue
        engine_text += p.read_text(encoding="utf-8") + "\n"
    dead = [c for c in errcodes.REGISTRY
            if not re.search(rf"\b{re.escape(c)}\b", engine_text)]
    check("registry_codes_used", not dead, f"僵尸码: {dead}")

    # ---- 5. EntityEntry 字段数（文档 36 字段） ----
    check("entity_entry_fields", len(EntityEntry.model_fields) == 36,
          f"len={len(EntityEntry.model_fields)}")

    # ---- 6. templates/project.json 顶层键 ----
    proj = json.loads((ROOT / "templates" / "project.json").read_text(encoding="utf-8"))
    check("project_template_keys", len(proj) == 20, f"len={len(proj)}")

    # ---- 7. v3 op 动作表：V3_OP_SHAPES 的动作须有代码真源 ----
    # 寻址表须是真实状态表；v3 专有动词须出现在 compile_ops 源码；
    # 沿用 v2 语义的动词（lines/locked/cognition）须出现在 state.py 合并分支。
    compile_src = inspect.getsource(proposal_v3.compile_ops)
    state_src = (ROOT / "engine" / "state.py").read_text(encoding="utf-8")
    bad_shapes = []
    for _table, _actions, _shape in proposal_v3.V3_OP_SHAPES:
        for word in re.findall(r"[a-z_]{3,}", _table):
            if word not in state.ASSERTED_KEYS and word not in state.KIND_TABLES:
                bad_shapes.append(f"未知寻址表 {_table}:{word}")
        passthrough = _table in ("lines", "locked", "cognition")
        for tok in re.findall(r"[a-z_]{3,}", _actions):
            truth = state_src if passthrough else compile_src
            if f'"{tok}"' not in truth:
                bad_shapes.append(f"{_table}:{tok} 无代码真源")
    check("v3_op_shapes_recognized", not bad_shapes, f"{bad_shapes}")

    # ---- 8. schemas 新鲜度：落盘文件必须等于即时生成 ----
    fresh = schema_gen.regenerate_all(write=False)
    stale = []
    for name, text in fresh.items():
        disk = (ROOT / "engine" / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8")
        if disk != text:
            stale.append(name)
    check("schemas_fresh", not stale, f"漂移: {stale}（改模型后重跑 python -m engine.models.schema_gen）")

    print(f"PARITY PASS ({len(PASS)}): " + ", ".join(PASS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
