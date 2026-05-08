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
limacharlie dr test --detect '...' --respond '[...]' --events '[{...}]'
limacharlie dr validate --detect '...' --respond '[...]'
```

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
