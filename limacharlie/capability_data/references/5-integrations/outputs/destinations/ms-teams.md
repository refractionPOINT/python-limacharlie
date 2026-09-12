# Microsoft Teams

Output detections and audit (only) to a Microsoft Teams channel via webhook.

Messages are delivered as [Adaptive Cards](https://learn.microsoft.com/en-us/adaptive-cards/).

- `webhook_url`: the Microsoft Teams Workflow webhook URL.
- `message`: (optional) a template string for custom message formatting.

Example:

```text
webhook_url: https://<environment-id>.<region>.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/...
```

## Provisioning

LimaCharlie connects to a Teams channel using a **Power Automate Workflow** webhook.

!!! warning "Incoming Webhooks retired"
    Microsoft retired Office 365 Connectors (including Incoming Webhooks) from Teams. The old `webhook.office.com` URLs no longer work. You must use a Power Automate Workflow as described below.

### Create a Workflow webhook

1. In Microsoft Teams, navigate to the target channel
2. Click **...** (More options) next to the channel name
3. Select **Workflows**
4. Search for and select the **Send webhook alerts to a channel** template
5. Give the workflow a name (e.g. "LimaCharlie") and authenticate your account
6. Click **Next**, confirm the Team and Channel, then click **Add workflow**
7. Copy the webhook URL from the confirmation dialog — this is the `webhook_url` you need in LimaCharlie

For details, see [Create incoming webhooks with Workflows](https://support.microsoft.com/en-us/office/create-incoming-webhooks-with-workflows-for-microsoft-teams-8ae491c7-0394-4861-ba59-055e33f75498).

!!! note "Workflow limitations"
    - Workflows post via **Flow bot**, which only works in **public channels**. For shared channels, open the workflow in Power Automate and change "Post As" from Flow bot to User.
    - Workflows are linked to the user who created them. If that user leaves the organization the workflow stops working. Add co-owners in Power Automate to avoid this.
