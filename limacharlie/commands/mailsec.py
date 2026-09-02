"""Email Security (mailsec) commands for LimaCharlie CLI v2.

Commands for the ``/mailsec`` API surface: the coverage screen, the message
index and its drawer, the justified raw-EML download, bulk remediation across a
selection you name, campaigns and campaign-wide sweeps, sender profiles, the
action audit trail, the abuse-mailbox report queue, standalone EML analysis,
retro-hunts, custom-rule validation and backtest, the connection preflight, and
the served onboarding guide.

Four permissions rather than the usual get/set pair, because mailsec asks to be
trusted with four different things:

  mailsec.get      read the product's own view (queue, drawer, campaigns,
                   senders, audit trail)
  mailsec.set      change detection behaviour and triage state
  mailsec.act      remediate live mail at the provider
  mailsec.get.eml  take the original bytes of somebody's mail out of the
                   building; requires a logged justification

Every command requires the org to be subscribed to the ``ext-email-security``
extension:

  limacharlie extension subscribe --name ext-email-security

Provider connections and policy are hive records — manage them with the hive
commands (``limacharlie hive list --hive-name mailsec_provider``, same for
``mailsec_policy`` and ``dr-mail``). The connection operations here are the
post-save preflight (``mailsec connection test``) and the served setup guide
(``mailsec onboarding``).
"""

from __future__ import annotations

import json
import re
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.mailsec import BULK_ACTIONS, Mailsec, normalize_bulk_selection
from ..output import format_output, detect_output_format
from ..discovery import register_explain
from ._input_helpers import load_file, load_stdin
from ._output_helpers import note


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_COVERAGE = """\
Coverage and volume for the org: how many mailboxes are protected,
which are not and why, and what was analysed over the window.

The mailboxes that are NOT protected are the point. A mailbox we
cannot subscribe is reported as visibly broken rather than omitted,
so the number is a coverage statement an admin can act on instead of
a count of whatever happened to work.

Examples:
  limacharlie mailsec coverage
  limacharlie mailsec coverage --window-days 30
"""

_EXPLAIN_MESSAGE_LIST = """\
The message index — the triage queue. Repeatable filters OR within a
key and AND across keys.

--user-reported is worth knowing about: a human taking the trouble to
report a message is the strongest signal this product gets, and it
outranks whatever the scorer decided.

Examples:
  limacharlie mailsec message list --verdict suspicious --verdict malicious
  limacharlie mailsec message list --mailbox cfo@corp.example --since 2026-08-01
  limacharlie mailsec message list --user-reported
  limacharlie mailsec message list --link-domain evil.example
"""

_EXPLAIN_MESSAGE_GET = """\
One message: the index row plus the re-parsed MDM (the drawer).

The MDM is re-parsed from the stored raw copy rather than read from
the index, and the response says which path produced it. Enrichments
are deliberately absent rather than recomputed — they were resolved
against sender profiles as they existed at ingest, and synthesising
today's values would show you a reputation the verdict was never
based on.

An unknown id returns a null message, not an error: the index has a
35-day TTL, so a miss is normal.

Examples:
  limacharlie mailsec message get 0057db2b-3a06-5aab-b3be-c1e6c15dcf10
"""

_EXPLAIN_MESSAGE_EML = """\
Download the original RFC822 bytes of a message.

This is a different privilege from opening the drawer (mailsec.get.eml,
not mailsec.get) because it takes a person's actual mail out of the
building. --justification is REQUIRED and is written to the access
audit with your identity: there is no way to fetch these bytes without
leaving a record of why.

Examples:
  limacharlie mailsec message eml 0057db2b-... --justification "INC-4471 credential harvest"
"""

_EXPLAIN_MESSAGE_SIMILAR = """\
Messages clustered with this one — "who else got this", answered from
a single message.

Examples:
  limacharlie mailsec message similar 0057db2b-...
"""

_EXPLAIN_MESSAGE_ACTION = """\
Remediate one message at the provider. Requires mailsec.act.

Executed by the collector holding the org's lease — the single choke
point where alert_only/enforce is applied and the audit row written.
Idempotent per (message, action).

Watch for result=alert_only: it means the action was DECIDED and
deliberately not performed because the org is not in enforce mode.
That is a success reported honestly, not a failure.

Examples:
  limacharlie mailsec message action 0057db2b-... --action quarantine_message --reason "confirmed phish"
  limacharlie mailsec message action 0057db2b-... --action restore_message
"""

_EXPLAIN_MESSAGE_REVISE = """\
Revise a message's verdict as an analyst. Requires mailsec.act.

This records a human triage decision over the scorer's — it is a
disposition, not a remediation — and appends to the message's verdict
history rather than overwriting it. --rationale is required and audited:
at least one, at most ten, each <= 280 characters.

mode is fixed to 'analyst' here because the operator of this CLI is a
person. An autonomous agent revises with its OWN key and mode 'ai'
through the API, not this command, so the audit can always say whether a
person or a model decided.

applied:false is an honest outcome, not an error: it means the message
was already at this verdict and nothing changed.

Examples:
  limacharlie mailsec message revise 0057db2b-... --verdict malicious --rationale "confirmed credential harvest"
  limacharlie mailsec message revise 0057db2b-... --verdict benign --rationale "internal test send" --rationale "sender verified"
"""

_EXPLAIN_MESSAGE_REVISIONS = """\
The verdict revision history for one message, oldest first.

Each entry is who decided (mode/actor), the verdict they set, when, and
the rationale they gave — the audit of how a message's disposition moved
over time.

Examples:
  limacharlie mailsec message revisions 0057db2b-...
"""

_EXPLAIN_MESSAGE_BULK_ACTION = """\
Remediate a set of messages you name, in bulk. Requires mailsec.act.

This is what turns a search result into provider-side action: pipe ids
out of `mailsec message list`, or paste a selection into a file, and act
on all of them at once. Up to 500 per call — a larger selection is
REFUSED, not truncated, because acting on the first 500 of 900 leaves
the rest in inboxes nobody will look at. Split it yourself.

TWO STEPS, like `campaign action` and `hunt remediate`:

  omit --confirm         preview only; nothing is changed
  --confirm <token>      execute the previewed selection

The preview reads the index and reports, per message, whether it still
exists, where it is now, and whether it is already where the action would
put it — plus the distinct-mailbox count, which is the blast radius you
are actually approving. It prints on stdout, `confirm` token included, so
a script reads step one's answer and passes it to step two.

The token is DERIVED FROM (action, attempt, the normalized member list),
not issued as a nonce, so it can only execute what you previewed. The
execute must therefore repeat the IDENTICAL --action, --msg-uuids and
--attempt the preview was minted with; change any of the three and the
server refuses the token as stale rather than acting on a set nobody read.

Expired ids and already-done messages are REPORTED, not errors and not
dropped. They stay in the confirmed set, and the provider re-checks each
one and answers `skipped` — the index only records where remediation last
put a message, and its owner may have moved it since.

Ids must be message UUIDs. A selection that carries anything else — the
header row and second column of a pasted CSV are the usual way this
happens — is refused by name, because a phantom id comes back from the
preview as "NOT IN INDEX", identical to a legitimately expired one, and
the counts you would be consenting over would be wrong.

Execution is ASYNCHRONOUS: 500 provider writes paced to respect Microsoft
365 / Google throttling cannot fit in one request. You get a bulk_id back
immediately (announced on stderr before the first poll, so a poll that
fails still leaves you the handle); --wait (the default) polls until the
job settles. Partial failure is a normal, honestly-reported outcome,
never a rollback.

THE EXIT CODE CARRIES THE OUTCOME, so `&&` means what it looks like:

  0    complete, with at least one message acted on (or --no-wait, or a
       preview that produced a token)
  !=0  not accepted; complete but every attempt failed; interrupted;
       stalled; still running at the timeout; or a poll that errored

A stalled job is the one worth knowing: the worker that accepted it is
gone. Re-send the same execute request with the same confirmation token
to finish it — every message already acted on collapses onto its existing
action row rather than being acted on twice.

--quiet silences both streams, as everywhere in this CLI. With it, the
exit code above and `mailsec message bulk-status <bulk_id>` are how you
read the result.

There is no --reason: the execute route does not carry one, and a
justification that never reaches the audit trail would be worse than an
absent one. Use `mailsec message action --reason` per message when the
reason matters.

Examples:
  limacharlie mailsec message bulk-action --action trash_message --msg-uuids 0057db2b-3a06-5aab-b3be-c1e6c15dcf10
  limacharlie mailsec message bulk-action --action quarantine_message --input-file uuids.txt
  limacharlie mailsec message list --verdict malicious --output json \\
    | jq -r '.messages[].msg_uuid' \\
    | limacharlie mailsec message bulk-action --action quarantine_message --input-file -
  limacharlie mailsec message bulk-action --action quarantine_message --msg-uuids 0057db2b-... --confirm 3f31ed...
"""

_EXPLAIN_MESSAGE_BULK_STATUS = """\
A bulk action's progress and per-message outcomes.

state is 'running', 'complete' or 'interrupted', and it answers a
different question from the outcome: a job that finished with six
failures is complete, because what a poller asks is whether anything is
still moving.

stalled:true means the worker that accepted the job is gone — the record
has not been heartbeaten within its window. The repair is to re-send the
same execute request with the same confirmation token to finish it: every
message already acted on collapses onto its existing action row rather
than being acted on twice.

Each item carries the action_id of its authoritative audit row, which
`mailsec action get` expands. items is a projection of the job record and
can lag by up to one heartbeat; it says so (items_source) rather than
presenting itself as the audit trail.

Examples:
  limacharlie mailsec message bulk-status 8f1c2d3e4a5b6c7d8e9f0a1b2c3d4e5f
"""

_EXPLAIN_CAMPAIGN_LIST = """\
Campaigns: one attack triaged once, rather than once per mailbox.

Examples:
  limacharlie mailsec campaign list --min-members 3
  limacharlie mailsec campaign list --verdict malicious
"""

_EXPLAIN_CAMPAIGN_GET = """\
One campaign with its aggregates and the cluster keys that grouped it.

Examples:
  limacharlie mailsec campaign get ec7e273b-ea9d-51e1-bdd8-9c18829d2071
"""

_EXPLAIN_CAMPAIGN_ACTION = """\
Sweep an action across every member of a campaign. Requires mailsec.act.

PREVIEWS BY DEFAULT. Copy the preview's member-bound `confirm` token into
--confirm to execute exactly the reviewed member set. A campaign id is not
a confirmation token and is refused by the server.

Examples:
  limacharlie mailsec campaign action ec7e273b-... --action quarantine_message
  limacharlie mailsec campaign action ec7e273b-... --action quarantine_message --confirm 3c514e...
"""

_EXPLAIN_SENDER_GET = """\
A sender's history with this org: prevalence, first seen, and how much
of their mail has been flagged.

The key is an address or a domain, optionally prefixed to disambiguate.

Examples:
  limacharlie mailsec sender get cfo@corp.example
  limacharlie mailsec sender get domain:corp.example
"""

_EXPLAIN_ACTION_GET = """\
One record from the action audit trail: what was decided, by whom, why,
and what the provider actually did.

Examples:
  limacharlie mailsec action get <action_id>
"""

_EXPLAIN_ANALYZE = """\
Parse and score an EML without ingesting it. Nothing is persisted and
no mailbox is touched.

Examples:
  limacharlie mailsec analyze --file suspect.eml
  limacharlie mailsec analyze --file suspect.eml --org-domain corp.example
"""

_EXPLAIN_REPORT_LIST = """\
The abuse-mailbox report queue: what the org's own people reported.

--oldest-first is what makes this an SLA surface. "The oldest thing
nobody has looked at" is the question a queue exists to answer, and it
is not answerable from a newest-first page.

Each report carries original_found. A report whose original was never
indexed is a real state — the message predates the connection, or
landed in a mailbox outside scope — and it is shown as a gap rather
than as a blank field that reads like a bug.

Examples:
  limacharlie mailsec report list --status open --oldest-first
  limacharlie mailsec report list --status resolved
"""

_EXPLAIN_REPORT_GET = """\
One report: who reported it, the message they reported, and the
original it refers to once located across the tenant's mailboxes.

Examples:
  limacharlie mailsec report get dfed9d76ce5ee1096852ea563f5cce23
"""

_EXPLAIN_REPORT_RESOLVE = """\
Close a report with a disposition. Requires mailsec.set.

'unknown' is deliberately not resolvable by a human: as the outcome of
someone closing a report it means "I looked and decided nothing", which
is indistinguishable in the SLA numbers from never having looked.

Resolving twice succeeds and reports already_resolved — two analysts
clicking at once is ordinary, and the second must not get an error for
an outcome that already holds.

Examples:
  limacharlie mailsec report resolve <report_id> --disposition true_positive
"""

_EXPLAIN_REPORT_REOPEN = """\
Reopen a resolved report. Requires mailsec.set.

The inverse of resolve: a report closed too early, or contradicted by
new evidence, returns to the queue rather than staying settled on a
disposition that no longer holds.

Reopening an already-open report succeeds and says so — the queue's
state is the point, not who raced to change it.

Examples:
  limacharlie mailsec report reopen <report_id>
"""

_EXPLAIN_HUNT_CREATE = """\
Start a retro-hunt over message history.

Examples:
  limacharlie mailsec hunt create --detect-file detect.json --since 2026-07-01
  limacharlie mailsec hunt create --lcql "..." --dry-run
"""

_EXPLAIN_HUNT_GET = """\
A hunt's status and results.

Examples:
  limacharlie mailsec hunt get <hunt_id>
"""

_EXPLAIN_HUNT_REMEDIATE = """\
Bulk-remediate a hunt's results. Requires mailsec.act.

Previews by default; --confirm executes, exactly like a campaign sweep.

Examples:
  limacharlie mailsec hunt remediate <hunt_id> --action quarantine_message
  limacharlie mailsec hunt remediate <hunt_id> --action quarantine_message --confirm <hunt_id>
"""

_EXPLAIN_RULE_VALIDATE = """\
Check a candidate detection rule without saving it.

Runs the SAME validation the dr-mail hive applies on save, so a rule
this accepts is a rule that will save. An invalid rule comes back as a
successful response with valid=false and the reason — that is the
answer to the question, not a failure to answer it.

Tenant rule ids must start with 'custom-'.

Examples:
  limacharlie mailsec rule validate --file rule.json
  limacharlie mailsec rule validate --file rule.json --rule-id custom-lookalike
"""

_EXPLAIN_RULE_BACKTEST = """\
Replay a candidate rule over recent mail and report what it would have
matched, so its precision is known before it is enabled.

Bounded to the window this product retains rather than the full-history
retro-hunt; every response says so in coverage_note and counts what it
could NOT examine (skipped_no_raw, skipped_unparse, truncated). A
precision figure whose denominator silently shrank is a number that
looks like a measurement and is not one.

precision is null - not 0 - when nothing it matched has an analyst
disposition yet. Zero would read as "everything it matched was wrong"
and would have you discard a good rule.

Examples:
  limacharlie mailsec rule backtest --file rule.json
  limacharlie mailsec rule backtest --file rule.json --since 2026-08-01
"""

_EXPLAIN_CONNECTION_TEST = """\
Exercise a saved provider connection end to end.

Takes the RECORD NAME of a mailsec_provider hive record, never a
credential: the credential stays in the secret hive and is resolved
server-side. Reports what the connection can actually do, including the
per-connection capabilities that depend on which scopes the customer's
admin granted.

Examples:
  limacharlie mailsec connection test gws-exp
  limacharlie mailsec connection test gws-exp --include-watch
"""

_EXPLAIN_ONBOARDING = """\
The setup guide for connecting a mail provider, with this org's own
values already substituted in.

Served by the backend rather than written into the docs so the
identifiers you must paste - the service account, the topic, the
subscription - are the real ones for this deployment rather than
placeholders you have to translate.

Examples:
  limacharlie mailsec onboarding --provider gworkspace
  limacharlie mailsec onboarding --provider m365
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_mailsec(ctx: click.Context) -> Mailsec:
    client = Client(
        oid=ctx.obj.oid,
        environment=ctx.obj.environment,
        print_debug_fn=ctx.obj.debug_fn,
        debug_full_response=ctx.obj.debug_full,
        debug_curl=ctx.obj.debug_curl,
        debug_verbose=ctx.obj.debug_verbose,
    )
    org = Organization(client)
    return Mailsec(org)


def _load_json_file(path: str, param_hint: str) -> Any:
    """Read a JSON document from a file, with a usage error rather than a
    traceback when it is not JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise click.BadParameter(f"cannot read {path}: {e}", param_hint=param_hint)
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"{path} is not valid JSON: {e}", param_hint=param_hint)


def _split_ids(text: str) -> list[str]:
    """Split one --msg-uuids value on commas, trimming each item.

    Comma-only, matching every other repeatable-and-comma-separated option in
    this CLI. It TRIMS around items rather than splitting ON whitespace, so a
    shell-quoted `"a, b"` is two ids and a value that somehow contains a space
    stays one token — which is what lets the shape check below name it instead
    of silently turning one bad paste into several plausible-looking members.
    """
    return [part.strip() for part in text.split(",") if part.strip()]


def _ids_from_document(value: Any, hint: str) -> list[str]:
    """Pull message ids out of a parsed --input-file / stdin document.

    The file goes through the shared YAML-or-JSON loader, so a caller can hand
    us a JSON array, a YAML list, or the ordinary one-id-per-line file. That
    last one parses as a single folded scalar — YAML turns its line breaks into
    spaces — so splitting the scalar on whitespace here is restoring the file's
    own line separators, not the flag-splitting rule above.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [part for line in value.split() for part in _split_ids(line)]
    if isinstance(value, (list, tuple)):
        ids: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise click.BadParameter(
                    f"expected message ids; found a {type(item).__name__}", param_hint=hint,
                )
            ids.extend(part for line in item.split() for part in _split_ids(line))
        return ids
    raise click.BadParameter(
        f"expected a list of message ids or one id per line; found a {type(value).__name__}",
        param_hint=hint,
    )


# A msg_uuid is a UUID the backend derives; nothing else is one.
_MSG_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _reject_non_message_ids(ids: list[str]) -> None:
    """Refuse a selection carrying anything that is not a message id.

    Shape-checking input is usually the server's job, but not here, because the
    server's answer is INDISTINGUISHABLE from a legitimate one: a phantom member
    comes back from the preview as "NOT IN INDEX", exactly like an id that
    expired past the 35-day retention. The member_count and mailbox_count a human
    is consenting over would silently be wrong.

    The way this happens in practice is a pasted CSV export: the header row and
    the second column become members. So the first offending token is named, in
    the order it was given, rather than reported as a count.
    """
    for value in ids:
        if not _MSG_UUID_RE.match(value):
            raise click.UsageError(
                f"'{value}' does not look like a message id: expected a UUID such as "
                "0057db2b-3a06-5aab-b3be-c1e6c15dcf10. A selection pasted out of a CSV "
                "usually needs its header row and its other columns removed."
            )


def _bulk_selection(msg_uuids: tuple[str, ...], input_file: str | None) -> list[str]:
    """Build the ONE normalized selection both bulk calls will use.

    Normalized once and reused, never rebuilt between the preview and the execute:
    the confirmation token is derived from the member list, so a second derivation
    is a second chance to disagree with the set a human just approved.

    Three sources, in the CLI's usual order of explicitness: the flag, a named
    file (``-`` being stdin), and — following the hive commands' idiom — a pipe,
    when nothing was named and stdin is not a terminal.
    """
    ids: list[str] = []
    for chunk in msg_uuids:
        ids.extend(_split_ids(chunk))
    if input_file == "-":
        ids.extend(_ids_from_document(load_stdin(), "stdin"))
    elif input_file:
        ids.extend(_ids_from_document(load_file(input_file, "--input-file"), "--input-file"))
    elif not ids:
        ids.extend(_ids_from_document(load_stdin(), "stdin"))
    if not ids:
        # An empty selection is a usage mistake, not a backend one, and it is
        # worth saying so before a round trip that would only agree.
        raise click.UsageError(
            "a bulk action needs at least one msg_uuid: pass --msg-uuids, --input-file, "
            "or pipe ids on stdin"
        )
    _reject_non_message_ids(ids)
    try:
        return normalize_bulk_selection(ids)
    except ValueError as e:
        raise click.UsageError(f"{e}: pass --msg-uuids and/or --input-file")


def _echo_bulk_preview(ctx: click.Context, preview: dict) -> None:
    """Render the preview for a human to consent from, on stderr.

    Every member is listed rather than a head of them: the point of this screen
    is the blast radius, and a truncated one under-reports exactly the thing the
    operator is being asked to approve.
    """
    summary = preview.get("summary") or {}
    note(ctx, "")
    note(ctx, f"action:        {preview.get('action')}")
    if preview.get("has_target_state"):
        note(ctx, f"target state:  {preview.get('target_state')}")
    note(ctx, f"selected:      {preview.get('member_count')} of at most {preview.get('cap')}")
    note(ctx, f"mailboxes:     {summary.get('mailbox_count')}")
    by_provider = summary.get("by_provider") or {}
    if by_provider:
        note(ctx, "providers:     " + ", ".join(f"{k}={v}" for k, v in sorted(by_provider.items())))
    note(
        ctx,
        f"actionable:    {summary.get('actionable')}   "
        f"(already in target state: {summary.get('already_in_target_state')}, "
        f"no longer indexed: {summary.get('missing')})",
    )
    note(ctx, "")
    for m in preview.get("messages") or []:
        if not m.get("exists"):
            note(ctx, f"  {m.get('msg_uuid')}  NOT IN INDEX (expired past retention, or never ingested)")
            continue
        flag = "  already in target state" if m.get("already_in_target_state") else ""
        note(
            ctx,
            f"  {m.get('msg_uuid')}  state={m.get('state')} "
            f"mailbox={m.get('mailbox')} provider={m.get('provider')}{flag}",
        )
    note(ctx, "")
    if preview.get("confirm"):
        note(ctx, f"confirm:       {preview.get('confirm')}")
        note(ctx, "")


def _output_preview(ctx: click.Context, preview: dict) -> None:
    """Emit the preview document without the table renderer's lossy summarising.

    Now that the preview IS the default output of this verb, the format matters.
    The table renderer flattens a record to one row per key and renders any
    nested value as a placeholder: measured on this document, `messages` becomes
    "[2 items]" and `summary` becomes "{7 keys}". Those two ARE the preview — the
    per-message placement and the mailbox count are the blast radius the operator
    is being asked to approve — so a table renders away the entire point.

    (The `confirm` token itself survives: the gateway's token is 32 hex
    characters and the renderer's cell width is never below 40. It is printed on
    stderr as well, by :func:`_echo_bulk_preview`, so a copy-paste never depends
    on that arithmetic staying true.)

    So the human rendering of a preview is the stderr report, and the document on
    stdout falls back to JSON when the format would have been a table. Every
    other format round-trips nested values whole and is left alone.
    """
    fmt = ctx.obj.output_format or detect_output_format()
    if fmt == "table":
        fmt = "json"
    if not ctx.obj.quiet:
        click.echo(format_output(preview, fmt))


def _bulk_state_line(status: dict) -> str:
    counts = status.get("counts") or {}
    parts = ", ".join(
        f"{k}={counts[k]}" for k in ("ok", "skipped", "failed", "alert_only", "not_found", "pending")
        if k in counts
    )
    return f"state={status.get('state')} {parts}".rstrip()


def _wait_for_bulk(ctx: click.Context, ms: Mailsec, bulk_id: str, timeout: int,
                   poll_interval: int) -> dict:
    """Poll a bulk job until it settles, narrating each poll.

    The loop itself lives in the SDK (:meth:`Mailsec.wait_for_bulk`), where a
    caller that is not this CLI can have it too. This is the narration half:
    progress lines while the job is moving, and nothing at the end, because the
    single terminal line is :func:`_bulk_outcome`'s to write next to the exit
    code it chooses.
    """
    def _on_poll(status: dict) -> None:
        if status.get("state") == "running" and not status.get("stalled"):
            note(ctx, f"bulk {bulk_id} {_bulk_state_line(status)}")

    return ms.wait_for_bulk(bulk_id, timeout=timeout, poll_interval=poll_interval,
                            on_poll=_on_poll)


def _bulk_outcome(ctx: click.Context, bulk_id: str, status: dict, timeout: int) -> int:
    """Say how the job ended, once, and return the exit code that means it.

    Exactly one terminal line per exit, so a watcher never ends in silence, and
    the code is the machine-readable half of the same sentence: a runbook chained
    with `&&` must stop when nothing was remediated, and must not stop merely
    because some members were already where the action would have put them.
    """
    line = _bulk_state_line(status)
    counts = status.get("counts") or {}
    if status.get("stalled"):
        note(
            ctx,
            f"bulk {bulk_id} is STALLED: {line} — no worker has touched it within its "
            f"heartbeat window. Re-send the same execute request with the same confirmation "
            f"token to finish it; nothing is acted on twice.",
        )
        return 1
    if status.get("state") == "interrupted":
        note(
            ctx,
            f"bulk {bulk_id} settled: {line} — INTERRUPTED: the job was finalized before "
            f"every member was acted on. The outcomes above are real; inspect them with "
            f"`limacharlie mailsec message bulk-status {bulk_id}`.",
        )
        return 1
    if status.get("state") == "complete":
        # Per-item failures inside an otherwise successful batch are the caller's
        # data, not an error. Zero successes and at least one failure is not:
        # nothing was remediated, and a chained command must not run as if it was.
        if not counts.get("ok") and counts.get("failed"):
            note(
                ctx,
                f"bulk {bulk_id} settled: {line} — NOTHING WAS REMEDIATED: every attempted "
                f"member failed. `limacharlie mailsec message bulk-status {bulk_id}` has the "
                f"per-message reason.",
            )
            return 1
        note(ctx, f"bulk {bulk_id} settled: {line}")
        return 0
    note(
        ctx,
        f"bulk {bulk_id} still running after {timeout}s: {line} — the job is unaffected; "
        f"keep polling with `limacharlie mailsec message bulk-status {bulk_id}`",
    )
    return 1


def _tri_state(flag: bool, no_flag: bool, name: str) -> bool | None:
    """Resolve a --x / --no-x pair into a tri-state.

    Neither flag means UNCONSTRAINED, which is not the same as False. The API
    is tri-state throughout and collapsing the two here would silently narrow
    every unfiltered read.
    """
    if flag and no_flag:
        raise click.BadParameter(f"--{name} and --no-{name} are mutually exclusive")
    if flag:
        return True
    if no_flag:
        return False
    return None


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@click.group(name="mailsec")
def group() -> None:
    """Email Security: mail ingest, verdicts, campaigns, remediation.

    \b
    Requires the ext-email-security extension:
      limacharlie extension subscribe --name ext-email-security

    \b
      coverage            Mailbox coverage and analysed volume
      message ...         The triage queue, drawer, raw EML, similar, actions,
                          revise, and bulk remediation of a selection
      campaign ...        Campaigns and campaign-wide sweeps
      sender get          A sender's history with this org
      action get          One record from the action audit trail
      analyze             Parse and score an EML without ingesting it
      report ...          Abuse-mailbox report queue (list, get, resolve, reopen)
      hunt ...            Retro-hunts (create, get, remediate)
      rule ...            Custom rule validation and backtest
      connection test     Provider connection preflight
      onboarding          Provider setup guide, with your values filled in
    """


@group.group("message")
def message_group() -> None:
    """The message index, drawer, raw EML, similar mail, actions, verdict revision,
    and bulk remediation across a selection you name."""


@group.group("campaign")
def campaign_group() -> None:
    """Campaigns and campaign-wide sweeps."""


@group.group("sender")
def sender_group() -> None:
    """Sender profiles."""


@group.group("action")
def action_group() -> None:
    """The action audit trail."""


@group.group("report")
def report_group() -> None:
    """The abuse-mailbox report queue (list, get, resolve, reopen)."""


@group.group("hunt")
def hunt_group() -> None:
    """Retro-hunts over message history."""


@group.group("rule")
def rule_group() -> None:
    """Custom detection rules: validate and backtest."""


@group.group("connection")
def connection_group() -> None:
    """Provider connections."""


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

@group.command("coverage")
@click.option("--window-days", default=None, type=int, help="Days of volume to summarise.")
@pass_context
def coverage(ctx, window_days) -> None:
    """Mailbox coverage and analysed volume.

    \b
    Example:
      limacharlie mailsec coverage --window-days 30
    """
    _output(ctx, _get_mailsec(ctx).get_coverage(window_days=window_days))


@group.command("analyze")
@click.option("--file", "eml_file", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Path to the .eml to analyse.")
@click.option("--org-domain", "org_domains", multiple=True,
              help="One of your org's domains (repeatable); makes direction and impersonation computable.")
@click.option("--direction", default=None, help="Override the computed direction.")
@pass_context
def analyze(ctx, eml_file, org_domains, direction) -> None:
    """Parse and score an EML without ingesting it.

    \b
    Example:
      limacharlie mailsec analyze --file suspect.eml --org-domain corp.example
    """
    import base64

    with open(eml_file, "rb") as f:
        raw = f.read()
    # Sent base64 rather than as text: an EML is bytes, and a raw 8-bit body or
    # a stray CR would not survive a JSON string round trip intact.
    ms = _get_mailsec(ctx)
    _output(ctx, ms.analyze(
        eml_b64=base64.b64encode(raw).decode("ascii"),
        org_domains=list(org_domains) or None,
        direction=direction,
    ))


@group.command("onboarding")
@click.option("--provider", default=None, type=click.Choice(["m365", "gworkspace"]),
              help="Which provider's guide to fetch.")
@pass_context
def onboarding(ctx, provider) -> None:
    """Provider setup guide, with this org's own values filled in.

    \b
    Example:
      limacharlie mailsec onboarding --provider gworkspace
    """
    _output(ctx, _get_mailsec(ctx).get_onboarding(provider=provider))


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@message_group.command("list")
@click.option("--verdict", multiple=True, help="malicious|suspicious|graymail|benign|unknown (repeatable).")
@click.option("--mailbox", default=None, help="Protected mailbox address (exact).")
@click.option("--sender-email", default=None, help="Sender address (exact).")
@click.option("--sender-domain", default=None, help="Sender registrable root domain.")
@click.option("--campaign-id", default=None, help="Only members of this campaign.")
@click.option("--state", multiple=True, help="Message state (repeatable).")
@click.option("--direction", multiple=True, help="inbound|outbound|internal (repeatable).")
@click.option("--user-reported", is_flag=True, default=False, help="Only mail a person reported.")
@click.option("--no-user-reported", is_flag=True, default=False, help="Only mail nobody reported.")
@click.option("--min-score", default=None, type=int, help="Only messages at or above this score.")
@click.option("--link-domain", default=None, help="IOC pivot: who else got mail linking here.")
@click.option("--attachment-sha256", default=None, help="IOC pivot: who else got this file.")
@click.option("--since", default=None, help="Lower time bound (RFC3339 or unix seconds).")
@click.option("--until", default=None, help="Upper time bound.")
@click.option("--cursor", default=None, help="Keyset token from a previous page.")
@click.option("--limit", default=None, type=int, help="Page size.")
@pass_context
def message_list(ctx, verdict, mailbox, sender_email, sender_domain, campaign_id, state,
                 direction, user_reported, no_user_reported, min_score, link_domain,
                 attachment_sha256, since, until, cursor, limit) -> None:
    """The message index — the triage queue.

    \b
    Examples:
      limacharlie mailsec message list --verdict suspicious
      limacharlie mailsec message list --user-reported
      limacharlie mailsec message list --link-domain evil.example
    """
    ms = _get_mailsec(ctx)
    _output(ctx, ms.list_messages(
        verdict=list(verdict) or None,
        mailbox=mailbox,
        sender_email=sender_email,
        sender_domain=sender_domain,
        campaign_id=campaign_id,
        state=list(state) or None,
        direction=list(direction) or None,
        user_reported=_tri_state(user_reported, no_user_reported, "user-reported"),
        min_score=min_score,
        link_domain=link_domain,
        attachment_sha256=attachment_sha256,
        since=since,
        until=until,
        cursor=cursor,
        limit=limit,
    ))


@message_group.command("get")
@click.argument("msg_uuid")
@pass_context
def message_get(ctx, msg_uuid) -> None:
    """One message: the index row plus the re-parsed MDM.

    \b
    Example:
      limacharlie mailsec message get 0057db2b-3a06-5aab-b3be-c1e6c15dcf10
    """
    _output(ctx, _get_mailsec(ctx).get_message(msg_uuid))


@message_group.command("eml")
@click.argument("msg_uuid")
@click.option("--justification", required=True,
              help="Why you are downloading this person's mail. Written to the access audit.")
@click.option("--out-file", "out_path", default=None, type=click.Path(dir_okay=False),
              help="Write the raw bytes to this path instead of to stdout. Deliberately NOT "
                   "--output: that is the global format option, and a command-level --output "
                   "would shadow it so that `--output yaml` silently wrote a file named 'yaml'.")
@pass_context
def message_eml(ctx, msg_uuid, justification, out_path) -> None:
    """Download the original bytes of a message (audited).

    \b
    Example:
      limacharlie mailsec message eml 0057db2b-... --justification "INC-4471"
    """
    ms = _get_mailsec(ctx)
    data = ms.get_message_eml(msg_uuid, justification)
    if out_path:
        with open(out_path, "wb") as f:
            f.write(data)
        if not ctx.obj.quiet:
            click.echo(f"wrote {len(data)} bytes to {out_path}")
        return
    click.get_binary_stream("stdout").write(data)


@message_group.command("similar")
@click.argument("msg_uuid")
@click.option("--cursor", default=None, help="Keyset token from a previous page.")
@click.option("--limit", default=None, type=int, help="Page size.")
@pass_context
def message_similar(ctx, msg_uuid, cursor, limit) -> None:
    """Messages clustered with this one — who else got it.

    \b
    Example:
      limacharlie mailsec message similar 0057db2b-...
    """
    _output(ctx, _get_mailsec(ctx).list_similar_messages(msg_uuid, cursor=cursor, limit=limit))


@message_group.command("action")
@click.argument("msg_uuid")
@click.option("--action", "action_name", required=True,
              help="quarantine_message|trash_message|restore_message|banner_message|unbanner_message")
@click.option("--reason", default=None, help="Recorded on the audit row.")
@click.option("--attempt", default=None, help="Caller-supplied idempotency token.")
@click.option("--banner", default=None, help="Banner HTML, for the banner actions.")
@pass_context
def message_action(ctx, msg_uuid, action_name, reason, attempt, banner) -> None:
    """Remediate one message at the provider (mailsec.act).

    \b
    Example:
      limacharlie mailsec message action 0057db2b-... --action quarantine_message --reason "phish"
    """
    ms = _get_mailsec(ctx)
    _output(ctx, ms.act_on_message(
        msg_uuid, action_name, reason=reason, attempt=attempt, banner=banner,
    ))


@message_group.command("revise")
@click.argument("msg_uuid")
@click.option("--verdict", required=True,
              type=click.Choice(["malicious", "suspicious", "graymail", "benign", "unknown"]),
              help="The verdict to set.")
@click.option("--rationale", "rationale", multiple=True, required=True,
              help="Why the verdict is changing (repeatable, at least one, each <= 280 chars). "
                   "Written to the revision audit.")
@click.option("--score", default=None, type=float, help="Optional score to record with the revision.")
@pass_context
def message_revise(ctx, msg_uuid, verdict, rationale, score) -> None:
    """Revise a message's verdict as an analyst (mailsec.act).

    \b
    mode is 'analyst' — the operator of this CLI is a person. An agent
    revises with its own key and mode 'ai' through the API, not here.
    applied:false means it was already this verdict, not an error.

    \b
    Example:
      limacharlie mailsec message revise 0057db2b-... --verdict malicious --rationale "confirmed phish"
    """
    ms = _get_mailsec(ctx)
    _output(ctx, ms.revise_verdict(msg_uuid, verdict, list(rationale), score=score))


@message_group.command("revisions")
@click.argument("msg_uuid")
@pass_context
def message_revisions(ctx, msg_uuid) -> None:
    """The verdict revision history for a message, oldest first.

    \b
    Example:
      limacharlie mailsec message revisions 0057db2b-...
    """
    _output(ctx, _get_mailsec(ctx).list_revisions(msg_uuid))


@message_group.command("bulk-action")
@click.option("--action", "action_name", required=True,
              help="The action to apply to every selected message: " + "|".join(BULK_ACTIONS) + ".")
@click.option("--msg-uuids", "msg_uuids", multiple=True,
              help="Message ids, comma-separated and/or repeatable. Combined with --input-file.")
@click.option("--input-file", default=None,
              type=click.Path(exists=True, dir_okay=False, allow_dash=True),
              help="File of message ids: a JSON/YAML list, or one per line. '-' reads stdin, and "
                   "stdin is also read when neither this nor --msg-uuids is given.")
@click.option("--attempt", default=None,
              help="Idempotency token. It is part of the confirmation, so a NEW attempt over the "
                   "same selection is a deliberate second run rather than a re-run of the first.")
@click.option("--banner", default=None, help="Banner HTML, for banner_message. Applies to the whole batch.")
@click.option("--confirm", default=None,
              help="Pass the token the preview returned to EXECUTE. Omit to preview. The token is "
                   "derived from the action, the attempt and the member list, so the execute must "
                   "repeat the identical --action, --msg-uuids and --attempt.")
@click.option("--wait/--no-wait", default=True,
              help="Poll until the job settles (default), or return as soon as it is accepted.")
@click.option("--timeout", default=300, type=click.IntRange(min=5),
              help="Maximum seconds to wait (default: 300).")
@click.option("--poll-interval", default=3, type=click.IntRange(min=1),
              help="Seconds between polls (default: 3).")
@pass_context
def message_bulk_action(ctx, action_name, msg_uuids, input_file, attempt, banner, confirm,
                        wait, timeout, poll_interval) -> None:
    """Remediate a set of messages you name, in bulk (mailsec.act).

    \b
    Previews unless --confirm is given, like `campaign action` and
    `hunt remediate`. The preview prints its confirm token, which is
    bound to the action, the attempt and the exact selection: repeat all
    three on the execute. Up to 500 per call; a larger one is refused
    rather than truncated.

    \b
    The exit code carries the outcome: 0 for a completed job that acted on
    something, non-zero for not-accepted, all-failed, interrupted, stalled,
    timed-out, or a failed poll.

    \b
    Example:
      limacharlie mailsec message bulk-action --action trash_message --msg-uuids 0057db2b-...
      limacharlie mailsec message bulk-action --action trash_message --msg-uuids 0057db2b-... --confirm 3f31ed...
    """
    # ONE list, normalized once, used by both calls. Rebuilding it between the
    # preview and the execute would be a second chance to disagree with the set
    # the operator just approved, which is exactly what the token exists to catch.
    selection = _bulk_selection(msg_uuids, input_file)
    ms = _get_mailsec(ctx)

    if not confirm:
        preview = ms.bulk_action_preview(action_name, selection, attempt=attempt)
        _echo_bulk_preview(ctx, preview)
        _output_preview(ctx, preview)
        return

    accepted = ms.bulk_action_execute(
        action_name, selection, confirm, attempt=attempt, banner=banner,
    )
    bulk_id = accepted.get("bulk_id")
    if not accepted.get("accepted") or not bulk_id:
        # The response says it did not take the job. Reporting success here is
        # how a runbook proceeds to its next step over mail nobody touched.
        note(ctx, "the bulk execute was NOT accepted; nothing is running")
        _output(ctx, accepted)
        ctx.exit(1)
        return

    # The handle, on stderr, BEFORE anything that can fail. A poll that 502s
    # after this still leaves the operator holding the id of a job that is
    # running; one that 502s before it would have orphaned the job entirely.
    note(ctx, f"bulk {bulk_id} accepted")
    if not accepted.get("started", True):
        note(ctx, f"bulk {bulk_id} already existed; adopting it rather than acting twice")

    if not wait:
        _output(ctx, accepted)
        return

    try:
        status = _wait_for_bulk(ctx, ms, bulk_id, timeout, poll_interval)
    except Exception as e:
        note(ctx, f"bulk {bulk_id} accepted, but polling it failed: {e}")
        note(
            ctx,
            f"the job is unaffected; resume with: "
            f"limacharlie mailsec message bulk-status {bulk_id}",
        )
        # The acceptance is what stdout has to carry: it is the document that
        # holds the bulk_id, and stdout stays one parseable document either way.
        _output(ctx, accepted)
        ctx.exit(1)
        return

    _output(ctx, status)
    code = _bulk_outcome(ctx, bulk_id, status, timeout)
    if code:
        ctx.exit(code)


@message_group.command("bulk-status")
@click.argument("bulk_id")
@pass_context
def message_bulk_status(ctx, bulk_id) -> None:
    """A bulk action's progress and per-message outcomes.

    \b
    state is running|complete|interrupted. stalled:true means the worker
    is gone — re-send the same execute to finish it.

    \b
    Example:
      limacharlie mailsec message bulk-status 8f1c2d3e4a5b6c7d8e9f0a1b2c3d4e5f
    """
    _output(ctx, _get_mailsec(ctx).bulk_action_status(bulk_id))


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@campaign_group.command("list")
@click.option("--state", multiple=True, help="Campaign state (repeatable).")
@click.option("--verdict", multiple=True, help="Campaign verdict (repeatable).")
@click.option("--min-members", default=None, type=int, help="Only campaigns with at least this many members.")
@click.option("--since", default=None, help="Lower time bound.")
@click.option("--until", default=None, help="Upper time bound.")
@click.option("--cursor", default=None, help="Keyset token from a previous page.")
@click.option("--limit", default=None, type=int, help="Page size.")
@pass_context
def campaign_list(ctx, state, verdict, min_members, since, until, cursor, limit) -> None:
    """Campaigns: one attack triaged once, not once per mailbox.

    \b
    Example:
      limacharlie mailsec campaign list --min-members 3
    """
    ms = _get_mailsec(ctx)
    _output(ctx, ms.list_campaigns(
        state=list(state) or None,
        verdict=list(verdict) or None,
        min_members=min_members,
        since=since, until=until, cursor=cursor, limit=limit,
    ))


@campaign_group.command("get")
@click.argument("campaign_id")
@pass_context
def campaign_get(ctx, campaign_id) -> None:
    """One campaign with its aggregates and cluster keys.

    \b
    Example:
      limacharlie mailsec campaign get ec7e273b-...
    """
    _output(ctx, _get_mailsec(ctx).get_campaign(campaign_id))


@campaign_group.command("action")
@click.argument("campaign_id")
@click.option("--action", "action_name", required=True, help="The typed action to sweep.")
@click.option("--confirm", default=None,
              help="Pass the member-bound token returned by the preview to EXECUTE. Omit to preview.")
@click.option("--reason", default=None, help="Recorded on every resulting audit row.")
@pass_context
def campaign_action(ctx, campaign_id, action_name, confirm, reason) -> None:
    """Sweep an action across a whole campaign (mailsec.act).

    \b
    Previews unless --confirm is given.

    \b
    Example:
      limacharlie mailsec campaign action ec7e273b-... --action quarantine_message --confirm 3c514e...
    """
    ms = _get_mailsec(ctx)
    _output(ctx, ms.act_on_campaign(campaign_id, action_name, confirm=confirm, reason=reason))


# ---------------------------------------------------------------------------
# Senders, audit
# ---------------------------------------------------------------------------

@sender_group.command("get")
@click.argument("key")
@pass_context
def sender_get(ctx, key) -> None:
    """A sender's history with this org.

    \b
    Example:
      limacharlie mailsec sender get cfo@corp.example
    """
    _output(ctx, _get_mailsec(ctx).get_sender_profile(key))


@action_group.command("get")
@click.argument("action_id")
@pass_context
def action_get(ctx, action_id) -> None:
    """One record from the action audit trail.

    \b
    Example:
      limacharlie mailsec action get <action_id>
    """
    _output(ctx, _get_mailsec(ctx).get_action(action_id))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@report_group.command("list")
@click.option("--status", multiple=True, help="open|triaging|resolved (repeatable).")
@click.option("--oldest-first", is_flag=True, default=False,
              help="Order by age — the SLA view: the oldest thing nobody has looked at.")
@click.option("--cursor", default=None, help="Keyset token from a previous page.")
@click.option("--limit", default=None, type=int, help="Page size.")
@pass_context
def report_list(ctx, status, oldest_first, cursor, limit) -> None:
    """The abuse-mailbox report queue.

    \b
    Example:
      limacharlie mailsec report list --status open --oldest-first
    """
    ms = _get_mailsec(ctx)
    _output(ctx, ms.list_reports(
        status=list(status) or None,
        # Only forwarded when set, so absent keeps the newest-first default
        # every other list in this API uses.
        oldest_first=True if oldest_first else None,
        cursor=cursor, limit=limit,
    ))


@report_group.command("get")
@click.argument("report_id")
@pass_context
def report_get(ctx, report_id) -> None:
    """One report and the original it refers to.

    \b
    Example:
      limacharlie mailsec report get dfed9d76ce5ee1096852ea563f5cce23
    """
    _output(ctx, _get_mailsec(ctx).get_report(report_id))


@report_group.command("resolve")
@click.argument("report_id")
@click.option("--disposition", required=True,
              type=click.Choice(["true_positive", "false_positive", "benign"]),
              help="What was decided. 'unknown' is deliberately not offered.")
@pass_context
def report_resolve(ctx, report_id, disposition) -> None:
    """Close a report with a disposition (mailsec.set).

    \b
    Example:
      limacharlie mailsec report resolve <report_id> --disposition true_positive
    """
    _output(ctx, _get_mailsec(ctx).resolve_report(report_id, disposition))


@report_group.command("reopen")
@click.argument("report_id")
@pass_context
def report_reopen(ctx, report_id) -> None:
    """Reopen a resolved report (mailsec.set).

    \b
    The inverse of resolve. Reopening an already-open report succeeds
    and says so.

    \b
    Example:
      limacharlie mailsec report reopen <report_id>
    """
    _output(ctx, _get_mailsec(ctx).reopen_report(report_id))


# ---------------------------------------------------------------------------
# Hunts
# ---------------------------------------------------------------------------

@hunt_group.command("create")
@click.option("--detect-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="JSON file holding a D&R detect block.")
@click.option("--lcql", default=None, help="An LCQL query, as an alternative to --detect-file.")
@click.option("--since", default=None, help="Lower time bound.")
@click.option("--until", default=None, help="Upper time bound.")
@click.option("--dry-run", is_flag=True, default=False, help="Estimate cost and matches without running.")
@pass_context
def hunt_create(ctx, detect_file, lcql, since, until, dry_run) -> None:
    """Start a retro-hunt over message history.

    \b
    Example:
      limacharlie mailsec hunt create --detect-file detect.json --since 2026-07-01
    """
    if not detect_file and not lcql:
        raise click.UsageError("a hunt needs something to match: pass --detect-file or --lcql")
    detect = _load_json_file(detect_file, "--detect-file") if detect_file else None
    ms = _get_mailsec(ctx)
    _output(ctx, ms.create_hunt(
        detect=detect, lcql=lcql, since=since, until=until,
        dry_run=True if dry_run else None,
    ))


@hunt_group.command("get")
@click.argument("hunt_id")
@pass_context
def hunt_get(ctx, hunt_id) -> None:
    """A hunt's status and results.

    \b
    Example:
      limacharlie mailsec hunt get <hunt_id>
    """
    _output(ctx, _get_mailsec(ctx).get_hunt(hunt_id))


@hunt_group.command("remediate")
@click.argument("hunt_id")
@click.option("--action", "action_name", required=True, help="The typed action to apply to the results.")
@click.option("--confirm", default=None, help="Pass the hunt id to EXECUTE. Omit to preview.")
@click.option("--reason", default=None, help="Recorded on every resulting audit row.")
@pass_context
def hunt_remediate(ctx, hunt_id, action_name, confirm, reason) -> None:
    """Bulk-remediate a hunt's results (mailsec.act).

    \b
    Previews unless --confirm is given.

    \b
    Example:
      limacharlie mailsec hunt remediate <hunt_id> --action quarantine_message --confirm <hunt_id>
    """
    ms = _get_mailsec(ctx)
    _output(ctx, ms.remediate_hunt(hunt_id, action_name, confirm=confirm, reason=reason))


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@rule_group.command("validate")
@click.option("--file", "rule_file", required=True, type=click.Path(exists=True, dir_okay=False),
              help="JSON file holding the candidate rule body.")
@click.option("--rule-id", default=None, help="Rule id; tenant ids must start with 'custom-'.")
@pass_context
def rule_validate(ctx, rule_file, rule_id) -> None:
    """Check a candidate rule without saving it.

    \b
    Runs the same validation the dr-mail hive applies on save.

    \b
    Example:
      limacharlie mailsec rule validate --file rule.json --rule-id custom-lookalike
    """
    rule = _load_json_file(rule_file, "--file")
    _output(ctx, _get_mailsec(ctx).validate_rule(rule, rule_id=rule_id))


@rule_group.command("backtest")
@click.option("--file", "rule_file", required=True, type=click.Path(exists=True, dir_okay=False),
              help="JSON file holding the candidate rule body.")
@click.option("--rule-id", default=None, help="Rule id; tenant ids must start with 'custom-'.")
@click.option("--since", default=None, help="Lower time bound.")
@click.option("--until", default=None, help="Upper time bound.")
@pass_context
def rule_backtest(ctx, rule_file, rule_id, since, until) -> None:
    """Replay a candidate rule over recent mail and report its precision.

    \b
    Example:
      limacharlie mailsec rule backtest --file rule.json --since 2026-08-01
    """
    rule = _load_json_file(rule_file, "--file")
    ms = _get_mailsec(ctx)
    _output(ctx, ms.backtest_rule(rule, rule_id=rule_id, since=since, until=until))


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

@connection_group.command("test")
@click.argument("record")
@click.option(
    "--include-watch",
    is_flag=True,
    default=False,
    help="Establish a real Workspace push watch to verify delivery (side effect; idempotent).",
)
@pass_context
def connection_test(ctx, record, include_watch) -> None:
    """Exercise a saved provider connection end to end.

    \b
    Takes the mailsec_provider RECORD NAME, never a credential.

    \b
    Example:
      limacharlie mailsec connection test gws-exp
      limacharlie mailsec connection test gws-exp --include-watch
    """
    _output(ctx, _get_mailsec(ctx).test_connection(record, include_watch=include_watch))


# ---------------------------------------------------------------------------
# Explain registration
# ---------------------------------------------------------------------------

register_explain("mailsec.coverage", _EXPLAIN_COVERAGE)
register_explain("mailsec.analyze", _EXPLAIN_ANALYZE)
register_explain("mailsec.onboarding", _EXPLAIN_ONBOARDING)
register_explain("mailsec.message.list", _EXPLAIN_MESSAGE_LIST)
register_explain("mailsec.message.get", _EXPLAIN_MESSAGE_GET)
register_explain("mailsec.message.eml", _EXPLAIN_MESSAGE_EML)
register_explain("mailsec.message.similar", _EXPLAIN_MESSAGE_SIMILAR)
register_explain("mailsec.message.action", _EXPLAIN_MESSAGE_ACTION)
register_explain("mailsec.message.revise", _EXPLAIN_MESSAGE_REVISE)
register_explain("mailsec.message.revisions", _EXPLAIN_MESSAGE_REVISIONS)
register_explain("mailsec.message.bulk-action", _EXPLAIN_MESSAGE_BULK_ACTION)
register_explain("mailsec.message.bulk-status", _EXPLAIN_MESSAGE_BULK_STATUS)
register_explain("mailsec.campaign.list", _EXPLAIN_CAMPAIGN_LIST)
register_explain("mailsec.campaign.get", _EXPLAIN_CAMPAIGN_GET)
register_explain("mailsec.campaign.action", _EXPLAIN_CAMPAIGN_ACTION)
register_explain("mailsec.sender.get", _EXPLAIN_SENDER_GET)
register_explain("mailsec.action.get", _EXPLAIN_ACTION_GET)
register_explain("mailsec.report.list", _EXPLAIN_REPORT_LIST)
register_explain("mailsec.report.get", _EXPLAIN_REPORT_GET)
register_explain("mailsec.report.resolve", _EXPLAIN_REPORT_RESOLVE)
register_explain("mailsec.report.reopen", _EXPLAIN_REPORT_REOPEN)
register_explain("mailsec.hunt.create", _EXPLAIN_HUNT_CREATE)
register_explain("mailsec.hunt.get", _EXPLAIN_HUNT_GET)
register_explain("mailsec.hunt.remediate", _EXPLAIN_HUNT_REMEDIATE)
register_explain("mailsec.rule.validate", _EXPLAIN_RULE_VALIDATE)
register_explain("mailsec.rule.backtest", _EXPLAIN_RULE_BACKTEST)
register_explain("mailsec.connection.test", _EXPLAIN_CONNECTION_TEST)
