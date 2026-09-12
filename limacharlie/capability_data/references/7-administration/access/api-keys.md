# API Keys

LimaCharlie Cloud has a concept of API keys. Those are secret keys that can be created and named, and then in turn be used to retrieve a JWT that can be associated with the LC REST API at <https://api.limacharlie.io>.

This allows construction of headless applications able to securely acquire time-restricted REST authentication tokens it can then use.

The list of available permissions can be programmatically retrieved from this URL: <https://app.limacharlie.io/owner_permissions>

## Managing

The API Keys are managed through the Organization view of the <https://limacharlie.io> web interface.

## Getting a JWT

Issue an HTTP POST to `https://jwt.limacharlie.io` with the Organization ID and API key. The returned JWT is valid for one hour.

=== "REST API"

    ```bash
    curl -X POST "https://jwt.limacharlie.io" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "oid=YOUR_OID&secret=YOUR_API_KEY"
    ```

    Response: `{ "jwt": "<JWT_VALUE_HERE>" }`

=== "Python"

    ```python
    from limacharlie.client import Client

    # JWT is acquired and refreshed automatically
    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    // JWT is acquired and refreshed automatically
    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    ```

=== "CLI"

    ```bash
    # Credentials are stored in ~/.limacharlie after login
    limacharlie auth login
    ```

### User API Keys

User API keys are to generate JSON web tokens (JWTs) for the REST API. In contrast to Organization API keys, the User API keys are associated with a specific user and provide the exact same access across all organizations.

This makes User API Keys very powerful but also riskier to manage. Therefore we recommend using Organization API keys whenever possible.

The User API keys can be used through all the same interfaces as the Organization API keys. The only difference is how you get the JWT. Instead of giving an `oid` parameter to `https://jwt.limacharlie.io/`, provide it with a `uid` parameter available through the LimaCharlie web interface.

`curl -X POST "https://jwt.limacharlie.io" -H "Content-Type: application/x-www-form-urlencoded" -d "uid=<YOUR_USER_ID>&secret=<YOUR_API_KEY>"`

In some instances, the JWT resulting from a User API key may be to large for normal API use, in which case you will get an `HTTP 413 Payload too large` from the API gateway. In those instances, also provide an `oid` (on top of the `uid`) to the `jwt.limacharlie.io` REST endpoint to get a JWT valid only for that organization.

`curl -X POST "https://jwt.limacharlie.io" -H "Content-Type: application/x-www-form-urlencoded" -d "oid=<YOUR_OID>&uid=<YOUR_USER_ID>&secret=<YOUR_API_KEY>"`

You may also use a User API Key to get the list of organizations available to it by querying the following REST endpoint:

`https://app.limacharlie.io/user_key_info?secret=<YOUR_USER_API_KEY>&uid=<YOUR_USER_ID>&with_names=true`

#### Ingestion Keys

The [artifact collection](../../5-integrations/extensions/limacharlie/artifact.md) in LC requires Ingestion Keys, which can be managed through the REST API section of the LC web interface. Access to manage these Ingestion Keys requires the `ingestkey.ctrl` permission.

## SDKs

The [Python SDK](../../6-developer-guide/sdks/python-sdk.md) and [Go SDK](../../6-developer-guide/sdks/go-sdk.md) handle the API Key to JWT exchange automatically and wrap the REST API into convenient objects.

## Privileges

API Keys have several on-off privileges available.

To see a full list, see the "REST API" section of your organization.

Making a REST call will fail with a `401` if your API Key / token is missing some privileges and the missing privilege will be specified in the error.

## Required Privileges

Below is a list of privileges required for some common tasks.

### Go Live

When "going Live" through the web UI, the following is required by the user:

- `output.*`: for the creation of the real-time output via HTTP to the browser.
- `sensor.task`: to send the commands (both manually for the console and to populate the various tabs) to the Sensor.

## Flair

API Keys may have "flair" as part of the key name. A flair is like a tag surrounded by `[]`. Although it is not required, we advise to put the flair at the end of the API key name for readability.

For example:
`orchestration-key[bulk]` is a key with a `bulk` flair.

Flairs are used to modify the behavior of an API key or provide some usage hints to various systems in LimaCharlie.

The following flairs are currently supported:

- `bulk`: indicates to the REST API that this key is meant to do a large amount of calls, the API gateway tweaks the API call limits accordingly.
- `segment`: indicates that only resources created by this key will be visible by this key. This is useful to provide access to a 3rd party in a limited fashion.

## Allowed IP Range

When creating an API key, you can optionally include an `allowed_ip_range`, which should be a [CIDR notation](https://aws.amazon.com/what-is/cidr/) IP range from which the API key can be used. Any use of the API key from a different IP address will fail. This is currently only configurable when creating an API key via the API and not in the UI.

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.

In LimaCharlie, an Organization ID is a unique identifier assigned to each tenant or customer account. It distinguishes different organizations within the platform, enabling LimaCharlie to manage resources, permissions, and data segregation securely. The Organization ID ensures that all telemetry, configurations, and operations are kept isolated and specific to each organization, allowing for multi-tenant support and clear separation between different customer environments.

Similar to agents, Sensors send telemetry to the LimaCharlie platform in the form of EDR telemetry or forwarded logs. Sensors are offered as a scalable, serverless solution for securely connecting endpoints of an organization to the cloud.

## Programmatic Management

!!! info "Prerequisites"
    Managing API keys programmatically requires an existing API key with the `apikey.ctrl` permission. See [Managing](#managing) for initial setup through the web interface.

### List API Keys

=== "REST API"

    ```bash
    curl -s -X GET "https://api.limacharlie.io/v1/orgs/YOUR_OID/keys" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.api_keys import ApiKeys

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    keys = ApiKeys(org).list()
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    keys, err := org.GetAPIKeys()
    ```

=== "CLI"

    ```bash
    limacharlie api-key list
    ```

### Create an API Key

=== "REST API"

    ```bash
    curl -s -X POST "https://api.limacharlie.io/v1/orgs/YOUR_OID/keys" \
      -H "Authorization: Bearer $LC_JWT" \
      -d "key_name=ci-key&perms=dr.list,dr.set"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.api_keys import ApiKeys

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    key = ApiKeys(org).create("ci-key", ["dr.list", "dr.set"])
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    key, err := org.CreateAPIKey("ci-key", []string{"dr.list", "dr.set"})
    ```

=== "CLI"

    ```bash
    limacharlie api-key create --name ci-key --permissions "dr.list,dr.set"
    ```

    To mint the key and store its value in the [secret hive](../config-hive/secrets.md) in a single step, add `--store-secret`:

    ```bash
    limacharlie api-key create --name <name> --permissions "..." --store-secret <secret-name> [--store-secret-tag <tag>]
    ```

    This creates the key and writes its value to `hive://secret/<secret-name>`. The value is shown only once at creation, so storing it directly avoids having to capture and re-pipe it. If a secret with that name already exists, it is updated in place via its etag. The identity running this command needs the `secret.set` permission (to write the secret) in addition to the permission to create API keys.

### Delete an API Key

=== "REST API"

    ```bash
    curl -s -X DELETE "https://api.limacharlie.io/v1/orgs/YOUR_OID/keys" \
      -H "Authorization: Bearer $LC_JWT" \
      -d "key_hash=KEY_HASH_TO_DELETE"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.api_keys import ApiKeys

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    ApiKeys(org).delete("KEY_HASH_TO_DELETE")
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    err := org.DeleteAPIKey("KEY_HASH_TO_DELETE")
    ```

=== "CLI"

    ```bash
    limacharlie api-key delete --key-hash KEY_HASH_TO_DELETE --confirm
    ```

---

## See Also

- [SDKs](../../6-developer-guide/sdks/index.md)
- [Python SDK](../../6-developer-guide/sdks/python-sdk.md)
- [Go SDK](../../6-developer-guide/sdks/go-sdk.md)
