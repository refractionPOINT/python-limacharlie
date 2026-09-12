# Atlassian

[Atlassian](https://www.atlassian.com/) makes a suite of products that help foster enterprise work management, IT service management, and Agile development. Atlassian's products include:

- Bitbucket
- Confluence
- Jira Work Management (this includes a suite of products, include Jira Software, Service Management, and Product Discovery)
- Opsgenie
- Trello

Atlassian has [extensive documentation](https://confluence.atlassian.com/alldoc/atlassian-documentation-32243719.html) for both their Cloud and Data Center/Server editions.

Currently, LimaCharlie supports ingestion of Jira events. Jira events can be ingested in LimaCharlie via a `json` webhook Adapter.

## Adapter Deployment

Jira events are ingested via a cloud-to-cloud webhook Adapter, configured to receive JSON events. In the creation of the Adapter, we map fields directly to the expected Atlassian events. The steps of creating this Adapter and enabling the input include:

1. Creating the webhook Adapter via the LimaCharlie CLI.
2. Discovering the URL created for the webhook Adapter.
3. Providing the completed URL to Jira for webhook events.

### 1. Creating the LimaCharlie Webhook Adapter

These steps are adapted from the [generic webhook adapter creation guide](../tutorials/webhook-adapter.md).

Creating a Webhook Adapter requires a set of parameters, including organization ID, Installation Key, platform, and mapping details. The following configuration has been provided to configure a webhook Adapter for ingesting Jira events:

```json
{
    "sensor_type": "webhook",
    "webhook": {
       "secret": "atlassian-jira-secret",
        "client_options": {
            "hostname": "atlassian-jira",
            "identity": {
                "oid": "<your_oid>",
                "installation_key": "<your_installation_key>"
            },
            "platform": "json",
            "sensor_seed_key": "atlassian-jira-super-secret-key",
            "mapping" : {
                "event_type_path" : "webhookEvent",
                "event_time_path" : "timestamp"
            }
        }
    }
}
```

The mapping above is based on the expected webhook event from Jira. Note that in the mapping above, we make the following change:

- `event_type_path` is mapped to the `webhookEvent` field
- `event_time_path` is mapped to the `timestamp` field

### 2. Building the Webhook URL

After creating the webhook, you'll need to retrieve the webhook URL from the [Get Org URLs](https://api.limacharlie.io/static/swagger/get-org-urls) API call. You'll need the following information to complete the Webhook URL:

- Organization ID
- Webhook name (from the config)
- Secret (from the config)

Let's assume the returned domain looks like `9157798c50af372c.hook.limacharlie.io`, the format of the URL would be:

`https://9157798c50af372c.hook.limacharlie.io/OID/HOOKNAME/SECRET`

Note that the `secret` value can be provided in the webhook URL or as an HTTP header named `lc-secret`.

### 3. Providing the URL to Jira for Webhook Events

Within the Atlassian Admin window, navigate to **Jira Administration** > **Jira settings** > **Advanced** > **WebHooks**. Select **+ Create a WebHook**.

![image.png](../../../assets/images/image(178).png)

- Choose an appropriate name to differentiate that this is a LimaCharlie webhook
- Provide the webhook URL (see step 2 above)
- (optional) Provide a description
- (optional) Provide a JQL query to select certain issues that will trigger Webhooks. The default selection is *All issues*.

Within the WebHook creation dialog, you can also select the granularity of events to send via the WebHook. High-level event categories include:

- Issues
  - Issue events
  - Worklog
  - Comment(s)
  - Entity Properties
  - Attachment
  - Issue Link
  - Filter
- User-related
- Jira configuration
- Project-related
- Jira Software-related

By default, issues will be sent as JSON, which is natively accepted by LimaCharlie. Save your WebHook configuration, and perform an action that you know will trigger the event.

If configured properly, you should see your Jira events in LimaCharlie. Here's an example event:

```json
{
  "event": {
    "issue": {
      "fields": {
        "aggregateprogress": {
          "progress": 0,
          "total": 0
        },
        "aggregatetimeestimate": null,
        "aggregatetimeoriginalestimate": null,
        "aggregatetimespent": null,
        "assignee": null,
        "attachment": [],
        "comment": {
          "comments": [],
          "maxResults": 0,
          "self": "https://###.atlassian.net...",
          "startAt": 0,
          "total": 0
        },
        "components": [],
        "created": "2023-12-02T11:16:02.927-0600",
        "creator": {
          "accountId": "...",
          "accountType": "atlassian",
          "active": true,
          "avatarUrls": {
            "16x16": "...",
            "24x24": "...",
            "32x32": "...",
            "48x48": "..."
          },
          "displayName": "Matt Bromiley",
          "self": "https://###.atlassian.net...",
          "timeZone": "America/Chicago"
        },
        "customfield_10001": null,
        "customfield_10002": null,
        "customfield_10003": null,
        "customfield_10004": null,
        "customfield_10005": null,
        "customfield_10006": null,
        "customfield_10007": null,
        "customfield_10008": null,
        "customfield_10009": null,
        "customfield_10010": null,
        "customfield_10014": null,
        "customfield_10015": null,
        "customfield_10016": null,
        "customfield_10017": null,
        "customfield_10018": {
          "hasEpicLinkFieldDependency": false,
          "nonEditableReason": {
            "message": "The Parent Link is only available to Jira Premium users.",
            "reason": "PLUGIN_LICENSE_ERROR"
          },
          "showField": false
        },
        "customfield_10019": "0|hzzzzz:",
        "customfield_10020": null,
        "customfield_10021": null,
        "customfield_10022": null,
        "customfield_10023": null,
        "customfield_10024": null,
        "customfield_10025": null,
        "customfield_10026": null,
        "customfield_10027": null,
        "customfield_10028": null,
        "customfield_10029": null,
        "customfield_10030": null,
        "description": null,
        "duedate": null,
        "environment": null,
        "fixVersions": [],
        "issuelinks": [],
        "issuerestriction": {
          "issuerestrictions": {},
          "shouldDisplay": true
        },
        "issuetype": {
          "avatarId": 10318,
          "description": "Tasks track small, distinct pieces of work.",
          "entityId": "e44d856a-3c4b-4a5e-bc67-c3c93227fe18",
          "hierarchyLevel": 0,
          "iconUrl": "https://###.atlassian.net/rest/api/...",
          "id": "10001",
          "name": "Task",
          "self": "https://###.atlassian.net/rest/api/...",
          "subtask": false
        },
        "labels": [],
        "lastViewed": "2023-12-02T17:18:42.192-0600",
        "priority": {
          "iconUrl": "https://###.atlassian.net/rest/api/...",
          "id": "3",
          "name": "Medium",
          "self": "https://###.atlassian.net/rest/api/..."
        },
        "progress": {
          "progress": 0,
          "total": 0
        },
        "project": {
          "avatarUrls": {
            "16x16": "...",
            "24x24": "...",
            "32x32": "...",
            "48x48": "..."
          },
          "id": "10000",
          "key": "KAN",
          "name": "My Kanban Project",
          "projectTypeKey": "software",
          "self": "https://###.atlassian.net/rest/api/...",
          "simplified": true
        },
        "reporter": {
          "accountId": "...",
          "accountType": "atlassian",
          "active": true,
          "avatarUrls": {
            "16x16": "...",
            "24x24": "...",
            "32x32": "...",
            "48x48": "..."
          },
          "displayName": "Matt Bromiley",
          "self": "...",
          "timeZone": "America/Chicago"
        },
        "resolution": null,
        "resolutiondate": null,
        "security": null,
        "status": {
          "description": "",
          "iconUrl": "https://###.atlassian.net/",
          "id": "10000",
          "name": "To Do",
          "self": "https://###.atlassian.net/rest/api/...",
          "statusCategory": {
            "colorName": "blue-gray",
            "id": 2,
            "key": "new",
            "name": "To Do",
            "self": "https://###.atlassian.net/rest/api/..."
          }
        },
        "statuscategorychangedate": "2023-12-02T11:16:03.211-0600",
        "subtasks": [],
        "summary": "sample issue",
        "timeestimate": null,
        "timeoriginalestimate": null,
        "timespent": null,
        "timetracking": {},
        "updated": "2023-12-02T11:16:03.129-0600",
        "versions": [],
        "votes": {
          "hasVoted": false,
          "self": "https://###.atlassian.net/rest/api/...",
          "votes": 0
        },
        "watches": {
          "isWatching": true,
          "self": "https://###.atlassian.net/rest/api/...",
          "watchCount": 1
        },
        "worklog": {
          "maxResults": 20,
          "startAt": 0,
          "total": 0,
          "worklogs": []
        },
        "workratio": -1
      },
      "id": "10012",
      "key": "KAN-13",
      "self": "https://###.atlassian.net/rest/api/..."
    },
    "timestamp": 1701559124723,
    "user": {
      "accountId": "...",
      "accountType": "atlassian",
      "active": true,
      "avatarUrls": {
        "16x16": "...",
        "24x24": "...",
        "32x32": "...",
        "48x48": "..."
      },
      "displayName": "Matt Bromiley",
      "self": "...",
      "timeZone": "America/Chicago"
    },
    "webhookEvent": "jira:issue_deleted"
  },
  "routing": {...},
  "ts": "2023-12-02 23:18:44"
}
```

Note that the Jira "webhookEvent" becomes the event type, also represented in the LimaCharlie Adapter timeline.
