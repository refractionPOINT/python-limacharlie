"""Email Security (mailsec) commands for LimaCharlie CLI v2.

Commands for the ``/mailsec`` API surface: the coverage screen, the message
index and its drawer, the justified raw-EML download, campaigns and
campaign-wide sweeps, sender profiles, the action audit trail, the
abuse-mailbox report queue, standalone EML analysis, retro-hunts, custom-rule
validation and backtest, the connection preflight, and the served onboarding
guide.

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
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.mailsec import Mailsec
from ..output import format_output, detect_output_format
from ..discovery import register_explain


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
      message ...         The triage queue, drawer, raw EML, similar, actions
      campaign ...        Campaigns and campaign-wide sweeps
      sender get          A sender's history with this org
      action get          One record from the action audit trail
      analyze             Parse and score an EML without ingesting it
      report ...          Abuse-mailbox report queue (list, get, resolve)
      hunt ...            Retro-hunts (create, get, remediate)
      rule ...            Custom rule validation and backtest
      connection test     Provider connection preflight
      onboarding          Provider setup guide, with your values filled in
    """


@group.group("message")
def message_group() -> None:
    """The message index, drawer, raw EML, similar mail, and actions."""


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
    """The abuse-mailbox report queue."""


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
register_explain("mailsec.campaign.list", _EXPLAIN_CAMPAIGN_LIST)
register_explain("mailsec.campaign.get", _EXPLAIN_CAMPAIGN_GET)
register_explain("mailsec.campaign.action", _EXPLAIN_CAMPAIGN_ACTION)
register_explain("mailsec.sender.get", _EXPLAIN_SENDER_GET)
register_explain("mailsec.action.get", _EXPLAIN_ACTION_GET)
register_explain("mailsec.report.list", _EXPLAIN_REPORT_LIST)
register_explain("mailsec.report.get", _EXPLAIN_REPORT_GET)
register_explain("mailsec.report.resolve", _EXPLAIN_REPORT_RESOLVE)
register_explain("mailsec.hunt.create", _EXPLAIN_HUNT_CREATE)
register_explain("mailsec.hunt.get", _EXPLAIN_HUNT_GET)
register_explain("mailsec.hunt.remediate", _EXPLAIN_HUNT_REMEDIATE)
register_explain("mailsec.rule.validate", _EXPLAIN_RULE_VALIDATE)
register_explain("mailsec.rule.backtest", _EXPLAIN_RULE_BACKTEST)
register_explain("mailsec.connection.test", _EXPLAIN_CONNECTION_TEST)
