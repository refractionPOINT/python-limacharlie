# IOC & Reputation Feeds

--8<-- "includes/email-security-beta.md"

The managed rule pack carries its own link and sender reputation signals. This
page is about the other lane: mirroring a threat feed **you** have chosen, and
are licensed to use, into a LimaCharlie `lookup`, then matching every message's
links, attachments and sender domains against it.

Nothing on this page is installed for you. Which feeds you trust, on what terms,
and how hard you act on a hit are your decisions, and they differ enough between
organizations that a default would be wrong more often than right.

## How the pieces fit

There is no email-specific feed integration. You are composing three things that
already exist:

| Piece | Role |
|---|---|
| [Lookup Manager](../5-integrations/extensions/limacharlie/lookup-manager.md) (`ext-lookup-manager`) | Fetches a feed on a schedule and writes it into a `lookup` Hive record |
| The `lookup` Hive | Holds the indicator set, keyed by the name you chose |
| `op: lookup` in a D&R rule | Tests one value out of a message against that record |

The feed never touches Email Security's own configuration. It is an organization
resource that a mail rule happens to read, which is why the same record can also
back an EDR rule, a cloud rule, or a query.

## Read the feed's licence first

This is the part people skip, and it is the part that has consequences.

A public threat feed is not public-domain data. Most carry terms covering
redistribution, attribution and commercial use, and those terms bind **you**,
not us. Two rules keep you out of trouble:

- **Fetch from the source, with your own credential.** The Lookup Manager
  configuration you write is your organization's, the key in it is your key, and
  the request goes from LimaCharlie to the provider on your behalf. Do not
  source a licensed feed from a third-party mirror, ours included, unless the
  licence plainly allows it.
- **Keep the attribution.** If the feed asks to be credited, credit it in the
  lookup's `tags` and in the `name` of any rule that acts on it, so an analyst
  reading a detection knows whose data decided it.

!!! warning "abuse.ch feeds: free, but not unconditional"
    The abuse.ch datasets (URLhaus, ThreatFox, MalwareBazaar) have required a
    free **Auth-Key** since 2024, and they are offered under fair-use
    principles rather than an open licence. Read
    [abuse.ch Terms of Use](https://abuse.ch/terms-of-use/) and the
    [Fair Use Principles](https://abuse.ch/terms-of-use/#principles) before you
    configure anything.

    Two consequences worth stating plainly:

    - **Use your own Auth-Key**, obtained from your own abuse.ch account, in
      your own organization's configuration.
    - **Commercial or for-profit use may require a paid subscription.** If you
      are an MSSP mirroring these feeds into customer tenants, that is exactly
      the case abuse.ch's fair-use wording is about. Ask them, not us.

## 1. Get a feed URL you are entitled to use

Sign in to the provider and copy the export URL it gives *you*. For abuse.ch,
the file exports embed your key as a path segment rather than a header:

```text
https://urlhaus-api.abuse.ch/v2/files/exports/YOUR-AUTH-KEY-HERE/<export-file>
```

The same shape holds for `threatfox-api.abuse.ch` and `mb-api.abuse.ch`. The
exact filenames are listed on each feed's export page once you are signed in,
so copy them from there rather than from this page.

Pick an export that satisfies three constraints:

| Constraint | Why |
|---|---|
| **Not a `.zip`** | The fetcher stores what it downloads. It does not unpack archives, so a zipped export lands as bytes nothing can read |
| **JSON, or one indicator per line** | Those are the two shapes the `format` field understands. A CSV export is neither |
| **Comfortably under 10 MB** | A `lookup` record is capped at 10 MB. Prefer the "recent" or "online" export over the full historical dump |

!!! tip "Size is the constraint people hit"
    The 10 MB ceiling is a hard limit on the Hive record, not a soft
    recommendation, and the full dumps of the larger feeds are well past it.
    Recent-window exports are also better detection content: an indicator from
    three years ago mostly costs you review time.

## 2. Subscribe the extension

```bash
limacharlie extension subscribe --name ext-lookup-manager --oid $OID
```

## 3. Configure the feed

The extension configuration is a single record holding **every** lookup the
extension manages, so read the current one before you write.

```bash
limacharlie extension config-get --name ext-lookup-manager --oid $OID --output yaml
```

```yaml
# lookups.yaml. This REPLACES the whole configuration.
data:
  lookup_manager_rules:
    - name: abusech-urlhaus-domains
      arl: "[https,urlhaus-api.abuse.ch/v2/files/exports/YOUR-AUTH-KEY-HERE/<export-file>]"
      format: newline
      tags: [ioc, abusech, urlhaus]

    - name: abusech-malwarebazaar-sha256
      arl: "[https,mb-api.abuse.ch/v2/files/exports/YOUR-AUTH-KEY-HERE/<export-file>]"
      format: newline
      tags: [ioc, abusech, malwarebazaar]
```

```bash
limacharlie extension config-set --name ext-lookup-manager \
  --input-file lookups.yaml --oid $OID
```

| Field | Meaning |
|---|---|
| `name` | The `lookup` record key this feed becomes, and therefore the name your rules will reference. Pick it once; renaming it orphans every rule pointing at the old name |
| `arl` | An [Authenticated Resource Locator](../8-reference/authentication-resource-locator.md). `[https,<host-and-path>]` is the whole form you need when the key is already in the path |
| `format` | `json`, `newline`, `yaml` or `optimized`. `newline` is the one for a plain indicator-per-line list |
| `tags` | Copied onto the `lookup` record. Tag the source here so the record's provenance survives the person who added it |

!!! warning "An ARL is comma-delimited"
    The bracket form splits on commas, so a URL containing one will not parse.
    Every abuse.ch export URL is comma-free, but check yours before assuming.

    An ARL also cannot set an arbitrary HTTP header. It supports `basic`,
    `bearer`, `token` and OTX authentication only, which is why the workable
    pattern is a feed that carries its credential in the URL. If your feed
    insists on a custom header, mirror it into a private GitHub repository or a
    GCS bucket yourself and point the ARL at that instead.

## 4. Sync it, and check what landed

A new configuration is **not** fetched immediately. The extension installs a
24-hour sync schedule when you subscribe, so without a manual kick your first
lookup could be a day away:

```bash
limacharlie extension request --name ext-lookup-manager --action sync --oid $OID
```

Then confirm the record exists and holds what you expect:

```bash
limacharlie hive get --hive-name lookup --key abusech-urlhaus-domains \
  --oid $OID --output yaml | head -40
```

A `newline` feed is stored as one key per line with no metadata attached. Blank
lines are dropped; comment lines are not, so a feed with a `#`-prefixed header
block contributes a handful of keys that no message will ever match. Harmless,
but do not mistake them for indicators when you eyeball the record.

!!! danger "Indicators must be lowercase"
    A D&R rule lowercases the value it extracts before looking it up, unless the
    rule sets `case sensitive: true`. A feed shipping uppercase hashes therefore
    matches **nothing**, silently, and looks exactly like a feed with no hits in
    it. Check a sample of the stored keys, not just the record's existence.

## 5. Match messages against it

`EMAIL_MESSAGE` carries the whole parsed message, so a rule reads the links,
attachments and sender out of the event and tests them against the lookup. These
run in the platform seat and produce a **LimaCharlie detection**. See
[Events & Automation](automation.md) for the seat this sits in.

### A link pointing at a known-bad domain

```yaml
# hive: dr-general, record name: email-link-in-ioc-feed
detect:
  op: and
  rules:
    - op: is
      path: routing/event_type
      value: EMAIL_MESSAGE
    - op: lookup
      path: event/links/?/href_url/domain/root
      resource: hive://lookup/abusech-urlhaus-domains

respond:
  - action: report
    name: email-link-matches-urlhaus
    priority: 2
```

`?` walks every element of `links`, and `href_url/domain/root` is the
registrable root domain of the destination, so `login.evil.example` matches an
entry for `evil.example`. That is usually what you want from a domain feed. If
your feed lists full URLs rather than domains, point the path at
`event/links/?/href_url/raw` instead and accept that it will then only match a
byte-identical URL.

### An attachment whose hash is in a malware feed

```yaml
# hive: dr-general, record name: email-attachment-in-ioc-feed
detect:
  op: and
  rules:
    - op: is
      path: routing/event_type
      value: EMAIL_MESSAGE
    - op: lookup
      path: event/attachments/*/sha256
      resource: hive://lookup/abusech-malwarebazaar-sha256

respond:
  - action: report
    name: email-attachment-matches-malwarebazaar
    priority: 1
```

`*` rather than `?` here on purpose: attachment explosion nests unpacked
children under `attachments[].explode.children[]`, recursively, and each child
carries its own hashes. The recursive wildcard reaches the hash of a payload
inside an archive inside an archive, which is the one an attacker was counting
on you not to compute.

### A sender whose domain is in a feed

```yaml
# hive: dr-general, record name: email-sender-domain-in-ioc-feed
detect:
  op: and
  rules:
    - op: is
      path: routing/event_type
      value: EMAIL_MESSAGE
    - op: lookup
      path: event/headers/from/email/domain/root
      resource: hive://lookup/my-sender-domain-blocklist

respond:
  - action: report
    name: email-sender-domain-matches-feed
    priority: 2
```

### Acting on it, not just alerting

A detection is the safe default. When you trust a feed enough to move mail on
its say-so, add the remediation action to the same rule. It goes through the
product's single remediation path, so `alert_only` / `enforce` mode, idempotency
and the audit row all apply unchanged:

```yaml
respond:
  - action: report
    name: email-link-matches-urlhaus
  - action: extension request
    extension name: ext-email-security
    extension action: quarantine_message
    extension request:
      msg_uuid: '{{ .event.msg_uuid }}'
```

Do this feed by feed rather than for feeds in general. A high-confidence,
narrowly-scoped list is worth quarantining on. A large aggregated reputation
list, refreshed daily, is worth a detection and a human.

## Changing the verdict instead of raising a detection

Everything above runs *after* the verdict is decided, so a feed hit produces a
detection alongside a message the engine may still have called benign. Feeding
the match into the verdict itself is the other seat: a `dr-mail` signal rule,
which compounds with the managed pack in the same scoring pass. Rules there
address the message model at the **root**, with no `event/` prefix:

```yaml
# What this will look like. It is NOT accepted today; see the note below.
name: Link matches my IOC feed
phase: pre_verdict
class: detection
weight: 90
confidence: 90
tags: [ioc]
fp_notes: >
  Only as good as the feed. Review the feed's own false-positive rate before
  giving this a weight this high.
detect:
  op: lookup
  path: links/?/href_url/domain/root
  resource: hive://lookup/abusech-urlhaus-domains
```

!!! warning "Lookups in `dr-mail` are not available yet"
    The `dr-mail` Hive validates a rule against a closed list of operators, and
    `lookup` is not on it. A record using it is **refused at write time**, not
    accepted and quietly ignored.

    The reason is deliberate: the operator is service-backed, and enabling it
    before the mail engine supplies it a lookup provider would mean a rule that
    parses and never matches. The two land together or not at all. Until then,
    use the `dr-general` rules above, which work today and give you the same
    match with a detection instead of a score.

## Keeping it honest

- **Freshness is 24 hours by default.** A feed syncs on the extension's
  schedule, so a rule's worst case is a day-old indicator set. For a feed you
  depend on, run a manual `sync` after any change and treat the lookup's
  contents as evidence, not as a live oracle.
- **A miss is not a verdict.** Absence from a feed says only that the feed had
  not published the indicator when it was last fetched. Write rules that treat a
  hit as evidence and never treat a non-hit as clearance.
- **Backtest before you enforce.** `limacharlie mailsec message list
  --link-domain <domain>` tells you who else received a given domain, which is
  the fastest way to find out whether a feed you are about to trust would have
  quarantined something it should not have. See
  [Messages & Triage](messages.md#the-two-ioc-pivots).
- **One feed, one lookup.** Merging several sources into one record saves a
  little configuration and costs you the ability to say which source decided a
  quarantine. Keep them separate and let the rule names carry the attribution.

## Related pages

| | |
|---|---|
| [Lookup Manager](../5-integrations/extensions/limacharlie/lookup-manager.md) | The extension itself, outside a mail context |
| [Authenticated Resource Locator](../8-reference/authentication-resource-locator.md) | The ARL forms and auth types |
| [Detections & Verdicts](detections.md) | How a verdict is produced and what the rules can read |
| [Custom Rules](custom-rules.md) | Writing `dr-mail` rules |
| [Events & Automation](automation.md) | The `EMAIL_*` events and the D&R seat |
