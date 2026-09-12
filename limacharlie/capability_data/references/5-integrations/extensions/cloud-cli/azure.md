# Azure

The Azure CLI is a set of commands used to create and manage Azure resources. With this component of the Cloud CLI Extension, you can interact with Azure directly from LimaCharlie.

This extension uses [the Azure CLI](https://learn.microsoft.com/en-us/cli/azure/get-started-with-azure-cli).

## Example

The following example returns a list of virtual machines and their respective details in Azure.

```yaml
- action: extension request
  extension action: run
  extension name: ext-cloud-cli
  extension request:
    tool: '{{ "az" }}'
    command_line: '{{ "vm list" }}'
    credentials: '{{ "hive://secret/secret-name" }}'
```

## Credentials

To utilize the Azure CLI, you will need:

- An application and a [service principal](https://learn.microsoft.com/en-us/entra/identity-platform/howto-create-service-principal-portal) with the appropriate permissions and a [client secret](https://learn.microsoft.com/en-us/entra/identity-platform/howto-create-service-principal-portal#option-3-create-a-new-client-secret)
- Create a secret in the secrets manager in the following format:

```text
appID/clientSecret/tenantID
```
