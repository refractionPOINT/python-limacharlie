"""Secret commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("secret", "secret", "secret")

# Override the generic hive explains with secret-specific documentation.

register_explain("secret.list", """\
List all secrets stored in the organization.  Only the key names and
metadata are returned; the actual secret values require the secret.get
permission to read.
""")

register_explain("secret.get", """\
Get a secret by key.  Returns the record including the secret value
in the data payload.  Requires the secret.get permission.

The data payload contains a single key:

  data:
    secret: "the-secret-value"
""")

register_explain("secret.set", """\
Create or update a secret.  Secrets store API keys, tokens, passwords,
and other sensitive values used by adapters, outputs, extensions,
and D&R rules.

The data payload should contain a single secret key:

  data:
    secret: "my-api-key-value"

Or as bare input (wrapped automatically):

  secret: sk-1234567890abcdef

Other components reference secrets using hive:// syntax without
needing the secret.get permission:

  hive://secret/my-secret-name

This is commonly used in:
  - Adapter configs for credentials
  - Output destinations for authentication
  - D&R respond actions for API tokens
  - Playbooks for external API access
  - ARL definitions for private repo tokens

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  echo '{"secret": "sk-abc123"}' | limacharlie secret set --key my-api-key
  limacharlie secret set --key slack-token --input-file secret.yaml
""")

register_explain("secret.delete", """\
Delete a secret.  Any configs referencing this secret via
hive://secret/name will fail after deletion.  Requires --confirm.

Examples:
  limacharlie secret delete --key my-api-key --confirm
""")
