# Single Sign-On

Single sign-on (SSO) is available at no extra cost for customers that leverage LimaCharlie's custom branded offering. If this applies to your Organization, and if you are interested in using the SSO, please submit a [Custom Branding / SSO Request](https://limacharlie.io/custom-branding).

If your organization does not currently have a custom branded site with LimaCharlie, you can learn about the requirements, costs & get started here.

## Strict SSO Enforcement

LimaCharlie offers the ability to implement strict SSO enforcement. This means that SSO can be configured as the only authentication option.

With this capability, you may say that any user with your email domain @example.com must authenticate via Google. This way you can disable the login + password, GitHub, and Microsoft login options for users with your email domain (@example.com) - regardless if they are logging in via your custom branded site, or via app.limacharlie.io

## How It Works

LimaCharlie's single sign-on functionality lets companies add their own SSO option that goes through their authentication server instead of through Google or something else. Identity Platform acts as the coordinator here. After configuring new Providers in Identity Platform, the app only needs to specify a provider ID, and then Identity Platform will handle talking to the company's auth server.

## User Experience

The high-level user experience is as follows:

- For organizations that choose to use SSO, the SSO will be enforced. Users going to custom branded versions of the LimaCharlie site will be presented with only the option to login through SSO, if their domain has the SSO configuration.

![sso 1](../../assets/images/sso-1.png)

- The same user going to the non-branded site would still be presented with all other authentication options. However, a user would only be able to use the authentification option approved for their domain.

![sso 2](../../assets/images/sso-2.png)

In LimaCharlie, an Organization represents a tenant within the Agentic SecOps Workspace, providing a self-contained environment to manage security data, configurations, and assets independently. Each Organization has its own sensors, detection rules, data sources, and outputs, offering complete control over security operations. This structure enables flexible, multi-tenant setups, ideal for managed security providers or enterprises managing multiple departments or clients.

## Related Articles

- [User Access](user-access.md)

## What's Next

- [Reference: Permissions](../../8-reference/permissions.md)
