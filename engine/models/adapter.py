"""Novel Studio Pydantic V2 领域模型校验适配器。

提供：
  - MODEL_REGISTRY: 核心领域模型注册表
  - validate_with_model: 纳秒级强类型模型校验与优雅错误格式化
  - export_clean_data: 借助 Pydantic 模型清洗、修剪空白并输出规范字典
"""
from __future__ import annotations

from typing import Any, Type, Union
from pydantic import BaseModel, ValidationError

from .entities import EntitiesState
from .ledger import LedgerState
from .timeline import TimelineState
from .lines import LinesState
from .current import CurrentState
from .patch import ProposalModel

MODEL_REGISTRY: dict[str, Type[BaseModel]] = {
    "entities": EntitiesState,
    "ledger": LedgerState,
    "timeline": TimelineState,
    "lines": LinesState,
    "current": CurrentState,
    "proposal": ProposalModel,
}


def _format_loc(loc: tuple[Union[str, int], ...]) -> str:
    """将 Pydantic 的错误定位元组格式化为路径表示，如 'entries[0].charges'。"""
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{item}]"
            else:
                parts.append(f"[{item}]")
        else:
            parts.append(str(item))
    return ".".join(parts)


def format_validation_error(error: dict[str, Any], prefix: str = "") -> str:
    """将单条 Pydantic 错误字典转化为优雅、符合引擎规范的中文化错误信息。"""
    loc_str = _format_loc(error.get("loc", ()))
    full_path = f"{prefix}.{loc_str}" if prefix and loc_str else (prefix or loc_str or "$")
    msg = error.get("msg", "")
    err_type = error.get("type", "")

    # 常见错误类型的人性化提示
    if err_type == "extra_forbidden":
        extra_key = error.get("loc", ())[-1] if error.get("loc") else "未知"
        return f"{full_path}: 不允许的未知字段「{extra_key}」（违反 Schema 字段黑白名单规范）"
    elif err_type == "missing":
        return f"{full_path}: 缺少必填字段"
    elif "greater_than_equal" in err_type or "ge" in err_type:
        return f"{full_path}: 数值超出允许下限（{msg}）"
    elif "string_pattern_mismatch" in err_type:
        return f"{full_path}: 格式不符合正则表达式规则（{msg}）"
    elif "enum" in err_type:
        return f"{full_path}: 枚举值非法（{msg}）"
    else:
        return f"{full_path}: {msg}"


def validate_with_model(
    model_or_name: Union[str, Type[BaseModel]],
    data: Any,
    prefix: str = ""
) -> list[str]:
    """使用指定的 Pydantic 模型校验数据。返回错误信息列表（全部合法返回空列表 []）。"""
    if isinstance(model_or_name, str):
        model_cls = MODEL_REGISTRY.get(model_or_name)
        if model_cls is None:
            raise KeyError(f"未注册的领域模型名称: {model_or_name}（可用: {list(MODEL_REGISTRY.keys())}）")
    else:
        model_cls = model_or_name

    if not isinstance(data, (dict, list)):
        return [f"{prefix or '$'}: 输入数据类型非法，期望字典或列表，得到 {type(data).__name__}"]

    errors: list[str] = []
    try:
        model_cls.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            errors.append(format_validation_error(err, prefix=prefix))

    return errors


def export_clean_data(model_or_name: Union[str, Type[BaseModel]], data: Any) -> dict[str, Any]:
    """通过 Pydantic 模型反序列化并导出清洗后的标准字典。"""
    if isinstance(model_or_name, str):
        model_cls = MODEL_REGISTRY[model_or_name]
    else:
        model_cls = model_or_name

    instance = model_cls.model_validate(data)
    return instance.model_dump(by_alias=True, exclude_none=True)
