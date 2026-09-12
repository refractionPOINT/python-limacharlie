# D&R-Driven AI Sessions

D&R-Driven AI Sessions allow you to automatically spawn Claude AI sessions in response to detections, events, or any condition matched by a Detection & Response rule. This enables powerful automated investigation, triage, and response workflows.

## Overview

When a D&R rule matches, the `start ai agent` response action launches a Claude session with:

- A prompt containing the context you specify
- The auto-installed `limacharlie` CLI for LimaCharlie operations (authenticated via `lc_api_key_secret`), plus any built-in tools and external MCP servers you configure
- Optional event data extracted and included automatically

The session runs autonomously, performing the investigation or analysis you've defined, and the results can be captured via outputs or stored for later review.

## The `start ai agent` Action

There are two ways to configure the action: **inline mode** (all parameters in the rule) or **definition mode** (referencing a pre-configured AI agent from the Hive).

### Inline Mode

Specify all session parameters directly in the D&R rule:

```yaml
respond:
  - action: start ai agent
    prompt: "Your instructions to Claude..."
    anthropic_secret: hive://secret/my-anthropic-key
```

#### Required Parameters (Inline Mode)

| Parameter | Description |
|-----------|-------------|
| `prompt` | The instructions for Claude. Supports [template strings](../4-data-queries/template-transforms.md) to include event data. |
| `anthropic_secret` | Your Anthropic API key. Use `hive://secret/<name>` to reference a [Hive Secret](../7-administration/config-hive/secrets.md). To route Claude through AWS Bedrock instead, use the manual environment-variable mode — see [Alternative AI Providers](alternative-providers.md). |

#### Optional Parameters (Inline Mode)

| Parameter | Description |
|-----------|-------------|
| `name` | Session name. Supports template strings. Useful for identifying sessions in logs. |
| `lc_api_key_secret` | LimaCharlie API key for org-level API access. Use `hive://secret/<name>`. |
| `lc_uid_secret` | LimaCharlie User ID. Required when `lc_api_key_secret` is a user API key (as opposed to an org API key). Use `hive://secret/<name>`. |
| `idempotent_key` | Unique key to prevent duplicate sessions. Supports template strings. |
| `debounce_key` | Serializes sessions: only one active session per key. New requests queue behind the active session and re-fire when it ends. Supports template strings. |
| `data` | Extract event data fields to include in the prompt as JSON. |
| `profile` | Inline session configuration (tools, model, limits, etc.). |
| `profile_name` | Reference a saved profile by name. Currently only supported for user sessions; for D&R sessions, use inline `profile` instead. |

> Note: You can specify either `profile` (inline) or `profile_name` (reference), but not both.

### Definition Mode

Reference a pre-configured AI agent definition stored in the Hive:

```yaml
respond:
  - action: start ai agent
    definition: hive://ai_agent/my-triage-bot
```

In definition mode, all session configuration (prompt, anthropic key, profile, etc.) comes from the referenced AI agent record. No other parameters are required.

#### Per-rule Augmentation

A rule using `definition:` can also supply its own `prompt:` and/or `data:` fields. When present, they are merged with the values on the `ai_agent` record so a single agent definition can be reused across many rules with per-rule, task-specific augmentation:

- **`prompt`** — appended to the `ai_agent` record's prompt with a blank line separating them. The agent's prompt acts as the stable core; the rule's prompt adds rule-specific flavor.
- **`data`** — extracted from the event rule-side (templates, `secret://` and gjson callbacks resolve as usual) and merged with the `ai_agent` record's own data extraction. The merged dictionary is appended to the prompt as a single JSON code block. **Rule keys override agent keys on collision**, so a rule can substitute or add specific fields for its trigger.

```yaml
respond:
  - action: start ai agent
    definition: hive://ai_agent/detection-investigator
    debounce_key: "investigate-{{ .routing.sid }}"
    # Appended to the ai_agent record's prompt
    prompt: |
      Focus specifically on credential-theft TTPs for this trigger.
    # Merged with the ai_agent record's data: extraction; rule keys win
    data:
      trigger_rule: "credential-dumping-suspect"
      detection_name: "{{ .detect.cat }}"
```

`debounce_key` can also be set at the action level even in definition mode (it overrides the value on the `ai_agent` record):

```yaml
respond:
  - action: start ai agent
    definition: hive://ai_agent/my-triage-bot
    debounce_key: "investigate-{{ .routing.sid }}"
```

## Configuration Options

### Prompt Templating

The `prompt` parameter supports LimaCharlie's template syntax. You can include event data directly in your instructions:

```yaml
- action: start ai agent
  prompt: |
    A suspicious process was detected on {{ .routing.hostname }}.

    Process: {{ .event.FILE_PATH }}
    Command Line: {{ .event.COMMAND_LINE }}
    User: {{ .event.USER_NAME }}

    Please investigate this activity and determine if it's malicious.
  anthropic_secret: hive://secret/anthropic-key
```

### Data Extraction

Use the `data` parameter to extract specific fields and include them as structured JSON:

```yaml
- action: start ai agent
  prompt: "Analyze this detection and provide a severity assessment."
  anthropic_secret: hive://secret/anthropic-key
  data:
    hostname: "{{ .routing.hostname }}"
    sensor_id: "{{ .routing.sid }}"
    process_path: "{{ .event.FILE_PATH }}"
    command_line: "{{ .event.COMMAND_LINE }}"
    parent_process: "{{ .event.PARENT/FILE_PATH }}"
    detection_name: "{{ .detect.cat }}"
```

The extracted data is appended to the prompt as a JSON code block.

### Idempotent Sessions

Prevent duplicate sessions for the same event using `idempotent_key`:

```yaml
- action: start ai agent
  prompt: "Investigate this detection..."
  anthropic_secret: hive://secret/anthropic-key
  idempotent_key: "{{ .detect.detect_id }}"
```

If a session with the same idempotent key was recently created (within 24 hours), the action is skipped.

### Debounced Sessions

Use `debounce_key` to serialize sessions so only one runs at a time per key. When a session is already active for a given debounce key, new requests are queued. When the active session ends, the most recent queued request is automatically re-fired.

This is useful for workflows where multiple detections may fire in rapid succession but should be handled sequentially by a single agent (e.g., a triage bot processing cases one at a time).

```yaml
- action: start ai agent
  prompt: "Investigate this case..."
  anthropic_secret: hive://secret/anthropic-key
  debounce_key: "triage-bot"
```

Unlike `idempotent_key` which silently drops duplicates, `debounce_key` guarantees the latest request will eventually be processed — it just waits for the current session to finish first. Only the most recent pending request is kept per key. The key supports template strings for dynamic serialization:

```yaml
# Serialize per sensor — one active investigation per endpoint
debounce_key: "investigate-{{ .routing.sid }}"
```

> **Debounce vs Idempotent**: Use `idempotent_key` when the same event should never create more than one session. Use `debounce_key` when each event should be processed, but sequentially rather than in parallel.

### Session Profiles

Profiles let you configure Claude's behavior, available tools, and resource limits.

#### Inline Profile

```yaml
- action: start ai agent
  prompt: "Investigate this activity..."
  anthropic_secret: hive://secret/anthropic-key
  profile:
    # Tool access
    allowed_tools:
      - Bash
      - Read
      - Grep
      - Glob
      - WebFetch
    denied_tools:
      - Write
      - Edit

    # Permission mode
    permission_mode: acceptEdits

    # Model configuration
    model: claude-sonnet-4-20250514
    max_turns: 50
    max_budget_usd: 5.0
    one_shot: true  # Complete initial task then terminate (this is the default for D&R sessions)
    ttl_seconds: 1800

    # Environment variables
    environment:
      LOG_LEVEL: debug
      API_KEY: hive://secret/external-api-key
```

> LimaCharlie itself does **not** need an `mcp_servers` entry — the session reaches LimaCharlie through the auto-installed `limacharlie` CLI, authenticated by the `lc_api_key_secret` you provide. The `mcp_servers` map below is only for *external/third-party* tools (threat-intel, ticketing, etc.).

#### Profile Options

> The full pattern grammar for `allowed_tools` and `denied_tools` (built-in Claude Code tool names, `Bash(prefix:*)` scoping, and MCP `mcp__server__tool` names), along with the precedence rules and `permission_mode` semantics, lives on the dedicated [Tool Permissions & Profiles](tool-permissions.md) page. Unattended D&R agents typically want `permission_mode: bypassPermissions` so tool calls don't block on approval prompts.

| Option | Type | Description |
|--------|------|-------------|
| `allowed_tools` | list | Tools Claude can use. If empty, all tools are allowed. See [Tool Permissions & Profiles](tool-permissions.md#tool-name-grammar). |
| `denied_tools` | list | Tools Claude cannot use. Takes precedence over `allowed_tools`. See [Tool Permissions & Profiles](tool-permissions.md#allowed_tools-vs-denied_tools). |
| `permission_mode` | string | `acceptEdits` (default), `plan`, or `bypassPermissions`. See [Tool Permissions & Profiles](tool-permissions.md#permission_mode). |
| `model` | string | Claude model to use (e.g., `claude-sonnet-4-20250514`) |
| `max_turns` | integer | Maximum conversation turns before auto-termination |
| `max_budget_usd` | float | Maximum spend limit in USD |
| `one_shot` | boolean | When `true`, session completes all work for the initial prompt (including tools, skills, and subagents) then terminates automatically. Default: `true` for D&R-triggered sessions. |
| `ttl_seconds` | integer | Maximum session lifetime in seconds. Capped at 24 hours. |
| `environment` | map | Environment variables. Values can use `hive://secret/` |
| `mcp_servers` | map | External/third-party MCP server configurations (see below). Not needed for LimaCharlie access. |

### MCP Server Configuration

MCP (Model Context Protocol) servers extend Claude's capabilities with *external/third-party* data sources and tools.

> You do **not** configure LimaCharlie here. The session already has the auto-installed `limacharlie` CLI for all LimaCharlie operations (authenticated by `lc_api_key_secret`). Reserve `mcp_servers` for outside services such as threat-intel, ticketing, or custom enrichment tools.

#### HTTP MCP Server

```yaml
mcp_servers:
  virustotal:
    type: http
    url: https://vt-mcp.example.com
    headers:
      x-apikey: hive://secret/vt-api-key
```

#### Stdio MCP Server

```yaml
mcp_servers:
  custom-tool:
    type: stdio
    command: /usr/bin/my-tool
    args:
      - --config
      - /etc/my-tool.conf
    env:
      API_KEY: hive://secret/tool-api-key
```

## Examples

### Example 1: Basic Detection Investigation

Automatically investigate when a suspicious process is detected:

```yaml
detect:
  event: NEW_PROCESS
  op: contains
  path: event/COMMAND_LINE
  value: -encodedcommand

respond:
  - action: report
    name: encoded-powershell-command
  - action: start ai agent
    prompt: |
      A PowerShell process with an encoded command was detected.

      Decode the command and analyze what it does.
      Check for persistence mechanisms, lateral movement, or data exfiltration.
      Provide a severity assessment and recommended response actions.
    anthropic_secret: hive://secret/anthropic-key
    data:
      command_line: "{{ .event.COMMAND_LINE }}"
      hostname: "{{ .routing.hostname }}"
      user: "{{ .event.USER_NAME }}"
```

### Example 2: Automated Triage with the LimaCharlie CLI

The session reaches LimaCharlie through the auto-installed `limacharlie` CLI — just provide `lc_api_key_secret` so the CLI is authenticated. No `mcp_servers` entry is needed for LimaCharlie itself:

```yaml
detect:
  target: detection
  event: "*"
  op: is greater than
  path: priority
  value: 3

respond:
  - action: start ai agent
    prompt: |
      A high-priority detection was triggered. Use the `limacharlie` CLI to:

      1. Get information about the sensor where this occurred
      2. Query recent events from the same sensor
      3. Check if the same detection occurred on other sensors
      4. Look up any relevant threat intelligence

      Produce a summary report with:
      - What happened
      - Scope of impact
      - Recommended immediate actions
      - Suggested long-term mitigations
    anthropic_secret: hive://secret/anthropic-key
    lc_api_key_secret: hive://secret/lc-api-key
    idempotent_key: "{{ .detect.detect_id }}"
    profile:
      max_turns: 100
      max_budget_usd: 10.0
```

### Example 3: Threat Hunting Automation

Automatically investigate IoC matches from threat intelligence:

```yaml
detect:
  event: DNS_REQUEST
  op: lookup
  path: event/DOMAIN_NAME
  resource: lookup/threat-domains

respond:
  - action: report
    name: threat-intel-domain-match
  - action: start ai agent
    name: "threat-hunt-{{ .routing.sid }}"
    prompt: |
      A DNS request to a known malicious domain was detected.

      Using the available tools:
      1. Identify the process that made the DNS request
      2. Examine the process's network connections
      3. Check for any files written by the process
      4. Look for persistence mechanisms
      5. Identify if other sensors communicated with this domain

      Document all findings and provide a detailed incident report.
    anthropic_secret: hive://secret/anthropic-key
    lc_api_key_secret: hive://secret/lc-api-key
    profile:
      allowed_tools:
        - Bash
        - Read
        - Grep
        - Glob
        - WebFetch
      denied_tools:
        - Write
        - Edit
      max_turns: 150
      ttl_seconds: 3600
```

### Example 4: Custom Enrichment

Use external tools via MCP for enrichment:

```yaml
respond:
  - action: start ai agent
    prompt: |
      Enrich this alert with external threat intelligence.

      Check the file hash against VirusTotal.
      Look up the IP address geolocation and reputation.
      Cross-reference with MITRE ATT&CK techniques.
    anthropic_secret: hive://secret/anthropic-key
    data:
      file_hash: "{{ .event.HASH }}"
      ip_address: "{{ .event.IP_ADDRESS }}"
    profile:
      mcp_servers:
        virustotal:
          type: http
          url: https://vt-mcp.example.com
          headers:
            x-apikey: hive://secret/vt-api-key
        mitre:
          type: http
          url: https://mitre-mcp.example.com
```

### Example 5: Definition Mode with Hive AI Agent

Instead of putting all session configuration inline in every D&R rule, you can store a reusable AI agent definition in the `ai_agent` hive and reference it by name.

#### Step 1: Create the AI Agent Record

Store the agent definition in the `ai_agent` hive (via the API, CLI, or infrastructure-as-code):

```yaml
ai_agent:
  detection-investigator:
    data:
      # Credentials (use hive://secret/ references)
      anthropic_secret: hive://secret/anthropic-key
      lc_api_key_secret: hive://secret/lc-api-key

      # Prompt with instructions
      prompt: |
        You are a detection investigator. A detection has fired and you need to
        investigate it and document your findings.

        Using the provided event data:
        1. Get details about the sensor where this occurred
        2. Check the process tree and parent/child relationships
        3. Look for related network connections and file operations
        4. Check if similar activity exists on other sensors
        5. Assess severity and provide a recommendation

        Document all findings in a structured report.

      # Session name (supports template strings)
      name: "investigate-{{ .routing.hostname }}"

      # Extract event data fields to include in the prompt
      data:
        hostname: routing.hostname
        sensor_id: routing.sid
        detection_name: detect.cat

      # Session configuration
      model: claude-sonnet-4-20250514
      max_turns: 50
      max_budget_usd: 5.0
      ttl_seconds: 1800
      one_shot: true
      permission_mode: bypassPermissions

      # Tool restrictions
      allowed_tools:
        - Bash
        - Read
        - Grep
        - Glob
        - WebFetch
      denied_tools:
        - Write
        - Edit

      # No mcp_servers entry is needed for LimaCharlie access — the
      # auto-installed `limacharlie` CLI uses lc_api_key_secret above.
      # Add mcp_servers only for external/third-party tools.

    usr_mtd:
      enabled: true
```

#### Step 2: Reference It from D&R Rules

The D&R rule becomes minimal — just a reference to the agent definition:

```yaml
detect:
  target: detection
  event: "*"
  op: is greater than
  path: priority
  value: 3

respond:
  - action: start ai agent
    definition: hive://ai_agent/detection-investigator
    debounce_key: "investigate-{{ .routing.sid }}"
```

This approach keeps D&R rules clean and lets you update the agent's behavior (prompt, model, tools, etc.) in one place without modifying every rule that uses it. The `debounce_key` can be overridden at the action level even in definition mode.

!!! tip "Per-rule prompt and data augmentation"
    Rules using `definition:` can additionally supply `prompt:` and/or `data:` to augment the referenced agent. The rule's prompt is appended to the agent's prompt (blank-line separated), and the rule's extracted data is merged into the agent's data extraction (rule keys override agent keys). See [Per-rule Augmentation](#per-rule-augmentation).

!!! tip "Reuse the same definition from the CLI"
    The same `ai_agent` Hive record can be used as a template from the CLI with `limacharlie ai start-session --definition <name>`. Individual fields (prompt, model, budget, tool list, environment, credentials) can be overridden per run, so one definition doubles as both a D&R-driven agent and an ad-hoc CLI template. See [Command Line Interface](cli.md#limacharlie-ai-start-session) for the full list of override flags.

#### AI Agent Record Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | Yes | Instructions for Claude. |
| `anthropic_secret` | string | Yes | Anthropic API key or `hive://secret/` reference. To route Claude through AWS Bedrock, keep a placeholder `anthropic_secret` and set the Bedrock variables under `environment:` — see [Alternative AI Providers](alternative-providers.md). |
| `bedrock` | object | No | AWS Bedrock provider block (`region`, `access_key_id_secret`, `secret_access_key_secret`, `session_token_secret`, `bearer_token_secret`). Accepted and validated, but not applied to record-based launches yet — see [Alternative AI Providers](alternative-providers.md#amazon-bedrock). |
| `vertex` | object | No | Google Cloud Vertex AI provider block (`project_id`, `region`, `service_account_json_secret`). Accepted and validated, but not applied to record-based launches yet — see [Alternative AI Providers](alternative-providers.md#google-cloud-vertex-ai). |
| `lc_api_key_secret` | string | No | LimaCharlie API key or `hive://secret/` reference. |
| `lc_uid_secret` | string | No | LimaCharlie User ID or `hive://secret/` reference. Required when `lc_api_key_secret` is a user API key. |
| `name` | string | No | Session name. Supports template strings. |
| `data` | map | No | Event data extraction mapping. |
| `allowed_tools` | list | No | Tools Claude can use. |
| `denied_tools` | list | No | Tools Claude cannot use. |
| `permission_mode` | string | No | `acceptEdits`, `plan`, or `bypassPermissions`. |
| `model` | string | No | Claude model identifier. When routing through Bedrock, use the Bedrock model ID format (see [Alternative AI Providers](alternative-providers.md)). |
| `max_turns` | integer | No | Maximum conversation turns. |
| `max_budget_usd` | float | No | Maximum spend limit in USD. |
| `ttl_seconds` | integer | No | Maximum session lifetime in seconds. |
| `one_shot` | boolean | No | Auto-terminate after initial task. |
| `environment` | map | No | Environment variables (values can use `hive://secret/`). |
| `mcp_servers` | map | No | External/third-party MCP server configurations. Not needed for LimaCharlie access (handled by the auto-installed CLI). |

## Best Practices

### Prompt Design

- **Be specific**: Tell Claude exactly what you want it to investigate and how to report findings
- **Provide context**: Include relevant event data in the prompt
- **Define outputs**: Specify the format you want for results (markdown, JSON, etc.)
- **Set boundaries**: Clearly state what actions Claude should NOT take

### Resource Limits

- **Set max_turns**: Prevent runaway sessions that consume excessive resources
- **Set max_budget_usd**: Cap costs for each session
- **Use ttl_seconds**: Automatically terminate long-running sessions

### Security

- **Store secrets in Hive**: Never hardcode API keys in D&R rules
- **Limit tools**: Only allow tools Claude needs for the task
- **Use denied_tools**: Explicitly block dangerous tools for sensitive operations
- **Restrict MCP access**: Only configure MCP servers that are necessary

### Deduplication and Serialization

- **Use idempotent_key**: Prevent duplicate sessions for the same event
- **Use debounce_key**: Serialize sessions so only one runs at a time per key, with queued requests re-fired on completion
- **Include unique identifiers**: Use `detect_id`, `this` atom, or similar unique values
- **Combine with suppression**: Use D&R suppression to limit how often sessions are spawned

## Troubleshooting

### Session Not Starting

- Verify the Anthropic API key is valid and stored correctly in Hive Secrets
- Check that the D&R rule is enabled and matching events
- Review D&R rule syntax for errors

### Session Failing

- Check `max_turns` isn't too low for the task
- Verify MCP server URLs and authentication
- Review session logs for error messages

### Unexpected Behavior

- Review the prompt for ambiguity
- Check that `allowed_tools` includes necessary tools
- Verify `denied_tools` isn't blocking required capabilities

## See Also

- [Compliance Case-Reviewer Agent](compliance/case-reviewer-agent.md) -- A production example of a D&R-driven session: classifies every new case against framework control citations on `case_created` events. Useful as a reference for prompt structure, scope-check patterns, debounce keys, and case-write workflows.
- [Tool Permissions & Profiles](tool-permissions.md) -- Configure `allowed_tools` / `denied_tools` for D&R sessions.
- [Runner Environment](runner-environment.md) -- What's pre-installed in the session container.
- [Alternative AI Providers](alternative-providers.md) -- Route through AWS Bedrock or Google Cloud Vertex AI instead of Anthropic direct.
