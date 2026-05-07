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
the Python source code in the data.python field.
""")

register_explain("playbook.set", """\
Create or update a playbook.  Playbooks are Python scripts with a
required entry point function.

The data payload contains the Python source under a 'python' key:

  data:
    python: |
      def playbook(sdk, data):
          # sdk is a limacharlie.Manager instance (or None)
          # data is a dict passed by the caller
          sensors = list(sdk.sensors())
          return {"data": {"count": len(sensors)}}

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
limacharlie SDK, scikit-learn, jinja2, markdown, pillow, flask.

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
