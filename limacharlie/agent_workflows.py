"""CLI-owned session workflow dispatch, conversation state and native handoff.

The runner supplies model transport and approval; domain selection/execution stays
here. D&R is the first registered operation. State conveys context, never authority.
"""

import json
import os
from pathlib import Path
import uuid
import hashlib

from .dr_interpreter import INTERPRETATION_SCHEMA, draft, extract_examples, render


class WorkflowSession:
    interpretation_schema = INTERPRETATION_SCHEMA

    def __init__(self, directory, session_id=""):
        self.root = Path(directory)
        name = "workflows" + (
            "-" + hashlib.sha256(session_id.encode()).hexdigest()[:20]
            if session_id
            else ""
        )
        self.path = self.root / ".lc-agent" / (name + ".json")
        self.history = []
        self.samples = []
        self.pending_handoff = ""
        if self.path.exists():
            state = json.loads(self.path.read_text())
            self.history = state.get("history", [])[-4:]
            self.samples = state.get("samples", [])
            self.pending_handoff = state.get("handoff", "")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = self.path.with_suffix(".tmp")
        with open(
            os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w"
        ) as f:
            json.dump(
                {
                    "history": self.history[-4:],
                    "samples": self.samples,
                    "handoff": self.pending_handoff,
                },
                f,
            )
        os.replace(temp, self.path)

    def native_accepted(self):
        self.pending_handoff = ""
        self.save()

    async def dispatch(
        self,
        request,
        interpret,
        *,
        org_hint="",
        instructions="",
        authorize=None,
        context=None,
    ):
        ambient = {}
        native_context = False
        for entry in context or []:
            if entry.get("kind") != "agent_workspace":
                native_context = True
                continue
            data = entry.get("data") or {}
            if (
                not isinstance(data, dict)
                or data.get("assignments")
                or data.get("dependency_results")
            ):
                native_context = True
                continue
            ambient["execution_context"] = data.get("execution_context") or {}
            ambient["public_context"] = [
                {"type": e.get("type"), "content": (e.get("content") or "")[:1500]}
                for e in data.get("public_context", [])[-4:]
            ]
        result = (
            {"status": "not_applicable"}
            if native_context
            else await draft(
                request,
                interpret,
                directory=self.root / "drafts" / str(uuid.uuid4()),
                org_hint=org_hint,
                route=True,
                conversation=self.history,
                previous_samples=self.samples,
                instructions=instructions,
                authorize=authorize,
                ambient_context=ambient,
            )
        )
        if result["status"] == "deploy_existing":
            if self.history and self.history[-1].get("status") != "tested":
                result.update(
                    status="needs_evidence",
                    message="The latest draft or edit has not passed validation. Retry that edit before deploying; an older draft will not be substituted.",
                )
            else:
                result["status"] = "not_applicable"
        result["workflow"] = (
            "dr-draft" if result["status"] != "not_applicable" else None
        )
        if result["status"] == "not_applicable":
            # Native Claude has not seen turns completed by a workflow. Supply
            # the result and artifact paths once, as context only. Native tool
            # policy and dr deploy checks remain authoritative.
            result["handoff"] = self.pending_handoff
            self.history = []
            self.samples = []
        else:
            response = render(result)
            text, supplied = extract_examples(request, strict=False)
            self.history.append(
                {
                    "request": text,
                    "status": result["status"],
                    "response": response,
                    "intent": result.get("intent"),
                    "organization": result.get("org_id"),
                }
            )
            self.history = self.history[-4:]
            if result["status"] == "tested":
                self.samples = json.loads(
                    (Path(result["workspace"]) / "evidence.json").read_text()
                )
            elif supplied:
                self.samples = supplied
            self.pending_handoff = json.dumps(self.history)
            result["response"] = response
        self.save()
        return result
