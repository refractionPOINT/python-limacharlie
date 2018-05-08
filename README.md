# LimaCharlie.io Python API

This Python library is a simple abstraction to the LimaCharlie.io REST API.
For more information on LimaCharlie.io: [https://limacharlie.io](https://limacharlie.io).
For more information on the REST API: [https://api.limacharlie.io](https://api.limacharlie.io).

## Overview Usage

### Installing
`sudo python ./setup.py develop`

### Importing
```python
import limacharlie

OID = 'Your-Org-ID'
API_KEY = 'Your-Secret-API-Key'

man = limacharlie.Manager( OID, API_KEY )
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

### Command Line Usage
#### Firehose
`python -m limacharlie.Firehose c82e5c17-d519-4ef5-a4ac-caa4a95d31ca 1.2.3.4:9424 event -n firehose_test -t fh_test`

Listens on interface `1.2.3.4`, port `9424` for incoming connections from LimaCharlie.io.
Receives only events from hosts tagged with `fh_test`.

#### Shell
`python -m limacharlie.Manager c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`

Starting the `Manager` module directly starts an interactive shell to limacharlie.io.