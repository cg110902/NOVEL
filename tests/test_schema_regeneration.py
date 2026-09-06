"""Ensure engine/schemas/*.json are in sync with the Pydantic model registry."""
import json

from engine.models.schema_gen import MODEL_REGISTRY, generate_schema, SCHEMA_DIR


class TestSchemaSync:
    def test_every_registered_model_has_schema(self):
        assert set(MODEL_REGISTRY) >= {"current", "entities", "lines", "ledger",
                                       "timeline", "synopsis", "locked", "cognition",
                                       "proposal"}

    def test_schemas_match_generated(self):
        for name in MODEL_REGISTRY:
            generated = json.dumps(generate_schema(name), ensure_ascii=False, indent=2) + "\n"
            path = SCHEMA_DIR / f"{name}.schema.json"
            assert path.is_file(), f"missing {path}"
            assert path.read_text(encoding="utf-8") == generated, (
                f"{name}.schema.json drifts from model registry; run "
                f"python -m engine.models.schema_gen and commit the result")
