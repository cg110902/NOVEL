"""engine.super_engine — 4.0 超级引擎内核

这是 4.0 的心脏：把所有确定性能力 + 智能生成 + 自愈 + 一键流程聚合

对外提供：
- SuperEngine(book_path): 统一入口
  - one_command(title, genre, protagonist, idea, chapters): 一条命令成书
  - auto_write(chapters): 批量续写
  - heal(): 一键自愈
  - status(): 超级状态
  - export(): 一键导出

设计目标：
- 功能非常非常强大：全自动、自愈、自检、自导出
- 使用非常非常简单：一条命令

Example:
    from engine.super_engine import SuperEngine
    engine = SuperEngine("workspace/我的书")
    engine.one_command("我的书", genre="玄幻", protagonist="林牧", idea="...", chapters=10)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from . import common, state
from .autopilot import one_command, run_batch, run_chapter, smart_init
from .generator import SmartGenerator
from .healer import heal_book
from .llm import get_provider


class SuperEngine:
    """4.0 超级引擎"""

    VERSION = "4.0.0"
    CODENAME = "One-Command Novel"

    def __init__(self, workspace: str | Path, llm_provider: str = "auto"):
        self.workspace = Path(workspace)
        self.llm_provider = llm_provider
        self.provider = get_provider(llm_provider)
        print(f"🚀 SuperEngine {self.VERSION} ({self.CODENAME}) | Provider: {self.provider.name}")

    def _resolve_book(self) -> Optional[Path]:
        if self.workspace.exists() and (self.workspace / "project.json").exists():
            return self.workspace
        # 尝试 resolve
        resolved = common.resolve_workspace(str(self.workspace))
        if resolved and (resolved / "project.json").exists():
            return resolved
        return None

    def smart_init(self, title: str, genre: str = "玄幻", protagonist: str = "林牧", idea: str = "", force: bool = False) -> Dict:
        """智能筑基"""
        return smart_init(
            self.workspace,
            title=title,
            genre=genre,
            protagonist=protagonist,
            idea=idea,
            force=force,
            llm_provider=self.llm_provider,
        )

    def one_command(
        self,
        title: str,
        genre: str = "玄幻",
        protagonist: str = "林牧",
        idea: str = "废柴逆袭，以智破局",
        chapters: int = 3,
        force: bool = False,
    ) -> Dict:
        """一条命令从零到成书"""
        return one_command(
            title=title,
            genre=genre,
            protagonist=protagonist,
            idea=idea,
            chapters=chapters,
            workspace=str(self.workspace),
            force=force,
            llm_provider=self.llm_provider,
        )

    def write_chapter(self, chapter_num: int) -> Dict:
        """单章全自动"""
        book = self._resolve_book()
        if not book:
            return {"ok": False, "error": f"书不存在: {self.workspace}"}
        proj = {}
        try:
            proj = common.load_json(book / "project.json")
        except Exception:
            pass
        return run_chapter(
            book,
            chapter_num,
            llm_provider=self.llm_provider,
            title=proj.get("title", ""),
            genre=proj.get("genre", "玄幻"),
            protagonist=proj.get("protagonist", "林牧"),
            idea=proj.get("idea", ""),
        )

    def auto_write(self, chapters: int = 5, start_ch: Optional[int] = None) -> Dict:
        """批量全自动"""
        book = self._resolve_book()
        if not book:
            return {"ok": False, "error": f"书不存在: {self.workspace}"}
        proj = {}
        try:
            proj = common.load_json(book / "project.json")
        except Exception:
            pass
        return run_batch(
            book,
            chapters=chapters,
            start_ch=start_ch,
            llm_provider=self.llm_provider,
            title=proj.get("title", ""),
            genre=proj.get("genre", "玄幻"),
            protagonist=proj.get("protagonist", "林牧"),
            idea=proj.get("idea", ""),
        )

    def heal(self, deep: bool = False) -> Dict:
        """一键自愈"""
        book = self._resolve_book()
        if not book:
            return {"ok": False, "error": f"书不存在: {self.workspace}"}
        return heal_book(book, deep=deep)

    def status(self) -> Dict:
        """超级状态"""
        book = self._resolve_book()
        if not book:
            return {"exists": False, "workspace": str(self.workspace)}
        try:
            from .commands.book_setup import _book_brief

            brief = _book_brief(book)
            # 增强信息
            finals = common.find_chapter_files(book, "final")
            brief["super_engine"] = {
                "version": self.VERSION,
                "provider": self.provider.name,
                "total_finals": len(finals),
                "words": sum(len(f.read_text(encoding="utf-8", errors="replace")) for f in finals),
            }
            return brief
        except Exception as e:
            return {"exists": True, "error": str(e), "workspace": str(book)}

    def export(self, txt: bool = True, views: bool = True) -> Dict:
        """一键导出"""
        book = self._resolve_book()
        if not book:
            return {"ok": False, "error": f"书不存在: {self.workspace}"}
        try:
            proj = common.load_json(book / "project.json")
            title = proj.get("title") or book.name
        except Exception:
            title = book.name

        results = {}
        finals = common.find_chapter_files(book, "final")
        if txt:
            txt_path = book / "export" / f"{title}.txt"
            txt_path.parent.mkdir(parents=True, exist_ok=True)
            with txt_path.open("w", encoding="utf-8") as out:
                for f in sorted(finals, key=lambda p: common.natural_chapter_sort_key(p)):
                    out.write(f.read_text(encoding="utf-8", errors="replace"))
                    out.write("\n\n")
            results["txt"] = str(txt_path)

        if views:
            view_path = book / "export" / "views" / "state_view.md"
            view_path.parent.mkdir(parents=True, exist_ok=True)
            view_path.write_text(f"# {title} 状态视图\n\n已完成 {len(finals)} 章\n", encoding="utf-8")
            results["views"] = str(view_path)

        return {"ok": True, "exports": results, "chapters": len(finals)}
