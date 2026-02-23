[Documentation](README.md) > Getting Started

# Getting Started

## Installation

```bash
pip install limacharlie
```

Docker:

```bash
docker run refractionpoint/limacharlie:latest --help

# Mount local credentials into the container
docker run -v ${HOME}/.limacharlie:/root/.limacharlie:ro refractionpoint/limacharlie:latest org info
```

## Quick Start

```bash
# New to LimaCharlie? Create an account directly from the CLI:
limacharlie auth signup

# Already have an account? Store credentials (API key):
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY

# -- or authenticate via browser (OAuth) --
limacharlie auth login --oauth --oid YOUR_ORG_ID

# Verify
limacharlie auth whoami

# Explore
limacharlie org info
limacharlie sensor list
limacharlie discover
```

## First Steps

Once authenticated, try these commands to explore your organization:

```bash
# View organization details
limacharlie org info

# List sensors in your fleet
limacharlie sensor list

# List D&R rules
limacharlie dr list

# Browse all commands by use-case
limacharlie discover
limacharlie discover --profile detection_engineering

# Get help on any command
limacharlie dr create --help
limacharlie dr create --ai-help
```

## Using the SDK

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

# Uses default credentials (~/.limacharlie or env vars)
client = Client()
org = Organization(client)

# View org info
print(org.get_info())

# List sensors
for sensor in org.list_sensors():
    print(sensor["hostname"], sensor["sid"])
```

## Next Steps

- [Authentication](authentication.md) — All auth methods and credential management
- [CLI Overview](cli/README.md) — Global options, output formats, filtering
- [SDK Overview](sdk/README.md) — Architecture and class reference
