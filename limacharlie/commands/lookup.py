"""Lookup commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("lookup", "lookup", "lookup")

# Override the generic hive-shortcut explains with lookup-specific ones.

register_explain("lookup.list", """\
List all lookups stored in the lookup hive.  Lookups are key-value
tables used for enrichment in D&R rules (via the "lookup" operator).

Each lookup record contains a data payload in one of these formats:
  lookup_data  - a dict of string keys to metadata dicts
  newline_content - a newline-separated list of string keys (no metadata)
  yaml_content - YAML string containing a dict of keys to metadata

Lookups can be populated manually, via the CLI, or automatically
refreshed every 24 hours by the ext-lookup-manager extension.
""")

register_explain("lookup.get", """\
Get a specific lookup by its key name from the lookup hive.  Returns
the full hive record including data payload and metadata.

The data payload will contain one of:
  lookup_data: {"key1": {metadata}, "key2": {metadata}}
  newline_content: "key1\\nkey2\\nkey3"
  yaml_content: "<yaml string>"

Lookups are queried in D&R rules using the "lookup" operator with
the lookup name as the resource.
""")

register_explain("lookup.set", """\
Create or update a lookup in the lookup hive.  Provide data via
--input-file (JSON/YAML) or stdin.

The input should be a hive record.  Lookup data supports three formats:

  Format 1 - lookup_data (dict with optional metadata per key):
    data:
      lookup_data:
        "8.8.8.8": {}
        "1.1.1.1": {provider: google}
        "c:\\\\windows\\\\system32\\\\ping.exe": {mtd1: known_bin}

  Format 2 - newline_content (simple list, no metadata):
    data:
      newline_content: "value1\\nvalue2\\nvalue3"

  Format 3 - yaml_content (YAML string):
    data:
      yaml_content: |
        key1: {meta: value}
        key2: {}

Optional user metadata:
    usr_mtd:
      enabled: true
      expiry: 0
      tags: [my-tag]
      comment: "IP blocklist"

Example:
  limacharlie lookup set --key my-blocklist --input-file blocklist.yaml
""")

register_explain("lookup.delete", """\
Delete a lookup from the lookup hive.  Requires --confirm for safety.
Any D&R rules that reference this lookup will fail after deletion.
""")
