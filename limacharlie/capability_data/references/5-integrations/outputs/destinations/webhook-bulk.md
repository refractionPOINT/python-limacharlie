# Webhook (Bulk)

Output batches of events, detections, audits, deployments or artifacts through a POST webhook.

- `dest_host`: the IP or DNS, port and page to HTTP(S) POST to, format `https://www.myorg.com:514/whatever`.
- `secret_key`: an arbitrary shared secret used to compute an HMAC (SHA256) signature of the webhook to verify authenticity. This is a required field. [See "Webhook Details" section.](webhook.md)
- `auth_header_name` and `auth_header_value`: set a specific value to a specific HTTP header name in the outgoing webhooks.
- `sec_per_file`: the number of seconds after which a file is cut and uploaded.
- `is_no_sharding`: do not add a shard directory at the root of the files generated.

Example:

```text
dest_host: https://webhooks.corp.com/new_detection
secret_key: this-is-my-secret-shared-key
auth_header_name: x-my-special-auth
auth_header_value: 4756345846583498
```

## Related articles

- [Tutorial: Creating a Webhook Adapter](../../../2-sensors-deployment/adapters/tutorials/webhook-adapter.md)

## What's Next

- [Testing Outputs](../testing.md)
