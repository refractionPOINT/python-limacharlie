# VMWare Carbon Black

## Overview

LimaCharlie can ingest Carbon Black events from a number of storage locations. Typically, an organization would export Carbon Black data via the API to a storage mechanism, such as an S3 bucket, which would then be ingested by LimaCharlie.

Carbon Black events are observable in Detection & Response rules via the `carbon_black` platform.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

## Config File

VMWare Carbon Black data can be exported via the API to an S3 bucket, and then ingested with LimaCharlie. The following command utilizes a CLI Adapter to ingest these events

```bash
./lc_adapter s3 client_options.identity.installation_key=<INSTALLATION_KEY> \
client_options.identity.oid=<OID> \
client_options.platform=carbon_black \
client_options.sensor_seed_key=tests3 \
bucket_name=lc-cb-test \
access_key=YYYYYYYYYY \
secret_key=XXXXXXXX  \
"prefix=events/org_key=NKZAAAEM/"
```

Here's a breakdown of the above example:

- `lc_adapter`: simply the CLI Adapter.
- `s3`: the data will be collected from an AWS S3 bucket.
- `client_options.identity.installation_key=....`: the Installation Key value from LimaCharlie.
- `client_options.identity.oid=....`: the Organization ID from LimaCharlie the installation key above belongs to.
- `client_options.platform=carbon_black`: this indicates the data received will be Carbon Black events from their API.
- `client_options.sensor_seed_key=....`: this is the value that identifies this instance of the Adapter. Record it to re-use the Sensor IDs generated for the Carbon Black sensors from this Adapter later if you have to re-install the Adapter.
- `bucket_name:....`: the name of the S3 bucket holding the data.
- `access_key:....`: the AWS Access Key for the API key below.
- `secret_key:....`: the API key for AWS that has access to this bucket.
- `prefix=....`: the file/directory name prefix that holds the Carbon Black data within the bucket.
