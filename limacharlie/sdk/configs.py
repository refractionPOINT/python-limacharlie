"""Configuration Sync (IaC) SDK for LimaCharlie v2."""

from __future__ import annotations

import json
import os
import glob as glob_module
from typing import Any, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from .organization import Organization


class ConfigException(Exception):
    """Configuration file error."""
    pass


class _QuotedStrDumper(yaml.SafeDumper):
    """SafeDumper that writes every string as a double-quoted scalar.

    PyYAML implements YAML 1.1 and leaves a string unquoted whenever YAML 1.1
    would read it back as a string. ext-infrastructure parses the pushed
    config with gopkg.in/yaml.v3, which applies YAML 1.2 rules, where some of
    those bare strings are numbers: ``0308``, ``0129``, ``1e3`` and ``0o17``
    would be stored in the hive as 308, 129, 1000 and 15. A double-quoted
    scalar is a string under every YAML version. Every other type is written
    exactly as ``yaml.safe_dump`` writes it.
    """


def _represent_quoted_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


_QuotedStrDumper.add_representer(str, _represent_quoted_str)


def _dump_push_config(config: dict[str, Any]) -> str:
    """Serialize a config for ext-infrastructure's ``push`` action.

    Args:
        config: Dict of configuration data to push.

    Returns:
        str: The config as a YAML document with every string double-quoted.
    """
    return yaml.dump(config, Dumper=_QuotedStrDumper, version=(1, 1))


def _unalias(value: Any, _path: tuple[int, ...] = ()) -> Any:
    """Rebuild dicts and lists so no object appears twice in the result.

    YAML anchors and aliases load as one shared object. Merging updates maps
    and lists in place, so a shared object would change in several places at
    once. (``copy.deepcopy`` keeps shared references shared, so it can't be
    used for this.)

    Raises:
        ConfigException: If the file contains a self-referencing anchor.
    """
    if not isinstance(value, (dict, list)):
        return value
    if id(value) in _path:
        raise ConfigException("Config file contains a self-referencing YAML anchor.")
    path = _path + (id(value),)
    if isinstance(value, dict):
        return {k: _unalias(v, path) for k, v in value.items()}
    return [_unalias(v, path) for v in value]


# Categories whose top-level keys hold maps that are merged one level deeper
# (hive name -> records, exfil section -> entries, yara rules/sources).
_NESTED_MERGE_CATEGORIES = frozenset({"hives", "exfil", "yara"})


class Configs:
    """Infrastructure-as-Code: fetch and push org configuration.

    Uses the ext-infrastructure extension to sync outputs, integrity, exfil,
    artifact, extensions, resources, org values, hives, installation keys,
    and YARA rules.

    D&R rules and FP rules should be synced via their respective hives
    (dr-general, dr-managed, dr-service, fp) rather than the legacy
    sync_dr / sync_fp flags.
    """

    CONF_VERSION = 3

    CONFIG_ROOTS = {
        "outputs", "extensions", "resources", "integrity",
        "exfil", "artifact", "org-value", "hives",
        "installation_keys", "yara",
        # Legacy categories, still merged from includes like the Go SDK does.
        "rules", "fps",
    }

    # All known hive names that can be synced.
    ALL_HIVES = {
        "cloudsec_policy",
        "cloudsec_provider",
        "cloudsec_query",
        "cloudsec_code_rule",
        "mailsec_provider",
        "acl",
        "dr-general",
        "dr-mail",
        "mailsec_policy",
        "app_control_policy",
        "app_control_rule",
        "dr-managed",
        "dr-service",
        "fp",
        "cloud_sensor",
        "extension_config",
        "yara",
        "lookup",
        "secret",
        "query",
        "playbook",
        "ai_agent",
        "ai_skill",
        "ai_memory",
        "external_adapter",
    }

    def __init__(self, org: Organization) -> None:
        """Create a Configs instance.

        Args:
            org: Organization SDK object.
        """
        self._org = org

    def fetch(self, sync_outputs: bool = False,
              sync_integrity: bool = False, sync_artifact: bool = False, sync_exfil: bool = False,
              sync_resources: bool = False, sync_extensions: bool = False, sync_org_values: bool = False,
              sync_hives: dict[str, bool] | None = None, sync_installation_keys: bool = False,
              sync_yara: bool = False) -> dict[str, Any]:
        """Fetch the current org configuration from the cloud.

        Args:
            sync_outputs: Fetch outputs.
            sync_integrity: Fetch integrity rules.
            sync_artifact: Fetch artifact/logging rules.
            sync_exfil: Fetch exfil rules.
            sync_resources: Fetch resource subscriptions.
            sync_extensions: Fetch extension subscriptions.
            sync_org_values: Fetch org config values.
            sync_hives: Dict of hive names to sync (e.g., {"dr-general": True}).
            sync_installation_keys: Fetch installation keys.
            sync_yara: Fetch YARA rules and sources.

        Returns:
            dict: The org configuration.
        """
        if sync_hives is None:
            sync_hives = {}

        from .extensions import Extensions
        ext = Extensions(self._org)
        data = ext.request("ext-infrastructure", "fetch", {
            "options": {
                "sync_outputs": sync_outputs,
                "sync_resources": sync_resources,
                "sync_extensions": sync_extensions,
                "sync_integrity": sync_integrity,
                "sync_exfil": sync_exfil,
                "sync_artifacts": sync_artifact,
                "sync_org_values": sync_org_values,
                "sync_hives": sync_hives,
                "sync_installation_keys": sync_installation_keys,
                "sync_yara": sync_yara,
            },
        }, is_impersonated=True)
        return data.get("data", {}).get("org", {})

    def push(self, config: dict[str, Any], is_force: bool = False, is_dry_run: bool = False,
             ignore_inaccessible: bool = False,
             sync_outputs: bool = False, sync_integrity: bool = False, sync_artifact: bool = False,
             sync_exfil: bool = False, sync_resources: bool = False, sync_extensions: bool = False,
             sync_org_values: bool = False, sync_hives: dict[str, bool] | None = None,
             sync_installation_keys: bool = False, sync_yara: bool = False) -> tuple[list[tuple[str, str, str]], list[str]]:
        """Push configuration to the org in the cloud.

        Args:
            config: Dict of configuration data to push.
            is_force: If True, remove cloud configs not in local file.
            is_dry_run: If True, simulate without making changes.
            ignore_inaccessible: If True, skip locked resources even with force.
            sync_outputs: Push outputs.
            sync_integrity: Push integrity rules.
            sync_artifact: Push artifact/logging rules.
            sync_exfil: Push exfil rules.
            sync_resources: Push resource subscriptions.
            sync_extensions: Push extension subscriptions.
            sync_org_values: Push org config values.
            sync_hives: Dict of hive names to sync.
            sync_installation_keys: Push installation keys.
            sync_yara: Push YARA rules and sources.

        Returns:
            tuple: (results, errors) where results is a list of
                (op_type, resource_type, name) tuples and errors is a list
                of error strings from the backend.
                op_type is '+' (added), '-' (removed), or '=' (unchanged).
        """
        if sync_hives is None:
            sync_hives = {}

        final_config = _dump_push_config(config)

        from .extensions import Extensions
        ext = Extensions(self._org)
        data = ext.request("ext-infrastructure", "push", {
            "config": final_config,
            "options": {
                "is_dry_run": is_dry_run,
                "is_force": is_force,
                "ignore_inaccessible": ignore_inaccessible,
                "sync_outputs": sync_outputs,
                "sync_resources": sync_resources,
                "sync_extensions": sync_extensions,
                "sync_integrity": sync_integrity,
                "sync_exfil": sync_exfil,
                "sync_artifacts": sync_artifact,
                "sync_org_values": sync_org_values,
                "sync_hives": sync_hives,
                "sync_installation_keys": sync_installation_keys,
                "sync_yara": sync_yara,
            },
        }, is_impersonated=True)
        data = data.get("data", {})

        results: list[tuple[str, str, str]] = []
        for op in data.get("ops", []):
            if op.get("is_added"):
                results.append(("+", op["type"], op["name"]))
            elif op.get("is_removed"):
                results.append(("-", op["type"], op["name"]))
            else:
                results.append(("=", op["type"], op["name"]))

        errors: list[str] = []
        for err in data.get("errors", []):
            if isinstance(err, str):
                errors.append(err)
            elif isinstance(err, dict):
                errors.append(err.get("error", str(err)))
            else:
                errors.append(str(err))

        return results, errors

    def fetch_to_file(self, file_path: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch configuration and save to a YAML file.

        Args:
            file_path: Path to save the config file.
            **kwargs: Same as fetch().

        Returns:
            dict: API response.
        """
        config = self.fetch(**kwargs)
        with open(os.path.abspath(file_path), "wb") as f:
            f.write(yaml.safe_dump(config, default_flow_style=False, version=(1, 1)).encode())
        return config

    def push_from_file(self, file_path: str, **kwargs: Any) -> tuple[list[tuple[str, str, str]], list[str]]:
        """Load configuration from a YAML file and push it.

        Args:
            file_path: Path to the config file.
            **kwargs: Same as push() (except config).

        Returns:
            tuple: (results, errors) — same as push().
        """
        file_path = os.path.abspath(file_path)
        config, _ = self._load_effective_config(file_path)
        return self.push(config=config, **kwargs)

    def _load_effective_config(self, config_file: str) -> tuple[dict[str, Any], list[str]]:
        """Load a config file and resolve any includes.

        Args:
            config_file: Absolute path to config file.

        Returns:
            tuple: (config_dict, list_of_included_files) where the files are
                absolute paths, in processing order, without duplicates.
        """
        config_file = os.path.abspath(config_file)
        with open(config_file, "rb") as f:
            config = _unalias(yaml.safe_load(f.read().decode()))
        if config is None:
            config = {}
        if "version" not in config:
            raise ConfigException("Version not found in config file.")
        if self.CONF_VERSION < config["version"]:
            raise ConfigException(f"Config version {config['version']} not supported (max: {self.CONF_VERSION}).")

        context_path = os.path.dirname(config_file)
        original_path = os.getcwd()
        os.chdir(context_path)
        try:
            includes = config.get("include", [])
            if isinstance(includes, str):
                includes = [includes]

            # Includes are processed in the order they are listed, so the
            # result does not depend on filesystem or hash ordering. A glob
            # pattern expands to its matches in sorted order. A file reached
            # more than once (by several patterns, or listed twice) is only
            # processed at its first occurrence.
            ordered_includes: list[str] = []
            seen: set[str] = set()
            for pattern in includes:
                matches = sorted(glob_module.glob(pattern, recursive=True))
                if not matches and ("?" not in pattern and "*" not in pattern):
                    raise ConfigException(f"No files matched include pattern: {pattern}")
                for match in matches:
                    key = os.path.abspath(match)
                    if key in seen:
                        continue
                    seen.add(key)
                    ordered_includes.append(key)

            all_included: list[str] = []
            for include in ordered_includes:
                sub_config, sub_includes = self._load_effective_config(include)
                for included in [include, *sub_includes]:
                    if included not in all_included:
                        all_included.append(included)

                # The merge is cumulative: an include overrides the file that
                # includes it, and a later include overrides an earlier one.
                for cat in self.CONFIG_ROOTS:
                    self._merge_category(config, cat, sub_config.get(cat))
        finally:
            os.chdir(original_path)

        return config, all_included

    @staticmethod
    def _merge_category(config: dict[str, Any], cat: str, sub_cat: Any) -> None:
        """Merge one category of an included config over ``config``.

        Mirrors the Go SDK's ``OrgConfig.Merge``: the included value wins.
        Maps merge by record name (hives and exfil one level deeper, so a
        hive record or exfil event is replaced as a whole). Lists, and the
        per-name lists of ``resources``, are unions that keep first-seen
        order and drop duplicates. ``yara`` rules and sources merge by name.

        Args:
            config: The accumulated config, modified in place.
            cat: Category name.
            sub_cat: The category value from the included config, or None.
        """
        if sub_cat is None:
            return
        cur = config.get(cat)
        if isinstance(sub_cat, list):
            if cur is None:
                cur = config[cat] = []
            if not isinstance(cur, list):
                raise ConfigException(f"Cannot merge include: '{cat}' is a list in one file and a map in another.")
            for item in sub_cat:
                if item not in cur:
                    cur.append(item)
            return
        if not isinstance(sub_cat, dict):
            raise ConfigException(f"Cannot merge include: '{cat}' must be a map or a list.")
        if cur is None:
            cur = config[cat] = {}
        if not isinstance(cur, dict):
            raise ConfigException(f"Cannot merge include: '{cat}' is a map in one file and a list in another.")

        if cat in _NESTED_MERGE_CATEGORIES:
            for name, records in sub_cat.items():
                if isinstance(records, dict) and isinstance(cur.get(name), dict):
                    cur[name].update(records)
                else:
                    cur[name] = records
        elif cat == "resources":
            for name, items in sub_cat.items():
                if isinstance(items, list) and isinstance(cur.get(name), list):
                    cur[name].extend(i for i in items if i not in cur[name])
                else:
                    cur[name] = items
        else:
            cur.update(sub_cat)
