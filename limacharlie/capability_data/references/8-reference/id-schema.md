# Reference: ID Schema

## Agent IDs

An AgentID is a 5-tuple that completely describes a Sensor, while a Sensor ID is the smallest single unique identifier that can identify a sensor.

The AgentID's components look like this: `OID.IID.SID.PLATFORM.ARCHITECTURE`.

For all components, a value of `0` indicates a wildcard that matches any value when comparing AgentIDs as masks.

## Architecture

The architecture is an 8 bit integer that identifies the exact architecture the sensor runs on. The important values are:

- `1`: 32 bit (`x86`)
- `2`: 64 bit (`x64`)
- `3`: ARM (`arm`)
- `4`: ARM64 (`arm64`)
- `5`: Alpine 64 (`alpine64`)
- `6`: Chrome (`chromium`)
- `7`: Wireguard (`wireguard`)
- `8`: ARML (`arml`)
- `9`: lc-adapter (`usp_adapter`)

Operating System Specifics

Looking for more detailed version information on a specific operating system? Check out these vendor guides:

- [Microsoft Windows](https://learn.microsoft.com/en-us/windows/win32/sysinfo/operating-system-version)
- [RHEL](https://access.redhat.com/articles/3078)
- [Ubuntu](https://wiki.ubuntu.com/Releases)

## Device IDs

Given the breadth of platforms supported by LimaCharlie, it is not unusual for one "device" (laptop, server, mobile etc) to be visible from multiple sensors. A basic example of this might be:

- We have a laptop, running macOS as its operating system and running a macOS sensor
- The laptop is also running a Windows Virtual Machine, running a Windows sensor

In this example, we're dealing with one piece of hardware, but two different sensors.

To help provide a holistic view of activity, LimaCharlie introduces the concept of a Device ID. This ID is mostly visible in the sensor's basic info and in the `routing` component of sensor events under the name `did` (Device ID).

This Device ID is automatically generated and assigned by LimaCharlie using correlation of specific low level events common to all the sensors. This means that if two sensors share a `did: 1234-5678...` ID, it means they are either on the same device or at least share the same visibility (they see the same activity from two angles).

## Installer ID

The Installer ID (IID) is a UUID that identifies a unique Installation Key. This allows us to cycle installation keys and repudiate old keys, in the event the key gets leaked.

## Organization ID

The Organization ID (OID) is a UUID which identifies a unique organization.

## Platform

The platform is a 32-bit integer (in its hex format) which identifies the exact platform the sensor runs on. Sensor telemetry will display the `plat` value in decimal format. Although it is structured with a major and minor platform, the important values are:

| Hex ID     | Decimal    | API Name                     | Platform Name                |
|------------|------------|------------------------------|------------------------------|
| 0x01000000 | 16777216   | crowdstrike                  | CrowdStrike                  |
| 0x02000000 | 33554432   | xml                          | XML                          |
| 0x03000000 | 50331648   | wel                          | Windows Event Logs           |
| 0x04000000 | 67108864   | msdefender                   | Microsoft Defender           |
| 0x05000000 | 83886080   | duo                          | Duo                          |
| 0x06000000 | 100663296  | okta                         | Okta                         |
| 0x07000000 | 117440512  | sentinel_one                 | SentinelOne                  |
| 0x08000000 | 134217728  | github                       | GitHub                       |
| 0x09000000 | 150994944  | slack                        | Slack                        |
| 0x0A000000 | 167772160  | cef                          | Common Event Format (CEF)    |
| 0x0B000000 | 184549376  | lc_event                     | LimaCharlie Events           |
| 0x0C000000 | 201326592  | azure_ad                     | Azure Active Directory       |
| 0x0D000000 | 218103808  | azure_monitor                | Azure Monitor                |
| 0x0E000000 | 234881024  | canary_token                 | Canary Token                 |
| 0x0F000000 | 251658240  | guard_duty                   | Guard Duty                   |
| 0x11000000 | 285212672  | itglue                       | IT Glue                      |
| 0x12000000 | 301989888  | k8s_pods                     | Kubernetes Pods              |
| 0x13000000 | 318767104  | zeek                         | Zeek                         |
| 0x14000000 | 335544320  | mac_unified_logging          | Macos Unified Logging        |
| 0x15000000 | 352321536  | azure_event_hub_namespace    | Azure Event Hub Namespace    |
| 0x16000000 | 369098752  | azure_key_vault              | Azure Key Vault              |
| 0x17000000 | 385875968  | azure_kubernetes_service     | Azure Kubernetes Service     |
| 0x18000000 | 402653184  | azure_network_security_group | Azure Network Security Group |
| 0x19000000 | 419430400  | azure_sql_audit              | Azure SQL Audit              |
| 0x1A000000 | 436207616  | email                        | Email                        |
| 0x1B000000 | 452984832  | fortigate                    | Fortigate                    |
| 0x1C000000 | 469762048  | trend_worryfree              | Trend Worry Free             |
| 0x1D000000 | 486539264  | netscaler                    | Netscaler                    |
| 0x1E000000 | 503316480  | paloalto_fw                  | Palo Alto Firewall           |
| 0x1F000000 | 520093696  | iis                          | Internet Information Services|
| 0x21000000 | 553648128  | hubspot                      | HubSpot                      |
| 0x22000000 | 570425344  | zendesk                      | Zendesk                      |
| 0x23000000 | 587202560  | pandadoc                     | PandaDoc                     |
| 0x24000000 | 603979776  | falconcloud                  | FalconCloud                  |
| 0x25000000 | 620756992  | mimecast                     | Mimecast                     |
| 0x26000000 | 637534208  | sublime                      | Sublime                      |
| 0x27000000 | 654311424  | box                          | Box                          |
| 0x28000000 | 671088640  | cylance                      | Cylance                      |
| 0x29000000 | 687865856  | proofpoint                   | Proofpoint                   |
| 0x2A000000 | 704643072  | entraid                      | EntraID                      |
| 0x2B000000 | 721420288  | wiz                          | Wiz                          |
| 0x2C000000 | 738197504  | bitwarden                    | Bitwarden                    |
| 0x2D000000 | 754974720  | trend_micro                  | Trend Micro                  |
| 0x2E000000 | 771751936  | otel                         | OpenTelemetry                |
| 0x2F000000 | 788529152  | cortex_xdr                   | Cortex XDR                   |
| 0x31000000 | 822083584  | harmony                      | Check Point Harmony          |
| 0x32000000 | 838860800  | threatlocker                 | ThreatLocker                 |
| 0x33000000 | 855638016  | halopsa                      | HaloPSA                      |
| 0x10000000 | 268435456  | windows                      | Windows                      |
| 0x20000000 | 536870912  | linux                        | Linux                        |
| 0x30000000 | 805306368  | macos                        | MacOS                        |
| 0x40000000 | 1073741824 | ios                          | iOS                          |
| 0x50000000 | 1342177280 | android                      | Android                      |
| 0x60000000 | 1610612736 | chrome                       | ChromeOS                     |
| 0x70000000 | 1879048192 | vpn                          | VPN                          |
| 0x80000000 | 2147483648 | text                         | Text (external telemetry)    |
| 0x90000000 | 2415919104 | json                         | JSON (external telemetry)    |
| 0xA0000000 | 2684354560 | gcp                          | GCP (external telemetry)     |
| 0xB0000000 | 2952790016 | aws                          | AWS (external telemetry)     |
| 0xC0000000 | 3221225472 | carbon_black                 | VMWare Carbon Black          |
| 0xD0000000 | 3489660928 | 1password                    | 1Password                    |
| 0xE0000000 | 3758096384 | office365                    | Microsoft/Office 365         |
| 0xF0000000 | 4026531840 | sophos                       | Sophos                       |

Tip: If you're writing a  rule to target a specific platform, consider using the `is platform` operator instead of the decimal value for easier readability.

## Sensor ID

The Sensor ID (SID) is a UUID that identifies a unique sensor.

Similar to agents, Sensors send telemetry to the LimaCharlie platform in the form of EDR telemetry or forwarded logs. Sensors are offered as a scalable, serverless solution for securely connecting endpoints of an organization to the cloud.

In LimaCharlie, a Sensor ID is a unique identifier assigned to each deployed endpoint agent (sensor). It distinguishes individual sensors across an organization's infrastructure, allowing LimaCharlie to track, manage, and communicate with each endpoint. The Sensor ID is critical for operations such as sending commands, collecting telemetry, and monitoring activity, ensuring that actions and data are accurately linked to specific devices or endpoints.

Installation keys are Base64-encoded strings provided to Sensors and Adapters in order to associate them with the correct Organization. Installation keys are created per-organization and offer a way to label and control your deployment population.

In LimaCharlie, an Organization ID is a unique identifier assigned to each tenant or customer account. It distinguishes different organizations within the platform, enabling LimaCharlie to manage resources, permissions, and data segregation securely. The Organization ID ensures that all telemetry, configurations, and operations are kept isolated and specific to each organization, allowing for multi-tenant support and clear separation between different customer environments.

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.

In LimaCharlie, an Organization ID (OID) is a unique identifier assigned to each tenant or customer account. It distinguishes different organizations within the platform, enabling LimaCharlie to manage resources, permissions, and data segregation securely. The Organization ID ensures that all telemetry, configurations, and operations are kept isolated and specific to each organization, allowing for multi-tenant support and clear separation between different customer environments.

In LimaCharlie, a Sensor ID (SID) is a unique identifier assigned to each deployed endpoint agent (sensor). It distinguishes individual sensors across an organization's infrastructure, allowing LimaCharlie to track, manage, and communicate with each endpoint. The Sensor ID is critical for operations such as sending commands, collecting telemetry, and monitoring activity, ensuring that actions and data are accurately linked to specific devices or endpoints.
