# Sublime

The Sublime Security CLI brings the power of Sublime's email platform to the command-line. With this component of the Cloud CLI Extension, you can interact with Sublime's email platform directly from LimaCharlie.

This extension uses [Sublime Security's native CLI](https://docs.sublimesecurity.com/reference/analysis-api-cli). The CLI is a Python package — its [source code](https://github.com/sublime-security/sublime-cli) is on GitHub.

## Example

The following response action returns information about the currently authentication Sublime Security user.

```yaml
- action: extension request
  extension action: run
  extension name: ext-cloud-cli
  extension request:
    cloud: '{{ "sublime" }}'
    command_line: '{{ "me" }}'
    credentials: '{{ "hive://secret/secret-name" }}'
```

## Credentials

To utilize Sublime's CLI capabilities, you will need:

- You will need an API key. See Sublime Security's [authentication reference](https://docs.sublimesecurity.com/reference/authentication) for provisioning details.
- Create a secret in the secrets manager in the following format:

```text
api_key
```
