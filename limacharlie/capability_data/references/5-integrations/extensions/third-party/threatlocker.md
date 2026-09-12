# ThreatLocker

[ThreatLocker](https://threatlocker.com) is an Application Control platform whose **approval-request queue** — end-users asking for an unknown binary to be allowed — is the single biggest source of operator toil in any rollout.

The ThreatLocker LimaCharlie Extension is a thin proxy over the [ThreatLocker Portal API](https://portalapi.g.threatlocker.com/swagger). It pairs with the [ThreatLocker adapter](../../../2-sensors-deployment/adapters/types/threatlocker.md), which delivers approval-request events into LimaCharlie: an AI agent (or a Playbook) reads each event, calls this extension to enrich it against the Portal API (matching built-in app, computer/group context, existing policies), then calls this extension again with the decision — **permit**, **reject**, or **ignore**. The extension itself makes no decisions; it forwards the JSON body verbatim and returns the Portal response verbatim.

## Setup

### 1. Create a Portal API token

In the ThreatLocker Portal, navigate to **Administration → API Users** and create a new API user. Copy the resulting **API token** — you will need it in the next step. ThreatLocker shows the token only once.

### 2. Find your instance letter

ThreatLocker hosts each tenant on a lettered instance (`b`, `c`, `d`, …, `g`, `h`, …) and API tokens are scoped to the instance that minted them. To find yours, click the **Help** button in the top-right corner of any Portal page and read the letter in parentheses next to **ThreatLocker Access** (e.g. `ThreatLocker Access (G)` → `instance_letter: g`).

> ⚠️ **A token from one instance returns `403 TOKEN_REVOKED` on every other instance.** The API does not distinguish "wrong instance" from a genuinely revoked token. If you are confident the token is active and still see `TOKEN_REVOKED`, double-check the instance letter before assuming the token was revoked.

### 3. Subscribe to the extension

Subscribe to `ext-threatlocker` from the LimaCharlie **Marketplace** (Extensions → Add-Ons).

### 4. Store the API token

In **Secrets Manager**, create a new secret (for example `threatlocker-api-token`) and paste the Portal API token as its value.

### 5. Configure the extension

In **Extensions → ext-threatlocker → Configuration**, fill in:

| Field | Required | Value |
| --- | --- | --- |
| `api_token` | yes | Reference to the secret created in step 4, e.g. `hive://secret/threatlocker-api-token`. |
| `instance_letter` | yes | The single lowercase letter from step 2, e.g. `g`. |
| `managed_organization_id` | no | UUID of the managed (child) organization. Sent as the `ManagedOrganizationId` header. Used by MSP **parent** tokens to scope every call to a specific child tenant. |

The API token is sent **verbatim** in the `Authorization` header — there is no `Bearer` prefix and no OAuth flow. The instance letter is validated at save time; everything else is rejected at request time by the Portal API.

## Actions

The extension exposes thirteen actions. All `POST` actions take a single `body` parameter — the JSON object forwarded verbatim as the Portal API request body. `GET` actions take typed parameters: an `id` for single-id endpoints, or named flags for the computer-group inspector.

The body field set per endpoint is **not shadowed** by the extension — the Portal API surface is large and changes over time, so the extension stays out of the way. Refer to the ThreatLocker Portal Swagger spec (visit `https://portalapi.<instance>.threatlocker.com/swagger`) for the exact field set per endpoint.

### Approval-request reads

#### `approval_request_search`

`POST ApprovalRequest/ApprovalRequestGetByParameters` — list approval requests matching a filter.

| Field | Type | Notes |
| --- | --- | --- |
| `body` | object | **Required.** Forwarded as the JSON request body. Common fields: `statusId` (1=pending, 4=approved, …), `searchText`, `requestTypeId`, `actionType` (array), `pageNumber`, `pageSize`, `orderBy`, `isAscending`. |

#### `approval_request_get`

`GET ApprovalRequest/ApprovalRequestGetById` — fetch a single approval request.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | **Required.** `approvalRequestId` (UUID). |

### Application reads

#### `application_get_matching`

`POST Application/ApplicationGetMatchingList` — the **primary enrichment call**. Given a file (`sha256`, path, certificates, …) returns the ThreatLocker built-in (or custom) applications it matches. An empty result is the "no built-in match" answer — meaning the file is unknown to ThreatLocker's curated catalog and an AI policy decision should weigh that accordingly.

| Field | Type | Notes |
| --- | --- | --- |
| `body` | object | **Required.** Common fields: `sha256`, `hash`, `path`, `certs`, `organizationIds`, `osType`, `approvalRequestId`. |

#### `application_get`

`GET Application/ApplicationGetById` — full details for a single application.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | **Required.** `applicationId` (UUID). |

#### `application_get_research`

`GET Application/ApplicationGetResearchDetailsById` — ThreatLocker's curated threat-research info for an application (Living-Off-The-Land flags, common abuse, reputation notes). Useful when deciding whether the matching app is sensitive enough to warrant a denial.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | **Required.** `applicationId` (UUID). |

### Computer reads

#### `computer_get`

`GET Computer/ComputerGetForEditById` — fetch a single computer's full record (group, OS, tags, last check-in). The fastest path from an approval-request event's `computerId` to the device context.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | **Required.** `computerId` (UUID). |

#### `computer_search`

`POST Computer/ComputerGetByAllParameters` — free-text or group/mode-scoped computer search.

| Field | Type | Notes |
| --- | --- | --- |
| `body` | object | **Required.** Common fields: `searchText`, `computerGroup`, `computerId`, `action`, `kindOfAction`, `showLastCheckIn`, `showDeleted`, `childOrganizations`, `pageNumber`, `pageSize`, `orderBy`, `isAscending`, `searchBy`. |

### Computer-group reads

#### `computer_group_list_for_permit`

`GET ComputerGroup/ComputerGroupGetForPermitApplication` — list the computer groups eligible to receive an approval/permit decision. Start here when picking the scope to attach a new permit policy to.

| Field | Type | Notes |
| --- | --- | --- |
| `os_type` | int | `0` = All (default), `1` = Windows, `2` = Mac, `3` = Linux. |

#### `computer_group_get_full`

`GET ComputerGroup/ComputerGroupGetGroupAndComputer` — rich one-shot inspector: a group plus (optionally) every policy attached to it and every computer in it, in a single round trip.

| Field | Type | Notes |
| --- | --- | --- |
| `computer_group_id` | string | **Required.** `ComputerGroupId` (UUID). |
| `os_type` | int | `0` = All, `1` = Windows, `2` = Mac, `3` = Linux. |
| `include_all_policies` | bool | Include policies attached to the group. **Recommended** — defaults to `true`. |
| `include_all_computers` | bool | Include computers in the group. **Recommended** — defaults to `true`. |
| `include_global` | bool | Include the global "All Computers" group. |
| `include_organizations` | bool | Include parent/child orgs. |
| `include_parent_groups` | bool | Include parent groups. |
| `include_logged_in_objects` | bool | Include logged-in objects. |
| `include_access_devices` | bool | Include access devices. |
| `include_removed_computers` | bool | Include removed computers. |
| `portal_module_type_id` | int | Optional `PortalModuleTypeId`. |

With `include_all_policies=true` and `include_all_computers=true` this endpoint answers, in a single call, *"who else is in this group, what policies are already attached, and would this new permit policy collide with any of them?"*

### Policy reads

#### `policy_get`

`GET Policy/PolicyGetById` — fetch one policy's full record by id. The Portal API has no list-policies-by-parameters endpoint; iterate via `computer_group_get_full` with `include_all_policies=true` and resolve each policy by id with `policy_get`.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | **Required.** `policyId` (UUID). |

### Decisions

The three write actions close the loop on an approval request — they are the only actions in this extension that mutate ThreatLocker state.

#### `approval_request_permit`

`POST ApprovalRequest/ApprovalRequestPermitApplication` — **approve**. Creates (or updates) a permit policy and lets the requestor's blocked application through.

| Field | Type | Notes |
| --- | --- | --- |
| `body` | object | **Required.** Full `PermitApplicationDto` body. Set `body.adminNotes` to the AI's reasoning — it lands in the Portal audit trail so a human can later reconstruct *why* an automated decision was made. |

#### `approval_request_reject`

`POST ApprovalRequest/ApprovalRequestUpdateForReject` — **deny**. Notifies the requestor with a reason.

| Field | Type | Notes |
| --- | --- | --- |
| `body` | object | **Required.** Set `body.rejectReason` (the requestor-visible message) and `body.responseReason` (the internal audit-trail note). |

#### `approval_request_ignore`

`POST ApprovalRequest/ApprovalRequestUpdateForIgnore` — **soft-dismiss**. Leaves the request in the queue for human review without notifying the requestor. Use this when the AI cannot confidently permit or reject.

| Field | Type | Notes |
| --- | --- | --- |
| `body` | object | **Required.** Forwarded as the JSON request body. |

## Detection & Response

Example response action that enriches a ThreatLocker approval-request event delivered by the [adapter](../../../2-sensors-deployment/adapters/types/threatlocker.md) by calling `application_get_matching` on the file's SHA-256:

```yaml
- action: extension request
  extension action: application_get_matching
  extension name: ext-threatlocker
  extension request:
    body:
      sha256: '{{ .event/hash }}'
      osType: 1
      approvalRequestId: '{{ .event/approvalRequestId }}'
```

> **Wrap literal strings in `{{ "..." }}`.**
> Values under `extension request` are evaluated as templates. A bare string without `{{ }}` is interpreted as a [gjson](https://github.com/tidwall/gjson) path against the event and, if it doesn't resolve, the key is silently dropped from the payload.

`extension request` actions are fire-and-forget — the rule engine does not surface the response back into the rule's evaluation context, so the enrichment result is not available to a subsequent action in the same rule. Workflows that chain (enrich → decide → write back) belong in a [Playbook](../limacharlie/playbook.md) or an AI agent, which can hold the intermediate results between calls.

## Authentication and tenancy

- The Portal API token is sent **verbatim** in the `Authorization` header — there is no `Bearer` prefix. Do not paste the token with a prefix; the API will reject it.
- The token is scoped to the instance that minted it. `403 TOKEN_REVOKED` means either the token was revoked **or** the wrong `instance_letter` was configured. Verify the instance letter first.
- For **MSPs**, a single parent-tenant token can be used to drive multiple child organizations by setting `managed_organization_id` to the child organization's UUID. The header `ManagedOrganizationId` is then attached to every request and the Portal scopes the response accordingly — one extension subscription per parent tenant, not per child.

## Notes

- The extension caches the underlying HTTP client per `(org, instance_letter, token, managed_organization_id)`. Rotating the secret in Secrets Manager evicts the cached client on the next surfaced `403 TOKEN_REVOKED`.
- No request or response transformation is performed — what ThreatLocker returns is what the caller sees. New Portal fields don't require a code change.
- Read actions are safe to retry. Write actions (`approval_request_permit` / `_reject` / `_ignore`) are not idempotent on the Portal side — re-firing them on the same `approvalRequestId` after the first success will surface a Portal error.
