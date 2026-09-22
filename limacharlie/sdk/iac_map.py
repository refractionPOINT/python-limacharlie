"""Local preflight for the sanitized lc-iac-map/v1 upload contract."""
from __future__ import annotations

import json
import re
import time
import unicodedata

MAX_BYTES = 10 * 1024 * 1024
EXTRACT_COMMAND = "limacharlie cloudsec code iac-map extract --input terraform.json --source-kind state_identity --repository owner/repo --commit FULL_COMMIT --workspace default"


def _refuse():
    raise ValueError("invalid sanitized IaC map; run " + EXTRACT_COMMAND)


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            _refuse()
        out[key] = value
    return out


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or not value.keys() <= set(required) | set(optional):
        _refuse()


def validate_iac_map(document: bytes | str) -> bytes:
    """Validate bounded sanitized JSON locally before any authenticated upload.

    Args:
        document: UTF-8 lc-iac-map/v1 bytes or text, never raw Terraform.

    Returns:
        bytes: Validated original bytes; the server canonicalizes independently.

    Raises:
        ValueError: If input is raw, malformed, ambiguous, or exceeds bounds.
    """
    if isinstance(document, str):
        if len(document) > MAX_BYTES:
            _refuse()
        try:
            document = document.encode("utf-8")
        except UnicodeError:
            _refuse()
    if not isinstance(document, bytes) or len(document) > MAX_BYTES:
        _refuse()
    # Bound nesting before Python's recursive JSON decoder runs. Braces within a
    # string do not count; malformed quoting is still rejected by json.loads.
    depth = 0
    quoted = escaped = False
    for byte in document:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 8:
                _refuse()
        elif byte in (93, 125):
            depth -= 1
    try:
        obj = json.loads(document, object_pairs_hook=_pairs,
                         parse_constant=lambda _: _refuse())
    except (ValueError, UnicodeError, RecursionError):
        _refuse()
    deadline = time.monotonic() + 2
    stack = [obj]
    nodes = 0
    while stack:
        value = stack.pop()
        nodes += 1
        if nodes > 2_000_000 or time.monotonic() > deadline:
            _refuse()
        if isinstance(value, dict):
            if len(value) > 256:
                _refuse()
            stack.extend(value.keys())
            stack.extend(value.values())
        elif isinstance(value, list):
            if len(value) > 50_000:
                _refuse()
            stack.extend(value)
        elif isinstance(value, str):
            try:
                invalid = len(value.encode("utf-8")) > 4096
            except UnicodeError:
                _refuse()
            if invalid or any(unicodedata.category(ch) in ("Cc", "Cf") or ch == "\ufffd" for ch in value):
                _refuse()
        elif value is None or type(value) not in (bool, int):
            _refuse()
    _keys(obj, ("schema", "repository", "tool", "workspace", "source_kind", "observed_at", "complete", "successful", "resources"))
    if obj["schema"] != "lc-iac-map/v1" or obj["tool"] not in ("terraform", "opentofu") or obj["source_kind"] not in ("state_identity", "plan_desired"):
        _refuse()
    if type(obj["complete"]) is not bool or type(obj["successful"]) is not bool or not isinstance(obj["resources"], list):
        _refuse()
    repo = obj["repository"]
    _keys(repo, ("provider", "name", "commit"))
    if repo["provider"] not in ("github", "gitlab", "bitbucket") or not isinstance(repo["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", repo["commit"]):
        _refuse()
    seen = set()
    for resource in obj["resources"]:
        _keys(resource, ("address", "type", "provider", "scope", "identity"), ("desired", "file", "line"))
        spec = _TYPES.get(resource["type"]) if isinstance(resource["type"], str) else None
        if spec is None or resource["provider"] != spec[0] or not isinstance(resource["address"], str) or resource["address"] in seen:
            _refuse()
        seen.add(resource["address"])
        _keys(resource["scope"], (), ("project", "account", "subscription", "region"))
        _keys(resource["identity"], (), ("native_id", "name"))
        if not resource["identity"] or any(not isinstance(v, str) for v in (*resource["scope"].values(), *resource["identity"].values())):
            _refuse()
        desired = resource.get("desired", {})
        _keys(desired, (), spec[1])
        if any(type(v) is not bool for v in desired.values()) or (obj["source_kind"] == "state_identity" and desired):
            _refuse()
    return document


# Closed v1 extraction allowlist; arbitrary desired values are never uploaded.
_TYPES = {'aws_db_instance': ('aws',
                     ('publicly_accessible', 'storage_encrypted', 'deletion_protection')),
 'aws_dynamodb_table': ('aws', ('deletion_protection_enabled',)),
 'aws_instance': ('aws', ('associate_public_ip_address',)),
 'aws_rds_cluster': ('aws', ('storage_encrypted', 'deletion_protection')),
 'aws_redshift_cluster': ('aws', ('publicly_accessible', 'encrypted')),
 'aws_s3_bucket': ('aws', ('force_destroy',)),
 'azurerm_cosmosdb_account': ('azure', ('public_network_access_enabled',)),
 'azurerm_key_vault': ('azure', ('public_network_access_enabled', 'purge_protection_enabled')),
 'azurerm_linux_virtual_machine': ('azure', ()),
 'azurerm_mssql_server': ('azure', ('public_network_access_enabled',)),
 'azurerm_mysql_flexible_server': ('azure', ('public_network_access_enabled',)),
 'azurerm_postgresql_flexible_server': ('azure', ('public_network_access_enabled',)),
 'azurerm_redis_cache': ('azure', ('public_network_access_enabled', 'non_ssl_port_enabled')),
 'azurerm_storage_account': ('azure',
                             ('https_traffic_only_enabled',
                              'public_network_access_enabled',
                              'allow_nested_items_to_be_public')),
 'azurerm_virtual_machine': ('azure', ()),
 'azurerm_windows_virtual_machine': ('azure', ()),
 'google_bigquery_dataset': ('gcp', ()),
 'google_compute_instance': ('gcp', ('deletion_protection', 'can_ip_forward')),
 'google_pubsub_subscription': ('gcp', ()),
 'google_pubsub_topic': ('gcp', ()),
 'google_sql_database_instance': ('gcp', ('deletion_protection',)),
 'google_storage_bucket': ('gcp', ('uniform_bucket_level_access', 'force_destroy'))}
