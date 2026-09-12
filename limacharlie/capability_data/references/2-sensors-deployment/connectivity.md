# Sensor Connectivity

The network connection required by the LimaCharlie Sensor is very simple. It requires a single TCP connection over port 443 to a specific domain, and optionally another destination for the [Artifact Collection](../4-data-queries/events/index.md) service.

The specific domains are listed in the Sensor Downloads section of your Organization's dashboard. They will vary depending on the datacenter you chose to create your organization in. To find yours, see the screenshots below.

Currently, web proxies are not supported, but since LimaCharlie requires a single connection to a single dedicated domain, it makes creating a single exception safe and easy.

## Proxy Tunneling

The LimaCharlie sensor supports unauthenticated proxy tunneling through [HTTP CONNECT](https://en.wikipedia.org/wiki/HTTP_tunnel).

This allows the LimaCharlie connection to go through the proxy in an opaque way (since the sensor does not support SSL interception).

To activate this feature, set the `LC_PROXY` environment variable to the DNS or hostname of the proxy to use. For example you could use: `LC_PROXY=proxy.corp.com:8080`.

### Windows

On Windows, you may use a light auto-detection of a globally-configured, unauthenticated proxy.

To enable this, set the same environment variable to the `-` value, like `LC_PROXY=-`. This will make the sensor query the registry key `HKLM\Software\Policies\Microsoft\Windows\CurrentVersion\Internet Settings\ProxyServer` and use its value as the proxy destination.

Also on Windows, in some cases the environment variable changes do not propagate to all processes in the expected way. Usually a reboot of the machine will fix it, but for machines that cannot be rebooted you have the ability to set a special value to the environment variable (deletion is usually problematic but setting a var works) that will disable the proxy specifically: `!`. So if you set the `LC_PROXY` variable to `!` (exclamation mark), the proxy will be disabled.

## Certificate Revocation Checks on Restricted Networks (Windows)

On Windows, when the sensor verifies code signatures it performs certificate revocation checks, which can attempt to reach CRL/OCSP endpoints over the network. On air-gapped or tightly restricted networks those lookups may stall or fail.

Setting the `LC_LOCAL_CACHE_ONLY_REVOCATION_CHECK` environment variable to `1` (or `true`) on the sensor process makes these revocation checks use only the local cache and never reach out to the network.

Similar to agents, Sensors send telemetry to the LimaCharlie platform in the form of EDR telemetry or forwarded logs. Sensors are offered as a scalable, serverless solution for securely connecting endpoints of an organization to the cloud.

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.
