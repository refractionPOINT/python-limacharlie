"""Playbook commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("playbook", "playbook", "playbook")

# Override the generic hive explains with playbook-specific documentation.

register_explain("playbook.list", """\
List all playbooks in the organization.  Playbooks are Python scripts
that run in LimaCharlie's serverless execution environment with full
SDK access.  They can be triggered by D&R rules, the API, or other
extensions.
""")

register_explain("playbook.get", """\
Get a specific playbook by key.  Returns the hive record containing
the Python source code in the data.python field and, when set, the
Python SDK version in data.sdk_version ("4" or "5"; absent means v4).
""")

register_explain("playbook.set", """\
Create or update a playbook.  Playbooks are Python scripts with a
required entry point function.

The data payload contains the Python source under a 'python' key, and
an optional 'sdk_version' key selecting the LimaCharlie Python SDK the
playbook runs on:

  sdk_version  absent, "" or "4"  SDK v4: sdk is a limacharlie.Manager
               "5"                SDK v5: sdk is a
                                  limacharlie.sdk.organization.Organization

sdk is None when the request carries no credentials.  Any other
sdk_version value is rejected when the playbook is saved.

SDK v4 example:

  data:
    python: |
      def playbook(sdk, data):
          # data is a dict passed by the caller
          sensors = list(sdk.sensors())
          return {"data": {"count": len(sensors)}}

SDK v5 example:

  data:
    sdk_version: "5"
    python: |
      def playbook(sdk, data):
          sensors = list(sdk.list_sensors())
          return {"data": {"oid": sdk.oid, "count": len(sensors)}}

With SDK v5, the returned value must be JSON-serializable and the
is_interactive request parameter is not supported (it is v4-only).

The playbook function must return a dict with one or more keys:
  data      - Arbitrary data returned to the caller
  error     - Error message string if execution failed
  detection - Detection data (generates an alert)
  cat       - Detection category name (required with detection)

Example generating a detection:

  data:
    python: |
      def playbook(sdk, data):
          return {
              "detection": {"summary": "issue found"},
              "cat": "custom-playbook-alert"
          }

Playbooks run with a 10-minute time limit and have access to:
limacharlie SDK (v4 or v5, per sdk_version), scikit-learn, jinja2,
markdown, pillow, weasyprint (flask only with SDK v4).

Invoke from a D&R respond action:

  - action: extension request
    extension name: ext-playbook
    extension action: run_playbook
    extension request:
      name: my-playbook
      credentials: hive://secret/my-key
      data:
        file: event.FILE_PATH

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie playbook set --key my-playbook --input-file playbook.yaml
""")

register_explain("playbook.delete", """\
Delete a playbook.  Any D&R rules or automations that invoke this
playbook will fail after deletion.  Requires --confirm.
""")
