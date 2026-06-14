"""App commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("app", "app", "app")

# Override the generic hive explains with app-specific documentation.

register_explain("app.list", """\
List all apps stored in the 'app' hive.  An app is a user-authored,
AI-generated mini web application: a single self-contained HTML
document that the LimaCharlie web UI renders inside a sandboxed
<iframe>.
""")

register_explain("app.get", """\
Get a specific app by key.  Returns the full record including the
HTML document, required permissions, and metadata.
""")

register_explain("app.set", """\
Create or update an app.  An app record holds a single self-contained
HTML document (HTML + inline JS + inline CSS) rendered in a sandboxed
iframe.

The data payload looks like:

  data:
    display_name: "My App"          # required, human label
    html: "<html>...</html>"        # required, the self-contained document
    description: "What it does"      # optional blurb
    icon: "🛠"                       # optional emoji / icon id / data-URI
    required_permissions:            # perms minted into the iframe JWT,
      - sensor.get                   #   intersected with the viewing user's
      - sensor.task                  #   own permissions at view time
    allowed_origins:                 # optional third-party https origins
      - https://example.com          #   the iframe JS may contact (CSP)
    required_services:               # optional first-party LC services to
      - search                       #   broker: search, replay, cases, ai
    locations:                       # optional UI surfaces: standalone,
      - standalone                   #   within_a_sensor, within_a_case, etc.
    expected_context:                # optional context keys passed in when
      - sid                          #   embedded (sid, atom, detection_id…)

Records can be tagged and organized with usr_mtd:

  usr_mtd:
    tags: [internal, dashboard]
    comment: "Sensor triage dashboard"

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie app set --key triage-dashboard --input-file app.yaml
""")

register_explain("app.delete", """\
Delete an app from the 'app' hive.  Requires --confirm.
""")
