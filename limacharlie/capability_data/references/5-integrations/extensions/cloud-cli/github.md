# GitHub

The GitHub CLI is a tool that brings GitHub to the terminal, allowing you to interact with and control Git accounts, repositories, organizations, and users from the CLI. With this component of the Cloud CLI Extension, you can interact with GitHub directly from LimaCharlie.

This extension uses [the GitHub CLI](https://cli.github.com/manual/).

## Example

The following example returns a list of GitHub organizations.

```yaml
- action: extension request
  extension action: run
  extension name: ext-cloud-cli
  extension request:
    cloud: '{{ "gh" }}'
    command_line: '{{ "org list" }}'
    credentials: '{{ "hive://secret/secret-name" }}'
```

## Credentials

To utilize the GitHub CLI, you will need:

- A [personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- Create a secret in the secrets manager in the following format:

```text
access_token
```
