"""Investigation Engine commands for LimaCharlie CLI v2.

``limacharlie investigate ...`` builds, tests and tunes investigation
templates and runs investigations with the Investigation Engine, so a person
or an AI agent can drive the whole loop from a terminal:

  kit -> draft -> validate -> test on past alerts -> refine -> save a DRAFT
  -> a person promotes it.

Output is the engine's own JSON by default when piped (``--output`` selects
another format). Failures carry the engine's coded issues verbatim.
"""

from __future__ import annotations

import functools
import json
import sys
from typing import Any, Callable

import click

from ..cli import pass_context
from ..client import Client
from ..discovery import register_explain
from ..output import detect_output_format, format_output
from ..errors import LimaCharlieError
from ..sdk.investigation import (
    KIT_SECTIONS,
    MAX_POLL_WAIT,
    Investigation,
    InvestigationError,
    parse_document,
)
from ..sdk.organization import Organization
from ._output_helpers import command_output, note

# Exit code of a result that is well-formed but says "no" (invalid template,
# refused save): the same code as the CLI's validation errors.
EXIT_REFUSED = 4

_STRUCTURED = ("json", "yaml", "toon", "jsonl")


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_GROUP = """\
Build, test and tune investigation templates, and run investigations, with
the Investigation Engine (experimental; it must be enabled for your
deployment and organization).

AI agent workflow for a new template (a person promotes it at the end):

  1. limacharlie investigate kit --section guide --section schema --section codes
  2. look at real data (detection get, search run, investigate wave ...)
  3. write the template YAML
  4. limacharlie investigate templates validate --file plan.yaml
  5. limacharlie investigate templates test --file plan.yaml --detect-cat <category> --last 10
  6. refine from the disagreements and unknowns, repeat 4-5
  7. limacharlie investigate templates save my-plan --file plan.yaml --comment "<what you tested>"
     (always a DRAFT; a draft runs only through a test or a run a person starts)
  8. a person reviews it and runs: limacharlie investigate templates promote my-plan --confirm

Questions without a template: use `investigate packs` then `investigate wave`.

Permissions: reads need investigation.get + insight.evt.get, writes (start,
wave, test, cancel, delete, decide) investigation.set + insight.evt.get, pause/resume
org.conf.set, template records investigation_plan.get/.set/.del.
"""

_EXPLAIN_KIT = """\
Fetch the authoring kit: template JSON Schema, the authoring guide, the
org's typed operator catalogue, examples, effective policy and budgets, every
validation code with its fix, the fact packs, and (when the engine has it) the
default template library.

The whole kit is about 33k tokens. Fetch it in parts with --section
(repeatable): start with guide, policy, codes, then schema and library. The
`size` entry of the answer says what was returned.

Examples:
  limacharlie investigate kit --section guide --section policy --section codes
  limacharlie investigate kit --section library
"""

_EXPLAIN_OPERATORS = """\
List the operators a template can call, with typed arguments and the shape of
the fact each produces, and whether this org may use it. --brief keeps only
name, class, description and availability; then ask again with --name for the
full rows of the operators you will use.

Examples:
  limacharlie investigate operators --brief
  limacharlie investigate operators --name ioc.prevalence --name entity.get
  limacharlie investigate operators --match search
"""

_EXPLAIN_PACKS = """\
List the fact packs a template or a wave can `use`: named, tested bundles of
facts (host context, hash spread, ...) with their parameters and exports.
--brief is the compact index (name, brief, params, exports); it is enough to
write waves.

Examples:
  limacharlie investigate packs --brief
  limacharlie investigate packs --name host_context
"""

_EXPLAIN_TEMPLATES_LIST = """\
List the templates the engine serves for this org (its investigation_plan
records): name, version, description, applies_to and status (draft or
active). Use it to see what exists and to pick a free name.

Example:
  limacharlie investigate templates list --status draft
"""

_EXPLAIN_TEMPLATES_GET = """\
Read a stored template record. By default the record is returned as a
document with status, etag, tags and comment; --yaml prints only the template
source, ready to edit and validate again.

Examples:
  limacharlie investigate templates get my-plan
  limacharlie investigate templates get my-plan --yaml > plan.yaml
"""

_EXPLAIN_TEMPLATES_VALIDATE = """\
Check a template (YAML file, or - for stdin) without running anything:
structure, operator names and arguments, every $reference and expression
against the operators' typed outputs, dependency cycles and the org's budgets.

The report has `valid`, `errors` and `warnings`, each {code, path, message,
suggestion?}, the worst-case step count and an `estimate`. Fix every error and
read every warning. Exit code is 0 when valid and 4 when not.

Example:
  limacharlie investigate templates validate --file plan.yaml
"""

_EXPLAIN_TEMPLATES_TEST = """\
Dry-run a template on REAL past alerts and report how it did. The plan's
read-only operators run with your own token on each sample; nothing is written
(no run, case, label or action). Response steps that would run are only listed
in `would_propose`.

Samples (at most 25 after expansion): --detection-id ID, --case-id ID,
--detect-cat CATEGORY with --last N (newest N alerts of the category), or
--sample '{"inputs": {...}, "expected": "false_positive"}'. A sample whose case
is closed is judged against the case's classification: `agreement` is agree,
disagree, undecided or none, and summary.agreement_rate is the share that
agreed. Use 5-10 samples of the category, with known false AND true positives.

Read the result in this order: `validation` (state `invalid`: fix the
template), `summary`, each `disagree`, then `undecided` samples (`unknowns` says
which fact could not be resolved and why). Steps that succeeded are left out
unless --include-steps.

The call waits for the test (default up to 600 s, --timeout). A test that is
still running prints its test_id: continue with --test-id ID. A test counts
against the org's concurrent run cap and may bill LLM steps.

Examples:
  limacharlie investigate templates test --file plan.yaml --detect-cat my-category --last 10
  limacharlie investigate templates test my-plan --detection-id <ID> --case-id <ID>
  limacharlie investigate templates test --test-id test-173...-ab12 --timeout 120
"""

_EXPLAIN_TEMPLATES_SAVE = """\
Validate a template and write it as the investigation_plan record NAME.

The record is ALWAYS a draft unless a person passes --status active. A source
that says `status: active` is refused. Nothing is written when validation has
errors, when the record exists and --overwrite is missing, or when the record
is active and the new one is a draft (a draft never replaces an active
template: save under a new name). A draft never runs on its own: it runs only
through `templates test` or a run a person starts, with autonomy capped at
`suggest`. Put what you tested in --comment so the reviewer sees it.

Examples:
  limacharlie investigate templates save my-plan --file plan.yaml --comment "10 samples, 9 agree, 0 unknown"
  limacharlie investigate templates save my-plan --file plan.yaml --overwrite
"""

_EXPLAIN_TEMPLATES_PROMOTE = """\
Make a stored draft template ACTIVE, so D&R rules and cases can run it on
their own. This is a person's decision: review the draft and its test
results first. AI agents must not run it. The stored template is validated
again and the write is conditional on the version that was read. Requires
--confirm.

Example:
  limacharlie investigate templates promote my-plan --confirm
"""

_EXPLAIN_TEMPLATES_DELETE = """\
Delete a template record. Runs already started keep running on the version
they began with. Requires --confirm.

Example:
  limacharlie investigate templates delete my-plan --confirm
"""

_EXPLAIN_TEMPLATES_INSTALL = """\
Write the engine's default template library to this org's investigation_plan
records. An org has only the templates it has installed.

Existing records are NEVER overwritten silently: they are skipped (with the
installed and library versions, so you can see an update is available) unless
--overwrite is given, and an active record is replaced only with
--status active --overwrite. Library templates are installed as DRAFTS by
default whatever status they are written with; a person promotes them or
re-runs with --status active. The result lists what was written, skipped and
failed.

Needs a engine version whose authoring kit has the `library` section.

Examples:
  limacharlie investigate templates install-defaults
  limacharlie investigate templates install-defaults --name mailsec-suspicious-message
"""

_EXPLAIN_RUNS_START = """\
Start an investigation run: the engine gathers facts with its operators,
weighs them and reaches a verdict (true_positive, false_positive or
inconclusive) with a proof.

Pick the plan with --template NAME, --file plan.yaml (an inline draft) or
--auto (the engine picks the active template whose applies_to matches the
trigger: detect_cat, severity, tag and source, the first three from --category,
--severity and --tag; a draft is never picked, and no match is refused with the
reason). Say what to investigate with --detection-id, --case-id, --entity-id or
--question. --urgency (low, medium, high, critical) defaults to a value derived
from --priority and --severity, else medium. A
draft template runs with autonomy capped at suggest; an active one acts as
the org's policy says (response actions may wait for a person's approval).
--idempotency-key makes a repeated start return the same run.

With --wait N the call blocks up to N seconds for the verdict; --follow then
streams the run's events until it ends. With --follow in a structured output
format stdout is JSON lines: the first line is the start answer ({"run": ...,
"joined": ...}), the following lines are events ({"seq": ..., "type": ...}).

Examples:
  limacharlie investigate runs start --template my-plan --detection-id <ID>
  limacharlie investigate runs start --auto --case-id 42 --category my-category --wait 30
"""

_EXPLAIN_RUNS_GET = """\
Read a run: state, phase, verdict, actions and usage.

Example:
  limacharlie investigate runs get <RUN_ID>
"""

_EXPLAIN_RUNS_LIST = """\
List the org's runs, newest first. Filters stack as AND. One page is returned
with --limit; continue with --cursor from the previous page's next_cursor, or
use --all to follow every page.

Examples:
  limacharlie investigate runs list --state running
  limacharlie investigate runs list --template my-plan --verdict false_positive --limit 50
"""

_EXPLAIN_RUNS_EVENTS = """\
Read a run's events (structure only, never customer values). Without --follow
one poll is made after --after. With --follow the CLI keeps polling until the
run is over, writing one JSON event per line (or one text line in table
mode). It ends with exit code 0 when the run finished and 1 when --timeout
elapsed first; resume with --after N (printed on stderr).

Examples:
  limacharlie investigate runs events <RUN_ID> --follow
  limacharlie investigate runs events <RUN_ID> --after 12 --wait 10
"""

_EXPLAIN_RUNS_STEPS = """\
Read a run's step log, plan graph, usage and belief curve. --values includes
customer values (default: structure only).
"""

_EXPLAIN_RUNS_CASE = """\
Read the case document a run wrote (404 until the run has one).
"""

_EXPLAIN_RUNS_CANCEL = """\
Cancel a run. --revert-leases also reverts the leases of its active actions.

Example:
  limacharlie investigate runs cancel <RUN_ID>
"""

_EXPLAIN_RUNS_DELETE = """\
Delete a run. Requires investigation.set + insight.evt.get and --confirm. The request is sent
once; a gateway timeout is not automatically retried.

Example:
  limacharlie investigate runs delete <RUN_ID> --confirm
"""

_EXPLAIN_WAVE = """\
Hand the engine a batch of questions at once and get compact, typed answers.
The engine runs every ready step in parallel with YOUR token (no template, no
verdict, nothing stored), reuses what it already knows, and can stop as soon
as the answer is known.

The file (YAML or JSON) holds the wave:

  steps:
    - {id: host, use: host_context, args: {sid: "<SID>"}}
    - {id: prev, op: ioc.prevalence, args: {file_hash: "<SHA256>"}, select: [hosts_30d]}
  stop_when: ["prev.hosts_30d >= 50"]
  deadline_ms: 20000

Each step has an id and exactly one of `op` (an operator) or `use` (a fact
pack, see `investigate packs`). `select` names the fields to return, `limit`
caps list elements. A string argument that is a whole reference
("$host__resolve.entity_id") reads another step. Flags override the file:
--stop-when (repeatable), --deadline-ms, --full, --validate-only, --input.

A step that is `unknown` or not `complete` established nothing: it is never an
absence. --validate-only checks the wave and runs nothing. An invalid wave
prints the engine's coded errors on stdout and exits 4.

Examples:
  limacharlie investigate wave --file wave.yaml --validate-only
  limacharlie investigate wave --file wave.yaml
"""

_EXPLAIN_ACTIONS_LIST = """\
List the org's actions across all runs: the approvals inbox. What needs a
person (awaiting_approval, proposed, uncertain) comes first. --state takes a
state or a comma separated list.

Examples:
  limacharlie investigate actions list --state awaiting_approval
"""

_EXPLAIN_ACTIONS_APPROVE = """\
Approve an action a run proposed. You also need the permission of the
action's class (for example sensor.task for a containment action). Approving
executes it.

Example:
  limacharlie investigate actions approve <RUN_ID> <ACTION_ID>
"""

_EXPLAIN_ACTIONS_DENY = """\
Deny an action a run proposed, with an optional note.

Example:
  limacharlie investigate actions deny <RUN_ID> <ACTION_ID> --note "known admin activity"
"""

_EXPLAIN_POLICY_GET = """\
Explain the effective policy: budgets, the operators and extension requests
that are denied, and the autonomy mode of each action class, optionally for
an alert shape (--category, --priority, --severity, --target-tag, --class).
"""

_EXPLAIN_POLICY_STATUS = """\
Whether automatic actions are paused for the org, and who last flipped the switch.
"""

_EXPLAIN_POLICY_PAUSE = """\
Pause automatic actions for the whole org (the kill switch). Needs org.conf.set.
"""

_EXPLAIN_POLICY_RESUME = """\
Resume automatic actions for the org. Needs org.conf.set.
"""

for _path, _text in {
    "investigate": _EXPLAIN_GROUP,
    "investigate.kit": _EXPLAIN_KIT,
    "investigate.operators": _EXPLAIN_OPERATORS,
    "investigate.packs": _EXPLAIN_PACKS,
    "investigate.templates.list": _EXPLAIN_TEMPLATES_LIST,
    "investigate.templates.get": _EXPLAIN_TEMPLATES_GET,
    "investigate.templates.validate": _EXPLAIN_TEMPLATES_VALIDATE,
    "investigate.templates.test": _EXPLAIN_TEMPLATES_TEST,
    "investigate.templates.save": _EXPLAIN_TEMPLATES_SAVE,
    "investigate.templates.promote": _EXPLAIN_TEMPLATES_PROMOTE,
    "investigate.templates.delete": _EXPLAIN_TEMPLATES_DELETE,
    "investigate.templates.install-defaults": _EXPLAIN_TEMPLATES_INSTALL,
    "investigate.runs.start": _EXPLAIN_RUNS_START,
    "investigate.runs.get": _EXPLAIN_RUNS_GET,
    "investigate.runs.list": _EXPLAIN_RUNS_LIST,
    "investigate.runs.events": _EXPLAIN_RUNS_EVENTS,
    "investigate.runs.steps": _EXPLAIN_RUNS_STEPS,
    "investigate.runs.case": _EXPLAIN_RUNS_CASE,
    "investigate.runs.cancel": _EXPLAIN_RUNS_CANCEL,
    "investigate.runs.delete": _EXPLAIN_RUNS_DELETE,
    "investigate.wave": _EXPLAIN_WAVE,
    "investigate.actions.list": _EXPLAIN_ACTIONS_LIST,
    "investigate.actions.approve": _EXPLAIN_ACTIONS_APPROVE,
    "investigate.actions.deny": _EXPLAIN_ACTIONS_DENY,
    "investigate.policy.get": _EXPLAIN_POLICY_GET,
    "investigate.policy.status": _EXPLAIN_POLICY_STATUS,
    "investigate.policy.pause": _EXPLAIN_POLICY_PAUSE,
    "investigate.policy.resume": _EXPLAIN_POLICY_RESUME,
}.items():
    register_explain(_path, _text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_investigation(ctx: click.Context) -> Investigation:
    client = Client(
        oid=ctx.obj.oid,
        environment=ctx.obj.environment,
        print_debug_fn=ctx.obj.debug_fn,
        debug_full_response=ctx.obj.debug_full,
        debug_curl=ctx.obj.debug_curl,
        debug_verbose=ctx.obj.debug_verbose,
    )
    return Investigation(Organization(client))


def _fmt(ctx: click.Context) -> str:
    return ctx.obj.output_format or detect_output_format()


def _error_document(exc: LimaCharlieError) -> dict[str, Any]:
    """The machine-readable form of any SDK failure.

    An engine failure keeps the engine's own answer. Any other failure (a Hive
    or API error, bad input) carries its message, HTTP status, the backend's
    ``error_code`` (the ``lc_error_code`` of a Hive answer) and suggestion.
    """
    if isinstance(exc, InvestigationError):
        return exc.to_dict()
    out: dict[str, Any] = {"error": exc.raw_message, "status": exc.status_code}
    code = getattr(exc, "error_code", None)
    if code:
        out["error_code"] = code
    if exc.suggestion:
        out["suggestion"] = exc.suggestion
    return out


def _engine_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Report a failure as a document when the output is machine-read.

    In a structured output format every SDK failure (the engine's, a Hive or
    API error, a refused input) is written to stderr as a document (message,
    ``error_code``, coded ``errors`` and ``warnings`` when the engine sent
    them) and the command exits with the error's exit code. In table mode the
    error propagates and prints as text, issues included.
    """
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except LimaCharlieError as exc:
            ctx = click.get_current_context()
            if _fmt(ctx) not in _STRUCTURED:
                raise
            click.echo(format_output(_error_document(exc), _fmt(ctx)), err=True)
            ctx.exit(exc.exit_code or 1)
    return wrapper


def _input_error(hint: str, message: str) -> InvestigationError:
    """A refused input, as a coded error (``invalid_input``) that renders as JSON when asked."""
    return InvestigationError(
        f"{hint}: {message}", status_code=None, exit_code=EXIT_REFUSED,
        issues=[{"code": "invalid_input", "path": hint, "message": message}],
    )


def _load_document(path: str, hint: str) -> Any:
    """Read a YAML or JSON file; unquoted scalars are read as the engine reads them (``off`` is text, ``012`` is 10)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        raise _input_error(hint, f"cannot read file: {exc}") from exc
    try:
        return parse_document(content, "the file")
    except LimaCharlieError as exc:
        raise _input_error(hint, exc.raw_message) from exc


def _read_source(path: str) -> str:
    """Read a template file, or stdin for ``-``."""
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        raise _input_error("--file", f"cannot read file: {exc}") from exc


def _parse_kv(pairs: tuple[str, ...], hint: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise _input_error(hint, f"expected KEY=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        out[key] = value
    return out


def _reject_constant(name: str) -> Any:
    """``json.loads`` hook: Python reads NaN and Infinity, but JSON (and the engine) has no such numbers."""
    raise ValueError(f"{name} is not a JSON number")


def _json_object(text: str | None, hint: str) -> dict[str, Any] | None:
    if text is None:
        return None
    try:
        value = json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:  # JSONDecodeError is one; so is a refused NaN/Infinity
        raise _input_error(hint, f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise _input_error(hint, "must be a JSON object")
    return value


def _label(verdict: Any) -> Any:
    return verdict.get("label") if isinstance(verdict, dict) else verdict


def _emit_page(ctx: click.Context, key: str, items: list[Any], next_cursor: str, project: Callable[[Any], Any]) -> None:
    """Print one page of a listing, the way hive listings are printed.

    Structured formats carry ``{key: [...], next_cursor}``. Table, CSV and
    JSONL print the (projected) rows and put the cursor on stderr, since they
    have nowhere to carry it.
    """
    fmt = _fmt(ctx)
    if fmt in ("json", "yaml", "toon"):
        command_output(ctx, {key: items, "next_cursor": next_cursor or ""})
        return
    command_output(ctx, [project(i) for i in items] if fmt in ("table", "csv") else items)
    if next_cursor:
        note(ctx, f"next_cursor: {next_cursor}")


def _run_row(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("run_id"),
        "state": run.get("state"),
        "template": run.get("template"),
        "verdict": _label(run.get("verdict")),
        "urgency": run.get("urgency"),
        "created": run.get("created"),
        "started_by": (run.get("started_by") or {}).get("actor") if isinstance(run.get("started_by"), dict) else None,
    }


def _action_row(action: dict[str, Any]) -> dict[str, Any]:
    run = action.get("run") or {}
    return {
        "run_id": action.get("run_id"),
        "id": action.get("id"),
        "class": action.get("class"),
        "state": action.get("state"),
        "mode": action.get("mode"),
        "template": run.get("template"),
        "verdict": _label(run.get("verdict")),
    }


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("investigate")
def group() -> None:
    """Investigation Engine: build and test investigation templates, run investigations (experimental)."""


@group.command("kit")
@click.option("--section", "sections", multiple=True, type=click.Choice(KIT_SECTIONS),
              help="Section to fetch (repeatable). Default: everything but 'library'; the whole kit is ~33k tokens.")
@pass_context
@_engine_errors
def kit_cmd(ctx, sections) -> None:
    """Fetch the authoring kit: schema, guide, operators, examples, policy, codes, packs, library."""
    command_output(ctx, _get_investigation(ctx).get_authoring_kit(list(sections) or None))


@group.command("operators")
@click.option("--match", "match", default=None, help="Keep operators whose name, class or description contains this text.")
@click.option("--name", "names", multiple=True, help="Keep only this operator (repeatable): its full row.")
@click.option("--brief", is_flag=True, default=False, help="Only name, class, description, available and why.")
@pass_context
@_engine_errors
def operators_cmd(ctx, match, names, brief) -> None:
    """List the typed operator catalogue."""
    data = _get_investigation(ctx).list_operators()
    rows = [o for o in data.get("operators") or [] if isinstance(o, dict)]
    if names:
        rows = [o for o in rows if o.get("name") in names]
    if match:
        needle = match.lower()
        rows = [o for o in rows if any(needle in str(o.get(k, "")).lower() for k in ("name", "class", "description"))]
    if brief:
        rows = [{k: o.get(k) for k in ("name", "class", "description", "available", "why")} for o in rows]
    command_output(ctx, rows if _fmt(ctx) in ("table", "csv", "jsonl") else {"operators": rows, "extension_requests": data.get("extension_requests", [])})


@group.command("packs")
@click.option("--name", default=None, help="Only this pack.")
@click.option("--brief", is_flag=True, default=False, help="The compact index: name, brief, params, exports.")
@pass_context
@_engine_errors
def packs_cmd(ctx, name, brief) -> None:
    """List the fact packs a template or a wave can use."""
    data = _get_investigation(ctx).list_packs(name)
    packs = [p for p in data.get("packs") or [] if isinstance(p, dict)]
    if brief:
        packs = [
            {
                "name": p.get("name"),
                "brief": p.get("brief"),
                "params": [{k: x.get(k) for k in ("name", "type", "required") if k in x} for x in p.get("params") or []],
                "exports": [{k: x.get(k) for k in ("name", "type", "ref", "brief") if k in x} for x in p.get("exports") or []],
            }
            for p in packs
        ]
    command_output(ctx, packs if _fmt(ctx) in ("table", "csv", "jsonl") else {"packs": packs})


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------

@group.group("templates")
def templates_group() -> None:
    """Investigation templates: list, get, validate, test, save (draft), promote, delete."""


@templates_group.command("list")
@click.option("--status", type=click.Choice(["draft", "active"]), default=None, help="Only templates with this status.")
@pass_context
@_engine_errors
def templates_list(ctx, status) -> None:
    """List the templates the engine serves for this org."""
    data = _get_investigation(ctx).list_engine_templates()
    rows = [t for t in data.get("templates") or [] if isinstance(t, dict)]
    if status:
        rows = [t for t in rows if (t.get("status") or "draft") == status]
    command_output(ctx, rows if _fmt(ctx) in ("table", "csv", "jsonl") else {"templates": rows})


@templates_group.command("get")
@click.argument("name")
@click.option("--yaml", "yaml_only", is_flag=True, default=False, help="Print only the template source.")
@pass_context
@_engine_errors
def templates_get(ctx, name, yaml_only) -> None:
    """Read a stored template record."""
    view = _get_investigation(ctx).get_template(name)
    if yaml_only:
        click.echo(view["yaml"], nl=False)
        return
    command_output(ctx, view)


def _file_option(fn: Callable[..., Any]) -> Callable[..., Any]:
    return click.option("--file", "-f", "file_path", default=None, help="Template YAML file ('-' for stdin).")(fn)


@templates_group.command("validate")
@_file_option
@pass_context
@_engine_errors
def templates_validate(ctx, file_path) -> None:
    """Check a template without running anything (exit 4 when it has errors)."""
    if not file_path:
        raise click.UsageError("--file is required.")
    report = _get_investigation(ctx).validate_plan(_read_source(file_path))
    command_output(ctx, report)
    if report.get("valid") is not True or report.get("errors"):
        ctx.exit(EXIT_REFUSED)


def _step_diagnostics(steps):
    return [
        {k: step[k] for k in ("fact", "op", "status", "complete", "reason", "message", "counts", "judgement") if k in step}
        for step in (steps or []) if isinstance(step, dict) and any(k in step for k in ("complete", "counts", "judgement"))
    ]


def _test_cost(value):
    # A response without a cost object (an older service) has no known cost: show it blank, never as 0 (free).
    cost = value if isinstance(value, dict) else {}
    usd = cost.get("llm_usd")
    if cost.get("llm_unpriced"):
        return f"{usd if usd is not None else 0} (unpriced)"
    return usd


def _compact_test(test: dict[str, Any], include_steps: bool) -> dict[str, Any]:
    """Keep safe decision diagnostics even when full step timing is omitted."""
    if include_steps or not isinstance(test.get("results"), list):
        return test
    out = dict(test)
    results = []
    for r in test["results"]:
        if not isinstance(r, dict) or not isinstance(r.get("steps"), list):
            results.append(r)
            continue
        r = dict(r)
        steps = r.pop("steps")
        r["problem_steps"] = [s for s in steps if isinstance(s, dict) and s.get("status") != "ok"]
        r["step_diagnostics"] = _step_diagnostics(steps)
        r["steps_total"] = len(steps)
        results.append(r)
    out["results"] = results
    return out


def _test_rows(test: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for r in test.get("results") or []:
        if not isinstance(r, dict):
            continue
        verdict = r.get("verdict") or {}
        rows.append({
            "index": r.get("index"),
            "sample": json.dumps(r.get("sample") or {}, separators=(",", ":")),
            "state": r.get("state"),
            "verdict": verdict.get("label") if isinstance(verdict, dict) else verdict,
            "p": verdict.get("p") if isinstance(verdict, dict) else None,
            "expected": (r.get("expected") or {}).get("label") if isinstance(r.get("expected"), dict) else None,
            "agreement": r.get("agreement"),
            "unknowns": len(r.get("unknowns") or []),
            "wall_ms": r.get("wall_ms"),
            "prior": verdict.get("prior") if isinstance(verdict, dict) else None,
            "decided": verdict.get("decided") if isinstance(verdict, dict) else None,
            "evidence": json.dumps(verdict.get("evidence") or [], separators=(",", ":")) if isinstance(verdict, dict) else None,
            "llm_cost": _test_cost(r.get("cost")),
            "step_diagnostics": json.dumps(_step_diagnostics(r.get("steps")), separators=(",", ":")),
        })
    return rows


def _print_test(ctx: click.Context, test: dict[str, Any], include_steps: bool) -> None:
    if _fmt(ctx) not in ("table", "csv"):
        command_output(ctx, _compact_test(test, include_steps))
        return
    header = f"test {test.get('test_id')}: {test.get('state')}"
    if "samples_done" in test:
        header += f" ({test.get('samples_done')}/{test.get('samples_total')} samples)"
    click.echo(header)
    for kind in ("errors", "warnings"):
        for issue in (test.get("validation") or {}).get(kind) or []:
            click.echo(f"  {kind[:-1]}: [{issue.get('code')}] {issue.get('path')}: {issue.get('message')}"
                       + (f" (did you mean {issue['suggestion']})" if issue.get("suggestion") else ""))
    rows = _test_rows(test)
    if rows:
        command_output(ctx, rows)
    summary = test.get("summary")
    if isinstance(summary, dict):
        click.echo("summary: " + ", ".join(f"{k}={summary[k]}" for k in (
            "samples", "ran", "errors", "decided", "undecided", "true_positive", "false_positive", "inconclusive",
            "with_expected", "agree", "disagree", "agreement_rate") if k in summary))
        if isinstance(summary.get("cost"), dict):
            llm_cost = _test_cost(summary["cost"])
            click.echo(f"LLM cost: {'unknown' if llm_cost is None else llm_cost}")
        if summary.get("unknown_reasons"):
            click.echo(f"unknown reasons: {summary['unknown_reasons']}")


@templates_group.command("test")
@click.argument("name", required=False)
@_file_option
@click.option("--test-id", default=None, help="Keep waiting on a test started earlier (replaces NAME, --file and the samples).")
@click.option("--detection-id", "detection_ids", multiple=True, help="Sample: a stored detection (repeatable).")
@click.option("--case-id", "case_ids", multiple=True, help="Sample: a case; its classification is the expected label (repeatable).")
@click.option("--detect-cat", "detect_cats", multiple=True, help="Sample: the newest alerts of this detection category (repeatable; see --last).")
@click.option("--last", type=click.IntRange(1, 25), default=10, show_default=True, help="How many alerts per --detect-cat.")
@click.option("--sample", "samples_json", multiple=True, help="Sample as a JSON object, e.g. '{\"inputs\": {...}, \"expected\": \"false_positive\"}' (repeatable).")
@click.option("--samples-file", default=None, help="YAML/JSON file holding a list of samples.")
@click.option("--mode", type=click.Choice(["triage", "full"]), default=None, help="triage (default for a test, the cheap pass) or full.")
@click.option("--strict", is_flag=True, default=False, help="Refuse the test when --overrides-json would loosen the org's policy (default: the loosening part is ignored and reported in policy.clamped).")
@click.option("--overrides-json", default=None, help="Tighten-only budget overrides, e.g. '{\"budgets\": {\"max_wall_seconds\": 120}}'.")
@click.option("--wait", "wait_seconds", type=click.IntRange(0, MAX_POLL_WAIT), default=5, show_default=True,
              help="Seconds the starting call waits for a fast test.")
@click.option("--timeout", type=click.FloatRange(min=0), default=600, show_default=True, help="Stop waiting for the test after this many seconds.")
@click.option("--no-wait", is_flag=True, default=False, help="Print the test as started (its test_id) and return.")
@click.option("--include-steps", is_flag=True, default=False, help="Keep every step of every sample (large). Default: problem steps and safe completeness, count and judgement diagnostics.")
@pass_context
@_engine_errors
def templates_test(ctx, name, file_path, test_id, detection_ids, case_ids, detect_cats, last, samples_json,
                   samples_file, mode, strict, overrides_json, wait_seconds, timeout, no_wait, include_steps) -> None:
    """Dry-run a template on real past alerts and report agreement."""
    inv = _get_investigation(ctx)
    if test_id:
        if name or file_path:
            raise click.UsageError("--test-id replaces NAME and --file.")
        test = inv.get_test_plan(test_id, wait=min(wait_seconds, MAX_POLL_WAIT))
    else:
        if bool(name) == bool(file_path):
            raise click.UsageError("Give exactly one of a stored template NAME or --file.")
        samples: list[dict[str, Any]] = []
        samples += [{"detection_id": d} for d in detection_ids]
        samples += [{"case_id": c} for c in case_ids]
        samples += [{"detect_cat": c, "last": last} for c in detect_cats]
        for text in samples_json:
            samples.append(_json_object(text, "--sample") or {})
        if samples_file:
            loaded = _load_document(samples_file, "--samples-file")
            if not isinstance(loaded, list) or not all(isinstance(s, dict) for s in loaded):
                raise _input_error("--samples-file", "must be a list of sample objects")
            samples += loaded
        if not samples:
            raise click.UsageError("Give at least one sample: --detection-id, --case-id, --detect-cat, --sample or --samples-file.")
        test = inv.test_plan(
            samples,
            template=name,
            inline=_read_source(file_path) if file_path else None,
            overrides=_json_object(overrides_json, "--overrides-json"),
            strict=strict,
            mode=mode,
            wait_seconds=wait_seconds,
        )
    if not no_wait and not test.get("done") and test.get("state") == "running":
        test = inv.wait_for_test(test, timeout=timeout)
    _print_test(ctx, test, include_steps)
    state = test.get("state")
    if state == "invalid":
        ctx.exit(EXIT_REFUSED)
    if state == "failed":
        ctx.exit(1)
    if state == "running":
        note(ctx, f"test still running; continue with: limacharlie investigate templates test --test-id {test.get('test_id')}")


@templates_group.command("save")
@click.argument("name")
@_file_option
@click.option("--status", type=click.Choice(["draft", "active"]), default="draft", show_default=True,
              help="'active' is for the person who reviewed the template; AI agents must leave it at draft.")
@click.option("--overwrite", is_flag=True, default=False, help="Replace an existing draft (an active one only with --status active).")
@click.option("--comment", default=None, help="What the template was tested on and how it did; stored as the record's comment.")
@click.option("--tag", "tags", multiple=True, help="Tag to add to the record (repeatable).")
@pass_context
@_engine_errors
def templates_save(ctx, name, file_path, status, overwrite, comment, tags) -> None:
    """Validate a template and save it as a DRAFT record (exit 4 when refused)."""
    if not file_path:
        raise click.UsageError("--file is required.")
    result = _get_investigation(ctx).save_template(
        name, _read_source(file_path), status=status, overwrite=overwrite, comment=comment, tags=list(tags) or None,
    )
    command_output(ctx, result)
    if not result.get("saved"):
        ctx.exit(EXIT_REFUSED)


@templates_group.command("promote")
@click.argument("name")
@click.option("--confirm", is_flag=True, default=False, help="Confirm that you reviewed the draft and want it active (required).")
@pass_context
@_engine_errors
def templates_promote(ctx, name, confirm) -> None:
    """Make a reviewed draft ACTIVE (a person's decision)."""
    if not confirm:
        raise click.UsageError("Promoting a template makes it runnable on its own and requires --confirm.")
    result = _get_investigation(ctx).promote_template(name)
    command_output(ctx, result)
    if not result.get("promoted"):
        ctx.exit(EXIT_REFUSED)


@templates_group.command("delete")
@click.argument("name")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
@_engine_errors
def templates_delete(ctx, name, confirm) -> None:
    """Delete a template record."""
    if not confirm:
        raise click.UsageError("Destructive operation requires --confirm flag.")
    result = _get_investigation(ctx).delete_template(name)
    note(ctx, f"Template '{name}' deleted.")
    command_output(ctx, result)


@templates_group.command("install-defaults")
@click.option("--name", "names", multiple=True, help="Install only this library template (repeatable).")
@click.option("--overwrite", is_flag=True, default=False, help="Replace existing records instead of skipping them.")
@click.option("--status", type=click.Choice(["draft", "active"]), default="draft", show_default=True,
              help="Status the templates are written with, whatever the library says.")
@pass_context
@_engine_errors
def templates_install_defaults(ctx, names, overwrite, status) -> None:
    """Write the engine's default template library to this org (never overwrites silently)."""
    result = _get_investigation(ctx).install_default_templates(list(names) or None, overwrite=overwrite, status=status)
    command_output(ctx, result)
    if result["failed"]:
        ctx.exit(1)


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------

@group.group("runs")
def runs_group() -> None:
    """Investigation runs: start, get, list, events, steps, case, cancel, delete."""


@runs_group.command("start")
@click.option("--template", default=None, help="Stored template to run.")
@_file_option
@click.option("--auto", is_flag=True, default=False,
              help="Let the engine pick the active template whose applies_to matches the trigger (sends no plan). "
                   "applies_to keys: detect_cat, severity, tag (set them with --category, --severity, --tag) and source (always api here). "
                   "Refused with a reason when no template matches.")
@click.option("--detection-id", default=None, help="Detection to investigate.")
@click.option("--case-id", default=None, help="Case to investigate.")
@click.option("--entity-id", default=None, help="Entity to investigate.")
@click.option("--question", default=None, help="Free-text question, for a template that takes one.")
@click.option("--category", default=None, help="Detection category of the alert: matched by --auto and by run-scoped policy records.")
@click.option("--severity", default=None, help="Severity of the alert (low, medium, high, critical): matched by --auto and policy records; sets the default urgency.")
@click.option("--priority", type=int, default=None, help="Detection priority: matched by policy records; sets the default urgency (8+ critical, 6+ high, 3+ medium).")
@click.option("--tag", "tags", multiple=True, help="Tag of the alert (repeatable): matched by --auto and by run-scoped policy records.")
@click.option("--input", "inputs", multiple=True, help="Run input KEY=VALUE (repeatable; values are text).")
@click.option("--inputs-json", default=None, help="Run inputs as a JSON object (typed values).")
@click.option("--urgency", type=click.Choice(["low", "medium", "high", "critical"]), default=None,
              help="Run urgency; it picks the decision thresholds. Default: derived from --priority / --severity, else medium.")
@click.option("--mode", type=click.Choice(["triage", "full", "scope"]), default=None, help="Run mode (engine default: full; triage is cheaper).")
@click.option("--case-mode", "case_mode", default=None, help="create, none or attach:<case id> (default: the org's policy, or the template's report.case).")
@click.option("--idempotency-key", default=None, help="Starting twice with the same key returns the same run.")
@click.option("--wait", "wait_seconds", type=click.IntRange(0, 60), default=0, help="Block up to this many seconds for the verdict (this CLI accepts 0..60; the run goes on after it).")
@click.option("--follow", is_flag=True, default=False, help="Then stream the run's events until it ends.")
@pass_context
@_engine_errors
def runs_start(ctx, template, file_path, auto, detection_id, case_id, entity_id, question, category, severity, priority,
               tags, inputs, inputs_json, urgency, mode, case_mode, idempotency_key, wait_seconds, follow) -> None:
    """Start an investigation run on a detection, case, entity or question."""
    if sum(bool(x) for x in (template, file_path, auto)) != 1:
        raise click.UsageError("Give exactly one of --template, --file or --auto.")
    trigger = {k: v for k, v in (("detection_id", detection_id), ("case_id", case_id),
                                 ("entity_id", entity_id), ("question", question)) if v}
    if not trigger:
        raise click.UsageError("Give one of --detection-id, --case-id, --entity-id or --question.")
    # The engine refuses plan.auto for a person's run; a start that names no plan at all is the one it gives the
    # template whose applies_to matches the trigger, so --auto sends no plan.
    for key, value in (("category", category), ("severity", severity), ("priority", priority)):
        if value is not None and value != "":
            trigger[key] = value
    if tags:
        trigger["tags"] = list(tags)
    request: dict[str, Any] = {"trigger": trigger}
    if template:
        request["plan"] = {"template": template}
    elif file_path:
        request["plan"] = {"inline": _read_source(file_path)}
    run_inputs: dict[str, Any] = _parse_kv(inputs, "--input")
    run_inputs.update(_json_object(inputs_json, "--inputs-json") or {})
    if run_inputs:
        request["inputs"] = run_inputs
    for key, value in (("urgency", urgency), ("mode", mode), ("case", case_mode), ("idempotency_key", idempotency_key)):
        if value:
            request[key] = value
    if wait_seconds:
        request["wait_seconds"] = wait_seconds
    inv = _get_investigation(ctx)
    answer = inv.start_run(request)
    if follow and _fmt(ctx) in _STRUCTURED:
        # One compact line, like the events that follow: the stream is JSON lines.
        if not ctx.obj.quiet:
            click.echo(json.dumps(answer, separators=(",", ":"), default=str))
    else:
        command_output(ctx, answer)
    if follow:
        run_id = (answer.get("run") or {}).get("run_id")
        if run_id:
            _follow_events(ctx, inv, run_id, 0, MAX_POLL_WAIT, None, 900)


@runs_group.command("get")
@click.argument("run_id")
@pass_context
@_engine_errors
def runs_get(ctx, run_id) -> None:
    """Read a run: state, phase, verdict, actions and usage."""
    command_output(ctx, _get_investigation(ctx).get_run(run_id))


@runs_group.command("list")
@click.option("--state", default=None, help="Only runs in this state (queued, running, decided, completed, cancelled, failed, budget_exhausted).")
@click.option("--verdict", default=None, help="Only runs with this verdict (true_positive, false_positive, inconclusive, undecided).")
@click.option("--template", default=None, help="Only runs of this template.")
@click.option("--trigger", default=None, help="Only runs started from this kind of trigger (detection, message, entity, case, question).")
@click.option("--entity", default=None, help="Only runs about this entity.")
@click.option("--started-by", default=None, help="Only runs started by this identity (user:<uid>, apikey:<key id>) or, failing that, this name (a user's email, a key's name).")
@click.option("--idempotency-key", default=None, help="Only the run started with this key.")
@click.option("--since", default=None, help="Only runs created at or after this RFC 3339 time.")
@click.option("--until", default=None, help="Only runs created before this RFC 3339 time.")
@click.option("--limit", type=click.IntRange(1, 200), default=None, help="Page size (engine default 50).")
@click.option("--cursor", default=None, help="Continue from the next_cursor of the previous page.")
@click.option("--all", "fetch_all", is_flag=True, default=False, help="Follow every page and print all runs.")
@pass_context
@_engine_errors
def runs_list(ctx, state, verdict, template, trigger, entity, started_by, idempotency_key, since, until, limit, cursor, fetch_all) -> None:
    """List the org's runs, newest first."""
    inv = _get_investigation(ctx)
    filters = dict(state=state, verdict=verdict, template=template, trigger=trigger, entity=entity,
                   started_by=started_by, idempotency_key=idempotency_key, since=since, until=until,
                   limit=limit, cursor=cursor)
    if fetch_all:
        _emit_page(ctx, "runs", list(inv.iter_runs(**filters)), "", _run_row)
        return
    page = inv.list_runs(**filters)
    _emit_page(ctx, "runs", page.get("runs") or [], page.get("next_cursor") or "", _run_row)


def _event_line(event: dict[str, Any]) -> str:
    data = event.get("data")
    return f"{event.get('seq')}\t{event.get('at')}\t{event.get('type')}\t" + (
        json.dumps(data, separators=(",", ":"), default=str) if data else "")


def _follow_events(ctx: click.Context, inv: Investigation, run_id: str, after: int, wait: int,
                   limit: int | None, timeout: float | None) -> None:
    """Stream a run's events until it is over, one per line, flushing as they arrive."""
    state: dict[str, Any] = {}
    structured = _fmt(ctx) in _STRUCTURED
    try:
        for event in inv.iter_run_events(run_id, after=after, wait=wait, limit=limit, timeout=timeout, state=state):
            if ctx.obj.quiet:
                continue
            click.echo(json.dumps(event, separators=(",", ":"), default=str) if structured else _event_line(event))
            sys.stdout.flush()
    except KeyboardInterrupt:
        note(ctx, f"interrupted; resume with --after {state.get('next', after)}")
        ctx.exit(130)
    if state.get("done"):
        return
    note(ctx, f"run not finished after {timeout:g}s; resume with --after {state.get('next', after)}")
    ctx.exit(1)


@runs_group.command("events")
@click.argument("run_id")
@click.option("--after", type=click.IntRange(min=0), default=0, show_default=True, help="Return events after this sequence number.")
@click.option("--wait", type=click.IntRange(0, MAX_POLL_WAIT), default=None, help="Seconds a poll waits for a new event (default 0, or 10 with --follow).")
@click.option("--limit", type=click.IntRange(1, 500), default=None, help="Events per poll.")
@click.option("--follow", is_flag=True, default=False, help="Keep polling until the run is over, printing one event per line.")
@click.option("--timeout", type=click.FloatRange(min=1), default=900, show_default=True, help="With --follow: stop after this many seconds (exit 1).")
@pass_context
@_engine_errors
def runs_events(ctx, run_id, after, wait, limit, follow, timeout) -> None:
    """Read a run's events, or follow them to the end."""
    inv = _get_investigation(ctx)
    if follow:
        _follow_events(ctx, inv, run_id, after, MAX_POLL_WAIT if wait is None else wait, limit, timeout)
        return
    page = inv.get_run_events(run_id, after=after, wait=wait or 0, limit=limit)
    if _fmt(ctx) in ("table", "csv"):
        for event in page.get("events") or []:
            click.echo(_event_line(event))
        note(ctx, f"next: {page.get('next')}  done: {page.get('done')}")
        return
    command_output(ctx, page)


@runs_group.command("steps")
@click.argument("run_id")
@click.option("--values", is_flag=True, default=False, help="Include customer values (default: structure only).")
@pass_context
@_engine_errors
def runs_steps(ctx, run_id, values) -> None:
    """Read a run's step log, plan graph, usage and belief curve."""
    command_output(ctx, _get_investigation(ctx).get_run_steps(run_id, values=values))


@runs_group.command("case")
@click.argument("run_id")
@pass_context
@_engine_errors
def runs_case(ctx, run_id) -> None:
    """Read the case document a run wrote."""
    command_output(ctx, _get_investigation(ctx).get_run_case(run_id))


@runs_group.command("cancel")
@click.argument("run_id")
@click.option("--revert-leases", is_flag=True, default=False, help="Also revert the leases of the run's active actions.")
@pass_context
@_engine_errors
def runs_cancel(ctx, run_id, revert_leases) -> None:
    """Cancel a run."""
    command_output(ctx, _get_investigation(ctx).cancel_run(run_id, revert_leases=revert_leases))


@runs_group.command("delete")
@click.argument("run_id")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@pass_context
@_engine_errors
def runs_delete(ctx, run_id, confirm) -> None:
    """Delete a run (requires --confirm)."""
    if not confirm:
        raise click.UsageError("Destructive operation requires --confirm flag.")
    result = _get_investigation(ctx).delete_run(run_id)
    note(ctx, f"Run '{run_id}' deleted.")
    command_output(ctx, result)


# ---------------------------------------------------------------------------
# wave
# ---------------------------------------------------------------------------

@group.command("wave")
@click.option("--file", "-f", "file_path", required=True, help="Wave file (YAML or JSON): steps, stop_when, deadline_ms, inputs.")
@click.option("--stop-when", "stop_when", multiple=True, help="Add a stop_when expression (repeatable; at most 8 in all).")
@click.option("--deadline-ms", type=click.IntRange(min=1), default=None, help="Wave deadline in milliseconds (engine default 30000).")
@click.option("--input", "inputs", multiple=True, help="Add a named input KEY=VALUE, read by steps as $KEY (repeatable).")
@click.option("--full", is_flag=True, default=False, help="Return raw operator values instead of the compact answer (many more tokens).")
@click.option("--validate-only", is_flag=True, default=False, help="Validate the wave and run nothing.")
@pass_context
@_engine_errors
def wave_cmd(ctx, file_path, stop_when, deadline_ms, inputs, full, validate_only) -> None:
    """Run a batch of operator and fact-pack questions in one call."""
    wave = _load_document(file_path, "--file")
    if isinstance(wave, list):
        wave = {"steps": wave}
    if not isinstance(wave, dict):
        raise _input_error("--file", "must hold a mapping (steps, stop_when, ...) or a list of steps")
    wave = dict(wave)
    if stop_when:
        wave["stop_when"] = list(wave.get("stop_when") or []) + list(stop_when)
    if deadline_ms:
        wave["deadline_ms"] = deadline_ms
    if inputs:
        wave["inputs"] = {**(wave.get("inputs") or {}), **_parse_kv(inputs, "--input")}
    if full:
        wave["full"] = True
    if validate_only:
        wave["validate_only"] = True
    try:
        result = _get_investigation(ctx).run_wave(wave)
    except InvestigationError as exc:
        if not exc.issues:
            raise
        # A refused wave is a result: its coded errors are what the caller needs, on stdout.
        command_output(ctx, {"valid": False, "error": exc.raw_message.split("\n")[0], "errors": exc.issues, "warnings": exc.warnings})
        ctx.exit(EXIT_REFUSED)
    command_output(ctx, result)
    if validate_only and result.get("valid") is False:
        ctx.exit(EXIT_REFUSED)


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------

@group.group("actions")
def actions_group() -> None:
    """The approvals inbox: list pending actions, approve or deny them."""


@actions_group.command("list")
@click.option("--state", default=None, help="An action state or a comma separated list (awaiting_approval, proposed, executing, active, ...). Default: all.")
@click.option("--class", "action_class", default=None, help="Only this action class.")
@click.option("--run-id", default=None, help="Only the actions of this run.")
@click.option("--limit", type=click.IntRange(1, 200), default=None, help="Page size (engine default 50).")
@click.option("--cursor", default=None, help="Continue from the next_cursor of the previous page.")
@click.option("--all", "fetch_all", is_flag=True, default=False, help="Follow every page.")
@pass_context
@_engine_errors
def actions_list(ctx, state, action_class, run_id, limit, cursor, fetch_all) -> None:
    """List the org's actions across runs; what needs a person comes first."""
    inv = _get_investigation(ctx)
    filters = dict(state=state, action_class=action_class, run_id=run_id, limit=limit, cursor=cursor)
    if fetch_all:
        _emit_page(ctx, "actions", list(inv.iter_actions(**filters)), "", _action_row)
        return
    page = inv.list_actions(**filters)
    _emit_page(ctx, "actions", page.get("actions") or [], page.get("next_cursor") or "", _action_row)


@actions_group.command("approve")
@click.argument("run_id")
@click.argument("action_id")
@pass_context
@_engine_errors
def actions_approve(ctx, run_id, action_id) -> None:
    """Approve an action (also needs the permission of the action's class)."""
    command_output(ctx, _get_investigation(ctx).decide_action(run_id, action_id, "approve"))


@actions_group.command("deny")
@click.argument("run_id")
@click.argument("action_id")
@click.option("--note", "reason", default=None, help="Why the action is denied.")
@pass_context
@_engine_errors
def actions_deny(ctx, run_id, action_id, reason) -> None:
    """Deny an action."""
    command_output(ctx, _get_investigation(ctx).decide_action(run_id, action_id, "deny", note=reason))


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

@group.group("policy")
def policy_group() -> None:
    """Effective policy and the pause switch for automatic actions."""


@policy_group.command("get")
@click.option("--category", default=None, help="Detection category to match run-scoped policy records.")
@click.option("--priority", type=int, default=None, help="Detection priority.")
@click.option("--severity", default=None, help="Detection severity.")
@click.option("--target-tag", "target_tags", multiple=True, help="Tag of the target sensor (repeatable).")
@click.option("--class", "action_class", default=None, help="Restrict to one action class.")
@click.option("--template", default=None, help="Template whose run identity to explain.")
@pass_context
@_engine_errors
def policy_get(ctx, category, priority, severity, target_tags, action_class, template) -> None:
    """Explain the effective policy."""
    command_output(ctx, _get_investigation(ctx).get_effective_policy(
        category=category, priority=priority, severity=severity,
        target_tags=list(target_tags) or None, action_class=action_class, template=template,
    ))


@policy_group.command("status")
@pass_context
@_engine_errors
def policy_status(ctx) -> None:
    """Show whether automatic actions are paused."""
    command_output(ctx, _get_investigation(ctx).get_autonomy())


@policy_group.command("pause")
@pass_context
@_engine_errors
def policy_pause(ctx) -> None:
    """Pause automatic actions for the org."""
    command_output(ctx, _get_investigation(ctx).set_autonomy("pause"))


@policy_group.command("resume")
@pass_context
@_engine_errors
def policy_resume(ctx) -> None:
    """Resume automatic actions for the org."""
    command_output(ctx, _get_investigation(ctx).set_autonomy("resume"))
