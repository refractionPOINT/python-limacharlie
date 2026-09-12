# Lookup Manager

The Lookup Manager Extension allows you to create, maintain & automatically refresh lookups in the Organization to then reference them in Detection & Response Rules.

The saved Lookup Configurations can be managed across tenants using Infrastructure as Code extension. To manage lookup versions across all of your tenants, update the file under the original Authenticated Resource Locator.

Every 24 hours, LimaCharlie will sync all of the lookups in the configuration. Lookups can also be manually synced by clicking the `Manual Sync` button on the extension page. When a lookup configuration is added, it will **not** be automatically synced immediately, unless you click on `Manual Sync`.

Lookup sources can be either direct links (URLs) to a given lookup or [ARLs](../../../8-reference/authentication-resource-locator.md).

Example JSON lookup: [LOLDrivers API](https://loldrivers.io/api/drivers.json)

## Usage

### Option 1: Preconfigured Lookups

LimaCharlie provides a curated list of several publicly available JSON lookups for use within your organization. These are provided in the lookup manager GUI.

See [lc-public-lookups](https://github.com/refractionpoint/lc-public-lookups) for the contents of each public lookup.

![image (1).png "Screenshot 2024 10 22 at 13.23.35(2).png"](../../../assets/images/image-(1).png "Screenshot 2024-10-22 at 13.23.35(2).png")

![image (2).png "Screenshot 2024 10 22 at 13.23.45(1).png"](../../../assets/images/image-(2).png "Screenshot 2024-10-22 at 13.23.45(1).png")

### Option 2: Publicly available Lookups

Giving the lookup configuration a name, the URL *or* [ARL](../../../8-reference/authentication-resource-locator.md), and clicking the Save button will create the new lookup source to sync to your lookups.

`[github,my-org/my-repo-name/path/to/lookup]`

### Option 3: Private Lookup Repository

To use a lookup from a private Github repository you will need to make use of an [Authentication Resource Locator](../../../8-reference/authentication-resource-locator.md).

**Step 1: Create a token in GitHub**
In GitHub go to *Settings* and click *Developer settings* in the left hand side bar.

Next click *Personal access token* followed by *Generate new token*. Select repo permissions and finally *Generate token*.

**Step 2: Connect LimaCharlie to your GitHub Repository**
Inside of LimaCharlie, click on *Lookup Manager* in the left hand menu. Then click *Add New Lookup Configuration*.

Give your lookup a name and then use the token you generated with the following format linked to your repository.

`[github,my-org/my-repo-name/path/to/lookup,token,bfuihferhf8erh7ubhfey7g3y4bfurbfhrb]`

## Infrastructure as Code

Example:

```yaml
hives:
    extension_config:
        ext-lookup-manager:
            data:
                lookup_manager_rules:
                    - arl: ""
                      format: json
                      name: alienvault
                      predefined: '[https,storage.googleapis.com/lc-lookups-bucket/alienvault-ip-reputation.json]'
                      tags:
                        - alienvault
                    - arl: ""
                      format: json
                      name: tor
                      predefined: '[https,storage.googleapis.com/lc-lookups-bucket/tor-ips.json]'
                      tags:
                        - tor
            usr_mtd:
                enabled: true
                expiry: 0
                tags: []
                comment: ""
```
