"""Cloud sensor commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("cloud-adapter", "cloud_sensor", "cloud adapter")

# Override the generic hive explains with cloud adapter documentation.

register_explain("cloud-adapter.list", """\
List all cloud adapter configurations.  Cloud adapters run in
LimaCharlie's infrastructure (as opposed to external adapters which
run on-prem).  They ingest data from cloud services like webhooks,
S3 buckets, GCS, PubSub, and SaaS APIs.
""")

register_explain("cloud-adapter.get", """\
Get a specific cloud adapter configuration by key.  Returns the full
record including sensor_type, connection settings, and metadata.
""")

register_explain("cloud-adapter.set", """\
Create or update a cloud adapter configuration.  Cloud adapters run
in LimaCharlie infrastructure and pull data from cloud services.

Webhook adapter example:

  sensor_type: webhook
  webhook:
    client_options:
      hostname: my-webhook
      identity:
        installation_key: <your-installation-key>
        oid: <your-oid>
      platform: json
      sensor_seed_key: my-webhook
    secret: my-webhook-secret

S3 adapter example:

  sensor_type: s3
  s3:
    client_options:
      hostname: s3-logs
      identity:
        installation_key: <your-installation-key>
        oid: <your-oid>
      platform: json
      sensor_seed_key: s3-logs
    bucket_name: my-log-bucket
    access_key: AKIA...
    secret_key: hive://secret/s3-creds
    prefix: logs/

The structure is the same as external adapters.  The top-level
sensor_type selects the adapter kind, and client_options are shared
across all types.

Supported cloud adapter types include: webhook, s3, gcs, pubsub,
office365, 1password, crowdstrike, duo, sophos, and others.

Secrets can be referenced with hive://secret/name syntax to avoid
storing credentials inline.

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie cloud-adapter set --key my-webhook --input-file cloud.yaml
""")

register_explain("cloud-adapter.delete", """\
Delete a cloud adapter configuration.  The cloud adapter will stop
ingesting data.  Requires --confirm.
""")
