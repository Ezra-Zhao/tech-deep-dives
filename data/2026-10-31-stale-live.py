"""Live staleness-boundary run for the 2026-10-31 article.

Three phases, each with a fresh Prometheus 3.15.0 TSDB on loopback,
same timing everywhere (scrape 5s, timeout 4s, rule groups 15s,
for: 1m), preregistered in data/2026-10-31-stale-prereg.md:

  C control     lab exporter (no sample timestamps), absent alert on
                nal_exporter_results_present - replication of the
                2026-10-27 kill measurement (about 75 s).
  T timestamped minimal exporter whose samples carry an explicit
                millisecond timestamp; same absent alert.
  R recorded    lab exporter plus a recording rule replicating the
                series as nal_present_recorded; absent alerts on both
                the original and the replica in the same kill event.

Per phase: wait for a healthy baseline, hold 30 s, SIGTERM the
exporter, poll every 5 s until the phase's main absent alert fires,
hold 20 s. Every poll is flushed to the progress JSONL in this
directory as it happens. Final summary plus all records go to
data/2026-10-31-stale-live.json. Only scratch copies and own
processes are killed; the lab repo is never modified.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "nal-stale-work", "run")
PROM = os.path.join(HERE, "nal-stale-work",
                    "prometheus-3.15.0.linux-amd64", "prometheus")
LAB = os.path.expanduser("~/workspace/oxide-proofs/net-assurance-lab")
SRC_RUN = os.path.join(LAB, "results", "20261019-171627")
API = "http://127.0.0.1:9090"
POLL_S = 5
ALERTS = ("NalExporterSeriesAbsent", "NalRecordedSeriesAbsent")
PRESENT_EXPR = 'nal_exporter_results_present{group="scenario_summaries"}'
RECORDED_EXPR = "nal_present_recorded"

T0 = time.time()
records = []
progress_path = os.path.join(HERE, "2026-10-31-stale-live-progress.jsonl")
prog = open(progress_path, "w", encoding="utf-8")


def emit(rec):
    rec["t_rel_s"] = round(time.time() - T0, 1)
    rec["t_wall"] = datetime.now(timezone.utc).isoformat()
    rec["t_epoch"] = time.time()
    records.append(rec)
    prog.write(json.dumps(rec, ensure_ascii=False) + "\n")
    prog.flush()


def api(path, params=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def query(expr):
    try:
        j = api("/api/v1/query", {"query": expr})
        res = j["data"]["result"]
        return [{"labels": x["metric"], "value": float(x["value"][1]),
                 "ts": x["value"][0]} for x in res]
    except Exception as e:
        return {"error": str(e)}


def alerts_now():
    try:
        j = api("/api/v1/alerts")
        out = []
        for a in j["data"]["alerts"]:
            if a["labels"].get("alertname") not in ALERTS:
                continue
            out.append({"name": a["labels"]["alertname"],
                        "state": a["state"],
                        "activeAt": a.get("activeAt"),
                        "value": a.get("value")})
        return out
    except Exception as e:
        return {"error": str(e)}


def poll(phase):
    rec = {"type": "poll", "phase": phase,
           "up": query('up{job="net-assurance-lab"}'),
           "present": query(PRESENT_EXPR),
           "absent": query("absent(" + PRESENT_EXPR + ")"),
           "recorded": query(RECORDED_EXPR),
           "absent_recorded": query("absent(" + RECORDED_EXPR + ")"),
           "alerts": alerts_now()}
    emit(rec)
    return rec


def parse_iso(s):
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$", s)
    base = m.group(1)
    frac = (m.group(2) or "0")[:6].ljust(6, "0")
    dt = datetime.strptime(base + "." + frac,
                           "%Y-%m-%dT%H:%M:%S.%f").replace(
                               tzinfo=timezone.utc)
    return dt.timestamp()


def wait_phase(phase, seconds):
    end = time.time() + seconds
    last = None
    while time.time() < end:
        last = poll(phase)
        time.sleep(POLL_S)
    return last


def wait_until(phase, cond, timeout_s, label):
    end = time.time() + timeout_s
    last = None
    while time.time() < end:
        last = poll(phase)
        if cond(last):
            return True, last
        time.sleep(POLL_S)
    emit({"type": "timeout", "phase": phase, "waiting_for": label})
    return False, last


def alert_state(rec, name):
    if not isinstance(rec.get("alerts"), list):
        return None
    for a in rec["alerts"]:
        if a["name"] == name:
            return a["state"]
    return None


def val(rec, key):
    v = rec.get(key) if rec else None
    if isinstance(v, list) and v:
        return v[0]["value"]
    return None


def write_config(workdir, rules_filename):
    cfg = os.path.join(workdir, "prometheus.yml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(
            "global:\n"
            "  scrape_interval: 5s\n"
            "  evaluation_interval: 5s\n"
            "  scrape_timeout: 4s\n\n"
            "rule_files:\n"
            "  - \"" + os.path.join(HERE, rules_filename) + "\"\n\n"
            "alerting:\n"
            "  alertmanagers: []\n\n"
            "scrape_configs:\n"
            "  - job_name: \"net-assurance-lab\"\n"
            "    metrics_path: /metrics\n"
            "    static_configs:\n"
            "      - targets: [\"127.0.0.1:9108\"]\n"
            "        labels:\n"
            "          lab: \"net-assurance-lab\"\n"
            "          env: \"local-loopback\"\n\n"
            "  - job_name: \"prometheus\"\n"
            "    static_configs:\n"
            "      - targets: [\"127.0.0.1:9090\"]\n")
    return cfg


def run_phase(name, exporter_kind, rules_filename, main_alert,
              fire_timeout_s):
    workdir = os.path.join(WORK, name)
    os.makedirs(workdir, exist_ok=True)
    results_copy = None
    if exporter_kind == "lab":
        results_copy = os.path.join(workdir, "results-live")
        if os.path.exists(results_copy):
            shutil.rmtree(results_copy)
        shutil.copytree(SRC_RUN, results_copy)
        cmd = [sys.executable,
               os.path.join(LAB, "src", "prom_exporter.py"),
               "--port", "9108", "--results-dir", results_copy]
    else:
        cmd = [sys.executable,
               os.path.join(HERE, "2026-10-31-stale-ts-exporter.py")]
    elog = open(os.path.join(workdir, "exporter.log"), "wb")
    exporter = subprocess.Popen(cmd, stdout=elog,
                                stderr=subprocess.STDOUT)
    emit({"type": "event", "phase": name, "event": "exporter_started",
          "pid": exporter.pid, "kind": exporter_kind})
    cfg = write_config(workdir, rules_filename)
    plog = open(os.path.join(workdir, "prometheus.log"), "wb")
    prom = subprocess.Popen(
        [PROM, "--config.file=" + cfg,
         "--storage.tsdb.path=" + os.path.join(workdir, "tsdb"),
         "--web.listen-address=127.0.0.1:9090"],
        stdout=plog, stderr=subprocess.STDOUT)
    emit({"type": "event", "phase": name, "event": "prometheus_started",
          "pid": prom.pid})
    flags = {}
    t_kill = None
    try:
        def healthy(r):
            if val(r, "present") != 1:
                return False
            if name == "recorded" and val(r, "recorded") != 1:
                return False
            return True
        ok, _ = wait_until(name + ":baseline", healthy, 120,
                           "healthy baseline")
        flags["baseline_ready"] = ok
        wait_phase(name + ":baseline", 30)
        t_kill = time.time()
        exporter.send_signal(signal.SIGTERM)
        exporter.wait(timeout=15)
        emit({"type": "event", "phase": name,
              "event": "exporter_killed", "t_epoch_event": t_kill,
              "exit": exporter.returncode})
        ok, _ = wait_until(
            name + ":kill",
            lambda r: alert_state(r, main_alert) == "firing",
            fire_timeout_s, main_alert + " firing")
        flags["main_fired"] = ok
        wait_phase(name + ":kill_hold", 20)
    finally:
        try:
            exporter.terminate()
        except Exception:
            pass
        try:
            prom.terminate()
            prom.wait(timeout=15)
        except Exception:
            pass
        emit({"type": "event", "phase": name, "event": "phase_end"})
        time.sleep(3)
    return flags, t_kill


def phase_summary(name, t_kill):
    polls = [r for r in records if r.get("type") == "poll"
             and r.get("phase", "").startswith(name + ":")]
    out = {"polls": len(polls)}

    def first_alert(aname, states):
        for r in polls:
            if r["t_epoch"] < t_kill or not isinstance(
                    r.get("alerts"), list):
                continue
            for a in r["alerts"]:
                if a["name"] == aname and a["state"] in states:
                    return {"pending_after_kill_s": round(
                                parse_iso(a["activeAt"]) - t_kill, 1),
                            "activeAt": a["activeAt"],
                            "firing_poll_after_kill_s": None,
                            "firing_lower_bound_s": None}
        return None

    def fill_firing(aname, entry):
        if entry is None:
            return None
        for r in polls:
            if r["t_epoch"] < t_kill or not isinstance(
                    r.get("alerts"), list):
                continue
            for a in r["alerts"]:
                if a["name"] == aname and a["state"] == "firing":
                    entry["firing_poll_after_kill_s"] = round(
                        r["t_epoch"] - t_kill, 1)
                    entry["firing_lower_bound_s"] = round(
                        parse_iso(a["activeAt"]) + 60 - t_kill, 1)
                    return entry
        return entry

    for aname, key in (("NalExporterSeriesAbsent", "absent_alert"),
                       ("NalRecordedSeriesAbsent", "recorded_alert")):
        out[key] = fill_firing(aname, first_alert(aname, ("pending",
                                                          "firing")))
    for key, field in (("present", "present_first_empty_poll_s"),
                       ("recorded", "recorded_first_empty_poll_s")):
        fe = None
        for r in polls:
            if r["t_epoch"] >= t_kill and isinstance(
                    r.get(key), list) and not r[key]:
                fe = r
                break
        out[field] = (round(fe["t_epoch"] - t_kill, 1) if fe else None)
    out["baseline_alert_polls"] = sum(
        1 for r in polls if r["phase"].endswith(":baseline")
        and isinstance(r.get("alerts"), list) and r["alerts"])
    # last visible present sample timestamp seen before kill (T phase:
    # the sample's own timestamp; C/R: the scrape timestamp)
    last = None
    for r in polls:
        if r["t_epoch"] < t_kill and isinstance(
                r.get("present"), list) and r["present"]:
            last = r["present"][0]
    out["last_present_sample_before_kill"] = last
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    version = subprocess.run([PROM, "--version"], capture_output=True,
                             text=True).stdout.splitlines()[0]
    emit({"type": "event", "event": "run_start",
          "prometheus_version": version})
    plan = [
        ("control", "lab", "2026-10-31-stale-rules-control.yml",
         "NalExporterSeriesAbsent", 240),
        ("timestamped", "ts", "2026-10-31-stale-rules-control.yml",
         "NalExporterSeriesAbsent", 540),
        ("recorded", "lab", "2026-10-31-stale-rules-recorded.yml",
         "NalRecordedSeriesAbsent", 540),
    ]
    summary = {}
    kills = {}
    for name, kind, rules, main_alert, timeout in plan:
        flags, t_kill = run_phase(name, kind, rules, main_alert, timeout)
        kills[name] = t_kill
        summary[name] = {"flags": flags}
        emit({"type": "event", "phase": name, "event": "phase_done",
              "flags": flags})
    for name, _, _, _, _ in plan:
        summary[name].update(phase_summary(name, kills[name]))
    summary["total_run_s"] = round(time.time() - T0, 1)
    with open(os.path.join(HERE, "2026-10-31-stale-live.json"), "w",
              encoding="utf-8") as fo:
        json.dump({"summary": summary, "records": records}, fo,
                  ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
