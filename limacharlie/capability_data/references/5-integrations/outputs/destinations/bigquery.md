# Google Cloud BigQuery

Output events and detections to a Google Cloud BigQuery Table.

For a practical use case of this output, see this [tutorial on pushing Velociraptor data to BigQuery](../../tutorials/velociraptor-bigquery.md).

- `schema`: describes the column names, data types, and other information; should match the text-formatted schema from bigquery
- `table`: the table name where to send data.
- `dataset`: the dataset name where to send data.
- `project`: the project name where to send the data.
- `secret_key`: the secret json key identifying a service account.
- `sec_per_file`: the number of seconds after which a batch of data is loaded.
- `custom_transform`: should align with the schema fields/formats

Example:

```text
schema: event_type:STRING, oid:STRING, sid:STRING
table: alerts
dataset: limacharlie_data
project: lc-example-analytics
secret_key: {
  "type": "service_account",
  "project_id": "my-lc-data",
  "private_key_id": "EXAMPLE_KEY_ID_REPLACE_WITH_YOURS",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...(your actual private key here)...\n-----END PRIVATE KEY-----\n",
  "client_email": "my-service-writer@my-lc-data.iam.gserviceaccount.com",
  "client_id": "YOUR_CLIENT_ID",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/my-service-writer%40my-lc-data.iam.gserviceaccount.com"
}
custom_transform: |-
  {
    "oid":"routing.oid",
    "sid":"routing.sid",
    "event_type":"routing.event_type"
  }
```

## Related articles

- [Building Reports with BigQuery + Looker Studio](../../../4-data-queries/tutorials/bigquery-looker-studio.md)
- [Google Cloud Pubsub](google-pubsub.md)
- [Google Cloud Storage](google-cloud-storage.md)
- [Google Workspace](../../../2-sensors-deployment/adapters/types/google-workspace.md)
- [Google Cloud Storage](../../../2-sensors-deployment/adapters/types/google-cloud-storage.md)
- [Tutorial: Ingesting Google Cloud Logs](../../../2-sensors-deployment/adapters/tutorials/google-cloud-logs.md)
- [Google Cloud](../../extensions/cloud-cli/google-cloud.md)
