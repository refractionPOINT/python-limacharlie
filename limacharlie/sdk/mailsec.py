"""Email Security (mailsec) SDK for LimaCharlie v2.

Wraps the ``/mailsec/{oid}/...`` REST routes served by the API gateway: the
coverage screen, the message index and its drawer, the justified raw-EML
download, analyst verdict revision and its history, bulk remediation across a
caller-supplied selection, campaigns, sender profiles, the action audit trail,
the abuse-mailbox report queue and its reopen, customer sample submission
(copy one message to LimaCharlie, list and withdraw what was sent), standalone
EML analysis,
custom-rule validation and backtest, the provider connection
preflight, the served onboarding guide, and the irreversible tenant purge.

Permissions, which are four rather than the usual get/set pair because mailsec
asks to be trusted with four different things:

- ``mailsec.get``     read the product's own view: the queue, the drawer,
                      campaigns, sender profiles, the audit trail
- ``mailsec.set``     change detection behaviour and triage state
- ``mailsec.act``     remediate live mail at the provider
- ``mailsec.get.eml`` take the original bytes of somebody's mail out of the
                      building; requires a logged justification

The one exception is the tenant purge (:meth:`Mailsec.prepare_tenant_purge`
and :meth:`Mailsec.purge_tenant`), which is Owner-level rather than mailsec
-level: it wants ``mailsec.act`` AND ``billing.ctrl`` AND ``user.ctrl``, the
same trio org deletion asks for, because destroying a product's entire record
for a tenant is an ownership decision rather than an analyst one.

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
import re
import time
import warnings
import uuid
from typing import Any, Callable, TYPE_CHECKING
from urllib.parse import quote as _quote

if TYPE_CHECKING:
    from .organization import Organization


# Verdict-revision rationale bounds, mirrored client-side so a caller learns
# the limit from a clear local error rather than from a 400 after the round
# trip. These match the gateway's own validation: at least one line, at most
# ten, each no longer than 280 characters.
DISPOSITIONS = ("malicious", "spam", "graymail", "benign", "simulation")

_MAX_RATIONALE_LINES = 10
_MAX_RATIONALE_LEN = 280


# The audited reason on a tenant purge, bounded the same way and for the same
# reason, with one extra: the confirmation token a purge spends is single-use
# and lives five minutes, so learning about an over-long reason from the server
# costs a re-mint. Checking here costs nothing.
_MAX_PURGE_REASON_LEN = 1024


# Customer sample submission. A person may copy ONE message at a time to
# LimaCharlie so detection can improve, when the org has opted in.
#
# Unlike the remediation vocabulary above, the category set IS validated
# client-side: it is closed, the server refuses anything else with a 400, and a
# submission is a disclosure of somebody's mail, so the caller should learn
# from a local error that a typo was not sent rather than after the round trip.
# The reason is bounded the same way the server bounds it (1..1024 characters
# after trimming; required for a submission, optional for a withdrawal).
SAMPLE_CATEGORIES = ("missed_threat", "false_positive", "other")
_MAX_SAMPLE_REASON_LEN = 1024
_MAX_SUBMISSION_PAGE = 200


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


# The states in which a bulk job has stopped moving of its own accord.
#
# ``interrupted`` belongs here with ``complete``: a worker that lost its pod
# finalizes the record with whatever outcomes it had, so the answer has already
# arrived and polling for a different one only burns the wait. What is NOT here
# is ``stalled``, which is a flag on a still-``running`` record rather than a
# state, and which is terminal for a different reason — see
# :meth:`Mailsec.wait_for_bulk`.
BULK_TERMINAL_STATES = ("complete", "interrupted")


def _check_force(force: Any) -> bool:
    """Validate the ``force`` argument of a remediation call.

    The server forces only on a JSON boolean ``true``, so a truthy non-bool
    (``1``, ``"yes"``) would either be sent as something it ignores or not be
    sent at all. Either way the caller believes they forced and nothing moved,
    so it is refused here instead.
    """
    if not isinstance(force, bool):
        raise TypeError(f"force must be a bool, not {type(force).__name__}")
    return force


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


def _check_sample_reason(reason: Any, *, required: bool) -> str:
    """Trim and bound the reason on a sample submission or withdrawal.

    The server trims and then requires 1..1024 characters for a submission
    (and at most 1024 for a withdrawal). Checking here, on the trimmed text,
    means a caller learns the limit locally and sends exactly what the server
    will record.
    """
    if reason is None:
        if required:
            raise ValueError(
                "a sample submission needs a reason: it is kept with the submission "
                "so the person reviewing it knows why you sent it"
            )
        return ""
    if not isinstance(reason, str):
        raise ValueError("reason must be text")
    text = reason.strip()
    if required and not text:
        raise ValueError(
            "a sample submission needs a reason: it is kept with the submission "
            "so the person reviewing it knows why you sent it"
        )
    if len(text) > _MAX_SAMPLE_REASON_LEN:
        raise ValueError(
            f"reason is {len(text)} characters; at most {_MAX_SAMPLE_REASON_LEN} are allowed"
        )
    return text


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




def _group_identity(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("group_id must be a lowercase SHA-256 identity")
    return value


def _group_job_identity(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value):
        raise ValueError("job/preview identity must be a lowercase UUID")
    return value


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

    def _delete(
        self,
        path: str,
        query_params: list[tuple[str, str]] | None = None,
        *,
        raw_response: bool = False,
    ) -> Any:
        return self._org.client.request(
            "DELETE",
            f"mailsec/{self.oid}/{path}",
            query_params=query_params or None,
            raw_response=raw_response,
        )

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def get_coverage(
        self, *, window_days: int | None = None,
        since: str | None = None, until: str | None = None,
    ) -> dict[str, Any]:
        """Coverage and volume for the org: mailboxes protected vs not, and
        what was analysed over the window.

        Args:
            window_days: Days of volume to summarise (server default applies
                when omitted). Cannot be combined with since or until.
            since: Start of the volume window (RFC3339 or unix seconds).
            until: End of the volume window (RFC3339 or unix seconds).

        Returns:
            The coverage summary, including the mailbox states that are NOT
            protected — a mailbox we cannot subscribe is reported as broken
            rather than omitted, so the number is a coverage statement rather
            than a count of what happened to work.

        Raises:
            ValueError: If window_days is combined with since or until.
        """
        if window_days is not None and (since is not None or until is not None):
            raise ValueError("window_days cannot be combined with since or until")
        pairs: list[tuple[str, str]] = []
        _add_scalar(pairs, "window_days", window_days)
        _add_scalar(pairs, "since", since)
        _add_scalar(pairs, "until", until)
        return self._get("coverage", pairs)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def list_messages(
        self,
        *,
        verdict: list[str] | None = None,
        severity: list[str] | None = None,
        group_id: str | None = None,
        mailbox: str | None = None,
        sender_email: str | None = None,
        sender_domain: str | None = None,
        campaign_id: str | None = None,
        state: list[str] | None = None,
        direction: list[str] | None = None,
        lane: str | None = None,
        disposition: str | None = None,
        user_reported: bool | None = None,
        min_score: int | None = None,
        link_domain: str | None = None,
        attachment_sha256: str | None = None,
        q: str | None = None,
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
            sender_domain: Sender registrable root domain. Sent to the API as
                ``sender_root_domain``; the Python name is retained for
                compatibility with existing callers.
            campaign_id: Only members of one campaign.
            group_id: Only recipient copies in one message group.
            severity: Rule impact (informational, low, medium, high, critical), repeatable.
            state: Message lifecycle state (repeatable).
            direction: ``inbound``, ``outbound``, ``internal`` (repeatable).
            disposition: Analyst/SOAR label or ``none`` for untriaged.
            lane: ``live`` or ``backfill``. Omit to include either processing
                lane. Supported with time, verdict and IOC queries; combining
                it with mailbox, sender_email or campaign_id is refused by
                the server with ``lane_unsupported``.
            user_reported: Tri-state. ``True`` only reported mail, ``False``
                only unreported, ``None`` (default) either. A human reporting
                a message is the strongest signal the product gets, so this
                is worth filtering on directly.
            min_score: Only messages at or above this score.
            link_domain: IOC pivot — who else received mail linking here.
            attachment_sha256: IOC pivot — who else received this file.
            q: Case-insensitive text search. At most 512 code points and must
                be paired with ``since``, an exact scalar pivot, or exactly
                one verdict so the index walk stays bounded.
            since: Lower time bound (RFC3339 or unix seconds).
            until: Upper time bound (RFC3339 or unix seconds).
            cursor: Opaque keyset token from a previous page.
            limit: Page size (server clamps).

        Returns:
            ``{"messages": [...], "next_cursor": str}``. An empty
            ``next_cursor`` means the last page.

        Raises:
            ValueError: If non-empty ``q`` is too long or lacks a bounded-walk
                companion filter.
        """
        if disposition is not None and disposition not in (*DISPOSITIONS, "none"):
            raise ValueError("invalid disposition filter")
        if q is not None:
            q = q.strip() or None
        if q:
            if len(q) > 512:
                raise ValueError("q must be at most 512 code points")
            bounded = any((since, mailbox, sender_email, campaign_id, group_id, link_domain, attachment_sha256))
            single_verdict = verdict is not None and len(verdict) == 1 and bool(verdict[0].strip())
            single_severity = severity is not None and len(severity) == 1 and bool(severity[0].strip())
            if not bounded and not single_verdict and not single_severity:
                raise ValueError(
                    "q requires since, mailbox, sender_email, campaign_id, "
                    "group_id, link_domain, attachment_sha256, or exactly one verdict/severity"
                )
        pairs: list[tuple[str, str]] = []
        _add_pairs(pairs, "verdict", verdict)
        _add_pairs(pairs, "severity", severity)
        _add_pairs(pairs, "state", state)
        _add_pairs(pairs, "direction", direction)
        for key, val in (
            ("mailbox", mailbox),
            ("sender_email", sender_email),
            ("sender_root_domain", sender_domain),
            ("campaign_id", campaign_id),
            ("group_id", group_id),
            ("min_score", min_score),
            ("link_domain", link_domain),
            ("attachment_sha256", attachment_sha256),
            ("q", q),
            ("since", since),
            ("until", until),
            ("cursor", cursor),
            ("limit", limit),
            ("user_reported", user_reported),
            ("lane", lane),
            ("disposition", disposition),
        ):
            _add_scalar(pairs, key, val)
        return self._get("messages", pairs)

    def get_message(self, msg_uuid: str) -> dict[str, Any]:
        """Get the message index row, analysis status, timing, and parsed MDM.

        ``mdm_source: stored`` serves the preserved MDM used to judge the
        message, including its original enrichments. ``eml_reparse`` is a
        fallback that parses the retained EML with today's parser and leaves
        enrichments absent. Expired content yields ``mdm: null`` and an
        ``mdm_unavailable_reason`` while the index row remains available.

        The ``message.analysis`` block reports ``state`` (pending/complete),
        outstanding ``pending`` lanes, terminal ``results`` and ``completed_at``.
        Complete closes the initial analysis window; later evidence may still
        change the verdict. A terminal failure is not a clean result.
        ``message.timing`` separates provider lag, queue time, processing and
        end-to-end latency in integer milliseconds. Unknown intervals are absent.
        These blocks are null when no initial analysis record is available.

        Args:
            msg_uuid: Message UUID.

        Returns:
            Message detail, or ``{"message": None}`` for an unknown or
            expired UUID. Message-index retention is at most 35 days and may
            be shortened by the organization's retention policy.
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
        """Get recent messages sharing clustering keys with this message.

        These are candidates, not necessarily members of the same campaign.
        The response names matched keys and its lookback windows. The route
        is not paginated; the old cursor and limit arguments were ignored
        by the server and are now refused when supplied.

        Args:
            msg_uuid: Message UUID.
            cursor: Unsupported legacy parameter; leave unset.
            limit: Unsupported legacy parameter; leave unset.

        Raises:
            ValueError: If cursor or limit is supplied. Use list_messages
                with campaign_id or time/IOC filters for a paginated search.
        """
        if cursor is not None or limit is not None:
            raise ValueError(
                "similar messages are not paginated; omit cursor and limit, "
                "or use list_messages with campaign_id or time/IOC filters"
            )
        return self._get(f"messages/{_seg(msg_uuid)}/similar")

    def set_disposition(self, msg_uuid: str, disposition: str | None = None, *, note: str = "", clear: bool = False) -> dict[str, Any]:
        """Set or clear an analyst/SOAR decision without changing the verdict.

        Args:
            msg_uuid: Stable message identity.
            disposition: Malicious, spam, graymail, benign, or simulation.
            note: Optional decision note, at most 1024 characters.
            clear: Remove the label while recording who cleared it.

        Returns:
            dict: Applied flag, decision sequence, and attributed decision.

        Raises:
            ValueError: If the value/note is invalid or clear conflicts with a value.
        """
        body = _disposition_body(disposition, note, clear)
        return self._post(f"messages/{_seg(msg_uuid)}/disposition", body)

    def set_bulk_disposition(self, msg_uuids: list[str], disposition: str | None = None, *, note: str = "", clear: bool = False) -> dict[str, Any]:
        """Set one independent decision on a bounded selection of messages.

        Args:
            msg_uuids: One to 500 unique stable message identities.
            disposition: Malicious, spam, graymail, benign, or simulation.
            note: Optional decision note, at most 1024 characters.
            clear: Remove the labels while recording attribution.

        Returns:
            dict: Per-message results, with partial failures reported explicitly.

        Raises:
            ValueError: If the selection or decision is invalid.
        """
        body = _disposition_body(disposition, note, clear)
        if not 1 <= len(msg_uuids) <= 500 or len(set(msg_uuids)) != len(msg_uuids):
            raise ValueError("msg_uuids must contain 1-500 unique message ids")
        if any(not isinstance(i, str) or not i.strip() or len(i) > 36 for i in msg_uuids):
            raise ValueError("invalid message id")
        body["msg_uuids"] = msg_uuids
        return self._post("messages/dispositions", body)

    def release_message(self, msg_uuid: str, *, reason: str, mode: str = "analyst", force: bool = False) -> dict[str, Any]:
        """Restore a message, revise its verdict and set disposition to benign.

        Args:
            msg_uuid: Stable message identity.
            reason: Audited reason for releasing the message.
            mode: Analyst or ai decision mode.
            force: Override alert-only mode for this action.

        Returns:
            dict: Audited release outcome; alert_only means no changes were made.

        Raises:
            ValueError: If mode or reason is invalid.
        """
        if mode not in ("analyst", "ai") or not reason.strip() or len(reason) > 1024:
            raise ValueError("release requires a bounded reason and analyst/ai mode")
        return self._post(f"messages/{_seg(msg_uuid)}/actions", {"action": "release_message", "reason": reason, "mode": mode, "force": force})

    def act_on_message(
        self,
        msg_uuid: str,
        action: str,
        *,
        reason: str | None = None,
        attempt: str | None = None,
        text: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Remediate one message at the provider. Requires ``mailsec.act``.

        Executed by the collector that holds the org's lease — the single
        choke point where the org's alert_only/enforce mode is applied and the
        audit row is written. Idempotent per (message, action).

        Args:
            msg_uuid: The message to act on.
            action: ``quarantine_message``, ``trash_message``,
                ``restore_message``, ``banner_message``, ``unbanner_message``.
                Sample submission has its own methods: see
                :meth:`submit_sample` and :meth:`withdraw_sample`.
            reason: Free-text justification recorded on the audit row.
            attempt: Caller-supplied idempotency token.
            text: ``banner_message`` only: plain-text wording for this one
                banner, replacing the organization's default and per-verdict
                wording (title, colour and logo stay the organization's). At
                most 512 characters; ``<``, ``>`` and control characters are
                refused by the server, and other actions refuse it. The banner
                itself is always rendered by the server from the organization's
                ``mailsec_policy`` record of type ``banners`` into a fixed,
                escaped template: no caller supplies markup.
            force: Perform the action even if the organization is in
                alert-only mode (no automation in enforce mode). The override
                is recorded in the audit trail. Sent only when ``True``.

        Returns:
            The action record, including ``result`` — note ``alert_only``,
            which means the action was DECIDED and deliberately not performed
            because the org is not in enforce mode. That is a success, not a
            failure, and it is reported as its own result rather than as
            ``ok``. ``force_required: true`` accompanies it: re-sending with
            ``force=True`` performs the action.
        """
        _check_force(force)
        if action == "submit_sample":
            # Sending it here would skip the category and reason the server
            # requires (and the local checks on them), and it copies a message
            # to LimaCharlie, so point at the method that asks for both.
            raise ValueError(
                "use submit_sample(msg_uuid, category, reason) for action "
                "'submit_sample': it needs a category and a reason"
            )
        body: dict[str, Any] = {"action": action}
        for key, val in (("reason", reason), ("attempt", attempt), ("text", text)):
            if val is not None:
                body[key] = val
        if force:
            body["force"] = True
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

    def list_revisions(self, msg_uuid: str, *, limit: int | None = None) -> dict[str, Any]:
        """The verdict revision history for one message, oldest first.

        Requires ``mailsec.get``. Every entry carries its ``seq``, the
        ``mode`` and ``actor`` that decided it, the ``verdict`` it set, its
        ``decided_at`` time, and the ``rationale`` given — the audit of how a
        message's disposition moved over time, read from the bottom up.

        Args:
            msg_uuid: Message UUID.
            limit: Maximum revisions to return (1–1000 at the gateway).

        Returns:
            Revision entries and ``revisions_truncated``. There is no cursor;
            a truncated response is an incomplete history.
        """
        pairs: list[tuple[str, str]] = []
        _add_scalar(pairs, "limit", limit)
        return self._get(f"messages/{_seg(msg_uuid)}/revisions", pairs)

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
        text: str | None = None,
        reason: str | None = None,
        force: bool = False,
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
            text: ``banner_message`` only — see :meth:`act_on_message`. One
                plain-text wording applied to every member's banner. Like
                ``reason`` it is not part of the confirmation.
            reason: Free-text justification, recorded on the job's audit row AND
                on every message's, exactly as :meth:`act_on_message` records it
                for one. It is deliberately NOT part of the confirmation, so
                rewording it between previewing and executing neither invalidates
                the token nor starts a second job over the same messages.
            force: Perform the action even if the organization is in
                alert-only mode (no automation in enforce mode). The override
                is recorded in the audit trail. Sent only when ``True``. Like
                ``reason`` it is not part of the confirmation, so the preview's
                token is reused; a forced execute runs as a NEW job with its
                own ``bulk_id`` rather than adopting the unforced one.
                :meth:`bulk_action_status` reports ``force_required: true``
                when members were withheld by alert-only mode.

        Returns:
            ``{"accepted": True, "bulk_id": str, "state": str, "counts": {...},
            "member_count": int, "started": bool, "already_running": bool,
            "already_complete": bool}``. ``started: false`` means this call
            adopted a job that already existed, which is the idempotent path and
            not a failure.

        Note:
            ``reason`` requires a backend that reads it. Deployments older than
            the fix forwarded only ``action``, ``msg_uuids``, ``confirm`` and
            ``attempt`` on this route and dropped a reason in transit; against
            those, a justification sent here never reaches the audit trail.
            Current deployments forward and record it. It is an ordinary
            optional argument rather than a version probe, because a client
            cannot tell the two apart from the response — the execute answers
            200 either way.
        """
        body: dict[str, Any] = {
            "action": action,
            "msg_uuids": normalize_bulk_selection(msg_uuids),
            "confirm": confirm,
        }
        _check_force(force)
        for key, val in (("attempt", attempt), ("reason", reason), ("text", text)):
            if val is not None:
                body[key] = val
        if force:
            body["force"] = True
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

    def wait_for_bulk(
        self,
        bulk_id: str,
        timeout: int = 300,
        poll_interval: int = 3,
        *,
        on_poll: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Poll a bulk action until it stops moving, bounded by *timeout*.

        Three things stop the loop, and they are deliberately not one thing:

        - the job reached a state in :data:`BULK_TERMINAL_STATES`;
        - ``stalled`` is true, which is terminal even though the job is not
          finished, because there is no automatic resumption — the record is not
          being heartbeaten, so no amount of further polling will move it;
        - the deadline passed, which says nothing about the job.

        Args:
            bulk_id: The handle returned by :meth:`bulk_action_execute`.
            timeout: Maximum seconds to wait.
            poll_interval: Seconds between polls.
            on_poll: Called with each status document as it arrives, for a
                caller that wants to narrate progress. It is invoked for the
                terminal poll too, so a caller that only wants progress should
                filter on the state itself.

        Returns:
            dict: The LAST status document, whichever of the three stopped the
            loop. There is no timeout exception, following :meth:`Jobs.wait`:
            a document that comes back ``running`` and not ``stalled`` is one
            the deadline ended, and the distinction is the caller's to draw
            because only the caller knows what it wants to do about it.
        """
        deadline = time.monotonic() + timeout
        while True:
            status = self.bulk_action_status(bulk_id)
            if on_poll is not None:
                on_poll(status)
            if status.get("state") in BULK_TERMINAL_STATES or status.get("stalled"):
                return status
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return status
            time.sleep(min(poll_interval, remaining))

    # ------------------------------------------------------------------
    # Message groups and durable all-recipient actions
    # ------------------------------------------------------------------

    def list_groups(
        self, *, verdict: list[str] | None = None, severity: list[str] | None = None,
        disposition: list[str] | None = None, user_reported: bool | None = None,
        all_groups: bool = False, since: str | None = None, until: str | None = None,
        cursor: str | None = None, limit: int | None = None,
    ) -> dict[str, Any]:
        """List the flagged message-group queue, ordered by last seen.

        Args:
            verdict: Repeatable engine verdict filter.
            severity: Repeatable severity filter.
            disposition: Repeatable analyst disposition filter, including none.
            user_reported: True or false to constrain reports; None is unconstrained.
            all_groups: Include groups outside the flagged queue.
            since: Earliest last-seen time, RFC3339 or unix seconds.
            until: Exclusive latest last-seen time.
            cursor: Opaque cursor bound to the complete filter set.
            limit: Page size.

        Returns:
            dict: Groups, next_cursor and materialized as_of timestamps.
        """
        pairs: list[tuple[str, str]] = []
        for key, values in (("verdict", verdict), ("severity", severity), ("disposition", disposition)):
            _add_pairs(pairs, key, values)
        _add_scalar(pairs, "user_reported", user_reported)
        if not isinstance(all_groups, bool):
            raise TypeError("all_groups must be a boolean")
        if all_groups:
            _add_scalar(pairs, "all", True)
        for key, value in (("since", since), ("until", until), ("cursor", cursor), ("limit", limit)):
            _add_scalar(pairs, key, value)
        return self._get("groups", pairs)

    def get_group(self, group_id: str) -> dict[str, Any]:
        """Read one consistent aggregate of every recipient copy.

        Args:
            group_id: The deterministic message-group identity.

        Returns:
            dict: Group with exact recipient/message counts and an as_of timestamp.

        Raises:
            ValueError: If group_id is not a lowercase SHA-256 identity.
        """
        return self._get(f"groups/{_group_identity(group_id)}")

    def prepare_group_action(
        self, group_id: str, action: str, preview_id: str, *,
        force: bool = False, reason: str | None = None, text: str | None = None,
        disposition: str | None = None, note: str | None = None, clear: bool = False,
    ) -> dict[str, Any]:
        """Freeze all recipient copies and parameters in a durable preview job.

        Args:
            group_id: Message-group identity.
            action: Remediation action name, or set_disposition (requires mailsec.act and mailsec.set).
            preview_id: Caller-minted UUID; reuse it when retrying identical parameters.
            force: Explicit override of organization alert-only mode.
            reason: Audited reason, frozen before confirmation.
            text: Optional plain-text banner override, frozen before confirmation.
            disposition: One of malicious, spam, graymail, benign or simulation.
            note: Disposition note of at most 1024 UTF-8 characters.
            clear: Clear every frozen copy's disposition instead of setting a value.

        Returns:
            dict: Job initially preparing; no token until every member is snapshotted.

        Raises:
            ValueError: If an identity or the frozen disposition parameters are invalid.
            TypeError: If force/clear is not a boolean or note is not text.
        """
        _check_force(force)
        if not isinstance(clear, bool):
            raise TypeError("clear must be a boolean")
        if action == "set_disposition":
            if force or reason or text:
                raise ValueError("set_disposition does not accept provider remediation parameters")
            if clear == (disposition is not None):
                raise ValueError("provide one disposition or clear=True")
            if disposition is not None and disposition not in {"malicious", "spam", "graymail", "benign", "simulation"}:
                raise ValueError("invalid disposition")
            if note is not None:
                if not isinstance(note, str):
                    raise TypeError("note must be text")
                note.encode("utf-8")
                if len(note) > 1024:
                    raise ValueError("note must be at most 1024 characters")
        elif disposition is not None or note is not None or clear:
            raise ValueError("disposition parameters require set_disposition")
        body: dict[str, Any] = {"action": action, "preview_id": _group_job_identity(preview_id)}
        if _check_force(force):
            body["force"] = True
        if clear:
            body["clear"] = True
        for key, value in (("reason", reason), ("text", text), ("disposition", disposition), ("note", note)):
            if value is not None:
                body[key] = value
        return self._post(f"groups/{_group_identity(group_id)}/actions/preview", body)

    def get_group_action(self, job_id: str) -> dict[str, Any]:
        """Read preparation/execution progress for a durable group action.

        Args:
            job_id: Durable job UUID.

        Returns:
            dict: Job phase, frozen membership/outcome counts and token when ready.

        Raises:
            ValueError: If job_id is malformed.
        """
        return self._get(f"group-actions/{_group_job_identity(job_id)}")

    def confirm_group_action(self, job_id: str, confirmation: str) -> dict[str, Any]:
        """Execute a completed preview as its original authenticated actor.

        Args:
            job_id: Durable job UUID.
            confirmation: Token from the completely prepared preview.

        Returns:
            dict: Running job; repeated confirmation adopts the same execution.

        Raises:
            ValueError: If job_id or the token is malformed.
        """
        if not isinstance(confirmation, str) or not re.fullmatch(r"[0-9a-f]{64}", confirmation):
            raise ValueError("confirmation must be the complete preview's token")
        return self._post(f"group-actions/{_group_job_identity(job_id)}/confirm", {"confirmation": confirmation})

    def wait_for_group_action(
        self, job_id: str, *, preparing: bool = False, timeout: int = 300,
        poll_interval: int = 3,
    ) -> dict[str, Any]:
        """Poll boundedly for a ready preview or completed execution.

        Args:
            job_id: Durable job UUID.
            preparing: Stop at ready when True; otherwise wait for done or failed.
            timeout: Maximum seconds, from 1 to 3600.
            poll_interval: Seconds between polls, from 1 to 60.

        Returns:
            dict: Last status; a nonterminal phase means the deadline expired.

        Raises:
            ValueError: If polling bounds or job identity are invalid.
            RuntimeError: If the server returns an unknown or missing phase.
        """
        _group_job_identity(job_id)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError("timeout must be an integer from 1 to 3600 seconds")
        if type(poll_interval) is not int or not 1 <= poll_interval <= 60:
            raise ValueError("poll_interval must be an integer from 1 to 60 seconds")
        deadline = time.monotonic() + timeout
        terminal = {"done", "failed"} | ({"ready", "running"} if preparing else set())
        for _ in range(timeout // poll_interval + 2):
            status = self.get_group_action(job_id)
            phase = status.get("job", {}).get("phase")
            if phase not in {"preparing", "ready", "running", "done", "failed"}:
                raise RuntimeError("group action returned an unknown or missing phase")
            if phase in terminal:
                return status
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return status
            time.sleep(min(poll_interval, remaining))
        return status

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
        attempt: str | None = None,
        actor: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Sweep an action across every member of a campaign.

        Requires ``mailsec.act``.

        ``confirm`` is what turns a PREVIEW into an EXECUTION. Without it the
        call reports what it would do and changes nothing — which is the right
        default for an operation whose blast radius is "every mailbox that got
        this attack".

        Re-running a sweep is idempotent per member: the default per-member
        attempt key is the campaign itself, so a double-click — or a retry of a
        request whose response was lost — collapses onto the audit row each
        member already has rather than claiming a second move. ``attempt`` is
        the escape hatch when the second run is a DELIBERATE one.

        Args:
            campaign_id: The campaign to sweep.
            action: The typed action, as for :meth:`act_on_message`.
            confirm: Pass the member-bound token returned by the preview to
                execute. Omit to preview.
            reason: The operator's justification. Recorded on the sweep's own
                record and stamped onto every member's audit row, so an analyst
                reading one message's timeline sees why it was acted on without
                having to find the sweep. Bounded server-side at 1024
                characters and refused rather than truncated.
            attempt: An opaque idempotency handle the caller mints. Omit for the
                normal case. A NEW value composes with the campaign to make a
                new action id for every member and a new sweep record, so a
                re-run after a provider outage is recorded BESIDE what failed
                instead of over it; the same value twice collapses onto the same
                rows. Bounded server-side at 128 characters — shorter than the
                reason because it is written verbatim onto every member's row —
                and refused rather than truncated, since a clipped idempotency
                key is a different key. Validated on the preview leg as well as
                the execute, and surrounding whitespace is trimmed before the
                bound is applied.
            actor: Ignored if supplied — the gateway stamps the acting
                identity from the authenticated claims, so an audit trail's
                subject can never be chosen by its subject.
            force: Perform the action even if the organization is in
                alert-only mode (no automation in enforce mode). The override
                is recorded in the audit trail. Applies to the EXECUTE only:
                it is not part of the confirmation token, and passing it
                without a ``confirm`` (a preview) raises ``ValueError``. The
                execution reports ``force_required: true`` when members were
                withheld by alert-only mode.

        Note:
            Neither ``reason`` nor ``attempt`` is part of the confirmation
            token, which is derived from the member set alone. Adding either one
            between previewing and executing therefore does not invalidate a
            token you already hold.
        """
        if _check_force(force) and not confirm:
            # Refused rather than dropped: a caller that believes it forced a
            # preview would read the preview's counts as what a forced sweep
            # will do, and the preview endpoint does not take force at all.
            raise ValueError("force applies to the execute; pass confirm to execute the sweep")
        body: dict[str, Any] = {"action": action}
        for key, val in (("confirm", confirm), ("reason", reason),
                         ("attempt", attempt), ("actor", actor)):
            if val is not None:
                body[key] = val
        if force:
            body["force"] = True
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
    # Customer sample submission
    # ------------------------------------------------------------------
    #
    # An organization can opt in (``mailsec_policy`` record of type
    # ``sample_sharing``, ``{"enabled": true}``; off by default) to let its
    # analysts copy ONE message at a time to LimaCharlie so detection quality
    # can improve. Nothing is ever submitted automatically. The copy is the
    # message's original bytes, compressed and encrypted, kept in a
    # LimaCharlie-owned bucket in the same datacenter as the organization's
    # Email Security data, plus a metadata row; both are deleted automatically
    # 400 days after submission, or immediately on withdrawal.

    def submit_sample(
        self,
        msg_uuid: str,
        category: str,
        reason: str,
        *,
        attempt: str | None = None,
    ) -> dict[str, Any]:
        """Copy ONE message to LimaCharlie to help improve detection.

        Requires ``mailsec.act`` and an organization that has opted in
        (``mailsec_policy`` record of type ``sample_sharing``). This sends
        the message's original bytes (attachments included) and the metadata
        listed below to a LimaCharlie-owned store in the organization's own
        datacenter. It is explicit, one message per call, and never done
        automatically. Only a person can do it: the backend refuses the same
        action from a D&R rule, an automation or the AI agent.

        What is kept: the original raw message (compressed and encrypted), and
        a row with the message id, your category and reason, your identity,
        the time, the verdict, score and matched rule ids at that time, the
        sender, subject, mailbox address and size. Retention is 400 days, then
        deleted automatically. Only LimaCharlie staff working on detection
        quality can open a submission, through a tool that records every
        access; :meth:`get_submission` shows how many times and when. Withdraw
        at any time with :meth:`withdraw_sample` or
        :meth:`withdraw_submission`: the copy and its metadata are deleted.

        Args:
            msg_uuid: The message to submit.
            category: ``missed_threat`` (we called it benign or unknown and
                it is a threat), ``false_positive`` (we flagged it and it is
                legitimate) or ``other``.
            reason: Why you are submitting it, 1 to 1024 characters after
                trimming. Required, and kept with the submission.
            attempt: Caller-supplied idempotency token.

        Returns:
            The action record. ``result: ok`` and ``skipped`` carry
            ``submission_id``; ``skipped`` means this message already has an
            active submission. A refusal (not opted in, no submissions store
            in this datacenter, or the message's raw copy is no longer
            stored) is reported like any other failed action, with the reason
            in ``error``; check ``result`` as well as catching exceptions.

        Raises:
            ValueError: If ``category`` is not one of the three, or ``reason``
                is blank or longer than 1024 characters.
        """
        if category not in SAMPLE_CATEGORIES:
            raise ValueError(
                f"category must be one of {', '.join(SAMPLE_CATEGORIES)}; got {category!r}"
            )
        text = _check_sample_reason(reason, required=True)
        body: dict[str, Any] = {"action": "submit_sample", "category": category, "reason": text}
        if attempt is not None:
            body["attempt"] = attempt
        return self._post(f"messages/{_seg(msg_uuid)}/actions", body)

    def withdraw_sample(
        self,
        msg_uuid: str,
        *,
        reason: str | None = None,
        attempt: str | None = None,
    ) -> dict[str, Any]:
        """Withdraw the submission made from one message. Requires ``mailsec.act``.

        Deletes LimaCharlie's stored copy of the message and its metadata (a
        hard delete), then records the withdrawal in the audit trail. Like
        :meth:`submit_sample`, only a person can do this.

        Args:
            msg_uuid: The message whose submission to withdraw.
            reason: Optional note recorded on the audit row, at most 1024
                characters.
            attempt: Caller-supplied idempotency token.

        Returns:
            The action record; read ``result`` and ``error`` as for
            :meth:`submit_sample`.

        Raises:
            ValueError: If ``reason`` is longer than 1024 characters.
        """
        body: dict[str, Any] = {"action": "withdraw_sample"}
        text = _check_sample_reason(reason, required=False)
        if text:
            body["reason"] = text
        if attempt is not None:
            body["attempt"] = attempt
        return self._post(f"messages/{_seg(msg_uuid)}/actions", body)

    def list_submissions(
        self,
        *,
        category: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """The samples this organization has submitted to LimaCharlie.

        Requires ``mailsec.get``. Newest first.

        Args:
            category: Only this category: ``missed_threat``,
                ``false_positive`` or ``other``.
            since: Lower time bound (RFC 3339).
            until: Upper time bound (RFC 3339).
            limit: Page size, 1 to 200 (the server default is 50).
            cursor: ``next_cursor`` from the previous page, passed back
                verbatim.

        Returns:
            ``{"enabled", "available", "submissions", "next_cursor"}``.
            ``enabled`` is whether the organization has opted in;
            ``available`` is whether this datacenter has a submissions store.
            Both are always present, so an empty list can be told apart from a
            feature that is off. A non-empty ``next_cursor`` means more pages.

        Raises:
            ValueError: If ``category`` or ``limit`` is out of range.
        """
        if category is not None and category not in SAMPLE_CATEGORIES:
            raise ValueError(
                f"category must be one of {', '.join(SAMPLE_CATEGORIES)}; got {category!r}"
            )
        if limit is not None and not (
            isinstance(limit, int) and not isinstance(limit, bool)
            and 1 <= limit <= _MAX_SUBMISSION_PAGE
        ):
            raise ValueError(f"limit must be between 1 and {_MAX_SUBMISSION_PAGE}; got {limit!r}")
        pairs: list[tuple[str, str]] = []
        for key, val in (
            ("category", category),
            ("since", since),
            ("until", until),
            ("limit", limit),
            ("cursor", cursor),
        ):
            _add_scalar(pairs, key, val)
        return self._get("submissions", pairs)

    def get_submission(self, submission_id: str) -> dict[str, Any]:
        """One submission and its recorded staff review accesses.

        Requires ``mailsec.get``.

        Args:
            submission_id: The submission id (from :meth:`list_submissions`).

        Returns:
            ``{"submission": {...}, "reviews": [{"ts": ...}]}``. ``reviews``
            lists up to200 access-attempt timestamps, oldest first, never the reviewer's
            identity. Access is recorded before decryption and can include failures.
            ``reviews_truncated`` identifies a partial history; ``review_count`` and
            ``last_reviewed_at`` in the submission include all accesses. An unknown id
            is not an error: it returns ``{"submission": None, "reviews": []}``,
            so branch on ``submission`` being ``None``.
        """
        return self._get(f"submissions/{_seg(submission_id)}")

    def withdraw_submission(self, submission_id: str) -> dict[str, Any]:
        """Withdraw a submission by id. Requires ``mailsec.act``.

        Deletes LimaCharlie's stored copy and the metadata row (a hard
        delete), then records the audit.

        Args:
            submission_id: The submission id (from :meth:`list_submissions`).

        Returns:
            ``{"withdrawn": true, "submission_id": ..., "action_id": ...}``
            when a copy was deleted. Withdrawal remains available after opt-out or
            provider disconnect, and expired copies are cleaned up if metadata remains.
            An unknown or already-deleted id returns ``{"withdrawn": false,
            "submission_id": ...}`` with no ``action_id``, so a second
            withdrawal is harmless and never deletes anything twice. Check
            ``withdrawn``.
        """
        return self._delete(f"submissions/{_seg(submission_id)}")

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

    def list_provider_quarantine(
        self, *, connection: str | None = None, status: str | None = None,
        since: str | int | None = None, until: str | int | None = None,
        cursor: str | None = None, limit: int | None = None,
    ) -> dict[str, Any]:
        """List Microsoft provider delivery observations and coverage.

        Args:
            connection: Optional connection record name.
            status: quarantined, filteredAsSpam or failed (case sensitive).
            since: Inclusive provider timestamp, RFC3339 or Unix seconds.
            until: Exclusive provider timestamp, RFC3339 or Unix seconds.
            cursor: Opaque cursor; keep filters unchanged between pages.
            limit: Page size, maximum 1000.

        Returns:
            dict: provider_quarantine, next_cursor and coverage. Failed means
            delivery failed, not hosted quarantine. An empty list with
            unavailable coverage does not establish that nothing was blocked.
        """
        pairs: list[tuple[str, str]] = []
        for key, val in (("connection", connection), ("status", status),
                         ("since", since), ("until", until),
                         ("cursor", cursor), ("limit", limit)):
            _add_scalar(pairs, key, val)
        return self._get("provider-quarantine", pairs)

    def list_release_requests(
        self, *, connection: str | None = None, status: str | None = None,
        since: str | int | None = None, until: str | int | None = None,
        cursor: str | None = None, limit: int | None = None,
    ) -> dict[str, Any]:
        """List Microsoft quarantine release activity and coverage.

        Args:
            connection: Optional connection record name.
            status: requested, released or denied (lowercase).
            since: Inclusive provider timestamp, RFC3339 or Unix seconds.
            until: Exclusive provider timestamp, RFC3339 or Unix seconds.
            cursor: Opaque cursor; keep filters unchanged between pages.
            limit: Page size, maximum 1000.

        Returns:
            dict: release_requests, next_cursor and coverage. This method
            observes requests and release/denial history; it approves nothing.
        """
        pairs: list[tuple[str, str]] = []
        for key, val in (("connection", connection), ("status", status),
                         ("since", since), ("until", until),
                         ("cursor", cursor), ("limit", limit)):
            _add_scalar(pairs, key, val)
        return self._get("release-requests", pairs)

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

    def resolve_report(self, report_id: str, disposition: str, *, remediation: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resolve a report and classify its linked message independently of verdict.

        Args:
            report_id: Report to resolve.
            disposition: Malicious, spam, graymail, benign, or simulation.
            remediation: Optional scope/action request. Without confirm, previews
                the action and leaves the report open. Group scope requires a UUID
                attempt reused through preview, confirmation and polling; its
                job may return remediation_pending until completed. Only the
                reported original is classified. Pass the returned confirm
                token to execute and resolve. Remediation requires mailsec.act.

        Returns:
            dict: Updated report, or remediation_preview without a resolution.

        Raises:
            ValueError: If disposition is outside the closed vocabulary.
        """
        if disposition not in DISPOSITIONS:
            raise ValueError("invalid disposition")
        body: dict[str, Any] = {"disposition": disposition}
        if remediation is not None:
            if remediation.get("scope") == "group":
                try:
                    uuid.UUID(remediation.get("attempt", ""))
                except (ValueError, TypeError, AttributeError):
                    raise ValueError("group remediation requires a UUID attempt reused through preview, confirmation and polling") from None
            body["remediation"] = dict(remediation)
        return self._post(f"reports/{_seg(report_id)}/resolve", body)

    def wait_for_report_resolution(self, report_id: str, disposition: str, *, remediation: dict[str, Any], timeout: int = 300, poll_interval: int = 2) -> dict[str, Any]:
        """Wait for a group preview or confirmed report resolution.

        Args:
            report_id: Report identifier.
            disposition: The same disposition used for the preview.
            remediation: Group action, UUID attempt and unchanged parameters;
                include confirm to execute and resolve, omit to prepare only.
            timeout: Maximum polling window, 1 to 300 seconds.
            poll_interval: Seconds between polls, 1 to 30.

        Returns:
            dict: Preview with job and confirmation, or resolved report.
                wait_timed_out means the durable job continues; repeat with the
                same attempt and confirmation to resume. HTTP errors propagate.

        Raises:
            ValueError: If bounds or group parameters are invalid.
        """
        if remediation.get("scope") != "group" or not 1 <= timeout <= 300 or not 1 <= poll_interval <= 30:
            raise ValueError("requires group remediation and bounded timeout/poll interval")
        frozen = dict(remediation)
        deadline = time.monotonic() + timeout
        for _ in range(302):
            result = self.resolve_report(report_id, disposition, remediation=frozen)
            if result.get("report", {}).get("status") == "resolved" or result.get("already_resolved") is True:
                return result
            preview = result.get("remediation_preview", {})
            if not frozen.get("confirm") and preview.get("job", {}).get("phase") in ("ready", "running", "done") and preview.get("confirmation"):
                return result
            job = (result.get("remediation") or preview).get("job", {})
            if job.get("phase") not in ("preparing", "running"):
                raise ValueError("incomplete group remediation outcome; report remains open")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {**result, "wait_timed_out": True}
            time.sleep(min(poll_interval, remaining))
        return {**result, "wait_timed_out": True}

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
            rule_id: The dr-mail record key. No prefix is reserved. If omitted,
                validation uses the placeholder ``unnamed``.
        """
        body: dict[str, Any] = {"rule": rule}
        if rule_id is not None:
            body["rule_id"] = rule_id
        return self._post("rules/validate", body)

    def preview_banner(
        self,
        banner: dict[str, Any],
        *,
        verdict: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        """Render a candidate warning banner without saving it.

        Runs the same validation the ``mailsec_policy`` hive applies on save
        and the same renderer the collector uses, so the ``html`` returned is
        what recipients get. An invalid banner is a successful response
        carrying ``valid: false`` and the reason. Requires ``mailsec.get``.

        Args:
            banner: The fields of a ``banners`` policy record (``title``,
                ``color``, ``text``, ``logo_url``, ``logo_alt``, ``variants``,
                ``enabled``); omit ``policy_type``.
            verdict: Preview the per-verdict variant for this verdict
                (``malicious``, ``suspicious``, ``graymail``, ``benign``,
                ``unknown``).
            text: Preview a ``banner_message`` action's own wording.
        """
        body: dict[str, Any] = {"banner": banner}
        if verdict is not None:
            body["verdict"] = verdict
        if text is not None:
            body["text"] = text
        return self._post("banner/preview", body)

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

    def get_onboarding(
        self, *, provider: str | None = None, project_id: str | None = None,
        sa_email: str | None = None, topic: str | None = None,
        subscription: str | None = None,
    ) -> dict[str, Any]:
        """Get the provider setup guide with optional Workspace substitutions.

        The backend supplies current scopes and setup steps. Workspace
        commands contain placeholders until the customer supplies their own
        project and service account; this read creates no provider resources.

        Args:
            provider: ``gworkspace`` (default) or ``m365``.
            project_id: Customer's Google Cloud project ID.
            sa_email: Customer's service account email address.
            topic: Workspace Pub/Sub topic name override.
            subscription: Workspace Pub/Sub subscription name override.

        Returns:
            Current provider scopes, setup steps and Workspace setup script.
        """
        pairs: list[tuple[str, str]] = []
        _add_scalar(pairs, "provider", provider)
        _add_scalar(pairs, "project_id", project_id)
        _add_scalar(pairs, "sa_email", sa_email)
        _add_scalar(pairs, "topic", topic)
        _add_scalar(pairs, "subscription", subscription)
        return self._get("onboarding", pairs)

    # ------------------------------------------------------------------
    # Tenant purge
    # ------------------------------------------------------------------

    def prepare_tenant_purge(self) -> dict[str, Any]:
        """Mint the single-use confirmation token a tenant purge requires.

        Changes nothing. This is the read half of the same two-step shape org
        deletion uses: it returns the warning describing what a purge would
        destroy, plus a token that :meth:`purge_tenant` will not act without.
        Showing a human that warning before anything is destroyed is the whole
        reason the destructive verb cannot be reached in one call.

        Requires Owner-level authority — ``mailsec.act`` AND ``billing.ctrl``
        AND ``user.ctrl``, the same trio org deletion asks for, because there
        is no separate "owner" permission to ask for instead.

        Returns:
            The mint, with ``confirmation`` (the token), ``expires_in_seconds``
            (300) and ``warning`` (the human-readable statement of what is
            about to be destroyed). The token is SINGLE-USE and expires in five
            minutes: a purge that has to be re-run needs a fresh one, so mint
            immediately before executing rather than early in a script.
        """
        return self._get("tenant")

    def purge_tenant(self, confirmation: str, reason: str | None = None) -> dict[str, Any]:
        """Permanently delete everything Email Security holds for this org.

        IRREVERSIBLE, and wider than it may look: the message index and the
        long-term evidence lane, campaigns, sender profiles, the remediation
        audit trail, user reports, stored raw messages and their parsed copies,
        link-detonation results, and the org's Email Security connection and
        policy configuration. It also stops the mail connections at the
        provider, so Microsoft or Google stops sending notifications about mail
        this org no longer has anywhere to put.

        RE-RUNNABLE, and that is the intended way to finish a partial one.
        ``complete`` is ``False`` when some portion did not land — a provider
        that was unreachable, an object store that refused a delete — and the
        same call repeated picks up what remains. Nothing is double-deleted by
        running it again. A fresh ``confirmation`` is needed for each attempt
        because the token is single-use.

        Args:
            confirmation: The token from :meth:`prepare_tenant_purge`.
            reason: Optional free text, at most 1024 characters, recorded in
                the org's audit log next to the caller's identity.

        Returns:
            The outcome, whose most important field is ``complete``. The rest
            are counts of what was removed and — deliberately alongside them —
            what was not: ``objects_deleted``, ``mdms_deleted``,
            ``detonation_results_deleted``, ``detonation_results_skipped``,
            ``objects_failed``, ``tables_purged``, ``subscriptions_stopped``,
            ``subscriptions_failed``, ``mailboxes_walked``,
            ``provider_records_deleted``, ``policy_records_deleted``,
            ``connections_unreachable``, ``rows_remained``. A caller that reads
            only the successes will believe a partial purge finished.

        Raises:
            ValueError: If ``confirmation`` is empty, or ``reason`` exceeds
                1024 characters. Both are checked here rather than left to the
                server because a rejected request still costs the token, and
                re-minting is a second round trip to learn something the client
                already knew.
        """
        token = (confirmation or "").strip()
        if not token:
            raise ValueError(
                "purge_tenant needs the confirmation token from "
                "prepare_tenant_purge(); there is no unconfirmed form of this call"
            )
        pairs: list[tuple[str, str]] = [("confirmation", token)]
        if reason is not None:
            if len(reason) > _MAX_PURGE_REASON_LEN:
                raise ValueError(
                    f"reason is {len(reason)} characters; the audit log records at "
                    f"most {_MAX_PURGE_REASON_LEN}"
                )
            pairs.append(("reason", reason))
        return self._delete("tenant", pairs)


def _disposition_body(disposition: str | None, note: str, clear: bool) -> dict[str, Any]:
    if (clear and disposition is not None) or (not clear and disposition not in DISPOSITIONS):
        raise ValueError("provide a valid disposition or clear=True")
    if len(note) > 1024:
        raise ValueError("note must contain at most 1024 characters")
    body: dict[str, Any] = {"note": note}
    if clear:
        body["clear"] = True
    else:
        body["disposition"] = disposition
    return body
