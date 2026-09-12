# Dumper

The Dumper Extension provides the ability to do dumping of several forensic artifacts on Windows hosts. It supports a single action, which is to dump.

It supports multiple targets -- `memory` to dump the memory of the host, and `mft` to dump the MFT of the file system to CSV. The extension then automates the ingestion of the resulting dump (and dump metadata) to LimaCharlie's [Artifact Ingestion system](artifact.md) where it can be downloaded or analyzed, and where you can create rules to automate detections of characteristics of those dumps.

## Usage

When enabled, dumper will be added to the Extensions view inside your Organization. It will accept the following parameters:

- `sid` - a Sensor ID for the host to perform the memory dump
- `target` - memory or mft
- `retention` - the number of days the memory dump should be retained for (default is 30)
- `ignore_cert` - ignore cert errors for payload and collection purposes (default `false`)

Upon submission of a request, the extension will perform a full memory dump of a host and upload the resulting dumps to LimaCharlie's artifact ingestion system and delete the local dumps afterwards.

Dumper requests can also be made via D&R rules. Here is is example of a D&R rule action that makes a request to Dumper:

```yaml
- action: extension request
  extension name: ext-dumper
  extension action: request_dump
  extension request:
    target: memory
    sid: <<routing.sid>>
    retention: 30 #default 30
    ignore_cert: true # default false
```

**Notes:**

The dumper extension does not currently validate that the host has enough available disc space for the memory dump. Although the dumper extension is free, the resulting memory dumps uploaded to LimaCharlie are subject to external logs pricing. This add-on relies on other paid resources (payloads) billed based on usage.
