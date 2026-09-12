# File

## Overview

This Adapter allows you to ingest logs from a file, either as a one time operation or by following its output (like `tail -f`). A more detailed guide to file collection can be found in the [Log Collection Guide](../../log-collection-guide.md).

### Configuration

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

Adapter type `file`:

- `file_path`: simple file pattern like `./files_*.txt`
- `no_follow`: if `true`, the file content will be sent, but additions to the file will not be reported
- `inactivity_threshold`: the number of seconds after which an unmodified file becomes ignored (default: 86400, i.e. 24 hours)
- `reactivation_threshold`: the number of seconds within which a previously inactive file must be modified to resume tailing (default: 60)
- `backfill`: if `true`, a single pass at all the matching files will be made to ingest them, useful for historical ingestion
- `serialize_files`: if `true`, files will be ingested one at a time, useful for very large number of files that could blow up memory
- `poll`: if `true`, use polling instead of filesystem event notifications to detect file changes. See [Polling Mode](#polling-mode) below
- `multi_line_json`: if `true`, the adapter will buffer lines and assemble complete JSON objects spanning multiple lines before sending them
- `write_timeout_sec`: number of seconds before a write to LimaCharlie times out (default: 600)

### Polling Mode

By default, the file adapter relies on OS-level filesystem notifications (such as `inotify` on Linux or `kqueue` on BSD/macOS) to detect when new data is written to a file. While efficient, this mechanism can fail to detect changes in certain situations:

- **Log rotation**: When a log management tool (e.g. `newsyslog`, `logrotate`) rotates a file, the original file descriptor may become stale. The filesystem notification watcher may remain attached to the old (now renamed or deleted) file and miss writes to the new file at the same path.
- **Network and virtual filesystems**: NFS, CIFS/SMB, and some FUSE-based filesystems may not reliably deliver filesystem notifications.
- **Platform-specific quirks**: Some operating systems or filesystem drivers have incomplete or inconsistent notification support.

Setting `poll: true` switches the adapter to a polling-based approach that periodically checks the file for new content. This is slightly less efficient than event-driven notifications but is more reliable across different platforms and when log rotation is in use.

The adapter also performs its own inode-based rotation detection — if a file's inode changes between poll cycles, the adapter automatically closes the old file handle and opens the new file. This works in conjunction with polling mode to provide reliable collection across rotations.

**When to use `poll: true`:**

- You are running on FreeBSD, OpenBSD, NetBSD, or Solaris
- Your log files are rotated by tools like `newsyslog` or `logrotate`
- The adapter stops collecting after a log rotation event
- Your files reside on a network or virtual filesystem

**Example:**

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "freebsd-syslogs"
  file_path: "/var/log/messages"
  poll: true
```

### CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter file client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=text \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
file_path=/path/to/file
```
