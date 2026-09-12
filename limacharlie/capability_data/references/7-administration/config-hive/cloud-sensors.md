# Config Hive: Cloud Sensors

## Format

## Permissions

- `cloudsensor.get`
- `cloudsensor.set`
- `cloudsensor.del`
- `cloudsensor.get.mtd`
- `cloudsensor.set.mtd`

## Command-Line Usage

Hive secrets can be managed from the command-line, via the `limacharlie hive` command. Positional and optional arguments for command-line usage are below:

```yaml
usage: limacharlie hive [-h] [-k KEY] [-d DATA] [-pk PARTITIONKEY] [--etag ETAG] [--expiry EXPIRY] [--enabled ENABLED] [--tags TAGS] action hive_name

positional arguments:
  action                the action to take, one of: list, list_mtd, get, get_mtd, set, update, remove
  hive_name             the hive name

options:
  -h, --help            show this help message and exit
  -k KEY, --key KEY     the name of the key.
  -d DATA, --data DATA  file containing the JSON data for the record, or "-" for stdin.
  -pk PARTITIONKEY, --partition-key PARTITIONKEY
                        the partition key to use instead of the default OID.
  --etag ETAG           the optional previous etag expected for transactions.
  --expiry EXPIRY       a millisecond epoch timestamp when the record should expire.
  --enabled ENABLED     whether the record is enabled or disabled.
  --tags TAGS           comma separated list of tags.
```

## Usage

## Example

```json
{
    "sensor_type": "webhook",
    "webhook": {
        "client_options": {
            "hostname": "test-webhook",
            "identity": {
                "installation_key": "3bc13b74-0d27-4633-9773-62293bf940a7",
                "oid": "aecec56a-046c-4078-bc08-8ebdc84dcad5"
            },
            "platform": "json",
            "sensor_seed_key": "test-webhook"
        },
        "secret": "super-secret-hook"
    }
}
```
