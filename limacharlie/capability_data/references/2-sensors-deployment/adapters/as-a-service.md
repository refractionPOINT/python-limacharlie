# Adapters as a Service

In some cases, users may need to install the LimaCharlie Adapter with persistence, to ensure that data collection survives a reboot and/or other disruptions.

To accommodate this need, the LimaCharlie adapter can be installed as a service.

## Service Installation

### Windows

To install the Windows LimaCharlie adapter as a service, insert the `-install:<service_name>` flag in the command line, following the adapter executable name.

For example:

`./lc_adapter.exe azure_event_hub client_options.identity.installation_key=...`

would be replaced with

`./lc_adapter.exe -install:azure_collection azure_event_hub client_options.identity.installation_key=...`

This would create a service named `azure_collection` with the adapter config.

Remember, adapter configurations can be provided via two methods:

- In the command line, as part of a list of flags
- Via a YAML config file

**Note:** The service will point to `lc_adapter.exe` based on its path at the creation of the service. If you wish to move the adapter to a permanent location, please do so before creating the service.

### Linux / systemd

To install a LimaCharlie adapter as a service on a Linux system with systemd, you will need a service file, the adapter binary, and your adapter command.

#### Adapter Binary

Download one of the [adapter binaries](deployment.md) and apply the necessary permissions:

```bash
wget -O /path/to/adapter-directory/lc-adapter $ADAPTER_BINARY_URL
chmod +x /path/to/adapter-directory/lc-adapter
```

#### Service File - /etc/systemd/system/limacharlie-adapter-name.service

You will replace `$ADAPTER_COMMAND` in the service file with your actual adapter command below.

```bash
[Unit]
Description=LC Adapter Name
After=network.target

[Service]
Type=simple
ExecStart=$ADAPTER_COMMAND
WorkingDirectory=/path/to/adapter-directory
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lc-adapter-name

[Install]
WantedBy=multi-user.target
```

#### Adapter Command

Your adapter command may differ depending on your use case--this is an example of a [file](types/file.md) adapter to ingest logs from a JSON file.

```bash
/path/to/adapter-directory/lc-adapter file file_path=/path/to/logs.json client_options.identity.installation_key=<INSTALLATION KEY> client_options.identity.oid=<ORG ID> client_options.platform=json client_options.sensor_seed_key=<SENSOR SEED KEY> client_options.mapping.event_type_path=<EVENT TYPE FIELD> client_options.hostname=<HOSTNAME>
```

#### Enable and Start the Service

```bash
sudo systemctl enable lc-adapter-name
sudo systemctl start lc-adapter-name
sudo systemctl status lc-adapter-name
```

## Service Uninstallation

### Windows

To remove a Windows LimaCharlie Adapter service, use the `-remove:<service_name>` flag.

### Linux

If your service is running with a systemd script, you can disable and remove it with the following:

```bash
sudo systemctl stop lc-adapter-name
sudo systemctl disable lc-adapter-name
sudo rm /etc/systemd/system/lc-adapter-name.service
sudo rm /path/to/adapter-directory/lc-adapter
```
