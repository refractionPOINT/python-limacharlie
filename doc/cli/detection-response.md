[Documentation](../README.md) > [CLI](README.md) > Detection & Response

# Detection & Response

Commands for D&R rules, false positive rules, rule replay testing, detections, and AI-assisted generation.

## dr

```bash
limacharlie dr list
limacharlie dr list --namespace managed
limacharlie dr get --name my-rule
limacharlie dr create --name my-rule \
  --detect '{"op":"is","event":"NEW_PROCESS"}' \
  --respond '[{"action":"report","name":"my-detection"}]'
limacharlie dr update --name my-rule --detect '...' --respond '[...]'
limacharlie dr delete --name my-rule
limacharlie dr test --input-file rule.yaml --events events.json
limacharlie dr test --name audit-rule --events audit-events.json --stream audit
limacharlie dr validate --detect '...' --respond '[...]'
```

`dr test` infers the Replay event layout from an inline rule's `detect.target`:
`detection` selects `detect` (event name in `cat`), `audit` selects `audit`
(event name in `etype`), and other targets select `event` (event name in
`routing.event_type`). `--stream event|detect|audit` overrides this choice;
specify it for non-EDR rules tested by name. Fixtures must preserve the real
target's event structure rather than wrapping audit or detection data as EDR.

## fp

```bash
limacharlie fp list
limacharlie fp get --name my-fp
limacharlie fp create --name my-fp --rule '{"op":"is","cat":"my-detection"}'
limacharlie fp delete --name my-fp
```

## replay

```bash
limacharlie replay run --rule-name my-rule --start 1704067200 --end 1704153600
limacharlie replay run --detect '{"op":"is"}' --respond '[{"action":"report"}]' --start 1704067200 --end 1704153600
```

## detection

```bash
limacharlie detection list --start 1704067200 --end 1704153600
limacharlie detection get --id DETECT_ID
```

## ai

```bash
limacharlie ai generate-rule --prompt 'detect powershell downloading files'
limacharlie ai generate-query --prompt 'find all DNS lookups to evil.com'
limacharlie ai generate-selector --prompt 'all Windows servers'
limacharlie ai generate-playbook --prompt 'respond to ransomware detection'
limacharlie ai summarize-detection --id DETECT_ID
```

## See Also

- [Detection Rules SDK](../sdk/detection-rules.md) — DRRules, FPRules, Replay Python classes
- [Data & Query](data-query.md) — Search and event history
- [Infrastructure](infrastructure.md) — Sync rules with infrastructure-as-code


## Prepare and check a draft from telemetry

```bash
limacharlie dr prepare --event-type DNS_REQUEST --last 24h --workspace draft --oid OID --output json
# If status is prepared, derive fixtures from draft/evidence.json using a short local script.
# Write candidate.json, positive.json, negative.json; do not retype full event envelopes.
limacharlie dr check --workspace draft --oid OID --output json
```

Preparation samples a literal event type across the organization when no endpoint is specified. It uses the query `*|EVENT_TYPE|*`, stops after at most two completed search pages, and retains at most the requested sample limit (default 20, range 1–1000). For endpoint-specific requests, supply an exact hostname or SID and optionally an event type; this reads that sensor only. The response records sampling scope and search completion separately from sample size. An empty or partial sample never establishes organization-wide absence. When status is `needs_evidence`, obtain representative evidence before writing fixtures; checking an empty evidence workspace fails. Relative windows accept minutes, hours or days, up to 31 days. It accepts a new or empty directory and refuses to overwrite a workspace containing files. Evidence and full observed paths are saved privately; the response includes a bounded path preview and focused operator guidance. Samples do not establish exhaustive coverage.

Checking performs structural diagnostics before server replay, tests each event in each fixture array independently, and exits nonzero on failure. For stateful/correlated rules, supply arrays of event sequences (nested arrays); each sequence is one independently checked scenario. The report distinguishes captured from modified/synthetic fixtures and sample grounding from unknown fields. It never deploys. Changes require a new check; hashes in check.json identify the tested files. Deploy the exact tested files with `dr deploy` after authorization.

In AI agent mode, preparation activates a per-user-turn drafting guardrail that blocks endpoint tasking, historical scans and remote mutations. AI Sessions clears it on the next actual user request, not tool results. This policy does not sandbox arbitrary Python/HTTP or replace least-privilege credentials.

Pass `--workspace draft` to `dr deploy` together with the candidate/fixture paths to require a successful check of those exact inputs. Modified files, wrong organization and failed checks are rejected. Deployment still repeats engine validation and preserves its existing metadata/etag guarantees. Both check and deploy accept nested fixture arrays for independent stateful scenarios.

### Experimental typed drafting: `dr build`

`dr build --workspace NEW_DIR --intent-file intent.json --source lc_sensor|custom_json
[--evidence-file examples.json]` compiles a bounded, versioned intent into a report-only
D&R draft and tests each constructed scenario against Replay. It never installs a rule.
AI Sessions can supply the intent with a short interpretation call; the workflow,
field grounding, fixture construction, validation and artifacts live in this package.

Version 1 intent example:

```json
{"version":1,"event_type":"OT_APP","name":"high-pressure","condition":{"op":"gt","path":["event","pressure"],"value":80}}
```

Conditions support `eq`, `gt`, `lt`, `contains`, `basename`, `all`/`any` with `rules`,
and `some` with an array `path` and a relative `where` condition. `some` preserves
same-element conjunctions. String comparisons explicitly accept `case_sensitive`.
Unsupported operators or ambiguous types require the general drafting workflow.

`custom_json` accepts arbitrary observed JSON fields, supplied as an array of LC
`{"routing":{"event_type":"OT_APP"},"event":{...}}` envelopes. This is not an
EDR schema allowlist. Missing fields and mixed incompatible types require more
evidence; they are never silently invented or coerced. Literal slash/wildcard keys,
regex, temporal sequences and non-report responses are outside this proof's compiler.

`lc_sensor` uses the specific DNS/process field contracts pinned to the sensor source
revision in `dr_workflow.py`. These contracts describe LC EDR fields only. A successful
fixture check says nothing about whether an organization collects those events, or
whether the rule provides comprehensive detection coverage. `dr check --workspace`
rechecks the artifacts; edited contract-backed candidates must be rebuilt from intent.
