# Google Cloud Storage

## Overview

This Adapter allows you to ingest files/blobs stored in Google Cloud Storage (GCS).

Note that this adapter operates as a sink by default, meaning it will "consume" files from the GCS bucket by deleting them once ingested.

## Configurations

Adapter Type: `gcs`

- `client_options`: see [common adapter configuration](../usage.md).
- `bucket_name`: the name of the bucket to ingest from.
- `service_account_creds`: the string version of the JSON credentials for a (Google) Service Account to use accessing the bucket.
- `prefix`: only ingest files with a given path prefix.
- `single_load`: if `true`, the adapter will not operate as a sink, it will ingest all files in the bucket once and will then exit.

### Infrastructure as Code Deployment

```python
sensor_type: "gcs"
gcs:
  bucket_name: "your-gcs-bucket-for-limacharlie-logs"
  service_account_creds: "hive://secret/gcs-service-account"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_GCS"
    platform: "json"
    sensor_seed_key: "gcs-log-processor"
    mapping:
      sensor_hostname_path: "resource.labels.instance_id"
      event_type_path: "logName"
      event_time_path: "timestamp"
    indexing: []
  # Optional configuration
  prefix: "security_logs/firewall/"  # Filter by path prefix
  parallel_fetch: 5                  # Parallel downloads
  single_load: false                 # Continuous processing
```

## API Doc

See the [official documentation](https://cloud.google.com/storage).
