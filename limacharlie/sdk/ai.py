"""AI generation SDK for LimaCharlie v2."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization

_HIVE_SECRET_PREFIX = "hive://secret/"
_AI_SESSIONS_URL = "https://ai.limacharlie.io"


class AI:
    """AI-powered generation of rules, queries, selectors, and playbooks."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        """The underlying API client."""
        return self._org.client

    def _resolve_secret(self, value: str) -> str:
        """Resolve a value that may be a hive://secret/ reference."""
        if not value or not value.startswith(_HIVE_SECRET_PREFIX):
            return value
        secret_name = value[len(_HIVE_SECRET_PREFIX):]
        if not secret_name:
            raise ValueError("empty secret name in hive://secret/ reference")
        from .hive import Hive
        record = Hive(self._org, "secret").get(secret_name)
        return record.data["secret"]

    def _resolve_map_secrets(self, m: dict[str, str] | None) -> dict[str, str] | None:
        """Resolve hive://secret/ references in all values of a string map."""
        if not m:
            return m
        return {k: self._resolve_secret(v) for k, v in m.items()}

    # Fields copied verbatim from an ai_agent hive record into the
    # request's ``profile`` section.  Every entry in this tuple maps
    # one-to-one to a field on the server's ``ProfileContent`` type
    # (see ai-sessions/pkg/api/types.go).
    _PROFILE_SCALAR_FIELDS: tuple[str, ...] = (
        "allowed_tools", "denied_tools", "permission_mode",
        "model", "max_turns", "max_budget_usd", "task_budget_tokens",
        "ttl_seconds", "one_shot", "plugins",
    )

    def start_session(self, definition_name: str, prompt: str | None = None,
                      name: str | None = None,
                      idempotent_key: str | None = None,
                      data: dict[str, Any] | None = None,
                      *,
                      model: str | None = None,
                      max_turns: int | None = None,
                      max_budget_usd: float | None = None,
                      task_budget_tokens: int | None = None,
                      ttl_seconds: int | None = None,
                      one_shot: bool | None = None,
                      permission_mode: str | None = None,
                      allowed_tools: list[str] | None = None,
                      denied_tools: list[str] | None = None,
                      plugins: list[str] | None = None,
                      environment: dict[str, str] | None = None,
                      anthropic_key: str | None = None,
                      lc_api_key: str | None = None,
                      lc_uid: str | None = None) -> dict[str, Any]:
        """Start an AI session using an ai_agent Hive definition as template.

        The definition stored in the ``ai_agent`` hive is treated as a
        template.  Any keyword arguments supplied here override the
        corresponding fields from the template.  ``environment`` is
        *merged* (override values win for matching keys); all other
        overrides *replace* the template value outright.

        Override values may be literal strings or ``hive://secret/<name>``
        references (same semantics as D&R rules); references are
        resolved automatically before the request is sent.

        Args:
            definition_name: Name of the ai_agent hive record to use as template.
            prompt: Replace the prompt from the definition.
            name: Replace the session name.
            idempotent_key: Deduplication key.
            data: Dict appended to the prompt as yaml event data (for
                standalone CLI invocations that lack a D&R event).

        Keyword Args:
            model: Replace the Anthropic model (e.g. ``claude-sonnet-4-6``).
            max_turns: Replace the maximum number of agent turns.
            max_budget_usd: Replace the hard USD cost cap.
            task_budget_tokens: Replace the per-task token budget.
            ttl_seconds: Replace the session time-to-live.
            one_shot: When True, session auto-terminates after the
                initial prompt is complete.  Use ``False`` to force the
                template's one_shot off.
            permission_mode: Replace the permission mode
                (``acceptEdits``, ``plan``, ``bypassPermissions``).
            allowed_tools: Replace the allowed tools list.
            denied_tools: Replace the denied tools list.
            plugins: Replace the enabled plugins list.
            environment: Env vars merged with the template's environment;
                override values win on conflicts.  Values may be
                ``hive://secret/<name>`` references.
            anthropic_key: Replace the Anthropic API key.  May be a
                literal key or a ``hive://secret/<name>`` reference.
            lc_api_key: Replace the LC API key (literal or secret ref).
            lc_uid: Replace the LC user ID (literal or secret ref).

        Returns:
            dict: Session creation response with session_id and status.
        """
        from .hive import Hive

        # Fetch the ai_agent definition; treat its fields as the template
        # that overrides stack on top of.
        record = Hive(self._org, "ai_agent").get(definition_name)
        defn = record.data or {}

        # Credential resolution: override wins, otherwise pull from the
        # hive record's *_secret field.  Override values are themselves
        # passed through secret resolution so a caller can still supply
        # a "hive://secret/..." reference.
        anthropic_key_final = self._resolve_secret(
            anthropic_key if anthropic_key is not None
            else defn.get("anthropic_secret", "")
        )
        lc_api_key_final = self._resolve_secret(
            lc_api_key if lc_api_key is not None
            else defn.get("lc_api_key_secret", "")
        )
        lc_uid_final = self._resolve_secret(
            lc_uid if lc_uid is not None
            else defn.get("lc_uid_secret", "")
        )

        # Fall back to the caller's own API key if nothing else produced one.
        if not lc_api_key_final:
            lc_api_key_final = self.client._api_key

        # Build the profile section by copying template fields verbatim.
        profile: dict[str, Any] = {}
        for field in self._PROFILE_SCALAR_FIELDS:
            if field in defn:
                profile[field] = defn[field]

        # Apply scalar / list overrides.  A None override means "keep template".
        scalar_overrides: dict[str, Any] = {
            "model": model,
            "max_turns": max_turns,
            "max_budget_usd": max_budget_usd,
            "task_budget_tokens": task_budget_tokens,
            "ttl_seconds": ttl_seconds,
            "one_shot": one_shot,
            "permission_mode": permission_mode,
            "allowed_tools": allowed_tools,
            "denied_tools": denied_tools,
            "plugins": plugins,
        }
        for field, value in scalar_overrides.items():
            if value is not None:
                profile[field] = value

        # Environment: merge template + overrides (override wins on key collision).
        template_env = defn.get("environment") or {}
        if template_env or environment:
            merged_env: dict[str, str] = {}
            merged_env.update(template_env)
            if environment:
                merged_env.update(environment)
            profile["environment"] = self._resolve_map_secrets(merged_env)

        # Resolve secrets in MCP server configs (not currently overridable
        # from the CLI -- the template wins).
        if defn.get("mcp_servers"):
            resolved_servers: dict[str, Any] = {}
            for srv_name, srv_cfg in defn["mcp_servers"].items():
                srv = dict(srv_cfg)
                if srv.get("headers"):
                    srv["headers"] = self._resolve_map_secrets(srv["headers"])
                if srv.get("env"):
                    srv["env"] = self._resolve_map_secrets(srv["env"])
                resolved_servers[srv_name] = srv
            profile["mcp_servers"] = resolved_servers

        # Build the final prompt, optionally appending supplied data.
        final_prompt = prompt or defn.get("prompt", "")
        if data:
            import yaml
            final_prompt += "\n\nEvent data:\n```yaml\n" + yaml.safe_dump(data, default_flow_style=False).rstrip("\n") + "\n```"

        # Build the request body.
        request_body: dict[str, Any] = {
            "prompt": final_prompt,
            "anthropic_key": anthropic_key_final,
            "trigger_source": "cli",
        }
        if lc_api_key_final:
            request_body["lc_api_key"] = lc_api_key_final
        if lc_uid_final:
            request_body["lc_uid"] = lc_uid_final
        if name or defn.get("name"):
            request_body["name"] = name or defn["name"]
        if idempotent_key:
            request_body["idempotent_key"] = idempotent_key
        if profile:
            request_body["profile"] = profile

        extra = {"X-LC-OID": self.client._oid}

        # Use the raw API key when available (works with current and future
        # ai-sessions deployments).  Fall back to JWT auth for OAuth users
        # (requires OrgDualAuthMiddleware on the server side).
        if self.client._api_key is not None:
            extra["Authorization"] = f"Bearer {self.client._api_key}"
            return self.client.request(
                "POST", "v1/api/sessions",
                raw_body=json.dumps(request_body).encode(),
                content_type="application/json",
                is_no_auth=True,
                alt_root=_AI_SESSIONS_URL,
                extra_headers=extra,
            )

        return self.client.request(
            "POST", "v1/api/sessions",
            raw_body=json.dumps(request_body).encode(),
            content_type="application/json",
            alt_root=_AI_SESSIONS_URL,
            extra_headers=extra,
        )

    def generate_dr_rule(self, description: str) -> dict[str, Any]:
        """Generate a complete D&R rule from a natural language description.

        Args:
            description: Natural language description of the desired rule.

        Returns:
            dict: Generated rule with detect and respond components.
        """
        return self.client.request("POST", "ai/dr",
                                   params={"query": description})

    def generate_detection(self, description: str) -> dict[str, Any]:
        """Generate a detection component from a natural language description.

        Args:
            description: Natural language description of the detection logic.

        Returns:
            dict: Generated detection component.
        """
        return self.client.request("POST", "ai/detection",
                                   params={"query": description})

    def generate_response(self, description: str) -> dict[str, Any]:
        """Generate a response component from a natural language description.

        Args:
            description: Natural language description of the response action.

        Returns:
            dict: Generated response component.
        """
        return self.client.request("POST", "ai/response",
                                   params={"query": description})

    def generate_lcql(self, description: str) -> dict[str, Any]:
        """Generate an LCQL query from a natural language description.

        Args:
            description: Natural language description of the query.

        Returns:
            dict: Generated LCQL query.
        """
        return self.client.request("POST", "ai/lcql",
                                   params={"query": description})

    def generate_sensor_selector(self, description: str) -> dict[str, Any]:
        """Generate a sensor selector from a natural language description.

        Args:
            description: Natural language description of the target sensors.

        Returns:
            dict: Generated sensor selector expression.
        """
        return self.client.request("POST", "ai/sensor_selector",
                                   params={"query": description})

    def generate_playbook(self, description: str) -> dict[str, Any]:
        """Generate a Python playbook from a natural language description.

        Args:
            description: Natural language description of the playbook logic.

        Returns:
            dict: Generated Python playbook code.
        """
        return self.client.request("POST", "ai/playbook/python",
                                   params={"query": description})

    def summarize_detection(self, detection_data: dict[str, Any]) -> dict[str, Any]:
        """Generate a human-readable summary of a detection.

        Args:
            detection_data: Detection data dict to summarize.

        Returns:
            dict: Human-readable summary.
        """
        return self.client.request("POST", "ai/det_summary",
                                   params={"query": json.dumps(detection_data)})

    # ------------------------------------------------------------------
    # Org-scoped AI Session management
    # ------------------------------------------------------------------

    def _org_request(self, verb: str, path: str,
                     query_params: dict[str, str] | None = None,
                     ) -> dict[str, Any]:
        """Make an authenticated request to the ai-sessions org endpoints.

        The org endpoints accept both API keys and JWTs via
        OrgDualAuthMiddleware. We send the raw API key when available
        (same pattern as start_session) for maximum compatibility.
        """
        extra: dict[str, str] = {"X-LC-OID": self.client._oid}
        if self.client._api_key is not None:
            extra["Authorization"] = f"Bearer {self.client._api_key}"
            return self.client.request(
                verb, path,
                query_params=query_params,
                is_no_auth=True,
                alt_root=_AI_SESSIONS_URL,
                extra_headers=extra,
            )
        return self.client.request(
            verb, path,
            query_params=query_params,
            alt_root=_AI_SESSIONS_URL,
            extra_headers=extra,
        )

    def list_sessions(self, status: str | None = None,
                      limit: int | None = None,
                      cursor: str | None = None) -> dict[str, Any]:
        """List AI sessions for the organization.

        Args:
            status: Filter by session status (running, ended, starting).
            limit: Maximum number of results (1-200, default 50).
            cursor: Pagination cursor from a previous response.

        Returns:
            dict with ``sessions`` list and ``next_cursor`` string.
        """
        qp: dict[str, str] = {}
        if status:
            qp["status"] = status
        if limit is not None:
            qp["limit"] = str(limit)
        if cursor:
            qp["cursor"] = cursor
        return self._org_request("GET", "v1/org/sessions",
                                 query_params=qp or None)

    def get_session(self, session_id: str) -> dict[str, Any]:
        """Get details of a specific AI session.

        Args:
            session_id: The session ID.

        Returns:
            dict with ``session`` object.
        """
        return self._org_request("GET", f"v1/org/sessions/{session_id}")

    def terminate_session(self, session_id: str) -> dict[str, Any]:
        """Terminate a running AI session.

        Args:
            session_id: The session ID to terminate.

        Returns:
            dict with ``terminated: true``.
        """
        return self._org_request("DELETE", f"v1/org/sessions/{session_id}")

    def get_session_history(self, session_id: str) -> dict[str, Any]:
        """Get the conversation history of an AI session.

        Args:
            session_id: The session ID.

        Returns:
            dict with ``messages`` list.
        """
        return self._org_request("GET", f"v1/org/sessions/{session_id}/history")

    def attach_session(self, session_id: str, *,
                       read_only: bool = False) -> "SessionAttachment":
        """Open a WebSocket attachment to a running AI session.

        The returned object is an async context manager yielding parsed
        JSON messages from the session.  See
        :mod:`limacharlie.sdk.ai_session` for the full protocol and
        helper classes.

        Args:
            session_id: The session to attach to.
            read_only: Use the org-scoped read-only endpoint instead of
                the owner-interactive one.  Required when the caller
                does not own the session.

        Returns:
            A :class:`SessionAttachment` instance.  Use ``async with``
            to connect, and :meth:`~SessionAttachment.messages` to
            iterate over streaming messages.
        """
        from .ai_session import SessionAttachment
        return SessionAttachment(self, session_id, read_only=read_only)

    def list_usage_identities(self) -> dict[str, Any]:
        """List all API key identities with AI session usage data.

        Returns:
            dict with ``identities`` list of strings.
        """
        return self._org_request("GET", "v1/org/usage/identities")

    def get_usage(self, identity: str) -> dict[str, Any]:
        """Get hourly token and cost usage for a specific API key identity.

        Args:
            identity: The API key identity name.

        Returns:
            dict with ``identity`` string and ``usage`` list of data points.
        """
        return self._org_request("GET", f"v1/org/usage/identities/{identity}")
