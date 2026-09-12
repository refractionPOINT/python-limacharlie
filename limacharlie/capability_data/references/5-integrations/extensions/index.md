# Extensions

Extensions add capabilities to LimaCharlie. Each extension is a separate piece of functionality that an organization subscribes to from the marketplace; once subscribed, extensions can be configured, called from D&R rules, or invoked directly.

See [Using Extensions](using-extensions.md) for the subscription / configuration model and how extensions are invoked.

## Categories

- [**LimaCharlie Extensions**](limacharlie/index.md) — built and maintained by LimaCharlie. Includes platform features (Git Sync, YARA Manager, Sensor Cull, Usage Alerts), forensic data collection (Artifact, BinLib, Dumper, Payload Manager), workflow tools (Cases, Feedback, Playbook), and protection / detection tooling (EPP, Exfil, Integrity, Lookup Manager, Reliable Tasking).

- [**Third-Party Extensions**](third-party/index.md) — built by partners or the community to integrate external tools and services. Examples: Velociraptor (DFIR collections), Zeek (network analysis), Hayabusa / Atomic Red Team / YARA (detection tooling), PagerDuty / Twilio (notifications), OTX / SecureAnnex (threat intel).

- [**Cloud CLI**](cloud-cli/index.md) — a single extension that runs cloud-provider CLIs as D&R response actions. Each supported platform (AWS, Azure, GCP, Okta, GitHub, etc.) has its own configuration page.

## Building extensions

If you want to publish your own extension, see the [Building Extensions](../../6-developer-guide/extensions/building-extensions.md) developer guide.

## See Also

- [Using Extensions](using-extensions.md)
- [API Integrations](../api-integrations/index.md) — the lookup-side complement to Cloud CLI's action-side
- [Outputs](../outputs/index.md) — for streaming data out instead of acting on it
