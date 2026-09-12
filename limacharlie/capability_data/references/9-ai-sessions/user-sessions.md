# User AI Sessions

User AI Sessions provide interactive access to an AI agent through the LimaCharlie web interface or API. Unlike D&R-driven sessions that run automatically, user sessions are manually initiated and allow real-time, bidirectional communication with the agent. Sessions run on Claude by default and can also run on OpenAI, Google Gemini, or OpenRouter models using your own credentials; see [AI Providers](providers.md).

## Overview

User sessions give you:

- **Interactive Claude Code**: Full Claude Code capabilities in a cloud-hosted environment
- **Real-time communication**: WebSocket-based streaming of responses and tool usage
- **Session management**: Create, list, and manage multiple sessions
- **File transfer**: Upload and download files to/from session workspaces
- **Profiles**: Save and reuse session configurations

## Getting Started

### Step 1: Registration

Before using AI Sessions, you must register. Registration is available to LimaCharlie users with approved email domains.

**Via Web UI:**
Navigate to the AI Sessions section in the LimaCharlie web console and click "Register".

**Via API:**

```bash
curl -X POST https://ai.limacharlie.io/v1/register \
  -H "Authorization: Bearer $LC_JWT"
```

### Step 2: Store AI Provider Credentials

AI Sessions uses a Bring Your Own Key (BYOK) model. Sessions run on Claude by default: you provide your Anthropic credentials—either an API key or via Claude Max OAuth. You can also connect OpenAI, Azure OpenAI, Google Gemini, or OpenRouter credentials and run sessions on those providers instead; see [AI Providers](providers.md). Credentials for every provider can be managed in the web application under **User Settings → AI Terminal**.

#### Option A: API Key

Store your Anthropic API key directly:

```bash
curl -X POST https://ai.limacharlie.io/v1/auth/claude/apikey \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-ant-api03-xxxxx"}'
```

> Note: API keys must start with `sk-ant-`.

#### Option B: Claude Max OAuth

If you have a Claude Max subscription, you can authenticate via OAuth:

1. Start the OAuth flow:

```bash
curl -X POST https://ai.limacharlie.io/v1/auth/claude/start \
  -H "Authorization: Bearer $LC_JWT"
```

1. Poll for the authorization URL:

```bash
curl https://ai.limacharlie.io/v1/auth/claude/url?session_id=<oauth_session_id> \
  -H "Authorization: Bearer $LC_JWT"
```

1. Visit the URL in your browser and authorize
2. Submit the authorization code:

```bash
curl -X POST https://ai.limacharlie.io/v1/auth/claude/code \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<oauth_session_id>", "code": "<authorization_code>"}'
```

### Step 3: Create a Session

Create a new session to start working with Claude:

```bash
curl -X POST https://ai.limacharlie.io/v1/sessions \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "allowed_tools": ["Bash", "Read", "Write", "Grep", "Glob"],
    "denied_tools": ["WebFetch"]
  }'
```

### Step 4: Connect via WebSocket

For real-time interaction, connect to the session via WebSocket:

```javascript
const ws = new WebSocket(
  'wss://ai.limacharlie.io/v1/sessions/{sessionId}/ws?token={jwt}'
);

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg.payload);
};

// Send a prompt
ws.send(JSON.stringify({
  type: 'prompt',
  payload: { text: 'List all files in the current directory' }
}));
```

!!! tip "Chat from the terminal"
    The LimaCharlie CLI's `limacharlie ai chat` command starts a new user session and drops you straight into the interactive chat — no manual `POST /v1/sessions` + WebSocket bring-up. Pre-requisite is running `limacharlie ai auth claude login` (or `set-key`) once to register your Anthropic credential. See [Command Line Interface](cli.md#limacharlie-ai-chat) for the full flag set, and `ai session attach --id <SESSION_ID> --interactive` for re-attaching to a session you started earlier.

## Session Profiles

Profiles let you save and reuse session configurations. You can have up to 10 profiles, with one designated as the default.

### Creating a Profile

```bash
curl -X POST https://ai.limacharlie.io/v1/profiles \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Investigation",
    "description": "Profile for security investigations",
    "allowed_tools": ["Bash", "Read", "Grep", "Glob", "WebFetch"],
    "denied_tools": ["Write", "Edit"],
    "permission_mode": "acceptEdits",
    "max_turns": 100,
    "max_budget_usd": 10.0
  }'
```

### Profile Options

| Option | Type | Description |
|--------|------|-------------|
| `name` | string | Profile name (max 100 characters) |
| `description` | string | Profile description (max 500 characters) |
| `allowed_tools` | list | Tools Claude can use. See [Tool Permissions & Profiles](tool-permissions.md) for the full pattern grammar. |
| `denied_tools` | list | Tools Claude cannot use. Always wins over `allowed_tools`. See [Tool Permissions & Profiles](tool-permissions.md). |
| `permission_mode` | string | `acceptEdits`, `plan`, or `bypassPermissions`. See [Tool Permissions & Profiles](tool-permissions.md#permission_mode). |
| `provider` | string | AI provider for the session: `anthropic` (default), `openai`, `google`, or `openrouter`. See [AI Providers](providers.md). |
| `model` | string | Model to use, in the chosen provider's naming. Defaults to the provider's default model. |
| `max_turns` | integer | Maximum conversation turns |
| `max_budget_usd` | float | Maximum spend limit in USD |
| `one_shot` | boolean | When `true`, session terminates after completing its initial work. Default: `false` for user sessions. |
| `ttl_seconds` | integer | Maximum session lifetime in seconds |
| `environment` | map | Environment variables passed to the session |
| `mcp_servers` | map | External/third-party MCP server configurations. LimaCharlie access is handled by the auto-installed `limacharlie` CLI and does not need an entry here. |

### Setting a Default Profile

```bash
curl -X POST https://ai.limacharlie.io/v1/profiles/{profileId}/default \
  -H "Authorization: Bearer $LC_JWT"
```

### Capturing Settings from a Session

You can create a new profile from an existing session's settings:

```bash
curl -X POST https://ai.limacharlie.io/v1/sessions/{sessionId}/capture-profile \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Session Config"}'
```

## Session Lifecycle

### What you see: Running / Waiting / Ended

Across the UI — the sidebar, session lists, the live grid, the chat header — a
session shows one of three states, with an optional **needs-attention** flag:

| State | Meaning |
|-------|---------|
| **Running** | The agent is actively working — thinking, running tools, or recovering. |
| **Waiting** | The session is alive but idle — waiting for your next prompt, asleep but resumable, or blocked on an unanswered tool approval or question. |
| **Ended** | The session is finished. The `end_reason` says why — see [End Reasons](#end-reasons) below. |

**Needs attention** — when a Running or Waiting session is blocked on a tool approval
or a question you haven't answered, the badge gains a trailing alert marker. If you
send a prompt while a session is blocked, the chat shows a "message queued" notice
with a button that scrolls the pending request into view.

### Hibernation

Idle sessions are automatically **hibernated**: the workspace is archived and the
session becomes **dormant**, incurring storage cost but **zero compute** until you
send a new message, at which point it resumes transparently. To you it simply stays
"Waiting" the whole time and picks up where it left off — the conversation and
working files are restored on resume.

### Forking

A dormant or ended session can be **forked** into a new session within its retention
window. The fork inherits the source's **conversation context** but starts with the
**forking user's profile** (its tools and capabilities). A fork preflight reports
whether the source is forkable and which of its MCP servers are missing from your
profiles, so you can acknowledge them before forking.

### Resource limits

Several [Profile Options](#profile-options) act as automatic termination triggers:
`max_turns` ends the session after a number of turns, `max_budget_usd` when
cumulative AI cost exceeds the cap, `one_shot` after the initial task, and
`ttl_seconds` sets the session lifetime (capped at 24 hours). A platform maximum
session duration, set by your organization's tier, also applies. When one of these is
reached the session moves to `ended` with the matching `end_reason` below.

### End Reasons

When a session enters the `ended` state, the `end_reason` field indicates why:

| Reason | Description |
|--------|-------------|
| `completed` | Session completed its task normally |
| `failed` | Session encountered an execution error |
| `job_completed` | Session runner process exited |
| `user_requested` | User terminated the session |
| `org_api_requested` | Session was terminated via the org API |
| `max_duration_exceeded` | Session exceeded its maximum duration |
| `startup_timeout` | Session failed to start within the allowed time |
| `heartbeat_stale` | Lost connection to the session runner |

### Terminating a Session

```bash
curl -X DELETE https://ai.limacharlie.io/v1/sessions/{sessionId} \
  -H "Authorization: Bearer $LC_JWT"
```

### Deleting Session Records

After a session is terminated, you can delete its record:

```bash
curl -X DELETE https://ai.limacharlie.io/v1/sessions/{sessionId}/record \
  -H "Authorization: Bearer $LC_JWT"
```

## File Transfer

### Uploading Files

1. Request an upload URL:

```bash
curl -X POST https://ai.limacharlie.io/v1/io/sessions/{sessionId}/upload \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "data.csv",
    "content_type": "text/csv",
    "size": 1024
  }'
```

1. Upload the file to the signed URL:

```bash
curl -X PUT "{upload_url}" \
  -H "Content-Type: text/csv" \
  --data-binary @data.csv
```

1. Notify that upload is complete:

```bash
curl -X POST https://ai.limacharlie.io/v1/io/sessions/{sessionId}/upload/complete \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{"upload_id": "{upload_id}"}'
```

The file will be available in the session at the `target_path` returned in step 1.

### Downloading Files

1. Request a download URL:

```bash
curl -X POST https://ai.limacharlie.io/v1/io/sessions/{sessionId}/download \
  -H "Authorization: Bearer $LC_JWT" \
  -H "Content-Type: application/json" \
  -d '{"path": "/workspace/output.txt"}'
```

1. Download the file from the signed URL:

```bash
curl -o output.txt "{download_url}"
```

### File Size Limits

- Maximum file size: 100 MB
- Maximum message size (WebSocket): 1 MB

## Use Cases

### Interactive Threat Investigation

Use Claude to investigate a security incident step by step:

```text
You: I need to investigate suspicious activity on sensor abc123.
     The user reported strange popup windows.

Claude: I'll investigate this sensor. Let me start by gathering some
        context about the sensor and recent events.

        [Uses LimaCharlie tools to query sensor info and events]

        I found several suspicious indicators:
        1. A new process "update.exe" started from a temp directory
        2. Multiple outbound connections to an unknown IP
        3. Registry modifications for persistence

        Would you like me to investigate any of these in more detail?
```

### Ad-hoc Analysis

Perform quick analysis tasks:

```text
You: Analyze this list of IP addresses and tell me which ones
     appear in threat intelligence feeds.

Claude: I'll analyze each IP address against available threat
        intelligence sources.

        [Checks each IP against VirusTotal, AbuseIPDB, etc.]

        Results:
        - 192.168.1.1: Clean (internal)
        - 45.33.32.156: Malicious - Known C2 server
        - 8.8.8.8: Clean (Google DNS)
```

### Learning and Exploration

Explore your LimaCharlie environment:

```text
You: Show me how to create a D&R rule that detects PowerShell
     downloading files from the internet.

Claude: Here's how to create a D&R rule for detecting PowerShell
        web downloads:

        [Provides detailed explanation with examples]
```

## Best Practices

### Session Management

- **Terminate when done**: Idle sessions are automatically hibernated to save resources, but explicitly terminating sessions you no longer need is still recommended
- **Use profiles**: Save common configurations for quick session creation
- **Set resource limits**: Use `max_turns` and `max_budget_usd` to control costs
- **Expect resume latency**: After a period of inactivity, your session may be hibernated. The first message after hibernation may take longer as the session resumes

### Security

- **Limit tool access**: Only enable tools needed for your task
- **Review tool usage**: Monitor what actions Claude is taking
- **Be careful with Write/Edit**: These tools can modify files

### Performance

- **Keep prompts focused**: Specific, clear prompts get better results
- **Upload files for large data**: Use file transfer instead of pasting into prompts
- **Use heartbeats**: Keep WebSocket connections alive with regular heartbeats

## Rate Limits

| Operation | Limit |
|-----------|-------|
| Registration requests | 10/minute per user |
| Session creation | 10/minute per user |
| Maximum concurrent sessions | 10 per user |
| WebSocket messages | 100/second per connection |
| Prompts | 60/minute per session |
| File uploads | 10/minute per session |

## Troubleshooting

### Cannot Register

- Verify your email domain is in the allowed list
- Check that your JWT token is valid
- Contact support if the issue persists

### Cannot Create Session

- Ensure you have credentials stored for the provider the session uses (Claude by default)
- Check you haven't exceeded the maximum session limit (10)
- Verify your profile configuration is valid

### WebSocket Connection Issues

- Use the query parameter for JWT if header doesn't work
- Send heartbeats every 30 seconds to keep connection alive
- Check session status—connection only works for `running` sessions

### Session Crashes

- Check `max_turns` isn't being exceeded
- Review the error message in session details
- Ensure MCP server configurations are correct
