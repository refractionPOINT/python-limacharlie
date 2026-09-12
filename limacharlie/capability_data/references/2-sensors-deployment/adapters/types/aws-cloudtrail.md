# AWS CloudTrail

[AWS CloudTrail](https://docs.aws.amazon.com/cloudtrail/) logs allow you to monitor AWS deployments. CloudTrail logs can provide granular visibility into AWS instances and can be used within D&R rules to identify AWS abuse.

This Adapter allows you to ingest AWS CloudTrail events via either an [S3 bucket](https://aws.amazon.com/s3/) or [SQS message queue](https://aws.amazon.com/sqs/).

CloudTrail events can be addressed in LimaCharlie as the `aws` platform.

## Adapter Deployment

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

CloudTrail logs can be collected via a cloud-to-cloud Adapter, or via the CLI Adapter. Furthermore, within each option, there is a choice of collecting logs from an S3 bucket or an SQS message queue.

## Cloud-to-Cloud Adapter

Within the LimaCharlie web application, you can create an AWS CloudTrail Cloud Connector using the `+ Add Sensor` option.

![image.png](../../../assets/images/image(160).png)

After providing an Installation Key, you will be guided through connecting either an S3 bucket or SQS queue to ingest AWS CloudTrail events.

### Collecting AWS CloudTrail Logs via an S3 Bucket

If collecting CloudTrail logs via an S3 bucket, you will need the following parameters:

- `bucket_name` - The name of the S3 bucket holding the data)
- `secret_key` - The API key for AWS that has access to the respective bucket.
- `access_key` - The AWS access key for the API key

The following sample configuration can be used to create an S3 CLI Adapter for AWS CloudTrail events:

```yaml
s3:
  client_options:
    hostname: aws-cloudtrail-logs
    identity:
      installation_key: <INSTALLATION_KEY>
      oid: <OID>
    platform: aws
    sensor_seed_key: super-special-seed-key
  bucket_name: <S3_BUCKET_NAME>
  secret_key: <S3_SECRET_KEY>
  access_key: <S3_ACCESS_KEY>
```

#### Collecting AWS CloudTrail Logs via an SQS Queue

If collecting CloudTrail logs via an SQS queue, you will need the following parameters:

- `secret_key` - The API key for AWS that has access to the respective bucket.
- `access_key` - The AWS access key for the API key
- `region` - The AWS region where the SQS instance lives
- `queue_url` - The URL to the SQS instance

The following sample configuration can be used to create an SQS CLI Adapter for AWS CloudTrail events:

```yaml
sqs:
  client_options:
    hostname: aws-cloudtrail-logs
    identity:
      installation_key: <INSTALLATION_KEY>
      oid: <OID>
    platform: aws
    sensor_seed_key: super-special-seed-key
  region: <SQS_REGION>
  secret_key: <SQS_SECRET_KEY>
  access_key: <SQS_ACCESS_KEY>
  queue_url: <SQS_QUEUE_URL>
```
