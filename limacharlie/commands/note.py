"""Note commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("note", "org_notes", "note", index_keys=("description",))

# Override the generic hive explains with note-specific documentation.

register_explain("note.list", """\
List all organization-level notes.  Notes store free-form text for
documentation, runbooks, and operational context at the org level.
These are distinct from investigation notes which are scoped to a
specific incident.

The listing returns whole records, so an org with many long notes
returns every note body in full.  Use --brief to get just the index --
each record's data reduced to its description, with metadata intact --
then pull the ones you need:

  limacharlie note list --brief
  limacharlie note get --key <name>
""")

register_explain("note.get", """\
Get a specific note by key.  Returns the full record including the
text content and metadata.
""")

register_explain("note.set", """\
Create or update an organization note.  Notes store free-form text.

The data payload contains the note text:

  data:
    text: |
      Security baseline for production environment.
      Last reviewed: 2026-01-15
      Next review: 2026-07-15

Notes can be tagged and organized with usr_mtd:

  data:
    text: "..."
  usr_mtd:
    tags: [baseline, production]
    comment: "Quarterly review doc"

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie note set --key prod-baseline --input-file note.yaml
""")

register_explain("note.delete", """\
Delete an organization note.  Requires --confirm.
""")
