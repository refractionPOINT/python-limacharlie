[Documentation](../README.md) > [SDK](README.md) > Configuration Sync

# Configuration Sync

The `Configs` class provides infrastructure-as-code sync using the `ext-infrastructure` extension. D&R rules and FP rules are synced via their hives (`dr-general`, `dr-managed`, `dr-service`, `fp`).

## Setup

```python
from limacharlie.sdk.configs import Configs

configs = Configs(org)
```

## Fetching Configuration

```python
# Fetch outputs and D&R rules (via hives)
data = configs.fetch(
    sync_outputs=True,
    sync_hives={"dr-general": True, "fp": True},
)
```

## Pushing Configuration

```python
# Push with dry run
configs.push(data, is_dry_run=True, sync_outputs=True,
             sync_hives={"dr-general": True, "fp": True})
```

## File-Based Sync

```python
# Fetch/push to/from file
configs.fetch_to_file("org.yaml", sync_outputs=True,
                      sync_hives={"dr-general": True})
configs.push_from_file("org.yaml", sync_outputs=True,
                       sync_hives={"dr-general": True})
```

## See Also

- [CLI: sync](../cli/infrastructure.md#sync) — CLI equivalents
- [Hive](hive.md) — Direct hive access
- [Detection Rules](detection-rules.md) — DRRules and FPRules
