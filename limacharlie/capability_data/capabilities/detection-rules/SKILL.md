---
name: detection-rules
description: "Create, edit, validate, test and deploy D&R automation and false-positive rules with the correct event target."
---

# Detection and response rules

First choose the evaluation surface: ordinary telemetry/automation D&R, email verdict (`dr-mail`), or cloud posture (`cloudsec_policy`). Load email-security or cloud-security for those specialized rules; shared detect syntax does not imply shared envelopes, paths, operators or response actions.

Use `limacharlie schema list --oid OID` for learned schemas, then `schema get --name EXACT_KEY --oid OID`. Preserve prefixes such as `evt:` and `det:`; bare event names default to `evt:`. Learned schemas contain observed fields, not the complete platform event catalog. When the cache is empty, use documented references or representative events to establish fields; if the required fields remain unknown, report the missing evidence instead of authoring rules or fixtures using assumed event types or paths. Passing synthetic fixtures proves behavior on those supplied inputs, not that those fields exist in real telemetry. Do not reset an empty schema cache as a discovery step.

For ordinary D&R, establish rule namespace and target. The default target is `edr`; alternate targets include detection, deployment, artifact, artifact_event, schedule, audit and billing. Their event structure and permitted actions differ. A detection-target event name is the originating report name. Inspect a real representative event and schema, then read the relevant operator and action documentation. Match the correct field level (`event/`, `routing/`, or target-specific root). Use `scope` when conditions must match one array element. Verify string case, regex fields and missing-field behavior against the operator reference.

External rule conversion through `dr convert-rules` must use dry-run; deploy converted candidates individually through the artifact workflow. Author the smallest rule meeting the request. AI generation is an optional drafting helper; generated content needs the same validation. Preserve enabled status, namespace and unrelated metadata when editing. Check existing rules for overlapping matches and avoid response loops, especially rules responding to detections or audit events they create. Bound repeated responses using documented suppression/stateful mechanisms.

Use a rule file containing `detect` and `respond`. Metadata belongs to the record, never to rule data: specify `--enabled` or `--disabled`, repeatable `--tag` (replaces the tag list), `--clear-tags`, and `--comment`. When editing, first read the existing namespace/key, preserve unrelated rule fields, and pass current `sys_mtd.etag` with `--etag`. Omitted metadata fields are preserved automatically; new records require explicit enabled state. Full Hive envelopes remain supported with metadata under `usr_mtd` and top-level `etag`.

Use `limacharlie dr deploy --key NAME --input-file rule.json --positive matching.json --negative nonmatching.json --disabled --tag example --comment "description" --oid OID --output json`. The command compiles and evaluates both fixtures, checks current metadata/etag, writes once, and verifies remote data and metadata. Use `--dry-run` to inspect without saving; it still evaluates the fixtures. Fixture files are nonempty JSON arrays, each representing one scenario. Changing inputs invalidates their evidence. Inspect the returned candidate and observed metadata against the user's request and require `status: verified`; fixture selection and matching user intent remain your responsibility.

Receipts survive session restarts. Retrying the same deployment reconciles the current record instead of repeating an uncertain write. Use `dr reconcile --key NAME` to inspect an interrupted deployment. If current state differs, inspect it before using `--accept-current` to acknowledge the observed state; this does not retry or write remotely. Prepare a fresh candidate with current etag for subsequent changes. Do not bypass through raw dr set/import or Hive writes.

If historical replay is appropriate, set an explicit time/sensor scope, inspect its estimate or limits where available, and track the returned job to completion. Historical volume is not an exact future cost forecast.

Deploy the exact tested artifact, then read it back from the same namespace and check enabled state. Changes after testing invalidate previous test evidence. Distinguish saved, enabled, evaluated and observed firing. When no safe live trigger exists, say the deployment is verified but live firing has not been observed. FP suppressions need narrow predicates and a negative control showing unrelated detections survive.

## References

Read the relevant bundled documentation before using unfamiliar schemas or operations. Paths are relative to the documentation docs root.

- `3-detection-response/index.md`
- `3-detection-response/alternate-targets.md`
- `3-detection-response/tutorials/dr-rule-building-guidebook.md`
- `3-detection-response/unit-tests.md`
- `8-reference/detection-logic-operators.md`
- `8-reference/response-actions.md`
- `3-detection-response/false-positives.md`
- `8-reference/schedule-events.md`
