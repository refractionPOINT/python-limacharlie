# LimaCharlie.io CLI and Python API

![LimaCharlie.io](https://storage.googleapis.com/limacharlie-io/logo_fast_glitch.gif)

This Python library is a simple abstraction to the LimaCharlie.io REST API.

For more information on LimaCharlie.io: [https://limacharlie.io](https://limacharlie.io).

## Documentation
* Python API Doc: https://python-limacharlie.readthedocs.io/en/latest/
* General LimaCharlie Doc: https://doc.limacharlie.io/
* REST API: [https://api.limacharlie.io](https://api.limacharlie.io)

## Getting Started
The Python API uses the LimaCharlie.io REST API. The REST API currently
supports many more functions. If the Python is missing a function available
in the REST API that you would like to use, let us know at support@limacharlie.io.

### Installing
`pip install limacharlie`

### Credentials
Authenticating to use the SDK / CLI can be done in a few ways.

#### Logging In
The simplest is to login to an organization using an [API key](https://docs.limacharlie.io/docs/platform-management-api-keys).

Use `limacharlie login` to store credentials locally. You will need an `OID` (Organization ID) and an API key, both
of which you can get from the "REST API" section of the web interface.

The login interface supports named environments, or a default one used when no environment is selected.

To list available environments: `limacharlie use`.

Setting a given environment in the current shell session can be done like: `. <(limacharlie use dev-org)`.

You can also specify a `UID` (User ID) during login to use a *user* API key representing
the total set of permissions that user has (see User Profile in the web interface).

#### Environment Variables
You can use the `LC_OID` and `LC_API_KEY` and `LC_UID` environment variables to replace
the values used logging in. The environment variables will be used if no other credentials
are specified.

#### Credentials File
When using `limacharle login` functionality, credentials are stored in a plain text format
on a `~/.limacharlie` file on disk.

Credentials are stored in the following format:

```yaml
# top level / default credentials
api_key: xxx
oid: xxx
# optional, only needs to be set for user scopd api keys
uid: xxx

# Environment specific credentials which can be selected using "limacharlie use <environment>"
# command. For example: "limacharlie use org-2".
env:
  org-1:
    api_key: xxx
    oid: xxx
    # optional, only needs to be set for user scopd api keys
    # uid: xxx
  org-2:
    api_key: xxx
    oid: xxx
    # optional, only needs to be set for user scopd api keys
    # uid: xxx
```

If you manually manipulate this file, make sure you preserve the permissions and ownership
as orginally set by the CLI (600) so other users can't read it.

If you prefer not to store credentials in a plain text format in a file on disk, use an
alternative method for authentication (e.g. environment variables, as described above).

## Docker

Docker image with latest version of the tool is available at https://hub.docker.com/r/refractionpoint/limacharlie.

Example usage:

```bash
docker run refractionpoint/limacharlie:latest whoami

# If you already have a credential file locally, you can mount it inside the Docker container
docker run -v ${HOME}/.limacharlie:/root/.limacharlie:ro refractionpoint/limacharlie:latest whoami
```
## SDK

The root of the functionality in the SDK is from the `Manager` object. It holds the crendentials
and is tied to a specific Organization.

You can authenticate the `Manager` using an `oid` (and optionally a `uid`), along with either
a `secret_api_key` or `jwt` directly. Alternatively you can just use an environment name (as specified
in `limacharlie login`). If no creds are provided, the `Manager` will try to use the default environment
and credentials.

### Importing
```python
import limacharlie

YARA_SIG = 'https://raw.githubusercontent.com/Yara-Rules/rules/master/Malicious_Documents/Maldoc_PDF.yar'

# Create an instance of the SDK.
man = limacharlie.Manager()

# Get a list of all the sensors in the current Organization.
all_sensors = man.sensors()

# Select the first sensor in the list.
sensor = all_sensors[ 0 ]

# Tag this sensor with a tag for 10 minutes.
sensor.tag( 'suspicious', ttl = 60 * 10 )

# Send a task to the sensor (unidirectionally, not expecting a response).
sensor.task( 'os_processes' )

# Send a yara scan to that sensor for processes "evil.exe".
sensor.task( 'yara_scan -e *evil.exe ' + YARA_SIG )
```

### Use of gevent
Note that the SDK uses the `gevent` package which sometimes has issues with other
packages that operate at a low level in python. For example, Jupyter notebooks
may see freezing on importing `limacharlie` and require a tweak to load:

```json
{
 "display_name": "IPython 2 w/gevent",
 "language": "python",
 "argv": [
  "python",
  "-c", "from gevent.monkey import patch_all; patch_all(thread=False); from ipykernel.kernelapp import main; main()",
  "-f",
  "{connection_file}"
 ]
}
```

### Components
#### Manager
This is a the general component that provides access to the managing functions
of the API like querying sensors online, creating and removing Outputs etc.

#### Firehose
The `Firehose` is a simple object that listens on a port for LimaCharlie.io data.
Under the hood it creates a Syslog Output on limacharlie.io pointing to itself
and removes it on shutdown. Data from limacharlie.io is added to `firehose.queue`
(a `gevent Queue`) as it is received.

It is a basic building block of automation for limacharlie.io.

#### Spout
Much like the `Firehose`, the Spout receives data from LimaCharlie.io, the difference
is that the `Spout` does not require opening a local port to listen actively on. Instead
it leverages `stream.limacharlie.io` to receive the data stream over HTTPS.

A `Spout` is automatically created when you instantiate a `Manager` with the
`is_interactive = True` and `inv_id = XXXX` arguments in order to provide real-time
feedback from tasking sensors.

#### Sensor
This is the object returned by `manager.sensor( sensor_id )`.

It supports a `task`, `hostname`, `tag`, `untag`, `getTags` and more functions. This
is the main way to interact with a specific sensor.

The `task` function sends a task to the sensor unidirectionally, meaning it does not
receive the response from the sensor (if any). If you want to interact with a sensor
in real-time, use the interactive mode (as mentioned in the `Spout`) and use either
the `request` function to receive replies through a `FutureResults` object or the
`simpleRequest` to wait for the response and receive it as a return value.

#### Artifacts
The `Artifacts` is a helpful class to upload [Artifact Collection](https://docs.limacharlie.io/docs/telemetry-artifacts)
to LimaCharlie without going through a sensor.

#### Payloads
The `Payloads` can be used to manage various executable [payloads](https://docs.limacharlie.io/docs/telemetry-sensors-payloads)
accessible to sensors.

#### Replay
The `Replay` object allows you to interact with [Replay](https://docs.limacharlie.io/docs/replay)
jobs managed by LimaCharlie. These allow you to re-run [D&R Rules](https://docs.limacharlie.io/docs/platform-management-config-hive-dr-rules)
on historical data.

#### Search
The `Search` object allows you to perform an IOC search across multiple organizations.

#### SpotCheck
The `SpotCheck` object (sometimes called Fleet Check) allows you to manage an active (query sensors directly
as opposed to searching on indexed historical data) search for various IOCs on an organization's sensors.

#### Configs
The `Configs` is used to retrieve an organization's configuration as a config file, or apply
an existing config file to an organization. This is the concept of Infrastructure As Code.

#### Webhook
The `Webhook` object demonstrates handling webhooks emited by the LimaCharlie cloud, including
verifying the shared-secret signing of the webhooks.

### Examples:
* [Basic Manager Operations](samples/demo_manager.py)
* [Basic Firehose Operations](samples/demo_firehose.py)
* [Basic Spout Operations](samples/demo_spout.py)
* [Basic Integrated Operations](samples/demo_interactive_sensor.py)
* [Rules Config Syncing](limacharlie/sample_configs/)

## Command Line Interface
Many of the objects available as part of the LimaCharlie Python SDK also support various
command line interfaces.

#### Firehose
`python -m limacharlie.Firehose 1.2.3.4:9424 event -n firehose_test -t fh_test --oid c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`

Listens on interface `1.2.3.4`, port `9424` for incoming connections from LimaCharlie.io.
Receives only events from hosts tagged with `fh_test`.

#### Spout
`python -m limacharlie.Spout event --oid c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`

Behaves similarly to the Firehose, but instead of listenning from an internet accessible port, it
connects to the `stream.limacharlie.io` service to stream the output over HTTPS. This means the Spout
allows you to get ad-hoc output like the Firehose, but it also works through NATs and proxies.

It is MUCH more convenient for short term ad-hoc outputs, but it is less reliable than a Firehose for
very large amounts of data.

#### Configs
`limacharlie configs fetch --oid c82e5c17-d519-4ef5-a4ac-c454a95d31ca`

`limacharlie configs push --dry-run --oid c82e5c17-d519-4ef5-a4ac-c454a95d31ca`

The `fetch` command will get a list of the Detection & Response rules in your
organization and will write them to the config file specified or the default
config file `lc_conf.yaml` in YAML format.

Then `push` can upload the rules specified in the config file (or the default one)
to your organization. The optional `--force` argument will remove active rules not
found in the config file. The `--dry-run` simulates the sync and displayes the changes
that would occur.

The `--config` allows you to specify an alternate config file and the `--api-key` allows
you to specify a file on disk where the API should be read from (otherwise, of if `-` is
specified as a file, the API Key is read from STDIN).

All these capabilities are also supported directly by the `limacharlie.Configs` object.

The Sync functionality currently supports all common useful configurations. The `--no-rules` and
`--no-outputs` flags can be used to ignore one or the other in config files and sync. Additional
flags are also supported, see `limacharlie configs --help`.

To understand better the config format, do a `fetch` from your organization or have
a look at the [samples](limacharlie/sample_configs/). Notice the use of the `include`
statement. Using this statement you can combine multiple config files together, making
it ideal for the management of complex rule sets and their versioning.

#### Spot Checks
`python -m limacharlie.SpotCheck --no-macos --no-linux --tags vip --file c:\\evil.exe`

Used to perform Organization-wide checks for specific indicators of compromise. Available as a custom
API `SpotCheck` object or as a module from the command line. Supports many types of IoCs like file names,
directories, registry keys, file hashes and yara signatures.

For detailed usage: `python -m limacharlie.SpotCheck --help`

#### Search
`limacharlie search --help`
Shortcut utility to perform IOC searches across all locally configured organizations.

#### Artifact Upload
`limacharlie artifacts upload --help`
Shortcut utility to upload [Artifact Collection](https://docs.limacharlie.io/docs/telemetry-artifacts) directly to
LimaCharlie with just the CLI (no Agent).

#### Artifact Download
`limacharlie artifacts get_original --help`
Shortcut utility to download [Artifact Collection](https://docs.limacharlie.io/docs/telemetry-artifacts) in
LimaCharlie locally.

#### Replay
`limacharlie replay --help`
Shortcut utility to perform [Replay](https://docs.limacharlie.io/docs/replay) jobs from the CLI.

#### Detection & Response
`limacharlie dr --help`
Shortcut utility to manage Detection and Response rules over the CLI.

#### Events & Detections
`limacharlie events --help` and `limacharlie detections --help`
Print out to STDOUT events or detections matching the parameter.

#### List Sensors
`limacharlie sensors --selector '*'`
Print out all basic sensor information for all sensors matching the selector.

#### Extension
`limacharlie extension --help`
Shortcut utility to perform actions pertaining [Extensions](https://docs.limacharlie.io/docs/extensions) using just the CLI.

#### ARLs
`limacharlie get-arl --help`

Print out data returned from the given [ARL](https://docs.limacharlie.io/docs/reference-authentication-resource-locator).

Example:
```
limacharlie get-arl -a [github,Yara-Rules/rules/email]
```
