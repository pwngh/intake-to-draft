"""Local demonstration boundary; model recordings are replayed without inference."""

import json
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
    return {"status": "ok", "demonstration": True, "stage": "intake-contract"}


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
