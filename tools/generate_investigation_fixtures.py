"""Generate public template compatibility fixtures from recorded observations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests/unit/fixtures/investigation_compatibility_snapshot.json"
KINDS = frozenset({"null", "bool", "int", "float", "string", "timestamp", "sequence", "mapping", "error"})
COLLECTION_KINDS = {"array": "sequence", "object": "mapping"}


def generate(snapshot: dict, output: Path) -> None:
    """Normalize observation kinds without deriving expectations from the SDK."""
    cases = []
    for source in snapshot["cases"]:
        case = dict(source)
        kind = COLLECTION_KINDS.get(case["kind"], case["kind"])
        if kind not in KINDS:
            raise ValueError(f"Unknown scalar observation kind: {kind!r}")
        case["kind"] = kind
        cases.append(case)
    fields = snapshot["fields"]
    for field in fields:
        if field["kind"] not in {"number", "bool"}:
            raise ValueError(f"Unknown typed field kind: {field['kind']!r}")
    output.mkdir(parents=True, exist_ok=True)
    generated = {
        "investigation_scalars.json": {
            "about": "Generated public template scalar contract from investigation_compatibility_snapshot.json; do not edit. Regenerate both fixtures with python tools/generate_investigation_fixtures.py. Canonical collection kinds are sequence/mapping. See README.investigation.md for provenance and input format.",
            "cases": cases,
        },
        "investigation_typed_fields.json": {
            "about": "Generated public template number/boolean field paths from investigation_compatibility_snapshot.json; do not edit. Regenerate both fixtures with python tools/generate_investigation_fixtures.py. A star denotes a list index or map key. See README.investigation.md for provenance and input format.",
            "fields": fields,
        },
    }
    for name, document in generated.items():
        (output / name).write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SNAPSHOT)
    parser.add_argument("--output-dir", type=Path, default=SNAPSHOT.parent)
    args = parser.parse_args()
    generate(json.loads(args.input.read_text(encoding="utf-8")), args.output_dir)


if __name__ == "__main__":
    main()
