"""Email Security (mailsec) SDK for LimaCharlie v2.

Wraps the ``/mailsec/{oid}/...`` REST routes served by the API gateway: the
coverage screen, the message index and its drawer, the justified raw-EML
download, analyst verdict revision and its history, bulk remediation across a
caller-supplied selection, campaigns, sender profiles, the action audit trail,
the abuse-mailbox report queue and its reopen, standalone EML analysis,
retro-hunts, custom-rule validation and backtest, the provider connection
preflight, and the served onboarding guide.

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

import base64
import binascii
import json
from typing import Any, TYPE_CHECKING
from urllib.parse import quote as _quote

if TYPE_CHECKING:
    from .organization import Organization


# Verdict-revision rationale bounds, mirrored client-side so a caller learns
# the limit from a clear local error rather than from a 400 after the round
# trip. These match the gateway's own validation: at least one line, at most
# ten, each no longer than 280 characters.
_MAX_RATIONALE_LINES = 10
_MAX_RATIONALE_LEN = 280


# The bulk remediation vocabulary, for documentation and for building help text.
#
# It is the per-message vocabulary plus ``move_to_spam`` and minus
# ``submit_to_triage``: bulk-submitting 500 messages to triage is not a bulk
# remediation but a bulk SPEND, so it sits behind a decision about cost rather
# than behind a preview that reports placement.
#
# Nothing in this module validates against it. The server owns the vocabulary,
# names the whole set in its refusal (``error_code: bulk_unsupported_action``,
# with ``supported_actions``), and a client-side copy that went stale would
# refuse an action the backend had just started supporting.
BULK_ACTIONS = (
    "quarantine_message",
    "trash_message",
    "move_to_spam",
    "restore_message",
    "banner_message",
    "unbanner_message",
)


def normalize_bulk_selection(msg_uuids: Any) -> list[str]:
    """Trim, drop blanks, deduplicate and sort a bulk selection.

    This mirrors the server's own normalization step for step, and that IS the
    contract rather than a tidy-up: the confirmation token a preview mints is
    derived from the normalized member list, so previewing one selection and
    executing a different one is refused instead of acting on messages nobody
    approved. Normalizing once and reusing the result for both calls is what
    makes the two lists provably the same list.

    Deduplication is a safety property and not only a convenience — a repeated
    id would otherwise be counted twice in the totals a human reads.

    The CAP is deliberately NOT applied here. 500 is the server's policy, it is
    re-checked on every call, and a second copy in the client would be a limit
    that drifts. A client that silently truncated a 900-message selection to fit
    would leave the remaining 400 in inboxes nobody is going to look at, which is
    why the server refuses an oversized selection rather than trimming it.

    Raises:
        ValueError: when the selection is empty once blanks are dropped. A bulk
            action over nothing is a caller bug worth surfacing rather than a
            successful no-op.
    """
    if isinstance(msg_uuids, str):
        raise ValueError(
            "msg_uuids must be a list of message ids, not a single string: pass "
            "[uuid] rather than uuid so a selection of one is still a selection"
        )
    out: list[str] = []
    seen: set[str] = set()
    for raw in msg_uuids or []:
        if not isinstance(raw, str):
            raise ValueError(f"every msg_uuid must be a string; found a {type(raw).__name__}")
        value = raw.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    if not out:
        raise ValueError("a bulk action needs at least one msg_uuid")
    out.sort()
    return out


def _seg(value: str) -> str:
    """Escape one caller-supplied path segment.

    `safe=""` so a slash is escaped too. Most of these ids are UUIDs the server
    minted and are harmless either way, but two are arbitrary user input: the
    sender key is an address or domain a person types, and the connection record
    is a hive record name. An unescaped slash in either silently addresses a
    DIFFERENT route rather than failing, which is the shape that turns a typo
    into a request nobody intended.
    """
    return _quote(str(value), safe="")


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
        return self._get(f"messages/{_seg(msg_uuid)}")

    def get_message_eml(self, msg_uuid: str, justification: str) -> bytes:
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
        response = self._get(
            f"messages/{_seg(msg_uuid)}/eml",
            [("justification", justification)],
        )
        if not isinstance(response, dict) or not isinstance(response.get("eml_b64"), str):
            raise ValueError("mailsec EML response did not contain eml_b64")
        try:
            raw = base64.b64decode(response["eml_b64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("mailsec EML response contained invalid base64") from exc
        size = response.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size != len(raw):
            raise ValueError(
                f"mailsec EML response size mismatch: declared {size!r}, decoded {len(raw)}"
            )
        return raw

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
        return self._get(f"messages/{_seg(msg_uuid)}/similar", pairs)

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
                ``restore_message``, ``banner_message``, ``unbanner_message``.
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
        for key, val in (("reason", reason), ("attempt", attempt), ("banner_html", banner)):
            if val is not None:
                body[key] = val
        return self._post(f"messages/{_seg(msg_uuid)}/actions", body)

    def revise_verdict(
        self,
        msg_uuid: str,
        verdict: str,
        rationale: list[str],
        *,
        mode: str = "analyst",
        score: float | None = None,
    ) -> dict[str, Any]:
        """Revise the verdict on one message. Requires ``mailsec.act``.

        This records a human's disposition over the scorer's — a triage
        decision, not a remediation — and appends a revision to the message's
        immutable verdict history rather than overwriting the last one.

        ``mode`` defaults to ``analyst`` because the caller of this SDK from
        the CLI is a person. An autonomous agent revises with its own key and
        ``mode="ai"``; the two are kept distinct so the audit trail can always
        say whether a person or a model decided.

        The rationale is REQUIRED and audited: at least one line, at most ten,
        each no longer than 280 characters. The bounds are checked here so a
        caller gets a clear local error instead of a 400 after the round trip.

        Args:
            msg_uuid: The message whose verdict is being revised.
            verdict: ``malicious``, ``suspicious``, ``graymail``, ``benign``,
                or ``unknown``.
            rationale: One or more free-text lines explaining the change.
            mode: The deciding actor's mode; ``analyst`` for a human,
                ``ai`` for an agent. The gateway stamps the actor identity
                itself — this only says which KIND of actor decided.
            score: An optional numeric score to record alongside the verdict.

        Returns:
            The revision result. ``applied`` is the honest outcome to read:
            ``applied: false`` means the message was already at this verdict
            and nothing changed — a no-op reported truthfully, not an error.
            The response also carries ``revision_seq``, ``prior``, and
            ``newly_flagged``.
        """
        if not rationale:
            raise ValueError(
                "a verdict revision needs at least one rationale line: the change is "
                "audited, and an unexplained one is not auditable"
            )
        if len(rationale) > _MAX_RATIONALE_LINES:
            raise ValueError(
                f"too many rationale lines: {len(rationale)} given, at most "
                f"{_MAX_RATIONALE_LINES} allowed"
            )
        for line in rationale:
            if not isinstance(line, str) or not line.strip():
                raise ValueError("every rationale line must be non-empty text")
            if len(line) > _MAX_RATIONALE_LEN:
                raise ValueError(
                    f"a rationale line is too long: {len(line)} characters, at most "
                    f"{_MAX_RATIONALE_LEN} allowed"
                )
        body: dict[str, Any] = {
            "verdict": verdict,
            "mode": mode,
            "rationale": list(rationale),
        }
        if score is not None:
            body["score"] = score
        return self._post(f"messages/{_seg(msg_uuid)}/verdict", body)

    def list_revisions(self, msg_uuid: str) -> dict[str, Any]:
        """The verdict revision history for one message, oldest first.

        Requires ``mailsec.get``. Every entry carries its ``seq``, the
        ``mode`` and ``actor`` that decided it, the ``verdict`` it set, its
        ``decided_at`` time, and the ``rationale`` given — the audit of how a
        message's disposition moved over time, read from the bottom up.
        """
        return self._get(f"messages/{_seg(msg_uuid)}/revisions")

    # ------------------------------------------------------------------
    # Bulk remediation by message id
    # ------------------------------------------------------------------
    #
    # The campaign sweep's preview-then-confirm discipline over a selection the
    # CALLER names rather than a cluster the backend clusters — which is what
    # turns any search result (the message index, a hunt, a shell pipeline) into
    # provider-side action.
    #
    # Three routes rather than two, because the execute CANNOT finish inside a
    # request: 500 provider writes paced to respect Microsoft 365 / Google
    # throttling do not fit the gateway's action budget. Execute therefore
    # returns a handle and the work proceeds on the collector, so a caller polls
    # :meth:`bulk_action_status` for outcomes.

    def bulk_action_preview(
        self,
        action: str,
        msg_uuids: Any,
        *,
        attempt: str | None = None,
    ) -> dict[str, Any]:
        """Report what a bulk action would do, and mint the confirmation that
        authorizes exactly that. Requires ``mailsec.get``.

        NOTHING IS CHANGED and no job is created. This reads the message index
        and reports, per message, whether it still exists, its current verdict
        and placement, and whether it is already where the action would put it.

        It REPORTS rather than refuses. A message that expired past the 35-day
        retention, and a message already in the target state, are both reported
        and both stay in the confirmed set — acting on a search result taken
        minutes ago legitimately includes both, and failing the batch over one
        expired id would make the feature unusable at exactly the window it
        exists for. An already-done message is still executed rather than
        filtered out, because ``already_in_target_state`` is read off the index
        and is ADVISORY: the index records where remediation last put a message
        and its owner may have moved it since, so the provider re-checks and
        answers ``skipped``.

        Args:
            action: One of :data:`BULK_ACTIONS`.
            msg_uuids: The selection. Normalized by
                :func:`normalize_bulk_selection` before it is sent.
            attempt: Caller-supplied idempotency token. It participates in the
                confirmation, so a NEW attempt over the same selection is a new
                token, a new job, and a deliberate second run — which is the
                escape hatch for acting on the same messages again.

        Returns:
            The per-message report in ``messages``, a ``summary``
            (``total``/``found``/``missing``/``already_in_target_state``/
            ``actionable``/``mailbox_count``/``by_provider`` — note
            ``mailbox_count``, which is the blast radius an operator actually
            reasons about), the ``cap``, and a ``confirm`` token DERIVED FROM
            THE EXACT SELECTION. Pass that token, this action, this attempt and
            this same list to :meth:`bulk_action_execute`; any change to the
            selection invalidates it.

        Raises:
            ValueError: on an empty selection. An oversized one is refused by
                the server, which names the cap and answers
                ``error_code: bulk_too_large`` so a caller can split rather
                than guess.
        """
        body: dict[str, Any] = {
            "action": action,
            "msg_uuids": normalize_bulk_selection(msg_uuids),
        }
        if attempt is not None:
            body["attempt"] = attempt
        return self._post("actions/bulk/preview", body)

    def bulk_action_execute(
        self,
        action: str,
        msg_uuids: Any,
        confirm: str,
        *,
        attempt: str | None = None,
        banner: str | None = None,
    ) -> dict[str, Any]:
        """Execute a previewed bulk action. Requires ``mailsec.act``.

        ASYNCHRONOUS, and the shape is not a convenience: up to 500 provider
        writes paced by the collector's rate governor cannot fit in one request,
        so this RETURNS IMMEDIATELY with a ``bulk_id`` and the work proceeds in
        the background. A caller that reported "quarantined 300 messages" off
        this response would be reporting what was asked for, not what happened;
        poll :meth:`bulk_action_status` for that.

        Idempotent by construction. The confirmation re-derives to a fixed bulk
        id, so re-sending the same request ADOPTS the existing job rather than
        acting twice, and each member's action collapses onto the audit row it
        already has. That is also the repair for a job whose worker died —
        status reports ``stalled``, and one more execute with the same
        confirmation finishes it.

        Partial failure is a normal, honestly-reported outcome and never a
        rollback: provider actions are not transactional, and "restoring" a
        message we quarantined is a second visible move in somebody's mailbox
        rather than an undo.

        Args:
            action: The action the preview was taken over. It is part of the
                confirmation, so it must match.
            msg_uuids: The SAME selection the preview was taken over. Normalized
                identically here, so passing the preview's own list back is
                enough; passing a different set is refused rather than acted on.
            confirm: The token from :meth:`bulk_action_preview`.
            attempt: The same attempt the preview used, when one was used.
            banner: Banner HTML for ``banner_message``, supplied once for the
                whole batch — it carries the org's text, which is a property of
                the org rather than of any one message.

        Returns:
            ``{"accepted": True, "bulk_id": str, "state": str, "counts": {...},
            "member_count": int, "started": bool, "already_running": bool,
            "already_complete": bool}``. ``started: false`` means this call
            adopted a job that already existed, which is the idempotent path and
            not a failure.

        Note:
            There is deliberately no ``reason``. The gateway forwards only
            ``action``, ``msg_uuids``, ``confirm``, ``attempt`` and the banner on
            this route, so a reason would be accepted by this client and dropped
            in transit — a justification that silently never reaches the audit
            trail is worse than one the caller knows it cannot give. Per-message
            reasons remain available through :meth:`act_on_message`.
        """
        body: dict[str, Any] = {
            "action": action,
            "msg_uuids": normalize_bulk_selection(msg_uuids),
            "confirm": confirm,
        }
        for key, val in (("attempt", attempt), ("banner", banner)):
            if val is not None:
                body[key] = val
        return self._post("actions/bulk/execute", body)

    def bulk_action_status(self, bulk_id: str) -> dict[str, Any]:
        """A bulk action's progress and per-message outcomes. Requires
        ``mailsec.get``.

        Args:
            bulk_id: The handle returned by :meth:`bulk_action_execute`. A
                preview mints no job and an ordinary action id is not one;
                either returns a typed not-found rather than a partial answer.

        Returns:
            ``state`` (``running``, ``complete`` or ``interrupted``), ``counts``
            (``ok``/``skipped``/``failed``/``alert_only``/``not_found``/
            ``pending``/``total``), and ``items`` — each member's ``result``,
            its ``reason``, and the ``action_id`` of its authoritative audit row,
            expandable through :meth:`get_action`.

            ``state`` and the row's outcome are separate on purpose: a job that
            finished with six failures is ``complete``, because the question a
            poller asks is whether anything is still moving.

            ``stalled`` is the field that makes a dead worker visible. The job
            record is heartbeaten whether or not anything changed, so a running
            job whose record has not moved is one nobody is working — and the
            repair is one more execute with the same confirmation, which is safe
            because every message already acted on collapses onto its existing
            action row.

            ``items`` is a projection of the job record rather than a re-read of
            the audit rows (``items_source: bulk_record``), so it can lag by up
            to one heartbeat. It says so rather than presenting itself as the
            audit trail, because a lag that looked authoritative would look like
            a lost action.
        """
        return self._get(f"actions/bulk/{_seg(bulk_id)}")

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
        return self._get(f"campaigns/{_seg(campaign_id)}")

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
            confirm: Pass the member-bound token returned by the preview to
                execute. Omit to preview.
            reason: Recorded on every resulting audit row.
            actor: Ignored if supplied — the gateway stamps the acting
                identity from the authenticated claims, so an audit trail's
                subject can never be chosen by its subject.
        """
        body: dict[str, Any] = {"action": action}
        for key, val in (("confirm", confirm), ("reason", reason), ("actor", actor)):
            if val is not None:
                body[key] = val
        return self._post(f"campaigns/{_seg(campaign_id)}/actions", body)

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
        return self._get(f"senders/{_seg(key)}")

    def get_action(self, action_id: str) -> dict[str, Any]:
        """One record from the action audit trail: what was decided, by whom,
        why, and what the provider actually did."""
        return self._get(f"actions/{_seg(action_id)}")

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
        return self._get(f"reports/{_seg(report_id)}")

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
        return self._post(f"reports/{_seg(report_id)}/resolve", {"disposition": disposition})

    def reopen_report(self, report_id: str) -> dict[str, Any]:
        """Reopen a resolved report. Requires ``mailsec.set``.

        The inverse of :meth:`resolve_report`: a report closed too early, or
        closed and then contradicted by new evidence, returns to the queue
        rather than staying settled on a disposition that no longer holds.

        Reopening an already-open report succeeds and says so — the queue's
        state is what matters, not who raced to change it — so a client does
        not have to treat "already open" as a failure.
        """
        return self._post(f"reports/{_seg(report_id)}/reopen", {})

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
        return self._get(f"hunts/{_seg(hunt_id)}")

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
        return self._post(f"hunts/{_seg(hunt_id)}/remediate", body)

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

    def test_connection(self, record: str, *, include_watch: bool = False) -> dict[str, Any]:
        """Exercise a saved provider connection end to end.

        Takes the RECORD NAME of a ``mailsec_provider`` hive record, never a
        credential: the credential stays in the secret hive and is resolved
        server-side by the pod that owns the connection. Reports what the
        connection can actually do — directory access, mail read, and the
        per-connection capabilities that depend on which scopes the customer's
        admin granted.

        Args:
            record: Saved ``mailsec_provider`` record name.
            include_watch: Opt in to the side-effecting Workspace push probe.
                The provider establishes or replaces a real watch; the call is
                idempotent and the watch expires on its provider schedule.
        """
        body: dict[str, Any] = {}
        if include_watch:
            body["include_watch"] = True
        return self._post(f"connections/{_seg(record)}/test", body)

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
