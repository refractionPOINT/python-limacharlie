# Outputs

Stream telemetry to external destinations.

## Documentation

- [Output Allowlisting](allowlisting.md) - Filtering output data
- [Output Billing](billing.md) - Billing and usage
- [Output Stream Structures](stream-structures.md) - Data format specifications
- [Testing Outputs](testing.md) - Testing output configurations

---

## Programmatic Management

!!! info "Prerequisites"
    All API examples require an API key with the `output` permission. See [API Keys](../../7-administration/access/api-keys.md) for setup.

### List Outputs

=== "REST API"

    ```bash
    curl -s -X GET \
      "https://api.limacharlie.io/v1/outputs/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.outputs import Outputs

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    outputs = Outputs(org).list()
    print(outputs)
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
        outputs, _ := org.Outputs()
        fmt.Println(outputs)
    }
    ```

=== "CLI"

    ```bash
    limacharlie output list
    ```

### Create Output

Example: create a syslog output for event data.

=== "REST API"

    ```bash
    curl -s -X POST \
      "https://api.limacharlie.io/v1/outputs/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT" \
      -d name="my-syslog" \
      -d module="syslog" \
      -d type="event" \
      -d dest_host="siem.example.com:514"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.outputs import Outputs

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    result = Outputs(org).create(
        name="my-syslog",
        module="syslog",
        data_type="event",
        dest_host="siem.example.com:514",
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
        result, _ := org.OutputAdd(limacharlie.OutputConfig{
            Name:            "my-syslog",
            Module:          limacharlie.OutputTypes.Syslog,
            Type:            limacharlie.OutputType.Event,
            DestinationHost: "siem.example.com:514",
        })
        fmt.Println(result)
    }
    ```

=== "CLI"

    ```bash
    # config.yaml contains module-specific fields like dest_host
    limacharlie output create \
      --name my-syslog \
      --module syslog \
      --type event \
      --input-file config.yaml
    ```

### Delete Output

=== "REST API"

    ```bash
    curl -s -X DELETE \
      "https://api.limacharlie.io/v1/outputs/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT" \
      -d name="my-syslog"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.outputs import Outputs

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    Outputs(org).delete("my-syslog")
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
        resp, _ := org.OutputDel("my-syslog")
        fmt.Println(resp)
    }
    ```

=== "CLI"

    ```bash
    limacharlie output delete --name my-syslog --confirm
    ```

---

## See Also

- [Stream Structures](stream-structures.md)
- [Output Destinations](destinations/amazon-s3.md)
- [D&R Response Actions](../../8-reference/response-actions.md)
