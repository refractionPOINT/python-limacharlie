"""Application Control commands for LimaCharlie CLI v2.

Wraps the two Application Control hives:

* ``app_control_policy`` -- one record per policy (priority, platforms, tags,
  mode, stance, trust_os_vendor).
* ``app_control_rule`` -- one record per allow/deny rule. The record name is
  the rule id; the rule names the policies it applies to.

Both hives are partitioned per organization and are governed by the
``app_control.get`` / ``app_control.set`` permissions. This module is a thin
layer over the generic hive client: the server validates every record, so the
CLI does no client-side validation of field names or values.
"""

from __future__ import annotations

import click

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = click.Group(
    "app-control",
    help="Manage Application Control policies and rules.",
)

policy_group = make_hive_group(
    "policy", "app_control_policy", "Application Control policy",
    "Application Control policies", explain_prefix="app-control.policy",
)
rule_group = make_hive_group(
    "rule", "app_control_rule", "Application Control rule",
    "Application Control rules", explain_prefix="app-control.rule",
)
group.add_command(policy_group)
group.add_command(rule_group)

register_explain("app-control", """\
Manage Application Control, which decides which programs may run on
endpoints.  Two kinds of records live in the organization's hives:

  policy  A policy (hive 'app_control_policy').  It sets how and where
          the controls apply: its priority, platforms, tags, mode and
          stance.
  rule    An allow or deny rule (hive 'app_control_rule').  The record
          key is the rule id.  Each rule lists the policies it belongs to.

Both are per-organization.  Reading needs the app_control.get permission
and writing needs app_control.set.  The server validates every record,
so an invalid policy or rule is rejected with the reason.

Examples:
  limacharlie app-control policy list
  limacharlie app-control policy set --key workstations --input-file policy.yaml
  limacharlie app-control rule list
  limacharlie app-control rule set --key block-tool-x --input-file rule.yaml
""")

register_explain("app-control.policy", """\
Manage Application Control policies (hive 'app_control_policy').  One
record per policy.  See 'limacharlie app-control policy set --ai-help'
for the record format.
""")

register_explain("app-control.rule", """\
Manage Application Control rules (hive 'app_control_rule').  One record
per allow or deny rule, keyed by rule id.  See
'limacharlie app-control rule set --ai-help' for the record format.
""")

register_explain("app-control.policy.list", """\
List all Application Control policies stored in the organization.  Each
record is one policy.  The hive is per-org (OID-partitioned).
""")

register_explain("app-control.policy.get", """\
Get a specific Application Control policy by key.  Returns the full
record including its data and metadata.
""")

register_explain("app-control.policy.set", """\
Create or update an Application Control policy.

The data payload describes one policy:

  data:
    priority: 100            # integer
    platforms: [windows]     # list of: windows, macos
    tags: [workstations]     # list of tags
    mode: permissive         # off | permissive | permissive_sync | enforcing
    stance: allowlist        # allowlist | blocklist
    trust_os_vendor: true    # boolean

The server validates the record and rejects invalid values with the
reason.  Records are stored disabled unless --enabled is passed or the
input file carries usr_mtd.enabled: true.

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie app-control policy set --key workstations --input-file policy.yaml
  limacharlie app-control policy set --key workstations --input-file policy.yaml --enabled
""")

register_explain("app-control.policy.delete", """\
Delete an Application Control policy.  Requires --confirm.
""")

register_explain("app-control.rule.list", """\
List all Application Control rules stored in the organization.  Each
record is one allow or deny rule, keyed by rule id.  The hive is per-org
(OID-partitioned).
""")

register_explain("app-control.rule.get", """\
Get a specific Application Control rule by rule id.  Returns the full
record including its data and metadata.
""")

register_explain("app-control.rule.set", """\
Create or update an Application Control rule.  The record key (--key) is
the rule id, at most 64 bytes.

The data payload describes one rule:

  data:
    action: deny                     # allow | deny
    kind: sha256                     # path | signer | signing_id | signer_root | sha256
    value: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    policies: [workstations]         # names of the policies the rule applies to

The server validates the record and rejects invalid values with the
reason.  Records are stored disabled unless --enabled is passed or the
input file carries usr_mtd.enabled: true.

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie app-control rule set --key block-tool-x --input-file rule.yaml
  limacharlie app-control rule set --key block-tool-x --input-file rule.yaml --enabled
""")

register_explain("app-control.rule.delete", """\
Delete an Application Control rule by rule id.  Requires --confirm.
""")
