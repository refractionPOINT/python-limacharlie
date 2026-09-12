# IMAP

## Overview

This Adapter allows you to ingest emails as events from an IMAP server.

## Configurations

Adapter Type: `imap`

- `client_options`: see [common adapter configuration](../usage.md).
- `server`: the domain and port of the IMAP server, like `imap.gmail.com:993`.
- `username`: the user name to log in to IMAP as.
- `password`: the password for the above user name.
- `inbox_name`: the name of the inbox to monitor.
- `is_insecure`: do NOT connect using SSL.
- `from_zero`: collect all existing emails in the inbox.
- `include_attachments`: send attachment data to LimaCharlie, used to generate attachment hashes in the cloud.
- `max_body_size`: only send attachments below this many bytes to LimaCharlie.
- `attachment_ingest_key`: if specified, an [Ingestion Key](../../../7-administration/access/api-keys.md) used to ingest attachment as Artifacts into LimaCharlie.
- `attachment_retention_days`: the number of days to retain Artifact attachment for.

### Configuration File Example

```yaml
imap:
  server: "imap.yourmailserver.com:993"
  username: "hive://secret/imap-username"
  password: "hive://secret/imap-password"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_IMAP"
    hostname: "imap-email-collector"
    platform: "json"
    sensor_seed_key: "imap-sensor-001"
    mapping:
      sensor_hostname_path: "headers.X-Originating-IP"
      event_type_path: "headers.Subject"
      event_time_path: "headers.Date"
    indexing: []
  # Optional IMAP-specific configuration
  inbox_name: "INBOX"                    # Default: "INBOX"
  is_insecure: false                     # Default: false (use SSL/TLS)
  from_zero: false                       # Default: false (only new emails)
  include_attachments: true              # Default: false
  max_body_size: 102400                  # Default: 0 (no limit)
  attachment_ingest_key: "attachments_data"      # Default: empty
  attachment_retention_days: 30          # Default: 0 (no retention)
```

## Use Cases

Although this Adapter can be used on any IMAP server for any inbox, it is often used to perform enterprise wide analysis and alerting using Email Journaling.

Email Journaling is supported by all major email platforms to perform analysis at scale. It generally involves enabling a data flow of all emails on the platform towards a specific email account where all emails accumulate.

Documentation for common platforms:

- [Exchange Online](https://learn.microsoft.com/en-us/exchange/security-and-compliance/journaling/journaling)
- [Google Workspace](https://support.google.com/a/answer/7276605?product_name=UnuFlow&hl=en&visit_id=638608978952474178-2452031765&rd=1&src=supportwidget0&hl=en)

## Example Format

Emails ingested through the IMAP Adapter are in raw format so that detailed header information can be included and analyzed. Below is an example of an email received into LimaCharlie from a Google Workspace mailbox:

```json
{
    "event": {
        "headers": {
            "arc-authentication-results": [
                "i=1; mx.google.com; dkim=pass header.i=@evil.com header.s=google header.b=LdyiNwmQ; spf=pass (google.com: domain of badguy@evil.com designates 209.85.220.41 as permitted sender) smtp.mailfrom=badguy@evil.com; dmarc=pass (p=NONE sp=NONE dis=NONE) header.from=evil.com; dara=pass header.i=@gmail.com"
            ],
            "arc-message-signature": [
                "i=1; a=rsa-sha256; c=relaxed/relaxed; d=google.com; s=arc-20160816; h=to:subject:message-id:date:from:mime-version:dkim-signature; bh=NWZDzWD3fcPGImfiLFJgiOAWQBc6o9f064zRNQOEAZA=; fh=LdhDNbjh6ex3RxMo3wPAKsbuLWT+x/GDPYiwjW9lr10=; b=Y4WpYrqSVH+EuabO9I4v/LUf9MpLBNxghhA3btw3i31h3YHwssUKcYmfGu/LN5+2qc O4h7QYPT8oq5Sbk5T9NYYXb/u2XEyFmcHq78X9r1VBGgRXVzDVoAVE6uYdE+bMSsnBCx grJrZV+HEejJh91iNRlJ8+RDlESBAWastC6YpDHmZkAveUjMUzFBYzTiqCmGBjNYjfoF FOZSrlXMPj4fitoFunI57miFMXjXxiselSo9UEMuyeEcHAuiGZUyNHhLDTri+Nmf/5w1 QvaKCTx7iL4HpeS7budFLf4CuPbqNVIKmvsGq5vn68WFSO8i8AOW08IsKVlw/13KWQlu 6pTg==; dara=google.com"
            ],
            "arc-seal": [
                "i=1; a=rsa-sha256; t=1725302104; cv=none; d=google.com; s=arc-20160816; b=VPXTfX1HVTFWRixWBstbi2VEAFi6Tt7tfZPEn+4DBZ84n6Jn0MxTWRLP/2Y2GZkDC4 /ugCK/hRaxSqb9UzO9H/AGyrc2qX+rrX1OwLyQqSX5mA6ovrtNOuuHdS5BIBZjNQJS9X +aZICM/ZlkBvcPTKk8xLv/7yLD08xfaIZLdDWmbasg+pxKE5l+nLaxg7mXNC++8PaJRV ziaF9M7xd+Cx1kzDaSMBjTaubqtv3k7rQCqCN7WSLtxn0l2oz/Mdzvntdfcc7/qLrwNi yfmoG/lB4SrikCJJ7DsnGBvn7uCQZjsVbVTi4wLzIUCjqk5XNjIbTVZ1zVQ/HNwvg43g 6MiQ=="
            ],
            "authentication-results": [
                "mx.google.com; dkim=pass header.i=@evil.com header.s=google header.b=LdyiNwmQ; spf=pass (google.com: domain of badguy@evil.com designates 209.85.220.41 as permitted sender) smtp.mailfrom=badguy@evil.com; dmarc=pass (p=NONE sp=NONE dis=NONE) header.from=evil.com; dara=pass header.i=@gmail.com"
            ],
            "content-type": [
                "multipart/alternative; boundary=\"00000000000006151206212733f4\""
            ],
            "date": [
                "Mon, 2 Sep 2024 11:34:26 -0700"
            ],
            "delivered-to": [
                "acme@gmail.com"
            ],
            "dkim-signature": [
                "v=1; a=rsa-sha256; c=relaxed/relaxed; d=evil.com; s=google; t=1725302104; x=1725906904; dara=google.com; h=to:subject:message-id:date:from:mime-version:from:to:cc:subject :date:message-id:reply-to; bh=NWZDzWD3fcPGImfiLFJgiOAWQBc6o9f064zRNQOEAZA=; b=LdyiNwmQU+l8TQfVFgJYRNMvGqiplaqTOqlGWpSMUGm8891aHvKrxkqpjnHULKaY5l PzU3i0TK4Xl5Mdhjde5ewyD1o5BWTx8qEOFMuiZBOwOQys6nzcwBzQxKEuc8d6+GN8Z1 2H4uBqSxYfOaHAVU5qVx5/7IJF4TMDY/LK8A4="
            ],
"from": [
                "Bad Guy <badguy@evil.io>"
            ],
            "message-id": [
                "<CAD-4=gGtg=3dbuOO8M6pLairyXpnTD6Oh3P1OXauW5-SOXV0yw@mail.gmail.com>"
            ],
            "mime-version": [
                "1.0"
            ],
            "received": [
                "by 2002:a05:7010:161f:b0:3f2:d648:d2e9 with SMTP id l31csp230833mdi; Mon, 2 Sep 2024 11:35:05 -0700 (PDT)",
                "from mail-sor-f41.google.com (mail-sor-f41.google.com. [209.85.220.41]) by mx.google.com with SMTPS id d2e1a72fcca58-715e5749b07sor4893537b3a.11.2024.09.02.11.35.04 for <acme@gmail.com> (Google Transport Security); Mon, 02 Sep 2024 11:35:04 -0700 (PDT)"
            ],
            "received-spf": [
                "pass (google.com: domain of badguy@evil.com designates 209.85.220.41 as permitted sender) client-ip=209.85.220.41;"
            ],
            "return-path": [
                "<badguy@evil.com>"
            ],
            "subject": [
                "more testing"
            ],
            "to": [
                "acme@gmail.com"
            ],
            "x-gm-message-state": [
                "AOJu0YzthcsAvu7FAaCG7tVsbF4IP4NAAP2ICmXBCZM3q/X+EjpqD6L+ HBDMSMll8JxmIsLL9Hq4U6l/4iwLiRBys3iUsJ3A03Tr5TQVO+PUZyvd5CBxtrsj0Hy675LgaQ7 0oJ2lN6XxBJuSm+/UvFWcTafXVHpnHqvcnYE6cByvJzwFOaEV06U="
            ],
"x-google-dkim-signature": [
                "v=1; a=rsa-sha256; c=relaxed/relaxed; d=1e100.net; s=20230601; t=1725302104; x=1725906904; h=to:subject:message-id:date:from:mime-version:x-gm-message-state :from:to:cc:subject:date:message-id:reply-to; bh=NWZDzWD3fcPGImfiLFJgiOAWQBc6o9f064zRNQOEAZA=; b=VNAyNje9Qf3Xz7pGtX6FCaK67/ICW8aVWws/VdEDA/Ay1XO91LBQdEv7cKjZ+mcm1K uS5gPPVBMXVf+68KmiWyoiartMf/X4VsuTWzJRHyrtL9O8fX26xcgElzkAmm9N6/hKYg qsZujh4fpii2jk8VIz3jGNWB41qUbJklu9BNSRLiwzQnew9Av/J48+JaxfZA38qD08x4 o7UPxTick1figeCmYpAR0x16ETNg6lLC8GdJEnnWlIUZJN+K2z3A7xwD6SdAjsy6HFur 6oonKeJjVIzirWToF2mspK5MHbGI8aXmFzpu51gvQsC9caRDNaod9C9GlwSM/2oLhQWN kozw=="
            ],
            "x-google-smtp-source": [
                "AGHT+IF4ypTOZTFYRo4zx1pdxWk8sJAzLq+8GoGM8toOjlzCT7o9u5Tw0AWDAwK+2MjV6eBL1v0fhHbYcjfipAgz4Y4="
            ],
"x-received": [
                "by 2002:a05:6a00:9451:b0:714:3153:ab4 with SMTP id d2e1a72fcca58-717458aeedemr5351482b3a.27.1725302104964; Mon, 02 Sep 2024 11:35:04 -0700 (PDT)",
                "by 2002:a05:6a20:c68e:b0:1ce:d412:f407 with SMTP id adf61e73a8af0-1ced412f48bmr6010277637.18.1725302103735; Mon, 02 Sep 2024 11:35:03 -0700 (PDT)"
            ]
        },
        "parts": [
            {
                "body_text": "One more test email.\r\n",
                "hashes": {
                    "md5": "cbe37e2ee4cf3c35d67a7c4a8e6a9e35",
                    "sha1": "c2f203f43304ab0a4c3154a84d0c876fa9c23204",
                    "sha256": "95dbb63f3fd41f7852395d84ef9570ef4db567c43d20e3f1e27c72c903b94686"
                },
                "headers": {
                    "content-type": [
                        "text/plain; charset=\"UTF-8\""
                    ]
                }
            },
            {
                "body_text": "<div dir=\"ltr\">One more test email.</div>\r\n",
                "hashes": {
                    "md5": "a2fcd5c1aa40abe526bbbbd58251a90f",
                    "sha1": "5748cc5fc2cd318a5584651731887ac9d9df4df2",
                    "sha256": "1f3877f593c1af2ad3e482aee2f4181a34e0f502799908f4ca330f3327d6c175"
                },
                "headers": {
                    "content-type": [
                        "text/html; charset=\"UTF-8\""
                    ]
                }
            }
        ]
    },
    "routing": {
        "arch": 9,
        "did": "",
        "event_id": "fb9554d8-522e-4977-a378-df7f3fcc186a",
        "event_time": 1725302106808,
        "event_type": "email",
        "ext_ip": "internal",
        "hostname": "testimap",
        "iid": "XXXXXXX",
        "int_ip": "",
        "moduleid": 6,
        "oid": "YYYYYY",
        "plat": 436207616,
        "sid": "ZZZZZZZZ",
        "tags": [
            "cloud2"
        ],
        "this": "f4925ea82ef44d18b349695466d6055a"
    }
}
```
