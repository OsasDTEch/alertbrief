"""
AlertBrief API + demo.

Run:
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8080
  open http://localhost:8080

Endpoints:
  GET  /                    the demo page (raw vs briefed, fire-a-storm)
  POST /ingest {kind, ...}  kind="single" or "storm"; returns raw alerts + briefed incidents
  POST /ingest/custom       accepts your own alert JSON list (SIGNL4-shaped)
"""
from __future__ import annotations

import random
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

import engine

app = FastAPI(title="AlertBrief", version="0.1")
HERE = Path(__file__).parent


@app.get("/", response_class=HTMLResponse)
def home():
    return (HERE / "index.html").read_text()


@app.post("/ingest")
async def ingest(req: Request):
    body = await req.json()
    kind = body.get("kind", "single")
    rng = random.Random()  # fresh randomness each press so the demo feels live
    if kind == "storm":
        alerts = engine.make_storm(rng)
    else:
        alerts = engine.make_single(rng, signature=body.get("signature"), service=body.get("service"))

    incidents = engine.process(alerts)
    return JSONResponse({
        "raw": [engine.alert_to_dict(a) for a in alerts],
        "incidents": [engine.incident_to_dict(i) for i in incidents],
    })


@app.post("/ingest/custom")
async def ingest_custom(req: Request):
    """Accept real/your own alerts. Each item needs the Alert fields; missing
    ones are defaulted so a minimal {service, signature, value} still works."""
    body = await req.json()
    items = body if isinstance(body, list) else body.get("alerts", [])
    rng = random.Random()
    alerts = []
    for it in items:
        svc = it.get("service", "api")
        sig = it.get("signature", "cpu_high")
        base = engine.make_single(rng, signature=sig, service=svc)[0]
        for k in ("value", "threshold", "host", "severity", "source", "unit", "metric"):
            if k in it:
                setattr(base, k, it[k])
        alerts.append(base)
    incidents = engine.process(alerts)
    return JSONResponse({
        "raw": [engine.alert_to_dict(a) for a in alerts],
        "incidents": [engine.incident_to_dict(i) for i in incidents],
    })
