# AlertBrief

A briefing layer for on-call alerts. The alert already reaches the right person; AlertBrief decides what they read when it does.

For every incident it answers four questions in one screen:

* **Is it real?** Computed from the alert and the team's own alert history: how often this fired this week, how often people acknowledged it, how often it cleared on its own within minutes.
* **What happened?** The sequence of events, taken from the alerts themselves.
* **What to check first.** General guidance for the alert type, filled in only with values from the alert.
* **What else is firing.** A storm of related alerts collapsed into one incident.

## Design rules

1. **Nothing configured per customer.** Correlation uses only the host names and timestamps inside the alerts. When an alert's message names another host (`connection refused to orders-db-01:5432`), that link is in the data already. The host most named by other alerts in the window is the root.
2. **Nothing invented.** Every line is tagged with where its facts came from: the alert, the alert history, a count made by code, or general guidance. Before a brief is shown, a guard extracts every name and number in it and checks each one against the source data. A model can rephrase a brief, but any sentence carrying a fact that is not in the source is rejected. The page shows an example of one being blocked.
3. **Users teach it what noise looks like.** The "is it real" verdict comes from what people already do in the alerting tool: acknowledging an alert versus letting it auto-resolve unread. A signature that fired 23 times this week, cleared by itself 21 times and was never acknowledged is marked as likely noise.
4. **Context, never action.** It briefs a person. It never remediates.

## Scenarios on the page

| Scenario | Pages | What the brief shows |
|---|---|---|
| Storm at 03:12 | 37 | A database runs out of memory and its process is killed. 36 alerts across 5 services become one incident with the root named. An unrelated certificate alert in the same window stays a separate, non-urgent incident. |
| Disk filling | 1 | A recurring disk alert, briefed with the resolution note people wrote the last three times. |
| Flapping CPU | 1 | A nightly spike that clears on its own, marked as likely noise, with the source-side change that would have skipped 21 of 23 pages. |

Alerts use the SIGNL4 inbound webhook shape (`Title`, `Message`, free fields, `X-S4-Service`, `X-S4-ExternalID`, `X-S4-Status`, `X-S4-AlertingScenario`).

## Run it

It is one static file with no build step and no server. Open `index.html` in a browser, or publish it with GitHub Pages.

All data is synthetic. No real system is represented.

Built by Omons Wisdom (Osas) · github.com/OsasDTEch · omonswisdom.ict@gmail.com
