"""Run the invented case through local inference; optionally verify a local trace."""

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import time

import httpx

from intake_draft.tracing import tracer_from_env
from intake_draft.workflow import ReviewRequest, ReviewService
from intake_draft.child_extraction import ChildLocalModel

ROOT = Path(__file__).resolve().parent.parent
QUERY = "I have chosen a new adult name because it feels like who I am. Please use only the explanation I actually give."
EXPECTED = {"birth_date": "1991-06-19", "petitioner_address": "18 Example Lane Sampletown",
            "petitioner_name": "Mara Vale", "requested_name": "Mara Wren",
            "reason_for_change": "I want a name that I chose for myself."}


def read_trace(run_id, path):
    config = json.loads(path.read_text())
    with httpx.Client(base_url=config["base_url"], auth=(config["public_key"], config["secret_key"]),
                      trust_env=False, follow_redirects=False, timeout=10) as client:
        deadline = time.monotonic() + 30
        while True:
            response = client.get("/api/public/v2/observations", params={
                "traceId": run_id, "fields": "core,basic,io", "limit": 100})
            response.raise_for_status()
            observations = response.json()["data"]
            if {"retrieve", "extract", "check", "route", "review", "fill"} <= {o["name"] for o in observations}:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Langfuse did not receive every workflow node within 30 seconds")
            time.sleep(1)
    rows = []
    for observation in sorted(observations, key=lambda o: o["startTime"]):
        assert observation["input"] is not None and observation["output"] is not None
        duration = (datetime.fromisoformat(observation["endTime"].replace("Z", "+00:00")) -
                    datetime.fromisoformat(observation["startTime"].replace("Z", "+00:00"))).total_seconds()
        assert duration >= 0
        rows.append({"node": observation["name"], "seconds": duration,
                     "input": observation["input"], "output": observation["output"]})
    return {"url": f"{config['base_url']}/project/{config['project_id']}/traces/{run_id}",
            "node_counts": dict(Counter(row["node"] for row in rows)), "observations": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    if args.trace:
        subprocess.run([str(ROOT / "scripts/langfuse"), "up"], check=True)
    os.environ["INTAKE_TRACING"] = "langfuse" if args.trace else "off"
    tracer = tracer_from_env()
    try:
        service = ReviewService(ROOT / ".runtime/live-review.sqlite", tracer=tracer, model_factory=ChildLocalModel,
                                embedding_dir=ROOT / ".runtime/minilm")
        transcript = json.loads((ROOT / "examples/intake.json").read_text())["transcript"]
        print("Running pinned local Qwen3-Coder; no hosted model or fallback.", flush=True)
        run = service.create_live(transcript, QUERY)
        if run["report"]["issues"]:
            raise RuntimeError(f"Live model step failed: {run['model_info']}")
        assert run["note"]["id"] == "adult_name_change_chosen_name", "Inspect the selected fictional requirements before review"
        for row in run["review_queue"]:
            value = row["proposed"]["value"] if row["proposed"] else ""
            if re.findall(r"\w+", value.casefold()) != re.findall(r"\w+", EXPECTED[row["field"]].casefold()):
                raise RuntimeError(f"Run {run['run_id']} needs manual review of {row['field']}; no guess was accepted")
            run = service.submit(run["run_id"], ReviewRequest(
                action="accept", reviewer="Scripted Live Demo Reviewer", expected_revision=run["revision"],
                field=row["field"], subject=row["subject"]))
        run = service.submit(run["run_id"], ReviewRequest(
            action="approve", reviewer="Scripted Live Demo Approver", expected_revision=run["revision"],
            confirmed_complete=True))
        trace = read_trace(run["run_id"], Path(os.environ.get("INTAKE_LANGFUSE_CONFIG", ROOT / ".runtime/langfuse-client.json"))) if args.trace else None
        output = {"run_id": run["run_id"], "model_info": run["model_info"], "retrieval": run["retrieval"],
                  "approval": run["approval"], "draft": run["draft"], "trace": trace,
                  "scope": "one development demonstration, not held-out accuracy measurement"}
        destination = ROOT / ".runtime/live-demo.json"
        destination.write_text(json.dumps(output, indent=2) + "\n")
        print(run["draft"]["text"])
        if trace:
            print("Verified node observations:", trace["node_counts"])
            print("Local trace:", trace["url"])
        print("Evidence:", destination)
        print("PASS: local model, cited reviewed draft" + (", and self-hosted Langfuse." if trace else "; tracing off."))
    finally:
        if tracer.client is not None:
            tracer.client.shutdown()


if __name__ == "__main__":
    main()
