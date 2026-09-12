# Usage Alerts

The usage alerts Extension allows you to create, maintain, & automatically refresh usage alert conditions for an Organization.

For example, you can create a usage alert rule that will fire a detection when artifact downloads have reached a 1GB threshold in the last 30 days (43200 minutes). This alert will be saved as a managed rule. When the threshold is reached, a detection will be created with the following `cat`:

`Usage alert - Output data over threshold - 1024 MB in 30.00 days`

These alert rules can be managed across tenants using the Infrastructure as Code extension.

Every hour, LimaCharlie will sync all of the usage alert rules in the configuration. They can also be manually synced by clicking the `Sync Usage Alert Rules` button on the extension page. When a usage alert rule is added, it will **not** be automatically synced immediately, unless you click on `Sync Usage Alert Rules`.

**NOTE**: The maximum timeframe is currently 43200 minutes (30 days).

## Usage - GUI

To define a new usage alert, simply click on the `Add New Usage Alert` button in the extension UI. Give it a name, like `Output data over threshold`, select a SKU (in this case, `output_data`), a timeframe, a limit, and click `Save`. ![image(275).png "image(275).png"](../../../assets/images/image(275).png "image(275).png")

If you want it to be added immediately, click on the `Sync Usage Alert Rules` button. Otherwise, it will get pushed automatically at the next hour interval.

![image(278).png "image(278).png"](../../../assets/images/image(278).png "image(278).png")

This will create a managed D&R rule on the backend in the `dr-managed` hive and will sync automatically every hour.

```yaml
hives:
    dr-managed:
        Output data over threshold:
            data:
                detect:
                    event: billing_record
                    op: and
                    rules:
                        - op: is
                          path: event/record/cat
                          value: output
                        - op: is
                          path: event/record/k
                          value: bytes_tx
                    target: billing
                respond:
                    - action: report
                      name: Usage alert - Output data over threshold - 1024 MB in 24.00 hours
                      suppression:
                        count_path: event/record/v
                        keys:
                            - output
                            - bytes_tx
                            - ext-usage-alerts
                            - Output data over threshold
                        max_count: 1.073741824e+09
                        min_count: 1.073741824e+09
                        period: 43200m
```

## Usage - Infrastructure as Code

If you are managing your organizations via infrastructure as code, you can also configure these rules in the `extension_config` hive.

```yaml
hives:
    extension_config:
        ext-usage-alerts:
            data:
                usage_alert_rules:
                    - enabled: true
                      limit: 1024
                      name: Output data over threshold
                      sku: output_data
                      timeframe: 43200
            usr_mtd:
                enabled: true
                expiry: 0
                tags: []
                comment: ""
```
