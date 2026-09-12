# Webhook

Output individually each event, detection, audit, deployment or artifact through a POST webhook.

- `dest_host`: the IP or DNS, port and page to HTTP(S) POST to, format `https://www.myorg.com:514/whatever`.
- `secret_key`: an arbitrary shared secret used to compute an HMAC (SHA256) signature of the webhook to verify authenticity. [See "Webhook Details" section.](../allowlisting.md)
- `auth_header_name` and `auth_header_value`: set a specific value to a specific HTTP header name in the outgoing webhooks.

Example:

```text
dest_host: https://webhooks.corp.com/new_detection
secret_key: this-is-my-secret-shared-key
auth_header_name: x-my-special-auth
auth_header_value: 4756345846583498
```

Example [hook to Google Chat](https://developers.google.com/chat/how-tos/webhooks):

```text
dest_host: https://chat.googleapis.com/v1/spaces/AAAA4-AAAB/messages?key=afsdfgfdgfE6vySjMm-dfdssss&token=pBh2oZWr7NTSj9jisenfijsnvfisnvijnfsdivndfgyOYQ%3D
secret_key: gchat-hook-sig42
custom_transform: |
   {
      "text": "Detection {{ .cat }} on {{ .routing.hostname }}: {{ .link }}"
   }
```
