[Documentation](../README.md) > [CLI](README.md) > Detection & Response

# Detection & Response

Commands for D&R rules, false positive rules, rule replay testing, detections, and AI-assisted generation.

## dr

```bash
limacharlie dr list
limacharlie dr list --namespace managed
limacharlie dr get --key my-rule
# Save a reviewed rule (new rules default to disabled).
limacharlie dr set --key my-rule --input-file rule.yaml
# Explicitly create/update and enable an authorized rule.
limacharlie dr set --key my-rule --detect detect.yaml --respond respond.yaml --enabled
limacharlie dr test --input-file rule.yaml --events events.json
limacharlie dr validate --detect detect.yaml --respond respond.yaml
limacharlie dr delete --key my-rule --confirm
```

`--detect`, `--respond`, and `--events` take file paths. A bare rule contains
`detect` and `respond`. For metadata, use a full Hive record with the rule inside
`data` and `usr_mtd` alongside it. Mixing metadata into a bare rule is rejected;
`data.usr_mtd.enabled` is not the record's enabled state. `--enabled` overrides
input metadata. Read back the record to verify its top-level `usr_mtd.enabled`.

Syntax validation does not test coverage. Use positive and negative test events,
and historical replay where available, before enabling a rule.

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
limacharlie ai generate-selector --description 'all Windows servers'
limacharlie ai generate-playbook --description 'respond to ransomware detection'
limacharlie ai summarize-detection --detection-id DETECT_ID
```

All `ai generate-*` commands accept `--prompt` and `--description` as aliases.
Their JSON/YAML output contains a `response` field; save the generated component
inside that field, not the outer envelope, when preparing component files.
The CLI exits with an error for missing, null, empty, or unresolved generated
results. Do not treat those as usable rules or weaken the requested coverage just
to get a smaller response.

## See Also

- [Detection Rules SDK](../sdk/detection-rules.md) — DRRules, FPRules, Replay Python classes
- [Data & Query](data-query.md) — Search and event history
- [Infrastructure](infrastructure.md) — Sync rules with infrastructure-as-code
