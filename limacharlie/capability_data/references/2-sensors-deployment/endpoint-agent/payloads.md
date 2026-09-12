# Payloads

## Overview

Payloads are executables or scripts that can be delivered and executed through LimaCharlie's Endpoint Agent.

Those payloads can be any executable or script natively understood by the endpoint. The main use case is to run something with specific functionality not available in the main LimaCharlie functionality. For example: custom executables provided by another vendor to cleanup a machine, forensic utilities or firmware-related utilities.

We encourage you to look at LimaCharlie native functionality first as it has several advantages:

- Usually has better performance.
- Data returned is always well structured JSON.
- Can be tasked automatically and [Detection & Response Rules](../../3-detection-response/index.md) can be created from their data.
- Data returned is indexed and searchable.

It is possible to set the Payload's file extension on the endpoint by making the Payload name end with that extension. For example, naming a Payload `extract_everything.bat`, the Payload will be sent as a batch file (`.bat`) and executed as such.  This is also true for PowerShell files (`.ps1`).

## Lifecycle

Payloads are uploaded to the LimaCharlie platform and given a name. The task `run` can then be used with the `--payload-name MY-PAYLOAD --arguments "-v EulaAccepted"` can be used to run the payload with optional arguments.

The STDOUT and STDERR data will be returned in a related `RECEIPT` event, up to 1 MB. If your payload generates more data, we recommend to pipe the data to a file on disk and use the `log_get` command to retrieve it.

!!! warning "The 1 MB limit is measured in bytes, and exceeding it returns no output at all"
    Two things about this limit surprise people:

    - **It is 1 MB of raw output bytes, not characters.** Output encoded as UTF-16 costs two bytes per character, so it reaches the limit at roughly 524,000 characters instead of 1,048,000. Windows tooling frequently produces UTF-16 — `Out-File`, `>` redirection and `Export-Csv` in Windows PowerShell all default to it — so a command that looks well under the limit can be at it.
    - **Going over the limit does not truncate the output — it removes it.** The `RECEIPT` still arrives, with the payload's exit code in `ERROR`, but `STDOUT` is absent rather than clipped at 1 MB. Very close to the limit the `RECEIPT` may not arrive at all.

    So if a `run` returns a receipt with no output, or no receipt, treat the output size as the first suspect. Writing to a file and collecting it with `log_get` (or `artifact_get`) has no such limit and is the right approach for anything that might approach it.

    To keep large output under the limit, emit UTF-8 or ASCII rather than UTF-16 — in PowerShell, `Out-File -Encoding utf8` or `[Console]::Out.Write()` — which doubles the number of characters that fit.

The payload is retrieved by the endpoint agent over HTTPS to the Ingestion API DNS endpoint. This DNS entry is available from the Sensor Download section of the web app if you need to allow it.

## Upload / Download via REST

Creating and getting Payloads is done asynchronously. The relevant REST APIs will return specific signed URLs instead of the actual Payload. In the case of a retrieving an existing payload, simply doing an HTTP GET using the returned URL will download the payload content. When creating a Payload the returned URL should be used in an HTTP PUT using the URL like:

```bash
curl -X PUT "THE-SIGNED-URL-HERE" -H "Content-Type: application/octet-stream" --upload-file your-file.exe
```

Note that the signed URLs are only valid for a few minutes.

## Permissions

Payloads are managed with two permissions:

- `payload.ctrl` allows you to create and delete payloads.
- `payload.use` allows you to run a given payload.
