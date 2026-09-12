# USB Data Loss Prevention

## Overview

The DLP extension provides fleet-wide USB device control. A USB DLP policy puts an endpoint in one of two modes:

- **Permissive** — every USB mass storage device is allowed. This is the state of an endpoint that has never been given a policy.
- **Enforcing** — USB mass storage devices are blocked, except those whose serial number you have explicitly allowlisted.

Policy is **declarative**. You describe the desired state once in the extension configuration, and it is reconciled onto every matching endpoint each time that endpoint syncs. There is no per-endpoint state to maintain and no tasking to re-run, and the policy is re-applied automatically after an agent restart.

Only USB mass storage is in scope. Other USB peripherals — keyboards, mice, cameras, printers — are neither listed nor blocked.

## Requirements

- The DLP extension enabled on the Organization — see [Enabling the DLP extension](#enabling-the-dlp-extension). The endpoint commands further down this page are part of the agent and work without it, but centrally managed policy does not: nothing is reconciled onto an endpoint until the extension is subscribed.
- Endpoint agent **5.3.1** or higher. USB DLP itself has been available since agent 5.0, but only 5.3.1 and above accept centrally managed policy. [Upgrade](../../../2-sensors-deployment/endpoint-agent/versioning-upgrades.md) if necessary.
- Windows, macOS, or Linux.
- The agent's kernel component must be installed and running. Blocking happens below user space — a filter driver on Windows, a system extension on macOS, a kernel module on Linux — so an agent deployed in user-mode-only cannot enforce a USB policy.

## Enabling the DLP extension

Navigate to the [DLP extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-dlp) in the Add-Ons marketplace, choose the target Organization, and select **Subscribe**.

Subscribing installs a single managed D&R rule, `ext-dlp-sync`, in your Organization's `dr-managed` hive, tagged `lc:system` and `ext:dlp`. That rule is what triggers reconciliation on each endpoint sync. Leave it in place: the extension re-creates it if it drifts, and removes it when you unsubscribe.

!!! note
    Subscribing on its own changes nothing. Until you add a policy, every endpoint matches no policy and is left untouched.

## Configuring policies

Open the extension's **Configuration** view. The configuration is one ordered list, **DLP Policies**. Each policy has four fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `platforms` | list of platform (`windows`, `macos`, `linux`) | The endpoint must run **one of** these platforms. Empty matches any platform. |
| `tags` | list of sensor tag | The endpoint must carry **all** of these tags. Empty matches any endpoint. |
| `mode` | `permissive` or `enforcing` | The USB DLP mode to apply. Leave unset to match endpoints and deliberately leave them unmanaged. |
| `usb_allowlist` | list of USB serial numbers | Devices allowed while in `enforcing` mode. |

### Targeting

Policies are evaluated **top to bottom, first match wins**. For each endpoint, the first policy whose `platforms` and `tags` filters are satisfied by the platform and tags that endpoint reports is the policy that applies; the rest are ignored.

- An endpoint matching **no** policy is left unmanaged. The extension never touches its USB configuration.
- A policy with **no** `platforms` and **no** `tags` matches every endpoint. Use it as a fleet-wide default and place it **last** — anything below it is unreachable.
- Put narrow policies above broad ones.

There is no per-sensor targeting field — policies cannot reference a Sensor ID directly. To scope a policy to a single endpoint, give that sensor a [tag](../../../2-sensors-deployment/sensor-tags.md) nothing else carries and target the tag:

```yaml
policies:
  # One specific endpoint: its own allowlist.
  - tags: [usb-exception-finance-01]
    mode: enforcing
    usb_allowlist:
      - 0123456789ABCDEF
  # Everyone else: locked down.
  - mode: enforcing
```

Because evaluation is first-match-wins, the single-sensor policy must sit **above** the broader one.

The same policy list, viewed as YAML:

```yaml
policies:
  # Windows workstations: only two approved drives.
  - platforms: [windows]
    tags: [workstation]
    mode: enforcing
    usb_allowlist:
      - 0123456789ABCDEF
      - AA00BB11CC22DD33
  # Kiosks, any platform: USB storage stays open.
  - tags: [kiosk]
    mode: permissive
  # Fleet-wide default: no USB mass storage at all.
  - mode: enforcing
```

### Points to watch

- An `enforcing` policy with an empty `usb_allowlist` blocks **all** USB mass storage on every endpoint it matches. That is a valid configuration — just confirm it is the one you meant.
- Serial numbers may not be empty or contain whitespace. The configuration is rejected when it is saved if they do.
- `mode` accepts only `permissive` and `enforcing`. Leaving it unset is how you exclude a matched set of endpoints from management without deleting the policy.
- Allowlist entries do not expire. There is no time-limited (TTL) allowlisting: a serial number stays allowed until you remove it from the policy. To grant temporary access, add the serial, then remove it when the exception ends — or use [`dlp_usb_add`](#live-response-commands) for a truly short-lived exception, accepting that it lasts only until the next policy change or agent restart.
- When an endpoint stops matching an enforcing policy — a targeting tag is removed, or the policy is deleted — it is returned to permissive on its next sync.
- Unsubscribing removes the sync rule, so policy is no longer reconciled onto anything. To hand endpoints back in a known state, set the policy that covers them to `permissive` and let it converge **before** you unsubscribe.

## Configuration via Hive

In addition to the web UI, the full DLP configuration is stored as a single record in the `extension_config` [hive](../../../7-administration/config-hive/index.md) at the key `ext-dlp`, and can be managed via [git-sync](git-sync.md) (under `hives/extension_config.yaml`) or directly with the LimaCharlie CLI. Reading the record requires the `ext.conf.get` [permission](../../../8-reference/permissions.md); writing it requires `ext.conf.set`.

Read the current configuration:

```bash
limacharlie hive get \
  --hive-name extension_config \
  --key ext-dlp \
  --oid <oid> --output yaml
```

The record's `data` is exactly the YAML shown above: a top-level `policies` list. To write it, put that structure in a file and set the record:

```bash
limacharlie hive set \
  --hive-name extension_config \
  --key ext-dlp \
  --input-file my-dlp-config.yaml \
  --enabled \
  --oid <oid> --output yaml
```

The same validation the web UI applies on save — `mode` values, serial number format — applies here, and an invalid record is rejected. You can dry-run a config against the live schema without writing it:

```bash
limacharlie hive validate \
  --hive-name extension_config \
  --key ext-dlp \
  --input-file my-dlp-config.yaml \
  --oid <oid> --output yaml
```

An empty (`{}`) response means the record is valid and would be accepted by a subsequent `hive set`; any other output describes the validation failure.

## Verifying the applied policy

Policy converges on each endpoint's next sync. To confirm what an endpoint is actually enforcing, task it with `dlp_status` (see [Live response commands](#live-response-commands)). The `DLP_STATUS_REP` reply reports the endpoint's current mode and USB serial allowlist — for a converged endpoint, these match the `mode` and `usb_allowlist` of the first policy it matches. An endpoint matching no policy, or one whose matching policy has `mode` unset, reports whatever state it was last in — permissive, unless something else set it.

## Finding USB serial numbers

An allowlist is built from device serial numbers. To collect them, task an endpoint with `usb_list_keys`, from the Sensor Console or the API. It replies with a `USB_KEY_LIST_REP` event containing one `USB_KEY` entry per USB mass storage device the endpoint sees:

| Field | Description |
| --- | --- |
| `USB_SERIAL_NUMBER` | Device serial number — the value to put in `usb_allowlist` |
| `USB_VENDOR_ID` / `USB_VENDOR_NAME` | Vendor ID, and the vendor name resolved from it |
| `USB_PRODUCT_ID` / `USB_PRODUCT_NAME` | Product ID, and the product name resolved from it |
| `USB_DEVICE_CLASS` / `USB_DEVICE_SUBCLASS` | USB device class and subclass |
| `USB_USB_VERSION` | USB version the device reports |
| `USB_ACTION` | Whether the entry reflects a device being added or removed |
| `TIMESTAMP` | When the endpoint observed the device |

`usb_list_keys` runs in user space, so it works on an endpoint whose kernel component is absent — useful for surveying devices before you deploy a policy.

## Assessing impact before enforcing

There is no report-only mode: `mode` is either `permissive` or `enforcing`, and no event is emitted when a device is blocked — or would have been blocked. To measure what an allowlist would break **before** turning enforcement on, stage the rollout:

1. **Inventory in permissive.** Subscribe the extension and leave endpoints in `permissive` (or matched by no policy) — neither changes endpoint behavior. Then collect real device usage:
    - Task the fleet with `usb_list_keys` on a recurring cadence — [Reliable Tasking](reliable-tasking.md) handles endpoints that are offline at task time. Every reply is retained as a `USB_KEY_LIST_REP` event (part of the default event collection set — see [Event collection](#event-collection)), so telemetry accumulates the serial number, vendor, and product of each device seen, per endpoint.
    - On Windows and macOS, the passive [`VOLUME_MOUNT`](../../../8-reference/edr-events.md#volume_mount) event fires in real time when a volume is mounted — useful for spotting active removable-storage use between polls. It is not available on Linux.
2. **Diff against the proposed allowlist.** Aggregate the observed `USB_SERIAL_NUMBER` values per endpoint from the collected `USB_KEY_LIST_REP` events (the Query console works well for this). The serials **not** on your proposed `usb_allowlist` are exactly the devices — and endpoints — that enforcement would block. For a standing report, keep the approved serials in a [lookup](../../../7-administration/config-hive/lookups.md) and alert on any observed serial missing from it with a [D&R rule](../../../7-administration/config-hive/dr-rules.md) on `USB_KEY_LIST_REP`.
3. **Enforce in stages.** Targeting is tag-based, so apply `enforcing` to a pilot tag first and broaden from there, keeping a broad `permissive` policy below it as an instant rollback (it converges on each endpoint's next sync).

Run the inventory phase long enough to catch devices used on a longer cadence — backup drives that only appear monthly are a common surprise. A device plugged in and removed between two `usb_list_keys` polls may go unobserved, so treat the inventory as a lower bound.

## Live response commands

The same controls are available as endpoint commands, for investigation and emergency response:

| Command | Description |
| --- | --- |
| `dlp_status` | Reports the endpoint's current mode and USB serial allowlist |
| `usb_list_keys` | Lists the USB mass storage devices the endpoint sees |
| `dlp_usb_enforcing` | Switches USB DLP to enforcing |
| `dlp_usb_permissive` | Switches USB DLP to permissive |
| `dlp_usb_add --usb <serial>` | Adds serial numbers to the allowlist; repeat `--usb` for several |
| `dlp_usb_rem --usb <serial>` | Removes serial numbers from the allowlist |

!!! note "A command and your policy can disagree"
    A command changes the endpoint immediately, but it does not change your policy. The extension pushes only when its policy differs from what the endpoint last received, so a manual change is not reverted straight away: it survives until the policy changes or the agent restarts, at which point the policy is re-applied and the manual change is lost. Treat the configuration as the source of truth, and use the commands for investigation or one-off intervention.

## Event collection

The USB and DLP reply events are part of the default event collection set on Windows, macOS, and Linux, so no action is needed in a default Organization. If you have customized event collection under **Sensors** / **Event Collection**, or manage it as Infrastructure-as-Code, add whichever of these you want retained:

```text
USB_KEY_LIST_REP,DLP_STATUS_REP,DLP_SET_ENFORCING_REP,DLP_SET_PERMISSIVE_REP,
DLP_USB_ADD_SERIAL_REP,DLP_USB_REM_SERIAL_REP
```

## See Also

- [Exfil](exfil.md) — event collection configuration
- [Endpoint Agent Commands](../../../8-reference/endpoint-commands.md) — full command reference
- [D&R Rules](../../../7-administration/config-hive/dr-rules.md) — managed rules, including `ext-dlp-sync`
