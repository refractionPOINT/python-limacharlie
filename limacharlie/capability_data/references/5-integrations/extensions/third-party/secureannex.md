# Secure Annex

[Secure Annex](https://secureannex.com/) is a browser extension security platform that provides a comprehensive analysis of the Chrome extensions installed across your organization's endpoints.

The Secure Annex LimaCharlie Extension allows you to query the Secure Annex API with the IDs of Chrome extensions installed on endpoints within your organization in order to get detailed information about the extensions. You can then perform additional analysis or craft rules based on the results.

API endpoints available for querying are:

- /manifest
- /extensions
- /vulnerabilities
- /signatures
- /urls
- /analysis

This is currently only supported on Windows, macOS, and Chrome sensors.

## Setup

1. Sign up and get an API key at <https://app.secureannex.com/settings/api>
2. Subscribe to the Secure Annex extension in LimaCharlie - <https://app.limacharlie.io/add-ons/extension-detail/ext-secureannex>
3. Add the API key to the Secure Annex extension configuration within LimaCharlie

## Usage

### Manually in the GUI

You can trigger an extension request manually within the web app by clicking the `Get extensions from endpoint` button. This will allow you to choose a sensor, or sensors via a Sensor Selector, to get extensions from. See [sensor selector expression examples](../../../8-reference/sensor-selector-expressions.md).

The extensions are gathered from endpoints via the reliable tasking extension, which appends `secureannex_extensions` to the investigation ID of the `RECEIPT` or `OS_PACKAGES_REP` event in order to trigger an extension request to query Secure Annex. The results will be in the timeline of the `ext-secureannex` sensor.

### Automatically via D&R Rules

Upon subscribing to the Secure Annex extension, several D&R rules are added to your organization in a **disabled state** to help you get more use out of the extension and automate your detections. They are as follows:

- `ext-secureannex-detect-vulnerabilities`
  - This will look at the vulnerabilities and associated severities in the `vulnerability` results returned, and create detections on high and critical vulnerabilities found
- `ext-secureannex-detect-risk-rating`
  - This will look at the risks and associated severities in the `manifest` results returned, and create detections on high and critical severities found
- `ext-secureannex-get-extensions-windows`
  - This schedules a base64 encoded PowerShell script to run every 24 hours to query Windows sensors for installed Chrome extensions, and bring back a list of the extension IDs and versions
  - The results will have a `secureannex_extensions` investigation ID associated that will allow LimaCharlie to automatically create Secure Annex extension requests with the IDs and versions included to perform a full analysis and bring back the results into the `ext-secureannex` sensor
- `ext-secureannex-get-extensions-mac`
  - This schedules a base64 encoded bash script to run every 24 hours to query macOS sensors for installed Chrome extensions, and bring back a list of the extension IDs and versions
  - The results will have a `secureannex_extensions` investigation ID associated that will allow LimaCharlie to automatically create Secure Annex extension requests with the IDs and versions included to perform a full analysis and bring back the results into the `ext-secureannex` sensor
- `ext-secureannex-get-extensions-chrome`
  - This schedules the `OS_PACKAGES` command to run every 24 hours to query Chrome sensors for installed Chrome extensions, and bring back a list of the extension IDs and versions
  - The results will have an investigation ID associated that will allow LimaCharlie to automatically create Secure Annex extension requests with the IDs and versions included to perform a full analysis and bring back the results into the `ext-secureannex` sensor

If you wish to use these, you need to enable them first. You can also copy the contents of these rules and create your own so they are no longer managed by the Secure Annex extension if you wish to modify them.

### Results

Results will show up in the live feed and timeline of the `ext-secureannex` Sensor.
