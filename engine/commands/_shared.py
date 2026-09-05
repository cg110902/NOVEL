"""命令层共享助手：章号规范、公共 CLI 参数与工作区越界防护（命令模块唯一取用口）。"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from .. import common

SLOT_RE = re.compile(r"\{\{\s*slot:(\w+)(?:\|[^}]*)?\s*\}\}")

# _resolve_and_validate 是否已自行打印过失败说明（多书歧义 / -w 越界）。
# 置位后 print_ws_not_found() 抑制误导性的二次报错（QA P2-2 / P3-11）。
_RESOLVE_NOTE_SHOWN = False


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


def _resolve_and_validate(ws_arg: str | None) -> Path | None:
    """统一解析并校验工作区必须在 workspace_root 之下（防 -w 越界）。

    失败时打印唯一一条准确说明后返回 None（调用方按 None 返回退出码）：
    - 多本书未指定 -w：列出全部书目录请求指定（此前误报「未找到 init」，QA P2-2）；
    - 显式 -w 越界：打印越界错误；
    - 其余（0 本书等）：交给调用方的「未找到」提示。
    """
    global _RESOLVE_NOTE_SHOWN
    _RESOLVE_NOTE_SHOWN = False
    if not ws_arg:
        books = common.list_books()
        if len(books) > 1:
            _RESOLVE_NOTE_SHOWN = True
            print("📚 存在多本书，请用 -w 指定其一：")
            for b in books:
                print(f"   - {b}")
            return None
    book = common.resolve_workspace(ws_arg)
    if book is None:
        return None
    try:
        # 若显式指定 -w，必须校验在 workspace_root 内
        if ws_arg:
            common.ensure_workspace_inside(book)
    except ValueError as exc:
        _RESOLVE_NOTE_SHOWN = True
        print(f"❌ {exc}")
        return None  # 调用方会按 None 处理，但已打印越界错误
    return book
