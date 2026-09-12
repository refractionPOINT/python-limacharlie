# Govee

The Govee Extension allows you to trigger color changes on your [supported Govee lights](https://developer.govee.com/docs/support-product-model) via a rule response action. It requires you to configure a Govee API key in the extension.

## Setup

1. Request an API key from Govee by following their [Apply for a Govee API key instructions](https://developer.govee.com/reference/apply-you-govee-api-key)
2. Get the Device ID (device) and model (sku) of the device you'd like to target by requesting a list of your supported devices from the Govee API:

```bash
curl --location 'https://openapi.api.govee.com/router/api/v1/user/devices' --header 'Govee-API-Key: YOUR_GOVEE_API_KEY'
```

1. Decide what RGB color(s) you want to use. By default, the extension will alert with red (`255,0,0`), and revert back to white (`255,255,255`) when the alert `duration` has ended.
2. Add your Govee API key to the extension configuration:
    ![govee](../../../assets/images/govee.png)

### Usage

When enabled, you may configure the response of a D&R rule to trigger a Govee event. Consider the following example response rule:

```yaml
- action: extension request
  extension action: run
  extension name: ext-govee
  extension request:
    device_id: '{{ "YOUR_GOVEE_DEVICE" }}'
    device_model: '{{ "YOUR_GOVEE_DEVICE_SKU" }}'
    alert_color: '{{ "255,0,0" }}'
    alert_brightness: '{{ "100" }}'
    revert_color: '{{ "255,255,255" }}'
    revert_brightness: '{{ "10" }}'
    duration: '{{ "30" }}'
  suppression:
    is_global: true
    keys:
      - Govee
    max_count: 1
    period: 1m
```

Note that the only required fields here are the `device_id` and `device_model`. Values supplied in the example are the defaults.

#### Parameters

**Required parameters:**

- `device_id`: returned via the Govee API, see example response below
- `device_model`: returned via the Govee API, see example response below

**Optional parameters:**

- `alert_color`: color of the light when alert fires, in [RGB format](https://htmlcolorcodes.com/color-picker/), default `255,0,0` (red)
- `revert_color`: color of the light to return to, after alert fires, in [RGB format](https://htmlcolorcodes.com/color-picker/), default `255,255,255` (white)
- `alert_brightness`: brightness of the light, default `100`
- `revert_brightness`: brightness of the light to return to, after alert fires, default `10`
- `duration`: duration of the alert in seconds, how long the light will remain at `alert_color` before returning to `revert_color`, default `30`

**Govee API sample request and response:**

```bash
curl --location 'https://openapi.api.govee.com/router/api/v1/user/devices' --header 'Govee-API-Key: YOUR_GOVEE_API_KEY'
```

```json
{
    "code": 200,
    "message": "success",
    "data": [
        {
            "sku": "H6008",                           # use in `device_model` parameter
            "device": "AA:BB:00:11:22:33:44:55",      # use in `device_id` parameter
            "deviceName": "DetectionLight",
            "type": "devices.types.light",
            "capabilities": [
                ...
            ]
        }
    ]
}
```
