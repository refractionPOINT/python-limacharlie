# Reference: Schedule Events

Schedule events are triggered automatically at various intervals per Organization or per Sensor, observable in rules via the `schedule` target.

Scheduling events have a very similar structure whether they are per-sensor or per-org.

The `event` component contains a single key, `frequency` which is the number of seconds frequency this scheduling event is for. The event type also contains the human readable version of the frequency.

The following frequencies are currently emitted:

- `30m`: `30m_per_org` and `30m_per_sensor`
- `1h`: `1h_per_org` and `1h_per_sensor`
- `3h`: `3h_per_org` and `3h_per_sensor`
- `6h`: `6h_per_org` and `6h_per_sensor`
- `12h`: `12h_per_org` and `12h_per_sensor`
- `24h`: `24h_per_org` and `24h_per_sensor`
- `168h` (7 days): `168h_per_org` and `168h_per_sensor`

Scheduling events are generated for each org that meets the following criteria:

- Has had at least 1 sensor online in the last 7 days.

Scheduling events are generated for each sensor that meets the following criteria:

- Has been online at least once in the last 30 days.

Scheduling events are not retained as part of the year retention in LimaCharlie. To leverage them, create D&R rules that target the `schedule` target and take the relevant `action` when matched. For example to issue an `os_packages` once per week on Windows hosts:

```yaml
detect:
  target: schedule
  event: 168h_per_sensor
  op: is platform
  name: windows
respond:
  - action: task
    command: os_packages
    investigation: weekly-package-list
```

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.

Similar to agents, Sensors send telemetry to the LimaCharlie platform in the form of EDR telemetry or forwarded logs. Sensors are offered as a scalable, serverless solution for securely connecting endpoints of an organization to the cloud.

## Related articles

- [Detection on Alternate Targets](../3-detection-response/alternate-targets.md)
- [Detection and Response Examples](../3-detection-response/examples.md)
- [Reference: Platform Events](platform-events.md)
