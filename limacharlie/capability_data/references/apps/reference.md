# Reference

The technical reference for app authors: the record fields, the `window.lc`
runtime your code calls, the design system, charting, permissions, and limits.

For the canonical record format and how to manage apps with the API, SDKs, or CLI,
see [Config Hive: Apps](../7-administration/config-hive/apps.md). For task-focused
examples, see [Building Blocks & Recipes](building-blocks-and-recipes.md).

## What an app is

An app is a **single, self-contained `<body>` fragment** — your HTML, inline CSS,
and inline JavaScript — stored in the `app` config hive. The console renders it
inside a sandboxed `<iframe>` and injects three things ahead of your content: a
strict Content-Security-Policy, the design-system stylesheet, and the `window.lc`
runtime. You write only the body; the host owns the document shell.

## Record fields

The fields you set when authoring an app (the `data` payload of an `app` hive
record). This is a summary — see
[Config Hive: Apps](../7-administration/config-hive/apps.md) for the authoritative
definition and validation.

| Field | Required | Purpose |
| --- | --- | --- |
| `display_name` | Yes | Name shown in the launcher and embeds (≤ 256 chars). |
| `html` | Yes | The self-contained `<body>` fragment to render. |
| `description` | No | Short blurb (≤ 4096 chars). |
| `icon` | No | Emoji, icon id, or small data-URI (≤ 256 chars). |
| `required_permissions` | No | LimaCharlie permissions the app needs (≤ 64). See [Permissions](#permissions-and-consent). |
| `allowed_origins` | No | External `https` sites the app may contact (≤ 32). See [External origins](#external-origins). |
| `required_services` | No | First-party services the app calls: `search`, `replay`, `cases`, `ai` (≤ 16). |
| `locations` | No | Where the app appears (≤ 8). See [Locations and context](#locations-and-context). |
| `expected_context` | No | Context keys the app expects when embedded (≤ 32). |
| `schema_version` | No | App format version. Omitted is treated as `1`. |

## The `window.lc` runtime

The console injects a trusted runtime as `window.lc`. It's the only bridge between
your app and LimaCharlie.

```js
await lc.ready            // resolves after the secure handshake — await before any call
lc.version               // '1'
lc.ctx.user              // { id, email, displayName } | null
lc.ctx.orgs              // [{ oid, name }] — the current organization is lc.ctx.orgs[0]
lc.ctx.context           // embed identifiers, e.g. { sid } on a sensor page
lc.ctx.theme             // { mode: 'dark' | 'light', vars: { '--lc-…': '…' } }
lc.api(method, path, body?, opts?)   // brokered LimaCharlie API call → Promise<JSON>
lc.chart(target, spec)               // themed chart → Chart instance
lc.onThemeChange(cb)                 // live theme updates; returns an unsubscribe fn
```

!!! warning "Always `await lc.ready` first"
    `lc.ctx` is empty and calls fail until the handshake completes. Begin every app
    with `await lc.ready`.

### The `lc.api` call

`lc.api(method, path, body?, opts?)` makes a LimaCharlie API call. The console
attaches a temporary, permission-scoped key — **never put an API key in an app.**

- **Paths are site-relative**, under `/v1`: `lc.api('GET', '/v1/who')`,
  `lc.api('GET', '/v1/sensors/' + oid)`. Absolute URLs, other hosts, and writes to
  the `app` hive itself are rejected.
- **Targeting a service.** Pass `opts.service` to route to a first-party service
  instead of the main API. The service must be listed in the app's
  `required_services`. The console host-pins the call and sends the same scoped
  key, but does **not** rewrite your path — use the path the service expects.

| Service | What it's for | Path shape |
| --- | --- | --- |
| `search` | Historical event search (LCQL) — the Query Console engine | `POST /v1/search/` → `GET /v1/search/<queryId>/` |
| `cases` | Case management | `GET /api/v1/cases` |
| `ai` | AI sessions / agents | `/v1/...` |
| `replay` | Sensor telemetry replay (distinct from `search`) | service-specific |

- **Errors** reject with an `Error` carrying `code` and `status`. The `code` is one
  of: `denied`, `rate_limited`, `unauthorized`, `http`, `timeout`, `aborted`,
  `malformed`. Catch and show `e.code`.
- **Limits:** about **10 requests/second** (burst 20), **8 concurrent**, request
  body up to **256 KB**, and a **70-second** timeout per call.

```js
try {
  const res = await lc.api('GET', '/v1/sensors/' + lc.ctx.orgs[0].oid)
} catch (e) {
  console.log(e.code, e.status)   // e.g. 'denied', 403
}
```

### The `lc.chart` helper

`lc.chart(target, spec)` draws a themed chart using **Chart.js v4**, provided by
the runtime (only when your app references `lc.chart`). Don't add your own chart
library — external scripts are blocked.

- **`target`** is a `<canvas>` element or its id, or any container element/id. If
  it isn't a canvas, one is created inside it. Give the container an explicit
  **height** or the chart renders invisible.
- **`spec`** is `{ type, data, options }`, exactly like Chart.js. `type` can be
  `bar`, `line`, `doughnut`, `pie`, and so on.
- **Theming is automatic.** Datasets you leave uncolored get the console palette
  (`--lc-accent`, `--lc-positive`, `--lc-warning`, `--lc-danger`, `--lc-muted`).
  Axis, grid, and text colors track the live theme and re-render on dark-mode
  toggle.
- **Returns** the Chart instance — call `.update()` or `.destroy()`. Calling
  `lc.chart` again on the same target replaces the previous chart cleanly.

### Reacting to theme changes

Theme tokens update live. If you draw something custom (not with the design-system
classes or `lc.chart`), subscribe to re-color it:

```js
const stop = lc.onThemeChange((theme) => {
  // theme.mode is 'dark' | 'light'; theme.vars holds the --lc-* values
})
// later: stop()
```

## Design system

The runtime injects CSS variables (`--lc-*`) derived from the live console theme
and a component stylesheet (`.lc-*`) that uses only those variables. **Compose the
classes and reference the variables; never hardcode colors or fonts** — that's what
keeps apps on-brand and dark-mode aware.

### Tokens

| Token | Use |
| --- | --- |
| `--lc-bg` | Page background |
| `--lc-surface` | Card / panel background |
| `--lc-line` | Borders and dividers |
| `--lc-ink` | Primary text |
| `--lc-muted` | Secondary text |
| `--lc-accent` | Links and primary accent |
| `--lc-positive` | Success (green) |
| `--lc-warning` | Warning (amber) |
| `--lc-danger` | Error (red) |
| `--lc-input-bg` / `--lc-input-line` | Form field background / border |
| `--lc-font-sans` / `--lc-font-mono` | UI font / monospace font |
| `--lc-radius` | Corner radius |
| `--lc-space` | Base spacing unit (8px) |

### Components

| Class | Element |
| --- | --- |
| `.lc-card` | Bordered container / panel |
| `.lc-btn`, `.lc-btn--primary`, `.lc-btn--danger` | Buttons |
| `.lc-input`, `.lc-select`, `.lc-textarea` | Form fields |
| `.lc-label` | Field label |
| `.lc-badge`, `.lc-badge--positive`, `.lc-badge--warning`, `.lc-badge--danger` | Status pills |
| `.lc-table` | Table |
| `.lc-kpi`, `.lc-kpi__value`, `.lc-kpi__label` | KPI metric (big number + label) |
| `.lc-row`, `.lc-col`, `.lc-stack` | Flex layout: horizontal row, vertical column, spaced stack |
| `.lc-muted` | Muted text |
| `.lc-mono` | Monospace text |
| `.lc-spinner` | Loading spinner |

Links, headings, and `code` / `pre` are styled for you as well.

## Permissions and consent

An app declares the permissions it needs in `required_permissions`. Two rules
bound this:

- **At authoring time**, you can only declare permissions you yourself hold. Each
  must be a real, non-root, issuable permission.
- **At view time**, the app runs with the **intersection** of its declared
  permissions and the *viewer's* own permissions. Anything the viewer lacks is
  simply dropped — the app runs without it and can never gain it.

The [consent screen](creating-and-managing-apps.md#understanding-the-consent-screen)
classifies permissions so viewers understand the risk:

| Class | Meaning | Examples |
| --- | --- | --- |
| **Dangerous** | Privilege-changing or billing actions | `apikey.ctrl`, `user.ctrl`, `billing.ctrl` |
| **Sensitive read** | Reads secrets, raw telemetry, or audit logs | `secret.get`, `insight.evt.get`, `audit.get` |
| **Write** | Changes state or takes action | `sensor.task`, `dr.set`, `secret.del` |
| **Read** | Read-only | `sensor.list`, `sensor.get` |

Dangerous and sensitive-read permissions trigger stronger warnings and require
re-consent every browser session. Request the **fewest** permissions an app needs,
and prefer read-only (`*.get`, `*.list`). See
[Permissions](../8-reference/permissions.md) for the full catalog.

## External origins

By default an app can reach **no** external website — only LimaCharlie, via
`lc.api`. To let an app's own `fetch` call an outside service, list it in
`allowed_origins`. Each entry:

- must use **`https`**;
- is **scheme + host** only, with an optional port — **no** path, query, fragment,
  credentials, or wildcards (e.g. `https://intel.example.com` or
  `https://intel.example.com:8443`);
- is shown to every viewer on the consent screen, with a warning that data could
  leave LimaCharlie.

Calls to declared origins use your app's own `fetch` and carry **no** LimaCharlie
key. Up to 32 origins.

## Locations and context

`locations` controls where an app may appear; `expected_context` declares the
identifiers it needs when embedded (the console passes them into `lc.ctx.context`).

| Location | Where it appears | Typical context |
| --- | --- | --- |
| `standalone` | The **Apps** launcher (default) | — |
| `within_a_sensor` | A sensor's page | `sid` |
| `within_a_detection` | A detection's page | `detection_id` |
| `within_a_case` | A case's page | case identifier |
| `within_a_dr_rule` | A D&R rule's page | rule identifier |

An app can declare several locations. Embedded surfaces beyond sensors are rolling
out — see [Choosing where an app appears](creating-and-managing-apps.md#choosing-where-an-app-appears).

## Hard rules and limits

Apps are validated when authored *and* when mounted. Some issues **block** the app;
others **warn** because the sandbox's Content-Security-Policy already neutralizes
them at runtime (the app silently breaks instead).

**Blocked** (the app won't save or run):

- Empty HTML, HTML over **3 MB**, or more than **20,000** elements.
- A `<base>` element, or an app-supplied `<meta http-equiv>` — the host owns the
  document shell and the CSP.

**Warned** (allowed, but blocked by CSP at runtime, so they won't work):

- External `<script src>`, external stylesheets, `@import` — inline everything.
- Nested `<iframe>`, `<embed>`, `<object>`, or `<form>` posting to an external
  action.
- Direct network calls (`fetch`, `XMLHttpRequest`, `WebSocket`) to anything not in
  `allowed_origins` — use `lc.api` for LimaCharlie data.

**Record limits:** unknown fields are rejected; total record size up to **10 MB**;
field caps as listed under [Record fields](#record-fields).

### The author's checklist

1. Output a single self-contained `<body>` fragment — no `<html>`, `<head>`,
   `<base>`, or `<meta http-equiv>`.
2. Inline all JavaScript and CSS — no external resources.
3. Read LimaCharlie data through `lc.api`; never embed a key or prompt for
   credentials.
4. Only contact external sites you declared in `allowed_origins`.
5. Style with `.lc-*` classes and `--lc-*` tokens — never hardcode colors or fonts.
6. Request the least permission necessary; prefer read-only.

## Where to go next

- [Building Blocks & Recipes](building-blocks-and-recipes.md) — worked examples.
- [Creating & Managing Apps](creating-and-managing-apps.md) — build, manage, place,
  and consent.
- [Config Hive: Apps](../7-administration/config-hive/apps.md) — record format and
  programmatic management.
