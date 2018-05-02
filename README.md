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

### Command Line Usage
#### Firehose
`python -m limacharlie.Firehose c82e5c17-d519-4ef5-a4ac-caa4a95d31ca 1.2.3.4:9424 event -n firehose_test -t fh_test`

Listens on interface `1.2.3.4`, port `9424` for incoming connections from LimaCharlie.io.
Receives only events from hosts tagged with `fh_test`.

#### Shell
`python -m limacharlie.Manager c82e5c17-d519-4ef5-a4ac-caa4a95d31ca`
