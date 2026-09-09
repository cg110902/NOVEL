"""Novel Studio 3.1 Pydantic V2 强类型领域模型包。

包含世界观实体、复式记账台账、时空因果轴、伏笔暗线生命周期与提案原子变更模型。
"""
from .entities import EntitiesState, EntityEntry, EntityType, EntityStatus, LifeStatus, FactionAttitude, KNOWN_RELATION_PREDS
from .ledger import LedgerState, LedgerPool, LedgerTransaction, TransactionType
from .timeline import TimelineState, TimelineEvent, TimelineArc, TimelineClock, ClockUrgency, ClockStatus, TimelineMilestone, EVT_ID_RE
from .derived import DerivedState, LineTemp, SceneViolation, HolderOrphan, KnowledgeFlag
from .lines import (
    LinesState,
    Foreshadow,
    ForeshadowStatus,
    Misunderstanding,
    MisunderstandingStatus,
    Knowledge,
    KnowledgeStatus,
)
from .current import CurrentState, Loadout
from .synopsis import SynopsisState, ChapterSynopsis
from .locked import LockedState, LockedEntry, LockedKind
from .cognition import CognitionState, CognitionEntry, CognitionKind
from .patch import ProposalModel
from .adapter import validate_with_model, export_clean_data, MODEL_REGISTRY

__all__ = [
    "EntitiesState",
    "EntityEntry",
    "EntityType",
    "EntityStatus",
    "LifeStatus",
    "FactionAttitude",
    "LedgerState",
    "LedgerPool",
    "LedgerTransaction",
    "TransactionType",
    "TimelineState",
    "TimelineEvent",
    "TimelineArc",
    "TimelineClock",
    "ClockUrgency",
    "ClockStatus",
    "TimelineMilestone",
    "EVT_ID_RE",
    "KNOWN_RELATION_PREDS",
    "DerivedState",
    "LineTemp",
    "SceneViolation",
    "HolderOrphan",
    "KnowledgeFlag",
    "LinesState",
    "Foreshadow",
    "ForeshadowStatus",
    "Misunderstanding",
    "MisunderstandingStatus",
    "Knowledge",
    "KnowledgeStatus",
    "CurrentState",
    "Loadout",
    "SynopsisState",
    "ChapterSynopsis",
    "LockedState",
    "LockedEntry",
    "LockedKind",
    "CognitionState",
    "CognitionEntry",
    "CognitionKind",
    "ProposalModel",
    "validate_with_model",
    "export_clean_data",
    "MODEL_REGISTRY",
]
