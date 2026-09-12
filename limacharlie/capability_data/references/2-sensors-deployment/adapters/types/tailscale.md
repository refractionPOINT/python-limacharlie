# Tailscale

[Tailscale](https://tailscale.com/) is a VPN service that makes devices and applications accessible anywhere in the world. Relying on the open source WireGuard protocol, Tailscale enables encrypted point-to-point connections.

Tailscale events can be ingested in LimaCharlie via a `json` Webhook Adapter.

## Adapter Deployment

Tailscale events are ingested via a cloud-to-cloud webhook Adapter configured to receive JSON events. In the creation of the Adapter, we map fields directly to the expected Tailscale webhook events. The steps of creating this Adapter and enabling the input include:

1. Creating the Webhook Adapter via the LimaCharlie CLI.
2. Discovering the URL created for the Webhook Adapter.
3. Providing the completed URL to Tailscale for Webhook events.

### 1. Creating the LimaCharlie Webhook Adapter

These steps are adapted from the [generic Webhook Adapter creation guide](../tutorials/webhook-adapter.md).

Creating a Webhook Adapter requires a set of parameters, including organization ID, Installation Key, platform, and mapping details. The following configuration has been provided to configure a Webhook Adapter for ingesting Tailscale events:

```json
{
    "sensor_type": "webhook",
    "webhook": {
       "secret": "tailscale-secret",
        "client_options": {
            "hostname": "tailscale",
            "identity": {
                "oid": "<your_oid>",
                "installation_key": "<your_installation_key>"
            },
            "platform": "json",
            "sensor_seed_key": "tailscale-super-secret-key",
            "mapping" : {
                "event_type_path" : "message"
            }
        }
    }
}
```

The mapping above is based on the expected Webhook event from Tailscale ([example provided here](https://tailscale.com/kb/1213/webhooks/)). Note that in the mapping above, we make the following change:

- `event_type_path` is mapped to the `message` field

### 2. Building the Webhook URL

After creating the webhook, you'll need to retrieve the webhook URL from the [Get Org URLs](https://api.limacharlie.io/static/swagger/#/Org/get_orgs__oid___urls) API call. You'll need the following information to complete the Webhook URL:

- Organization ID
- Webhook name (from the config)
- Secret (from the config)

Let's assume the returned domain looks like `9157798c50af372c.hook.limacharlie.io`, the format of the URL would be:

`https://9157798c50af372c.hook.limacharlie.io/OID/HOOKNAME/SECRET`

Note that the `secret` value can be provided in the webhook URL or as an HTTP header named `lc-secret`.

### 3. Providing the URL to Tailscale for Webhook Events

Within the Tailscale Admin Console, navigate to **Settings** > **Webhooks**. Select **Add endpoint...**

![image.png](../../../assets/images/image(168).png)

Provide the completed Webhook URL from Step 2, above. You can also select the various events you want sent via Webhook. Options include:

![image.png](../../../assets/images/image(170).png)

Select **Add endpoint**. Tailscale will provide you a webhook secret unique to this endpoint. You may want to keep this value, however it is not required within LimaCharlie.

#### 4. Test Webhook Output

Within the Tailscale Admin Console, you can test the webhook out and ensure that LimaCharlie is receiving events. Within the Webhook Endpoint options, select **Test endpoint...**.

You should see the webhook event populate within the LimaCharlie Adapter a moment later. Note that the `event_type` will match the `message` field from the Tailscale webhook event.
