# Google Workspace

[Google Workspace](https://workspace.google.com/) provides various communication, collaboration, and productivity applications for businesses of all sizes. [Google Workspace audit logs](https://cloud.google.com/logging/docs/audit/gsuite-audit-logging) provide data to help track "Who did what, where, an when?".

Google Workspace Audit logs can be ingested via a Google Cloud Platform, deploye as a cloud-to-cloud LimaCharlie Adapter. Events will be ingested and observed via the `gcp` platform.

## Adapter Deployment

Prior to ingesting Google Workspace Audit logs in LimaCharlie, you must first configure logs to be written to GCP. Afterwards, a cloud-to-cloud GCP Adapter can be deployed to ingest these events into LimaCharlie.

The following steps help prepare this:

### Step 1: Enable Platform Sharing in Google Workspace

In the Google Workspace admin console navigate to [Account -> Account Settings -> Legal and Compliance](https://admin.google.com/u/1/ac/companyprofile/legal)

Verify that under "Sharing options", `Google Cloud Platform Sharing Options` is set to Enabled.

For further details, refer to [Google's documentation on Audit logs for Google Workspace](https://cloud.google.com/logging/docs/audit/gsuite-audit-logging)

### Step 2: Verify logs appear in Google Cloud Platform

In the GCP Console go to the [Logs Explorer](https://console.cloud.google.com/logs/query).  Ensure you're at the organization level (and not in a particular folder).

From the Resources drop-down, choose `Audited Resource`, then press Apply.

You should see logging details related to Google Workspace, under the following log name(s):

`logName:admin.googleapis.com`

### Step 3: Create a cloud-to-cloud GCP Adapter

Once Google Workspace Audit logs are pushed to GCP, events can be ingested via either [Google Cloud Storage](google-cloud-storage.md) or [Google Cloud Pubsub](google-cloud-pubsub.md). Utilize the appropriate documentation to set up the desired Adapter.
