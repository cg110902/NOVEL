"""对象层（Object Layer）：十一表真值之上的统一对象视图 + 派生计算。

三条纪律（与 state.py 的 SSOT 契约配套）：
1. 本层不存真值：registry/envelope 是内存视图，用完即弃；唯一落盘的是
   derived.json（纯派生，删了可重算）；
2. 本层不写断言：一切写入仍走提案通道；derive 只读十一表 + final；
3. 派生节独立：单节计算异常只污染本节（stats 记错），不阻断封存。
"""
from .registry import build_registry, resolve_ref
from .envelope import kind_of_id, to_envelope
from .derive import compute_derived, seal_derived

__all__ = [
    "build_registry",
    "resolve_ref",
    "kind_of_id",
    "to_envelope",
    "compute_derived",
    "seal_derived",
]
