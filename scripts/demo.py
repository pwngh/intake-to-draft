"""Exercise real HTTP on an OS-selected loopback port, then stop the server."""

import json
import os
import socket
import subprocess
import sys
import time
import tempfile
from pathlib import Path

import httpx


def reviewed_run(client) -> dict:
    response = client.post("/demo/runs")
    response.raise_for_status()
    run = response.json()
    base = f"/runs/{run['run_id']}"
    assert run["status"] == "needs_review" and run["audit"] == []
    assert client.get(base + "/draft").status_code == 409

    def decide(action, **fields):
        nonlocal run
        response = client.post(base + "/review", json={
            "action": action, "reviewer": "Scripted Demo Reviewer", "expected_revision": run["revision"], **fields})
        response.raise_for_status()
        run = response.json()

    for row in run["review_queue"]:
        if row["field"] == "petitioner_address":
            decide("reject", field=row["field"], reason="Check both address fragments before using them.")
        else:
            decide("accept", field=row["field"], subject=row["subject"])
    approval = {"action": "approve", "reviewer": "Scripted Demo Approver",
                "expected_revision": run["revision"], "confirmed_complete": True}
    assert client.post(base + "/review", json=approval).status_code == 409
    decide("correct", field="petitioner_address", value="18 Example Lane Sampletown",
           citations=[{"line": 5, "quote": "18 Example Lane"}, {"line": 6, "quote": "Sampletown"}],
           reason="Combine the street and city confirmed on source lines 5 and 6.")
    assert client.get(base + "/draft").status_code == 409  # Field decisions alone are not final approval.
    decide("approve", reviewer="Scripted Demo Approver", confirmed_complete=True)
    artifact = client.get(base + "/draft")
    artifact.raise_for_status()
    assert artifact.json()["approval"]["reviewer"] == "Scripted Demo Approver"
    birth = next(row for row in run["draft"]["provenance_table"] if row["field"] == "birth_date")
    assert birth["value"] == "1991-06-19" and birth["lines"] == [8]
    assert birth["earlier_assertions"][0]["citations"][0]["line"] == 4
    assert [e["action"] for e in run["audit"] if e["field"] == "petitioner_address"] == ["reject", "correct"]
    return run


def main() -> None:
    example = json.loads((Path(__file__).resolve().parent.parent / "examples/intake.json").read_text())
    # Pass the bound socket to Uvicorn so port selection has no release/rebind race.
    with tempfile.TemporaryDirectory(prefix="intake-demo-") as temporary, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "intake_draft.api:app", "--fd", str(listener.fileno()),
             "--log-level", "error", "--no-access-log"],
            pass_fds=(listener.fileno(),),
            env={**os.environ, "INTAKE_REVIEW_DB": str(Path(temporary) / "review.sqlite")},
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False) as client:
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("demonstration server exited before becoming ready")
                    try:
                        response = client.get("/health")
                        response.raise_for_status()
                        break
                    except httpx.TransportError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("demonstration server did not become ready") from None
                        time.sleep(0.05)
                response = client.post("/intakes/validate", json=example)
                response.raise_for_status()
                first = response.json()
                repeated = client.post("/intakes/validate", json=example)
                repeated.raise_for_status()
                assert first == repeated.json(), "line numbering must be reproducible"
                response = client.post("/references/search", json={"query": "adult name change", "limit": 1})
                response.raise_for_status()
                notes = response.json()["matches"]
                assert notes[0]["id"] == "adult_name_change"
                assert client.post("/intakes/validate", json={"transcript": "  "}).status_code == 422
                extraction = client.get("/demo/extraction")
                extraction.raise_for_status()
                report = extraction.json()
                assert report["transcript_sha256"] == first["sha256"]
                assert report == client.get("/demo/extraction").json()
                birth = next(field for field in report["fields"] if field["field"] == "birth_date")
                assert birth["proposed"]["value"] == "1991-06-19"
                assert [a["value"] for a in birth["history"]] == ["1991-06-18", "1991-06-19"]
                address = next(field for field in report["fields"] if field["field"] == "petitioner_address")
                assert [c["line"] for c in address["proposed"]["citations"]] == [5, 6]
                assert report["status"] == "needs_review" and report["approved"] is False
                print("DEMONSTRATION ONLY — Republic of Alderhaven, a fictional jurisdiction.")
                print("Source lines:")
                for line in first["lines"]:
                    print(f"{line['number']}: {line['text']}")
                print("Transcript SHA-256:", first["sha256"])
                print("Candidate reference:", notes[0]["id"])
                print("Invented required fields:", ", ".join(notes[0]["required_fields"]))
                print("Recorded extraction model:", report["recorded_model"])
                print("Field | Proposed or earlier value | Source lines | Selection")
                for row in report["provenance_table"]:
                    print(f"{row['field']} | {row['value']} | {row['lines']} | {row['selection']}")
                run = reviewed_run(client)
                repeated_run = reviewed_run(client)
                assert run["draft"]["text"] == repeated_run["draft"]["text"]
                assert run["draft"]["provenance_table"] == repeated_run["draft"]["provenance_table"]
                print("\nScripted review audit (manual actions use the same API):")
                for event in run["audit"]:
                    print(f"{event['revision']}: {event['action']} {event['field'] or 'draft'} by {event['reviewer']}")
                print("\n" + run["draft"]["text"])
                print("Filled value | Source lines | Reviewer | Earlier assertions")
                for row in run["draft"]["provenance_table"]:
                    earlier = [a["value"] for a in row["earlier_assertions"]]
                    print(f"{row['value']} | {row['lines']} | {row['reviewer']} | {earlier}")
                print("PASS: human review gate, cited fictional draft, persistent audit, and repeatability.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
