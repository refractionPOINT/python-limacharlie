[Documentation](../README.md) > [SDK](README.md) > Other Classes

# Other Classes

Additional SDK classes for extensions, artifacts, payloads, outputs, AI, billing, and more.

## Extensions

```python
from limacharlie.sdk.extensions import Extensions

ext = Extensions(org)
subscribed = ext.list_subscribed()
ext.subscribe("my-extension")
result = ext.request("my-extension", "do-action", {"key": "value"})
```

## Artifacts

```python
from limacharlie.sdk.artifacts import Artifacts

artifacts = Artifacts(org, access_token="your-ingestion-key")
artifacts.upload("/path/to/file", source="my-source", retention_days=30)
artifact_list = artifacts.list()
```

## Payloads

```python
from limacharlie.sdk.payloads import Payloads
```

See `limacharlie.sdk.payloads` for upload, download, listing, and deletion.

## Outputs

```python
from limacharlie.sdk.outputs import Outputs
```

Outputs can also be managed directly from the `Organization` class:

```python
outputs = org.get_outputs()
org.add_output("my-output", "syslog", "event", dest_host="1.2.3.4:514")
org.delete_output("my-output")
```

## AI

```python
from limacharlie.sdk.ai import AI
```

AI-assisted generation of rules, queries, selectors, and playbooks.

## Billing

```python
from limacharlie.sdk.billing import Billing
```

Billing status and detailed usage breakdowns.

## Users

```python
from limacharlie.sdk.users import Users
```

User invitation, removal, and permission management.

## Investigations

```python
from limacharlie.sdk.investigations import Investigations
```

Investigation tracking and management.

## Downloads

```python
from limacharlie.sdk.downloads import downloads
```

Sensor installer and adapter binary downloads.

## See Also

- [CLI: extension](../cli/hive-data.md#extension) — Extension CLI commands
- [CLI: artifact, payload, output](../cli/infrastructure.md) — Infrastructure CLI commands
- [Organization](organization.md) — Outputs and rules via Organization class
