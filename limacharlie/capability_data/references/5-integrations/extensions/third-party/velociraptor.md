# Velociraptor

## Overview

[Velociraptor](https://github.com/Velocidex/Velociraptor) is an open source endpoint visibility tool that includes power digital forensic, incident response, and incident triage capabilities. LimaCharlie can be used to deploy Velociraptor at scale, allowing for easy artifact collection and incident analysis.

The interface defines 2 main actions:

1. **Show Artifact** - allows you to inspect the VQL artifacts available for collection
2. **Collect Artifact** - allows you to run an artifact collection on one or more endpoints

### Show Artifact

Simply choose an artifact from the list to inspect it's contents.

![velociraptor ext 1](../../../assets/images/velociraptor-ext-1.png)

Result of the action

![velociraptor ext 2](../../../assets/images/velociraptor-ext-2.png)

### Collect Artifact

This allows you to collect one or more Velociraptor [Artifacts](https://docs.velociraptor.app/artifact_references/) from one or more endpoints via the Endpoint Agent.
![velociraptor 3](../../../assets/images/velociraptor-3.png)

Velociraptor will generate a ZIP file with all collected data, which is automatically ingested into LimaCharlie's Artifact system for download.

#### Arguments

- **Artifacts** - Select one or more Velociraptor artifacts you wish to collect
- **Sensor Selector** - Select either a single sensor by selecting it's Sensor ID from the dropdown or use a [Sensor Selector Expression](../../../8-reference/sensor-selector-expressions.md) to cast a wider net such as `plat==windows`
- **Arguments (optional)** - See below
- **Collection Seconds (optional)** - Define how long (in seconds) the Extension will wait for a targeted endpoint to come online and be processed for collection.
- **Retention Days (optional)** - Define how long the collected artifact will be retained by the platform.
- **Ignore SSL Errors (optional)** - Tells the endpoint to ignore SSL errors while running and collecting. This can be useful if the endpoint is behind a MITM proxy or firewall performing SSL interception.

##### Arguments (optional)

These are optional arguments (or parameters) passed directly to the Velociraptor Artifact. Arguments use the format `"Key=[\"value\"]"` for list parameters and `"Key=Y"` for boolean parameters.

For example, to run a [Linux.Triage.UAC](https://triage.velocidex.com/docs/linux.triage.uac/) collection targeting all categories, specify:

```text
"Targets=[\"_All\"]"
```

If `_All` returns more data than needed, you can define a single target instead. See the [UAC target reference](https://triage.velocidex.com/docs/linux.triage.uac/) for the full list of available options.

For [Windows.KapeFiles.Targets](https://github.com/Velocidex/velociraptor/blob/master/artifacts/definitions/Windows/KapeFiles/Targets.yaml), you can use `"HighLevelTargets=[\"_KapeTriage\"]"`.

## Monitoring Collections

You are able to track Velociraptor hunts by viewing the Timeline for the `ext-velociraptor` sensor.

![velociraptor ext 4](../../../assets/images/velociraptor-ext-4.png)

Once you see `artifact_uploaded` in the timeline, you can expect to find the artifact on the "Artifacts" screen.

![velociraptor ext 5](../../../assets/images/velociraptor-ext-5.png)

## Correlating a Collection (`job_id` to Artifact)

The `collect` action returns a `job_id`, for example:

```json
{
  "data": {
    "job_id": "bf24a49c-96e5-4c20-98a4-77f33bb7ce34",
    "n_sensors": 1
  }
}
```

This `job_id` is the extension's correlation key for the collection request. It is **not** a payload or artifact ID. The collected data is ingested as a LimaCharlie **Artifact**, which has its own artifact ID. There are two ways to map one to the other.

### 1. Webhook events (recommended for automation)

With an `ext-velociraptor` webhook output configured, the extension emits a lifecycle of events as a collection progresses, all carrying the `job_id`:

| Event | Key fields | When |
|-------|------------|------|
| `job_created` | `job_id`, `sids`, `request`, `inv_id` | Request accepted and tasks sent to sensors |
| `artifact_generated` / `artifact_timeout` / `artifact_failed` | `job_id`, `sid` | Collection produced on the endpoint (or timed out / failed) |
| `artifact_uploaded` / `upload_generated` | `job_id`, `sid` | Collection ZIP uploaded to the platform |
| `velociraptor_collection` | `job_id`, `sid`, `collection`, `collection_artifact`, `inv_id` | Collection ingested and parsed |
| `job_finished` | `job_id` | All taskings for the job are complete |

The `collection_artifact` field in the `velociraptor_collection` event is the LimaCharlie **artifact ID** for that `job_id`. This is the definitive `job_id` to artifact mapping.

### 2. Artifact `original_path`

The ingested collection ZIP is named so that its path ends in `_<job_id>.zip`. In the Artifact Collection — or in a D&R rule via `{{ .event.original_path }}` — you can match or filter artifacts by their `job_id`.

## Automating Collection Retrieval

Let's say you wanted to automatically fetch new Velociraptor collections and send somewhere else for storage/processing. This can be accomplished via  rules which watch for the artifact upload and send to a tailored output.

Example D&R rule

```yaml
# Detection
op: is
path: routing/log_type
target: artifact_event
value: velociraptor

# Response
- action: output
  name: artifacts-tailored
  suppression:
    is_global: false
    keys:
        - '{{ .event.original_path }}'
        - '{{ .routing.log_id }}'
    max_count: 1
    period: 1m
- action: report
  name: VR artifact ingested
```

To see how you could use something like this to automate post-processing of Velociraptor triage collections, check out this [open source example](https://github.com/shortstack/lcvr-to-timesketch) which sends KAPE Triage acquisitions to a webhook which then retrieves the collection for processing via [Plaso](https://github.com/log2timeline/plaso/) and into [Timesketch](https://github.com/google/timesketch).

To see how you can send Velociraptor data to BigQuery for further analysis, see this [tutorial](../../tutorials/velociraptor-bigquery.md).

## Using Velociraptor in D&R Rules

If you want to trigger a Velociraptor collection as a response to one of your detections, you can configure an extension request in the respond block of a rule.

This example will kick off the KAPE files Velociraptor artifact to collect event logs from the system involved in the detection.

```yaml
- action: extension request
  extension action: collect
  extension name: ext-velociraptor
  extension request:
    artifact_list: ['Windows.KapeFiles.Targets']
    sid: '{{ .routing.sid }}' # Use a sensor selector OR a sid, **not both**
    sensor_selector: '' # Use a sensor selector OR a sid, **not both**
    args: '{{ "EventLogs=Y" }}'
    collection_ttl: 3600 # 1 hour - collection_ttl is specified in seconds
    retention_ttl: 7 # retention_ttl is specified in days
    ignore_cert: false
```

### Migrating D&R Rule from legacy Service to new Extension

***Note: LimaCharlie has migrated from Services to Extensions. Legacy services are no longer supported.***

The [Python CLI](https://github.com/refractionPOINT/python-limacharlie) gives you a direct way to assess if any rules reference legacy Velociraptor service, preview the change and execute the conversion required in the rule "response".

Command line to preview Velociraptor rule conversion:

```bash
limacharlie extension convert_rules --name ext-velociraptor
```

A dry-run response (default) will display the rule name being changed, a JSON of the service request rule and a JSON of the incoming extension request change.

To execute the change in the rule, explicitly set `--dry-run` flag to `--no-dry-run`

Command line to execute Velociraptor rule conversion:

```bash
limacharlie extension convert_rules --name ext-velociraptor --no-dry-run
```
