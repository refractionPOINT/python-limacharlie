# Creating & Managing Apps

This page walks through building an app with the AI assistant, managing apps from
the **Apps** page, and reading the consent screen that appears before an app runs.

You manage everything from **Apps** in your organization sidebar
(`/orgs/<your-org>/apps`). The page header reads:

> Custom mini apps for this organization. Apps run in a sandboxed frame and act on
> your behalf only within the permissions you approve.

## Building an app with the AI assistant

The fastest way to build an app — and the one that needs no coding — is to
describe it to the LimaCharlie AI assistant.

1. On the **Apps** page, click **Create new App**. This opens a new AI session
   already primed to build an app for your organization.
2. **Describe the outcome you want**, in plain language. Be specific about the
   result, not the method. Good prompts:
    - *"A dashboard with three big numbers: total sensors, sensors online now, and
      sensors that haven't checked in for 24 hours."*
    - *"A table of my detections from the last 7 days, with the detection name, the
      sensor hostname, and the time, newest first."*
    - *"A bar chart of how many of my sensors are on Windows, macOS, and Linux."*
3. **Let the assistant build it.** Behind the scenes it reads the official app
   authoring guide, confirms every LimaCharlie data call against your
   organization's live API so it doesn't invent endpoints, writes the app, and
   saves it to your organization.
4. When it's done, the assistant shows an **Open your live app** card right in the
   chat. Click it to jump straight to your running app.

!!! tip "Talk in outcomes, refine in conversation"
    You don't need to know any LimaCharlie API or write any HTML. If the first
    result isn't quite right, just say so — *"group the table by platform"*,
    *"make the offline count red"*, *"add a refresh button"* — and the assistant
    revises the app in place.

!!! note "New apps may start turned off"
    An app has to be **enabled** to be active (and to appear in any embedded
    locations). If your new app shows a *disabled* status, switch it on with the
    **Status** toggle on the **Apps** page — see [Turning apps on and off](#turning-apps-on-and-off).

### Editing an existing app

1. On the **Apps** page, open the **⋯** menu on the app's row and choose
   **Edit with AI** (also available as **Edit App** from the app's own page).
2. An AI session opens with your existing app loaded. Describe the change you want
   and the assistant updates and re-saves the app.

## Building an app with the API, SDKs, or CLI

Apps are stored as records in the `app` config hive, so you can also create and
manage them programmatically — handy for version control, Infrastructure-as-Code,
or bulk deployment across organizations.

The record format, the security invariants enforced when you save, and full
REST / Python / Go / CLI examples live in
[Config Hive: Apps](../7-administration/config-hive/apps.md). The short version of
the CLI flow:

```bash
# Create (and enable) an app from a JSON file describing the record:
limacharlie hive set --hive-name app --key my-app --input-file app.json --enabled

# Later, turn it off or back on:
limacharlie hive disable --hive-name app --key my-app
limacharlie hive enable  --hive-name app --key my-app
```

!!! warning "Apps are created disabled unless you say otherwise"
    A new hive record is **disabled by default**. The `--enabled` flag above
    creates and enables it in one step; without it, the app stays off until you run
    `limacharlie hive enable`.

For what goes *inside* the `html` field — the runtime your code calls, the design
system, and charting — see the [Reference](reference.md).

## Managing apps from the Apps page

The **Apps** page lists every app in the organization. Each row shows four columns:

| Column | What it shows |
| --- | --- |
| **App** | The app's icon, name, and description. |
| **Permissions** | A quick summary of what the app can do — for example *"2 read"* or *"1 sensitive · 1 write"*. Red badges flag sensitive access. |
| **Last modified** | When the app last changed, and who changed it. |
| **Status** | A toggle to enable or disable the app. |

The **⋯** menu on each row offers:

- **Open** — run the app in its own full-page view.
- **Edit with AI** — open an AI session to modify it (needs `app.set`).
- **Delete** — remove the app (needs `app.del`). You'll be asked to confirm:
  *Delete "&lt;name&gt;"? This cannot be undone.*

### Turning apps on and off

The **Status** toggle enables or disables an app (you need `app.set.mtd`).

- A **disabled** app is inactive and does **not** appear in its embedded locations
  (for example, it won't show on sensor pages).
- An **enabled** app is live. Enabling does not bypass consent — each viewer still
  approves the app the first time they open it.

## Choosing where an app appears

When you build an app you decide where it should surface. In conversation you can
just say where you want it — *"put this on each sensor's page"* — and the assistant
configures the rest. Under the hood, two settings control this:

- **Locations** — where the app is allowed to appear:
  - **Standalone** — in the **Apps** launcher (the default).
  - **Within a sensor / case / detection / D&R rule** — embedded as a panel on
    that object's page.
- **Expected context** — the identifiers the app needs when embedded. The console
  passes these in automatically. For example, an app placed on sensor pages
  receives that sensor's ID (`sid`), so it can show data for *the sensor you're
  looking at* without you typing anything.

An app can live in several places at once — for instance, both in the launcher and
on every sensor page. See [Building Blocks & Recipes](building-blocks-and-recipes.md#recipe-an-embedded-sensor-panel)
for a worked embedded example, and the [Reference](reference.md#locations-and-context)
for the exact values.

## Understanding the consent screen

The first time you open an app — and again whenever it materially changes — you
see a **consent screen** before it runs. It is your chance to confirm what the app
will be able to do *on your behalf*. Read it like a permission prompt for a phone
app. It has four parts:

1. **What it is and who touched it last.** The app's name, description, and the
   user who last edited it, with the date. Unexpected author? Stop and check.
2. **Permissions this app will use.** The access the app will run with, grouped by
   how much it matters:
    - **Sensitive permissions** (red) — privilege-changing or billing actions.
      Treat these with the most caution.
    - **Sensitive data access** (red) — the app can read secrets, raw telemetry,
      or audit logs. If it can *also* reach an external site, that data could
      leave LimaCharlie.
    - **Can make changes** (amber) — the app can modify your environment (for
      example, tag or isolate a sensor, change a rule).
    - **Read-only access** — the app can read the listed data but not change it.
    - **Not granted** — permissions the app asked for that *you don't hold*. The
      app runs **without** these; it can never gain them by asking.
3. **External data access.** Either a reassuring *"This app cannot contact any
   external sites."*, or a warning that lists every outside website the app may
   contact. Anything the app can read could be sent to those sites, so only
   continue if you trust the author.
4. **LimaCharlie services.** Any additional first-party services the app can call
   beyond the main API — Search (historical events), Replay (telemetry), Cases, or
   AI — using the same approved permissions.

The button reads **Open app** for an ordinary app, or **I understand, open app**
when the app requests sensitive access. Choose **Cancel** to back out without
running it.

!!! info "When you'll be asked again"
    For most apps, your approval is remembered in that browser, so you won't be
    prompted again — **unless the app changes** (its content, permissions,
    external sites, or services), which re-triggers consent so you can review
    what's new. Apps that can read **sensitive data** or perform **privileged /
    billing** actions are deliberately *not* remembered across sessions: you
    re-approve them each browser session.

## Where to go next

- [Building Blocks & Recipes](building-blocks-and-recipes.md) — patterns for
  tables, KPIs, charts, forms, and embedded panels.
- [Reference](reference.md) — the runtime, design system, charting, permissions,
  and limits.
- [Config Hive: Apps](../7-administration/config-hive/apps.md) — the record format
  and programmatic management.
