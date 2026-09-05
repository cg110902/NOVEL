"""JSON Schema 生成器：engine/schemas/*.json 的唯一构建源（Pydantic 模型 = 唯一真源）。

统一后的校验体系分工：
  - engine/models/*（Pydantic）    → 字段结构 / 类型 / 枚举 / 约束的唯一真源；
  - engine/schemas/*.json          → 本生成器的构建产物（勿手改！），由 validator.py 在
                                      load_state / save_state 闸门与提案顶层校验消费；
  - state.validate_proposal        → 跨字段业务规则（不属于 schema 范畴，维持现状）。

闸门补丁层（GATE_PATCHES）：模型给字段配了默认值 → 生成 schema 会让相应键变为可选；
但持久层文件由引擎全量写出，「落盘必完整」是防外部腐蚀的硬闸门（现状语义，测试锁定）。
因此以下差异被显式钉死为闸门完整性约束，而非跟随模型放宽——这是本文件里
唯一允许「schema 比模型严」的地方，每一处都写明理由。

重新生成：python -m engine.models.schema_gen
守卫测试：（产物 ≠ 生成结果即报警）
"""
from __future__ import annotations

import json
from pathlib import Path

from .adapter import MODEL_REGISTRY

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

BANNER = ("本文件由 engine/models/schema_gen.py 从 Pydantic 模型自动生成，禁止手改；"
          "重新生成：python -m engine.models.schema_gen")


def _inline_refs(schema: dict) -> dict:
    """解引用 $defs/$ref 并内联（validator.py 是 mini 子集校验器，不支持 $ref）。

    本仓库模型无递归引用；depth 仅为防御性保险丝。
    """
    defs = schema.get("$defs", {})

    def deref(node, depth: int = 0):
        if depth > 64:
            raise ValueError("schema $ref 嵌套过深（疑似递归模型）")
        if isinstance(node, dict):
            if "$ref" in node:
                target_name = node["$ref"].rsplit("/", 1)[-1]
                if target_name not in defs:
                    raise ValueError(f"未知的 $ref 目标: {node['$ref']}")
                return deref(defs[target_name], depth + 1)
            # 注意：只剔除 $defs/$ref 结构键；"title" 必须保留——它同时也是合法字段名
            # （如 ChapterSynopsis.title），无差别剔除会破坏 properties。
            return {k: deref(v, depth + 1) if isinstance(v, (dict, list)) else v
                    for k, v in node.items() if k not in ("$defs", "$ref")}
        if isinstance(node, list):
            return [deref(x, depth + 1) for x in node]
        return node

    return deref(schema)


def _drop_null_branch(sub: dict) -> dict:
    """从 anyOf 中摘除 {"type": "null"} 分支（闸门拒绝显式 null：键要么缺席要么合法）。"""
    if isinstance(sub, dict) and "anyOf" in sub:
        kept = [b for b in sub["anyOf"] if b != {"type": "null"}]
        if len(kept) == 1:
            return kept[0]
        return {**sub, "anyOf": kept}
    return sub


def _gate_patch(name: str, schema: dict) -> dict:
    """闸门补丁层：把「落盘必完整」类约束显式钉回生成的 schema（见模块 docstring）。"""
    props = schema.get("properties", {})

    if name == "entities":
        # 手写闸门要求顶层必有 entries；模型有 default_factory 所以生成结果缺 required。
        schema["required"] = ["entries"]

    elif name == "timeline":
        schema["required"] = ["events", "arcs"]  # clocks 仍可选（与现状闸门一致）

    elif name == "ledger":
        schema["required"] = ["pools", "transactions"]

    elif name == "synopsis":
        schema["required"] = ["chapters"]

    elif name == "lines":
        # 顶层三个台账数组必填（手写闸门原有；模型 default_factory 会使其可选，显式钉回）
        schema["required"] = ["foreshadows", "misunderstandings", "knowledge"]
        for arr_key in ("foreshadows", "misunderstandings", "knowledge"):
            items = props[arr_key]["items"]
            # 台账条目落盘必须带 status（模型有默认值 → 生成结果缺；外部腐蚀在闸门拦下）
            required = set(items.get("required", []))
            required.add("status")
            items["required"] = sorted(required)
            # target_ch：拒绝显式 null（键缺席=未定；null 不是合法目标）
            if "target_ch" in items.get("properties", {}):
                items["properties"]["target_ch"] = _drop_null_branch(
                    items["properties"]["target_ch"])

    elif name == "current":
        # loadout：Optional[Loadout] 生成的 anyOf 含 null 分支；现状闸门要求 loadout
        # 必须为对象（null 非法），摘除后直接内联 Loadout 子 schema，报错也更可读。
        if "loadout" in props:
            props["loadout"] = _drop_null_branch(props["loadout"])

    elif name == "proposal":
        # 浅层信封原则（与现状闸门分工一致）：分区深校验归 Pydantic 轨道
        #（validate_proposal 中 models.validate_with_model），schema 只看容器类型；
        # 否则同一违规会产出 schema+pydantic 双份措辞不同的报错。
        for sec, container in (("current", "object"), ("entities", "array"),
                               ("lines", "array"), ("timeline", "object"),
                               ("ledger", "object"), ("synopsis", "object")):
            props[sec] = {"type": container}
        # _draft 拒绝显式 null（缺省=非草稿；null 非法）
        props["_draft"] = {"type": "boolean"}

    schema["$comment"] = BANNER
    return schema


def _strip_null_branches(node):
    """递归摘除 anyOf 中的 {"type": "null"} 分支（QA P2-8）。

    闸门统一语义：「落盘必完整」——Optional 字段的键要么缺席、要么为合法值，
    显式 null 一律非法。此前只对 target_ch/loadout/_draft 三处逐点 patch，
    其余 Optional 字段生成的 anyOf 仍带 null 分支，导致闸门放行 null 并在下游
    引发 `e.get("type", "person")` 键存在值为 None 的静默失效。改为生成器级全局规则。
    """
    if isinstance(node, dict):
        if "anyOf" in node:
            kept = [b for b in node["anyOf"] if not (isinstance(b, dict) and b.get("type") == "null")]
            if len(kept) < len(node["anyOf"]):
                if len(kept) == 1:
                    return _strip_null_branches(kept[0])
                return _strip_null_branches({**node, "anyOf": kept})
        return {k: _strip_null_branches(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_null_branches(v) for v in node]
    return node


def generate_schema(name: str) -> dict:
    """由注册模型生成某分区的闸门 schema（内联引用 + 闸门补丁 + 全局 null 摘除）。"""
    if name not in MODEL_REGISTRY:
        raise KeyError(f"未注册的领域模型名称: {name}（可用: {sorted(MODEL_REGISTRY)}）")
    raw = MODEL_REGISTRY[name].model_json_schema(by_alias=True)
    return _strip_null_branches(_gate_patch(name, _inline_refs(raw)))


def regenerate_all(write: bool = True) -> dict[str, str]:
    """重新生成全部 schema 文件；返回 {name: 写入路径或差异提示}。"""
    out: dict[str, str] = {}
    for name in MODEL_REGISTRY:
        text = json.dumps(generate_schema(name), ensure_ascii=False, indent=2) + "\n"
        path = SCHEMA_DIR / f"{name}.schema.json"
        if write:
            path.write_text(text, encoding="utf-8")
            out[name] = str(path)
        else:
            out[name] = text
    return out


if __name__ == "__main__":
    for n, p in regenerate_all().items():
        print(f"✅ {n}.schema.json → {p}")
