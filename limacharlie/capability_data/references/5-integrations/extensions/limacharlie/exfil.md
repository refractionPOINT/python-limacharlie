# Exfil (Event Collection)

The Exfil Extension helps manage which real-time [events](../../../8-reference/edr-events.md) get sent from EDR sensors to LimaCharlie. By default, LimaCharlie Sensors send events to the cloud based on a standard profile. This extension exposes those profiles for customization. The Exfil extension allows you to customize Event Collection from LimaCharlie Sensors, as well as mitigate sensors with high I/O or large [detection and response](../../../3-detection-response/examples.md) rulesets.

> Event Collection Rule Synchronization
>
> Please note that Exfil (or Event Collection) rule configurations are synchronized with sensors every few minutes.

## Enabling the Exfil Extension

To enable the Exfil extension, navigate to the [Exfil extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-exfil) in the marketplace. Select the Organization you wish to enable the extension for, and select **Subscribe**.

![exfil 1.png "image(231).png"](../../../assets/images/exfil-1.png "image(231).png")

After clicking subscribe, the Exfil extension should be available almost immediately.

## Using the Exfil Extension

Once the extension is enabled, you will see an **Event Collection** option under **Sensors** in the LimaCharlie web UI.

![exfil 2.png "image(227).png"](../../../assets/images/exfil-2.png "image(227).png")

There are three rule options within the Exfil extension:

- **Event Collection Rules** manage events sent by the Sensor to the LimaCharlie cloud.
- **Performance Rules** are useful for high I/O servers, but may impact event accuracy. This feature is available only on Windows Sensors.
- **Watch Rules** allow for conditional operators for an event, allowing you to specify a list of sensors to help manage high-volume events. Conditional operators for Watch Rule events include:

  - The **event** itself, such as `MODULE_LOAD`.
  - The **path** within the event component to be evaluated, such as `FILE_PATH`.
  - The **operator** to evaluate or compare that should be done between the path and the value.
  - The **value** to be used in comparison with the operator.

A sample **Watch Rule** might be

```text
Event: MODULE_LOAD
Path: FILE_PATH
Operator: ends with
Value: wininet.dll
```

The above rule would configures the sensor(s) to send *only* `MODULE_LOAD` events where the `FILE_PATH` ends with the value `wininet.dll`.

### Watch Rule Fields

When authoring Watch Rules outside of the web UI (REST API, hive, or git-sync), the schema is strict about types. The most common cause of a Watch Rule failing to apply is a scalar where a list is expected.

| Field                | Type                                                        | Required |
|----------------------|-------------------------------------------------------------|----------|
| `event`              | string (single event name, e.g. `FILE_CREATE`)              | yes      |
| `operator`           | enum: `is`, `contains`, `starts with`, `ends with`          | yes      |
| `value`              | string                                                      | yes      |
| `path`               | **list** of strings                                         | yes      |
| `filters.platforms`  | **list** of strings (e.g. `[mac]`, `[windows]`, `[linux]`)  | yes      |
| `filters.tags`       | **list** of strings                                         | optional |

> Common gotcha
>
> `path`, `filters.platforms`, and `filters.tags` must be YAML lists, not bare scalars. `path: FILE_PATH` will fail validation; `path: [FILE_PATH]` (or the multi-line `- FILE_PATH` form) is correct. The same applies for `filters.platforms` and `filters.tags`.

### Watch Rule Operators

Watch Rules support exactly four operators. The configured `value` is compared **literally** (not as a pattern) against the string at `path` in the event:

| Operator      | Match condition                                                |
|---------------|----------------------------------------------------------------|
| `is`          | The field value exactly equals the configured value.            |
| `contains`    | The configured value appears anywhere in the field value.       |
| `starts with` | The field value begins with the configured value.               |
| `ends with`   | The field value ends with the configured value.                 |

Additional behavior to be aware of:

- **No regular expressions, globs, or wildcards.** A value such as `^/Users/[^/]+/(Downloads|Desktop)/` is matched character-for-character — including the `^`, `[`, `(`, etc. — and will not behave as a regex.
- **Case-insensitive.** Both the configured value and the event field are lowercased before comparison, so `wininet.dll` and `WININET.DLL` match.
- **String fields only.** Only string-typed event fields are evaluated; numeric fields at the configured `path` are skipped.
- **Unknown operators are dropped silently.** A Watch Rule whose `operator` is anything other than the four values above will not match any event. Use one of the supported operators above (or combine multiple Watch Rules) to express the condition you need.

> Performance Rules
>
> Performance rules, applied via tag to a set of Sensors, are useful for high I/O systems. These rules can be set via the web application or REST API.

### Throughput Limits

Enabling *every* event for Exfil can produce an exceedingly large amount of traffic. Our first recommendation would be to optimize events required for detection & response rules, in order to ensure that all rules are active. We'd also recommend prioritizing events that contribute to outputs, such as forwarded `DNS_REQUESTS`.

LimaCharlie attempts to process all events in real-time. However, if events fall behind, they are enqueued to a certain limit. If that limit is reached (e.g. in the case of a long, sustained burst or enabling *all* events at the same time), the queue may eventually get dropped. In that event, an error is emitted to the platform logs.

Seeing event collection errors is a sign you may need to do one of the following:

1. Reduce the population of events collected.
2. Reduce the number of  rules you run or rule complexity.
3. Adopt a selective subset of events by utilizing Watch Rules that only bring back events with specific values.
4. Enable the IR mode (below).

#### Afterburner

Before a backlogged queue is dropped, LimaCharlie attempts to increase performance by entering a special mode we call "afterburner." This mode tries to address one of the common scenarios that can lead to a large influx of data: spammy processes starting over and over. This happens in situations such as the building of software, in which executables like `devenv.exe` or `git` can be called hundreds of times per second. The afterburner mode attempts to (1) de-duplicate those processes and (2) assess only each one through the D&R rules and Outputs.

#### IR Mode

The afterburner mode does not address all possible causes or situations. To help with this, LimaCharlie offers "IR mode." This mode is enabled by tagging a LimaCharlie sensor with the tag `ir`. The goal of "IR mode" is to provide a solution for users who want to record a very large number of events, but do not need to run D&R rules over all of them. When enabled, "IR mode" will not de-duplicate events. Furthermore, D&R rules will *only* be run against the follow event types:

1. `CODE_IDENTITY`
2. `DNS_REQUEST`
3. `NETWORK_CONNECTIONS`
4. `NEW_PROCESS`

IR mode is designed to give a balance between recording all events, while maintaining basic D&R rule capabilities.

## Configuration via Hive

In addition to the web UI and the REST actions below, the full Exfil configuration is stored under the `extension_config` hive at the key `ext-exfil` and can be managed via [git-sync](git-sync.md) or directly with the LimaCharlie CLI.

A complete, valid Watch Rule looks like:

```yaml
exfil_rules:
  watch:
    Mac User Downloads File Events:
      event: FILE_CREATE
      operator: contains
      value: /Downloads/
      path:
        - FILE_PATH
      filters:
        platforms:
          - mac
        tags:
          - file-watch
```

Note the YAML list form (`-`) used for `path`, `filters.platforms`, and `filters.tags`. See [Watch Rule Fields](#watch-rule-fields) for the full schema.

### Validate Before Pushing

If a hive `set` against `extension_config/ext-exfil` fails or times out without surfacing a clear error, the most likely cause is a schema-validation failure. You can dry-run any config against the live schema before writing it:

```bash
limacharlie hive validate \
  --hive-name extension_config \
  --key ext-exfil \
  --input-file my-exfil-config.yaml \
  --output yaml
```

An empty (`{}`) response means the record is valid and would be accepted by a subsequent `hive set`. Any other output is a description of the validation failure — fix the offending field and re-run `validate` until it returns empty.

`validate` is read-only: it never modifies the stored configuration regardless of the result.

## Actions via REST API

The following REST API actions can be sent to interact with the Exfil extension:

### List Rules

```json
{
  "action": "list_rules"
}
```

### Event Collection Rules

#### Add Event Collection Rule

```json
{
  "action": "add_event_rule",
  "name": "windows-vip",
  "events": [
    "NEW_TCP4_CONNECTION",
    "NEW_TCP6_CONNECTION"
  ],
  "tags": [
    "vip"
  ],
  "platforms": [
    "windows"
  ]
}
```

#### Remove Event Collection Rule

```json
{
  "action": "remove_event_rule",
  "name": "windows-vip"
}
```

### Watch Rules

#### Add Watch Rule

```json
{
  "action": "add_watch",
  "name": "wininet-loading",
  "event": "MODULE_LOAD",
  "operator": "ends with",
  "value": "wininet.dll",
  "path": [
    "FILE_PATH"
  ],
  "tags": [
    "server"
  ],
  "platforms": [
    "windows"
  ]
}
```

#### Remove Watch Rule

```json
{
  "action": "remove_watch",
  "name": "wininet-loading"
}
```

### Performance Rules

#### Add Performance Rule

```json
{
  "action": "add_perf_rule",
  "name": "sql-servers",
  "tags": [
    "sql"
  ],
  "platforms": [
    "windows"
  ]
}
```

#### Remove Performance Rule

```json
{
  "action": "remove_perf_rule",
  "name": "sql-servers"
}
```

## See Also

- [Compliance Frameworks](../../../9-ai-sessions/compliance/frameworks.md) -- Exfil rules ship as part of every framework's recommended baseline. The `compliance-baseline-deploy` skill writes them under `data.exfil_rules.list` while preserving existing default rules (e.g., `default-chrome`, `default-linux`).
- [Compliance Gap Analysis](../../../9-ai-sessions/compliance/gap-analysis.md) -- Section A of the gap report enumerates missing exfil events per framework and per platform, with the relevant control citations.
