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

    # ------------------------------------------------------------------
    # User-scoped endpoints: registration, Claude credential management,
    # and user-owned session creation.  Unlike the org endpoints above,
    # these identify the caller by their JWT's UID only and never carry
    # X-LC-OID.  They back the ``limacharlie ai chat`` and
    # ``limacharlie ai auth claude`` commands.
    # ------------------------------------------------------------------

    def _user_request(self, verb: str, path: str,
                      raw_body: bytes | None = None,
                      query_params: dict[str, str] | None = None,
                      ) -> dict[str, Any]:
        """Call an ai-sessions user-scoped endpoint with the caller's JWT.

        User-scoped endpoints on ai-sessions identify the caller via
        ``claims.UID()`` alone; sending X-LC-OID is unnecessary here
        and the routes don't accept raw API keys.
        """
        kwargs: dict[str, Any] = {"alt_root": _AI_SESSIONS_URL}
        if raw_body is not None:
            kwargs["raw_body"] = raw_body
            kwargs["content_type"] = "application/json"
        if query_params:
            kwargs["query_params"] = query_params
        return self.client.request(verb, path, **kwargs)

    def register_user(self) -> dict[str, Any]:
        """Register the authenticated user with ai-sessions (idempotent).

        Required once per UID before creating user-owned sessions or
        storing Claude credentials.  Safe to call repeatedly: the
        server returns the same ``registered_at`` on subsequent calls.

        Returns:
            dict with ``registered: true`` and ``registered_at``.
        """
        return self._user_request("POST", "v1/register", raw_body=b"")

    def claude_auth_status(self) -> dict[str, Any]:
        """Return whether the authenticated user has Claude credentials stored.

        Returns:
            dict with ``has_credentials`` (bool) and, when True,
            ``credential_type`` (``"oauth"`` or ``"apikey"``) and
            ``created_at`` (ISO-8601 string).
        """
        return self._user_request("GET", "v1/auth/claude/status")

    def claude_login_start(self) -> dict[str, Any]:
        """Begin the browser OAuth flow for storing a Claude OAuth token.

        Starts a pooled OAuth job on the server side; the returned
        ``oauth_session_id`` must be passed to
        :meth:`claude_login_get_url` (poll) and
        :meth:`claude_login_submit_code`.

        Returns:
            dict with ``oauth_session_id``, ``expires_in`` (seconds),
            and a user-facing ``message``.
        """
        return self._user_request("POST", "v1/auth/claude/start", raw_body=b"")

    def claude_login_get_url(self, oauth_session_id: str) -> dict[str, Any]:
        """Poll for the browser URL that completes the OAuth flow.

        The server spins up a headless browser that produces the URL;
        the first few calls typically return ``status="pending"`` until
        the URL is ready.

        Args:
            oauth_session_id: The ID returned from :meth:`claude_login_start`.

        Returns:
            dict with ``status`` (``pending``/``ready``/``failed``) and
            ``url`` when ``status="ready"``.
        """
        return self._user_request(
            "GET", "v1/auth/claude/url",
            query_params={"session_id": oauth_session_id},
        )

    def claude_login_submit_code(self, oauth_session_id: str,
                                 code: str) -> dict[str, Any]:
        """Complete the OAuth flow by submitting the code from the browser.

        Args:
            oauth_session_id: The ID returned from :meth:`claude_login_start`.
            code: The authorization code copied from the browser.

        Returns:
            dict with ``success`` and ``status`` (``completed`` on success).
        """
        body = json.dumps({
            "session_id": oauth_session_id,
            "code": code,
        }).encode()
        return self._user_request("POST", "v1/auth/claude/code", raw_body=body)

    def claude_set_apikey(self, api_key: str) -> dict[str, Any]:
        """Store a raw Anthropic API key for the authenticated user.

        Args:
            api_key: A literal Anthropic API key.  ``hive://secret/<name>``
                references are resolved before the request is sent.

        Returns:
            dict with ``success: true``.
        """
        resolved = self._resolve_secret(api_key)
        body = json.dumps({"api_key": resolved}).encode()
        return self._user_request("POST", "v1/auth/claude/apikey",
                                  raw_body=body)

    def claude_logout(self) -> dict[str, Any]:
        """Remove the authenticated user's stored Claude credentials."""
        return self._user_request("DELETE", "v1/auth/claude")

    def create_user_session(self, *,
                            name: str | None = None,
                            idempotent_key: str | None = None,
                            model: str | None = None,
                            max_turns: int | None = None,
                            max_budget_usd: float | None = None,
                            task_budget_tokens: int | None = None,
                            one_shot: bool | None = None,
                            permission_mode: str | None = None,
                            allowed_tools: list[str] | None = None,
                            denied_tools: list[str] | None = None,
                            plugins: list[str] | None = None,
                            ) -> dict[str, Any]:
        """Create a user-owned AI session (interactive chat).

        Unlike :meth:`start_session` (org-scoped, runs an ai_agent
        template), this creates a bare interactive session owned by the
        authenticated UID.  Use :meth:`attach_session` to send prompts.

        The caller must have Claude credentials stored
        (:meth:`claude_set_apikey` or :meth:`claude_login_start`).

        Keyword Args mirror the :class:`CreateSessionRequest` fields
        accepted by ``POST /v1/sessions`` on ai-sessions (see
        ``internal/sessionmanager/models.go``).

        Returns:
            dict representation of the created session (``id``,
            ``status``, ``created_at``, ...).
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if idempotent_key is not None:
            body["idempotent_key"] = idempotent_key
        if model is not None:
            body["model"] = model
        if max_turns is not None:
            body["max_turns"] = max_turns
        if max_budget_usd is not None:
            body["max_budget_usd"] = max_budget_usd
        if task_budget_tokens is not None:
            body["task_budget_tokens"] = task_budget_tokens
        if one_shot is not None:
            body["one_shot"] = one_shot
        if permission_mode is not None:
            body["permission_mode"] = permission_mode
        if allowed_tools is not None:
            body["allowed_tools"] = allowed_tools
        if denied_tools is not None:
            body["denied_tools"] = denied_tools
        if plugins is not None:
            body["plugins"] = plugins
        return self._user_request("POST", "v1/sessions",
                                  raw_body=json.dumps(body).encode())
