"""engine.commands.autopilot — 4.0 一键成书命令集

新增命令：
- novel / one: 一条命令从零到成书
- create: 极简开书（交互式）
- write: 单章全自动
- auto: 批量全自动
- run: 智能运行（自动判断是新书还是续写）
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .. import common
from ..autopilot import one_command, run_batch, run_chapter, smart_init
from ._shared import _norm_ch, usage_error, ws_gate, ws_gate_code


def _resolve_book_dir(workspace_arg: str | None) -> Path | None:
    if workspace_arg:
        return common.resolve_workspace(workspace_arg)
    books = common.list_books()
    if len(books) == 1:
        return books[0]
    return None


def _get_title(args) -> str | None:
    # 位置参数 title 与 -t/--title 二选一，位置参数优先
    t = getattr(args, "title", None)
    if t and isinstance(t, str) and t.strip() and t not in ("novel", "one", "create", "write", "auto", "run"):
        return t.strip()
    t2 = getattr(args, "title_opt", None)
    if t2:
        return t2.strip()
    return None


def cmd_novel(args) -> int:
    """一条命令从零到成书"""
    title = _get_title(args) or getattr(args, "book_title", None)
    if not title:
        print("❌ novel 需要书名，例如: python studio.py novel \"我的新书\" -g 玄幻 -p 林牧 --chapters 5")
        return 2

    genre = getattr(args, "genre", "玄幻") or "玄幻"
    protagonist = getattr(args, "protagonist", "林牧") or "林牧"
    idea = getattr(args, "idea", "") or getattr(args, "idea_text", "") or "废柴逆袭，以智破局"
    chapters = getattr(args, "chapters", 3) or 3
    workspace = getattr(args, "workspace", None)
    force = bool(getattr(args, "force", False))
    llm = getattr(args, "llm", "auto") or "auto"

    # 清理 chapters
    try:
        chapters = int(chapters)
        if chapters < 1:
            chapters = 1
        if chapters > 50:
            print("⚠️ 章数过大，已限制为 50 章（单次上限）")
            chapters = 50
    except Exception:
        chapters = 3

    result = one_command(
        title=title,
        genre=genre,
        protagonist=protagonist,
        idea=idea,
        chapters=chapters,
        workspace=workspace,
        force=force,
        llm_provider=llm,
    )

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        if result.get("ok"):
            print(f"\n✅ 一键成书完成！书目录: {result.get('workspace')}")
            print(f"   下一步: python studio.py status -w \"{result.get('workspace')}\"")
        else:
            print(f"\n❌ 一键成书未完全成功: {result}")

    return 0 if result.get("ok") else 1


def cmd_one(args) -> int:
    """one 是 novel 的别名"""
    return cmd_novel(args)


def cmd_create(args) -> int:
    """极简开书：交互式或参数式"""
    title = _get_title(args)
    if not title:
        # 交互式
        print("📚 Novel Studio 4.0 - 极简开书向导")
        try:
            title = input("书名: ").strip() or "我的新书"
            genre = input("题材 (玄幻/都市/科幻/悬疑) [玄幻]: ").strip() or "玄幻"
            protagonist = input("主角名 [林牧]: ").strip() or "林牧"
            idea = input("一句话脑洞 [废柴逆袭]: ").strip() or "废柴逆袭，以智破局"
        except EOFError:
            print("\n❌ 输入中断")
            return 2
    else:
        genre = getattr(args, "genre", "玄幻") or "玄幻"
        protagonist = getattr(args, "protagonist", "林牧") or "林牧"
        idea = getattr(args, "idea", "") or "废柴逆袭"

    workspace = getattr(args, "workspace", None)
    force = bool(getattr(args, "force", False))
    llm = getattr(args, "llm", "auto") or "auto"

    if workspace is None:
        safe_title = re.sub(r'[\\/:*?"<>|]', "", title).strip() or "我的新书"
        workspace = f"workspace/{safe_title}"

    res = smart_init(workspace, title=title, genre=genre, protagonist=protagonist, idea=idea, force=force, llm_provider=llm)

    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        if res["ok"]:
            print(f"✅ 开书成功: {res['workspace']}")
            print(f"   已生成 bible {len(res['bible'])} 份, characters {len(res['characters'])} 份")
            print(f"   下一步一键写书: python studio.py auto -w \"{res['workspace']}\" --chapters 5")
            print(f"   或单章: python studio.py write ch_001 -w \"{res['workspace']}\"")
        else:
            print(f"❌ {res.get('error')}")

    return 0 if res["ok"] else 1


def cmd_write(args) -> int:
    """单章全自动"""
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()

    ch_raw = getattr(args, "chapter", None) or getattr(args, "chapter_arg", None) or "1"
    ch_num = common.chapter_token_to_num(ch_raw)
    if not ch_num:
        return usage_error(f"无法解析章节号: {ch_raw!r}", args)

    llm = getattr(args, "llm", "auto") or "auto"

    # 获取 project 信息
    try:
        proj = common.load_json(book / "project.json")
    except Exception:
        proj = {}

    title = proj.get("title", "")
    genre = proj.get("genre", "玄幻")
    protagonist = proj.get("protagonist", "林牧")
    idea = proj.get("idea", "")

    print(f"🚀 [Write] 全自动撰写 {book.name} 第 {ch_num} 章...")
    res = run_chapter(book, ch_num, llm_provider=llm, title=title, genre=genre, protagonist=protagonist, idea=idea)

    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res["ok"]:
            print(f"✅ 第 {ch_num} 章完成: {res['final_path']} ({res['words']}字, {res['elapsed']}s)")
            for s in res["steps"]:
                print(f"   - {s}")
        else:
            print(f"❌ 第 {ch_num} 章失败: {res.get('error')}")
            for s in res.get("steps", []):
                print(f"   - {s}")

    return 0 if res["ok"] else 1


def cmd_auto(args) -> int:
    """批量全自动"""
    book = ws_gate(args)
    if book is None:
        # 若指定了 title 等，可能是想一键新书+批量？提示
        if _get_title(args):
            # 转调 novel
            return cmd_novel(args)
        return ws_gate_code()

    chapters = getattr(args, "chapters", 3) or 3
    try:
        chapters = int(chapters)
    except Exception:
        chapters = 3

    start_ch = None
    ch_arg = getattr(args, "chapter", None) or getattr(args, "start", None)
    if ch_arg:
        # 支持 ch_005:ch_010 或单个
        if ":" in str(ch_arg):
            parts = str(ch_arg).split(":")
            s = common.chapter_token_to_num(parts[0])
            e = common.chapter_token_to_num(parts[1]) if len(parts) > 1 else None
            if s:
                start_ch = s
                if e and e >= s:
                    chapters = e - s + 1
        else:
            s = common.chapter_token_to_num(ch_arg)
            if s:
                start_ch = s

    llm = getattr(args, "llm", "auto") or "auto"

    try:
        proj = common.load_json(book / "project.json")
    except Exception:
        proj = {}

    title = proj.get("title", "")
    genre = proj.get("genre", "玄幻")
    protagonist = proj.get("protagonist", "林牧")
    idea = proj.get("idea", "")

    print(f"🚀 [Auto] {book.name} 批量全自动 {chapters} 章 (起始 {start_ch or '自动'})...")

    res = run_batch(book, chapters=chapters, start_ch=start_ch, llm_provider=llm, title=title, genre=genre, protagonist=protagonist, idea=idea)

    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"\n📊 批量结果: {res['completed']}/{res['total']} 章完成")
        for r in res["results"]:
            mark = "✅" if r["ok"] else "❌"
            print(f"  {mark} {r.get('chapter')} - {r.get('words','?')}字 - {r.get('elapsed','?')}s")
            if not r["ok"]:
                print(f"     error: {r.get('error')}")

    return 0 if res["ok"] else 1


def cmd_run(args) -> int:
    """智能运行：自动判断是新书还是续写"""
    # 若有 title 参数且 workspace 不存在 -> novel
    title = _get_title(args)
    workspace_arg = getattr(args, "workspace", None)

    book_dir = None
    if workspace_arg:
        book_dir = common.resolve_workspace(workspace_arg)

    # 如果 workspace 不存在且提供了 title，走 novel
    if title and (book_dir is None or not (book_dir / "project.json").exists()):
        return cmd_novel(args)

    # 如果 workspace 存在，走 auto
    if book_dir and (book_dir / "project.json").exists():
        return cmd_auto(args)

    # 如果既没有 title 也没有 workspace，尝试自动检测单本书
    books = common.list_books()
    if len(books) == 1:
        # 单本书，直接 auto
        from argparse import Namespace

        # 构造 auto 参数
        args.workspace = str(books[0])
        return cmd_auto(args)

    # 否则进入 create 向导
    print("🤖 [Run] 未检测到明确目标，进入智能向导...")
    print("   - 若想开新书: python studio.py run -t \"书名\" -g 玄幻 -p 主角 --chapters 5")
    print("   - 若想续写: python studio.py run -w workspace/书名 --chapters 5")
    print("   - 极简开书: python studio.py create \"书名\"")
    print("")
    return cmd_create(args)
