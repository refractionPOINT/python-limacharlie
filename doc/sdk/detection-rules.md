[Documentation](../README.md) > [SDK](README.md) > Detection Rules

# Detection Rules

Classes for managing Detection & Response rules, false positive rules, and rule replay testing.

## DRRules

```python
from limacharlie.sdk.dr_rules import DRRules

dr = DRRules(org)
all_rules = dr.list()
dr.create("my-rule", detection={...}, response=[...])
dr.delete("my-rule")
```

Rules can also be managed directly from the `Organization` class:

```python
rules = org.get_rules()
org.add_rule(
    "my-rule",
    detection={"op": "is", "event": "NEW_PROCESS"},
    response=[{"action": "report", "name": "my-detection"}],
)
org.delete_rule("my-rule")
```

## FPRules

```python
from limacharlie.sdk.fp_rules import FPRules

fp = FPRules(org)
all_fp = fp.list()
fp.create("my-fp", rule={"op": "is", "cat": "my-detection"})
fp.delete("my-fp")
```

## Replay

Test rules against historical data or specific events:

```python
from limacharlie.sdk.replay import Replay

replay = Replay(org)

# Test against historical data
result = replay.run(
    detect={"op": "is", "event": "NEW_PROCESS"},
    respond=[{"action": "report", "name": "test"}],
    start=1704067200,
    end=1704153600,
)

# Test against specific events
result = replay.scan_events(
    events=[{"event": {"FILE_PATH": "evil.exe"}, "routing": {}}],
    rule_content={"detect": {"op": "is"}, "respond": [{"action": "report"}]},
)

# Validate rule syntax
replay.validate_rule({"detect": {"op": "is"}, "respond": [{"action": "report"}]})
```

## See Also

- [CLI: dr, fp, replay](../cli/detection-response.md) — CLI equivalents
- [Hive](hive.md) — D&R rules are stored in hives
- [Configuration Sync](configs.md) — Sync rules via infrastructure-as-code
