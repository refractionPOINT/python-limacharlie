# OTX

AlienVault's Open Threat Exchange (OTX) is the "neighborhood watch of the global intelligence community." It enables private companies, independent security researchers, and government agencies to openly collaborate and share the latest information about emerging threats, attack methods, and malicious actors, promoting greater security across the entire community.

[More information about OTX](https://otx.alienvault.com/) is available on the AlienVault site.

## Enabling the OTX Extension

Before utilizing the OTX extension, you will need an AlienVault OTX API Key from your [AlienVault OTX account](https://otx.alienvault.com/).

To enable the OTX extension, navigate to the [OTX extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-otx). Select the Organization you wish to enable the extension for, and select **Subscribe**.

Once the extension is enabled, navigate to Extensions > OTX. You will need to provide your OTX API Key, which can be done directly in the form or via LimaCharlie's [Secrets Manager](../../../7-administration/config-hive/secrets.md).

Pulses will be synced to rules and lookups automatically every 3 hours.

## Using the OTX Extension

After providing a valid API key, the Extension will automatically create [Detection & Response rules](https://doc.limacharlie.io/docs/detection-and-response) for your organization. The OTX rules make use of the following events:

- Process Events
  - [CODE_IDENTITY](../../../8-reference/edr-events.md#code_identity)
  - [EXISTING_PROCESS](../../../8-reference/edr-events.md#existing_process)
  - [MEM_HANDLES_REP](../../../8-reference/edr-events.md#mem_handles_rep) (response to the [mem_handles](../../../8-reference/endpoint-commands.md) Sensor command)
  - [NEW_PROCESS](../../../8-reference/edr-events.md#new_process)
- Network Events
  - [DNS_REQUEST](../../../8-reference/edr-events.md#dns_request)
  - [HTTP_REQUEST](../../../8-reference/edr-events.md#http_request)
  - [NETWORK_CONNECTIONS](../../../8-reference/edr-events.md#network_connections)
  - [NEW_TCP4_CONNECTION](../../../8-reference/edr-events.md#new_tcp4_connection)
  - [NEW_TCP6_CONNECTION](../../../8-reference/edr-events.md#new_tcp6_connection)
  - [NEW_UDP4_CONNECTION](../../../8-reference/edr-events.md#new_udp4_connection)
  - [NEW_UDP6_CONNECTION](../../../8-reference/edr-events.md#new_udp6_connection)

Please ensure that the events you are interested in using with OTX lookups are enabled in the **Sensors >** Event Collection menu.
