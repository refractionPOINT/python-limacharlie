# SQS

## Overview

This Adapter allows you to ingest events received from an AWS SQS instance.

## Configurations

Adapter Type: `sqs`

- `client_options`: see [common adapter configuration](../usage.md).
- `access_key`: an Access Key from AWS used to access the queue.
- `secret_key`: the secret key associated with the `access_key` used to access the queue.
- `queue_url`: the queue URL for the SQS instance.

### Infrastructure as Code Deployment

```python
sensor_type: "sqs"
sqs:
  queue_url: "https://sqs.us-east-1.amazonaws.com/123456789012/your-security-logs-queue"
  aws_access_key_id: "hive://secret/aws-access-key-id"
  aws_secret_access_key: "hive://secret/aws-secret-access-key"
  aws_region: "us-east-1"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_SQS"
    platform: "json"
    sensor_seed_key: "aws-sqs-sensor"
    mapping:
      sensor_hostname_path: "source.instance_id"
      event_type_path: "detail.eventName"
      event_time_path: "time"
    indexing: []
  # Optional SQS-specific configuration
  max_messages: 10                       # Default: 10 (max messages per poll)
  wait_time_seconds: 20                  # Default: 20 (long polling)
  visibility_timeout: 300                # Default: 300 seconds
  delete_after_processing: true          # Default: true
```

## API Doc

See the [official documentation](https://aws.amazon.com/sqs/).
