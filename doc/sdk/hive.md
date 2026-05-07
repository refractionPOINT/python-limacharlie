[Documentation](../README.md) > [SDK](README.md) > Hive

# Hive

The `Hive` class provides access to LimaCharlie's key-value stores. Hives are used for configuration data including secrets, lookups, playbooks, D&R rules, and more.

## Setup

```python
from limacharlie.sdk.hive import Hive, HiveRecord

hive = Hive(org, "secret")
```

## Listing Records

```python
records = hive.list()                      # {name: HiveRecord}
```

## Getting a Record

```python
record = hive.get("my-key")               # HiveRecord
print(record.data, record.etag)
```

## Creating or Updating

```python
new_record = HiveRecord("my-key", data={"value": "secret123"})
hive.set(new_record)
```

## Transactional Updates

Update with automatic etag retry to handle concurrent modifications:

```python
def update_fn(record):
    record.data["counter"] = record.data.get("counter", 0) + 1

hive.update_tx("my-key", update_fn)
```

## Deleting

```python
hive.delete("my-key")
```

## Common Hive Categories

| Category | Description | CLI Shortcut |
|---|---|---|
| `secret` | Secrets and credentials | `limacharlie secret` |
| `lookup` | Lookup tables | `limacharlie lookup` |
| `playbook` | Response playbooks | `limacharlie playbook` |
| `dr-general` | D&R rules (general) | `limacharlie dr` |
| `fp` | False positive rules | `limacharlie fp` |

## See Also

- [CLI: hive and shortcuts](../cli/hive-data.md) — CLI equivalents
- [Detection Rules](detection-rules.md) — DRRules and FPRules helpers
- [Configuration Sync](configs.md) — Sync hives via infrastructure-as-code
