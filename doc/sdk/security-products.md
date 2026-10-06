[Documentation](../README.md) > [SDK](README.md) > Security Products

# Cloud Security, Code Security, and Email Security

Use `CloudSec` for both Cloud Security and Code Security, and `Mailsec` for Email Security. Both take an authenticated `Organization`; its UUID determines which tenant every request addresses.

Install or upgrade with `python -m pip install --upgrade limacharlie`. See [installation](../getting-started.md#installation) for setup.

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.cloudsec import CloudSec
from limacharlie.sdk.mailsec import Mailsec

# Uses the selected organization's saved CLI credentials.
org = Organization(Client())
cloud = CloudSec(org)
mail = Mailsec(org)
```

Enable each product once using `limacharlie extension subscribe --name ext-cloud-security` or `--name ext-email-security`. Save credentials in the secret Hive and reference them from `cloudsec_provider` or `mailsec_provider` records. Follow the full [Cloud Security](https://docs.limacharlie.io/cloud-security/getting-started/) and [Email Security](https://docs.limacharlie.io/email-security/getting-started/) provider guides.

## Cloud and Code Security

Check collection health and coverage before reviewing findings. Code scanning additionally needs a supported source-control connection and a `cloudsec_policy` record of type `code_scanning`.

```python
print(cloud.get_scan_status())
print(cloud.get_provider_manifests(provider_type="gcp"))
print(cloud.list_findings(severity=["CRITICAL", "HIGH"], status=["open"]))

print(cloud.get_code_capabilities())
print(cloud.get_code_status())
for repository in cloud.iter_code_repos(limit=100):
    print(repository["repo"], repository.get("scan_status"))
print(cloud.get_code_coverage())
```

`partial`, `unknown`, stale evidence, or an unmatched code-to-cloud join describes a coverage gap. Scans are asynchronous: acceptance is not completion. Availability depends on the provider and deployment; consult `get_code_capabilities()` before configuring PR checks or remediation.

`cloudsec.get` permits ordinary reads. `cloudsec.set` permits ordinary writes; AutoFix and remediation decisions require `cloudsec.respond`. Provider records use `cloudsec_provider.*` and credentials use `secret.*`; policy, saved-query, and code-rule Hives reuse `cloudsec.get/set`.

See the [Cloud and Code Security CLI reference](../cli/cloud-security.md) for build provenance, sanitized IaC maps, runtime evidence, container lineage, and governed remediation.

Entity Pivot `search_entities(q)` accepts prefixes of at least two characters and at most 512 UTF-8 bytes; it preserves `next_cursor` for additional pages.

`pivot_entity(identifier, type=None, at=None)` resolves one identifier and reads the cards of its non-ambiguous `authoritative` or `corroborated` matches (at most 10, de-duplicated). It returns `cards`, `candidates` (the raw resolve results, where ambiguous and `possible` matches stay), every other top-level resolve key, and `truncated` / `card_errors` when more than 10 qualified or a card read failed. No cards are read when `index_ready` is not true or `feature_disabled` is true. `resolve_entities` and `pivot_entity` accept any identifier `type` of at most 64 bytes; the API rejects types it does not know.

Both also take `observation_selectors`, at most 4 read selectors answered from adapter events and needing `insight.evt.get`: `{"type": "vendor_device_id", "platform": "sophos|crowdstrike|office365|entraid|okta|duo", "value": <at most 128 bytes>, "origin_sid": <optional lowercase UUID>}` or `{"type": "foreign_hostname", "value": <at most 512 bytes>}`. The SDK rejects what the API would reject (count, type, platform, sizes, `origin_sid` format, blank or non-UTF-8 values) with `ValueError` before any request. `at` also pins the UTC day the selectors are evaluated on, and an identifier explicitly typed `hostname` that the inventory does not know triggers an implicit `foreign_hostname` lookup while fewer than 4 selectors are used. The response gains `observed_matches[]` and `observations` (`status` of `ok`, `incomplete`, `unavailable` or `forbidden`, optional `reason` of `schema_missing`, `deadline`, `query_budget`, `error` or `bounds`, plus `queries`, `rows` and `truncated`). Candidate Host ids in `observed_matches[].devices[].candidates[].entity` are evidence only, never merged, and `pivot_entity` does not read their cards (call `get_entity`). Cards read with `insight.evt.get` carry `also_seen_as[]` and `cloud_sign_ins[]`, with `observations` on the `get_entity` response; each such card read runs a bounded enrichment (at most 16 queries, 2,000 facts / 4 MiB and 5 seconds), so `pivot_entity` costs one resolve plus, per card, one read and one enrichment. `incomplete`, `unavailable` and `forbidden` mean UNKNOWN, never "none". A signed-in Chrome sensor is a User (`eu_`) entity, an old `eh_` id may `redirect_to` it, and `telemetry_sources[]` entries carry `identity_source` (`parser` or `mapping`).

```python
pivot = cloud.pivot_entity("fixture@example.com", type="email")
for card in pivot["cards"]:
    print(card["card"]["entity"]["id"], card.get("redirect_to"))

observed = cloud.resolve_entities(
    [{"value": "web-01", "type": "hostname"}], at=1791000000,
    observation_selectors=[{"type": "vendor_device_id", "platform": "sophos", "value": "fixture-device-id"}])
print(observed["observations"]["status"])
```

## Email Security

Connect a small pilot scope first. The connection test accepts the **saved provider record name**, rather than a credential or provider name.

```python
print(mail.get_onboarding(provider="m365"))
print(mail.test_connection("pilot"))
print(mail.get_coverage(window_days=7))
print(mail.list_messages(limit=20))  # confirm benign pilot mail arrived, too

# Keep the same filters while walking opaque cursors.
cursor = None
while True:
    page = mail.list_messages(
        verdict=["suspicious", "malicious"], cursor=cursor, limit=200,
    )
    for message in page.get("messages", []):
        print(message)
    cursor = page.get("next_cursor")
    if not cursor:
        break
```

`get_message(msg_uuid)` returns the indexed message and its parsed representation, preferring the preserved message used to judge it. Inspect `mdm_source` and `mdm_unavailable_reason`: older or unavailable content may use a reparse or have no parsed representation.

Raw EML is bytes and requires a separate permission and an audited justification:

```python
raw = mail.get_message_eml("<MSG_UUID>", justification="incident investigation")
with open("suspect.eml", "wb") as output:
    output.write(raw)
```

To inspect a local file without ingesting it, preserve its bytes with base64:

```python
import base64

with open("suspect.eml", "rb") as source:
    encoded = base64.b64encode(source.read()).decode("ascii")
print(mail.analyze(eml_b64=encoded, org_domains=["corp.example"]))
```

`mailsec.get` permits structured reads, `mailsec.set` changes triage and rules, and `mailsec.act` remediates provider mail, revises verdicts, and tests connections. Original-byte downloads require both `mailsec.get` and `mailsec.get.eml`. Provider records use `mailsec_provider.*` and credentials use `secret.*`; policy and `dr-mail` Hives reuse `mailsec.get/set`.

An organization that has opted in (a `mailsec_policy` record of type `sample_sharing`) can copy one message at a time to LimaCharlie to improve detection. `submit_sample(msg_uuid, category, reason)` needs `mailsec.act`, sends the original message to LimaCharlie (deleted after 400 days, or on `withdraw_sample(msg_uuid)` / `withdraw_submission(submission_id)`), and raises `ValueError` for an unknown category (`missed_threat`, `false_positive`, `other`) or a reason that is blank or over 1024 characters. A refusal comes back as `result: "failed"` with `error`, not as an exception. `list_submissions()` (paginated, always returns `enabled` and `available`) and `get_submission()` (includes `reviews`, one timestamp per recorded access to the copy) need `mailsec.get`.

Start with `alert_only`. Manual provider actions need an explicit `force=True` override in that mode; inspect the action and audit outcome. Bulk and campaign actions use preview and confirmation so the executed selection matches what was reviewed. See the [Email Security CLI reference](../cli/email-security.md) for these workflows, verdict revisions, campaigns, user reports, and offboarding.

## Pagination and filters

List methods return one page unless documented as iterators. A short page can still have a `next_cursor`; continue until it is empty. Keep the original filters and return cursors verbatim. Boolean selectors are tri-state: omit them for no constraint, use `True` for a positive selection, and `False` for a negative selection. `list_similar_messages()` returns a bounded candidate set and does not support cursor pagination.
