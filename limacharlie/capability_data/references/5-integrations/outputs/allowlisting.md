# Adding Outputs to an Allow List

At LimaCharlie, we rely on infrastructure with auto-scalers, and thus do not have static IPs nor a CIDR that you can rely on for an allow list (or "whitelisting").

Typically, the concern around adding IPs to an allow list for Outputs is based on wanting to limit abuse and ensure that data from webhooks is truly coming from LimaCharlie and not other sources. To address this, we provide a `secret_key` parameter that can be used as a *shared secret* between LimaCharlie and your webhook receiver. When we issue a webhook, we include a `lc-signature` header that is an HMAC of the content of the webhook using the shared `secret_key`.
