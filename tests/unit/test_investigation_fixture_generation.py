"""Reproduce canonical fixtures from recorded public compatibility observations."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
spec = importlib.util.spec_from_file_location("generate_investigation_fixtures", ROOT / "tools/generate_investigation_fixtures.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def test_regeneration_matches_both_checked_in_fixtures(tmp_path):
    snapshot = json.loads(generator.SNAPSHOT.read_text(encoding="utf-8"))
    generator.generate(snapshot, tmp_path)
    for name in ("investigation_scalars.json", "investigation_typed_fields.json"):
        assert (tmp_path / name).read_bytes() == (FIXTURES / name).read_bytes()
    cases = json.loads((tmp_path / "investigation_scalars.json").read_text(encoding="utf-8"))["cases"]
    assert {c["kind"] for c in cases} <= generator.KINDS


def test_generation_normalizes_public_collection_kinds(tmp_path):
    generator.generate({"cases": [{"src": "[]", "kind": "array"}, {"src": "{}", "kind": "object"}], "fields": []}, tmp_path)
    cases = json.loads((tmp_path / "investigation_scalars.json").read_text(encoding="utf-8"))["cases"]
    assert [c["kind"] for c in cases] == ["sequence", "mapping"]


def test_generation_rejects_unknown_scalar_kind(tmp_path):
    with pytest.raises(ValueError, match="Unknown scalar observation kind"):
        generator.generate({"cases": [{"src": "x", "kind": "unrecognized"}], "fields": []}, tmp_path)
