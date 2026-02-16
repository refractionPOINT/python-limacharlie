"""Organization SDK class for LimaCharlie v2.

Wraps all org-scoped API operations. This is the main entry point
for interacting with a LimaCharlie organization.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Generator
from typing import Any, TYPE_CHECKING
from urllib.parse import quote as urlescape

if TYPE_CHECKING:
    from ..client import Client


class Organization:
    """Represents a LimaCharlie organization.

    Provides access to all organization-level operations including
    sensors, rules, hives, outputs, users, and more.

    Usage:
        client = Client(oid="...", api_key="...")
        org = Organization(client)
        info = org.get_info()
    """

    def __init__(self, client: Client) -> None:
        """Initialize with an authenticated Client.

        Args:
            client: An authenticated Client instance.
        """
        self._client = client

    @property
    def oid(self) -> str:
        return self._client.oid

    @property
    def client(self) -> Client:
        return self._client

    def get_info(self) -> dict[str, Any]:
        """Get organization details (sensor count, version, quotas, name).

        Returns:
            dict: Organization information.
        """
        return self._client.request("GET", f"orgs/{self.oid}")

    def get_urls(self) -> dict[str, Any]:
        """Get service URLs for the organization.

        Returns:
            dict: URL mappings for various services.
        """
        data = self._client.request("GET", f"orgs/{self.oid}/url", is_no_auth=True)
        return data.get("url", data)

    def get_config(self, config_name: str) -> str | None:
        """Get an organization configuration value.

        Args:
            config_name: Configuration key name.

        Returns:
            str: Configuration value.
        """
        data = self._client.request("GET", f"configs/{self.oid}/{config_name}")
        return data.get("value", None)

    def set_config(self, config_name: str, value: str) -> dict[str, Any]:
        """Set an organization configuration value.

        Args:
            config_name: Configuration key name.
            value: Configuration value.

        Returns:
            dict: API response.
        """
        return self._client.request("POST", f"configs/{self.oid}/{config_name}", params={"value": value})

    def get_stats(self) -> dict[str, Any]:
        """Get usage statistics for the organization.

        Returns:
            dict: Usage statistics.
        """
        return self._client.request("GET", f"usage/{self.oid}")

    def get_errors(self) -> dict[str, Any]:
        """Get organization errors.

        Returns:
            dict: Error mappings keyed by component.
        """
        resp = self._client.request("GET", f"errors/{self.oid}")
        return resp.get("errors", resp)

    def dismiss_error(self, component: str) -> dict[str, Any]:
        """Dismiss an organization error.

        Args:
            component: Error component name.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"errors/{self.oid}/{urlescape(component, safe='')}")

    def get_mitre_report(self) -> dict[str, Any]:
        """Get MITRE ATT&CK coverage report.

        Returns:
            dict: MITRE report data.
        """
        return self._client.request("GET", f"mitre/{self.oid}")

    def get_schemas(self, platform: str | None = None) -> dict[str, Any]:
        """Get event schemas/ontology.

        Args:
            platform: Optional platform filter.

        Returns:
            dict: Schema definitions.
        """
        qp = {}
        if platform:
            qp["platform"] = platform
        return self._client.request("GET", f"orgs/{self.oid}/schema", query_params=qp or None)

    def get_schema(self, name: str) -> dict[str, Any]:
        """Get a specific event schema.

        Args:
            name: Schema/event type name.

        Returns:
            dict: Schema definition.
        """
        return self._client.request("GET", f"orgs/{self.oid}/schema/{urlescape(name, safe='')}")

    def get_runtime_metadata(self, entity_type: str | None = None, entity_name: str | None = None) -> dict[str, Any]:
        """Get runtime metadata.

        Args:
            entity_type: Optional entity type filter.
            entity_name: Optional entity name filter.

        Returns:
            dict: Runtime metadata.
        """
        qp = {}
        if entity_type:
            qp["entity_type"] = entity_type
        if entity_name:
            qp["entity_name"] = entity_name
        return self._client.request("GET", f"runtime_mtd/{self.oid}", query_params=qp or None)

    def set_quota(self, quota: int) -> dict[str, Any]:
        """Set the sensor quota for the organization.

        Args:
            quota: Number of sensors allowed.

        Returns:
            dict: API response.
        """
        return self._client.request("POST", f"orgs/{self.oid}/quota", params={"quota": quota})

    def rename(self, new_name: str) -> dict[str, Any]:
        """Rename the organization.

        Args:
            new_name: New organization name.

        Returns:
            dict: API response.
        """
        return self._client.request("POST", f"orgs/{self.oid}/name", query_params={"name": new_name})

    def get_ontology(self) -> dict[str, Any]:
        """Get the LimaCharlie ontology (event type definitions).

        Returns:
            dict: Ontology data.
        """
        return self._client.request("GET", "ontology")

    def get_event_types(self) -> dict[str, Any]:
        """List available event types.

        Returns:
            dict: Event type mappings.
        """
        return self._client.request("GET", "events")

    def who_am_i(self) -> dict[str, Any]:
        """Query the API to see current identity and permissions.

        Returns:
            dict: Identity and permission information.
        """
        return self._client.request("GET", "who")

    def test_auth(self, permissions: list[str] | None = None) -> bool:
        """Test authentication and optionally verify specific permissions.

        Args:
            permissions: Optional list of permission strings to verify.

        Returns:
            bool: True if authentication (and permissions) are valid.
        """
        try:
            self._client.refresh_jwt()
        except Exception:
            return False

        if not permissions:
            return True

        perms = self.who_am_i()
        if "user_perms" in perms:
            effective = perms["user_perms"].get(self.oid, [])
        else:
            if self.oid in perms.get("orgs", []):
                effective = perms.get("perms", [])
            else:
                effective = []

        return all(p in effective for p in permissions)

    # --- Static/class methods for org management ---

    def list_accessible_orgs(self, offset: int | None = None, limit: int | None = None, filter_text: str | None = None) -> dict[str, Any]:
        """List organizations accessible to the current user.

        Args:
            offset: Pagination offset.
            limit: Maximum number of results.
            filter_text: Case-insensitive substring filter.

        Returns:
            dict: Organization list with 'orgs' and 'names' keys.
        """
        qp = {}
        if offset is not None:
            qp["offset"] = str(offset)
        if limit is not None:
            qp["limit"] = str(limit)
        if filter_text:
            qp["filter"] = filter_text

        # Use minimal JWT to avoid header size issues
        original_jwt = self._client._jwt
        try:
            self._client.refresh_jwt(oid_override="-")
            resp = self._client.request("GET", "user/orgs", query_params=qp or None)
        finally:
            self._client._jwt = original_jwt

        orgs_list = resp.get("orgs", [])
        oids = [org.get("oid") for org in orgs_list if org.get("oid")]
        names = {org.get("oid"): org.get("name") for org in orgs_list if org.get("oid")}
        return {"orgs": oids, "names": names}

    @staticmethod
    def create_org(client: Client, name: str, location: str | None = None, template: str | None = None) -> dict[str, Any]:
        """Create a new organization.

        Args:
            client: Authenticated Client instance.
            name: Organization name.
            location: Data center location.
            template: Optional template name.

        Returns:
            dict: New organization details.
        """
        params = {"name": name}
        if location:
            params["loc"] = location
        if template:
            params["template"] = template
        return client.request("POST", "orgs/new", params=params)

    @staticmethod
    def check_name(client: Client, name: str) -> dict[str, Any]:
        """Check if an organization name is available.

        Args:
            client: Authenticated Client instance.
            name: Name to check.

        Returns:
            dict: Availability information.
        """
        return client.request("GET", "orgs/new", query_params={"name": name})

    def delete_org(self, confirm_token: str | None = None) -> dict[str, Any]:
        """Delete the organization (two-step process).

        Without confirm_token: returns a confirmation token.
        With confirm_token: performs the deletion.

        Args:
            confirm_token: Confirmation token from first call.

        Returns:
            dict: Confirmation token or deletion result.
        """
        if confirm_token is None:
            return self._client.request("GET", f"orgs/{self.oid}/delete")
        return self._client.request("DELETE", f"orgs/{self.oid}/delete", params={"confirmation": confirm_token})

    # --- Users ---

    def get_users(self) -> list[str]:
        """List organization users.

        Returns:
            list: User email strings.
        """
        resp = self._client.request("GET", f"orgs/{self.oid}/users")
        return resp.get("users", resp)

    def add_user(self, email: str) -> dict[str, Any]:
        """Invite a user to the organization.

        Args:
            email: User email address.

        Returns:
            dict: API response.
        """
        return self._client.request("POST", f"orgs/{self.oid}/users", params={"email": email})

    def remove_user(self, email: str) -> dict[str, Any]:
        """Remove a user from the organization.

        Args:
            email: User email address.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"orgs/{self.oid}/users", params={"email": email})

    def get_user_permissions(self) -> dict[str, Any]:
        """List user permissions.

        Returns:
            dict: User permission mappings.
        """
        resp = self._client.request("GET", f"orgs/{self.oid}/users/permissions")
        return resp.get("user_permissions", resp)

    def add_user_permission(self, email: str, permission: str) -> dict[str, Any]:
        """Grant a permission to a user.

        Args:
            email: User email address.
            permission: Permission string (e.g., 'dr.set').

        Returns:
            dict: API response.
        """
        return self._client.request("POST", f"orgs/{self.oid}/users/permissions",
                                    params={"email": email, "perm": permission})

    def remove_user_permission(self, email: str, permission: str) -> dict[str, Any]:
        """Revoke a permission from a user.

        Args:
            email: User email address.
            permission: Permission string.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"orgs/{self.oid}/users/permissions",
                                    params={"email": email, "perm": permission})

    def set_user_role(self, email: str, role: str) -> dict[str, Any]:
        """Set a predefined role for a user, replacing all their permissions.

        Valid roles: Owner, Administrator, Operator, Viewer, Basic.

        Args:
            email: User email address.
            role: Role name (Owner, Administrator, Operator, Viewer, Basic).

        Returns:
            dict: API response with success, role, and permissions list.
        """
        return self._client.request("PUT", f"orgs/{self.oid}/users/role",
                                    raw_body=json.dumps({"email": email, "role": role}).encode(),
                                    content_type="application/json")

    # --- API Keys ---

    def get_api_keys(self) -> dict[str, Any]:
        """List API keys.

        Returns:
            dict: API key list keyed by key hash.
        """
        resp = self._client.request("GET", f"orgs/{self.oid}/keys")
        return resp.get("api_keys", resp)

    def add_api_key(self, name: str, permissions: list[str], ip_range: str | None = None) -> dict[str, Any]:
        """Create a new API key.

        Args:
            name: Key name.
            permissions: List of permission strings.
            ip_range: Optional CIDR IP range restriction.

        Returns:
            dict: New key details (includes the key value).
        """
        params = {"key_name": name, "perms": ",".join(permissions)}
        if ip_range:
            params["allowed_ip_range"] = ip_range
        return self._client.request("POST", f"orgs/{self.oid}/keys", params=params)

    def remove_api_key(self, key_hash: str) -> dict[str, Any]:
        """Delete an API key.

        Args:
            key_hash: Key hash identifier.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"orgs/{self.oid}/keys", params={"key_hash": key_hash})

    # --- Installation Keys ---

    def get_installation_keys(self) -> dict[str, Any]:
        """List installation keys.

        Returns:
            dict: Installation key list keyed by iid.
        """
        resp = self._client.request("GET", f"installationkeys/{self.oid}")
        return resp.get(self.oid, resp)

    def get_installation_key(self, iid: str) -> dict[str, Any]:
        """Get a specific installation key.

        Args:
            iid: Installation key ID.

        Returns:
            dict: Key details.
        """
        return self._client.request("GET", f"installationkeys/{self.oid}/{iid}")

    def create_installation_key(self, description: str, tags: list[str] | str | None = None, use_public_ca: bool = False) -> dict[str, Any]:
        """Create a new installation key.

        Args:
            description: Key description.
            tags: Optional list of tags.
            use_public_ca: Use public root CA.

        Returns:
            dict: New key details.
        """
        params = {"desc": description, "use_public_root_ca": "true" if use_public_ca else "false"}
        if tags:
            params["tags"] = tags if isinstance(tags, str) else ",".join(tags)
        return self._client.request("POST", f"installationkeys/{self.oid}", params=params)

    def delete_installation_key(self, iid: str) -> dict[str, Any]:
        """Delete an installation key.

        Args:
            iid: Installation key ID.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"installationkeys/{self.oid}", params={"iid": iid})

    # --- Ingestion Keys ---

    def get_ingestion_keys(self) -> dict[str, Any] | None:
        """List ingestion keys.

        Returns:
            dict: Ingestion key list.
        """
        data = self._client.request("GET", f"insight/{self.oid}/ingestion_keys")
        return data.get("keys", None)

    def create_ingestion_key(self, name: str) -> dict[str, Any]:
        """Create a new ingestion key.

        Args:
            name: Key name.

        Returns:
            dict: New key details.
        """
        return self._client.request("POST", f"insight/{self.oid}/ingestion_keys", params={"name": name})

    def delete_ingestion_key(self, name: str) -> dict[str, Any]:
        """Delete an ingestion key.

        Args:
            name: Key name.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"insight/{self.oid}/ingestion_keys",
                                    query_params={"name": name})

    # --- Outputs ---

    def get_outputs(self) -> dict[str, Any]:
        """List configured outputs.

        Returns:
            dict: Output configurations.
        """
        resp = self._client.request("GET", f"outputs/{self.oid}")
        return resp.get(self.oid, resp)

    def add_output(self, name: str, module: str, data_type: str, **kwargs: Any) -> dict[str, Any]:
        """Create a new output.

        Args:
            name: Output name.
            module: Output module type (e.g., 'syslog', 's3').
            data_type: Data type (e.g., 'event', 'detect').
            **kwargs: Module-specific parameters.

        Returns:
            dict: API response.
        """
        params = {"name": name, "module": module, "type": data_type}
        params.update(kwargs)
        return self._client.request("POST", f"outputs/{self.oid}", params=params)

    def delete_output(self, name: str) -> dict[str, Any]:
        """Delete an output.

        Args:
            name: Output name.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"outputs/{self.oid}", params={"name": name})

    # --- Tags ---

    def get_all_tags(self) -> list[str]:
        """Get all tags used by sensors in the org.

        Returns:
            list: Tag strings.
        """
        resp = self._client.request("GET", f"tags/{self.oid}")
        return resp.get("tags") or []

    def find_sensors_by_tag(self, tag: str) -> dict[str, Any]:
        """Find all sensors with a specific tag.

        Args:
            tag: Tag to search for.

        Returns:
            dict: SID to info mapping.
        """
        return self._client.request("GET", f"tags/{self.oid}/{urlescape(tag, safe='')}")

    def mass_tag(self, selector: str, tag: str, ttl: int | None = None) -> dict[str, Any]:
        """Add a tag to all sensors matching a selector expression.

        Iterates over all sensors matching the selector and applies
        the tag to each one.

        Args:
            selector: Sensor selector expression (bexpr).
            tag: Tag string to add.
            ttl: Optional TTL in seconds.

        Returns:
            dict: Summary with count of sensors tagged.
        """
        from .sensor import Sensor
        count = 0
        for sensor_info in self.list_sensors(selector=selector):
            sid = sensor_info.get("sid")
            if sid:
                sensor = Sensor(self, sid)
                sensor.add_tag(tag, ttl=ttl)
                count += 1
        return {"tagged": count, "tag": tag, "selector": selector}

    def mass_untag(self, selector: str, tag: str) -> dict[str, Any]:
        """Remove a tag from all sensors matching a selector expression.

        Iterates over all sensors matching the selector and removes
        the tag from each one.

        Args:
            selector: Sensor selector expression (bexpr).
            tag: Tag string to remove.

        Returns:
            dict: Summary with count of sensors untagged.
        """
        from .sensor import Sensor
        count = 0
        for sensor_info in self.list_sensors(selector=selector):
            sid = sensor_info.get("sid")
            if sid:
                sensor = Sensor(self, sid)
                sensor.remove_tag(tag)
                count += 1
        return {"untagged": count, "tag": tag, "selector": selector}

    # --- Online Sensors ---

    def get_online_sensors(self, sids: list[str] | None = None) -> list[str]:
        """Get list of online sensors.

        Args:
            sids: Optional list of SIDs to check.

        Returns:
            list: Online SID strings.
        """
        params = {}
        if sids:
            params["sids"] = sids
        resp = self._client.request("POST", f"online/{self.oid}", params=params)
        return [k for k, v in resp.items() if v]

    # --- Sensors ---

    def list_sensors(self, selector: str | None = None, limit: int | None = None, with_ip: str | None = None, with_hostname_prefix: str | None = None, is_online_only: bool = False) -> Generator[dict[str, Any], None, None]:
        """List sensors in the organization.

        Args:
            selector: Sensor selector expression (bexpr).
            limit: Max number per page.
            with_ip: Filter by IP address.
            with_hostname_prefix: Filter by hostname prefix.
            is_online_only: If True, only return sensors that are currently online.

        Yields:
            dict: Sensor information dicts.
        """
        continuation_token = None
        while True:
            qp = {}
            if continuation_token:
                qp["continuation_token"] = continuation_token
            if selector:
                qp["selector"] = selector
            if limit:
                qp["limit"] = str(limit)
            if with_ip:
                qp["with_ip"] = with_ip
            if with_hostname_prefix:
                qp["with_hostname_prefix"] = with_hostname_prefix
            if is_online_only:
                qp["is_online_only"] = "true"

            resp = self._client.request("GET", f"sensors/{self.oid}", query_params=qp or None)
            for s in resp.get("sensors", []):
                yield s

            continuation_token = resp.get("continuation_token")
            if not continuation_token:
                break

    def find_sensors_by_hostname(self, hostname: str) -> dict[str, Any]:
        """Find sensors by hostname prefix.

        Args:
            hostname: Hostname prefix.

        Returns:
            dict: Matching sensors.
        """
        return self._client.request("GET", f"hostnames/{self.oid}",
                                    query_params={"hostname": hostname})


    def export_sensors(self) -> dict[str, Any]:
        """Export full sensor manifest.

        Returns:
            dict: Sensor export data.
        """
        return self._client.request("POST", f"export/{self.oid}/sensors")

    def set_sensor_version(self, version: str | None = None, is_fallback: bool = False, is_sleep: bool = False) -> dict[str, Any]:
        """Set sensor version/branch for the organization.

        Args:
            version: Specific version string.
            is_fallback: Use fallback version.
            is_sleep: Put sensors to sleep.

        Returns:
            dict: API response.
        """
        qp = {}
        if version:
            qp["specific_version"] = version
        if is_fallback:
            qp["is_fallback"] = "true"
        if is_sleep:
            qp["is_sleep"] = "true"
        return self._client.request("POST", f"modules/{self.oid}", query_params=qp or None)

    # --- Services ---

    def service_request(self, service_name: str, data: dict[str, Any], is_async: bool = False, is_impersonate: bool = False) -> dict[str, Any]:
        """Send a request to a service/replicant.

        Args:
            service_name: Service name.
            data: Request data dict.
            is_async: Whether to run asynchronously.
            is_impersonate: If True, include JWT for impersonation.

        Returns:
            dict: Service response.
        """
        params = {
            "request_data": base64.b64encode(json.dumps(data).encode()),
            "is_async": is_async,
        }
        if is_impersonate:
            self._client.refresh_jwt()
            params["jwt"] = self._client._jwt
        return self._client.request("POST", f"service/{self.oid}/{service_name}", params=params)

    def get_available_services(self) -> list[str] | dict[str, Any]:
        """List available services/replicants.

        Returns:
            list: Service names.
        """
        data = self._client.request("GET", f"service/{self.oid}")
        return data.get("replicants", data)

    # --- Groups ---

    def get_groups(self) -> list[dict[str, Any]]:
        """List organization groups.

        Returns:
            list: Group dicts.
        """
        resp = self._client.request("GET", "groups")
        return resp.get("groups", resp)

    def create_group(self, name: str) -> dict[str, Any]:
        """Create a new group.

        Args:
            name: Group name.

        Returns:
            dict: New group info.
        """
        return self._client.request("POST", "groups", params={"name": name})

    def get_group(self, group_id: str) -> dict[str, Any]:
        """Get group details.

        Args:
            group_id: Group ID.

        Returns:
            dict: Group details.
        """
        return self._client.request("GET", f"groups/{group_id}")

    def delete_group(self, group_id: str) -> dict[str, Any]:
        """Delete a group.

        Args:
            group_id: Group ID.

        Returns:
            dict: API response.
        """
        return self._client.request("DELETE", f"groups/{group_id}")

    def add_group_owner(self, group_id: str, email: str) -> dict[str, Any]:
        return self._client.request("POST", f"groups/{group_id}/owners", params={"member_email": email})

    def remove_group_owner(self, group_id: str, email: str) -> dict[str, Any]:
        return self._client.request("DELETE", f"groups/{group_id}/owners", params={"member_email": email})

    def add_group_member(self, group_id: str, email: str) -> dict[str, Any]:
        return self._client.request("POST", f"groups/{group_id}/users", params={"member_email": email})

    def remove_group_member(self, group_id: str, email: str) -> dict[str, Any]:
        return self._client.request("DELETE", f"groups/{group_id}/users", params={"member_email": email})

    def set_group_permissions(self, group_id: str, permissions: list[str]) -> dict[str, Any]:
        return self._client.request("POST", f"groups/{group_id}/permissions",
                                    params={"perm": permissions})

    def get_group_logs(self, group_id: str) -> dict[str, Any]:
        return self._client.request("GET", f"groups/{group_id}/logs")

    def add_group_org(self, group_id: str, oid: str) -> dict[str, Any]:
        return self._client.request("POST", f"groups/{group_id}/orgs", params={"oid": oid})

    def remove_group_org(self, group_id: str, oid: str) -> dict[str, Any]:
        return self._client.request("DELETE", f"groups/{group_id}/orgs", params={"oid": oid})

    # --- Extensions ---

    def get_subscriptions(self) -> dict[str, Any] | None:
        """List subscribed extensions.

        Returns:
            dict: Subscription list.
        """
        data = self._client.request("GET", f"orgs/{self.oid}/resources")
        return data.get("resources", None)

    def subscribe_to_extension(self, name: str) -> dict[str, Any]:
        res_cat, res_name = name.split("/", 1)
        return self._client.request("POST", f"orgs/{self.oid}/resources",
                                    params={"res_cat": res_cat, "res_name": res_name})

    def unsubscribe_from_extension(self, name: str) -> dict[str, Any]:
        res_cat, res_name = name.split("/", 1)
        return self._client.request("DELETE", f"orgs/{self.oid}/resources",
                                    params={"res_cat": res_cat, "res_name": res_name})

    # --- Detections ---

    def get_detections(self, start: int, end: int, limit: int | None = None, category: str | None = None) -> Generator[dict[str, Any], None, None]:
        """Get historical detections.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).
            limit: Maximum number of detections.
            category: Filter by detection category.

        Yields:
            dict: Detection records.
        """
        cursor = "-"
        n_returned = 0
        while cursor:
            qp = {"start": str(int(start)), "end": str(int(end)), "cursor": cursor, "is_compressed": "true"}
            if limit is not None:
                qp["limit"] = str(limit)
            if category:
                qp["cat"] = category

            resp = self._client.request("GET", f"insight/{self.oid}/detections", query_params=qp)
            cursor = resp.get("next_cursor")
            for d in self._client.unwrap(resp.get("detects", "")):
                yield d
                n_returned += 1
                if limit is not None and n_returned >= limit:
                    return
            if limit is not None and n_returned >= limit:
                return

    def get_detection_by_id(self, detect_id: str) -> dict[str, Any]:
        """Get a detection by ID.

        Args:
            detect_id: Detection ID.

        Returns:
            dict: Detection details.
        """
        return self._client.request("GET", f"insight/{self.oid}/detections/{detect_id}")

    # --- Audit ---

    def get_audit_logs(self, start: int, end: int, limit: int | None = None, event_type: str | None = None, sid: str | None = None) -> Generator[dict[str, Any], None, None]:
        """Get audit logs.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).
            limit: Maximum number of results.
            event_type: Filter by event type.
            sid: Filter by sensor ID.

        Yields:
            dict: Audit log entries.
        """
        cursor = "-"
        n_returned = 0
        while cursor:
            qp = {"start": str(int(start)), "end": str(int(end)), "cursor": cursor, "is_compressed": "true"}
            if limit is not None:
                qp["limit"] = str(limit)
            if event_type:
                qp["event_type"] = event_type
            if sid:
                qp["sid"] = str(sid)

            resp = self._client.request("GET", f"insight/{self.oid}/audit", query_params=qp)
            cursor = resp.get("next_cursor")
            for entry in self._client.unwrap(resp.get("events", "")):
                yield entry
                n_returned += 1
                if limit is not None and n_returned >= limit:
                    return
            if limit is not None and n_returned >= limit:
                return

    # --- Jobs ---

    def get_jobs(self, start_time: int | None = None, end_time: int | None = None, limit: int | None = None, sid: str | None = None) -> list[dict[str, Any]]:
        """List service jobs.

        Args:
            start_time: Start time filter.
            end_time: End time filter.
            limit: Max results.
            sid: Filter by sensor ID.

        Returns:
            list: Job dicts.
        """
        import time as _time
        qp = {"is_compressed": "true", "with_data": "false"}
        if start_time is None:
            start_time = int(_time.time()) - 86400
        if end_time is None:
            end_time = int(_time.time())
        qp["start"] = str(int(start_time))
        qp["end"] = str(int(end_time))
        if limit is not None:
            qp["limit"] = str(limit)
        if sid is not None:
            qp["sid"] = str(sid)
        resp = self._client.request("GET", f"job/{self.oid}", query_params=qp)
        raw_jobs = resp.get("jobs", "")
        if not raw_jobs:
            return []
        jobs = self._client.unwrap(raw_jobs)
        return [job for job_id, job in jobs.items()]
