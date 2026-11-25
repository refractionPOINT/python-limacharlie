"""Deception commands for LimaCharlie CLI v2.

Wraps the ``ext-deception`` extension:

* ``config`` -- the configuration record (``extension_config`` / ``ext-deception``).
* ``plan`` / ``deploy`` / ``rollout-status`` -- apply the configuration.
* ``list`` / ``list-hosts`` / ``verify`` / ``rotate`` / ``remove`` -- the decoys.
* ``coverage`` / ``test-fire`` / ``list-test-runs`` / ``list-test-paths``.
* ``list-hits`` / ``list-readers`` -- what touched the decoys.
* ``drops`` -- sensorless tokens (a link, a QR code, a host name, a document).
* ``kinds`` / ``restore-rules`` / ``uninstall`` / ``uninstall-status``.

The extension validates every request and the configuration, so the CLI
validates nothing itself beyond the shape of its own flags.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any

import click

from ..cli import pass_context
from ..client import Client
from ..discovery import register_explain
from ..sdk.deception import (
    DOCUMENT_FORMATS,
    DROP_FORMS,
    LAYERS,
    PLATFORMS,
    Deception,
)
from ..sdk.organization import Organization
from ._input_helpers import load_file, load_stdin
from .. import output as output_state
from ..output import detect_output_format, format_output
from ._output_helpers import command_output
from ._time_validation import validate_epoch_seconds

group = click.Group(
    "deception",
    help="Deception: decoys on endpoints and drops anywhere, alerting on read and use.",
)


@click.group("drops")
def drops_group() -> None:
    """Drops: tokens with no sensor behind them (create, list, get, update, rotate, delete)."""


@click.group("config")
def config_group() -> None:
    """The configuration record: get, set, enable."""


group.add_command(drops_group)
group.add_command(config_group)


def _get_dec(ctx: click.Context) -> Deception:
    client = Client(
        oid=ctx.obj.oid,
        environment=ctx.obj.environment,
        print_debug_fn=ctx.obj.debug_fn,
        debug_full_response=ctx.obj.debug_full,
        debug_curl=ctx.obj.debug_curl,
        debug_verbose=ctx.obj.debug_verbose,
    )
    return Deception(Organization(client))


def _page_options(fn):
    fn = click.option("--page-token", default=None, help="next_page_token of the previous page.")(fn)
    fn = click.option("--page-size", type=click.IntRange(min=1, max=500), default=None,
                      help="Page size (default 100, at most 500).")(fn)
    return fn


def _scope_options(fn):
    """--policy, --sid, --instance-id and --template of verify, rotate and remove."""
    fn = click.option("--template", default=None,
                      help="The decoys of this template (it need not be in the configuration any more).")(fn)
    fn = click.option("--instance-id", "instance_ids", multiple=True,
                      help="A decoy instance id from 'deception list' (repeatable).")(fn)
    fn = click.option("--sid", default=None, help="The decoys of this sensor.")(fn)
    fn = click.option("--policy", default=None, help="The decoys of this policy.")(fn)
    return fn


def _document_options(fn):
    """The content fields of a document drop."""
    fn = click.option("--document-file", type=click.Path(exists=True), default=None,
                      help="YAML or JSON with the document fields (file_name, title, lines, link_text, author); "
                           "the flags below override it.")(fn)
    fn = click.option("--author", default=None, help="Document author property (at most 64 characters).")(fn)
    fn = click.option("--link-text", default=None, help="What the visible link shows (at most 60 characters).")(fn)
    fn = click.option("--line", "lines", multiple=True,
                      help="One body paragraph (repeatable, in order; at most 20 of 200 characters).")(fn)
    fn = click.option("--title", default=None, help="Document title (at most 120 characters).")(fn)
    fn = click.option("--file-name", default=None, help="Downloaded file name, ending in .docx or .svg.")(fn)
    return fn


def _document(document_file: str | None, file_name: str | None, title: str | None,
              lines: tuple[str, ...], link_text: str | None, author: str | None) -> dict[str, Any] | None:
    """The document object from --document-file and the field flags, or None when none was given."""
    doc: dict[str, Any] = {}
    if document_file:
        loaded = load_file(document_file, "--document-file")
        if not isinstance(loaded, dict):
            raise click.BadParameter("must hold a mapping of document fields", param_hint="--document-file")
        doc.update(loaded)
    for key, value in (("file_name", file_name), ("title", title), ("link_text", link_text), ("author", author)):
        if value is not None:
            doc[key] = value
    if lines:
        doc["lines"] = list(lines)
    if not document_file and not doc:
        return None
    return doc


def _save_option(fn):
    return click.option(
        "--save", "save_path", type=click.Path(dir_okay=False, writable=True), default=None,
        help="Also write the paste file to this path: the document (document drops) or the QR code as SVG "
             "(qr drops). The answer is printed either way.",
    )(fn)


_SAVE_FAILED = "the answer above is complete; nothing was written to {path}: {why}"


def _save_paste(result: dict[str, Any], path: str) -> None:
    """Write the file a drop's paste carries (a document, or a QR code as SVG) to ``path``."""
    paste = result.get("paste") or {}
    doc = paste.get("document")
    try:
        if isinstance(doc, dict) and doc.get("content_b64"):
            content = base64.b64decode(doc["content_b64"], validate=True)
            expected = doc.get("sha256")
            if expected and hashlib.sha256(content).hexdigest() != str(expected).lower():
                raise click.ClickException(_SAVE_FAILED.format(
                    path=path, why="the document does not match its sha256"))
            with open(path, "wb") as f:
                f.write(content)
        elif paste.get("qr_svg"):
            with open(path, "w", encoding="utf-8") as f:
                f.write(paste["qr_svg"])
        else:
            raise click.ClickException(_SAVE_FAILED.format(
                path=path, why="its paste has no file (a url or hostname drop, or a deleted drop)"))
    except (binascii.Error, ValueError, OSError) as exc:
        raise click.ClickException(_SAVE_FAILED.format(path=path, why=exc))
    click.echo(f"Wrote {path}", err=True)


def _output_and_save(ctx, result: dict[str, Any], save_path: str | None) -> None:
    # Print first: a create cannot be repeated to get the same value, so the
    # answer must reach the operator even if the file cannot be written.
    _out(ctx, None, result)
    if save_path:
        _save_paste(result, save_path)


def _out(ctx: click.Context, rows: str | None, data: Any) -> None:
    """Print an answer.

    Every format but a table prints the answer whole. A table cannot show an
    answer's nested values (a list reads "[4 items]" and long values are cut),
    so a table shows the answer's ``rows`` list as a table followed by the
    rest of the answer as YAML (page tokens and totals whole), and any other
    answer as YAML. With --filter or --fields the answer is printed as usual,
    since those are written against the whole answer.
    """
    fmt = ctx.obj.output_format or detect_output_format()
    if fmt != "table" or ctx.obj.quiet or output_state._filter_expr or output_state._fields:
        command_output(ctx, data)
        return
    if rows and isinstance(data, dict) and isinstance(data.get(rows), list) and data[rows] \
            and all(isinstance(r, dict) for r in data[rows]):
        click.echo(format_output(data[rows], "table"))
        rest = {k: v for k, v in data.items() if k != rows and v not in (None, "", [], {})}
        if rest:
            click.echo(format_output(rest, "yaml"))
        return
    click.echo(format_output(data, "yaml"))


def _require_confirm(confirm: bool) -> None:
    if not confirm:
        raise click.UsageError("Destructive operation requires --confirm flag.")


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_PAGE_HELP = (
    "Filtering and paging happen on the server. --page-size is at most 500 (default 100); "
    "pass a page's next_page_token as --page-token to get the next one (empty: the last page)."
)

register_explain("deception", """\
Deception ('ext-deception') plants unique decoys on endpoints through the
sensor (credential files, keys, documents, browser entries...) and alerts when
one is read or used, and makes drops: tokens with no sensor behind them (a
link, a QR code, a host name, a document) to put anywhere an intruder looks.

Everything that decides what alerts is one record, the 'ext-deception' record
of the 'extension_config' hive: policies, templates, reader allowlists and
declared drops ('deception config'). The extension keeps no learned state.

  config            The configuration record: get, set, enable.
  kinds             Decoy kinds, the template library, benign readers.
  plan / deploy     What deploy would do; apply the configuration.
  rollout-status    How far the rollout to the sensors is (cheap to poll).
  list, list-hosts  Decoys, and hosts with their status.
  verify, rotate, remove
                    Act on decoys (by policy, sensor, template or instance).
  coverage          What is covered, unavailable, blind or broken.
  test-fire         Prove each alert path (list-test-runs, list-test-paths).
  list-hits         Recorded hits (or hit groups).
  list-readers      Who reads the decoys, with the allowlist entry to approve them.
  drops ...         create, list, get, update, rotate, delete, draft-document.
  restore-rules     Put shipped detection rules back as shipped.
  uninstall         Remove everything before unsubscribing (uninstall-status reads).

Permissions: ext.request for every request; ext.conf.get and ext.conf.set for
the configuration record.

Quick start:
  limacharlie extension subscribe --name ext-deception
  limacharlie deception kinds
  limacharlie deception config set --input-file deception.yaml
  limacharlie deception plan
  limacharlie deception deploy
  limacharlie deception coverage
  limacharlie deception test-fire
""")

register_explain("deception.config", """\
The configuration record: the 'ext-deception' record of the 'extension_config'
hive. It also works with 'limacharlie extension config-get/config-set', the
generic 'hive' commands and 'limacharlie sync' (--hive-extension-config).
A disabled record gives the extension an empty configuration, and requests
that read policies refuse with "the ext-deception configuration is disabled".
""")

register_explain("deception.config.get", """\
Read the configuration record: data (the configuration), usr_mtd (enabled,
tags, comment, expiry) and sys_mtd (etag). Save it, edit 'data', and give the
file back to 'config set': the etag in the file makes the write a
compare-and-set, refused if someone saved the record in the meantime.

Example:
  limacharlie deception config get --output yaml > ext-deception.yaml
""")

register_explain("deception.config.set", """\
Write the configuration record. The extension validates the whole
configuration (kind specs included) and refuses it with the problems.

Input (--input-file or stdin, YAML or JSON) is either:
  * the configuration itself (schema_version, policies, templates,
    reader_allowlist, drops, ...), or
  * a record as 'config get' prints it: 'data' holds the configuration,
    with optional 'usr_mtd' and an etag ('etag' or 'sys_mtd.etag').

Metadata:
  * no usr_mtd and no flag: an existing record keeps its metadata; a record
    that does not exist yet is created ENABLED (creation is conditional, so a
    record created meanwhile is not replaced).
  * a usr_mtd block replaces the stored metadata (as 'hive set': a block
    without 'enabled' stores the record disabled).
  * --enabled / --disabled set the enabled state and win over usr_mtd.

Etag: --etag, or the one in the input, makes the write a compare-and-set; a
stale etag, or the etag of a record deleted since, is refused (read the
record again). --no-etag ignores the one in
the input. Reading the stored metadata takes ext.conf.get (or
ext.conf.get.mtd); writing takes ext.conf.set.

Examples:
  limacharlie deception config set --input-file deception.yaml
  limacharlie deception config get --output yaml > rec.yaml   # edit data:
  limacharlie deception config set --input-file rec.yaml       # compare-and-set
""")

register_explain("deception.config.enable", """\
Enable the configuration record (a record saved disabled, for example by
'extension config-set' on a new record, gives the extension an empty
configuration). Same as:
  limacharlie hive enable --hive-name extension_config --key ext-deception
""")

register_explain("deception.kinds", """\
Every decoy kind with its spec version and JSON schema, LimaCharlie's template
library (copy a 'library' entry into your configuration's templates, without
its 'recommended' field), each template's alert profile, and the starter list
of benign readers to copy into reader_allowlist (never applied automatically).
""")

register_explain("deception.plan", """\
Read-only. Per policy: sensors, decoys to place and retire, what is
unavailable and why; the shipped detection rules and their state; the exfil
watch-rule budget; the sources the org sends; the Lookups reader allowlists
reference; the configuration's drops; the isolation cap; warnings.
plan.deploy.rollout is the rollout's progress.

--draft-policy FILE plans an unsaved policy (a policy record as the
configuration stores it) instead, with --draft-templates FILE (a list of
template records the save would add); not with --policy or --sid.

Examples:
  limacharlie deception plan
  limacharlie deception plan --policy linux-servers
  limacharlie deception plan --draft-policy policy.yaml --draft-templates templates.yaml
""")

register_explain("deception.deploy", """\
Idempotent. Converges the plumbing rules, installs missing shipped detection
rules (never overwriting an edited one) and the extension's entries in
ext-exfil, ext-integrity and ext-artifact, then starts placing decoys. The
rollout continues on its own after it returns: follow it with
'rollout-status'. Never subscribes the org to another extension.

--apply-pack RULE (repeatable) overwrites that shipped rule with the current
shipped version; --apply-all-pack overwrites every shipped rule (your edits
to them are replaced).

Examples:
  limacharlie deception deploy
  limacharlie deception deploy --apply-pack deception-alert --apply-pack deception-respond
""")

register_explain("deception.rollout-status", """\
Read-only and cheap to poll: where the rollout round stands as of its last
pass (deploy.in_progress, deploy.rollout: state, done, total, remaining,
offline, failed, next_pass_by...).
""")

register_explain("deception.list", """\
List decoys: id, sensor, hostname, policy, template, kind, state, path,
sha256, and for failed decoys their cause. Secret values are never returned.
States: planned, placed, verified, retired, gone, failed (default: planned,
placed, verified). --summary also counts every match before paging.
""" + _PAGE_HELP + """

Examples:
  limacharlie deception list --policy linux-servers
  limacharlie deception list --state failed --exclude-skipped --summary
""")

register_explain("deception.list-hosts", """\
Sensors with decoys, and targeted sensors a rollout visited, with their
status: protected, partial, pending, failed, skipped, none, no_decoy,
not_reached or restricted. --sort problems lists the hosts that need
attention first. --summary counts every matching host by status.
""" + _PAGE_HELP + """

Examples:
  limacharlie deception list-hosts --sort problems --summary
  limacharlie deception list-hosts --status failed
""")

_OP_HELP = """\
Scope with --instance-id (repeatable), --sid, --policy and/or --template
(combined when several are given); the extension needs at least one. One call
handles a bounded batch: 'more: true' in the answer means run it again to
continue. 'issues' says what could not be done and why.
"""

register_explain("deception.verify", "Re-check by file hash that decoys are still in place.\n\n" + _OP_HELP)
register_explain("deception.rotate", """\
Retire decoys and plant replacements with new secrets at new paths (for
example after a decoy leaked). For decoys on offline sensors, rotate the
ones the issues name by --instance-id later: a new scoped rotation would
rotate the whole scope again, its own replacements included.

""" + _OP_HELP)
register_explain("deception.remove", """\
Remove decoys from their hosts after checking each file is still the one
planted (a file the extension cannot prove is its own is left in place).
While a policy still selects the template, the next rollout plants a
replacement. To remove everything before unsubscribing, use 'uninstall'.
Requires --confirm.

""" + _OP_HELP)

register_explain("deception.coverage", """\
Per template and alert layer: active, unavailable (with the missing piece),
blind, partial or broken; the token forms in use; the sources the org sends;
the covered-sensor numbers reported for billing; and, for the whole org, the
alert path counts.
""")

register_explain("deception.test-fire", """\
Fire the test-only decoys of the enabled policies (or one --policy), one run
per alert path, or one active drop (--drop-id, not with --policy). Test hits
are synthetic: they never open cases or trigger responses. A run is final when
its detection comes back, or about an hour after it starts without one: read
the outcome with 'list-test-runs' and 'list-test-paths'.
""")

register_explain("deception.list-test-runs", """\
Recent test-fire runs (kept 30 days), newest first: state pending, detected or
not_detected. --state pending or finished.
""" + _PAGE_HELP)

register_explain("deception.list-test-paths", """\
Every alert path with its latest test result (passed, failed, untested) or
why no test proves it (not_testable with its code), plus whether the org is
'proven' (every testable path passed, the newest within 48 hours).
--state passed, failed, untested, not_testable or testable.
""" + _PAGE_HELP)

register_explain("deception.list-hits", """\
Recorded hits (kept 90 days), newest first, from the extension's own record:
no detection query. Synthetic test hits are left out unless --include-test.
--group lists hit groups (one per incident on one decoy or drop) instead;
--group-id lists the hits of one group. --hit-id reads one hit (the other
filters are then not applied). --since and --until are Unix seconds.
--event-type (repeatable): deception_hit, deception_drop_hit,
deception_coverage_warning. --auto-response-outcome (repeatable): done,
capped, failed, refused, pending, skipped, unreported, not_isolated.
""" + _PAGE_HELP + """

Examples:
  limacharlie deception list-hits --layer read --mode observe --page-size 50
  limacharlie deception list-hits --group --event-type deception_hit --event-type deception_drop_hit
""")

register_explain("deception.list-readers", """\
Who reads the decoys: the recorded on-host reads and modifications of the
last --days days (default 30, at most 90) by reader identity and policy, each
with hit counts, whether the reader_allowlist approves it, and a
reader_allowlist entry to paste into the configuration when one is possible.
Use it with observe mode to build the allowlist.
""" + _PAGE_HELP)

register_explain("deception.restore-rules", """\
Write the current shipped version of each named shipped detection rule over
the organization's record and enable it (the repair for a shipped rule that is
disabled, missing, expired or edited). Starts no rollout.

Example:
  limacharlie deception restore-rules --rule deception-respond
""")

register_explain("deception.uninstall", """\
Run this BEFORE unsubscribing. The first call starts the uninstall: nothing
new is placed, every decoy is removed (offline sensors get a queued removal),
and only when none is waiting are the rules, the entries in other extensions'
configurations, the tags and the adapter deleted. Run it again at any time to
advance it and read the status, until safe_to_unsubscribe is true.
Requires --confirm (not with --cancel).

--force finishes although decoys remain on offline sensors (they stay on
disk, inert once unsubscribed). --cancel abandons it; deploy then puts back
what was removed. 'uninstall-status' only reads.
""")

register_explain("deception.uninstall-status", """\
Read-only: where an uninstall stands (not_started, removing_decoys,
removing_rules, done, cancelled or engine_unavailable), the decoys left, and
whether it is safe to unsubscribe. Never starts or advances anything.
""")

register_explain("deception.drops", """\
Drops are tokens with no sensor behind them: a link (url), a QR code (qr), a
host name (hostname) or a document (docx or svg). A hit names the drop's
label and memo. create, get and rotate return what to paste (the only answers
that carry a secret value); --save writes the document or QR code to a file.
Drops declared in the configuration's 'drops' list are managed there: update
and delete refuse them.
""")

register_explain("deception.drops.create", """\
Make a drop. --form url, qr, hostname or document; --label says where it is
put (shown as the case's host, never written into the token). Document drops
take --format docx or svg and optional content (--title, --line, ...; a field
left out is generated: see 'drops draft-document'). url and qr drops take an
optional --redirect-url (checked against Google Web Risk). --mode observe
alerts at medium priority until --observe-until.

Examples:
  limacharlie deception drops create --form url --label "finance wiki: payroll page"
  limacharlie deception drops create --form document --format docx --label "HR share" --save offer.docx
""")

register_explain("deception.drops.list", """\
List drops, newest first (or --sort last_hit), without their secret values.
--state active, disabled, deleted (default active and disabled). --last-hit
never, since or not_since (with --last-hit-since, RFC 3339).
""" + _PAGE_HELP)

register_explain("deception.drops.get", """\
One drop and what to paste, by --drop-id or by --name (a drop the
configuration declares). --save writes its document or QR code to a file.
""")

register_explain("deception.drops.update", """\
Change a drop's label, memo, state (active or disabled), mode, observe end,
redirect or document content. Compare-and-set on the drop's version: pass
--version as read, or leave it out to use the current one. --observe-until ""
clears it; --redirect-url "" removes the redirect; --reset-document makes the
whole document generated again.
""")

register_explain("deception.drops.rotate", """\
Give a drop a new value to paste. The old one keeps alerting for 90 days.
Compare-and-set on the version (default: the current one).
""")

register_explain("deception.drops.delete", """\
Stop a drop's alerts for good (not reversible). The token stays wherever it
was put: remove it there too. Requires --confirm.
""")

register_explain("deception.drops.draft-document", """\
Read-only: the content a document drop would be generated with (a library
template, picked at random each call); fields given are checked and kept.
""")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@config_group.command("get")
@pass_context
def config_get(ctx) -> None:
    """Read the configuration record (data, metadata, etag)."""
    _out(ctx, None, _get_dec(ctx).get_config().to_dict())


@config_group.command("set")
@click.option("--input-file", type=click.Path(exists=True), default=None,
              help="YAML or JSON: the configuration, or a record as 'config get' prints it. Reads stdin if omitted.")
@click.option("--etag", default=None, help="Write only if the stored record still has this etag.")
@click.option("--no-etag", is_flag=True, default=False, help="Ignore an etag in the input (overwrite).")
@click.option("--enabled/--disabled", "enabled", default=None,
              help="Set the record's enabled state (default: kept; a new record is created enabled).")
@pass_context
def config_set(ctx, input_file, etag, no_etag, enabled) -> None:
    """Write the configuration record (validated by the extension)."""
    if etag and no_etag:
        raise click.UsageError("--etag and --no-etag are mutually exclusive.")
    body = load_file(input_file, "--input-file") if input_file else load_stdin()
    if body is None:
        raise click.UsageError("Provide the configuration via --input-file or stdin.")
    if not isinstance(body, dict):
        raise click.UsageError("The configuration must be a mapping.")
    usr_mtd = None
    if "data" in body:
        config = body["data"]
        if not isinstance(config, dict):
            raise click.UsageError("'data' must be a mapping: the configuration.")
        if body.get("usr_mtd") is not None:
            if not isinstance(body["usr_mtd"], dict):
                raise click.UsageError("usr_mtd must be a mapping of metadata fields.")
            usr_mtd = body["usr_mtd"]
        if not etag and not no_etag:
            etag = body.get("etag") or (body.get("sys_mtd") or {}).get("etag")
    else:
        config = body
    result = _get_dec(ctx).set_config(config, etag=etag or None, enabled=enabled, usr_mtd=usr_mtd)
    _out(ctx, None, result)


@config_group.command("enable")
@pass_context
def config_enable(ctx) -> None:
    """Enable the configuration record (a disabled record reads as empty)."""
    _out(ctx, None, _get_dec(ctx).enable_config())


# ---------------------------------------------------------------------------
# kinds, plan, deploy, rollout
# ---------------------------------------------------------------------------

@group.command("kinds")
@pass_context
def kinds(ctx) -> None:
    """Decoy kinds, the template library and the benign readers."""
    _out(ctx, None, _get_dec(ctx).list_kinds())


@group.command("plan")
@click.option("--policy", default=None, help="Limit to one policy.")
@click.option("--sid", default=None, help="Limit to one sensor.")
@click.option("--draft-policy", "draft_policy_file", type=click.Path(exists=True), default=None,
              help="YAML or JSON file with an unsaved policy record to plan instead.")
@click.option("--draft-templates", "draft_templates_file", type=click.Path(exists=True), default=None,
              help="With --draft-policy: YAML or JSON file with a list of template records the save would add.")
@pass_context
def plan(ctx, policy, sid, draft_policy_file, draft_templates_file) -> None:
    """Show what deploy would do (read-only)."""
    if draft_templates_file and not draft_policy_file:
        raise click.UsageError("--draft-templates needs --draft-policy.")
    draft_policy = load_file(draft_policy_file, "--draft-policy") if draft_policy_file else None
    draft_templates = load_file(draft_templates_file, "--draft-templates") if draft_templates_file else None
    if draft_policy_file and not isinstance(draft_policy, dict):
        raise click.BadParameter("must hold a policy record (a mapping)", param_hint="--draft-policy")
    if draft_templates is not None and not isinstance(draft_templates, list):
        raise click.BadParameter("must hold a list of template records", param_hint="--draft-templates")
    _out(ctx, None, _get_dec(ctx).plan(
        policy=policy, sid=sid, draft_policy=draft_policy, draft_templates=draft_templates,
    ))


@group.command("deploy")
@click.option("--policy", default=None, help="Limit to one policy.")
@click.option("--sid", default=None, help="Limit to one sensor.")
@click.option("--apply-pack", "apply_pack", multiple=True,
              help="Overwrite this shipped detection rule with the current shipped version (repeatable).")
@click.option("--apply-all-pack", is_flag=True, default=False, help="Overwrite every shipped detection rule.")
@pass_context
def deploy(ctx, policy, sid, apply_pack, apply_all_pack) -> None:
    """Apply the configuration: rules, other extensions' entries, decoys."""
    _out(ctx, None, _get_dec(ctx).deploy(
        policy=policy, sid=sid, apply_pack=list(apply_pack), apply_all_pack=apply_all_pack,
    ))


@group.command("rollout-status")
@pass_context
def rollout_status(ctx) -> None:
    """How far the rollout to the sensors is (read-only, cheap)."""
    _out(ctx, None, _get_dec(ctx).rollout_status())


@group.command("restore-rules")
@click.option("--rule", "rules", multiple=True, required=True,
              help="Shipped detection rule to restore, for example deception-respond (repeatable).")
@pass_context
def restore_rules(ctx, rules) -> None:
    """Put shipped detection rules back as shipped, enabled, without a rollout."""
    result = _get_dec(ctx).restore_rules(list(rules))
    _out(ctx, None, result)
    # A rule counts as repaired only when it was written AND reads back
    # enabled, with no error (the extension reports a failed read-back so).
    rows = result.get("rules") or []
    if not rows or any(
        not isinstance(r, dict) or not r.get("restored") or not r.get("enabled") or r.get("error")
        for r in rows
    ):
        ctx.exit(1)


# ---------------------------------------------------------------------------
# decoys and hosts
# ---------------------------------------------------------------------------

@group.command("list")
@click.option("--policy", default=None, help="Only this policy's decoys.")
@click.option("--sid", default=None, help="Only this sensor's decoys.")
@click.option("--state", "states", multiple=True,
              type=click.Choice(["planned", "placed", "verified", "retired", "gone", "failed"]),
              help="Only decoys in this state (repeatable; default planned, placed, verified).")
@click.option("--template", default=None, help="Only this template's decoys.")
@click.option("--kind", default=None, help="Only this kind's decoys.")
@click.option("--text", default=None, help="Path, template, policy, hostname or sensor id contains this.")
@click.option("--cause", default=None, help="Only failed decoys of this cause (for example directory_missing).")
@click.option("--include-test", is_flag=True, default=False, help="Also list test-fire decoys.")
@click.option("--include-superseded", is_flag=True, default=False, help="Also list earlier failed attempts.")
@click.option("--exclude-skipped", is_flag=True, default=False, help="Leave out decoys skipped on purpose.")
@click.option("--summary", is_flag=True, default=False, help="Also count every match before paging.")
@_page_options
@pass_context
def list_decoys(ctx, policy, sid, states, template, kind, text, cause, include_test,
                include_superseded, exclude_skipped, summary, page_token, page_size) -> None:
    """List decoys (never their secret values)."""
    _out(ctx, "instances", _get_dec(ctx).list_decoys(
        policy=policy, sid=sid, states=list(states), include_test=include_test, template=template,
        kind=kind, text=text, cause=cause, summary=summary, include_superseded=include_superseded,
        exclude_skipped=exclude_skipped, page_token=page_token, page_size=page_size,
    ))


@group.command("list-hosts")
@click.option("--policy", default=None, help="Only this policy.")
@click.option("--template", default=None, help="Only sensors holding this template's decoy.")
@click.option("--sid", default=None, help="Only this sensor.")
@click.option("--text", default=None, help="Hostname, sensor id, path, template or policy contains this.")
@click.option("--status", default=None,
              help="Only hosts of this status (protected, partial, pending, failed, skipped, none, "
                   "no_decoy, not_reached, restricted).")
@click.option("--state", "states", multiple=True,
              type=click.Choice(["planned", "placed", "verified", "retired", "gone", "failed"]),
              help="Decoy states that count (repeatable; default planned, placed, verified, failed).")
@click.option("--sort", type=click.Choice(["sid", "problems"]), default=None,
              help="sid (default) or problems (hosts that need attention first).")
@click.option("--include-test", is_flag=True, default=False, help="Also count test-fire decoys.")
@click.option("--include-superseded", is_flag=True, default=False, help="Also count earlier failed attempts.")
@click.option("--include-deleted", is_flag=True, default=False, help="Also list sensors removed from the platform.")
@click.option("--summary", is_flag=True, default=False, help="Also count every matching host by status.")
@_page_options
@pass_context
def list_hosts(ctx, policy, template, sid, text, status, states, sort, include_test,
               include_superseded, include_deleted, summary, page_token, page_size) -> None:
    """List targeted sensors and sensors with decoys, with their status."""
    _out(ctx, "hosts", _get_dec(ctx).list_hosts(
        policy=policy, template=template, text=text, states=list(states), include_test=include_test,
        status=status, include_superseded=include_superseded, sid=sid, summary=summary, sort=sort,
        include_deleted=include_deleted, page_token=page_token, page_size=page_size,
    ))


@group.command("verify")
@_scope_options
@pass_context
def verify(ctx, policy, sid, instance_ids, template) -> None:
    """Re-check that decoys are still in place."""
    _out(ctx, None, _get_dec(ctx).verify(
        policy=policy, sid=sid, instance_ids=list(instance_ids), template=template,
    ))


@group.command("rotate")
@_scope_options
@pass_context
def rotate(ctx, policy, sid, instance_ids, template) -> None:
    """Retire decoys and plant replacements with new secrets."""
    _out(ctx, None, _get_dec(ctx).rotate(
        policy=policy, sid=sid, instance_ids=list(instance_ids), template=template,
    ))


@group.command("remove")
@_scope_options
@click.option("--confirm", is_flag=True, default=False, help="Confirm the removal (required).")
@pass_context
def remove(ctx, policy, sid, instance_ids, template, confirm) -> None:
    """Remove decoys from their hosts."""
    _require_confirm(confirm)
    _out(ctx, None, _get_dec(ctx).remove(
        policy=policy, sid=sid, instance_ids=list(instance_ids), template=template,
    ))


# ---------------------------------------------------------------------------
# coverage and test-fire
# ---------------------------------------------------------------------------

@group.command("coverage")
@click.option("--policy", default=None, help="Limit to one policy.")
@pass_context
def coverage(ctx, policy) -> None:
    """What is covered, unavailable, blind or broken."""
    _out(ctx, None, _get_dec(ctx).coverage(policy))


@group.command("test-fire")
@click.option("--policy", default=None, help="Only this policy's alert paths.")
@click.option("--drop-id", default=None, help="Fire this active drop instead (not with --policy).")
@pass_context
def test_fire(ctx, policy, drop_id) -> None:
    """Prove each alert path works (synthetic hits, no cases, no responses)."""
    _out(ctx, "runs", _get_dec(ctx).test_fire(policy=policy, drop_id=drop_id))


@group.command("list-test-runs")
@click.option("--policy", default=None, help="Only this policy's runs.")
@click.option("--template", default=None, help="Only this template's runs.")
@click.option("--layer", type=click.Choice(LAYERS), default=None, help="Only this alert layer.")
@click.option("--state", type=click.Choice(["pending", "finished"]), default=None, help="Default: both.")
@_page_options
@pass_context
def list_test_runs(ctx, policy, template, layer, state, page_token, page_size) -> None:
    """Recent test-fire runs, newest first."""
    _out(ctx, "runs", _get_dec(ctx).list_test_runs(
        policy=policy, template=template, layer=layer, state=state,
        page_token=page_token, page_size=page_size,
    ))


@group.command("list-test-paths")
@click.option("--policy", default=None, help="Only this policy's paths.")
@click.option("--template", default=None, help="Only this template's paths.")
@click.option("--state", type=click.Choice(["passed", "failed", "untested", "not_testable", "testable"]),
              default=None, help="Default: all.")
@_page_options
@pass_context
def list_test_paths(ctx, policy, template, state, page_token, page_size) -> None:
    """Every alert path with its latest test result, or why no test proves it."""
    _out(ctx, "paths", _get_dec(ctx).list_test_paths(
        policy=policy, template=template, state=state, page_token=page_token, page_size=page_size,
    ))


# ---------------------------------------------------------------------------
# hits and readers
# ---------------------------------------------------------------------------

@group.command("list-hits")
@click.option("--since", type=int, default=None, help="Only hits at or after this time (Unix seconds).")
@click.option("--until", type=int, default=None, help="Only hits before this time (Unix seconds).")
@click.option("--layer", type=click.Choice(LAYERS), default=None, help="Only this layer.")
@click.option("--template", default=None, help="Only hits on this template's decoys.")
@click.option("--policy", default=None, help="Only this policy's hits.")
@click.option("--sid", default=None, help="Only this sensor's hits.")
@click.option("--classification", default=None,
              help="For example human-likely, automated, ai-agent-likely, scanner-likely, link-preview-likely.")
@click.option("--event-type", "event_types", multiple=True,
              type=click.Choice(["deception_hit", "deception_drop_hit", "deception_coverage_warning"]),
              help="Only these event types (repeatable; default every type).")
@click.option("--drop-id", default=None, help="Only this drop's hits.")
@click.option("--mode", type=click.Choice(["observe", "live", "context"]), default=None, help="Only this mode.")
@click.option("--auto-response-outcome", "auto_response_outcomes", multiple=True,
              help="Only hits whose automatic response had this outcome (repeatable): done, capped, failed, "
                   "refused, pending, skipped, unreported, not_isolated.")
@click.option("--case-group-key", default=None, help="Only the hits of this incident (<sid>:<incident id>).")
@click.option("--group", "group_", is_flag=True, default=False, help="List hit groups instead of hits.")
@click.option("--group-id", default=None, help="Only the hits of this group.")
@click.option("--hit-id", default=None, help="Only this hit (the other filters are not applied).")
@click.option("--include-test", is_flag=True, default=False, help="Also list synthetic test-fire hits.")
@_page_options
@pass_context
def list_hits(ctx, since, until, layer, template, policy, sid, classification, event_types, drop_id, mode,
              auto_response_outcomes, case_group_key, group_, group_id, hit_id, include_test,
              page_token, page_size) -> None:
    """Recorded hits (or hit groups), newest first."""
    validate_epoch_seconds(since, "since")
    validate_epoch_seconds(until, "until")
    _out(ctx, "groups" if group_ else "hits", _get_dec(ctx).list_hits(
        since=since, until=until, layer=layer, template=template, policy=policy, sid=sid,
        classification=classification, event_types=list(event_types), drop_id=drop_id,
        include_test=include_test, mode=mode, group=group_, group_id=group_id,
        auto_response_outcomes=list(auto_response_outcomes), case_group_key=case_group_key,
        hit_id=hit_id, page_token=page_token, page_size=page_size,
    ))


@group.command("list-readers")
@click.option("--days", type=click.IntRange(min=1, max=90), default=None, help="The window (default 30, at most 90).")
@click.option("--policy", default=None, help="Only this policy's decoys.")
@click.option("--template", default=None, help="Only this template's decoys.")
@click.option("--platform", type=click.Choice(PLATFORMS), default=None, help="Only this platform.")
@_page_options
@pass_context
def list_readers(ctx, days, policy, template, platform, page_token, page_size) -> None:
    """Who reads the decoys, and the allowlist entry that would approve them."""
    _out(ctx, "readers", _get_dec(ctx).list_readers(
        days=days, policy=policy, template=template, platform=platform,
        page_token=page_token, page_size=page_size,
    ))


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

@group.command("uninstall")
@click.option("--force", is_flag=True, default=False,
              help="Finish although decoys remain on offline sensors (they stay on disk, inert).")
@click.option("--cancel", is_flag=True, default=False, help="Abandon the uninstall (no --confirm needed).")
@click.option("--confirm", is_flag=True, default=False, help="Confirm starting or advancing the uninstall.")
@pass_context
def uninstall(ctx, force, cancel, confirm) -> None:
    """Remove everything the extension put in this org, before unsubscribing."""
    if force and cancel:
        raise click.UsageError("--force and --cancel are mutually exclusive.")
    if not cancel:
        _require_confirm(confirm)
    _out(ctx, None, _get_dec(ctx).uninstall(force=force, cancel=cancel))


@group.command("uninstall-status")
@pass_context
def uninstall_status(ctx) -> None:
    """Where an uninstall stands (read-only)."""
    _out(ctx, None, _get_dec(ctx).uninstall_status())


# ---------------------------------------------------------------------------
# drops
# ---------------------------------------------------------------------------

@drops_group.command("create")
@click.option("--form", type=click.Choice(DROP_FORMS), required=True, help="url, qr, hostname or document.")
@click.option("--label", required=True, help="Where the drop is put (at most 128 characters).")
@click.option("--memo", default=None, help="Notes for the analyst (at most 1024 characters).")
@click.option("--format", "format_", type=click.Choice(DOCUMENT_FORMATS), default=None,
              help="Document drops: docx or svg.")
@click.option("--domain", default=None, help="One of the deployment's decoy domains (default: the first).")
@click.option("--mode", type=click.Choice(["live", "observe"]), default=None, help="live (default) or observe.")
@click.option("--observe-until", default=None, help="RFC 3339 time the drop goes live by itself.")
@click.option("--redirect-url", default=None, help="url and qr drops: where a visitor is sent after the hit.")
@_document_options
@_save_option
@pass_context
def drops_create(ctx, form, label, memo, format_, domain, mode, observe_until, redirect_url,
                 file_name, title, lines, link_text, author, document_file, save_path) -> None:
    """Make a drop and print what to paste."""
    if save_path and form in ("url", "hostname"):
        # Refused before the drop is made: a failure after it would invite a
        # retry that makes a second drop.
        raise click.UsageError("--save needs --form qr or document: url and hostname drops have no file.")
    document = _document(document_file, file_name, title, lines, link_text, author)
    result = _get_dec(ctx).create_drop(
        form, label, memo=memo, format=format_, domain=domain, mode=mode,
        observe_until=observe_until, redirect_url=redirect_url, document=document,
    )
    _output_and_save(ctx, result, save_path)


@drops_group.command("list")
@click.option("--form", "forms", multiple=True, type=click.Choice(DROP_FORMS), help="Only this form (repeatable).")
@click.option("--state", "states", multiple=True, type=click.Choice(["active", "disabled", "deleted"]),
              help="Only this state (repeatable; default active and disabled).")
@click.option("--text", default=None, help="Label or memo contains this.")
@click.option("--name", default=None, help="Only the drop of this configuration name.")
@click.option("--managed-by", type=click.Choice(["config", "api"]), default=None,
              help="config (declared in the configuration) or api (made with create).")
@click.option("--last-hit", type=click.Choice(["never", "since", "not_since"]), default=None,
              help="never, since or not_since (with --last-hit-since).")
@click.option("--last-hit-since", default=None, help="RFC 3339 time for --last-hit since and not_since.")
@click.option("--sort", type=click.Choice(["created", "last_hit"]), default=None, help="created (default) or last_hit.")
@click.option("--include-test", is_flag=True, default=False, help="Also list the hidden test drops.")
@_page_options
@pass_context
def drops_list(ctx, forms, states, text, name, managed_by, last_hit, last_hit_since, sort,
               include_test, page_token, page_size) -> None:
    """List drops (never their secret values)."""
    _out(ctx, "drops", _get_dec(ctx).list_drops(
        forms=list(forms), states=list(states), text=text, include_test=include_test, name=name,
        managed_by=managed_by, last_hit=last_hit, last_hit_since=last_hit_since, sort=sort,
        page_token=page_token, page_size=page_size,
    ))


@drops_group.command("get")
@click.option("--drop-id", default=None, help="The drop's id.")
@click.option("--name", default=None, help="Or the configuration name of a declared drop.")
@_save_option
@pass_context
def drops_get(ctx, drop_id, name, save_path) -> None:
    """One drop, with what to paste."""
    if bool(drop_id) == bool(name):
        raise click.UsageError("Give exactly one of --drop-id and --name.")
    _output_and_save(ctx, _get_dec(ctx).get_drop(drop_id=drop_id, name=name), save_path)


@drops_group.command("update")
@click.option("--drop-id", required=True, help="The drop's id.")
@click.option("--version", type=int, default=None,
              help="The version read with the drop (default: the current version, read first).")
@click.option("--label", default=None, help="New label.")
@click.option("--memo", default=None, help="New memo.")
@click.option("--state", type=click.Choice(["active", "disabled"]), default=None, help="active or disabled.")
@click.option("--mode", type=click.Choice(["live", "observe"]), default=None, help="live or observe.")
@click.option("--observe-until", default=None, help='RFC 3339 time; "" clears it.')
@click.option("--redirect-url", default=None, help='A public https URL; "" removes the redirect.')
@_document_options
@click.option("--reset-document", is_flag=True, default=False,
              help="Make the whole document generated again (not with the document fields).")
@pass_context
def drops_update(ctx, drop_id, version, label, memo, state, mode, observe_until, redirect_url,
                 file_name, title, lines, link_text, author, document_file, reset_document) -> None:
    """Change a drop's label, memo, state, mode, redirect or document."""
    document = _document(document_file, file_name, title, lines, link_text, author)
    if reset_document:
        if document is not None:
            raise click.UsageError("--reset-document cannot be combined with document fields.")
        document = {}
    _out(ctx, None, _get_dec(ctx).update_drop(
        drop_id, version, label=label, memo=memo, state=state, mode=mode,
        observe_until=observe_until, redirect_url=redirect_url, document=document,
    ))


@drops_group.command("rotate")
@click.option("--drop-id", required=True, help="The drop's id.")
@click.option("--version", type=int, default=None,
              help="The version read with the drop (default: the current version, read first).")
@_save_option
@pass_context
def drops_rotate(ctx, drop_id, version, save_path) -> None:
    """Give a drop a new value to paste (the old one alerts 90 more days)."""
    _output_and_save(ctx, _get_dec(ctx).rotate_drop(drop_id, version), save_path)


@drops_group.command("delete")
@click.option("--drop-id", required=True, help="The drop's id.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm the deletion (required).")
@pass_context
def drops_delete(ctx, drop_id, confirm) -> None:
    """Stop a drop's alerts for good."""
    _require_confirm(confirm)
    _out(ctx, None, _get_dec(ctx).delete_drop(drop_id))


@drops_group.command("draft-document")
@click.option("--format", "format_", type=click.Choice(DOCUMENT_FORMATS), required=True, help="docx or svg.")
@_document_options
@pass_context
def drops_draft_document(ctx, format_, file_name, title, lines, link_text, author, document_file) -> None:
    """The content a document drop would be generated with (read-only)."""
    document = _document(document_file, file_name, title, lines, link_text, author)
    _out(ctx, None, _get_dec(ctx).draft_drop_document(format_, document))
