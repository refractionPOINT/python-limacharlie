"""Command discovery and explain system for LimaCharlie CLI v2.

Provides profile-based command grouping, help topics, and contextual
explain texts consumed by the --ai-help system.
"""

from __future__ import annotations

from typing import Any

# Use-case profiles shared with lc-mcp-server. Its ``historical_data_readonly``
# and ``cloud_security_readonly`` profiles are permission-restricted variants,
# not distinct discovery use cases. The CLI also keeps its older
# ``sensor_management`` and ``cases`` profiles; they are separate profiles whose
# commands overlap ``fleet_management`` and ``investigation_management``.
MCP_USE_CASE_PROFILES = frozenset({
    "core",
    "historical_data",
    "live_investigation",
    "threat_response",
    "fleet_management",
    "detection_engineering",
    "platform_admin",
    "ai_powered",
    "api_access",
    "investigation_management",
    "cloud_security",
})

# Profile definitions mapping use-case profiles to their relevant command groups
PROFILES = {
    "core": {
        "description": "Authentication, local configuration, shell completion, and built-in help",
        "commands": [
            "auth login", "auth logout", "auth whoami", "auth use-org",
            "auth test", "auth use-env", "auth list-envs", "auth list-orgs",
            "auth signup", "auth get-token",
            "config show-paths", "config migrate",
            "completion",
            "help discover", "help topic", "help cheatsheet",
        ],
    },
    "sensor_management": {
        "description": "Sensor lifecycle, deployment, and monitoring commands",
        "commands": [
            "sensor list", "sensor get", "sensor delete",
            "sensor wait-online", "sensor upgrade", "sensor set-version",
            "sensor export", "sensor dump", "sensor sweep",
            "tag list", "tag add", "tag remove", "tag find",
            "tag mass-add", "tag mass-remove",
            "endpoint-policy isolate", "endpoint-policy rejoin", "endpoint-policy status",
            "endpoint-policy seal", "endpoint-policy unseal",
            "installation-key list", "installation-key create", "installation-key delete",
        ],
    },
    "detection_engineering": {
        "description": "D&R rule creation, testing, deployment, and false positives",
        "commands": [
            "dr list", "dr get", "dr set", "dr delete",
            "dr test", "dr replay", "dr validate", "dr export", "dr import",
            "dr convert-rules",
            "fp list", "fp get", "fp set", "fp delete",
            "exfil list", "exfil create-watch", "exfil create-event", "exfil delete",
            "integrity list", "integrity get", "integrity create", "integrity delete",
            "logging list", "logging get", "logging create", "logging delete",
            "schema list", "schema get", "schema reset",
            "usp validate",
            "replay run",
            "ai generate-rule", "ai generate-detection", "ai generate-response",
        ],
    },
    "historical_data": {
        "description": "Searching, querying, and analyzing historical telemetry",
        "commands": [
            "search run", "search validate", "search estimate",
            "search saved-list", "search saved-get", "search saved-create", "search saved-delete",
            "event list", "event get", "event children", "event overview", "event timeline",
            "event types", "event schema", "event retention",
            "detection list", "detection get",
            "ai generate-query",
        ],
    },
    "live_investigation": {
        "description": "Real-time sensor tasking, streaming, and IOC searching",
        "commands": [
            "task send", "task request", "task reliable-send", "task reliable-list",
            "stream events", "stream detections", "stream audit",
            "ioc search", "ioc batch-search", "ioc hosts", "ioc enrich", "ioc batch-enrich",
            "stream firehose",
            "artifact list", "artifact upload", "artifact download",
            "payload list", "payload upload", "payload download", "payload delete",
            "spotcheck run",
        ],
    },
    "threat_response": {
        "description": "Incident response: isolation, tagging, sensor management during threats",
        "commands": [
            "endpoint-policy isolate", "endpoint-policy rejoin",
            "tag add", "tag mass-add",
            "task send", "task request",
            "sensor dump", "sensor sweep",
            "yara scan",
            "case list", "case get", "case update", "case add-note",
            "case entity add", "case entity search",
            "mailsec message list", "mailsec message get", "mailsec message action",
            "mailsec message bulk-action", "mailsec campaign action",
            "mailsec hunt create", "mailsec hunt remediate",
        ],
    },
    "fleet_management": {
        "description": "Installation keys, deployment, upgrades, downloads, and fleet-wide operations",
        "commands": [
            "installation-key list", "installation-key create", "installation-key delete",
            "download sensor", "download adapter", "download list",
            "sensor upgrade", "sensor set-version", "sensor export",
            "tag mass-add", "tag mass-remove",
            "sync pull", "sync push",
        ],
    },
    "platform_admin": {
        "description": "Organization, users, groups, API and ingestion keys, billing, outputs, adapters, extensions, jobs, and hive records (apps, lookups, notes, playbooks, secrets, SOPs)",
        "commands": [
            "org info", "org list", "org create", "org delete", "org config-get",
            "org config-set", "org urls", "org stats", "org errors",
            "user list", "user invite", "user remove", "user permissions list",
            "group list", "group create", "group delete",
            "api-key list", "api-key create", "api-key delete",
            "billing status", "billing details", "billing plans",
            "output list", "output create", "output delete",
            "audit list",
            "api",
            "app list", "app get", "app set", "app delete",
            "app enable", "app disable", "app tag set", "app tag add", "app tag rm",
            "cloud-adapter list", "cloud-adapter get", "cloud-adapter set", "cloud-adapter delete",
            "cloud-adapter enable", "cloud-adapter disable", "cloud-adapter tag set",
            "cloud-adapter tag add", "cloud-adapter tag rm", "cloud-adapter list-types",
            "cloud-adapter schema", "cloud-adapter sensors",
            "external-adapter list", "external-adapter get", "external-adapter set", "external-adapter delete",
            "external-adapter enable", "external-adapter disable", "external-adapter tag set",
            "external-adapter tag add", "external-adapter tag rm", "external-adapter list-types",
            "external-adapter schema", "external-adapter sensors",
            "extension list", "extension subscribe", "extension unsubscribe", "extension list-available",
            "extension rekey", "extension schema", "extension request",
            "extension config-list", "extension config-get", "extension config-set", "extension config-delete",
            "hive list", "hive get", "hive set", "hive delete", "hive enable", "hive disable",
            "hive validate", "hive schema", "hive rename", "hive list-types", "hive export", "hive import",
            "ingestion-key list", "ingestion-key create", "ingestion-key delete",
            "job list", "job get", "job delete", "job wait",
            "lookup list", "lookup get", "lookup set", "lookup delete",
            "lookup enable", "lookup disable", "lookup tag set", "lookup tag add", "lookup tag rm",
            "note list", "note get", "note set", "note delete",
            "note enable", "note disable", "note tag set", "note tag add", "note tag rm",
            "playbook list", "playbook get", "playbook set", "playbook delete",
            "playbook enable", "playbook disable", "playbook tag set", "playbook tag add", "playbook tag rm",
            "secret list", "secret get", "secret set", "secret delete",
            "secret enable", "secret disable", "secret tag set", "secret tag add", "secret tag rm",
            "sop list", "sop get", "sop set", "sop delete",
            "sop enable", "sop disable", "sop tag set", "sop tag add", "sop tag rm",
        ],
    },
    "ai_powered": {
        "description": "AI-powered generation of rules, queries, selectors, and playbooks, plus AI cost models, memory, and skills",
        "commands": [
            "ai generate-rule", "ai generate-detection", "ai generate-response",
            "ai generate-query", "ai generate-selector", "ai generate-playbook",
            "ai summarize-detection",
            "ai-cost-model list", "ai-cost-model get", "ai-cost-model set", "ai-cost-model delete",
            "ai-cost-model enable", "ai-cost-model disable", "ai-cost-model tag set",
            "ai-cost-model tag add", "ai-cost-model tag rm",
            "ai-memory list-records", "ai-memory list", "ai-memory get",
            "ai-memory set", "ai-memory delete", "ai-memory delete-record",
            "ai-skill list", "ai-skill get", "ai-skill set", "ai-skill delete",
            "ai-skill enable", "ai-skill disable", "ai-skill tag set", "ai-skill tag add", "ai-skill tag rm",
        ],
    },
    "api_access": {
        "description": "Direct API access and authentication for automation",
        "commands": [
            "api",
            "auth get-token", "auth whoami", "auth test",
        ],
    },
    "cases": {
        "description": "SOC case lifecycle, investigation tracking, and reporting",
        "commands": [
            "case list", "case get", "case update",
            "case add-note", "case bulk-update", "case merge",
            "case entity list", "case entity add", "case entity update",
            "case entity remove", "case entity search",
            "case telemetry list", "case telemetry add",
            "case telemetry update", "case telemetry remove",
            "case artifact list", "case artifact add", "case artifact remove",
            "case detection list", "case detection add", "case detection remove",
            "case tag set", "case tag add", "case tag remove",
            "case report", "case dashboard",
            "case config-get", "case config-set",
            "case assignees",
        ],
    },
    "investigation_management": {
        "description": "Case workflows, analyst feedback, notes, and investigation artifacts",
        "commands": [
            "case list", "case get", "case update", "case add-note",
            "case bulk-update", "case merge", "case report", "case dashboard",
            "feedback request-approval", "feedback request-ack", "feedback request-question",
            "feedback channel list", "feedback channel add", "feedback channel remove",
            "note list", "note get", "note set", "note delete",
            "artifact list", "artifact upload", "artifact download",
        ],
    },
    "cloud_security": {
        "description": "Cloud posture, identity, findings, attack paths, and vulnerability management",
        "commands": [
            "cloudsec overview", "cloudsec changes", "cloudsec risk-trend", "cloudsec scan-status",
            "cloudsec topology", "cloudsec free-tier",
            "cloudsec code repos", "cloudsec code status", "cloudsec code sbom",
            "cloudsec code capabilities", "cloudsec code fixes",
            "cloudsec code rescan", "cloudsec code autofix", "cloudsec code ingest", "cloudsec code scan",
            "cloudsec code pr-check", "cloudsec code webhook",
            "cloudsec code iac-map extract", "cloudsec code iac-map push",

            "cloudsec code provenance push", "cloudsec code provenance list",
            "cloudsec code impact", "cloudsec code coverage",
            "cloudsec image repos", "cloudsec image repo-facets",
            "cloudsec image list", "cloudsec image get",
            "cloudsec fleet overview",
            "cloudsec finding list", "cloudsec finding facets", "cloudsec finding causes",
            "cloudsec finding classes", "cloudsec finding get",
            "cloudsec finding runtime-check", "cloudsec finding chain", "cloudsec finding resolve",
            "cloudsec finding bulk-resolve", "cloudsec finding set-owner", "cloudsec finding set-ticket",
            "cloudsec remediation list", "cloudsec remediation get", "cloudsec remediation create",
            "cloudsec remediation approve", "cloudsec remediation reject", "cloudsec remediation cancel",
            "cloudsec attack-path list",
            "cloudsec ciem public-access", "cloudsec ciem facets", "cloudsec ciem identities", "cloudsec ciem identity",
            "cloudsec inventory list", "cloudsec inventory facets",
            "cloudsec data-security facets", "cloudsec data-security stores",
            "cloudsec resource get", "cloudsec graph neighbors",
            "cloudsec query list", "cloudsec query run",
            "cloudsec compliance report", "cloudsec compliance frameworks", "cloudsec compliance assignments",
            "cloudsec compliance run", "cloudsec compliance runs",
            "cloudsec compliance attestations", "cloudsec compliance attest",
            "cloudsec compliance events", "cloudsec compliance export",
            "cloudsec compliance schedules", "cloudsec compliance schedule-set",
            "cloudsec azure scope-hierarchy",
            "cloudsec chokepoint list", "cloudsec chokepoint dismiss", "cloudsec chokepoint restore",
            "cloudsec resolve sensors", "cloudsec resolve assets",
            "cloudsec caasm assets", "cloudsec caasm coverage", "cloudsec caasm policy get",
            "cloudsec caasm policy set", "cloudsec caasm ingest",
            "cloudsec provider manifest", "cloudsec provider test",
            "cloudsec policy vocabulary", "cloudsec policy suggest",
            "cloudsec simulate resources", "cloudsec simulate findings",
            "cloudsec export findings", "cloudsec export inventory",
            "cloudsec export compliance", "cloudsec export query",
            "vulnerability scan", "vulnerability dashboard",
            "vulnerability cve list", "vulnerability cve get", "vulnerability cve hosts",
            "vulnerability cve packages", "vulnerability cve epss-history",
            "vulnerability host list", "vulnerability host packages",
            "vulnerability finding resolve", "vulnerability finding bulk-resolve",
            "vulnerability finding list", "vulnerability finding reset",
            "vulnerability snapshot list",
        ],
    },
    "email_security": {
        "description": "Email security: mail triage queue, verdicts, campaigns, remediation, and reports",
        "commands": [
            "mailsec coverage",
            "mailsec message list", "mailsec message get", "mailsec message eml",
            "mailsec message similar", "mailsec message action",
            "mailsec message revise", "mailsec message revisions",
            "mailsec message bulk-action", "mailsec message bulk-status",
            "mailsec campaign list", "mailsec campaign get", "mailsec campaign action",
            "mailsec sender get",
            "mailsec action get",
            "mailsec analyze",
            "mailsec report list", "mailsec report get",
            "mailsec report resolve", "mailsec report reopen",
            "mailsec hunt create", "mailsec hunt get", "mailsec hunt remediate",
            "mailsec rule validate", "mailsec rule backtest",
            "mailsec connection test",
            "mailsec onboarding",
            "mailsec tenant purge",
        ],
    },
    "data_access": {
        "description": "Retrieve data through the Authenticated Resource Locator (ARL) resolver",
        "commands": [
            "arl get",
        ],
    },
}

# Explain text registry - populated by commands via @explain decorator or register_explain()
_EXPLAIN_REGISTRY = {}


def register_explain(command_path: str, text: str) -> None:
    """Register explain text for a command.

    Args:
        command_path: Dotted command path (e.g., 'rule.create').
        text: Multi-paragraph explain text.
    """
    _EXPLAIN_REGISTRY[command_path] = text


def get_explain(command_path: str) -> str | None:
    """Get explain text for a command.

    Args:
        command_path: Dotted command path.

    Returns:
        str or None.
    """
    return _EXPLAIN_REGISTRY.get(command_path)


def get_profile(name: str) -> dict[str, Any] | None:
    """Get profile definition by name.

    Args:
        name: Profile name.

    Returns:
        dict with 'description' and 'commands' or None.
    """
    return PROFILES.get(name)


def list_profiles() -> list[tuple[str, str]]:
    """List all available profile names and descriptions.

    Returns:
        list of (name, description) tuples.
    """
    return [(name, info["description"]) for name, info in PROFILES.items()]


def format_discovery(profile_name: str | None = None) -> str:
    """Format the discovery output.

    Args:
        profile_name: Optional profile name to filter by.

    Returns:
        str: Formatted discovery text.
    """
    if profile_name:
        profile = get_profile(profile_name)
        if profile is None:
            available = ", ".join(PROFILES.keys())
            return f"Unknown profile: {profile_name}\nAvailable profiles: {available}"

        lines = [f"Profile: {profile_name}", f"  {profile['description']}", "", "Commands:"]
        for cmd in profile["commands"]:
            lines.append(f"  limacharlie {cmd}")
        return "\n".join(lines)

    # Show all profiles
    lines = ["LimaCharlie CLI - Command Discovery", "=" * 40, ""]
    for name, info in PROFILES.items():
        lines.append(f"[{name}]")
        lines.append(f"  {info['description']}")
        lines.append(f"  Commands: {len(info['commands'])}")
        lines.append("")

    lines.append("Use 'limacharlie discover --profile <name>' for command details.")
    lines.append("Use 'limacharlie help <topic>' for concept guides.")
    return "\n".join(lines)
