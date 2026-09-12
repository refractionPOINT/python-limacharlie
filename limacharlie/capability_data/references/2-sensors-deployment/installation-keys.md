# Installation Keys

Installation keys are Base64-encoded strings provided to Sensors and Adapters in order to associate them with the correct Organization. Installation keys are created per-organization and offer a way to label and control your deployment population.

There are four components of an Installation Key:

- Organization ID **(**OID**)**: The Organization ID that this key should enroll into.
- **Installer ID (IID)**: Installer ID that is generated and associated with every Installation Key.
- **Tags**: A list of Tags automatically applied to sensors enrolling with the key.
- **Description**: The description used to help you differentiate uses of various keys.

## Management

Installation keys can be managed on the **Sensors > Installation Keys** page in the web app.

On this page, under the `Connectivity` section, you will see the various URLs associated with Sensor and Adapter connectivity.

### Pinned Certificates

Typically, Sensors require access over port 443 and use pinned SSL certificates. This is the default deployment option, and does not support traffic interception.

If you need to install sensors without pinned certificates, an installation key must be created with a specific flag. This must be done via the REST API, by setting the `use_public_root_ca` flag to `true`.

See the [Python SDK Manager.replicantRequest source](https://github.com/refractionPOINT/python-limacharlie/blob/master/limacharlie/Manager.py#L1386) for more detail.

## Use of Tags

Generally speaking, we use at least one Installation Key per organization. Then we use different keys to help differentiate parts of our infrastructure. For example, you may create a key with Tag "server" that you will use to install on your servers, a key with "vip" for executives in your organization, or a key with "sales" for the sales department, etc. This way you can use the tags on various sensors to figure out different detection and response rules for different types of hosts on your infrastructure.

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.

Installation keys are Base64-encoded strings provided to Sensors and Adapters in order to associate them with the correct Organization. Installation keys are created per-organization and offer a way to label and control your deployment population.

In LimaCharlie, an Organization ID is a unique identifier assigned to each tenant or customer account. It distinguishes different organizations within the platform, enabling LimaCharlie to manage resources, permissions, and data segregation securely. The Organization ID ensures that all telemetry, configurations, and operations are kept isolated and specific to each organization, allowing for multi-tenant support and clear separation between different customer environments.

In LimaCharlie, an Organization ID (OID) is a unique identifier assigned to each tenant or customer account. It distinguishes different organizations within the platform, enabling LimaCharlie to manage resources, permissions, and data segregation securely. The Organization ID ensures that all telemetry, configurations, and operations are kept isolated and specific to each organization, allowing for multi-tenant support and clear separation between different customer environments.

Similar to agents, Sensors send telemetry to the LimaCharlie platform in the form of EDR telemetry or forwarded logs. Sensors are offered as a scalable, serverless solution for securely connecting endpoints of an organization to the cloud.

Adapters serve as flexible data ingestion mechanisms for both on-premise and cloud environments.

## Programmatic Management

!!! info "Prerequisites"
    All programmatic examples require an API key with `ikey.list`, `ikey.set`, and `ikey.del` permissions. See [API Keys](../7-administration/access/api-keys.md) for setup instructions.

### List Installation Keys

=== "REST API"

    ```bash
    curl -s -X GET "https://api.limacharlie.io/v1/installationkeys/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.installation_keys import InstallationKeys

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    keys = InstallationKeys(org).list()
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    keys, err := org.InstallationKeys()
    ```

=== "CLI"

    ```bash
    limacharlie installation-key list
    ```

### Create an Installation Key

=== "REST API"

    ```bash
    curl -s -X POST "https://api.limacharlie.io/v1/installationkeys/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT" \
      -d "desc=Production+servers&tags=server,prod"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.installation_keys import InstallationKeys

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    key = InstallationKeys(org).create("Production servers", tags=["server", "prod"])
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    iid, err := org.AddInstallationKey(limacharlie.InstallationKey{
        Description: "Production servers",
        Tags:        []string{"server", "prod"},
    })
    ```

=== "CLI"

    ```bash
    limacharlie installation-key create --description "Production servers" --tags "server,prod"
    ```

### Delete an Installation Key

=== "REST API"

    ```bash
    curl -s -X DELETE "https://api.limacharlie.io/v1/installationkeys/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT" \
      -d "iid=IID_TO_DELETE"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.installation_keys import InstallationKeys

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    InstallationKeys(org).delete("IID_TO_DELETE")
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    err := org.DelInstallationKey("IID_TO_DELETE")
    ```

=== "CLI"

    ```bash
    limacharlie installation-key delete --iid IID_TO_DELETE --confirm
    ```

---

## See Also

- [Sensor Deployment Overview](index.md)
- [Windows Installation](endpoint-agent/windows/installation.md)
- [Linux Installation](endpoint-agent/linux/installation.md)
- [Python SDK](../6-developer-guide/sdks/python-sdk.md)
- [Go SDK](../6-developer-guide/sdks/go-sdk.md)
