# Google Cloud Pubsub

## Overview

This Adapter allows you to ingest events from a Google Cloud Pubsub subscription.

## Configurations

Adapter Type: `pubsub`

- `client_options`: see [common adapter configuration](../usage.md).
- `sub_name`: the name of the subscription to subscribe to.
- `service_account_creds`: the string version of the JSON credentials for a (Google) Service Account to use accessing the subscription.
- `project_name`: project name where the `sub_name` exists.

### CLI Deployment

This example assumes that the Adapter is running from a host that has [default credentials](https://cloud.google.com/docs/authentication/production) (via the `GOOGLE_APPLICATION_CREDENTIALS` environment variable) setup. If it's not the case you will need to use `service_account_creds` to provide the contents of the JSON credentials of the GCP Service Account to use.

```bash
./lc_adapter pubsub client_options.identity.installation_key=f5eaaaad-575a-498e-bfc2-5f83e249a646 \
    client_options.identity.oid=8cbe27f4-bfa1-4afb-ba19-138cd51389cd \
    client_options.platform=gcp \
    sub_name=usp \
    project_name=monitored-proj \
    client_options.sensor_seed_key=gcplogs
```

Here's the breakdown of the above example:

- `lc_adapter`: simply the CLI Adapter.
- `pubsub`: the method the Adapter should use to collect data locally.
- `client_options.identity.installation_key=....`: the Installation Key value from LimaCharlie.
- `client_options.identity.oid=....`: the Organization ID from LimaCharlie the installation key above belongs to.
- `client_options.platform=gcp`: this indicates that the data read is logs from Google Cloud Platform.
- `client_options.sensor_seed_key=....`: this is the value that identifies this instance of the Adapter. Record it to re-use the Sensor ID generated for this Adapter later if you have to re-install the Adapter.
- `sub_name=usp`: the Subscription name to consume the logs from.
- `project_name=monitored-proj`: the GCP Project name this Subscription belongs to.

### Infrastructure as Code Deployment

```python
sensor_type: "pubsub"
pubsub:
  sub_name: "your-pubsub-subscription-name"
  project_name: "your-gcp-project-id"
  service_account_creds: "hive://secret/gcp-pubsub-service-account"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_PUBSUB"
    platform: "json"
    sensor_seed_key: "gcp-pubsub-sensor"
    mapping:
      # Map Pub/Sub message to sensor fields
      sensor_hostname_path: "attributes.hostname"
      event_type_path: "attributes.eventType"
      event_time_path: "publishTime"
    indexing: []
  # Optional configuration
  max_ps_buffer: 1048576  # 1MB buffer (optional)
```

## API Doc

See the [official documentation](https://cloud.google.com/pubsub).
