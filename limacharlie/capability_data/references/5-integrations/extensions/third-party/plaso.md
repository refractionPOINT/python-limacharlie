# Plaso

Plaso Extension Pricing

While it is free to enable the Plaso extension, pricing is applied to both the original downloaded artifact and the processed (Plaso) artifacts -- $0.02/GB for the original downloaded artifact, and $1.0/GB for the generation of the processed artifacts.

## About

[Plaso](https://plaso.readthedocs.io/) is a Python-based suite of tools used for creation of analysis timelines from forensic artifacts acquired from an endpoint.

These timelines are invaluable tools for digital forensic investigators and analysts, enabling them to effectively correlate the vast quantities of information encountered in logs and various forensic artifacts encountered in an intrusion investigation.

The primary tools in the Plaso suite used for this process are [log2timeline](https://plaso.readthedocs.io/en/latest/sources/user/Using-log2timeline.html), [psort](https://plaso.readthedocs.io/en/latest/sources/user/Using-psort.html), and [psteal](https://plaso.readthedocs.io/en/latest/sources/user/Using-psteal.html).

- `log2timeline` - bulk forensic artifact parser
- `psort` - builds timelines based on output from `log2timeline`
- `psteal` - Simply a wrapper for `log2timeline` and `psort`

The `ext-plaso` extension within LimaCharlie allows you to run `log2timeline` and `psort` (using the `psteal` wrapper) against artifacts obtained from an endpoint, such as event logs, registry hives, and various other forensic artifacts. When executed, Plaso will parse and extract information from all acquired evidence artifacts that it has support for. See the [Plaso parsers and plugins reference](https://plaso.readthedocs.io/en/latest/sources/user/Parsers-and-plugins.html) for the full list of supported parsers.

## Extension Configuration

Long Execution Times

Note that it can take **several minutes** for the plaso generation to complete for larger triage collections, but once it finishes you will see the results in the `ext-plaso` Sensor timeline, as well as the uploaded artifacts on the Artifacts page.

The `ext-plaso` extension runs `psteal` (`log2timeline` + `psort`) against the acquired evidence using the following commands:

1. ```bash
   psteal.py --source /path/to/artifact -o dynamic --storage-file $artifact_id.plaso -w $artifact_id.csv
   ```

Upon running `psteal.py`, a `.plaso` file and a `.csv` file are generated. They will be uploaded as LimaCharlie artifacts.

- Resulting `.plaso` file contains the raw output of `log2timeline.py`
- Resulting `.csv` file contains the CSV formatted version of the `.plaso` file contents

1. ```bash
   pinfo.py $artifact_id.plaso -w $artifact_id_pinfo.json --output_format json
   ```

After `psteal.py` runs, information is gathered from the resulting `.plaso` file using the `pinfo.py` utility and pushed into the `ext-plaso` sensor timeline as a `pinfo` event. This event provides a detailed summary with metrics of the processing that occurred, as well as any relevant errors you should be aware of.

The following events will be pushed to the `ext-plaso` sensor timeline:

- `job_queued`: indicates that `ext-plaso` has received and queued a request to process data
- `job_started`: indicates that `ext-plaso` has started processing the data
- `job_failed`: indicates that the processing job failed; the `error` field contains the reason
- `pinfo`: contains the `pinfo.py` output summarizing the results of the plaso file generation
- `plaso`: contains the `artifact_id` of the plaso file that was uploaded to LimaCharlie
- `csv`: contains the `artifact_id` of the CSV file that was uploaded to LimaCharlie; when timeline ingestion is enabled, it also reports `events_sent_to_timeline` and `rows_skipped`
- `plaso_event`: one event per row of the generated timeline, only when timeline ingestion is enabled (see [Timeline Ingestion](#timeline-ingestion))

## Timeline Ingestion

By default, the generated timeline is only available as downloadable `.plaso` and `.csv` artifacts. Setting the optional `send_to_timeline` parameter to `true` on a `generate` request additionally ingests every row of the generated CSV timeline as an individual `plaso_event` event on the `ext-plaso` sensor timeline.

Each `plaso_event` carries the timeline columns under `results`, including the forensic timestamp (`results/datetime`), the plaso parser that produced the entry, and the event message. Rows are ingested in chronological order (as sorted by `psort`), making the full forensic timeline searchable with LCQL and usable in D&R rules. Combined with the automation below, this enables an end-to-end triage workflow — collection, timeline generation, and detection — entirely within LimaCharlie.

Ingestion Volume

A Plaso timeline for a full triage collection can contain hundreds of thousands to millions of rows. Enabling `send_to_timeline` ingests all of them as events, which is billed as regular event ingestion volume.

Rows of the CSV that cannot be parsed are skipped rather than failing the job; the final `csv` status event reports how many events were ingested (`events_sent_to_timeline`) and how many rows were skipped (`rows_skipped`).

## Usage & Automation

LimaCharlie can automatically kick off evidence processing with Plaso based off of the artifact ID provided in a  rule action, or you can run it manually via the extension.

### Velociraptor Triage Acquisition Processing

If you use the LimaCharlie [Velociraptor](velociraptor.md) extension, a good use case of `ext-plaso` would be to trigger Plaso evidence processing upon ingestion of a Velociraptor KAPE files artifact collection.

1. Configure a D&R rule to watch for Velociraptor collection events upon ingestion, and then trigger the Plaso extension:

   **Detect:**

   ```yaml
   op: and
   target: artifact_event
   rules:
       - op: is
         path: routing/log_type
         value: velociraptor
       - op: is
         not: true
         path: routing/event_type
         value: export_complete
   ```

   **Respond:**

   ```yaml
   - action: extension request
     extension action: generate
     extension name: ext-plaso
     extension request:
         artifact_id: '{{ .routing.log_id }}'
         send_to_timeline: true
   ```

   The `send_to_timeline` parameter is optional; when set to `true`, the resulting timeline rows are also ingested as `plaso_event` events (see [Timeline Ingestion](#timeline-ingestion)).

2. Launch a `Windows.KapeFiles.Targets` artifact collection in the LimaCharlie Velociraptor extension. This instructs Velociraptor to gather all endpoint artifacts defined in [this KAPE Target file](https://github.com/EricZimmerman/KapeFiles/blob/master/Targets/Compound/KapeTriage.tkape).

   **Argument options:**

   - `EventLogs=Y` - EventLogs only, quicker processing time for proof of concept
   - `KapeTriage=Y` - full [KapeTriage](https://github.com/EricZimmerman/KapeFiles/blob/master/Targets/Compound/KapeTriage.tkape) files collection ![velociraptor ext 3](../../../assets/images/velociraptor-ext-3.png)
3. Once Velociraptor collects, zips, and uploads the evidence, the previously created D&R rule will send the triage `.zip` to `ext-plaso` for processing. Watch the `ext-plaso` sensor timeline for status and the Artifacts page for the resulting `.plaso` & `.csv` output files. See [Working with the Output](#working-with-the-output).

### MFT Processing

If you use the LimaCharlie [Dumper](../limacharlie/dumper.md) extension, a good use case of `ext-plaso` would be to trigger Plaso evidence processing upon ingestion of a MFT CSV artifact.

1. Configure a D&R rule to watch for MFT collection events upon ingestion, and then trigger the Plaso extension:

   **Detect:**

   ```yaml
   op: and
   target: artifact_event
   rules:
       - op: is
         path: routing/log_type
         value: mftcsv
       - op: is
         not: true
         path: routing/event_type
         value: export_complete
   ```

   **Respond:**

   ```yaml
   - action: extension request
     extension action: generate
     extension name: ext-plaso
     extension request:
         artifact_id: '{{ .routing.log_id }}'
   ```

2. Launch an MFT dump in the LimaCharlie Dumper extension.
   ![plaso ext 1](../../../assets/images/plaso-ext-1.png)
3. Once dumper is complete and uploads the evidence, the previously created D&R rule will send the zipped MFT CSV to `ext-plaso` for processing. Watch the `ext-plaso` sensor timeline for status and the Artifacts page for the resulting `.plaso` & `.csv` output files. See [Working with the Output](#working-with-the-output).

## Working with the Output

Running the extension generates the following useful outputs:

![image.png](../../../assets/images/image(254).png)

- `pinfo` on `ext-plaso` sensor timeline
   First and foremost, after the completion of a processing job by `ext-plaso`, it is highly encouraged to analyze the resulting `pinfo` event on the `ext-plaso` sensor timeline. This event provides a detailed summary with metrics of the processing that occurred, as well as any relevant errors you should be aware of.

  - Pay close attention to fields such as `warnings_by_parser` or `warnings_by_path_spec` which may reveal parser errors that were encountered.
  - Sample output of `pinfo` showing counts of parsed artifacts nested under `storage_counters` -- this provides insight as to which, and how many events will be present in your CSV timeline.

```text
"amcache": 986,
"appcompatcache": 4096,
"bagmru": 29,
"chrome_27_history": 29,
"chrome_66_cookies": 246,
"explorer_mountpoints2": 2,
"explorer_programscache": 1,
"filestat": 3495,
"lnk": 160,
"mft": 4790977,
"mrulist_string": 2,
"mrulistex_shell_item_list": 3,
"mrulistex_string": 5,
"mrulistex_string_and_shell_item": 5,
"mrulistex_string_and_shell_item_list": 1,
"msie_webcache": 143,
"msie_zone": 60,
"networks": 4,
"olecf_automatic_destinations": 37,
"olecf_default": 5,
"recycle_bin": 3,
"shell_items": 297,
"total": 5840430,
"user_access_logging": 34,
"userassist": 44,
"utmp": 13,
"windows_boot_execute": 8,
"windows_run": 10,
"windows_sam_users": 16,
"windows_services": 2004,
"windows_shutdown": 8,
"windows_task_cache": 835,
"windows_timezone": 4,
"windows_typed_urls": 3,
"windows_version": 6,
"winevtx": 382674,
"winlogon": 8,
"winreg_default": 654177
```

### Downloadable Artifacts

![image.png](../../../assets/images/image(253).png)

- `plaso` artifact
   The downloadable `.plaso` file contains the raw output of `log2timeline.py` and can be [imported into Timesketch](https://timesketch.org/guides/user/upload-data/) as a timeline.
- `csv` artifact
   The downloadable `.csv` file can be easily viewed in any CSV viewer, but a highly recommended tool for this is [Timeline Explorer](https://ericzimmerman.github.io/) from Eric Zimmerman.

### Timeline Events

If the request was made with `send_to_timeline: true`, the full timeline is also available as `plaso_event` events on the `ext-plaso` sensor timeline, where it can be explored chronologically, queried with LCQL, and matched by D&R rules. See [Timeline Ingestion](#timeline-ingestion).
