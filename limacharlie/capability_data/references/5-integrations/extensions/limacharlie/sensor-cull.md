# Sensor Cull

The Sensor Cull Extension performs continuous cleaning of "old" sensors that have not connected to an Organization within a set period of time. This is useful for environments with cloud deployments or VM/template-based deployments that may enroll sensors repeatedly, and for a short period of time.

The extension works by creating rules that describe when specified sensors should be cleaned up.

## Enabling the Sensor Cull Extension

To enable the Sensor Cull extension, navigate to the [Sensor Cull extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-sensor-cull) in the LimaCharlie marketplace.

![sensor cull 1](../../../assets/images/sensor-cull-1.png)

After clicking **Subscribe**, the Sensor Cull extension should be available almost immediately.

## Using the Sensor Cull Extension

Once enabled, you will see a **Sensor Cull** option under **Sensors** within the LimaCharlie web UI. You can also interact with the extension via REST API.

![sensor cull 2](../../../assets/images/sensor-cull-2.png)

Within the Sensor Cull module, you have the ability to create rules. Sensor Cull rules are run automatically once a day, and can be edited as needed.

![sensor cull 3](../../../assets/images/sensor-cull-3.png)

Each rule specifies a single sensor `tag` used as a selector for the sensors the rule applies to. A rule also has a `name` (simply used for your bookkeeping), and a `ttl` which is the number of days a sensor can remain unconnected to LimaCharlie before it becomes eligible for cleanup.

## Actions via REST API

The following REST API actions can be sent to interact with the Sensor Cull extension:

### get_rules

Get the list of existing rules

```json
{
  "action": "get_rules"
}
```

### run

Perform an ad-hoc cleanup.

```json
{
  "action": "run"
}
```

### add_rule

The following example creates a rule name `my new rule` that applies to all sensors with the `vip` Tag, and cleans them up when they have not connected in 30 days.

```json
{
  "action": "add_rule",
  "name": "my new rule",
  "tag": "vip",
  "ttl": 30
}
```

### del_rule

Delete an existing rule by name.

```json
{
  "action": "del_rule",
  "name": "my new rule"
}
```
