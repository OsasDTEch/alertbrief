# AlertBrief · Project State
Last updated: 19 October 2026

## Status: Stage 1 and 2 built, tested, running locally. Not yet deployed.

## What is done

- **Deterministic engine (`engine.py`)**
  - Synthetic world: 8 services with a dependency graph, 8 alert signatures, a runbook map. All config-as-data.
  - Alert generator: single alerts and realistic storms (one root failure cascading into dependents).
  - Correlation: a batch of alerts is grouped into incidents; a cascade through the dependency graph collapses into ONE incident rooted at the shared dependency.
  - Enrichment: related alerts from the last hour, weekly frequency per signature, runbook match.
  - Brief: a deterministic template brief built only from facts, plus an optional Groq LLM path that only phrases those facts.
  - Fabrication guard: rejects any number/host/service in the brief that is not present in the fact bundle.
  - Root-cause alignment fix applied: the brief and runbook describe the ROOT service, not the loudest dependent alert.

- **API (`app.py`)** — FastAPI. `GET /` serves the demo; `POST /ingest` (single|storm); `POST /ingest/custom` takes SIGNL4-shaped JSON.

- **Demo UI (`index.html`)** — raw vs briefed side by side, "fire one alert" and "fire a storm" buttons.

- **Tested end to end:** single -> 1 briefed incident; storm of ~24 -> 1 incident across 6 services, correctly root-caused; guard rejects invented values; all endpoints 200.

## What is left

| Stage | Item | Notes |
|---|---|---|
| 3 | Deeper enrichment | more runbook signatures; related-alert ranking; richer brief across more alert types |
| 4 | outturn eval | assert no brief states a fact absent from its source bundle; this is the credibility layer and the story for the Slack/David |
| 5 | Deploy | uvicorn + nginx + DuckDNS like HeatDesk, so it is a live clickable link |
| - | Persistence | the enrichment history is in-memory; move to Postgres for a real immutable audit trail |
| - | Real ingest | wire to an actual SIGNL4 inbound webhook (currently synthetic + /ingest/custom) |

## The next action that matters
Deploy Stage 1+2 to a live link, then message Ronald: "you said engineers need everything
they can get at 3am, so I built it," with the link. The build is ready for that; it only
needs deploying.
