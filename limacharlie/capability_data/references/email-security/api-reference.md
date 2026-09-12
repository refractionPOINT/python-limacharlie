# API Reference

--8<-- "includes/email-security-beta.md"

All Email Security routes live under
`https://api.limacharlie.io/v1/mailsec/{oid}/…` and appear in the public OpenAPI
spec at [`/openapi`](https://api.limacharlie.io/openapi). Authentication is the
standard `Authorization: Bearer <JWT>` header.

!!! info "Permissions & enable gate"
    Every route requires the organization to be subscribed to
    `ext-email-security` — a `403` on any route means subscribe first. The `oid`
    is always taken from the authorized path.

    Reads and the read-only `POST`s (`analyze`, `rules/validate`,
    `rules/backtest`) require `mailsec.get`. Resolving a report requires
    `mailsec.set`. Anything that touches live mail — the action routes and the
    connection test — requires `mailsec.act`. Downloading raw message bytes
    requires `mailsec.get` **and** `mailsec.get.eml`.

    The tenant purge routes are the exception to all of that. Both
    `GET /tenant` and `DELETE /tenant` require Owner-level authority —
    `mailsec.act` **and** `billing.ctrl` **and** `user.ctrl` together.

    Connections, policy and custom rules are **not** `/mailsec` routes: their CRUD
    goes through Hive (`mailsec_provider`, `mailsec_policy`, `dr-mail`).

Shared behaviours:

- **Repeatable filters** are passed as repeated query keys —
  `?verdict=malicious&verdict=suspicious`. OR within a key, AND across keys.
- **Boolean selectors are tri-state.** An absent parameter means "not filtered",
  which is *not* the same as passing `false`.
- **Keyset pagination.** Pages carry `next_cursor`; pass it back as `?cursor=`.
  An empty `next_cursor` is the last page. A cursor is **bound to the filter set
  that minted it** — changing a filter mid-walk fails the next page rather than
  resuming at a position that means something else. Restart the walk.
- **Times** are RFC3339 or unix seconds on input.
- **A miss is not an error.** An unknown or expired message, campaign or report
  id returns a null object rather than a `404`: the index has a 35-day retention
  and a miss is a normal outcome.

## Reads

| Route | Returns |
|---|---|
| `GET /coverage` | Mailboxes discovered / protected / excluded / in error, message volume and the verdict funnel over the window, the parse-degradation rate, backfill progress, the emission backlog, per-connection health, and the `overview` block (open reports, active campaigns, resolved automation mode, and `processing_latency_p95` — see [Time to verdict](pipeline.md#time-to-verdict)). Params: `since`, `until`, `window_days`. With no window at all the default period is served from a short-lived server-side memo; naming an explicit range or a `window_days` always computes that exact period. `window_days` is the whole-days shorthand the CLI's `--window-days` uses (1-35, counted back from now); it cannot be combined with `since`/`until`, and its ceiling is the platform's maximum message retention. A window reaching past the organization's own retention horizon returns `volume.truncated`: the counts are of what is really stored, and the flag says the period asked about is longer than the period kept |
| `GET /messages` | `{messages, next_cursor}` — the message index. Filters: `mailbox`, `sender_email`, `sender_root_domain`, `campaign_id`, `link_domain`, `attachment_sha256`, `verdict[]`, `state[]`, `direction[]`, `user_reported`, `min_score`, `q`, `since`, `until`, `cursor`, `limit` |
| `GET /messages/{msg_uuid}` | `{message, mdm, mdm_source}` — the index row, the full signal rationale, the action timeline, and the Message Data Model. `mdm_source` is `stored` (the model the collector judged with, enrichments included) or `eml_reparse` (a fresh parse of the original bytes, no enrichments). `mdm_unavailable_reason` replaces the model when neither is available |
| `GET /messages/{msg_uuid}/similar` | `{messages, since}` — recent messages sharing at least one clustering key, each with the `matched_keys` that matched, plus the lookback window that was searched. Candidates, not a cluster |
| `GET /messages/{msg_uuid}/revisions` | `{revisions, revisions_truncated}` — one message's whole verdict-revision history, oldest first: who decided (`actor`, `mode`), when, the structured rationale, and the `prior` state each one displaced. The first revision's `prior` is the engine's own verdict and the pack version that produced it. Not paginated — revisions are few by nature — but an optional `limit` is accepted and `revisions_truncated` reports the pathological history that exceeded the backend's ceiling. Gated on `mailsec.get`: a revision is the product's structured record of a decision about a message you can already open |
| `GET /actions/bulk/{bulk_id}` | The running truth of a bulk remediation — see [Bulk Remediation](remediation.md). An unknown bulk id, or an ordinary `action_id` passed here, returns a typed not-found rather than a partial answer |
| `GET /campaigns` | `{campaigns, next_cursor}`. Filters: `state[]`, `verdict[]`, `min_members`, `since`, `until`, `cursor`, `limit`. Every campaign has at least two members, so `min_members` only narrows past that; values below `2` have no effect |
| `GET /campaigns/{campaign_id}` | `{campaign}` — span, membership, verdict, and the keys that bound the messages together |
| `GET /reports` | The user-report queue. Params: `status[]` (`open`, `triaging`, `resolved`), `oldest_first`, `cursor`, `limit` |
| `GET /reports/{report_id}` | One report: who reported it, the message they reported, the original once located across the tenant's mailboxes, and its triage state |
| `GET /senders/{key}` | The accumulated profile for one correspondent. `key` is qualified (`email:someone@corp.example` or `domain:corp.example`) or a bare address or domain. A key with no profile says so explicitly rather than returning a zeroed profile |
| `GET /actions/{action_id}` | `{action}` — one audit entry expanded, **including the JSON request payload the message timeline omits**. For a raw-message download that payload carries the access justification. Gated on `mailsec.get`: reading who did what to a message is part of reading the product |
| `GET /onboarding` | `{scopes, steps, script}` — the setup steps, OAuth scopes and `gcloud` commands for connecting a tenant, for rendering in a setup flow. Each step carries a `console` and, where verifiable, a `verified_by` naming the connection-test check that proves it. Params: `provider` (`gworkspace` default, or `m365`), `project_id`, `sa_email`, `topic`, `subscription` — supply them and the commands come back ready to run rather than templated |
| `GET /tenant` | `{confirmation, expires_in_seconds, warning}` — the tenant-purge preview. Returns the warning describing exactly what a purge removes, and mints the single-use `confirmation` token that [`DELETE /tenant`](#delete-tenant) requires. **It changes nothing.** The token expires after `expires_in_seconds` (300). Requires Owner-level authority, not `mailsec.get` |

**Numeric and boolean parameters are validated.** `limit` is 1-1000 (the backend serves 200 by default), `min_score` is 0-100, `min_members` is 0 or more, and `user_reported` and `oldest_first` take `true`/`false`. A value that is unparseable, out of range, or given more than once is refused with **400** and a response body naming the parameter, for example `{"parameter": "limit", "error": "limit: \"all\" is not an integer"}`. It is not silently dropped, so a filter you sent is always a filter that was applied.

### `GET /messages/{msg_uuid}/eml`

The justified raw download. Requires `mailsec.get` **and** `mailsec.get.eml`, and
the `justification` query parameter is **required**.

| Param | |
|---|---|
| `justification` | Why these bytes are being accessed. Recorded against your authenticated identity in the organization's action audit and retained for 400 days — a failed attempt is recorded too. Stored verbatim; the backend enforces a minimum and a maximum length and refuses an over-long reason rather than truncating |

Raw copies expire with their retention lane — `message_days` (up to 35) for the message index, `flagged_days` (up to 400) once a message is flagged, see [`retention`](policy.md#retention) — after
which this returns a typed expiry error while the index row stays readable.

**Every attempt is telemetry.** Served or refused, each call emits an
`EMAIL_ACTION` event with `action: get_eml` on the connection's sensor, carrying
the actor, the message, the mailbox, the stated justification, and — on a served
download — the `bytes` handed over. That is what makes the download *alertable*
rather than merely recorded: see
[Detections & Verdicts](detections.md#watching-the-download-itself) for a rule
that fires on volume. A refused attempt carries `result: refused` and a
`refused_reason`:

| `refused_reason` | Meaning |
|---|---|
| `permission_denied` | The caller holds `mailsec.get` but not `mailsec.get.eml` |
| `quota_exceeded` | The organization's download budget for the window is spent |
| `quota_unavailable` | The budget could not be evaluated (a `503`, not a `429` — nothing was exceeded) |
| `justification_missing` / `justification_too_short` / `justification_too_long` | No usable reason was supplied |
| `message_not_found` | The `msg_uuid` matched no indexed message |
| `eml_never_stored` | The message exists but no raw copy was written at ingest |
| `eml_expired` | The raw copy aged out of its retention lane |
| `read_failed` | The object is there and could not be read |
| `eml_store_not_configured` | This deployment has no raw-message store |
| `internal_error` | The service could not complete the read (an index-store failure, not an object failure) |

The response's `audited` block echoes the `action_id`, the recorded actor and
justification, and `event_emitted` — which is `false` when the organization has
no live mail connection to ship the event on. Expand the `action_id` through
`GET /actions/{action_id}` to read the justification back.

!!! warning "This route is rate-limited, and deliberately the only one that is"
    Two budgets apply, both per rolling hour:

    | Budget | Limit |
    |---|---|
    | Per API key (or user) per organization | **120** downloads |
    | Per organization, across every key | **600** downloads |

    Exceeding either returns `429` with a body naming the budget. The
    organization-wide refusal is recorded in the action audit and emitted as an
    `EMAIL_ACTION` with `refused_reason: quota_exceeded`.

    These budgets **fail closed**: if they cannot be evaluated, the download is
    refused with a `503` and `refused_reason: quota_unavailable` rather than
    served. A budget that cannot be counted is not a budget, and this is the one
    route that hands original message bytes out of the platform. No other Email
    Security route is rate-limited, so none is affected.

    Every other Email Security route returns the product's *view* of a message —
    the index row, the verdict, the parsed model — and reading those in bulk is
    what a dashboard does. This one returns the message, so a legitimate key
    doing it in bulk is exfiltration. There is no bulk EML export route, and the
    limits are sized for an analyst working a queue rather than for a scrape.

### `DELETE /tenant`

The tenant purge. It permanently deletes everything Email Security holds for the
organization — the message index and the long-term evidence lane, campaigns,
sender profiles, the action audit trail, user reports, stored raw messages and
their parsed copies, link-detonation results, and the organization's provider
connection and policy configuration — and it stops the mail connections at the
provider so no further notifications arrive. It cannot be undone, and there is no
smaller scope than the whole organization.

Both this route and `GET /tenant` require **Owner-level authority**:
`mailsec.act`, `billing.ctrl` and `user.ctrl` together — the same three
permissions deleting the organization requires. There is no separate "owner"
permission.

The `confirmation` token comes from `GET /tenant`, which returns the warning text
and changes nothing. The token is **single-use** and expires **5 minutes** after
it is minted, so the destructive call cannot be replayed, and cannot be reached
without the warning having been served first.

| Param | |
|---|---|
| `confirmation` | **Required.** The token minted by `GET /tenant`. A token that has expired, has already been spent, or was minted for another organization is refused |
| `reason` | Optional free text, **1024 characters maximum**. Recorded in the organization's audit log next to your authenticated identity. An over-long reason is refused rather than truncated |

The response reports what was removed rather than flattening it into success:

| Field | |
|---|---|
| `complete` | `true` when nothing was left behind. `false` means part of the purge did not finish and the call should be repeated |
| `objects_deleted` | Stored raw messages removed |
| `mdms_deleted` | Parsed message copies (Message Data Models) removed |
| `detonation_results_deleted` | Link-detonation results removed |
| `detonation_results_skipped` | Link-detonation results left in place — reported rather than quietly counted as deleted |
| `objects_failed` | Stored items that could not be removed. Any non-zero value is a reason `complete` is `false` |
| `tables_purged` | The list of the product's data sets that were cleared, named so a partial purge shows which ones were reached |
| `subscriptions_stopped` | Provider notification subscriptions stopped, after which the provider sends nothing further |
| `subscriptions_failed` | Subscriptions the provider would not stop |
| `mailboxes_walked` | Mailboxes visited while stopping notifications |
| `provider_records_deleted` | Email Security provider connection records removed |
| `policy_records_deleted` | Email Security policy records removed |
| `connections_unreachable` | Connections that could not be reached at all — a revoked credential or a tenant that is already gone. Their data is still purged; only the provider-side stop could not be confirmed |
| `rows_remained` | Rows still present when the pass ended. Non-zero means re-run |

**The call is re-runnable.** A purge that returns `complete: false` has deleted
whatever it could, and repeating it deletes what remained — nothing is
double-counted and nothing is skipped for having been attempted. Mint a **fresh**
confirmation token for each attempt: the previous one was spent.

Deletion also happens without this route being called — 30 days after an
organization unsubscribes from Email Security, and immediately when the
organization is deleted. See
[Data retention and deletion](policy.md#data-retention-and-deletion).

## Writes

| Route | Does |
|---|---|
| `POST /messages/{msg_uuid}/actions` | Perform a typed action on one message. Body: `action` (`quarantine_message`, `trash_message`, `move_to_spam`, `restore_message`, `banner_message`, `unbanner_message`), optional `reason`, optional `attempt` (idempotency token — omit to collapse onto the existing attempt). `banner_message` uses the organization's own banner, rendered from its `mailsec_policy` record of type `banners`; the body's `banner` field is **deprecated and ignored** and will be removed. Requires `mailsec.act` |
| `POST /campaigns/{campaign_id}/actions` | Sweep a campaign. Same body plus `confirm`. **Without `confirm` this previews** and changes nothing, returning the member ids, the distinct mailboxes, the counts and a `confirm` token derived from that exact member set. With `confirm` it executes exactly that set; a campaign that grew since the preview is refused. Capped at 500 members. `reason` is recorded on **every member's** audit row and on the sweep's own row (`action_id` in the response); `attempt` (bounded at 128 characters, refused not truncated) mints a new row per member, so a deliberate retry is recorded beside what it retried instead of over it. Neither is part of the `confirm` token. Requires `mailsec.act` |
| `POST /actions/bulk/execute` | Execute a previewed bulk remediation. Returns a `bulk_id` immediately and the provider work proceeds in the background. Requires `mailsec.act`. See [Bulk Remediation](remediation.md) |
| `POST /reports/{report_id}/resolve` | Record a triage outcome. Body: `disposition` — one of `true_positive`, `false_positive`, `benign`. Resolving an already-resolved report succeeds and reports `already_resolved`, so two analysts clicking at once is not an error. Requires `mailsec.set` |
| `POST /reports/{report_id}/reopen` | Put a resolved report back in the queue — see [`POST /reports/{report_id}/reopen`](#post-reportsreport_idreopen). Requires `mailsec.set` |
| `POST /messages/{msg_uuid}/verdict` | Re-judge one message — see [`POST /messages/{msg_uuid}/verdict`](#post-messagesmsg_uuidverdict). Requires `mailsec.act` |
| `POST /connections/{record}/test` | Probe a configured connection and report each requirement independently: the credential, each scope, a real directory read, and — for Google Workspace — the notification subscription and topic. Every check carries `id`, `name`, `required`, `status`, and on failure `detail` and `remediation`. A failed **optional** check leaves `ok` true. Body: `include_watch` (Workspace only; the one probe with a side effect — it establishes an idempotent, self-expiring push watch). Takes a **record name, not a credential**. Requires `mailsec.act` |

### `POST /messages/{msg_uuid}/verdict`

Record a re-judgement of one message, replacing the class the engine stamped.

| Field | |
|---|---|
| `verdict` | **Required.** `malicious`, `suspicious`, `graymail`, `benign` or `unknown`. `unknown` is an honest abstention that escalates to a human queue. `error` is refused — it means judgement itself failed, which is an engine fact nobody decides |
| `mode` | **Required.** Which *seat* decided: `analyst` for a person, `ai` for an autonomous triage agent calling with its own organization credentials. `auto` is refused; that is the scorer's own path and it does not override itself |
| `rationale` | **Required.** A non-empty list of short strings. A class with no reason is a naked verdict, and the same explainability contract applies to a revision as to the engine. Bounded: at most **10 bullets of 280 characters**, clipped on a character boundary with `rationale_truncated` set, rather than the verdict being refused over a long explanation |
| `score` | Optional. Omitting it keeps the engine's score beside the new class |

**Who** revised is stamped from your authenticated identity and is never read
from the body. `mode` names the seat, not the person: a caller misstating it can
only do so beside an `actor` it did not choose, where the two disagree visibly.

Requires **`mailsec.act`**, not `mailsec.set`, and that is the one permission
choice on this surface that is not read off the "does it touch a mailbox" line. A
revision can move the message into the flagged set, which promotes its evidence
from the 35-day lane to the 400-day one — a ratchet with no demotion — and it
ships an `EMAIL_VERDICT` that fires every matching D&R rule. That is the product
doing something on the organization's behalf, and `mailsec.act` is the single
grant an operator revokes to stop an autonomous caller doing it.

| Response field | |
|---|---|
| `applied` | Whether a revision was written |
| `already_current` | `true` when the message already carried this class, score and mode |
| `revision_seq` | The revision this call produced — or, on a no-op, the one that already says it |
| `prior` | What was displaced: `verdict`, `score`, `mode`, `engine_version` |
| `newly_flagged` | Whether the message entered the flagged set |
| `flagged_mirrored` | Whether its 400-day evidence row was updated in the same transaction |
| `event_emitted`, `retained` | Whether the `EMAIL_VERDICT` shipped, and whether the evidence reached the retained lane |
| `rationale`, `rationale_truncated`, `actor`, `verdict`, `mode`, `decided_at` | The revision as recorded |

!!! note "A no-op is a success, not an error"
    Re-recording the class, score and mode a message already carries changes
    nothing: the response is `200` with `applied: false` and
    `already_current: true`. Distinguish the two through the body, not the status
    code. Re-wording the rationale alone is not a change; a person confirming an
    agent's call **is** one, because the mode moves.

The revision is durable before the event and the evidence promotion are
attempted, so a failure to ship telemetry comes back as a retryable error whose
body still says `applied: true`. The recorded judgement is never silently
discarded, and the event is never claimed when it did not ship. This route is not
retried on your behalf: one billable verdict change must not become two because a
response was lost — poll [`GET /messages/{msg_uuid}/revisions`](#reads) instead,
or re-send it yourself.

### `POST /reports/{report_id}/reopen`

Put a resolved user report back in the queue. Its status returns to `open` and it
is worked again.

**Takes no request body.** Who reopened is stamped from your authenticated
identity and is deliberately not supplied by the caller.

This is the escape hatch for a resolution nobody made: a report from an
[automated sender](user-reports.md#automated-senders) is born resolved and
attributed to `system:automated-sender`, and that classifier is only defensible
because it is reversible. It serves a wrong AI resolution and an analyst's
mis-click equally; none of the three is special here.

The resolution columns are deliberately **kept** — only the status moves — so the
row still reads "previously resolved `benign` by `system:automated-sender`"
rather than erasing the very thing being disputed.

Reopening a report that is already open or being triaged succeeds and reports
`already_open`, so two analysts clicking at once is not an error;
`reopened_from` names the state it came out of. An unknown report id **is** an
error rather than a silent success, because this route names one specific row to
change.

Requires `mailsec.set` — exactly like the resolve it undoes. An analyst who can
close a report must be able to reopen one, or a mis-click is permanent.

### Read-only `POST`s

| Route | Does |
|---|---|
| `POST /analyze` | Parse a raw message into the Message Data Model and judge it with the packaged rules against default policy. **Nothing is ingested or stored**: no index row is written, no raw copy kept, and the organization's mail history is unchanged. Body: `eml_b64` (preferred) or `eml`, plus optional `org_domains` and `direction`. Tenant context it cannot have — your sender history, your VIP list — is named explicitly in the payload rather than silently missing. Requires `mailsec.get` |
| `POST /actions/bulk/preview` | Preview a bulk remediation over a caller-supplied selection: reports each message's current state and the distinct-mailbox blast radius, and mints the `confirm` token derived from that exact selection. **Nothing is changed and no job is created** — it is a `POST` only because up to 500 message ids do not belong in a query string. Requires `mailsec.get`, like the campaign preview it mirrors. See [Bulk Remediation](remediation.md) |
| `POST /rules/validate` | Compile a candidate `dr-mail` rule and report its errors without saving it. Body: `rule` (object), optional `rule_id`. Runs the same compile the `dr-mail` Hive applies on save, with **one exception**: it does not check that a `lookup` resource the rule names actually exists in your organization, because it cannot read your `lookup` records. A rule naming a missing lookup validates here and is refused on save — see [Custom Rules](custom-rules.md#rules-for-lookup-in-a-mail-rule). An invalid rule is a `200` carrying `valid: false` and the reason, not an error response. Requires `mailsec.get` |
| `POST /rules/backtest` | Replay a candidate rule over the organization's indexed message window and report what it would have matched. Body: `rule`, optional `rule_id`, `since`, `until`. Every response carries a `coverage_note` and counts what it could not examine (`skipped_no_raw`, `skipped_unparse`, `truncated`). `precision` is `null` — not `0` — when nothing it matched has an analyst disposition yet. Requires `mailsec.get` |

## Registered, but not implemented yet

Three retro-hunt routes appear in the public OpenAPI document. **None of them is
served.**

- `POST /hunts` — replay a detect block or an LCQL query over the message history
- `GET /hunts/{hunt_id}` — a hunt's progress and its matches
- `POST /hunts/{hunt_id}/remediate` — act across everything a hunt matched

They are registered now so that the URLs and their permission gates are frozen
before any client ships against them, and so that calling one gives you a
refusal rather than a `404` you cannot tell from a typo. The permission gates are
live and are the same ones the served routes use; what is missing is the replay
engine behind them.

**Do not build against them yet, and do not branch on the refusal.**
`GET /hunts/{hunt_id}` answers a typed `not_implemented` naming the milestone it
waits on. The two `POST`s currently fail with a plain routing error instead,
because the typed refusal is registered on a different backend from the one they
are addressed to. Treat all three as unavailable rather than as a contract.

Until they serve, mail hunting is
[LCQL over `EMAIL_MESSAGE`](automation.md#querying-mail-with-lcql) — which is what
the console's **Hunt** screen runs — and acting on what you find is
[bulk remediation](remediation.md) over the message ids you selected.

## Action results

Action routes report the outcome honestly rather than flattening it into
success/failure:

| `result` | Meaning |
|---|---|
| `ok` | The provider was changed |
| `skipped` | The desired state already held; no provider write happened |
| `alert_only` | Decided and deliberately not performed, because the organization is not in enforce mode. **Not an error** |
| `failed` | The provider refused or errored; `error` carries the reason |
| `pending` | In flight |

A campaign sweep returns `attempted`, `succeeded`, `skipped` (a subset of
`succeeded`: members already in the target state, which cost no provider write),
`alert_only`, a per-member `failed` map, and `action_id` — the sweep's own audit
row, readable through `GET /actions/{action_id}`, carrying the operator's
justification and the counts. It does not abort on the first error.

## Telemetry event contract

The routes above are the read/write surface. The **event** surface is ordinary
LimaCharlie telemetry on the `email` platform, delivered to the default D&R
target and to every configured Output, and it is a contract in its own right:
these types and JSON paths are frozen and additive-only, because a year of stored
telemetry and every customer rule is keyed on them.

| Event | Cardinality |
|---|---|
| `EMAIL_MESSAGE` | Exactly once per message, at ingest, immutable. Carries the full Message Data Model |
| `EMAIL_VERDICT` | Once per verdict **decision**. `revision/seq: 0` with `revision/mode: auto` is the rule pack's own verdict, emitted at ingest immediately after that message's `EMAIL_MESSAGE`; `seq: 1…` is one per override (`analyst`, `ai`, `detonation`) |
| `EMAIL_ACTION` | Once per remediation outcome, including failures and skips |
| `EMAIL_USER_REPORT` | Once per message that reaches the abuse mailbox |
| `EMAIL_INGEST_ERROR` | Once per message that could not be fetched or processed |

Two consequences worth stating plainly:

- **The verdict appears twice at ingest** — inside `EMAIL_MESSAGE` under
  `event/verdict/…` and again as the `seq 0` `EMAIL_VERDICT` under
  `event/revision/…`. That is deliberate. It is what lets a rule about verdicts
  be written once instead of once for the engine and once for every later
  override, and it is why `EMAIL_VERDICT` can be treated as the complete verdict
  stream for a message.
- **The `seq 0` event is not a revision record.** `GET /messages/{msg_uuid}`
  reports `revision_count: 0` and an empty revision history for a message nobody
  has overridden. The rule pack's verdict is on the message itself, not in its
  history of disagreements.

The `EMAIL_VERDICT` body is documented field by field in
[Events & Automation](automation.md#email_verdict).

## Attribution

`actor` and `source` on every audit row are stamped by the server from the
caller's verified claims — a user token keeps its stable user id, and an
authorized organization API key is attributed as `api-key:<key-id>`. A request
body **cannot** supply `by`, `actor` or `source`: an audit trail is only worth
having if it names who really asked.

## SDK and CLI

The Python SDK exposes the same surface, and the CLI wraps it — see
[Command Line Interface](cli.md). Both are generated against these routes, so
anything documented here is reachable from either.
