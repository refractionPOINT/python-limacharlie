# Template compatibility fixtures

`investigation_compatibility_snapshot.json` retains the scalar spellings,
observed result kinds/values and number/boolean field paths from the existing
investigation-service compatibility observations. It is a recorded input,
independent of the SDK resolver; this change does not claim a new service
capture. `ie_catalogue.json` separately records the public operator/pack API.

Regenerate **both** derived files from the checked-in snapshot at the repo root:

```sh
python tools/generate_investigation_fixtures.py
```

This deterministically writes `investigation_scalars.json` and
`investigation_typed_fields.json`. Do not edit those generated files. Tests
regenerate them in a temporary directory and require exact byte equality.

To refresh observations, export scalar rows (`src`, `kind`, optional `value`
or `error`) and typed-field rows (`path`, `kind`) from the investigation
service's compatibility harness into the snapshot's `cases` and `fields`
lists. Preserve every spelling and the observed value; do not derive expected
results by calling the SDK resolver. The export is a local recorded artifact,
not a new public endpoint. To normalize an exported snapshot before updating
the checked-in input, use:

```sh
python tools/generate_investigation_fixtures.py --input observations.json --output-dir generated
```

The input format uses public value categories: `null`, `bool`, `int`, `float`,
`string`, `timestamp`, `array`, `object`, or `error`. Canonical `sequence` and
`mapping` inputs are also accepted. Generation maps `array` to `sequence` and
`object` to `mapping`. Output fixtures and their consumer accept **only** the
canonical kinds; unknown kinds fail clearly, rather than defaulting to a map.
Typed field kinds are `number` or `bool`; a star in a path is a list index or
map key. Timestamps use UTC RFC 3339 and non-finite values retain their textual
spellings so rejection tests remain reproducible. Keep diagnostic text in
public contract terminology. When refreshing inputs, review both generated
files for schema/value changes and rerun the SDK compatibility tests.
