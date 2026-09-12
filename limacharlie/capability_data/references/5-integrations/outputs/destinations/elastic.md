# Elastic

Output events and detections to [Elastic](https://www.elastic.co/).

- `addresses`: the IPs or DNS where to send the data to.
- `index`: the index name to send data to.
- `username`: user name if using username/password auth. (use either username/password -or- API key)
- `password`: password if using username/password auth.
- `cloud_id`: Cloud ID from Elastic.
- `api_key`: API key; if using it for auth. (use either username/password -or- API key)
- `is_create_action`: if `true`, the `_bulk` request uses the `create` action instead of `index`. Required when sending to a data stream.
- `is_compress_request`: if `true`, the `_bulk` request body is gzipped.

Example:

```text
addresses: 11.10.10.11,11.10.11.11
username: some
password: pass1234
index: limacharlie
```

## Sending to a data stream

Elasticsearch [data streams](https://www.elastic.co/docs/manage-data/data-store/data-streams)
support only the `create` action in a
[`_bulk`](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
request. By default this output uses the `index` action, which a data stream
rejects, so set `is_create_action` to `true` when the value of `index` names a
data stream:

```text
addresses: https://elastic.mydomain.com:9200
api_key: some-api-key
index: logs-limacharlie-default
is_create_action: true
```

The `index` value stays a plain name; Elastic resolves it to the data stream's
backing indices and applies the lifecycle policy configured on the Elastic side.

### Timestamp requirement

Elastic also requires that every document indexed into a data stream carry a
`@timestamp` field mapped as `date` or `date_nanos`. LimaCharlie records do not
have a top-level `@timestamp`; their time is in `routing.event_time`, a Unix
timestamp in milliseconds, which the default `date` mapping accepts as
`epoch_millis`.

So either add the field on the Elastic side with an ingest pipeline on the data
stream, or add it to the records themselves with the output's
`custom_transform`. Prefix the key with `+` to put the transform in additive
mode, which keeps the rest of the record instead of replacing it with only the
listed fields:

```text
custom_transform: |-
  {
    "+@timestamp": "routing.event_time"
  }
```

The unquoted `routing.event_time` is a field path rather than a template
string, so the value is copied as a number and Elastic reads it as
`epoch_millis`.

See [Template Strings and Transforms](../../../4-data-queries/template-transforms.md)
for the transform syntax.

## Compressing requests

Setting `is_compress_request` to `true` gzips the `_bulk` request body and sends
it with `Content-Encoding: gzip`, which Elasticsearch decompresses
transparently. LimaCharlie's JSON compresses well, so this cuts the bytes
leaving LimaCharlie for your cluster substantially, at the cost of some CPU
spent compressing. It is independent of `is_create_action` and works with both
bulk actions.

```text
addresses: https://elastic.mydomain.com:9200
api_key: some-api-key
index: limacharlie
is_compress_request: true
```

## Related articles

- [OpenSearch](opensearch.md)

## What's Next

- [Google Cloud BigQuery](bigquery.md)
