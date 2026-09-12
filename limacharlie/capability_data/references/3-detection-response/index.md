# Detection and Response

Build custom detection logic with automated response actions.

## Documentation

- [Detection and Response Examples](examples.md) - Sample detection rules
- [Detection on Alternate Targets](alternate-targets.md) - Detections beyond endpoint events
- [False Positive Rules](false-positives.md) - Managing false positives
- [Writing and Testing Rules](tutorials/writing-testing-rules.md) - Rule development guide
- [Stateful Rules](stateful-rules.md) - Rules with state tracking
- [Sensor Variables](sensor-variables.md) - Share state across rules with per-sensor variables
- [Unit Tests](unit-tests.md) - Testing detection rules
- [Replay](../5-integrations/services/replay.md) - Replaying events for testing

## Programmatic Management

!!! info "Prerequisites"
    You need a valid API key with `dr.list` and `dr.set` permissions.
    See [API Keys](../7-administration/access/api-keys.md) for setup instructions.

### List D&R Rules

=== "REST API"

    ```bash
    curl -s -X GET "https://api.limacharlie.io/v1/rules/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    hive = Hive(org, "dr-general")
    rules = hive.list()
    for name, record in rules.items():
        print(name, record.enabled)
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)
    rules, _ := org.DRRules()
    for name, rule := range rules {
        fmt.Println(name, rule)
    }
    ```

=== "CLI"

    ```bash
    limacharlie dr list
    # Filter by namespace:
    limacharlie dr list --namespace managed
    ```

### Get a Rule

=== "REST API"

    ```bash
    curl -s -X GET "https://api.limacharlie.io/v1/hive/dr-general/YOUR_OID/RULE_NAME/data" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    hive = Hive(org, "dr-general")
    rule = hive.get("my-detection-rule")
    print(rule.data)
    ```

=== "Go"

    ```go
    hc := limacharlie.NewHiveClient(org)
    record, _ := hc.Get(limacharlie.HiveArgs{
        HiveName:     "dr-general",
        PartitionKey: org.GetOID(),
        Key:          "my-detection-rule",
    })
    fmt.Println(record.Data)
    ```

=== "CLI"

    ```bash
    limacharlie dr get --key my-detection-rule
    # From a specific namespace:
    limacharlie dr get --key my-detection-rule --namespace managed
    ```

### Create or Update a Rule

=== "REST API"

    ```bash
    curl -s -X POST "https://api.limacharlie.io/v1/hive/dr-general/YOUR_OID/my-new-rule/data" \
      -H "Authorization: Bearer $LC_JWT" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d 'data={"detect":{"event":"NEW_PROCESS","op":"ends with","path":"event/FILE_PATH","value":".bat"},"respond":[{"action":"report","name":"bat-file-execution"}]}' \
      -d 'usr_mtd={"enabled":true}'
    ```

=== "Python"

    ```python
    from limacharlie.sdk.hive import Hive, HiveRecord

    hive = Hive(org, "dr-general")
    hive.set(HiveRecord(
        name="my-new-rule",
        data={
            "detect": {
                "event": "NEW_PROCESS",
                "op": "ends with",
                "path": "event/FILE_PATH",
                "value": ".bat",
            },
            "respond": [
                {"action": "report", "name": "bat-file-execution"}
            ],
        },
        enabled=True,
    ))
    ```

=== "Go"

    ```go
    detection := limacharlie.Dict{
        "event": "NEW_PROCESS",
        "op":    "ends with",
        "path":  "event/FILE_PATH",
        "value": ".bat",
    }
    response := limacharlie.List{
        limacharlie.Dict{"action": "report", "name": "bat-file-execution"},
    }
    err := org.DRRuleAdd("my-new-rule", detection, response,
        limacharlie.NewDRRuleOptions{
            IsReplace: true,
            IsEnabled: true,
        })
    ```

=== "CLI"

    ```bash
    # Save your rule to a YAML file, then create-and-enable in one shot.
    # (New hive records are disabled by default; --enabled mirrors the
    # `enabled=True` / `IsEnabled: true` in the SDK examples above.)
    limacharlie dr set --key my-new-rule --input-file rule.yaml --enabled
    ```

### Delete a Rule

=== "REST API"

    ```bash
    curl -s -X DELETE "https://api.limacharlie.io/v1/hive/dr-general/YOUR_OID/my-new-rule" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    hive = Hive(org, "dr-general")
    hive.delete("my-new-rule")
    ```

=== "Go"

    ```go
    err := org.DRRuleDelete("my-new-rule")
    ```

=== "CLI"

    ```bash
    limacharlie dr delete --key my-new-rule --confirm
    ```

### Enable / Disable a Rule

=== "REST API"

    ```bash
    # 1. Read current metadata to preserve tags, expiry, comment:
    CURRENT=$(curl -s -X GET \
      "https://api.limacharlie.io/v1/hive/dr-general/YOUR_OID/my-rule/mtd" \
      -H "Authorization: Bearer $LC_JWT")

    # 2. Merge and update (set enabled to false, keep other fields):
    curl -s -X POST "https://api.limacharlie.io/v1/hive/dr-general/YOUR_OID/my-rule/mtd" \
      -H "Authorization: Bearer $LC_JWT" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d 'usr_mtd={"enabled":false,"expiry":0,"tags":["my-tag"],"comment":"kept"}'
    ```

    !!! warning
        The API **replaces** `usr_mtd` entirely. Sending only `{"enabled":false}` will reset tags, expiry, and comment to their defaults. Always read the current metadata first and resend all fields.

=== "Python"

    ```python
    hive = Hive(org, "dr-general")
    # Read-modify-write to preserve other metadata:
    record = hive.get_metadata("my-rule")
    record.enabled = False  # or True to re-enable
    hive.set(record)
    ```

=== "Go"

    ```go
    hc := limacharlie.NewHiveClient(org)
    // Read current metadata first to preserve tags, expiry, comment.
    existing, _ := hc.GetMTD(limacharlie.HiveArgs{
        HiveName:     "dr-general",
        PartitionKey: org.GetOID(),
        Key:          "my-rule",
    })
    enabled := false
    hc.Add(limacharlie.HiveArgs{
        HiveName:     "dr-general",
        PartitionKey: org.GetOID(),
        Key:          "my-rule",
        Enabled:      &enabled,
        Tags:         existing.UsrMtd.Tags,
        Expiry:       &existing.UsrMtd.Expiry,
        Comment:      &existing.UsrMtd.Comment,
    })
    ```

=== "CLI"

    ```bash
    # Disable a rule (reads metadata first to preserve other fields):
    limacharlie dr disable --key my-rule
    # Re-enable:
    limacharlie dr enable --key my-rule
    # Or using the generic hive command:
    limacharlie hive disable --hive-name dr-general --key my-rule
    ```

### Test a Rule Against Sample Events

=== "REST API"

    ```bash
    curl -s -X POST "https://api.limacharlie.io/v1/rules/YOUR_OID/test" \
      -H "Authorization: Bearer $LC_JWT" \
      -H "Content-Type: application/json" \
      -d '{
        "rule_name": "my-detection-rule",
        "events": [{"event": {"FILE_PATH": "c:\\temp\\test.bat"}, "routing": {}}]
      }'
    ```

=== "Python"

    ```python
    from limacharlie.sdk.replay import Replay

    replay = Replay(org)
    results = replay.scan_events(
        events=[{"event": {"FILE_PATH": "c:\\temp\\test.bat"}, "routing": {}}],
        rule_name="my-detection-rule",
        trace=True,
    )
    print(results)
    ```

=== "Go"

    ```go
    hc := limacharlie.NewHiveClient(org)
    // Retrieve the rule, then use the replay service
    // to test it against sample events.
    record, _ := hc.Get(limacharlie.HiveArgs{
        HiveName:     "dr-general",
        PartitionKey: org.GetOID(),
        Key:          "my-detection-rule",
    })
    fmt.Println(record.Data)
    ```

=== "CLI"

    ```bash
    # Test an existing rule against a file of sample events:
    limacharlie dr test --name my-detection-rule --events events.json --trace
    # Test an inline rule file:
    limacharlie dr test --input-file rule.yaml --events events.json
    ```

### Replay a Rule Against Historical Data

=== "REST API"

    ```bash
    curl -s -X POST "https://api.limacharlie.io/v1/rules/YOUR_OID/replay" \
      -H "Authorization: Bearer $LC_JWT" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "rule_name=my-detection-rule" \
      -d "start=1700000000" \
      -d "end=1700086400" \
      -d "dry_run=true"
    ```

=== "Python"

    ```python
    from limacharlie.sdk.replay import Replay

    replay = Replay(org)
    results = replay.run(
        rule_name="my-detection-rule",
        start=1700000000,
        end=1700086400,
        dry_run=True,
        trace=True,
    )
    print(results)
    ```

=== "Go"

    ```go
    // Replay is available via the replay service.
    // Use the REST API or CLI for replay operations.
    ```

=== "CLI"

    ```bash
    limacharlie dr replay --name my-detection-rule \
      --start 1700000000 --end 1700086400 \
      --dry-run --trace
    # Replay on a specific sensor:
    limacharlie dr replay --name my-detection-rule \
      --start 1700000000 --end 1700086400 --sid SENSOR_ID
    ```

### Validate Rule Components

=== "REST API"

    ```bash
    curl -s -X POST "https://api.limacharlie.io/v1/hive/dr-general/YOUR_OID/test-rule/validate" \
      -H "Authorization: Bearer $LC_JWT" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d 'data={"detect":{"event":"NEW_PROCESS","op":"is","path":"event/FILE_PATH","value":"test.exe"},"respond":[{"action":"report","name":"test"}]}'
    ```

=== "Python"

    ```python
    from limacharlie.sdk.hive import Hive, HiveRecord

    hive = Hive(org, "dr-general")
    result = hive.validate(HiveRecord(
        name="test-rule",
        data={
            "detect": {
                "event": "NEW_PROCESS",
                "op": "is",
                "path": "event/FILE_PATH",
                "value": "test.exe",
            },
            "respond": [
                {"action": "report", "name": "test"}
            ],
        },
    ))
    print(result)
    ```

=== "Go"

    ```go
    // Use the Hive validate endpoint via the REST API.
    ```

=== "CLI"

    ```bash
    limacharlie dr validate --detect detect.yaml --respond respond.yaml
    ```

### Export and Import Rules

=== "REST API"

    ```bash
    # Export all rules
    curl -s -X GET "https://api.limacharlie.io/v1/rules/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    hive = Hive(org, "dr-general")
    all_rules = hive.list()
    for name, record in all_rules.items():
        print(name, record.data)
    ```

=== "Go"

    ```go
    rules, _ := org.DRRules()
    for name, rule := range rules {
        fmt.Println(name, rule)
    }
    ```

=== "CLI"

    ```bash
    # Export all rules to YAML:
    limacharlie dr export > rules.yaml
    # Import rules from YAML (dry-run first):
    limacharlie dr import --input-file rules.yaml --dry-run
    limacharlie dr import --input-file rules.yaml
    ```

---

## See Also

- [Writing Rules](tutorials/writing-testing-rules.md)
- [Detection Examples](examples.md)
- [Response Actions](../8-reference/response-actions.md)
- [False Positive Rules](false-positives.md)
- [LCQL Queries](../4-data-queries/index.md)
