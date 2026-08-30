#!/usr/bin/env python3
"""Novel Studio 薄壳入口：sys.path 注入后调用 engine.cli.main（业务逻辑一律在 engine/*）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
