"""pytest 夹具：隔离工作区、最小可用书、CLI 调用助手。

为什么需要隔离
--------------
引擎强制书目录必须在 workspace_root 之下（`common.ensure_workspace_inside`），而
workspace_root 默认锚定仓库根的 `workspace/`。若测试直接在那里建书，测试书会与开发者
手上的真书混进同一个 `list_books()` 结果，于是：

- 「多本书未指定 -w → exit 2」这条断言，会随开发者手上有几本书而变绿变红；
- 「仅一本书 → 自动选中」这条断言同理。

也就是说测试在测环境而不是测代码。故本套件通过 NOVEL_STUDIO_WORKSPACE_ROOT 把根
重定向到 pytest 的临时目录，测试之间与开发者环境之间完全隔离。

退出码口径
----------
0 = 成功 ｜ 1 = 业务拒收 ｜ 2 = 用法错误。这是全仓库统一契约，测试一律断言精确值，
不用「非零即可」这种会放过真实回归的宽松判据。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDIO = REPO_ROOT / "studio.py"
PY = sys.executable

# 细纲 front-matter 的合法键集（多一个键即 beats_fm_extra_keys 报错）
BEATS_FM_KEYS = (
    "chapter", "vol", "form", "pov", "words", "tension_curve",
    "tension_score", "stage_mode", "style_notes", "editor_extra",
)


# ---------------------------------------------------------------------------
# 隔离工作区根
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def ws_root(tmp_path_factory) -> Path:
    """整个测试会话共用的隔离工作区根。"""
    root = tmp_path_factory.mktemp("novel_ws")
    return root


@pytest.fixture
def env(ws_root) -> dict:
    """传给子进程的环境：重定向工作区根 + 开调试模式。"""
    e = dict(os.environ)
    e["NOVEL_STUDIO_WORKSPACE_ROOT"] = str(ws_root)
    e["NOVEL_STUDIO_DEBUG"] = "1"
    e.pop("PYTHONPATH", None)
    return e


# ---------------------------------------------------------------------------
# CLI 调用助手
# ---------------------------------------------------------------------------
class CliResult:
    def __init__(self, code: int, out: str, err: str):
        self.code = code
        self.out = out
        self.err = err

    @property
    def crashed(self) -> bool:
        """崩栈检测。

        必须独立于退出码判断：P3-4 那个 UnboundLocalError 的退出码碰巧也是 1，
        与期望值相同，只比对退出码会让它假绿。
        """
        return "Traceback (most recent call last)" in (self.out + self.err)

    def json(self) -> dict:
        """从输出里取第一个 JSON 对象（错误信封与正常 JSON 模式共用）。"""
        raw = self.out
        i = raw.find("{")
        if i < 0:
            raise AssertionError(f"输出中无 JSON：{raw[:400]!r}")
        return json.loads(raw[i:])


@pytest.fixture
def cli(env):
    """调用 studio.py。返回 CliResult。

    注意：不要在调用处用 `cmd | tail; echo $?` 之类取退出码——那拿到的是管道状态，
    不是命令状态。这里一律由 subprocess 直接给 returncode。
    """
    def run(*args, cwd: Path | None = None) -> CliResult:
        proc = subprocess.run(
            [PY, str(STUDIO), *[str(a) for a in args]],
            capture_output=True, text=True, env=env,
            cwd=str(cwd or REPO_ROOT),
        )
        return CliResult(proc.returncode, proc.stdout, proc.stderr)
    return run


# ---------------------------------------------------------------------------
# 最小可用书
# ---------------------------------------------------------------------------
def _prose(n_chars: int, seed: str, hero: str = "陆沉舟") -> str:
    """生成够字数的正文。

    必须带上主角名：否则 protagonist_pov_drift 会报「主角视角失焦」（该闸门按
    正文中主角名出现比例判定，通篇不点名即 0%）。
    """
    blocks = [
        f"{hero}把手里的东西翻过来又翻过去，指腹蹭过边缘那道旧痕，心里把账算了一遍。",
        f"风从巷口灌进来，卷着水汽，{hero}抬眼看了看檐下那盏灯，影子在墙上抖。",
        f"{hero}没说话，只把东西往怀里收了收，眼睛却盯着对面那个人的手。",
        f"对方笑了一下，说这个价钱已经是看在老交情上，{hero}再压就没有了。",
        f"{hero}点点头，转身走开，走出十几步才回头看了一眼，巷子里已经没人了。",
    ]
    out: list[str] = []
    total = 0
    i = 0
    while total < n_chars:
        s = blocks[i % len(blocks)]
        out.append(s)
        total += len(s)
        i += 1
    return "\n\n".join(out)


# 逐章轮换，避免 beats_form_repeat_without_reason（同 form 连续复用须写 form_reason）
_FORMS = ("暗流汇聚", "危机逼近", "正面冲突", "余波荡漾")
# 逐章轮换，避免 style_notes_copy（style_notes 与上一章全同）
_STYLES = (
    "平实口语 | 动作收尾",
    "短句急促 | 对白推进",
    "冷叙述 | 环境压人",
    "絮语式 | 算账收口",
)


def _beats(ch: str, num: int, words_lo: int, words_hi: int) -> str:
    i = (num - 1) % len(_FORMS)
    return (
        "---\n"
        f"chapter: {ch}\n"
        "vol: vol_01\n"
        f"form: {_FORMS[i]}\n"
        "pov: 陆沉舟·视角\n"
        f"words: {words_lo}-{words_hi}\n"
        "tension_curve: 起势 → 试探 → 破局 → 收口\n"
        f"tension_score: {5 + (num % 3)}\n"
        "stage_mode: Simmering\n"
        f"style_notes: {_STYLES[i]}\n"
        "editor_extra: 打斗最多两回合，靠算计脱身。\n"
        "---\n\n"
        "## 本章坐标\n\n"
        f"- **所属阶段**：阶段一（ch_00{num}）\n"
        f"- 当章预定规划：第{num}章推进主线，主角把处境与手段立起来。\n\n"
        "## 核心冲突与场景脉络\n\n"
        f"- **本章核心戏剧目标**：第{num}章把主角的算盘和底线立住。\n\n"
        "## 拍点与场景切片\n\n"
        "- **场景一：开场**\n"
        f"  - 内容：第{num}章开场，主角在日常里遇到异常，开始盘算。\n"
        "- **场景二：交锋**\n"
        f"  - 内容：第{num}章中段，主角与对手交锋，靠算计脱身。\n"
    )


def build_book(ws_root: Path, slug: str, chapters: int = 3,
               words: tuple[int, int] = (600, 900)) -> Path:
    """在隔离根下建一本最小可用的书：init + 填实模板 + 写 beats/raw/final。

    模板里的 {{slot:}} 不填实会被 unfilled_slot 拦成 error，故逐一覆写为无槽内容。
    """
    book = ws_root / slug
    if book.exists():
        shutil.rmtree(book)
    proc = subprocess.run(
        [PY, str(STUDIO), "init", "-w", str(book), "-t", f"测试书{slug}",
         "-g", "悬疑", "-p", "陆沉舟"],
        capture_output=True, text=True,
        env={**os.environ, "NOVEL_STUDIO_WORKSPACE_ROOT": str(ws_root)},
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"init 失败：{proc.stdout}{proc.stderr}"

    # 覆写模板，清掉 {{slot:}}
    (book / "bible" / "project_bible.md").write_text(
        "# 项目圣经\n\n## 世界规则\n\n- 灯司掌灯籍，私藏无籍之灯等同谋逆。\n",
        encoding="utf-8")
    (book / "outlines" / "main_plot.md").write_text(
        "# 主线\n\n## 总纲\n\n主角从底层拾灯人一步步查出灯司的账目黑洞。\n",
        encoding="utf-8")
    (book / "outlines" / "vol_01" / "outline.md").write_text(
        "# 卷一大纲\n\n## 阶段一\n\nch_001—ch_003：立身、得灯、被盯上。\n",
        encoding="utf-8")
    (book / "characters" / "protagonist.md").write_text(
        "# 陆沉舟\n\n## 核心\n\n底层拾灯人，爱算账，嘴碎，靠算计脱身。\n",
        encoding="utf-8")

    lo, hi = words
    target = (lo + hi) // 2
    bdir = book / "outlines" / "vol_01" / "beats"
    rawdir = book / "manuscript" / "vol_01" / "raw"
    findir = book / "manuscript" / "vol_01" / "final"
    for d in (bdir, rawdir, findir):
        d.mkdir(parents=True, exist_ok=True)

    for i in range(1, chapters + 1):
        ch = f"ch_{i:03d}"
        (bdir / f"{ch}.md").write_text(_beats(ch, i, lo, hi), encoding="utf-8")
        body = _prose(target, f"第{i}章")
        (rawdir / f"{ch}_v1.md").write_text(
            f"# 第{i}章 测试标题\n\n{body}\n", encoding="utf-8")
        (findir / f"{ch}.md").write_text(
            f"# 第{i}章 测试标题\n\n{body}\n", encoding="utf-8")

    # project.json 必须与实际产出对齐，否则测试书的 check 天生带一堆告警，
    # 后续断言就分不清是「代码回归」还是「夹具本身不干净」。
    # - words_target 默认 [2000,3000]，而测试书每章只有 target 字 → word_band_breach；
    # - 6 个词表未配置 → wordlist_unconfigured ×6（其中 abstract_phrases /
    #   empty_criteria_words 还分别驱动 beats_scene_abstract / acceptance_empty_criterion，
    #   不配等于这两个闸门在测试书里永远不触发）。
    pj = book / "project.json"
    cfg = json.loads(pj.read_text(encoding="utf-8"))
    cfg["words_target"] = [lo, hi]
    cfg["generic_stopwords"] = ["掌柜", "伙计", "官差", "路人", "行人", "街坊", "邻居"]
    cfg["critical_injury_words"] = ["重伤", "濒死", "断臂", "毒发", "气绝"]
    cfg["abstract_phrases"] = ["巧妙化解", "发生争执", "气氛变得紧张", "众人震惊"]
    cfg["high_heat_forms"] = ["生死博弈"]
    cfg["empty_criteria_words"] = ["读者", "沉浸感", "代入感", "引人入胜"]
    cfg["hook_words"] = {
        "anticlimax": ["虚惊一场", "原来没事", "白跑一趟"],
        "strong": ["动手", "下狱", "报官"],
        "suspense": ["尾随", "夜半", "对不上"],
    }
    pj.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return book


@pytest.fixture
def book(ws_root) -> Path:
    """一本三章、check 干净的书。"""
    return build_book(ws_root, "bk_main")
