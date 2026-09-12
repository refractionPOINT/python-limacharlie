# Payload Manager

[Payloads](../../../2-sensors-deployment/endpoint-agent/payloads.md), such as scripts, pre-built binaries, or other files, can be deployed to LimaCharlie sensors for any reason necessary.

One method of adding payloads to an Organization is via the web UI on the payloads screen. This is suitable for ad-hoc payload needs, however does not scale past a handful of payloads, or for multiple organizations requiring access the same payload(s).

The payload manager allows you to create, maintain, and automatically create/update payloads within your organization(s). Furthermore, payload configurations can be saved and utilized across multiple organizations using LimaCharlie's Infrastructure as Code capabilities.

Payloads added in the payload manager will be synced once every 24 hours per org.

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.

Infrastructure as Code (IaC) automates the management and provisioning of IT infrastructure using code, making it easier to scale, maintain, and deploy resources consistently. In LimaCharlie, IaC allows security teams to deploy and manage sensors, rules, and other security infrastructure programmatically, ensuring streamlined, repeatable configurations and faster response times, while maintaining infrastructure-as-code best practices in cybersecurity operations.
