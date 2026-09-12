# Strelka

## Strelka Extension Pricing

Note that usage of ext-strelka will incur usage of Artifact Exporting (applied to processed artifacts at a rate of $0.02/GB) as well as webhook data received in LimaCharlie and the related costs on top of the ext-strelka specific pricing.

[Strelka](https://github.com/target/strelka) is a real-time file scanning system used for threat hunting, threat detection, and incident response.

The Strelka extension receives files using Artifacts by specifying an `artifact_id` in the `run_on` request. The extension will then process the file and return the results to the caller as well as send the results to its related Sensor.

## Configuration

Example  rule that processes all Artifacts ingested with the type `zeek-extract`:

**Detect:**

```yaml
event: ingest
op: is
path: routing/log_type
target: artifact_event
value: zeek-extract
```

**Respond:**

```yaml
- action: extension request
  extension action: run_on
  extension name: ext-strelka
  extension request:
    artifact_id: '{{ .routing.log_id }}'
```

## Usage

If you use the LimaCharlie [Zeek](zeek.md) extension, a good use case would be to trigger a Zeek analysis upon ingestion of a PCAP artifact, which will generate the necessary Zeek artifacts to trigger the Strelka extension in the above example.

**Detect:**

```yaml
op: exists
event: ingest
artifact type: pcap
path: /
target: artifact_event
```

**Respond:**

```yaml
- action: extension request
  extension action: run_on
  extension name: ext-zeek
  extension request:
    artifact_id: '{{ .routing.log_id }}'
    retention: 30
```
