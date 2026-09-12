# Feedback

The Feedback extension enables interactive feedback requests across external channels. It sends approval/denial prompts, acknowledgement requests, or free-form questions to Slack, Telegram, Microsoft Teams, email, or a built-in web UI. It collects responses and dispatches them to LimaCharlie subsystems (case notes via ext-cases, playbook triggers via ext-playbook, or AI agent sessions via the AI Sessions API).

Designed for AI-driven and human-initiated workflows where operator approval or input is required before taking an automated action. For example, a D&R rule or playbook can ask a human "Should we isolate host compromised-01?" and wait for a response before proceeding.

## Enabling the Extension

Navigate to the [Feedback extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-feedback) in the marketplace. Select the organization you wish to enable it for, and select **Subscribe**.

On subscription, the extension automatically:

1. Creates a webhook adapter for the organization
2. Installs a D&R rule that routes feedback responses to the extension for processing

No additional configuration is required. You can immediately start configuring channels and sending feedback requests.

## Concepts

### Channels

A **channel** defines how feedback requests are delivered to respondents. Each channel has a name and a type. Channels are configured through the extension config (see [Channel Configuration](#channel-configuration)).

| Channel Type | Description | In-Chat Buttons | Requirements |
|-------------|-------------|:---------------:|--------------|
| `web` | Built-in web UI. Returns a shareable URL that displays the question with response buttons or text input. | N/A | None |
| `slack` | Sends an interactive Block Kit message to a Slack channel with action buttons. | Yes | A [Slack Tailored Output](../../outputs/destinations/slack.md) with `slack_api_token` and `slack_channel`. See [Slack Setup](#slack-setup). |
| `telegram` | Sends a message with inline keyboard buttons to a Telegram chat via Bot API. | Yes | A [Telegram Tailored Output](../../outputs/destinations/telegram.md) with `bot_token` and `chat_id`. See [Telegram Setup](#telegram-setup). |
| `ms_teams` | Sends an Adaptive Card to a Microsoft Teams channel via webhook. A button links to the web UI for response. | No (link to web UI) | A [Microsoft Teams Tailored Output](../../outputs/destinations/ms-teams.md) with `webhook_url`. See [Microsoft Teams Setup](#microsoft-teams-setup). |
| `email` | Sends an HTML email with the question and a link to the web approval page. | No (link to web UI) | An [SMTP Tailored Output](../../outputs/destinations/smtp.md) with `dest_host`, `dest_email`, `from_email`, and SMTP credentials. See [Email Setup](#email-setup). |

### Feedback Types

Each feedback type has a dedicated action:

| Feedback Type | Action | UI | Response Values |
|--------------|--------|-----|-----------------|
| `simple_approval` | `request_simple_approval` | **Approve** and **Deny** buttons | `approved` or `denied` |
| `acknowledgement` | `request_acknowledgement` | **Acknowledge** button | `acknowledged` |
| `question` | `request_question` | Free-form text input | `answered` + free-form `text` |

### Feedback Destinations

When a respondent answers, the extension dispatches the response to the configured destination:

| Destination | Behavior |
|-------------|----------|
| `case` | Adds a note to the specified case via ext-cases. Requires a `case_id`. |
| `playbook` | Triggers the specified playbook via ext-playbook with the response data. Requires a `playbook_name`. |
| `ai_agent` | Starts an AI agent session with the response data appended to the agent's prompt. Requires an `ai_agent_name` referencing an `ai_agent` hive record. |

### Response Content

Each feedback request can include optional JSON data per choice. When the respondent selects a choice, the corresponding content is included in the dispatched response. This allows automation to carry structured payloads through the human decision point.

- For `request_simple_approval`, use `approved_content` and `denied_content`.
- For `request_acknowledgement`, use `acknowledged_content`.
- For `request_question`, no content fields are available -- the respondent's free-form text IS the response.

### Timeouts

All feedback actions accept an optional timeout. When `timeout_seconds` is set (minimum 60), the system automatically responds with a default choice if no human responds before the deadline. The timeout response flows through the same webhook/D&R/dispatch path as a normal response, with `responder` set to `"timeout"`.

| Parameter | Applies To | Description |
|-----------|-----------|-------------|
| `timeout_seconds` | All actions | Number of seconds to wait before auto-responding (minimum 60) |
| `timeout_choice` | `request_simple_approval` | Which choice to auto-select: `approved` or `denied`. Required when `timeout_seconds` is set. |
| `timeout_content` | All actions | JSON data to include in the timeout response (overrides the per-choice content). Required for `request_question` when `timeout_seconds` is set. |

For `request_acknowledgement`, the timeout choice is always `acknowledged`. For `request_question`, the timeout choice is always `answered` and `timeout_content` provides the automatic answer.

When a timeout is configured, the channel message includes a note like "(Auto-denied in 5 minutes if no response)" so the respondent knows the deadline.

## Channel Configuration

Channels are managed through the extension config, not via extension actions. You can configure channels through the LimaCharlie web UI (extension settings page), via the CLI, or through infrastructure-as-code with git-sync.

=== "CLI"
    ```bash
    # Add channels individually
    limacharlie feedback channel add --name ops --type web
    limacharlie feedback channel add --name slack-ops --type slack --output-name my-slack-output
    limacharlie feedback channel add --name tg-ops --type telegram --output-name my-telegram-output
    limacharlie feedback channel add --name teams-ops --type ms_teams --output-name my-teams-output
    limacharlie feedback channel add --name email-ops --type email --output-name my-smtp-output

    # List configured channels
    limacharlie feedback channel list

    # Remove a channel
    limacharlie feedback channel remove --name old-channel
    ```

=== "Hive (bulk)"
    ```bash
    echo '{"data":{"channels":[{"name":"ops","channel_type":"web"},{"name":"slack-ops","channel_type":"slack","output_name":"my-slack-output"},{"name":"tg-ops","channel_type":"telegram","output_name":"my-telegram-output"},{"name":"teams-ops","channel_type":"ms_teams","output_name":"my-teams-output"},{"name":"email-ops","channel_type":"email","output_name":"my-smtp-output"}]},"usr_mtd":{"enabled":true}}' | \
      limacharlie hive set --hive-name extension_config --key ext-feedback
    ```

=== "Infrastructure as Code"
    Channels can be managed via [git-sync](git-sync.md) by including the extension config in your synced repository:
    ```yaml
    # extension_config/ext-feedback
    channels:
      - name: ops
        channel_type: web
      - name: slack-ops
        channel_type: slack
        output_name: my-slack-output
      - name: tg-ops
        channel_type: telegram
        output_name: my-telegram-output
      - name: teams-ops
        channel_type: ms_teams
        output_name: my-teams-output
      - name: email-ops
        channel_type: email
        output_name: my-smtp-output
    ```

For all channel types except `web`, the `output_name` field references a LimaCharlie [Tailored Output](../../outputs/index.md) that holds the credentials for the channel.

## Sending Feedback Requests

### Simple Approval

The `request_simple_approval` action sends a question with Approve/Deny buttons.

=== "CLI"
    ```bash
    limacharlie feedback request-approval \
      --channel ops \
      --question "Should we isolate host compromised-01?" \
      --destination case --case-id 78 \
      --approved-content '{"action": "isolate", "sid": "sensor-abc"}' \
      --denied-content '{"action": "skip"}'
    ```

=== "CLI (with timeout)"
    ```bash
    # Auto-deny after 5 minutes if no human responds
    limacharlie feedback request-approval \
      --channel ops \
      --question "Should we isolate host compromised-01?" \
      --destination case --case-id 78 \
      --approved-content '{"action": "isolate", "sid": "sensor-abc"}' \
      --denied-content '{"action": "skip"}' \
      --timeout 300 --timeout-choice denied
    ```

=== "Extension Request (generic)"
    ```bash
    limacharlie extension request \
      --name ext-feedback \
      --action request_simple_approval \
      --data '{
        "channel": "ops",
        "question": "Should we isolate host compromised-01?",
        "feedback_destination": "case",
        "case_id": "78",
        "approved_content": {"action": "isolate", "sid": "sensor-abc"},
        "denied_content": {"action": "skip"}
      }'
    ```

The response includes:

```json
{
  "request_id": "a1b2c3d4-...",
  "url": "https://feedback-system.limacharlie.io/r/a1b2c3d4-..."
}
```

The `url` is the shareable link to the web UI where the respondent can answer. For Slack, Telegram, Microsoft Teams, and email channels, no URL is returned in the response -- the message is sent directly to the configured channel.

### Acknowledgement

The `request_acknowledgement` action sends a question with an Acknowledge button.

=== "CLI"
    ```bash
    limacharlie feedback request-ack \
      --channel ops \
      --question "Alert: Ransomware detected on file-server-02. Please acknowledge." \
      --destination case --case-id 92 \
      --acknowledged-content '{"status": "seen"}'
    ```

=== "CLI (with timeout)"
    ```bash
    # Auto-acknowledge after 10 minutes
    limacharlie feedback request-ack \
      --channel ops \
      --question "Alert: Ransomware detected on file-server-02. Please acknowledge." \
      --destination case --case-id 92 \
      --timeout 600
    ```

=== "Extension Request (generic)"
    ```bash
    limacharlie extension request \
      --name ext-feedback \
      --action request_acknowledgement \
      --data '{
        "channel": "ops",
        "question": "Alert: Ransomware detected on file-server-02. Please acknowledge.",
        "feedback_destination": "case",
        "case_id": "92",
        "acknowledged_content": {"status": "seen"}
      }'
    ```

### Question (Free-Form Text)

The `request_question` action sends a question with a text input field. The respondent types a free-form answer.

=== "CLI"
    ```bash
    limacharlie feedback request-question \
      --channel ops \
      --question "What is the root cause of alert X?" \
      --destination playbook --playbook handle-root-cause
    ```

=== "CLI (with timeout)"
    ```bash
    # Auto-answer after 5 minutes with a default response
    limacharlie feedback request-question \
      --channel ops \
      --question "What is the root cause of alert X?" \
      --destination playbook --playbook handle-root-cause \
      --timeout 300 --timeout-content '{"answer": "no response"}'
    ```

=== "Extension Request (generic)"
    ```bash
    limacharlie extension request \
      --name ext-feedback \
      --action request_question \
      --data '{
        "channel": "ops",
        "question": "What is the root cause of alert X?",
        "feedback_destination": "playbook",
        "playbook_name": "handle-root-cause"
      }'
    ```

The response event includes `choice: "answered"` and a `text` field with the respondent's answer.

### D&R Rule Example

A D&R rule can request human approval before taking automated action. The response is dispatched to a playbook that performs the action.

**Detection:**

```yaml
op: is
event: NEW_PROCESS
path: event/FILE_PATH
value: /usr/bin/suspicious-tool
```

**Response:**

```yaml
- action: extension request
  extension name: ext-feedback
  extension action: request_simple_approval
  extension request:
    channel: '{{ "ops-slack" }}'
    question: '{{ "Suspicious process detected on " }}{{ .routing.hostname }}{{ ". Isolate host?" }}'
    feedback_destination: '{{ "playbook" }}'
    playbook_name: '{{ "isolate-host" }}'
    approved_content:
      action: '{{ "isolate" }}'
      sid: routing.sid
    denied_content:
      action: '{{ "monitor" }}'
      sid: routing.sid
    timeout_seconds: 300
    timeout_choice: '{{ "denied" }}'
```

The `timeout_seconds: 300` and `timeout_choice: "denied"` ensure the rule auto-denies if no one responds within 5 minutes, preventing the workflow from hanging indefinitely.

### Playbook Example

A playbook can request approval during execution:

```python
def playbook(sdk, data):
    # Request human approval with a 5-minute timeout.
    # sdk is a limacharlie.Manager instance.
    response = sdk.extensionRequest(
        "ext-feedback",
        "request_simple_approval",
        {
            "channel": "ops",
            "question": f"Isolate host {data.get('hostname', 'unknown')}?",
            "feedback_destination": "playbook",
            "playbook_name": "handle-isolation-response",
            "approved_content": {"action": "isolate", "sid": data.get("sid")},
            "denied_content": {"action": "skip"},
            "timeout_seconds": 300,
            "timeout_choice": "denied",
        },
    )

    # The response will trigger the handle-isolation-response playbook
    # when the human responds (or after 5 minutes with choice="denied"
    # and responder="timeout").
    return {"request_id": response.get("request_id")}
```

## Response Flow

1. A feedback request is created and stored with a 7-day TTL
2. The question is delivered via the configured channel (Slack message or web URL)
3. The respondent clicks a button or submits a text response (or the timeout fires if configured)
4. The response is routed through the organization's webhook adapter (authenticated via `lc-secret` header)
5. A D&R rule matches the response event and triggers the extension's `process_response` action
6. The extension atomically claims the request (preventing duplicate processing) and dispatches the response to the configured destination

If a timeout is configured and no human responds before the deadline, the system automatically sends a response with the configured default choice. The timeout response includes `responder: "timeout"` so downstream automation can distinguish it from human responses.

Feedback requests expire after **7 days**. Expired requests show an error in the web UI and are rejected by the extension.

Responses are protected against replay: once a response is processed, any duplicate deliveries (from webhook retries or replay) are rejected. This also prevents races between a human response and a timeout firing simultaneously -- whichever is processed first claims the request.

## Slack Setup

To use Slack channels:

1. Create a Slack App with "Interactivity & Shortcuts" enabled
2. Set the Request URL to the Slack callback endpoint: `https://feedback-system.limacharlie.io/callback/slack`
3. Install the app to your Slack workspace and note the Bot User OAuth Token
4. In LimaCharlie, create a [Slack Tailored Output](../../outputs/destinations/slack.md) with:
    - `slack_api_token`: the Bot User OAuth Token
    - `slack_channel`: the target channel (e.g. `#security-ops`)
5. Add a Slack channel to your extension config referencing the output name (see [Channel Configuration](#channel-configuration)). For example, a channel with `name: "ops"`, `channel_type: "slack"`, and `output_name: "my-slack-output"`.

!!! note
    For `request_question` feedback type, Slack shows a "Respond" button that links to the web UI, since Slack interactive messages do not support inline text input fields.

## Telegram Setup

To use Telegram channels, you need a Telegram bot and a LimaCharlie Tailored Output with its credentials.

### Step 1: Create a Telegram Bot

1. Open Telegram and start a conversation with [**@BotFather**](https://t.me/BotFather) ([Telegram Bot API documentation](https://core.telegram.org/bots#botfather))
2. Send `/newbot` and follow the prompts to choose a name and username
3. BotFather will respond with a **bot token** (e.g. `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`). Save this token.
4. Add the bot to the Telegram group or channel where you want feedback messages delivered
5. Get the **chat ID** of the group or channel. You can do this by:
    - Adding the bot to the group, sending a message, then checking `https://api.telegram.org/bot<TOKEN>/getUpdates` for the `chat.id` field
    - For channels, the chat ID is typically a negative number like `-1001234567890`

For more information, see the [Telegram Bot API documentation](https://core.telegram.org/bots/api).

### Step 2: Create a Tailored Output

In LimaCharlie, create a Telegram [Tailored Output](../../outputs/index.md) with:

- `bot_token`: the bot token from BotFather
- `chat_id`: the target chat, group, or channel ID

### Step 3: Add a Telegram Channel

Add a channel to your extension config referencing the output name:

```yaml
channels:
  - name: tg-ops
    channel_type: telegram
    output_name: my-telegram-output
```

### How Telegram Responses Work

For `simple_approval` and `acknowledgement` feedback types, Telegram messages include **inline keyboard buttons** (Approve/Deny or Acknowledge) that the respondent can tap directly in the chat. The response is processed immediately without leaving Telegram.

For `request_question`, a "Respond" button links to the web UI since Telegram inline keyboards do not support text input.

When a response is received, the original Telegram message is updated to show the choice and who responded.

!!! note
    The extension automatically registers a webhook with the Telegram bot (using [`setWebhook`](https://core.telegram.org/bots/api#setwebhook)) to receive button-click callbacks. If the bot is also used for other webhook-based integrations, the ext-feedback webhook registration will override the existing one. Use a dedicated bot for ext-feedback if this is a concern.

## Microsoft Teams Setup

To use Microsoft Teams channels, you need a Teams Workflow webhook URL and a LimaCharlie Tailored Output.

!!! warning "Incoming Webhooks retired"
    Microsoft retired Office 365 Connectors (including Incoming Webhooks) from Teams. You must use a Power Automate Workflow as described below.

### Create a Workflow Webhook

1. In Microsoft Teams, navigate to the channel where you want feedback messages
2. Click **...** (More options) next to the channel name
3. Select **Workflows**
4. Search for and select the **Send webhook alerts to a channel** template
5. Give the workflow a name (e.g. "LimaCharlie Feedback") and authenticate your account
6. Click **Next**, confirm the Team and Channel, then click **Add workflow**
7. Copy the webhook URL from the confirmation dialog

For details, see [Create incoming webhooks with Workflows](https://support.microsoft.com/en-us/office/create-incoming-webhooks-with-workflows-for-microsoft-teams-8ae491c7-0394-4861-ba59-055e33f75498).

### Create the Tailored Output

In LimaCharlie, create a Microsoft Teams [Tailored Output](../../outputs/index.md) with:

- `webhook_url`: the Teams webhook URL (from either option above)

### Add a Teams Channel

Add a channel to your extension config referencing the output name:

```yaml
channels:
  - name: teams-ops
    channel_type: ms_teams
    output_name: my-teams-output
```

### How Teams Responses Work

Feedback requests are delivered as [Adaptive Cards](https://learn.microsoft.com/en-us/adaptive-cards/) in the Teams channel. The card displays the question and a button that opens the web approval page in a browser. Responses are collected through the web UI.

## Email Setup

To use email channels, you need an SMTP server and a LimaCharlie Tailored Output with its credentials.

### Create a Tailored Output

In LimaCharlie, create an SMTP [Tailored Output](../../outputs/index.md) with:

- `dest_host`: SMTP server address, optionally with port (e.g. `smtp.example.com:587`). Defaults to port 587 if not specified.
- `dest_email`: the recipient email address (e.g. `soc@example.com`)
- `from_email`: the sender email address (e.g. `limacharlie@example.com`)
- `username` (optional): SMTP authentication username
- `password` (optional): SMTP authentication password

### Add an Email Channel

Add a channel to your extension config referencing the output name:

```yaml
channels:
  - name: email-ops
    channel_type: email
    output_name: my-smtp-output
```

### How Email Responses Work

The extension sends an HTML email containing the feedback question and a **Respond** button that links to the web approval page. Responses are collected through the web UI.

## Actions Reference

| Action | User-facing | Description |
|--------|:-----------:|-------------|
| `request_simple_approval` | Yes | Send a feedback request with Approve/Deny buttons |
| `request_acknowledgement` | Yes | Send a feedback request with an Acknowledge button |
| `request_question` | Yes | Send a question with a free-form text input |
| `process_response` | No | Internal: processes a response received via webhook |

### request_simple_approval Parameters

| Parameter | Required | Description |
|-----------|:--------:|-------------|
| `channel` | Yes | Name of the feedback channel |
| `question` | Yes | The question or prompt to present |
| `feedback_destination` | Yes | `case`, `playbook`, or `ai_agent` |
| `case_id` | When destination is `case` | Case to add the response note to |
| `playbook_name` | When destination is `playbook` | Playbook to trigger with the response |
| `ai_agent_name` | When destination is `ai_agent` | Name of the `ai_agent` hive record to start a session with |
| `approved_content` | No | JSON data included when the respondent approves |
| `denied_content` | No | JSON data included when the respondent denies |
| `timeout_seconds` | No | Auto-respond after this many seconds if no response (minimum 60) |
| `timeout_choice` | When `timeout_seconds` is set | Choice to auto-select on timeout: `approved` or `denied` |
| `timeout_content` | No | JSON data for the timeout response (overrides the choice's content) |

### request_acknowledgement Parameters

| Parameter | Required | Description |
|-----------|:--------:|-------------|
| `channel` | Yes | Name of the feedback channel |
| `question` | Yes | The question or prompt to present |
| `feedback_destination` | Yes | `case`, `playbook`, or `ai_agent` |
| `case_id` | When destination is `case` | Case to add the response note to |
| `playbook_name` | When destination is `playbook` | Playbook to trigger with the response |
| `ai_agent_name` | When destination is `ai_agent` | Name of the `ai_agent` hive record to start a session with |
| `acknowledged_content` | No | JSON data included when the respondent acknowledges |
| `timeout_seconds` | No | Auto-acknowledge after this many seconds if no response (minimum 60) |
| `timeout_content` | No | JSON data for the timeout response (overrides `acknowledged_content`) |

### request_question Parameters

| Parameter | Required | Description |
|-----------|:--------:|-------------|
| `channel` | Yes | Name of the feedback channel |
| `question` | Yes | The question or prompt to present |
| `feedback_destination` | Yes | `case`, `playbook`, or `ai_agent` |
| `case_id` | When destination is `case` | Case to add the response note to |
| `playbook_name` | When destination is `playbook` | Playbook to trigger with the response |
| `ai_agent_name` | When destination is `ai_agent` | Name of the `ai_agent` hive record to start a session with |
| `timeout_seconds` | No | Auto-answer after this many seconds if no response (minimum 60) |
| `timeout_content` | When `timeout_seconds` is set | JSON data used as the automatic answer on timeout (required for question type) |
