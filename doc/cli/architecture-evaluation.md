# CLI-owned capability prototype

This experimental branch evaluates direct CLI use by agents. It is not a release.

`limacharlie help capability` lists packaged capabilities; add a capability ID
to read its operating procedure, and `--reference PATH` for declared documentation.
`--prompt` supplies compact agent instructions and a catalog directly from the CLI.
New commands extend existing `help` and `dr` roots; the lazy root-module map is unchanged.

`limacharlie dr deploy --key NAME --input-file candidate.json --positive yes.json
--negative no.json --oid OID --output json` validates target-aware positive and
negative fixtures, checks metadata and etag, writes the loaded candidate and reads
it back. `--dry-run` performs checks and returns before/candidate without writing.
The matching fixture exercises compilation on the actual target layout. Evidence
is recomputed in every invocation rather than stored as an approval token.

The package contains a snapshot of capability knowledge for this experiment, with
source provenance. A real migration would retire the duplicate source. The command
does not yet replace all raw mutation routes or provide persistent recovery receipts;
those limitations must be included in the architecture evaluation, not hidden by
successful task demonstrations. Neither this prototype nor the MCP workflow is a
credential isolation boundary against arbitrary authorized code.
