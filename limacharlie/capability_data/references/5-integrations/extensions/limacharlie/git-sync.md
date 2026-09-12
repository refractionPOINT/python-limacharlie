# Git Sync

The Git Sync Extension is a tool that automates the management of Infrastructure-as-Code (IaC) configurations. It simplifies the process of deploying and managing infrastructure by synchronizing changes between a Git repository and target organizations.

**Key features:**

- **Centralized Configuration:** Stores all IaC configurations in a single Git repository.
- **Recurring Apply:** Can automatically sync IaC changes between Git and LC organizations at regular intervals.
- **Recurring Export:** Can automatically export IaC from LC organizations to GitHub at regular intervals.
- **Export Request:** Allows you to export the configuration of an Organization into the Git repository.
- **Automated Deployment:** Helps automate the deployment process, reducing manual effort.
- MSSP**-Friendly:** Designed to accommodate multiple organizations within a single repository, allowing for global configurations to be shared between orgs.
- **Flexible Configuration:** Allows for customization and additional configuration directories.
- **Transparent Operations:** Tracks operations through an extension Sensor.

By using `ext-git-sync`, you can streamline your IaC workflows, improve consistency, and reduce the risk of errors.

## Use Cases

### Sync FROM Git

If you have a properly structured git repository containing org configurations, the extension can sync the running org configurations with the contents of the configs in git.

![d2 (1).png "pull config(1).png"](../../../assets/images/d2-(1).png "pull_config(1).png")

### Export TO Git

Assuming you have an empty git repository, you can configure the extension to export the current org configuration to the repository. It will be placed in an `exports` subdirectory.

![d2 (2).png "push config(1).png"](../../../assets/images/d2-(2).png "push_config(1).png")

## Git Repo Structure

For applying org configs from a git repository, the repo must adhere to the following structure. The root of the repository must contain an `orgs` directory with `[org-id]` child directories, each containing an `index.yaml` .

```text
.
└── orgs [required]
    └── a326700d-3cd7-49d1-ad08-20b396d8549d [required]
        └── index.yaml [required]
```

The `index.yaml` determines which other files in the repo are included in the configuration for this org.

For instance, assume all of the configurations for this org were unique to this org and could be nested inside of the org's directory.

```text
.
└── orgs
    └── a326700d-3cd7-49d1-ad08-20b396d8549d
        ├── extensions.yaml
        ├── hives
        │   ├── cloud_sensor.yaml
        │   ├── dr-general.yaml
        │   ├── dr-managed.yaml
        │   ├── dr-service.yaml
        │   ├── extension_config.yaml
        │   ├── fp.yaml
        │   ├── lookup.yaml
        │   ├── query.yaml
        │   ├── secret.yaml
        │   └── yara.yaml
        ├── index.yaml
        ├── installation_keys.yaml
        ├── org_values.yaml
        ├── outputs.yaml
        └── resources.yaml
```

Notice that all configurations for this org are contained within the org's own directory. In this case, the `index.yaml` would simply contain references to the relative path of this org's configuration files. See below for an example of the contents of `index.yaml` for this use case.

```yaml
version: 3
include:
    - extensions.yaml
    - hives/fp.yaml
    - outputs.yaml
    - resources.yaml
    - hives/query.yaml
    - hives/yara.yaml
    - hives/dr-managed.yaml
    - hives/lookup.yaml
    - hives/dr-service.yaml
    - org_values.yaml
    - installation_keys.yaml
    - hives/secret.yaml
    - hives/cloud_sensor.yaml
    - hives/dr-general.yaml
    - hives/extension_config.yaml
```

### Sharing configurations across multiple orgs

Now, assume you have a global rule set you want to apply across many orgs. You could structure the repo similar to the example below.

```text
.
├── hives
│   ├── dr-general.yaml
│   └── yara.yaml
└── orgs
    ├── 7e41e07b-c44c-43a3-b78d-41f34204789d
    │   └── index.yaml
    ├── a326700d-3cd7-49d1-ad08-20b396d8549d
    │   └── index.yaml
    └── cb639126-e0bc-4563-a577-2e559c0610b2
        └── index.yaml
```

The corresponding `index.yaml` at each org level would look similar to the following

```yaml
version: 3
include:
    - ../../hives/yara.yaml
    - ../../hives/dr-general.yaml
```

### Exporting configurations

Configuration exports will be placed in a separate `exports` subdirectory to avoid overwriting configurations that are pushed across multiple organizations.

```text
.
└── exports
    └── orgs
        └── a326700d-3cd7-49d1-ad08-20b396d8549d
            ├── extensions.yaml
            ├── hives
            │   ├── cloud_sensor.yaml
            │   ├── dr-general.yaml
            │   ├── dr-managed.yaml
            │   ├── dr-service.yaml
            │   ├── extension_config.yaml
            │   ├── fp.yaml
            │   ├── lookup.yaml
            │   ├── query.yaml
            │   ├── secret.yaml
            │   └── yara.yaml
            ├── index.yaml
            ├── installation_keys.yaml
            ├── org_values.yaml
            ├── outputs.yaml
            └── resources.yaml
```

## Setting up Git Sync with Github

This guide walks you through the process of configuring Git synchronization between GitHub and LimaCharlie, allowing for automated deployment and version control of your security configurations.

### Step 0: Making a Git Sync specific SSH Key

- First create the directory

`mkdir -p ~/.ssh/gitsync`

- Set appropriate permissions for the directory

`chmod 700 ~/.ssh/gitsync`

- Now generate the SSH key

`ssh-keygen -t ed25519 -C "limacharlie-gitsync" -f ~/.ssh/gitsync/id_ed25519`

### Step 1: Generate GitHub Deploy Keys

1. Navigate to your GitHub repository
2. Click on the **Settings** tab
3. In the left sidebar, select **Deploy keys**
4. Click the **Add deploy key** button
5. Enter a descriptive title for your key (e.g., "LimaCharlie Git Sync Integration")
6. Paste your public SSH key into the "Key" field
7. **Important:** Check the box for **Allow write access**
8. Click **Add key** to save

### Step 2: Store SSH Private Key in LimaCharlie

1. Log in to your LimaCharlie account
2. Navigate to the **Secret Manager** section of your Organization
3. Click **Create New Secret**
4. Choose a descriptive name for your secret (e.g., "github-deploy-key")
5. Paste the **private** part of your SSH key into the value field
6. Save the secret

### Step 3: Configure Git Sync in LimaCharlie

1. Navigate to the **Git Sync** section in LimaCharlie
2. Under the **SSH Key** section, select **Secret Manager**
3. From the dropdown menu, select the secret you created in Step 2
4. Set the **user name** to `git`
5. Copy the SSH URL from your GitHub repository (found on the repository's main page, under Code)
6. Paste the SSH URL into the **repository** URL field in LimaCharlie
7. Configure the **branch** name (required)
8. Select the push and pull options which allow you to specify which items to push to or pull from Git configurations.
9. Optionally, select push and pull schedules if you wish to regularly sync or export your Infrastructure as Code configurations to and from LimaCharlie. This will create D&R rules on the backend that kick off the push and pull actions on the selected schedule/interval.
10. Click **save settings**.

### Step 4: Verify Integration

1. Perform a test commit to your GitHub repository by clicking "Push to Git" in the upper right corner.

2. Verify that your configuration has been pushed to Github.

### Troubleshooting

If you encounter synchronization issues:

- Verify that the deploy key has proper write permissions
- Ensure the correct SSH URL format is used (should begin with `git@github.com:`)
- Check that the private key in Secret Manager matches the public key added to GitHub

[Infrastructure](infrastructure.md)
