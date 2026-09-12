# DigitalOcean

The DigitalOcean CLI, or `doctl`, is the official CLI for the DigitalOcean API. With this component of the Cloud CLI Extension, you can interact with DigitalOcean directly from LimaCharlie.

This extension uses [DigitalOcean's official `doctl` CLI tool](https://github.com/digitalocean/doctl). [Reference documentation](https://docs.digitalocean.com/reference/doctl/reference/) is also available.

## Example

The following example of a response action will enumerate a list of compute droplets within a DigitalOcean instance.

```yaml
- action: extension request
  extension action: run
  extension name: ext-cloud-cli
  extension request:
    tool: '{{ "doctl" }}'
    command_line: '{{ "compute droplet list" }}'
    credentials: '{{ "hive://secret/secret-name" }}'
```

## Credentials

To utilize `doctl` capabilities, you will need:

- A personal access token. See DigitalOcean's [create-personal-access-token reference](https://docs.digitalocean.com/reference/api/create-personal-access-token/).
- Create a secret in the secrets manager in the following format:

  ```text
  personalAccessToken
  ```
