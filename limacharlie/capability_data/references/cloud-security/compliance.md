# Compliance

Cloud Security evaluates compliance frameworks continuously against the live
estate: each control maps to detection rules, and a control fails when open
findings prove the violation — so the compliance report is always as fresh
as the last sweep, with finding-level evidence per control.

## The report

```bash
# Whole-estate assessment against a framework (default: cis-gcp).
limacharlie cloudsec compliance report --framework cis-gcp

# Which frameworks are available?
limacharlie cloudsec compliance frameworks
```

Thirteen frameworks ship today — `cis-aws`, `cis-azure`, `cis-gcp` (the
default), `cis-m365`, `soc2`, `pci-dss`, `hipaa`, `iso-27001`, `nist-csf`,
`nist-ai-rmf`, `owasp-llm`, `owasp-top10`, and `cis-supply-chain`. `nist-ai-rmf`
and `owasp-llm` are AI frameworks: they assess the OpenAI and Anthropic estate
connected through the [AI providers](providers.md#ai-security-aispm).
`owasp-top10` (OWASP Top 10:2021, mapped by CWE) and `cis-supply-chain` (the CIS
Software Supply Chain Security Guide's *Source Code* and *Dependencies*
sections) are graded off [Code Scanning](code-scanning.md) and apply only when a
source-code provider is connected. `cis-m365` is graded off the
Microsoft Entra directory, so it covers the benchmark's Entra chapter and reports
NOT_ASSESSED for the admin centers that are not collected (Defender, Purview,
Exchange, SharePoint, Teams) — read each control's description for what it
assesses and why. It applies to a tenant connected as an `entra` provider, or as
the Entra half of an `azure` one. The set
grows over time, so `limacharlie cloudsec compliance frameworks`
(`GET /compliance/frameworks`) — which carries each framework's `id`, `name`,
`version`, and control counts — is the source of truth for valid
`--framework` values.

The report is per-control, and each control lands in one of four states:

- **PASS** — no open finding proves a violation of the control.
- **FAIL** — one or more open findings prove it; their `finding_id`s are
  attached as evidence.
- **NOT_ASSESSED** — the control cannot be evaluated automatically. These are
  the manual / attestation controls (policy documents, board sign-off,
  interview evidence): the framework marks them as not auto-assessable, so no
  rule is run and no verdict is invented. A control also lands here when the
  detection that would have decided it never ran — including when a
  [`rules` policy](custom-rules.md#compliance-interaction) has **disabled every
  rule the control relies on** and it has no other basis to be graded from. A
  zero-violation result from a detector that did not run is not evidence of
  compliance, so it is never reported as a PASS.
- **NOT_APPLICABLE** — the control has nothing to assess in *this* estate:
  either the framework's cloud has no resources connected, or the control
  declares no resource types to apply to.

A framework scoped to a single cloud assesses only that cloud's findings —
`cis-aws` looks at AWS findings, `cis-gcp` at GCP. A framework with no
in-scope resource types comes back **NOT_APPLICABLE** rather than a vacuous
PASS, so an empty estate never reads as compliant.

### How the score is computed

The report's summary carries `passed`, `failed`, `not_assessed`,
`not_applicable`, `total`, `score`, and `applicable`. The score is the share of
**assessable** controls that pass:

```text
score = passed / (passed + failed) × 100
```

Only PASS and FAIL are assessable. NOT_ASSESSED and NOT_APPLICABLE controls are
excluded from the denominator entirely, so a manual control you have not
attested does not drag the number down, and a framework you are only partly in
scope for is not penalized for the parts that do not apply.

!!! warning "No assessable controls means `applicable: false`, not 100%"
    When nothing in the framework is assessable against your estate, the report
    comes back with `applicable: false` and a `score` of **0** — never a
    vacuous 100. Read `applicable` before reading `score`: a 0 with
    `applicable: false` means "we could not assess this", not "you failed
    everything".

!!! note "FAIL evidence is capped per control"
    A failing control attaches at most **25** proving `finding_id`s in the JSON
    report, while `evidence_count` reports the true total — so a control with
    900 violations shows 25 examples and `evidence_count: 900`. The CSV export
    raises the cap to 2,000 ids per control for auditors who need the fuller
    list; use the [findings API](findings.md) itself when you need all of them.

### Auditor export

For auditors, the same report exports as CSV — one row per control including
the evidence finding ids — via the API's `?format=csv`
(see [Automation & IaC](automation.md#csv-export)).

## Scoped assignments

A whole-estate score is often the wrong altitude: production must meet the
bar, the sandbox does not. A `compliance`-typed `cloudsec_policy` record
creates a **named, scoped assignment** — a framework evaluated over a subset
of the estate:

```bash
cat > prod-cis.json <<EOF
{
  "policy_type": "compliance",
  "compliance": {
    "framework_id": "cis-gcp",
    "description": "Production accounts only",
    "scope": [
      {"account_glob": ["proj-prod-*"]}
    ]
  }
}
EOF

limacharlie hive set --hive-name cloudsec_policy --key prod-cis \
  --oid $OID --input-file prod-cis.json --enabled
```

Scope matchers support `account_contains`, `account_glob`, `name_contains`,
and `name_glob` (globs use the shared dialect, including leading-`!`
negation — see [Glob syntax](configuration.md#glob-syntax)); an empty scope
means the whole estate.

List assignments (each with its own scoped score) and evaluate one:

```bash
limacharlie cloudsec compliance assignments
limacharlie cloudsec compliance report --assignment prod-cis
```

When `--assignment` is set, its framework is used and `--framework` is
ignored.

!!! info "Permissions"
    Reading compliance requires `cloudsec.get`. Assignments are Hive policy
    records, so creating them follows the `cloudsec_policy` hive
    permissions.
