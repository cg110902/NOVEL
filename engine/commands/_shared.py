"""命令层共享助手：章号规范、公共 CLI 参数与工作区越界防护（命令模块唯一取用口）。"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .. import common

SLOT_RE = re.compile(r"\{\{\s*slot:(\w+)(?:\|[^}]*)?\s*\}\}")

# _resolve_and_validate 是否已自行打印过失败说明（多书歧义 / -w 越界）。
# 置位后 print_ws_not_found() 抑制误导性的二次报错（QA P2-2 / P3-11）。
_RESOLVE_NOTE_SHOWN = False
# QA P5/P12：解析失败原因登记（JSON 错误信封与「二次打印去重」共用同一事实源）。
_RESOLVE_REASON: str | None = None


def _norm_ch(token: str) -> str | None:
    if isinstance(token, str) and re.fullmatch(r"ch_\d{3,}", token):
        return token
    n = common.chapter_token_to_num(token)
    return f"ch_{n:03d}" if n and n >= 1 else None


def _add_common_opts(p: argparse.ArgumentParser, json_flag: bool = True) -> None:
    p.add_argument("-w", "--workspace", help="书工作区目录（如 workspace/我的书）；仅一本书时可省略")
    if json_flag:
        p.add_argument("--json", action="store_true", help="结构化 JSON 输出（Agent 首选用例）")


def print_ws_not_found(msg: str = "❌ 未找到书工作区或其 project.json（先运行 init）") -> None:
    """统一的「工作区不可用」出口：若 _resolve_and_validate 已打印过准确说明则静默。"""
    if _RESOLVE_NOTE_SHOWN:
        return
    print(msg)


def resolve_note_shown() -> bool:
    """_resolve_and_validate 本轮是否已打印过失败说明（QA P12：调用方二次打印前必须查询）。"""
    return _RESOLVE_NOTE_SHOWN


def _resolve_and_validate(ws_arg: str | None, suppress_text: bool = False) -> Path | None:
    """统一解析并校验工作区必须在 workspace_root 之下（防 -w 越界）。

    失败时打印唯一一条准确说明后返回 None（调用方按 None 返回退出码）：
    - 多本书未指定 -w：列出全部书目录请求指定（此前误报「未找到 init」，QA P2-2）；
    - 显式 -w 越界：打印越界错误；
    - 其余（0 本书等）：交给调用方的「未找到」提示。
    suppress_text=True（--json 模式）时不向 stdout 打文本，由调用方输出 JSON 信封（QA P5）。
    """
    global _RESOLVE_NOTE_SHOWN, _RESOLVE_REASON
    _RESOLVE_NOTE_SHOWN = False
    _RESOLVE_REASON = None
    if not ws_arg:
        books = common.list_books()
        if len(books) > 1:
            _RESOLVE_NOTE_SHOWN = True
            _RESOLVE_REASON = "multiple_books"
            if not suppress_text:
                print("📚 存在多本书，请用 -w 指定其一：")
                for b in books:
                    print(f"   - {b}")
            return None
    book = common.resolve_workspace(ws_arg)
    if book is None:
        _RESOLVE_REASON = "workspace_not_found"
        return None
    try:
        # 若显式指定 -w，必须校验在 workspace_root 内
        if ws_arg:
            common.ensure_workspace_inside(book)
    except ValueError as exc:
        _RESOLVE_NOTE_SHOWN = True
        _RESOLVE_REASON = "workspace_out_of_bounds"
        if not suppress_text:
            print(f"❌ {exc}")
        return None  # 调用方会按 None 处理，但已打印越界错误
    return book


def ws_gate(args) -> Path | None:
    """命令统一工作区闸门（QA P5：--json 契约覆盖错误路径）。

    解析失败 / project.json 缺失时：--json 模式输出结构化错误信封（stdout 可解析，
    不混文本）；文本模式保持人话提示；两种模式均只打印一次说明（QA P12 去重）。
    返回 None 时调用方直接 return 1。
    """
    js = bool(getattr(args, "json", False))
    book = _resolve_and_validate(args.workspace, suppress_text=js)
    if book is not None and not (book / "project.json").exists():
        _RESOLVE_REASON = "project_missing"
        book = None
    if book is None:
        if js:
            payload = {
                "ok": False,
                "code": _RESOLVE_REASON or "workspace_not_found",
                "books": [str(b) for b in common.list_books()],
                "hint": ("请用 -w 指定书目录" if _RESOLVE_REASON == "multiple_books"
                         else "先运行 python studio.py init -w workspace/<slug> -t \"书名\""),
            }
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print_ws_not_found()
        return None
    return book
