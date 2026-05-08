"""AI skill commands for LimaCharlie CLI v2.

Wraps the ``ai_skill`` hive — a typed store for Claude Code Skill
definitions. Each record is the structured equivalent of an on-disk
SKILL.md directory: the SKILL.md frontmatter is broken out into typed
fields (description, when_to_use, allowed-tools, effort, context,
arguments, hooks, paths, shell, ...), the SKILL.md body lives in
``content``, and bundled supporting files (scripts, reference docs)
live in ``files`` keyed by path-relative-to-skill-root.

Reference: https://code.claude.com/docs/en/skills.md
"""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
from ..discovery import register_explain

group = make_hive_group("ai-skill", "ai_skill", "AI skill", "AI skills")

# Override the generic hive explains with ai_skill-specific documentation.

register_explain("ai-skill.list", """\
List all Claude Code skill definitions stored in the 'ai_skill' hive.
Each record is a self-contained skill (SKILL.md body + frontmatter +
optional supporting files), keyed by skill name.
""")

register_explain("ai-skill.get", """\
Get a single skill record by key.  Returns the full SKILL.md body
(content), all frontmatter fields (description, when_to_use,
allowed-tools, effort, context, arguments, hooks, paths, shell, ...),
and any bundled supporting files keyed by their relative path.
""")

register_explain("ai-skill.set", """\
Create or update a Claude Code skill definition.  The data payload
mirrors the on-disk SKILL.md schema with one extension: bundled files
live under a 'files' map keyed by path-relative-to-skill-root.

Required:
  data:
    content: |             # SKILL.md body (markdown — the prompt)
      Find duplicate IOCs across recent detections and report counts.

Optional frontmatter (mirrors official YAML keys verbatim):
  data:
    content: "..."
    name: my-skill         # slug, [a-z0-9-]{1,64}; defaults to record key
    description: "..."     # listing summary; combined with when_to_use
                           # under a 1536 char ceiling
    when_to_use: "..."     # supplementary trigger context
    argument-hint: "[issue-number]"
    arguments: ["target", "since"]   # or "target since"
    disable-model-invocation: false
    user-invocable: true
    allowed-tools: ["Bash(git:*)", "Read"]   # or space-separated string
    model: "inherit"
    effort: low|medium|high|xhigh|max
    context: fork
    agent: my-agent-type   # only meaningful when context=fork
    hooks: { ... }         # opaque pass-through
    paths: ["src/**/*.go"] # or comma-separated string
    shell: bash|powershell

Bundled supporting files (hive-only extension, max 100 entries):
  data:
    content: "..."
    files:
      scripts/helper.sh: "#!/bin/bash\\n..."
      reference/api.md:  "# API notes\\n..."

Provide data via --input-file (YAML/JSON) or pipe through stdin.

Examples:
  limacharlie ai-skill set --key triage --input-file skill.yaml
  cat skill.yaml | limacharlie ai-skill set --key triage
""")

register_explain("ai-skill.delete", """\
Delete a Claude Code skill record from the 'ai_skill' hive.  Requires
--confirm.
""")

register_explain("ai-skill.enable", """\
Enable a skill record (sets usr_mtd.enabled=true).
""")

register_explain("ai-skill.disable", """\
Disable a skill record (sets usr_mtd.enabled=false).  Disabled skills
remain stored but are skipped by Claude when listing available skills.
""")
