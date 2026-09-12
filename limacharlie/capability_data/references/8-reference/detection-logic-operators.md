# Detection Logic Operators

Operators are used in the Detection part of a Detection & Response rule. Operators may also be accompanied by other available parameters, such as transforms, times, and others, referenced later in this page.

> For more information on how to use operators, read [Detection & Response Rules](../3-detection-response/index.md).

## Operators

### and, or

The standard logical boolean operations to combine other logical operations. Takes a single `rules:` parameter that contains a list of other operators to "AND" or "OR" together.

Example:

```yaml
op: or
rules:
  - ...rule1...
  - ...rule2...
  - ...
```

### is

Tests for equality between the value of the `"value": <>` parameter and the value found in the event at the `"path": <>` parameter.

Supports the [file name](#file-name) and [sub domain](#sub-domain) transforms, [lookbacks](#lookbacks), and [sensor variables](../3-detection-response/sensor-variables.md).

Example rule:

```yaml
event: NEW_PROCESS
op: is
path: event/PARENT/PROCESS_ID
value: 9999
```

### exists

Tests if any elements exist at the given path (regardless of its value).

Example rule:

```yaml
event: NEW_PROCESS
op: exists
path: event/PARENT
```

The `exists` operator also supports an optional `truthy` parameter. When `true`, this parameter indicates the `exists` should treat `null` and `""` (empty string) values as if they were non-existent like:

The rule:

```yaml
op: exists
path: some/path
truthy: true
```

applied to:

```json
{
  "some": {
    "path": ""
  }
}
```

would NOT match.

### contains

The `contains` checks if a substring can be found in the value at the path.

An optional parameter `count: 3` can be specified to only match if the given
 substring is found *at least* 3 times in path.

An optional parameter `case sensitive: false` can be specified to perform case-insensitive matching (defaults to `true`).

Supports the [file name](#file-name) and [sub domain](#sub-domain) transforms.

Example rule:

```yaml
event: NEW_PROCESS
op: contains
path: event/COMMAND_LINE
value: reg
count: 2
```

### ends with, starts with

The `starts with` checks for a prefix match and `ends with` checks for a suffix match.

They both check if the value found at `path` matches the given `value`, based on the operator.

Supports the [file name](#file-name) and [sub domain](#sub-domain) transforms.

### is greater than, is lower than

Check to see if a value is greater or lower (numerically) than a value in the event.

They both use the `path` and `value` parameters. They also both support the `length of` parameter as a boolean (true or false). If set to true, instead of comparing
 the value at the specified path, it compares the length of the value at that path.

### matches

The `matches` op compares the value at `path` with a regular expression supplied in the `re` parameter. Under the hood, this uses the Golang's `regexp` [package](https://golang.org/pkg/regexp/), which also enables you to apply the regexp to log files.

**Note**: Unlike other operators, `matches` defaults to **case-insensitive** matching unless `case sensitive: true` is explicitly set.

Supports the [file name](#file-name) and [sub domain](#sub-domain) transforms.

Example:

```yaml
event: FILE_TYPE_ACCESSED
op: matches
path: event/FILE_PATH
re: .*\\system32\\.*\.scr
case sensitive: false
```

### not

The `not` operator inverts the result of its rule. For example, when applied to an `is` operator, it changes the logic from "equals" to "does not equal". When applied to an or operator, it changes the logic from "any of these conditions are true" to "none of these conditions are true"

Example:

```yaml
event: NEW_PROCESS
op: is
not: true
path: event/PARENT/PROCESS_ID
value: 9999
```

### string distance

The `string distance` op looks up the [Levenshtein Distance](https://en.wikipedia.org/wiki/Levenshtein_distance) between two strings. In other words it generates the minimum number of character changes required for one string to become equal to another.

For example, the Levenshtein Distance between `google.com` and `googlr.com` (`r` instead of `e`) is 1.

This can be used to find variations of file names or domain names that could be used for phishing, for example.

Suppose your company is `onephoton.com`. Looking for the Levenshtein Distance between all `DOMAIN_NAME` in `DNS_REQUEST` events, compared to `onephoton.com` it could detect an attacker using `onephot0n.com` in a phishing email domain.

The operator takes a `path` parameter indicating which field to compare, a `max` parameter indicating the maximum Levenshtein Distance to match and a `value` parameter that is either a string or a list of strings that represent the value(s) to compare to. Note that although `string distance` supports the `value` to be a list, most other operators do not.

Supports the [file name](#file-name) and [sub domain](#sub-domain) transforms.

Example:

```yaml
event: DNS_REQUEST
op: string distance
path: event/DOMAIN_NAME
value:
  - onephoton.com
  - www.onephoton.com
max: 2
```

This would match `onephotom.com` and `0nephotom.com` but NOT `0neph0tom.com`.

Using the [file name](#file-name) transform to apply to a file name in a path:

```yaml
event: NEW_PROCESS
op: string distance
path: event/FILE_PATH
file name: true
value:
  - svchost.exe
  - csrss.exe
max: 2
```

This would match `svhost.exe` and `csrss32.exe` but NOT `csrsswin32.exe`.

### is 32 bit, is 64 bit, is arm

All of these operators take no additional arguments, they simply match if the relevant Sensor characteristic is correct.

Example:

```yaml
op: is 64 bit
```

### is platform

Checks if the event under evaluation is from a sensor of the given platform.

Takes a `name` parameter for the platform name. The current platforms are:

**Endpoint Platforms:**

- `windows`
- `linux`
- `macos`
- `ios`
- `android`
- `chrome`

**Cloud & Service Platforms:**

- `gcp` (Google Cloud Platform)
- `aws` (Amazon Web Services)
- `azure_ad` (Azure Active Directory)
- `azure_event_hub_namespace`
- `azure_key_vault`
- `azure_kubernetes_service`
- `azure_monitor`
- `azure_network_security_group`
- `azure_sql_audit`
- `guard_duty` (AWS GuardDuty)
- `k8s_pods` (Kubernetes)

**Identity & Access Management:**

- `1password`
- `bitwarden`
- `duo`
- `entraid` (Microsoft Entra ID)
- `okta`
- `sublime`

**Security Products:**

- `carbon_black`
- `cortex_xdr` (Palo Alto Cortex XDR)
- `crowdstrike`
- `cylance`
- `falconcloud`
- `harmony` (Check Point Harmony)
- `msdefender` (Microsoft Defender)
- `sentinel_one`
- `sophos`
- `threatlocker`
- `trend_micro`
- `trend_worryfree`
- `wiz`

**Communication & Collaboration:**

- `box`
- `github`
- `office365`
- `slack`
- `email`

**IT & Business Services:**

- `halopsa` (HaloPSA)
- `hubspot`
- `itglue`
- `mimecast`
- `pandadoc`
- `proofpoint`
- `zendesk`

**Network & Infrastructure:**

- `canary_token`
- `fortigate`
- `iis` (Internet Information Services)
- `netscaler`
- `paloalto_fw` (Palo Alto Firewall)
- `zeek`

**Data Formats:**

- `vpn`
- `text`
- `json`
- `xml`
- `cef` (Common Event Format)
- `wel` (Windows Event Log)
- `mac_unified_logging`
- `otel` (OpenTelemetry)

**Other:**

- `lc_event` (LimaCharlie internal events)

Example:

```yaml
op: is platform
name: 1password
```

Note: Platform names are case-sensitive and should be lowercase.

### is tagged

Determines if the Tag supplied in the `tag` parameter is already associated with the sensor that the event under evaluation is from.

### lookup

Looks up a value against a [lookup add-on](https://app.limacharlie.io/add-ons/category/lookup) (a.k.a. resource) such as a threat feed.

```yaml
event: DNS_REQUEST
op: lookup
path: event/DOMAIN_NAME
resource: hive://lookup/malwaredomains
case sensitive: false
```

This rule will get the `event/DOMAIN_NAME` of a `DNS_REQUEST` event and check if it's a member of the `lookup` named `malwaredomains`. If it is, then the rule is a match.

The value is supplied via the `path` parameter and the lookup is defined in the `resource` parameter. Resources are of the form `hive://lookup/RESOURCE_NAME`. In order to access a lookup, your Organization must be subscribed to it.

Supports the [file name](#file-name) and [sub domain](#sub-domain) transforms.

> API-based lookups, like VirusTotal and IP Geolocation, work a little bit differently. For more information, see [Using API-based lookups](../5-integrations/api-integrations/index.md).
>
> You can create your own lookups and optionally publish them in the add-on marketplace. To learn more, see [Lookups](../7-administration/config-hive/lookups.md) and [Lookup Manager](../5-integrations/extensions/limacharlie/lookup-manager.md).

### scope

In some cases, you may want to limit the scope of the matching and the `path` you use to be within a specific part of the event. The `scope` operator allows you to do just that, reset the root of the `event/` in paths to be a sub-path of the event.

This comes in as very useful for example when you want to test multiple values of a connection in a `NETWORK_CONNECTIONS` event but always on a per-connection. If you  were to do a rule like:

```yaml
event: NETWORK_CONNECTIONS
op: and
rules:
  - op: starts with
    path: event/NETWORK_ACTIVITY/?/SOURCE/IP_ADDRESS
    value: '10.'
  - op: is
    path: event/NETWORK_ACTIVITY/?/DESTINATION/PORT
    value: 445
```

you would hit on events where *any* connection has a source IP prefix of `10.` and *any* connection has a destination port of `445`. Obviously this is not what we had in mind, we wanted to know if a *single* connection has those two characteristics.

The solution is to use the `scope` operator. The `path` in the operator will become the new `event/` root path in all operators found under the `rule`. So the above would become

Example:

```yaml
event: NETWORK_CONNECTIONS
op: scope
path: event/NETWORK_ACTIVITY/
rule:
  op: and
  rules:
    - op: starts with
      path: event/SOURCE/IP_ADDRESS
      value: '10.'
    - op: is
      path: event/DESTINATION/PORT
      value: 445
```

### cidr

The `cidr` checks if an IP address at the path is contained within a given
[CIDR network mask](https://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing).

Example rule:

```yaml
event: NETWORK_CONNECTIONS
op: cidr
path: event/NETWORK_ACTIVITY/SOURCE/IP_ADDRESS
cidr: 10.16.1.0/24
```

### is private address

The `is private address` operator checks if an IP address at the path is a private/non-routable address. Supports both IPv4 and IPv6.

**IPv4 ranges matched:**

| Range | Description | RFC |
|-------|-------------|-----|
| `10.0.0.0/8` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `172.16.0.0/12` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `192.168.0.0/16` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `100.64.0.0/10` | CGNAT/Shared Address Space | [RFC 6598](https://datatracker.ietf.org/doc/html/rfc6598) |

**IPv6 ranges matched:**

| Range | Description | RFC |
|-------|-------------|-----|
| `fc00::/7` | Unique Local Address (ULA) | [RFC 4193](https://datatracker.ietf.org/doc/html/rfc4193) |

Note: This operator does **not** match loopback (`127.0.0.0/8`, `::1`) or link-local (`169.254.0.0/16`, `fe80::/10`) addresses. Use `cidr` if you need to match those specifically.

Example rule:

```yaml
event: NETWORK_CONNECTIONS
op: is private address
path: event/NETWORK_ACTIVITY/SOURCE/IP_ADDRESS
```

### is private ipv4 address

The `is private ipv4 address` operator checks if an IP address at the path is a private IPv4 address. Returns false for IPv6 addresses.

**Ranges matched:**

| Range | Description | RFC |
|-------|-------------|-----|
| `10.0.0.0/8` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `172.16.0.0/12` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `192.168.0.0/16` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `100.64.0.0/10` | CGNAT/Shared Address Space | [RFC 6598](https://datatracker.ietf.org/doc/html/rfc6598) |

Example rule:

```yaml
event: NETWORK_CONNECTIONS
op: is private ipv4 address
path: event/NETWORK_ACTIVITY/SOURCE/IP_ADDRESS
```

### is private ipv6 address

The `is private ipv6 address` operator checks if an IP address at the path is a private IPv6 address (ULA). Returns false for IPv4 addresses.

**Ranges matched:**

| Range | Description | RFC |
|-------|-------------|-----|
| `fc00::/7` | Unique Local Address (ULA) | [RFC 4193](https://datatracker.ietf.org/doc/html/rfc4193) |

Example rule:

```yaml
event: NETWORK_CONNECTIONS
op: is private ipv6 address
path: event/NETWORK_ACTIVITY/SOURCE/IP_ADDRESS
```

### is public address

The `is public address` operator checks if an IP address at the path is a publicly routable unicast address. Supports both IPv4 and IPv6.

**IPv4 ranges excluded (will NOT match as public):**

| Range | Description | RFC |
|-------|-------------|-----|
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `100.64.0.0/10` | CGNAT/Shared Address Space | [RFC 6598](https://datatracker.ietf.org/doc/html/rfc6598) |
| `127.0.0.0/8` | Loopback | [RFC 1122](https://datatracker.ietf.org/doc/html/rfc1122) |
| `169.254.0.0/16` | Link-Local | [RFC 3927](https://datatracker.ietf.org/doc/html/rfc3927) |
| `224.0.0.0/4` | Multicast | [RFC 5771](https://datatracker.ietf.org/doc/html/rfc5771) |
| `0.0.0.0` | Unspecified | [RFC 1122](https://datatracker.ietf.org/doc/html/rfc1122) |

**IPv6 ranges excluded (will NOT match as public):**

| Range | Description | RFC |
|-------|-------------|-----|
| `fc00::/7` | Unique Local Address (ULA) | [RFC 4193](https://datatracker.ietf.org/doc/html/rfc4193) |
| `::1` | Loopback | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |
| `fe80::/10` | Link-Local | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |
| `ff00::/8` | Multicast | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |
| `fec0::/10` | Site-Local (deprecated) | [RFC 3879](https://datatracker.ietf.org/doc/html/rfc3879) |
| `::` | Unspecified | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |

Example rule:

```yaml
event: NETWORK_CONNECTIONS
op: is public address
path: event/NETWORK_ACTIVITY/SOURCE/IP_ADDRESS
```

### is public ipv4 address

The `is public ipv4 address` operator checks if an IP address at the path is a publicly routable IPv4 address. Returns false for IPv6 addresses.

**Ranges excluded (will NOT match as public):**

| Range | Description | RFC |
|-------|-------------|-----|
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | Private | [RFC 1918](https://datatracker.ietf.org/doc/html/rfc1918) |
| `100.64.0.0/10` | CGNAT/Shared Address Space | [RFC 6598](https://datatracker.ietf.org/doc/html/rfc6598) |
| `127.0.0.0/8` | Loopback | [RFC 1122](https://datatracker.ietf.org/doc/html/rfc1122) |
| `169.254.0.0/16` | Link-Local | [RFC 3927](https://datatracker.ietf.org/doc/html/rfc3927) |
| `224.0.0.0/4` | Multicast | [RFC 5771](https://datatracker.ietf.org/doc/html/rfc5771) |
| `0.0.0.0` | Unspecified | [RFC 1122](https://datatracker.ietf.org/doc/html/rfc1122) |

Example rule:

```yaml
event: NETWORK_CONNECTIONS
op: is public ipv4 address
path: event/NETWORK_ACTIVITY/SOURCE/IP_ADDRESS
```

### is public ipv6 address

The `is public ipv6 address` operator checks if an IP address at the path is a publicly routable IPv6 address. Returns false for IPv4 addresses.

**Ranges excluded (will NOT match as public):**

| Range | Description | RFC |
|-------|-------------|-----|
| `fc00::/7` | Unique Local Address (ULA) | [RFC 4193](https://datatracker.ietf.org/doc/html/rfc4193) |
| `::1` | Loopback | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |
| `fe80::/10` | Link-Local | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |
| `ff00::/8` | Multicast | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |
| `fec0::/10` | Site-Local (deprecated) | [RFC 3879](https://datatracker.ietf.org/doc/html/rfc3879) |
| `::` | Unspecified | [RFC 4291](https://datatracker.ietf.org/doc/html/rfc4291) |

Example rule:

```yaml
event: NETWORK_CONNECTIONS
op: is public ipv6 address
path: event/NETWORK_ACTIVITY/SOURCE/IP_ADDRESS
```

## Transforms

Transforms are transformations applied to the value being evaluated in an event, prior to the evaluation.

### file name

Sample: `file name: true`

The `file name` transform takes a `path` and replaces it with the file name component of the `path`. This means that a `path` of `c:\windows\system32\wininet.dll` will become `wininet.dll`.

### sub domain

Sample: `sub domain: "-2:"`

The `sub domain` extracts specific components from a domain name. The value of `sub domain` is in [slice notation](https://stackoverflow.com/questions/509211/understanding-slice-notation). It looks like `startIndex:endIndex`, where the index is 0-based and indicates which parts of the domain to keep.

Some examples:

- `0:2` means the first 2 components of the domain: `aa.bb` for `aa.bb.cc.dd`.
- `-1` means the last component of the domain: `cc` for `aa.bb.cc`.
- `1:` means all components starting at 1: `bb.cc` for `aa.bb.cc`.
- `:` means to test the operator to every component individually.

### is older than

Test if a value in event at the `"path": <>` parameter, assumed to be either a second-based epoch or a millisecond-based epoch is older than a number of seconds as specified by the `seconds` parameter, centered in time at "now" during evaluation.

Example rule:

```yaml
event: login-attempt
op: is older than
path: routing/event_time
seconds: 3600
```

where the example above would match on a `login-attempt` event that occurred more than 1h ago.

## Times

All operators support an optional parameter named `times`. When specified, it must contain a list of Time Descriptors when the accompanying operator is valid. Your rule can mix-and-match multiple Time Descriptors as part of a single rule on per-operator basis.

Here's an example rule that matches a Chrome process starting between 11PM and 5AM, Monday through Friday, Pacific Time:

```yaml
event: NEW_PROCESS
op: ends with
path: event/FILE_PATH
value: chrome.exe
case sensitive: false
times:
  - day_of_week_start: 2     # 1 - 7 (1 = Sunday, 7 = Saturday)
    day_of_week_end: 6       # 1 - 7 (1 = Sunday, 7 = Saturday)
    time_of_day_start: 2200  # 0 - 2359
    time_of_day_end: 2359    # 0 - 2359
    tz: America/Los_Angeles  # time zone
  - day_of_week_start: 2
    day_of_week_end: 6
    time_of_day_start: 0
    time_of_day_end: 500
    tz: America/Los_Angeles
```

### Time Zone

The `tz` should match a TZ database name from the [Time Zones Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).

## Value Modifiers

Several operators (`is`, `contains`, `starts with`, `ends with`, `is greater than`, `is lower than`) support special syntax in the `value` parameter to dynamically resolve values at evaluation time.

### Lookbacks

Use `<<path>>` to compare against a value from elsewhere in the same event:

```yaml
op: is
path: event/DESTINATION/IP_ADDRESS
value: <<event/SOURCE/IP_ADDRESS>>
```

### Sensor Variables

Use `[[variable_name]]` to compare against values stored in a [sensor variable](../3-detection-response/sensor-variables.md). Variables are set using the [`add var` response action](response-actions.md#add-var-del-var) and can hold multiple values. The operator checks if the value at `path` matches **any** value in the variable.

```yaml
op: is
path: event/FILE_PATH
value: '[[known-good-processes]]'
```

If the variable is empty or does not exist, the operator returns `false`. Combined with `not: true`, this allows rules to fire only when a variable is not set. See [Sensor Variables](../3-detection-response/sensor-variables.md) for detailed usage and examples.

---

## See Also

- [D&R Rules Overview](../3-detection-response/index.md)
- [Response Actions](response-actions.md)
- [Sensor Variables](../3-detection-response/sensor-variables.md)
- [Writing Rules](../3-detection-response/tutorials/writing-testing-rules.md)
