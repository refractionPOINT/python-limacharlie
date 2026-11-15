"""Host Posture SDK for LimaCharlie v2.

Wraps the ``ext-host-posture`` extension and the ``host_posture_rule`` hive.

The rules live in the organization's ``host_posture_rule`` hive, one record
per rule (record name = rule id, data = ``{"rule": ..., "scope": ...}``). The
extension serves LimaCharlie's default pack of rules, the per-host results
and the scan and sweep actions over the standard extension request channel.
"""

from __future__ import annotations

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
#: Prefix of the tag holding the digest of the data the pack wrote. The
#: extension computes the digest and hands it out with the pack; clients write
#: it as given and never compute one. The extension compares it with the
#: record to tell an edited rule from an unedited one.
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
                platforms, digest, record: {rule, scope}}]}``.
        """
        return self._request("default_pack")

    def pack_status(self) -> dict[str, Any]:
        """How each rule of the org's hive compares with the default pack.

        Returns:
            dict: ``{pack_version, rules: [{id, pack_version_of_rule,
                installed_version, state}]}`` with ``state`` one of ``new``,
                ``update_available``, ``current``, ``edited``, ``org_newer``.
        """
        return self._request("pack_status")

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

        Records are written with the caller's own permissions. Every decision
        comes from the extension's ``pack_status``; this client computes no
        digest. Nothing is overwritten silently:

        * ``new``: the record is created (create-only: a record created in the
          meantime is not replaced; on that conflict ``pack_status`` is read
          again and the rule's new state is reported as ``state_now``), with the tags ``lc:default-pack`` and
          ``lc:pack-sha256:<digest>``, the digest as ``default_pack`` returned it.
        * ``update_available``: replaced only with ``update`` (or ``force``).
          The replacement is conditional on the etag that was read and keeps
          the record's enabled state, expiry, other tags, ``ui_actions`` and
          own comment.
        * ``edited`` (including a record with no digest tag) and ``org_newer``
          (unedited, with a higher version than the pack's): replaced only
          with ``force``.
        * ``current``: nothing to do.

        Args:
            ids: Install only these rule ids (default: the whole pack).
            update: Replace unedited rules with a newer pack version.
            force: Also replace ``edited`` and ``org_newer`` rules (implies ``update``).
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
        states = {
            str(r.get("id")): r
            for r in (self.pack_status().get("rules") or []) if isinstance(r, dict)
        }

        hive = self._rules()
        comment = f"{PACK_COMMENT_PREFIX} {pack_version}"
        result: dict[str, Any] = {
            "pack_version": pack_version, "dry_run": dry_run,
            "created": [], "updated": [], "skipped": [], "failed": [],
        }
        for rule_id in selected:
            try:
                self._install_one(
                    hive, result, by_id[rule_id], states.get(rule_id), comment,
                    update=update, force=force, enabled=enabled, dry_run=dry_run,
                )
            except LimaCharlieError as exc:
                result["failed"].append({"id": rule_id, "error": exc.raw_message})
        return result

    def _state_now(self, rule_id: str) -> str | None:
        """Re-read ``pack_status`` after a write conflict and return the rule's new state.

        Returns:
            str | None: The state the extension reports now, or None when it
                could not be read.
        """
        try:
            for item in self.pack_status().get("rules") or []:
                if isinstance(item, dict) and str(item.get("id")) == rule_id:
                    return item.get("state")
        except LimaCharlieError:
            return None
        return None

    def _install_one(
        self,
        hive: Hive,
        result: dict[str, Any],
        entry: dict[str, Any],
        status: dict[str, Any] | None,
        comment: str,
        *,
        update: bool,
        force: bool,
        enabled: bool,
        dry_run: bool,
    ) -> None:
        rule_id = str(entry["id"])
        data = entry["record"]
        digest = entry.get("digest")
        if not isinstance(digest, str) or not digest:
            raise ValidationError("the pack entry carries no digest")
        digest_tag = PACK_DIGEST_TAG_PREFIX + digest
        pack_rule_version = entry.get("version")
        if status is None:
            raise ValidationError("the extension reported no status for this rule")
        state = status.get("state")
        skip = {
            "id": rule_id, "state": state,
            "installed_version": status.get("installed_version"), "pack_version": pack_rule_version,
        }

        if state == "new":
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
                        **skip, "state_now": self._state_now(rule_id),
                        "reason": "the record was created while installing, so it was not written: "
                                  "see state_now, and run the command again",
                    })
                    return
                raise
            result["created"].append(item)
            return

        if state == "current":
            result["skipped"].append({**skip, "reason": "already up to date"})
            return
        if state == "update_available":
            if not update:
                result["skipped"].append({
                    **skip, "update_available": True,
                    "reason": "a newer version is in the pack: pass --update to replace the unedited rule",
                })
                return
        elif state in ("edited", "org_newer"):
            if not force:
                why = ("the rule was edited" if state == "edited"
                       else "the rule is newer than the pack's")
                result["skipped"].append({**skip, "reason": f"{why}: pass --force to replace it"})
                return
        else:
            raise ValidationError(f"unknown pack state {state!r}")

        try:
            existing = hive.get(rule_id)
        except ApiError as exc:
            if is_record_not_found(exc):
                result["skipped"].append({**skip, "reason": "the record was deleted while installing: run the command again"})
                return
            raise
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
        item = {
            "id": rule_id, "state": state,
            "from_version": status.get("installed_version"), "to_version": pack_rule_version,
        }
        if dry_run:
            result["updated"].append(item)
            return
        try:
            hive.set(record)
        except ApiError as exc:
            if _is_conflict(exc):
                result["skipped"].append({
                    **skip, "state_now": self._state_now(rule_id),
                    "reason": "the record changed while updating, so it was not replaced: "
                              "see state_now, and run the command again",
                })
                return
            raise
        result["updated"].append(item)
