# Detections & Verdicts

--8<-- "includes/email-security-beta.md"

Every message gets exactly one verdict, and the verdict always carries its
reasons. This page explains how the reasons are produced, what the rules can see,
and how to tune it.

## The verdict

| Verdict | Meaning |
|---|---|
| `malicious` | Score at or above the malicious threshold |
| `suspicious` | Score at or above the suspicious threshold |
| `graymail` | Bulk or marketing mail: neither an attack nor wanted |
| `benign` | Below the suspicious threshold, and nothing said "graymail" |
| `unknown` | No judgement was reached |
| `error` | Judging failed |

The verdict object on a message carries:

| Field | Meaning |
|---|---|
| `verdict` | The class above |
| `score` | 0–100 |
| `top_signals` | Up to five contributing rules, heaviest first, each with `rule_id`, `name` and `weight`. This is the "why this verdict" block |
| `matched_signals` | Every rule id that matched, including suppressed ones — the hunting surface |
| `tags` | The deduplicated, sorted tags of the rules that actually contributed |
| `engine_version` | The rule-pack version that decided it |
| `decided_at` | When |
| `mode` | Who last decided: `auto` (the rule pack), `analyst` (a person), `ai` (a triage agent) or `detonation` ([link detonation](#link-detonation)). See [Revising a verdict](#revising-a-verdict) |
| `campaign_id` | The campaign this message was clustered into, if any |

!!! info "A number alone is never the answer"
    A non-benign verdict always populates `top_signals`. The console renders it
    as **Why this verdict** in the message drawer, and the API returns it on both
    the index row (the single heaviest signal) and the detail response (the full
    list). A score with no explanation would not be actionable and is not
    offered.

### The verdict is also an event

Every verdict this product reaches is emitted as an `EMAIL_VERDICT` event, so a
rule that acts on verdicts is written **once**:

| `revision/seq` | `revision/mode` | What it is |
|---|---|---|
| `0` | `auto` | What the rule pack decided, emitted at ingest immediately after the message's `EMAIL_MESSAGE` |
| `1`, `2`, … | `analyst` | A human overrode it |
| | `ai` | The AI triage agent overrode it |
| | `detonation` | Link detonation found something at the other end and overrode it |

The `seq 0` event repeats a verdict that is already inside `EMAIL_MESSAGE`, and
that duplication is deliberate: without it, "tell me when a message is judged
malicious" would be two rules against two paths on two event types — one for the
engine's opinion and one for everything that happened after it — that you would
have to keep in agreement forever.

`EMAIL_MESSAGE` is still emitted once per message and is still immutable. The
verdict *history* is the sequence of `EMAIL_VERDICT` events, which is what lets a
hunt reconstruct what was known at any point in time.

The `seq 0` event is an event and nothing else. It is not an entry in the
message's revision history, and a message nobody has overridden reports zero
revisions in the API and the console.

See [Events & Automation](automation.md) for the payload and
[Custom Rules](custom-rules.md#acting-on-a-verdict) for a rule that uses it.

## Revising a verdict

The engine's call is the first word, not the last. A person or an AI triage agent
can replace it, and the replacement is **appended** rather than written over the
top.

```bash
limacharlie mailsec message revise <msg_uuid> \
  --verdict malicious --rationale "confirmed credential harvest" --oid $OID
```

| Field | |
|---|---|
| `verdict` | **Required.** `malicious`, `suspicious`, `graymail`, `benign` or `unknown`. `unknown` is an honest abstention that escalates to a human queue. `error` is refused — it means judgement itself failed, which is an engine fact nobody decides |
| `mode` | **Required.** Which seat decided: `analyst` or `ai`. `auto` is refused; the scorer does not override itself. The CLI always sends `analyst`, because the operator of a CLI is a person — an agent revises with its **own** key and `mode: ai` |
| `rationale` | **Required.** A non-empty list of short reasons. A class with no reason is a naked verdict, and the same explainability contract applies to a revision as to the engine |
| `score` | Optional. Omit it and the engine's score stays beside the new class, rather than a made-up number landing in the column a backtest reads |

`rationale` is bounded rather than refused: at most **10 bullets of 280
characters**, clipped on a character boundary with `rationale_truncated` set. A
verdict is not thrown away over a long explanation.

**Who** revised is stamped from your authenticated identity and is never read
from the request. `mode` names the seat, not the person, so a caller misstating
it can only do so beside an `actor` it did not choose — where the two disagree
visibly.

!!! note "A no-op is a success, not an error"
    Re-recording the class, score and mode a message already carries changes
    nothing: `applied: false`, `already_current: true`, and `revision_seq` names
    the revision that already says it. Re-wording the rationale alone is not a
    change. A person confirming an agent's call **is** one, because the mode
    moves.

Revising takes **`mailsec.act`**, not `mailsec.set` — the only place on this
surface where the permission is not read off the "does it touch a mailbox" line.
A revision can move a message into the flagged set, which promotes its evidence
from the 35-day lane to the 400-day one, and that promotion is a ratchet with no
demotion. It also emits an `EMAIL_VERDICT` that fires every matching rule. That
is the product doing things on the organization's behalf, and `mailsec.act` is
the single grant an operator revokes to stop an autonomous caller doing them.

### The four modes

| `mode` | Who |
|---|---|
| `auto` | The rule pack, at ingest. Only the engine writes this one |
| `analyst` | A person, through the console, the CLI or the API |
| `ai` | An autonomous triage agent calling with its own organization credentials — see [AI Triage](ai-triage.md) |
| `detonation` | [Link detonation](#link-detonation) came back with something the static pass could not know |

### The history

The revisions are an append-only sequence. Each entry carries its `seq`, the
`verdict` and `mode`, the `actor`, `decided_at`, the `rationale`, and the `prior`
state it displaced — verdict, score, mode and engine version. **The first
revision's `prior` is the engine's own verdict**, so the chain reaches back to
what the pack originally said without a separate lookup.

```bash
limacharlie mailsec message revisions <msg_uuid> --oid $OID --output yaml
```

`GET /messages/{msg_uuid}/revisions` serves the whole chain, oldest first. It is
deliberately **not paginated** — a message's revisions are few by nature — but
`revisions_truncated` reports the pathological history that exceeded the
backend's ceiling. It is gated on `mailsec.get`: a revision is the product's own
structured record of a decision about a message you can already open, not the
original bytes `mailsec.get.eml` guards.

The message drawer inlines the most recent revisions, which is what an analyst
reads; the route exists for the rare message with more than the drawer inlines,
and for an audit export that wants the chain entire. A message nobody has
overridden reports `revision_count: 0` and an empty history — the engine's own
verdict is on the message, not in its history of disagreements.

Nothing is rewritten. `EMAIL_MESSAGE` still stands as the record of what the
engine decided at ingest, the row carries the current answer, and each revision
ships an [`EMAIL_VERDICT`](automation.md#email_verdict) at the next `seq`.

## Scoring

Each matching rule carries a **weight** (0–100, how much this evidence is worth)
and a **confidence** (0–100, how often it is right when it fires). The score
combines them with diminishing returns rather than a sum:

```text
score = 100 × ( 1 − Π (1 − wᵢ/100 × cᵢ/100) )
```

Each signal removes a fraction of the *remaining* headroom. A sum would let five
weak signals outscore one strong one and would need clamping at 100, which makes
every heavily-signalled message look identical. One rule at weight *N* and
confidence 100 scores exactly *N*, which is the identity every threshold is
reasoned about against.

| Threshold | Default | Where to change it |
|---|---|---|
| `malicious_min` | 85 | [`mailsec_policy/thresholds`](policy.md#thresholds) |
| `suspicious_min` | 45 | [`mailsec_policy/thresholds`](policy.md#thresholds) |

`malicious_min` must stay above `suspicious_min`. Composed policy that inverts
the pair is refused, and an inverted pair reaching the scorer any other way falls
back to the defaults rather than making every suspicious message malicious.

### The graymail lane

Graymail is a **lane, not a score band**. Rules classed `graymail` contribute no
score at all; they set the verdict to `graymail` only when the score did not
reach `suspicious_min` **and** no `detection`-class rule fired.

That last clause is the point: a newsletter that also carries a credential-phish
link is a phish that happens to look like a newsletter, and filing it under
"marketing" is filing it where nobody looks.

### Exclusions

Exclusions are applied **before** scoring, so a suppressed rule contributes
nothing to the score and never appears in `top_signals`. It still appears in
`matched_signals`, so a suppression is auditable rather than invisible.

Exclusions can be scoped by rule id, sender address, sender domain or mailbox,
require a written reason, and can carry an expiry — after which they become inert
without anyone deleting them. See
[Policy Reference → Exclusions](policy.md#exclusions).

## What the rules can read

Rules are standard D&R detect blocks evaluated against the **Message Data
Model** — the parsed message — plus the enrichments the pipeline stamped onto it.
Because the enrichments are *in the message*, a rule reads them as ordinary paths
and a re-evaluation later sees exactly what the pipeline saw.

### The parsed message

`headers` (including the raw header list, decomposed sender and recipient
addresses, and every domain and IP found), `sender` (with `reply_to_mismatch`,
free-mail and disposable flags), `recipients`, `subject`, `body` (HTML and plain,
extracted display text, thread segmentation into the current reply and previous
quoted threads, hidden-text detection), `links`, `attachments`, `auth` (parsed
SPF / DKIM / DMARC / ARC results with alignment) and `hops` (the parsed `Received`
chain).

### Enrichments

| Path | What it carries |
|---|---|
| `enrichments/sender_profile` | This organization's history with the sender **address**: `first_seen_ts`, `days_known`, `msg_count_30d`, `flagged_count_180d`, `prevalence` (`none` / `new` / `rare` / `common`) |
| `enrichments/domain_profile` | The same, keyed on the sender's registrable **domain** |
| `enrichments/sender_domain` | The sender domain's registration age, from RDAP with a bounded global cache |
| `enrichments/link_features[]` | Per link, aligned with `links[]`: `domain`, `domain_age_days`, `popularity_bucket` (`top1k` / `top100k` / `top1m` / `unranked`), `in_urlhaus`, `mixed_script` (a homograph label mixing writing systems), `credentials_in_url` (the `https://apple.com@evil.example/` trick) |
| `enrichments/lookalike` | `vip_hit` (`display_name:<name>` when the display name matches a VIP whose address does not, `email:<addr>` when the sender *is* the VIP), `org_domain_distance` and `brand_domain_distance` — edit distances against your own domains and known brands |
| `enrichments/detonation` | What [link detonation](#link-detonation) found at the other end of a link, when it ran: `hops[]` with each hop's `resolved_ips`, `connected_addr` and `tls`, a `landing` (`effective_url`, `title`, `has_password_input`, `form_action_hosts`, …), or a `refusal` (`kind`, `reason`). **Added after the first verdict**, so it is absent on a message that was never detonated — which is most of them |
| `attachments[].explode` | Attachment explosion: recursive `children` with their own names, hashes, magic types and depth; `archive` (`encrypted`, `file_count`, `max_depth_hit`); `vba` (`auto_exec`, `suspicious`, `hex_strings`); `qr[].url`; `ocr_excerpt`; `yara_matches`; the `scanners` that ran |

Attachment explosion is bounded — a per-message time budget and size and event
caps — and can only ever fail toward "not scanned". `explode.scanners` names what
actually ran for that attachment, so a rule that depends on a particular kind of
evidence can tell "the scanner found nothing" from "that scanner did not run".

!!! warning "Absent is not benign"
    An enrichment that could not be resolved is **absent**, never a reassuring
    value. `domain_age_days` is missing when the registry lookup was unavailable,
    rate-limited or a cache miss — which is common — and a
    newly-registered-domain rule must therefore test *presence* as well as a
    threshold. Likewise `popularity_bucket` is empty when the lookup did not run,
    which is a different fact from `unranked`, a positive finding that the domain
    really is not in the list. A missing lookup must never become a suspicion.

### The sender-history feedback loop, and why it is closed

Sender profiles are read **before** the message is counted, so the stamp answers
"what did this organization know about this sender *before* this message
arrived". Counting first would make `msg_count_30d` never zero and first contact
indistinguishable from second contact.

More importantly, the profile's `flagged_count_180d` counter is only incremented
for verdicts that flag **independently of prevalence signals**. Rules whose
evidence *is* the accumulated history carry a `prevalence` tag, and the counter
is computed with those rules removed.

The reason is a loop observed live before the contract existed: the sender-history
rule alone can cross the suspicious threshold, and if a flagged verdict fed the
counter, one false positive would re-flag that sender forever — each flag
re-incrementing the counter that caused it, never decaying, and in enforce mode
quarantining a legitimate sender silently. Counting only the independent lane
makes a history rule an amplifier of *other* evidence and never of itself.

## The managed rule pack

A packaged, versioned set of rules ships with the product and its version is
stamped into every verdict as `engine_version`. The current pack:

| Rule id | Class | Weight | What it says |
|---|---|:--:|---|
| `ms-sender-first-contact` | signal | 30 | First message ever from this sender (`prevalence: none`) |
| `ms-sender-known-bad-history` | signal | 65 | This sender has been independently flagged before |
| `ms-sender-domain-newly-registered` | signal | 45 | The sender's domain was registered in the last week |
| `ms-auth-dmarc-fail` | signal | 50 | DMARC failed |
| `ms-auth-spf-fail-inbound` | signal | 40 | SPF failed on inbound mail |
| `ms-impersonation-vip-display-name` | signal | 55 | Display name matches a VIP but the address does not |
| `ms-impersonation-org-domain-lookalike` | signal | 70 | Sender domain is one or two edits from one of your domains |
| `ms-impersonation-exact-org-domain-external` | **detection** | 85 | Claims one of your domains but arrived from outside |
| `ms-impersonation-reply-to-mismatch` | signal | 35 | `Reply-To` points at a different organization than `From` |
| `ms-link-display-href-mismatch` | signal | 60 | A link's visible text names a different site than its destination |
| `ms-link-credentials-in-url` | signal | 75 | A link embeds credentials before the host |
| `ms-link-mixed-script-domain` | **detection** | 80 | A link's domain mixes writing systems within one label |
| `ms-link-unranked-domain` | signal | 30 | A link points at a domain absent from the top-1M list |
| `ms-link-known-malicious-url` | **detection** | 95 | A link matches the managed malicious-URL feed |
| `ms-graymail-list-unsubscribe` | graymail | — | Bulk mail carrying `List-Unsubscribe` |
| `ms-graymail-precedence-bulk` | graymail | — | The message declares itself bulk |

Rule ids are stable and are never renamed — that is the only reason an exclusion
or a per-rule override can be persisted at all.

You can disable a packaged rule or replace its weight for your organization
without forking anything, through
[`mailsec_policy/thresholds` → `rule_overrides`](policy.md#thresholds).

!!! tip "Judge a message without ingesting it"
    `POST /mailsec/{oid}/analyze` (`limacharlie mailsec analyze --file
    suspect.eml`) parses a raw message you supply and runs the enrichers and the
    packaged rules against default policy. **Nothing is ingested or stored**: no
    index row is written, no raw copy is kept, and the organization's mail
    history is unchanged. It is how you test a rule change, or analyze a sample
    that was never in the tenant. The tenant-specific context it cannot have —
    your sender history, your VIP list — is named explicitly in the response
    rather than silently missing.

## Link detonation

Static link features answer what a URL *looks* like. Detonation answers where it
actually goes: the redirect chain, the address each hop really connected to, the
landing page's certificate, and bounded signals from the page itself.

It is an **enrichment, never a gate**. No mail is held waiting for it. The
message is judged, `EMAIL_MESSAGE` is emitted and the automations run first;
detonation happens afterwards and, if what it finds changes the answer, it files
a [verdict revision](#revising-a-verdict) in `mode: detonation`.

!!! info "Availability is per region"
    Detonation needs an isolated, separately-governed analysis environment — the
    process that fetches attacker-chosen URLs and parses attacker-written HTML
    holds no mailbox credential, no organization key and no LimaCharlie identity
    at all. Where that environment is not deployed, detonation is simply
    **absent**: nothing is stamped, and it never degrades into a fetch from a
    service that can reach a mailbox.

### What gets detonated

Four conditions, all of them required:

| | |
|---|---|
| The verdict is **`suspicious`** | Not `malicious` — that has already crossed the threshold that fires automations, so a fetch there takes a slot from the message where the answer would change something. Not `benign`, for the other end of the same argument |
| The message has at least one `http`/`https` link | Other schemes are skipped before anything is queued |
| It is a **first ingest**, not a redelivery | A re-delivered message has already had its turn |
| The environment is deployed in that region | Otherwise absent |

Up to **five distinct URLs per message**, taken in message order after
duplicates are folded together. Five, because a phishing message's payload link
is in the first few and a newsletter has hundreds — and stated honestly: a
message whose sixth link is the malicious one is not fully examined.

The URLs come from the message's own link list, **after** a mail gateway's
rewrite has been unwrapped. Detonating the wrapper would describe your mail
plumbing rather than the attacker's infrastructure.

Two other things reach the same machinery: an analyst or a rule dispatching
[`crawl_link`](policy.md#the-two-asking-actions), and an
[AI triage agent](ai-triage.md) doing the same. Three invocations, one mechanism
— a second detonation path would be a second answer for one message.

### One fetch per URL, per organization

A URL is **claimed** before it is fetched, and the claim is organization-wide
rather than per message. That is what makes a campaign cheap: four hundred
messages carrying one link cost one fetch.

| Outcome | |
|---|---|
| **Claimed** | This is the first caller. It fetches and writes the result back |
| **Fresh** | A completed result already exists and is recent enough to reuse. Nothing is fetched |
| **In flight** | Another caller holds a live claim. Nothing is stamped and **nothing waits** — mail is never held for detonation |
| **Backoff** | This URL failed recently and is not retried yet |

Everything about the lane sheds rather than blocks or grows: bounded workers, a
bounded queue, and a per-organization cap on how many detonations are in flight
at once so one organization's campaign cannot take every slot. A drop costs one
message a better verdict, which is a different thing from losing mail, and the
two do not share a policy.

### A refusal is a result, not an error

"This link redirects to the cloud metadata address" is the single most valuable
thing detonation produces, so a refusal is a **successful** detonation carrying a
typed reason — never an error a caller would log as infrastructure and discard.

| Reason | |
|---|---|
| `invalid_url` | The URL could not be parsed |
| `scheme_not_allowed` | Not `http` or `https` |
| `port_not_allowed` | Not a web port |
| `credentials_in_url` | Credentials before the host — the `https://apple.com@evil.example/` trick |
| `blocked_address` | A hop resolved to an address that must never be connected to: loopback, link-local, private ranges, the cloud metadata address |
| `no_usable_address` | The name resolved, and **every** address it resolved to was blocked. Deliberately its own finding: "this host now points only at an internal address" is not a DNS failure |
| `dns_failure` | The name did not resolve |
| `too_many_hops` | The redirect chain ran past its limit |
| `redirect_loop` | The chain came back to somewhere it had been |
| `missing_location` | A redirect status with no usable destination |
| `budget_exceeded` | The target stalled past the time budget — itself evidence |
| `transport_error` | The connection failed |

(A thirteenth code, `disabled`, is reserved in the contract for "asked for
where detonation is not deployed". Nothing stamps it on a message — in that
situation nothing is stamped at all — so do not write a rule that waits for it.)

Each hop's real connected address is recorded, so a name that answered
differently the second time cannot hide behind the first answer. TLS facts are
recorded even when the certificate does not verify — refusing to look at a page
because its certificate is untrusted would blind detonation to the pages most
likely to be malicious. Oversized pages are **truncated and reported as
truncated**, never refused: refusing would hand an attacker a one-line way to
blind detonation by padding a harvest page.

### `mode: detonation`

When the evidence changes the class, the message is re-judged in full — both
rule packs, your policy, your thresholds — and the new class is filed as a
revision in `mode: detonation`.

It has the **lowest authority** of the three revising modes:

| The message's current mode | A detonation revision |
|---|---|
| `auto`, or a previous `detonation` | Applies |
| `ai` | **Refused.** The evidence is still stamped on the message |
| `analyst` | **Refused.** The evidence is still stamped on the message |
| Anything else | **Refused.** The rule is an allow-list, so a mode this build does not recognize is not overwritten either |

A machine does not overrule a person, or an agent that already looked. The
refusal is a satisfied outcome, not a failure: the detonation block lands on the
message either way, and only the verdict is left alone.

`detonation` is not a mode any caller can claim. The
[revision API](api-reference.md#post-messagesmsg_uuidverdict) accepts `analyst`
and `ai`; this one is stamped by the engine that produced it.

### What is kept, and what is not

The **page body never comes back**. What is stored is a hash and size, a title, a
bounded excerpt, structural signals, and the redirect chain with each hop's
resolved and connected addresses and TLS facts.

Results are **always sealed** — there is no plaintext mode, and the lane refuses
to start without a key. Each result is encrypted under a key derived from your
organization's own key, stored under a path that leads with your organization id,
and bound to that exact path so that a copied object cannot be opened elsewhere.
The environment that does the fetching never holds your organization's key; it
writes through a single-object, single-use signed URL and holds no credential of
yours at all.

Detonation results are removed by a [tenant purge](policy.md#what-a-purge-removes)
and by the ordinary retention sweep, along with everything else the product holds
for you.

### Reading it

The detonation block lands on the message's enrichments and in the drawer, and
rules read it as an ordinary path:

```yaml
# The landing page asks for a password
op: is
path: enrichments/detonation/landing/has_password_input
value: true
```

```yaml
# A link's chain ended somewhere it must never be connected to
op: is
path: enrichments/detonation/refusal/kind
value: blocked_address
```

The block carries `url` — **which link this describes**, and the only field that
says so — plus `hops[]` (each with `host`, `resolved_ips`, `connected_addr`,
`status`, `next_url` and `tls`), a `landing` (`effective_url`, `status`, `title`,
`body_sha256`, `body_bytes`, `body_complete`, `text_excerpt`,
`has_password_input`, `form_count`, `form_action_hosts`), a `refusal`
(`kind`, `reason`) where there was one, `elapsed_ms` and `detonated_at`.

!!! warning "Most of these fields are absent rather than false or empty"
    A boolean like `has_password_input`, and `refusal/kind` itself, are omitted
    when they have no value — so "the page had no password field" and "no
    detonation ran" look identical to a rule that only tests for `false`. Test
    for **presence** first when the difference matters, exactly as you would for
    [any other enrichment](#enrichments).

When several of a message's links were detonated, the drawer shows the most
damning one — credential harvest first, then a refusal that found a private
pivot, then any other refusal, then a landing with a bad certificate. The others
are not discarded: each link carries its own resolved chain.

## Watching the download itself

Detection does not stop at the mail. The most privileged thing anyone can do in
this product is take a person's original message out of it, and that act is
telemetry too: every call to
[`GET /messages/{msg_uuid}/eml`](api-reference.md#get-messagesmsg_uuideml) —
served or refused — emits an `EMAIL_ACTION` with `action: get_eml`, carrying the
actor, the mailbox, the stated justification, and the `bytes` handed over.

One download is an analyst doing their job. A hundred in an hour is not, and it
is the *volume* that says so — which is why the byte count is on the event.

```yaml
# Detect: one identity pulling raw mail in bulk
op: and
rules:
  - op: is
    path: routing/event_type
    value: EMAIL_ACTION
  - op: is
    path: event/action
    value: get_eml
  - op: is
    path: event/result
    value: ok
```

```yaml
# Respond
- action: report
  name: mailsec-raw-download
  detect_data:
    actor: '{{ .detect.event.actor }}'
    mailbox: '{{ .detect.event.mailbox.address }}'
    bytes: '{{ .detect.event.bytes }}'
  suppression:
    is_global: true
    keys:
      - 'mailsec-raw-download'
      - '{{ .detect.event.actor }}'
    max_count: 25
    period: 1h
```

The suppression block is doing the real work: it lets twenty-five downloads an
hour by one identity pass without a detection and reports the twenty-sixth, so
the rule is quiet for normal use and loud for a scrape. Set `max_count` to what
your team actually does in an hour, not to a number that feels safe.
`is_global: true` keys the budget on the identity across the whole organization
rather than per sensor — an analyst working two mail connections is still one
analyst.

Templates in `detect_data` and `metadata` resolve against the **detection**, not
the raw event, which is why the paths above are `.detect.event.…`.

!!! tip "Alert on the refusals too — they are the earlier signal"
    A stolen or over-broad key usually fails before it succeeds. Match
    `event/result` = `refused` and read `event/refused_reason`:
    `permission_denied` means somebody without the `mailsec.get.eml` grant
    reached for raw mail, and `quota_exceeded` means the organization's download
    budget was hit. Both are worth a detection on the first occurrence, with no
    suppression at all.

```yaml
# Detect: somebody reached for raw mail without the grant
op: and
rules:
  - op: is
    path: routing/event_type
    value: EMAIL_ACTION
  - op: is
    path: event/action
    value: get_eml
  - op: is
    path: event/refused_reason
    value: permission_denied
```

Both rules are ordinary platform D&R rules on the `edr` target, so the same
response arsenal applies — page a channel, open a ticket, disable the key.

## Two seats for rules

Signal rules run in the collector, before the verdict is emitted. Platform D&R
rules run afterwards, on the emitted events, with the whole response arsenal.
Same syntax, different seat. See [Custom Rules](custom-rules.md) and
[Events & Automation](automation.md).
