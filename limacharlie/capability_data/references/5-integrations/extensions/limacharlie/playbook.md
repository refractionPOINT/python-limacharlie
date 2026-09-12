# Playbook [LABS]

> LimaCharlie LABS

!!! warning "Python SDK v4 only"
    The Playbook execution environment runs on the LimaCharlie **Python SDK v4**.
    The recently released [Python SDK v5](../../../6-developer-guide/sdks/python-sdk.md)
    is **not yet supported** in playbooks — write playbook code against v4 APIs.
    See the [Python SDK v4 documentation](../../../6-developer-guide/sdks/python-sdk-v4.md)
    for the supported `Manager` interface and module layout.

The Playbook Extension allows you to execute Python playbooks within the context of your Organization in order to automate tasks and customize more complex detections.

The playbooks themselves are managed in the playbook Hive Configurations and can be managed across tenants using the Infrastructure as Code extension.

The execution of a playbook can be triggered through the following means:

1. Interactively in the web app by going to the Extensions section for the Playbook extension.
2. By issuing an `extension request` action through a [D&R rule](../../../3-detection-response/examples.md).
3. By issuing an extension request on the API directly: <https://api.limacharlie.io/static/swagger/#/Extensions/createExtensionRequest>
4. By issuing an extension request through the Python CLI/SDK or Golang SDK.

This means playbooks can be issued in a fully automated fashion based on events, detections, audit messages or any other [target](../../../3-detection-response/alternate-targets.md) of D&R rules. But it can also be used in an ad-hoc fashion triggered manually.

## Enabling Extension

The Playbook extension can be enabled by subscribing your organization to the ext-playbook add-on.

![Enabling Extension The Playbook extension can be enabled by subscribing your organization to the ext-playbook add-on](../../../assets/images/image(317).png)

## Accessing Playbooks

Playbooks are created, modified, and deleted via the Playbooks option located within the Automation menu.

> Note: If you are unable to see the Playbooks option, ensure your user account has the appropriate permissions enabled.
>
> ![Playbooks are created, modified, and deleted via the Playbooks option located within the Automation menu](../../../assets/images/image(319).png)

![Playbooks option in the Automation menu](../../../assets/images/image(321).png)

## Usage

When invoking a playbook, all you need is the playbook name as defined in Hive. Optionally, a playbook can also receive a JSON dictionary object as parameters, this is useful when triggering a playbook from a D&R rule and you want to pass some context, or when passing context interactively.

### D&R rule example

Here is an example D&R rule starting a new invocation of a playbook.

```yaml
- action: extension request
  extension name: ext-playbook
  extension action: run_playbook
  extension request:
    name: '{{ "my-playbook" }}'
    credentials: '{{ "hive://secret/my-api-key" }}'
    data:
      some: event.FILE_PATH
      for_the: '{{ "running of the playbook" }}'
```

### Python example

```python
import limacharlie

# Manager picks up credentials from the environment or ~/.limacharlie.
man = limacharlie.Manager()
ext = limacharlie.Extension(man)

# Issue a request to the "ext-playbook" extension.
response = ext.request("ext-playbook", "run_playbook", {
    "name": "my-playbook",
    "credentials": "hive://secret/my-playbook-api-key",
    "data": {
        "some": "data"
    }
})

# The returned data from the playbook.
print(response)
```

## Playbook structure

A playbook is a normal python script. The only required component is a top level function called `playbook` which takes 2 arguments:

- `sdk`: an instance of the LC Python SDK v4 `limacharlie.Manager`, pre-authenticated to the relevant Organization based on the credentials provided, if any, `None` otherwise.
- `data`: the optional JSON dictionary provided as context to your playbook.

The function must return a dictionary with the following optional keys:

1. `data`: a dictionary of data to return to the caller
2. `error`: an error message (string) to return to the caller
3. `detection`: a dictionary to use as detection
4. `cat`: a string to use as the category of the detection, if `detection` is specified.

This allows your playbook to return information about its execution, return data, errors or generate a detection. The python `print()` statement is not currently being returned to the caller or otherwise accessible, so you will want to use the `data` in order to return information about the execution of your playbook.

### Example playbook

The following is a sample playbook that sends a webhook to an external product with a secret stored in LimaCharlie, and it returns the data as the response from the playbook.

```python
import json
import urllib.request
import limacharlie

def playbook(sdk, data):
  # Get the secret we need from LimaCharlie.
  mySecret = limacharlie.Hive(sdk, "secret").get("my-secret-name").data["secret"]

  # Send the Webhook.
  request = urllib.request.Request("https://example.com/webhook", data=json.dumps(data).encode('utf-8'), headers={
    "Content-Type": "application/json",
    "Authorization": f"Bearer {mySecret}"
  }, method="POST")

  try:
    with urllib.request.urlopen(request) as response:
      response_body = response.read().decode('utf-8')
      # Parse the JSON response
      parsed_response = json.loads(response_body)
  except Exception as e:
    # Some error occured, let the caller/LC know.
    return {
      "error": str(e),
    }

  # Return the data to the caller/LC.
  return {
    "data": parsed_response,
  }
```

#### Example playbook with custom detection category

When a playbook generates a detection, you can customize the detection category name that appears in the UI by setting the `cat` field at the top level of the return dictionary. This is particularly useful when you want detections from different playbooks to have descriptive names instead of the generic "playbook-detection".

The following example checks if a server sensor has missed a check-in and creates a detection with a custom category name:

```python
def playbook(sdk, data):
  if not sdk:
    return {"error": "LC API key required"}

  # Check for sensors that haven't checked in recently
  import time
  current_time = time.time()
  threshold = 3600  # 1 hour in seconds

  missing_sensors = []
  # Manager.sensors() is a v4 generator yielding Sensor objects.
  for sensor in sdk.sensors():
    info = sensor.getInfo()
    last_seen = info.get('last_seen', 0)
    if (current_time - last_seen) > threshold:
      missing_sensors.append({
        "sid": sensor.sid,
        "hostname": info.get('hostname', 'unknown')
      })

  if missing_sensors:
    # Return a detection with a custom category name
    # The 'cat' field MUST be at the top level, not inside 'detection'
    return {
      "detection": {
        "summary": f"Found {len(missing_sensors)} sensors missing check-in",
        "missing_sensors": missing_sensors
      },
      "cat": "Server-Sensor-Missing-Check-In"
    }

  # No issues found
  return {
    "data": {"status": "all sensors checked in"}
  }
```

**Important:** The `cat` field must be placed at the **top level** of the return dictionary, alongside `detection`, not inside it. When this playbook creates a detection, it will appear in the Detections UI with the category name "Server-Sensor-Missing-Check-In" instead of the default "playbook-detection".

**Without `cat`:** Detection appears as "playbook-detection → ext_playbook"

**With `cat`:** Detection appears as "Server-Sensor-Missing-Check-In → ext_playbook"

### Execution environment

Playbooks contents are cached for short periods of time ( on the order of 10 seconds ) in the cloud.

Playbooks are instantiated on demand and the instance is reused for an undefined amount of time.

Playbook code only executes during the main call to the `playbook` function, background on-going running is not supported.

The execution environment is provisioned on a per-Organization basis, meaning all your playbooks may execute within the same container, but NEVER on a container used by another Organization.

Although you have access to the local environment, this environment is ephemeral and can be wiped at any moment in between executions so you should take care that your playbook is self contained and doesn't assume pre-existing conditions.

A single execution of a playbook is limited to 10 minutes.

The current execution environment is based on the default libraries provided by the `python:slim` Dockerhub official container plus the following packages:

- Python
  - `weasyprint`
  - `flask`
  - `gunicorn`
  - `flask`
  - `limacharlie` (LimaCharlie SDK/CLI)
  - `lcextension` (LimaCharlie Extension SDK)
  - `scikit-learn` (Python Machine Learning kit)
  - `jinja2`
  - `markdown`
  - `pillow`
- NodeJS
- AI
  - Claude Code (`claude`) CLI tool
  - Codex (`codex`) CLI tool
  - Gemini CLI (`gemini`) CLI tool

Custom packages and execution environment tweaks are not available in self-serve mode, but they *may* be available on demand, get in touch with us at <support@limacharlie.io>.

## Infrastructure as Code

Example:

```yaml
hives:
    playbook:
        my-playbook:
            data:
                python: |-
                    def playbook(sdk, data):
                        if not sdk:
                            return {"error": "LC API key required to list sensors"}
                        return {
                            "data": {
                                "sensors": [s.getInfo() for s in sdk.sensors()]
                            }
                        }
            usr_mtd:
                enabled: true
                expiry: 0
                tags: []
                comment: ""
```

## Billing

Playbooks are billed per seconds of total execution time.
