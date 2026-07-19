"""Cloud Security (CNAPP) SDK for LimaCharlie v2.

Wraps the ``/cloudsec/{oid}/...`` REST routes served by the API
gateway: the merged, risk-ranked findings worklist (CSPM + attack
paths + CIEM), the single-identity access rollup, the resource
inventory, the pre-aggregated estate topology and security graph,
compliance assessment, the risk overview, CAASM (third-party asset
attack surface), sensor<->cloud-asset resolution, the finding triage
writes, the cloudsec_policy authoring aids (vocabulary, live
autocomplete, and the two "Simulate" preflights), CSV exports of the
read surface, per-provider coverage manifests, and the multi-org
fleet overview (``/cloudsec/fleet/overview``).

Reads require the ``cloudsec.get`` permission and writes require
``cloudsec.set``; every route additionally requires the org to be
subscribed to the ``ext-cloud-security`` extension (403 otherwise).

Provider credentials/config and the cloudsec policies are hive
records (``cloudsec_provider``, ``cloudsec_policy``, ``cloudsec_query``
hives) managed through the standard Hive API; the provider operations
here are the pre-save credential preflight
(:meth:`CloudSec.test_provider`) and the coverage manifests
(:meth:`CloudSec.get_provider_manifests`).
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from ..errors import AuthenticationError

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


def _query_run_body(
    named: str | None,
    text: str | None,
    query: dict[str, Any] | None,
    project: list[str] | None,
) -> dict[str, Any]:
    """Assemble the graph-query POST body (shared by run/export)."""
    body: dict[str, Any] = {}
    if named is not None:
        body["named"] = named
    if text is not None:
        body["text"] = text
    if query is not None:
        body["query"] = query
    if project is not None:
        body["project"] = project
    return body


# Chunk size for the bulk sensor<->asset resolution GETs: ids ride as repeated
# query params and the platform load balancer caps URLs at ~8KB, so one request
# can only carry ~190 UUIDs. 100 per request (~4KB) leaves comfortable headroom;
# the gateway's own per-request cap is 500.
_RESOLVE_CHUNK_SIZE = 100


class CloudSec:
    """Cloud Security (CNAPP) client for LimaCharlie."""

    def __init__(self, org: Organization) -> None:
        self._org = org
        # Request-scoped multi-org JWT for the fleet route, cached across
        # calls (pagination) and re-minted on a 401. Never installed on the
        # client — the client's own token is not touched by fleet calls.
        self._fleet_jwt: str | None = None

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
        *,
        raw_response: bool = False,
    ) -> Any:
        return self._org.client.request(
            "GET",
            f"cloudsec/{self.oid}/{path}",
            query_params=query_params or None,
            raw_response=raw_response,
        )

    def _post(
        self,
        path: str,
        body: dict[str, Any],
        query_params: list[tuple[str, str]] | None = None,
        *,
        raw_response: bool = False,
    ) -> Any:
        return self._org.client.request(
            "POST",
            f"cloudsec/{self.oid}/{path}",
            query_params=query_params or None,
            raw_body=json.dumps(body).encode(),
            content_type="application/json",
            raw_response=raw_response,
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
            sort: Server-side sort key: ``lc_risk`` (the default),
                ``severity``, or ``first_seen``.
            order: ``desc`` (the default) or ``asc``.
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

    def get_finding_classes(self) -> dict[str, Any]:
        """The canonical ``finding_class`` vocabulary.

        Served from the backend enum so callers never guess at the valid
        values for the ``finding_class`` filter or a suppression-policy
        matcher.

        Returns:
            ``{"classes": ["toxic_combination", "public_exposure", ...]}``.
        """
        return self._get("findings/classes")

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

    def get_identity(self, urn: str) -> dict[str, Any]:
        """The single-identity effective-access rollup for one identity urn.

        The same row shape the public-access principals list carries
        (grant / privileged / sensitive-reach counts, posture facets, risk
        score), but for ANY identity — not only the risk-ranked top-N.
        Powers the Identity 360 view.

        Returns:
            ``{"identity": {...}}``, or ``{"identity": null}`` when the urn
            is not a known identity.
        """
        return self._get("ciem/identity", _query_pairs(urn=urn))

    # ------------------------------------------------------------------
    # Inventory / resources / data security
    # ------------------------------------------------------------------

    def list_inventory(
        self,
        *,
        resource_type: str | None = None,
        provider: str | None = None,
        account: str | None = None,
        region: str | None = None,
        q: str | None = None,
        account_unscoped: bool | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List the cloud resource inventory.

        Args:
            resource_type: Filter by resource type (the ``type`` selector).
            provider: Filter by the producing provider sweep (e.g. ``gcp``,
                ``aws``, ``okta``, ``google_workspace``).
            account, region: Scalar filters.
            q: Substring search.
            account_unscoped: Escape hatch — when ``True`` the walk drops
                the per-account scoping and spans the whole estate. Only
                forwarded when set (the account-scoped default holds
                otherwise); the gateway ignores a ``False`` value.
            cursor, limit: Keyset pagination.

        Returns:
            ``{"resources": [...], "next_cursor": str}``.
        """
        return self._get("inventory", _query_pairs(
            type=resource_type, provider=provider, account=account,
            region=region, q=q,
            account_unscoped=account_unscoped or None,
            cursor=cursor, limit=limit,
        ))

    def get_inventory_facets(self) -> dict[str, Any]:
        """Inventory facet counts (by type/account/region)."""
        return self._get("inventory/facets")

    def get_topology(self) -> dict[str, Any]:
        """Pre-aggregated estate topology (exact at any estate size).

        Per-scope node counts and inter-scope relationship rollups, an
        ``O(#scopes)`` response independent of resource count — the server
        aggregation powering the Topology view.

        Returns:
            ``{"available": bool, "scopes": [...], "edges": [...],
            "generated_at": int}``. ``available`` is ``False`` when the
            projector has not yet materialized this org (callers should
            fall back to the inventory walk).
        """
        return self._get("topology")

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
    # Policy authoring: vocabulary, autocomplete, and preview (Simulate)
    # ------------------------------------------------------------------
    #
    # Helpers for authoring the cloudsec_policy hive records (Data
    # Classification / Coverage / Exclusions / suppression). The policies
    # themselves are set through the Hive API; these are the read-only aids
    # the rule form uses: the vocabulary and live autocomplete that drive
    # the pickers, and the two "Simulate" preflights that evaluate an
    # in-edit matcher against the estate before it is saved.

    def get_policy_vocabulary(self) -> dict[str, Any]:
        """The server-driven cloudsec_policy authoring vocabulary.

        The per-surface capability table (which matcher dimensions each
        policy surface honors), the closed vocabularies (resource types
        grouped per section, providers, criticality tiers, content classes,
        suggested classes), and the org's in-use histograms (accounts,
        regions, label keys, network tags, resource types) so the rule form
        can offer autocomplete without the operator guessing at valid
        tokens.

        Returns:
            ``{"surfaces": {...}, "resource_types": {...},
            "content_classes": [...], "providers": [...], "tiers": [...],
            "suggested_classes": [...], "in_use": {...}}``.
        """
        return self._get("policy/vocabulary")

    def suggest_policy_values(
        self,
        dimension: str,
        q: str,
        *,
        target: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Live matcher-value autocomplete from the org's own inventory.

        The live companion to :meth:`get_policy_vocabulary`'s bundled
        histograms, for the high-cardinality dimensions.

        Args:
            dimension: ``name`` (walks the estate's policy-matchable
                resources for names containing ``q``) or ``account``
                (filters the account facet).
            q: The typed fragment to match (case-insensitive substring;
                the backend caps it at 256 bytes).
            target: Optional walk narrowing —
                ``data_store`` | ``compute`` | ``identity`` | ``any`` — to
                the rule set being edited.
            limit: Max suggestions (default 20, server cap 50).

        Returns:
            ``{"values": [{"value": str, "count": int}, ...],
            "truncated": bool, "evaluated": int}``.
        """
        body: dict[str, Any] = {"dimension": dimension, "q": q}
        if target is not None:
            body["target"] = target
        if limit is not None:
            body["limit"] = limit
        return self._post("policy/suggest", body)

    def simulate_resource_match(
        self,
        rules: list[dict[str, Any]],
        *,
        target: str | None = None,
        resource_types: list[str] | None = None,
        sample_limit: int | None = None,
    ) -> dict[str, Any]:
        """Preview a resource-matcher rule set against the stored inventory.

        Evaluates a set of cloudsec_policy resource matcher rules (the
        Data Classification / Coverage / Exclusions vocabulary:
        ``account_contains`` / ``account_glob`` / ``name_contains`` /
        ``name_glob`` / ``label`` / ``label_key_present`` / ``tag``; rules
        compose as OR) read-only — nothing is saved.

        Args:
            rules: The matcher rules to evaluate (at least one).
            target: Which rule set is being simulated —
                ``data_store`` | ``compute`` | ``identity`` | ``any``
                (default ``any``) — scoping the walked resource family.
            resource_types: Optional explicit resource_type narrowing
                (exclusions rules).
            sample_limit: Sample size to return (default 25, server cap
                100).

        Returns:
            ``{"evaluated": int, "matched": int, "indeterminate": int,
            "truncated": bool, "sample": [...],
            "indeterminate_sample": [...]}``. ``indeterminate`` counts rows
            whose stored shape cannot evaluate a label constraint;
            ``truncated`` is ``True`` when the walk hit its size/time bound.
        """
        body: dict[str, Any] = {"rules": rules}
        if target is not None:
            body["target"] = target
        if resource_types is not None:
            body["resource_types"] = resource_types
        if sample_limit is not None:
            body["sample_limit"] = sample_limit
        return self._post("simulate/resources", body)

    def simulate_finding_match(
        self,
        match: dict[str, Any],
        *,
        sample_limit: int | None = None,
    ) -> dict[str, Any]:
        """Preview a suppression matcher against the org's OPEN findings.

        Evaluates a suppression-policy matcher (``finding_class`` /
        ``rule`` / account globs / ``urn_prefix`` / ``max_severity``) with
        the exact semantics the suppression engine applies, read-only —
        nothing is dispositioned. An empty ``match`` is allowed: it matches
        everything up to the default severity ceiling, and showing that
        blast radius is the point of the preview.

        Args:
            match: The suppression matcher object.
            sample_limit: Sample size to return (default 25, server cap
                100).

        Returns:
            ``{"evaluated": int, "matched": int, "truncated": bool,
            "sample": [...]}``.
        """
        body: dict[str, Any] = {"match": match}
        if sample_limit is not None:
            body["sample_limit"] = sample_limit
        return self._post("simulate/findings", body)

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
        return self._post(
            "query", _query_run_body(named, text, query, project),
        )

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
        """Cloud-collection run status for a provider.

        Args:
            provider: Provider id (e.g. ``gcp`` — the server default —
                ``aws``, ``azure``, ``okta``, ...; validated server-side).
                Lowered before sending: the backend scan-state lookup is a
                case-sensitive read keyed on lowercase provider ids, so a
                raw ``"AWS"`` would silently read as never-scanned.

        Returns:
            ``{"status": {...}}``.
        """
        if provider is not None:
            provider = provider.strip().lower()
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
    # Providers (preflight + coverage manifests)
    # ------------------------------------------------------------------

    def get_provider_manifests(
        self, *, provider_type: str | None = None,
    ) -> dict[str, Any]:
        """Per-provider coverage manifests for the org.

        For each provider: the collectors (resource kinds + edge kinds)
        with their status, the posture checks that can fire, the
        activity/CIEM support level, the validation grade, the known
        gaps, and the org's own scan coverage/freshness — the honest,
        machine-readable picture of what the platform CAN collect merged
        with what THIS org's connection actually got.

        Args:
            provider_type: Fetch a single provider's manifest (e.g.
                ``gcp``, ``aws``, ``azure``, ``okta``), including one the
                org has never swept. Omit to list every provider the org
                has a manifest or a sweep for.

        Returns:
            ``{"manifests": [...]}``, or ``{"manifest": {...}}`` when
            ``provider_type`` is given.
        """
        return self._get("providers/manifest", _query_pairs(
            type=provider_type,
        ))

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

    # ------------------------------------------------------------------
    # Fleet (multi-org)
    # ------------------------------------------------------------------

    def get_fleet_overview(
        self,
        *,
        oids: list[str] | None = None,
        group: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        trend_days: int | None = None,
        all_orgs: bool = True,
    ) -> dict[str, Any]:
        """Multi-org fleet posture board in one call.

        One posture row per authorized org (score, severity distribution,
        trend direction, coverage/freshness, usage counters) plus, on the
        first page, the cross-tenant rollups (widely-recurring rules,
        fleet risk distribution, orgs with failing providers).

        The org set is the orgs the caller's token carries — optionally
        narrowed by ``oids`` and/or an org ``group`` — intersected with
        the orgs where the caller holds ``cloudsec.get`` and that are
        subscribed to the cloud-security extension. An org failing either
        filter is silently excluded (counted in ``skipped``), never an
        error. Keyset-paginated by org (default 25 per page, cap 100);
        the resolved org set is capped at 500 — past that, narrow with
        ``oids`` or a ``group``.

        Args:
            oids: Explicit org ids to include.
            group: An org-group id — include the group's member orgs
                (the caller must be a member or owner of the group).
            cursor, limit: Keyset pagination (by org).
            trend_days: Days of score-trend window per org (default 30).
            all_orgs: When the client uses user-scoped credentials, mint
                a multi-org JWT spanning every org the user can access
                and send it on this request only (the fleet call is
                otherwise limited to the single org the client's own JWT
                is scoped to). The client's own token is never touched;
                the multi-org token is cached across calls (pagination)
                and re-minted once on a 401. Ignored for org-scoped
                (non-user) API keys.

        Returns:
            ``{"orgs": [...], "next_cursor": str, "total_orgs": int,
            "skipped": {"not_enabled", "lookup_failed"}, "rollups": {...}
            (first page only)}``.
        """
        client = self._org.client
        qp = _query_pairs(
            oids=oids, group=group, cursor=cursor, limit=limit,
            trend_days=trend_days,
        )

        is_user_scoped = (
            getattr(client, "_uid", None) is not None
            or getattr(client, "_oauth_creds", None) is not None
        )
        if not (all_orgs and is_user_scoped):
            # The fleet path is NOT oid-scoped: no cloudsec/{oid}/ prefix.
            return client.request(
                "GET", "cloudsec/fleet/overview", query_params=qp or None,
            )

        # Request-scoped multi-org token: sent as an explicit Authorization
        # header with is_no_auth so the client's own (org-scoped) JWT and its
        # 401-refresh machinery stay completely out of the call — a plain
        # request() retry would re-mint an ORG-scoped token and silently
        # collapse the fleet to one org. A 401 re-mints the multi-org token
        # once and retries; a second 401 is a real auth failure.
        if self._fleet_jwt is None:
            self._fleet_jwt = client.mint_jwt()
        for attempt in range(2):
            try:
                return client.request(
                    "GET", "cloudsec/fleet/overview",
                    query_params=qp or None,
                    is_no_auth=True,
                    extra_headers={
                        "Authorization": f"Bearer {self._fleet_jwt}",
                    },
                )
            except AuthenticationError:
                self._fleet_jwt = None
                if attempt == 1:
                    raise
                self._fleet_jwt = client.mint_jwt()
        raise AssertionError("unreachable")

    # ------------------------------------------------------------------
    # CSV exports
    # ------------------------------------------------------------------
    #
    # ``?format=csv`` on the four exportable reads streams a text/csv
    # attachment instead of JSON: the gateway walks the FULL filtered set
    # server-side (any cursor/limit is ignored), capped at 100k rows with
    # a trailing ``#`` comment row on truncation, and cells are sanitized
    # against spreadsheet formula injection.

    def export_findings_csv(
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
    ) -> str:
        """Export the (filtered) findings worklist as CSV text.

        Takes the same filter selectors as :meth:`list_findings`; the
        server walks the full filtered set (no pagination), capped at
        100k rows.

        Returns:
            The CSV document as a string.
        """
        pairs = _finding_query_pairs(
            severity=severity, finding_class=finding_class, status=status,
            account=account, reachable=reachable, kev=kev, q=q,
            sort=sort, order=order,
        )
        pairs.append(("format", "csv"))
        return self._get("findings", pairs, raw_response=True)

    def export_inventory_csv(
        self,
        *,
        resource_type: str | None = None,
        provider: str | None = None,
        account: str | None = None,
        region: str | None = None,
        q: str | None = None,
        account_unscoped: bool | None = None,
    ) -> str:
        """Export the (filtered) cloud resource inventory as CSV text.

        Takes the same filter selectors as :meth:`list_inventory`; the
        server walks the full filtered set (no pagination), capped at
        100k rows.

        Returns:
            The CSV document as a string.
        """
        pairs = _query_pairs(
            type=resource_type, provider=provider, account=account,
            region=region, q=q,
            account_unscoped=account_unscoped or None,
        )
        pairs.append(("format", "csv"))
        return self._get("inventory", pairs, raw_response=True)

    def export_compliance_csv(
        self,
        *,
        framework: str | None = None,
        assignment: str | None = None,
    ) -> str:
        """Export a compliance assessment as CSV text.

        Takes the same selectors as :meth:`get_compliance`.

        Returns:
            The CSV document as a string.
        """
        pairs = _query_pairs(framework=framework, assignment=assignment)
        pairs.append(("format", "csv"))
        return self._get("compliance", pairs, raw_response=True)

    def export_query_csv(
        self,
        *,
        named: str | None = None,
        text: str | None = None,
        query: dict[str, Any] | None = None,
        project: list[str] | None = None,
    ) -> str:
        """Run a graph query and export the rows as CSV text.

        Takes the same query selectors as :meth:`run_query` (provide
        exactly one of ``named`` / ``text`` / ``query``).

        Returns:
            The CSV document as a string.
        """
        return self._post(
            "query",
            _query_run_body(named, text, query, project),
            query_params=[("format", "csv")],
            raw_response=True,
        )
