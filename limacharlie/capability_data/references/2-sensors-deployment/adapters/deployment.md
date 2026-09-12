# Adapter Deployment

Adapters can be deployed in one of two ways:

- **On-prem**, Adapters utilize the LC Adapter binary to ingest a data source and forward it to LimaCharlie.
- **Cloud-to-cloud**, connects the LimaCharlie cloud directly with your cloud source and automatically ingests data.

Which Adapter Do I Use for Cloud Data?

You can use on-prem adapters to forward cloud data, or you could acquire the same data with a cloud-to-cloud connection. So, which one to use?

The answer lies in _how_ you want to send your data to LimaCharlie. Are you OK with configuring a connector from our platform, or would you rather use a bastion box in between? Either way works for us!

The data ingested from adapters is parsed/mapped into JSON by LimaCharlie, according to the parameters you provided, unless using a pre-defined format.

## Adapter Binaries

Software-based, or "on-prem" adapters are available in the following formats:

### POSIX-compliant

- [AIX ppc64](https://downloads.limacharlie.io/adapter/aix/ppc64)
- [Linux (Generic) 64-bit](https://downloads.limacharlie.io/adapter/linux/64)
- [Linux (Generic) arm](https://downloads.limacharlie.io/adapter/linux/arm)
- [Linux (Generic) arm64](https://downloads.limacharlie.io/adapter/linux/arm64)
- [FreeBSD 64-bit](https://downloads.limacharlie.io/adapter/freebsd/64)
- [OpenBSD 64-bit](https://downloads.limacharlie.io/adapter/openbsd/64)
- [NetBSD 64-bit](https://downloads.limacharlie.io/adapter/netbsd/64)
- [Solaris 64-bit](https://downloads.limacharlie.io/adapter/solaris/64)

### macOS

- [macOS x64](https://downloads.limacharlie.io/adapter/mac/64)
- [macOS arm64](https://downloads.limacharlie.io/adapter/mac/arm64)

### Windows

- [Windows x64](https://downloads.limacharlie.io/adapter/windows/64)

### Docker

- <https://hub.docker.com/r/refractionpoint/lc-adapter>

Another platform?

If you need support for a specific platform, or require more information about supported platforms, please [let us know](https://www.limacharlie.io/contact).

## On-Prem + Cloud Management

LimaCharlie Adapters deployed manually (on-prem) also support cloud-based management. This makes the deployment of the adapter extremely easy while also making it easy to update the configs remotely after the fact. This is particularly critical for service providers that may be deploying adapters on customer networks where gaining access to the local adapter may be difficult.

To accomplish this, you need the `externaladapter.*` permissions.

### Preparing

The first step of deploying this way is to create a new External Adapter record. These are found in the `external_adapter` Hive or under the Sensors section of the web app.

The content of an external adapter is exactly the same as a traditional [adapter configuration](usage.md) in YAML. It describes what you want your external adapter to do, like collect from file, operate as a syslog server etc. For example:

```yaml
sensor_type: syslog
syslog:
    client_options:
        buffer_options: {}
        hostname: test-syslog
        identity:
            installation_key: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
            oid: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
        mapping: {}
        platform: text
        sensor_seed_key: test-syslog
    port: 4242
```

Once your external adapter record is created, take note of the `GUID` (Globally Unique ID) found under the `sys_mtd` section of the JSON record, or on the right-hand side of the record view in the web app

.

This `GUID` is a shared secret value you will use in the deployed adapter to reference it to the record it should update and operate from.

### Deploying

Now that the configuration of the adapter is ready, you can deploy the adapter on-prem according to the [normal process](usage.md). The only difference is that instead of running it with the full configuration locally, you can run it with the `cloud` collection method like this:

```bash
./lc_adapter cloud conf_guid=XXXXXXXXXXXXXXXXXXXXx oid=YYYYYYYYYYYYYYYYYYY
```

This will start the adapter telling it to fetch the configuration it requires from the cloud based on the Organization ID (your tenant in LC) and the `GUID` of the record it should use.

From this point on, updating the record in LimaCharlie will automatically reconfigure the adapter on-prem, within about 1 minute of the change.

Adapters serve as flexible data ingestion mechanisms for both on-premise and cloud environments.
