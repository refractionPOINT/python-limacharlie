# Infrastructure

The Infrastructure Extension allows you to perform infrastructure-as-code (IaC) modifications to your Organization. IaC modifications can be made in the web UI or via the LimaCharlie [CLI tool](https://github.com/refractionPOINT/python-limacharlie/#configs-1). Users can create new organizations from known templates or maintain a common configuration across multiple organizations.

> Scaling Organization Management
>
> If you're a managed service company or need to manage a large number of Organizations, consider LimaCharlie's [MSSP demo setup](https://github.com/refractionPOINT/mssp-demo).

## Enabling the Infrastructure Extension

To enable the Infrastructure extension, navigate to the [Infrastructure extension page](https://app.limacharlie.io/add-ons/extension-detail/ext-infrastructure) in the marketplace. Select the organization you wish to enable the extension for, and select **Subscribe**.

![infra 1.png "image(234).png"](../../../assets/images/infra-1.png "image(234).png")

After clicking **Subscribe**, the Infrastructure extension should be available almost immediately.

> Where to start?
>
> IaC can be a powerful tool for rapidly deploying and managing Organizations within LimaCharlie. We provide [example templates and configurations](https://github.com/refractionPOINT/templates) on GitHub.

## Using the Infrastructure Extension

Once enabled, you will see an Infrastructure as Code option under the **Organization Settings** within the LimaCharlie web UI. The extension also becomes available via the REST API.

![infra 2.png "image(240).png"](../../../assets/images/infra-2.png "image(240).png")

Within the Infrastructure As Code module, you can:

- **Apply a New Config** to an existing organization. Changes are made additively, and are good for merging new configuration parameters into your organization.
- **Edit the Entire Configuration** for an existing organization. This is your current configuration, and can be modified directly in the web UI.
- Perform **Fetch**, **Push**, or **Push-from-file** operations.

![infra 3.png "image(241).png"](../../../assets/images/infra-3.png "image(241).png")

## Actions via REST API

The REST interface for the Infrastructure extension mimics the CLI tool. The following REST API actions can be sent to interact with the Infrastructure extension:

```json
{
  "params": {
    "sync_artifacts": {
      "type": "bool",
      "desc": "applies to artifacts"
    },
    "is_force": {
      "type": "bool",
      "desc": "make the org an exact copy of the configuration provided."
    },
    "is_dry_run": {
      "type": "bool",
      "desc": "do not apply config, just simulate."
    },
    "sync_integrity": {
      "type": "bool",
      "desc": "applies to integrity"
    },
    "action": {
      "is_required": true,
      "values": [
        "push",
        "fetch"
      ],
      "type": "enum",
      "desc": "action to take."
    },
    "sync_org_values": {
      "type": "bool",
      "desc": "applies to org_values"
    },
    "sync_resources": {
      "type": "bool",
      "desc": "applies to resources"
    },
    "config": {
      "type": "str",
      "desc": "configuration to apply."
    },
    "config_source": {
      "type": "str",
      "desc": "ARL where configs to apply are located."
    },
    "ignore_inaccessible": {
      "desc": "ignore resources which are inaccessible like locked or segmented.",
      "type": "bool"
    },
    "sync_fp": {
      "type": "bool",
      "desc": "applies to fp"
    },
    "sync_exfil": {
      "desc": "applies to exfil",
      "type": "bool"
    },
    "sync_dr": {
      "type": "bool",
      "desc": "applies to dr"
    },
    "sync_outputs": {
      "type": "bool",
      "desc": "applies to outputs"
    },
    "config_root": {
      "type": "str",
      "desc": "file name of the root config within config_source to apply."
    }
  }
}
```

## Related Articles

- [Integrity](integrity.md)
