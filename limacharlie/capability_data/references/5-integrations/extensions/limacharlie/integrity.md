# Integrity

The Integrity Extension helps you manage all aspects of file or registry integrity monitoring (FIM and RIM, respectively). This extension automates integrity checks of file system and registry values through pattern-based rules.

## Enabling the Integrity Extension

To enable the Integrity extension, navigate to the [Integrity extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-integrity) in the marketplace. Select the Organization you wish to enable the extension for, and select **Subscribe**.

![integrity 1(1).png "image(242).png"](../../../assets/images/integrity-1(1).png "image(242).png")

After clicking **Subscribe**, the Infrastructure extension should be available almost immediately.

## Using the Integrity Extension

Once enabled, you will see an **File/Reg Integrity** option under **Automation** within the LimaCharlie web UI.

![integrity 2.png "image(243).png"](../../../assets/images/integrity-2.png "image(243).png")

Selecting this option allows you to customize **File & Registry Integrity Monitoring** rules, as seen in the screenshot below.

![integrity 3.png "image(244).png"](../../../assets/images/integrity-3.png "image(244).png")

Selecting **Add Monitoring Rule** will allow you to create a FIM or RIM rule, specifying a platform, Tag(s), and pattern(s).

![integrity 4.png "image(245).png"](../../../assets/images/integrity-4.png "image(245).png")

### Rule Patterns

Patterns are file or registry patterns and support wildcards (\*, ?, +). Windows directory separators (backslash, `"\"`) must be escape with a double-slash `"\\"`.

When a FIM or RIM rule is tripped, you will see a `FIM_HIT` event in the Sensor(s) timeline.

![integrity 5](../../../assets/images/integrity-5.png)

### Example Rule Patterns

#### Windows **File Monitoring**

| **Monitor a specific directory on all drives** | **Monitor a specific file on a specific drive** |
| --- | --- |
| ?:\\Windows\\System32\\drivers | C:\\Windows\\System32\\specialfile.exe |
| ?:\\inetpub\\wwwroot |  |

#### Windows Registry Monitoring

> All registry monitoring patterns MUST begin with **\\REGISTRY**, followed by the hive and then the path or value to monitor.

| Monitor for changes to system Run and RunOnce | Monitor all users for additions to a user's Run |
| --- | --- |
| \\REGISTRY\\MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\* | \\REGISTRY\\USER\S-\*\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\* |
| \\REGISTRY\\MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce\* |  |

#### Linux

| **Monitor for changes to root's authorized\_keys** | **Monitor for changes to all user private ssh directories** |
| --- | --- |
| /root/.ssh/authorized\_keys | /home/\*/.ssh/\* |

#### macOS

| Monitor for changes to user keychains | Monitor for changes to system keychains |
| --- | --- |
| /Users/\*/Library/Keychains/\* | /Library/Keychains |

### Linux Support

FIM is supported on Linux systems, however, support may vary based on Linux distribution and software.

#### Linux with eBPF Support

Linux hosts capable of running with [eBPF](https://ebpf.io/) have file notification and FIM capabilities on par with Windows and macOS.

#### Legacy Support

FIM is partially supported on systems without eBPF. Specified file expressions are actively monitored via `inotify` (as opposed to macOS and Windows, which utilize passive kernel monitoring). Due to [inotify](https://man7.org/linux/man-pages/man7/inotify.7.html) limitations, paths with wildcards are less efficient and only support monitoring up to 20 sub-directories covered by the wildcard. In addition to this, the path expressions should specify a final wildcard of *when all files under a directory need to be monitored. Omitting the final* `*` will result in only the top-level directory being monitoring.

## Actions via REST API

The following REST API actions can be sent to interact with the Integrity extension:

### List Rules

```json
{
  "action": "list_rules"
}
```

### Add Rule

```json
{
  "action": "add_rule",
  "name": "linux-root-ssh-configs",
  "patterns": [
    "/root/.ssh/*"
  ],
  "tags": [
    "vip",
    "workstation"
  ],
  "platforms": [
    "linux"
  ]
}
```

### Remove Rule

```json
{
  "action": "remove_rule",
  "name": "linux-ssh-configs"
}
```

## Related Articles

- [Reference: Endpoint Agent Commands](../../../8-reference/endpoint-commands.md)
- [Detection and Response Examples](../../../3-detection-response/examples.md)
- [Compliance Frameworks](../../../9-ai-sessions/compliance/frameworks.md) -- FIM rules ship as part of every framework's recommended baseline (PCI DSS Req 11.5.x, HIPAA §164.312(c)(1), CMMC SI.L2-3.14.1, etc.). The Compliance plugin's `compliance-baseline-deploy` skill deploys these rules into `ext-integrity` automatically.
- [Compliance Gap Analysis](../../../9-ai-sessions/compliance/gap-analysis.md) -- Surfaces missing FIM rules per framework and flags when `ext-integrity` is not subscribed.
