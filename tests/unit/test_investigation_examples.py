"""Every wave example in the Investigation Engine docs and help is valid against the operator catalogue.

The catalogue is a recorded fixture (``fixtures/ie_catalogue.json``: operators with their
argument names and output fields, packs with their params and exports), so the check needs
no network. It catches an example that names an operator, pack, argument or ``select`` field
the engine does not have.
"""

import json
import re
from pathlib import Path

import pytest

from limacharlie.commands import investigate
from limacharlie.sdk.investigation import parse_document

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "doc" / "cli" / "investigation-engine.md"
CATALOGUE = json.loads((Path(__file__).parent / "fixtures" / "ie_catalogue.json").read_text())
OPERATORS = {o["name"]: o for o in CATALOGUE["operators"]}
PACKS = {p["name"]: p for p in CATALOGUE["packs"]}


def _doc_blocks() -> list[str]:
    return re.findall(r"```ya?ml\n(.*?)```", DOC.read_text(), flags=re.S)


def _help_blocks() -> list[str]:
    """Indented YAML examples in the command help texts (a ``steps:`` block)."""
    out = []
    for name in dir(investigate):
        text = getattr(investigate, name)
        if not (name.startswith(("_EXPLAIN", "_HELP")) and isinstance(text, str)):
            continue
        for m in re.finditer(r"^( +)steps:\n(?:\1.*\n?)+", text, flags=re.M):
            out.append("\n".join(line[len(m.group(1)):] if line.startswith(m.group(1)) else line
                                 for line in m.group(0).splitlines()))
    return out


def _waves() -> list[tuple[str, dict]]:
    found = []
    for i, block in enumerate(_doc_blocks()):
        doc = parse_document(block, "example")
        if isinstance(doc, dict) and "steps" in doc:
            found.append((f"doc#{i}", doc))
    for i, block in enumerate(_help_blocks()):
        found.append((f"help#{i}", parse_document(block, "example")))
    return found


def _check_wave(wave: dict) -> list[str]:
    problems = []
    for step in wave["steps"]:
        sid = step.get("id", "?")
        has_op, has_use = "op" in step, "use" in step
        if has_op == has_use:
            problems.append(f"{sid}: needs exactly one of op or use")
            continue
        args = set((step.get("args") or {}).keys())
        select = set(step.get("select") or [])
        if has_op:
            op = OPERATORS.get(step["op"])
            if op is None:
                problems.append(f"{sid}: unknown operator {step['op']}")
                continue
            for a in sorted(args - {a["name"] for a in op["args"]}):
                problems.append(f"{sid}: {step['op']} has no argument {a}")
            for f in sorted(select - set(op["output"]["properties"])):
                problems.append(f"{sid}: {step['op']} has no output field {f}")
        else:
            pack = PACKS.get(step["use"])
            if pack is None:
                problems.append(f"{sid}: unknown pack {step['use']}")
                continue
            for a in sorted(args - {p["name"] for p in pack["params"]}):
                problems.append(f"{sid}: pack {step['use']} has no param {a}")
            for p in pack["params"]:
                if p["required"] and p["name"] not in args:
                    problems.append(f"{sid}: pack {step['use']} needs param {p['name']}")
            for f in sorted(select - set(pack["exports"])):
                problems.append(f"{sid}: pack {step['use']} has no export {f}")
    return problems


def test_the_examples_were_found():
    sources = [name for name, _ in _waves()]
    assert any(n.startswith("doc#") for n in sources) and any(n.startswith("help#") for n in sources)


@pytest.mark.parametrize("name,wave", _waves(), ids=lambda v: v if isinstance(v, str) else "")
def test_wave_example_matches_the_operator_catalogue(name, wave):
    assert _check_wave(wave) == []


def test_the_check_catches_a_wrong_select_field():
    wave = {"steps": [{"id": "p", "op": "ioc.prevalence", "args": {"file_hash": "x"}, "select": ["first_seen"]}]}
    assert _check_wave(wave) == ["p: ioc.prevalence has no output field first_seen"]
