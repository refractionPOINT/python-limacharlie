# BinLib

Binary Library, or "BinLib", is a collection of executable binaries (such as EXE or ELF files) that have been observed within your environment. If enabled, this Extension helps you build your own private collection of observed executables for subsequent analysis and searching.

When LimaCharlie observes a binary and path for the first time a `CODE_IDENTITY` event is generated. The metadata from this event is stored within `binlib`, and is available for searching, tagging, and downloading. Additionally, you can run [YARA](../third-party/yara.md) scans against observed binaries.

## Enabling BinLib

BinLib requires subscribing to the `ext-reliable-tasking` Extension in order to function properly. This can be enabled [in the Add-ons marketplace](https://app.limacharlie.io/add-ons/extension-detail/ext-reliable-tasking).

BinLib can be a powerful additional to your detection and response capabilities. Analysts can:

- Look for historical evidence of malicious binaries
- Tag previously-observed files for data enrichment (i.e. [MITRE ATT&CK Techniques](https://attack.mitre.org/matrices/enterprise/))
- Compare observed hashes to known good or known bad lists
- [YARA scan](../third-party/yara.md) and auto-tag for integration in detection & response rules

## Usage

First, subscribe your tenant to the [BinLib](https://app.limacharlie.io/add-ons/extension-detail/binlib) extension.

![binlib 1](../../../assets/images/binlib-1.png)

To perform one of the following operations against your own library, choose the command and select **Run Request.**

The BinLib page in the web app offers an easy way to get started with some of the core requests exposed by the extension: Check Hash, Search, and Yara Scan.

![binlib 2](../../../assets/images/binlib-2.png)

### check_hash

#### Accepted Values: MD5, SHA1, SHA256

The `check_hash` operation lets you search to see if a particular hash has been observed in your Organization. Output includes a boolean if the hash was found and three hash values, if available.

Sample Output:

```json
{
  "data": {
    "found": true,
    "md5": "e977bded5d4198d4895ac75150271158",
    "sha1": "9e2b05f142c35448c9bc48c40a732d632485c719",
    "sha256": "2f5d0c6159b194d6f0f2eae0b7734708368a23aebf9af4db9293865b57ffcaeb"
  }
}
```

### get_hash_data

#### Accepted Values: MD5, SHA1, SHA256

#### Careful Downloading Binaries

LimaCharlie does not filter the binaries observed by your organization. You must exercise caution if downloading a malicious file. We recommend downloading potential malicious binaries to an isolated analysis system.

The `get_hash_data` operation provides a link to the raw data for the hash of interest, allowing you to download the resulting binary file (if previously observed within your environment).

Sample Output:

```json
{
  "data": {
    "download_url": "https://storage.googleapis.com/lc-library-bin/b_2f5d0c...",
    "found": true,
    "md5": "e977bded5d4198d4895ac75150271158",
    "sha1": "9e2b05f142c35448c9bc48c40a732d632485c719",
    "sha256": "2f5d0c6159b194d6f0f2eae0b7734708368a23aebf9af4db9293865b57ffcaeb"
  }
}
```

### get_hash_metadata

#### Accepted Values: MD5, SHA1, SHA256

The `get_hash_metadata` operation obtains the metadata for a hash of interest, including signing details, file type, and additional hashes.

```json
{
  "data": {
    "found": true,
    "md5": "e977bded5d4198d4895ac75150271158",
    "metadata": {
      "imp_hash": "c105252faa9163fd63fb81bb334c61bf",
      "res_company_name": "Google LLC",
      "res_file_description": "Google Chrome Installer",
      "res_product_name": "Google Chrome Installer",
      "res_product_version": "113.0.5672.127",
      "sha256": "2f5d0c6159b194d6f0f2eae0b7734708368a23aebf9af4db9293865b57ffcaeb",
      "sig_authentihash": "028f24e2c1fd42a3edaf0dcf8a59afe39201fa7d3bb5804dca8559fde41b3f34",
      "sig_issuer": "US, DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1",
      "sig_serial": "0e4418e2dede36dd2974c3443afb5ce5",
      "sig_subject": "US, California, Mountain View, Google LLC, Google LLC",
      "size": 5155608,
      "type": "pe"
    },
    "sha1": "9e2b05f142c35448c9bc48c40a732d632485c719",
    "sha256": "2f5d0c6159b194d6f0f2eae0b7734708368a23aebf9af4db9293865b57ffcaeb"
  }
}
```

### search

The `search` operation searches the library for binary data points, including or *other than* a known hash.

Searchable fields include:

- imp_hash
- res_company_name
- res_file_description
- res_product_name
- sha256
- sig_authentihash
- sig_hash
- sig_issuer
- sig_subject
- size
- type

Note that search criteria are ANDed. Binaries must meet ALL criteria to be returned.

Search results can be downloaded as a CSV.

![binlib 3](../../../assets/images/binlib-3.png)

### tag

The `tag` operation allows you to add tag(s) to a hash, allowing for additional classification within binlib.

The below example Tags the Google Installer with the `google` tag.

![binlib 4](../../../assets/images/binlib-4.png)

Successful tagging yields an `updated` event:

```json
{
  "data": {
    "found": true,
    "md5": "e977bded5d4198d4895ac75150271158",
    "sha1": "9e2b05f142c35448c9bc48c40a732d632485c719",
    "sha256": "2f5d0c6159b194d6f0f2eae0b7734708368a23aebf9af4db9293865b57ffcaeb",
    "updated": true
  }
}
```

### untag

The `untag` operation removes a tag from a binary.

### YARA scan

The `yara_scan` operation lets you run YARA scans across observed files. Scans require:

- Criteria or hash to filter files to be scanned
- [Rule name(s)](../../../7-administration/config-hive/yara.md) or rule(s)

You also have the option to tag hits on match.

Note that search criteria are ANDed. Binaries must meet ALL criteria to be returned.

![binlib 5](../../../assets/images/binlib-5.png)

## Automating

Here are some examples of useful rules that could be used to automate interactions with Binlib.

### Scan all acquired files with Yara

This rule will automatically scan all acquired files in binlib with a Yara rule:

```yaml
detect:

event: acquired
op: is tagged
tag: ext:binlib

respond:

- action: report
  name: binlib-test
- action: extension request
  extension action: yara_scan
  extension name: binlib
  extension request:
    hash: '{{ .event.sha256 }}'
    rule_names:
      - yara_rule_name_here
```

and this rule will alert on matches:

```yaml
detect:

event: yara_scan
op: exists
path: event/matches/hash

respond:

- action: report
  name: YARA Match via Binlib
```
