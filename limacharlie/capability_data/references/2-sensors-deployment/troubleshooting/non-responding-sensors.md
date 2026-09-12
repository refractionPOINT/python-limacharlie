# Detecting Sensors No Longer Sending Data

## Overview

A common request is to alert an administrator if a Sensor that normally forwards data, stops or fails to send data. This LimaCharlie Playbook is meant to be triggered on a schedule by  rule. It checks for data sent, via the LimaCharlie Python SDK, within a given time window. If no data is sent during the time period, then an alert is generated, one per sensor.

## Example Playbook Code

```python
import time
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.sensor import Sensor

# LimaCharlie D&R Rule to trigger this playbook
# every 30 minutes.
# detection:
#   target: schedule
#   event: 30m_per_org
#   op: exists
#   path: /
# response:
# - action: extension request
#   extension name: ext-playbook
#   extension action: run_playbook
#   extension request:
#     name: check-missing-data
#     credentials: hive://secret/playbook-missing-data-creds

SENSOR_SELECTOR = "plat == windows and `server` in tags"
DATA_WITHIN = 10 * 60 * 1000 # 10 minutes

def notify_missing_data(sdk: Organization, sensor: Sensor):
    # TODO: Implement this, but it's optional if all you want is a detection
    # since those will be generated automatically.
    pass

def get_relevant_sensors(sdk: Organization) -> list[Sensor]:
    sensors = sdk.list_sensors(selector=SENSOR_SELECTOR)
    relevant_sensors = []
    for sensor_info in sensors:
        relevant_sensors.append(Sensor(sdk, sensor_info["sid"]))
    return relevant_sensors

def playbook(sdk: Organization, data: dict) -> dict | None:
    # Get the sensors we care about.
    relevant_sensors = get_relevant_sensors(sdk)

    stopped_sensors = []

    # For each sensor, check if we've received data within that time period.
    for sensor in relevant_sensors:
        # To do that we will get the data overview and see if a recent time stamp is present.
        data_overview = sensor.get_overview(int(time.time() - DATA_WITHIN), int(time.time()))
        after = int(time.time() * 1000) - DATA_WITHIN
        for timestamp in data_overview:
            if timestamp > after:
                print(f"Data received for sensor {sensor.sid} at {timestamp}")
                break
        else:
            print(f"No data received for sensor {sensor.sid} in the last {DATA_WITHIN} seconds")
            notify_missing_data(sdk, sensor)
            stopped_sensors.append(sensor)

    # Report a detection for stopped sensors.
    if stopped_sensors:
        return {"detection":{
            "stopped_sensors": [sensor.sid for sensor in stopped_sensors]
        }}
    return None
```
