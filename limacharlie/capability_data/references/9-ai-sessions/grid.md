# Grid: Your AI Field Engineer

Grid is the fastest way to put a working AI security engineer inside your
environment. You describe the outcome you want in plain English — "triage
quarantined phishing in our Google Workspace and open a case for anything
risky" — and Grid stands up the automation that delivers it, then keeps
watching over it for you.

No rule syntax to learn. No detection logic to write. No integrations to wire
by hand. You bring the goal; Grid builds and runs the security program.

!!! tip "The one-sentence version"
    Grid takes a plain-language goal and turns it into running, supervised
    security automation in your LimaCharlie organization — usually in a few
    minutes.

## What Grid actually gives you

When you onboard with Grid, you don't get a chatbot that answers questions and
forgets. You get an **AI Field Deployed Engineer (FDE)** — a persistent,
named expert that lives in your organization.

The FDE is modeled on a real Forward Deployed Engineer: the resident expert a
security vendor embeds with a customer to design, build, and tune their setup.
Two things make this different from a typical AI assistant:

- **It supervises; it doesn't do the grunt work itself.** To "automate
  phishing triage," the FDE doesn't read your emails one by one. It *builds* a
  dedicated worker agent whose only job is email triage, wires up the data
  source and the trigger that feeds it, and gives it a place to file its
  findings. Then the FDE steps back and watches that worker — is it doing a
  good job, is the data still flowing, does it need tuning?
- **It keeps working when you're not looking.** The FDE runs unattended on a
  schedule you choose (anywhere from every 30 minutes to weekly). Every run it
  re-checks the workers it built, looks for gaps, and improves what's drifting.

Think of it as hiring an engineer who designs your security automation, builds
it, and then shows up every day to make sure it's still working — except it
does the first build in minutes and never takes a day off.

## Built on battle-hardened infrastructure

Grid is new. What it stands on is not.

Every worker agent, trigger, and detection Grid builds runs on the
**LimaCharlie platform** — the same Agentic SecOps workspace that MSSPs and
security teams already rely on to run detection and response across their
fleets at scale. The data pipeline, the detection-and-response engine, the
secrets vault, the case management, the audit trail — none of it is new code
written for an AI demo. Grid is an expert *operator* of infrastructure that has
been carrying real production security workloads for years.

That matters in two practical ways:

- **Everything Grid builds is real LimaCharlie configuration** — D&R rules,
  cloud adapters, playbooks, AI agents — that you can inspect, edit, export,
  or run yourself. There is no Grid-only black box your automation is trapped
  inside.
- **The guardrails are platform guardrails.** Grid's permissions, data
  residency, audit logging, and rollback are enforced by LimaCharlie itself,
  not by the AI's good intentions (more on this below).

## How it works, end to end

Grid runs as a short, guided conversation. Here is the whole arc:

1. **You state the outcome.** Grid asks one main question: what do you want to
   be true in this organization that isn't true today? You answer in plain
   language. Grid leads with expert recommendations instead of quizzing you on
   technical details.
2. **Grid connects the data, if needed.** An FDE is worthless without the data
   its outcome depends on. If the source you need (a SaaS feed, cloud logs,
   endpoint telemetry) isn't flowing yet, Grid helps you connect it first —
   walking you through credentials and picking the right adapter type for you.
3. **Grid proposes a charter.** It writes a complete, plain-language plan: the
   outcome, exactly what it will build, what runs automatically versus what
   needs your approval, and how you'll know it's working. It validates this
   against your *real* data before showing it to you — so the plan ships with
   verified specifics, not guesses. You review it and reply **go** (or ask for
   changes).
4. **Grid builds the whole thing.** On its first run the FDE builds the
   *complete* solution end to end — every worker agent, every trigger, every
   detection — and tests it before it hands back to you. No "phase one now,
   the rest later."
5. **Grid shows you what it built.** You get a visual map (the "story") of
   everything now running in your organization: the FDE supervisor, every
   worker it created, and how they connect.
6. **Grid keeps watch.** From then on the FDE runs on its schedule, supervising
   what it built and flagging anything that needs your attention.

!!! note "Talking in outcomes, not plumbing"
    Throughout, Grid deliberately speaks in outcomes and implications — "the
    system will investigate each restore request and flag the risky ones,
    costing roughly X" — not in LimaCharlie mechanics. You never need to know
    what a D&R rule is to use Grid. The mechanics are there if you want them;
    they're just never required.

## Your first few minutes

The quickest way to meet Grid is to give it a goal and watch it work.

1. **Open Grid** and sign in (or create an account — Grid can stand up a brand
   new organization for you as part of onboarding).
2. **Describe the outcome you want.** Be concrete about the result, not the
   method. Good first prompts:
    - *"Triage quarantined phishing in our Google Workspace and open a case for
      anything risky."*
    - *"Watch our cloud audit logs for risky permission changes and alert me
      before anything bad happens."*
    - *"Review endpoint detections each morning and summarize what actually
      matters."*
3. **Answer the few questions Grid asks.** It will only ask for what it can't
   figure out on its own — your goal, any hard constraints, and the occasional
   judgment call where your preference has to win. If it needs a credential
   (an API key, an LLM provider key), it gives you a secure form — you never
   paste secrets into the chat.
4. **Read the charter and reply `go`.** Take a moment to confirm what will run
   on its own versus what will ask you first.
5. **Watch it build,** then explore the story map of what now exists.

That's it. You now have a supervised AI engineer running in your org.

!!! tip "Start small, then grow"
    You don't have to automate everything at once. Give your FDE one clear
    outcome to own. Once you trust it, open a chat and ask it to take on more.

## You stay in control

Autonomy is a dial you set, not a default you accept.

- **Approval gates.** During onboarding you decide which actions the FDE may
  take on its own and which must ask a human first. Anything that changes your
  environment, notifies people, or deletes something can be put behind an
  approval step. When the FDE wants to do something gated, it opens a **case**
  explaining what it wants to do, why, and the cost — and waits for your
  go-ahead. Nothing risky happens silently.
- **Least privilege, enforced by the platform.** Each FDE (and each worker it
  builds) runs with its own scoped API key holding only the permissions its job
  needs. That key — not the AI's prompt — is the real boundary. An action
  outside its grant simply can't happen.
- **Full audit trail.** Everything Grid does is ordinary LimaCharlie activity:
  logged, attributable, and reviewable like any other operation in your org.

## Everything is visible and reversible

Grid never leaves you guessing about what it changed.

- **The story map** shows the full graph of what an FDE owns — the supervisor,
  its workers, the triggers, the data sources, the playbooks — and how they
  connect. It's the picture of your automation, kept current as the FDE builds.
- **One-tag rollback.** Every single resource an FDE creates or touches is
  tagged with that FDE's name. Removing an FDE and its *entire* footprint —
  every worker, rule, and secret it ever made — is a single tag query. There's
  no orphaned configuration left behind, and nothing you can't undo.

## Talking to your FDE

Your FDE isn't a fire-and-forget script. You can open a chat with it any time
from the org overview ("**Chat with FDE**").

In a chat the FDE behaves differently from its unattended runs: it orients
itself read-only, gives you a short plain-language status — what it's built,
what's pending, anything unhealthy — and then waits for your direction. It
won't run its build-and-supervise program while you're talking to it, so you
can ask questions, request changes, or hand it new work without it charging off
on its own. Lead it like you'd lead an engineer on your team.

## What it costs

A LimaCharlie organization runs on a free tier by default, and many Grid setups
fit inside it. Some outcomes need paid components — a high-volume data feed,
deployed endpoint sensors, or a deterministic playbook — and when that's the
case Grid tells you *before* it builds: which paid piece the outcome needs, why,
in plain terms, and what you'll need to do (add a payment method, raise a
quota). If you'd rather not, Grid offers to re-scope to free-tier-only pieces.
You never get a surprise bill from automation you didn't approve.

## Where to go next

Grid is the guided, outcome-first front door to LimaCharlie's AI capabilities.
Everything it builds is standard platform configuration, so when you want to go
deeper, the rest of these docs apply directly:

- [AI Sessions Overview](index.md) — the AI runtime Grid's FDEs run on.
- [User Sessions](user-sessions.md) — interactive AI sessions, including the
  chat experience behind "Chat with FDE."
- [D&R-Driven Sessions](dr-sessions.md) — how scheduled and event-triggered AI
  runs work under the hood.
- [AI Memory](memory.md) — how an FDE remembers its charter and state across
  runs.
- [Tool Permissions & Profiles](tool-permissions.md) — the permission model
  that bounds what every agent can do.
- [Story Tags](../8-reference/story-tags.md) — the tagging schema behind the
  story map and one-tag rollback.
