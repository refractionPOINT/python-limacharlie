"""Email Security (mailsec) SDK for LimaCharlie v2.

Wraps the ``/mailsec/{oid}/...`` REST routes served by the API gateway: the
coverage screen, the message index and its drawer, the justified raw-EML
download, campaigns, sender profiles, the action audit trail, the
abuse-mailbox report queue, standalone EML analysis, retro-hunts, custom-rule
validation and backtest, the provider connection preflight, and the served
onboarding guide.

Permissions, which are four rather than the usual get/set pair because mailsec
asks to be trusted with four different things:

- ``mailsec.get``     read the product's own view: the queue, the drawer,
                      campaigns, sender profiles, the audit trail
- ``mailsec.set``     change detection behaviour and triage state
- ``mailsec.act``     remediate live mail at the provider
- ``mailsec.get.eml`` take the original bytes of somebody's mail out of the
                      building; requires a logged justification

Every route additionally requires the org to be subscribed to the
``ext-email-security`` extension (403 otherwise)::

    limacharlie extension subscribe --name ext-email-security

Provider connections and policy are hive records — manage them with the hive
commands (``limacharlie hive list --hive-name mailsec_provider``, same for
``mailsec_policy`` and ``dr-mail``). The one connection operation here is the
post-save credential preflight (:meth:`Mailsec.test_connection`).

Two conventions inherited from the API contract that callers must not
"helpfully" work around:

- **Cursors are opaque and are passed back verbatim.** They encode which index
  the walk is pinned to, and they are bound to the filter set they were minted
  under; changing a filter mid-walk is an error rather than a page that
  silently means something else.
- **Booleans are tri-state.** Leaving one unset means the dimension is
  unconstrained, which is NOT the same as sending ``False``.
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


def _add_scalar(pairs: list[tuple[str, str]], key: str, value: Any) -> None:
    """Append a scalar param, skipping ``None`` so absent stays absent.

    ``False`` is forwarded, ``None`` is not: that is the whole tri-state
    contract, and collapsing them would turn "unconstrained" into "must be
    false" on every boolean the API has.
    """
    if value is None:
        return
    if isinstance(value, bool):
        pairs.append((key, "true" if value else "false"))
    else:
        pairs.append((key, str(value)))


class Mailsec:
    """Email Security client for LimaCharlie."""

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
        *,
        raw_response: bool = False,
    ) -> Any:
        return self._org.client.request(
            "GET",
            f"mailsec/{self.oid}/{path}",
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
            f"mailsec/{self.oid}/{path}",
            query_params=query_params or None,
            raw_body=json.dumps(body).encode(),
            content_type="application/json",
            raw_response=raw_response,
        )

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def get_coverage(self, *, window_days: int | None = None) -> dict[str, Any]:
        """Coverage and volume for the org: mailboxes protected vs not, and
        what was analysed over the window.

        Args:
            window_days: Days of volume to summarise (server default applies
                when omitted).

        Returns:
            The coverage summary, including the mailbox states that are NOT
            protected — a mailbox we cannot subscribe is reported as broken
            rather than omitted, so the number is a coverage statement rather
            than a count of what happened to work.
        """
        pairs: list[tuple[str, str]] = []
        _add_scalar(pairs, "window_days", window_days)
        return self._get("coverage", pairs)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def list_messages(
        self,
        *,
        verdict: list[str] | None = None,
        mailbox: str | None = None,
        sender_email: str | None = None,
        sender_domain: str | None = None,
        campaign_id: str | None = None,
        state: list[str] | None = None,
        direction: list[str] | None = None,
        user_reported: bool | None = None,
        min_score: int | None = None,
        link_domain: str | None = None,
        attachment_sha256: str | None = None,
        since: str | None = None,
        until: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """The message index: the triage queue.

        Repeatable filters OR within a key and AND across keys.

        Args:
            verdict: ``malicious``, ``suspicious``, ``graymail``, ``benign``,
                ``unknown`` (repeatable).
            mailbox: Protected mailbox address (exact).
            sender_email: Envelope/header sender address (exact).
            sender_domain: Sender registrable root domain.
            campaign_id: Only members of one campaign.
            state: Message lifecycle state (repeatable).
            direction: ``inbound``, ``outbound``, ``internal`` (repeatable).
            user_reported: Tri-state. ``True`` only reported mail, ``False``
                only unreported, ``None`` (default) either. A human reporting
                a message is the strongest signal the product gets, so this
                is worth filtering on directly.
            min_score: Only messages at or above this score.
            link_domain: IOC pivot — who else received mail linking here.
            attachment_sha256: IOC pivot — who else received this file.
            since: Lower time bound (RFC3339 or unix seconds).
            until: Upper time bound (RFC3339 or unix seconds).
            cursor: Opaque keyset token from a previous page.
            limit: Page size (server clamps).

        Returns:
            ``{"messages": [...], "next_cursor": str}``. An empty
            ``next_cursor`` means the last page.
        """
        pairs: list[tuple[str, str]] = []
        _add_pairs(pairs, "verdict", verdict)
        _add_pairs(pairs, "state", state)
        _add_pairs(pairs, "direction", direction)
        for key, val in (
            ("mailbox", mailbox),
            ("sender_email", sender_email),
            ("sender_domain", sender_domain),
            ("campaign_id", campaign_id),
            ("min_score", min_score),
            ("link_domain", link_domain),
            ("attachment_sha256", attachment_sha256),
            ("since", since),
            ("until", until),
            ("cursor", cursor),
            ("limit", limit),
            ("user_reported", user_reported),
        ):
            _add_scalar(pairs, key, val)
        return self._get("messages", pairs)

    def get_message(self, msg_uuid: str) -> dict[str, Any]:
        """One message: the index row plus the re-parsed MDM (the drawer).

        The MDM is not stored in Spanner — the index row is a summary and the
        raw bytes live in object storage — so the drawer re-parses the stored
        EML and says which path produced it (``mdm_source``). Enrichments are
        deliberately ABSENT rather than recomputed: they were resolved against
        sender profiles as they existed at ingest, and synthesising today's
        values would show a reputation the verdict was never based on.

        An unknown id returns ``{"message": None}`` rather than an error: the
        index has a 35-day TTL, so a miss is a normal outcome.
        """
        return self._get(f"messages/{msg_uuid}")

    def get_message_eml(self, msg_uuid: str, justification: str) -> Any:
        """The original RFC822 bytes of a message.

        Requires ``mailsec.get.eml`` — a different privilege from opening the
        drawer, because this takes a person's actual mail out of the building.
        The justification is REQUIRED and is written to the access audit with
        the caller's identity; there is no way to fetch these bytes without
        leaving a record of why.

        Args:
            msg_uuid: The message.
            justification: Why the download is happening. Stored verbatim.
        """
        if not justification or not justification.strip():
            raise ValueError(
                "a justification is required to download raw mail: the access is audited, "
                "and an unexplained one is not auditable"
            )
        return self._get(
            f"messages/{msg_uuid}/eml",
            [("justification", justification)],
        )

    def list_similar_messages(
        self,
        msg_uuid: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Messages clustered with this one — the campaign view from a single
        message, which is how "who else got this" is answered."""
        pairs: list[tuple[str, str]] = []
        _add_scalar(pairs, "cursor", cursor)
        _add_scalar(pairs, "limit", limit)
        return self._get(f"messages/{msg_uuid}/similar", pairs)

    def act_on_message(
        self,
        msg_uuid: str,
        action: str,
        *,
        reason: str | None = None,
        attempt: str | None = None,
        banner: str | None = None,
    ) -> dict[str, Any]:
        """Remediate one message at the provider. Requires ``mailsec.act``.

        Executed by the collector that holds the org's lease — the single
        choke point where the org's alert_only/enforce mode is applied and the
        audit row is written. Idempotent per (message, action).

        Args:
            msg_uuid: The message to act on.
            action: ``quarantine_message``, ``trash_message``,
                ``restore_message``, ``apply_banner``, ``remove_banner``.
            reason: Free-text justification recorded on the audit row.
            attempt: Caller-supplied idempotency token.
            banner: Banner HTML, for the banner actions.

        Returns:
            The action record, including ``result`` — note ``alert_only``,
            which means the action was DECIDED and deliberately not performed
            because the org is not in enforce mode. That is a success, not a
            failure, and it is reported as its own result rather than as
            ``ok``.
        """
        body: dict[str, Any] = {"action": action}
        for key, val in (("reason", reason), ("attempt", attempt), ("banner", banner)):
            if val is not None:
                body[key] = val
        return self._post(f"messages/{msg_uuid}/actions", body)

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def list_campaigns(
        self,
        *,
        state: list[str] | None = None,
        verdict: list[str] | None = None,
        min_members: int | None = None,
        since: str | None = None,
        until: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Campaigns: one attack, triaged once, rather than once per mailbox."""
        pairs: list[tuple[str, str]] = []
        _add_pairs(pairs, "state", state)
        _add_pairs(pairs, "verdict", verdict)
        for key, val in (
            ("min_members", min_members),
            ("since", since),
            ("until", until),
            ("cursor", cursor),
            ("limit", limit),
        ):
            _add_scalar(pairs, key, val)
        return self._get("campaigns", pairs)

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        """One campaign with its aggregates and cluster keys."""
        return self._get(f"campaigns/{campaign_id}")

    def act_on_campaign(
        self,
        campaign_id: str,
        action: str,
        *,
        confirm: str | None = None,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Sweep an action across every member of a campaign.

        Requires ``mailsec.act``.

        ``confirm`` is what turns a PREVIEW into an EXECUTION. Without it the
        call reports what it would do and changes nothing — which is the right
        default for an operation whose blast radius is "every mailbox that got
        this attack".

        Args:
            campaign_id: The campaign to sweep.
            action: The typed action, as for :meth:`act_on_message`.
            confirm: Pass the campaign id to execute. Omit to preview.
            reason: Recorded on every resulting audit row.
            actor: Ignored if supplied — the gateway stamps the acting
                identity from the authenticated claims, so an audit trail's
                subject can never be chosen by its subject.
        """
        body: dict[str, Any] = {"action": action}
        for key, val in (("confirm", confirm), ("reason", reason), ("actor", actor)):
            if val is not None:
                body[key] = val
        return self._post(f"campaigns/{campaign_id}/actions", body)

    # ------------------------------------------------------------------
    # Senders and the audit trail
    # ------------------------------------------------------------------

    def get_sender_profile(self, key: str) -> dict[str, Any]:
        """A sender's history with this org: prevalence, first seen, how much
        of their mail has been flagged.

        Args:
            key: An address (``cfo@corp.example``) or a domain
                (``corp.example``), optionally prefixed ``email:`` /
                ``domain:`` to disambiguate.
        """
        return self._get(f"senders/{key}")

    def get_action(self, action_id: str) -> dict[str, Any]:
        """One record from the action audit trail: what was decided, by whom,
        why, and what the provider actually did."""
        return self._get(f"actions/{action_id}")

    # ------------------------------------------------------------------
    # Standalone analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        *,
        eml: str | None = None,
        eml_b64: str | None = None,
        org_domains: list[str] | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        """Parse and score an EML without ingesting it.

        Nothing is persisted and no mailbox is touched — this is the "what
        would you say about this file" path, served by the stateless api-mode
        actor rather than by the collector.

        Args:
            eml: Raw RFC822 text.
            eml_b64: The same bytes base64-encoded, for content that does not
                survive a text field.
            org_domains: The org's own domains, which is what makes direction
                and impersonation computable.
            direction: Override the computed direction.
        """
        if not eml and not eml_b64:
            raise ValueError("analyze needs the message: pass eml or eml_b64")
        body: dict[str, Any] = {}
        for key, val in (
            ("eml", eml),
            ("eml_b64", eml_b64),
            ("org_domains", org_domains),
            ("direction", direction),
        ):
            if val is not None:
                body[key] = val
        return self._post("analyze", body)

    # ------------------------------------------------------------------
    # Abuse-mailbox report queue
    # ------------------------------------------------------------------

    def list_reports(
        self,
        *,
        status: list[str] | None = None,
        oldest_first: bool | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """The user-report queue: what the org's own people reported.

        Args:
            status: ``open``, ``triaging``, ``resolved`` (repeatable).
            oldest_first: Order by AGE rather than recency. This is what makes
                the queue an SLA surface — "the oldest thing nobody has looked
                at" is the question a queue exists to answer, and it is not
                answerable from a newest-first page.
            cursor: Opaque keyset token.
            limit: Page size.

        Returns:
            ``{"reports": [...], "next_cursor": str}``. Each report carries
            ``original_found``, which is explicit rather than inferred from an
            empty id: a report whose original was never indexed is a real
            state (the message predates the connection, or landed outside
            scope) and the queue shows it as a gap rather than as a blank
            field that reads like a loading bug.
        """
        pairs: list[tuple[str, str]] = []
        _add_pairs(pairs, "status", status)
        for key, val in (
            ("oldest_first", oldest_first),
            ("cursor", cursor),
            ("limit", limit),
        ):
            _add_scalar(pairs, key, val)
        return self._get("reports", pairs)

    def get_report(self, report_id: str) -> dict[str, Any]:
        """One report: who reported it, the message they reported, and the
        original it refers to once located across the tenant's mailboxes.

        An unknown id returns ``{"report": None}``, matching the message
        drawer, so a client branches on null rather than on a status code.
        """
        return self._get(f"reports/{report_id}")

    def resolve_report(self, report_id: str, disposition: str) -> dict[str, Any]:
        """Close a report with a disposition. Requires ``mailsec.set``.

        Args:
            report_id: The report.
            disposition: ``true_positive`` (it was malicious),
                ``false_positive`` (we flagged it and it was fine), or
                ``benign`` (it was never a threat). ``unknown`` is a real
                stored value but is NOT resolvable by a human: as the outcome
                of someone closing a report it means "I looked and decided
                nothing", which is indistinguishable in the SLA numbers from
                never having looked.

        Returns:
            The updated report plus ``already_resolved``. Resolving twice
            succeeds and says so — two analysts clicking at once is ordinary,
            and the second must not get a failure for an outcome that already
            holds.
        """
        return self._post(f"reports/{report_id}/resolve", {"disposition": disposition})

    # ------------------------------------------------------------------
    # Hunts
    # ------------------------------------------------------------------

    def create_hunt(
        self,
        *,
        detect: dict[str, Any] | None = None,
        lcql: str | None = None,
        since: str | None = None,
        until: str | None = None,
        dry_run: bool | None = None,
    ) -> dict[str, Any]:
        """Start a retro-hunt over message history.

        Args:
            detect: A D&R detect block to match.
            lcql: An LCQL query, as an alternative to ``detect``.
            since: Lower time bound.
            until: Upper time bound.
            dry_run: Estimate cost and match count without running.
        """
        body: dict[str, Any] = {}
        for key, val in (
            ("detect", detect),
            ("lcql", lcql),
            ("since", since),
            ("until", until),
            ("dry_run", dry_run),
        ):
            if val is not None:
                body[key] = val
        return self._post("hunts", body)

    def get_hunt(self, hunt_id: str) -> dict[str, Any]:
        """A hunt's status and results."""
        return self._get(f"hunts/{hunt_id}")

    def remediate_hunt(
        self,
        hunt_id: str,
        action: str,
        *,
        confirm: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Bulk-remediate a hunt's results. Requires ``mailsec.act``.

        Like a campaign sweep, ``confirm`` is what turns a preview into an
        execution.
        """
        body: dict[str, Any] = {"action": action}
        for key, val in (("confirm", confirm), ("reason", reason)):
            if val is not None:
                body[key] = val
        return self._post(f"hunts/{hunt_id}/remediate", body)

    # ------------------------------------------------------------------
    # Custom rules
    # ------------------------------------------------------------------

    def validate_rule(
        self,
        rule: dict[str, Any],
        *,
        rule_id: str | None = None,
    ) -> dict[str, Any]:
        """Check a candidate rule without saving it.

        Runs the SAME validation the ``dr-mail`` hive applies on save, so a
        rule this accepts is a rule that will save. An invalid rule is a
        successful response carrying ``valid: false`` and the reason — it is
        the ANSWER to the question, not a failure to answer it.

        Args:
            rule: The rule body (``name``, ``fp_notes``, ``phase``,
                ``weight``, ``detect``, ...).
            rule_id: The rule id. Tenant rule ids must start with
                ``custom-``; omitting it validates against a placeholder in
                that namespace so an unnamed draft is not refused for a name
                it was never asked for.
        """
        body: dict[str, Any] = {"rule": rule}
        if rule_id is not None:
            body["rule_id"] = rule_id
        return self._post("rules/validate", body)

    def backtest_rule(
        self,
        rule: dict[str, Any],
        *,
        rule_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        """Replay a candidate rule over recent mail and report what it would
        have matched.

        Bounded to the window this product retains rather than the
        full-history retro-hunt, and every response says so in
        ``coverage_note``. It also counts what it could NOT examine
        (``skipped_no_raw``, ``skipped_unparse``, ``truncated``), because a
        precision figure whose denominator silently shrank is a number that
        looks like a measurement and is not one.

        ``precision`` is ``None`` — not ``0`` — when nothing it matched has an
        analyst disposition yet. Zero would read as "everything it matched was
        wrong" and would have an author discard a good rule.
        """
        body: dict[str, Any] = {"rule": rule}
        for key, val in (("rule_id", rule_id), ("since", since), ("until", until)):
            if val is not None:
                body[key] = val
        return self._post("rules/backtest", body)

    # ------------------------------------------------------------------
    # Connections and onboarding
    # ------------------------------------------------------------------

    def test_connection(self, record: str) -> dict[str, Any]:
        """Exercise a saved provider connection end to end.

        Takes the RECORD NAME of a ``mailsec_provider`` hive record, never a
        credential: the credential stays in the secret hive and is resolved
        server-side by the pod that owns the connection. Reports what the
        connection can actually do — directory access, mail read, and the
        per-connection capabilities that depend on which scopes the customer's
        admin granted.
        """
        return self._post(f"connections/{record}/test", {})

    def get_onboarding(self, *, provider: str | None = None) -> dict[str, Any]:
        """The setup guide for connecting a mail provider, with this org's own
        values already substituted in.

        Served by the backend rather than written into the docs or the web app
        so that the identifiers a customer must paste — the service account,
        the topic, the subscription — are the real ones for this deployment
        rather than placeholders a reader has to translate.
        """
        pairs: list[tuple[str, str]] = []
        _add_scalar(pairs, "provider", provider)
        return self._get("onboarding", pairs)
