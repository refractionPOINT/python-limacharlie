# Config Hive

The Config Hive is LimaCharlie's hierarchical configuration store. It provides a centralized way to manage configurations that can be referenced across the platform.

## Hive Types

- [D&R Rules](dr-rules.md) - Detection and response rule storage
- [Lookups](lookups.md) - Key-value lookup tables for enrichment
- [Secrets](secrets.md) - Secure credential management
- [YARA](yara.md) - YARA rule storage and management
- [Cloud Sensors](cloud-sensors.md) - Cloud sensor configurations
- [Apps](apps.md) - User-authored, AI-generated mini web applications
- [SOPs](../../9-ai-sessions/sops.md) - Standard Operating Procedures that AI agents read and follow
- [Organization Notes](../../9-ai-sessions/org-notes.md) - Free-form reference documents about the organization, read by analysts and AI agents

## Usage

Hive records can be:

- Referenced in D&R rules using the `hive://` prefix
- Managed via the web interface, CLI, or API
- Version controlled using the Git Sync extension

!!! warning "New records are disabled by default"
    Every new Hive record — D&R rules, FP rules, secrets, lookups, YARA sources, cloud sensors, AI skills, playbooks, etc. — is created **disabled** unless the request explicitly sets `usr_mtd.enabled: true`. A disabled record is stored normally but is skipped by every consumer that respects the flag (rules don't fire, lookups aren't queried, AI skills aren't enumerated). When debugging "the record exists but nothing happens", check `usr_mtd.enabled` first.

    Enable a record at creation time by either:

    1. Passing `--enabled` on the CLI `set` command (e.g. `limacharlie secret set --key … --input-file … --enabled`).
    2. Including `usr_mtd.enabled: true` in the request body / input file.
    3. Setting `enabled=True` (Python SDK) or `Enabled: &enabled` (Go SDK) on the record before calling `set` / `Add`.

    Or call the matching `enable` subcommand after creation (`limacharlie <hive> enable --key …`).

---

## See Also

- [D&R Rules](dr-rules.md)
- [Secrets Manager](secrets.md)
- [Lookups](lookups.md)
