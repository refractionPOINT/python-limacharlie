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
    RUN_OUTCOMES,
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

A template has `gather` (steps that read the org's data), `rules` (`escalate`
and `close` rules over what was gathered, each with an id and a sentence for
the case), an optional `ai_review` (the fallback for what rules cannot decide)
and `act` / `case` (an `act` entry names the rules that fire it in
`on_rules: [<rule id> | ai_review]`; `on` is not a key). A `gather` step can carry
`record:` (one entry or a list) to say what the case shows of it: entities with a
verdict (`malicious_when` / `benign_when`; an unknown never asserts one; `each`,
`outcome_map` and `absence` give one entity per list element), telemetry and
artifacts (`ref` holds ids only). Nothing is scored: a run ends with an outcome
(closed_by_rule, escalated_by_rule, closed_by_ai, escalated_by_ai,
ai_recommends_benign, ai_recommends_malicious, couldnt_tell, conflict) and the
rule or the AI behind it. Whether the AI may DECIDE, or only recommend, is the
template's own `ai_may_decide` key (off, escalate, close_and_escalate).

The template is the authority: nothing above it limits what it does. Each `act`
entry says `do` (the action), `target` (not on a close), `on_rules`, a REQUIRED `approval`
(`none`, `required` or `{when: <expression>}`) and, for a reversible action
(contain.*), a `lease` and `on_lease_end` (`release`, `hold` or a `check:`
that runs again before it releases). A case close is an `act` entry too
(`do: close.false_positive`, `approval`, `on_rules`). A draft only suggests.
The org keeps three controls that belong to no template: the pause, the
circuit breaker and the plain settings (`investigate settings get|pause|resume`).

AI agent workflow for a new template (a person promotes it at the end):

  1. limacharlie investigate kit --section guide --section schema --section codes
  2. look at real data (detection get, search run, investigate wave ...)
  3. write the template YAML
  4. limacharlie investigate templates validate --file plan.yaml
  5. limacharlie investigate templates test --file plan.yaml --detect-cat <category> --last 10
  6. refine from the rules that disagreed with analysts, what the AI had to
     recommend and what stayed unknown, repeat 4-5
  7. limacharlie investigate templates save my-plan --file plan.yaml --comment "<what you tested>"
     (always a DRAFT; a draft runs only through a test or a run a person starts,
     and it only suggests its actions)
  8. a person reviews it and runs: limacharlie investigate templates promote my-plan --confirm

Questions without a template: use `investigate packs` then `investigate wave`.

Permissions: reads need investigation.get + insight.evt.get, writes (start,
wave, test, cancel, delete, decide) investigation.set + insight.evt.get, stats
also investigation_policy.set, template records investigation_plan.get/.set/.del,
settings pause/resume write the `paused` field of the default investigation_policy
record (investigation_policy.get and .set); settings get reads it through the
engine (the reads above).
"""

_EXPLAIN_KIT = """\
Fetch the authoring kit: template JSON Schema, the authoring guide, the
org's typed operator catalogue, examples, the org settings (budgets, pause,
circuit breaker, whether an AI agent is configured), every
validation code with its fix, the fact packs, and (when the engine has it) the
default template library.

The whole kit is about 33k tokens. Fetch it in parts with --section
(repeatable): start with guide, settings, codes, then schema and library. The
`size` entry of the answer says what was returned.

Examples:
  limacharlie investigate kit --section guide --section settings --section codes
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
(no run, case, label or action). `act` entries that would run are only listed
in `would_propose`.

Samples (at most 25 after expansion): --detection-id ID, --case-id ID,
--detect-cat CATEGORY with --last N (newest N alerts of the category), or
--sample '{"inputs": {...}, "expected": "false_positive"}'. A sample whose case
is closed is judged against the analyst's classification of the case. Use 5-10
samples of the category, with known false AND true positives.

Per sample the result says which rule decided (`verdict.decided_by.rule` and
the `outcome`), what the AI recommended when no rule decided
(`verdict.recommendation`), what was `missing`, and `agreement`: `rule` and
`ai` are each agree, disagree, unclear or none. The `summary` has the share of
alerts decided by rules (`rule_share`), per rule id how many it decided and how
many agreed or disagreed (`rules`), the AI's agree/disagree/unclear counts
(`ai`) and the cost per sample. These numbers inform you; nothing blocks on
them.

Read the result in this order: `validation` (state `invalid`: fix the
template), `summary`, each `disagree` (tighten or remove that rule), then
`undecided` samples (couldnt_tell or conflict: `missing` and `unknowns` say
which step could not be resolved and why). A pattern the AI recommends
correctly again and again is a candidate for a new rule. Steps that succeeded
are left out unless --include-steps.

The call waits for the test (default up to 600 s, --timeout). A test that is
still running prints its test_id: continue with --test-id ID. A test counts
against the org's concurrent run cap and may bill AI steps.

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
through `templates test` or a run a person starts, and it only suggests its
actions: none is executed. Put what you tested in --comment so the reviewer
sees it. Saving never lets the AI decide: that is the template's `ai_may_decide`
key, which a person reviews before promoting the template.

Examples:
  limacharlie investigate templates save my-plan --file plan.yaml --comment "10 samples, 7 decided by rules (0 disagree), 2 AI recommendations agree, 1 unknown"
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
  limacharlie investigate templates install-defaults --name mailsec-message
"""

_EXPLAIN_RUNS_START = """\
Start an investigation run: the engine gathers what the template's rules and
review read and ends with an outcome (see `investigate`): a rule decided
(closed_by_rule, escalated_by_rule, with the rule's sentence), the AI decided
where the template allows it (closed_by_ai, escalated_by_ai), the AI recommends
and a person acts on it (ai_recommends_benign, ai_recommends_malicious), or
nothing could be decided (couldnt_tell, conflict; `verdict.missing` says what
was missing and who needed it).

Pick the plan with --template NAME, --file plan.yaml (an inline draft) or
--auto (the engine picks the active template whose applies_to matches the
trigger: detect_cat, severity, tag and source, the first three from --category,
--severity and --tag; a draft is never picked, and no match is refused with the
reason). Say what to investigate with --detection-id, --case-id, --entity-id or
--question. --urgency (low, medium, high, critical) defaults to a value derived
from --priority and --severity, else medium. A
draft template only suggests its actions; an active one does what its `act`
entries say: `approval: required` waits for a person, `{when: ...}` waits only
when the condition holds or is unknown (when it is false the action acts on its
own), and nothing acts alone while the org is paused (`investigate settings`);
over the circuit breaker's cap an automatic containment waits too (closes and
tags do not count toward it).
--idempotency-key makes a repeated start return the same run.

Repeat --trust-lookup NAME / --trust-value VALUE to add to template trust for
this run only. The identity starting the run needs lookup.get for Lookups.
Automatic runs use only template trust.

With --wait N the call blocks up to N seconds for the outcome; --follow then
streams the run's events until it ends (--timeout defaults to 900 seconds;
0 has no time limit). On an interruption or stream error, resume with
runs events RUN_ID --follow --after N using the printed sequence.
With --follow in a structured output
format stdout is JSON lines: the first line is the start answer ({"run": ...,
"joined": ...}), the following lines are events ({"seq": ..., "type": ...}).

Examples:
  limacharlie investigate runs start --template my-plan --detection-id <ID>
  limacharlie investigate runs start --auto --case-id 42 --category my-category --wait 30
"""

_EXPLAIN_RUNS_GET = """\
Read a run: state, phase, actions, usage and the `verdict`: `outcome`, `label`,
`decided_by` {kind, rule, say}, the AI's `recommendation` (label,
self_rated_confidence, rationale, citations) when it only recommends, and
`missing` [{step, reason, needed_by, ask}]. `ai_may_decide` is the AI mode the
run started with and `ai_agent` the AI agent it uses. `self_rated_confidence`
is the AI's own rating: shown, never used.

Example:
  limacharlie investigate runs get <RUN_ID>
"""

_EXPLAIN_RUNS_LIST = """\
List the org's runs, newest first. Filters stack as AND. One page is returned
with --limit; continue with --cursor from the previous page's next_cursor, or
use --all to follow every page. --outcome keeps the runs that ended with one
outcome (or `undecided`); it needs investigation_policy.set, like --verdict.

Examples:
  limacharlie investigate runs list --state running
  limacharlie investigate runs list --outcome ai_recommends_benign --limit 50
  limacharlie investigate runs list --template my-plan --outcome couldnt_tell
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
Read a run's step log, plan graph, usage and outcome timeline. Every step has a
`narrative`: `why` it ran, what it `found`, and what it was `used` for (a rule,
the AI review, another step, the case, or nothing). --values includes customer
values (default: structure only).
"""

_EXPLAIN_RUNS_CASE = """\
Read the case document a run wrote (404 until the run has one). It opens with
the outcome sentence: the deciding rule's sentence, or the AI's recommendation
and what was missing.
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
outcome, no case), reuses what it already knows, and can stop as soon
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

_EXPLAIN_SETTINGS_GET = """\
Show the org's Investigation Engine settings as the engine enforces them: the
`default` record of the investigation_policy hive. `paused` says whether
nothing acts alone, and `set_by` / `set_at` say who last saved the record and
when (a pause is a field of that record, so this is who paused it unless
someone saved the record again since). `circuit_breaker` shows the caps and
`used_last_hour` / `tripped`. The rest: the run identity and whether it is
ready, where notifications go, which AI agent answers, budgets, the `limits`
(`max_parallel_runs`, 1 to 2000, default 100: starts above it wait in the
queue; optional `runs_per_hour`: starts above it are recorded as `capped`; see
`investigate queue`) and the case mode. `source: builtin` means the engine runs on its built-in settings: there
is no record, or the stored one does not parse (then `paused` is true, there is
no identity and `warnings` says `settings_rejected`: repair the record). With a
rejected record the engine keeps its last good copy.

The settings never override a template. What a template does is written in the
template: approval, lease and what happens when it ends, whether the AI may
decide.

Example:
  limacharlie investigate settings get
"""

_EXPLAIN_SETTINGS_PAUSE = """\
Pause the org: set `paused: true` on the `default` investigation_policy record.
Nothing acts alone while it is true: an action that would have acted alone
waits for a person. Runs still investigate, and approvals, denials, undos and
lease ends still work. Actions already taken are not undone, and actions that
waited keep waiting for a person after a resume. Only that field changes, and
the write is conditional on the version read, so a concurrent edit is never
overwritten. Saving it twice changes nothing, and the command fails (non-zero
exit) when the record does not read back as paused. It writes the record only:
run `settings get` to confirm the engine enforces it (its `warnings` name a
record the engine rejected). Needs investigation_policy.get and
investigation_policy.set. If Git Sync manages the investigation_policy
hive, keep the pause in git too or the next sync undoes it.

Example:
  limacharlie investigate settings pause
"""

_EXPLAIN_SETTINGS_RESUME = """\
Lift the pause: set `paused: false` on the `default` investigation_policy
record. Actions that waited while paused keep waiting for a person. Same
conditional write as `settings pause`. Needs investigation_policy.get and
investigation_policy.set.

Example:
  limacharlie investigate settings resume
"""

_EXPLAIN_QUEUE = """\
Show the org's run queue. An org runs at most `limits.max_parallel_runs`
investigations at once (settings record `investigation_policy/default`, 1 to
2000, default 100); a start above that waits in the queue and runs when a slot
frees, it is never refused. The answer has the totals (`queued`, `claimed`,
`running`, `max_parallel_runs`), the oldest wait, the counts by urgency band,
by rule and by template, the hour's counters against the optional
`limits.runs_per_hour` cap (a start above the cap is recorded as a terminal
`capped` run), and the recent flushes with their progress. Totals are exact.

Needs investigation.get and insight.evt.get. An engine that does not serve the
queue yet answers "The run queue is not available on this deployment yet."

Example:
  limacharlie investigate queue
"""

_EXPLAIN_QUEUE_FLUSH = """\
Flush queued starts: cancel the starts that are waiting and not yet running.
Name exactly one scope: `--rule <name>`, `--template <name>` or `--all`.

Each flushed start becomes a terminal `flushed` run that records who flushed
it, when and your `--note`; the alert shows as not investigated. Running
investigations are not touched. A start that arrives after the flush began
queues normally, so fixing a rule does not lose its new alerts. A flush cannot
be undone. A large flush finishes in the engine (`done: false`): the progress
is in `limacharlie investigate queue` under `flushes`.

The command shows how many starts the flush will cancel and asks you to
confirm; `--yes` skips the question (scripts). Needs investigation.set and
insight.evt.get. The request is sent once and never retried.

Examples:
  limacharlie investigate queue flush --rule suspicious-powershell --note "rule fixed"
  limacharlie investigate queue flush --template suspicious-process --yes
  limacharlie investigate queue flush --all --yes
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
    "investigate.queue": _EXPLAIN_QUEUE,
    "investigate.queue.flush": _EXPLAIN_QUEUE_FLUSH,
    "investigate.settings.get": _EXPLAIN_SETTINGS_GET,
    "investigate.settings.pause": _EXPLAIN_SETTINGS_PAUSE,
    "investigate.settings.resume": _EXPLAIN_SETTINGS_RESUME,
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


def _outcome(verdict: Any) -> Any:
    """The outcome a run ended with ('' while nothing settled), or None for a run without one."""
    return verdict.get("outcome") if isinstance(verdict, dict) else None


def _decided_by(verdict: Any) -> Any:
    """The id of the rule that decided, ``ai_review`` when the review did, or None."""
    by = verdict.get("decided_by") if isinstance(verdict, dict) else None
    if not isinstance(by, dict):
        return None
    return by.get("rule") or by.get("kind")


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
        "outcome": _outcome(run.get("verdict")),
        "decided_by": _decided_by(run.get("verdict")),
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
        "approval": (action.get("approval") or {}).get("form") if isinstance(action.get("approval"), dict) else None,
        "approval_reason": action.get("approval_reason"),
        "template": run.get("template"),
        "outcome": _outcome(run.get("verdict")),
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
    """Fetch the authoring kit: schema, guide, operators, examples, settings, codes, packs, library."""
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
                **{k: p[k] for k in ("version", "digest", "source", "trust", "trust_provenance") if k in p},
                "params": [{k: x.get(k) for k in ("name", "type", "required") if k in x} for x in p.get("params") or []],
                "exports": [{k: x.get(k) for k in ("name", "type", "ref", "brief") if k in x} for x in p.get("exports") or []],
            }
            for p in packs
        ]
    command_output(ctx, packs if _fmt(ctx) in ("table", "csv", "jsonl") else {"packs": packs})


@group.group("pack")
def pack_group() -> None:
    """Manage org-authored pack YAML; discover resolved packs with packs."""


@pack_group.command("get")
@click.argument("name")
@pass_context
@_engine_errors
def pack_get(ctx, name) -> None:
    """Read an org pack, including exact source and etag."""
    command_output(ctx, _get_investigation(ctx).get_pack(name))


@pack_group.command("save")
@click.argument("name")
@click.option("--file", "-f", "file_path", required=True, help="Pack YAML file ('-' for stdin).")
@click.option("--etag", default=None, help="Revision to replace; omit to create only.")
@pass_context
@_engine_errors
def pack_save(ctx, name, file_path, etag) -> None:
    """Store exact pack YAML through Hive validation."""
    command_output(ctx, _get_investigation(ctx).save_pack(name, _read_source(file_path), etag=etag))


@pack_group.command("delete")
@click.argument("name")
@click.option("--confirm", is_flag=True, help="Confirm deletion of the org pack.")
@pass_context
@_engine_errors
def pack_delete(ctx, name, confirm) -> None:
    """Delete an org pack; pinned runs retain their frozen sources."""
    if not confirm:
        raise click.UsageError("Deleting a pack requires --confirm.")
    command_output(ctx, _get_investigation(ctx).delete_pack(name))


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
        verdict = r.get("verdict") if isinstance(r.get("verdict"), dict) else {}
        recommendation = verdict.get("recommendation") if isinstance(verdict.get("recommendation"), dict) else {}
        agreement = r.get("agreement") if isinstance(r.get("agreement"), dict) else {}
        rows.append({
            "index": r.get("index"),
            "state": r.get("state"),
            "outcome": verdict.get("outcome"),
            "decided_by": _decided_by(verdict),
            "expected": (r.get("expected") or {}).get("label") if isinstance(r.get("expected"), dict) else None,
            "rule_agreement": agreement.get("rule"),
            "ai_agreement": agreement.get("ai"),
            "ai_recommends": recommendation.get("label"),
            "missing": len(verdict.get("missing") or []),
            "unknowns": len(r.get("unknowns") or verdict.get("unknowns") or []),
            "wall_ms": r.get("wall_ms"),
            "ai_cost": _test_cost(r.get("cost")),
            "sample": json.dumps(r.get("sample") or {}, separators=(",", ":")),
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
            "samples", "ran", "errors", "with_expected", "decided_by_rules", "rule_share") if k in summary))
        if summary.get("by_outcome"):
            click.echo(f"outcomes: {summary['by_outcome']}")
        rules = summary.get("rules") if isinstance(summary.get("rules"), dict) else {}
        for rule_id, counts in sorted(rules.items()):
            if isinstance(counts, dict):
                click.echo(f"rule {rule_id}: decided={counts.get('decided')} agree={counts.get('agree')} disagree={counts.get('disagree')}")
        if isinstance(summary.get("ai"), dict):
            click.echo("ai: " + ", ".join(f"{k}={summary['ai'][k]}" for k in ("recommended", "agree", "disagree", "unclear") if k in summary["ai"]))
        if isinstance(summary.get("cost"), dict):
            llm_cost = _test_cost(summary["cost"])
            click.echo(f"AI cost: {'unknown' if llm_cost is None else llm_cost}")
        per_sample = summary.get("cost_per_sample")
        if isinstance(per_sample, dict):
            click.echo("per sample: " + ", ".join(f"{k}={per_sample[k]}" for k in ("steps", "llm_usd", "wall_ms") if k in per_sample))
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
@click.option("--strict", is_flag=True, default=False, help="Refuse the test when --overrides-json would loosen the org's budgets (default: the loosening part is ignored).")
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
@click.option("--trust-lookup", "trust_lookups", multiple=True, help="Same-org Lookup to trust for this run only (repeatable; up to 64; adds to template trust). The identity starting the run needs lookup.get.")
@click.option("--trust-value", "trust_values", multiple=True, help="Inline trusted value for this run only (repeatable; at most 100).")
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
@click.option("--category", default=None, help="Detection category of the alert: matched by --auto.")
@click.option("--severity", default=None, help="Severity of the alert (low, medium, high, critical): matched by --auto; sets the default urgency.")
@click.option("--priority", type=int, default=None, help="Detection priority: sets the default urgency (8+ critical, 6+ high, 3+ medium).")
@click.option("--tag", "tags", multiple=True, help="Tag of the alert (repeatable): matched by --auto.")
@click.option("--input", "inputs", multiple=True, help="Run input KEY=VALUE (repeatable; values are text).")
@click.option("--inputs-json", default=None, help="Run inputs as a JSON object (typed values).")
@click.option("--urgency", type=click.Choice(["low", "medium", "high", "critical"]), default=None,
              help="Run urgency (how soon it matters). Default: derived from --priority / --severity, else medium.")
@click.option("--mode", type=click.Choice(["triage", "full", "scope"]), default=None, help="Run mode (engine default: full; triage is cheaper).")
@click.option("--case-mode", "case_mode", default=None, help="create, none or attach:<case number> (default: a new case for a detection or case trigger, unless the settings' case is none).")
@click.option("--idempotency-key", default=None, help="Starting twice with the same key returns the same run.")
@click.option("--wait", "wait_seconds", type=click.IntRange(0, 60), default=0, help="Block up to this many seconds for the verdict (this CLI accepts 0..60; the run goes on after it).")
@click.option("--follow", is_flag=True, default=False, help="Then stream the run's events until it ends.")
@click.option("--timeout", type=click.FloatRange(min=0), default=900, show_default=True,
              help="With --follow: stop after this many seconds; 0 follows without a time limit.")
@pass_context
@_engine_errors
def runs_start(ctx, template, file_path, auto, detection_id, case_id, entity_id, question, category, severity, priority,
               tags, inputs, inputs_json, urgency, mode, case_mode, idempotency_key, wait_seconds, follow, timeout, trust_lookups, trust_values) -> None:
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
    if trust_lookups or trust_values:
        request["trust"] = {}
        if trust_lookups:
            request["trust"]["lookups"] = list(trust_lookups)
        if trust_values:
            request["trust"]["values"] = list(trust_values)
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
            _follow_events(ctx, inv, run_id, 0, MAX_POLL_WAIT, None, timeout or None)


@runs_group.command("get")
@click.argument("run_id")
@pass_context
@_engine_errors
def runs_get(ctx, run_id) -> None:
    """Read a run: state, phase, outcome, actions and usage."""
    command_output(ctx, _get_investigation(ctx).get_run(run_id))


@runs_group.command("list")
@click.option("--state", default=None, help="Only runs in this state (queued, running, decided, completed, cancelled, failed, budget_exhausted, flushed, capped).")
@click.option("--outcome", type=click.Choice([*RUN_OUTCOMES, "undecided"]), default=None,
              help="Only runs that ended with this outcome (or undecided: nothing settled yet; needs investigation_policy.set).")
@click.option("--verdict", default=None, help="Only runs with this verdict label (true_positive, false_positive, inconclusive, undecided; needs investigation_policy.set).")
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
def runs_list(ctx, state, outcome, verdict, template, trigger, entity, started_by, idempotency_key, since, until, limit, cursor, fetch_all) -> None:
    """List the org's runs, newest first."""
    inv = _get_investigation(ctx)
    filters = dict(state=state, outcome=outcome, verdict=verdict, template=template, trigger=trigger, entity=entity,
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
    last_sequence = after
    structured = _fmt(ctx) in _STRUCTURED
    try:
        for event in inv.iter_run_events(run_id, after=after, wait=wait, limit=limit, timeout=timeout, state=state):
            if ctx.obj.quiet:
                last_sequence = event.get("seq", last_sequence)
                continue
            click.echo(json.dumps(event, separators=(",", ":"), default=str) if structured else _event_line(event))
            sys.stdout.flush()
            last_sequence = event.get("seq", last_sequence)
    except LimaCharlieError:
        note(ctx, f"event stream failed; resume with --after {last_sequence}")
        raise
    except KeyboardInterrupt:
        note(ctx, f"interrupted; resume with --after {last_sequence}")
        ctx.exit(130)
    if state.get("done"):
        return
    note(ctx, f"run not finished after {timeout:g}s; resume with --after {last_sequence}")
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
    """Read a run's step log (with each step's narrative), plan graph, usage and outcome timeline."""
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
# queue
# ---------------------------------------------------------------------------

@group.group("queue", invoke_without_command=True)
@pass_context
@_engine_errors
def queue_group(ctx) -> None:
    """Show the org's run queue (starts waiting for a free slot); `queue flush` cancels them."""
    if click.get_current_context().invoked_subcommand is None:
        command_output(ctx, _get_investigation(ctx).get_queue())


def _queued_count(queue: dict[str, Any], rule: str | None, template: str | None) -> int | None:
    """How many queued starts a flush of this scope cancels, from the queue answer (None: not stated)."""
    if rule is None and template is None:
        value = queue.get("queued")
    else:
        key, name = ("by_rule", rule) if rule is not None else ("by_template", template)
        label = "rule" if rule is not None else "template"
        rows = queue.get(key)
        if not isinstance(rows, list):
            return None
        value = 0
        for row in rows:
            if isinstance(row, dict) and row.get(label) == name:
                value = row.get("queued")
                break
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@queue_group.command("flush")
@click.option("--rule", default=None, help="Flush the queued starts of this detection rule.")
@click.option("--template", default=None, help="Flush the queued starts of this template.")
@click.option("--all", "all_", is_flag=True, default=False, help="Flush every queued start of the org.")
@click.option("--note", "note_text", default=None, help="Why; kept on every flushed run and in the audit log.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Do not ask for confirmation.")
@pass_context
@_engine_errors
def queue_flush(ctx, rule, template, all_, note_text, yes) -> None:
    """Cancel queued starts: one rule, one template or all (running investigations are not touched; cannot be undone)."""
    given = [name for name, value in (("--rule", rule), ("--template", template)) if value is not None] + (["--all"] if all_ else [])
    if len(given) != 1:
        raise click.UsageError("Name exactly one of --rule, --template or --all.")
    inv = _get_investigation(ctx)
    scope_text = "every queued start" if all_ else f"the queued starts of {'rule' if rule is not None else 'template'} '{rule if rule is not None else template}'"
    if not yes:
        count = _queued_count(inv.get_queue(), rule, template)
        how_many = "an unknown number of" if count is None else str(count)
        click.echo(
            f"This cancels {how_many} queued start(s) ({scope_text}). Starts not yet running are cancelled and "
            "recorded as flushed; running investigations are not touched. This cannot be undone.",
            err=True,
        )
        click.confirm("Flush them?", abort=True, err=True)
    result = inv.flush_queue(rule=rule, template=template, all=all_, note=note_text)
    flushed = result.get("flushed") if isinstance(result, dict) else None
    if isinstance(flushed, int) and not isinstance(flushed, bool):
        suffix = "" if result.get("done", True) else " so far; the rest finishes in the engine (see `investigate queue`)"
        note(ctx, f"Flushed {flushed} queued start(s){suffix}.")
    command_output(ctx, result)


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

@group.group("settings")
def settings_group() -> None:
    """The org's engine settings, and the pause for automatic actions."""


@settings_group.command("get")
@pass_context
@_engine_errors
def settings_get(ctx) -> None:
    """Show the org settings the engine enforces (paused, circuit breaker, identity, notifications, budgets, limits)."""
    command_output(ctx, _get_investigation(ctx).get_settings())


@settings_group.command("pause")
@pass_context
@_engine_errors
def settings_pause(ctx) -> None:
    """Pause the org: nothing acts alone (sets paused on the default settings record)."""
    command_output(ctx, _get_investigation(ctx).pause_actions())


@settings_group.command("resume")
@pass_context
@_engine_errors
def settings_resume(ctx) -> None:
    """Lift the pause (clears paused on the default settings record)."""
    command_output(ctx, _get_investigation(ctx).resume_actions())


@group.command("stats")
@click.option("--template", default=None, help="Only runs of this template.")
@click.option("--since", default=None, help="Only runs created at or after this RFC 3339 time.")
@click.option("--until", default=None, help="Only runs created before this RFC 3339 time.")
@pass_context
@_engine_errors
def stats_cmd(ctx, template, since, until) -> None:
    """Show the engine's performance statistics (needs investigation_policy.set too)."""
    command_output(ctx, _get_investigation(ctx).get_stats(template=template, since=since, until=until))
