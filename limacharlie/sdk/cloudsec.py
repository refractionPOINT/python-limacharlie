"""Cloud Security (CNAPP) SDK for LimaCharlie v2.

Wraps the ``/cloudsec/{oid}/...`` REST routes served by the API
gateway: the merged, risk-ranked findings worklist (CSPM + attack
paths + CIEM) with its facet and shared-fix (cause) rollups, the
identity access population and single-identity rollup, the resource
inventory, the Data Security (DSPM) store list and facets, the
pre-aggregated estate topology and security graph, compliance
assessment, the risk overview, CAASM (third-party asset attack
surface), sensor<->cloud-asset resolution, the finding triage
writes, the cloudsec_policy authoring aids (vocabulary, live
autocomplete, and the two "Simulate" preflights), CSV exports of the
read surface, per-provider coverage manifests, the free-tier
standing, and the multi-org fleet overview
(``/cloudsec/fleet/overview``).

The AppSec code lane additionally exposes what each connected
source-control organization may actually DO
(:meth:`CloudSec.get_code_capabilities` — GitHub connections only), the
dependency-upgrade queue (:meth:`CloudSec.get_code_fixes`), the
registry-backed container-image inventory
(:meth:`CloudSec.list_image_repos`, :meth:`CloudSec.list_container_images`,
:meth:`CloudSec.get_container_image`), the pull-request check
(:meth:`CloudSec.check_pull_request`) and the connection's App webhook
repair (:meth:`CloudSec.configure_code_webhook`).

Compliance comes in two shapes. :meth:`CloudSec.get_compliance` is the
live, point-in-time assessment that keeps nothing. The v2 surface —
:meth:`CloudSec.create_compliance_run`,
:meth:`CloudSec.list_compliance_runs`,
:meth:`CloudSec.list_compliance_attestations`,
:meth:`CloudSec.create_compliance_attestation`,
:meth:`CloudSec.list_compliance_events`,
:meth:`CloudSec.export_compliance_run`,
:meth:`CloudSec.list_compliance_schedules` and
:meth:`CloudSec.set_compliance_schedule` — is the audit-grade half:
immutable runs, append-only attestation revisions, a drift stream and
deterministic exports.

Reads require the ``cloudsec.get`` permission and writes require
``cloudsec.set``; every route additionally requires the org to be
subscribed to the ``ext-cloud-security`` extension (403 otherwise).

Provider credentials/config and the cloudsec policies are hive
records (``cloudsec_provider``, ``cloudsec_policy``, ``cloudsec_query``
hives) managed through the standard Hive API; the provider operations
here are the pre-save credential preflight
(:meth:`CloudSec.test_provider`) and the coverage manifests
(:meth:`CloudSec.get_provider_manifests`). GitLab and Bitbucket Cloud
are both supported ``provider_type`` values today (a ``gitlab_namespace``
+ optional ``gitlab_base_url`` for a self-managed instance, or a
``bitbucket_workspace``, plus ``credentials`` on both — see
``cloudsec provider test`` in the CLI for a worked example of each
record). Creating the connection itself has no dedicated SDK method;
it is a plain hive write, e.g.
``Hive(org, "cloudsec_provider").set(HiveRecord(name="my-gitlab",
data={"provider_type": "gitlab", "gitlab_namespace": "acme/platform",
"credentials": "hive://secret/gitlab-token"}, enabled=True))``, or the
equivalent ``limacharlie hive set --hive-name cloudsec_provider`` CLI
command.
"""

from __future__ import annotations

import base64
import json
from typing import Any, TYPE_CHECKING
from urllib.parse import quote as _quote
from urllib.request import urlopen as _urlopen

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


def _inventory_account_selector(
    account_empty: bool | None,
    account_unscoped: bool | None,
) -> dict[str, bool | None]:
    """Return one inventory account-empty query selector.

    ``account_unscoped`` is the deprecated API name. Preserve it on the wire for
    callers that still use that argument, while new callers use the unambiguous
    ``account_empty`` name. Sending conflicting aliases is almost certainly a caller
    bug and must not silently choose one.
    """
    if account_empty is not None and account_unscoped is not None:
        if bool(account_empty) != bool(account_unscoped):
            raise ValueError(
                "account_empty and account_unscoped cannot have different values"
            )
        return {"account_empty": account_empty or None}
    if account_empty is not None:
        return {"account_empty": account_empty or None}
    return {"account_unscoped": account_unscoped or None}


def _validate_iac_selectors(attribution, origin):
    if origin is not None and type(origin) is not bool:
        raise ValueError("has_iac_origin must be a boolean or None")
    if attribution is not None:
        if not isinstance(attribution, (list, tuple)) or not 1 <= len(attribution) <= 4:
            raise ValueError("iac_attribution must contain one to four verdicts")
        if any(v not in ("attributed", "ambiguous", "none", "unknown") for v in attribution):
            raise ValueError("invalid iac_attribution verdict")


def _require_iac_receipt(response, pairs, raw_response=False):
    expected = {}
    for key, value in pairs or []:
        if key == "has_iac_origin":
            expected[key] = value == "true"
        elif key == "iac_attribution":
            expected.setdefault(key, []).append(value)
    if not expected:
        return response
    try:
        if raw_response:
            line, separator, body = response.partition("\n")
            prefix = "# lc_iac_filters_v1="
            if not separator or len(line) > 1024 or not line.startswith(prefix):
                raise ValueError("missing receipt")
            encoded = line[len(prefix):].rstrip("\r")
            applied = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True))
        else:
            applied = response.get("applied_iac_filters")
        if json.dumps(applied, sort_keys=True, separators=(",", ":")) != json.dumps(expected, sort_keys=True, separators=(",", ":")):
            raise ValueError("receipt mismatch")
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError("IaC query selectors were not acknowledged by this server version") from None
    return body if raw_response else response


def _finding_query_pairs(
    *,
    has_iac_origin: bool | None = None,
    iac_attribution: list[str] | None = None,
    severity: list[str] | None = None,
    finding_class: list[str] | None = None,
    status: list[str] | None = None,
    account: list[str] | None = None,
    owner: list[str] | None = None,
    owner_pin: list[str] | None = None,
    sla: list[str] | None = None,
    repo: list[str] | None = None,
    image_urn: list[str] | None = None,
    fix_state: list[str] | None = None,
    exploit_band: list[str] | None = None,
    grain: list[str] | None = None,
    cause: str | None = None,
    source: str | None = None,
    reachable: bool | None = None,
    kev: bool | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Assemble the findings worklist selectors shared by list/facets/causes.

    ``owner`` is the one selector here whose EMPTY value is a real
    selection: ``owner=[""]`` asks for the UNASSIGNED bucket, so it must
    reach the wire as ``?owner=`` rather than being dropped. Pass ``None``
    (or ``[]``) for no owner constraint.

    ``repo`` is deliberately NOT like that. A finding with no repository is
    every cloud finding in the estate, which is not a bucket anyone selects,
    so an empty value there matches nothing rather than meaning "unscoped".

    ``source`` is a SCALAR, not a list, because the vocabulary it mirrors is
    the one-word answer ``list_code_repos`` gives per repository — and
    ``"both"``, the value that would otherwise want a list, already means
    "no constraint".

    ``grain`` is the one selector whose ABSENCE is not "unconstrained": see
    :meth:`CloudSec.list_findings` for what the server's default grain
    holds back. Every one of these repeatable keys is forwarded verbatim —
    the vocabularies live at the backend, and a value outside one returns
    an empty page rather than silently widening the read.

    Legacy repeatable selectors are TRUNCATED AT 100 VALUES by the gateway,
    with no error and no signal in the response. A script fanning out over
    more than 100 repositories, owners or image urns must batch them.
    IaC attribution instead rejects more than four or unknown verdicts locally.
    """
    _validate_iac_selectors(iac_attribution, has_iac_origin)
    return _query_pairs(
        iac_attribution=iac_attribution, has_iac_origin=has_iac_origin,
        severity=severity, finding_class=finding_class, status=status,
        account=account, owner=owner, owner_pin=owner_pin, sla=sla,
        repo=repo, image_urn=image_urn, fix_state=fix_state,
        exploit_band=exploit_band, grain=grain, cause=cause,
        source=source, reachable=reachable, kev=kev, q=q,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


# The merged-identity cross-filter, shared verbatim by the identity facet
# rail and the ranked Access list so a facet count describes the
# population the list would return (the empty-tier bucket excepted — the
# rail does not count it; see get_identity_facets).
def _identity_query_pairs(
    *,
    provider: list[str] | None = None,
    account: list[str] | None = None,
    region: list[str] | None = None,
    source: list[str] | None = None,
    kind: list[str] | None = None,
    criticality: list[str] | None = None,
    risk_band: list[str] | None = None,
    mfa: str | None = None,
    admin: bool | None = None,
    external: bool | None = None,
    public: bool | None = None,
    disabled: bool | None = None,
    crown_jewel: bool | None = None,
    can_escalate: bool | None = None,
    dormant_90d: bool | None = None,
    with_sensitive: bool | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Assemble the identity cross-filter shared by facets/access list."""
    return _query_pairs(
        provider=provider, account=account, region=region, source=source,
        kind=kind, criticality=criticality, risk_band=risk_band, mfa=mfa,
        admin=admin, external=external, public=public, disabled=disabled,
        crown_jewel=crown_jewel, can_escalate=can_escalate,
        dormant_90d=dormant_90d, with_sensitive=with_sensitive,
        q=q, cursor=cursor, limit=limit,
    )


# The Data Security (DSPM) cross-filter, shared by the store facets and the
# store list for the same reason.
def _data_store_query_pairs(
    *,
    provider: list[str] | None = None,
    account: list[str] | None = None,
    region: list[str] | None = None,
    store_kind: list[str] | None = None,
    tier: list[str] | None = None,
    data_class: list[str] | None = None,
    sensitivity: bool | None = None,
    exposure: bool | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Assemble the data-store cross-filter shared by facets/list."""
    return _query_pairs(
        provider=provider, account=account, region=region,
        store_kind=store_kind, tier=tier, data_class=data_class,
        sensitivity=sensitivity, exposure=exposure,
        q=q, cursor=cursor, limit=limit,
    )


def _query_run_body(
    named: str | None,
    text: str | None,
    query: dict[str, Any] | None,
    project: str | None,
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
        response = self._org.client.request(
            "GET",
            f"cloudsec/{self.oid}/{path}",
            query_params=query_params or None,
            raw_response=raw_response,
        )
        return _require_iac_receipt(response, query_params, raw_response)

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
        has_iac_origin: bool | None = None,
        iac_attribution: list[str] | None = None,
        severity: list[str] | None = None,
        finding_class: list[str] | None = None,
        status: list[str] | None = None,
        account: list[str] | None = None,
        owner: list[str] | None = None,
        sla: list[str] | None = None,
        repo: list[str] | None = None,
        image_urn: list[str] | None = None,
        fix_state: list[str] | None = None,
        exploit_band: list[str] | None = None,
        grain: list[str] | None = None,
        cause: str | None = None,
        source: str | None = None,
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
            iac_attribution: One to four attributed, ambiguous, none or unknown verdicts.
            has_iac_origin: Recorded origin evidence exists; False is not proof of no IaC.
            severity: Filter values (CRITICAL/HIGH/MEDIUM/LOW/INFO), OR'd.
            finding_class: Filter values (toxic_combination, public_exposure,
                ciem_risk, privilege_escalation, vulnerability, misconfig,
                coverage_gap), OR'd.
            status: Filter values (open/resolved/accepted), OR'd.
                ``resolved`` means the risk is gone (mitigated or a false
                positive); ``accepted`` is a LIVE risk acceptance — the risk
                is still there and an owner signed off on carrying it, so it
                is deliberately NOT rolled into ``resolved``. An acceptance
                that passes its expiry, or that dispositioned an earlier
                occurrence of a finding that closed and recurred, reads
                ``open`` again. The same three values are the keys of the
                ``status`` map returned by :meth:`get_finding_facets`.
            account: Cloud account filter values, OR'd.
            owner: Assigned-owner filter values, OR'd. The EMPTY STRING is
                a real value selecting the UNASSIGNED bucket, so
                ``owner=[""]`` is the untriaged backlog and
                ``owner=["alice@corp.com", ""]`` is "mine or nobody's".
                Pass ``None`` for no owner constraint. Owners are set with
                :meth:`set_finding_owner` and counted by the ``owner``
                facet of :meth:`get_finding_facets`.
            sla: Remediation-SLA state filter values, OR'd:
                ``breached`` (past due), ``due_soon`` (inside the last
                quarter of its own window, clamped to 1-7 days),
                ``on_track``, ``exempt`` (the finding is not open, so the
                clock does not report on it), ``none`` (no SLA clause
                covers it). The state is DERIVED at read time from the
                finding's ``due_at`` and status — there is no built-in
                default SLA, so on an org that has not written an ``sla``
                policy every finding is ``none``. Counted by the ``sla``
                facet of :meth:`get_finding_facets`.
            repo: Source-repository filter values, OR'd, keyed
                ``"<owner>/<name>"`` exactly as :meth:`list_code_repos`
                returns them. This is the AppSec code lane's subject
                selector; cloud findings have no repository, so any repo
                filter excludes them. An unknown repository honestly
                returns nothing rather than widening the read.
            image_urn: Container-image filter values, OR'd. Each value is
                the FULL image node urn — the ``urn`` field of a
                :meth:`list_container_images` row (or ``image.urn`` from
                :meth:`get_container_image`), never a bare ``sha256:...``
                digest. The server matches on the literal urn, so a digest
                or a partial string matches nothing and says so with an
                empty page rather than an error. This is how you pivot
                from an image to the findings on it.
            fix_state: Fix-availability filter values, OR'd:
                ``fix_available``, ``no_fix``, ``unknown``. ``unknown`` is
                a first-class value and is NOT a synonym for ``no_fix`` —
                a fixed version nobody collected is not a fix that does
                not exist. ``no_fix`` is asserted only on a positive
                signal (a malicious package, or a VEX assertion that makes
                the fix moot).
            exploit_band: Exploit-urgency filter values, OR'd, most urgent
                first: ``kev_overdue``, ``kev_due``, ``exploit_likely``,
                ``exploit_probable``, ``elevated``, ``baseline``, ``none``.
                KEV dominates EPSS; a KEV entry whose remediation due date
                is missing or unparseable bands ``kev_due`` and never
                ``kev_overdue``. ``none`` selects findings with no exploit
                signal at all.
            grain: Which UNIT OF WORK a vulnerability finding states, OR'd:
                ``package`` (upgrade <pkg> on host X, closing N CVEs),
                ``cve`` (one finding per CVE, with the affected resources
                as pivot targets), ``other`` (everything else, including
                the container-image and source-repository vulnerability
                lanes).

                UNLIKE every other selector here, OMITTING this is NOT
                "no constraint". The default worklist leads with the
                ``package`` grain and EXCLUDES the per-CVE rollups a
                package finding already states pair for pair, so the same
                pair is never counted twice under two rule ids. Pass
                ``grain=["cve"]`` to reach every per-CVE finding including
                those, or both values for the unfiltered union. The
                ``grain`` facet of :meth:`get_finding_facets` always
                reports the full per-grain population, so you can see what
                the default is holding back.
            cause: Exact shared-fix cause key, as
                :meth:`list_finding_causes` returns it. A SCALAR, not a
                list. An unknown key returns no findings.
            source: The code lane's PRODUCER filter — which scanner found
                the finding. ``"hosted"`` is the scan LimaCharlie ran,
                ``"ingest"`` a document your own pipeline pushed (SARIF,
                CycloneDX, or a local ``cloudsec code scan``), ``"other"``
                a producer that is neither — today the source control's own
                detectors — and ``"none"`` a finding with no code
                provenance at all, which on a cloud estate is nearly every
                row. ``"both"`` (and ``None``) apply no constraint.

                It is applied INSIDE the server's keyset query, so a page
                and a count under it describe the same set. An unrecognised
                value is REJECTED by the server with an error naming it,
                never quietly ignored: this selector is a scalar, so a
                dropped value and an absent one are the same thing on the
                wire, and absent means unconstrained.
            reachable: Only findings on (non-)reachable resources.
            kev: Only findings with (without) a KEV vulnerability.
            q: Substring search.
            sort: Server-side sort key: ``lc_risk`` (the default),
                ``severity``, ``first_seen``, or ``due_at``. ``due_at``
                is the one key that defaults to ASCENDING (soonest due
                first) and it places findings with no due date LAST rather
                than excluding them.
            order: ``desc`` (the default, except for ``due_at``) or ``asc``.
            cursor: Keyset-pagination token from a previous page.
            limit: Page size (server clamps to 1000).

        Returns:
            ``{"findings": [...], "next_cursor": str}``.
        """
        return self._get("findings", _finding_query_pairs(
            iac_attribution=iac_attribution, has_iac_origin=has_iac_origin,
            severity=severity, finding_class=finding_class, status=status,
            account=account, owner=owner, sla=sla, repo=repo,
            image_urn=image_urn, fix_state=fix_state,
            exploit_band=exploit_band, grain=grain, cause=cause,
            source=source, reachable=reachable, kev=kev, q=q,
            sort=sort, order=order, cursor=cursor, limit=limit,
        ))

    def get_finding_facets(
        self,
        *,
        has_iac_origin: bool | None = None,
        iac_attribution: list[str] | None = None,
        severity: list[str] | None = None,
        finding_class: list[str] | None = None,
        status: list[str] | None = None,
        account: list[str] | None = None,
        owner: list[str] | None = None,
        owner_pin: list[str] | None = None,
        sla: list[str] | None = None,
        repo: list[str] | None = None,
        image_urn: list[str] | None = None,
        fix_state: list[str] | None = None,
        exploit_band: list[str] | None = None,
        grain: list[str] | None = None,
        cause: str | None = None,
        source: str | None = None,
        reachable: bool | None = None,
        kev: bool | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """Cross-filtered facet counts for the findings worklist.

        Takes the same filter selectors as :meth:`list_findings`; each
        facet dimension is counted against the other active filters.

        Args:
            iac_attribution: One to four attributed, ambiguous, none or unknown verdicts.
            has_iac_origin: Recorded origin evidence exists; False is not proof of no IaC.
            owner_pin: Owners to keep in the ``owner`` facet even when they
                would not rank into it. NOT a filter — it selects no rows
                and changes no count. The ``owner`` facet is capped at the
                top 50 owners by count (``owner_truncated`` reports whether
                any were dropped), so pin the calling user to keep their own
                row reachable on an estate with more owners than the cap.
                The unassigned bucket is always included and outranks every
                pin.

                The guarantee is BOUNDED BY THAT CAP, not absolute: the
                pins and the active ``owner`` filter share the 50 slots
                (and the unassigned bucket takes one), so past ~50
                combined values a pin can still be dropped — and
                ``owner_truncated`` cannot distinguish that from ordinary
                tail truncation. Render a pinned-but-absent owner as zero
                rather than assuming the map is complete.

            sla: Remediation-SLA state filter values — see
                :meth:`list_findings`. The ``sla`` facet always carries
                EVERY state key, zeroes included, so a caller never has to
                invent a missing count (a ``breached`` chip that vanishes
                reads as "the feature is off", not "you are on top of it").
            repo: Source-repository filter values — see
                :meth:`list_findings`. The ``repo`` facet counts the code
                lane's repositories and NEVER the non-repository findings
                (there is no empty-key bucket holding the cloud estate). It
                is capped at the top 200 by count, with any actively
                selected repository pinned into it; ``repo_truncated``
                reports whether any were dropped.
            source: The code lane's PRODUCER filter — which scanner found
                the finding. ``"hosted"`` is the scan LimaCharlie ran,
                ``"ingest"`` a document your own pipeline pushed (SARIF,
                CycloneDX, or a local ``cloudsec code scan``), ``"other"``
                a producer that is neither — today the source control's own
                detectors — and ``"none"`` a finding with no code
                provenance at all, which on a cloud estate is nearly every
                row. ``"both"`` (and ``None``) apply no constraint.

                It is applied INSIDE the server's keyset query, so a page
                and a count under it describe the same set. An unrecognised
                value is REJECTED by the server with an error naming it,
                never quietly ignored: this selector is a scalar, so a
                dropped value and an absent one are the same thing on the
                wire, and absent means unconstrained.

                The ``source`` facet is the one dimension here whose values
                SUM EXACTLY TO ``total`` — every key is always present,
                zeroes included — which is what lets a hosted-vs-pushed
                split be quoted as a share of the estate rather than of one
                page. That holds only when ``source`` is NOT itself
                filtered: like every dimension it is counted with its own
                filter excluded while ``total`` applies it, so under
                ``source="hosted"`` the map still sums to the unfiltered
                population. Compute a share on an unfiltered read.

                The key is ABSENT if the server has the facet turned off.
                That never means zero — read it with ``.get("source")`` and
                render nothing rather than a 0% split.

        Returns:
            ``{"facets": {..., "owner": {"": 12, "alice@corp.com": 3},
            "owner_truncated": false, "sla": {"breached": 4, "due_soon": 1,
            "on_track": 20, "exempt": 0, "none": 900}}}``.
        """
        return self._get("findings/facets", _finding_query_pairs(
            iac_attribution=iac_attribution, has_iac_origin=has_iac_origin,
            severity=severity, finding_class=finding_class, status=status,
            account=account, owner=owner, owner_pin=owner_pin, sla=sla,
            repo=repo, image_urn=image_urn, fix_state=fix_state,
            exploit_band=exploit_band, grain=grain, cause=cause,
            source=source, reachable=reachable, kev=kev, q=q,
        ))

    def list_finding_causes(
        self,
        *,
        has_iac_origin: bool | None = None,
        iac_attribution: list[str] | None = None,
        cause: str | None = None,
        severity: list[str] | None = None,
        finding_class: list[str] | None = None,
        status: list[str] | None = None,
        account: list[str] | None = None,
        owner: list[str] | None = None,
        sla: list[str] | None = None,
        repo: list[str] | None = None,
        image_urn: list[str] | None = None,
        fix_state: list[str] | None = None,
        exploit_band: list[str] | None = None,
        grain: list[str] | None = None,
        source: str | None = None,
        reachable: bool | None = None,
        kev: bool | None = None,
        q: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Findings grouped by their CAUSE (the shared-fix rollup).

        A cause is the mutable object — a firewall rule, the principal an
        attack path's grants land on — whose single edit resolves every
        finding grouped under it, so a worklist can be worked by fix
        instead of by row. Takes the same filter selectors as
        :meth:`list_findings`, so a rollup can be scoped exactly like the
        list it summarizes.

        **Only CAUSE-BEARING findings are in scope, which is a small slice
        of an estate.** Causes are stamped on the attack-path classes;
        vulnerability findings — roughly 90% of a typical estate —
        deliberately carry none, because a per-package cause would evict
        every attack-path fix from the ranking and would cost the sparse
        index this rollup is fast because of. So the counts here never sum
        to the worklist total, and a rollup scoped to a class that carries
        no cause (``finding_class=["vulnerability"]``) legitimately returns
        ``{"causes": [], "distinct": 0}`` — that is "no shared fix on this
        class", not "no findings".

        Args:
            iac_attribution: One to four attributed, ambiguous, none or unknown verdicts.
            has_iac_origin: Recorded origin evidence exists; False is not proof of no IaC.
            cause: One cause key. Set it for the count of that cause alone,
                returned as a single-entry ``causes`` — or an EMPTY
                ``causes`` when no finding under the filter carries it, so
                read the list rather than indexing ``causes[0]``. Clamped
                to 512 chars server-side.
            limit: Rollup size when ``cause`` is omitted (default 20,
                server cap 200). Not a page size — the rollup is not
                paginated, and ``distinct`` reports the tail it hides.

        Returns:
            ``{"causes": [{"key": str, "name": str, "kind": str,
            "count": int}, ...], "distinct": int}``. ``kind`` is an OPEN
            vocabulary (``firewall_rule``, ``entitled_identity``, ...) that
            grows server-side — treat an unrecognized value as "some
            object" rather than assuming a class. ``distinct`` is the total
            number of causes matching the filter and MAY exceed
            ``len(causes)`` when ``limit`` truncates.

            A count is a whole-population figure, not a capped one: it does
            not degrade to a lower bound the way folding a paginated
            worklist client-side does. It is computed on each finding's
            STORED status, though, which lags a disposition that expired on
            its own — an acceptance past its expiry still counts as
            accepted until the projector's periodic backstop rewrites it,
            while reading that finding returns it as open. Treat a count as
            a ranking and scale signal; the finding's own read is the
            authority on its status.
        """
        return self._get("findings/causes", _finding_query_pairs(
            iac_attribution=iac_attribution, has_iac_origin=has_iac_origin,
            severity=severity, finding_class=finding_class, status=status,
            account=account, owner=owner, sla=sla, repo=repo,
            image_urn=image_urn, fix_state=fix_state,
            exploit_band=exploit_band, grain=grain, cause=cause,
            source=source, reachable=reachable, kev=kev, q=q,
            limit=limit,
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
                (owner/ticket are kept). ``accepted`` puts the finding in
                the ``accepted`` status — a live risk acceptance, not a
                resolution.
            reason: Optional operator note.
            expires_at: Unix seconds; only meaningful for ``accepted``, and
                OPTIONAL — omitting it accepts the risk permanently, which
                is a supported disposition. When set, the finding reopens
                at that instant.

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

    def get_identity_facets(
        self,
        *,
        provider: list[str] | None = None,
        account: list[str] | None = None,
        region: list[str] | None = None,
        source: list[str] | None = None,
        kind: list[str] | None = None,
        criticality: list[str] | None = None,
        risk_band: list[str] | None = None,
        mfa: str | None = None,
        admin: bool | None = None,
        external: bool | None = None,
        public: bool | None = None,
        disabled: bool | None = None,
        crown_jewel: bool | None = None,
        can_escalate: bool | None = None,
        dormant_90d: bool | None = None,
        with_sensitive: bool | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """CIEM identity facet counts.

        Takes the same cross-filter as :meth:`list_identity_access`, so a
        facet count describes the population that list would return — with
        the single documented exception of the no-tier bucket under
        ``criticality`` (see below). With no selectors the response is the whole-population
        rollup. Each dimension is counted under the OTHER active
        selectors but not its own, so a value's count is exactly how many
        rows selecting it would list.

        Args:
            provider: Producing sweeps, OR'd (alias of ``source``).
            account, region: Placement filters, OR'd. These two are served
                from the projector's merged view; on a tenant whose view
                has not been built yet the call FAILS rather than
                returning a misleading zero.
            source: Producing sweeps (``okta``, ``gcp``,
                ``google_workspace``, ...), OR'd.
            kind: Identity kinds (``user``, ``service_account``, ``group``,
                ``ai_agent``, ...), OR'd.
            criticality: Crown-jewel tiers, OR'd. A CLOSED vocabulary —
                ``critical`` / ``high`` / ``medium`` / ``low`` — plus the
                empty string, which selects identities with no tier
                assigned. An unrecognized tier matches nothing rather than
                erroring, so a typo reads as "no such identities". The
                empty-tier bucket is the ONE selection the facet rail does
                not count (the criticality facet skips it), so it is the
                one case where a facet count cannot predict the list.
            risk_band: Risk bands, OR'd — ``critical`` / ``high`` /
                ``medium`` / ``low``, the band token rather than a numeric
                range. Also closed, and also fails closed: an unrecognized
                band selects nothing.
            mfa: ``on`` | ``off`` | ``unknown``. ``unknown`` is everyone
                the MFA question does not apply to (no identity-provider
                observation, or non-human) — it is NOT ``off``.
            admin, external, public, disabled, crown_jewel, can_escalate,
                dormant_90d, with_sensitive: Tri-state — ``None`` leaves
                the dimension unconstrained, which is NOT the same as
                ``False`` (which pins it).
            q: Substring filter over the identity's urn/email/kind.

        Returns:
            ``{"facets": {...}}``.
        """
        return self._get("ciem/facets", _identity_query_pairs(
            provider=provider, account=account, region=region, source=source,
            kind=kind, criticality=criticality, risk_band=risk_band, mfa=mfa,
            admin=admin, external=external, public=public, disabled=disabled,
            crown_jewel=crown_jewel, can_escalate=can_escalate,
            dormant_90d=dormant_90d, with_sensitive=with_sensitive, q=q,
        ))

    def list_identity_access(
        self,
        *,
        provider: list[str] | None = None,
        account: list[str] | None = None,
        region: list[str] | None = None,
        source: list[str] | None = None,
        kind: list[str] | None = None,
        criticality: list[str] | None = None,
        risk_band: list[str] | None = None,
        mfa: str | None = None,
        admin: bool | None = None,
        external: bool | None = None,
        public: bool | None = None,
        disabled: bool | None = None,
        crown_jewel: bool | None = None,
        can_escalate: bool | None = None,
        dormant_90d: bool | None = None,
        with_sensitive: bool | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """One page of the Access screen's identity population.

        The same per-principal effective-access rollup rows
        :meth:`get_public_access` carries (grant / privileged /
        sensitive-reach counts, posture facets, risk score), but
        server-filtered and pageable instead of a risk-ranked top-N.
        Takes the same selectors as :meth:`get_identity_facets` — see
        there for what each one means.

        Ranked by risk score descending by default. A walk that spans a
        projector recompute can move a row across the cursor, so use it
        for browsing, not for exact exports.

        Args:
            cursor, limit: Keyset pagination (default page 500).

        Returns:
            ``{"principals": [...], "next_cursor": str | None}``, plus
            ``served_from`` / ``data_as_of`` when the page came from the
            projector's materialized merged view.
        """
        return self._get("ciem/identities", _identity_query_pairs(
            provider=provider, account=account, region=region, source=source,
            kind=kind, criticality=criticality, risk_band=risk_band, mfa=mfa,
            admin=admin, external=external, public=public, disabled=disabled,
            crown_jewel=crown_jewel, can_escalate=can_escalate,
            dormant_90d=dormant_90d, with_sensitive=with_sensitive,
            q=q, cursor=cursor, limit=limit,
        ))

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
        has_iac_origin: bool | None = None,
        resource_type: str | None = None,
        provider: str | None = None,
        account: str | None = None,
        region: str | None = None,
        q: str | None = None,
        account_empty: bool | None = None,
        account_unscoped: bool | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List the cloud resource inventory.

        Args:
            has_iac_origin: Recorded origin evidence exists; False is not proof of no IaC.
            resource_type: Filter by resource type (the ``type`` selector).
            provider: Filter by the producing provider sweep (e.g. ``gcp``,
                ``aws``, ``okta``, ``google_workspace``).
            account, region: Scalar filters.
            q: Substring search.
            account_empty: When ``True``, select only resources whose account
                is empty. Omit this and ``account`` to span the whole estate.
            account_unscoped: Deprecated alias for ``account_empty``. It is
                retained for compatibility with older gateways and callers.
            cursor, limit: Keyset pagination.

        Returns:
            ``{"resources": [...], "next_cursor": str}``.
        """
        _validate_iac_selectors(None, has_iac_origin)
        selector = _inventory_account_selector(account_empty, account_unscoped)
        return self._get("inventory", _query_pairs(
            type=resource_type, provider=provider, account=account,
            region=region, q=q, has_iac_origin=has_iac_origin,
            **selector,
            cursor=cursor, limit=limit,
        ))

    def get_inventory_facets(self, *, has_iac_origin: bool | None = None) -> dict[str, Any]:
        """Get inventory facet counts under an optional origin selector.

        Args:
            has_iac_origin: Recorded origin evidence exists; False is not proof of no IaC.

        Returns:
            dict: Cross-filtered type, account, region and available origin buckets.
        """
        _validate_iac_selectors(None, has_iac_origin)
        return self._get("inventory/facets", _query_pairs(has_iac_origin=has_iac_origin))

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

    def get_data_security_facets(
        self,
        *,
        provider: list[str] | None = None,
        account: list[str] | None = None,
        region: list[str] | None = None,
        store_kind: list[str] | None = None,
        tier: list[str] | None = None,
        data_class: list[str] | None = None,
        sensitivity: bool | None = None,
        exposure: bool | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """DSPM data-store facet counts (total/sensitive/public, store kinds).

        Takes the same cross-filter as :meth:`list_data_stores`, so the
        counts describe the population that list would return. Each
        dimension is counted under the OTHER active selectors but not its
        own. With no selectors the response is the whole-population
        rollup.

            ONE exception to that: the no-tier bucket. Both this rail and
            the identity rail skip the empty value when counting, so
            selecting it (``tier=[""]``) returns rows the facets never
            counted. Every other value's count predicts its list exactly.

        Args:
            provider, account, region: Placement filters, OR'd within a
                key. An empty-string value selects the unscoped bucket.
            store_kind: Store kinds (``bucket``, ``sql_instance``, ...),
                OR'd.
            tier: Criticality tiers, OR'd. Same closed vocabulary as the
                identity filter's ``criticality`` — ``critical`` /
                ``high`` / ``medium`` / ``low``, plus the empty string for
                stores with no tier assigned. That empty-tier bucket is the
                ONE selection this rail does not count (the tier facet
                skips it), so it is the one case where a facet count cannot
                predict the list.
            data_class: Content classes (``pii``, ``secrets``, ...), OR'd.
            sensitivity: Tri-state — ``True`` only sensitive stores,
                ``False`` only non-sensitive, ``None`` unconstrained.
            exposure: Tri-state — ``True`` only publicly-exposed stores,
                ``False`` only non-public, ``None`` unconstrained.
            q: Substring filter over the store's name/urn.

        Returns:
            ``{"facets": {...}}``.
        """
        return self._get("data-security/facets", _data_store_query_pairs(
            provider=provider, account=account, region=region,
            store_kind=store_kind, tier=tier, data_class=data_class,
            sensitivity=sensitivity, exposure=exposure, q=q,
        ))

    def list_data_stores(
        self,
        *,
        provider: list[str] | None = None,
        account: list[str] | None = None,
        region: list[str] | None = None,
        store_kind: list[str] | None = None,
        tier: list[str] | None = None,
        data_class: list[str] | None = None,
        sensitivity: bool | None = None,
        exposure: bool | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """One keyset page of the org's data stores (DSPM row list).

        Served from the materialized graph store under the same selectors
        as :meth:`get_data_security_facets` — see there for what each one
        means — so the filtered list stays exact at any estate size
        instead of client-filtering a capped walk. Ordered by the stored
        key, which is stable and safe for a full walk.

        Args:
            cursor, limit: Keyset pagination (server caps the page at
                1000).

        Returns:
            ``{"stores": [{"urn", "name", "store_kind", "provider",
            "account", "region", "is_public", "is_sensitive",
            "criticality", "data_classes"}, ...], "next_cursor": str}``.
        """
        return self._get("data-security/stores", _data_store_query_pairs(
            provider=provider, account=account, region=region,
            store_kind=store_kind, tier=tier, data_class=data_class,
            sensitivity=sensitivity, exposure=exposure,
            q=q, cursor=cursor, limit=limit,
        ))

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
        surface: str | None = None,
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
            surface: Policy surface whose capability and token vocabulary must
                be validated (for example ``coverage`` or
                ``classification.compute``). New authoring clients should set it.
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
        if surface is not None:
            body["surface"] = surface
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
        project: str | None = None,
    ) -> dict[str, Any]:
        """Run a graph query. Provide exactly one of named / text / query.

        Args:
            named: A query-pack name (see :meth:`list_queries`).
            text: A text query.
            query: A raw DSL object.
            project: Optional drawable projection; the only value is
                ``"graph"``, which adds an induced subgraph (``nodes`` +
                ``edges``) over the matched URNs next to the rows.

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
    # Compliance v2 (immutable runs, attestations, drift, schedules)
    # ------------------------------------------------------------------
    #
    # :meth:`get_compliance` above is the LIVE, point-in-time assessment:
    # ask it a question and it answers about the estate as it is now,
    # keeping nothing. The v2 surface here is the audit-grade half — an
    # assessment is PERSISTED as an immutable run, manual evidence is
    # recorded as append-only attestation revisions, control-state changes
    # accumulate as a drift stream, and a run can be rendered to a
    # deterministic artifact months later. Use it when somebody has to be
    # able to prove what was true on a date.

    def create_compliance_run(
        self,
        *,
        framework: str | None = None,
        assignment: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Assess compliance and PERSIST the result as an immutable run.

        Args:
            framework: Framework id for an estate-wide run. Defaults to
                the backend's default framework when neither this nor
                ``assignment`` is given.
            assignment: A named assignment. Its own framework SUPERSEDES
                ``framework``, so a ``framework`` passed alongside it is
                silently discarded. An unknown name is an error.
            run_id: An idempotency key. Omit and every call performs a
                FULL assessment and writes a NEW run — the generated id
                embeds the current time, so two calls a second apart
                produce two runs. Pass one and a retry replays the stored
                run verbatim instead of re-assessing, provided the
                assignment, framework, scope and assignment revision all
                still match; if any of them moved, the call is refused
                rather than quietly assessing something else under an id
                you already published. (The generated id is a hash over
                the scope AND the current time, so it is unpredictable
                and not readable back — it is an identity, not a label.)

        Returns:
            ``{"run": {...}, "report": {...}, "assignment": {...}}``.
            ``run`` carries the identity an auditor needs —  ``run_id``,
            ``framework_id``, ``framework_version``, ``catalog_hash``,
            ``rule_pack_hash``, ``assignment_revision``, ``scope_hash``,
            ``result_set_hash``, ``scan_generations``, ``status``,
            ``started_at``, ``completed_at``, ``summary`` — and ``report``
            the framework info plus one ``ControlResult`` per control.

        Note:
            This is the expensive call on this surface: it evaluates every
            control against the estate. The reads
            (:meth:`list_compliance_runs`, :meth:`export_compliance_run`)
            are what you poll; this is what you schedule.

            ``rule_pack_hash`` reads the literal ``"unobserved"`` — not an
            empty string — when no detector run reported one.

            In ``report.summary``, ``score`` is computed over ASSESSABLE
            controls only and ``low_coverage`` is true when that covers
            less than half of the gradeable ones. Never render the score
            without the coverage beside it.

            Check ``applicable`` FIRST. False means nothing was assessable
            at all, in which case ``score`` is 0 — and that 0 does not
            mean "failed everything". ``low_coverage`` is also false in
            that case, because it is only computed when ``applicable`` is
            true, so a false ``low_coverage`` is reassuring only once you
            know something was assessed.
        """
        body: dict[str, Any] = {}
        for key, value in (
            ("framework", framework),
            ("assignment", assignment),
            ("run_id", run_id),
        ):
            if value:
                body[key] = value
        return self._post("compliance/v2", body)

    def list_compliance_runs(
        self,
        *,
        run_id: str | None = None,
        framework: str | None = None,
        assignment: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List completed compliance runs, or read one run in full.

        Args:
            run_id: Read ONE run and its historical control snapshot.
                When given, the other selectors are ignored.
            framework: Framework id. Defaults to the backend default.
            assignment: Assignment name. Defaults to the whole estate.
            limit: Maximum runs (backend default 50, max 200; a larger
                ask is reduced to the default rather than clamped to the
                max).

        Returns:
            With ``run_id``: ``{"run": {...}, "controls": [...]}`` — note
            the key is ``controls``, not ``report``, and the results are
            RECONSTRUCTED from the drift stream rather than stored whole.
            Without it: ``{"runs": [{...}, ...]}``, only ``completed``
            runs, newest first.

        Note:
            Unlike :meth:`create_compliance_run`, the list does NOT derive
            the framework from the assignment. Passing an assignment
            without its matching framework returns an empty list, not an
            error — pass both, or neither.
        """
        return self._get("compliance/runs", _query_pairs(
            run_id=run_id, framework=framework, assignment=assignment,
            limit=limit,
        ))

    def list_compliance_attestations(
        self,
        *,
        framework: str | None = None,
        assignment: str | None = None,
    ) -> dict[str, Any]:
        """List the attestation revisions for one assignment + framework.

        Returns:
            ``{"attestations": [...]}`` — EVERY revision, not just the
            current ones, ordered by attestation id then revision
            descending. Only the highest revision of each id counts
            toward an assessment; the earlier ones are the audit trail.
        """
        return self._get("compliance/attestations", _query_pairs(
            framework=framework, assignment=assignment,
        ))

    def create_compliance_attestation(
        self,
        attestation: dict[str, Any],
        *,
        framework: str | None = None,
        assignment: str | None = None,
    ) -> dict[str, Any]:
        """Write one attributed, immutable attestation revision.

        Manual evidence for a control no detector can grade. Attestations
        are APPEND-ONLY: a revision is inserted, never updated, so
        re-writing an existing ``(id, revision)`` fails rather than
        rewriting a record somebody's name is on.

        Args:
            attestation: The revision. REQUIRED: ``id``, ``revision``
                (an integer ≥ 1), ``control_key``, ``outcome`` (``pass``,
                ``fail`` or ``not_applicable``), ``effective_at`` and
                ``expires_at`` (which must be after ``effective_at``).

                ``approved_at`` is OPTIONAL to write and load-bearing to
                use: an attestation without it is stored and returned but
                never counts toward a control, so omitting it writes a
                record that silently does nothing. ``rationale`` is not
                validated either, but it is the only field that says WHY
                a human asserted this — write it.

                Also optional: ``requirement_id`` (empty matches any
                requirement of the control), ``evidence_refs``,
                ``compensating_control_ref``, ``supersedes_id`` and
                ``revoked_at``. You may also pass
                ``expected_scope_hash`` and ``expected_framework_version``
                as optimistic preconditions — the write is refused if the
                scope or catalog moved under you.

                The server owns the attribution: ``assessor``,
                ``approver``, ``revoked_by``, ``created_at``, ``oid``,
                ``assignment``, ``framework_id``, ``framework_version``
                and ``scope_hash`` are stamped from the calling identity
                and the resolved scope, overwriting anything you send.
            framework: Framework id. Defaults to the backend default.
            assignment: Assignment name. Defaults to the whole estate.

        Returns:
            ``{"attestations": [...]}`` — the full list after the write.

        Note:
            ``evidence_refs`` entries must be ``https://``, ``output://``
            or ``ticket://`` urls with no embedded credentials.

            Only a REVOCATION is pinned to exactly ``previous + 1``,
            because the server copies that specific prior revision
            forward. An ordinary superseding revision is merely INSERTED,
            so its ``(id, revision)`` must be unused — and since only the
            highest revision of an id is ever consulted, one written
            below the current high-water mark is accepted and then inert.
            Nothing refuses it, so raise the number yourself.

            REVOCATION IS A LATER REVISION, never a delete. Re-send the
            same ``id`` with ``revision`` exactly one higher and a
            ``revoked_at``; everything else in the body is ignored,
            because the server copies the previous revision forward and
            overlays only those two fields. That keeps the original
            author's attribution intact and records yours separately.

            An attestation only counts toward a control while it is
            approved, not revoked, and inside its validity window — AND
            while its framework version, control key and scope hash still
            match the assessment. Editing an assignment's scope changes
            the scope hash and silently orphans the attestations written
            under the old one.
        """
        return self._post(
            "compliance/attestations",
            attestation,
            _query_pairs(framework=framework, assignment=assignment),
        )

    def list_compliance_events(
        self,
        *,
        assignment: str | None = None,
        days: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """The compliance drift stream: material control-state changes.

        Args:
            assignment: Assignment name. Defaults to the whole estate.
                There is deliberately no framework selector — events are
                keyed on the assignment alone.
            days: Lookback. Backend default 90, ceiling 3650 — and an
                ask ABOVE the ceiling falls back to the DEFAULT rather
                than clamping to it, so ``days=5000`` is 90 days, not
                3650.
            limit: Maximum events. Backend default 200, ceiling 1000,
                with the same fall-back-to-default behaviour.

        Returns:
            ``{"events": [{"event_id", "oid", "assignment",
            "framework_id", "control_key", "run_id",
            "previous_fingerprint", "fingerprint", "occurred_at",
            "result"}, ...]}``, newest first.

        Note:
            This is a CHANGE-ONLY stream. An event is appended only when a
            control's result fingerprint differs from its previous state,
            so a control that stayed PASS across ten runs produces one
            event, not ten. An empty window means "nothing moved", never
            "nothing ran". ``previous_fingerprint`` is empty on a
            control's first event.
        """
        return self._get("compliance/events", _query_pairs(
            assignment=assignment, days=days, limit=limit,
        ))

    def export_compliance_run(
        self,
        run_id: str,
        *,
        fmt: str | None = None,
        brand: str | None = None,
    ) -> dict[str, Any]:
        """Render a stored compliance run as a deterministic artifact.

        Args:
            run_id: The immutable run id, as
                :meth:`list_compliance_runs` returns it.
            fmt: ``json`` (the default), ``csv`` or ``pdf``. Anything else
                is refused by name.
            brand: PDF only — the heading. Defaults to "LimaCharlie Cloud
                Security".

        Returns:
            ``{"format": str, "content": str, "filename": str}``.
            ``content`` is the document's bytes, BASE64-ENCODED on this
            JSON transport — decode it before writing a file, including
            for ``json`` and ``csv``.

        Note:
            The export reads the STORED run, never the live estate, and
            the JSON snapshot deliberately carries no generation
            timestamp. Exporting the same run id a year from now returns
            the same bytes — which is the point.

            The PDF is an executive handoff, one line per control, with
            non-ASCII characters replaced. Use ``json`` or ``csv`` when
            something downstream has to parse it.
        """
        return self._get("compliance/export", _query_pairs(
            run_id=run_id, format=fmt, brand=brand,
        ))

    def list_compliance_schedules(self) -> dict[str, Any]:
        """List the org's recurring compliance assessment schedules.

        Returns:
            ``{"schedules": [{"id", "oid", "assignment", "framework_id",
            "owner", "cadence", "delivery", "destination_ref", "formats",
            "enabled", "next_run_at", "last_run_id", "last_error",
            "revision", "created_by", "updated_by", "updated_at"}, ...]}``.
        """
        return self._get("compliance/schedules")

    def set_compliance_schedule(self, schedule: dict[str, Any]) -> dict[str, Any]:
        """Create or revise a recurring compliance assessment schedule.

        Args:
            schedule: The schedule. Required: ``id``, ``assignment``,
                ``framework_id``, ``owner``, ``cadence``
                (``weekly`` or ``monthly``), ``delivery`` (``output``,
                ``email`` or ``webhook``), ``destination_ref``,
                ``formats`` (a non-empty list of ``json``/``csv``/``pdf``
                with no duplicates), ``next_run_at``, and ``revision``
                (an integer ≥ 1). ``enabled`` is optional.

                ``destination_ref`` MUST be an ``output://`` or
                ``secret://`` reference. Credentials and webhook secrets
                are never carried inline.

        Returns:
            ``{"schedules": [...]}`` — the full list after the write.

        Note:
            ``revision`` is an optimistic-concurrency token, not a
            version label: an edit must RAISE it (any higher value, not
            strictly ``+1``). A lower revision is refused; the same
            revision is an idempotent no-op if the content is identical
            and a refusal if it is not. ``created_by`` and ``updated_by``
            are stamped from the calling identity, and ``created_by`` on
            an existing schedule is immutable — the stored value wins.
        """
        return self._post("compliance/schedules", schedule)

    def get_azure_scope_hierarchy(self) -> dict[str, Any]:
        """Azure scope containment evidence (tenant → … → resource).

        Returns:
            ``{"edges": [{"parent_urn", "child_urn", "source",
            "observed_at"}, ...], "traversable": false}``, sorted by
            parent then child. ``source`` and ``observed_at`` are omitted
            when not recorded.

        Note:
            ``traversable: false`` is a CONTRACT, not a status that might
            change. Containment is stored outside the property graph on
            purpose: it can explain inherited authorization, but it must
            never become a free traversal step in a graph query, because
            "contained by" is not "can reach".
        """
        return self._get("azure/scope-hierarchy")

    # ------------------------------------------------------------------
    # AppSec code lane (repositories, scan status, SBOM)
    # ------------------------------------------------------------------

    def list_code_repos(
        self,
        *,
        q: str | None = None,
        has_findings: bool | None = None,
        provider: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List the org's source repositories as the code lane sees them.

        Args:
            q: Case-insensitive substring over the repository key
                (``"<owner>/<name>"``) and urn.
            has_findings: ``True`` keeps only repositories with at least one
                OPEN finding, ``False`` only those with none. ``None`` (the
                default) leaves the dimension unconstrained — note that
                ``False`` is a real selection, not "no filter".
            provider: Source-control provider (e.g. ``github``). Omit for
                every provider that produces repositories.
            cursor: Keyset-pagination token from a previous page.
            limit: Page size (default 100, server clamps to 500).

        Returns:
            ``{"repos": [...], "next_cursor": str}``. Each entry carries
            ``repo`` (the ``"<owner>/<name>"`` key every other code call
            takes), ``urn``, ``owner``, ``provider``, the source-control
            facts the connector collected, the code-scan state, and the open
            finding rollup (``open_findings``, ``findings_by_class``,
            ``findings_by_severity``, ``top_severity``).

            ``scan_status`` is ``scanned``, ``partial`` or ``unknown``.
            ``partial`` means the scan tripped a limit, so the finding set is
            INCOMPLETE and must not be read as a clean bill. ``unknown``
            means this surface has no scan state for the repository and says
            so rather than implying it was never scanned; a machine-readable
            ``scan_status_reason`` accompanies it. The authoritative view of
            the RUN is :meth:`get_code_status`.

        Note:
            A page can come back SHORT while ``next_cursor`` is still set —
            the cursor, not the page length, says whether the walk is done.
            Use :meth:`iter_code_repos` to walk it correctly.
        """
        return self._get("code/repos", _query_pairs(
            q=q, has_findings=has_findings, provider=provider,
            cursor=cursor, limit=limit,
        ))

    def iter_code_repos(self, **selectors: Any):
        """Yield every repository matching the selectors, page by page.

        Wraps :meth:`list_code_repos` and follows ``next_cursor`` to the end,
        which is the only correct way to walk this endpoint: a filtered page
        may be short without being the last one, so a caller that stops on a
        short page silently truncates its own inventory.
        """
        selectors.pop("cursor", None)
        cursor: str | None = None
        while True:
            page = self.list_code_repos(cursor=cursor, **selectors)
            for repo in page.get("repos") or []:
                yield repo
            cursor = page.get("next_cursor") or None
            if not cursor:
                return

    def get_code_status(self) -> dict[str, Any]:
        """Code-lane run status and lane-wide finding totals.

        Returns:
            ``{"code": [...], "any_running": bool, "totals": {...}}``. Each
            ``code`` entry is one source-control connection's
            ``code:<provider>`` scan row (``is_running``, ``started_at``,
            ``completed_at``, ``last_stats``, ``last_error``); ``totals``
            carries ``open_findings``, ``by_class`` and
            ``repos_with_findings``.

            An EMPTY ``code`` list means no retained run status is available.
            It does not mean the lane is off — that is a property of the
            org's ``code_scanning`` policy record, not of this call.
        """
        return self._get("code/status")

    def get_code_sbom(
        self, repo: str, *, provider: str | None = None,
    ) -> dict[str, Any]:
        """Get a short-lived signed download link for a repository's SBOM.

        Args:
            repo: The repository key ``"<owner>/<name>"`` as
                :meth:`list_code_repos` returns it.
            provider: The source-control provider the key belongs to;
                defaults to ``github`` server-side.

        Returns:
            ``{"repo": str, "urn": str, "sbom": {...} | None,
            "reason": str}``. When ``sbom`` is present it carries ``url``
            (a plain unauthenticated GET, valid until ``expires_at``),
            ``size_bytes``, ``format`` (``cyclonedx``) and
            ``content_encoding`` (``gzip``).

            A repository with no SBOM yet is a SUCCESSFUL response with
            ``sbom`` ``None`` and a machine-readable ``reason``
            (``sbom_not_generated_yet`` or
            ``code_lane_not_enabled_in_datacenter``) — only a repository the
            org does not have is an error. Check ``sbom`` for ``None`` before
            using it.

        Note:
            The document is served straight from object storage, so the link
            leaves this API's auth boundary. It is deliberately short-lived;
            fetch it promptly and do not store it.
        """
        # The key contains a '/', so it is percent-encoded into ONE path
        # segment. The gateway accepts either spelling, but encoding is what
        # keeps the request unambiguous for anything in between.
        quoted = _quote(repo, safe="")
        return self._get(
            f"code/repos/{quoted}/sbom", _query_pairs(provider=provider))

    def download_code_sbom(
        self, repo: str, *, provider: str | None = None,
    ) -> bytes | None:
        """Fetch a repository's SBOM document itself (gzipped CycloneDX).

        Returns ``None`` — not an exception — when the repository has no SBOM
        yet, mirroring :meth:`get_code_sbom`. Any other failure raises.

        The signed link is fetched with a bare HTTP GET and deliberately
        WITHOUT this SDK's auth headers: it is a pre-signed object-storage
        URL, and sending LimaCharlie credentials to a Google endpoint would
        put them somewhere they do not belong.
        """
        resp = self.get_code_sbom(repo, provider=provider)
        sbom = resp.get("sbom")
        if not sbom or not sbom.get("url"):
            return None
        with _urlopen(sbom["url"]) as body:
            return body.read()

    def rescan_code_repo(
        self,
        repo: str,
        *,
        ref: str | None = None,
        provider: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Ask the code lane to rescan ONE repository now.

        This is the manual door onto the same trigger a push webhook takes.
        It does not wait for the scan, and it is not a promise that one will
        run: the response means the trigger was ACCEPTED.

        Args:
            repo: The repository — ``"<owner>/<name>"``, its bare name, or
                its canonical urn.
            ref: The git ref a push landed on
                (``"refs/heads/main"``). Optional; the lane scans the
                default branch either way, and a ref naming a branch other
                than the one the last scan cloned is declined.
            provider: The source-control provider the repository belongs to;
                defaults to ``github`` server-side.
            source: A short token recording who asked, for the host's log
                line and the mark it persists. Defaults to ``manual``.

        Returns:
            ``{"accepted": bool, "repo": str, "provider": str,
            "debounce_seconds": int}``. ``debounce_seconds`` is the window a
            burst of triggers for one repository collapses into.

        Note:
            Several outcomes are a quiet no-op from here: a repository
            outside the org's ``code_scanning`` policy scope, one over the
            free-tier quota or the per-connection daily cap, one in a failure
            backoff, or a connection whose collection is paused at that
            instant. The result is visible per repository on
            :meth:`list_code_repos`, not on this response.
        """
        body: dict[str, Any] = {"repo": repo, "source": source or "manual"}
        if ref:
            body["ref"] = ref
        if provider:
            body["provider"] = provider
        return self._post("code/scan", body)

    def check_pull_request(
        self,
        repo: str,
        pr: int,
        base_sha: str,
        head_sha: str,
        action: str,
        *,
        prev_base_sha: str | None = None,
        base_ref: str | None = None,
        head_ref: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Ask the code lane what a pull request INTRODUCES, as a check run.

        The lane scans the pull request's base and head and publishes a
        GitHub check run on the head commit reporting only what is NEW in
        it; the repository's own findings stay on
        :meth:`list_code_repos`. Its normal caller is the shipped D&R rule
        on the org's source-control webhook, but this is a plain
        documented route, so a CI job can ask the same question.

        Args:
            repo: The repository — ``"<owner>/<name>"``, its bare name, or
                its canonical urn.
            pr: The pull-request number.
            base_sha: A FULL commit id. Still required, but NOT
                authoritative: the lane takes the base from the provider,
                because a caller-chosen base decides what the diff is
                measured from and a base equal to the head would make any
                pull request look like it introduced nothing.
            head_sha: The FULL commit id of the head. A branch or tag name
                is refused — the check is published ON the commit, and a
                ref would let it be attached to a commit nobody proposed.
            action: REQUIRED. The webhook action: ``opened``,
                ``synchronize``, ``reopened`` or ``edited``. Every other
                pull-request event leaves what the pull request introduces
                untouched and is refused — and so is an ABSENT action: the
                collection host checks membership of that closed set
                without an empty-string exemption, so a request carrying
                no action is refused unconditionally. A CI job with no
                webhook to quote should send ``synchronize``, which is
                what a push to an open pull request is.
            prev_base_sha: REQUIRED when ``action`` is ``edited``, refused
                as incomplete without it. ``edited`` is in the set for one
                thing it reports — a pull request RETARGETED at a
                different base branch, which changes the diff under review
                without pushing a commit. A title or body change is
                reported the same way and changes nothing, so this value
                (GitHub's ``changes.base.sha.from``) is what tells the two
                apart. It is EVIDENCE, never a scan input: the check is
                refused if the provider says the base did not actually
                move, so an editing spree costs no scan and nothing
                against the daily write budget.
            base_ref: Optional branch the pull request targets.
            head_ref: Optional branch the pull request comes from.
            provider: Source-control provider; defaults to ``github``.

        Returns:
            ``{"accepted": bool, "repo": str, "pr": int, "provider": str,
            "debounce_seconds": int}``.

        Note:
            The pull request is READ FROM THE PROVIDER before anything is
            scanned and what it says wins: the check is published only
            when the pull request is open, belongs to this repository, and
            its head commit is the ``head_sha`` you sent. A pull request
            whose own base and head are the same commit is refused.

            ``accepted`` means the check was QUEUED, never that one will
            appear. It is acknowledged immediately, debounced per pull
            request (a push of several commits becomes one check) and
            handed to the collector replica holding that connection, which
            applies the rest of the decision. Each of these is a quiet
            no-op from here: a connection whose GitHub App has not been
            granted *Checks: Read and write* and *Pull requests: Read and
            write* (the connection App is read-only by default —
            :meth:`get_code_capabilities` reports which permission is
            missing); a repository outside the ``code_scanning`` policy
            scope or with ``pr_checks`` off; a repository over the
            free-tier quota; a connection that has spent its daily
            source-control write budget; or a connection paused or failing
            over at that instant.

            The verdict is the check run's conclusion, set by the policy's
            ``gating.fail_on``.
        """
        body: dict[str, Any] = {
            "repo": repo,
            "pr": pr,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
        body["action"] = action
        for key, value in (
            ("prev_base_sha", prev_base_sha),
            ("base_ref", base_ref),
            ("head_ref", head_ref),
            ("provider", provider),
        ):
            if value:
                body[key] = value
        return self._post("code/pr_check", body)

    def configure_code_webhook(
        self, connection: str, url: str, secret: str,
    ) -> dict[str, Any]:
        """Point a GitHub connection's App webhook at this org's adapter.

        Push rescans and pull-request checks are driven by the GitHub
        App's OWN webhook — one per App, covering every repository the App
        is installed on — delivered to the connection's
        ``github-code-webhook-<connection>`` webhook adapter. A connection
        whose App has no webhook, or one pointing elsewhere, is repaired
        here: LimaCharlie rewrites the App's hook config with the App's own
        credential.

        Args:
            connection: The ``cloudsec_provider`` hive record name of a
                GitHub connection.
            url: The adapter's hook url. It is refused unless it is
                EXACTLY
                ``https://<hooks domain>/<this oid>/github-code-webhook-<connection>/<url secret>``
                — the adapter's own name, whose ``github-code-webhook-``
                PREFIX is what the server actually enforces on that
                segment — where the hooks domain is this org's own: the
                ``url.hooks`` value of ``GET /orgs/{oid}/url``, always
                under ``.hook.limacharlie.io``. https only, no
                credentials, port, query or fragment, and the org in the
                path must be this one. The rule is narrow on purpose: a
                caller who could name any url could redirect an org's
                source-control event stream, and the secret needed to
                accept it, to a server they control.
            secret: The webhook signing secret the adapter verifies
                (``X-Hub-Signature-256``); 20 to 256 bytes, with no
                whitespace and no control characters.

        Returns:
            The connection's RE-DETECTED webhook status:
            ``{"state": "available" | "unavailable" | "unknown",
            "reason": str, "missing_events": [str, ...], "detail": str}``.
            ``reason`` is ``webhook_not_configured``,
            ``webhook_points_elsewhere``, ``missing_events``,
            ``verification_unavailable``, or empty.

        Note:
            Neither the url nor the secret is ever returned or logged, by
            this method or by the server.

            Event subscriptions (Push, Pull request) CANNOT be changed
            through the API. When ``reason`` is ``missing_events`` an org
            owner has to tick them in the App's settings.

            A refusal is a 400 carrying a machine-readable ``reason`` —
            among them ``connection_not_found``, ``provider_not_github``,
            ``webhook_in_use_by_other_org`` (the App's webhook already
            delivers to another org) and ``webhook_not_active`` (the App
            has no active webhook, which GitHub's API cannot create, so an
            owner must tick Active first). A failure talking to GitHub is
            a 502 with a ``github_`` reason; a request past its
            50-second bound is a 504 with reason ``timeout`` AND MAY STILL
            HAVE BEEN APPLIED, so re-read the status rather than retrying
            blindly; a transient LimaCharlie failure is a 503 with reason
            ``host_unavailable`` and is safe to retry. The write itself is
            idempotent.
        """
        return self._post("code/webhook", {
            "connection": connection,
            "url": url,
            "secret": secret,
        })

    def autofix_code_finding(
        self,
        finding_id: str,
        *,
        repo: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Open a pull request raising the vulnerable dependency a finding is about.

        The finding id is the ONLY input that decides anything. The backend
        resolves it against the dependency rows its own scan produced and
        raises that package to that advisory's fixed version, so a fix can
        never be requested for a package or a version the organization's own
        scan did not find.

        Args:
            finding_id: the id of an open dependency (SCA) finding, as
                returned by :meth:`list_findings`.
            repo: optional — narrows the search to one repository. It is a
                hint, not an authorization: the finding id is what is acted
                on.
            provider: the source-control provider; defaults to ``github``
                server-side.

        Returns:
            ``{"accepted": bool, "finding_id": str, "repo": str,
            "provider": str, "debounce_seconds": int}``.

        Note:
            ``accepted`` does not mean a pull request exists. The request is
            acknowledged immediately and handed to the collector replica
            holding that connection, which clones the repository in a
            sandbox, edits the manifest and opens the pull request — that
            pull request is where the result appears. Each of these is a
            quiet no-op from here: an organization with no Code Actions App
            configured (the write App is separate and opt-in — the read-only
            connection App is never used to write) or one whose App lacks
            *Contents: Read and write*; a finding whose package is flagged
            malicious (the remediation is removal and credential rotation,
            not an upgrade) or for which no fixed version has been
            published; an ecosystem other than npm, pip, go or maven; a
            repository outside the ``code_scanning`` policy scope or over the
            free-tier quota; a package that already has an AutoFix pull
            request open; and a connection at its daily AutoFix limit.

            For **npm** the ``package-lock.json`` *is* rewritten by
            default: one read-only registry metadata document supplies the
            new version's resolved URL and integrity digest. It is left
            stale only where the ``code_scanning`` policy sets
            ``autofix_registry_access: false``, where the lock is a
            ``yarn.lock``/``pnpm-lock.yaml``, or where the entry could not
            be rewritten safely. For **go** the ``go.sum`` is *not*
            regenerated — it hashes a module zip nobody downloaded — and
            only where the tree has one. For **pip**
            (``requirements.txt``) and **maven** there is no lockfile, so
            the change is complete. Wherever a lock is left stale the pull
            request says so prominently and names the command to run; trust
            the pull request over this summary.
        """
        body: dict[str, Any] = {"finding_id": finding_id}
        if repo:
            body["repo"] = repo
        if provider:
            body["provider"] = provider
        return self._post("code/autofix", body)

    def push_iac_map(self, document: bytes | str) -> dict[str, Any]:
        """Push a sanitized IaC map with the organization's write authorization.

        Args:
            document: Locally extracted lc-iac-map/v1 JSON, at most 10 MiB.

        Returns:
            dict: Reconcile counts, partial coverage, content hash and replay status.

        Raises:
            ValueError: If local preflight rejects the sanitized document.
            AuthenticationError: If the organization lacks cloudsec.set permission.
        """
        from .iac_map import validate_iac_map
        raw = validate_iac_map(document)
        return self._org.client.request(
            "POST", f"cloudsec/{self.oid}/code/iac-map",
            raw_body=raw, content_type="application/json")

    def push_code_provenance(self, document: bytes | str | dict[str, Any]) -> dict[str, Any]:
        """Push build provenance without changing signed document bytes.

        Args:
            document: LC provenance, SLSA v1 or an offline Sigstore bundle.

        Returns:
            dict: Result counts and server-computed attestation identity.

        Raises:
            ValueError: If the document exceeds the 1 MiB wire limit.
            TypeError: If the document is not bytes, str or dict.
        """
        if isinstance(document, dict):
            raw = json.dumps(document, separators=(",", ":")).encode("utf-8")
        elif isinstance(document, str):
            raw = document.encode("utf-8")
        elif isinstance(document, bytes):
            raw = document
        else:
            raise TypeError("provenance document must be bytes, str or dict")
        if not raw or len(raw) > 1 << 20:
            raise ValueError("provenance document must be between 1 byte and 1 MiB")
        return self._org.client.request(
            "POST", f"cloudsec/{self.oid}/code/provenance",
            raw_body=raw, content_type="application/json",
        )

    def list_code_provenance(self, *, repo_urn: str | None = None,
                             commit: str | None = None, digest: str | None = None,
                             cursor: str | None = None) -> dict[str, Any]:
        """Read normalized build attestations and their full-claim decisions.

        Args:
            repo_urn: Canonical repository URN within this organization.
            commit: Full hexadecimal source commit.
            digest: OCI sha256 artifact digest.
            cursor: Opaque cursor from the previous response.

        Returns:
            dict: Result containing provenance records and optional next_cursor.
        """
        params = [(key, value) for key, value in (
            ("repo_urn", repo_urn), ("commit", commit), ("digest", digest),
            ("cursor", cursor)) if value is not None]
        return self._get("code/provenance", params)

    def ingest_code_results(
        self,
        repo: str,
        source: str,
        document: bytes | str | dict[str, Any],
        *,
        commit: str | None = None,
        ref: str | None = None,
        default_branch: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Push results your own pipeline produced for one repository.

        The document is recorded as Cloud Security findings on that
        repository, deduplicated against the hosted scan by IDENTITY — so
        pushing something the hosted scanner also found updates it rather
        than duplicating it, and re-pushing an identical document writes
        nothing.

        Args:
            repo: the ``"<owner>/<name>"`` key :meth:`list_code_repos`
                returns. It must be selected by an enabled ``code_scanning``
                policy — the same switch the hosted lane uses — but it does
                NOT have to be in the org's collected inventory: pushing for
                a repository no connected source-control organization covers
                creates it, with only the facts the push vouches for and
                ``source: "ingest"`` on :meth:`list_code_repos`. Such a
                repository counts against the free tier's repository quota
                exactly like a collected one, and is removed along with its
                findings if it goes a month with no push that moves its
                commit.
            source: ``"sarif"``, ``"cyclonedx"`` or ``"report"`` (the
                LimaCharlie scanner's own ``report/v1`` document, which is
                loss-free and therefore dedupes exactly).
            document: the document, as raw bytes (gzipped or not), a string,
                or an already-parsed object.
            commit: the revision the document describes. Recorded, not
                verified, and worth sending: it is what tells somebody
                reading a finding which checkout produced it.
            default_branch: the repository's shipping branch. Only worth
                sending for a repository LimaCharlie does not collect —
                nothing else can state it there, and it is left unset rather
                than guessed when you do not know it.

        Returns:
            ``{"result": {...}}`` — what landed: ``findings``, the SoR
            counters (``created``/``updated``/``deleted``/``unchanged``),
            what the merge did (``enriched``/``carried_forward``/``closed``)
            and ``notes``, the machine-readable list of things the FORMAT
            could not carry. A ``notes`` entry is not an error; it is the
            honest half of the answer, and ``secrets_not_ingestable`` in
            particular means credential findings were deliberately dropped
            (a pushed document cannot carry the keyed digest a secret is
            identified by, and the plaintext is never accepted).

        A pushed document can only ever close findings IT previously
        reported. It can never close what the hosted scanner found.

        AND IT CLOSES NOTHING AT ALL UNLESS IT PROVES ITS SCAN RAN. A SARIF
        is read as an authoritative enumeration — one whose absent findings
        mean "fixed" rather than "not looked for" — only when it carries
        ``run.invocations[].executionSuccessful: true``, which SARIF 2.1.0
        defines for exactly this purpose. Without it the push is ADDITIVE:
        the findings land, nothing closes, and ``notes`` carries
        ``sarif_no_invocation_evidence``. The rule exists because a scan step
        with a broken ``--config`` still emits the tool's full rule catalogue
        and zero results, and treating that as a clean pass would resolve
        real vulnerabilities.

        Trivy does not write ``invocations``, so a document straight from it
        never closes anything. Add the field yourself when your scan step
        exited 0 — the CLI's ``code ingest --scanner-succeeded`` does it for
        you — or push the scanner's own ``report/v1``, which states its
        coverage directly. A document that says its run FAILED is also
        additive, and says so with ``sarif_execution_unsuccessful``.

        None of this applies to a secret scanner. Credential findings are
        never ingested from a pushed document in any format
        (``secrets_not_ingestable``), so a gitleaks SARIF creates nothing to
        close whatever its ``invocations`` say; that class comes from the
        hosted scan.
        """
        body: dict[str, Any] = {"repo": repo, "source": source}
        if isinstance(document, (bytes, bytearray)):
            # Sent base64 rather than decoded here: the document may be a gzip
            # stream (the scanner writes report.json.gz) and decoding it
            # locally only to re-encode it as JSON would parse a multi-megabyte
            # payload twice for nothing.
            body["document_b64"] = base64.b64encode(bytes(document)).decode("ascii")
        elif isinstance(document, str):
            body["document_b64"] = base64.b64encode(document.encode("utf-8")).decode("ascii")
        else:
            body["document"] = document
        if commit is not None:
            body["commit"] = commit
        if ref is not None:
            body["ref"] = ref
        if default_branch is not None:
            body["default_branch"] = default_branch
        if provider is not None:
            body["provider"] = provider
        return self._post("code/ingest", body)

    def get_code_capabilities(self, *, repo: str | None = None) -> dict[str, Any]:
        """What each connected source-control organization may actually DO
        for the AppSec code lane: repository scanning, PR checks, PR
        comments, and dependency AutoFix pull requests.

        This only covers **GitHub** connections. A GitLab or Bitbucket
        connection scans with its own read-only token and holds no write
        plane to detect (no PR checks, no PR comments, no AutoFix pull
        requests), so it never appears here — not even as an ``unknown``
        entry. Use ``cloudsec provider manifest`` for what a GitLab or
        Bitbucket connection actually collects.

        A capability reading ``available`` means the control MAY be
        offered, never that anything fires on its own: a ``pr_checks``
        capability of ``available`` says the connection COULD publish a
        check run, not that a webhook is wired to trigger one.

        Args:
            repo: Narrow to the one connection covering a single repository
                (``"<owner>/<name>"`` as :meth:`list_code_repos` returns
                it). Omit to list every GitHub connection.

        Returns:
            ``{"connections": [{"connection", "org", "provider", "mode",
            "scan_app_id", "actions_app_id", "repository_selection",
            "repository", "suspended", "verified_at", "capabilities":
            [{"id", "state", "needs", "missing", "reason", "detail"}, ...]},
            ...]}``. ``capabilities[].id`` is one of ``repo_scanning``,
            ``pr_checks``, ``pr_comments``, ``fix_pull_requests``;
            ``state`` is ``available`` | ``unavailable`` | ``unknown``
            (``unknown`` means the installation could not be read, not that
            it was denied). A connection whose read failed still appears,
            every capability ``unknown`` and ``verified_at`` empty, rather
            than being dropped from the list.
        """
        return self._get("code/capabilities", _query_pairs(repo=repo))

    def get_code_fixes(
        self, *, cursor: str | None = None, limit: int | None = None,
    ) -> dict[str, Any]:
        """The dependency-upgrade queue: open code (SCA) findings grouped by
        the single package upgrade that would close them, ranked so the
        highest-leverage fix leads.

        Args:
            cursor: Keyset-pagination token from a previous page.
            limit: Page size (backend default 5, max 20).

        Returns:
            ``{"fixes": [{"key", "cause_key", "title", "ecosystem",
            "package", "fixed_version", "finding_count",
            "repository_count", "top_severity",
            "representative_finding_id"}, ...], "distinct": int,
            "next_cursor": str, "scope": str, "caveat": str}``.
            ``representative_finding_id`` is usable with
            :meth:`autofix_code_finding`. ``distinct`` is the total number
            of fixes in scope, which may exceed the page returned; read
            ``scope``/``caveat`` for exactly what population is counted
            rather than assuming.
        """
        return self._get("code/fixes", _query_pairs(cursor=cursor, limit=limit))

    def iter_code_fixes(self, **selectors: Any):
        """Yield every fix in the dependency-upgrade queue, page by page.

        Wraps :meth:`get_code_fixes` and follows ``next_cursor`` to the
        end, which is the correct way to walk this endpoint: a page may be
        short without being the last one.

        Yields:
            dict: One ``fixes`` entry per iteration, in the same shape
            :meth:`get_code_fixes` documents.
        """
        selectors.pop("cursor", None)
        cursor: str | None = None
        while True:
            page = self.get_code_fixes(cursor=cursor, **selectors)
            for fix in page.get("fixes") or []:
                yield fix
            cursor = page.get("next_cursor") or None
            if not cursor:
                return

    # ------------------------------------------------------------------
    # Container images (registry-backed image inventory)
    # ------------------------------------------------------------------
    #
    # These reads have their own contract rather than riding the generic
    # resource inventory, because an image and its placement are different
    # objects: an image is keyed on its DIGEST ALONE and is therefore
    # global across every registry, account, cluster and provider that
    # holds it, while tags, registry and push time belong to the
    # repository<->image MEMBERSHIP. Every filter and sort runs
    # server-side.

    def list_image_repos(
        self,
        *,
        q: str | None = None,
        provider: list[str] | None = None,
        account: list[str] | None = None,
        registry: list[str] | None = None,
        region: list[str] | None = None,
        has_findings: bool | None = None,
        has_images: bool | None = None,
        scanning_state: str | None = None,
        sort: str | None = None,
        order: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """One page of connected container-image repositories.

        Args:
            q: Substring over the repository path, display name, registry
                and urn.
            provider: Cloud provider filter values, OR'd.
            account: Account filter values, OR'd.
            registry: Registry-host filter values, OR'd.
            region: Registry-region filter values, OR'd.
            has_findings: ``True`` for repositories with at least one OPEN
                finding, ``False`` for those with none. TRI-STATE: omit
                (``None``) for no constraint — ``False`` is a real
                selection, not "unfiltered".
            has_images: Same tri-state shape, on whether the repository
                currently contains any image.
            scanning_state: Native registry-scanning state:
                ``enabled``, ``disabled`` or ``unknown``. A SCALAR, not a
                list — the backend would take several, but the gateway
                forwards only one, so a list here would silently drop
                every value after the first. ``unknown`` means the
                registry did not report the state, not that scanning is
                off.
            sort: ``name`` (the default), ``risk``, ``images`` or
                ``last_pushed``. An unrecognised key is silently coerced
                to ``name`` by the server rather than rejected, so a typo
                returns a successful, wrongly-ordered page.
            order: ``asc`` or ``desc``. The default follows the sort key —
                ``asc`` for ``name``, ``desc`` for the rest.
            cursor: Keyset-pagination token from a previous page.
            limit: Page size (default 100, max 1000).

        Returns:
            ``{"image_repos": [{"urn", "provider", "registry",
            "repository", "display_name", "account", "region",
            "scanning_state", "image_count", "tagged_image_count",
            "open_findings", "top_severity", "first_seen", "last_seen"},
            ...], "next_cursor": str, "total": int, "coverage": {...}}``.

            ``total`` is the size of the whole filtered set, not of the
            page. ``top_severity`` is ABSENT when the repository has no
            open findings — a missing key means "none", never ``INFO``.
            ``account`` and ``region`` are omitted when the provider did
            not report them.

            ``coverage`` is ``{"mode": ..., "repository_inventory_available":
            bool}`` and says how much of the estate this list can possibly
            represent: ``observed_only`` means no registry inventory was
            collected at all and the rows exist only because something was
            seen running or scanned. So an EMPTY list with
            ``repository_inventory_available`` false means "not
            collected", never "zero repositories".

        Note:
            ``next_cursor`` is the ONLY end-of-set signal. A short page is
            not necessarily the last one, and a full page does not
            guarantee another — walk with :meth:`iter_image_repos` or loop
            on the cursor. The cursor is bound to the filter and sort it
            was issued under; changing any selector mid-walk is an error
            rather than a silently different result.
        """
        return self._get("code/image-repos", _query_pairs(
            q=q, provider=provider, account=account, registry=registry,
            region=region, has_findings=has_findings,
            has_images=has_images, scanning_state=scanning_state,
            sort=sort, order=order, cursor=cursor, limit=limit,
        ))

    def iter_image_repos(self, **selectors: Any):
        """Yield every matching image repository, page by page.

        Wraps :meth:`list_image_repos` and follows ``next_cursor`` to the
        end, which is the correct way to walk it: a page can be short
        without being the last.

        Yields:
            dict: One ``image_repos`` entry per iteration.
        """
        selectors.pop("cursor", None)
        cursor: str | None = None
        while True:
            page = self.list_image_repos(cursor=cursor, **selectors)
            for row in page.get("image_repos") or []:
                yield row
            cursor = page.get("next_cursor") or None
            if not cursor:
                return

    def get_image_repo_facets(
        self,
        *,
        q: str | None = None,
        provider: list[str] | None = None,
        account: list[str] | None = None,
        registry: list[str] | None = None,
        region: list[str] | None = None,
        has_findings: bool | None = None,
        has_images: bool | None = None,
        scanning_state: str | None = None,
    ) -> dict[str, Any]:
        """Cross-filtered facet counts for the image-repository list.

        Takes the SAME selectors as :meth:`list_image_repos` (minus
        paging, which this endpoint ignores), so the rail describes the
        population that list returns.

        Returns:
            ``{"total": int, "providers": [{"value", "count"}, ...],
            "accounts": [...], "registries": [...],
            "scanning_states": [...]}``.

        Note:
            Each faceted dimension excludes its OWN selector so the rail
            answers "what if I changed this one filter" — with three
            exceptions that always constrain every count: ``region``,
            ``has_images`` and ``has_findings`` (and the ``q`` search).
            There is deliberately no ``region`` facet for that reason.

            The empty string is a legitimate bucket value meaning "the
            provider did not report it", not a parsing artifact. A
            dimension with no rows may be absent rather than an empty
            list, so read each with ``.get(...)``.
        """
        return self._get("code/image-repos/facets", _query_pairs(
            q=q, provider=provider, account=account, registry=registry,
            region=region, has_findings=has_findings,
            has_images=has_images, scanning_state=scanning_state,
        ))

    def list_container_images(
        self,
        *,
        q: str | None = None,
        repo_urn: list[str] | None = None,
        provider: list[str] | None = None,
        account: list[str] | None = None,
        registry: list[str] | None = None,
        tag: list[str] | None = None,
        findings: str | None = None,
        running: bool | None = None,
        signed: bool | None = None,
        sort: str | None = None,
        order: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """One page of container images, keyed by digest.

        An image is identified by its DIGEST ALONE, so one row is the same
        artifact everywhere it is stored. The placement selectors below
        (``repo_urn``, ``provider``, ``account``, ``registry``, ``tag``)
        therefore select images with AT LEAST ONE matching placement — the
        returned row still lists its other placements.

        Args:
            q: Substring over the image name, urn, and the joined
                repository path, registry host and tags.
            repo_urn: Image-repository urn filter values, OR'd — the
                ``urn`` field of a :meth:`list_image_repos` row.
            provider: Provider filter values, OR'd (matched on placement).
            account: Account filter values, OR'd (matched on placement).
            registry: Registry-host filter values, OR'd (on placement).
            tag: Exact tag filter values, OR'd (on placement).
            findings: ``with`` (open findings), ``without`` (none), or
                ``any``. A SCALAR. Anything the server does not recognise
                is treated as ``any``, i.e. unconstrained.
            running: ``True`` for images observed running on a workload,
                ``False`` for those not. TRI-STATE — omit for no
                constraint.
            signed: ``True``/``False`` on the image's signature. TRI-STATE,
                and note that signing status is only recorded when a
                provider reports it: an image whose status is UNKNOWN
                matches NEITHER ``True`` nor ``False``, and the field is
                not echoed back in the row.
            sort: ``name`` (the default), ``risk`` or ``pushed``. An
                unrecognised key is silently coerced to ``name``.
            order: ``asc`` or ``desc`` (default ``asc`` for ``name``,
                ``desc`` otherwise).
            cursor: Keyset-pagination token from a previous page.
            limit: Page size (default 100, max 1000).

        Returns:
            ``{"images": [{"urn", "digest", "name", "open_findings",
            "findings_by_severity", "top_severity", "workload_count",
            "built_from_repo_count", "repository_count", "repositories",
            "repositories_truncated", "first_seen", "last_seen",
            "scanner_provenance", "registry_observed"}, ...],
            "next_cursor": str, "total": int, "coverage": {...}}``.

            ``urn`` is what :meth:`list_findings` takes as ``image_urn``.
            ``repositories`` is a BOUNDED SAMPLE (100) of placements —
            ``{"repository_urn", "provider", "registry", "repository",
            "account", "region", "tags", "tag_count", "tags_truncated",
            "last_seen"}`` — so read ``repository_count`` for the truth
            and ``repositories_truncated`` for whether you are seeing all
            of them. ``tags`` is separately capped at 100.

            ``top_severity`` is ABSENT when there are no open findings; a
            missing key means "none", never ``INFO``.
            ``findings_by_severity`` is always an object (``{}`` when
            empty). ``coverage`` carries a third ``mode`` this list can
            report that :meth:`list_image_repos` cannot: ``mixed``, meaning
            registry inventory exists but some images were only ever
            observed at runtime.

        Note:
            ``next_cursor`` is the only end-of-set signal, and the cursor
            is bound to the filter and sort it was issued under. Cursors
            from :meth:`list_image_repos` are NOT interchangeable with
            these.

            Every count and the ``risk``/``pushed`` sort keys come from a
            rollup rebuilt once per collection pass, so they describe the
            last rebuild rather than this instant.
        """
        return self._get("code/images", _query_pairs(
            q=q, repo_urn=repo_urn, provider=provider, account=account,
            registry=registry, tag=tag, findings=findings,
            running=running, signed=signed, sort=sort, order=order,
            cursor=cursor, limit=limit,
        ))

    def iter_container_images(self, **selectors: Any):
        """Yield every matching container image, page by page.

        Wraps :meth:`list_container_images` and follows ``next_cursor`` to
        the end.

        Yields:
            dict: One ``images`` entry per iteration.
        """
        selectors.pop("cursor", None)
        cursor: str | None = None
        while True:
            page = self.list_container_images(cursor=cursor, **selectors)
            for row in page.get("images") or []:
                yield row
            cursor = page.get("next_cursor") or None
            if not cursor:
                return

    def get_container_image(self, digest: str) -> dict[str, Any]:
        """One container image by digest, with its placements and use.

        Args:
            digest: The image digest, ``sha256:`` followed by 64 lowercase
                hex characters, exactly as :meth:`list_container_images`
                returns it. Anything else is refused as an invalid digest;
                a well-formed digest the org has never seen is "not
                found", not an empty result.

        Returns:
            ``{"image": {...}, "memberships": [...],
            "membership_count": int, "memberships_truncated": bool,
            "workloads": [{"urn", "name"}, ...], "workload_count": int,
            "source_repositories": [{"urn", "name"}, ...],
            "source_repository_count": int}``. ``image`` is one
            :meth:`list_container_images` row; ``memberships`` are the
            placement objects that row documents.

        Note:
            ``memberships``, ``workloads`` and ``source_repositories`` are
            BOUNDED SAMPLES of 100, not complete sets, and there is no
            pagination for them — the paired ``*_count`` is the truth.
            Only memberships carry a ``_truncated`` flag; for the other
            two, compare the list length against the count yourself. To
            get past 100 placements, list images filtered by ``repo_urn``
            instead.
        """
        return self._get(f"code/images/{_quote(digest, safe='')}")

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

        ``resolver_ready`` (is redis-cloudsec provisioned at all) is merged,
        not dropped: it is pessimistic — one not-ready chunk makes the whole
        merged answer not-ready. Readiness does not establish cache health or
        complete coverage; unresolved identifiers remain unknown. It
        stays ABSENT when no chunk reported it (an older backend) rather than
        being invented as False.
        """
        resolved: list[Any] = []
        unresolved: list[Any] = []
        ready: list[Any] = []
        values = list(values)
        for i in range(0, len(values), _RESOLVE_CHUNK_SIZE):
            chunk = values[i:i + _RESOLVE_CHUNK_SIZE]
            resp = self._get(path, _query_pairs(**{key: chunk}))
            resolved.extend(resp.get("resolved") or [])
            unresolved.extend(resp.get("unresolved") or [])
            if "resolver_ready" in resp:
                ready.append(resp["resolver_ready"])
        out: dict[str, Any] = {"resolved": resolved, "unresolved": unresolved}
        if ready:
            out["resolver_ready"] = all(bool(v) for v in ready)
        return out

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

    def get_free_tier(self) -> dict[str, Any]:
        """The org's cloud-security free-tier standing and its limits.

        Describes where the org stands BEFORE it bounces off a limit; it
        does not enforce anything (the collector and the provider-record
        validator do, so a limit applies whether or not this was called).

        The trial countdown is deliberately absent — the authoritative
        clock lives in the datacenter, and a deadline derived here could
        disagree with the enforcer. The collector publishes a gated reason
        through :meth:`get_scan_status` instead.

        Returns:
            ``{"is_free_tier": bool, "sensor_quota": int}``, plus
            ``max_providers`` and ``enabled_providers`` for a free-tier
            org only (a paying org has no provider cap, so reporting one
            would advertise a limit that does not exist).
            ``enabled_providers`` is OMITTED — not zeroed — when the
            count could not be read, so an absent key means "unknown",
            never "none configured".
        """
        return self._get("free-tier")

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
        has_iac_origin: bool | None = None,
        iac_attribution: list[str] | None = None,
        severity: list[str] | None = None,
        finding_class: list[str] | None = None,
        status: list[str] | None = None,
        account: list[str] | None = None,
        owner: list[str] | None = None,
        sla: list[str] | None = None,
        repo: list[str] | None = None,
        image_urn: list[str] | None = None,
        fix_state: list[str] | None = None,
        exploit_band: list[str] | None = None,
        grain: list[str] | None = None,
        cause: str | None = None,
        source: str | None = None,
        reachable: bool | None = None,
        kev: bool | None = None,
        q: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> str:
        """Export the (filtered) findings worklist as CSV text.

        The exported rows carry ``due_at``, ``sla_state`` and
        ``sla_source`` alongside the worklist fields.

        Takes the same filter selectors as :meth:`list_findings`; the
        server walks the full filtered set (no pagination), capped at
        100k rows.

        Returns:
            The CSV document as a string.
        """
        pairs = _finding_query_pairs(
            iac_attribution=iac_attribution, has_iac_origin=has_iac_origin,
            severity=severity, finding_class=finding_class, status=status,
            account=account, owner=owner, sla=sla, repo=repo,
            image_urn=image_urn, fix_state=fix_state,
            exploit_band=exploit_band, grain=grain, cause=cause,
            source=source, reachable=reachable, kev=kev, q=q,
            sort=sort, order=order,
        )
        pairs.append(("format", "csv"))
        return self._get("findings", pairs, raw_response=True)

    def export_inventory_csv(
        self,
        *,
        has_iac_origin: bool | None = None,
        resource_type: str | None = None,
        provider: str | None = None,
        account: str | None = None,
        region: str | None = None,
        q: str | None = None,
        account_empty: bool | None = None,
        account_unscoped: bool | None = None,
    ) -> str:
        """Export the (filtered) cloud resource inventory as CSV text.

        Takes the same filter selectors as :meth:`list_inventory`; the
        server walks the full filtered set (no pagination), capped at
        100k rows.

        Returns:
            The CSV document as a string.
        """
        _validate_iac_selectors(None, has_iac_origin)
        selector = _inventory_account_selector(account_empty, account_unscoped)
        pairs = _query_pairs(
            type=resource_type, provider=provider, account=account,
            region=region, q=q, has_iac_origin=has_iac_origin,
            **selector,
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
        project: str | None = None,
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
