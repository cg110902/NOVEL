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

def _launch_wizard():
    """零参数智能向导：4.0 一键成书"""
    print("=" * 70)
    print(" 🚀 Novel Studio 4.0 - 全自动一键成书引擎")
    print("=" * 70)
    print(" 检测到未输入命令，进入极简向导模式")
    print("")
    print("  【超级命令】一条命令从零到成书：")
    print("    python studio.py novel \"我的新书\" -g 玄幻 -p 林牧 --idea \"废柴逆袭\" --chapters 10")
    print("")
    print("  【其他快捷】")
    print("    python studio.py create \"书名\"          # 极简开书")
    print("    python studio.py auto -w workspace/书名 --chapters 5  # 批量续写")
    print("    python studio.py write ch_001 -w workspace/书名       # 单章全自动")
    print("    python studio.py status                 # 查看进度")
    print("    python studio.py help                   # 全部命令")
    print("=" * 70)
    print("")
    # 尝试交互式
    try:
        from pathlib import Path
        import sys
        # 检查是否有现有书
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from engine import common
        books = common.list_books()
        if books:
            print(f"📚 检测到 {len(books)} 本现有书：")
            for b in books:
                print(f"   - {b}")
            print("")
            choice = input("是否直接续写现有书？(y/n) [y]: ").strip().lower() or "y"
            if choice in ("y", "yes", "是"):
                # 选第一本或让用户选
                if len(books) == 1:
                    target = books[0]
                else:
                    print("请选择：")
                    for i, b in enumerate(books, 1):
                        print(f"  {i}. {b}")
                    idx = input(f"编号 [1]: ").strip() or "1"
                    try:
                        target = books[int(idx) - 1]
                    except Exception:
                        target = books[0]
                chs = input("续写多少章？ [3]: ").strip() or "3"
                try:
                    chs = int(chs)
                except Exception:
                    chs = 3
                from engine.cli import main as cli_main
                return cli_main(["auto", "-w", str(target), "--chapters", str(chs)])
    except Exception:
        pass

    # 新书向导
    try:
        print("📖 新书向导：")
        title = input("书名 [我的新书]: ").strip() or "我的新书"
        genre = input("题材 (玄幻/都市/科幻/悬疑/历史) [玄幻]: ").strip() or "玄幻"
        protagonist = input("主角名 [林牧]: ").strip() or "林牧"
        idea = input("一句话脑洞 [废柴逆袭，以智破局]: ").strip() or "废柴逆袭，以智破局"
        chapters = input("首批写多少章？ [3]: ").strip() or "3"
        try:
            chapters = int(chapters)
        except Exception:
            chapters = 3

        print("")
        print(f"🎬 即将一键成书：{title} | {genre} | {protagonist} | {chapters}章")
        print(f"   脑洞：{idea}")
        confirm = input("确认开始？(y/n) [y]: ").strip().lower() or "y"
        if confirm not in ("y", "yes", "是"):
            print("已取消")
            return 0

        from engine.cli import main as cli_main
        return cli_main(["novel", title, "-g", genre, "-p", protagonist, "--idea", idea, "--chapters", str(chapters)])

    except (EOFError, KeyboardInterrupt):
        print("\n已退出向导，运行 python studio.py help 查看全部命令")
        return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # 零参数 -> 向导
        raise SystemExit(_launch_wizard())
    raise SystemExit(main())
