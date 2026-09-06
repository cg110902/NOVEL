"""Broad CLI --json envelope contract: no bare text on stdout."""
import json


MATRIX = [
    # (args, is_argparse_usage_error)
    (["status", "--json"], False),
    (["check", "--json"], False),
    (["cockpit", "ch_001", "--json"], False),
    (["help", "--json"], False),
    (["errcodes", "--json"], False),
    (["config", "nope", "--json"], True),
    (["state", "nope", "--json"], True),
    (["graph", "nope", "--json"], True),
    (["simulate"], True),
    (["beats", "bad", "--json"], True),
    (["evidence", "bad", "--json"], True),
    (["pack", "ch_zzz", "--json"], False),
    (["pack", "--json"], False),
    (["sync", "ch_zzz", "--json"], False),
    (["sync", "ch_001", "--json"], False),
    (["proposal", "new", "ch_zzz", "--json"], False),
    (["proposal", "check", "ch_001", "--json"], False),
    (["proposal", "auto", "ch_001", "--json"], False),
    (["review", "new", "ch_zzz", "--json"], False),
    (["audit", "ch_zzz", "--json"], False),
    (["checkpoint", "ch_zzz", "--json"], False),
    (["calendar", "5", "--json"], False),
    (["ask", "x", "--json"], False),
    (["pov", "x", "--json"], False),
    (["recall", "ch_zzz", "--json"], False),
    (["evidence", "candidates", "ch_zzz", "--json"], False),
    (["graph", "neighbors", "x", "--json"], False),
    (["graph", "path", "a", "b", "--json"], False),
    (["export", "--json"], False),
    (["milestone", "list", "--json"], False),
    (["ledger", "recompute", "--json"], False),
    (["snapshot", "list", "--json"], False),
]

# Commands that accept -w; status/check/cockpit/export/milestone/ledger/snapshot all do,
# help/errcodes don't.
ACCEPTS_W = set({"status", "check", "cockpit", "pack", "sync", "proposal", "review",
                 "audit", "checkpoint", "calendar", "ask", "pov", "recall", "evidence",
                 "graph", "export", "milestone", "ledger", "snapshot", "beats", "config",
                 "state", "simulate"})


class TestJsonEnvelope:
    def test_no_bare_stdout_on_json(self, ws, book):
        for args, is_argparse_usage in MATRIX:
            cmd = list(args)
            if "-w" not in cmd and cmd[0] in ACCEPTS_W:
                cmd += ["-w", str(book)]
            p = ws.run(cmd)
            if is_argparse_usage:
                assert p.stdout == "", f"{cmd} should leave stdout empty on argparse error: {p.stdout!r}"
                assert "usage:" in p.stderr
                continue
            if p.stdout:
                try:
                    parsed = json.loads(p.stdout)
                except Exception as exc:
                    raise AssertionError(f"{cmd}: stdout not JSON: {p.stdout[:200]!r} ({exc})")
                assert isinstance(parsed, (dict, list))


# Error paths that should always carry a structured {ok:false, code} envelope when --json.
ERROR_MATRIX = [
    (["critic", "ch_001"], 1),
    (["critic", "ch_zzz"], 2),
    (["proposal", "check", "ch_001"], 1),
    (["proposal", "verify", "ch_001"], 1),
    (["proposal", "auto", "ch_001"], 1),
    (["sync", "ch_001"], 1),
    (["state", "get", "entities.不存在.realm"], 1),
    (["milestone", "add", "--title", "x", "--target-ch", "0"], 2),
    (["ledger", "pool", "add", "1bad", "--name", "燃料", "--unit", "升", "--initial", "10"], 2),
]


class TestJsonErrorEnvelope:
    def test_error_payloads_have_ok_and_code(self, ws, book):
        for args, rc in ERROR_MATRIX:
            p, data = ws.run_json(args + ["-w", str(book), "--json"])
            assert p.returncode == rc, f"{args}: rc={p.returncode} stdout={p.stdout!r}"
            assert data.get("ok") is False, f"{args}: {data}"
            assert data.get("code"), f"{args}: missing code in {data}"
            assert data.get("error"), f"{args}: missing error in {data}"

