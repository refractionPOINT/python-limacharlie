# Reference: Endpoint Agent Commands

## Supported Commands by OS

For commands which emit a report/reply event type from the agent, the corresponding event type is provided.

| Command | Report/Reply Event | macOS | Windows | Linux | Chrome | Edge |
| --- | --- | --- | --- | --- | --- | --- |
| [artifact\_get](#artifact_get) | [LOG\_GET\_REP](edr-events.md#log_get_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [container\_list](#container_list) | [CONTAINER\_LIST\_REP](edr-events.md#container_list_rep) |  |  | ☑️ |  |  |
| deny\_tree | N/A | ☑️ | ☑️ | ☑️ |  |  |
| [dir\_find](#dir_find) | [DIR\_FIND\_REP](edr-events.md#dir_find_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [dir\_find\_hash](#dir_findhash) | [DIR\_FINDHASH\_REP](edr-events.md#dir_findhash_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [dir\_list](#dir_list) | [DIR\_LIST\_REP](edr-events.md#dir_list_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [dns\_resolve](#dns_resolve) | [DNS\_REQUEST](edr-events.md#dns_request) | ☑️ | ☑️ | ☑️ | ☑️ | ☑️ |
| [doc\_cache\_get](#doc_cache_get) | [GET\_DOCUMENT\_REP](edr-events.md#get_document_rep) | ☑️ | ☑️ |  |  |  |
| [get\_debug\_data](#get_debug_data) | [DEBUG\_DATA\_REP](edr-events.md#debug_data_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [exfil\_add](#exfil_add) | [CLOUD\_NOTIFICATION](edr-events.md#cloud_notification) | ☑️ | ☑️ | ☑️ |  |  |
| [exfil\_del](#exfil_del) | [CLOUD\_NOTIFICATION](edr-events.md#cloud_notification) | ☑️ | ☑️ | ☑️ |  |  |
| [exfil\_get](#exfil_get) | [GET\_EXFIL\_EVENT\_REP](edr-events.md#get_exfil_event_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [file\_del](#file_del) | [FILE\_DEL\_REP](edr-events.md#file_del_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [file\_get](#file_get) | [FILE\_GET\_REP](edr-events.md#file_get_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [file\_grep](#file_grep) | [FILE\_GREP\_REP](edr-events.md#file_grep_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [file\_hash](#file_hash) | [FILE\_HASH\_REP](edr-events.md#file_hash_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [file\_info](#file_info) | [FILE\_INFO\_REP](edr-events.md#file_info_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [file\_mov](#file_mov) | [FILE\_MOV\_REP](edr-events.md#file_mov_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [fim\_add](#fim_add) | [FIM\_ADD](edr-events.md#fim_add) | ☑️ | ☑️ | ☑️ |  |  |
| [fim\_del](#fim_del) | [FIM\_REMOVE](edr-events.md#fim_remove) | ☑️ | ☑️ | ☑️ |  |  |
| [fim\_get](#fim_get) | [FIM\_LIST\_REP](edr-events.md#fim_list_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [hidden\_module\_scan](#hidden_module_scan) | [HIDDEN\_MODULE\_DETECTED](edr-events.md#hidden_module_detected) |  | ☑️ | ☑️ |  |  |
| [history\_dump](#history_dump) | [HISTORY\_DUMP\_REP](edr-events.md#history_dump_rep) | ☑️ | ☑️ | ☑️ | ☑️ | ☑️ |
| [log\_get](#log_get) | N/A |  | ☑️ |  |  |  |
| logoff | N/A | ☑️ | ☑️ | ☑️ |  |  |
| [mem\_find\_handle](#mem_find_handle) | [MEM\_FIND\_HANDLES\_REP](edr-events.md#mem_find_handles_rep) |  | ☑️ |  |  |  |
| [mem\_find\_string](#mem_find_string) | [MEM\_FIND\_STRING\_REP](edr-events.md#mem_find_string_rep) | ☑️ | ☑️ | ☑️ |  |  |
| mem\_handles | [MEM\_HANDLES\_REP](edr-events.md#mem_handles_rep) |  | ☑️ |  |  |  |
| [mem\_map](#mem_map) | [MEM\_MAP\_REP](edr-events.md#mem_map_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [mem\_read](#mem_read) | [MEM\_READ\_REP](edr-events.md#mem_read_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [mem\_strings](#mem_strings) | [MEM\_STRINGS\_REP](edr-events.md#mem_strings_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [netstat](#netstat) | [NETSTAT\_REP](edr-events.md#netstat_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [os\_autoruns](#os_autoruns) | [OS\_AUTORUNS\_REP](edr-events.md#os_autoruns_rep) | ☑️ | ☑️ |  |  |  |
| [os\_drivers](#os_drivers) | N/A |  | ☑️ |  |  |  |
| [os\_kill\_process](#os_kill_process) | [OS\_KILL\_PROCESS\_REP](edr-events.md#os_kill_process_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [os\_packages](#os_packages) | [OS\_PACKAGES\_REP](edr-events.md#os_packages_rep) |  | ☑️ | ☑️ | ☑️ | ☑️ |
| [os\_processes](#os_processes) | [OS\_PROCESSES\_REP](edr-events.md#os_processes_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [os\_resume](#os_resume) | [OS\_RESUME\_REP](edr-events.md#os_resume_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [os\_services](#os_services) | [OS\_SERVICES\_REP](edr-events.md#os_services_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [os\_suspend](#os_suspend) | [OS\_SUSPEND\_REP](edr-events.md#os_suspend_rep) | ☑️ | ☑️ | ☑️ |  |  |
| os\_users | [OS\_USERS\_REP](edr-events.md#os_users_rep) |  | ☑️ |  |  |  |
| [os\_version](#os_version) | [OS\_VERSION\_REP](edr-events.md#os_version_rep) | ☑️ | ☑️ | ☑️ |  |  |
| put | [RECEIPT](edr-events.md#receipt) | ☑️ | ☑️ | ☑️ |  |  |
| [rejoin\_network](#rejoin_network) | [REJOIN\_NETWORK](edr-events.md#rejoin_network) | ☑️ | ☑️ | ☑️ | ☑️ | ☑️ |
| [repo\_list](#repo_list) | [REPO\_LIST\_REP](edr-events.md#repo_list_rep) | ☑️ | ☑️ | ☑️ |  |  |
| restart | N/A | ☑️ | ☑️ | ☑️ |  |  |
| [run](#run) | N/A | ☑️ | ☑️ | ☑️ |  |  |
| seal |  |  | ☑️ |  |  |  |
| [segregate\_network](#segregate_network) | [SEGREGATE\_NETWORK](edr-events.md#segregate_network) | ☑️ | ☑️ | ☑️ | ☑️ | ☑️ |
| set\_performance\_mode | N/A | ☑️ | ☑️ | ☑️ |  |  |
| shutdown |  | ☑️ | ☑️ | ☑️ |  |  |
| [uninstall](#uninstall) | N/A | ☑️ | ☑️ | ☑️ |  |  |
| [usb\_list\_devices](#usb_list_devices) | [USB\_DEVICE\_LIST\_REP](edr-events.md#usb_device_list_rep) | ☑️ | ☑️ | ☑️ |  |  |
| [upgrade\_core](#upgrade_core) | N/A | ☑️ | ☑️ | ☑️ |  |  |
| [yara\_scan](#yara_scan) | [YARA\_DETECTION](edr-events.md#yara_detection) | ☑️ | ☑️ | ☑️ |  |  |
| yara\_update | N/A | ☑️ | ☑️ | ☑️ |  |  |
| epp\_status | [EPP\_STATUS\_REP] | ☑️ |  |  |  |  |
| [epp\_scan](#epp_scan) | [EPP\_SCAN\_REP] | ☑️ |  |  |  |  |
| [epp\_list\_exclusions](#epp_list_exclusions) | [EPP\_LIST\_EXCLUSIONS\_REP] | ☑️ |  |  |  |  |
| [epp\_add\_exclusion](#epp_add_exclusion) | [EPP\_ADD\_EXCLUSION\_REP] | ☑️ |  |  |  |  |
| [epp\_rem\_exclusion](#epp_rem_exclusion) | [EPP\_REM\_EXCLUSION\_REP] | ☑️ |  |  |  |  |
| [epp\_list\_quarantine](#epp_list_quarantine) | [EPP\_LIST\_QUARANTINE\_REP] | ☑️ |  |  |  |  |

## Command Descriptions

### artifact_get

Collect one or more artifacts from a sensor and upload them to Artifact Collection.

Exactly one of `--file`, `--source` or `--root-dir` must be given. `--root-dir`
selects the bounded multi-file mode, which walks a directory tree and uploads
every file matching the include expressions, subject to the budgets below.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `--file`: Single file path to collect from the sensor
- `--source`: OS-specific artifact source to collect (for example a Windows Event Log channel)
- `--root-dir`: Root directory for bounded multi-file retrieval
- `-x, --file-exp` (optional): Glob to retrieve under `--root-dir`, repeatable; defaults to all files
- `-X, --exclude-exp` (optional): Glob to exclude under `--root-dir`, repeatable
- `-d, --depth` (optional): Maximum directory depth for multi-file retrieval (default: 6, max: 32)
- `--max-files` (optional): Maximum files to upload (default: 25, max: 100)
- `--max-file-size` (optional): Maximum size in bytes of each uploaded file (default: 8388608, max: 67108864)
- `--max-total-bytes` (optional): Maximum bytes uploaded across all files (default: 67108864, max: 1073741824)
- `--max-files-scanned` (optional): Maximum filesystem entries to examine (default: 250000)
- `--max-seconds` (optional): Wall-clock discovery budget in seconds (default: 120, max: 900)
- `--type` (optional): Artifact type (e.g., "pcap")
- `--payload-id` (optional): Idempotent payload ID for the request (auto-generated if not
  provided). Not valid with `--root-dir`; multi-file mode generates one payload ID per file.
- `--days-retention` (optional): Number of days the artifact should be retained (default: 30)
- `--is-ignore-cert` (optional): If set, the sensor will ignore SSL certificate mismatches during artifact upload

**Response Event:** LOG_GET_REP

**Usage Examples:**

```bash
limacharlie task send --sid <SID> --task 'artifact_get --file "C:\\Windows\\System32\\drivers\\etc\\hosts"'
```

Collect every `.conf` file under `/etc`, at most 10 files and 8 MB in total:

```bash
limacharlie task send --sid <SID> --task 'artifact_get --root-dir /etc -x "*.conf" --max-files 10 --max-total-bytes 8388608'
```

**Sample Response (multi-file):**

```json
{
  "event": {
    "FILES": [
      {
        "FILE_PATH": "/etc/ssh/sshd_config",
        "PAYLOAD_ID": "4e6f2f1a-2c3d-4b5e-8a90-1f2e3d4c5b6a",
        "ERROR": 200
      }
    ],
    "SCAN_ENTRIES_SCANNED": 812,
    "SCAN_FILES_SCANNED": 137,
    "SCAN_BYTES_PROCESSED": 48213,
    "SCAN_IS_TRUNCATED": 0,
    "SCAN_STOPPED_REASON": "complete"
  }
}
```

Each entry reports the per-file upload status in `ERROR` (200 on success), with
`ERROR_MESSAGE` present when an individual file fails. A partial run still
returns the files it did upload.

---

### container_list

Inventory the containers running on a Linux host, and optionally the local
container images, across the Docker, containerd, Podman and CRI-O runtimes.

Containers are discovered from cgroups, so they are reported even when no
container daemon is reachable. When a Docker or Podman daemon is available the
records are enriched with the image reference, digest, state and creation time;
records that could not be enriched are marked `CONTAINER_IS_PARTIAL`.

**Platforms:** Linux

**Parameters:**

- `--runtime` (optional): Runtime to query: `docker`, `containerd`, `podman`, `crio`, or `all` (default: `all`)
- `--include-images` (optional): Also list local Docker/Podman images
- `--include-stopped` (optional): Also list stopped Docker/Podman containers
- `--limit` (optional): Maximum total records (default: 500, max: 5000)

**Response Event:** CONTAINER_LIST_REP

**Usage Example:**

```bash
limacharlie task send --sid <SID> --task 'container_list --runtime docker --include-images'
```

**Sample Response:**

```json
{
  "event": {
    "CONTAINERS": [
      {
        "CONTAINER_ID": "b66423fa5cb15cb7dad7ee901e91d4e022916fdc977ba43c30b8ca2f953e8d79",
        "CONTAINER_RUNTIME": "docker",
        "NAME": "web-frontend",
        "CONTAINER_IMAGE_REF": "nginx:1.27",
        "CONTAINER_IMAGE_DIGEST": "9c2b0f6cd1a54e5f3f8c2b1d7e4a09b3c65d8e2f1a4b7c093d6e5f8a2b1c4d7e0",
        "STATE": "running",
        "PROCESS_ID": 4812
      }
    ],
    "SCAN_ENTRIES_SCANNED": 217,
    "CONTAINER_DAEMON_ERRORS": 0,
    "CONTAINER_IS_PARTIAL": 0,
    "SCAN_IS_TRUNCATED": 0
  }
}
```

---

### dir_list

List files and directories at a specified path on the endpoint.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `rootdir` (positional): Root directory where to begin the listing from
- `fileexp` (positional): File name expression supporting basic wildcards like `*` and `?` (e.g., "*.exe")
- `-d, --depth` (optional): Maximum depth of the listing, defaults to a single level

**Response Event:** DIR_LIST_REP

**Usage Example:**

```bash
limacharlie task send --sid <SID> --task 'dir_list "C:\\Windows\\System32" "*.exe" --depth 1'
```

**Sample Response:**

```json
{
  "event": {
    "DIRECTORY_LIST": [
      {
        "FILE_PATH": "C:\\Windows\\System32\\cmd.exe",
        "FILE_SIZE": 289792,
        "LAST_MODIFIED": 1579000000
      }
    ]
  }
}
```

---

### dir_find

Search a directory tree for files matching metadata criteria, and optionally
return their hashes. This is the general form of
[dir\_findhash](#dir_findhash): it can filter on size, modification time and
hash at once, and it is bounded by explicit time, entry and byte budgets so a
search cannot run away on a large filesystem.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `rootDir` (positional, required): Root directory to search
- `-x, --file-exp` (optional): Glob to include, repeatable; defaults to all files
- `-X, --exclude-exp` (optional): Glob to exclude, repeatable; matching directories are pruned
- `-d, --depth` (optional): Maximum directory depth (default: 1, max: 32)
- `--min-size` (optional): Minimum file size in bytes
- `--max-size` (optional): Maximum file size in bytes
- `--newer-than` (optional): Only files modified after this Unix epoch second
- `--older-than` (optional): Only files modified before this Unix epoch second
- `--hash` (optional): MD5, SHA-1 or SHA-256 digest to match, repeatable
- `--with-hashes` (optional): Return MD5, SHA-1 and SHA-256 for every hit
- `--limit` (optional): Maximum results (default: 1000, max: 10000)
- `--max-files-scanned` (optional): Maximum filesystem entries to examine (default: 250000, max: 5000000)
- `--max-seconds` (optional): Wall-clock budget in seconds (default: 120, max: 900)
- `--max-bytes` (optional): Maximum bytes read for hashing (default: 1073741824)
- `--one-file-system` (optional): Do not cross filesystem boundaries
- `--include-dirs` (optional): Also return matching directories

**Response Event:** DIR_FIND_REP

**Usage Example:**

```bash
limacharlie task send --sid <SID> --task 'dir_find "C:\\Users" -x "*.exe" -X "AppData" --depth 4 --newer-than 1756684800 --with-hashes'
```

**Sample Response:**

```json
{
  "event": {
    "FILES": [
      {
        "FILE_PATH": "C:\\Users\\jdoe\\Downloads\\setup.exe",
        "FILE_SIZE": 481232,
        "MODIFICATION_TIME": 1756771200000,
        "HASH_MD5": "77a097c81e679798f68f968be1498620",
        "HASH_SHA1": "55c92f35ad24bc59ca2ea74028203ae3a3a7d493",
        "HASH": "aeb6310a1ac57c1beb98d74361c58b056522780c1b4d60e7a6c605ecaed47e01"
      }
    ],
    "SCAN_ENTRIES_SCANNED": 18422,
    "SCAN_FILES_SCANNED": 15310,
    "SCAN_BYTES_PROCESSED": 4812331,
    "SCAN_IS_TRUNCATED": 0,
    "SCAN_STOPPED_REASON": "complete"
  }
}
```

---

### dir_findhash

Search for files matching a specific hash across a directory tree.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `dir_path` (required): Root directory to search
- `hash` (required): Hash value to search for (MD5, SHA1, or SHA256)
- `depth` (optional): Maximum recursion depth

**Response Event:** DIR_FINDHASH_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> dir_findhash --dir_path "/var" --hash <HASH_VALUE>
```

---

### dns_resolve

Perform DNS resolution on the endpoint to determine what DNS server responds.

**Platforms:** macOS | Windows | Linux | Chrome | Edge

**Parameters:**

- `hostname` (required): Hostname to resolve

**Response Event:** DNS_REQUEST

**Usage Example:**

```bash
limacharlie sensor task <SID> dns_resolve --hostname "example.com"
```

---

### doc_cache_get

Retrieve a previously cached document from the sensor's local cache.

**Platforms:** macOS | Windows

**Parameters:**

- `hash` (required): Hash of the cached document

**Response Event:** GET_DOCUMENT_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> doc_cache_get --hash <DOC_HASH>
```

---

### exfil_add

Add an exfiltration detection watch for specific event types and patterns.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `event` (required): Event type to monitor (e.g., "DNS_REQUEST", "NEW_PROCESS")
- `operator` (required): Comparison operator ("is", "contains", "matches", etc.)
- `path` (required): JSON path to the field to watch (e.g., "event/DOMAIN_NAME")
- `value` (required): Value or pattern to match
- `expire` (optional): TTL in seconds for the watch (default: permanent)

**Response Event:** EXFIL_ADD_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> exfil_add --event "DNS_REQUEST" --operator "contains" --path "event/DOMAIN_NAME" --value "malware" --expire 3600
```

---

### exfil_del

Remove an exfiltration detection watch by its ID.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `id` (required): Watch ID to remove (from exfil_get response)

**Response Event:** EXFIL_DEL_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> exfil_del --id <WATCH_ID>
```

---

### exfil_get

List all active exfiltration detection watches on the sensor.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** EXFIL_GET_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> exfil_get
```

---

### file_del

Delete a file from the endpoint filesystem.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `file_path` (required): Path to the file to delete

**Response Event:** FILE_DEL_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> file_del --file_path "/tmp/suspicious_file"
```

---

### file_get

Retrieve a file from the endpoint and upload it to LimaCharlie cloud storage.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `file_path` (required): Path to the file to retrieve

**Response Event:** FILE_GET_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> file_get --file_path "C:\\Windows\\System32\\calc.exe"
```

---

### file_grep

Search the contents of files under a directory tree for one or more literal
byte patterns. Patterns are literal, not regular expressions.

Use `--no-content` to return only the path, pattern index, offset and length of
each match and never any file bytes. This lets an operator confirm that a
secret or indicator is present on a host without exfiltrating the surrounding
data.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `rootDir` (positional, required): Root directory to search
- `-p, --pattern` (required): Literal byte pattern to find, repeatable
- `-x, --file-exp` (optional): Glob to include, repeatable; defaults to all files
- `-X, --exclude-exp` (optional): Glob to exclude, repeatable; matching directories are pruned
- `-d, --depth` (optional): Maximum directory depth (default: 1, max: 32)
- `-i, --ignore-case` (optional): Use ASCII case-insensitive matching
- `--context-bytes` (optional): Surrounding bytes to return for each match (max: 4096)
- `--no-content` (optional): Return only path and offsets, never file bytes
- `--max-file-size` (optional): Maximum file size to read in bytes (default: 16777216, max: 67108864)
- `--max-matches-per-file` (optional): Maximum matches returned per file (default: 10, max: 1000)
- `--limit` (optional): Maximum total matches (default: 500, max: 10000)
- `--max-files-scanned` (optional): Maximum filesystem entries to examine (default: 250000, max: 5000000)
- `--max-seconds` (optional): Wall-clock budget in seconds (default: 120, max: 900)
- `--max-bytes` (optional): Maximum bytes read (default: 1073741824)
- `--binary` (optional): Also scan files that contain NUL bytes
- `--one-file-system` (optional): Do not cross filesystem boundaries

**Response Event:** FILE_GREP_REP

**Usage Example:**

```bash
limacharlie task send --sid <SID> --task 'file_grep /home -x "*.env" -p "AWS_SECRET_ACCESS_KEY" --depth 5 --no-content'
```

**Sample Response:**

```json
{
  "event": {
    "FILE_MATCHES": [
      {
        "FILE_PATH": "/home/jdoe/app/.env",
        "MATCH_PATTERN_INDEX": 0,
        "MATCH_OFFSET": 412,
        "MATCH_LENGTH": 21,
        "FILE_CONTENT": "REJfSE9TVD0xMC4wLjAuNQpleHBvcnQgQVdTX1NFQ1JFVF9BQ0NFU1NfS0VZPXdKYWxyWFV0bkZFTUkvSzdNREVORwoj"
      }
    ],
    "SCAN_ENTRIES_SCANNED": 9014,
    "SCAN_FILES_SCANNED": 7781,
    "SCAN_BYTES_PROCESSED": 33814402,
    "SCAN_IS_TRUNCATED": 0,
    "SCAN_STOPPED_REASON": "complete"
  }
}
```

`MATCH_PATTERN_INDEX` is the zero-based index of the `--pattern` that matched.
`FILE_CONTENT` carries the matched bytes plus any requested context, and is
absent when `--no-content` is used.

---

### file_hash

Calculate cryptographic hashes (MD5, SHA1, SHA256) for a file.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `file_path` (required): Path to the file to hash

**Response Event:** FILE_HASH_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> file_hash --file_path "/etc/passwd"
```

**Sample Response:**

```json
{
  "event": {
    "FILE_PATH": "/etc/passwd",
    "HASH": "abc123...",
    "MD5": "def456...",
    "SHA1": "ghi789...",
    "SHA256": "jkl012..."
  }
}
```

---

### file_info

Get detailed metadata about a file without retrieving its contents.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `file_path` (required): Path to the file

**Response Event:** FILE_INFO_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> file_info --file_path "C:\\Program Files\\app.exe"
```

**Sample Response:**

```json
{
  "event": {
    "FILE_PATH": "C:\\Program Files\\app.exe",
    "FILE_SIZE": 1048576,
    "CREATED": 1579000000,
    "MODIFIED": 1580000000,
    "ACCESSED": 1581000000
  }
}
```

---

### file_mov

Move or rename a file on the endpoint filesystem.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `src_path` (required): Source file path
- `dst_path` (required): Destination file path

**Response Event:** FILE_MOV_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> file_mov --src_path "/tmp/file.txt" --dst_path "/tmp/renamed.txt"
```

---

### fim_add

Add a File Integrity Monitoring (FIM) watch for a specific path or pattern.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `file_path` (required): Path or pattern to monitor (supports wildcards)

**Response Event:** FIM_ADD_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> fim_add --file_path "C:\\Windows\\System32\\*.dll"
```

---

### fim_del

Remove a File Integrity Monitoring watch.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `file_path` (required): Path pattern to stop monitoring

**Response Event:** FIM_REMOVE (note: event name is FIM_REMOVE, not FIM_DEL_REP)

**Usage Example:**

```bash
limacharlie sensor task <SID> fim_del --file_path "C:\\Windows\\System32\\*.dll"
```

---

### fim_get

List all active File Integrity Monitoring watches on the sensor.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** FIM_LIST_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> fim_get
```

---

### get_debug_data

Retrieve internal sensor debug data for troubleshooting.

**Platforms:** Windows

**Parameters:** None

**Response Event:** DEBUG_DATA_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> get_debug_data
```

Sensors running version 5.3.6 or later include a `LOSS_ACCOUNTING` sequence in the reply, reporting how many events the sensor's outbound queue has evicted or refused (in events and in bytes), how deep the queue currently is, and the bounds it is enforcing. See [the LOSS_ACCOUNTING field reference](edr-events.md#loss_accounting) for a description of each value.

---

### hidden_module_scan

Scan for hidden or stealthy modules loaded in process memory that may not appear in normal module lists.

**Platforms:** Windows

**Parameters:**

- `pid` (optional): Specific process ID to scan (default: all processes)

**Response Event:** HIDDEN_MODULE_DETECTED

**Usage Example:**

```bash
limacharlie sensor task <SID> hidden_module_scan --pid 1234
```

---

### history_dump

Export a dump of recent events from the sensor's local event cache.

**Platforms:** macOS | Windows | Linux | Chrome | Edge

**Parameters:** None

**Response Event:** HISTORY_DUMP_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> history_dump
```

---

### log_get

Retrieve Windows Event Logs or macOS Unified Logs from the endpoint.

**Platforms:** Windows (Event Logs) | macOS (Unified Logs)

**Parameters:**

- `source` (Windows required): Event log source name (e.g., "Security", "System")
- `predicate` (macOS optional): Unified log filter predicate

**Response Event:** LOG_GET_REP

**Usage Example:**

```bash
# Windows
limacharlie sensor task <SID> log_get --source "Security"

# macOS
limacharlie sensor task <SID> log_get --predicate "eventType == logEvent"
```

---

### mem_find_string

Search process memory for specific string patterns.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `pid` (required): Process ID to scan
- `strings` (required): String or list of strings to search for

**Response Event:** MEM_FIND_STRING_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> mem_find_string --pid 1234 --strings "password"
```

---

### mem_find_handle

Find handles (file, registry, process) held by a process on Windows.

**Platforms:** Windows

**Parameters:**

- `pid` (optional): Specific process ID (default: all processes)
- `needle` (optional): Handle name pattern to search for

**Response Event:** MEM_FIND_HANDLE_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> mem_find_handle --pid 1234 --needle "malware.exe"
```

---

### mem_map

Get memory map of a process showing loaded modules and memory regions.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `pid` (required): Process ID to map

**Response Event:** MEM_MAP_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> mem_map --pid 1234
```

---

### mem_read

Read raw memory from a process at a specific address.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `pid` (required): Process ID
- `base_address` (required): Memory address to read from (hex format)
- `size` (required): Number of bytes to read

**Response Event:** MEM_READ_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> mem_read --pid 1234 --base_address 0x00400000 --size 1024
```

---

### mem_strings

Extract all readable strings from a process's memory.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `pid` (required): Process ID to scan

**Response Event:** MEM_STRINGS_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> mem_strings --pid 1234
```

---

### netstat

Get current network connections on the endpoint (similar to netstat command).

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** NETWORK_CONNECTIONS

**Usage Example:**

```bash
limacharlie sensor task <SID> netstat
```

**Sample Response:**

```json
{
  "event": {
    "NETWORK_ACTIVITY": [
      {
        "STATE": "ESTABLISHED",
        "LOCAL_ADDRESS": "192.168.1.100",
        "LOCAL_PORT": 50234,
        "REMOTE_ADDRESS": "93.184.216.34",
        "REMOTE_PORT": 443,
        "PID": 1234,
        "PROCESS": "chrome.exe"
      }
    ]
  }
}
```

---

### network_summary

Get aggregated network statistics and active connections summary.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** NETWORK_SUMMARY

**Usage Example:**

```bash
limacharlie sensor task <SID> network_summary
```

---

### os_kill_process

Terminate a running process.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `pid` (required): Process ID to terminate

**Response Event:** OS_KILL_PROCESS_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_kill_process --pid 1234
```

---

### os_packages

List installed software packages on the endpoint.

**Platforms:** Windows (via registry) | macOS (future) | Linux (future)

**Response Event:** OS_PACKAGES_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_packages
```

**Sample Response:**

```json
{
  "event": {
    "PACKAGES": [
      {
        "NAME": "Google Chrome",
        "VERSION": "120.0.6099.130",
        "PUBLISHER": "Google LLC"
      }
    ]
  }
}
```

---

### os_processes

Get a list of all running processes with detailed information.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** EXISTING_PROCESS (multiple events, one per process)

**Usage Example:**

```bash
limacharlie sensor task <SID> os_processes
```

**Sample Response:**

```json
{
  "event": {
    "PROCESS_ID": 1234,
    "PARENT_PROCESS_ID": 5678,
    "COMMAND_LINE": "C:\\Windows\\System32\\notepad.exe",
    "FILE_PATH": "C:\\Windows\\System32\\notepad.exe",
    "USER_NAME": "DOMAIN\\user"
  }
}
```

---

### os_resume

Resume a suspended process.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `pid` (required): Process ID to resume

**Response Event:** OS_RESUME_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_resume --pid 1234
```

---

### os_services

List all services/daemons running on the endpoint.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** OS_SERVICES_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_services
```

---

### os_suspend

Suspend (pause) a running process.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `pid` (required): Process ID to suspend

**Response Event:** OS_SUSPEND_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_suspend --pid 1234
```

---

### os_autoruns

List programs configured to run automatically at system startup.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** OS_AUTORUNS_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_autoruns
```

---

### os_drivers

List all loaded kernel drivers/modules.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** OS_DRIVERS_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_drivers
```

---

### os_version

Get detailed operating system version information.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** OS_VERSION_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> os_version
```

**Sample Response:**

```json
{
  "event": {
    "OS_NAME": "Windows 11",
    "OS_VERSION": "10.0.22631",
    "ARCHITECTURE": "x64"
  }
}
```

---

### rejoin_network

Re-enable network connectivity for a sensor that was previously isolated.

**Platforms:** macOS | Windows | Linux | Chrome | Edge

**Parameters:** None

**Response Event:** None (sensor reconnects)

**Usage Example:**

```bash
limacharlie sensor task <SID> rejoin_network
```

---

### repo_list

Report the git working copies present on a host, and what each one is: its
checked-out revision, its remotes and, optionally, its declared submodules. Use
it to find source checkouts on machines that are not meant to hold code, or to
inventory which repositories an engineering fleet has cloned.

The search is bounded by explicit depth, repository, entry and time budgets so
it cannot run away on a large filesystem.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `-r, --root` (optional): Root directory to search from, repeatable. When
  omitted the agent uses its own per-platform roots, described below, and never
  scans the whole volume. An explicitly empty root is rejected rather than
  ignored.
- `-d, --depth` (optional): Maximum directory depth below each root (default: 6, max: 32)
- `--with-submodules` (optional): Also report the submodules declared in each repository's `.gitmodules`
- `--max-repos` (optional): Maximum repositories to report before stopping (default: 200, max: 5000)
- `--max-entries` (optional): Maximum filesystem entries to examine before stopping (default: 500000)
- `--max-seconds` (optional): Wall-clock budget in seconds (default: 120, max: 900)

Out-of-range budgets are rejected when the command is issued rather than being
silently clamped, so a value the agent would not honour fails at the prompt.

With no `--root`, the default roots are:

| Platform | Default roots |
| --- | --- |
| Windows | `C:\Users` |
| macOS | `/Users`, `/opt`, `/srv` |
| Linux | `/home`, `/root`, `/opt`, `/srv` |

**Response Event:** REPO_LIST_REP

**Usage Example:**

```bash
limacharlie task send --sid <SID> --task 'repo_list --with-submodules --depth 4'
```

Restricting the search to specific roots:

```bash
limacharlie task send --sid <SID> --task 'repo_list -r "C:\\Users\\jdoe\\src" -r "D:\\code" --max-repos 50'
```

**Sample Response:**

```json
{
  "event": {
    "REPOSITORY_LIST": [
      {
        "DIRECTORY_PATH": "C:\\Users\\jdoe\\src\\lc-test-repo",
        "REPOSITORY_GIT_DIR": "C:\\Users\\jdoe\\src\\lc-test-repo\\.git",
        "REPOSITORY_HEAD_COMMIT": "0123456789abcdef0123456789abcdef01234567",
        "REPOSITORY_HEAD_REF": "refs/heads/main",
        "MODIFICATION_TIME": 1756771200000,
        "REPOSITORY_REMOTES": [
          {
            "NAME": "origin",
            "URL": "https://github.com/example/lc-test-repo.git"
          }
        ]
      }
    ],
    "DIRECTORY_LIST_DEPTH": 6,
    "SCAN_ENTRIES_SCANNED": 1195,
    "SCAN_MAX_ENTRIES": 500000,
    "SCAN_MAX_RESULTS": 200,
    "SCAN_MAX_SECONDS": 120,
    "SCAN_IS_TRUNCATED": 0,
    "SCAN_STOPPED_REASON": "complete"
  }
}
```

---

### run

Execute a command or script on the endpoint (out-of-band execution).

**Platforms:** macOS | Linux

**Parameters:**

- `command` (required): Command line to execute

**Response Event:** EXEC_OOB

**Usage Example:**

```bash
limacharlie sensor task <SID> run --command "ps aux | grep chrome"
```

---

### segregate_network

Isolate a sensor from the network (except LimaCharlie cloud connectivity).

**Platforms:** macOS | Windows | Linux | Chrome | Edge

**Parameters:** None

**Response Event:** None (sensor becomes isolated)

**Usage Example:**

```bash
limacharlie sensor task <SID> segregate_network
```

---

### uninstall

Uninstall the sensor from the endpoint.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `--is-confirmed` (required): Must be specified as a confirmation that you want to uninstall the sensor
- `--msi` (optional): Windows only — must be specified if the sensor was installed via MSI
- `--native` (optional): Use the sensor's built-in (native) uninstall procedure instead of the default legacy shell-based procedure

By default, the sensor uninstalls itself by running a shell command that invokes the on-disk agent's own uninstaller. This legacy procedure works on every sensor version. With `--native`, the sensor performs the uninstallation itself without spawning a shell command.

> **Note:** `--native` requires sensor version 5.3.3 or later. Older sensors silently ignore the native uninstall request — nothing happens on the endpoint. If you are unsure of a sensor's version, omit `--native`.

`--msi` takes precedence over `--native`: the native procedure does not unregister the MSI product, so sensors installed via MSI should use `--msi`.

**Response Event:** None (sensor uninstalls and disconnects)

**Usage Example:**

```bash
limacharlie sensor task <SID> uninstall --is-confirmed
limacharlie sensor task <SID> uninstall --is-confirmed --native
```

---

### usb_list_devices

List every USB device currently attached to the host, whatever its class. This
is the general form of `usb_list_keys`, which reports only mass-storage keys.
The command takes no arguments.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** USB_DEVICE_LIST_REP

**Usage Example:**

```bash
limacharlie task send --sid <SID> --task 'usb_list_devices'
```

**Sample Response:**

```json
{
  "event": {
    "USB_DEVICES": [
      {
        "USB_VENDOR_ID": 2385,
        "USB_PRODUCT_ID": 5734,
        "USB_DEVICE_CLASS": 0,
        "USB_USB_VERSION": 300,
        "USB_MANUFACTURER_STRING": "Kingston",
        "USB_SERIAL_NUMBER": "BAD0USB",
        "USB_INTERFACES": [
          {
            "USB_INTERFACE_CLASS": 8,
            "USB_INTERFACE_SUBCLASS": 6,
            "USB_INTERFACE_PROTOCOL": 80
          }
        ]
      }
    ],
    "ERROR": 0
  }
}
```

A host with no USB devices attached returns an empty list, not an error:

```json
{
  "event": {
    "USB_DEVICES": [],
    "ERROR": 0
  }
}
```

---

### upgrade_core

Task the sensor to upgrade its own on-disk agent (the installed service) to a new release. The sensor downloads, verifies, and installs the release itself; if the new version fails to start, it automatically rolls back to the previous one. See [Service Upgrades](../2-sensors-deployment/endpoint-agent/service-upgrades.md) for the full upgrade procedure.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `--beta` (required): Opt in to the native upgrade procedure; the command is rejected without it while the feature is in beta
- `--force` (optional): Upgrade even if the sensor already reports the latest available release
- `--version` (optional): Pin the exact release to install (e.g. `5.3.3`), downgrades included; defaults to the latest available release

> **Note:** Requires sensor version 5.3.3 or later. Sensors running an older version silently drop the request and no upgrade takes place.

**Response Event:** None

**Usage Example:**

```bash
limacharlie sensor task <SID> upgrade_core --beta
limacharlie sensor task <SID> upgrade_core --beta --version 5.3.3
```

---

### yara_scan

Scan files or process memory with YARA rules.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `rule` (required): YARA rule content
- `file_path` (optional): Specific file to scan
- `pid` (optional): Specific process to scan
- `process_expr` (optional): Process name pattern to scan

**Response Event:** YARA_DETECTION

**Usage Example:**

```bash
# Scan a file
limacharlie sensor task <SID> yara_scan --file_path "C:\\suspicious.exe" --rule "rule test { strings: $a = \"malware\" condition: $a }"

# Scan process memory
limacharlie sensor task <SID> yara_scan --pid 1234 --rule "rule test { strings: $a = \"malware\" condition: $a }"
```

---

### pcap_ifaces

List available network interfaces for packet capture.

**Platforms:** macOS | Windows | Linux

**Parameters:** None

**Response Event:** PCAP_INTERFACES_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> pcap_ifaces
```

---

### pcap_start

Start capturing network packets on a specified interface.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `iface` (required): Network interface ID or name
- `max_size` (optional): Maximum capture size in MB

**Response Event:** PCAP_START_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> pcap_start --iface eth0 --max_size 100
```

---

### pcap_stop

Stop an active packet capture and upload the PCAP file.

**Platforms:** macOS | Windows | Linux

**Parameters:**

- `iface` (optional): Specific interface to stop (default: all)

**Response Event:** PCAP_STOP_REP, followed by EXPORT_COMPLETE

**Usage Example:**

```bash
limacharlie sensor task <SID> pcap_stop
```

---

### reg_list

List Windows registry keys and values.

**Platforms:** Windows

**Parameters:**

- `reg` (required, positional): Registry path to list. Must start with one of `hkcr`, `hkcc`, `hkcu`, `hklm`, `hku` (e.g., `hklm\software`). Backslashes must be escaped.

**Response Event:** REGISTRY_LIST_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> reg_list "hklm\\software\\microsoft\\windows\\currentversion\\run"
```

---

### reg_get

Fetch a single named value from a Windows registry key. Complements `reg_list`, which enumerates a whole key.

> **Note:** Added in sensor version 5.3.0.

**Platforms:** Windows

**Parameters:**

- `reg` (required, positional): Registry key to read from. Must start with one of `hkcr`, `hkcc`, `hkcu`, `hklm`, `hku` (e.g., `hklm\software`). Backslashes must be escaped.
- `name` (optional, positional): Name of the value to fetch; omit for the key's default (unnamed) value

**Response Event:** REGISTRY_GET_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> reg_get "hklm\\software\\microsoft\\windows\\currentversion\\run" "OneDrive"
```

---

### epp_scan

Trigger an Endpoint Protection (EPP) scan on a file or directory.

**Platforms:** Windows

**Parameters:**

- `file_path` (required): Path to scan

**Response Event:** EPP_SCAN_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> epp_scan --file_path "C:\\Users\\Public"
```

---

### epp_list_exclusions

List EPP scan exclusions currently configured on the sensor.

**Platforms:** Windows

**Parameters:** None

**Response Event:** EPP_LIST_EXCLUSIONS_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> epp_list_exclusions
```

---

### epp_add_exclusion

Add a path, process or file extension to EPP scan exclusions.

**Platforms:** Windows

**Parameters:**

- `value` (positional, required): Value of the exclusion to add (a file/directory path, a process name, or a file extension)
- `--type` / `-t` (required): Type of exclusion. Options are: `extension`, `path`, `process`

**Response Event:** EPP_ADD_EXCLUSION_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> epp_add_exclusion "C:\\safe_app" --type path
limacharlie sensor task <SID> epp_add_exclusion "safe_app.exe" --type process
```

---

### epp_rem_exclusion

Remove a path, process or file extension from EPP scan exclusions.

**Platforms:** Windows

**Parameters:**

- `value` (positional, required): Value of the exclusion to remove (a file/directory path, a process name, or a file extension)
- `--type` / `-t` (required): Type of exclusion. Options are: `extension`, `path`, `process`

**Response Event:** EPP_REM_EXCLUSION_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> epp_rem_exclusion "C:\\safe_app" --type path
```

---

### epp_list_quarantine

List files currently in EPP quarantine.

**Platforms:** Windows

**Parameters:** None

**Response Event:** EPP_LIST_QUARANTINE_REP

**Usage Example:**

```bash
limacharlie sensor task <SID> epp_list_quarantine
```

---

## Command Usage Notes

**General Syntax:**

```bash
limacharlie sensor task <SENSOR_ID> <COMMAND_NAME> [--param value ...]
```

**Platform Abbreviations:**

- macOS: Apple macOS and OS X
- Windows: Microsoft Windows (7, 8, 10, 11, Server editions)
- Linux: Linux distributions (Ubuntu, CentOS, Debian, etc.)
- Chrome: Chrome browser extension sensor
- Edge: Microsoft Edge browser extension sensor

**Response Events:**
Most commands generate a response event (typically ending in `_REP`) that can be:

- Viewed in the LimaCharlie web interface under Sensor > Timeline
- Retrieved via API
- Triggered on with D&R rules

**Error Handling:**
Response events typically include an `ERROR` field:

- `ERROR: 0` indicates success
- Non-zero ERROR values indicate specific error conditions

**Permissions:**
Some commands require elevated privileges (root/administrator) on the endpoint to execute successfully.

**Timeouts:**
Commands have default timeouts (typically 30-60 seconds). Long-running operations may timeout and can be made persistent using the Reliable Tasking extension.
