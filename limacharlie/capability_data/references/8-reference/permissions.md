# Reference: Permissions

## Overview

LimaCharlie uses a granular permission system that controls access to all platform functionality. Permissions are applied through User accounts, API Keys, or Groups and follow a hierarchical naming convention: `category`.`action`

## Permission Structure

### Naming Convention

- **Category**: Functional area (e.g. sensor, org, dr)
- **Action**: Operation type (e.g. get, list, set, del, ctrl)

## Core Permissions

### Organization Management

| Permission | Description |
| --- | --- |
| org.get | View organization information |
| org.del | Delete organization |
| org.set\_quota | Manage organization quotas |
| org.conf.get | View organization configuration |
| org.conf.set | Modify organization configuration |

### User & Access Control

| Permission | Description |
| --- | --- |
| apikey.ctrl | Create, delete, and modify API keys |
| user.ctrl | Manage user accounts and permissions |
| billing.ctrl | Access and modify billing information |

### Sensor Management

| Permission | Description |
| --- | --- |
| sensor.list | List all sensors in organization |
| sensor.get | View detailed sensor information |
| sensor.task | Send commands and tasks to sensors |
| sensor.del | Delete sensors |
| sensor.tag | Manage sensor tags and labels |

### Installation Keys

| Permission | Description |
| --- | --- |
| ikey.list | List installation keys |
| ikey.set | Create new installation keys |
| ikey.del | Delete installation keys |

### Detection & Response (D&R)

#### General D&R Rules

| Permission | Description |
| --- | --- |
| dr.list | List general detection rules |
| dr.set | Create and modify general detection rules |
| dr.del | Delete general detection rules |

#### Managed D&R Rules

| Permission | Description |
| --- | --- |
| dr.list.managed | List managed detection rules |
| dr.set.managed | Create and modify managed detection rules |
| dr.del.managed | Delete managed detection rules |

#### Service D&R Rules

| Permission | Description |
| --- | --- |
| dr.list.service | List service detection rules |
| dr.set.service | Create and modify service detection rules |
| dr.del.service | Delete service detection rules |

#### False Positives

| Permission | Description |
| --- | --- |
| fp.ctrl | Manage false positive suppressions |

## Configuration Management (Hive)

### Secrets

| Permission | Description |
| --- | --- |
| secret.get | Access secret values |
| secret.set | Create and modify secrets |
| secret.del | Delete secrets |
| secret.get.mtd | View secret metadata only |
| secret.set.mtd | Modify secret metadata only |

### Lookups

| Permission | Description |
| --- | --- |
| lookup.get | Access lookup tables |
| lookup.set | Create and modify lookup tables |
| lookup.del | Delete lookup tables |
| lookup.get.mtd | View lookup metadata only |
| lookup.set.mtd | Modify lookup metadata only |

### Models

| Permission | Description |
| --- | --- |
| model.get | Access behavioral models |
| model.set | Create and modify behavioral models |
| model.del | Delete behavioral models |
| model.get.mtd | View model metadata only |
| model.set.mtd | Modify model metadata only |

### Queries

| Permission | Description |
| --- | --- |
| query.get | Access saved queries |
| query.set | Create and modify saved queries |
| query.del | Delete saved queries |
| query.get.mtd | View query metadata only |
| query.set.mtd | Modify query metadata only |

### YARA Rules

| Permission | Description |
| --- | --- |
| yara.get | Access YARA rules |
| yara.set | Create and modify YARA rules |
| yara.del | Delete YARA rules |
| yara.get.mtd | View YARA rule metadata only |
| yara.set.mtd | Modify YARA rule metadata only |

### AI Agents

| Permission | Description |
| --- | --- |
| ai\_agent.get | Access AI agent configurations |
| ai\_agent.set | Create and modify AI agents |
| ai\_agent.del | Delete AI agents |
| ai\_agent.get.mtd | View AI agent metadata only |
| ai\_agent.set.mtd | Modify AI agent metadata only |

### Cloud Sensors

| Permission | Description |
| --- | --- |
| cloudsensor.get | Access cloud sensor configurations |
| cloudsensor.set | Create and modify cloud sensor configurations |
| cloudsensor.del | Delete cloud sensor configurations |
| cloudsensor.get.mtd | View cloud sensor metadata only |
| cloudsensor.set.mtd | Modify cloud sensor metadata only |

### Playbooks

| Permission | Description |
| --- | --- |
| playbook.get | Access playbooks |
| playbook.set | Create and modify playbooks |
| playbook.del | Delete playbooks |
| playbook.get.mtd | View playbook metadata only |
| playbook.set.mtd | Modify playbook metadata only |

### SOPs

| Permission | Description |
| --- | --- |
| sop.get | Access Standard Operating Procedures |
| sop.set | Create and modify SOPs |
| sop.del | Delete SOPs |
| sop.get.mtd | View SOP metadata only |
| sop.set.mtd | Modify SOP metadata only |

### Organization Notes

| Permission | Description |
| --- | --- |
| org_notes.get | Access organization notes |
| org_notes.set | Create and modify organization notes |
| org_notes.del | Delete organization notes |
| org_notes.get.mtd | View organization note metadata only |
| org_notes.set.mtd | Modify organization note metadata only |

### Apps

| Permission | Description |
| --- | --- |
| app.get | Access app records |
| app.set | Create and modify app records |
| app.del | Delete app records |
| app.get.mtd | View app metadata only |
| app.set.mtd | Modify app metadata only |

### External Adapters

| Permission | Description |
| --- | --- |
| externaladapter.get | Access external adapter configurations |
| externaladapter.set | Create and modify external adapters |
| externaladapter.del | Delete external adapter configurations |
| externaladapter.get.mtd | View external adapter metadata only |
| externaladapter.set.mtd | Modify external adapter metadata only |

## Extensions & Services

### Extensions

| Permission | Description |
| --- | --- |
| ext.request | Request extension actions |
| ext.conf.get | View extension configurations |
| ext.conf.set | Modify extension configurations |
| ext.conf.del | Delete extension configurations |
| ext.conf.get.mtd | View extension metadata only |
| ext.conf.set.mtd | Modify extension metadata only |
| ext.sub | Subscribe to extension services |
| ext.sub.mtd | Manage extension subscription metadata |

### Replicant Services

| Permission | Description |
| --- | --- |
| replicant.get | View replicant service status |
| replicant.ctrl | Control replicant services |

## Data Access & Analytics

### Insight & Detections

| Permission | Description |
| --- | --- |
| insight.list | List available insights |
| insight.ctrl | Control insight generation |
| insight.del | Delete insights |
| insight.evt.get | Access detailed event data |
| insight.evt.get.simple | Access simplified event data |
| insight.det.get | Access detection details |
| insight.stat | Access insight statistics |

### Audit & Logging

| Permission | Description |
| --- | --- |
| audit.get | Access audit logs and error messages |
| audit.set | Create audit logs entries |

## Operations Management

### Jobs

| Permission | Description |
| --- | --- |
| job.get | View job status and results |
| job.ctrl | Create and schedule jobs |

### Outputs

| Permission | Description |
| --- | --- |
| output.list | List output configurations |
| output.set | Create and modify output configurations |
| output.del | Delete output configurations |

### Payloads

| Permission | Description |
| --- | --- |
| payload.ctrl | Manage sensor payloads |

### Module Management

| Permission | Description |
| --- | --- |
| module.update | Update sensor modules |

### Ingestion

| Permission | Description |
| --- | --- |
| ingestkey.ctrl | Manage data ingestion keys |

## Permission Application

Permissions can be applied through:

1. **User Accounts**: Direct assignment to individual users
2. **API Keys**: Embedded in API key configurations for programmatic access
3. **Groups**: Assigned to groups, then inherited by group members

## Best Practices

1. **Principle of Least Privilege**: Grant only the minimum permissions required
2. **Use Groups**: Manage permissions through groups rather than individual assignments
3. **Regular Auditing**: Periodically review and audit permission assignments
4. **Separate Environments**: Use different permission sets for development, staging, and production
5. **API Key Management**: Rotate API keys regularly and scope them appropriately
