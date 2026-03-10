"""Command discovery and explain system for LimaCharlie CLI v2.

Provides profile-based command grouping, help topics, and contextual
explain texts consumed by the --ai-help system.
"""

from __future__ import annotations

from typing import Any

# Profile definitions mapping use-case profiles to their relevant command groups
PROFILES = {
    "sensor_management": {
        "description": "Sensor lifecycle, deployment, and monitoring commands",
        "commands": [
            "sensor list", "sensor get", "sensor delete", "sensor online",
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
            "rule list", "rule get", "rule create", "rule update", "rule delete",
            "rule test", "rule replay", "rule validate", "rule export", "rule import",
            "fp list", "fp get", "fp create", "fp delete",
            "replay run",
            "ai generate-rule", "ai generate-detection", "ai generate-response",
            "dr convert-rules",
        ],
    },
    "historical_data": {
        "description": "Searching, querying, and analyzing historical telemetry",
        "commands": [
            "search run", "search validate", "search estimate", "search interactive",
            "search saved list", "search saved get", "search saved create", "search saved delete",
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
        ],
    },
    "fleet_management": {
        "description": "Installation keys, deployment, upgrades, downloads, and fleet-wide operations",
        "commands": [
            "installation-key list", "installation-key create", "installation-key delete",
            "download sensor", "download adapter", "download list",
            "sensor upgrade", "sensor set-version", "sensor export",
            "tag mass-add", "tag mass-remove",
            "sync pull", "sync push", "sync diff",
        ],
    },
    "platform_admin": {
        "description": "Users, groups, API keys, billing, outputs, and organization management",
        "commands": [
            "org info", "org list", "org create", "org delete", "org config get",
            "org config set", "org urls", "org stats", "org errors",
            "user list", "user invite", "user remove", "user permissions list",
            "group list", "group create", "group delete",
            "api-key list", "api-key create", "api-key delete",
            "billing status", "billing details", "billing plans",
            "output list", "output create", "output delete",
            "audit list",
            "api",
        ],
    },
    "ai_powered": {
        "description": "AI-powered generation of rules, queries, selectors, and playbooks",
        "commands": [
            "ai generate-rule", "ai generate-detection", "ai generate-response",
            "ai generate-query", "ai generate-selector", "ai generate-playbook",
            "ai summarize-detection",
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
