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
limacharlie org config-set --name sensor_auto_upgrade --value stable  # See below
limacharlie org mitre                    # MITRE ATT&CK coverage report
limacharlie org schema                   # Event schemas
limacharlie org schema --event-type NEW_PROCESS
limacharlie org list                     # List accessible organizations
limacharlie org create --name my-org --location us
limacharlie org rename --name new-name
limacharlie org delete                   # Step 1: get confirmation token
limacharlie org delete --confirm-token <token>  # Step 2: confirm
```

`org config-set` accepts only these configuration names,
matched exactly (case-sensitive). Any other name is rejected by the API as
unknown.

| Name | Purpose | Permission to set |
|------|---------|-------------------|
| `vt`, `otx`, `domain`, `shodan`, `pagerduty`, `twilio`, `socprime`, `alphamountain`, `pangea`, `echotrail`, `hybrid_analysis`, `greynoise`, `ipqs` | Integration API keys and settings. | `org.conf.set` |
| `sensor_auto_upgrade` | Automatic sensor upgrades. | `org.conf.set` and `module.update` |

Where automatic sensor upgrades are available, `sensor_auto_upgrade` keeps the
organization's sensors on a sensor release channel: when a new version of that
channel is published, they are upgraded automatically, in batches. The value
names the channel:

| Value | Meaning |
|-------|---------|
| `stable` | Follow the stable sensor version. |
| `latest` | Follow the latest sensor version. |
| `true` | Same as `stable`. |
| `false` | Off. Unset and empty also mean off. |

The API refuses any other value. Switching from `latest` to `stable` moves the
sensors down to the stable version. Automatic upgrades pause when the sensor
version is set by hand; setting the value again while it is already on resumes
them.

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

## audit

```bash
limacharlie audit list --start 1704067200 --end 1704153600
```

## See Also

- [Organization SDK](../sdk/organization.md) — Organization Python class
- [Other SDK Classes](../sdk/other-classes.md) — Users, Billing, and more
- [Authentication](../authentication.md) — Credential setup
