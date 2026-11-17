"""Local demonstration boundary; model recordings are replayed without inference."""

import json
import os
from importlib.resources import files

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from intake_draft.contracts import (
    NumberedTranscript,
    SearchRequest,
    TranscriptRequest,
    number_transcript,
)
from intake_draft.references import ReferenceIndex
from intake_draft.extraction import JURISDICTION, citation_table, replay_record
from intake_draft.workflow import InvalidReview, ReviewConflict, ReviewRequest, ReviewService, RunNotFound

app = FastAPI(
    title="Intake to draft demonstration",
    description=f"{JURISDICTION}. Not a legal form or legal advice.",
    version="0.1.0",
)
index = ReferenceIndex()


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo rejected transcripts, including malformed Unicode, into errors.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ]
        },
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "demonstration": True, "stage": "review-and-draft"}


@app.post("/intakes/validate", response_model=NumberedTranscript)
def validate_intake(request: TranscriptRequest) -> NumberedTranscript:
    return number_transcript(request)


@app.post("/references/search")
def search_references(request: SearchRequest) -> dict:
    return {"demonstration": True, "backend": "keyword", "matches": index.search(request.query, request.limit)}


@app.get("/demo/extraction")
def replay_extraction() -> dict:
    record = json.loads(files("intake_draft").joinpath("data/recorded_name_change.json").read_text())
    report = replay_record(record)
    return {**report, "recorded_model": record["model"], "model_digest": record["model_digest"],
            "provenance_table": citation_table(report)}


def review_service() -> ReviewService:
    return ReviewService(os.environ.get("INTAKE_REVIEW_DB", ".runtime/review.sqlite"))


@app.exception_handler(ReviewConflict)
@app.exception_handler(InvalidReview)
@app.exception_handler(RunNotFound)
async def review_error(_request: Request, exc: Exception) -> JSONResponse:
    status = 404 if isinstance(exc, RunNotFound) else 409 if isinstance(exc, ReviewConflict) else 422
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.post("/demo/runs", status_code=201)
def start_review() -> dict:
    record = json.loads(files("intake_draft").joinpath("data/recorded_name_change.json").read_text())
    return review_service().create(record)


@app.get("/runs/{run_id}")
def get_review(run_id: str) -> dict:
    return review_service().get(run_id)


@app.post("/runs/{run_id}/review")
def review_field(run_id: str, request: ReviewRequest) -> dict:
    return review_service().submit(run_id, request)


@app.get("/runs/{run_id}/draft")
def get_draft(run_id: str) -> dict:
    run = review_service().get(run_id)
    if run["status"] != "draft":
        raise ReviewConflict("draft is unavailable until explicit complete approval")
    return {**run["draft"], "approval": run["approval"]}
