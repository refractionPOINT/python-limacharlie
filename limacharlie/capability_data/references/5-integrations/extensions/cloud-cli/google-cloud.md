# Google Cloud

The Google Cloud command line interface, or gcloud CLI, allows you to create and manage Google Cloud resources and services directly on the command line. With this component of the Cloud CLI Extension, you can interact with Google Cloud directly from LimaCharlie.

This extension uses [Google Cloud's native CLI tool](https://cloud.google.com/cli).

## Example

The following example stops the specified GCP compute instance.

```yaml
- action: extension request
  extension action: run
  extension name: ext-cloud-cli
  extension request:
    tool: '{{ "gcloud" }}'
    command_tokens:
      - compute
      - instances
      - stop
      - '{{ .routing.hostname }}'
    credentials: '{{ "hive://secret/secret-name" }}'
```

## Credentials

To utilize Google Cloud CLI capabilities, you will need:

- A GCP service account JSON key. See Google Cloud's [service account keys guide](https://cloud.google.com/iam/docs/keys-create-delete).
- Create a secret in the secrets manager in the following format:

  ```json
  {
      "type": "",
      "project_id": "",
      "private_key_id": "",
      "private_key": "",
      "client_email": "",
      "client_id": "",
      "auth_uri": "",
      "token_uri": "",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_x509_cert_url": "",
      "universe_domain": "googleapis.com"
  }
  ```
