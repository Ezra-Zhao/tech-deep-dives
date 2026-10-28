"""Live anti-blind run for net-assurance-lab (2026-10-27 article).

Real Prometheus 3.15.0 + the lab's real exporter (src/prom_exporter.py)
over a COPY of run 20261019-171627. The candidate rule file holds three
rules, all for: 1m, group interval 15s (frozen in the bench script):
the existing NalExporterResultsMissing, plus NalExporterDown (up == 0)
and NalExporterSeriesAbsent (absent(...)).

Phases, in order:
  baseline  healthy exporter, complete artifacts (45 s)
  delete    remove malformed.json from the copy; wait for the present
            rule to fire, then 30 s more (up/absent must stay silent)
  restore   put malformed.json back; wait for resolution
  settle    30 s healthy
  kill      SIGTERM the exporter process; wait for the absent rule to
            fire (theory: lookback 300 s + for: 60 s + alignment),
            then 30 s more (the present rule must never fire)
  recover   restart the exporter; wait for all anti-blind alerts to
            resolve

Every 5 s the poller records the three instant queries (up, present,
absent), the target health and /api/v1/alerts into a JSONL progress
file (flushed per record, so a host restart cannot lose the run), and
a final summary goes to data/2026-10-27-blind-alert-live.json.

The lab repo and its real results/ tree are never modified: the
exporter serves a scratch copy, deletions happen only in the copy.
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
WORK = os.path.join(HERE, "nal-blind-work")
LAB = os.path.expanduser("~/workspace/oxide-proofs/net-assurance-lab")
SRC_RUN = os.path.join(LAB, "results", "20261019-171627")
RESULTS = os.path.join(WORK, "results-live")
PROM = os.path.join(WORK, "prometheus")
API = "http://127.0.0.1:9090"
POLL_S = 5
RULES = ("NalExporterResultsMissing", "NalExporterDown",
         "NalExporterSeriesAbsent")

T0 = time.time()
records = []
progress_path = os.path.join(WORK, "live-progress.jsonl")
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
        return [{"labels": x["metric"], "value": float(x["value"][1])}
                for x in res]
    except Exception as e:  # prometheus not up yet etc.
        return {"error": str(e)}


def alerts_now():
    try:
        j = api("/api/v1/alerts")
        out = []
        for a in j["data"]["alerts"]:
            if a["labels"].get("alertname") not in RULES:
                continue
            out.append({"name": a["labels"]["alertname"],
                        "state": a["state"],
                        "activeAt": a.get("activeAt"),
                        "value": a.get("value"),
                        "labels": {k: v for k, v in a["labels"].items()
                                   if k not in ("alertname",)}})
        return out
    except Exception as e:
        return {"error": str(e)}


def target_health():
    try:
        j = api("/api/v1/targets", {"state": "active"})
        for t in j["data"]["activeTargets"]:
            if t["labels"].get("job") == "net-assurance-lab":
                return t["health"]
        return "not-found"
    except Exception:
        return "unknown"


def poll(phase):
    rec = {"type": "poll", "phase": phase,
           "up": query('up{job="net-assurance-lab"}'),
           "present": query(
               'nal_exporter_results_present{group="scenario_summaries"}'),
           "absent": query(
               'absent(nal_exporter_results_present'
               '{group="scenario_summaries"})'),
           "target_health": target_health(),
           "alerts": alerts_now()}
    emit(rec)
    return rec


def parse_iso(s):
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$", s)
    base, frac, tz = m.group(1), (m.group(2) or "0")[:6].ljust(6, "0"), m.group(3)
    dt = datetime.strptime(base + "." + frac,
                           "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
    return dt.timestamp()


def wait_phase(phase, seconds):
    end = time.time() + seconds
    last = None
    while time.time() < end:
        last = poll(phase)
        time.sleep(POLL_S)
    return last


def wait_until(phase, cond, timeout_s, label):
    """Poll until cond(record) is true; return (ok, last_record)."""
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


def start_exporter():
    log = open(os.path.join(WORK, "exporter.log"), "ab")
    p = subprocess.Popen(
        [sys.executable, os.path.join(LAB, "src", "prom_exporter.py"),
         "--port", "9108", "--results-dir", RESULTS],
        stdout=log, stderr=subprocess.STDOUT)
    emit({"type": "event", "event": "exporter_started", "pid": p.pid})
    return p


def main():
    os.makedirs(WORK, exist_ok=True)
    if os.path.exists(RESULTS):
        shutil.rmtree(RESULTS)
    shutil.copytree(SRC_RUN, RESULTS)
    emit({"type": "event", "event": "run_start",
          "source_run": SRC_RUN,
          "prometheus_version": subprocess.run(
              [PROM, "--version"], capture_output=True,
              text=True).stdout.splitlines()[0]})

    exporter = start_exporter()
    prom_log = open(os.path.join(WORK, "prometheus.log"), "wb")
    prom = subprocess.Popen(
        [PROM, "--config.file=" + os.path.join(
            HERE, "2026-10-27-blind-prometheus.yml"),
         "--storage.tsdb.path=" + os.path.join(WORK, "tsdb"),
         "--web.listen-address=127.0.0.1:9090"],
        cwd=HERE, stdout=prom_log, stderr=subprocess.STDOUT)
    emit({"type": "event", "event": "prometheus_started", "pid": prom.pid})

    summary = {"phases": {}}
    try:
        ok, _ = wait_until(
            "baseline", lambda r: isinstance(r["up"], list)
            and r["up"] and r["up"][0]["value"] == 1
            and isinstance(r["present"], list) and r["present"]
            and r["present"][0]["value"] == 1,
            120, "healthy baseline")
        summary["phases"]["baseline_ready"] = ok
        wait_phase("baseline", 45)

        # ---------------- delete artifacts -------------------------
        victim = os.path.join(RESULTS, "malformed.json")
        backup = os.path.join(WORK, "malformed.json.bak")
        shutil.copy2(victim, backup)
        t_del = time.time()
        os.remove(victim)
        emit({"type": "event", "event": "artifact_deleted",
              "file": "malformed.json", "t_epoch_event": t_del})
        ok, _ = wait_until(
            "delete",
            lambda r: alert_state(r, "NalExporterResultsMissing")
            == "firing", 300, "present rule firing after delete")
        summary["phases"]["delete_fired"] = ok
        wait_phase("delete_hold", 30)

        t_restore = time.time()
        shutil.copy2(backup, victim)
        emit({"type": "event", "event": "artifact_restored",
              "t_epoch_event": t_restore})
        ok, _ = wait_until(
            "restore",
            lambda r: alert_state(r, "NalExporterResultsMissing") is None,
            240, "present rule resolved after restore")
        summary["phases"]["restore_resolved"] = ok
        wait_phase("settle", 30)

        # ---------------- kill exporter ----------------------------
        t_kill = time.time()
        exporter.send_signal(signal.SIGTERM)
        exporter.wait(timeout=15)
        emit({"type": "event", "event": "exporter_killed",
              "t_epoch_event": t_kill, "exit": exporter.returncode})
        ok, _ = wait_until(
            "kill",
            lambda r: alert_state(r, "NalExporterSeriesAbsent")
            == "firing", 660, "absent rule firing after kill")
        summary["phases"]["kill_absent_fired"] = ok
        wait_phase("kill_hold", 30)

        # ---------------- recover ----------------------------------
        t_rec = time.time()
        exporter2 = start_exporter()
        emit({"type": "event", "event": "recovery_started",
              "t_epoch_event": t_rec})
        ok, _ = wait_until(
            "recover",
            lambda r: isinstance(r["alerts"], list) and not r["alerts"],
            300, "all anti-blind alerts resolved after recovery")
        summary["phases"]["recover_resolved"] = ok
        wait_phase("recover_hold", 15)
        exporter = exporter2
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
        emit({"type": "event", "event": "run_end"})

    # ---------------- summary extraction ---------------------------
    events = {r["event"]: r for r in records if r.get("type") == "event"}
    polls = [r for r in records if r.get("type") == "poll"]

    def first_poll(phase, pred):
        for r in polls:
            if r["phase"] == phase and pred(r):
                return r
        return None

    def first_alert(name, states, after_epoch):
        for r in polls:
            if r["t_epoch"] < after_epoch or not isinstance(
                    r.get("alerts"), list):
                continue
            for a in r["alerts"]:
                if a["name"] == name and a["state"] in states:
                    return {"poll_t_rel_s": r["t_rel_s"],
                            "poll_epoch": r["t_epoch"],
                            "activeAt": a["activeAt"],
                            "active_epoch": parse_iso(a["activeAt"])
                            if a["activeAt"] else None,
                            "state": a["state"]}
        return None

    def val(rec, key):
        v = rec.get(key) if rec else None
        if isinstance(v, list) and v:
            return v[0]["value"]
        return None

    t_del = events["artifact_deleted"]["t_epoch_event"]
    t_kill = events["exporter_killed"]["t_epoch_event"]
    t_restore = events["artifact_restored"]["t_epoch_event"]
    t_rec = events["recovery_started"]["t_epoch_event"]

    s = {}
    p = first_alert("NalExporterResultsMissing", ("pending", "firing"),
                    t_del)
    f = first_alert("NalExporterResultsMissing", ("firing",), t_del)
    s["delete_present_rule"] = {
        "pending_after_event_s": round(p["active_epoch"] - t_del, 1)
        if p else None,
        "firing_poll_after_event_s": round(f["poll_epoch"] - t_del, 1)
        if f else None,
        "firing_lower_bound_s": round(f["active_epoch"] + 60 - t_del, 1)
        if f else None}
    fp = first_poll("delete", lambda r: val(r, "present") == 0)
    s["delete_present_first_zero_poll_s"] = (
        round(fp["t_epoch"] - t_del, 1) if fp else None)
    s["delete_up_values_seen"] = sorted(
        {val(r, "up") for r in polls if r["phase"] in
         ("delete", "delete_hold") and val(r, "up") is not None})
    s["delete_absent_nonempty_polls"] = sum(
        1 for r in polls if r["phase"] in ("delete", "delete_hold")
        and isinstance(r.get("absent"), list) and r["absent"])
    res = first_poll("restore", lambda r: isinstance(r.get("alerts"), list)
                     and all(a["name"] != "NalExporterResultsMissing"
                             for a in r["alerts"]))
    s["delete_resolve_poll_after_restore_s"] = (
        round(res["t_epoch"] - t_restore, 1) if res else None)

    for name, key in (("NalExporterDown", "kill_up_rule"),
                      ("NalExporterSeriesAbsent", "kill_absent_rule"),
                      ("NalExporterResultsMissing", "kill_present_rule")):
        p = first_alert(name, ("pending", "firing"), t_kill)
        f = first_alert(name, ("firing",), t_kill)
        s[key] = {
            "pending_after_kill_s": round(p["active_epoch"] - t_kill, 1)
            if p else None,
            "firing_poll_after_kill_s": round(f["poll_epoch"] - t_kill, 1)
            if f else None,
            "firing_lower_bound_s": round(f["active_epoch"] + 60 - t_kill, 1)
            if f else None}
    s["kill_observation_window_s"] = round(
        (first_poll("kill_hold", lambda r: True) or polls[-1])["t_epoch"]
        - t_kill, 1)
    fe = first_poll("kill", lambda r: isinstance(r.get("present"), list)
                    and not r["present"])
    s["kill_present_first_empty_poll_s"] = (
        round(fe["t_epoch"] - t_kill, 1) if fe else None)
    fa = first_poll("kill", lambda r: isinstance(r.get("absent"), list)
                    and r["absent"])
    s["kill_absent_first_nonempty_poll_s"] = (
        round(fa["t_epoch"] - t_kill, 1) if fa else None)
    last_ok = None
    for r in polls:
        if r["t_epoch"] < t_kill and val(r, "up") == 1:
            last_ok = r
    s["last_healthy_poll_before_kill_rel_s"] = (
        last_ok["t_rel_s"] if last_ok else None)
    for name in RULES:
        rr = first_poll("recover", lambda r, n=name: isinstance(
            r.get("alerts"), list) and all(a["name"] != n
                                           for a in r["alerts"]))
        s[f"recover_{name}_gone_poll_after_restart_s"] = (
            round(rr["t_epoch"] - t_rec, 1) if rr else None)
    s["phase_flags"] = summary["phases"]
    s["poll_count"] = len(polls)
    s["total_run_s"] = round(time.time() - T0, 1)

    with open(os.path.join(HERE, "2026-10-27-blind-alert-live.json"), "w",
              encoding="utf-8") as fo:
        json.dump({"summary": s, "events": events, "records": records},
                  fo, ensure_ascii=False, indent=1)
    shutil.copy2(progress_path, os.path.join(
        HERE, "2026-10-27-blind-alert-live-progress.jsonl"))
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
