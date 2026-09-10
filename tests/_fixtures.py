"""测试夹具：在临时目录里建一本隔离的书工作区（绝不碰仓库 workspace/）。

用 `NOVEL_STUDIO_WORKSPACE_ROOT` 重定向工作区根，因此测试与开发者手上有几本书无关。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDIO = REPO_ROOT / "studio.py"
PYTHON = sys.executable


class TempBook:
    """上下文管理器：临时工作区根 + 一本已 init 的书。"""

    def __init__(self, title: str = "测试书", genre: str = "悬疑"):
        self.title = title
        self.genre = genre
        self.root: Path | None = None
        self.book: Path | None = None
        self._prev_env: str | None = None

    def __enter__(self) -> "TempBook":
        self.root = Path(tempfile.mkdtemp(prefix="novel_test_ws_"))
        self._prev_env = os.environ.get("NOVEL_STUDIO_WORKSPACE_ROOT")
        os.environ["NOVEL_STUDIO_WORKSPACE_ROOT"] = str(self.root)
        self.book = self.root / self.title
        rc = self.run("init", "-w", str(self.book), "-t", self.title, "-g", self.genre)
        if rc.returncode != 0:
            raise RuntimeError(f"init 失败: {rc.stdout} {rc.stderr}")
        return self

    def __exit__(self, *exc) -> None:
        if self._prev_env is None:
            os.environ.pop("NOVEL_STUDIO_WORKSPACE_ROOT", None)
        else:
            os.environ["NOVEL_STUDIO_WORKSPACE_ROOT"] = self._prev_env
        if self.root and self.root.is_dir():
            shutil.rmtree(self.root, ignore_errors=True)

    # ---- 便捷方法 ----
    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([PYTHON, str(STUDIO), *args, "-w", str(self.book)],
                              capture_output=True, text=True, encoding="utf-8",
                              cwd=str(REPO_ROOT),
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def run_json(self, *args: str) -> dict:
        proc = self.run(*args, "--json")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"命令 {' '.join(args)} 未产出 JSON：rc={proc.returncode}\n"
                f"stdout={proc.stdout[:800]}\nstderr={proc.stderr[:800]}") from exc

    def path(self, *parts: str) -> Path:
        assert self.book is not None
        return self.book.joinpath(*parts)

    def write(self, rel: str, text: str) -> Path:
        p = self.path(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def read(self, rel: str) -> str:
        return self.path(*rel.split("/")).read_text(encoding="utf-8")

    def state(self, key: str) -> dict:
        return json.loads(self.read(f"state/{key}.json"))

    def set_state(self, key: str, data: dict) -> None:
        self.write(f"state/{key}.json", json.dumps(data, ensure_ascii=False, indent=2))

    # ---- 稿件夹具 ----
    def seed_chapter(self, ch: str = "ch_001", cjk_body: str = "") -> None:
        """铺齐 beats / raw_v1 / raw_v2 / final 四件套，让工序指针可推进。"""
        vol = "vol_01"
        self.write(f"outlines/{vol}/beats/{ch}.md", _BEATS_TMPL.format(ch=ch, vol=vol))
        body = cjk_body or ("林牧推门进屋，" * 120)
        self.write(f"manuscript/{vol}/raw/{ch}_v1.md", f"# {ch} 毛坯\n\n{body}\n")
        self.write(f"manuscript/{vol}/raw/{ch}_v2.md", f"# {ch} 初修\n\n{body}\n")
        self.write(f"manuscript/{vol}/final/{ch}.md", f"# {ch}\n\n{body}\n")


_BEATS_TMPL = """---
chapter: {ch}
vol: {vol}
form: 危机逼近
pov: 主角视角
words: 2000-3000
tension_curve: 逼近 → 破局
tension_score: 6
stage_mode: Simmering
style_notes: 通俗直白大白话 | 极度好扫读
---

## 本章坐标与核心戏剧目标

- **本章核心戏剧目标**：主角在本章拿到关键物证并付出代价。

## 交付契约

- **核心看点**：主角当众揭穿账目造假。
- **验收要点**：
  1. 主角取得账册原件并留下物证；
  2. 反派当场失势但未彻底倒台；
  3. 章末停在主角递出账册的动作上。
"""
