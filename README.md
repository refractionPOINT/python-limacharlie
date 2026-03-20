# LimaCharlie Python SDK & CLI

![LimaCharlie.io](https://storage.googleapis.com/limacharlie-io/logo_fast_glitch.gif)

Python SDK and command-line interface for the [LimaCharlie](https://limacharlie.io) endpoint detection and response platform.

* **[Documentation](doc/README.md)** — CLI reference, SDK guide, authentication
* [Platform Docs](https://doc.limacharlie.io/) | [REST API](https://api.limacharlie.io) | [Issues](https://github.com/refractionPOINT/python-limacharlie)

## Installation

```bash
pip install limacharlie
```

```bash
docker run refractionpoint/limacharlie:latest --help
```

See [Getting Started](doc/getting-started.md) for Docker credential mounting and first steps.

## Quick Start

```bash
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY
limacharlie auth whoami
limacharlie org info
limacharlie sensor list
```

See [Authentication](doc/authentication.md) for OAuth, environments, credential resolution, JWT caching, and config directory migration.

## Documentation

| Guide | Topics |
|-------|--------|
| [Getting Started](doc/getting-started.md) | Installation, Docker, first steps |
| [Authentication](doc/authentication.md) | API keys, OAuth, environments, JWT caching, config migration |
| [CLI Overview](doc/cli/README.md) | Command pattern, output formats, filtering, discovery |
| [SDK Overview](doc/sdk/README.md) | Architecture, setup, class reference |

Full reference: [doc/README.md](doc/README.md)

## Development

### Setup

```bash
git clone https://github.com/refractionPOINT/python-limacharlie.git
cd python-limacharlie
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The editable install (`-e`) means changes to the source code take effect immediately without reinstalling.

### Running the CLI

After the editable install, the `limacharlie` command is available in your venv:

```bash
limacharlie --version
limacharlie --help
limacharlie sensor list --help
```

### Running Tests

Unit tests run without any credentials or network access:

```bash
# All unit tests
pytest tests/unit/ -v

# Single test file
pytest tests/unit/test_client.py -v

# Single test case
pytest tests/unit/test_client.py::TestClientInit::test_creates_with_explicit_creds -v
```

Integration tests require a real LimaCharlie organization:

```bash
pytest tests/integration/ --oid YOUR_ORG_ID --key YOUR_API_KEY -v
```

### Building

```bash
pip install build && python -m build
pip install dist/limacharlie-*-py3-none-any.whl && limacharlie version
```

## Releasing

Releases are published to [PyPI](https://pypi.org/project/limacharlie/) automatically via GitHub Actions when a version tag is pushed. The package version is derived from the git tag using `setuptools-scm` — there is no hardcoded version to bump.

```bash
git tag 5.1.0
git push origin 5.1.0
```

The workflow runs unit tests, builds the package, and publishes to PyPI using [Trusted Publishers](https://docs.pypi.org/trusted-publishers/) (OIDC) — no API tokens or secrets required. See [`.github/workflows/publish-to-pypi.yml`](.github/workflows/publish-to-pypi.yml) for details.
