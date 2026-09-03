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

# 中文数字到阿拉伯数字的简易映射（用于“第三章”这类写法）
_CN_NUM_MAP = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "零": 0, "〇": 0,
}


def _cn_chapter_to_int(s: str) -> int | None:
    """尝试将“第三章/第十章/第十二章”等中文数字转为 int，失败返回 None。"""
    s = s.strip()
    # 只处理 1-99 的常见情况
    if not s:
        return None
    # 十
    if s == "十":
        return 10
    # 十X
    m = re.fullmatch(r"十([一二三四五六七八九])", s)
    if m:
        return 10 + _CN_NUM_MAP[m.group(1)]
    # X十
    m = re.fullmatch(r"([一二三四五六七八九])十", s)
    if m:
        return _CN_NUM_MAP[m.group(1)] * 10
    # X十Y
    m = re.fullmatch(r"([一二三四五六七八九])十([一二三四五六七八九])", s)
    if m:
        return _CN_NUM_MAP[m.group(1)] * 10 + _CN_NUM_MAP[m.group(2)]
    # 单字
    if s in _CN_NUM_MAP and _CN_NUM_MAP[s] != 0:
        return _CN_NUM_MAP[s]
    return None


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


def ensure_workspace_inside(book_path: Path | None, root: Path | None = None) -> Path:
    """校验书目录必须在 workspace/ 之下，否则抛 ValueError（防 -w 越界改任意目录）。"""
    if book_path is None:
        raise ValueError("未指定书工作区")
    wr = workspace_root(root).resolve()
    bp = Path(book_path).resolve()
    if bp != wr and wr not in bp.parents:
        raise ValueError(f"书目录必须在 {wr} 之下: {bp}")
    return bp


# ---------------------------------------------------------------------------
# 章节号（全仓库唯一口径）
# ---------------------------------------------------------------------------
def chapter_token_to_num(token: object) -> int | None:
    """'7' / 'ch_007' / 7 / '第3章' / '第三章' / 'chapter3' → 3；解析失败 None（绝不抛）。"""
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
    # 中文数字章节：第X章
    m = re.search(r"第\s*([一二三四五六七八九十零〇两]+)\s*章", s)
    if m:
        n = _cn_chapter_to_int(m.group(1))
        if n and n >= 1:
            return n
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
    """扫描 ch_*.md。area ∈ {final, raw, beats}。加固：跳过 symlink、越界解析。"""
    book_dir = Path(book_dir).resolve()
    if area == "beats":
        base, pattern = book_dir / "outlines", "*/beats/ch_*.md"
    else:
        base, pattern = book_dir / "manuscript", f"*/{area}/ch_*.md"
    raw_files = [f for f in base.glob(pattern) if not f.name.startswith(".")]
    files: list[Path] = []
    for f in raw_files:
        # 跳过符号链接，防止外部文件注入
        if f.is_symlink():
            continue
        try:
            resolved = f.resolve()
            # 必须仍在 book_dir 内
            if resolved != book_dir and book_dir not in resolved.parents:
                continue
        except OSError:
            continue
        files.append(f)
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
        for attempt in range(4):
            try:
                os.replace(tmp, p)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.05 * (2 ** attempt))
        # POSIX 持久化：fsync 父目录，确保 rename 落盘（断电不丢）
        with contextlib.suppress(Exception):
            # Windows 上 O_DIRECTORY 可能不支持，回退到不 fsync 目录
            try:
                dir_fd = os.open(p.parent, os.O_DIRECTORY)
            except (AttributeError, OSError):
                # 回退：尝试普通 open 目录（部分平台）
                dir_fd = None
            if dir_fd is not None:
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def load_json(path: Path | str, default=None):
    """读 JSON。文件缺失：有 default 则返回之，否则抛 ValueError；**内容损坏必抛，绝不静默兜底**。
    加固：超大文件（>10MB）拒绝解析，防 JSON 炸弹。"""
    p = Path(path)
    try:
        # 防炸弹：先检查文件大小
        try:
            if p.stat().st_size > 10 * 1024 * 1024:
                raise ValueError(f"JSON 文件过大（>{10}MB），拒绝解析: {p.name}")
        except FileNotFoundError:
            raise
        except OSError:
            pass
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

    改进：双重 mtime 检查 + inode 校验，缩小 TOCTOU 窗口，避免误删他人新锁。
    """
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
                # 第一次检查
                st1 = lock.stat()
                age1 = time.time() - st1.st_mtime
                if age1 > 120:
                    # 二次检查，缩小竞态窗口
                    time.sleep(0.01)
                    try:
                        st2 = lock.stat()
                        # 必须仍是同一 inode 且仍陈旧，才抢占
                        if st2.st_ino == st1.st_ino and (time.time() - st2.st_mtime) > 120:
                            lock.unlink()
                            continue
                    except FileNotFoundError:
                        # 锁在两次检查间已消失，直接重试创建
                        continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"等待锁超时（{timeout}s）: {lock}") from None
            attempts += 1
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
