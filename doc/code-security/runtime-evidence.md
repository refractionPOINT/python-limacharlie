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
| `""` (unknown) | no usable evidence — missing, stale, expired, unattributable or conflicting |
| `present` | an agent is on the resource, but the telemetry cannot carry a claim |
| `not_observed` | a **complete** telemetry window saw the package never run |
| `loaded` | the package is mapped into a running process |
| `executing` | the package **is** the running executable |

`not_observed` is the only negative rung and it is **not a safety claim**. It does not
say the package is gone, that the finding is fixed, or that the vulnerability is not
exploitable, and it never moves the finding's `lc_risk`, fingerprint or disposition.

Incomplete evidence never becomes a negative. An interrupted or too-young window, a
shed write, a truncated watch list, a versionless package, an unattributable package
and a conflicting package inventory all resolve to `present` or unknown, each with a
`reason` from `RUNTIME_REASONS` naming the gate that failed.

`dormant` was the old spelling of `not_observed`. `decode_runtime_status` folds it
(plan 24 §14) and nothing in the SDK can emit it. The CIEM identity-dormancy facet
(`dormant_90d`, `dormant_admin`), the AI-sessions session status and sensor sleep mode
keep the word and are unrelated vocabularies.

Fold a result to one verdict with `runtime_headline`, not with a maximum of your own:
the negative rung ranks *below* `present` so that one incomplete package — or a
partial sensor enumeration — vetoes a whole-resource negative.

This method requires a gateway route that is **not deployed yet**
(`POST /cloudsec/{oid}/findings/{id}/runtime-check`). Until it ships the call fails
like any unknown route rather than answering from nothing.

Contract: https://github.com/refractionPOINT/go-cloudsec/pull/413
Package: https://github.com/maximelb/claude-config/issues/150

Program: https://github.com/maximelb/claude-config/issues/149
Epic: https://github.com/maximelb/claude-config/issues/134
Backend: https://github.com/refractionPOINT/legion_graph/pull/241
