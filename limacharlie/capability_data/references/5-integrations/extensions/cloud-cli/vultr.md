# Vultr

The [Vultr](https://vultr.com/) CLI, or `vultr-cli`, is the official CLI for the Vultr API. With this component of the Cloud CLI Extension, you can interact with Vultr directly from LimaCharlie.

This extension uses [Vultr's official CLI tool](https://github.com/vultr/vultr-cli). [Reference documentation](https://www.vultr.com/news/how-to-easily-manage-instances-with-vultr-cli/) is also available.

## Example

The following example of a response action will enumerate a list of instance within a Vultr account.

```yaml
- action: extension request
  extension action: run
  extension name: ext-cloud-cli
  extension request:
    cloud: '{{ "vultr-cli" }}'
    command_line: '{{ "instance list" }}'
    credentials: '{{ "hive://secret/secret-name" }}'
```

## Credentials

To utilize `vultr-cli` capabilities, you will need:

- A personal access token from [Vultr's API settings page](https://my.vultr.com/settings/#settingsapi).
- Your access token will need to have access control open to IPv6
  <!-- Screenshot of Vultr access control settings was unavailable during migration from document360 -->
- Create a secret in the secrets manager in the following format:

  ```text
  personalAccessToken
  ```
