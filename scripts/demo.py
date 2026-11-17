"""Exercise real HTTP on an OS-selected loopback port, then stop the server."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def main() -> None:
    example = json.loads((Path(__file__).resolve().parent.parent / "examples/intake.json").read_text())
    # Pass the bound socket to Uvicorn so port selection has no release/rebind race.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "intake_draft.api:app", "--fd", str(listener.fileno()),
             "--log-level", "error", "--no-access-log"],
            pass_fds=(listener.fileno(),),
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
                    except httpx.ConnectError:
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
                print("DEMONSTRATION ONLY — invented intake and reference requirements.")
                print("Source lines:")
                for line in first["lines"]:
                    print(f"{line['number']}: {line['text']}")
                print("Transcript SHA-256:", first["sha256"])
                print("Candidate reference:", notes[0]["id"])
                print("Invented required fields:", ", ".join(notes[0]["required_fields"]))
                print("PASS: HTTP validation, reference retrieval, and repeatability.")
                print("This slice does not extract facts, review fields, trace models, or produce a draft.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
