# NIMS

Notion Incident Management System (NIMS) helps SOC/IR teams streamline their incident collaboration. While not a replacement for advanced SIEM or SOAR case management systems, it offers a practical alternative for teams that don't have access to these tools.

The Notion template uses interconnected relational databases to enable effective incident tracking and case management.

The LimaCharlie NIMS extension allows you to send detections from LimaCharlie to NIMS via the Notion API.

Once you subscribe an org to the extension, it creates a D&R rule that sends all detections from your org to your NIMS alert database. Because Notion databases do have a limit on the number of records, the extension also has the ability to purge old alerts that are 1) not associated with any incidents, and 2) older than the specified number of days. A D&R rule is also created to perform this cleanup automatically (or not) based on your configuration.

[More information about NIMS, including the template and corresponding docs](https://nims-template.notion.site/), is available on the project's Notion page.

## Configuration

In order to use this extension, you will need 3 pieces of data:

- Notion authentication token
- NIMS Alert database ID
- NIMS Asset database ID

### Find your database IDs

1. Navigate to the Alert database within NIMS under `Databases`
2. Right click on the database and click `Copy link`[![NIMS database link button screenshot](https://github.com/shortstack/nims-webhook/raw/main/screenshots/link.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/link.png)
3. Locate the database ID in the URL

   - The database ID is the long string of letters and numbers in the URL after the last `/` and before the `?` or `#` if present
   - Example:

     - Link: `https://www.notion.so/184cdc5a1ef3710badc2d2b1271aeb81?v=174cdc3a1ef181719981000cab12bf54&pvs=4`
     - ID: `184cdc5a1ef3710badc2d2b1271aeb81`
4. Copy the ID
5. Repeat the above for the Asset database

### Generate an auth token

This will walk you through creating a Notion integration, getting the auth token, and adding the integration to the proper NIMS databases.

While completing the following steps, be sure to add the connection to all 3 databases—Alert, Asset, and Incident. Incident is only necessary in order to perform the alerts cleanup to see whether or not the alert is tied to an incident.

1. Go to `Manage connections` in Notion [![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/connection.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/connection.png)
2. Click `Develop or manage integrations`[![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/manage.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/manage.png)
3. Click `New integration`[![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/new.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/new.png)
4. Configure the new integration

   - Give it a name, ex: `nims_template`
   - Choose the workspace
   - Type: `Internal`
   - Click `Save` [![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/integration.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/integration.png)
5. Click `Configure integration settings` [![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/configure.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/configure.png)
6. Copy the `Internal Integration Secret`-- this is your auth token

   - Click `Save` [![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/token.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/token.png)
7. Navigate to your `Alert Database`

   - Click the 3-dot menu and find `Connections`
   - Click on your newly created integration [![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/alerts.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/alerts.png)
8. Click `Confirm`
   [![connection](https://github.com/shortstack/nims-webhook/raw/main/screenshots/confirm.png)](https://github.com/shortstack/nims-webhook/blob/main/screenshots/confirm.png)
9. Repeat steps 7 and 8 for the `Asset Database` and the `Incident Database`

## Example D&R rule

**Detect:**

```yaml
op: exists
path: cat
target: detection
```

**Respond:**

```yaml
- action: extension request
  extension action: push_detections
  extension name: ext-nims
  extension request:
    cat: '{{ .cat }}'
    detection: '{{json .detect }}'
    event_time: '{{ .routing.event_time }}'
    hostname: '{{ .routing.hostname }}'
    int_ip: '{{ .routing.int_ip }}'
    link: '{{ .link }}'
    metadata: '{{json .detect_mtd }}'
```

## Related

- [OTX](otx.md)
