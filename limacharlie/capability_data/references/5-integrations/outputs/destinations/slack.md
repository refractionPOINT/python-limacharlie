# Slack

Output detections and audit (only) to a Slack community and channel.

- `slack_api_token`: the Bot User OAuth Token from your Slack App.
- `slack_channel`: the channel to output to within the community (e.g. `#detections`).

Example:

```text
slack_api_token: xoxb-your-bot-token
slack_channel: #detections
```

## Provisioning

To use this Output, you need to create a Slack App and Bot:

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**, select **From scratch**, and choose the workspace
3. From the sidebar, click **OAuth & Permissions**
4. Under **Bot Token Scopes**, click **Add an OAuth Scope** and add `chat:write`
5. From the sidebar, click **Install App**, then **Install to Workspace**
6. Copy the **Bot User OAuth Token** — this is the `slack_api_token` you need in LimaCharlie
7. In your Slack workspace, go to the target channel and invite the bot with the slash command: `/invite @your-app-name`

### Interactivity Setup (for ext-feedback)

If using this output with the [Feedback extension](../../extensions/limacharlie/feedback.md) for interactive Slack messages (approval buttons, acknowledgements):

1. In your Slack App settings ([api.slack.com/apps](https://api.slack.com/apps)), click **Interactivity & Shortcuts** in the sidebar
2. Toggle **Interactivity** to **On**
3. Set the **Request URL** to `https://feedback-system.limacharlie.io/callback/slack`
4. Click **Save Changes**

This allows Slack to send button-click interactions back to the feedback extension for processing. No additional LimaCharlie output parameters are needed — the extension registers the callback automatically.
