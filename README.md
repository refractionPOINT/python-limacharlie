# LimaCharlie.io Python API

This Python library is a simple abstraction to the LimaCharlie.io REST API.
For more information on LimaCharlie.io: [https://limacharlie.io](https://limacharlie.io).
For more information on the REST API: [https://api.limacharlie.io](https://api.limacharlie.io).

## Documentation
* Python API Doc: https://python-limacharlie.readthedocs.io/en/latest/
* General LimaCharlie Doc: http://doc.limacharlie.io/

## Overview Usage
The Python API uses the LimaCharlie.io REST API. The REST API currently
supports many more functions. If the Python is missing a function available
in the REST API that you would like to use, let us know at support@limacharlie.io.

### Installing
`pip install limacharlie`

### Credentials
All APIs/modules accept specific Organization ID (OID) and API Keys programatically.
However it is often convenient to provide those via environment variables or
files. Therefore, if the OID and API Key provided is `None`, credentials will be
acquired in the following order globally:
1. `LC_OID` and `LC_API_KEY` environment variables.
1. `LC_CREDS_FILE` environment variable points to a YAML file with `oid: <OID>` and `api_key: <KEY>`.
1. Assumes a creds file (like #2) is present at `~/.limacharlie`.

To set your credentials in your home directory's `.limacharlie` file, use `limacharlie login`, all
future API / CLI commands in the future will automatically have access to those credentials.

The "login" mechanism supports multiple environments.

Listing environments:
```
limacharlie use
```
and then selecting a specific environment:
```
. <(limacharlue use my-home-org)
```
note the use of `. <()` to source the output from the `use my-home-org` command which outputs an `export` command.

### Importing
```python
import limacharlie

OID = 'Your-Org-ID'
API_KEY = 'Your-Secret-API-Key'
YARA_SIG = 'https://raw.githubusercontent.com/Yara-Rules/rules/master/Malicious_Documents/Maldoc_PDF.yar'

man = limacharlie.Manager( OID, API_KEY )
all_sensors = man.sensors()
sensor = all_sensors[ 0 ]
sensor.tag( 'suspicious', ttl = 60 * 10 )
sensor.task( 'os_processes' )
sensor.task( 'yara_scan -e *evil.exe ' + YARA_SIG )
```

### Components
#### Manager
This is a the general component that provides access to the managing functions
of the API like querying sensors online, creating and removing Outputs etc.

#### Firehose
The firehose is a simple object that listens on a port for LimaCharlie.io data.
Under the hood it creates a Syslog Output on limacharlie.io pointing to itself
and removes it on shutdown. Data from limacharlie.io is added to `firehose.queue`
(a `gevent Queue`) as it is received.

It is a basic building block of automation for limacharlie.io.

#### Sensor
This is the object returned by `manager.sensor( sensor_id )`.

It supports a `task`, `tag`, `untag` and `getTags` functions. This
is the main way to interact with a specific sensor.

#### Integrated Behavior
This mode is available by specifying an `inv_id` and `is_interactive = True` to a
Manager object. It makes the Manager setup the relevant comms channels so that any
Sensor objects it produces support the `.request()` function which behaves like the
`.task()` function but it also returns a `FutureResponses` object that is a proxy
for any responses from the task.

For a better idea on usage see [the demo](limacharlie/demo_interactive_sensor.py).

### Command Line Usage
Some Python API classes support being executed directly from the command line
to provide easier access to some of the capabilities.

#### Firehose
`limacharlie.Firehose 1.2.3.4:9424 event -n firehose_test -t fh_test --oid c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`

Listens on interface `1.2.3.4`, port `9424` for incoming connections from LimaCharlie.io.
Receives only events from hosts tagged with `fh_test`.

#### Spout
`limacharlie.Spout event --oid c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`

Behaves similarly to the Firehose, but instead of listenning from an internet accessible port, it
connects to the `output.limacharlie.io` service to stream the output over HTTP. This means the Spout
allows you to get ad-hoc output like the Firehose, but it also works through NATs and proxies.

It is MUCH more convenient for short term ad-hoc outputs, but it is less reliable than a Firehose for
very large amounts of data.

#### Shell
`limacharlie.Manager --oid c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`

Starting the `Manager` module directly starts an interactive shell to limacharlie.io.

#### Config Syncing
`limacharlie.Sync fetch --oid c82e5c17-d519-4ef5-a4ac-c454a95d31ca`

`limacharlie.Sync push --dry-run --oid c82e5c17-d519-4ef5-a4ac-c454a95d31ca`

The `fetch` command will get a list of the Detection & Response rules in your
organization and will write them to the config file specified or the default
config file `LCConf` in YAML format.

Then `push` can upload the rules specified in the config file (or the default one)
to your organization. The optional `--force` argument will remove active rules not
found in the config file. The `--dry-run` simulates the sync and displayes the changes
that would occur.

The `--config` allows you to specify an alternate config file and the `--api-key` allows
you to specify a file on disk where the API should be read from (otherwise, of if `-` is
specified as a file, the API Key is read from STDIN).

All these capabilities are also supported directly by the `limacharlie.Sync` object.

The Sync functionality currently supports D&R rules as well as Outputs. The `--no-rules` and
`--no-outputs` flags can be used to ignore one or the other in config files and sync.

To understand better the config format, do a `fetch` from your organization or have
a look at the [samples](limacharlie/sample_configs/). Notice the use of the `include`
statement. Using this statement you can combine multiple config files together, making
it ideal for the management of complex rule sets and their versioning.

#### Spot Checks
`limacharlie.SpotCheck --no-macos --no-linux --tags vip --file c:\\evil.exe`

Used to perform Organization-wide checks for specific indicators of compromise. Available as a custom
API `SpotCheck` object or as a module from the command line. Supports many types of IoCs like file names,
directories, registry keys, file hashes and yara signatures.

For detailed usage: `limacharlie.SpotCheck --help`

### Examples:
* [Basic Manager Operations](limacharlie/demo_manager.py)
* [Basic Firehose Operations](limacharlie/demo_firehose.py)
* [Basic Spout Operations](limacharlie/demo_spout.py)
* [Basic Integrated Operations](limacharlie/demo_interactive_sensor.py)
* [Rules Config Syncing](limacharlie/sample_configs/)
