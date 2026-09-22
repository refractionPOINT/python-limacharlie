# Runtime identity evidence

`CloudSec.resolve_sensors` and `CloudSec.resolve_assets`, and the corresponding
CLI commands, preserve optional fields in resolved rows. For CS-14 enabled
cohorts these include `level`, `source`, `observed_at`, `stale_at`, and optional
`node` placement with `cluster_urn`, `node_uid`, confidence and its own expiry.
The SDK does not reinterpret identity as risk or manufacture absent posture flags.

An unresolved identifier is **unknown**, even when `resolver_ready` is true.
Readiness describes reader provisioning, not successful cache access or complete
sensor coverage. In particular, unresolved assets do not prove that no sensor
runs there. This clarifies the older resolve-helper docstring's absence example.
Chunked responses preserve evidence fields and merge readiness pessimistically.

Node placement is supplemental to an independent asset identity. It does not
prove host-versus-container execution, loaded code, exploitability, or absence of
other placements. Missing or expired node evidence does not invalidate an
independently valid primary asset match.

These optional fields require owner-approved backend dependencies and scoped
live validation. Their compatibility tests do not establish provider coverage,
production authorization or the public containment claim.

Program: https://github.com/maximelb/claude-config/issues/149
Epic: https://github.com/maximelb/claude-config/issues/134
Backend: https://github.com/refractionPOINT/legion_graph/pull/241
