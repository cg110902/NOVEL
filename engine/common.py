"""引擎确定性底座：IO 安全、章节号、检索、哈希、锁。全部纯字符串/数字操作，零语义判断。

设计约束：
- 仅 stdlib；上层模块（state/pack/evidence/checks/snapshot）只许复用本文件，不得旁路。
- 任何函数都不返回「结论性」字段；本文件里的失败一律以异常抛出（fail-fast），由 CLI 层转成退出码。
- 状态文件损坏绝不静默兜底为空默认值——必须让调用方显式失败。
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

CH_NAME_RE = re.compile(r"ch[_-]?0*(\d+)(?![0-9])", re.IGNORECASE)
CHAPTER_RE = re.compile(r"chapter[_-]?0*(\d+)(?![0-9])", re.IGNORECASE)
VOL_RE = re.compile(r"vol[_-]?0*(\d+)", re.IGNORECASE)
VERSION_RE = re.compile(r"[_-]?v(\d+)(?:\D|$)", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def reconfigure_utf8() -> None:
    """Windows 控制台 UTF-8 修正（POSIX 下为空操作）。"""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8")


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 工作区解析
# ---------------------------------------------------------------------------
def workspace_root(root: Path | None = None) -> Path:
    """所有书工作区的父目录：<repo>/workspace（见仓库 .gitignore）。"""
    return (root or project_root()) / "workspace"


def list_books(root: Path | None = None) -> list[Path]:
    """枚举工作区内的书（判定标志：目录内有 project.json）。"""
    base = workspace_root(root)
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "project.json").is_file())


def resolve_workspace(arg: str | None, root: Path | None = None) -> Path | None:
    """解析书工作区路径。

    显式 -w 优先（相对路径锚定仓库根）；未指定时若 workspace/ 下恰有一本书则自动选中，
    0 本或多本返回 None——由调用方给出可读提示，绝不猜测。
    """
    if arg:
        p = Path(arg).expanduser()
        if not p.is_absolute():
            p = (root or project_root()) / p
        return p
    books = list_books(root)
    return books[0] if len(books) == 1 else None


# ---------------------------------------------------------------------------
# 章节号（全仓库唯一口径）
# ---------------------------------------------------------------------------
def chapter_token_to_num(token: object) -> int | None:
    """'7' / 'ch_007' / 7 / '第3章' / 'chapter3' → 3；解析失败 None（绝不抛）。"""
    if isinstance(token, bool) or token is None:
        return None
    if isinstance(token, int):
        return token if token >= 1 else None
    s = str(token).strip()
    if s.isdigit():
        return int(s) if int(s) >= 1 else None
    m = CH_NAME_RE.search(s) or CHAPTER_RE.search(s) or re.search(r"第\s*(\d+)\s*章", s)
    if m:
        n = int(m.group(1))
        return n if n >= 1 else None
    return None


def chapter_number_from_name(name: str) -> int | None:
    stem = Path(name).stem
    m = CH_NAME_RE.search(stem) or CHAPTER_RE.search(stem)
    return int(m.group(1)) if m else None


def file_matches_chapter(path: Path | str, target: object) -> bool:
    """ch_007 / ch_007_v2 / chapter7_* 等命名都能对上目标章号；支持 vol_01/ch_007 跨卷精准过滤；target=None 全通过。"""
    if target is None:
        return True
    p = Path(path)
    want = chapter_token_to_num(target)
    got = chapter_number_from_name(p.name)
    if want is None or want != got:
        return False
    if isinstance(target, str):
        m_vol = VOL_RE.search(target)
        if m_vol:
            want_vol = int(m_vol.group(1))
            got_vol = 0
            for part in p.parts:
                m = VOL_RE.search(part)
                if m:
                    got_vol = int(m.group(1))
                    break
            if want_vol != got_vol:
                return False
    return True


def chapter_version_from_name(name: str) -> int:
    """从文件名提取版本号：ch_001_v2.md → 2；无版本 → 0（数字版本，非字典序）。"""
    m = VERSION_RE.search(Path(name).stem)
    return int(m.group(1)) if m else 0


def natural_chapter_sort_key(path: Path) -> tuple[int, int, int, str]:
    """(卷号, 章号, 稿版本, 名字)：跨目录排序的确定性键（数字版本，v10 > v2）。"""
    vol = 0
    for part in path.parts:
        m = VOL_RE.search(part)
        if m:
            vol = int(m.group(1))
            break
    return (vol, chapter_number_from_name(path.name) or 0,
            chapter_version_from_name(path.name), path.name)


def find_chapter_files(book_dir: Path, area: str = "final", target: object = None) -> list[Path]:
    """扫描 ch_*.md。area ∈ {final, raw, beats}。"""
    book_dir = Path(book_dir)
    if area == "beats":
        base, pattern = book_dir / "outlines", "*/beats/ch_*.md"
    else:
        base, pattern = book_dir / "manuscript", f"*/{area}/ch_*.md"
    files = [f for f in base.glob(pattern) if not f.name.startswith(".")]
    if target is not None:
        files = [f for f in files if file_matches_chapter(f, target)]
    return sorted(files, key=natural_chapter_sort_key)


def latest_chapter_number(book_dir: Path, area: str = "final") -> int:
    nums = (chapter_number_from_name(f.name) for f in find_chapter_files(book_dir, area))
    return max((n for n in nums if n is not None), default=0)


def parse_front_matter(text: str) -> dict[str, str]:
    """极简 YAML 子集：`---` 包裹的顶层 `key: value` 行（beats 卡协议够用，零嵌套；兼容 UTF-8 BOM）。"""
    out: dict[str, str] = {}
    lines = (text or "").lstrip("\ufeff").splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return out
    for ln in lines[i + 1:]:
        if ln.strip() == "---":
            break
        if ":" in ln and not ln.startswith((" ", "\t", "#")):
            k, _, v = ln.partition(":")
            v = v.strip()
            # 剥离行内注释（模板引导遗留）：整段以 # 开头＝空值；「空白+#」截断。
            # 只认带前置空白的 #，词中 #（如 C#）不受影响。
            if v.startswith("#"):
                v = ""
            else:
                v = re.split(r"\s+#", v, maxsplit=1)[0].strip()
            out[k.strip()] = v.strip("\"'")
    return out


def md_section(text: str, title_pat: str) -> list[str]:
    """从 Markdown 提取某级标题下的全部正文行（直到同级或更高级别标题；兼容 UTF-8 BOM）。"""
    lines: list[str] = []
    inside = False
    for ln in (text or "").lstrip("\ufeff").splitlines():
        if re.match(r"^##\s", ln):
            if inside:
                break
            inside = bool(re.match(title_pat, ln))
            continue
        if inside:
            lines.append(ln)
    return lines


# ---------------------------------------------------------------------------
# IO 安全
# ---------------------------------------------------------------------------
def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        # 在 Windows 上处理并发文件锁/IDE实时索引/杀毒软件短暂占用导致的 PermissionError (WinError 5/32)
        for attempt in range(4):
            try:
                os.replace(tmp, p)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.05 * (2 ** attempt))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def load_json(path: Path | str, default=None):
    """读 JSON。文件缺失：有 default 则返回之，否则抛 ValueError；**内容损坏必抛，绝不静默兜底**。
    注意：default 只对 FileNotFoundError 生效——JSON 损坏/编码错误一律抛 ValueError，
    调用方若需要降级展示请自行 try/except（P2-1 教训：传 default 不等于安全）。
    读取兼容 UTF-8 BOM（Windows 记事本常见，P3-3）；GBK 等其他编码 → 包装为带文件名的
    ValueError（P3-4），不再裸抛 UnicodeDecodeError。"""
    p = Path(path)
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise ValueError(f"文件不存在: {p}") from None
    except UnicodeDecodeError as exc:
        raise ValueError(f"编码错误 {p.name}（须为 UTF-8）: {exc}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 损坏 {p.name}: {exc}") from exc


def dump_json(path: Path | str, data) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def canonical_json_hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@contextlib.contextmanager
def file_lock(dir_path: Path | str, name: str = ".engine.lock", timeout: float = 30.0):
    """同目录互斥锁（O_EXCL 创建锁文件）；超时抛 TimeoutError；>120s 的陈锁允许抢占。
    锁目录 = 被保护资源所在目录（同文件系统保证原子创建）。"""
    lock = Path(dir_path) / name
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    acquired = False
    attempts = 0
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 120:
                    # 陈锁抢占（P3-18）：stat 判定后立即 unlink，竞态窗口缩至微秒级；
                    # 锁恰被他人释放/重建时 unlink 失败 → 下一轮重试，代价可忽略
                    lock.unlink()
                    continue
            except OSError:
                pass  # 锁消失或被重建 → 走正常重试
            if time.monotonic() >= deadline:
                raise TimeoutError(f"等待锁超时（{timeout}s）: {lock}") from None
            attempts += 1
            # 平滑微退避，避免极高频自旋消耗系统资源
            sleep_time = min(0.05, 0.01 * (1.15 ** min(attempts, 12)))
            time.sleep(sleep_time)
    try:
        yield lock
    finally:
        if acquired:
            with contextlib.suppress(OSError):
                lock.unlink()


# ---------------------------------------------------------------------------
# 杂项确定性小件
# ---------------------------------------------------------------------------
def est_tokens(text: str) -> int:
    """粗估 token：中文 1 字≈1，ASCII 4 字符≈1（向上取整）。只用于 pack/status 的体积自报。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def cjk_count(text: str) -> int:
    """中文字符数（全书字数的统一口径）。"""
    return len(_CJK_RE.findall(text or ""))


def time_suffix() -> str:
    """微秒级时间戳（归档重名兜底，替代旧工程的文件名冲突问题）。"""
    return datetime.datetime.now().strftime("%H%M%S%f")


def safe_child_path(root: Path | str, relative: str) -> Path:
    """root 内寻址（--open 与导出用）；越界（含 .. 逃逸）一律抛 ValueError。"""
    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"路径越界: {relative} 不在 {root} 内")
    return candidate
