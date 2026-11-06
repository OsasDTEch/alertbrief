# AlertBrief, explained

Written for you, plain. What it is, how it works, why it's built this way, and how to run it.

## The one-sentence version

On-call tools like SIGNL4 get the right alert to the right person. AlertBrief makes that
alert worth reading: it turns a raw "DB CPU 98%" into a briefed incident with a likely
cause, the first things to check, and the matching runbook, and when a storm of alerts
fires it collapses them into one page instead of forty.

## Why it exists

Ronald (SIGNL4 co-founder) told you the real pain: engineers need all the info they can
get, especially in the middle of the night. This is the thing that gives it to them. It's
also your next live artifact, the one you send him instead of a pitch.

## How it works, in three steps

**Step 1, deterministic (code, no AI).** This is the spine.
- It knows a small service map: api depends on db and cache, worker depends on queue, and
  so on. That map is how it reasons about cause.
- When alerts come in, it **correlates** them: if api, auth and search all scream right
  after db fails, the code works out they're all downstream of db and groups them into
  ONE incident rooted at db.
- It then **enriches**: pulls related alerts from the last hour, counts how often this
  fired in the last week, and matches a runbook section from a simple lookup table.

**Step 2, the brief.** Now it writes the human-readable part: likely cause + first checks.
- By default this is a **template** built straight from the facts in step 1. No AI needed,
  always correct, a little stiff.
- Optionally, if you set a `GROQ_API_KEY`, an LLM phrases it more naturally, **but** it's
  only allowed to use facts step 1 produced.

**Step 3, the fabrication guard.** This is the part that's very you.
- Before any brief is shown, a guard checks every number, host and service name in it
  against the facts. If the model invented a figure or a hostname, the guard throws it out
  and falls back to the safe template. A confidently wrong brief at 3am is worse than no
  brief, so it simply cannot invent.

## Why it's built this way (your doctrine, in code)

- **Deterministic before probabilistic.** With the AI switched off entirely, you still get
  a correlated incident, a runbook and related alerts. The model is an upgrade, not a
  dependency.
- **The model never computes.** It phrases facts; it never produces a number. Numbers come
  from the alert, always.
- **A fallback for every AI path.** Model down, slow, or it invented something -> the
  template brief is used. The alert is never blocked or dropped.
- **Config as data.** The service map and the runbook map are plain dictionaries you edit
  without touching logic.

## What you actually see

- **Fire one alert**: a raw warning on the left, a briefed incident on the right.
- **Fire a storm**: ~24 raw alerts on the left, one briefed incident on the right, correctly
  blamed on the single root service. That collapse is the moment that sells it.

## How to run it

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8080
# open http://localhost:8080
```

No keys needed. To let an LLM phrase the briefs, copy `.env.example` to `.env`, add a
`GROQ_API_KEY`, and `export` it before running.

## Feeding it real alerts

`POST /ingest/custom` with a list like:
```json
[{"service":"db","signature":"conn_pool","value":97.0,"host":"db-1.prod"}]
```
Signatures available: cpu_high, mem_high, disk_full, latency_high, error_rate_high,
conn_pool, replica_lag, queue_backlog.

## What's built vs not (short version)

Built and tested: the whole deterministic engine, the brief + guard, the API, the demo UI,
single + storm. Not yet: an outturn eval over the briefs, a real database for history, a
live SIGNL4 webhook, and deployment to a public link. See PROJECT_STATE.md for the full
list.

## The point of all this

Deploy it to a live link, send Ronald "you said engineers need everything they can get at
3am, so I built it," and you've turned a cold thread into a warm one with a working demo,
not a pitch. It also retires the dead DispatchIQ link as your alerting artifact.
