# Humio

Output events and detections to the [Humio.com](https://humio.com) service.

- `humio_repo`: the name of the humio repo to upload to.
- `humio_api_token`: the humio ingestion token.
- `endpoint_url`: optionally specify a custom endpoint URL, if you have Humio deployed on-prem use this to point to it, otherwise it defaults to the Humio cloud.

Example:

```text
humio_repo: sandbox
humio_api_token: fdkoefj0erigjre8iANUDBFyfjfoerjfi9erge
```

Note: You may need to [create a new parser in Humio](https://docs.humio.com/docs/parsers/creating-a-parser/) to correctly [parse timestamps](https://docs.humio.com/reference/query-functions/functions/parsetimestamp/).  You can use the following JSON parser:

```text
parseJson() | parseTimestamp(field=@timestamp,format="unixTimeMillis",timezone="Etc/UTC")
```

For the Community Edition of Humio, the `endpoint_url` is: `https://cloud.community.humio.com`.
