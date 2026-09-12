# YARA

The [YARA](https://github.com/Yara-Rules/rules) Extension is designed to help you with all aspects of YARA scanning. It takes what is normally a manual piecewise process, provides a framework and automates it. Once configured, YARA scans can be run on demand for a particular endpoint or continuously in the background across your entire fleet.

Yara configurations are synchronized with sensors every few minutes.

There are three main sections to the YARA job:

- Sources
- Rules
- Scan

## Where Does My YARA Scan?

Automated YARA scanners in LimaCharlie will run on all files loaded in memory (e.g. exe, dll, etc), and on the memory itself.

Files on disk can be scanned using a Sensor command. You can trigger a Manual Scan that's run on-demand by:

- Clicking the Run YARA scan button on the sensor details page,
- Clicking the Scan button on the YARA Scanners page
- Using the console
- Within the Response section of a rule (sample below)
- Using the LimaCharlie API

## Rules

This is where you define your YARA rule(s). You can copy and paste your YARA rules into the `Rule` box, or you can define sources via the [ext-yara-manager](../limacharlie/yara-manager.md). Sources can be either direct links (URLs) to a given YARA rule (or directory of rules) or [ARLs](../../../8-reference/authentication-resource-locator.md) to a YARA rule.

![yara 1](../../../assets/images/yara-1.png)

![yara 2](../../../assets/images/yara-2.png)

## Scanners

Scanners define which sets of sensors should be scanned with which sets of YARA rules.

Filter Tags are tags that must ALL be present on a sensor for it to match (AND condition), while the platform of the sensor much match one of the platforms in the filter (OR condition).

To apply YARA rules to scan an endpoint (or set of endpoints), you must select the platform or tags, and then add the YARA rules you would like to run.

## Using Yara in D&R Rules

If you want to trigger a Yara scan as a response to one of your detections, you can configure an extension request in the respond block of a rule. A Yara scan request can be executed with a blank selector OR Sensor ID. However, one of them must be specified.

```yaml
- action: extension request
  extension action: scan
  extension name: ext-yara
  extension request:
 sources: [ ]# Specify Yara Rule sources as strings
 selector: ''
        sid: '{{ .routing.sid }}' # Use a sensor selector OR a sid, **not both**
 yara_scan_ttl: 86400 # "Default: 1 day (86,400 seconds)"
```

## Migrating D&R Rule from legacy Service to new Extension

***Note: LimaCharlie has migrated from Services to Extensions. Legacy services are no longer supported.***

The [Python CLI](https://github.com/refractionPOINT/python-limacharlie) gives you a direct way to assess if any rules reference legacy Yara service, preview the change and execute the conversion required in the rule "response".

Command line to preview Yara rule conversion:

```bash
limacharlie extension convert_rules --name ext-yara
```

A dry-run response (default) will display the rule name being changed, a JSON of the service request rule and a JSON of the incoming extension request change.

To execute the change in the rule, explicitly set `--dry-run` flag to `--no-dry-run`

Command line to execute Yara rule conversion:

```bash
limacharlie extension convert_rules --name ext-yara --no-dry-run
```
