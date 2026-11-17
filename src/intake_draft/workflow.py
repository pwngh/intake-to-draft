"""Durable human decisions around an untrusted recorded-model extraction."""

import copy
import fcntl
import hashlib
import json
import sqlite3
import unicodedata
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict
from uuid import uuid4

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from pydantic import Field, field_validator, model_validator

from intake_draft.contracts import NumberedTranscript, StrictModel, TranscriptRequest, number_transcript
from intake_draft.drafting import render_draft
from intake_draft.extraction import Citation, RecordedModel, check_output, messages_for, note_by_id


class ReviewConflict(ValueError):
    """The supplied revision or requested transition is no longer valid."""


class InvalidReview(ValueError):
    """A review decision has unsupported fields or evidence."""


class RunNotFound(LookupError):
    pass


class ReviewRequest(StrictModel):
    action: Literal["accept", "correct", "reject", "approve"]
    reviewer: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)
    field: str | None = None
    subject: str = Field(default="case", pattern=r"^(case|child-[1-9][0-9]*)$")
    value: str | None = Field(default=None, min_length=1, max_length=4_000)
    citations: list[Citation] = Field(default_factory=list, max_length=20)
    reason: str = Field(default="", max_length=2_000)
    confirmed_complete: bool = False

    @field_validator("reviewer", "reason")
    @classmethod
    def plain_text(cls, value: str) -> str:
        if any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
            raise ValueError("review text must not contain control characters")
        return value.strip()

    @model_validator(mode="after")
    def action_shape(self):
        if not self.reviewer:
            raise ValueError("reviewer identity is required")
        if self.action == "approve":
            if self.field is not None or self.subject != "case" or self.value is not None or self.citations:
                raise ValueError("approval cannot supply field values")
            if not self.confirmed_complete:
                raise ValueError("approval requires confirming the entire transcript and reviewed facts")
        else:
            if not self.field or self.confirmed_complete:
                raise ValueError("field decisions require a field and cannot approve the draft")
            if self.action == "correct":
                if self.value is None or not self.citations or not self.reason:
                    raise ValueError("correction requires a value, citations, and reason")
            elif self.value is not None or self.citations:
                raise ValueError("accept and reject cannot supply values or citations")
            if self.action == "reject" and not self.reason:
                raise ValueError("rejection requires a reason")
        return self


class RunState(TypedDict, total=False):
    run_id: str
    record: dict
    source: dict
    note: dict
    raw: str
    error: str
    report: dict
    decisions: dict
    audit: list
    revision: int
    status: str
    approval: dict | None
    draft: dict | None


def field_key(field: str, subject: str) -> str:
    return f"{field}/{subject}"


def review_queue(state: RunState) -> list[dict]:
    rows = {field_key(f["field"], f["subject"]): copy.deepcopy(f) for f in state["report"]["fields"]}
    emitted = {f["field"] for f in rows.values()}
    for field in state["note"]["required_fields"]:
        if field not in emitted:
            subject = "child-1" if field == "children" else "case"
            rows[field_key(field, subject)] = {
                "field": field, "subject": subject, "proposed": None, "history": [], "issues": ["missing_fact"]}
    for key, decision in state["decisions"].items():
        rows.setdefault(key, {"field": decision["field"], "subject": decision["subject"],
                              "proposed": None, "history": [], "issues": ["human_added_subject"]})
    for key, row in rows.items():
        decision = state["decisions"].get(key)
        row["decision"] = decision
        row["needs_action"] = decision is None or decision["action"] == "reject"
    return [rows[key] for key in sorted(rows)]


def reviewed_values(state: RunState) -> list[dict]:
    return [{"field": d["field"], "subject": d["subject"], **d["selected"],
             "reviewer": d["reviewer"], "action": d["action"]}
            for d in state["decisions"].values() if d["selected"] is not None]


def apply_review(state: RunState, request: ReviewRequest, at: str) -> dict:
    """Pure validation/transition, run before resume and again inside the review node."""
    if state["approval"] is not None or state["status"] == "draft":
        raise ReviewConflict("approved runs are sealed; start a new run to revise one")
    if request.expected_revision != state["revision"]:
        raise ReviewConflict("stale review revision; reload the run")
    revision = state["revision"] + 1
    decisions = copy.deepcopy(state["decisions"])
    approval, before, after = None, None, None
    if request.action == "approve":
        if any(row["needs_action"] for row in review_queue(state)):
            raise ReviewConflict("every required field and emitted subject needs a cited accept or correction")
        artifact = render_draft(NumberedTranscript.model_validate(state["source"]), state["note"],
                                reviewed_values(state), state["report"])
        approval = {"reviewer": request.reviewer, "at": at, "revision": revision,
                    "transcript_sha256": state["source"]["sha256"],
                    "draft_sha256": hashlib.sha256(artifact["text"].encode()).hexdigest(),
                    "confirmed_complete": True}
        after = approval
    else:
        if request.field not in state["note"]["required_fields"]:
            raise InvalidReview("field is not a stored requirement")
        if (request.field == "children") != (request.subject != "case"):
            raise InvalidReview("children require separate child subjects; other fields require case")
        key = field_key(request.field, request.subject)
        original = next((f for f in state["report"]["fields"]
                         if field_key(f["field"], f["subject"]) == key), None)
        proposed = original["proposed"] if original else None
        before = decisions[key]["selected"] if key in decisions else proposed
        if request.action == "accept":
            if proposed is None:
                raise ReviewConflict("no usable model proposal to accept; correct with evidence or reject")
            after = proposed
        elif request.action == "correct":
            payload = {"facts": [{"field": request.field, "subject": request.subject, "assertions": [{
                "value": request.value, "kind": "stated", "citations": [c.model_dump() for c in request.citations]}]}]}
            checked = check_output(json.dumps(payload), NumberedTranscript.model_validate(state["source"]), state["note"])
            after = checked["fields"][0]["proposed"] if checked["fields"] else None
            if after is None:
                raise InvalidReview("correction must be supported by ordered quotations from this transcript")
        decisions[key] = {"field": request.field, "subject": request.subject,
                          "action": request.action, "selected": after, "reviewer": request.reviewer,
                          "at": at, "revision": revision}
    event = {"revision": revision, "action": request.action, "reviewer": request.reviewer,
             "at": at, "field": request.field, "subject": request.subject, "reason": request.reason,
             "before": before, "after": after}
    return {"decisions": decisions, "revision": revision, "approval": approval,
            "audit": [*state["audit"], copy.deepcopy(event)]}


def build_workflow(checkpointer):
    def extract(state):
        source = NumberedTranscript.model_validate(state["source"])
        try:
            return {"raw": RecordedModel(state["record"])(messages_for(source, state["note"]), source.sha256)}
        except (ValueError, OSError):
            return {"raw": "", "error": "model_step_failed"}

    def check(state):
        report = check_output(state["raw"], NumberedTranscript.model_validate(state["source"]), state["note"])
        if state.get("error"):
            report["issues"] = [state["error"]]
        return {"report": report}

    def route(state):
        return {"status": "drafting" if state["approval"] else "needs_review"}

    def review(state):
        event = interrupt({"kind": "human_review", "revision": state["revision"],
                           "queue": review_queue(state)})
        return apply_review(state, ReviewRequest.model_validate(event["request"]), event["at"])

    def fill(state):
        if not state["approval"] or any(row["needs_action"] for row in review_queue(state)):
            raise ReviewConflict("draft filling requires explicit complete approval")
        draft = render_draft(NumberedTranscript.model_validate(state["source"]), state["note"],
                             reviewed_values(state), state["report"])
        if hashlib.sha256(draft["text"].encode()).hexdigest() != state["approval"]["draft_sha256"]:
            raise ReviewConflict("reviewed draft does not match its approval")
        return {"draft": draft, "status": "draft"}

    graph = StateGraph(RunState)
    for name, node in (("extract", extract), ("check", check), ("route", route), ("review", review), ("fill", fill)):
        graph.add_node(name, node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "check")
    graph.add_edge("check", "route")
    graph.add_conditional_edges("route", lambda s: "fill" if s["approval"] else "review")
    graph.add_edge("review", "route")
    graph.add_edge("fill", END)
    return graph.compile(checkpointer=checkpointer)


class ReviewService:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()

    @contextmanager
    def _graph(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Serialize revision checks and resumes across local processes, not just HTTP threads.
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with closing(sqlite3.connect(str(self.path), check_same_thread=False)) as conn:
                saver = SqliteSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=[]))
                with tracing_context(enabled=False):
                    yield build_workflow(saver)

    @staticmethod
    def _config(run_id):
        return {"configurable": {"thread_id": run_id}}

    def _state(self, graph, run_id):
        config = self._config(run_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            raise RunNotFound("run not found")
        if snapshot.tasks and not snapshot.interrupts:
            # next omits completed pending writes; tasks also covers that crash window.
            graph.invoke(None, config)
        return graph.get_state(config).values

    @staticmethod
    def _view(state):
        return {key: state[key] for key in (
            "run_id", "status", "revision", "source", "note", "report", "audit", "approval", "draft")} | {
                "review_queue": review_queue(state)}

    def create(self, record: dict) -> dict:
        run_id = uuid4().hex
        source = number_transcript(TranscriptRequest(transcript=record["transcript"]))
        initial = {"run_id": run_id, "record": record, "source": source.model_dump(),
                   "note": note_by_id(record["note_id"]), "decisions": {}, "audit": [],
                   "revision": 0, "status": "starting", "approval": None, "draft": None}
        with self._graph() as graph:
            graph.invoke(initial, self._config(run_id))
            return self._view(self._state(graph, run_id))

    def get(self, run_id: str) -> dict:
        with self._graph() as graph:
            return self._view(self._state(graph, run_id))

    def submit(self, run_id: str, request: ReviewRequest) -> dict:
        with self._graph() as graph:
            state = self._state(graph, run_id)
            at = datetime.now(timezone.utc).isoformat()
            apply_review(state, request, at)  # Reject before consuming a durable interrupt.
            graph.invoke(Command(resume={"request": request.model_dump(), "at": at}), self._config(run_id))
            return self._view(self._state(graph, run_id))
