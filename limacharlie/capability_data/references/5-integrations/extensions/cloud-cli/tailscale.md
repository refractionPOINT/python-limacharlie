# Tailscale

The Tailscale CLI brings Tailscale's powerful software-defined networking, based on WireGuard, to the command line. This Extension allows you to interact with a Tailscale network(s) from LimaCharlie.

This extension uses [Tailscale's native CLI](https://tailscale.com/kb/1031/install-linux).

## Example

Returns the current Tailscale status.

```yaml
- action: extension request
  extension action: run
  extension name: ext-cloud-cli
  extension request:
    cloud: '{{ "tailscale" }}'
    command_line: '{{ "status --json" }}'
    credentials: '{{ "hive://secret/secret-name" }}'
```

## Credentials

To utilize Tailscale's CLI capabilities, you will need:

- An [auth key](https://tailscale.com/kb/1085/auth-keys)
- Create a secret in the secrets manager in the following format:

```text
authKey
```

## Command-line Interface

LimaCharlie Extensions allow users to expand and customize their security environments by integrating third-party tools, automating workflows, and adding new capabilities. Organizations subscribe to Extensions, which are granted specific permissions to interact with their infrastructure. Extensions can be private or public, enabling tailored use or broader community sharing. This framework supports scalability, flexibility, and secure, repeatable deployments.
