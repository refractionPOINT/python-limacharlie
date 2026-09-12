# API Reference

This document provides a complete reference for the AI Sessions REST API and WebSocket protocol.

## Base URL

| Environment | URL |
|-------------|-----|
| Production | `https://ai.limacharlie.io` |
| Staging | `https://ai-staging.limacharlie.io` |

## Authentication

All API requests require a valid LimaCharlie JWT token in the Authorization header:

```text
Authorization: Bearer <LC-JWT>
```

For WebSocket connections, you can also pass the token as a query parameter:

```text
wss://ai.limacharlie.io/v1/sessions/{sessionId}/ws?token=<LC-JWT>
```

## Rate Limits

| Operation | Limit |
|-----------|-------|
| Registration | 10 requests/minute per user |
| Session creation | 10 requests/minute per user |
| WebSocket messages | 100 messages/second per connection |

---

## REST API Endpoints

### Registration

#### Register User

```text
POST /v1/register
```

Register the authenticated user for the AI Sessions platform.

##### Response: 200 OK

```json
{
  "registered": true,
  "registered_at": "2025-01-15T10:30:00Z"
}
```

**Error Responses:**

- `401`: Invalid or missing JWT token
- `403`: Email domain not in allowed list
- `409`: User already registered

#### Deregister User

```text
DELETE /v1/register
```

Deregister the user and delete all associated data. This terminates all active sessions and deletes stored credentials.

##### Response: 200 OK

```json
{
  "deregistered": true
}
```

---

### Sessions

#### List Sessions

```text
GET /v1/sessions
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status: `starting`, `running`, `ended` |
| `limit` | integer | Max results (default 50, max 200) |
| `cursor` | string | Pagination cursor |

##### Response: 200 OK

```json
{
  "sessions": [
    {
      "id": "abc123",
      "status": "running",
      "region": "us-central1",
      "created_at": "2025-01-15T10:30:00Z",
      "started_at": "2025-01-15T10:30:05Z",
      "lc_auth_type": "jwt",
      "allowed_tools": ["Bash", "Read"],
      "denied_tools": ["Write"]
    }
  ],
  "next_cursor": "xyz789"
}
```

#### Create Session

```text
POST /v1/sessions
```

**Request Body:**

```json
{
  "lc_credentials": {
    "type": "org_api_key",
    "org_api_key": "xxxxxxxx"
  },
  "provider": "openai",
  "allowed_tools": ["Bash", "Read", "Write"],
  "denied_tools": ["WebFetch"]
}
```

`provider` is optional: one of `anthropic`, `openai`, `google`, `openrouter`. It overrides the profile's provider for this session; when both are omitted the session runs on Claude. See [AI Providers](providers.md).

##### Response: 201 Created

```json
{
  "session": {
    "id": "abc123",
    "status": "starting",
    "region": "us-central1",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Error Responses:**

- `400`: Invalid request body
- `403`: Not registered, or no stored credentials for the session's provider
- `409`: Maximum concurrent sessions (10) reached

#### Get Session

```text
GET /v1/sessions/{sessionId}
```

##### Response: 200 OK

```json
{
  "session": {
    "id": "abc123",
    "status": "running",
    "region": "us-central1",
    "created_at": "2025-01-15T10:30:00Z",
    "started_at": "2025-01-15T10:30:05Z",
    "terminated_at": null,
    "end_reason": null,
    "exit_code": null,
    "error_message": null,
    "allowed_tools": ["Bash", "Read"],
    "denied_tools": ["Write"]
  }
}
```

#### Rename Session

```text
PATCH /v1/sessions/{sessionId}
```

Update a session's user-facing name. The name is metadata over the session
record, so renaming works in every state, `ended` included.

##### Request Body

```json
{
  "name": "Ransomware triage - host WIN-DC01"
}
```

Leading and trailing whitespace is trimmed. The trimmed name must be non-empty
and at most 200 characters.

##### Response: 200 OK

Returns the updated session in the same shape as [Get Session](#get-session).

```json
{
  "session": {
    "id": "abc123",
    "name": "Ransomware triage - host WIN-DC01",
    "status": "running",
    "region": "us-central1",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Error Responses:**

- `400`: Missing or malformed body, empty name (`name_required`), or a name over 200 characters (`name_too_long`)
- `403`: The session belongs to another user
- `404`: No such session

#### Terminate Session

```text
DELETE /v1/sessions/{sessionId}
```

##### Response: 200 OK

```json
{
  "terminated": true
}
```

#### Delete Session Record

```text
DELETE /v1/sessions/{sessionId}/record
```

Delete a terminated session from history. Only sessions in the `ended` state can be deleted.

##### Response: 200 OK

```json
{
  "deleted": true
}
```

#### Fork Preflight Check

```text
GET /v1/sessions/{sessionId}/fork-preflight
```

Inspect a source session before forking. Reports whether the source can be forked, a suggested name, and any MCP servers the source uses that are missing from the forker's profile (these must be acknowledged when forking).

Forking your own session needs no special permission. Forking a session owned by the organization (an API/D&R session) requires the `ai_agent.set` permission on the org.

##### Query Parameters

| Parameter | Description |
|-----------|-------------|
| `profile_id` | The forker's profile ID. Defaults to the caller's default profile if omitted. |

##### Response: 200 OK

```json
{
  "source_session_id": "abc123",
  "source_session_type": "user",
  "source_status": "ended",
  "source_name": "Investigation 2025-01-15",
  "source_lifetime_days": 3,
  "default_fork_name": "Fork of Investigation 2025-01-15",
  "source_mcp_servers": ["virustotal"],
  "missing_mcps": ["virustotal"],
  "is_forkable": true,
  "is_forkable_reason": "",
  "history_available": true
}
```

`source_session_type` is `user` or `api`. When `missing_mcps` is non-empty, pass those names in `acknowledge_missing_tools` on the fork request.

#### Fork Session

```text
POST /v1/sessions/{sessionId}/fork
```

Create a new session forked from the given source. The fork inherits the source's conversation context but starts with the forker's profile. The source must be in a forkable state (dormant or ended, within its retention window).

All fields are optional:

```json
{
  "name": "Continued investigation",
  "profile_id": "profile-xyz",
  "initial_prompt": "Pick up where the previous session left off and check the new IOCs.",
  "acknowledge_missing_tools": ["virustotal"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Name for the forked session (defaults to a derived name). |
| `profile_id` | string | Profile to use for the fork (defaults to the caller's default profile). |
| `initial_prompt` | string | Initial prompt for the forked session. |
| `acknowledge_missing_tools` | array | MCP servers present in the source but missing from the fork profile, acknowledged by the caller. |

##### Response: 201 Created

Returns the new session object, the same shape as [Create Session](#create-session). The new session's `forked_from_session_id` field references the source.

##### Errors

| Status | Meaning |
|--------|---------|
| `403` | Forking an org-owned session without the `ai_agent.set` permission. |
| `409` | Source is not in a forkable state, or a create/fork/resume is already in progress. |
| `410` | Source workspace archive is no longer available. |
| `412` | Source uses MCP servers missing from the fork profile; acknowledge them via `acknowledge_missing_tools`. |
| `429` | Maximum concurrent sessions reached. |

---

### Profiles

#### List Profiles

```text
GET /v1/profiles
```

##### Response: 200 OK

```json
{
  "profiles": [
    {
      "id": "profile123",
      "name": "Investigation",
      "description": "Profile for security investigations",
      "is_default": true,
      "allowed_tools": ["Bash", "Read"],
      "denied_tools": ["Write"],
      "permission_mode": "acceptEdits",
      "provider": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "max_turns": 100,
      "max_budget_usd": 10.0,
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

#### Create Profile

```text
POST /v1/profiles
```

**Request Body:**

```json
{
  "name": "Investigation",
  "description": "Profile for security investigations",
  "allowed_tools": ["Bash", "Read", "Grep"],
  "denied_tools": ["Write", "Edit"],
  "permission_mode": "acceptEdits",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "max_turns": 100,
  "max_budget_usd": 10.0,
  "mcp_servers": {
    "virustotal": {
      "type": "http",
      "url": "https://vt-mcp.example.com",
      "headers": {
        "x-apikey": "hive://secret/vt-api-key"
      }
    }
  },
  "is_default": false
}
```

##### Response: 201 Created

```json
{
  "profile": {
    "id": "profile123",
    "name": "Investigation",
    ...
  }
}
```

`provider` is optional: one of `anthropic`, `openai`, `google`, `openrouter` (default `anthropic`). `model` must be valid for the chosen provider; when omitted, the provider's default model is used. See [AI Providers](providers.md).

**Error Responses:**

- `400`: Invalid request body
- `409`: Maximum profiles (10) reached

#### Get Profile

```text
GET /v1/profiles/{profileId}
```

#### Update Profile

```text
PUT /v1/profiles/{profileId}
```

#### Delete Profile

```text
DELETE /v1/profiles/{profileId}
```

> Note: The default profile cannot be deleted.

#### Set Default Profile

```text
POST /v1/profiles/{profileId}/default
```

#### Capture Session as Profile

```text
POST /v1/sessions/{sessionId}/capture-profile
```

**Request Body:**

```json
{
  "name": "My Session Config",
  "description": "Captured from session abc123"
}
```

---

### Claude Authentication

#### Start OAuth Flow

```text
POST /v1/auth/claude/start
```

##### Response: 200 OK

```json
{
  "oauth_session_id": "oauth123",
  "expires_in": 300,
  "message": "Poll /auth/claude/url for the OAuth URL"
}
```

#### Get OAuth URL

```text
GET /v1/auth/claude/url?session_id={oauth_session_id}
```

##### Response: 200 OK (URL Ready)

```json
{
  "status": "url_ready",
  "url": "https://console.anthropic.com/oauth/authorize?...",
  "message": "Visit the URL to authorize"
}
```

##### Response: 200 OK (Pending)

```json
{
  "status": "pending",
  "message": "Waiting for OAuth URL to be generated"
}
```

#### Submit OAuth Code

```text
POST /v1/auth/claude/code
```

**Request Body:**

```json
{
  "session_id": "oauth123",
  "code": "authorization_code_from_anthropic"
}
```

##### Response: 200 OK

```json
{
  "success": true,
  "status": "completed",
  "message": "Claude credentials stored successfully"
}
```

#### Store API Key

```text
POST /v1/auth/claude/apikey
```

**Request Body:**

```json
{
  "api_key": "sk-ant-api03-xxxxx"
}
```

##### Response: 200 OK

```json
{
  "success": true,
  "message": "API key stored successfully"
}
```

#### Get Credential Status

```text
GET /v1/auth/claude/status
```

##### Response: 200 OK

```json
{
  "has_credentials": true,
  "credential_type": "api_key",
  "created_at": "2025-01-15T10:30:00Z"
}
```

#### Delete Credentials

```text
DELETE /v1/auth/claude
```

---

### Provider Credentials

Credentials for the non-Claude providers are managed under `/v1/credentials`. Request body shapes and examples are on the [AI Providers](providers.md) page; the full schemas are in the OpenAPI specification served by the service at `GET /openapi`.

#### Get Credential Status (All Providers)

```text
GET /v1/credentials
```

##### Response: 200 OK

```json
{
  "providers": {
    "anthropic":  {"has_credentials": true, "type": "oauth_token", "created_at": "2026-08-01T12:00:00Z"},
    "openai":     {"has_credentials": true, "type": "api_key", "created_at": "2026-08-10T09:30:00Z"},
    "google":     {"has_credentials": false},
    "openrouter": {"has_credentials": false}
  }
}
```

#### Store and Delete Provider Credentials

```text
POST   /v1/credentials/openai         # OpenAI API key
POST   /v1/credentials/openai/azure   # Azure OpenAI configuration
DELETE /v1/credentials/openai

POST   /v1/credentials/google         # Google AI Studio API key
POST   /v1/credentials/google/vertex  # Vertex AI service account (Gemini)
DELETE /v1/credentials/google

POST   /v1/credentials/openrouter     # OpenRouter API key
DELETE /v1/credentials/openrouter
```

Storing a credential replaces any previous credential for that provider. `DELETE` removes it immediately.

---

### File Transfer

#### Request Upload URL

```text
POST /v1/io/sessions/{sessionId}/upload
```

**Request Body:**

```json
{
  "filename": "data.csv",
  "content_type": "text/csv",
  "size": 1024
}
```

##### Response: 200 OK

```json
{
  "upload_url": "https://storage.googleapis.com/...",
  "upload_id": "upload123",
  "target_path": "/workspace/uploads/data.csv",
  "expires_at": "2025-01-15T11:30:00Z"
}
```

**Error Responses:**

- `413`: File size exceeds limit (100 MB)

#### Notify Upload Complete

```text
POST /v1/io/sessions/{sessionId}/upload/complete
```

**Request Body:**

```json
{
  "upload_id": "upload123"
}
```

##### Response: 200 OK

```json
{
  "success": true,
  "path": "/workspace/uploads/data.csv"
}
```

#### Request Download URL

```text
POST /v1/io/sessions/{sessionId}/download
```

**Request Body:**

```json
{
  "path": "/workspace/output.txt"
}
```

##### Response: 200 OK

```json
{
  "download_url": "https://storage.googleapis.com/...",
  "expires_at": "2025-01-15T11:30:00Z"
}
```

---

## WebSocket Protocol

### Connection

**Endpoint:**

```text
wss://ai.limacharlie.io/v1/sessions/{sessionId}/ws
```

**Authentication:**

- Header: `Authorization: Bearer <JWT>`
- Query parameter: `?token=<JWT>`

### Connection Errors

| Code | Description |
|------|-------------|
| 4001 | Invalid or missing authentication |
| 4003 | Session belongs to different user |
| 4004 | Session not found |
| 4009 | Session not running |
| 4100 | Session ended |
| 4101 | Connection reset |
| 4500 | Internal error |

### Message Format

All messages are JSON objects:

```json
{
  "type": "message_type",
  "timestamp": "2025-01-15T10:30:00Z",
  "session_id": "abc123",
  "payload": { ... }
}
```

---

### Client to Server Messages

#### prompt

Send a user prompt to Claude.

```json
{
  "type": "prompt",
  "payload": {
    "text": "List all files in the current directory"
  }
}
```

#### interrupt

Interrupt the current Claude operation.

```json
{
  "type": "interrupt"
}
```

#### heartbeat

Keep the connection alive (send every 30 seconds).

```json
{
  "type": "heartbeat"
}
```

#### upload_request

Request a signed URL for file upload.

```json
{
  "type": "upload_request",
  "payload": {
    "request_id": "req_123",
    "filename": "data.csv",
    "content_type": "text/csv",
    "size": 1024
  }
}
```

#### upload_complete

Notify that file upload has completed.

```json
{
  "type": "upload_complete",
  "payload": {
    "request_id": "req_123",
    "filename": "data.csv",
    "path": "/workspace/uploads/data.csv"
  }
}
```

#### download_request

Request a signed URL for file download.

```json
{
  "type": "download_request",
  "payload": {
    "request_id": "req_456",
    "path": "/workspace/output.txt"
  }
}
```

---

### Server to Client Messages

#### assistant

Claude's response content.

```json
{
  "type": "assistant",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "content": [
      {
        "type": "text",
        "text": "Here are the files in the current directory:\n\n- file1.txt\n- file2.py"
      }
    ],
    "model": "claude-sonnet-4-20250514"
  }
}
```

#### tool_use

Claude is invoking a tool.

```json
{
  "type": "tool_use",
  "timestamp": "2025-01-15T10:30:01Z",
  "payload": {
    "id": "tool_abc123",
    "name": "Bash",
    "input": {
      "command": "ls -la"
    }
  }
}
```

#### tool_result

Result of a tool execution.

```json
{
  "type": "tool_result",
  "timestamp": "2025-01-15T10:30:02Z",
  "payload": {
    "tool_use_id": "tool_abc123",
    "content": "total 16\ndrwxr-xr-x 2 user user 4096 Jan 15 10:00 .\n..."
  }
}
```

#### user

Echo of user input (for display purposes).

```json
{
  "type": "user",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "text": "List all files in the current directory"
  }
}
```

#### system

System messages from Claude.

```json
{
  "type": "system",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "message": "Working directory: /workspace"
  }
}
```

#### result

Final result of a Claude operation.

```json
{
  "type": "result",
  "timestamp": "2025-01-15T10:35:00Z",
  "payload": {
    "success": true,
    "summary": "Listed directory contents successfully"
  }
}
```

#### session_status

Session status update.

```json
{
  "type": "session_status",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "status": "running"
  }
}
```

#### session_end

Session has ended.

```json
{
  "type": "session_end",
  "timestamp": "2025-01-15T10:35:00Z",
  "payload": {
    "reason": "completed",
    "exit_code": 0
  }
}
```

**End Reasons:**

- `completed`: Session completed normally
- `failed`: Session encountered an execution error
- `job_completed`: Session runner process exited
- `user_requested`: User terminated the session
- `org_api_requested`: Session was terminated via the org API
- `max_duration_exceeded`: Session exceeded its maximum duration
- `startup_timeout`: Session failed to start within the allowed time
- `heartbeat_stale`: Lost connection to the session runner

#### session_error

An error occurred in the session.

```json
{
  "type": "session_error",
  "timestamp": "2025-01-15T10:35:00Z",
  "payload": {
    "error": "Claude process died unexpectedly",
    "details": "Exit code: 1"
  }
}
```

#### error

General error message.

```json
{
  "type": "error",
  "timestamp": "2025-01-15T10:35:00Z",
  "payload": {
    "message": "Rate limit exceeded",
    "code": "rate_limited"
  }
}
```

**Error Codes:**

- `session_not_found`: Session no longer exists
- `session_not_running`: Session is not in running state
- `session_crashed`: Session process crashed
- `invalid_message`: Malformed message received
- `rate_limited`: Too many messages sent

#### upload_url

Response to upload_request.

```json
{
  "type": "upload_url",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "request_id": "req_123",
    "upload_id": "upload_789",
    "url": "https://storage.googleapis.com/...",
    "target_path": "/workspace/uploads/data.csv",
    "expires_at": "2025-01-15T11:30:00Z"
  }
}
```

#### download_url

Response to download_request.

```json
{
  "type": "download_url",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "request_id": "req_456",
    "url": "https://storage.googleapis.com/...",
    "expires_at": "2025-01-15T11:30:00Z"
  }
}
```

---

## Connection Management

### Heartbeat

- **Client**: Send `heartbeat` message every 30 seconds
- **Server**: Sends WebSocket ping frames every 30 seconds
- **Timeout**: Connection closed after 60 seconds of inactivity

### Reconnection

If the connection is lost:

1. Reconnect using the same session ID
2. Server sends any buffered messages (up to 60 seconds old)
3. If session has ended, server sends `session_end` message

### Message Size

Maximum message size is 1 MB. Use file transfer for larger payloads.

---

## Example: Complete Session Flow

```javascript
const jwt = 'your-limacharlie-jwt';
const baseUrl = 'https://ai.limacharlie.io';

// 1. Create session
const createResp = await fetch(`${baseUrl}/v1/sessions`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwt}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    allowed_tools: ['Bash', 'Read', 'Write']
  })
});
const { session } = await createResp.json();

// 2. Wait for session to be running
let status = 'starting';
while (status === 'starting') {
  await new Promise(r => setTimeout(r, 1000));
  const resp = await fetch(`${baseUrl}/v1/sessions/${session.id}`, {
    headers: { 'Authorization': `Bearer ${jwt}` }
  });
  const data = await resp.json();
  status = data.session.status;
}

// 3. Connect via WebSocket
const ws = new WebSocket(
  `wss://ai.limacharlie.io/v1/sessions/${session.id}/ws?token=${jwt}`
);

// 4. Set up heartbeat
const heartbeat = setInterval(() => {
  ws.send(JSON.stringify({ type: 'heartbeat' }));
}, 30000);

// 5. Handle messages
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  switch (msg.type) {
    case 'assistant':
      console.log('Claude:', msg.payload.content);
      break;
    case 'tool_use':
      console.log('Using tool:', msg.payload.name);
      break;
    case 'tool_result':
      console.log('Tool result:', msg.payload.content);
      break;
    case 'session_end':
      console.log('Session ended:', msg.payload.reason);
      clearInterval(heartbeat);
      break;
    case 'error':
      console.error('Error:', msg.payload.message);
      break;
  }
};

// 6. Send a prompt
ws.send(JSON.stringify({
  type: 'prompt',
  payload: { text: 'Hello! List the files in the current directory.' }
}));

// 7. Later: interrupt if needed
// ws.send(JSON.stringify({ type: 'interrupt' }));

// 8. Cleanup
ws.onclose = () => {
  clearInterval(heartbeat);
};
```
