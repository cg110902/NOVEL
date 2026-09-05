"""mini JSON Schema 子集校验器：type / enum / pattern / required / properties / items /
additionalProperties / minItems。

刻意不支持 if/then 等条件语法——跨字段规则属于业务事实，放在 state.py 的分区校验里（带更准确的报错）。
本模块零业务、零 IO：输入数据+schema，输出错误列表（永不抛异常，除非 schema 自身畸形）。
"""
from __future__ import annotations

MAX_ERRORS = 25

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _type_ok(value, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return True  # 未知 type 关键字放行（前向兼容）


def _validate(value, schema: dict, path: str, errors: list[str]) -> None:
    if len(errors) >= MAX_ERRORS:
        return
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, x) for x in types):
            got = "null" if value is None else type(value).__name__
            errors.append(f"{path}: 类型应为 {'/'.join(types)}，实际 {got}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 值 {value!r} 必须 ∈ {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 必须等于 {schema['const']!r}（实际 {value!r}）")
    if "anyOf" in schema:
        ok = False
        branch_errors: list[list[str]] = []
        for sub in schema["anyOf"]:
            sub_errors = []
            _validate(value, sub, path, sub_errors)
            if not sub_errors:
                ok = True
                break
            branch_errors.append(sub_errors)
        if not ok:
            if not branch_errors:
                # 空 anyOf（如 null 分支被全部摘除后的理论残形）= 任何值都非法
                errors.append(f"{path}: 无可匹配的 anyOf 分支")
                return
            # 报告与实际值"最接近"的分支错误（条数最少者），而非倾倒整个子 schema；
            # 例如 Optional 字段收到错误类型时，仍能给出"类型应为 string"而非 anyOf 转储。
            best = min(branch_errors, key=len)
            errors.extend(best[:3])
            if len(best) > 3:
                errors.append(f"{path}: ...（anyOf 最接近分支尚有 {len(best) - 3} 条问题略）")
            return
    if isinstance(value, str) and "pattern" in schema:
        import re
        if not re.search(schema["pattern"], value):
            errors.append(f"{path}: 不匹配模式 {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < 最小值 {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > 最大值 {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: 长度 {len(value)} < {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: 长度 {len(value)} > {schema['maxLength']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: 数组长度 {len(value)} < {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: 数组长度 {len(value)} > {schema['maxItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                _validate(item, item_schema, f"{path}[{i}]", errors)
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: 缺少必填字段 {req}")
        props = schema.get("properties") or {}
        ap = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                _validate(v, props[k], f"{path}.{k}" if path else f"$.{k}", errors)
            elif ap is False:
                errors.append(f"{path}: 不允许的字段 {k}" + (f"（合法字段: {sorted(props)}）" if props else ""))
            elif isinstance(ap, dict):
                _validate(v, ap, f"{path}.{k}" if path else f"$.{k}", errors)


def validate(data, schema: dict) -> list[str]:
    """返回错误消息列表（带 JSON 路径前缀）；空列表 = 通过。"""
    errors: list[str] = []
    _validate(data, schema, "$", errors)
    return errors[:MAX_ERRORS]