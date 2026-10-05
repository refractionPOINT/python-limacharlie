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
limacharlie billing security activate mail_security --accepted-quote accepted-quote.json --accept-pricing --oid <oid> --output yaml
limacharlie billing security stop code_security --confirm --oid <oid> --output yaml
```

Read requires `org.get` and `billing.ctrl`; activation and stop require `billing.ctrl`
and `user.ctrl`. Review the price before passing `--accept-pricing`. Mail costs
$1 per protected mailbox-month, Code $0.80 per protected repository-month plus the
separate Cloud Security base fee. Rates are divided by 30 per UTC entity-day;
31 days of constant paid coverage cost 31/30 of the monthly rate. Today's high-water
mark is provisional; accrued usage is an estimate rather than a finalized invoice.

Read `get` after mutation: a pending transition does not confirm protection.
Stop preserves accrued charges and trial history. Code stop keeps the Cloud base
fee; stopping that separate subscription is a separate operation.


## audit

```bash
limacharlie audit list --start 1704067200 --end 1704153600
```

## See Also

- [Organization SDK](../sdk/organization.md) — Organization Python class
- [Other SDK Classes](../sdk/other-classes.md) — Users, Billing, and more
- [Authentication](../authentication.md) — Credential setup

Security activation requires `--accepted-quote FILE`, a JSON file containing the
complete reviewed `status.pricing_quote` from `billing security get`. Verify
`status.quote_guard_version` is 1, review the rates and independent Code Cloud fee,
then pass that unchanged quote with `--accept-pricing`. All nine fields are required,
including Email's zero/empty Cloud fields. HTTP 409 `security_quote_changed` requires
GET and fresh consent; HTTP 503 is retryable after checking status. HTTP 200
`acknowledged: false` is pending: poll GET until the control settles and protection
matches the request. The SDK uses `Billing(org).activate_security(product,
accept_pricing=True, accepted_quote=reviewed_quote)` with the same complete quote.
