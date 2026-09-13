"""Typed, read-only D&R construction. No model, shell, or deployment logic.

Custom telemetry is grounded in supplied or sampled JSON. Platform contracts
cover only explicitly listed LC sensor fields, never the universe of LC data.
"""

import copy
import json
import math
import re
import time
from pathlib import Path

from .dr_drafting import digest, load, save
from .sdk.dr_deploy import evidence as replay_evidence
from .sdk.replay import Replay

VERSION = 1
SENSOR_REVISION = "f861f987568e8ee24c72115c82246557de7c6a54"
CONTRACTS = {
    "DNS_REQUEST": {"event/DOMAIN_NAME": "str"},
    "NEW_PROCESS": {"event/FILE_PATH": "str", "event/PARENT/FILE_PATH": "str"},
}
# These are field contracts, not guarantees that an organization collects them.
CONTRACT_SOURCES = {
    "DNS_REQUEST": "sensor/modules/hbs/collector_2_dns_tracker.c",
    "NEW_PROCESS": "sensor/modules/hbs/collector_1_process_tracker.c",
}
PACKAGES = {
    "dns-domain": {
        "version": 1,
        "event_type": "DNS_REQUEST",
        "description": "Exact DNS domain, case insensitive; excludes subdomains.",
        "parameters": ["domain"],
        "limitations": ["DNS observation is not proof of malicious activity."],
    },
    "java-child": {
        "version": 1,
        "event_type": "NEW_PROCESS",
        "description": "Java/javaw spawning one of the explicitly selected executable names.",
        "parameters": ["children"],
        "limitations": [
            "Behavioral heuristic, not proof of Log4Shell.",
            "Renamed or embedded JVMs and other exploitation paths are outside coverage.",
        ],
    },
}
MISSING = object()


class NeedsEvidence(ValueError):
    pass


def package_intent(name, parameters, report_name):
    if name == "dns-domain":
        if (
            set(parameters) != {"domain"}
            or not isinstance(parameters["domain"], str)
            or not parameters["domain"]
        ):
            raise ValueError("dns-domain requires one nonempty domain string")
        condition = {
            "op": "eq",
            "path": ["event", "DOMAIN_NAME"],
            "value": parameters["domain"],
            "case_sensitive": False,
        }
    elif name == "java-child":
        children = parameters.get("children")
        if (
            set(parameters) != {"children"}
            or not isinstance(children, list)
            or not 1 <= len(children) <= 8
            or any(
                not isinstance(x, str) or not x or "/" in x or "\\" in x
                for x in children
            )
        ):
            raise ValueError("java-child requires 1–8 explicit executable basenames")

        def names(path, values):
            return {
                "op": "any",
                "rules": [
                    {
                        "op": "basename",
                        "path": path,
                        "value": v,
                        "case_sensitive": False,
                    }
                    for v in values
                ],
            }

        condition = {
            "op": "all",
            "rules": [
                names(
                    ["event", "PARENT", "FILE_PATH"],
                    ["java", "java.exe", "javaw", "javaw.exe"],
                ),
                names(["event", "FILE_PATH"], children),
            ],
        }
    else:
        raise ValueError("Unknown reviewed package")
    return {
        "version": VERSION,
        "event_type": PACKAGES[name]["event_type"],
        "name": report_name,
        "condition": condition,
    }


def validate(intent):
    if (
        not isinstance(intent, dict)
        or set(intent) != {"version", "event_type", "name", "condition"}
        or type(intent["version"]) is not int
        or intent["version"] != VERSION
    ):
        raise ValueError("Require version=1, event_type, name and condition only")
    if not isinstance(intent["event_type"], str) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,128}", intent["event_type"]
    ):
        raise ValueError("Require a literal event_type")
    if not isinstance(intent["name"], str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,128}", intent["name"]
    ):
        raise ValueError("Require a literal report name")
    leaves = []

    def walk(node, prefix=(), depth=0):
        if depth > 6 or not isinstance(node, dict):
            raise ValueError("Conditions must be objects at most six levels deep")
        op = node.get("op")
        if op in ("all", "any"):
            if (
                set(node) != {"op", "rules"}
                or not isinstance(node["rules"], list)
                or not 1 <= len(node["rules"]) <= 12
            ):
                raise ValueError("all/any require 1–12 rules")
            for child in node["rules"]:
                walk(child, prefix, depth + 1)
            return
        path = node.get("path")
        if (
            not isinstance(path, list)
            or not path
            or any(
                not isinstance(k, str) or not k or "/" in k or k in ("*", "?")
                for k in path
            )
        ):
            raise ValueError(
                "Paths require literal JSON object keys; slash/wildcard keys need the specialist path"
            )
        if not prefix and path[0] != "event":
            raise ValueError("This operation matches event data only")
        if op == "some":
            if set(node) != {"op", "path", "where"}:
                raise ValueError("some requires path and where")
            walk(node["where"], prefix + tuple(path) + ("?",), depth + 1)
            return
        if (
            op not in ("eq", "gt", "lt", "contains", "basename")
            or set(node) - {"op", "path", "value", "case_sensitive"}
            or "value" not in node
        ):
            raise ValueError(
                "Unsupported predicate; supported: eq, gt, lt, contains, basename, all, any, some"
            )
        value = node["value"]
        if (
            type(value) not in (str, int, float, bool)
            or isinstance(value, float)
            and not math.isfinite(value)
        ):
            raise ValueError("Predicate values must be finite JSON scalars")
        if op in ("gt", "lt") and type(value) not in (int, float):
            raise ValueError("Numeric comparison requires a number")
        if op in ("contains", "basename") and (not isinstance(value, str) or not value):
            raise ValueError("String predicate requires a nonempty string")
        if "case_sensitive" in node and type(node["case_sensitive"]) is not bool:
            raise ValueError("case_sensitive must be a boolean")
        # Non-string values have no case. The interpreter can include this
        # harmless default; compile_rule omits it from non-string predicates.
        leaves.append((prefix + tuple(path), node))

    walk(intent["condition"])
    if len(leaves) > 16:
        raise ValueError("At most 16 predicates are supported on the fast path")
    return leaves


def compile_rule(intent):
    validate(intent)

    def compile_node(node, scoped=False):
        op = node["op"]
        if op in ("all", "any"):
            return {
                "op": {"all": "and", "any": "or"}[op],
                "rules": [compile_node(x, scoped) for x in node["rules"]],
            }
        path = "/".join((["event"] if scoped else []) + node["path"])
        if op == "some":
            return {
                "op": "scope",
                "path": path + "/",
                "rule": compile_node(node["where"], True),
            }
        result = {
            "op": {
                "eq": "is",
                "gt": "is greater than",
                "lt": "is lower than",
                "contains": "contains",
                "basename": "is",
            }[op],
            "path": path,
            "value": node["value"],
        }
        if op == "basename":
            result["file name"] = True
        if isinstance(node["value"], str):
            result["case sensitive"] = node.get("case_sensitive", True)
        return result

    return {
        "detect": {"event": intent["event_type"], **compile_node(intent["condition"])},
        "respond": [{"action": "report", "name": intent["name"]}],
    }


def get(value, path):
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def put(value, path, content):
    for key in path[:-1]:
        if not isinstance(value.get(key), dict):
            value[key] = {}
        value = value[key]
    value[path[-1]] = content


def matches(node, event):
    """Intent oracle, independent of emitted D&R syntax. Not a platform emulator."""
    op = node["op"]
    if op == "all":
        return all(matches(c, event) for c in node["rules"])
    if op == "any":
        return any(matches(c, event) for c in node["rules"])
    actual = get(event, node["path"])
    if op == "some":
        return isinstance(actual, list) and any(
            matches(node["where"], x) for x in actual
        )
    if actual is MISSING:
        return False
    expected = node["value"]
    if op in ("gt", "lt"):
        return type(actual) in (int, float) and (
            actual > expected if op == "gt" else actual < expected
        )
    if op == "basename":
        if not isinstance(actual, str):
            return False
        actual = re.split(r"[/\\]", actual)[-1]
    if isinstance(expected, str):
        if not isinstance(actual, str):
            return False
        if not node.get("case_sensitive", True):
            actual, expected = actual.lower(), expected.lower()
    elif type(actual) is not type(expected) and not (
        type(actual) in (int, float) and type(expected) in (int, float)
    ):
        return False
    return expected in actual if op == "contains" else actual == expected


def witness(node, desired, event):
    op = node["op"]
    if op in ("all", "any"):
        if (op == "all" and desired) or (op == "any" and not desired):
            for child in node["rules"]:
                witness(child, desired, event)
        else:
            for child in node["rules"]:
                witness(child, not desired, event)
            witness(node["rules"][0], desired, event)
    elif op == "some":
        item = {}
        witness(node["where"], desired, item)
        put(event, node["path"], [item])
    else:
        v = node["value"]
        if op in ("gt", "lt"):
            v = v + (1 if op == "gt" else -1) if desired else v
        elif not desired:
            v = (
                (not v)
                if type(v) is bool
                else v + 1
                if type(v) in (int, float)
                else "__negative_control__"
            )
            if v == node["value"]:
                v += "_different"
        elif op == "basename":
            v = "/fixture/" + v
        put(event, node["path"], v)


def fixtures(intent, samples):
    condition = intent["condition"]
    base = (
        copy.deepcopy(samples[0])
        if samples
        else {"routing": {"event_type": intent["event_type"]}, "event": {}}
    )
    cases = []

    def add(label, obj):
        if not any(existing[1] == obj for existing in cases):
            cases.append((label, obj))

    for desired in (True, False):
        event = copy.deepcopy(base)
        witness(condition, desired, event)
        if matches(condition, event) != desired:
            raise ValueError("Conflicting predicates need specialist fixture design")
        add("constructed-" + str(desired).lower(), event)
    # Exercise each alternative and predicate boundary through the intent oracle.
    positive = copy.deepcopy(cases[0][1])

    def variants(node, root, target):
        op = node["op"]
        if op in ("all", "any"):
            for child in node["rules"]:
                variants(child, root, target)
        elif op == "some":
            array = get(target, node["path"])
            if isinstance(array, list) and array:
                variants(node["where"], root, array[0])
                if node["where"]["op"] == "all" and len(node["where"]["rules"]) > 1:
                    split = []
                    for child in node["where"]["rules"]:
                        item = {}
                        witness(child, True, item)
                        split.append(item)
                    old_array = copy.deepcopy(array)
                    put(target, node["path"], split)
                    add("split-array-control", copy.deepcopy(root))
                    put(target, node["path"], old_array)
        else:
            old = copy.deepcopy(target)
            for desired in (True, False):
                witness(node, desired, target)
                add("predicate-" + str(desired).lower(), copy.deepcopy(root))
                target.clear()
                target.update(copy.deepcopy(old))
            values = []
            if isinstance(node["value"], str):
                values = [node["value"].upper(), node["value"] + ".extra"]
                if op == "basename":
                    values += [
                        "C:\\fixture\\" + node["value"],
                        "/fixture/prefix-" + node["value"],
                    ]
            elif type(node["value"]) in (int, float):
                values = [node["value"] - 1, node["value"], node["value"] + 1]
            for value in values:
                put(target, node["path"], value)
                add("boundary-control", copy.deepcopy(root))
                target.clear()
                target.update(copy.deepcopy(old))
            parent = get(target, node["path"][:-1]) if node["path"][:-1] else target
            if isinstance(parent, dict):
                parent.pop(node["path"][-1], None)
                add("missing-field-control", copy.deepcopy(root))
                target.clear()
                target.update(copy.deepcopy(old))

    variants(condition, positive, positive)
    for event in samples[:4]:
        add("observed", copy.deepcopy(event))
    if len(cases) > 100:
        raise ValueError("Fixture budget exceeded")
    return [
        {
            "label": label,
            "event": event,
            "expected": matches(condition, event),
            "provenance": "supplied_or_captured"
            if event in samples
            else "modified_or_constructed",
        }
        for label, event in cases
    ]


def observed_types(value, prefix="", result=None, depth=0):
    """Accumulate every type, including heterogeneous elements of one array."""
    if depth > 30:
        raise NeedsEvidence("Provide a shallower representative event")
    if result is None:
        result = {}
    if prefix:
        result.setdefault(prefix, set()).add(type(value).__name__)
    if isinstance(value, dict):
        for key, child in value.items():
            observed_types(
                child, prefix + "/" + key if prefix else key, result, depth + 1
            )
    elif isinstance(value, list):
        for child in value:
            observed_types(child, prefix + "/?", result, depth + 1)
    return result


def schema_context(intent, samples, source):
    leaves = validate(intent)
    fields = {}
    for event in samples:
        if event.get("routing", {}).get("event_type") != intent["event_type"]:
            raise NeedsEvidence("Evidence event type differs from the requested source")
        for path, kinds in observed_types(event).items():
            fields.setdefault(path, set()).update(kinds)
    if source == "lc_sensor":
        contract = CONTRACTS.get(intent["event_type"], {})
        if not contract or any("/".join(path) not in contract for path, _ in leaves):
            raise NeedsEvidence(
                "Requested fields are outside the reviewed LC sensor contracts; use observed custom_json evidence"
            )
        for path, kind in contract.items():
            fields.setdefault(path, set()).add(kind)
    elif source != "custom_json":
        raise ValueError("source must explicitly be lc_sensor or custom_json")
    for path, node in leaves:
        kinds = fields.get("/".join(path), set())
        if not kinds:
            raise NeedsEvidence("Unverified field: " + "/".join(path))
        expected = type(node["value"]).__name__
        allowed = {"int", "float"} if expected in ("int", "float") else {expected}
        if not kinds <= allowed:
            raise NeedsEvidence(
                "Mixed or incompatible observed types at "
                + "/".join(path)
                + ": "
                + ",".join(sorted(kinds))
            )
    return {
        "kind": "lc_sensor_contract" if source == "lc_sensor" else "observed_json",
        "sensor_revision": SENSOR_REVISION if source == "lc_sensor" else None,
        "sample_count": len(samples),
        "absence_proven": False,
        "source_path": CONTRACT_SOURCES.get(intent["event_type"])
        if source == "lc_sensor"
        else None,
        "note": "Field availability and fixture behavior do not prove collection or detection coverage.",
    }


def replay_cases(org, candidate, cases, cancelled=None):
    """Correlate every stateless fixture in one Replay request.

    Only for this compiler's stateless, report-only event predicates. Markers
    live in routing, outside its permitted condition paths. A matching positive
    cannot conceal a failing positive or a matching negative.
    """
    if cancelled is not None and cancelled.is_set():
        raise TimeoutError("Draft cancelled")
    events = [copy.deepcopy(case["event"]) for case in cases]
    for index, event in enumerate(events):
        event.setdefault("routing", {})["lc_draft_fixture_id"] = index
    try:
        response = Replay(org).scan_events(
            events, rule_content=candidate, stream="event"
        )
        proof = replay_evidence(response)
        if proof["processed"] != len(cases):
            raise ValueError("Replay did not process every fixture")
        matched = set()
        for result in response["results"]:
            if not isinstance(result, dict) or result.get("action") != "report":
                raise ValueError("Unexpected Replay result")
            index = (
                result.get("data", {})
                .get("detect", {})
                .get("routing", {})
                .get("lc_draft_fixture_id")
            )
            if (
                type(index) is not int
                or not 0 <= index < len(cases)
                or index in matched
            ):
                raise ValueError("Replay result lost or duplicated fixture identity")
            matched.add(index)
        if bool(matched) != proof["matched"]:
            raise ValueError("Replay match summary disagrees with fixture results")
        return [
            {
                "label": case["label"],
                "expected": case["expected"],
                "processed": 1,
                "matched": index in matched,
                **(
                    {"error": "Fixture did not have its required outcome"}
                    if (index in matched) != case["expected"]
                    else {}
                ),
            }
            for index, case in enumerate(cases)
        ]
    except (ValueError, AttributeError, TypeError) as exc:
        return [{"error": str(exc)}]


def build(
    org,
    directory,
    intent,
    *,
    samples=None,
    source="custom_json",
    package=None,
    cancelled=None,
):
    """Construct and independently replay bounded scenarios; never mutate LC resources."""
    started = time.monotonic()
    samples = samples or []
    if (
        not isinstance(samples, list)
        or len(samples) > 100
        or any(
            not isinstance(e, dict)
            or not isinstance(e.get("routing"), dict)
            or "event" not in e
            for e in samples
        )
    ):
        raise ValueError("Evidence must be at most 100 LC event envelopes")
    if len(json.dumps(samples).encode()) > 2 * 1024 * 1024:
        raise ValueError("Evidence exceeds 2 MiB")
    if any(e.get("routing", {}).get("oid") not in (None, org.oid) for e in samples):
        raise ValueError("Evidence belongs to a different organization")
    from .agent_policy import enabled

    if enabled():
        from .draft_guard import activate

        activate(org.oid, Path(directory).resolve())
    schema = schema_context(intent, samples, source)
    candidate = compile_rule(intent)
    cases = fixtures(intent, samples)
    if not any(c["expected"] for c in cases) or not any(
        not c["expected"] for c in cases
    ):
        raise ValueError("Require positive and negative scenarios")
    root = Path(directory).resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("Use a new or empty workspace")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    root.chmod(0o700)
    positives = [c["event"] for c in cases if c["expected"]]
    negatives = [c["event"] for c in cases if not c["expected"]]
    artifacts = {
        "candidate.json": candidate,
        "positive.json": positives,
        "negative.json": negatives,
    }
    for name, value in {
        **artifacts,
        "intent.json": intent,
        "evidence.json": samples,
        "scenarios.json": cases,
        "manifest.json": {
            "version": 1,
            "org_id": org.oid,
            "evidence_sha256": digest(samples),
            "schema_source": schema,
        },
    }.items():
        save(root / name, value)
    checks = replay_cases(org, candidate, cases, cancelled)
    errors = [c["error"] for c in checks if "error" in c]
    report = {
        "status": "invalid" if errors else "tested",
        "errors": errors,
        "checks": checks,
        "candidate": candidate,
        "intent": intent,
        "schema": schema,
        "workspace": str(root),
        "org_id": org.oid,
        "grounding": schema["kind"],
        "evidence_sha256": digest(samples),
        "inputs_sha256": {k: digest(v) for k, v in artifacts.items()},
        "deployed": False,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "operation_version": VERSION,
        "limitations": PACKAGES[package]["limitations"]
        if package
        else ["Only the supplied intent and fixtures were checked."],
    }
    if cancelled is not None and cancelled.is_set():
        raise TimeoutError("Draft cancelled before finalization")
    if any(load(root / k, json_only=True) != v for k, v in artifacts.items()):
        raise ValueError("Draft files changed during validation")
    save(root / "check.json", report)
    return report
