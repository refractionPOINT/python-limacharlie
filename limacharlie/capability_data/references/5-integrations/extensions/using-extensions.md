# Using Extensions

## Components

Extensions can be interacted with using two main components:

### Configurations

Extension Configurations are records in [Hive](../../7-administration/config-hive/index.md). Each Extension has its configuration in the Hive record of the same name in the `extension_configuration` Hive.

These configurations are manipulated by simply storing the value in the record, LimaCharlie takes care of validating and notifying the Extension with the new value.

Configurations are a great way of storing rarely-written settings for an Extension without the developer of the Extension having to manage secure storage for it.

The structure of the configuration for a given Extension is published by the Extension via its "schema".

Schemas are available through the [Schema API](https://api.limacharlie.io/static/swagger/#/Extension-Schema/getExtensionSchema) or the LimaCharlie CLI: `limacharlie extension schema --help`.

### Requests

Requests are, as the name implies, direct individual requests to an Extension. A request contains an "action" and a "payload" (JSON object) to be sent to the Extension. Some requests can be flagged to have the Extension impersonate the requester (identity and permissions) during execution.

The "action" and "payload" entirely depends on the Extension it is destined to. The list of actions and individual payload structures available for an Extension is documented by each Extension using the "schema" they publish.

Schemas are available through the [Schema API](https://api.limacharlie.io/static/swagger/#/Extension-Schema/getExtensionSchema) or the LimaCharlie CLI: `limacharlie extension schema --help`.

## Interacting

### Interactively

The LimaCharlie webapp automatically displays a machine-generated user interface for each Extension based on the schema it publishes.

### Automation

[Detection & Response Rules](../../3-detection-response/index.md), the main automation mechanism in LimaCharlie can interact with Extensions using the `extension request` action in the Response component.

### API

Extensions can be interacted with using a few different APIs:

- Getting the schema for an Extension: [https://api.limacharlie.io/static/swagger/#/Extension-Schema](https://api.limacharlie.io/static/swagger/#/Extension-Request)
- Making requests to an Extension: <https://api.limacharlie.io/static/swagger/#/Extension-Request>

LimaCharlie Extensions allow users to expand and customize their security environments by integrating third-party tools, automating workflows, and adding new capabilities. Organizations subscribe to Extensions, which are granted specific permissions to interact with their infrastructure. Extensions can be private or public, enabling tailored use or broader community sharing. This framework supports scalability, flexibility, and secure, repeatable deployments.

## Programmatic Management

!!! info "Prerequisites"
    All API examples require an API key with the `extension` permission. See [API Keys](../../7-administration/access/api-keys.md) for setup.

### List Subscribed Extensions

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/orgs/YOUR_OID/subscriptions" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.extensions import Extensions

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    subscribed = Extensions(org).list_subscribed()
    print(subscribed)
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
        })
        org := limacharlie.NewOrganization(client)
        extensions, _ := org.Extensions()
        fmt.Println(extensions)
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension list
    ```

### List Available Extensions

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/extension/definition" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.extensions import Extensions

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    available = Extensions(org).get_all()
    print(available)
    ```

=== "Go"

    There is no dedicated Go SDK method for listing all available extensions. Use the REST API directly.

=== "CLI"

    ```bash
    limacharlie extension list-available
    ```

### Subscribe to an Extension

=== "REST API"

    ```bash
    curl -s -X POST \
      "https://api.limacharlie.io/v1/orgs/YOUR_OID/subscription/extension/ext-reliable-tasking" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.extensions import Extensions

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    Extensions(org).subscribe("ext-reliable-tasking")
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
        })
        org := limacharlie.NewOrganization(client)
        _ = org.SubscribeToExtension("ext-reliable-tasking")
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension subscribe --name ext-reliable-tasking
    ```

### Unsubscribe from an Extension

=== "REST API"

    ```bash
    curl -s -X DELETE \
      "https://api.limacharlie.io/v1/orgs/YOUR_OID/subscription/extension/ext-reliable-tasking" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.extensions import Extensions

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    Extensions(org).unsubscribe("ext-reliable-tasking")
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
        })
        org := limacharlie.NewOrganization(client)
        _ = org.UnsubscribeFromExtension("ext-reliable-tasking")
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension unsubscribe --name ext-reliable-tasking
    ```

### Call an Extension (Request)

=== "REST API"

    ```bash
    curl -s -X POST \
      "https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking" \
      -H "Authorization: Bearer $LC_JWT" \
      -d oid="YOUR_OID" \
      -d action="list_jobs" \
      -d data='{}'
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.extensions import Extensions

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    result = Extensions(org).request(
        extension_name="ext-reliable-tasking",
        action="list_jobs",
        data={},
    )
    print(result)
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
        })
        org := limacharlie.NewOrganization(client)
        var resp limacharlie.Dict
        _ = org.ExtensionRequest(
            &resp,
            "ext-reliable-tasking",
            "list_jobs",
            limacharlie.Dict{},
            false,
        )
        fmt.Println(resp)
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension request \
      --name ext-reliable-tasking \
      --action list_jobs \
      --data '{}'
    ```

### Get Extension Schema

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/extension/schema/ext-reliable-tasking?oid=YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.extensions import Extensions

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    schema = Extensions(org).get_schema("ext-reliable-tasking")
    print(schema)
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
        })
        org := limacharlie.NewOrganization(client)
        schema, _ := org.GetExtensionSchema("ext-reliable-tasking")
        fmt.Println(schema)
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension schema --name ext-reliable-tasking
    ```

### Extension Configuration CRUD

Extension configurations are stored in the `extension_config` [Hive](../../7-administration/config-hive/index.md). Use the CLI or Hive API to manage them.

#### List Configs

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/hive/extension_config/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    configs = Hive(org, "extension_config").list()
    print(configs)
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
        })
        org := limacharlie.NewOrganization(client)
        hive := limacharlie.NewHiveClient(org)
        configs, _ := hive.List(limacharlie.HiveArgs{
            HiveName:     "extension_config",
            PartitionKey: "YOUR_OID",
        })
        fmt.Println(configs)
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension config-list
    ```

#### Get Config

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/hive/extension_config/YOUR_OID/ext-reliable-tasking/data" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    config = Hive(org, "extension_config").get("ext-reliable-tasking")
    print(config)
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
        })
        org := limacharlie.NewOrganization(client)
        hive := limacharlie.NewHiveClient(org)
        config, _ := hive.Get(limacharlie.HiveArgs{
            HiveName:     "extension_config",
            PartitionKey: "YOUR_OID",
            Key:          "ext-reliable-tasking",
        })
        fmt.Println(config)
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension config-get --name ext-reliable-tasking
    ```

#### Set Config

=== "REST API"

    ```bash
    curl -s -X POST \
      "https://api.limacharlie.io/v1/hive/extension_config/YOUR_OID/ext-reliable-tasking/data" \
      -H "Authorization: Bearer $LC_JWT" \
      -d data='{"setting_a": "value1"}' \
      -d usr_mtd='{"enabled": true}'
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive, HiveRecord

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    Hive(org, "extension_config").set(HiveRecord(
        name="ext-reliable-tasking",
        data={"setting_a": "value1"},
        enabled=True,
    ))
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
        })
        org := limacharlie.NewOrganization(client)
        hive := limacharlie.NewHiveClient(org)
        enabled := true
        hive.Add(limacharlie.HiveArgs{
            HiveName:     "extension_config",
            PartitionKey: "YOUR_OID",
            Key:          "ext-reliable-tasking",
            Data:         limacharlie.Dict{"setting_a": "value1"},
            Enabled:      &enabled,
        })
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension config-set \
      --name ext-reliable-tasking \
      --input-file config.yaml
    ```

#### Delete Config

=== "REST API"

    ```bash
    curl -s -X DELETE \
      "https://api.limacharlie.io/v1/hive/extension_config/YOUR_OID/ext-reliable-tasking" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.hive import Hive

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    Hive(org, "extension_config").delete("ext-reliable-tasking")
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
        })
        org := limacharlie.NewOrganization(client)
        hive := limacharlie.NewHiveClient(org)
        hive.Remove(limacharlie.HiveArgs{
            HiveName:     "extension_config",
            PartitionKey: "YOUR_OID",
            Key:          "ext-reliable-tasking",
        })
    }
    ```

=== "CLI"

    ```bash
    limacharlie extension config-delete --name ext-reliable-tasking
    ```
