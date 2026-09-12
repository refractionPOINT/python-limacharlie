# Endpoint Agent Versioning and Upgrades

LimaCharlie frequently releases new versions of the endpoint agent (typically every few weeks), giving you full control over which version runs in your Organization. Sensors are not updated by default, allowing you to manage versioning and deployment as needed.

## Endpoint Agent Components

The LimaCharlie endpoint agent consists of two main components, each versioned independently:

1. **On-disk agent**: Implements core identity, cryptography, and transport mechanisms. This component rarely requires updates and typically remains static.
2. **Over-the-air core**: The main component that receives frequent updates and delivers advanced functionality. It can be easily updated via the LimaCharlie cloud.

When updates occur, they impact the over-the-air component, as it's the easiest to modify, with the update size generally being around 3-5 MB.

## Version Labels

LimaCharlie provides three version labels to simplify version management:

1. **Latest**: The most recent release with new fixes and features.
2. **Stable**: A less frequently updated version, ideal for maintaining slower update cadences.
3. **Experimental**: The beta version of the next "Latest" release.

You can upgrade to any of these version labels for your organization by using the LimaCharlie web interface or the [API](https://api.limacharlie.io/static/swagger/#/Modules/upgradeOrg).

### Upgrading to Specific Versions

In addition to using version labels, you can upgrade your organization to a specific sensor version using semantic version strings (e.g., `4.33.20`). This is useful when:

- You need to pin your organization to a specific tested version
- You want to maintain version consistency across multiple organizations
- You need to rollback to a previous version for compatibility reasons
- You're testing a specific version before broader deployment

To upgrade or manage sensors using the API:

```bash
# Upgrade to a specific version
curl -X POST "https://api.limacharlie.io/v1/modules/{oid}?specific_version=4.33.20" \
  -H "Authorization: Bearer {api_key}" \
  -H "Content-Type: application/json"

# Upgrade to latest version label
curl -X POST "https://api.limacharlie.io/v1/modules/{oid}?specific_version=latest" \
  -H "Authorization: Bearer {api_key}" \
  -H "Content-Type: application/json"

# Downgrade to previous version (rollback)
curl -X POST "https://api.limacharlie.io/v1/modules/{oid}?is_fallback=true" \
  -H "Authorization: Bearer {api_key}" \
  -H "Content-Type: application/json"

# Move sensors to dormant mode
curl -X POST "https://api.limacharlie.io/v1/modules/{oid}?is_sleep=true" \
  -H "Authorization: Bearer {api_key}" \
  -H "Content-Type: application/json"
```

**Note**: Specific version strings follow semantic versioning format (MAJOR.MINOR.PATCH) and must correspond to an available LimaCharlie sensor release. If you specify an invalid or unavailable version, the API will return an error.

## Managing Versioning for Sensors

To manage the versioning of sensors, you can leverage LimaCharlie's **System** Tags:

- `lc:latest`: Tags the Sensor to receive the most recent version.

  - This tag is primarily intended for testing `latest` sensor version against a small set of representative sensors before org-wide upgrades to `latest`.
- `lc:stable`: Tags the sensor to receive a stable version.
- `lc:experimental`: Tags the sensor to receive the experimental version.

These tags can be applied to individual sensors to alter version behavior, and updates take effect within 10 minutes. This method also enables staging deployments to test updates on a small group of sensors before organization-wide rollouts.

## Updating Endpoint Agents

### Best Practices

When deploying new sensor versions, follow a controlled testing approach by first applying the `lc:latest` tag to a small subset of representative systems across different operating systems and workloads. Monitor these test systems for a period of time, evaluating stability, performance, and telemetry quality. If testing is successful, update the organization-level sensor version and remove the `lc:latest` tag from test systems, while maintaining a rollback plan and monitoring system health during the deployment. Note that the `lc:latest` sensor tag should primarily be used for upgrade testing purposes, as it automatically updates sensors to new versions as they are released.

### Manual Update

You can manually trigger an update for all endpoint agents in your organization by simply clicking a button in the web interface. This action updates the over-the-air component of the sensors within 20 minutes, with no need to re-download installers, as the installer remains unchanged.

### Auto-Update

To automate updates, apply the `lc:stable` tag to your sensors. This will ensure that sensors automatically update to the latest stable version upon release.

### Staged Deployment

For testing new versions, tag specific sensors with `lc:latest` to run the latest version without affecting the rest of your organization. This allows you to test new releases on selected hosts before proceeding with a full rollout.
