"""Configuration management commands for LimaCharlie CLI v2.

Commands for inspecting config paths, migrating from legacy layout,
and managing CLI configuration.
"""

from __future__ import annotations

import json
import os
from typing import Any

import click

from ..cli import pass_context
from ..discovery import register_explain
from ..file_utils import atomic_write, safe_open_read, secure_makedirs
from ..output import detect_output_format, format_output
from ..paths import (
    get_all_paths,
    get_config_dir,
    get_config_path,
    get_jwt_cache_path,
    get_legacy_paths,
    is_legacy_mode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _remove_stale_legacy(stale_legacy: list[dict[str, str]]) -> int:
    """Remove stale legacy files after verifying content matches destination.

    Returns the number of files that were skipped due to content mismatch.
    """
    skipped = 0
    for item in stale_legacy:
        if not _safe_content_match(item["path"], item["dest"]):
            click.echo(
                f"Warning: Legacy {item['label']} ({item['path']}) differs from "
                f"{item['dest']}. Skipping removal - review both files manually.",
                err=True,
            )
            skipped += 1
            continue
        try:
            os.unlink(item["path"])
            click.echo(f"Removed legacy {item['label']}: {item['path']}")
        except OSError as e:
            click.echo(
                f"Warning: Could not remove legacy {item['label']} {item['path']}: {e}",
                err=True,
            )
    return skipped


def _safe_content_match(path_a: str, path_b: str) -> bool:
    """Return True if two files have identical content.

    Returns False if either file cannot be read (missing, permissions,
    symlink rejected). Used to verify that a legacy file matches its
    migrated counterpart before deletion, preventing data loss when
    the destination was created independently with different content.
    """
    try:
        content_a = safe_open_read(path_a)
        content_b = safe_open_read(path_b)
        return content_a == content_b
    except (OSError, Exception):
        return False


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("config")
def group() -> None:
    """Manage CLI configuration and file locations.

    Inspect resolved config paths, migrate from legacy file layout,
    and manage CLI settings.
    """


# ---------------------------------------------------------------------------
# show-paths
# ---------------------------------------------------------------------------

_EXPLAIN_SHOW_PATHS = """\
Display all resolved file paths used by the CLI for configuration,
JWT caching, and search checkpoints. Shows which environment variables
are active and whether each path exists on disk.

Useful for debugging path resolution issues, verifying migration status,
and understanding which config files are in effect.

Environment variables that affect paths:
  LC_CONFIG_DIR      Override the base config directory
  LC_CREDS_FILE      Override the config file path directly
  LC_LEGACY_CONFIG   Force legacy flat-file layout (set to "1")
  LC_EPHEMERAL_CREDS Disable all disk persistence
"""
register_explain("config.show-paths", _EXPLAIN_SHOW_PATHS)


@group.command("show-paths")
@pass_context
def show_paths(ctx: click.Context) -> None:
    """Display all resolved config and data file paths."""
    paths = get_all_paths()
    legacy = get_legacy_paths()

    result: dict[str, Any] = {}

    # Config directory
    result["config_dir"] = paths["config_dir"]
    result["config_dir_exists"] = os.path.isdir(paths["config_dir"])

    # Config file
    result["config_file"] = paths["config_file"]
    result["config_file_exists"] = os.path.isfile(paths["config_file"])

    # JWT cache
    result["jwt_cache"] = paths["jwt_cache"]
    result["jwt_cache_exists"] = os.path.isfile(paths["jwt_cache"])

    # Checkpoint directory
    result["checkpoint_dir"] = paths["checkpoint_dir"]
    result["checkpoint_dir_exists"] = os.path.isdir(paths["checkpoint_dir"])

    # Legacy paths
    result["legacy_config_file"] = legacy["config_file"]
    result["legacy_config_exists"] = os.path.isfile(legacy["config_file"])
    result["legacy_jwt_cache"] = legacy["jwt_cache"]
    result["legacy_jwt_cache_exists"] = os.path.isfile(legacy["jwt_cache"])

    # Active mode
    result["legacy_mode_forced"] = is_legacy_mode()

    # Env var overrides
    env_overrides = {}
    for var in ("LC_CONFIG_DIR", "LC_CREDS_FILE", "LC_LEGACY_CONFIG",
                "LC_NO_MIGRATION_WARNING", "LC_EPHEMERAL_CREDS"):
        val = os.environ.get(var)
        if val is not None:
            env_overrides[var] = val
    result["env_overrides"] = env_overrides if env_overrides else "(none)"

    _output(ctx, result)


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------

_EXPLAIN_MIGRATE = """\
Migrate configuration files from legacy locations to the new directory
layout. This command copies files from the old flat-file locations to
the consolidated config directory.

Legacy locations:
  ~/.limacharlie              Config file (YAML)
  ~/.limacharlie_jwt_cache    JWT cache (JSON)

New locations (Unix):
  ~/.limacharlie.d/config.yaml       Config file
  ~/.limacharlie.d/jwt_cache.json    JWT cache
  ~/.limacharlie.d/search_checkpoints/  (already in place)

New locations (Windows):
  %APPDATA%/limacharlie/config.yaml
  %APPDATA%/limacharlie/jwt_cache.json
  %APPDATA%/limacharlie/search_checkpoints/

Options:
  --dry-run      Preview what would be copied without making changes.
  --remove-old   Delete legacy files after successful migration.
  --force        Overwrite files in the new location if they already exist.
"""
register_explain("config.migrate", _EXPLAIN_MIGRATE)


@group.command("migrate")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview migration without making changes.")
@click.option("--remove-old", is_flag=True, default=False,
              help="Delete legacy files after successful migration.")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing files in new location.")
@pass_context
def migrate(ctx: click.Context, dry_run: bool, remove_old: bool, force: bool) -> None:
    """Migrate config files from legacy to new directory layout."""
    if is_legacy_mode():
        click.echo(
            "Error: LC_LEGACY_CONFIG=1 is set. Unset it before migrating.",
            err=True,
        )
        ctx.exit(1)
        return

    config_dir = get_config_dir()
    legacy = get_legacy_paths()
    migrations: list[dict[str, str]] = []

    # Determine what needs migrating
    new_config = os.path.join(config_dir, "config.yaml")
    new_jwt = os.path.join(config_dir, "jwt_cache.json")
    legacy_config = legacy["config_file"]
    legacy_jwt = legacy["jwt_cache"]

    # Track legacy files that can be cleaned up (already migrated or about to be).
    # Each entry includes the destination path so we can verify content before removal.
    stale_legacy: list[dict[str, str]] = []

    if os.path.isfile(legacy_config):
        if not os.path.isfile(new_config) or force:
            migrations.append({
                "source": legacy_config,
                "dest": new_config,
                "label": "config file",
            })
        else:
            click.echo(
                f"Skipping config file: {new_config} already exists (use --force to overwrite)."
            )
            stale_legacy.append({
                "path": legacy_config,
                "dest": new_config,
                "label": "config file",
            })

    if os.path.isfile(legacy_jwt):
        if not os.path.isfile(new_jwt) or force:
            migrations.append({
                "source": legacy_jwt,
                "dest": new_jwt,
                "label": "JWT cache",
            })
        else:
            click.echo(
                f"Skipping JWT cache: {new_jwt} already exists (use --force to overwrite)."
            )
            stale_legacy.append({
                "path": legacy_jwt,
                "dest": new_jwt,
                "label": "JWT cache",
            })

    if not migrations and not stale_legacy:
        click.echo("Nothing to migrate. No legacy files found or all already migrated.")
        return

    # If nothing to copy but stale files exist, handle cleanup.
    if not migrations and stale_legacy:
        if remove_old:
            if dry_run:
                click.echo("Dry run - the following legacy files would be removed:")
                for s in stale_legacy:
                    click.echo(f"  {s['label']}: {s['path']}")
                return
            skipped = _remove_stale_legacy(stale_legacy)
            if skipped:
                click.echo(
                    "Some legacy files could not be removed due to content mismatch. "
                    "Review the warnings above.",
                    err=True,
                )
                ctx.exit(3)
            else:
                click.echo("Legacy files cleaned up.")
            return
        else:
            click.echo(
                "Already migrated. Legacy files still present - use --remove-old to clean up."
            )
            return

    # Preview mode
    if dry_run:
        click.echo("Dry run - the following files would be migrated:")
        for m in migrations:
            click.echo(f"  {m['label']}: {m['source']} -> {m['dest']}")
        if remove_old:
            click.echo("Legacy files would be removed after migration.")
        return

    # Ensure target directory exists with secure permissions
    if not os.path.isdir(config_dir):
        click.echo(f"Creating config directory: {config_dir}")
        secure_makedirs(config_dir)

    # Perform migration
    migrated: list[dict[str, str]] = []
    for m in migrations:
        source = m["source"]
        dest = m["dest"]
        label = m["label"]

        try:
            # Read source content
            content = safe_open_read(source)

            # Write to new location atomically with secure permissions
            atomic_write(dest, content)

            # Verify the copy by reading back
            verify = safe_open_read(dest)
            if verify != content:
                click.echo(
                    f"Error: Verification failed for {label}. "
                    f"Source and destination contents differ. "
                    f"Source file was NOT removed.",
                    err=True,
                )
                ctx.exit(2)
                return

            click.echo(f"Migrated {label}: {source} -> {dest}")
            migrated.append(m)

        except OSError as e:
            click.echo(f"Error migrating {label}: {e}", err=True)
            ctx.exit(2)
            return

    # Optionally remove old files (both freshly migrated and previously stale)
    skipped_removals = 0
    if remove_old:
        # Freshly migrated files were just copied and verified, safe to remove.
        for item in migrated:
            try:
                os.unlink(item["source"])
                click.echo(f"Removed legacy {item['label']}: {item['source']}")
            except OSError as e:
                click.echo(
                    f"Warning: Could not remove legacy {item['label']} {item['source']}: {e}",
                    err=True,
                )
        # Stale legacy files (skipped because dest already existed) need
        # content verification before removal to prevent data loss.
        skipped_removals = _remove_stale_legacy(stale_legacy)

    if not remove_old and (migrated or stale_legacy):
        # Collect all legacy files that still exist
        remaining = []
        for m in migrated:
            if os.path.isfile(m["source"]):
                remaining.append(m["source"])
        for s in stale_legacy:
            if os.path.isfile(s["path"]):
                remaining.append(s["path"])
        if remaining:
            click.echo(
                "Tip: Run with --remove-old to delete legacy files, or remove manually:\n"
                + "".join(f"  {p}\n" for p in remaining)
            )

    if skipped_removals:
        click.echo(
            "Migration complete, but some legacy files could not be removed "
            "due to content mismatch. Review the warnings above.",
            err=True,
        )
        ctx.exit(3)
    else:
        click.echo("Migration complete.")
