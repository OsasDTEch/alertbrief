"""
AlertBrief engine. Deterministic spine first, model as an upgrade.

Pipeline per the spec:
  raw alert(s)
    -> [1] DETERMINISTIC (code): correlate into incidents, pull related alerts,
           frequency stats, match runbook section
    -> [2] BRIEF: a likely cause + first checks, chosen ONLY from facts the code
           attached. Fabrication guard rejects any claim not backed by those facts.
           If the (optional) LLM is unavailable or low-confidence, a deterministic
           template brief is produced instead. Never blocks the alert.
    -> enriched incident

Synthetic data throughout. No real system is represented.
"""

from __future__ import annotations

import os
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

# --------------------------------------------------------------------------- config as data

# A tiny service dependency graph. "api depends on db" means a db failure
# can cascade into api alerts. This is the correlation backbone.
SERVICES = ["api", "web", "worker", "db", "cache", "queue", "auth", "search"]

DEPENDS_ON = {
    "api":    ["db", "cache", "auth"],
    "web":    ["api", "auth"],
    "worker": ["queue", "db"],
    "auth":   ["db"],
    "search": ["db"],
    # db, cache, queue are leaf infrastructure
}

# Alert signatures -> runbook section. Config, not code.
RUNBOOK = {
    "cpu_high":        ("Runbook 3.1 CPU saturation", "Check top processes, recent deploys, and request rate. Scale out if sustained."),
    "mem_high":        ("Runbook 3.2 Memory pressure", "Check for leaks and cache growth; restart the leaking worker if RSS keeps climbing."),
    "disk_full":       ("Runbook 4.0 Disk pressure", "Clear old logs and build artifacts; expand the volume if under 10% free."),
    "latency_high":    ("Runbook 5.2 Latency", "Check downstream dependency health and connection-pool saturation before touching the app."),
    "error_rate_high": ("Runbook 6.1 Error spike", "Correlate with the most recent deploy; check dependency errors and roll back if the spike started at a release."),
    "conn_pool":       ("Runbook 5.4 Connection pool exhausted", "Check for slow queries holding connections; raise pool size only after the slow query is found."),
    "replica_lag":     ("Runbook 7.3 Replica lag", "Check write volume and long transactions on the primary; route reads to primary if lag exceeds threshold."),
    "queue_backlog":   ("Runbook 8.1 Queue backlog", "Check consumer health and scale consumers; inspect for poison messages blocking the head."),
}

# Which signatures each service can emit, to keep synthetic alerts realistic.
SERVICE_SIGNATURES = {
    "api":    ["latency_high", "error_rate_high", "cpu_high", "conn_pool"],
    "web":    ["latency_high", "error_rate_high", "cpu_high"],
    "worker": ["cpu_high", "mem_high", "queue_backlog"],
    "db":     ["cpu_high", "disk_full", "conn_pool", "replica_lag"],
    "cache":  ["mem_high", "latency_high"],
    "queue":  ["queue_backlog", "disk_full"],
    "auth":   ["latency_high", "error_rate_high"],
    "search": ["latency_high", "cpu_high"],
}

SEVERITY = ["warning", "critical"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- data model

@dataclass
class Alert:
    id: str
    service: str
    signature: str          # e.g. cpu_high
    metric: str             # human label
    value: float
    threshold: float
    unit: str
    severity: str
    host: str
    source: str             # which monitoring tool emitted it
    ts: str                 # UTC ISO

    def summary(self) -> str:
        return f"{self.service} {self.metric} {self.value}{self.unit} (threshold {self.threshold}{self.unit}) on {self.host}"


@dataclass
class Incident:
    id: str
    root_service: str
    alerts: list[Alert]
    related_recent: list[str] = field(default_factory=list)   # ids seen in last hour
    frequency_7d: int = 0
    runbook_title: str = ""
    runbook_text: str = ""
    brief: dict = field(default_factory=dict)                 # {cause, checks, source, confidence}

    def primary(self) -> Alert:
        # the alert ON the root service represents the incident; among those,
        # the most severe and highest-value. This keeps the cause and runbook
        # aligned with the root cause, not the loudest dependent alert.
        return sorted(
            self.alerts,
            key=lambda a: (a.service == self.root_service, a.severity == "critical", a.value),
            reverse=True,
        )[0]


# --------------------------------------------------------------------------- synthetic generation

_METRIC = {
    "cpu_high":        ("CPU", "%", 90),
    "mem_high":        ("memory", "%", 85),
    "disk_full":       ("disk used", "%", 90),
    "latency_high":    ("p99 latency", "ms", 500),
    "error_rate_high": ("error rate", "%", 2),
    "conn_pool":       ("connection pool in use", "%", 90),
    "replica_lag":     ("replica lag", "s", 10),
    "queue_backlog":   ("queue depth", " msgs", 1000),
}
_SOURCES = ["Prometheus", "Datadog", "CloudWatch", "Grafana"]


def _mk_alert(rng: random.Random, service: str, signature: str) -> Alert:
    metric, unit, thresh = _METRIC[signature]
    over = rng.uniform(1.05, 1.8)
    value = round(thresh * over, 1)
    return Alert(
        id=f"alt-{rng.randrange(16**6):06x}",
        service=service,
        signature=signature,
        metric=metric,
        value=value,
        threshold=float(thresh),
        unit=unit,
        severity="critical" if over > 1.4 else "warning",
        host=f"{service}-{rng.randrange(1,6)}.prod",
        source=rng.choice(_SOURCES),
        ts=_utc_now().isoformat(),
    )


def make_single(rng: random.Random, signature: Optional[str] = None, service: Optional[str] = None) -> list[Alert]:
    service = service or rng.choice(SERVICES)
    signature = signature or rng.choice(SERVICE_SIGNATURES[service])
    return [_mk_alert(rng, service, signature)]


def make_storm(rng: random.Random, root: Optional[str] = None) -> list[Alert]:
    """One root infra failure cascading into every dependent service."""
    root = root or rng.choice(["db", "cache", "queue"])
    root_sig = {"db": "conn_pool", "cache": "mem_high", "queue": "queue_backlog"}[root]
    alerts = [_mk_alert(rng, root, root_sig)]
    # everything that depends (directly or transitively) on root lights up
    dependents = [s for s, deps in DEPENDS_ON.items() if root in deps]
    second = []
    for s, deps in DEPENDS_ON.items():
        if any(d in dependents for d in deps):
            second.append(s)
    cascade = dependents + second
    for s in cascade:
        for _ in range(rng.randint(2, 5)):
            sig = "latency_high" if "latency_high" in SERVICE_SIGNATURES[s] else rng.choice(SERVICE_SIGNATURES[s])
            alerts.append(_mk_alert(rng, s, sig))
    rng.shuffle(alerts)
    return alerts


# --------------------------------------------------------------------------- [1] deterministic correlation + enrichment

def _root_of(services_present: set[str]) -> str:
    """The service in the set that the most others depend on is the likely root."""
    score = Counter()
    for s in services_present:
        for dep in DEPENDS_ON.get(s, []):
            if dep in services_present:
                score[dep] += 1
    if score:
        return score.most_common(1)[0][0]
    return sorted(services_present)[0]


def correlate(alerts: list[Alert]) -> list[Incident]:
    """Group a batch of alerts into incidents. A cascade through the dependency
    graph collapses into ONE incident rooted at the shared dependency."""
    if not alerts:
        return []
    services_present = {a.service for a in alerts}
    root = _root_of(services_present)

    # Alerts on the root, plus alerts on services that (transitively) depend on it,
    # belong to one incident. Anything unrelated becomes its own incident.
    def depends_on_root(service: str, seen=None) -> bool:
        seen = seen or set()
        if service in seen:
            return False
        seen.add(service)
        deps = DEPENDS_ON.get(service, [])
        if root in deps:
            return True
        return any(depends_on_root(d, seen) for d in deps)

    in_cascade, others = [], defaultdict(list)
    for a in alerts:
        if a.service == root or depends_on_root(a.service):
            in_cascade.append(a)
        else:
            others[a.service].append(a)

    incidents: list[Incident] = []
    if in_cascade:
        incidents.append(Incident(id=f"inc-{int(time.time()*1000)%10**8:08d}", root_service=root, alerts=in_cascade))
    for svc, group in others.items():
        incidents.append(Incident(id=f"inc-{random.randrange(16**8):08x}", root_service=svc, alerts=group))
    return incidents


# a tiny in-memory history so "related recent" and "frequency" are real, not faked
_HISTORY: list[tuple[datetime, str, str]] = []   # (ts, service, signature)


def enrich(inc: Incident) -> Incident:
    now = _utc_now()
    primary = inc.primary()

    # frequency over the last 7 days for this signature on this service
    inc.frequency_7d = sum(
        1 for (ts, svc, sig) in _HISTORY
        if svc == primary.service and sig == primary.signature and ts > now - timedelta(days=7)
    )
    # related alerts in the last hour (any service)
    inc.related_recent = [
        f"{svc} {sig}" for (ts, svc, sig) in _HISTORY
        if ts > now - timedelta(hours=1)
    ][-5:]

    # runbook match from the primary signature
    title, text = RUNBOOK.get(primary.signature, ("No runbook matched", ""))
    inc.runbook_title, inc.runbook_text = title, text

    # record this incident's alerts into history for future enrichment
    for a in inc.alerts:
        _HISTORY.append((now, a.service, a.signature))
    return inc


# --------------------------------------------------------------------------- [2] brief, with fabrication guard + deterministic fallback

def _fact_bundle(inc: Incident) -> dict:
    """Everything the brief is ALLOWED to reference. The guard checks against this."""
    p = inc.primary()
    return {
        "root_service": inc.root_service,
        "primary_signature": p.signature,
        "primary_metric": p.metric,
        "primary_value": f"{p.value}{p.unit}",
        "threshold": f"{p.threshold}{p.unit}",
        "severity": p.severity,
        "host": p.host,
        "alert_count": len(inc.alerts),
        "affected_services": sorted({a.service for a in inc.alerts}),
        "runbook_title": inc.runbook_title,
        "runbook_text": inc.runbook_text,
        "frequency_7d": inc.frequency_7d,
        "related_recent": inc.related_recent,
    }


def _deterministic_brief(inc: Incident, facts: dict) -> dict:
    """Template brief built only from facts. Always correct, never invented."""
    p = inc.primary()
    svcs = facts["affected_services"]
    if len(svcs) > 1:
        cause = (f"{facts['alert_count']} alerts across {', '.join(svcs)} correlate to a "
                 f"{facts['root_service']} problem ({facts['primary_signature']}). "
                 f"The dependent services are most likely reacting to {facts['root_service']}, not failing on their own.")
    else:
        cause = (f"{facts['root_service']} {facts['primary_metric']} is {facts['primary_value']} "
                 f"against a {facts['threshold']} threshold on {facts['host']}.")
    checks = []
    if facts["runbook_text"]:
        checks.append(facts["runbook_text"])
    checks.append(f"Confirm on {facts['host']} first, it is the alert that fired hardest.")
    if facts["frequency_7d"]:
        checks.append(f"This signature fired {facts['frequency_7d']} time(s) in the last 7 days, check whether a known pattern is recurring.")
    return {
        "cause": cause,
        "checks": checks,
        "source": "deterministic",
        "confidence": "grounded",
    }


def _guard(text: str, facts: dict) -> bool:
    """Fabrication guard: every concrete token the model emitted (numbers, hosts,
    service names) must appear in the fact bundle. If it invents one, reject."""
    import re
    flat = " ".join(str(v) for v in _flatten(facts)).lower()
    # numbers and host-like / service tokens the model used
    tokens = re.findall(r"[a-z0-9][a-z0-9._-]*%?|\d+\.?\d*\w*", text.lower())
    suspicious = [t for t in tokens if (any(ch.isdigit() for ch in t) or t in SERVICES or ".prod" in t)]
    for t in suspicious:
        if t not in flat:
            return False
    return True


def _flatten(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _flatten(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _flatten(v)
    else:
        yield x


def _llm_brief(inc: Incident, facts: dict) -> Optional[dict]:
    """Optional. Uses Groq if GROQ_API_KEY is set, else returns None so the
    deterministic brief is used. The model only phrases; it computes nothing."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        import json, urllib.request
        prompt = (
            "You are an on-call assistant. Using ONLY the facts in this JSON, write a one-line "
            "likely cause and 2-3 short first-check steps. Do not invent any number, host, or "
            "service not present in the facts. Return JSON {\"cause\":..., \"checks\":[...]}.\n\n"
            + json.dumps(facts)
        )
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
        content = json.loads(out["choices"][0]["message"]["content"])
        cause = str(content.get("cause", ""))
        checks = [str(c) for c in content.get("checks", [])]
        # fabrication guard: reject anything not grounded in the facts
        if not _guard(cause + " " + " ".join(checks), facts):
            return None
        return {"cause": cause, "checks": checks, "source": "llm", "confidence": "grounded"}
    except Exception:
        return None   # deterministic fallback for every probabilistic path


def brief(inc: Incident) -> Incident:
    facts = _fact_bundle(inc)
    inc.brief = _llm_brief(inc, facts) or _deterministic_brief(inc, facts)
    return inc


# --------------------------------------------------------------------------- top-level

def process(alerts: list[Alert]) -> list[Incident]:
    incidents = correlate(alerts)
    out = []
    for inc in incidents:
        out.append(brief(enrich(inc)))
    return out


def alert_to_dict(a: Alert) -> dict:
    return asdict(a)


def incident_to_dict(inc: Incident) -> dict:
    return {
        "id": inc.id,
        "root_service": inc.root_service,
        "alert_count": len(inc.alerts),
        "affected_services": sorted({a.service for a in inc.alerts}),
        "primary": asdict(inc.primary()),
        "alerts": [asdict(a) for a in inc.alerts],
        "related_recent": inc.related_recent,
        "frequency_7d": inc.frequency_7d,
        "runbook_title": inc.runbook_title,
        "brief": inc.brief,
    }
