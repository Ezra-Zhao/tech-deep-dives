"""Anti-blind alert bench for net-assurance-lab (2026-10-27 article).

Offline, deterministic part of the experiment. The live timing part is
2026-10-27-blind-live.py; this script covers what can be settled
without a clock:

  A. Parse the candidate rule file (data/2026-10-27-blind-alerts-
     candidate.yml) and the lab's own alerts.yml; confirm the existing
     rule was copied verbatim and all three candidate rules share
     for: 1m.
  B. Truth table: model the series visible to an instant PromQL query
     in four states -- healthy; artifacts deleted while the exporter
     lives; exporter killed, still inside the 5-minute lookback window;
     exporter killed, past the lookback window -- and evaluate each
     candidate expression with faithful semantics:
       * `up` is synthesised by Prometheus per target: 1 after a good
         scrape, 0 after a failed one; it never comes from the
         exporter, so it survives the exporter's death.
       * nal_exporter_results_present is exporter-rendered: while the
         exporter lives it is re-rendered every scrape (0 when a group
         fails to load); once the exporter dies the last sample (1)
         stays visible to instant queries for the lookback delta
         (default 5m), then the series is empty.
       * absent(v) is 1 exactly when the instant vector v is empty.
     An expression "can fire" in a state when it yields a non-empty
     result there (for: only adds time; it cannot create a result).
  C. Theoretical blind-window budget per rule and death mode, from the
     deployed timing parameters: scrape interval 5s, rule-group
     evaluation interval 15s, for: 60s, lookback delta 300s. A rule
     whose expression is empty in a state has an unbounded window in
     that state; the budget is the interval [best, worst] for the
     rules that can fire.

Output: data/2026-10-27-blind-alert-bench.json
No network, no live processes, no repo modification.
"""
import json
import os
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.expanduser("~/workspace/oxide-proofs/net-assurance-lab")

OUT = {"generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z")}

# ------------------------------------------------------------------ A
with open(os.path.join(HERE, "2026-10-27-blind-alerts-candidate.yml"),
          encoding="utf-8") as f:
    cand = yaml.safe_load(f)
GROUP = cand["groups"][0]
RULES = GROUP["rules"]
OUT["candidate_group"] = {"name": GROUP["name"],
                          "interval": GROUP.get("interval"),
                          "count": len(RULES)}
OUT["candidate_rules"] = [
    {"alert": r["alert"], "expr": " ".join(r["expr"].split()),
     "for": r.get("for"), "severity": r["labels"]["severity"]}
    for r in RULES]

with open(os.path.join(LAB, "monitoring", "rules", "alerts.yml"),
          encoding="utf-8") as f:
    lab_rules = yaml.safe_load(f)["groups"][0]["rules"]
lab_missing = next(r for r in lab_rules
                   if r["alert"] == "NalExporterResultsMissing")
cand_missing = next(r for r in RULES
                    if r["alert"] == "NalExporterResultsMissing")
OUT["existing_rule_verbatim"] = {
    "expr_equal": " ".join(lab_missing["expr"].split())
    == " ".join(cand_missing["expr"].split()),
    "for_equal": lab_missing.get("for") == cand_missing.get("for"),
    "labels_equal": lab_missing["labels"] == cand_missing["labels"],
    "annotations_equal": lab_missing["annotations"]
    == cand_missing["annotations"],
}

with open(os.path.join(LAB, "monitoring", "prometheus.yml"),
          encoding="utf-8") as f:
    prom_cfg = yaml.safe_load(f)
OUT["lab_prometheus_config"] = {
    "scrape_interval": prom_cfg["global"]["scrape_interval"],
    "scrape_timeout": prom_cfg["global"].get("scrape_timeout"),
    "evaluation_interval_global": prom_cfg["global"]["evaluation_interval"],
    "alertmanagers": prom_cfg.get("alerting", {}).get("alertmanagers"),
}

# ------------------------------------------------------------------ B
# Series model per state. present: dict group -> value, or None when the
# series has no visible sample at query time (past lookback / never
# scraped). up: 0/1 (always exists while the target is configured).
STATES = {
    "healthy": {
        "desc": "Exporter alive, complete artifact set.",
        "up": 1,
        "present": {"scenario_summaries": 1, "run_meta": 1,
                    "fault_proxy_log": 1},
    },
    "artifacts_deleted_exporter_alive": {
        "desc": "One scenario summary deleted; exporter alive and "
                "scraped; the scenario_summaries group flips to 0.",
        "up": 1,
        "present": {"scenario_summaries": 0, "run_meta": 1,
                    "fault_proxy_log": 1},
    },
    "exporter_killed_within_lookback": {
        "desc": "Exporter dead <5m: up already 0, but the last present "
                "sample (1) is still inside the lookback window.",
        "up": 0,
        "present": {"scenario_summaries": 1, "run_meta": 1,
                    "fault_proxy_log": 1},
    },
    "exporter_killed_past_lookback": {
        "desc": "Exporter dead >5m: every nal_* series has gone stale "
                "and vanished from instant queries; up stays 0.",
        "up": 0,
        "present": None,
    },
}


def eval_rule(alert, state):
    """Return (can_fire, detail) for one candidate rule in one state."""
    if alert == "NalExporterResultsMissing":
        present = state["present"]
        if present is None:
            return False, "series empty: == 0 yields no result"
        hits = [g for g, v in present.items() if v == 0]
        return (bool(hits), f"groups at 0: {hits}")
    if alert == "NalExporterDown":
        return (state["up"] == 0, f"up = {state['up']}")
    if alert == "NalExporterSeriesAbsent":
        present = state["present"]
        empty = present is None or "scenario_summaries" not in present
        return (empty, "instant vector empty" if empty
                else "series still visible")
    raise ValueError(alert)


truth = {}
for state_name, state in STATES.items():
    row = {"desc": state["desc"], "rules": {}}
    for r in RULES:
        can, detail = eval_rule(r["alert"], state)
        row["rules"][r["alert"]] = {"can_fire": can, "detail": detail}
    truth[state_name] = row
OUT["truth_table"] = truth

# ------------------------------------------------------------------ C
SCRAPE_S, EVAL_S, FOR_S, LOOKBACK_S = 5, 15, 60, 300


def budget(can_fire_early, needs_staleness):
    """[best, worst] seconds from the death event to firing.

    best: the event lands just before a scrape/evaluation boundary.
    worst: it lands just after one, paying a full scrape interval plus
    a full evaluation interval on top of for: (and of the lookback
    delta on the staleness path). Unbounded when the expression can
    never produce a result in the state.
    """
    if not can_fire_early and not needs_staleness:
        return None
    base = LOOKBACK_S if needs_staleness else 0
    return [base + FOR_S, base + SCRAPE_S + EVAL_S + FOR_S]


OUT["timing_parameters"] = {
    "scrape_interval_s": SCRAPE_S, "rule_group_interval_s": EVAL_S,
    "for_s": FOR_S, "lookback_delta_s_default": LOOKBACK_S,
}
OUT["theoretical_blind_windows"] = {
    "artifacts_deleted": {
        "NalExporterResultsMissing": budget(True, False),
        "NalExporterDown": None,
        "NalExporterSeriesAbsent": None,
    },
    "exporter_killed": {
        "NalExporterResultsMissing": None,
        "NalExporterDown": budget(True, False),
        "NalExporterSeriesAbsent": budget(False, True),
    },
}

with open(os.path.join(HERE, "2026-10-27-blind-alert-bench.json"), "w",
          encoding="utf-8") as f:
    json.dump(OUT, f, ensure_ascii=False, indent=1)
print(json.dumps({
    "verbatim": OUT["existing_rule_verbatim"],
    "truth": {s: {a: v["can_fire"] for a, v in row["rules"].items()}
              for s, row in truth.items()},
    "windows": OUT["theoretical_blind_windows"],
}, ensure_ascii=False, indent=1))
