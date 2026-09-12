# Runner Environment

Every AI Session executes inside a managed container image — the **session runner** — that LimaCharlie pre-builds with a fixed set of CLI tools, language runtimes, and reference data. This page documents what is on `PATH` so you can decide which tools to expose to an agent in `allowed_tools` (or block in `denied_tools`) without having to read the Dockerfile.

The runner is a Debian Bookworm slim image. The agent process runs as a non-root `claude` user out of the `/workspace` directory. Anything listed below is available as a normal shell command from inside `Bash` tool calls, gated by the session's [tool permissions](tool-permissions.md).

!!! note
    This list is the contract the runner image ships with — but tool **availability** is not the same as tool **authorization**. Even when a CLI is pre-installed, the agent still needs an `allowed_tools` entry such as `Bash(gcloud:*)` (or a bare `Bash`) before it can invoke it, and any required credentials must be supplied via the session's `env` or fetched from a Hive secret at runtime.

## Cloud provider CLIs

| Command | Tool | Notes |
|---|---|---|
| `gcloud` | Google Cloud CLI | Includes `gsutil`, `bq`, and the standard component set. |
| `aws` | AWS CLI v2 | Installed under `/usr/local/aws-cli`. |
| `az` | Azure CLI | Installed under `/opt/az`. |
| `doctl` | DigitalOcean CLI | |
| `vultr-cli` | Vultr CLI | |

## Source control & developer tooling

| Command | Tool | Notes |
|---|---|---|
| `git` | Git | |
| `gh` | GitHub CLI | Authenticate with a token in the session `env` (e.g. `GH_TOKEN`). |
| `node`, `npm` | Node.js 20.x | Used by `claude` and `m365`. |
| `python3`, `pip`, `pipx` | Python 3 + pipx | Activated venv lives at `/opt/venv` (see [Python environment](#python-environment)). |
| `jq` | JSON processor | |
| `tree`, `less`, `groff`, `unzip`, `tar`, `wget`, `curl` | Standard Unix utilities | |

## Identity, secrets & remote access

| Command | Tool | Notes |
|---|---|---|
| `op` | 1Password CLI | |
| `sdm` | StrongDM CLI | |
| `tailscale` | Tailscale | |
| `m365` | Microsoft 365 CLI | Installed globally via `npm`. |

## Security tooling

| Command | Tool | Notes |
|---|---|---|
| `sublime` | [Sublime Security CLI](https://docs.sublime.security/docs/sublime-cli) | Email security analysis. |
| `chkp_harmony_endpoint_management_cli` | [Check Point Harmony Endpoint Management CLI](https://github.com/CheckPointSW/harmony-endpoint-management-cli) | Pass credentials via `CP_CI_CLIENT_ID`, `CP_CI_ACCESS_KEY`, `CP_CI_GATEWAY`. |
| `mmdblookup` | MaxMind DB lookup (`mmdb-bin`) | GeoLite2 City + ASN databases mounted at `/usr/share/GeoIP/`. May be absent in local-built images; the SDK bridge advertises GeoIP capabilities only when the databases exist. |

## Binary analysis

| Command / Path | Tool | Notes |
|---|---|---|
| `lcre` | [LCRE](https://github.com/refractionPOINT/lcre) | LimaCharlie Reverse Engineering helper binary. Ghidra scripts at `/opt/lcre/scripts/ghidra` (also exposed as `LCRE_SCRIPTS_PATH`). |
| `analyzeHeadless` | Ghidra 11.0.3 | Installed at `/opt/ghidra` (also `GHIDRA_HOME`). `support/` is on `PATH`, so headless invocations work directly. Backed by OpenJDK 17 JRE (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`). |

## LimaCharlie & Claude CLIs

| Command | Tool | Notes |
|---|---|---|
| `limacharlie` | LimaCharlie CLI v2 (Python) | Installed in the `/opt/venv` Python environment from the [`cli-v2` branch](https://github.com/refractionPOINT/python-limacharlie/tree/cli-v2). For D&R-driven sessions, agent-scoped credentials are pre-injected — see [D&R-Driven Sessions](dr-sessions.md). |
| `claude` | [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) | The same upstream CLI the runner orchestrates internally. Agents can shell out to it for sub-invocations when needed. |

## Python environment

The container ships an activated Python virtual environment at `/opt/venv` (placed first on `PATH` for the `claude` user). It pre-installs:

- `claude-agent-sdk` — the SDK the runner orchestrator drives.
- `limacharlie` — the LimaCharlie Python SDK and `limacharlie` command, from the `cli-v2` branch.
- `chkp-harmony-endpoint-management-cli` and `sublime-cli` — installed in dedicated pipx-managed venvs and exposed via `/usr/local/bin/` symlinks (see the security tooling table above).

Plain `pip install <pkg>` from inside an agent session installs into `/opt/venv` and is immediately importable.

## Reference data on disk

| Path | Contents |
|---|---|
| `/workspace/documentation/` | Full clone of [refractionPOINT/documentation](https://github.com/refractionPOINT/documentation) (this site's source). Useful for `Read`/`Grep`-based lookups without a `WebFetch` round-trip. |
| `/workspace/lc-ai/ai-agents/`, `/workspace/lc-ai/ai-teams/` | Reference catalogue of existing AI agent and team definitions from the [lc-ai](https://github.com/refractionPOINT/lc-ai) repository — useful when an agent is asked to design or modify another agent. |
| `/opt/lc-essentials/`, `/opt/lc-advanced-skills/`, `/opt/lc-fundamentals/` | The three first-party Claude Code plugins from `lc-ai/marketplace/plugins/`. The skills they contain are loaded automatically when the corresponding plugin is enabled for the session. |

## Stability of this list

The runner image is rebuilt and re-tagged on every release of `ai-sessions`. CLI tools are pinned to specific versions in the Dockerfile and only change when that pin is bumped — they will not silently disappear or get downgraded between sessions on the same image tag. Adding a new CLI to the runner is a code change in [`docker/Dockerfile.session-runner`](https://github.com/refractionPOINT/ai-sessions/blob/master/docker/Dockerfile.session-runner) and ships in the next image build.

## See also

- [Tool Permissions & Profiles](tool-permissions.md) — how to authorize the agent to actually call any of these via `Bash(<prefix>:*)`.
- [D&R-Driven Sessions](dr-sessions.md) and [User Sessions](user-sessions.md) — how sessions are launched and how `env` / Hive secrets get into the runner.
- [Alternative Providers](alternative-providers.md) — Bedrock and Vertex configuration; relies on `aws`/`gcloud` credentials available in the same runner.
