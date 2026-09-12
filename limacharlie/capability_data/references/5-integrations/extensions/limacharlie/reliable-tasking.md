# Reliable Tasking

The Reliable Tasking Extension enables you to task Sensor(s) that are currently offline. The extension queues the task in the cloud and automatically delivers it when the Sensor(s) come online.

## How It Works

When you create a reliable task, the extension:

1. Resolves the targeting criteria (`sid`, `tag`, or `selector`) to a list of sensors and records one queued task per sensor, with an expiry of `now + ttl`.
2. Immediately attempts delivery to the sensors that are currently online.
3. Retries delivery every time a targeted sensor reconnects to the cloud (on its `CONNECTED` event).
4. Removes the queued task for a sensor once that sensor confirms receipt of the command.

Two properties follow from this design that are worth understanding:

- **Delivery only happens while a sensor is connected.** Tasks are never pre-staged on an offline sensor; a task queued for an offline sensor exists only in the extension's queue until the sensor reconnects.
- **The TTL is evaluated at delivery time.** At every delivery attempt, expired tasks are skipped. If a sensor is offline for the entire TTL and reconnects afterwards, the task is *not* delivered — the extension has given up on it.

> **Note:** The sensor commands `restart` and `upgrade_core` do not produce a receipt from the sensor, so they are considered confirmed (and removed from the queue) as soon as they are successfully sent to a connected sensor.

## Enabling the Reliable Tasking Extension

To enable the Reliable Tasking extension, navigate to the [Reliable Tasking extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-reliable-tasking) in the marketplace. Select the Organization you wish to enable the extension for, and select **Subscribe**.

After clicking **Subscribe**, the Reliable Tasking extension should be available almost immediately.

## Using the Reliable Tasking Extension

Once enabled, you will see a **Reliable Tasking** option under **Automation** within the LimaCharlie web UI. You can also interact with the extension via REST API.

Within the Reliable Tasking module, you can:

- Task Sensor(s)
- Untask Sensor(s)
- List active task(s)

## Actions via REST API

The following REST API actions can be sent to interact with the Reliable Tasking extension:

### Create a Task

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=task&data={"context":"version","selector":"plat==windows","task":"run --shell-command whoami","ttl":3600}'
```

All parameters are provided in the request body as URL-encoded form data. The `data` parameter should contain a JSON object with the following fields:

**Required Parameters:**

- `task`: The command to execute, similar to a command-line `task` (e.g., `"run --shell-command whoami"`, `"mem_map --pid 4"`)
- One of `sid`, `tag`, or `selector` (targeting criteria):
  - `sid`: Target a single sensor by Sensor ID
  - `tag`: Target all sensors that have this tag
  - `selector`: A [Sensor Selector Expression](../../../8-reference/sensor-selector-expressions.md) specifying which sensors should receive the task. Use `"*"` to target all sensors in the organization.
    - Examples:
      - `"selector":"plat==windows"` - All Windows sensors
      - `"selector":"sid=='abc-123-def'"` - A specific sensor by ID
      - `"selector":"production in tags"` - All sensors with the "production" tag
      - `"selector":"plat==linux and int_ip matches '^10\\.3\\..*'"` - Complex expressions using AND/OR logic

**Optional Parameters:**

- `context`: An identifier that will be reflected in the `investigation_id` of the corresponding `RECEIPT` or `_REP` event, allowing you to craft D&R rules based on the response
- `ttl`: Time-to-live in seconds - how long the extension should keep trying to deliver the task to sensors that haven't acknowledged it. Defaults to 1 week (604800 seconds). There is no minimum value; short TTLs (even a few seconds) are valid and are a supported way to bound how late a task may be delivered. See [TTL and Delivery Guarantees](#ttl-and-delivery-guarantees).

For more details on sensor selector syntax and available fields (`sid`, `plat`, `tags`, `hostname`, `int_ip`, etc.), see the [Sensor Selector Expressions reference](../../../8-reference/sensor-selector-expressions.md).

**Response:**

```json
{
  "task_id": "abc123...",
  "total_sensors": 250,
  "tasked_sensors": 200,
  "queued_sensors": 50
}
```

- `task_id`: The unique ID for this tasking request across all targeted sensors. Keep it if you may need to [untask](#untask) later or correlate feedback events.
- `total_sensors`: Number of sensors matched by the targeting criteria.
- `tasked_sensors`: Sensors that were online and were sent the task immediately.
- `queued_sensors`: Sensors that were offline; the task remains queued for them until they reconnect or the TTL expires.

**Additional Examples:**

Target a specific sensor:

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=task&data={"task":"os_version","selector":"sid=='\''sensor-123-abc'\''","ttl":86400}'
```

Target all Linux servers with a specific tag:

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=task&data={"task":"file_get -f /etc/passwd","selector":"plat==linux and production in tags","context":"audit-2024","ttl":172800}'
```

Target all sensors:

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=task&data={"task":"os_version","selector":"*","ttl":3600}'
```

### List Tasks

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=list&data={}'
```

This returns the pending reliable tasks, organized per sensor and then per `task_id`, including the command, context, and expiry time of each queued task.

Like `task` and `untask`, the `list` action accepts `sid`, `tag`, or `selector` to scope which sensors' queues are returned; the selector defaults to `*` (all sensors), which is why an empty `data` object works. Note that the scoping applies to *sensors*, not to the selector a task was originally created with. Tasks that have expired or have been confirmed received by the sensor are not listed.

### Untask

The `untask` action deletes queued tasks, aborting delivery of ALL tasks that fit the given criteria. Use it to cancel tasks that have not yet been delivered (e.g., to sensors that are still offline).

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=untask&data={"selector":"*","task_id":"$TASK_ID"}'
```

**Parameters:**

- One of `sid`, `tag`, or `selector` is required and scopes which sensors to untask (same semantics as `task`; use `"*"` to cover all sensors).
- `task_id` (optional): Only remove tasks with this task ID (as returned by the `task` action). If omitted, ALL queued tasks on the matching sensors are removed.

**Response:**

```json
{
  "deleted": 50
}
```

`deleted` is the number of queued task records that were actually removed.

**Examples:**

Cancel a specific tasking request everywhere it is still queued:

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=untask&data={"selector":"*","task_id":"abc123"}'
```

Remove all queued tasks from a single sensor:

```bash
curl --location 'https://api.limacharlie.io/v1/extension/request/ext-reliable-tasking' \
--header 'Authorization: Bearer $JWT' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data 'oid=$YOUR_OID&action=untask&data={"sid":"sensor-123-abc"}'
```

Untasking removes tasks from the delivery queue, which is the only place a not-yet-delivered task exists — so once `untask` returns, a queued task can no longer be delivered. A task that has already been delivered to a connected sensor cannot be recalled.

## TTL and Delivery Guarantees

The `ttl` is the authoritative bound on how late a task may be delivered:

- The expiry (`creation time + ttl`) is checked at every delivery attempt. Once expired, a task is never delivered, including to a sensor that reconnects after the TTL has elapsed.
- There is no minimum TTL. If you need "run this within the next 2 minutes or not at all", `"ttl":120` does exactly that.
- Expired tasks do not appear in `list` results and require no cleanup, though calling `untask` on them is harmless.

If you are implementing your own timeout on top of reliable tasking (e.g., marking a task as failed after N seconds), the recommended pattern is:

1. Create the task with `ttl` set to your timeout. This guarantees the platform will not deliver it after your deadline.
2. Optionally call `untask` with the `task_id` when you declare the timeout, as immediate cleanup.

One caveat: the TTL bounds when delivery *starts*, not when results arrive. A sensor that reconnects just before expiry can still receive the task, and its `RECEIPT`/`_REP` events may arrive after your deadline. Design your response handling (D&R rules, `context` matching) to tolerate a late receipt for a task delivered near the end of its TTL.

## Monitoring Task Delivery

The extension reports its activity as events in your organization through a webhook Adapter named `ext-reliable-tasking` (installed automatically on subscription). Each event's type reflects the action:

- `add_task`: A new tasking request was recorded (includes `task_id`, targeting criteria, and `ttl`)
- `try_task`: A targeted sensor is online and delivery is being attempted
- `task_sent`: The task was sent to the sensor (includes `sid` and `task_id`)
- `task_done`: The sensor confirmed receipt; the task is removed from the queue
- `task_failure`: Sending the task to a sensor failed (includes the error)

These events can be used in D&R rules to track fleet-wide completion or alert on failures, for example:

```yaml
detect:
  event: task_failure
  op: is
  path: routing/hostname
  value: ext-reliable-tasking
respond:
  - action: report
    name: reliable-task-delivery-failure
```

## Capturing Task Responses

If you're using reliable tasks to issue commands across your sensors, you're probably going to want to view or act on the responses from these commands as well.

If you add a value to the `context` parameter in the extension request, this value will be reflected in the `investigation_id` of the corresponding `RECEIPT` or `_REP` event, allowing you to craft a D&R rule based on the response.

The above example cURL command has a `context` of `version` so the below D&R rule looks for that value.

### Example detect block

```yaml
op: contains
event: RECEIPT
path: routing/investigation_id
value: version
```

### Example respond block

```yaml
- action: output
  name: tasks-output         # Send responses to the specified output
- action: report
  name: "Reliable task ran"  # Detect on the task being run
```

## Fanning Out at Scale

A single `task` request fans out server-side: the extension resolves the `tag` or `selector` to the full sensor list, queues one task per sensor, and paces the deliveries itself. To send one command to many sensors, make **one** API call with a `tag` or `selector` — do not loop over sensors making one call per `sid`.

Like all LimaCharlie REST API calls, requests to the extension endpoint are subject to per-credential API rate limits, measured over a 60-second window. A client exceeding its quota receives an `HTTP 429` response that includes `X-RateLimit-Quota` (requests allowed per window) and `X-RateLimit-Period` (window length in seconds) headers; back off and retry after the window when you receive one. With server-side fan-out, even very large deployments should only need a handful of API calls, keeping you well below the limits.

## Migrating Rule from legacy Service to new Extension

***Note: LimaCharlie has migrated from Services to Extensions. Legacy services are no longer supported.***

The [Python CLI](https://github.com/refractionPOINT/python-limacharlie) gives you a direct way to assess if any rules reference the legacy reliable tasking service and convert them to use the extension.

Command line to preview Reliable Tasking rule conversion:

```bash
limacharlie extension convert_rules --name ext-reliable-tasking
```

A dry-run response (default) will display the rule name being changed, a JSON of the service request rule and a JSON of the incoming extension request change.

To execute the change in the rule, explicitly set `--dry-run` flag to `--no-dry-run`

Command line to execute reliable tasking rule conversion:

```bash
limacharlie extension convert_rules --name ext-reliable-tasking --no-dry-run
```
