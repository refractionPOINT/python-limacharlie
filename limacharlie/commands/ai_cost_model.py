"""AI cost model commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("ai-cost-model", "ai_cost_model", "AI cost model")

# Override the generic hive explains with cost-model-specific documentation.

register_explain("ai-cost-model.list", """\
List all AI cost-model profiles stored in the organization.  Each
profile turns AI-agent activity into an auditable cost/savings figure
by pairing a fully-burdened analyst rate with the standard manual
handling time for one investigation of that kind of work.  Because
this hive is per-org (OID-partitioned), the profiles are per-tenant.
""")

register_explain("ai-cost-model.get", """\
Get a specific AI cost-model profile by key.  Returns the full record
including the economic inputs and metadata.
""")

register_explain("ai-cost-model.set", """\
Create or update an AI cost-model profile.

The data payload describes one costing profile:

  data:
    label: "SOC L1 Triage"           # optional display name
    loaded_hourly_rate: 95.0         # required: fully-burdened USD/hour
    minutes_per_investigation: 30.0  # required: standard manual minutes
    rate_source_note: "FY26 loaded SOC cost / 1,600 hrs"  # optional provenance

loaded_hourly_rate and minutes_per_investigation are required and must
be non-negative; the backend rejects either value above 100000.

Profiles can be tagged and organized with usr_mtd:

  data:
    label: "SOC L1 Triage"
    loaded_hourly_rate: 95.0
    minutes_per_investigation: 30.0
  usr_mtd:
    tags: [soc, triage]
    comment: "FY26 baseline"

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie ai-cost-model set --key soc-l1 --input-file model.yaml
""")

register_explain("ai-cost-model.delete", """\
Delete an AI cost-model profile.  Requires --confirm.
""")
