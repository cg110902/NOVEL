#!/usr/bin/env python3
"""Novel Studio 薄壳入口：sys.path 注入后调用 engine.cli.main（业务逻辑一律在 engine/*）。

依赖缺失属于环境问题，不是业务阻断也不是用法错：此前 `engine.cli` 在 import 期
就抛 ModuleNotFoundError 裸 traceback，退出码 1（与「体检有 errors」同码），
调用方无法区分「书有问题」和「环境没装好」。这里在 import 期兜住，给人话提示
并用独立退出码 3（见 engine/README.md 退出码契约）。
"""
import os
import sys
from pathlib import Path

# 彻底解决 Windows 控制台默认 GBK 编码引发的中文乱码与 Unicode (Emoji/特殊标点) 编码报错
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for _stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENV_EXIT_CODE = 3
 

try:
    from engine.cli import main  # noqa: E402
except ImportError as _exc:  # 依赖没装 / 装错解释器
    _missing = getattr(_exc, "name", None) or str(_exc)
    sys.stderr.write(
        "\n❌ 运行环境缺少依赖，引擎无法启动。\n"
        f"   缺失模块：{_missing}\n"
        f"   当前解释器：{sys.executable}\n"
        "   修复：在当前解释器安装依赖 →\n"
        f"       {sys.executable} -m pip install -r requirements.txt\n"
        "   （若你用的是虚拟环境，请先激活它，或用该环境的 python 直接跑 studio.py）\n\n")
    raise SystemExit(ENV_EXIT_CODE) from None

if __name__ == "__main__":
    raise SystemExit(main())
