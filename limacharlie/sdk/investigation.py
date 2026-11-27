"""Investigation Engine SDK for LimaCharlie v2.

Wraps the ``/investigate/{oid}/...`` REST routes served by the API gateway:
the authoring kit, the typed operator and fact-pack catalogues, plan
validation and dry runs on past alerts, investigation runs (start, read,
list, events, cancel, delete), waves, the approvals inbox, the org settings and the
pause of automatic actions (a field of the settings record).

The feature is experimental and gated per deployment. Where it is off, every
route is an unknown path (HTTP 404 with no engine error code); where the
organisation has no engine, the gateway answers 503.
:class:`InvestigationError` says which of those happened.

Permissions (all of the listed ones are required):

- reads (runs, templates, operators, packs, kit, settings, test results, the
  approvals inbox): ``investigation.get`` + ``insight.evt.get``
- writes (start a run, waves, cancel, delete, test a plan, decide an action):
  ``investigation.set`` + ``insight.evt.get``; deciding an action also needs
  the permission of the action's own class (for example ``sensor.task``)
- the performance stats additionally need ``investigation_policy.set``, and so
  does filtering the run list by outcome or verdict
- pause / resume of automatic actions: they write the ``paused`` field of the
  hive record ``investigation_policy/default`` (the org settings), so they need
  ``investigation_policy.get`` and ``investigation_policy.set``, explicit grants
  no default role has. Reading the settings through the engine
  (:meth:`Investigation.get_settings`) needs only the reads above.
- the template records themselves (hive ``investigation_plan``):
  ``investigation_plan.get`` / ``investigation_plan.set`` /
  ``investigation_plan.del``. These are explicit grants, no default role has
  them.

A template has ``gather`` steps (what to read), ``rules`` (``escalate`` and
``close`` rules over what was gathered, each with an id and a sentence) and an
optional ``ai_review`` for what rules cannot decide. A run ends with an
*outcome* (:data:`RUN_OUTCOMES`) and the rule or the AI behind it; nothing is
scored. Whether the AI may *decide* (rather than recommend) is
``ai_may_decide``, a key of the template itself (``off``, ``escalate`` or
``close_and_escalate``). What a template does is written in the template: each
``act`` entry says what it does (``do``), whether a person approves it
(``approval``), and for a reversible action how long it lasts (``lease``) and
what happens then (``on_lease_end``). The settings record holds only what
belongs to no single template: the pause, the circuit breaker, the run
identity, notifications, the AI agent and budgets.

Templates are plain Hive records. This module never writes an *active*
template unless the caller passes ``status="active"`` explicitly (the call a
person makes), never overwrites a record without ``overwrite=True`` and never
replaces an active template with a draft. A draft runs only through a dry run
(:meth:`Investigation.test_plan`) or a run started by a person, with
every action only suggested (recorded, never executed).
"""

from __future__ import annotations

import base64
import datetime
import functools
import json
import re
import time
from typing import Any, Iterator, TYPE_CHECKING
from urllib.parse import quote as _quote

import yaml

from ..errors import ApiError, LimaCharlieError, ValidationError
from .hive import Hive, HiveRecord, is_permission_denied, is_record_not_found

if TYPE_CHECKING:
    from .organization import Organization


PLAN_HIVE = "investigation_plan"
PACK_HIVE = "investigation_pack"
POLICY_HIVE = "investigation_policy"

#: The one record of the settings hive the engine reads: the org settings.
SETTINGS_RECORD = "default"
STATUS_DRAFT = "draft"
STATUS_ACTIVE = "active"

#: Sections of the authoring kit the engine can return.
KIT_SECTIONS = ("schema", "guide", "operators", "examples", "settings", "codes", "packs", "library")

#: Decisions the gateway accepts on an action.
ACTION_VERBS = ("approve", "deny", "revert", "extend", "confirm")

#: Run states after which a run no longer changes.
TERMINAL_RUN_STATES = ("completed", "cancelled", "failed", "budget_exhausted", "flushed", "capped")

#: How a run ends (``verdict.outcome`` of a run, a list row and a test sample).
RUN_OUTCOMES = (
    "closed_by_rule", "escalated_by_rule", "closed_by_ai", "escalated_by_ai",
    "ai_recommends_benign", "ai_recommends_malicious", "couldnt_tell", "conflict",
)

#: What a template lets the AI decide (its ``ai_may_decide`` key): nothing (it
#: only recommends), escalate, or close and escalate.
AI_MODES = ("off", "escalate", "close_and_escalate")

#: Template (record) names this module will create.
TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# What the gateway accepts as a run, action or test id; anything else is
# refused there. "." and ".." are refused as path traversal.
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

# Sent as the etag of a write that must create a record. The hive ignores the
# etag when no record exists and refuses the write when one does (it matches no
# stored etag), so a record created between our check and the write is never
# overwritten.
_CREATE_ONLY_ETAG = "create-only: the record must not exist"

# The engine's long polls (run events, test results) wait at most this long.
MAX_POLL_WAIT = 10
MAX_EVENTS_LIMIT = 500

# Bound cursor history while refusing pagination cycles.
_MAX_PAGINATION_CURSORS = 10000

# Seconds added to a call's own wait to form its HTTP timeout.
_WAIT_MARGIN = 35


class InvestigationError(ApiError):
    """An Investigation Engine call failed.

    Carries what the engine said, verbatim, next to the HTTP status: the
    engine's ``error_code`` (``bad_request``, ``not_found``, ``conflict``,
    ``too_many_runs``, ...) and the coded ``errors`` / ``warnings`` of a plan
    or wave that was refused (each ``{code, path, message, suggestion?}``).

    ``error_code`` (inherited) is the engine's code, or None when the answer
    did not come from the engine itself (for example a gateway 404).
    ``reason_code`` is the engine's specific cause of a refused run start
    (``no_template_applies``, ``template_draft``, ...), or None.

    Attributes:
        issues: The coded errors of a refused plan or wave.
        warnings: The coded warnings that came with them.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None,
        issues: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
        response_body: Any = None,
        suggestion: str | None = None,
        exit_code: int = 1,
    ) -> None:
        self.issues = issues or []
        self.warnings = warnings or []
        # The reason code ends the text a person reads; the machine-readable document keeps the
        # engine's message as sent and carries the code in its own key.
        reason = _body_token(response_body, "reason_code")
        self._reason_suffix = f" (reason_code: {reason})" if reason and reason not in message else ""
        message += self._reason_suffix
        super().__init__(message, status_code=status_code, response_body=response_body, suggestion=suggestion)
        self.exit_code = exit_code

    @property
    def reason_code(self) -> str | None:
        """The engine's ``reason_code`` of a refused run start, if the answer carried one."""
        return _body_token(self.response_body, "reason_code")

    @property
    def path(self) -> str | None:
        """The JSON Pointer of the policy field a refused policy answer names, if it carried one."""
        body = self.response_body
        value = body.get("path") if isinstance(body, dict) else None
        return value if isinstance(value, str) else None

    def to_dict(self) -> dict[str, Any]:
        """Render the failure as a machine-readable document.

        Returns:
            dict: ``error`` (message), ``status`` (HTTP), ``error_code``,
                ``reason_code`` and ``path`` when the engine sent them, and
                ``errors`` / ``warnings`` exactly as the engine sent them.
        """
        error = self.raw_message
        if self._reason_suffix and error.endswith(self._reason_suffix):
            error = error[: -len(self._reason_suffix)]
        out: dict[str, Any] = {"error": error, "status": self.status_code}
        if self.error_code:
            out["error_code"] = self.error_code
        if self.reason_code:
            out["reason_code"] = self.reason_code
        if self.path is not None:
            out["path"] = self.path
        fields = self.response_body.get("fields") if isinstance(self.response_body, dict) else None
        if isinstance(fields, dict) and fields:
            out["fields"] = fields
        if self.issues:
            out["errors"] = self.issues
        if self.warnings:
            out["warnings"] = self.warnings
        if self.suggestion:
            out["suggestion"] = self.suggestion
        return out


def _body_token(body: Any, key: str) -> str | None:
    value = body.get(key) if isinstance(body, dict) else None
    return value if isinstance(value, str) and value else None


def _issue_line(issue: Any) -> str:
    if not isinstance(issue, dict):
        return str(issue)
    line = f"[{issue.get('code', '?')}] {issue.get('path', '')}: {issue.get('message', '')}".replace(" : ", ": ")
    if issue.get("suggestion"):
        line += f" (did you mean {issue['suggestion']})"
    return line


_PERMISSION_HINT = (
    "Reads need investigation.get + insight.evt.get, writes (start, wave, cancel, delete, test, decide) need "
    "investigation.set + insight.evt.get, the stats also need investigation_policy.set, and template records need "
    "investigation_plan.get / investigation_plan.set. Deciding an action also needs the permission of its class, "
    "and an API key needs a key id."
)

_DISABLED_HINT = (
    "The Investigation Engine is experimental and gated per deployment: this API does not serve /investigate "
    "for this organization's region. Check you target the right environment, or ask for the feature to be enabled."
)


def _wrap_error(exc: LimaCharlieError) -> LimaCharlieError:
    """Turn a transport error into an :class:`InvestigationError` that says what to do."""
    status = exc.status_code
    if status is None or status == 401 or status < 400:
        return exc
    body = getattr(exc, "response_body", None)
    message = ""
    code: str | None = None
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if isinstance(body, dict):
        message = str(body.get("error") or "")
        code = body.get("error_code") if isinstance(body.get("error_code"), str) else None
        issues = [i for i in (body.get("errors") or []) if i] if isinstance(body.get("errors"), list) else []
        warnings = [w for w in (body.get("warnings") or []) if w] if isinstance(body.get("warnings"), list) else []
    elif isinstance(body, str) and body.strip():
        message = body.strip()
    if not message:
        message = exc.raw_message
    lines = [_issue_line(i) for i in issues]
    if lines and not any(line in message for line in lines):
        message += "\n" + "\n".join(f"  {line}" for line in lines)

    suggestion: str | None = None
    if status == 404 and code is None:
        suggestion = _DISABLED_HINT
    elif status == 403 and code is None:
        suggestion = _PERMISSION_HINT
    elif status == 503 and code != "unavailable":
        suggestion = "No engine serves this organization right now (feature off or the region is unavailable); retry later."
    elif status == 429 and code == "too_many_runs":
        suggestion = "The organization's concurrent run cap is reached; wait for a run to finish and retry."
    elif status == 501:
        suggestion = "This feature is not enabled in the engine."
    elif status in (502, 504):
        suggestion = "The engine did not answer in time. Reads can be retried; check a run's state before starting it again."
    return InvestigationError(
        message,
        status_code=status,
        issues=issues,
        warnings=warnings,
        response_body=body,
        suggestion=suggestion or "",  # "": no generic advice when the engine's own message is enough
        exit_code=exc.exit_code,
    )


#: What a person reads when the API answers 501 ``not_implemented`` for a queue call: the engine of the region
#: has not been updated to the queue yet.
QUEUE_NOT_AVAILABLE = "The run queue is not available on this deployment yet."

#: What each refusal of an AI agent's answer means, by the engine's ``error_code`` (HTTP status in brackets).
#: ``None`` is a 403 that carries no engine code (the API's own: the key lacks ``investigation.get``).
AGENT_ANSWER_MEANINGS: dict[str | None, str] = {
    "invalid_answer": (
        "The answer does not match what the step asked for (400). Nothing was recorded: fix the fields the "
        "message names and send it again before the deadline."
    ),
    "forbidden": (
        "The answer token does not match this request (403). Use the LC_IE_ANSWER_TOKEN of the session the "
        "engine started for this run and request."
    ),
    "not_found": "There is no such request on this run (404). Check LC_IE_RUN_ID and LC_IE_REQUEST_ID.",
    "already_answered": "This request already has an answer (409); a second answer is never taken.",
    "deadline_passed": "The request's deadline passed (409): the step already counted as unknown (timeout). Too late to answer.",
    "not_waiting": (
        "The run no longer waits for this answer (409): the session ended, the start was refused, the run was "
        "cancelled or it is over. Too late to answer."
    ),
    "not_implemented": "The engine of this deployment does not take AI agent answers yet (501).",
    None: "The API refused the answer (403): the key needs the investigation.get permission.",
}

_ANSWER_ROUTE_HINT = (
    "A 404 with no engine error code means this API deployment does not serve agent answers yet (an engine "
    "refusal of an unknown request has an error_code)."
)

_DELETE_ROUTE_HINT = (
    "A 404 with no engine error code means this API deployment does not serve run deletion: the "
    "Investigation Engine is not enabled for it, or it is a version that predates `runs delete`."
)

_TEMPLATE_PERMISSION_HINT = (
    "Template records are the hive 'investigation_plan': reading needs investigation_plan.get, writing "
    "investigation_plan.set, deleting investigation_plan.del. They are explicit grants that no default role has."
)


def _record_errors(permission_hint: str) -> Any:
    """Build the decorator that reports a failed hive-record operation as an :class:`InvestigationError`.

    A refused permission also says which permission the operation needs
    (``permission_hint``). Any other Hive or API failure keeps its message,
    HTTP status, response body (so ``error_code`` still carries the backend's
    ``lc_error_code``) and exit code, so callers handle one error type
    whatever went wrong.
    """
    def decorate(fn: Any) -> Any:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except InvestigationError:
                raise
            except LimaCharlieError as exc:
                denied = is_permission_denied(exc)
                if not denied and not isinstance(exc, ApiError):
                    raise  # input errors and the like are not Hive answers
                raise InvestigationError(
                    exc.raw_message,
                    status_code=403 if denied else exc.status_code,
                    response_body=getattr(exc, "response_body", None),
                    suggestion=permission_hint if denied else (exc.suggestion or ""),
                    exit_code=2 if denied else exc.exit_code,  # 2 = authentication or permission
                ) from exc
        return wrapper
    return decorate


_template_record_errors = _record_errors(_TEMPLATE_PERMISSION_HINT)

_POLICY_PERMISSION_HINT = (
    "The pause is the 'paused' field of the hive record 'investigation_policy/default' (the org settings): "
    "reading it needs investigation_policy.get, pausing and resuming investigation_policy.set. "
    "They are explicit grants that no default role has."
)

_policy_record_errors = _record_errors(_POLICY_PERMISSION_HINT)


def _check_id(kind: str, value: str) -> str:
    if not isinstance(value, str) or value in (".", "..") or not _ID_RE.match(value):
        raise ValidationError(f"invalid {kind} {value!r}: use letters, digits and . _ : - (at most 128 characters)")
    return value


def _check_wait(wait: int) -> int:
    if not isinstance(wait, int) or isinstance(wait, bool) or wait < 0 or wait > MAX_POLL_WAIT:
        raise ValidationError(f"wait must be an integer between 0 and {MAX_POLL_WAIT} seconds")
    return wait


_STR_TAG = "tag:yaml.org,2002:str"
_BOOL_TAG = "tag:yaml.org,2002:bool"
_INT_TAG = "tag:yaml.org,2002:int"
_FLOAT_TAG = "tag:yaml.org,2002:float"
_NULL_TAG = "tag:yaml.org,2002:null"
_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"
_BINARY_TAG = "tag:yaml.org,2002:binary"
_MERGE_TAG = "tag:yaml.org,2002:merge"
# Tag of an unquoted, untagged scalar until its context says what it is.
_PLAIN_TAG = "tag:limacharlie.io,2026:plain"

_INT64_MIN, _INT64_MAX, _UINT64_MAX = -(1 << 63), (1 << 63) - 1, (1 << 64) - 1
_YAML_STYLE_FLOAT_RE = re.compile(r"^[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?$")
_DOT_FLOAT_RE = re.compile(r"^\.[0-9]+([eE][-+]?[0-9]+)?$")
_TS_DATE = r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})"
_TS_CLOCK = r"([0-9]{1,2}):([0-9]{1,2}):([0-9]{1,2})(?:\.([0-9]+))?"
# The four layouts yaml.v3 tries, in the order it tries them.
_TIMESTAMP_RES = (
    re.compile(rf"^{_TS_DATE}[Tt]{_TS_CLOCK}(Z|[+-][0-9]{{2}}:[0-9]{{2}})$"),
    re.compile(rf"^{_TS_DATE} {_TS_CLOCK}()$"),
    re.compile(rf"^{_TS_DATE}()()()()()$"),
)
_RESOLVE_MAP: dict[str, tuple[str, Any]] = {}
for _words, _tag, _val in (
    (("true", "True", "TRUE"), _BOOL_TAG, True),
    (("false", "False", "FALSE"), _BOOL_TAG, False),
    (("", "~", "null", "Null", "NULL"), _NULL_TAG, None),
    ((".nan", ".NaN", ".NAN"), _FLOAT_TAG, float("nan")),
    ((".inf", ".Inf", ".INF", "+.inf", "+.Inf", "+.INF"), _FLOAT_TAG, float("inf")),
    (("-.inf", "-.Inf", "-.INF"), _FLOAT_TAG, float("-inf")),
):
    for _w in _words:
        _RESOLVE_MAP[_w] = (_tag, _val)
_BOOL_WORDS_1_1 = {
    "y": True, "Y": True, "yes": True, "Yes": True, "YES": True, "on": True, "On": True, "ON": True,
    "n": False, "N": False, "no": False, "No": False, "NO": False, "off": False, "Off": False, "OFF": False,
}


def _go_parse_uint(s: str) -> int | None:
    """Go ``strconv.ParseUint(s, 0, 64)`` (without the underscore rules: callers strip them)."""
    if not s:
        return None
    base = 10
    if s[0] == "0":
        if len(s) >= 3 and s[1] in "bB":
            base, s = 2, s[2:]
        elif len(s) >= 3 and s[1] in "oO":
            base, s = 8, s[2:]
        elif len(s) >= 3 and s[1] in "xX":
            base, s = 16, s[2:]
        else:
            base, s = 8, s[1:]
    n = 0
    for ch in s:
        d = "0123456789abcdef".find(ch.lower()) if ch.isascii() else -1
        if d < 0 or d >= base:
            return None
        n = n * base + d
        if n > _UINT64_MAX:
            return None
    return n


def _go_parse_int(s: str) -> int | None:
    """Go ``strconv.ParseInt(s, 0, 64)``."""
    neg = s[:1] == "-"
    if s[:1] in ("+", "-"):
        s = s[1:]
    n = _go_parse_uint(s)
    if n is None:
        return None
    n = -n if neg else n
    return n if _INT64_MIN <= n <= _INT64_MAX else None


def _go_float(s: str) -> float | None:
    """The float for a decimal spelling Go's ParseFloat accepts; None when it overflows."""
    value = float(s)
    return None if value in (float("inf"), float("-inf")) else value


def _parse_timestamp(s: str) -> str | None:
    """A timestamp as yaml.v3 reads it, rendered as the UTC RFC 3339 text the engine would store.

    Only the layouts yaml.v3 knows are timestamps: ``2006-1-2``,
    ``2006-1-2T15:4:5.999Z07:00`` (a lower-case ``t`` too) and
    ``2006-1-2 15:4:5.999`` with no zone. Anything Go's time parser would
    reject (month 13, February 30th, hour 25) is text.
    """
    for rx in _TIMESTAMP_RES:
        m = rx.match(s)
        if m:
            break
    else:
        return None
    year, month, day = int(m[1]), int(m[2]), int(m[3])
    hour, minute, second = (int(m[4]), int(m[5]), int(m[6])) if m[4] else (0, 0, 0)
    shift = 400 if year < 400 else 0  # datetime has no year 0; the calendar repeats every 400 years
    try:
        local = datetime.datetime(year + shift, month, day, hour, minute, second)
    except ValueError:
        return None
    zone = m[8] or "Z"
    offset = 0
    if zone != "Z":
        if int(zone[1:3]) > 24 or int(zone[4:6]) > 59:
            return None
        offset = (int(zone[1:3]) * 60 + int(zone[4:6])) * (1 if zone[0] == "+" else -1)
    try:
        utc = local - datetime.timedelta(minutes=offset)
    except OverflowError:
        return None
    frac = (m[7] or "")[:9].rstrip("0")
    if utc.year - shift < 0:
        return None
    stamp = f"{utc.year - shift:04d}-{utc.month:02d}-{utc.day:02d}T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}"
    return stamp + (f".{frac}" if frac else "") + "Z"


def _resolve_scalar(text: str, tag: str = "") -> tuple[str, Any]:
    """Resolve a scalar according to the public template YAML contract.

    Checked against normalized recorded compatibility observations in
    ``tests/unit/fixtures/investigation_scalars.json``. Regeneration and
    provenance are documented in that directory's ``README.investigation.md``.
    ``tag`` is empty for a plain scalar or an explicit ``!!int``-style tag.
    Returns ``(tag, value)``; timestamps use UTC RFC 3339 text.

    Raises:
        ValueError: If an explicit tag does not fit the text.
    """
    kind, value = _natural_scalar(text, tag)
    if tag in ("", _STR_TAG, _BINARY_TAG) or kind == tag:
        return kind, value
    if tag == _FLOAT_TAG and kind == _INT_TAG:
        return _FLOAT_TAG, float(value)
    raise ValueError(f"cannot decode {kind.rsplit(':', 1)[-1]} `{text}` as a {tag.rsplit(':', 1)[-1]}")


def _natural_scalar(text: str, tag: str) -> tuple[str, Any]:
    if tag in (_STR_TAG, _BINARY_TAG):
        return _STR_TAG, text
    first = text[:1]
    if first == "":
        hint = "N"
    elif first in "+-":
        hint = "S"
    elif first in "0123456789":
        hint = "D"
    elif first in "yYnNtTfFoO~":
        hint = "M"
    elif first == ".":
        hint = "."
    else:
        return _STR_TAG, text
    if text in _RESOLVE_MAP:
        return _RESOLVE_MAP[text]
    if hint == ".":
        if _DOT_FLOAT_RE.match(text):
            f = _go_float(text)
            if f is not None:
                return _FLOAT_TAG, f
    elif hint in ("D", "S"):
        if tag in ("", _TIMESTAMP_TAG):
            ts = _parse_timestamp(text)
            if ts is not None:
                return _TIMESTAMP_TAG, ts
        plain = text.replace("_", "")
        n = _go_parse_int(plain)
        if n is None and plain[0] not in "+-":
            n = _go_parse_uint(plain)
        if n is not None:
            return _INT_TAG, n
        if _YAML_STYLE_FLOAT_RE.match(plain):
            f = _go_float(plain)
            if f is not None:
                return _FLOAT_TAG, f
    return _STR_TAG, text


class _TemplateLoader(yaml.SafeLoader):
    """YAML loader for template sources and other documents sent to the engine.

    The engine reads YAML with gopkg.in/yaml.v3, not with PyYAML's YAML 1.1
    rules, and what a scalar means depends on where it sits:

    * Under a step's ``args`` or an ``act`` entry's ``attrs`` (and in any
      document that is not a template) an unquoted scalar is resolved by yaml.v3's rules: ``yes``/``off`` are text,
      ``012`` is 10, ``1_000`` is 1000, ``0o17`` is 15, ``1e3`` is a float, a
      date is a timestamp (kept as its UTC RFC 3339 text, which is what the
      stored record holds).
    * Everywhere else the engine reads into text fields, so the author's spelling
      is kept: ``description: 1e3`` stays ``"1e3"``. A few fields are numbers or
      booleans (``version``, ``pack_version``, ``always``) and are read as such.

    A quoted scalar is always text. A mapping key is always text.
    """

    def resolve(self, kind: Any, value: Any, implicit: Any) -> str:
        if kind is yaml.ScalarNode and implicit[0]:
            return _PLAIN_TAG
        return super().resolve(kind, value, implicit)


def _construct_resolved(tag: str) -> Any:
    def construct(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
        text = str(loader.construct_scalar(node))
        try:
            return _resolve_scalar(text, tag)[1]
        except ValueError as exc:
            raise yaml.constructor.ConstructorError(None, None, str(exc), node.start_mark) from exc
    return construct


def _construct_binary(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    try:
        return base64.b64decode(str(loader.construct_scalar(node)), validate=False).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise yaml.constructor.ConstructorError(None, None, f"cannot read !!binary as text: {exc}", node.start_mark) from exc


for _t in (_BOOL_TAG, _INT_TAG, _FLOAT_TAG, _NULL_TAG, _TIMESTAMP_TAG):
    _TemplateLoader.add_constructor(_t, _construct_resolved(_t))
_TemplateLoader.add_constructor(_PLAIN_TAG, _construct_resolved(_STR_TAG))
_TemplateLoader.add_constructor(_BINARY_TAG, _construct_binary)

# Template fields the engine reads as numbers or booleans, by path ("*" is any
# list index or map key). Every other scalar outside a fact's args is text.
_NUMBER_PATHS = {("version",), ("gather", "*", "pack_version")}
_BOOL_PATHS = {("gather", "*", "always")}


def _path_matches(path: tuple[str, ...], patterns: set[tuple[str, ...]]) -> bool:
    return any(
        len(p) == len(path) and all(a == "*" or a == b for a, b in zip(p, path)) for p in patterns
    )


def _retag(node: yaml.Node, path: tuple[str, ...], any_ctx: bool, seen: set[int], document: bool = False) -> None:
    """Decide what each unquoted scalar of the document is, from where it sits.

    ``document`` is a file the CLI turns into JSON itself (a wave, samples):
    the engine never reads it as YAML, so a date keeps the author's spelling.
    """
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, yaml.ScalarNode):
        if node.tag != _PLAIN_TAG:
            return
        if any_ctx:
            node.tag = _resolve_scalar(node.value)[0]
            if document and node.tag == _TIMESTAMP_TAG:
                node.tag = _STR_TAG
        elif _path_matches(path, _NUMBER_PATHS):
            tag = _resolve_scalar(node.value)[0]
            node.tag = tag if tag in (_INT_TAG, _FLOAT_TAG) else _STR_TAG
        elif _path_matches(path, _BOOL_PATHS):
            if node.value in _BOOL_WORDS_1_1:
                node.tag, node.value = _BOOL_TAG, "true" if _BOOL_WORDS_1_1[node.value] else "false"
            else:
                tag = _resolve_scalar(node.value)[0]
                node.tag = tag if tag == _BOOL_TAG else _STR_TAG
        else:
            node.tag = _STR_TAG
        return
    if isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _retag(item, path + ("*",), any_ctx, seen, document)
        return
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if isinstance(key, yaml.ScalarNode) and key.tag == _PLAIN_TAG:
                key.tag = _MERGE_TAG if key.value == "<<" else _STR_TAG
            name = key.value if isinstance(key, yaml.ScalarNode) else "*"
            child_any = any_ctx or (
                (len(path) == 2 and path[0] == "gather" and name == "args")
                or (len(path) == 2 and path[0] == "act" and name == "attrs")
            )
            _retag(value, path + (name,), child_any, seen, document)


def _load_yaml(source: str, allow_aliases: bool, document: bool) -> Any:
    """Parse YAML with the engine's scalar rules; raise ``yaml.YAMLError``."""
    if not allow_aliases:
        for event in yaml.parse(source, Loader=_TemplateLoader):
            if isinstance(event, yaml.AliasEvent):
                raise ValidationError(
                    "YAML anchors and aliases are not supported in a template; write the value out"
                )
    loader = _TemplateLoader(source)
    try:
        node = loader.get_single_node()
        if node is None:
            return None
        _retag(node, (), document, set(), document)
        return loader.construct_document(node)
    finally:
        loader.dispose()


def _check_json_carries(doc: Any, what: str) -> None:
    try:
        json.dumps(doc, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{what} holds a value JSON cannot carry: {exc}") from exc


def parse_document(source: str, what: str = "the document") -> Any:
    """Parse a YAML or JSON document into plain JSON-compatible values.

    Unquoted scalars are read the way the engine's YAML library reads a value
    it holds as ``any``: ``off``/``yes``/``no`` stay text, ``012`` is 10,
    ``1_000`` is 1000 and ``0o17`` is 15. A date stays the text it was written as.

    Args:
        source: The YAML or JSON text.
        what: What the text is, for error messages (for example ``"the wave file"``).

    Returns:
        Any: The parsed value.

    Raises:
        ValidationError: If the text is not YAML or JSON, or holds a value
            JSON cannot carry (a set tag, ``.nan`` or ``.inf``, for example).
    """
    if not isinstance(source, str) or not source.strip():
        raise ValidationError(f"{what} is empty")
    try:
        doc = _load_yaml(source, allow_aliases=True, document=True)
    except yaml.YAMLError as exc:
        try:
            doc = json.loads(source)
        except ValueError:
            raise ValidationError(f"{what} is neither valid YAML nor JSON: {exc}") from exc
    _check_json_carries(doc, what)
    return doc


def parse_template_source(source: str) -> dict[str, Any]:
    """Parse a template's YAML source into the mapping stored in the hive record.

    Args:
        source: The template YAML.

    Returns:
        dict: The template as plain JSON-compatible values.

    Raises:
        ValidationError: If the source is empty, not YAML, not a mapping,
            uses YAML anchors or aliases (a template has no use for them) or
            holds a value JSON cannot carry (``.nan``, ``.inf``).
    """
    if not isinstance(source, str) or not source.strip():
        raise ValidationError("the template is empty")
    try:
        doc = _load_yaml(source, allow_aliases=False, document=False)
    except yaml.YAMLError as exc:
        raise ValidationError(f"the template is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValidationError("the template must be a YAML mapping (description, applies_to, gather, rules, ...)")
    _check_json_carries(doc, "the template")
    return doc


# A string the engine's parser could read as something else when it is not
# quoted: numbers (any base, with underscores, signs or exponents), dates,
# ``.inf``/``.nan``, and the null, boolean and YAML 1.1 boolean words. A superset
# of what yaml.v3 resolves: quoting a string that did not need it changes nothing.
_NEEDS_QUOTES_RE = re.compile(
    r"^(?:[-+]?\.?[0-9]\S*$|[-+]?\.(?:inf|nan)|(?:~|null|true|false|y|n|yes|no|on|off|<<)$)",
    re.IGNORECASE,
)


class _TemplateDumper(yaml.SafeDumper):
    """SafeDumper that quotes every string the engine could read as a non-string.

    PyYAML quotes only what YAML 1.1 reads as a non-string. ``"1e3"`` and
    ``"0o17"`` are text there but numbers to the engine, so they are quoted
    here. Every other value is written as ``yaml.safe_dump`` writes it.
    """

    def ignore_aliases(self, data: Any) -> bool:
        return True


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    quote = bool(_NEEDS_QUOTES_RE.match(data)) or _resolve_scalar(data)[0] != _STR_TAG
    return dumper.represent_scalar(_STR_TAG, data, style='"' if quote else None)


_TemplateDumper.add_representer(str, _represent_str)


def dump_template(data: dict[str, Any]) -> str:
    """Render a template mapping as YAML, in the key order it was written.

    Every string reads back as the same string in the engine, whatever it
    looks like (``"1e3"``, ``"0o17"``, ``"on"``, ``"2026-11-10"`` are quoted).

    Args:
        data: The template mapping.

    Returns:
        str: YAML text the engine accepts.
    """
    return yaml.dump(
        data, Dumper=_TemplateDumper, sort_keys=False, default_flow_style=False, allow_unicode=True,
    )


def _rendered_template(name: str, data: dict[str, Any]) -> str:
    """The YAML to validate for a template record, proven to be exactly that record.

    Validation sees the rendered text, the hive keeps ``data``. If reading the
    text back does not give ``data`` (a number in a text field, for example)
    the engine would be validating a different template than the one stored.
    """
    text = dump_template(data)
    try:
        same = json.dumps(parse_template_source(text)) == json.dumps(data)
    except ValidationError:
        same = False
    if not same:
        raise ValidationError(
            f"template {name!r} cannot be rendered as YAML that reads back identically (a number where the "
            "engine reads text, or a value YAML cannot spell); fix the record before validating it"
        )
    return text


class Investigation:
    """Investigation Engine client for LimaCharlie."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def oid(self) -> str:
        """The organization ID every call is made for."""
        return self._org.oid

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _call(
        self,
        verb: str,
        path: str,
        *,
        query: list[tuple[str, str]] | None = None,
        body: dict[str, Any] | None = None,
        write: bool = False,
        timeout: int | None = None,
        redact_body: bool = False,
    ) -> Any:
        """Make one engine call, mapping failures to :class:`InvestigationError`.

        A write is never replayed after a gateway timeout: the engine may
        already have started the work. ``redact_body`` keeps the request body
        out of the debug output (a body that carries a secret).
        """
        kwargs: dict[str, Any] = {"query_params": query or None, "timeout": timeout}
        if body is not None:
            try:
                kwargs["raw_body"] = json.dumps(body, allow_nan=False).encode()
            except ValueError as exc:
                raise ValidationError(f"the request holds a value JSON cannot carry: {exc}") from exc
            kwargs["content_type"] = "application/json"
        if write:
            kwargs["retry_gateway_timeout"] = False
        if redact_body:
            kwargs["redact_body"] = True
        try:
            return self._org.client.request(verb, f"investigate/{self.oid}/{path}", **kwargs)
        except LimaCharlieError as exc:
            raise _wrap_error(exc) from exc

    def _get(self, path: str, query: list[tuple[str, str]] | None = None, timeout: int | None = None) -> Any:
        return self._call("GET", path, query=query, timeout=timeout)

    @staticmethod
    def _q(**params: Any) -> list[tuple[str, str]]:
        """Build a query string list from the arguments that are set."""
        out: list[tuple[str, str]] = []
        for name, value in params.items():
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            out.append((name.rstrip("_"), str(value)))
        return out

    def get_stats(
        self,
        template: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        """Read the engine's performance statistics for the org.

        The numbers come from the engine's own records of runs, steps and
        actions. They describe what the engine did (volumes, durations, costs,
        and what happened to each action class per template); they do not
        judge whether a verdict was right.

        Args:
            template: Only runs of this template.
            since: Only runs created at or after this RFC 3339 time.
            until: Only runs created before this RFC 3339 time.

        Returns:
            dict: The statistics, including ``window`` (``truncated`` is true
                when more runs matched than the engine aggregates) and
                ``actions``, with ``by_class_state`` and ``by_template_class``
                (one row per template and action class). Times and counts are
                passed through as the engine sent them.

        Raises:
            InvestigationError: On any API failure.
        """
        return self._get("stats", self._q(template=template, since=since, until=until))

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------

    def get_authoring_kit(self, sections: list[str] | None = None) -> dict[str, Any]:
        """Fetch the authoring kit, whole or in sections.

        The whole kit is large (tens of thousands of tokens); ask for the
        sections you need.

        Args:
            sections: Any of :data:`KIT_SECTIONS`. None asks for the engine's
                default (everything except ``library``).

        Returns:
            dict: The kit, with a ``size`` entry saying what was returned.

        Raises:
            ValidationError: If a section name is not one the engine knows.
            InvestigationError: On any API failure.
        """
        if sections:
            unknown = [s for s in sections if s not in KIT_SECTIONS]
            if unknown:
                raise ValidationError(f"unknown kit section(s) {', '.join(unknown)}; choose from {', '.join(KIT_SECTIONS)}")
        query = self._q(sections=",".join(sections) if sections else None)
        return self._get("authoring-kit", query)

    def list_operators(self) -> dict[str, Any]:
        """List the operator catalogue with typed arguments and outputs.

        Returns:
            dict: ``operators`` (per operator: class, args, output, summary,
                availability for this org) and ``extension_requests``.
        """
        return self._get("operators")

    def list_packs(self, name: str | None = None) -> dict[str, Any]:
        """List the fact packs a plan or a wave can ``use``.

        Args:
            name: Return only this pack.

        Returns:
            dict: ``packs``, each with params, exports and cost class.
        """
        return self._get("packs", self._q(name=name))

    def list_engine_templates(self) -> dict[str, Any]:
        """List the templates the engine has loaded for this org.

        Returns:
            dict: ``templates`` with name, version, description, applies_to and status.
        """
        return self._get("templates")

    # ------------------------------------------------------------------
    # Org settings (the ``default`` record of the investigation_policy hive)
    # ------------------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        """Read the org's Investigation Engine settings, as the engine enforces them.

        The settings are the ``default`` record of the ``investigation_policy``
        hive: ``paused``, the circuit breaker, the run identity, notifications,
        the AI agent, budgets and case mode. Nothing in them overrides a
        template: what a template acts on is written in the template. Needs
        ``investigation.get`` + ``insight.evt.get``.

        Returns:
            dict: ``etag``, ``source`` (``default``, or ``builtin`` when there
                is no record), ``set_by`` and ``set_at`` (who last saved the
                record and when), ``paused``, ``circuit_breaker`` (``per_hour``,
                ``per_run``, ``used_last_hour``, ``tripped``,
                ``oldest_in_window``), ``identity`` and ``identity_readiness``,
                ``notify``, ``llm``, ``budgets``, ``case``, ``speculation`` and
                ``warnings`` (for example ``settings_rejected``). The answer
                reflects the record the engine enforces: the last good copy
                when the stored one is rejected.

        Raises:
            InvestigationError: On any API failure.
        """
        return self._get("settings")

    # ------------------------------------------------------------------
    # Pause of automatic actions (the ``paused`` field of the settings record)
    # ------------------------------------------------------------------

    def _policy(self) -> Hive:
        return Hive(self._org, POLICY_HIVE)

    def _read_settings_record(self) -> HiveRecord | None:
        try:
            return self._policy().get(SETTINGS_RECORD)
        except ApiError as exc:
            if is_record_not_found(exc):
                return None
            raise

    @staticmethod
    def _pause_view(record: HiveRecord | None) -> dict[str, Any]:
        view: dict[str, Any] = {"paused": False, "record": SETTINGS_RECORD}
        if record is None:
            return view
        data = record.data if isinstance(record.data, dict) else {}
        view["paused"] = record.enabled is True and data.get("paused") is True
        if record.enabled is not True:
            view["inactive_reason"] = "disabled"
        if record.expiry:
            # The hive deletes the whole record at its expiry, and the pause with it.
            view["expires"] = record.expiry
        view.update(etag=record.etag, last_author=record.last_author, last_modified=record.last_modified)
        return view

    @staticmethod
    def _paused_field(record: HiveRecord | None) -> bool:
        """What the record's ``paused`` field says, whether or not the engine reads the record."""
        data = record.data if record is not None and isinstance(record.data, dict) else {}
        return data.get("paused") is True

    def _write_paused(self, existing: HiveRecord | None, paused: bool) -> None:
        """Save ``paused`` on the settings record, conditional on the version read."""
        data: dict[str, Any] = {} if existing is None else json.loads(json.dumps(existing.data))
        data["paused"] = paused
        record = HiveRecord(
            name=SETTINGS_RECORD, data=data,
            enabled=True if existing is None else existing.enabled,
            etag=_CREATE_ONLY_ETAG if existing is None else existing.etag,
        )
        if existing is not None:
            # Metadata replaces the stored metadata wholesale: start from what is stored.
            record.tags, record.comment, record.ui_actions, record.expiry = (
                existing.tags, existing.comment, existing.ui_actions, existing.expiry,
            )
        self._policy().set(record)

    def _set_paused(self, paused: bool) -> dict[str, Any]:
        existing = self._read_settings_record()
        if existing is not None and not isinstance(existing.data, dict):
            # The engine cannot read it either, and what it falls back to is not ours to guess.
            raise ValidationError(
                f"the {SETTINGS_RECORD} record of {POLICY_HIVE} does not hold an object: fix it before pausing or resuming"
            )
        if paused and existing is not None and existing.enabled is not True:
            # The engine ignores a disabled record: writing the field would pause nothing.
            raise ValidationError(
                f"the {SETTINGS_RECORD} record of {POLICY_HIVE} is disabled, so the engine ignores it and a pause "
                "written on it would stop nothing: enable the record first"
            )
        # Resume looks at the field itself: a disabled record that still says paused would pause the org
        # again the day someone enables it.
        if self._paused_field(existing) == paused and (existing is None or not paused or existing.enabled is True):
            return {**self._pause_view(existing), "changed": False}
        if existing is not None and not existing.etag:
            raise ValidationError(
                f"the {SETTINGS_RECORD} record of {POLICY_HIVE} was returned without a version, so the write could "
                "not be conditional and could overwrite a concurrent edit: nothing was written"
            )
        try:
            self._write_paused(existing, paused)
        except ApiError as exc:
            if is_permission_denied(exc):
                raise
            # Someone may have saved the record between our read and the write: if it now says what we wanted,
            # so be it. Anything else (including a failed re-read) is the original failure.
            try:
                current = self._read_settings_record()
            except LimaCharlieError:
                raise exc
            if self._paused_field(current) == paused and (not paused or (current is not None and current.enabled is True)):
                return {**self._pause_view(current), "changed": False}
            raise
        try:
            after = self._read_settings_record()
        except LimaCharlieError as exc:
            raise InvestigationError(
                f"the {SETTINGS_RECORD} record of {POLICY_HIVE} was saved with paused={str(paused).lower()}, but reading it "
                f"back failed ({exc.raw_message}): check `investigate settings get`; repeating the command is safe",
                status_code=getattr(exc, "status_code", None),
                exit_code=exc.exit_code,
            ) from exc
        if self._paused_field(after) != paused or (paused and (after is None or after.enabled is not True)):
            # Expired, deleted or changed by someone else between our write and this read: never report success.
            raise InvestigationError(
                f"the {SETTINGS_RECORD} record of {POLICY_HIVE} was saved but does not read back as "
                f"paused={str(paused).lower()}: another writer or an expiry changed it; check `investigate settings get`",
                status_code=409,
            )
        return {**self._pause_view(after), "changed": True}

    @_policy_record_errors
    def get_pause(self) -> dict[str, Any]:
        """Read the ``paused`` field of the settings record straight from the hive.

        This does not need the engine. :meth:`get_settings` is the answer the
        engine enforces (it also says who saved the record and when). Needs
        ``investigation_policy.get``.

        Returns:
            dict: ``paused`` (bool) and ``record`` (the record name). When the
                record exists: ``etag``, ``last_author``, ``last_modified``, and
                ``inactive_reason`` (``disabled``) when the record exists but
                the engine ignores it, and ``expires`` when the record carries
                an expiry (the hive deletes the whole record then, the pause
                with it).

        Raises:
            InvestigationError: On any API failure.
        """
        return self._pause_view(self._read_settings_record())

    @_policy_record_errors
    def pause_actions(self) -> dict[str, Any]:
        """Pause the org: nothing acts alone while ``paused`` is true on the settings record.

        Runs still investigate. An action that would have acted alone waits for
        a person, who can still approve, deny and undo. Only the ``paused``
        field changes: every other field and the record's metadata are kept.
        The write is conditional on the record read, so a concurrent edit is
        never overwritten; a concurrent pause that wins the race counts as
        done. A record that does not exist yet is created holding only
        ``paused: true``. A disabled record is refused (the engine ignores it).
        Needs ``investigation_policy.get`` and ``investigation_policy.set``.

        Returns:
            dict: The state after the write (:meth:`get_pause`) and ``changed``.

        Raises:
            ValidationError: If the record is disabled or does not hold an object.
            InvestigationError: On any API failure.
        """
        return self._set_paused(True)

    @_policy_record_errors
    def resume_actions(self) -> dict[str, Any]:
        """Lift the pause: set ``paused`` to false on the settings record.

        Actions that waited while paused keep waiting for a person. Same
        conditional write as :meth:`pause_actions`. With no record there is
        nothing to lift. Needs ``investigation_policy.get`` and
        ``investigation_policy.set``.

        Returns:
            dict: The state after the write (:meth:`get_pause`) and ``changed``
                (False when it was not paused).

        Raises:
            ValidationError: If the record does not hold an object.
            InvestigationError: On any API failure.
        """
        return self._set_paused(False)

    # ------------------------------------------------------------------
    # Plan validation and dry runs
    # ------------------------------------------------------------------

    def validate_plan(self, source: str) -> dict[str, Any]:
        """Type-check a template without running anything.

        Args:
            source: The template YAML.

        Returns:
            dict: ``valid``, ``errors`` and ``warnings`` (each ``{code, path,
                message, suggestion?}``), the worst-case cost, an ``estimate`` and
                ``ai_rules`` (the ids of the rules that read an ``ask_ai``
                answer: they decide only where ``ai_may_decide`` allows).
                ``resolved_packs`` preserves scope/name/version/digest for every
                resolved version-only pack pin. A template in the format the
                engine had before (``facts``, ``proofs``, ...) is refused with
                ``legacy_template_format``.
        """
        return self._call("POST", "plans/validate", body={"yaml": source})

    def test_plan(
        self,
        samples: list[dict[str, Any]],
        *,
        template: str | None = None,
        inline: str | None = None,
        overrides: dict[str, Any] | None = None,
        strict: bool = False,
        mode: str | None = None,
        wait_seconds: int = 5,
    ) -> dict[str, Any]:
        """Start a dry run of a plan on real past alerts.

        Nothing is written: no run, case, label or action. The test runs the
        plan's read-only operators under the caller's own token. Nothing
        blocks on the result: it is information for the author.

        Args:
            samples: Each one of ``{detection_id}``, ``{case_id}``,
                ``{detect_cat, last}`` or ``{inputs, expected}``; at most 25
                after expansion.
            template: A stored template (draft or active). Give this or ``inline``.
            inline: Template YAML to test as a draft.
            overrides: Tighten-only budget overrides.
            strict: Refuse the test when ``overrides`` would loosen the org's
                budgets; without it the loosening part is ignored.
            mode: ``triage`` (default) or ``full``.
            wait_seconds: Let the call wait this long for a fast test (0..10).

        Returns:
            dict: The test object: ``test_id``, ``state`` (running, done,
                failed, invalid), ``validation``, ``results``, ``summary``,
                ``next`` and ``done``. Each result has a ``verdict`` (the
                ``outcome``, ``decided_by`` {kind, rule}, the AI's
                ``recommendation`` and what was ``missing``), the analyst's
                ``expected`` label and ``agreement`` {rule, ai}. The
                ``summary`` has ``decided_by_rules``, ``rule_share``, per
                rule id ``rules`` {decided, agree, disagree}, ``ai``
                {recommended, agree, disagree, unclear}, ``by_outcome``,
                ``unknown_reasons`` and ``cost_per_sample``. Initial
                ``validation`` retains ``resolved_packs``.

        Raises:
            ValidationError: If not exactly one of ``template``/``inline`` is
                given, or there are no samples.
        """
        if bool(template) == bool(inline):
            raise ValidationError("give exactly one of a stored template or an inline template")
        if not samples:
            raise ValidationError("give at least one sample (detection, case, category or inputs)")
        _check_wait(wait_seconds)
        request: dict[str, Any] = {"samples": samples, "wait_seconds": wait_seconds}
        if template:
            request["template"] = template
        else:
            request["inline"] = inline
        if overrides:
            request["overrides"] = overrides
        if strict:
            request["strict"] = True
        if mode:
            request["mode"] = mode
        return self._call(
            "POST", "test-plan", body=request, write=True, timeout=wait_seconds + _WAIT_MARGIN,
        )

    def get_test_plan(self, test_id: str, after: int = 0, wait: int = 0) -> dict[str, Any]:
        """Read a plan test, optionally waiting for more results.

        Args:
            test_id: The ``test_id`` of :meth:`test_plan`.
            after: Number of results already seen.
            wait: Seconds to wait (0..10) for another result or the end.

        Returns:
            dict: The same test object as :meth:`test_plan`.
        """
        _check_id("test id", test_id)
        _check_wait(wait)
        return self._get(
            f"test-plan/{_quote(test_id, safe='')}", self._q(after=after, wait=wait), timeout=wait + _WAIT_MARGIN,
        )

    def wait_for_test(
        self,
        test: dict[str, Any],
        timeout: float = 600,
        wait: int = MAX_POLL_WAIT,
        sleep: Any = time.sleep,
    ) -> dict[str, Any]:
        """Poll a plan test until it is over or the timeout elapses.

        Args:
            test: The object :meth:`test_plan` returned.
            timeout: Give up after this many seconds and return the latest state.
            wait: Seconds each poll may wait on the engine (0..10).
            sleep: Pause between polls that return at once (injectable for tests).

        Returns:
            dict: The latest test object. ``done`` tells whether it finished.
        """
        deadline = time.monotonic() + timeout
        while not test.get("done") and test.get("state") not in ("invalid", "failed", "done"):
            if time.monotonic() >= deadline:
                break
            seen = test.get("samples_done") or 0
            test = self.get_test_plan(test["test_id"], after=seen, wait=wait)
            if wait == 0:
                sleep(1)
        return test

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def start_run(self, request: dict[str, Any]) -> dict[str, Any]:
        """Start an investigation run.

        Args:
            request: The run request: ``trigger``, ``plan`` (``template`` or
                ``inline``; omit it to let the engine pick the active template
                whose ``applies_to`` matches the trigger; ``{"auto": true}`` is
                refused for a person's run), ``inputs``, ``urgency`` (``low``,
                ``medium``, ``high`` or ``critical``), ``mode``, ``case``,
                ``idempotency_key``, ``wait_seconds``, optional ``trust``
                (``lookups`` and ``values`` lists), additive to template trust
                for this run only, and ``parent_run`` (the run whose AI session
                makes this start: the engine then asks no AI agent for the
                new run).

        Returns:
            dict: ``run`` and ``joined`` (True when an open run of the same
                key absorbed the request instead of a new one starting).
        """
        if "trust" in request:
            trust = request["trust"]
            normalized = {}
            if trust is not None:
                if not isinstance(trust, dict):
                    raise ValidationError("trust must be an object")
                if any(key not in {"lookups", "values"} for key in trust):
                    raise ValidationError("trust accepts only lookups and values")
                for key, maximum in (("lookups", 64), ("values", 100)):
                    if key not in trust:
                        continue
                    entries = trust[key]
                    if not isinstance(entries, list):
                        raise ValidationError(f"trust.{key} must be a list of nonblank strings")
                    if len(entries) > maximum:
                        raise ValidationError(f"trust.{key} accepts at most {maximum} entries")
                    if any(not isinstance(entry, str) or not entry.strip() for entry in entries):
                        raise ValidationError(f"trust.{key} must contain only nonblank strings")
                    if entries:
                        normalized[key] = list(entries)
            request = dict(request)
            if normalized:
                request["trust"] = normalized
            else:
                request.pop("trust")
        wait = request.get("wait_seconds") or 0
        return self._call("POST", "runs", body=request, write=True, timeout=max(_WAIT_MARGIN, int(wait) + _WAIT_MARGIN))

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Read a run (state, phase, outcome, actions, usage).

        Args:
            run_id: The run id.

        Returns:
            dict: The run plus its ``critical_path``. Its ``verdict`` has the
                ``outcome`` (one of :data:`RUN_OUTCOMES`), ``label`` (false_positive,
                true_positive or inconclusive), ``decided``, ``decided_by``
                {kind, rule, say}, the AI's ``recommendation`` {label,
                self_rated_confidence, rationale, citations, by} when it only
                recommends, and ``missing`` [{step, reason, needed_by, ask}].
                ``ai_may_decide`` is the mode the run started with and
                ``ai_agent`` the AI agent it uses. ``self_rated_confidence`` is
                the AI's own rating: shown, never used.
        """
        return self._get(f"runs/{_quote(_check_id('run id', run_id), safe='')}")

    def list_runs(
        self,
        *,
        state: str | None = None,
        outcome: str | None = None,
        verdict: str | None = None,
        template: str | None = None,
        trigger: str | None = None,
        entity: str | None = None,
        started_by: str | None = None,
        idempotency_key: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List one page of the org's runs, newest first.

        Args:
            state: Only runs in this state.
            outcome: Only runs that ended with this outcome (one of
                :data:`RUN_OUTCOMES`) or ``undecided`` (nothing settled yet).
            verdict: Only runs with this verdict label (``true_positive``,
                ``false_positive``, ``inconclusive``).
            template: Only runs of this template.
            trigger: Only runs with this trigger source.
            entity: Only runs about this entity.
            started_by: Only runs started by this identity (``user:<uid>``).
            idempotency_key: Only the run started with this key.
            since: Only runs created at or after this RFC 3339 time.
            until: Only runs created before this RFC 3339 time.
            limit: Page size, 1..200 (engine default 50).
            cursor: ``next_cursor`` of the previous page.

        Returns:
            dict: ``runs`` and ``next_cursor`` ("" on the last page).

        Raises:
            ValidationError: If ``limit`` is out of range or ``outcome`` is not an outcome.
        """
        if limit is not None and not 1 <= limit <= 200:
            raise ValidationError("limit must be between 1 and 200")
        if outcome is not None and outcome != "undecided" and outcome not in RUN_OUTCOMES:
            raise ValidationError(f"outcome must be undecided or one of {', '.join(RUN_OUTCOMES)}")
        return self._get(
            "runs",
            self._q(
                state=state, outcome=outcome, verdict=verdict, template=template, trigger=trigger, entity=entity,
                started_by=started_by, idempotency_key=idempotency_key, since=since, until=until,
                limit=limit, cursor=cursor,
            ),
        )

    def iter_runs(self, **filters: Any) -> Iterator[dict[str, Any]]:
        """Walk every run matching the filters, following cursors.

        Args:
            **filters: The keyword arguments of :meth:`list_runs`, ``cursor`` included.

        Yields:
            dict: One run at a time.

        Raises:
            ApiError: If a cursor repeats or the 10,000-cursor history limit is exceeded.
        """
        seen = {filters["cursor"]} if filters.get("cursor") else set()
        while True:
            page = self.list_runs(**filters)
            yield from page.get("runs") or []
            nxt = page.get("next_cursor") or ""
            if not nxt:
                return
            if nxt in seen:
                raise ApiError("Run listing did not advance: the engine returned a repeated cursor.")
            if len(seen) >= _MAX_PAGINATION_CURSORS:
                raise ApiError("Run listing exceeded the cursor history limit; resume with an explicit cursor.")
            seen.add(nxt)
            filters["cursor"] = nxt

    def get_run_steps(self, run_id: str, values: bool = False) -> dict[str, Any]:
        """Read a run's step log, plan graph and outcome timeline.

        Args:
            run_id: The run id.
            values: Include customer values (default: structure only).

        Returns:
            dict: ``steps`` (each with a ``narrative`` {why, found, used}),
                ``critical_path``, ``edges``, ``usage``, ``timeline`` (the
                outcome over time) and ``ai_may_decide``.
        """
        return self._get(
            f"runs/{_quote(_check_id('run id', run_id), safe='')}/steps", self._q(values=True if values else None),
        )

    def get_run_case(self, run_id: str) -> dict[str, Any]:
        """Read the case document a run wrote.

        Args:
            run_id: The run id.

        Returns:
            dict: The case view; a 404 ``not_found`` until the run has one.
        """
        return self._get(f"runs/{_quote(_check_id('run id', run_id), safe='')}/case")

    def get_run_events(self, run_id: str, after: int = 0, wait: int = 0, limit: int | None = None) -> dict[str, Any]:
        """Read a run's events after a sequence number (one long poll).

        Args:
            run_id: The run id.
            after: Return events with a greater ``seq``.
            wait: Seconds to wait (0..10) for the first new event.
            limit: Events per page, 1..500.

        Returns:
            dict: ``events``, ``next`` (pass as ``after`` next time) and
                ``done`` (the run is over and everything was returned).

        Raises:
            ValidationError: If an argument is out of range.
        """
        _check_wait(wait)
        if after < 0:
            raise ValidationError("after must be 0 or more")
        if limit is not None and not 1 <= limit <= MAX_EVENTS_LIMIT:
            raise ValidationError(f"limit must be between 1 and {MAX_EVENTS_LIMIT}")
        return self._get(
            f"runs/{_quote(_check_id('run id', run_id), safe='')}/events",
            self._q(after=after, wait=wait, limit=limit),
            timeout=wait + _WAIT_MARGIN,
        )

    def iter_run_events(
        self,
        run_id: str,
        after: int = 0,
        wait: int = MAX_POLL_WAIT,
        limit: int | None = None,
        timeout: float | None = None,
        state: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Follow a run's events until the run is over.

        Args:
            run_id: The run id.
            after: Start after this sequence number.
            wait: Seconds each poll waits for a new event (0..10).
            limit: Events per poll, 1..500.
            timeout: Stop after this many seconds (None: follow to the end).
            state: Dict the generator fills with ``next`` (resume point),
                ``done`` and ``timed_out`` so the caller can report how it ended.

        Yields:
            dict: Events in order, each ``{seq, at, type, data}``.
        """
        state = state if state is not None else {}
        state.update(next=after, done=False, timed_out=False)
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            page = self.get_run_events(run_id, after=state["next"], wait=wait, limit=limit)
            for event in page.get("events") or []:
                yield event
            state["next"] = page.get("next", state["next"])
            if page.get("done"):
                state["done"] = True
                return
            if deadline is not None and time.monotonic() >= deadline:
                state["timed_out"] = True
                return
            if wait == 0:
                time.sleep(1)

    def cancel_run(self, run_id: str, revert_leases: bool = False) -> dict[str, Any]:
        """Cancel a run.

        Args:
            run_id: The run id.
            revert_leases: Also revert the leases of the run's active actions.

        Returns:
            dict: The cancelled run.
        """
        body = {"revert_leases": True} if revert_leases else {}
        return self._call("POST", f"runs/{_quote(_check_id('run id', run_id), safe='')}/cancel", body=body, write=True)

    def delete_run(self, run_id: str) -> dict[str, Any]:
        """Delete a run (requires investigation.set and insight.evt.get).

        Args:
            run_id: The run id.

        Returns:
            dict: The engine's deletion response.

        Raises:
            ValidationError: If the run id is invalid.
            InvestigationError: If the API refuses deletion or the request fails.
        """
        try:
            return self._call("DELETE", f"runs/{_quote(_check_id('run id', run_id), safe='')}", write=True)
        except InvestigationError as exc:
            if exc.status_code == 404 and not exc.error_code:
                # Without an engine code the API did not serve the route at all: either the feature is
                # off or this API deployment predates run deletion.
                # Rebuilt, not patched: the message text embeds the suggestion it was built with.
                raise InvestigationError(
                    exc.raw_message,
                    status_code=exc.status_code,
                    issues=exc.issues,
                    warnings=exc.warnings,
                    response_body=exc.response_body,
                    suggestion=_DELETE_ROUTE_HINT,
                    exit_code=exc.exit_code,
                ) from exc
            raise

    # ------------------------------------------------------------------
    # The run queue
    # ------------------------------------------------------------------

    def _queue_call(self, verb: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """One run-queue call; an engine that does not serve the queue yet is said plainly."""
        try:
            return self._call(verb, path, **kwargs)
        except InvestigationError as exc:
            if exc.status_code == 501 and exc.error_code == "not_implemented":
                raise InvestigationError(
                    QUEUE_NOT_AVAILABLE,
                    status_code=exc.status_code,
                    issues=exc.issues,
                    warnings=exc.warnings,
                    response_body=exc.response_body,
                    suggestion="",
                    exit_code=exc.exit_code,
                ) from exc
            raise

    def get_queue(self) -> dict[str, Any]:
        """Read the org's run queue (requires investigation.get and insight.evt.get).

        A start waits in the queue when the org already runs ``limits.max_parallel_runs``
        investigations. The totals are exact, never a sum of a page.

        Returns:
            dict: ``queued``, ``claimed``, ``running`` and ``max_parallel_runs``;
                ``oldest_enqueued_at`` (None when nothing waits) and
                ``oldest_wait_ms``; ``by_band`` (urgency to count);
                ``by_rule`` and ``by_template`` (each row
                ``{rule | template, queued, oldest_enqueued_at}``; the row of
                starts no rule made has no ``rule`` key); ``hour``
                (``started``, ``runs_per_hour`` (None: no cap), ``flushed``,
                ``capped``, ``start_failed``, ``resets_at``); ``flushes``
                (recent flushes and their progress); ``as_of``.

        Raises:
            InvestigationError: ``status_code`` 501 when the engine of this
                deployment does not serve the queue yet, or the API refuses.
        """
        return self._queue_call("GET", "queue")

    def flush_queue(
        self,
        *,
        rule: str | None = None,
        template: str | None = None,
        all: bool = False,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Flush queued starts (requires investigation.set and insight.evt.get).

        Cancels the starts that are queued and not yet running: each becomes a
        terminal ``flushed`` run (who, when and the note are kept). Running
        investigations are not touched, and a start that arrives after the flush
        began queues normally. This cannot be undone. The call is sent once,
        never retried by the SDK.

        Args:
            rule: Flush the starts of this detection rule.
            template: Flush the starts of this template.
            all: Flush every queued start of the org.
            note: Why (kept on every flushed run and in the audit log).

        Exactly one of ``rule``, ``template`` and ``all`` is required.

        Returns:
            dict: ``flush_id``, ``flushed`` (how many so far) and ``done``
                (false while a large flush continues in the engine; see
                ``flushes`` of :meth:`get_queue`), plus ``scope``, ``by``,
                ``actor``, ``note``, ``at``, ``cutoff`` and, once finished,
                ``done_at``. ``replayed`` is True when an identical flush
                made in the last minute answered this call: it flushed
                nothing itself.

        Raises:
            ValidationError: If the scope is not exactly one of the three.
            InvestigationError: ``status_code`` 501 when the engine of this
                deployment does not serve the queue yet, or the API refuses.
        """
        scopes = [("rule", rule), ("template", template)]
        given = [name for name, value in scopes if value is not None] + (["all"] if all else [])
        if len(given) != 1:
            raise ValidationError("a flush needs exactly one of rule, template or all")
        body: dict[str, Any] = {}
        for name, value in scopes:
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise ValidationError(f"the {name} to flush must be a non-empty name")
                body[name] = value
        if all:
            body["all"] = True
        if note:
            body["note"] = note
        return self._queue_call("POST", "queue/flush", body=body, write=True)

    # ------------------------------------------------------------------
    # AI agent answers
    # ------------------------------------------------------------------

    def submit_agent_answer(
        self,
        run_id: str,
        request_id: str,
        token: str,
        answer: dict[str, Any],
    ) -> dict[str, Any]:
        """Answer the AI agent step of a run (requires investigation.get).

        An ``ai_agent`` step of a template starts one of the org's AI agents as
        an AI Session and waits for its answer. The session gets the run id,
        the request id and a one-time answer token in its environment
        (``LC_IE_RUN_ID``, ``LC_IE_REQUEST_ID``, ``LC_IE_ANSWER_TOKEN``) and
        answers here. The answer holds the fields the step's ``returns`` declares
        and a short ``rationale``. An answer that does not match is refused with
        nothing recorded: fix it and send it again before the deadline. A valid
        answer is taken once.

        The token is a secret: it is sent in the request body only, is kept out
        of the debug output, and is never part of an error.

        Args:
            run_id: The run the session was started for (``LC_IE_RUN_ID``).
            request_id: The step's request (``LC_IE_REQUEST_ID``).
            token: The answer token (``LC_IE_ANSWER_TOKEN``).
            answer: The answer object.

        Returns:
            dict: ``run_id``, ``request_id`` and ``state`` (``answered``).

        Raises:
            ValidationError: If an id, the token or the answer is malformed.
            InvestigationError: ``error_code`` ``invalid_answer`` (400, with
                ``fields`` when the API relays it; the message always names
                each field and why), ``forbidden`` (403, wrong token), ``not_found``
                (404), ``already_answered`` / ``deadline_passed`` /
                ``not_waiting`` (409, too late) or ``not_implemented`` (501).
                ``suggestion`` says what each means. The call is never replayed after a
                timeout (only after a 401 token refresh, which the API refused before
                reading anything).
        """
        run_id = _check_id("run id", run_id)
        request_id = _check_id("request id", request_id)
        if not isinstance(token, str) or not token.strip():
            raise ValidationError("the answer token is required")
        if not isinstance(answer, dict):
            raise ValidationError("the answer must be a JSON object")
        path = f"runs/{_quote(run_id, safe='')}/agent-answers/{_quote(request_id, safe='')}"
        try:
            return self._call("POST", path, body={"token": token, "answer": answer}, write=True, redact_body=True)
        except InvestigationError as exc:
            if exc.error_code:
                meaning = AGENT_ANSWER_MEANINGS.get(exc.error_code)
            elif exc.status_code == 403:
                meaning = AGENT_ANSWER_MEANINGS[None]
            elif exc.status_code == 404:
                meaning = _ANSWER_ROUTE_HINT
            else:
                meaning = None
            if meaning is None:
                raise
            raise InvestigationError(
                exc.raw_message,
                status_code=exc.status_code,
                issues=exc.issues,
                warnings=exc.warnings,
                response_body=exc.response_body,
                suggestion=meaning,
                exit_code=exc.exit_code,
            ) from exc

    # ------------------------------------------------------------------
    # Waves
    # ------------------------------------------------------------------

    def run_wave(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run a wave: a batch of operator and fact-pack questions in one call.

        An invalid wave raises :class:`InvestigationError` whose ``issues``
        carry the engine's coded errors.

        Args:
            request: ``steps`` (each with ``id`` and one of ``op`` or ``use``,
                ``args``, ``select``, ``limit``), ``stop_when``,
                ``deadline_ms``, ``inputs``, ``full``, ``validate_only``.

        Returns:
            dict: ``results``, ``stopped_by``, ``usage`` and ``compact``; with
                ``validate_only``, the validation report.
        """
        if "trust" in request:
            raise ValidationError("request-level trust is supported only by run start")
        if not isinstance(request.get("steps"), list) or not request["steps"]:
            raise ValidationError("a wave needs a non-empty 'steps' list")
        deadline = request.get("deadline_ms") or 30000
        return self._call("POST", "waves", body=request, write=True, timeout=max(130, int(deadline / 1000) + _WAIT_MARGIN))

    # ------------------------------------------------------------------
    # Actions (the approvals inbox)
    # ------------------------------------------------------------------

    def list_actions(
        self,
        state: str | list[str] | None = None,
        action_class: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List the org's actions across all runs, what needs a person first.

        Args:
            state: One action state or several (``awaiting_approval``, ``proposed``, ...).
            action_class: Only this action class.
            run_id: Only the actions of this run.
            limit: Page size, 1..200.
            cursor: ``next_cursor`` of the previous page.

        Returns:
            dict: ``actions`` (each with a ``run`` summary) and ``next_cursor``.
        """
        if limit is not None and not 1 <= limit <= 200:
            raise ValidationError("limit must be between 1 and 200")
        if run_id:
            _check_id("run id", run_id)
        if isinstance(state, (list, tuple)):
            state = ",".join(state)
        return self._get("actions", self._q(state=state, class_=action_class, run_id=run_id, limit=limit, cursor=cursor))

    def iter_actions(self, **filters: Any) -> Iterator[dict[str, Any]]:
        """Walk every action matching the filters, following cursors.

        Args:
            **filters: The keyword arguments of :meth:`list_actions`, ``cursor`` included.

        Yields:
            dict: One action at a time.

        Raises:
            ApiError: If a cursor repeats or the 10,000-cursor history limit is exceeded.
        """
        seen = {filters["cursor"]} if filters.get("cursor") else set()
        while True:
            page = self.list_actions(**filters)
            yield from page.get("actions") or []
            nxt = page.get("next_cursor") or ""
            if not nxt:
                return
            if nxt in seen:
                raise ApiError("Action listing did not advance: the engine returned a repeated cursor.")
            if len(seen) >= _MAX_PAGINATION_CURSORS:
                raise ApiError("Action listing exceeded the cursor history limit; resume with an explicit cursor.")
            seen.add(nxt)
            filters["cursor"] = nxt

    def decide_action(
        self, run_id: str, action_id: str, verb: str, note: str | None = None, seconds: int | None = None,
    ) -> dict[str, Any]:
        """Approve, deny, revert, extend or confirm an action.

        The caller also needs the permission of the action's class.

        Args:
            run_id: The run the action belongs to.
            action_id: The action id.
            verb: One of :data:`ACTION_VERBS`.
            note: A reason (deny, revert).
            seconds: How long to extend a lease (extend).

        Returns:
            dict: The action after the decision.

        Raises:
            ValidationError: If the verb is unknown.
        """
        if verb not in ACTION_VERBS:
            raise ValidationError(f"verb must be one of {', '.join(ACTION_VERBS)}")
        body: dict[str, Any] = {}
        if note:
            body["note"] = note
        if seconds is not None:
            body["seconds"] = seconds
        path = f"runs/{_quote(_check_id('run id', run_id), safe='')}/actions/{_quote(_check_id('action id', action_id), safe='')}/{verb}"
        return self._call("POST", path, body=body, write=True)

    # ------------------------------------------------------------------
    # Templates (hive records)
    # ------------------------------------------------------------------

    def get_pack(self, name: str) -> dict[str, Any]:
        """Read an org-authored pack's exact YAML and revision.

        Args:
            name: Pack record name.

        Returns:
            dict: Name, YAML, etag and enabled state.
        """
        record = Hive(self._org, PACK_HIVE).get(name)
        return {"name": name, "yaml": (record.data or {}).get("yaml"),
                "etag": record.etag, "enabled": record.enabled}

    def save_pack(self, name: str, source: str, *, etag: str | None = None) -> dict[str, Any]:
        """Create a pack or conditionally replace its exact YAML source.

        Hive validates the envelope, pack schema and managed-name collisions.
        Permissions reuse investigation_plan.set. No source is reserialized.

        Args:
            name: Pack record key, matching the name in YAML.
            source: Complete pack YAML, including its positive version.
            etag: Revision from get_pack; omit to create only.

        Returns:
            dict: Hive write response.

        Raises:
            ValidationError: If name, source or revision is empty or invalid.
        """
        if not isinstance(name, str) or not TEMPLATE_NAME_RE.fullmatch(name):
            raise ValidationError("Invalid pack name")
        if not isinstance(source, str) or not source.strip():
            raise ValidationError("Pack YAML is required")
        if etag is not None and not etag:
            raise ValidationError("etag must not be empty")
        return Hive(self._org, PACK_HIVE).set(HiveRecord(
            name=name, data={"yaml": source}, enabled=True if etag is None else None,
            etag=etag if etag is not None else _CREATE_ONLY_ETAG))

    def delete_pack(self, name: str) -> dict[str, Any]:
        """Delete an org pack using investigation_plan.del.

        Args:
            name: Pack record name.
        """
        return Hive(self._org, PACK_HIVE).delete(name)

    def _plans(self) -> Hive:
        return Hive(self._org, PLAN_HIVE)

    @_template_record_errors
    def get_template(self, name: str) -> dict[str, Any]:
        """Read a stored template.

        Args:
            name: The template (record) name.

        Returns:
            dict: ``name``, ``status``, ``yaml`` (the source), ``data`` (the
                record), ``etag``, ``tags``, ``comment``, ``enabled`` and
                modification info.

        Raises:
            ApiError: If the record does not exist or cannot be read.
        """
        return self._template_view(self._plans().get(name))

    @staticmethod
    def _template_view(record: HiveRecord) -> dict[str, Any]:
        data = record.data or {}
        return {
            "name": record.name,
            "status": data.get("status") or STATUS_DRAFT,
            "version": data.get("version"),
            "yaml": dump_template(data),
            "data": data,
            "etag": record.etag,
            "tags": record.tags or [],
            "comment": record.comment,
            "enabled": record.enabled,
            "last_author": record.last_author,
            "last_modified": record.last_modified,
        }

    @_template_record_errors
    def save_template(
        self,
        name: str,
        source: str,
        *,
        status: str | None = None,
        overwrite: bool = False,
        comment: str | None = None,
        tags: list[str] | None = None,
        ignore_source_status: bool = False,
    ) -> dict[str, Any]:
        """Validate a template and write it as an ``investigation_plan`` record.

        The record is a DRAFT unless ``status="active"`` is passed. The
        source may not say ``status: active`` by itself: activating is an
        explicit act of a person, not something a template can smuggle in.
        Nothing is written when validation reports an error, when the record
        exists and ``overwrite`` is false, or when the record is active and
        the new status is not (an active template is replaced only by an
        explicit ``status="active"`` with ``overwrite=True``).

        Args:
            name: Record name: lowercase letters, digits, ``-`` and ``_``, at most 64.
            source: The template YAML, without a ``name:`` key.
            status: ``draft`` (default) or ``active``.
            overwrite: Replace an existing draft.
            comment: Stored as the record's comment (what it was tested on).
            tags: Tags to add to the record (an existing record keeps its own).
            ignore_source_status: Replace whatever ``status`` the source says
                with ``status`` instead of refusing an ``active`` source. For
                installing library templates, which are written as active.

        Returns:
            dict: ``saved`` (bool). When true: ``name``, ``status``, ``etag``,
                ``warnings``. When false: ``reason`` and, for an invalid
                template, the ``validation`` report.

        Raises:
            ValidationError: For a malformed name, status or source.
            InvestigationError: On engine failures.
            ApiError: On hive failures.
        """
        if not TEMPLATE_NAME_RE.match(name or ""):
            raise ValidationError(
                "name must be lowercase letters, digits, - and _, start with a letter or digit and be at most 64 characters"
            )
        explicit_active = status == STATUS_ACTIVE
        if status not in (None, STATUS_DRAFT, STATUS_ACTIVE):
            raise ValidationError("status must be draft or active")
        data = parse_template_source(source)
        if "name" in data:
            raise ValidationError(
                "the template has a `name:` key; the name is the record's name and is not part of the YAML"
            )
        written_status = data.get("status")
        if written_status not in (None, STATUS_DRAFT, STATUS_ACTIVE):
            raise ValidationError(f"the template sets status to {written_status!r}; use draft or active")
        if written_status == STATUS_ACTIVE and not explicit_active and not ignore_source_status:
            return {
                "saved": False,
                "reason": "the template sets status: active. A template cannot activate itself: leave status out "
                          "(it is saved as a draft), or pass status=active explicitly as the person who reviewed it.",
            }
        final_status = STATUS_ACTIVE if explicit_active else STATUS_DRAFT
        data["status"] = final_status

        report = self.validate_plan(_rendered_template(name, data))
        if report.get("valid") is not True or report.get("errors"):
            return {
                "saved": False,
                "reason": "the template does not validate; fix every error and call again",
                "validation": report,
            }

        hive = self._plans()
        record = HiveRecord(name=name, data=data)
        try:
            existing = hive.get(name)
        except ApiError as exc:
            if not is_record_not_found(exc):
                raise
            existing = None
        if existing is None:
            record.etag = _CREATE_ONLY_ETAG
        else:
            stored = (existing.data or {}).get("status") or STATUS_DRAFT
            if stored == STATUS_ACTIVE and final_status != STATUS_ACTIVE:
                return {
                    "saved": False,
                    "reason": f"template {name!r} is active: a draft never replaces an active template. "
                              "Save your version under a new name; a person decides whether it replaces the active one.",
                }
            if stored not in (STATUS_DRAFT, STATUS_ACTIVE):
                return {"saved": False, "reason": f"record {name!r} has status {stored!r}, which is neither draft nor active: save under another name"}
            if not overwrite:
                return {
                    "saved": False,
                    "reason": f"a {stored} template named {name!r} already exists: pass overwrite to replace it, or save under another name",
                }
            record.etag = existing.etag
        if tags or comment:
            # Metadata replaces the stored metadata wholesale, and a block
            # sent without `enabled` is stored as disabled: start from what is
            # stored and add to it.
            if existing is not None:
                record.tags, record.comment, record.expiry = existing.tags, existing.comment, existing.expiry
                record.ui_actions = existing.ui_actions
            record.enabled = True if existing is None or existing.enabled is None else existing.enabled
            if tags:
                record.tags = list(dict.fromkeys((record.tags or []) + tags))
            if comment:
                record.comment = comment
        try:
            hive.set(record)
        except ApiError:
            # A write the hive applied whose answer was lost, then replayed with
            # its now stale etag, fails although the record is saved.
            try:
                now = hive.get(name)
                landed = (
                    (now.data or {}) == data
                    and (not comment or now.comment == record.comment)
                    and (not tags or set(tags) <= set(now.tags or []))
                )
            except LimaCharlieError:
                landed = False
            if not landed:
                raise

        # Say what is stored, not what was sent.
        stored_record = hive.get(name)
        stored_status = (stored_record.data or {}).get("status") or STATUS_DRAFT
        if stored_status != final_status:
            raise ApiError(
                f"the record {name!r} was written but its status reads {stored_status!r}, not {final_status!r}: "
                "have a person check it in the console"
            )
        return {
            "saved": True,
            "name": name,
            "status": stored_status,
            "etag": stored_record.etag,
            "last_author": stored_record.last_author,
            "warnings": report.get("warnings") or [],
            "next_step": (
                "A draft runs only through a test or a run a person starts, and only suggests its actions (none is executed). "
                "A person reviews it and promotes it to active."
                if stored_status == STATUS_DRAFT else "The template is active."
            ),
        }

    @_template_record_errors
    def promote_template(self, name: str) -> dict[str, Any]:
        """Make a stored draft template active.

        This is the person's decision step. The stored template is validated
        again first and nothing changes when it has errors. The write is
        conditional on the etag that was read, so a concurrent edit is not
        overwritten.

        Args:
            name: The template (record) name.

        Returns:
            dict: ``promoted`` (bool), ``name``, ``status`` and, when not
                promoted, ``reason``/``validation``.
        """
        hive = self._plans()
        record = hive.get(name)
        data = dict(record.data or {})
        if (data.get("status") or STATUS_DRAFT) == STATUS_ACTIVE:
            return {"promoted": False, "name": name, "status": STATUS_ACTIVE, "reason": "the template is already active"}
        data["status"] = STATUS_ACTIVE
        report = self.validate_plan(_rendered_template(name, data))
        if report.get("valid") is not True or report.get("errors"):
            return {"promoted": False, "name": name, "status": STATUS_DRAFT,
                    "reason": "the template does not validate", "validation": report}
        hive.set(HiveRecord(name=name, data=data, etag=record.etag))
        stored = hive.get(name)
        return {
            "promoted": (stored.data or {}).get("status") == STATUS_ACTIVE,
            "name": name,
            "status": (stored.data or {}).get("status"),
            "etag": stored.etag,
            "warnings": report.get("warnings") or [],
        }

    @_template_record_errors
    def delete_template(self, name: str) -> dict[str, Any]:
        """Delete a stored template record.

        Args:
            name: The template (record) name.

        Returns:
            dict: The hive's answer.
        """
        return self._plans().delete(name)

    def install_default_templates(
        self,
        names: list[str] | None = None,
        *,
        overwrite: bool = False,
        status: str = STATUS_DRAFT,
    ) -> dict[str, Any]:
        """Write the engine's default template library to the org's records.

        Reads the authoring kit's ``library`` section. An existing record is
        skipped unless ``overwrite`` is set, and an active record is never
        replaced by a draft. The result lists everything written and skipped,
        with the installed and library versions so an update can be offered.

        Args:
            names: Install only these library templates (default: all).
            overwrite: Replace existing drafts (and existing active records
                only when ``status`` is ``active``).
            status: ``draft`` (default) or ``active``. Library entries are
                written with this status whatever they say themselves.

        Returns:
            dict: ``written``, ``skipped`` (each with a ``reason``) and
                ``failed`` lists.

        Raises:
            ValidationError: If the engine returns no library, a requested
                name is not in it, or ``status`` is invalid.
        """
        if status not in (STATUS_DRAFT, STATUS_ACTIVE):
            raise ValidationError("status must be draft or active")
        kit = self.get_authoring_kit(["library"])
        library = kit.get("library")
        if not isinstance(library, list):
            raise ValidationError(
                "the engine returned no `library` section: this engine version has no default template library yet"
            )
        by_name = {str(e.get("name")): e for e in library if isinstance(e, dict)}
        if names:
            missing = [n for n in names if n not in by_name]
            if missing:
                raise ValidationError(
                    f"not in the default library: {', '.join(missing)}. Available: {', '.join(sorted(by_name)) or 'none'}"
                )
            selected = [by_name[n] for n in names]
        else:
            selected = [by_name[n] for n in sorted(by_name)]
        result: dict[str, list[dict[str, Any]]] = {"written": [], "skipped": [], "failed": []}
        for entry in selected:
            name = str(entry.get("name"))
            try:
                outcome = self.save_template(
                    name, entry.get("yaml") or "", status=status, overwrite=overwrite,
                    comment=f"default library template v{entry.get('version', '?')}",
                    ignore_source_status=True,
                )
            except LimaCharlieError as exc:
                result["failed"].append({"name": name, "error": exc.raw_message})
                continue
            if outcome.get("saved"):
                result["written"].append({"name": name, "status": outcome["status"], "version": entry.get("version")})
                continue
            item: dict[str, Any] = {"name": name, "reason": outcome.get("reason"), "library_version": entry.get("version")}
            if "validation" in outcome:
                result["failed"].append({"name": name, "error": outcome["reason"], "validation": outcome["validation"]})
                continue
            try:
                installed = self.get_template(name)
            except LimaCharlieError:
                installed = None
            if installed is not None:
                item["installed_version"] = installed.get("version")
                item["installed_status"] = installed.get("status")
                item["update_available"] = installed.get("version") != entry.get("version")
                if not overwrite:
                    item["reason"] = (
                        f"a {installed.get('status')} template named {name!r} is already installed; "
                        "pass overwrite to replace it"
                    )
            result["skipped"].append(item)
        return result
