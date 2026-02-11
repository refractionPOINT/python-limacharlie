"""Configuration Sync (IaC) SDK for LimaCharlie v2."""

import json
import os
import glob as glob_module

import yaml


class ConfigException(Exception):
    """Configuration file error."""
    pass


class Configs:
    """Infrastructure-as-Code: fetch and push org configuration.

    Supports syncing D&R rules, FP rules, outputs, integrity, exfil,
    artifact, extensions, resources, org values, hives, installation keys,
    and YARA rules.
    """

    CONF_VERSION = 3

    CONFIG_ROOTS = {
        "rules", "outputs", "extensions", "resources", "integrity",
        "fps", "exfil", "artifact", "org-value", "hives",
        "installation_keys", "yara",
    }

    def __init__(self, org, use_extension=False):
        """Create a Configs instance.

        Args:
            org: Organization SDK object.
            use_extension: If True, use the infrastructure extension instead of service.
        """
        self._org = org
        self._use_extension = use_extension

    def fetch(self, sync_rules=False, sync_fps=False, sync_outputs=False,
              sync_integrity=False, sync_artifact=False, sync_exfil=False,
              sync_resources=False, sync_extensions=False, sync_org_values=False,
              sync_hives=None, sync_installation_keys=False, sync_yara=False):
        """Fetch the current org configuration from the cloud.

        Args:
            sync_rules: Fetch D&R rules.
            sync_fps: Fetch false positive rules.
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

        if self._use_extension:
            from .extensions import Extensions
            ext = Extensions(self._org)
            data = ext.request("ext-infrastructure", "fetch", {
                "options": {
                    "sync_dr": sync_rules,
                    "sync_outputs": sync_outputs,
                    "sync_resources": sync_resources,
                    "sync_extensions": sync_extensions,
                    "sync_integrity": sync_integrity,
                    "sync_fp": sync_fps,
                    "sync_exfil": sync_exfil,
                    "sync_artifacts": sync_artifact,
                    "sync_org_values": sync_org_values,
                    "sync_hives": sync_hives,
                    "sync_installation_keys": sync_installation_keys,
                    "sync_yara": sync_yara,
                },
            }, is_impersonated=True)
            return data.get("data", {}).get("org", {})
        else:
            data = self._org.service_request("infrastructure-service", {
                "action": "fetch",
                "sync_dr": sync_rules,
                "sync_outputs": sync_outputs,
                "sync_resources": sync_resources,
                "sync_extensions": sync_extensions,
                "sync_integrity": sync_integrity,
                "sync_fp": sync_fps,
                "sync_exfil": sync_exfil,
                "sync_artifacts": sync_artifact,
                "sync_org_values": sync_org_values,
                "sync_hives": sync_hives,
                "sync_installation_keys": sync_installation_keys,
                "sync_yara": sync_yara,
            }, is_impersonate=True)
            result = {"version": self.CONF_VERSION}
            org_yaml = data.get("org", "")
            if org_yaml:
                parsed = yaml.safe_load(org_yaml)
                if parsed:
                    result.update(parsed)
            return result

    def push(self, config, is_force=False, is_dry_run=False,
             ignore_inaccessible=False, sync_rules=False, sync_fps=False,
             sync_outputs=False, sync_integrity=False, sync_artifact=False,
             sync_exfil=False, sync_resources=False, sync_extensions=False,
             sync_org_values=False, sync_hives=None,
             sync_installation_keys=False, sync_yara=False):
        """Push configuration to the org in the cloud.

        Args:
            config: Dict of configuration data to push.
            is_force: If True, remove cloud configs not in local file.
            is_dry_run: If True, simulate without making changes.
            ignore_inaccessible: If True, skip locked resources even with force.
            sync_rules: Push D&R rules.
            sync_fps: Push false positive rules.
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
            list: List of (op_type, resource_type, name) tuples.
                op_type is '+' (added), '-' (removed), or '=' (unchanged).
        """
        if sync_hives is None:
            sync_hives = {}

        final_config = yaml.safe_dump(config, version=(1, 1))

        if self._use_extension:
            from .extensions import Extensions
            ext = Extensions(self._org)
            data = ext.request("ext-infrastructure", "push", {
                "config": final_config,
                "options": {
                    "is_dry_run": is_dry_run,
                    "is_force": is_force,
                    "ignore_inaccessible": ignore_inaccessible,
                    "sync_dr": sync_rules,
                    "sync_outputs": sync_outputs,
                    "sync_resources": sync_resources,
                    "sync_extensions": sync_extensions,
                    "sync_integrity": sync_integrity,
                    "sync_fp": sync_fps,
                    "sync_exfil": sync_exfil,
                    "sync_artifacts": sync_artifact,
                    "sync_org_values": sync_org_values,
                    "sync_hives": sync_hives,
                    "sync_installation_keys": sync_installation_keys,
                    "sync_yara": sync_yara,
                },
            }, is_impersonated=True)
            data = data.get("data", {})
        else:
            data = self._org.service_request("infrastructure-service", {
                "action": "push",
                "is_dry_run": is_dry_run,
                "is_force": is_force,
                "ignore_inaccessible": ignore_inaccessible,
                "config": final_config,
                "sync_dr": sync_rules,
                "sync_outputs": sync_outputs,
                "sync_resources": sync_resources,
                "sync_extensions": sync_extensions,
                "sync_integrity": sync_integrity,
                "sync_fp": sync_fps,
                "sync_exfil": sync_exfil,
                "sync_artifacts": sync_artifact,
                "sync_org_values": sync_org_values,
                "sync_hives": sync_hives,
                "sync_installation_keys": sync_installation_keys,
                "sync_yara": sync_yara,
            }, is_impersonate=True)

        results = []
        for op in data.get("ops", []):
            if op.get("is_added"):
                results.append(("+", op["type"], op["name"]))
            elif op.get("is_removed"):
                results.append(("-", op["type"], op["name"]))
            else:
                results.append(("=", op["type"], op["name"]))
        return results

    def fetch_to_file(self, file_path, **kwargs):
        """Fetch configuration and save to a YAML file.

        Args:
            file_path: Path to save the config file.
            **kwargs: Same as fetch().
        """
        config = self.fetch(**kwargs)
        with open(os.path.abspath(file_path), "wb") as f:
            f.write(yaml.safe_dump(config, default_flow_style=False, version=(1, 1)).encode())
        return config

    def push_from_file(self, file_path, **kwargs):
        """Load configuration from a YAML file and push it.

        Args:
            file_path: Path to the config file.
            **kwargs: Same as push() (except config).

        Returns:
            list: List of (op_type, resource_type, name) tuples.
        """
        file_path = os.path.abspath(file_path)
        config, _ = self._load_effective_config(file_path)
        return self.push(config=config, **kwargs)

    def _load_effective_config(self, config_file):
        """Load a config file and resolve any includes.

        Args:
            config_file: Absolute path to config file.

        Returns:
            tuple: (config_dict, list_of_included_files)
        """
        config_file = os.path.abspath(config_file)
        with open(config_file, "rb") as f:
            config = yaml.safe_load(f.read().decode())
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

            globbed_includes = set()
            for pattern in includes:
                found = False
                for match in glob_module.iglob(pattern, recursive=True):
                    globbed_includes.add(match)
                    found = True
                if ("?" not in pattern and "*" not in pattern) and not found:
                    raise ConfigException(f"No files matched include pattern: {pattern}")

            all_included = list(globbed_includes)
            for include in list(globbed_includes):
                sub_config, sub_includes = self._load_effective_config(include)
                all_included.extend(sub_includes)

                for cat in self.CONFIG_ROOTS:
                    sub_cat = sub_config.get(cat)
                    if sub_cat is None:
                        continue
                    if isinstance(sub_cat, list):
                        config.setdefault(cat, []).extend(sub_cat)
                    elif cat in ("exfil", "hives"):
                        for k, v in sub_cat.items():
                            config.setdefault(cat, {}).setdefault(k, {}).update(v)
                    else:
                        config.setdefault(cat, {}).update(sub_cat)
        finally:
            os.chdir(original_path)

        return config, all_included
