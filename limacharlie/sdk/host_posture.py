"""Host Posture SDK for LimaCharlie v2.

Wraps the ``ext-host-posture`` extension and the ``host_posture_rule`` hive.

The rules live in the organization's ``host_posture_rule`` hive, one record
per rule (record name = rule id, data = ``{"rule": ..., "scope": ...}``). The
extension serves LimaCharlie's default pack of rules, the per-host results
and the scan and sweep actions over the standard extension request channel.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization

from ..errors import ApiError, LimaCharlieError, ValidationError
from .extensions import Extensions
from .hive import Hive, HiveRecord, is_record_not_found

EXTENSION_NAME = "ext-host-posture"
HIVE_NAME = "host_posture_rule"

#: Tag on every record written by :meth:`HostPosture.install_default_pack`.
DEFAULT_PACK_TAG = "lc:default-pack"
#: Prefix of the tag holding the digest of the data the pack wrote. A record
#: whose stored data still hashes to it has not been edited since.
PACK_DIGEST_TAG_PREFIX = "lc:pack-sha256:"
#: Start of the comment of a record the pack wrote.
PACK_COMMENT_PREFIX = "LimaCharlie default pack"

# Sent as the etag of a write that must create a record. The hive ignores the
# etag when no record exists and refuses the write when one does (it matches no
# stored etag), so a record created between our check and the write is never
# overwritten.
_CREATE_ONLY_ETAG = "create-only: the record must not exist"

STATUSES = ("pass", "fail", "error", "not_applicable", "unsupported")
SEVERITIES = ("critical", "high", "medium", "low", "info")


def record_digest(data: dict[str, Any]) -> str:
    """Digest of a rule record's data, as stored in the pack digest tag.

    Args:
        data: The record data (``{"rule": ..., "scope": ...}``).

    Returns:
        str: First 32 hex characters of the SHA-256 of the canonical JSON.
    """
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _digest_tag(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        if tag.startswith(PACK_DIGEST_TAG_PREFIX):
            return tag[len(PACK_DIGEST_TAG_PREFIX):]
    return None


def _rule_version(data: Any) -> int | None:
    rule = data.get("rule") if isinstance(data, dict) else None
    version = rule.get("version") if isinstance(rule, dict) else None
    return version if isinstance(version, int) and not isinstance(version, bool) else None


def _is_conflict(exc: Exception) -> bool:
    return isinstance(exc, ApiError) and (exc.status_code == 409 or "ETAG_MISMATCH" in str(exc))


def _paging(data: dict[str, Any], cursor: str | None, limit: int | None) -> None:
    if cursor:
        data["cursor"] = cursor
    if limit is not None:
        data["limit"] = limit


class HostPosture:
    """Host Posture client for LimaCharlie."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def oid(self) -> str:
        return self._org.oid

    def _request(self, action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return Extensions(self._org).request(EXTENSION_NAME, action, data=data or {}, unwrap=True)

    def _rules(self) -> Hive:
        return Hive(self._org, HIVE_NAME)

    # ------------------------------------------------------------------
    # Extension requests
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Build identity, pack version and rule counts of the extension."""
        return self._request("status")

    def default_pack(self) -> dict[str, Any]:
        """LimaCharlie's default pack.

        Returns:
            dict: ``{pack_version, rules: [{id, version, title, severity,
                platforms, record: {rule, scope}}]}``.
        """
        return self._request("default_pack")

    def query_summary(self) -> dict[str, Any]:
        """Org-wide counts: hosts assessed and failing, results by status, and so on."""
        return self._request("query_summary")

    def query_hosts(
        self,
        *,
        platform: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """One page of hosts with their failing counts (server-side filters)."""
        data: dict[str, Any] = {}
        for key, value in (("platform", platform), ("severity", severity), ("status", status), ("search", search)):
            if value:
                data[key] = value
        _paging(data, cursor, limit)
        return self._request("query_hosts", data)

    def query_host(self, sid: str) -> dict[str, Any]:
        """Every rule result of one host, with evidence."""
        return self._request("query_host", {"sid": sid})

    def query_rules(
        self,
        *,
        severity: str | None = None,
        platform: str | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """One page of rules with their assessed, failing and error host counts."""
        data: dict[str, Any] = {}
        for key, value in (("severity", severity), ("platform", platform), ("search", search)):
            if value:
                data[key] = value
        _paging(data, cursor, limit)
        return self._request("query_rules", data)

    def query_rule_hosts(
        self,
        rule_id: str,
        status: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """One page of the hosts that have ``status`` for a rule."""
        if status not in ("fail", "error", "pass", "not_applicable"):
            raise ValidationError("status must be one of fail, error, pass, not_applicable")
        data: dict[str, Any] = {"rule_id": rule_id, "status": status}
        _paging(data, cursor, limit)
        return self._request("query_rule_hosts", data)

    def query_standards(self, framework: str | None = None) -> dict[str, Any]:
        """How hosts do against each standard control."""
        return self._request("query_standards", {"framework": framework} if framework else {})

    def scan(self, sid: str) -> dict[str, Any]:
        """Scan one online sensor now.

        Returns:
            dict: ``{job_id, sid, platform, tasks_issued}``.
        """
        return self._request("scan", {"sid": sid})

    def sweep(self, tags: list[str] | None = None) -> dict[str, Any]:
        """Sweep sensors now with reliable tasking, which reaches offline sensors.

        Args:
            tags: Only sensors carrying at least one of these tags. Default: all.

        Returns:
            dict: ``{job_id, sensors_tasked}``.
        """
        return self._request("sweep", {"tags": list(tags)} if tags else {})

    # ------------------------------------------------------------------
    # Default pack installation
    # ------------------------------------------------------------------

    def install_default_pack(
        self,
        ids: list[str] | None = None,
        *,
        update: bool = False,
        force: bool = False,
        enabled: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Write LimaCharlie's default pack into the org's ``host_posture_rule`` hive.

        Records are written with the caller's own permissions. Nothing is
        overwritten silently:

        * A rule that is not in the hive is created (create-only: a record
          created in the meantime is not replaced).
        * A rule that exists is skipped, unless ``update`` is set and the
          record is one this pack wrote that nobody edited since (its stored
          data still matches the digest tag the install left) and the pack's
          version is newer. The replacement is conditional on the etag that
          was read, and keeps the record's enabled state, expiry, other tags,
          ui_actions and own comment.
        * A rule the org edited, a record this pack did not write, or one that
          is as new as or newer than the pack's is replaced only with
          ``force``.

        Args:
            ids: Install only these rule ids (default: the whole pack).
            update: Replace older, unedited pack rules.
            force: Replace any existing rule that differs from the pack (implies ``update``).
            enabled: State of rules that are created.
            dry_run: Report what would happen and write nothing.

        Returns:
            dict: ``pack_version``, ``dry_run`` and the lists ``created``,
                ``updated``, ``skipped`` (each with a ``reason``) and ``failed``.

        Raises:
            ValidationError: If a requested id is not in the pack or the
                extension returned no pack.
        """
        update = update or force
        pack = self.default_pack()
        entries = pack.get("rules")
        if not isinstance(entries, list) or not entries:
            raise ValidationError("the extension returned no default pack")
        pack_version = pack.get("pack_version")
        by_id = {str(e.get("id")): e for e in entries if isinstance(e, dict) and e.get("record")}
        if ids:
            missing = [i for i in ids if i not in by_id]
            if missing:
                raise ValidationError(
                    f"not in the default pack: {', '.join(missing)}. Available: {', '.join(sorted(by_id))}"
                )
            selected = list(dict.fromkeys(ids))
        else:
            selected = sorted(by_id)

        hive = self._rules()
        comment = f"{PACK_COMMENT_PREFIX} {pack_version}"
        result: dict[str, Any] = {
            "pack_version": pack_version, "dry_run": dry_run,
            "created": [], "updated": [], "skipped": [], "failed": [],
        }
        for rule_id in selected:
            entry = by_id[rule_id]
            data = entry["record"]
            pack_rule_version = entry.get("version", _rule_version(data))
            try:
                self._install_one(
                    hive, result, rule_id, data, pack_rule_version, comment,
                    update=update, force=force, enabled=enabled, dry_run=dry_run,
                )
            except LimaCharlieError as exc:
                result["failed"].append({"id": rule_id, "error": exc.raw_message})
        return result

    def _install_one(
        self,
        hive: Hive,
        result: dict[str, Any],
        rule_id: str,
        data: dict[str, Any],
        pack_rule_version: Any,
        comment: str,
        *,
        update: bool,
        force: bool,
        enabled: bool,
        dry_run: bool,
    ) -> None:
        digest_tag = PACK_DIGEST_TAG_PREFIX + record_digest(data)
        try:
            existing = hive.get(rule_id)
        except ApiError as exc:
            if not is_record_not_found(exc):
                raise
            existing = None

        if existing is None:
            record = HiveRecord(
                name=rule_id, data=data, etag=_CREATE_ONLY_ETAG,
                enabled=enabled, tags=[DEFAULT_PACK_TAG, digest_tag], comment=comment,
            )
            item = {"id": rule_id, "version": pack_rule_version, "enabled": enabled}
            if dry_run:
                result["created"].append(item)
                return
            try:
                hive.set(record)
            except ApiError as exc:
                if _is_conflict(exc):
                    result["skipped"].append({
                        "id": rule_id, "reason": "the record was created while installing: run the command again",
                    })
                    return
                raise
            result["created"].append(item)
            return

        installed_version = _rule_version(existing.data)
        skip = {"id": rule_id, "installed_version": installed_version, "pack_version": pack_rule_version}
        if existing.data == data:
            result["skipped"].append({**skip, "reason": "already up to date"})
            return
        if not update:
            newer = isinstance(installed_version, int) and isinstance(pack_rule_version, int) \
                and pack_rule_version > installed_version
            result["skipped"].append({
                **skip, "update_available": newer,
                "reason": "the rule already exists: pass --update to replace an unedited older version, "
                          "or --force to replace it whatever it holds",
            })
            return
        if not force:
            stored_digest = _digest_tag(existing.tags)
            if stored_digest is None or stored_digest != record_digest(existing.data or {}):
                result["skipped"].append({
                    **skip, "reason": "the rule was edited, or was not installed from the pack: "
                                      "pass --force to replace it",
                })
                return
            if not (isinstance(installed_version, int) and isinstance(pack_rule_version, int)
                    and pack_rule_version > installed_version):
                result["skipped"].append({**skip, "reason": "the installed version is not older than the pack's"})
                return

        tags = [t for t in (existing.tags or []) if not t.startswith(PACK_DIGEST_TAG_PREFIX)]
        if DEFAULT_PACK_TAG not in tags:
            tags.append(DEFAULT_PACK_TAG)
        tags.append(digest_tag)
        keep_comment = existing.comment and not existing.comment.startswith(PACK_COMMENT_PREFIX)
        record = HiveRecord(
            name=rule_id, data=data, etag=existing.etag,
            enabled=bool(existing.enabled), expiry=existing.expiry, tags=tags,
            comment=existing.comment if keep_comment else comment, ui_actions=existing.ui_actions,
        )
        item = {"id": rule_id, "from_version": installed_version, "to_version": pack_rule_version}
        if dry_run:
            result["updated"].append(item)
            return
        try:
            hive.set(record)
        except ApiError as exc:
            if _is_conflict(exc):
                result["skipped"].append({
                    **skip, "reason": "the record changed while updating, so it was not replaced: run the command again",
                })
                return
            raise
        result["updated"].append(item)
