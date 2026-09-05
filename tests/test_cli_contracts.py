"""CLI 契约测试：用法错误、安全边界、工作区解析。

覆盖来源：仓库外的故障注入套件 fi_a.sh（36 例）移植进仓库。
移植的动因是 P3-4 那个 UnboundLocalError 一路进到了 main——因为此前仓库内没有任何
测试，而套件在仓库外不受版本控制，跑不跑全凭人记得。

退出码口径（全仓库统一）：0 成功 ｜ 1 业务拒收 ｜ 2 用法错误。
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 章号归一（QA P3-3）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("token,expected_code,why", [
    # ch_7 不再是「非法章号」，而归一为 ch_007。判据是行为而非报错：
    # beats new 能出脚手架 = 归一发生；exit 2 才说明被当成非法语法。
    ("ch_7", 0, "归一为 ch_007 后正常出脚手架"),
    ("ch_0", 2, "第 0 章不存在，用法错误"),
    ("abc", 2, "无法解析为章号"),
])
def test_chapter_token_normalization(cli, book, token, expected_code, why):
    r = cli("beats", "new", token, "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == expected_code, why


def test_pack_normalized_chapter_reports_canonical_form(cli, book):
    """pack ch_7 应报 ch_007 而非 ch_7——报规范名即证明归一发生。"""
    r = cli("pack", "ch_7", "-w", book)
    assert not r.crashed, r.out + r.err
    # 归一后 ch_007 无细纲，业务拒收（1），不是用法错（2）
    assert r.code == 1
    assert "ch_007" in r.out, f"未报规范章号：{r.out[:200]}"
    assert "ch_7" not in r.out.replace("ch_007", ""), "仍在报未归一的 ch_7"


def test_evidence_dup_accepts_normalized_chapter(cli, book):
    r = cli("evidence", "dup", "ch_7", "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 0


def test_sync_normalized_chapter_is_business_reject(cli, book):
    """归一为 ch_007 后因无定稿而拒（业务 1），不是用法错（2）。"""
    r = cli("sync", "ch_7", "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 1


def test_calendar_rejects_garbage(cli, book):
    r = cli("calendar", "abc", "-w", book)
    assert r.code == 2


# ---------------------------------------------------------------------------
# 安全：路径穿越 / 越权读取
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("args", [
    ("pack", "--open", "../../etc/passwd"),
    ("pack", "--open", "../../../etc/passwd"),
    ("pack", "--open", "/etc/passwd"),
    ("evidence", "file", "../../etc/passwd"),
    ("evidence", "file", "../../../engine/state.py"),
])
def test_path_traversal_blocked(cli, book, args):
    """越界路径一律业务拒收（1），绝不能读到工作区外的文件。"""
    r = cli(*args, "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 1, f"{args} 未被拒：exit={r.code}"
    assert "越界" in r.out or "越权" in r.out, r.out[:200]


def test_pack_role_gateway_denies_state(cli, book):
    """P0-2 角色网关：drafter 禁读 state/。"""
    r = cli("pack", "ch_001", "--open", "state/current.json",
            "--as", "drafter", "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 1
    assert "网关" in r.out or "禁读" in r.out, r.out[:200]


def test_pack_illegal_role_is_usage_error(cli, book):
    r = cli("pack", "ch_001", "--as", "nosuchrole", "-w", book)
    assert r.code == 2


# ---------------------------------------------------------------------------
# config 非法输入
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("args,why", [
    (("config", "set", "generic_stopwords", "not-json"), "值不是合法 JSON"),
    (("config", "set", "words_target", "[2000]"), "区间须为二元正整数对"),
    (("config", "set", "no_such_key", "[]"), "未知参数键"),
    (("config", "get", "no_such_key"), "未知参数键"),
    (("config", "unset", "no_such_key"), "未知参数键"),
])
def test_config_rejects_bad_input(cli, book, args, why):
    r = cli(*args, "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 2, why


def test_config_suggest_does_not_crash(cli, book):
    """P2-3 回归：alias_suggestions 是派生建议、不在 PARAM_SPEC 里，
    文本渲染器曾因 KeyError 崩溃。"""
    for extra in ([], ["--json"]):
        r = cli("config", "suggest", *extra, "-w", book)
        assert not r.crashed, r.out + r.err
        assert r.code == 0


# ---------------------------------------------------------------------------
# state 手术刀边界
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("args", [
    ("state", "get", "nosuchtable.field"),
    ("state", "set", "nosuchtable.field", "x"),
])
def test_state_rejects_unknown_partition(cli, book, args):
    r = cli(*args, "-w", book)
    assert r.code == 2


def test_state_show_works(cli, book):
    r = cli("state", "show", "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 0


# ---------------------------------------------------------------------------
# ledger 资源池（QA P0-3）
# ---------------------------------------------------------------------------
def test_ledger_pool_add_requires_initial(cli, book):
    """P0-3：省略 --initial 会被当成 0，从而悄悄改掉账本基准，故必须必填。"""
    r = cli("ledger", "pool", "add", "qa_p1", "--name", "探针池",
            "--unit", "个", "-w", book)
    assert r.code == 2


@pytest.mark.parametrize("initial", [0, 247])
def test_ledger_pool_add_accepts_explicit_initial(cli, book, initial):
    r = cli("ledger", "pool", "add", f"qa_p{initial}", "--name", "探针池",
            "--unit", "个", "--initial", str(initial), "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 0, r.out[:200]


def test_ledger_pool_add_rejects_duplicate(cli, book):
    cli("ledger", "pool", "add", "dup_pool", "--name", "甲", "--unit", "个",
        "--initial", "1", "-w", book)
    r = cli("ledger", "pool", "add", "dup_pool", "--name", "甲", "--unit", "个",
            "--initial", "1", "-w", book)
    assert r.code == 1


def test_ledger_pool_add_rejects_bad_id(cli, book):
    r = cli("ledger", "pool", "add", "9bad", "--name", "甲", "--unit", "个",
            "--initial", "1", "-w", book)
    assert r.code == 2


def test_ledger_recompute_self_consistent(cli, book):
    r = cli("ledger", "recompute", "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 0


# ---------------------------------------------------------------------------
# 未知子命令
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("args", [
    ("nosuchcmd",),
    ("ledger", "nosuch"),
    ("snapshot", "nosuch"),
    ("proposal", "nosuch"),
    ("evidence", "nosuchkind"),
])
def test_unknown_subcommand_is_usage_error(cli, book, args):
    r = cli(*args, "-w", book)
    assert r.code == 2


@pytest.mark.parametrize("cmd", ["beats", "graph"])
def test_no_arg_commands_infer_chapter(cli, book, cmd):
    """P1-4：章节推断使无参调用不再是用法错误。"""
    r = cli(cmd, "-w", book)
    assert not r.crashed, r.out + r.err
    assert r.code == 0


# ---------------------------------------------------------------------------
# 工作区解析失败路径（QA P3-4 回归）
# ---------------------------------------------------------------------------
# 这一组是 P3-4 那个 UnboundLocalError 的回归网。该缺陷的成因是 ws_gate() 里给
# _RESOLVE_REASON 赋值却漏了 global，于是走「非 project_missing」分支时读未绑定的
# 局部名即崩栈——本该输出结构化错误信封的 --json 路径直接吐 Traceback。
#
# 关键：必须断言 not r.crashed，不能只比对退出码。崩栈时退出码碰巧也是 1，
# 与期望值相同，只比对退出码会让它假绿。

BAD_PATH = "/tmp/definitely-not-a-book-dir"


@pytest.mark.parametrize("args", [
    ("check", "--json"),
    ("pack", "ch_001", "--json"),
    ("ask", "灯债", "--json"),
    ("cockpit", "--json"),
])
def test_bad_workspace_json_emits_envelope_not_traceback(cli, args):
    r = cli(*args, "-w", BAD_PATH)
    assert not r.crashed, f"--json 错误路径崩栈：{r.err[-500:]}"
    assert r.code == 1
    d = r.json()
    assert d["ok"] is False
    assert "code" in d, d


def test_bad_workspace_text_mode(cli):
    r = cli("check", "-w", BAD_PATH)
    assert not r.crashed, r.err[-500:]
    assert r.code == 1
    assert "Traceback" not in r.out


@pytest.mark.parametrize("as_json", [True, False])
def test_out_of_bounds_workspace_rejected(cli, as_json):
    """/etc 在工作区根之外，必须拒收，不能当书目录用。"""
    args = ("check",) + (("--json",) if as_json else ())
    r = cli(*args, "-w", "/etc")
    assert not r.crashed, r.err[-500:]
    assert r.code == 1


@pytest.mark.parametrize("as_json", [True, False])
def test_multiple_books_requires_explicit_w(cli, ws_root, as_json):
    """多本书且未指定 -w → exit 2（不是 1）：这是「用法错误」而非「业务拒收」。

    用两本临时书构造歧义，不依赖开发者手上有几本书——否则这条断言会随环境变绿变红。
    """
    from conftest import build_book
    build_book(ws_root, "amb_a")
    build_book(ws_root, "amb_b")
    args = ("check",) + (("--json",) if as_json else ())
    r = cli(*args)
    assert not r.crashed, r.err[-500:]
    assert r.code == 2, f"多书歧义应为用法错误 2，实得 {r.code}"
    if as_json:
        assert r.json()["code"] == "multiple_books"


def test_project_missing_is_business_reject(cli, ws_root):
    """有目录但无 project.json → exit 1（业务拒收），且原因要真的传到退出码分类。

    P3-4 的第二个缺陷就在这里：project_missing 赋的是局部变量，ws_gate_code() 读的是
    模块级那个，原因永远传不过去。
    """
    shell = ws_root / "空壳书"
    shell.mkdir(parents=True, exist_ok=True)
    r = cli("check", "--json", "-w", shell)
    assert not r.crashed, r.err[-500:]
    assert r.code == 1
    assert r.json()["code"] == "project_missing"


def test_valid_book_unaffected(cli, book):
    """正常路径不能因为错误路径的改动而受影响。"""
    r = cli("check", "-w", book)
    assert not r.crashed, r.err[-500:]
    assert r.code == 0
