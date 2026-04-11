"""Feedback SDK for LimaCharlie v2.

Wraps the ext-feedback extension for sending interactive feedback
requests (approval, acknowledgement, question) to external channels
(Slack, Email, Telegram, Teams, or built-in Web UI) and managing
channel configuration.
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization

from .extensions import Extensions
from .hive import Hive, HiveRecord

_EXTENSION_NAME = "ext-feedback"


class Feedback:
    """Feedback system client for LimaCharlie."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def oid(self) -> str:
        return self._org.oid

    # ------------------------------------------------------------------
    # Feedback requests
    # ------------------------------------------------------------------

    def request_simple_approval(
        self,
        channel: str,
        question: str,
        feedback_destination: str,
        *,
        case_id: str | None = None,
        playbook_name: str | None = None,
        approved_content: dict | None = None,
        denied_content: dict | None = None,
        timeout_seconds: int | None = None,
        timeout_choice: str | None = None,
        timeout_content: dict | None = None,
    ) -> dict[str, Any]:
        """Send a simple approval (Approve/Deny) request to a channel.

        Args:
            channel: Name of the configured feedback channel.
            question: The prompt to present to the respondent.
            feedback_destination: "case" or "playbook".
            case_id: Case number (required when destination is "case").
            playbook_name: Playbook to trigger (required when destination is "playbook").
            approved_content: JSON data included in the response when approved.
            denied_content: JSON data included in the response when denied.
            timeout_seconds: Auto-respond after this many seconds (minimum 60).
            timeout_choice: Choice to auto-select on timeout ("approved" or "denied");
                required when timeout_seconds is set.
            timeout_content: JSON data to include in the timeout response
                (overrides the choice's content if set).

        Returns:
            dict with request_id and optionally url (for web channels).
        """
        data: dict[str, Any] = {
            "channel": channel,
            "question": question,
            "feedback_destination": feedback_destination,
        }
        if case_id is not None:
            data["case_id"] = case_id
        if playbook_name is not None:
            data["playbook_name"] = playbook_name
        if approved_content is not None:
            data["approved_content"] = json.dumps(approved_content)
        if denied_content is not None:
            data["denied_content"] = json.dumps(denied_content)
        if timeout_seconds is not None:
            data["timeout_seconds"] = timeout_seconds
        if timeout_choice is not None:
            data["timeout_choice"] = timeout_choice
        if timeout_content is not None:
            data["timeout_content"] = json.dumps(timeout_content)
        ext = Extensions(self._org)
        return ext.request(_EXTENSION_NAME, "request_simple_approval", data=data)

    def request_acknowledgement(
        self,
        channel: str,
        question: str,
        feedback_destination: str,
        *,
        case_id: str | None = None,
        playbook_name: str | None = None,
        acknowledged_content: dict | None = None,
        timeout_seconds: int | None = None,
        timeout_content: dict | None = None,
    ) -> dict[str, Any]:
        """Send an acknowledgement request to a channel.

        Args:
            channel: Name of the configured feedback channel.
            question: The prompt to present to the respondent.
            feedback_destination: "case" or "playbook".
            case_id: Case number (required when destination is "case").
            playbook_name: Playbook to trigger (required when destination is "playbook").
            acknowledged_content: JSON data included in the response when acknowledged.
            timeout_seconds: Auto-acknowledge after this many seconds (minimum 60).
            timeout_content: JSON data to include in the timeout response
                (overrides acknowledged_content if set).

        Returns:
            dict with request_id and optionally url (for web channels).
        """
        data: dict[str, Any] = {
            "channel": channel,
            "question": question,
            "feedback_destination": feedback_destination,
        }
        if case_id is not None:
            data["case_id"] = case_id
        if playbook_name is not None:
            data["playbook_name"] = playbook_name
        if acknowledged_content is not None:
            data["acknowledged_content"] = json.dumps(acknowledged_content)
        if timeout_seconds is not None:
            data["timeout_seconds"] = timeout_seconds
        if timeout_content is not None:
            data["timeout_content"] = json.dumps(timeout_content)
        ext = Extensions(self._org)
        return ext.request(_EXTENSION_NAME, "request_acknowledgement", data=data)

    def request_question(
        self,
        channel: str,
        question: str,
        feedback_destination: str,
        *,
        case_id: str | None = None,
        playbook_name: str | None = None,
        timeout_seconds: int | None = None,
        timeout_content: dict | None = None,
    ) -> dict[str, Any]:
        """Send a question with free-form text input to a channel.

        Args:
            channel: Name of the configured feedback channel.
            question: The question to present to the respondent.
            feedback_destination: "case" or "playbook".
            case_id: Case number (required when destination is "case").
            playbook_name: Playbook to trigger (required when destination is "playbook").
            timeout_seconds: Auto-answer after this many seconds (minimum 60).
            timeout_content: JSON data to include in the timeout response
                (required when timeout_seconds is set for question type).

        Returns:
            dict with request_id and optionally url (for web channels).
        """
        data: dict[str, Any] = {
            "channel": channel,
            "question": question,
            "feedback_destination": feedback_destination,
        }
        if case_id is not None:
            data["case_id"] = case_id
        if playbook_name is not None:
            data["playbook_name"] = playbook_name
        if timeout_seconds is not None:
            data["timeout_seconds"] = timeout_seconds
        if timeout_content is not None:
            data["timeout_content"] = json.dumps(timeout_content)
        ext = Extensions(self._org)
        return ext.request(_EXTENSION_NAME, "request_question", data=data)

    # ------------------------------------------------------------------
    # Channel configuration
    # ------------------------------------------------------------------

    def _get_config(self) -> HiveRecord:
        hive = Hive(self._org, "extension_config")
        return hive.get(_EXTENSION_NAME)

    def _set_config(self, record: HiveRecord) -> dict[str, Any]:
        hive = Hive(self._org, "extension_config")
        return hive.set(record)

    def list_channels(self) -> list[dict[str, Any]]:
        """List configured feedback channels.

        Returns:
            List of channel dicts with name, channel_type, and output_name.
        """
        record = self._get_config()
        return record.data.get("channels", [])

    def add_channel(
        self,
        name: str,
        channel_type: str,
        output_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a feedback channel to the configuration.

        Args:
            name: Unique channel name.
            channel_type: One of web, slack, email, telegram, ms_teams.
            output_name: Tailored Output name with channel credentials
                (required for all types except web).

        Returns:
            Hive set response.
        """
        record = self._get_config()
        channels = record.data.get("channels", [])
        for ch in channels:
            if ch.get("name") == name:
                raise ValueError(f"channel {name!r} already exists")
        entry: dict[str, str] = {
            "name": name,
            "channel_type": channel_type,
        }
        if output_name is not None:
            entry["output_name"] = output_name
        channels.append(entry)
        record.data["channels"] = channels
        return self._set_config(record)

    def remove_channel(self, name: str) -> dict[str, Any]:
        """Remove a feedback channel from the configuration.

        Args:
            name: Channel name to remove.

        Returns:
            Hive set response.
        """
        record = self._get_config()
        channels = record.data.get("channels", [])
        new_channels = [ch for ch in channels if ch.get("name") != name]
        if len(new_channels) == len(channels):
            raise ValueError(f"channel {name!r} not found")
        record.data["channels"] = new_channels
        return self._set_config(record)
