from __future__ import annotations

"""Configuration management for LimaCharlie SDK & CLI v2.

Handles credential resolution, environment/profile management, and config file I/O.

Credential resolution order (highest priority first):
    1. Explicit parameters passed to Client()
    2. LC_OID, LC_API_KEY, LC_UID environment variables
    3. Named environment from LC_CURRENT_ENV (or 'default')
    4. Default credentials in ~/.limacharlie config file
"""

import os
import stat
import shutil
import tempfile
from typing import Any, TypedDict

import yaml

from .errors import ConfigError


class Credentials(TypedDict):
    """Credential dict returned by resolve_credentials and get_environment_creds."""

    oid: str | None
    uid: str | None
    api_key: str | None
    oauth: dict[str, str] | None


# Default config file path
CONFIG_FILE_PATH = os.path.expanduser("~/.limacharlie")

# Environment variable names
ENV_OID = "LC_OID"
ENV_API_KEY = "LC_API_KEY"
ENV_UID = "LC_UID"
ENV_CURRENT_ENV = "LC_CURRENT_ENV"
ENV_CREDS_FILE = "LC_CREDS_FILE"
ENV_EPHEMERAL_CREDS = "LC_EPHEMERAL_CREDS"


def _get_config_path() -> str:
    """Return the config file path, respecting LC_CREDS_FILE override."""
    return os.environ.get(ENV_CREDS_FILE, CONFIG_FILE_PATH)


def is_ephemeral() -> bool:
    """Return True if ephemeral credentials mode is enabled."""
    return bool(os.environ.get(ENV_EPHEMERAL_CREDS))


def load_config() -> dict[str, Any] | None:
    """Load the config file as a dict.

    Returns:
        dict or None if the file does not exist or ephemeral mode is active.
    """
    if is_ephemeral():
        return None
    path = _get_config_path()
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        data = yaml.safe_load(f.read())
    return data or {}


def save_config(config: dict[str, Any]) -> None:
    """Securely write the config dict to the config file.

    Uses atomic write (write to temp, chmod 600, then move) to prevent
    race conditions where another user could read credentials mid-write.

    Args:
        config: dict to serialize as YAML.

    Raises:
        ConfigError: if ephemeral mode is active.
    """
    if is_ephemeral():
        raise ConfigError(
            "Cannot write config in ephemeral credentials mode (LC_EPHEMERAL_CREDS is set).",
            suggestion="Use environment variables (LC_OID, LC_API_KEY) instead of config files.",
        )

    path = _get_config_path()
    content = yaml.safe_dump(config, default_flow_style=False).encode()

    fd, tmp_path = tempfile.mkstemp()
    try:
        # os.chown/os.getuid are Unix-only; skip on Windows where file
        # ownership is managed by the OS via ACLs.
        if hasattr(os, "chown"):
            os.chown(tmp_path, os.getuid(), os.getgid())
        os.chmod(tmp_path, stat.S_IWUSR | stat.S_IRUSR)  # 0o600
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
        shutil.move(tmp_path, path)
    finally:
        if os.path.isfile(tmp_path):
            os.unlink(tmp_path)


def get_environment_creds(name: str = "default") -> Credentials:
    """Load credentials for a named environment from the config file.

    Args:
        name: environment name ('default' for top-level creds).

    Returns:
        dict with keys: oid, uid, api_key, oauth (any may be None).
    """
    result = {"oid": None, "uid": None, "api_key": None, "oauth": None}

    if is_ephemeral():
        return result

    config = load_config()
    if config is None:
        return result

    if name == "default":
        result["oid"] = config.get("oid")
        result["uid"] = config.get("uid")
        result["api_key"] = config.get("api_key")
        result["oauth"] = config.get("oauth")
    else:
        env_data = config.get("env", {}).get(name, {})
        result["oid"] = env_data.get("oid")
        result["uid"] = env_data.get("uid")
        result["api_key"] = env_data.get("api_key")
        result["oauth"] = env_data.get("oauth")

    return result


def resolve_credentials(
    oid: str | None = None,
    api_key: str | None = None,
    uid: str | None = None,
    environment: str | None = None,
) -> Credentials:
    """Resolve credentials from all sources in priority order.

    Priority: explicit params > env vars > config file.

    Args:
        oid: explicit org ID.
        api_key: explicit API key.
        uid: explicit user ID.
        environment: named environment to load from config.

    Returns:
        dict with keys: oid, uid, api_key, oauth.
    """
    result = {"oid": None, "uid": None, "api_key": None, "oauth": None}

    # 1. If a specific environment is requested, load it first as the base
    if environment is not None:
        result = get_environment_creds(environment)
    else:
        # Try env vars first, then default config
        env_oid = os.environ.get(ENV_OID)
        env_key = os.environ.get(ENV_API_KEY)
        env_uid = os.environ.get(ENV_UID)

        if env_key is not None:
            # If LC_API_KEY is set, use env vars
            result["oid"] = env_oid
            result["uid"] = env_uid
            result["api_key"] = env_key
        else:
            # Fall back to config file (named env or default)
            env_name = os.environ.get(ENV_CURRENT_ENV) or None
            if env_name is None:
                # Check if a current_env is set in the config file
                cfg = load_config()
                if cfg is not None:
                    env_name = cfg.get("current_env")
            env_name = env_name or "default"
            result = get_environment_creds(env_name)

            # Even if we loaded from file, env vars for OID/UID override
            if env_oid is not None:
                result["oid"] = env_oid
            if env_uid is not None:
                result["uid"] = env_uid

    # 2. Explicit parameters always override
    if oid is not None:
        result["oid"] = oid
    if api_key is not None:
        result["api_key"] = api_key
        # If an explicit API key is provided, clear any OAuth creds
        # and uid from config file fallback since the API key takes
        # precedence. Including a stale uid with an API key causes
        # the JWT endpoint to reject the request.
        result["oauth"] = None
        result["uid"] = None
    if uid is not None:
        result["uid"] = uid

    return result


def write_credentials(environment: str | None, oid: str | None, api_key: str | None, uid: str = "", oauth_creds: dict[str, str] | None = None) -> None:
    """Write credentials to the config file for a named environment.

    Args:
        environment: environment name ('default' for top-level).
        oid: organization ID.
        api_key: API key (may be None for OAuth).
        uid: user ID (empty string to clear).
        oauth_creds: OAuth credentials dict.
    """
    config = load_config() or {}

    if environment == "default" or environment is None:
        if oid is not None:
            config["oid"] = oid
        if api_key is not None:
            config["api_key"] = api_key
        if uid != "":
            config["uid"] = uid
        elif uid == "" and "uid" in config:
            config.pop("uid", None)
        if oauth_creds is not None:
            config["oauth"] = oauth_creds
    else:
        config.setdefault("env", {})
        config["env"].setdefault(environment, {})
        env = config["env"][environment]
        if oid is not None:
            env["oid"] = oid
        if api_key is not None:
            env["api_key"] = api_key
        if uid != "":
            env["uid"] = uid
        elif uid == "" and "uid" in env:
            env.pop("uid", None)
        if oauth_creds is not None:
            env["oauth"] = oauth_creds

    save_config(config)


def list_environments() -> list[str]:
    """List all configured environment names.

    Returns:
        list of environment name strings.
    """
    config = load_config()
    if config is None:
        return []
    envs = list(config.get("env", {}).keys())
    # Add 'default' if top-level creds exist
    if config.get("oid") or config.get("api_key") or config.get("oauth"):
        envs.insert(0, "default")
    return envs
