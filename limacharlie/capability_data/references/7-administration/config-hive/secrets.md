# Config Hive: Secrets

With its multitude of data ingestion and output options, LimaCharlie users can end up with a myriad of credentials and secret keys to faciliate unique data operations. However, not all users should be privy to these secret keys. Within the Config Hive, the `secrets` hive component allows you to decouple secrets from their usage or configuration across LimaCharlie. Furthermore, you can also grant permissions to users that allows them to see the configuration of an output, but not have access to the associated credentials.

The most common usage is for storing secret keys used by various [Adapters](../../2-sensors-deployment/adapters/usage.md) or [Outputs](../../5-integrations/outputs/testing.md). By referencing `secrets` within the Config Hive, we can configure these services without needing to reveal secret keys to all users.

Watch the video below to learn more about hive secrets, or continue reading below.

## Format

A secret record in `hive` has a very basic format:

```json
{
    "secret": "data"
}
```

The `data` portion of the records in this hive must have a single key called `secret` who's value will be used by various LimaCharlie components.

## Permissions

The `secret` hive requires the following permissions for the various operations:

- `secret.get`
- `secret.set`
- `secret.del`
- `secret.get.mtd`
- `secret.set.mtd`

## Secret Management

Over time, and with enough integrations, you may need to create and/or update secrets on demand. We provide quick options for both via either the LimaCharlie CLI or web app.

### Creating Secrets

With the appropriate permissions, users can create secrets in the following ways:

1. Using the LimaCharlie CLI, secrets can be created using the `limacharlie hive set secret` command (example below).
2. Via the web app, under **Organization Settings** > **Secrets Manager**.

### Updating Secrets

Once they are set, secrets can be updated via the following methods:

1. Using the LimaCharlie CLI, secrets can be updated using the `limacharlie hive update secret` command.
2. Via the web app, **Organization Settings** > **Secrets Manager**. Select the secret you wish to update, and update in the dialog box. Click **Save Secret** to save changes in the platform.

## Usage

Using a secret in combination with an output has very few steps:

1. Create a secret in the `secret` hive
2. Create an Output and use the format `hive://secret/my-secret-name` as the value for a credentials field.

## Programmatic Management

!!! info "Prerequisites"
    All API and SDK examples require an API key with the appropriate permissions. See [API Keys](../access/api-keys.md) for setup instructions.

### List Secrets

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/hive/secret/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    hive = Hive(org, "secret")
    records = hive.list()
    for name, record in records.items():
        print(name, record.data)
    ```

=== "Go"

    ```go
    package main

    import (
        "fmt"
        limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"
    )

    func main() {
        client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
            OID:    "YOUR_OID",
            APIKey: "YOUR_API_KEY",
        }, nil)
        org, _ := limacharlie.NewOrganization(client)
        hc := limacharlie.NewHiveClient(org)

        records, _ := hc.List(limacharlie.HiveArgs{
            HiveName:     "secret",
            PartitionKey: "YOUR_OID",
        })
        for name, record := range records {
            fmt.Println(name, record.Data)
        }
    }
    ```

=== "CLI"

    ```bash
    limacharlie secret list
    ```

### Get a Secret

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/hive/secret/YOUR_OID/my-secret/data" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    hive = Hive(org, "secret")
    record = hive.get("my-secret")
    print(record.data)
    ```

=== "Go"

    ```go
    package main

    import (
        "fmt"
        limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"
    )

    func main() {
        client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
            OID:    "YOUR_OID",
            APIKey: "YOUR_API_KEY",
        }, nil)
        org, _ := limacharlie.NewOrganization(client)
        hc := limacharlie.NewHiveClient(org)

        record, _ := hc.Get(limacharlie.HiveArgs{
            HiveName:     "secret",
            PartitionKey: "YOUR_OID",
            Key:          "my-secret",
        })
        fmt.Println(record.Data)
    }
    ```

=== "CLI"

    ```bash
    limacharlie secret get --key my-secret
    ```

### Create / Update a Secret

!!! warning
    New hive records are created **disabled by default**. Each example below explicitly enables the secret — drop the `enabled` portion if you want the secret to start disabled and enable it later via `limacharlie secret enable --key …`.

=== "REST API"

    ```bash
    curl -s -X POST \
      "https://api.limacharlie.io/v1/hive/secret/YOUR_OID/my-secret/data" \
      -H "Authorization: Bearer $LC_JWT" \
      -d 'data={"secret":"my-secret-value"}' \
      -d 'usr_mtd={"enabled":true}'
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive, HiveRecord

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    hive = Hive(org, "secret")
    record = HiveRecord(
        "my-secret",
        data={"secret": "my-secret-value"},
        enabled=True,
    )
    hive.set(record)
    ```

=== "Go"

    ```go
    package main

    import (
        limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"
    )

    func main() {
        client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
            OID:    "YOUR_OID",
            APIKey: "YOUR_API_KEY",
        }, nil)
        org, _ := limacharlie.NewOrganization(client)
        hc := limacharlie.NewHiveClient(org)

        enabled := true
        hc.Add(limacharlie.HiveArgs{
            HiveName:     "secret",
            PartitionKey: "YOUR_OID",
            Key:          "my-secret",
            Data:         limacharlie.Dict{"secret": "my-secret-value"},
            Enabled:      &enabled,
        })
    }
    ```

=== "CLI"

    ```bash
    limacharlie secret set --key my-secret \
      --input-file secret.json --enabled
    ```

    Where `secret.json` contains:

    ```json
    {
        "data": {
            "secret": "my-secret-value"
        }
    }
    ```

    The `--enabled` flag creates-and-enables the record in one shot. Omit it (and `usr_mtd.enabled` in the file) to leave the secret disabled until you call `limacharlie secret enable --key my-secret`.

### Delete a Secret

=== "REST API"

    ```bash
    curl -s -X DELETE \
      "https://api.limacharlie.io/v1/hive/secret/YOUR_OID/my-secret" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    hive = Hive(org, "secret")
    hive.delete("my-secret")
    ```

=== "Go"

    ```go
    package main

    import (
        limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"
    )

    func main() {
        client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
            OID:    "YOUR_OID",
            APIKey: "YOUR_API_KEY",
        }, nil)
        org, _ := limacharlie.NewOrganization(client)
        hc := limacharlie.NewHiveClient(org)

        hc.Remove(limacharlie.HiveArgs{
            HiveName:     "secret",
            PartitionKey: "YOUR_OID",
            Key:          "my-secret",
        })
    }
    ```

=== "CLI"

    ```bash
    limacharlie secret delete --key my-secret --confirm
    ```

### Enable / Disable a Secret

=== "REST API"

    ```bash
    # 1. Read current metadata to preserve tags, expiry, comment:
    CURRENT=$(curl -s -X GET \
      "https://api.limacharlie.io/v1/hive/secret/YOUR_OID/my-secret/mtd" \
      -H "Authorization: Bearer $LC_JWT")

    # 2. Merge and update (set enabled to false, keep other fields):
    curl -s -X POST "https://api.limacharlie.io/v1/hive/secret/YOUR_OID/my-secret/mtd" \
      -H "Authorization: Bearer $LC_JWT" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d 'usr_mtd={"enabled":false,"expiry":0,"tags":[],"comment":""}'
    ```

    !!! warning
        The API **replaces** `usr_mtd` entirely. Sending only `{"enabled":false}` will reset tags, expiry, and comment to their defaults. Always read the current metadata first and resend all fields.

=== "Python"

    ```python
    hive = Hive(org, "secret")
    # Read-modify-write to preserve other metadata:
    record = hive.get_metadata("my-secret")
    record.enabled = False  # or True to re-enable
    hive.set(record)
    ```

=== "Go"

    ```go
    hc := limacharlie.NewHiveClient(org)
    // Read current metadata first to preserve tags, expiry, comment.
    existing, _ := hc.GetMTD(limacharlie.HiveArgs{
        HiveName:     "secret",
        PartitionKey: org.GetOID(),
        Key:          "my-secret",
    })
    enabled := false
    hc.Add(limacharlie.HiveArgs{
        HiveName:     "secret",
        PartitionKey: org.GetOID(),
        Key:          "my-secret",
        Enabled:      &enabled,
        Tags:         existing.UsrMtd.Tags,
        Expiry:       &existing.UsrMtd.Expiry,
        Comment:      &existing.UsrMtd.Comment,
    })
    ```

=== "CLI"

    ```bash
    # Disable a secret (reads metadata first to preserve other fields):
    limacharlie secret disable --key my-secret
    # Re-enable:
    limacharlie secret enable --key my-secret
    # Or using the generic hive command:
    limacharlie hive disable --hive-name secret --key my-secret
    ```

## Example

Let's create a simple secret using the LimaCharlie CLI in a terminal. First, create a small file with the secret record in it:

```text
echo "my-secret-value" > my-secret
```

Next, set this secret in Hive via the LimaCharlie CLI:

```bash
limacharlie hive set secret --key my-secret --data my-secret --data-key secret
```

You should get a confirmation that the secret was created, including metadata of the secret and associated OID:

```json
{
    "guid": "3a7a2865-a439-4d1a-8f50-b9a6d833075c",
    "hive": {
        "name": "secret",
        "partition": "8cbe27f4-aaaa-bbbb-cccc-138cd51389cd"
        },
    "name": "my-secret"
}
```

Next, create an output in the web app, using the value `hive://secret/my-secret` as the Secret Key value.

![secret](../../assets/images/secret.png)

And that's it! The output should start as expected, however when viewing the output's configuration, the secret should refer to the `hive` ARN, rather than the actual credentials.

## See Also

- [Adapter Usage](../../2-sensors-deployment/adapters/usage.md) -- Common consumer of hive secrets.
- [Outputs](../../5-integrations/outputs/index.md) -- Another common consumer of hive secrets.
- [D&R-Driven AI Sessions](../../9-ai-sessions/dr-sessions.md) -- The `start ai agent` action consumes Anthropic and LC API keys via `hive://secret/<name>` references.
- [Compliance Installation](../../9-ai-sessions/compliance/installation.md) -- The `compliance-deploy` skill stages a scoped LC API key and an Anthropic key in this hive as part of reviewer-agent deployment.
