# Designing Access for Multi-Org Deployments

This guide is written for administrators who operate more than a single organization — typically MSSPs, MDRs, or enterprises with multiple business units — and who need to give access to two distinct populations:

- **Internal staff** (analysts, engineers, managers) who need access across *many* organizations.
- **End customers** (or business-unit owners) who should only see their *own* organization.

The mechanics of granting and verifying access are documented in [User Access](user-access.md). This page focuses on the architectural decisions that happen *before* you start clicking "Add user" — so that the access model stays safe and manageable as you grow from one customer to fifty.

## Building blocks

Three LimaCharlie primitives combine to form every access model:

| Primitive | Scope | Typical use |
| --- | --- | --- |
| **Organization** | Single tenant (isolated data, sensors, billing) | One per customer / business unit |
| **Direct user** | One user ↔ one organization | A user who should see only that single org (e.g. an end-customer contact) |
| **Organization Group** | Set of orgs × set of users × set of permissions | A job-function bundle: everyone in the group gets the same permissions on every org in the group |

Supporting primitives that reinforce the model:

- **Predefined roles** (`Owner`, `Administrator`, `Operator`, `Viewer`, `Basic`) — apply a whole permission preset in one step. See [Reference: Permissions](../../8-reference/permissions.md).
- **Organization API keys** — machine access, scoped to a specific set of permissions on a specific org. See [API Keys](api-keys.md).
- **SSO / Strict SSO** — force users on your domain to authenticate via your IdP only. See [SSO](sso.md).
- **Group owners vs. group members** — owners manage a group (add users, add orgs, change permissions) but the group's permissions do **not** apply to them. Members receive the permissions but cannot modify the group.

## Recommended architecture for an MSSP

The pattern below scales from two customers to several hundred without restructuring. Use it as the starting point and adapt as needed.

```mermaid
flowchart LR
    subgraph Staff [MSSP Staff Groups by job function]
        GE[Engineers group<br/>Administrator-equivalent]
        GA2[L2 Analysts group<br/>Administrator-equivalent]
        GA1[L1 Analysts group<br/>Operator-equivalent]
        GRO[Read-only group<br/>Viewer-equivalent]
    end

    subgraph Customers [Customer Organizations one per tenant]
        C1[Customer A org]
        C2[Customer B org]
        C3[Customer C org]
    end

    subgraph EndUsers [End-customer users added directly]
        U1[Alice - Customer A contact]
        U2[Bob - Customer B contact]
    end

    GE --- C1
    GE --- C2
    GE --- C3
    GA2 --- C1
    GA2 --- C2
    GA2 --- C3
    GA1 --- C1
    GA1 --- C2
    GA1 --- C3
    GRO --- C1
    GRO --- C2
    GRO --- C3

    U1 -.-> C1
    U2 -.-> C2
```

Three rules keep this architecture coherent:

1. **One organization per customer tenant.** Data, sensors, billing and configuration are self-contained in an organization. A customer *is* an organization. Do not mix customers inside a single org.
2. **Your staff get access through Organization Groups, by job function.** Never add internal staff directly to a customer org — that does not scale and silently drifts over time.
3. **Your customers get access directly on their own organization.** Never add an end-customer user to a group that spans multiple customer orgs — groups are additive, and a group that touches other customers would leak access to data the user must not see.

### Optional: an internal "management" organization

Many MSSPs also create a dedicated organization used only internally (templates, IaC source of truth, demo / training work). It is not a customer tenant. You can include it in a staff group, but do **not** enrol customer users in it.

## Granting access to your internal staff

Design the groups around job functions, not around customers. A typical starting set — the right-most column is the permission level you want each group to grant (matching the predefined roles you use for direct users makes the overall model easier to reason about):

| Group | Members | Permission level |
| --- | --- | --- |
| `engineers` | Detection engineers, platform admins | Administrator-equivalent |
| `analysts-l2` | Senior analysts, IR leads | Administrator-equivalent |
| `analysts-l1` | Front-line SOC | Operator-equivalent |
| `read-only` | Leadership, auditors | Viewer-equivalent |

Workflow once the groups exist:

1. **Create each group once.** `limacharlie group create --name <name>` (or via the **Groups** page).
2. **Add every customer org** to each relevant group. `limacharlie group org-add --gid <id> --oid <customer_oid>`.
3. **Set the group's permissions.** In the **Groups** page of the web app, select the permissions that match the intended permission level. Via the CLI, pass the explicit permission list: `limacharlie group permissions-set --gid <id> --permissions 'sensor.list,sensor.get,dr.list,...'`. Note that the group CLI takes a raw permission list — unlike `limacharlie user permissions set-role` for direct users, there is no single role-preset flag. Keep the list aligned with the direct-user role of the same name so effective permissions stay easy to reason about.
4. **Add a user to exactly the group(s) matching their job.** `limacharlie group member-add --gid <id> --email <address>`.
5. **When you onboard a new customer**, simply add the new org to each staff group (step 2). Every staff member instantly gets the right level of access on the new tenant, with no per-user work.

### Separating production from non-production

A very common refinement is to split a sensitive group (e.g. `engineers`) into two:

- `engineers-nonprod` — includes sandbox / demo / pre-prod customer orgs.
- `engineers-prod` — includes live customer orgs, restricted to senior staff who have signed off on your production change-control process.

Membership in `engineers-prod` becomes the formal gate to production access, and is easy to audit (`limacharlie group get --id <engineers-prod>` lists members, orgs, and permissions in one response).

## Granting access to your end customers

End customers must stay confined to their own organization. The safe pattern is always the same:

1. **Add the customer's email directly to their own org only.** `limacharlie --oid <customer_oid> user invite --email <address>`, or the **Users** page of that org.
2. **Assign a predefined role** that matches what you agreed to in your service agreement. `limacharlie --oid <customer_oid> user permissions set-role --email <address> --role Viewer` (or `Operator`, `Administrator`, etc.).
3. **Do not add customer users to any staff Organization Group.** A group that contains other customers' orgs would silently grant the user access to data belonging to those other customers.

!!! warning "Groups are additive only"
    Permissions granted through a group are **added** to the user's direct permissions on each included organization. A group cannot be used to *reduce* or *restrict* what a user can see. Treat "membership in a group" as "give every permission in that group, on every org in that group."

If you want to give a customer access to *multiple* of their own organizations (for example, a customer with several business units), you have two clean options:

- **Direct users on each org.** Simple, auditable, fine if the customer only has a handful of orgs.
- **A customer-specific Organization Group** that contains *only* that customer's orgs and *only* that customer's users. Do not mix tenants inside a single group.

## Hardening

A few controls sharply reduce the risk of an access-control mistake:

- **Strict SSO Enforcement on your own domain.** Forces every user authenticating as `@yourcompany.com` to go through your identity provider. Offboarding in your IdP immediately locks the user out of LimaCharlie. See [Strict SSO Enforcement](sso.md#strict-sso-enforcement).
- **Organization API keys over user API keys.** An Organization API key is scoped to a single organization and to the minimum permissions needed by the integration. User API keys grant the same access as the user themselves across *every* organization they can reach — reserve them for interactive work only, never for production automation. See [User API Keys](api-keys.md#user-api-keys).
- **Separate group owners from members.** An engineering manager can be an *owner* of a staff group (to add/remove members) without being a member themselves — they gain the ability to manage access without automatically having access to customer data. This is a useful separation-of-duties control.
- **Review access on a cadence.** The companion section [Verifying and Reviewing Access](user-access.md#verifying-and-reviewing-access) shows how to enumerate every user, group, and effective permission on an organization, plus how to pull the audit trail of access changes.

## New-customer onboarding checklist

Once you have the architecture above in place, adding a new customer is a short, repeatable list:

1. **Create the customer's organization.** The creator automatically holds the `Owner` role on it.
2. **Grant `Owner` to a shared internal account as well,** so administrative access does not depend on the creator's personal account being available. `limacharlie --oid <customer_oid> user permissions set-role --email <shared-account> --role Owner`. A full billing/legal ownership transfer is a separate support request; see [Can I Transfer Ownership of an Organization?](../../8-reference/faq/account-management.md#can-i-transfer-ownership-of-an-organization).
3. **Add the new org to each staff Organization Group** that should cover it (e.g. `engineers-prod`, `analysts-l1`, `read-only`). Staff access is now complete — no per-user work.
4. **Invite the customer's designated contacts directly on the new org,** using a predefined role. Do not add them to any group.
5. **Configure the rest of the tenant** (installation keys, adapters, D&R rules, outputs) — often from Infrastructure-as-Code templates if you have them; see [Infrastructure Extension](../../5-integrations/extensions/limacharlie/infrastructure.md).
6. **Run the [verification checklist](user-access.md#suggested-validation-checklist-for-a-new-production-organization)** before declaring the tenant live.

## Anti-patterns to avoid

| Anti-pattern | Why it breaks | What to do instead |
| --- | --- | --- |
| Adding staff directly to each customer org | Does not scale, drifts, permissions diverge across orgs | Staff access only via Organization Groups, by job function |
| Putting customer users in a multi-tenant group | Groups are additive — the user now sees every other org in the group | Direct users on the customer's own org only |
| One huge "everyone" staff group with every permission | No separation of duties, no prod gate | Split groups by role (`Viewer`, `Operator`, `Administrator`) and by blast radius (`nonprod` vs `prod`) |
| Using a user API key for an integration | Scopes to every org the user can reach; breaks when the user leaves | Organization API key scoped to the minimum permissions on that single org |
| Hand-picking permissions for every user | Hard to audit, easy to drift | Use predefined roles (`set-role`) and refine only when a role genuinely does not fit |

---

## Related

- [User Access](user-access.md) — mechanics of adding users, groups, and verifying access.
- [Reference: Permissions](../../8-reference/permissions.md) — full permission catalogue and predefined roles.
- [API Keys](api-keys.md) — machine access, Organization vs. User API keys.
- [SSO](sso.md) — federated authentication and strict SSO enforcement.
- [Security Service Providers (MSSP, MSP, MDR)](../../1-getting-started/use-cases/mssp-msp-mdr.md) — broader MSSP platform use cases.
