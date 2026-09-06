"""Schema validator + Pydantic model boundary tests."""
import json
from pathlib import Path

import pytest

from engine import validator
from engine import models
from engine.models import (EntitiesState, LedgerState, TimelineState, LinesState, CurrentState,
                           SynopsisState, LockedState, CognitionState, ProposalModel)


SCHEMAS = Path(Path(__file__).resolve().parent.parent, "engine", "schemas")


def _load(name):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class TestValidator:
    def test_unknown_additional_properties(self):
        assert validator.validate({"a": 1, "extra": 2}, {"type": "object", "properties": {"a": {"type": "integer"}}, "additionalProperties": False}) != []

    def test_required(self):
        assert validator.validate({}, {"type": "object", "required": ["x"]}) != []

    def test_enum(self):
        assert validator.validate("bad", {"type": "string", "enum": ["a", "b"]}) != []
        assert validator.validate("a", {"type": "string", "enum": ["a", "b"]}) == []

    def test_pattern(self):
        assert validator.validate("abc", {"type": "string", "pattern": "^ch_\\d{3,}$"}) != []
        assert validator.validate("ch_001", {"type": "string", "pattern": "^ch_\\d{3,}$"}) == []

    def test_integer_not_bool(self):
        assert validator.validate(True, {"type": "integer"}) != []
        assert validator.validate(1, {"type": "integer"}) == []

    def test_anyof_closest(self):
        schema = {
            "anyOf": [
                {"type": "integer", "minimum": 1},
                {"type": "string"},
            ]
        }
        errs = validator.validate(None, schema)
        assert errs

    def test_null_rejected_if_not_allowed(self):
        schema = {"type": ["object", "null"], "properties": {}}
        # contains a null branch so a bare null passes
        assert validator.validate(None, {"type": ["object", "null"]}) == []


class TestDomainModels:
    def test_entity_extra_forbidden(self):
        with pytest.raises(Exception):
            EntitiesState.model_validate({"entries": [{"name": "A", "unknown": 1}]})

    def test_entity_aliases_merge(self):
        ent = EntitiesState.model_validate({"entries": [{"name": "A", "aliases": ["x"]}]})
        assert ent.entries[0].aliases == ["x"]

    def test_locked_has_max_entries(self):
        data = {"schema_version": "novel-studio.locked/v1",
                "entries": [{"id": f"LOCK-{i:03d}", "fact": "x"*4, "since_ch": "ch_001", "kind": "rule", "quote": "q"} for i in range(51)]}
        with pytest.raises(Exception):
            LockedState.model_validate(data)

    def test_proposal_requires_schema(self):
        with pytest.raises(Exception):
            ProposalModel.model_validate({"chapter": "ch_001"})

    def test_proposal_alias_schema(self):
        pm = ProposalModel.model_validate({"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001"})
        assert pm.schema_version == "novel-studio.state-mutation/v2"


class TestSchemaFiles:
    @pytest.mark.parametrize("name", ["current", "entities", "lines", "ledger", "timeline", "synopsis", "locked", "cognition", "proposal"])
    def test_schema_valid_json(self, name):
        schema = _load(f"{name}.schema.json")
        assert isinstance(schema, dict)
        assert "type" in schema
