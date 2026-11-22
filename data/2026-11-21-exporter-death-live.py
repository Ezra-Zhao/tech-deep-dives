"""Live exporter-death run for the 2026-11-21 article.

Preregistered in data/2026-11-21-exporter-death-prereg.md. Two phases,
each with fresh Prometheus 3.15.0 TSDBs on loopback, same timing as
the 2026-11-09 run (scrape 5s, timeout 4s, rule groups 15s, for: 1m,
lookback 300s):

  E exporter-death (main)
              a sender Prometheus scrapes the lab exporter and
              remote-writes everything to a receiver Prometheus
              (--web.enable-remote-write-receiver, no scrape of the
              exporter). Both instances carry two candidate rules:
              absent(present) verbatim from the earlier articles and
              up == 0 (new). SIGTERM the EXPORTER only; the sender
              keeps scraping (and failing) and keeps pushing.
  C control   one Prometheus scrapes the lab exporter directly with
              the absent rule only; SIGTERM the exporter (fourth
              replication of the ~75 s stale window).

Per phase: healthy baseline, hold 30 s, kill, poll every 5 s (E polls
both the receiver and the sender) until the absent alert fires, hold
20 s. Every poll is flushed to the progress JSONL as it happens; the
final summary plus all records go to
data/2026-11-21-exporter-death-live.json. Only own processes are
killed; the lab repo is never modified (a scratch copy of the run
artifacts is served).
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
WORK = os.path.join(HERE, "rw-work", "run21")
PROM = os.path.join(HERE, "rw-work",
                    "prometheus-3.15.0.linux-amd64", "prometheus")
LAB = os.path.expanduser("~/workspace/oxide-proofs/net-assurance-lab")
SRC_RUN = os.path.join(LAB, "results", "20261019-171627")
RULES = os.path.join(HERE, "2026-11-21-exporter-death-rules.yml")
POLL_S = 5
PRESENT_EXPR = 'nal_exporter_results_present{group="scenario_summaries"}'
UP_EXPR = 'up{job="net-assurance-lab"}'
ABSENT_ALERT = "NalExporterSeriesAbsent"
UP_ALERT = "NalExporterUpZero"

T0 = time.time()
records = []
progress_path = os.path.join(
    HERE, "2026-11-21-exporter-death-live-progress.jsonl")
prog = open(progress_path, "w", encoding="utf-8")


def emit(rec):
    rec["t_rel_s"] = round(time.time() - T0, 1)
    rec["t_wall"] = datetime.now(timezone.utc).isoformat()
    rec["t_epoch"] = time.time()
    records.append(rec)
    prog.write(json.dumps(rec, ensure_ascii=False) + "\n")
    prog.flush()


def api(base, path, params=None):
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def query(base, expr):
    try:
        j = api(base, "/api/v1/query", {"query": expr})
        res = j["data"]["result"]
        return [{"labels": x["metric"], "value": float(x["value"][1]),
                 "ts": x["value"][0]} for x in res]
    except Exception as e:
        return {"error": str(e)}


def alerts_now(base):
    try:
        j = api(base, "/api/v1/alerts")
        out = []
        for a in j["data"]["alerts"]:
            if a["labels"].get("alertname") not in (ABSENT_ALERT, UP_ALERT):
                continue
            out.append({"name": a["labels"]["alertname"],
                        "state": a["state"],
                        "activeAt": a.get("activeAt"),
                        "value": a.get("value")})
        return out
    except Exception as e:
        return {"error": str(e)}


def probe(base):
    return {"present": query(base, PRESENT_EXPR),
            "absent": query(base, "absent(" + PRESENT_EXPR + ")"),
            "up_job": query(base, UP_EXPR),
            "alerts": alerts_now(base)}


def poll(phase, targets):
    rec = {"type": "poll", "phase": phase}
    for name, base in targets.items():
        rec[name] = probe(base)
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


def wait_phase(phase, targets, seconds):
    end = time.time() + seconds
    last = None
    while time.time() < end:
        last = poll(phase, targets)
        time.sleep(POLL_S)
    return last


def wait_until(phase, targets, cond, timeout_s, label):
    end = time.time() + timeout_s
    last = None
    while time.time() < end:
        last = poll(phase, targets)
        if cond(last):
            return True, last
        time.sleep(POLL_S)
    emit({"type": "timeout", "phase": phase, "waiting_for": label})
    return False, last


def alert_state(side, name, state):
    if not isinstance(side.get("alerts"), list):
        return False
    return any(a["name"] == name and a["state"] == state
               for a in side["alerts"])


def val(side, key):
    v = side.get(key) if side else None
    if isinstance(v, list) and v:
        return v[0]["value"]
    return None


def scrape_cfg_block():
    return (
        "scrape_configs:\n"
        "  - job_name: \"net-assurance-lab\"\n"
        "    metrics_path: /metrics\n"
        "    static_configs:\n"
        "      - targets: [\"127.0.0.1:9108\"]\n"
        "        labels:\n"
        "          lab: \"net-assurance-lab\"\n"
        "          env: \"local-loopback\"\n\n")


def write_control_cfg(workdir):
    cfg = os.path.join(workdir, "prometheus.yml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(
            "global:\n"
            "  scrape_interval: 5s\n"
            "  evaluation_interval: 5s\n"
            "  scrape_timeout: 4s\n\n"
            "rule_files:\n"
            "  - \"" + RULES + "\"\n\n"
            "alerting:\n"
            "  alertmanagers: []\n\n"
            + scrape_cfg_block())
    return cfg


def write_sender_cfg(workdir):
    cfg = os.path.join(workdir, "sender.yml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(
            "global:\n"
            "  scrape_interval: 5s\n"
            "  evaluation_interval: 5s\n"
            "  scrape_timeout: 4s\n\n"
            "rule_files:\n"
            "  - \"" + RULES + "\"\n\n"
            "alerting:\n"
            "  alertmanagers: []\n\n"
            "remote_write:\n"
            "  - url: http://127.0.0.1:9091/api/v1/write\n"
            "    remote_timeout: 5s\n"
            "    queue_config:\n"
            "      capacity: 2500\n"
            "      max_shards: 1\n"
            "      min_shards: 1\n"
            "      max_samples_per_send: 500\n"
            "      batch_send_deadline: 5s\n"
            "      min_backoff: 30ms\n"
            "      max_backoff: 5s\n\n"
            + scrape_cfg_block())
    return cfg


def write_receiver_cfg(workdir):
    cfg = os.path.join(workdir, "receiver.yml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(
            "global:\n"
            "  scrape_interval: 5s\n"
            "  evaluation_interval: 5s\n"
            "  scrape_timeout: 4s\n\n"
            "rule_files:\n"
            "  - \"" + RULES + "\"\n\n"
            "alerting:\n"
            "  alertmanagers: []\n")
    return cfg


def start_exporter(workdir):
    results_copy = os.path.join(workdir, "results-live")
    if os.path.exists(results_copy):
        shutil.rmtree(results_copy)
    shutil.copytree(SRC_RUN, results_copy)
    elog = open(os.path.join(workdir, "exporter.log"), "wb")
    p = subprocess.Popen(
        [sys.executable, os.path.join(LAB, "src", "prom_exporter.py"),
         "--port", "9108", "--results-dir", results_copy],
        stdout=elog, stderr=subprocess.STDOUT)
    return p


def exporter_direct_check():
    try:
        with urllib.request.urlopen("http://127.0.0.1:9108/metrics",
                                    timeout=5) as r:
            body = r.read().decode("utf-8", "replace")
        line = [ln for ln in body.splitlines()
                if ln.startswith(
                    'nal_exporter_results_present{group="scenario_summaries"}')]
        return {"http_ok": True,
                "present_line": line[0] if line else None}
    except Exception as e:
        return {"http_ok": False, "error": str(e)}


def start_prom(args, workdir, logname):
    plog = open(os.path.join(workdir, logname), "wb")
    return subprocess.Popen([PROM] + args, stdout=plog,
                            stderr=subprocess.STDOUT)


def run_control():
    name = "control"
    workdir = os.path.join(WORK, name)
    os.makedirs(workdir, exist_ok=True)
    base = "http://127.0.0.1:9090"
    targets = {"local": base}
    exporter = start_exporter(workdir)
    emit({"type": "event", "phase": name, "event": "exporter_started",
          "pid": exporter.pid})
    cfg = write_control_cfg(workdir)
    prom = start_prom(
        ["--config.file=" + cfg,
         "--storage.tsdb.path=" + os.path.join(workdir, "tsdb"),
         "--web.listen-address=127.0.0.1:9090"],
        workdir, "prometheus.log")
    emit({"type": "event", "phase": name, "event": "prometheus_started",
          "pid": prom.pid})
    flags = {}
    t_kill = None
    try:
        ok, _ = wait_until(name + ":baseline", targets,
                           lambda r: val(r["local"], "present") == 1, 120,
                           "healthy baseline")
        flags["baseline_ready"] = ok
        wait_phase(name + ":baseline", targets, 30)
        t_kill = time.time()
        exporter.send_signal(signal.SIGTERM)
        exporter.wait(timeout=15)
        emit({"type": "event", "phase": name,
              "event": "exporter_killed", "t_epoch_event": t_kill,
              "exit": exporter.returncode})
        ok, _ = wait_until(name + ":kill", targets,
                           lambda r: alert_state(r["local"], ABSENT_ALERT,
                                                 "firing"),
                           240, "absent firing")
        flags["main_fired"] = ok
        wait_phase(name + ":kill_hold", targets, 20)
    finally:
        for p in (exporter, prom):
            try:
                p.terminate()
                p.wait(timeout=15)
            except Exception:
                pass
        emit({"type": "event", "phase": name, "event": "phase_end"})
        time.sleep(3)
    return flags, t_kill


def run_main():
    name = "exporter-death"
    workdir = os.path.join(WORK, name)
    os.makedirs(workdir, exist_ok=True)
    rbase = "http://127.0.0.1:9091"
    sbase = "http://127.0.0.1:9092"
    targets = {"receiver": rbase, "sender": sbase}
    exporter = start_exporter(workdir)
    emit({"type": "event", "phase": name, "event": "exporter_started",
          "pid": exporter.pid})
    rcfg = write_receiver_cfg(workdir)
    receiver = start_prom(
        ["--config.file=" + rcfg,
         "--storage.tsdb.path=" + os.path.join(workdir, "receiver-tsdb"),
         "--web.listen-address=127.0.0.1:9091",
         "--web.enable-remote-write-receiver"],
        workdir, "receiver.log")
    emit({"type": "event", "phase": name, "event": "receiver_started",
          "pid": receiver.pid})
    scfg = write_sender_cfg(workdir)
    sender = start_prom(
        ["--config.file=" + scfg,
         "--storage.tsdb.path=" + os.path.join(workdir, "sender-tsdb"),
         "--web.listen-address=127.0.0.1:9092",
         "--storage.tsdb.retention.time=2h"],
        workdir, "sender.log")
    emit({"type": "event", "phase": name, "event": "sender_started",
          "pid": sender.pid})
    flags = {}
    t_kill = None
    try:
        ok, _ = wait_until(
            name + ":baseline", targets,
            lambda r: val(r["receiver"], "present") == 1
            and val(r["receiver"], "up_job") == 1, 180,
            "receiver healthy baseline")
        flags["baseline_ready"] = ok
        wait_phase(name + ":baseline", targets, 30)
        t_kill = time.time()
        exporter.send_signal(signal.SIGTERM)
        exporter.wait(timeout=15)
        emit({"type": "event", "phase": name,
              "event": "exporter_killed", "t_epoch_event": t_kill,
              "exit": exporter.returncode})
        chk = exporter_direct_check()
        emit({"type": "event", "phase": name,
              "event": "exporter_direct_check_after_kill",
              "check": chk})
        flags["exporter_dead_after_kill"] = not chk.get("http_ok")
        flags["sender_alive_after_kill"] = sender.poll() is None
        ok, _ = wait_until(name + ":kill", targets,
                           lambda r: alert_state(r["receiver"],
                                                 ABSENT_ALERT, "firing"),
                           620, "receiver absent firing")
        flags["main_fired"] = ok
        wait_phase(name + ":kill_hold", targets, 20)
        flags["sender_alive_at_end"] = sender.poll() is None
    finally:
        for p in (sender, receiver, exporter):
            try:
                p.terminate()
                p.wait(timeout=15)
            except Exception:
                pass
        emit({"type": "event", "phase": name, "event": "phase_end"})
        time.sleep(3)
    return flags, t_kill


def alert_summary(polls, side_key, alert_name, t_kill):
    entry = None
    for r in polls:
        side = r.get(side_key)
        if not side or r["t_epoch"] < t_kill:
            continue
        if not isinstance(side.get("alerts"), list):
            continue
        for a in side["alerts"]:
            if a["name"] == alert_name and a["state"] in (
                    "pending", "firing"):
                entry = {"pending_after_kill_s": round(
                             parse_iso(a["activeAt"]) - t_kill, 1),
                         "activeAt": a["activeAt"]}
                break
        if entry:
            break
    if entry:
        entry["firing_lower_bound_s"] = round(
            parse_iso(entry["activeAt"]) + 60 - t_kill, 1)
        for r in polls:
            side = r.get(side_key)
            if not side or r["t_epoch"] < t_kill:
                continue
            if alert_state(side, alert_name, "firing"):
                entry["firing_first_poll_s"] = round(
                    r["t_epoch"] - t_kill, 1)
                break
    return entry


def side_summary(phase_prefix, side_key, t_kill):
    polls = [r for r in records if r.get("type") == "poll"
             and r.get("phase", "").startswith(phase_prefix + ":")
             and side_key in r]
    out = {"polls": len(polls)}
    out["absent_alert"] = alert_summary(polls, side_key, ABSENT_ALERT,
                                        t_kill)
    out["up_alert"] = alert_summary(polls, side_key, UP_ALERT, t_kill)
    fe = None
    for r in polls:
        side = r[side_key]
        if r["t_epoch"] >= t_kill and isinstance(
                side.get("present"), list) and not side["present"]:
            fe = r
            break
    out["present_first_empty_poll_s"] = (
        round(fe["t_epoch"] - t_kill, 1) if fe else None)
    fz = None
    for r in polls:
        side = r[side_key]
        if r["t_epoch"] >= t_kill and isinstance(
                side.get("up_job"), list) and side["up_job"] \
                and side["up_job"][0]["value"] == 0:
            fz = r
            break
    out["up_first_zero_poll_s"] = (
        round(fz["t_epoch"] - t_kill, 1) if fz else None)
    post = [r[side_key]["up_job"][0]["value"] for r in polls
            if r["t_epoch"] >= t_kill
            and isinstance(r[side_key].get("up_job"), list)
            and r[side_key]["up_job"]]
    out["up_post_kill_values"] = sorted(set(post))
    out["up_post_kill_nonempty_polls"] = len(post)
    out["up_post_kill_total_polls"] = sum(
        1 for r in polls if r["t_epoch"] >= t_kill)
    last = None
    for r in polls:
        side = r[side_key]
        if isinstance(side.get("present"), list) and side["present"]:
            if r["t_epoch"] < t_kill + 30:
                last = side["present"][0]
    out["last_present_sample_seen"] = last
    out["baseline_alert_polls"] = sum(
        1 for r in polls if r["phase"].endswith(":baseline")
        and isinstance(r[side_key].get("alerts"), list)
        and r[side_key]["alerts"])
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    version = subprocess.run([PROM, "--version"], capture_output=True,
                             text=True).stdout.splitlines()[0]
    emit({"type": "event", "event": "run_start",
          "prometheus_version": version})
    check = subprocess.run([os.path.join(os.path.dirname(PROM), "promtool"),
                            "check", "rules", RULES],
                           capture_output=True, text=True)
    emit({"type": "event", "event": "promtool_check",
          "stdout": check.stdout.strip(), "stderr": check.stderr.strip(),
          "returncode": check.returncode})
    summary = {}
    flags, t_kill = run_main()
    summary["exporter-death"] = {
        "flags": flags,
        "receiver": side_summary("exporter-death", "receiver", t_kill),
        "sender": side_summary("exporter-death", "sender", t_kill)}
    emit({"type": "event", "phase": "exporter-death",
          "event": "phase_done", "flags": flags})
    flags, t_kill = run_control()
    summary["control"] = {
        "flags": flags,
        "local": side_summary("control", "local", t_kill)}
    emit({"type": "event", "phase": "control", "event": "phase_done",
          "flags": flags})
    summary["total_run_s"] = round(time.time() - T0, 1)
    with open(os.path.join(HERE, "2026-11-21-exporter-death-live.json"),
              "w", encoding="utf-8") as fo:
        json.dump({"summary": summary, "records": records}, fo,
                  ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
