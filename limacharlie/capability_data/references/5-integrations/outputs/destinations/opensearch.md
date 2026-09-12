# OpenSearch

Output events and detections to [OpenSearch](https://opensearch.org/).

- `addresses`: the IPs or DNS where to send the data to
- `index`: the index name to send data to
- `username`: user name if using username/password auth
- `password`: password if using username/password auth

Example:

```text
addresses: https://1.2.3.4:9200, https://elastic.mydomain.com:9200
username: some
password: pass1234
index: limacharlie-events
```

## Related articles

- [Elastic](elastic.md)
- [ASW](scp.md)
