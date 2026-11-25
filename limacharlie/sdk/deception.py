"""Deception SDK for LimaCharlie v2.

Wraps the ``ext-deception`` extension: decoys planted on endpoints through the
sensor, and drops (sensorless tokens: a link, a QR code, a host name, a
document) put anywhere an intruder would look.

Everything that decides what alerts lives in one record, the ``ext-deception``
record of the ``extension_config`` hive (policies, templates, reader
allowlists, declared drops). The extension serves the rest over the standard
extension request channel: plan and deploy, the decoys and hosts, coverage and
test-fire, the recorded hits and readers, the drops, and the uninstall.

The extension validates every request and every configuration, so this client
validates nothing itself: it builds the request from the arguments given and
leaves out the ones that are not.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization

from ..errors import ValidationError
from .extensions import Extensions
from .hive import Hive, HiveRecord

EXTENSION_NAME = "ext-deception"
#: The configuration record: the ``extension_config`` record named after the extension.
CONFIG_HIVE = "extension_config"
CONFIG_RECORD = EXTENSION_NAME

# Sent as the etag of a write that must create the record. The hive ignores the
# etag when no record exists and refuses the write when one does (it matches no
# stored etag), so a record created between the existence check and the write
# is never overwritten.
_CREATE_ONLY_ETAG = "create-only: the record must not exist"

LAYERS = ("read", "modify", "delete", "use")
DROP_FORMS = ("url", "qr", "hostname", "document")
DOCUMENT_FORMATS = ("docx", "svg")
PLATFORMS = ("windows", "linux", "macos")


def _put(data: dict[str, Any], key: str, value: Any) -> None:
    """Set ``key`` when ``value`` was given: not None, not False, not an empty list."""
    if value is None or value is False:
        return
    if isinstance(value, (list, tuple)):
        if not value:
            return
        value = list(value)
    data[key] = value


def _paging(data: dict[str, Any], page_token: str | None, page_size: int | None) -> None:
    _put(data, "page_token", page_token or None)
    _put(data, "page_size", page_size)


class Deception:
    """Deception (``ext-deception``) client for LimaCharlie."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def oid(self) -> str:
        return self._org.oid

    def _request(self, action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return Extensions(self._org).request(EXTENSION_NAME, action, data=data or {}, unwrap=True)

    def _config_hive(self) -> Hive:
        return Hive(self._org, CONFIG_HIVE)

    # ------------------------------------------------------------------
    # Configuration record
    # ------------------------------------------------------------------

    def get_config(self) -> HiveRecord:
        """Read the configuration record (data, metadata and etag).

        Returns:
            HiveRecord: The ``ext-deception`` record of ``extension_config``.
        """
        return self._config_hive().get(CONFIG_RECORD)

    def set_config(
        self,
        config: dict[str, Any],
        *,
        etag: str | None = None,
        enabled: bool | None = None,
        usr_mtd: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write the configuration record.

        The extension validates the whole configuration when it is saved.

        * An existing record keeps its metadata (enabled state, tags, comment,
          expiry) unless ``enabled`` or ``usr_mtd`` is given.
        * A record that does not exist yet is created enabled unless
          ``enabled`` is False (or ``usr_mtd`` says otherwise): a disabled
          record gives the extension an empty configuration. Creation is
          conditional, so a record created in the meantime is not replaced.

        Args:
            config: The configuration (the record's ``data``).
            etag: Write only if the stored record still has this etag
                (compare-and-set; from :meth:`get_config`).
            enabled: Set the record's enabled state.
            usr_mtd: A whole metadata block, as a record read with
                :meth:`get_config` carries it. It replaces the stored metadata;
                a block without ``enabled`` stores the record disabled, as the
                hive does. ``enabled`` overrides its ``enabled``.

        Returns:
            dict: The hive's answer.

        Raises:
            ValidationError: If ``etag`` is given and the record does not
                exist (it was deleted since it was read).
            ApiError: If the hive refuses the write, for example on an etag
                mismatch.
        """
        hive = self._config_hive()
        record = HiveRecord(name=CONFIG_RECORD, data=config, etag=etag)
        if usr_mtd is not None:
            record.expiry = usr_mtd.get("expiry")
            record.enabled = bool(usr_mtd.get("enabled", False))
            record.tags = usr_mtd.get("tags")
            record.comment = usr_mtd.get("comment")
            record.ui_actions = usr_mtd.get("ui_actions")
            if enabled is not None:
                record.enabled = enabled
            return hive.set(record)

        # Reading the stored metadata takes ext.conf.get (or ext.conf.get.mtd).
        exists = hive.merge_current_metadata(record)
        if not exists:
            if etag:
                raise ValidationError(
                    f"the {CONFIG_RECORD} record no longer exists, so the etag cannot match: "
                    "read it again, or write it without an etag to create it"
                )
            record.etag = _CREATE_ONLY_ETAG
            record.enabled = True if enabled is None else enabled
            return hive.set(record)
        if enabled is None:
            # Data only: the hive keeps the stored metadata as it is.
            record.enabled = record.tags = record.comment = record.expiry = record.ui_actions = None
        else:
            record.enabled = enabled
        return hive.set(record)

    def enable_config(self) -> dict[str, Any]:
        """Enable the configuration record (a disabled record reads as empty).

        Returns:
            dict: The hive's answer.
        """
        hive = self._config_hive()
        record = hive.get_metadata(CONFIG_RECORD)
        record.enabled = True
        return hive.set(record)

    # ------------------------------------------------------------------
    # Plan, deploy and rollout
    # ------------------------------------------------------------------

    def plan(
        self,
        *,
        policy: str | None = None,
        sid: str | None = None,
        draft_policy: dict[str, Any] | None = None,
        draft_templates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Show what deploy would do (read-only).

        Args:
            policy: Limit to one policy.
            sid: Limit to one sensor.
            draft_policy: Plan an unsaved policy record instead (not with
                ``policy`` or ``sid``).
            draft_templates: With ``draft_policy``: template records the save
                would add.

        Returns:
            dict: ``plan``, ``pack``, ``watch_budget``, ``sources``,
                ``reader_lookups``, ``warnings``, ``drops``, ``isolation_cap``
                and, with a draft, ``draft``.
        """
        data: dict[str, Any] = {}
        _put(data, "policy", policy)
        _put(data, "sid", sid)
        _put(data, "draft_policy", draft_policy)
        _put(data, "draft_templates", draft_templates)
        return self._request("plan", data)

    def deploy(
        self,
        *,
        policy: str | None = None,
        sid: str | None = None,
        apply_pack: list[str] | None = None,
        apply_all_pack: bool = False,
    ) -> dict[str, Any]:
        """Apply the configuration: rules, other extensions' entries, decoys.

        Args:
            policy: Limit to one policy.
            sid: Limit to one sensor.
            apply_pack: Shipped detection rules to overwrite with the current
                shipped version.
            apply_all_pack: Overwrite every shipped rule.

        Returns:
            dict: ``ops`` and what the deploy wrote.
        """
        data: dict[str, Any] = {}
        _put(data, "policy", policy)
        _put(data, "sid", sid)
        _put(data, "apply_pack", apply_pack)
        _put(data, "apply_all_pack", apply_all_pack)
        return self._request("deploy", data)

    def rollout_status(self) -> dict[str, Any]:
        """Where the rollout to the sensors stands; cheap enough to poll."""
        return self._request("rollout_status")

    def restore_rules(self, rules: list[str]) -> dict[str, Any]:
        """Put shipped detection rules back as shipped, enabled, without a rollout.

        Args:
            rules: Shipped rule names, for example ``deception-respond``.

        Returns:
            dict: ``rules``: one result per rule (``name``, ``restored``,
                ``enabled``, ``error`` and ``code``).
        """
        return self._request("restore_rules", {"rules": list(rules)})

    def list_kinds(self) -> dict[str, Any]:
        """Decoy kinds with their spec schemas, the template library and the benign readers."""
        return self._request("list_kinds")

    # ------------------------------------------------------------------
    # Decoys and hosts
    # ------------------------------------------------------------------

    def list_decoys(
        self,
        *,
        policy: str | None = None,
        sid: str | None = None,
        states: list[str] | None = None,
        include_test: bool = False,
        template: str | None = None,
        kind: str | None = None,
        text: str | None = None,
        cause: str | None = None,
        summary: bool = False,
        include_superseded: bool = False,
        exclude_skipped: bool = False,
        page_token: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """One page of decoys (no secret value is ever returned).

        Args:
            policy: Only this policy's decoys.
            sid: Only this sensor's decoys.
            states: Any of planned, placed, verified, retired, gone, failed.
            include_test: Also list test-fire decoys.
            template: Only this template's decoys.
            kind: Only this kind's decoys.
            text: Substring of path, template, policy, hostname or sensor id.
            cause: Only failed decoys of this failure cause.
            summary: Also count every match before paging.
            include_superseded: Also list earlier failed attempts.
            exclude_skipped: Leave out decoys skipped on purpose.
            page_token: From the previous page.
            page_size: Up to 500 (default 100).

        Returns:
            dict: ``instances``, ``next_page_token`` and, with ``summary``, ``summary``.
        """
        data: dict[str, Any] = {}
        for key, value in (
            ("policy", policy), ("sid", sid), ("states", states), ("include_test", include_test),
            ("template", template), ("kind", kind), ("text", text), ("cause", cause),
            ("summary", summary), ("include_superseded", include_superseded),
            ("exclude_skipped", exclude_skipped),
        ):
            _put(data, key, value)
        _paging(data, page_token, page_size)
        return self._request("list", data)

    def list_hosts(
        self,
        *,
        policy: str | None = None,
        template: str | None = None,
        text: str | None = None,
        states: list[str] | None = None,
        include_test: bool = False,
        status: str | None = None,
        include_superseded: bool = False,
        sid: str | None = None,
        summary: bool = False,
        sort: str | None = None,
        include_deleted: bool = False,
        page_token: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """One page of targeted sensors and sensors with decoys, with their status.

        Args:
            policy: Only this policy.
            template: Only sensors holding this template's decoy.
            text: Substring of hostname, sensor id, path, template or policy.
            states: Decoy states that count (default planned, placed, verified, failed).
            include_test: Also count test-fire decoys.
            status: Only sensors of this status (protected, partial, pending,
                failed, skipped, none, no_decoy, not_reached, restricted).
            include_superseded: Also count earlier failed attempts.
            sid: Only this sensor.
            summary: Also count every matching host by status.
            sort: ``sid`` (default) or ``problems``.
            include_deleted: Also list sensors removed from the platform.
            page_token: From the previous page.
            page_size: Up to 500 (default 100).

        Returns:
            dict: ``hosts``, ``next_page_token``, ``targets`` and, with
                ``summary``, ``summary``.
        """
        data: dict[str, Any] = {}
        for key, value in (
            ("policy", policy), ("template", template), ("text", text), ("states", states),
            ("include_test", include_test), ("status", status),
            ("include_superseded", include_superseded), ("sid", sid), ("summary", summary),
            ("sort", sort), ("include_deleted", include_deleted),
        ):
            _put(data, key, value)
        _paging(data, page_token, page_size)
        return self._request("list_hosts", data)

    def _decoy_op(
        self,
        action: str,
        policy: str | None,
        sid: str | None,
        instance_ids: list[str] | None,
        template: str | None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        _put(data, "policy", policy)
        _put(data, "sid", sid)
        _put(data, "instance_ids", instance_ids)
        _put(data, "template", template)
        return self._request(action, data)

    def verify(
        self,
        *,
        policy: str | None = None,
        sid: str | None = None,
        instance_ids: list[str] | None = None,
        template: str | None = None,
    ) -> dict[str, Any]:
        """Re-check that decoys are still in place (scopes combine).

        Args:
            policy: The live decoys of this policy.
            sid: The live decoys of this sensor.
            instance_ids: These decoys.
            template: The live decoys of this template.

        Returns:
            dict: ``started``, ``skipped``, ``operations``, ``issues`` and
                ``more`` (true: call again to continue).
        """
        return self._decoy_op("verify", policy, sid, instance_ids, template)

    def rotate(
        self,
        *,
        policy: str | None = None,
        sid: str | None = None,
        instance_ids: list[str] | None = None,
        template: str | None = None,
    ) -> dict[str, Any]:
        """Retire decoys and plant replacements with new secrets at new paths.

        Args:
            policy: The decoys of this policy.
            sid: The decoys of this sensor.
            instance_ids: These decoys.
            template: The decoys of this template.

        Returns:
            dict: As :meth:`verify`.
        """
        return self._decoy_op("rotate", policy, sid, instance_ids, template)

    def remove(
        self,
        *,
        policy: str | None = None,
        sid: str | None = None,
        instance_ids: list[str] | None = None,
        template: str | None = None,
    ) -> dict[str, Any]:
        """Remove decoys from their hosts, after checking each file is still the one planted.

        Args:
            policy: The decoys of this policy.
            sid: The decoys of this sensor.
            instance_ids: These decoys.
            template: The decoys of this template.

        Returns:
            dict: As :meth:`verify`.
        """
        return self._decoy_op("remove", policy, sid, instance_ids, template)

    # ------------------------------------------------------------------
    # Coverage and test-fire
    # ------------------------------------------------------------------

    def coverage(self, policy: str | None = None) -> dict[str, Any]:
        """What is covered, unavailable, blind or broken.

        Args:
            policy: Limit to one policy.

        Returns:
            dict: ``coverage``, ``sources``, ``metering``, ``drops`` and, for
                the whole org, ``sensors`` and ``alert_paths``.
        """
        data: dict[str, Any] = {}
        _put(data, "policy", policy)
        return self._request("coverage", data)

    def test_fire(self, *, policy: str | None = None, drop_id: str | None = None) -> dict[str, Any]:
        """Fire the test-only decoys, one run per alert path, or one drop.

        Args:
            policy: Only this policy's alert paths.
            drop_id: Fire this drop instead (not with ``policy``).

        Returns:
            dict: ``runs`` and ``issues``.
        """
        data: dict[str, Any] = {}
        _put(data, "policy", policy)
        _put(data, "drop_id", drop_id)
        return self._request("test_fire", data)

    def list_test_runs(
        self,
        *,
        policy: str | None = None,
        template: str | None = None,
        layer: str | None = None,
        state: str | None = None,
        page_token: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """One page of recent test-fire runs, newest first.

        Args:
            policy: Only this policy's runs.
            template: Only this template's runs.
            layer: read, modify, delete or use.
            state: pending or finished.
            page_token: From the previous page.
            page_size: Up to 500 (default 100).

        Returns:
            dict: ``runs`` and ``next_page_token``.
        """
        data: dict[str, Any] = {}
        for key, value in (("policy", policy), ("template", template), ("layer", layer), ("state", state)):
            _put(data, key, value)
        _paging(data, page_token, page_size)
        return self._request("list_test_runs", data)

    def list_test_paths(
        self,
        *,
        policy: str | None = None,
        template: str | None = None,
        state: str | None = None,
        page_token: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """One page of alert paths with their latest test result.

        Args:
            policy: Only this policy's paths.
            template: Only this template's paths.
            state: passed, failed, untested, not_testable or testable.
            page_token: From the previous page.
            page_size: Up to 500 (default 100).

        Returns:
            dict: ``paths``, ``next_page_token``, ``counts``, ``proven`` and
                ``not_proven``.
        """
        data: dict[str, Any] = {}
        for key, value in (("policy", policy), ("template", template), ("state", state)):
            _put(data, key, value)
        _paging(data, page_token, page_size)
        return self._request("list_test_paths", data)

    # ------------------------------------------------------------------
    # Hits and readers
    # ------------------------------------------------------------------

    def list_hits(
        self,
        *,
        since: int | None = None,
        until: int | None = None,
        layer: str | None = None,
        template: str | None = None,
        policy: str | None = None,
        sid: str | None = None,
        classification: str | None = None,
        event_types: list[str] | None = None,
        drop_id: str | None = None,
        include_test: bool = False,
        mode: str | None = None,
        group: bool = False,
        group_id: str | None = None,
        auto_response_outcomes: list[str] | None = None,
        case_group_key: str | None = None,
        hit_id: str | None = None,
        page_token: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """One page of recorded hits (or hit groups), newest first.

        Args:
            since: Only hits at or after this time (Unix seconds).
            until: Only hits before this time (Unix seconds).
            layer: read, modify, delete or use.
            template: Only hits on this template's decoys.
            policy: Only this policy's hits.
            sid: Only this sensor's hits.
            classification: For example ai-agent-likely or link-preview-likely.
            event_types: Any of deception_hit, deception_drop_hit,
                deception_coverage_warning (default: every type).
            drop_id: Only this drop's hits.
            include_test: Also list synthetic test-fire hits.
            mode: observe, live or context.
            group: List hit groups instead of hits.
            group_id: Only the hits of this group.
            auto_response_outcomes: Only hits whose automatic response has one
                of these outcomes (done, capped, failed, refused, pending,
                skipped, unreported, not_isolated).
            case_group_key: Only the hits of this incident.
            hit_id: Only this hit (the other filters are not applied).
            page_token: From the previous page.
            page_size: Up to 500 (default 100).

        Returns:
            dict: ``hits`` (or ``groups``), ``next_page_token`` and, on the
                first page, ``total`` and ``total_capped``.
        """
        data: dict[str, Any] = {}
        for key, value in (
            ("since", since), ("until", until), ("layer", layer), ("template", template),
            ("policy", policy), ("sid", sid), ("classification", classification),
            ("drop_id", drop_id), ("include_test", include_test), ("mode", mode),
            ("group", group), ("group_id", group_id), ("case_group_key", case_group_key),
            ("hit_id", hit_id),
        ):
            _put(data, key, value)
        if event_types:
            if len(event_types) == 1:
                data["event_type"] = event_types[0]
            else:
                data["event_types"] = list(event_types)
        if auto_response_outcomes:
            data["auto_response_outcome"] = ",".join(auto_response_outcomes)
        _paging(data, page_token, page_size)
        return self._request("list_hits", data)

    def list_readers(
        self,
        *,
        days: int | None = None,
        policy: str | None = None,
        template: str | None = None,
        platform: str | None = None,
        page_token: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """Who reads the decoys, and the allowlist entry that would approve each reader.

        Args:
            days: The window, ending now (default 30, at most 90).
            policy: Only this policy's decoys.
            template: Only this template's decoys.
            platform: windows, linux or macos.
            page_token: From the previous page.
            page_size: Up to 500 (default 100).

        Returns:
            dict: ``readers``, ``unknown_process``, ``window``, ``lookups`` and
                ``next_page_token``.
        """
        data: dict[str, Any] = {}
        for key, value in (("days", days), ("policy", policy), ("template", template), ("platform", platform)):
            _put(data, key, value)
        _paging(data, page_token, page_size)
        return self._request("list_readers", data)

    # ------------------------------------------------------------------
    # Drops
    # ------------------------------------------------------------------

    def create_drop(
        self,
        form: str,
        label: str,
        *,
        memo: str | None = None,
        format: str | None = None,
        domain: str | None = None,
        mode: str | None = None,
        observe_until: str | None = None,
        redirect_url: str | None = None,
        document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a drop: a token with no sensor behind it.

        Args:
            form: url, qr, hostname or document.
            label: Where the drop is put (shown as the case's host).
            memo: Notes for the analyst.
            format: Document drops: docx or svg.
            domain: One of the deployment's decoy domains.
            mode: live (default) or observe.
            observe_until: RFC 3339 time the drop goes live by itself.
            redirect_url: url and qr drops: where a visitor is sent after the hit.
            document: Document drops: file_name, title, lines, link_text, author.

        Returns:
            dict: ``drop`` and ``paste`` (what to put where it goes: the one
                answer that carries a secret value).
        """
        data: dict[str, Any] = {"form": form, "label": label}
        for key, value in (
            ("memo", memo), ("format", format), ("domain", domain), ("mode", mode),
            ("observe_until", observe_until), ("redirect_url", redirect_url),
        ):
            _put(data, key, value)
        if document is not None:
            data["document"] = document
        return self._request("create_drop", data)

    def list_drops(
        self,
        *,
        forms: list[str] | None = None,
        states: list[str] | None = None,
        text: str | None = None,
        include_test: bool = False,
        name: str | None = None,
        managed_by: str | None = None,
        last_hit: str | None = None,
        last_hit_since: str | None = None,
        sort: str | None = None,
        page_token: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """One page of drops, without their secret values.

        Args:
            forms: Any of url, qr, hostname, document.
            states: Any of active, disabled, deleted (default active and disabled).
            text: Substring of the label or memo.
            include_test: Also list the hidden test drops.
            name: Only the drop of this configuration name.
            managed_by: config or api.
            last_hit: never, since or not_since.
            last_hit_since: RFC 3339 time, for ``last_hit`` since and not_since.
            sort: created (default) or last_hit.
            page_token: From the previous page.
            page_size: Up to 500 (default 100).

        Returns:
            dict: ``drops``, ``next_page_token`` and, on the first page,
                ``total`` and ``total_capped``.
        """
        data: dict[str, Any] = {}
        for key, value in (
            ("forms", forms), ("states", states), ("text", text), ("include_test", include_test),
            ("name", name), ("managed_by", managed_by), ("last_hit", last_hit),
            ("last_hit_since", last_hit_since), ("sort", sort),
        ):
            _put(data, key, value)
        _paging(data, page_token, page_size)
        return self._request("list_drops", data)

    def get_drop(self, *, drop_id: str | None = None, name: str | None = None) -> dict[str, Any]:
        """One drop, with what to paste.

        Args:
            drop_id: The drop's id.
            name: Or the configuration name of a declared drop.

        Returns:
            dict: ``drop`` and ``paste`` (a deleted drop has none).

        Raises:
            ValidationError: Unless exactly one of ``drop_id`` and ``name`` is given.
        """
        if bool(drop_id) == bool(name):
            raise ValidationError("give exactly one of drop_id and name")
        return self._request("get_drop", {"drop_id": drop_id} if drop_id else {"name": name})

    def _drop_version(self, drop_id: str, version: int | None) -> int:
        if version is not None:
            return version
        current = self.get_drop(drop_id=drop_id).get("drop") or {}
        if not isinstance(current.get("version"), int):
            raise ValidationError(f"the extension returned no version for drop {drop_id}")
        return current["version"]

    def update_drop(
        self,
        drop_id: str,
        version: int | None = None,
        *,
        label: str | None = None,
        memo: str | None = None,
        state: str | None = None,
        mode: str | None = None,
        observe_until: str | None = None,
        redirect_url: str | None = None,
        document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Change a drop made with :meth:`create_drop` (compare-and-set on version).

        A field left as None is unchanged. An empty ``observe_until`` clears it
        and an empty ``redirect_url`` removes the redirect. A ``document``
        replaces the content (``{}`` makes it all generated again).

        Args:
            drop_id: The drop's id.
            version: The version read with the drop. None: read the drop now
                and use its current version.
            label: As in :meth:`create_drop`.
            memo: As in :meth:`create_drop`.
            state: active or disabled.
            mode: live or observe.
            observe_until: RFC 3339 time, or "" to clear it.
            redirect_url: A public https URL, or "" to remove the redirect.
            document: Document drops: the new content.

        Returns:
            dict: ``drop``.
        """
        data: dict[str, Any] = {"drop_id": drop_id, "version": self._drop_version(drop_id, version)}
        for key, value in (
            ("label", label), ("memo", memo), ("state", state), ("mode", mode),
            ("observe_until", observe_until), ("redirect_url", redirect_url), ("document", document),
        ):
            if value is not None:
                data[key] = value
        return self._request("update_drop", data)

    def rotate_drop(self, drop_id: str, version: int | None = None) -> dict[str, Any]:
        """Give a drop a new secret; the old one keeps alerting for 90 days.

        Args:
            drop_id: The drop's id.
            version: The version read with the drop. None: read the drop now
                and use its current version.

        Returns:
            dict: ``drop`` and ``paste`` (the new value).
        """
        return self._request(
            "rotate_drop", {"drop_id": drop_id, "version": self._drop_version(drop_id, version)},
        )

    def delete_drop(self, drop_id: str) -> dict[str, Any]:
        """Stop a drop's alerts for good (not reversible).

        Args:
            drop_id: The drop's id.

        Returns:
            dict: ``drop``.
        """
        return self._request("delete_drop", {"drop_id": drop_id})

    def draft_drop_document(self, format: str, document: dict[str, Any] | None = None) -> dict[str, Any]:
        """The content a document drop would be generated with (read-only).

        Args:
            format: docx or svg.
            document: Fields to keep as given.

        Returns:
            dict: ``document``: file_name, title, lines, link_text, author.
        """
        data: dict[str, Any] = {"format": format}
        if document:
            data["document"] = document
        return self._request("draft_drop_document", data)

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def uninstall(self, *, force: bool = False, cancel: bool = False) -> dict[str, Any]:
        """Start or advance the uninstall, and return its status.

        Args:
            force: Finish although decoys remain on offline sensors.
            cancel: Abandon the uninstall.

        Returns:
            dict: ``state``, ``safe_to_unsubscribe``, ``message``, ``decoys``,
                ``rules_kept`` and ``issues``.
        """
        data: dict[str, Any] = {}
        _put(data, "force", force)
        _put(data, "cancel", cancel)
        return self._request("uninstall", data)

    def uninstall_status(self) -> dict[str, Any]:
        """Where an uninstall stands, without changing anything."""
        return self._request("uninstall_status")
