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

### Importing
```python
import limacharlie

OID = 'Your-Org-ID'
API_KEY = 'Your-Secret-API-Key'
YARA_SIG = 'https://raw.githubusercontent.com/Yara-Rules/rules/master/Malicious_Documents/Maldoc_PDF.yar'

man = limacharlie.Manager( OID, API_KEY )
all_sensors = man.sensors()
sensor = man.sensor( all_sensors[ 0 ] )
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

#### Hunter
This is a parent class to inherit from to construct complex automation flows
that include both interaction with limacharlie.io, sensors as well as response events
from those sensors.

### Command Line Usage
Some Python API classes support being executed directly from the command line
to provide easier access to some of the capabilities.

#### Firehose
`python -m limacharlie.Firehose c82e5c17-d519-4ef5-a4ac-caa4a95d31ca 1.2.3.4:9424 event -n firehose_test -t fh_test`

Listens on interface `1.2.3.4`, port `9424` for incoming connections from LimaCharlie.io.
Receives only events from hosts tagged with `fh_test`.

#### Shell
`python -m limacharlie.Manager c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`

Starting the `Manager` module directly starts an interactive shell to limacharlie.io.

### Examples:
* [Basic Manager Operations](limacharlie/demo_manager.py)
* [Basic Firehose Operations](limacharlie/demo_firehose.py)
* [Basic Hunter Operations](limacharlie/demo_hunter.py)
