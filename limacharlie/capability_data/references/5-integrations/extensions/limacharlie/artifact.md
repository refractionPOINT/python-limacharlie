# Artifact

The Artifact Extension provides low-level collection capabilities which can be configured to run automatically via Detection & Response rules, Sensor collections, or pushed via REST API. When enabled, an Artifact Collection menu will be available within the LimaCharlie web UI.

> Billing for Artifacts
>
> Note that while the Artifact extension is free to enable, ingested artifacts do incur a charge. Please refer to pricing details to confirm Artifact ingestion and retention costs.

## Enabling the Artifact Extension

To enable the Artifact extension, navigate to the [Artifact extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-artifact) in the marketplace. Select the Organization you wish to enable the extension for, and select **Subscribe.**

![artifact 1](../../../assets/images/artifact-1.png)

After clicking **Subscribe**, the Artifact extension should be available almost immediately.

> Note that the Artifact extension first requires enabling the [Reliable Tasking extension](reliable-tasking.md).

## Using the Artifact Extension

When enabled, you will see an **Artifact Collection** option under **Sensors** menu for the respective organization.

![artifact 2](../../../assets/images/artifact-2.png)

Within the Artifact Collection page, you can configure:

- Artifact collection rules for files.
- Artifact collection rules to stream Windows Event Log (WEL) events.
- Artifact collection rules to stream Mac Unified Log (MUL) events.
- PCAP capture rules to capture network traffic (Only available on Linux)

The following screenshot provides examples of capturing Windows Security and Sysmon Windows Event Logs via Artifact Collection. Rather than using an Adapter, capturing WEL events via the `wel://` pattern adds the corresponding events to the sensor telemetry, creating a real-time stream of Windows Event Log data. However, you can also specify the pattern to collect the specific `.evtx` files.

More information on Artifact collections can be found below.

![artifact 3](../../../assets/images/artifact-3.png)
