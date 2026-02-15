"""External adapter commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("external-adapter", "external_adapter", "external adapter")

# Override the generic hive explains with adapter-specific documentation.

register_explain("external-adapter.list", """\
List all external adapter configurations.  External adapters are
on-prem or self-hosted adapters whose configuration is managed from
the cloud via the external_adapter hive.

Each record contains the adapter type and its connection settings.
Common adapter types: syslog, file, s3, gcs, pubsub, webhook, stdin,
office365, 1password, crowdstrike, carbon_black, duo, sophos, and many
others.

Use --output json for the full config including connection details.
""")

register_explain("external-adapter.get", """\
Get a specific external adapter configuration by key.  Returns the
full record including sensor_type, connection settings, mapping
options, and hive metadata.
""")

register_explain("external-adapter.set", """\
Create or update an external adapter configuration.  The adapter
process running on-prem pulls this config from the cloud.

Minimal syslog adapter example:

  sensor_type: syslog
  syslog:
    client_options:
      hostname: my-syslog-source
      identity:
        installation_key: <your-installation-key>
        oid: <your-oid>
      platform: text
      sensor_seed_key: my-syslog-source
    port: 514

The top-level sensor_type selects the adapter kind.  The matching
key contains type-specific config.  client_options is shared across
all types.

Key client_options fields:
  hostname         - Display name for this adapter sensor
  sensor_seed_key  - Stable unique ID for this adapter instance
  platform         - Data format: text, json, xml, cef, carbon_black,
                     crowdstrike, wel, gcp, aws, office365, etc.
  identity.installation_key - Enrollment key for the adapter
  identity.oid     - Target organization ID
  mapping          - Parsing and field mapping configuration

Common mapping options:
  parsing_re         - Regex with named groups for text parsing
  parsing_grok       - Grok pattern for structured extraction
  sensor_key_path    - Path to sensor identifier field
  event_type_path    - Path to event type field
  event_time_path    - Path to timestamp field
  rename_only        - Only emit mapped fields
  drop_fields        - List of field paths to drop

You can wrap the config in a hive record with usr_mtd:

  data:
    sensor_type: syslog
    syslog: { ... }
  usr_mtd:
    enabled: true
    tags: [production]
    comment: "Main syslog collector"

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie external-adapter set --key corp-syslog --input-file adapter.yaml
  cat adapter.json | limacharlie external-adapter set --key corp-syslog
""")

register_explain("external-adapter.delete", """\
Delete an external adapter configuration.  The on-prem adapter
process will stop receiving config updates.  Requires --confirm.

Examples:
  limacharlie external-adapter delete --key corp-syslog --confirm
""")
