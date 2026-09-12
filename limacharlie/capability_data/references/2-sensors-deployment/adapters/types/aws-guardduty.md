# AWS GuardDuty

## Overview

This Adapter allows you to ingest AWS GuardDuty events via either an [S3 bucket](https://aws.amazon.com/s3/) or [SQS message queue](https://aws.amazon.com/sqs/).

[AWS GuardDuty](https://aws.amazon.com/guardduty/) helps you protect your AWS accounts with intelligent threat detection.

Telemetry Platform: `guard_duty`

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

#### Collecting AWS GuardDuty Logs via an S3 Bucket

If collecting GuardDuty logs via an S3 bucket, you will need the following parameters:

- `bucket_name` - The name of the S3 bucket holding the data)
- `secret_key` - The API key for AWS that has access to the respective bucket.
- `access_key` - The AWS access key for the API key

The following command will create an Adapter using the (1) Adapter binary and (2) logs stored in an S3 bucket:

```bash
./lc_adapter s3 client_options.identity.installation_key=<INSTALLATION_KEY> \
client_options.identity.oid=<OID> \
client_options.platform=guard_duty \
bucket_name=lc-ct-test \
access_key=YYYYYYYYYY \
secret_key=XXXXXXXX \
client_options.hostname=guardduty-logs
```

#### Collecting AWS GuardDuty Logs via an SQS Queue

If collecting GuardDuty logs via an SQS queue, you will need the following parameters:

- `secret_key` - The API key for AWS that has access to the respective bucket.
- `access_key` - The AWS access key for the API key
- `region` - The AWS region where the SQS instance lives
- `queue_url` - The URL to the SQS instance

The following command will create an Adapter using the (1) Adapter binary and (2) logs stored in an SQS queue:

```bash
./lc_adapter sqs client_options.identity.installation_key=<INSTALLATION_KEY> \
client_options.identity.oid=<OID> \
client_options.platform=guard_duty \
client_options.sensor_seed_key=<SENSOR_SEED_KEY> \
client_options.hostname=guardduty-logs \
access_key=YYYYYYYYYY \
secret_key=XXXXXXXX \
queue_url=<QUEUE_URL> \
region=<AWS-REGION>
```

## Guided Deployment

Within the LimaCharlie web application, you can create an AWS GuardDuty Cloud Connector using the `+ Add Sensor` option.

![Add Sensor option for AWS GuardDuty Cloud Connector in the LimaCharlie web application](../../../assets/images/image(304).png)
