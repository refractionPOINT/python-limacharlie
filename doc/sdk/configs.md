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

## Includes

A config file can pull in other files with `include:` (a single path or a
list). Paths are relative to the including file, and glob patterns are
accepted (`include: ["outputs/*.yaml"]`); a non-glob path that matches no file
is an error. `sync push` merges the included files with the same rules as the
Go SDK:

- Includes are processed in the order listed. A glob expands to its matches in
  sorted order. A file reached more than once (listed twice, or matched by
  several patterns) is processed only at its first occurrence.
- A later include overrides an earlier one, and an included file overrides the
  file that includes it. This is decided per record: output, org value,
  installation key, hive record (per hive name and key), exfil event/watch/
  performance entry, YARA rule/source, and so on. The winning record replaces
  the other one entirely; records are not merged field by field.
- `extensions` and each entry of `resources` are unions: values from all files
  are kept, without duplicates, in first-seen order.

```yaml
version: 3
include:
  - base.yaml
  - team/*.yaml   # team/a.yaml, then team/b.yaml: b.yaml wins on a shared key
```

## ACL Scope Membership

```python
# Preserve scope membership and the ACL tags on secret records together.
hives = {"acl": True, "secret": True}
configs.fetch_to_file("acl.yaml", sync_hives=hives)
results, errors = configs.push_from_file("acl.yaml", sync_hives=hives, is_dry_run=True)
if errors:
    raise RuntimeError("; ".join(errors))
```

ACL scopes are records under `hives.acl`; classification tags remain in each
record's `usr_mtd.tags`. Fetching membership requires `acl.get`; writing it or
changing `acl:` tags requires `acl.set`, alongside the existing resource permissions.
The syncing identity must also hold each scope needed to read restricted contents.
Do not use an `acl_restricted: true` redaction marker as replacement record data.
Use the stable UID (not email) for a user member and the key name for an API-key
member.
See [CLI ACL sync](../cli/infrastructure.md#acl-scopes) for permission setup.

## See Also

- [CLI: sync](../cli/infrastructure.md#sync) — CLI equivalents
- [Hive](hive.md) — Direct hive access
- [Detection Rules](detection-rules.md) — DRRules and FPRules
