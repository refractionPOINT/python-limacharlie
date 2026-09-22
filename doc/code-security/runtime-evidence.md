# Runtime identity evidence

`CloudSec.resolve_sensors` and `CloudSec.resolve_assets`, and the corresponding
CLI commands, preserve optional fields in resolved rows. For CS-14 enabled
cohorts these include `level`, `source`, `observed_at`, `stale_at`, and optional
`node` placement with `cluster_urn`, `node_uid`, confidence and its own expiry.
The SDK does not reinterpret identity as risk or manufacture absent posture flags.

An unresolved identifier is **unknown**, even when `resolver_ready` is true.
Readiness describes reader provisioning, not successful cache access or complete
sensor coverage. In particular, unresolved assets do not prove that no sensor
runs there. Chunked responses preserve evidence fields and merge readiness pessimistically.

Node placement is supplemental to an independent asset identity. It does not
prove host-versus-container execution, loaded code, exploitability, or absence of
other placements. Missing or expired node evidence does not invalidate an
independently valid primary asset match.

These optional fields require owner-approved backend dependencies and scoped
live validation. Their compatibility tests do not establish provider coverage,
production authorization or the public containment claim.

## Runtime PACKAGE evidence: the five-rung ladder (CS-15)

A different question from the identity resolution above, with its own vocabulary:
**did the vulnerable code actually run?** `CloudSec.check_finding_runtime` asks it for
one finding, and the answer is one of exactly five rungs
(`limacharlie.sdk.cloudsec.RUNTIME_STATUSES`):

| Rung | Means |
|---|---|
| `unknown` | no usable evidence — missing, stale, expired, unattributable or conflicting |
| `present` | an agent is on the resource, but the telemetry cannot carry a claim |
| `not_observed` | a **complete** telemetry window saw the package never run |
| `loaded` | the package is mapped into a running process |
| `executing` | the package **is** the running executable |

The unknown rung has two spellings and one rendered form. Go's zero value is `""`, so an
unset status is unknown by construction; a public API renders it as the literal
`"unknown"` (`RUNTIME_WIRE_UNKNOWN`), because an empty string in a JSON enum reads as a
missing field rather than as an answer. `decode_runtime_status` accepts both.

`not_observed` is the only negative rung and **it is not a safety claim**. It does not
say the package is gone, that the finding is fixed, or that the vulnerability is not
exploitable, and it never moves the finding's `lc_risk`, fingerprint or disposition.

Incomplete evidence never becomes a negative. An interrupted or too-young window, a
shed write, a truncated watch list, a versionless package, an unattributable package
and a conflicting package inventory all resolve to `present` or unknown, each with a
`reason` from `RUNTIME_REASONS` naming the gate that failed.

Read the answer with the two readers, not by hand:

* `runtime_verdict(response)` — the server's whole-resource verdict, plus the coverage
  it rests on. It is a **field read**: the backend already computes the fold, so
  re-deriving it in the client would be a permanent drift surface. And the obvious hand-rolled fold is wrong in a dangerous
  way — the negative rung ranks *below* `present`, so taking the strongest per-package
  answer reports a whole-machine negative whenever nothing positive turned up, losing
  the veto that one incomplete package (or an incomplete sensor set) holds.
* `runtime_packages(response)` — the per-package rows, flat, with statuses decoded and
  every other field passed through.

Two things to read before `status`:

* **`accepted`.** False means the check did not run, and `reason` is then one of
  `RUNTIME_UNAVAILABLE_REASONS` (`feature_disabled`, `no_resource`, `no_packages`,
  `no_sensors`, `cache_unavailable`) rather than a verdict reason. The feature is
  **default-off**, so that is the common answer today — and it is not a statement that
  nothing ran. An unknown finding id returns `runtime: null`.
* **`complete` and `retry_after_seconds`.** Asking is what *starts* the measurement: the
  route publishes the finding's packages as relevant and evidence accumulates over the
  following minutes. A cold first call is expected to be inconclusive; ask again after
  the retry rather than reporting the immature window as a finished answer.

`dormant` was the old name for `not_observed`. `decode_runtime_status` folds it and
nothing in the SDK can emit it. The CIEM identity-dormancy facet (`dormant_90d`,
`dormant_admin`), the AI-sessions session status and sensor sleep mode keep the word and
are unrelated vocabularies.

This method requires the gateway route
`POST /cloudsec/{oid}/findings/{id}/runtime-check`. Where it is not yet available the
call fails like any unknown route rather than answering from nothing.
