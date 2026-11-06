# AlertBrief · Product Requirements
An AI layer that turns a raw alert into a briefed one, for the on-call engineer at 3am.
Status: Stage 1 and 2 built and tested. Working name: AlertBrief.

---

## 0. Why this exists

Ronald Czachara, co-founder of Derdack / SIGNL4, said in July:
> "Often engineers need all the information they can get to resolve an issue, especially in the middle of the night."

SIGNL4 delivers the right alert to the right person. It does not make the alert itself
smarter. The engineer still opens their phone to "DB CPU 98%" and has to reconstruct the
context half asleep. AlertBrief is the layer that fills that gap, and it is also the
artifact that reopens the Ronald conversation with a live link instead of a pitch.

## 1. The problem

At 3am the first ten minutes of every incident is the same manual work: what else is
firing, has this happened before, what usually causes it, where is the runbook, what do I
check first. A storm makes it worse: one failing dependency fires forty alerts and the
engineer has to work out by hand that they are one incident.

## 2. What it is

A briefing layer that turns a raw alert into a one-screen brief before it reaches the
person. For one alert: likely cause, first checks, matching runbook, related recent
alerts, weekly frequency. For a storm: many alerts collapse into one incident with one
brief. It is not a monitor, not a replacement for SIGNL4 delivery, and not
auto-remediation. Every brief is context for a human.

## 3. Requirements

| ID | Requirement | Status |
|---|---|---|
| R1 | Accept alerts as JSON, one or many | done |
| R2 | Correlate alerts into one incident by service dependency, deterministically | done |
| R3 | Attach related recent alerts + weekly frequency | done |
| R4 | Match incident to a runbook section from a config map | done |
| R5 | Produce a short brief: cause, first checks, runbook | done |
| R6 | Fabrication guard: no number/host/service in the brief that isn't in the facts | done |
| R7 | Deterministic fallback if the model is unavailable; never block the alert | done |
| R8 | One brief per incident, not per alert | done |
| R9 | Demo UI: raw vs briefed, fire-a-storm | done |
| R10 | Immutable enrichment log, UTC timestamps | partial (in-memory history) |
| R11 | outturn eval asserting brief ⊆ source facts | not yet (Stage 4) |

## 4. Architecture, doctrine applied

Deterministic spine first, model as an upgrade. Cheap pass first, a fallback for every
probabilistic path, fabrication guard.

```
raw alert(s)
  -> [1] DETERMINISTIC (code): correlate via the dependency graph, related alerts,
         frequency, runbook match. No LLM.
  -> [2] BRIEF: cause + first checks, chosen only from the facts step 1 attached.
         Guard rejects any invented number/host/service. No model or low confidence
         -> deterministic template brief. Never blocks the alert.
  -> enriched incident
```

## 5. Out of scope (this build)
Watching a real monitoring system, remediation, real customer data, auth/multi-tenant,
billing, replacing SIGNL4 delivery.

## 6. Principles
- Context, never action.
- Deterministic spine, model as upgrade (useful with the LLM off).
- Never invent at 3am. A wrong cause is worse than no cause.
- One buzz per incident.
- Synthetic and reproducible.
