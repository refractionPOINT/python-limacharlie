[Documentation](../README.md) > [CLI](README.md) > Platform Administration

# Platform Administration

Commands for organization management, users, groups, API keys, ingestion keys, billing, and audit logs.

## org

```bash
limacharlie org info                     # Name, sensor count, version, quotas
limacharlie org stats                    # Usage statistics
limacharlie org quota-usage              # Enforced sensor quota usage + breakdown
limacharlie org urls                     # Service URLs (for firewall rules)
limacharlie org errors                   # Platform errors
limacharlie org dismiss-error --component <name>
limacharlie org config-get --name vt     # Read a config value
limacharlie org config-set --name vt --value <key>
limacharlie org mitre                    # MITRE ATT&CK coverage report
limacharlie org schema                   # Event schemas
limacharlie org schema --event-type NEW_PROCESS
limacharlie org list                     # List accessible organizations
limacharlie org create --name my-org --location us
limacharlie org rename --name new-name
limacharlie org delete                   # Step 1: get confirmation token
limacharlie org delete --confirm-token <token>  # Step 2: confirm
```

## user

```bash
limacharlie user list
limacharlie user invite --email user@example.com
limacharlie user remove --email user@example.com
limacharlie user permissions list
limacharlie user permissions add --email user@example.com --permission dr.set
limacharlie user permissions set-role --email user@example.com --role Administrator
```

## group

```bash
limacharlie group list
limacharlie group create --name my-group
limacharlie group member-add --group-id GID --email user@example.com
```

## api-key

```bash
limacharlie api-key list
limacharlie api-key create --name ci-key --permissions '["dr.list","sensor.list"]'
limacharlie api-key delete --key-hash HASH
```

## ingestion-key

```bash
limacharlie ingestion-key list
limacharlie ingestion-key create --name my-ingest-key
```

## billing

```bash
limacharlie billing status                     # Billing overview
limacharlie billing details                    # Detailed breakdown
```


### Security product billing

```bash
limacharlie billing security get mail_security --oid <oid> --output yaml
limacharlie billing security get code_security --from 2026-10-01 --until 2026-11-01 --oid <oid> --output yaml
```

Read requires `org.get` and `billing.ctrl`. Subscribing to Email Security or Cloud
Security purchases its coverage on a paid organization with a payment method or
authorized invoicing. Coverage starts automatically; unsubscribing or moving the
organization to the free tier stops future paid coverage. Inspect `get` until the
protection service acknowledges the transition.

Mail costs $1 per protected mailbox-month; Code costs $0.80 per protected
repository-month plus the Cloud Security base fee. Rates are divided by 30 per
UTC entity-day; 31 days of constant paid coverage cost 31/30 of the monthly rate.
Today's high-water mark is provisional; accrued usage is an estimate rather than
a finalized invoice.

The 14-day trial covers up to 25 mailboxes or 10 repositories. Trial-period usage
is free, including for paid organizations. On the free tier, coverage pauses when
the trial expires. Unsubscribing preserves accrued charges and trial history.
Unsubscribing from Cloud Security also stops Code coverage and its Cloud base fee.


## audit

```bash
limacharlie audit list --start 1704067200 --end 1704153600
```

## See Also

- [Organization SDK](../sdk/organization.md) — Organization Python class
- [Other SDK Classes](../sdk/other-classes.md) — Users, Billing, and more
- [Authentication](../authentication.md) — Credential setup
