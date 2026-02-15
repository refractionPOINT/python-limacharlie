"""SOP commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("sop", "sop", "SOP", "SOPs")

# Override the generic hive explains with SOP-specific documentation.

register_explain("sop.list", """\
List all Standard Operating Procedures stored in the organization.
SOPs document processes and procedures for incident response,
security operations, and compliance workflows.
""")

register_explain("sop.get", """\
Get a specific SOP by key.  Returns the full record including the
document content and metadata.
""")

register_explain("sop.set", """\
Create or update a Standard Operating Procedure.  SOPs store
structured documentation for operational processes.

The data payload contains the document text:

  data:
    text: |
      Incident Response Procedure
      1. Isolate the affected endpoint
      2. Collect forensic artifacts
      3. Analyze timeline of events
      4. Contain and remediate
      5. Document findings

SOPs can be tagged and organized with usr_mtd:

  data:
    text: "..."
  usr_mtd:
    tags: [incident-response, tier-1]
    comment: "IR playbook for ransomware"

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie sop set --key ransomware-ir --input-file sop.yaml
""")

register_explain("sop.delete", """\
Delete a Standard Operating Procedure.  Requires --confirm.
""")
