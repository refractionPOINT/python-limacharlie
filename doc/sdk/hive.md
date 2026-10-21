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
records = hive.list_mtd()                  # same, without the data (record.data is None)
```

`list_mtd()` never loads the record data on the server, so prefer it when only
names and metadata are needed. A hive too big for the server to return in one
response is refused with HTTP 413 (`HIVE_LISTING_TOO_LARGE`); `list()` and
`list_mtd()` then read it page by page by themselves and return the whole hive.

### Paging

To bound memory on a big hive, walk it page by page instead:

```python
for page in hive.iter_pages(limit=100):                # {name: HiveRecord} per page
    for name, record in page.items():
        ...

page, next_cursor = hive.list_page(limit=100)          # one page, in record name order
page, next_cursor = hive.list_page(limit=100, cursor=next_cursor)   # next_cursor == "" on the last page
```

`list_page()` and `iter_pages()` also take `mtd_only=True`, `tag_prefix="..."`
(only records with a tag starting with it) and `max_bytes=...` (a lower size
bound for a page). The server caps `limit` and the byte size of a page, so a
page can hold fewer records than asked. An invalid cursor raises `ApiError`
(HTTP 400, `INVALID_CURSOR`). Against an API that predates paging, the whole
hive comes back as a single final page.

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
