"""Alert-chain bench for net-assurance-lab (2026-10-24 article).

Deterministic, offline part of the experiment:
  A. Parse the 10 alert rules from monitoring/rules/alerts.yml.
  B. Collect exporter metrics for two archived real runs and evaluate
     every rule twice: by *intent* (direct computation from the run
     artifacts) and by *PromQL semantics* (faithful vector matching:
     a binary vector-vector operation matches series only when their
     label sets are identical, Prometheus default).
  C. Boundary fixtures: synthetic results dirs that flip each rule's
     underlying condition just below / at / just above its threshold,
     pushed through the real exporter collect() code path.
  D. for:/recovery state machine simulation at the rules-group
     evaluation interval (15 s).
  E. Dashboard reconciliation: all panel targets of both Grafana
     dashboards checked against the exporter output of run R0 and
     against the underlying JSON artifacts.

Output: data/2026-10-24-alert-chain-bench.json
No network, no repo modification; fixtures live in a temp dir.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time

import yaml

LAB = os.path.expanduser("~/workspace/oxide-proofs/net-assurance-lab")
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "prom_exporter", os.path.join(LAB, "src", "prom_exporter.py"))
EXP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXP)
FAULT_CFG = {"loss_ratio": 0.2, "delay_ms": 40.0, "jitter_ms": 30.0,
             "flap_period_s": 2.5, "flap_down_s": 0.6}

OUT = {"generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
       "lab": LAB}

# ---------------------------------------------------------------- rules
with open(os.path.join(LAB, "monitoring", "rules", "alerts.yml"),
          encoding="utf-8") as f:
    rules_doc = yaml.safe_load(f)
GROUP = rules_doc["groups"][0]
RULES = GROUP["rules"]
OUT["rules_group"] = {"name": GROUP["name"], "interval": GROUP.get("interval"),
                      "count": len(RULES)}
OUT["rules"] = [{"alert": r["alert"], "expr": " ".join(r["expr"].split()),
                 "for": r.get("for"), "severity": r["labels"]["severity"]}
                for r in RULES]

with open(os.path.join(LAB, "monitoring", "prometheus.yml"),
          encoding="utf-8") as f:
    prom_cfg = yaml.safe_load(f)
OUT["prometheus_config"] = {
    "scrape_interval": prom_cfg["global"]["scrape_interval"],
    "evaluation_interval": prom_cfg["global"]["evaluation_interval"],
    "alertmanagers": prom_cfg.get("alerting", {}).get("alertmanagers"),
    "rule_files": prom_cfg.get("rule_files"),
}

# ------------------------------------------------------- exposition parse
SERIES_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+(\S+)$')
LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def parse_exposition(text):
    series = []  # (metric, labels dict, value)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = SERIES_RE.match(line)
        if not m:
            continue
        labels = dict(LABEL_RE.findall(m.group(2) or ""))
        try:
            value = float(m.group(3))
        except ValueError:
            continue
        series.append((m.group(1), labels, value))
    return series


def select(series, metric, matchers):
    """matchers: dict label -> ('='|'=~', value)"""
    out = []
    for name, labels, value in series:
        if name != metric:
            continue
        ok = True
        for lab, (op, want) in matchers.items():
            got = labels.get(lab)
            if got is None:
                ok = False
                break
            if op == "=" and got != want:
                ok = False
                break
            if op == "=~" and not re.fullmatch(want, got):
                ok = False
                break
        if ok:
            out.append((labels, value))
    return out


def parse_for_seconds(text):
    if text is None:
        return 0
    m = re.fullmatch(r"\s*(?:(\d+)m)?\s*(?:(\d+)s)?\s*", str(text))
    if not m or (m.group(1) is None and m.group(2) is None):
        return 0
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


# -------------------------------------------- PromQL-faithful evaluation
def eval_promql(rule_alert, series):
    """Evaluate the rule's expr with Prometheus vector-matching semantics.

    Returns list of (labels, value) series for which the expression
    yields a result (i.e. alert instances in pending/firing state).
    Only the expression shapes present in alerts.yml are supported;
    anything else raises, so a silent mis-evaluation cannot pass.
    """
    if rule_alert == "NalBaselineHighPacketLoss":
        return [(l, v) for l, v in select(
            series, "nal_loss_ratio", {"scenario": ("=~", "baseline_.*")})
            if v > 0.05]
    if rule_alert == "NalBaselineP99LatencyHigh":
        return [(l, v) for l, v in select(
            series, "nal_rtt_ms",
            {"scenario": ("=~", "baseline_.*"), "stat": ("=", "p99")})
            if v > 50]
    if rule_alert == "NalBaselineThroughputCollapse":
        echo = select(series, "nal_throughput_pps",
                      {"kind": ("=", "echo"), "scenario": ("=~", "baseline_.*")})
        send = select(series, "nal_throughput_pps",
                      {"kind": ("=", "send"), "scenario": ("=~", "baseline_.*")})
        # Default vector matching: label sets must be identical.
        send_by_labels = {tuple(sorted(l.items())): v for l, v in send}
        return [(l, v) for l, v in echo
                if tuple(sorted(l.items())) in send_by_labels
                and v < 0.5 * send_by_labels[tuple(sorted(l.items()))]]
    if rule_alert == "NalFaultLossAboveInjectionBand":
        return [(l, v) for l, v in select(
            series, "nal_loss_ratio", {"scenario": ("=", "fault_sustained")})
            if v > 0.75]
    if rule_alert == "NalFaultP99LatencyExtreme":
        return [(l, v) for l, v in select(
            series, "nal_rtt_ms",
            {"scenario": ("=", "fault_sustained"), "stat": ("=", "p99")})
            if v > 1000]
    if rule_alert == "NalLinkFlapDetected":
        return [(l, v) for l, v in select(series, "nal_link_flap_detected", {})
                if v == 1]
    if rule_alert == "NalFlapShareDominatesLoss":
        flap = select(series, "nal_fault_proxy_drop_ratio",
                      {"cause": ("=", "flap")})
        loss = select(series, "nal_fault_proxy_drop_ratio",
                      {"cause": ("=", "loss")})
        loss_by_labels = {tuple(sorted(l.items())): v for l, v in loss}
        return [(l, v) for l, v in flap
                if tuple(sorted(l.items())) in loss_by_labels
                and v > loss_by_labels[tuple(sorted(l.items()))]]
    if rule_alert == "NalMalformedPacketEchoed":
        return [(l, v) for l, v in select(
            series, "nal_malformed_echoed_total", {}) if v > 0]
    if rule_alert == "NalResultsStale":
        return [(l, v) for l, v in select(
            series, "nal_results_age_seconds", {}) if v > 86400]
    if rule_alert == "NalExporterResultsMissing":
        return [(l, v) for l, v in select(
            series, "nal_exporter_results_present", {}) if v == 0]
    raise ValueError(f"unsupported rule {rule_alert}")


def eval_promql_corrected(rule_alert, series):
    """The two binary-op rules with ignoring() added (proposed fix)."""
    if rule_alert == "NalBaselineThroughputCollapse":
        echo = select(series, "nal_throughput_pps",
                      {"kind": ("=", "echo"), "scenario": ("=~", "baseline_.*")})
        send = {(l.get("scenario"), l.get("mode")): v for l, v in select(
            series, "nal_throughput_pps",
            {"kind": ("=", "send"), "scenario": ("=~", "baseline_.*")})}
        return [(l, v) for l, v in echo
                if (l.get("scenario"), l.get("mode")) in send
                and v < 0.5 * send[(l.get("scenario"), l.get("mode"))]]
    if rule_alert == "NalFlapShareDominatesLoss":
        flap = select(series, "nal_fault_proxy_drop_ratio", {"cause": ("=", "flap")})
        loss = select(series, "nal_fault_proxy_drop_ratio", {"cause": ("=", "loss")})
        if flap and loss:
            return [(l, v) for l, v in flap if v > loss[0][1]]
        return []
    return eval_promql(rule_alert, series)


# ------------------------------------------------------- intent evaluation
def intent_from_artifacts(results_dir):
    """What the rule author meant, computed straight from the artifacts."""
    def load(name):
        with open(os.path.join(results_dir, name), encoding="utf-8") as f:
            return json.load(f)
    intent = {}
    baselines = {}
    for sc in ("baseline_burst", "baseline_sustained"):
        d = load(f"{sc}.json")["all_packets"]
        baselines[sc] = d
    fault = load("fault_sustained.json")["all_packets"]
    malformed = load("malformed.json")
    proxy = None
    with open(os.path.join(results_dir, "fault_proxy_log.jsonl"),
              encoding="utf-8") as f:
        for line in f:
            if '"summary"' in line:
                proxy = json.loads(line)["summary"]
    total_in = proxy["in_client"] + proxy["in_server"]
    intent["NalBaselineHighPacketLoss"] = {
        sc: baselines[sc]["loss_rate"] for sc in baselines}
    intent["NalBaselineP99LatencyHigh"] = {
        sc: baselines[sc]["rtt_ms"]["p99"] for sc in baselines}
    intent["NalBaselineThroughputCollapse"] = {
        sc: {"echo": baselines[sc]["echo_throughput_pps"],
             "send": baselines[sc]["throughput_pps"],
             "ratio": (baselines[sc]["echo_throughput_pps"] /
                       baselines[sc]["throughput_pps"]
                       if baselines[sc]["throughput_pps"] else None)}
        for sc in baselines}
    intent["NalFaultLossAboveInjectionBand"] = fault["loss_rate"]
    intent["NalFaultP99LatencyExtreme"] = fault["rtt_ms"]["p99"]
    intent["NalLinkFlapDetected"] = proxy["dropped_flap"]
    intent["NalFlapShareDominatesLoss"] = {
        "flap_ratio": proxy["dropped_flap"] / total_in,
        "loss_ratio": proxy["dropped_loss"] / total_in,
        "dropped_flap": proxy["dropped_flap"],
        "dropped_loss": proxy["dropped_loss"],
        "total_in": total_in}
    intent["NalMalformedPacketEchoed"] = malformed["malformed_echoed"]
    return intent


def evaluate_run(run_dir, label):
    text = EXP.collect(run_dir, FAULT_CFG)
    series = parse_exposition(text)
    age = select(series, "nal_results_age_seconds", {})
    entry = {"run_dir": run_dir,
             "exporter_series_total": len(series),
             "results_age_seconds_at_eval": age[0][1] if age else None,
             "intent": intent_from_artifacts(run_dir),
             "promql": {}, "promql_corrected": {}}
    for r in RULES:
        name = r["alert"]
        hits = eval_promql(name, series)
        entry["promql"][name] = {
            "instances": len(hits),
            "values": [v for _, v in hits],
            "label_sets": [l for l, _ in hits]}
        hits_c = eval_promql_corrected(name, series)
        entry["promql_corrected"][name] = {
            "instances": len(hits_c), "values": [v for _, v in hits_c]}
    OUT.setdefault("runs", {})[label] = entry
    return entry


R0 = os.path.join(LAB, "results", "20261019-171627")   # latest
R1 = os.path.join(LAB, "results", "20261019-154535")   # first verified run
evaluate_run(R0, "R0_latest_20261019-171627")
evaluate_run(R1, "R1_first_20261019-154535")

# ------------------------------------------------------------- fixtures
def write_scenario(dirpath, name, sent=1000, echoed=1000, loss_rate=0.0,
                   p99=5.0, send_pps=1000.0, echo_pps=1000.0,
                   malformed_echoed=0):
    stats = {"sent": sent, "echoed": echoed, "lost": sent - echoed,
             "loss_rate": loss_rate, "throughput_pps": send_pps,
             "echo_throughput_pps": echo_pps, "wall_seconds": 1.0,
             "rtt_ms": {"min": 0.1, "mean": 1.0, "p50": 0.5, "p95": 2.0,
                        "p99": p99, "max": max(3.0, p99)}}
    doc = {"mode": "sustained", "packet_size_bytes": 256,
           "malformed_sent": 0, "malformed_echoed": malformed_echoed,
           "all_packets": stats, "valid_packets": stats}
    with open(os.path.join(dirpath, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    with open(os.path.join(dirpath, f"server_stats_{name}.json"), "w",
              encoding="utf-8") as f:
        json.dump({"received_total": echoed, "valid": echoed,
                   "malformed": 0, "echoed": echoed}, f)
    with open(os.path.join(dirpath, f"{name}.csv"), "w", encoding="utf-8") as f:
        f.write("seq,malformed_sent,echoed,rtt_ms\n0,0,1,0.5\n")


def make_fixture(tmp, run_id, baseline_loss=0.0, baseline_p99=5.0,
                 echo_ratio=1.0, fault_loss=0.5, fault_p99=400.0,
                 dropped_loss=100, dropped_flap=100, malformed_echoed=0,
                 omit_scenario=None):
    d = tempfile.mkdtemp(dir=tmp, prefix="fx-")
    for sc in EXP.SCENARIOS:
        if sc == omit_scenario:
            continue
        if sc.startswith("baseline"):
            write_scenario(d, sc, loss_rate=baseline_loss, p99=baseline_p99,
                           send_pps=1000.0, echo_pps=1000.0 * echo_ratio)
        elif sc == "fault_sustained":
            write_scenario(d, sc, loss_rate=fault_loss, p99=fault_p99)
        else:
            write_scenario(d, sc, malformed_echoed=malformed_echoed)
    with open(os.path.join(d, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "python": "3.12.3", "platform": "linux"}, f)
    with open(os.path.join(d, "fault_proxy_log.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"summary": {
            "in_client": 500, "in_server": 500,
            "dropped_loss": dropped_loss, "dropped_flap": dropped_flap,
            "forwarded": 1000 - dropped_loss - dropped_flap,
            "delayed": 1000 - dropped_loss - dropped_flap}}) + "\n")
    return d


TODAY_ID = time.strftime("%Y%m%d-%H%M%S")
YESTERDAY_ID = time.strftime("%Y%m%d-%H%M%S",
                             time.localtime(time.time() - 90000))
tmp = tempfile.mkdtemp(prefix="nal-bench-")
fixture_cases = [
    # (case name, fixture kwargs, rule, note)
    ("baseline_loss_at_threshold_0.05", dict(baseline_loss=0.05),
     "NalBaselineHighPacketLoss", "expr is >, equality must not fire"),
    ("baseline_loss_above_0.06", dict(baseline_loss=0.06),
     "NalBaselineHighPacketLoss", ""),
    ("baseline_p99_at_50", dict(baseline_p99=50.0),
     "NalBaselineP99LatencyHigh", "equality must not fire"),
    ("baseline_p99_above_60", dict(baseline_p99=60.0),
     "NalBaselineP99LatencyHigh", ""),
    ("throughput_collapse_extreme_echo_10pct", dict(echo_ratio=0.10),
     "NalBaselineThroughputCollapse",
     "intent condition strongly true (echo = 10% of send)"),
    ("fault_loss_at_0.75", dict(fault_loss=0.75),
     "NalFaultLossAboveInjectionBand", "equality must not fire"),
    ("fault_loss_above_0.80", dict(fault_loss=0.80),
     "NalFaultLossAboveInjectionBand", ""),
    ("fault_p99_at_1000", dict(fault_p99=1000.0),
     "NalFaultP99LatencyExtreme", "equality must not fire"),
    ("fault_p99_above_1200", dict(fault_p99=1200.0),
     "NalFaultP99LatencyExtreme", ""),
    ("flap_zero_drops", dict(dropped_flap=0),
     "NalLinkFlapDetected", "no flap drops -> detected must be 0"),
    ("flap_share_3x_loss", dict(dropped_loss=100, dropped_flap=300),
     "NalFlapShareDominatesLoss",
     "intent condition strongly true (flap share 0.3 vs loss share 0.1)"),
    ("malformed_echoed_1", dict(malformed_echoed=1),
     "NalMalformedPacketEchoed", "a single echoed malformed packet"),
    ("results_fresh_today", dict(run_id=TODAY_ID),
     "NalResultsStale", "run_id = now"),
    ("results_old_yesterday_plus", dict(run_id=YESTERDAY_ID),
     "NalResultsStale", "run_id = 25 h ago"),
    ("exporter_missing_one_scenario", dict(omit_scenario="malformed"),
     "NalExporterResultsMissing", "one scenario summary deleted"),
]
fx_out = []
for case_name, kwargs, rule, note in fixture_cases:
    kwargs.setdefault("run_id", TODAY_ID)
    d = make_fixture(tmp, **kwargs)
    series = parse_exposition(EXP.collect(d, FAULT_CFG))
    hits = eval_promql(rule, series)
    hits_c = eval_promql_corrected(rule, series)
    age = select(series, "nal_results_age_seconds", {})
    fx_out.append({"case": case_name, "rule": rule, "note": note,
                   "promql_instances": len(hits),
                   "promql_values": [v for _, v in hits],
                   "promql_corrected_instances": len(hits_c),
                   "promql_corrected_values": [v for _, v in hits_c],
                   "age_seconds": age[0][1] if age else None})
OUT["fixtures"] = fx_out
shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------- for: / recovery simulation
EVAL_S = 15  # rules group interval from alerts.yml


def simulate(rule_alert, timeline):
    """timeline: list of (t_seconds, condition_bool) change points,
    condition holds from its timestamp until the next change point.
    Prometheus semantics: at each evaluation, if the expression is true
    the alert is pending; it fires once it has been continuously true
    for the rule's for: duration; a false evaluation resets pending;
    a firing alert resolves at the first evaluation where the
    expression is false."""
    for_s = parse_for_seconds(
        next(r.get("for") for r in RULES if r["alert"] == rule_alert))
    events = []
    state = "inactive"
    true_since = None
    t_end = max(t for t, _ in timeline) + for_s + 90
    t = 0
    while t <= t_end:
        cond = False
        for tt, cc in timeline:
            if tt <= t:
                cond = cc
        if cond:
            if true_since is None:
                true_since = t
                state = "pending"
                events.append({"t": t, "event": "pending"})
            if state == "pending" and (t - true_since) >= for_s:
                state = "firing"
                events.append({"t": t, "event": "firing",
                               "held_seconds": t - true_since})
        else:
            if state in ("pending", "firing"):
                events.append({"t": t, "event": "resolved",
                               "was": state})
            state = "inactive"
            true_since = None
        t += EVAL_S
    return {"rule": rule_alert, "for_seconds": for_s, "events": events}


OUT["for_recovery_simulation"] = {
    "eval_interval_seconds": EVAL_S,
    "sustained_true_firing_delay_per_rule": [
        {"rule": r["alert"], "for": r.get("for"),
         "for_seconds": parse_for_seconds(r.get("for")),
         "fires_at_eval_t": next(
             (e["t"] for e in simulate(r["alert"], [(0, True)])["events"]
              if e["event"] == "firing"), None)}
        for r in RULES],
    "transient_spike_45s_baseline_p99": simulate(
        "NalBaselineP99LatencyHigh", [(0, True), (45, False)]),
    "fire_then_recover_baseline_p99": simulate(
        "NalBaselineP99LatencyHigh", [(0, True), (180, False)]),
    "flap_detected_fastest_path": simulate(
        "NalLinkFlapDetected", [(0, True), (180, False)]),
    "malformed_immediate": simulate(
        "NalMalformedPacketEchoed", [(0, True), (180, False)]),
    "stale_slowest_path": simulate(
        "NalResultsStale", [(0, True), (600, False)]),
}

# ------------------------------------------------ dashboard reconciliation
dash_out = {"dashboards": [], "targets_total": 0, "targets_with_series": 0,
            "targets_empty": []}
r0_series = parse_exposition(EXP.collect(R0, FAULT_CFG))
SEL_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?$")


def eval_selector(series, expr):
    m = SEL_RE.match(expr.strip())
    if not m:
        return None
    metric, raw = m.group(1), m.group(2) or ""
    matchers = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        mm = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)(=~|=)"([^"]*)"', part)
        if mm:
            matchers[mm.group(1)] = (mm.group(2), mm.group(3))
    return select(series, metric, matchers)


for fname in ("service-overview.json", "fault-comparison.json"):
    with open(os.path.join(LAB, "monitoring", "grafana", "dashboards", fname),
              encoding="utf-8") as f:
        dash = json.load(f)
    panels = []
    for panel in dash.get("panels", []):
        for tgt in panel.get("targets", []):
            expr = tgt.get("expr", "")
            got = eval_selector(r0_series, expr)
            dash_out["targets_total"] += 1
            n = len(got) if got is not None else 0
            if n:
                dash_out["targets_with_series"] += 1
            else:
                dash_out["targets_empty"].append(
                    {"dashboard": fname, "panel": panel.get("title"),
                     "expr": expr})
            panels.append({"panel": panel.get("title"), "expr": expr,
                           "series_matched": n,
                           "values": [v for _, v in (got or [])][:8]})
    dash_out["dashboards"].append(
        {"file": fname, "title": dash.get("title"), "uid": dash.get("uid"),
         "panels": len(dash.get("panels", [])), "targets": panels})

# Spot reconciliation: exporter values vs artifact values for R0
fault_json = OUT["runs"]["R0_latest_20261019-171627"]["intent"]
dash_out["spot_checks"] = {
    "fault_loss_ratio_exporter_vs_json": {
        "json": fault_json["NalFaultLossAboveInjectionBand"],
        "note": "threshold input; exporter series checked in runs.R0"},
    "flap_share_intent": fault_json["NalFlapShareDominatesLoss"],
}
OUT["dashboards"] = dash_out

with open(os.path.join(HERE, "2026-10-24-alert-chain-bench.json"), "w",
          encoding="utf-8") as f:
    json.dump(OUT, f, ensure_ascii=False, indent=1)
print(json.dumps({
    "rules": OUT["rules_group"],
    "r0_promql": {k: v["instances"] for k, v in
                  OUT["runs"]["R0_latest_20261019-171627"]["promql"].items()},
    "r0_corrected": {k: v["instances"] for k, v in
                     OUT["runs"]["R0_latest_20261019-171627"]
                     ["promql_corrected"].items()},
    "r1_promql": {k: v["instances"] for k, v in
                  OUT["runs"]["R1_first_20261019-154535"]["promql"].items()},
    "fixtures": [(x["case"], x["promql_instances"],
                  x["promql_corrected_instances"]) for x in fx_out],
    "dashboards": {k: dash_out[k] for k in
                   ("targets_total", "targets_with_series")},
}, ensure_ascii=False, indent=1))
