# Sensor Tags

Tags in LimaCharlie are simple strings that can be associated with any number of sensors. A Sensor can also have an arbitrary number of tags associated with it.

Tags appear in every event coming from a sensor under the `routing` component of the event. This greatly simplifies the writing of detection and response rules based on the presence of specific tags, at the cost of including more non-unique data per event.
Tags can be used for a variety of purposes, including:

- to classify endpoints
- automate detection and response
- create powerful workflows
- trigger automations

## Use Cases for Sensor Tags

### Classification

You can use tags to classify an endpoint in a number of different ways based on what is important to you.  Some examples of classifications are shown below for inspiration.

#### Departments

Create tags to classify endpoints based on what business department they belong to.  e.g. sales, finance, operations, development, support, legal, executives.

#### Usage Type

You may wish to tag endpoints based on their type of usage.  e.g. workstation, server, production, staging.

By having endpoints tagged in this manner you can easily identify endpoints and decide what actions you may wish to take while considering the tag.  For example, if you see an endpoint is tagged with `workstation` and `executives`, and you happen to see suspicious activity on the endpoint, it may be worthwhile for you to prioritize response.

### Automating detection and response

You can use tags to automate detection and response.

For example, you can create a detection & response rule so that when a specific user logs in on a device, the box is tagged as `VIP-sales` and the sensor starts collecting an extended list of events from that box.

### Creating workflows

You can use tags to create workflows and automations. For instance, you can configure an output (forwarder) to send all detections containing `VIP-sales` tag to Slack so that you can review them asap, while detections tagged as `sales` can be sent to an email address.

### Trigger Automations

Create a Yara scanning rule so that endpoints tagged as 'sales' are continuously scanned against the specific sets of Yara signatures.

## Adding Tags

Tags can be added to a sensor a few different ways:

1. Enrollment: the installation keys can optionally have a list of Tags that will get applied to sensors that use them.
2. Manually: using the API as described below, either manually by a human or through some other integration.
3. Detection & Response: automated detection and response rules can programatically add a tag (and check for tags).

### Manual API

Issue a `POST` to `/{sid}/tags` REST endpoint

### Detection & Response

In detection and response rules. To achieve this, in the response part of the detection & response rule, specify the add tag action. For example, to tag a device as DESKTOP, you would say:

```yaml
- action: add tag
tag: DESKTOP
```

## Removing Tags

### Manual API

Issue a `DELETE` to `/{sid}/tags` REST endpoint

### Detection & Response

In detection and response rules

### Manual in the web app

In the web app, click on the sensor in question to expand it. You will see the list of tags you can add/edit/remove.

## Checking Tags

### Manual API

Issue a `GET` to `/{sid}/tags` REST endpoint

### Detection & Response

In detection and response rules

## System Tags

We provide system level functionality with a few system tags.  Those tags are listed below for reference:

### lc:latest

When you tag a sensor with `lc:latest`, the sensor version currently assigned to the Organization will be ignored for that specific sensor, and the latest version of the sensor will be used instead. This means you can tag a representative set of computers in the Organization with the `lc:latest` tag in order to test-deploy the latest version and confirm no negative effects.

### lc:stable

When you tag a sensor with `lc:stable`, the sensor version currently assigned to the Organization will be ignored for that specific sensor, and the *stable* version of the sensor will be used instead. This means you can upgrade an organization as a whole, but leave a few specific sensors behind by assigning the lc:stable tag to them.

### lc:experimental

When you tag a sensor with `lc:experimental`, the sensor version currently assigned to the Organization will be ignored for that specific sensor. An experimental version of the sensor will be used instead. This tag is typically used when working with the LimaCharlie team to troubleshoot sensor-specific issues.

### lc:no_kernel

When you tag a sensor with `lc:no_kernel`, the kernel component will not be loaded on the host.

### lc:debug

When you tag a sensor with `lc:debug`, the debug version of the sensor currently assigned to the Organization will be used.

### lc:limit-update

When you tag a sensor with lc:limit-update, the sensor will not update the version it's running at run-time. The version will only be loaded when the sensor starts from scratch like after a reboot.

### lc:sleeper

When you tag a sensor with *lc:sleeper*, the sensor will keep its connection to the LimaCharlie Cloud, but will disable all other functionality to avoid any impact on the system. To wake up sensors from sleeper mode, set your organization's Quota to accommodate the number of sensors you want to activate, then remove the `lc:sleeper` tag from those sensors. For more details, see [Sleeper Deployments](endpoint-agent/sleeper.md).

Similar to agents, Sensors send telemetry to the LimaCharlie platform in the form of EDR telemetry or forwarded logs. Sensors are offered as a scalable, serverless solution for securely connecting endpoints of an organization to the cloud.

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.

## Programmatic Management

!!! info "Prerequisites"
    All programmatic examples require an API key with `sensor.tag` permissions. See [API Keys](../7-administration/access/api-keys.md) for setup instructions.

### List All Organization Tags

=== "REST API"

    ```bash
    curl -s -X GET "https://api.limacharlie.io/v1/tags/YOUR_OID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    tags = org.get_all_tags()
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    tags, err := org.GetAllTags()
    ```

=== "CLI"

    ```bash
    limacharlie tag list
    ```

### List Tags for a Sensor

=== "REST API"

    ```bash
    curl -s -X GET "https://api.limacharlie.io/v1/YOUR_SID/tags" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.sensor import Sensor

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    sensor = Sensor(org, "YOUR_SID")
    tags = sensor.get_tags()
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    sensor := org.GetSensor("YOUR_SID")
    tags, err := sensor.GetTags()
    ```

=== "CLI"

    ```bash
    limacharlie tag list --sid YOUR_SID
    ```

### Add a Tag to a Sensor

=== "REST API"

    ```bash
    curl -s -X POST "https://api.limacharlie.io/v1/YOUR_SID/tags" \
      -H "Authorization: Bearer $LC_JWT" \
      -d "tags=my-tag&ttl=3600"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.sensor import Sensor

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    sensor = Sensor(org, "YOUR_SID")
    sensor.add_tag("my-tag", ttl=3600)
    ```

=== "Go"

    ```go
    import (
        "time"
        limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"
    )

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    sensor := org.GetSensor("YOUR_SID")
    err := sensor.AddTag("my-tag", time.Hour)
    ```

=== "CLI"

    ```bash
    limacharlie tag add --sid YOUR_SID --tag my-tag --ttl 3600
    ```

### Remove a Tag from a Sensor

=== "REST API"

    ```bash
    curl -s -X DELETE "https://api.limacharlie.io/v1/YOUR_SID/tags" \
      -H "Authorization: Bearer $LC_JWT" \
      -d "tag=my-tag"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization
    from limacharlie.sdk.sensor import Sensor

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    sensor = Sensor(org, "YOUR_SID")
    sensor.remove_tag("my-tag")
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    sensor := org.GetSensor("YOUR_SID")
    err := sensor.RemoveTag("my-tag")
    ```

=== "CLI"

    ```bash
    limacharlie tag remove --sid YOUR_SID --tag my-tag
    ```

### Find Sensors by Tag

=== "REST API"

    ```bash
    curl -s -X GET "https://api.limacharlie.io/v1/tags/YOUR_OID/my-tag" \
      -H "Authorization: Bearer $LC_JWT"
    ```

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    sensors = org.find_sensors_by_tag("my-tag")
    ```

=== "Go"

    ```go
    import limacharlie "github.com/refractionPOINT/go-limacharlie/limacharlie"

    client, _ := limacharlie.NewClient(limacharlie.ClientOptions{
        OID:    "YOUR_OID",
        APIKey: "YOUR_API_KEY",
    }, nil)
    org, _ := limacharlie.NewOrganization(client)

    sensors, err := org.GetSensorsWithTag("my-tag")
    ```

=== "CLI"

    ```bash
    limacharlie tag find --tag my-tag
    ```

### Mass Add Tag by Selector

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    result = org.mass_tag('plat == "windows"', "my-tag", ttl=3600)
    ```

=== "CLI"

    ```bash
    limacharlie tag mass-add --selector 'plat == "windows"' --tag my-tag
    ```

### Mass Remove Tag by Selector

=== "Python"

    ```python
    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization

    client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
    org = Organization(client)
    result = org.mass_untag('plat == "windows"', "my-tag")
    ```

=== "CLI"

    ```bash
    limacharlie tag mass-remove --selector 'plat == "windows"' --tag my-tag
    ```

---

## See Also

- [D&R Rules with Tags](../3-detection-response/index.md)
- [Sensor Selectors](../8-reference/sensor-selector-expressions.md)
- [Python SDK](../6-developer-guide/sdks/python-sdk.md)
- [Go SDK](../6-developer-guide/sdks/go-sdk.md)
- [Compliance Frameworks](../9-ai-sessions/compliance/frameworks.md) -- Scope-tag conventions per framework (`cde` for PCI, `ephi-host` for HIPAA, `cui` for CMMC, `fisma-scope` for NIST 800-53, etc.). The compliance reviewer agents key their in-scope check off these tags.
