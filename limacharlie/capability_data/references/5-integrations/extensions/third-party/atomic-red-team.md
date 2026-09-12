# Atomic Red Team

**Atomic Red Team** is a library of tests mapped to the MITRE ATT&CK framework, provided by Red Canary. With this Extension, LimaCharlie users can use Atomic Red Team to quickly, portably, and reproducibly test their environments.

See [the Atomic Red Team project site](https://atomicredteam.io/) for more information.

## Enabling the Atomic Red Team Extension

Enabling Atomic Red Team can be done within the LimaCharlie **Marketplace**, or at [this link](https://beta.app.limacharlie.io/add-ons/extension-detail/ext-atomic-red-team).

Under the Organization dropdown, select a tenant (organization) you want to subscribe to Atomic Red Team and click subscribe.

Please note that Extensions are applied on a per-tenant basis. If you have multiple organizations you want to subscribe to Atomic Red Team, you will need to subscribe each organization to the extension separately.

## Supported Platforms

The extension supports sensors on **Windows**, **Linux**, and **macOS**. Sensors must be online for tests to run.

On Linux and macOS, the extension installs PowerShell Core (`pwsh`) automatically during the Prepare step if it is not already present.

## Three-Step Workflow

The extension uses a three-step workflow: **Prepare Host** → **Run Tests** → **Cleanup Host**. This matches how the upstream Atomic Red Team project is intended to be used.

### Step 1: Prepare Host

Before running any tests, you must prepare the target sensor. This installs the Atomic Red Team framework and its dependencies.

**What it does:**

- **Windows**: adds a Windows Defender exclusion for `C:\AtomicRedTeam` (best-effort — Tamper Protection may block it), installs NuGet, the `powershell-yaml` module, and the Invoke-AtomicRedTeam framework with atomics.
- **Linux**: installs PowerShell Core via the system package manager (apt/dnf), then installs the framework to `/opt/AtomicRedTeam`.
- **macOS**: installs PowerShell Core via the official `.pkg` installer, then installs the framework to `/opt/AtomicRedTeam`.

You only need to prepare a host once. After that, you can run as many tests as you want.

### Step 2: Run Tests

Select one or more MITRE ATT&CK technique IDs from the dropdown and click Run. Tests execute sequentially — each test checks prerequisites, installs them if needed, executes the technique, and optionally runs the atomic cleanup step.

The **Clean** option controls whether each test's atomic cleanup runs after execution (reverting technique-specific changes). This is separate from the host-level Cleanup step.

If multiple tests are selected, they are chained automatically. Each test completion triggers the next via a callback. A single `job_id` tracks the entire run.

### Step 3: Cleanup Host

When you are done testing, run Cleanup to reverse the changes made by Prepare:

- **Windows**: removes the Defender exclusion and deletes `C:\AtomicRedTeam`.
- **Linux/macOS**: deletes `/opt/AtomicRedTeam`.
- All platforms: uninstalls the `powershell-yaml` PowerShell module.

Cleanup is best-effort — if some components can't be removed (e.g., files locked), it reports partial success with details.

## Checking Results

When the extension is enabled, you will see an Adapter named `ext-atomic-red-team`. This adapter receives all extension activity as webhook events:

| Event | When |
|-------|------|
| `prepare_started` / `prepare_success` / `prepare_failed` | Prepare Host lifecycle |
| `run_started` / `test_result` / `run_success` / `run_failed` | Test execution (one `test_result` per technique) |
| `cleanup_started` / `cleanup_success` / `cleanup_failed` | Cleanup Host lifecycle |

Each event includes a `job_id` for correlation and the sensor ID. The `test_result` event includes the technique ID, execution status, and a base64-encoded log of the test output.

Within the **Timeline** of the sensor you ran a test on, you will also find `RECEIPT` events that contain the raw execution output (STDOUT, STDERR, exit code).

Between webhook events in the `ext-atomic-red-team` adapter and `RECEIPT` events on the sensor, you can correlate and identify successful and failed tests.

## Notes

- The Defender exclusion on Windows is best-effort. If Tamper Protection blocks it, the extension still installs the framework and reports a warning. Defender may quarantine some atomic test files.
- Some techniques include many sub-tests (e.g., T1082 on Windows has 17+). Individual sub-tests may time out after 120 seconds — this is an upstream `Invoke-AtomicTest` default, not a limitation of the extension.
- The list of available techniques is loaded from the upstream Atomic Red Team index at extension startup.
