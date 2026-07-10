"""Cloud Security (CNAPP) SDK for LimaCharlie v2.

Wraps the ``/cloudsec/{oid}/...`` REST routes served by the API
gateway: the merged, risk-ranked findings worklist (CSPM + attack
paths + CIEM), the resource inventory and security graph, compliance
assessment, the risk overview, CAASM (third-party asset attack
surface), sensor<->cloud-asset resolution, and the finding triage
writes.

Reads require the ``cloudsec.get`` permission and writes require
``cloudsec.set``; every route additionally requires the org to be
subscribed to the ``ext-cloud-inventory`` extension (403 otherwise).

Provider credentials/config and the cloudsec policies are hive
records (``cloudsec_provider``, ``cloudsec_policy``, ``cloudsec_query``
hives) managed through the standard Hive API; the one provider
operation here is the pre-save credential preflight
(:meth:`CloudSec.test_provider`).
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


def _add_pairs(
    pairs: list[tuple[str, str]],
    key: str,
    values: list[str] | tuple[str, ...] | None,
) -> None:
    """Append one ``(key, value)`` pair per value (repeatable query param)."""
    if not values:
        return
    for v in values:
        pairs.append((key, str(v)))


def _add_scalar(
    pairs: list[tuple[str, str]],
    key: str,
    value: Any,
) -> None:
    """Append a single ``(key, value)`` pair when the caller set a value.

    Booleans are lowered to ``true``/``false`` (the gateway parses them
    with ``strconv.ParseBool``).
    """
    if value is None:
        return
    if isinstance(value, bool):
        pairs.append((key, "true" if value else "false"))
    else:
        pairs.append((key, str(value)))


def _query_pairs(**params: Any) -> list[tuple[str, str]]:
    """Build the query-pair list from keyword selectors, skipping unset keys.

    List/tuple values become repeated keys (OR within a key, AND across
    keys, matching the gateway contract); scalars go through
    :func:`_add_scalar`. Kwarg order is preserved so the emitted query
    string is deterministic.
    """
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            _add_pairs(pairs, key, value)
        else:
            _add_scalar(pairs, key, value)
    return pairs


def _finding_query_pairs(
    *,
    severity: list[str] | None = None,
    finding_class: list[str] | None = None,
    status: list[str] | None = None,
    account: list[str] | None = None,
    reachable: bool | None = None,
    kev: bool | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Assemble the findings worklist selectors shared by list/facets."""
    return _query_pairs(
        severity=severity, finding_class=finding_class, status=status,
        account=account, reachable=reachable, kev=kev, q=q,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


# Chunk size for the bulk sensor<->asset resolution GETs: ids ride as repeated
# query params and the platform load balancer caps URLs at ~8KB, so one request
# can only carry ~190 UUIDs. 100 per request (~4KB) leaves comfortable headroom;
# the gateway's own per-request cap is 500.
_RESOLVE_CHUNK_SIZE = 100


class CloudSec:
    """Cloud Security (CNAPP) client for LimaCharlie."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def oid(self) -> str:
        return self._org.oid

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        query_params: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        return self._org.client.request(
            "GET",
            f"cloudsec/{self.oid}/{path}",
            query_params=query_params or None,
        )

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._org.client.request(
            "POST",
            f"cloudsec/{self.oid}/{path}",
            raw_body=json.dumps(body).encode(),
            content_type="application/json",
        )

    # ------------------------------------------------------------------
    # Findings worklist
    # ------------------------------------------------------------------

    def list_findings(
        self,
        *,
        severity: list[str] | None = None,
        finding_class: list[str] | None = None,
        status: list[str] | None = None,
        account: list[str] | None = None,
        reachable: bool | None = None,
        kev: bool | None = None,
        q: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List the merged, risk-ranked cloud-security findings.

        Args:
            severity: Filter values (CRITICAL/HIGH/MEDIUM/LOW/INFO), OR'd.
            finding_class: Filter values (toxic_combination, public_exposure,
                ciem_risk, privilege_escalation, vulnerability, misconfig,
                malware, secret, scan_finding, coverage_gap), OR'd.
            status: Filter values (open/resolved), OR'd.
            account: Cloud account filter values, OR'd.
            reachable: Only findings on (non-)reachable resources.
            kev: Only findings with (without) a KEV vulnerability.
            q: Substring search.
            sort, order: Server-side ordering selectors.
            cursor: Keyset-pagination token from a previous page.
            limit: Page size (server clamps to 1000).

        Returns:
            ``{"findings": [...], "next_cursor": str}``.
        """
        return self._get("findings", _finding_query_pairs(
            severity=severity, finding_class=finding_class, status=status,
            account=account, reachable=reachable, kev=kev, q=q,
            sort=sort, order=order, cursor=cursor, limit=limit,
        ))

    def get_finding_facets(
        self,
        *,
        severity: list[str] | None = None,
        finding_class: list[str] | None = None,
        status: list[str] | None = None,
        account: list[str] | None = None,
        reachable: bool | None = None,
        kev: bool | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """Cross-filtered facet counts for the findings worklist.

        Takes the same filter selectors as :meth:`list_findings`; each
        facet dimension is counted against the other active filters.

        Returns:
            ``{"facets": {...}}``.
        """
        return self._get("findings/facets", _finding_query_pairs(
            severity=severity, finding_class=finding_class, status=status,
            account=account, reachable=reachable, kev=kev, q=q,
        ))

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        """Get one finding by id (e.g. ``fnd_<fingerprint>``).

        Returns:
            ``{"finding": {...}}``.
        """
        return self._get(f"findings/{finding_id}")

    # ------------------------------------------------------------------
    # Finding triage writes (cloudsec.set)
    # ------------------------------------------------------------------

    def set_finding_status(
        self,
        finding_id: str,
        kind: str,
        *,
        reason: str | None = None,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        """Disposition (or reopen) a finding.

        Args:
            finding_id: The finding to disposition.
            kind: ``mitigated``, ``accepted``, ``false_positive``, or
                ``open`` to clear the disposition and reopen the finding
                (owner/ticket are kept).
            reason: Optional operator note.
            expires_at: Unix seconds; only meaningful for ``accepted``.

        Returns:
            ``{"ok": bool}``.
        """
        resolution: dict[str, Any] = {"kind": kind}
        if reason is not None:
            resolution["reason"] = reason
        if expires_at is not None:
            resolution["expires_at"] = expires_at
        return self._post(
            f"findings/{finding_id}/status", {"resolution": resolution},
        )

    def bulk_set_finding_status(
        self,
        finding_ids: list[str],
        kind: str,
        *,
        reason: str | None = None,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        """Apply one resolution to many findings at once.

        ``kind`` must be ``mitigated``, ``accepted``, or
        ``false_positive`` — unlike :meth:`set_finding_status`, the bulk
        endpoint does NOT accept ``open`` (reopen findings one at a
        time).

        Returns:
            ``{"updated": int}``.
        """
        resolution: dict[str, Any] = {"kind": kind}
        if reason is not None:
            resolution["reason"] = reason
        if expires_at is not None:
            resolution["expires_at"] = expires_at
        return self._post("findings/bulk/status", {
            "finding_ids": list(finding_ids),
            "resolution": resolution,
        })

    def set_finding_owner(self, finding_id: str, owner: str) -> dict[str, Any]:
        """Assign (or clear, with an empty string) the owner of a finding.

        Returns:
            ``{"ok": bool}``.
        """
        return self._post(f"findings/{finding_id}/owner", {"owner": owner})

    def set_finding_ticket(self, finding_id: str, ticket: str) -> dict[str, Any]:
        """Link (or clear, with an empty string) a ticket id/url to a finding.

        Returns:
            ``{"ok": bool}``.
        """
        return self._post(f"findings/{finding_id}/ticket", {"ticket": ticket})

    # ------------------------------------------------------------------
    # Attack paths / CIEM
    # ------------------------------------------------------------------

    def list_attack_paths(
        self,
        *,
        severity: list[str] | None = None,
        account: list[str] | None = None,
        status: list[str] | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """Headline toxic-combination attack paths.

        Returns:
            ``{"paths": [...]}``.
        """
        return self._get("attack-paths", _query_pairs(
            severity=severity, account=account, status=status, q=q,
        ))

    def get_public_access(self) -> dict[str, Any]:
        """CIEM: public/external access to sensitive resources.

        Returns:
            ``{"access": [...]}``.
        """
        return self._get("ciem/public-access")

    def get_identity_facets(self) -> dict[str, Any]:
        """CIEM identity facet counts.

        Returns:
            ``{"facets": {...}}``.
        """
        return self._get("ciem/facets")

    # ------------------------------------------------------------------
    # Inventory / resources / data security
    # ------------------------------------------------------------------

    def list_inventory(
        self,
        *,
        resource_type: str | None = None,
        account: str | None = None,
        region: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List the cloud resource inventory.

        Args:
            resource_type: Filter by resource type (the ``type`` selector).
            account, region: Scalar filters.
            q: Substring search.
            cursor, limit: Keyset pagination.

        Returns:
            ``{"resources": [...], "next_cursor": str}``.
        """
        return self._get("inventory", _query_pairs(
            type=resource_type, account=account, region=region,
            q=q, cursor=cursor, limit=limit,
        ))

    def get_inventory_facets(self) -> dict[str, Any]:
        """Inventory facet counts (by type/account/region)."""
        return self._get("inventory/facets")

    def get_data_security_facets(self) -> dict[str, Any]:
        """DSPM data-store facet counts (total/sensitive/public, store kinds).

        Returns:
            ``{"facets": {...}}``.
        """
        return self._get("data-security/facets")

    def get_resource(self, urn: str) -> dict[str, Any]:
        """Get the canonical record for any urn the graph knows.

        Returns:
            ``{"resource": {...}}`` or ``{"resource": null}`` when unknown.
        """
        return self._get("resource", _query_pairs(urn=urn))

    # ------------------------------------------------------------------
    # Security graph
    # ------------------------------------------------------------------

    def get_graph_neighbors(
        self, urn: str, *, limit: int | None = None,
    ) -> dict[str, Any]:
        """Expand a resource's 1-hop neighborhood in the security graph.

        Args:
            urn: The anchor resource.
            limit: Max neighbors (default 200, hard cap 500).

        Returns:
            ``{"graph": {"nodes": [...], "edges": [...]}}`` with ``truncated``.
        """
        return self._get("graph/neighbors", _query_pairs(urn=urn, limit=limit))

    def list_queries(self) -> dict[str, Any]:
        """List the named graph queries in the query pack.

        Returns:
            ``{"queries": [{"name","title","description","query"}, ...]}``.
        """
        return self._get("queries")

    def run_query(
        self,
        *,
        named: str | None = None,
        text: str | None = None,
        query: dict[str, Any] | None = None,
        project: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run a graph query. Provide exactly one of named / text / query.

        Args:
            named: A query-pack name (see :meth:`list_queries`).
            text: A text query.
            query: A raw DSL object.
            project: Optional aliases to project into the rows.

        Returns:
            ``{"rows": [{alias: urn, ...}, ...]}``.
        """
        body: dict[str, Any] = {}
        if named is not None:
            body["named"] = named
        if text is not None:
            body["text"] = text
        if query is not None:
            body["query"] = query
        if project is not None:
            body["project"] = project
        return self._post("query", body)

    # ------------------------------------------------------------------
    # Compliance
    # ------------------------------------------------------------------

    def get_compliance(
        self,
        *,
        framework: str | None = None,
        assignment: str | None = None,
    ) -> dict[str, Any]:
        """Per-control pass/fail compliance assessment.

        Args:
            framework: Framework id (default cis-gcp server-side);
                ignored when ``assignment`` is set.
            assignment: Named scoped assignment to evaluate instead.

        Returns:
            ``{"report": {...}}``.
        """
        return self._get("compliance", _query_pairs(
            framework=framework, assignment=assignment,
        ))

    def list_compliance_frameworks(self) -> dict[str, Any]:
        """List selectable compliance frameworks.

        Returns:
            ``{"frameworks": [{"id","name","version","control_count"}, ...]}``.
        """
        return self._get("compliance/frameworks")

    def list_compliance_assignments(self) -> dict[str, Any]:
        """List the org's scoped compliance assignments (with scores)."""
        return self._get("compliance/assignments")

    # ------------------------------------------------------------------
    # Overview / trends / chokepoints
    # ------------------------------------------------------------------

    def get_overview(self, *, trend_days: int | None = None) -> dict[str, Any]:
        """Composed risk overview (score, severity distribution, top paths,
        coverage, trend, recent changes) in one round-trip."""
        return self._get("overview", _query_pairs(trend_days=trend_days))

    def list_chokepoints(self) -> dict[str, Any]:
        """Estate-wide chokepoints ranked by attack paths broken.

        Returns:
            ``{"chokepoints": [...], "total_paths": int}``.
        """
        return self._get("chokepoints")

    def dismiss_chokepoint(
        self, urn: str, *, reason: str | None = None,
    ) -> dict[str, Any]:
        """Dismiss an estate-wide choke point from the risk overview.

        Returns:
            ``{"ok": bool}``.
        """
        body: dict[str, Any] = {"urn": urn}
        if reason is not None:
            body["reason"] = reason
        return self._post("chokepoints/dismiss", body)

    def restore_chokepoint(self, urn: str) -> dict[str, Any]:
        """Restore (un-dismiss) a previously dismissed choke point."""
        return self._post("chokepoints/restore", {"urn": urn})

    def list_changes(self, *, limit: int | None = None) -> dict[str, Any]:
        """Recent finding lifecycle changes (created/closed), newest first."""
        return self._get("changes", _query_pairs(limit=limit))

    def get_risk_trend(self, *, trend_days: int | None = None) -> dict[str, Any]:
        """The org risk-score history, oldest first."""
        return self._get("risk-trend", _query_pairs(trend_days=trend_days))

    def get_scan_status(self, *, provider: str | None = None) -> dict[str, Any]:
        """Cloud-collection run status for a provider (gcp|aws|azure).

        Returns:
            ``{"status": {...}}``.
        """
        return self._get("scan-status", _query_pairs(provider=provider))

    # ------------------------------------------------------------------
    # Sensor <-> cloud asset resolution
    # ------------------------------------------------------------------

    def _resolve_chunked(
        self, path: str, key: str, values: list[str],
    ) -> dict[str, Any]:
        """Run a bulk resolve as URL-safe chunks and merge the responses.

        The ids ride as repeated query params, so an unbounded batch would
        blow the ~8KB load-balancer URL limit long before the gateway's
        500-per-request cap — chunking makes any batch size work.
        """
        resolved: list[Any] = []
        unresolved: list[Any] = []
        values = list(values)
        for i in range(0, len(values), _RESOLVE_CHUNK_SIZE):
            chunk = values[i:i + _RESOLVE_CHUNK_SIZE]
            resp = self._get(path, _query_pairs(**{key: chunk}))
            resolved.extend(resp.get("resolved") or [])
            unresolved.extend(resp.get("unresolved") or [])
        return {"resolved": resolved, "unresolved": unresolved}

    def resolve_sensors(self, sids: list[str]) -> dict[str, Any]:
        """Resolve sensor ids to the cloud asset each runs on.

        Any batch size works — requests are chunked (100 ids each) to
        stay within URL limits, and the per-chunk responses are merged.

        Returns:
            ``{"resolved": [...], "unresolved": [...]}``.
        """
        return self._resolve_chunked("resolve/sensors", "sid", sids)

    def resolve_assets(self, urns: list[str]) -> dict[str, Any]:
        """Resolve cloud asset URNs to the sensors running on each.

        Any batch size works — requests are chunked (100 URNs each) to
        stay within URL limits, and the per-chunk responses are merged.

        Returns:
            ``{"resolved": [...], "unresolved": [...]}``.
        """
        return self._resolve_chunked("resolve/assets", "urn", urns)

    # ------------------------------------------------------------------
    # CAASM (third-party asset attack surface)
    # ------------------------------------------------------------------

    def list_caasm_assets(
        self,
        *,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """The merged third-party asset inventory (EDR/IdP/MDM/scanner sources).

        Returns:
            ``{"resources": [...], "next_cursor": str}``.
        """
        return self._get("caasm/assets", _query_pairs(
            q=q, cursor=cursor, limit=limit,
        ))

    def list_caasm_coverage(
        self,
        *,
        status: list[str] | None = None,
        severity: list[str] | None = None,
        q: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Coverage-gap findings (assets missing a required tool).

        Same shape as :meth:`list_findings` with the ``coverage_gap``
        class stamped server-side.

        Returns:
            ``{"findings": [...], "next_cursor": str}``.
        """
        return self._get("caasm/coverage", _query_pairs(
            status=status, severity=severity, q=q, sort=sort,
            order=order, cursor=cursor, limit=limit,
        ))

    def get_caasm_policy(self) -> dict[str, Any]:
        """The stored expected-coverage policy.

        Returns:
            The standard resource-list shape: ``resources`` holds zero
            rows (no policy declared) or one row whose ``props`` object
            is the policy (``{"expect": [...]}``).
        """
        return self._get("caasm/policy")

    def set_caasm_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        """Set (upsert) the expected-coverage policy.

        Args:
            policy: e.g. ``{"expect": [{"label": "edr-on-devices",
                "capability": "edr", "kinds": ["device"]}]}``. Validated
                server-side; an invalid policy is rejected loudly.

        Returns:
            ``{"ok": bool}``.
        """
        return self._post("caasm/policy", {"policy": policy})

    def caasm_ingest(
        self,
        source: str,
        *,
        records: list[dict[str, Any]] | None = None,
        record: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest raw third-party asset records into the merged inventory.

        Args:
            source: One of sentinelone|crowdstrike|defender|okta|entraid|
                ms_graph|wiz.
            records: Raw vendor-shaped JSON objects (batch). Chunk large
                imports — the request body is capped at 1 MiB.
            record: A single object (alternative to ``records``).
            policy: Optional inline coverage policy override.

        Returns:
            ``{"result": {"received","normalized","skipped","assets",
            "created","updated","deleted"}}``.
        """
        body: dict[str, Any] = {"source": source}
        if records is not None:
            body["records"] = records
        if record is not None:
            body["record"] = record
        if policy is not None:
            body["policy"] = policy
        return self._post("caasm/ingest", body)

    # ------------------------------------------------------------------
    # Provider preflight
    # ------------------------------------------------------------------

    def test_provider(self, provider: dict[str, Any]) -> dict[str, Any]:
        """Preflight a cloud provider configuration before saving it.

        Connects to the provider with the given credentials (ephemeral —
        never stored) and probes every permission surface collection
        needs. ``credentials`` may be inline plaintext or a
        ``hive://secret/<name>`` reference to an already-saved secret.

        Args:
            provider: A ``cloudsec_provider`` hive record shape.

        Returns:
            ``{"supported": bool, "report": {"provider", "ok",
            "checks": [{"id","name","required","ok","detail"}, ...]}}``.
        """
        return self._post("providers/test", {"provider": provider})
