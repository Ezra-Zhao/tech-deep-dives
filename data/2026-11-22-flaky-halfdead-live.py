"""Live flaky half-dead run for the 2026-11-22 article.

Preregistered in data/2026-11-22-flaky-halfdead-prereg.md. Four arms
in parallel, each a fresh Prometheus 3.15.0 (scrape 5s, timeout 4s,
rule eval 15s, for: 1m, lookback 300s) scraping its own flaky
exporter: A period 2, B period 6, C period 24, D period 6 with
sample timestamps. Healthy baseline ~35 s, then all arms flip to
flaky for 400 s. Poll every 5 s. Only own processes are killed.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "rw-work", "run22")
PROM = os.path.join(HERE, "rw-work",
                    "prometheus-3.15.0.linux-amd64", "prometheus")
RULES = os.path.join(HERE, "2026-11-22-flaky-halfdead-rules.yml")
EXPORTER = os.path.join(HERE, "2026-11-22-flaky-exporter.py")
PRESENT = 'nal_exporter_results_present{group="scenario_summaries"}'
UP = 'up{job="net-assurance-lab"}'
ARMS = [
    {"name": "A", "period": 2, "ts": "0", "prom_port": 19101, "exp_port": 18101},
    {"name": "B", "period": 6, "ts": "0", "prom_port": 19102, "exp_port": 18102},
    {"name": "C", "period": 24, "ts": "0", "prom_port": 19103, "exp_port": 18103},
    {"name": "D", "period": 6, "ts": "1", "prom_port": 19104, "exp_port": 18104},
]
BASELINE_S = 35
FLAKY_S = 400
TAIL_S = 10
POLL_S = 5

T0 = time.time()
records = []
prog = open(os.path.join(HERE, "2026-11-22-flaky-halfdead-live-progress.jsonl"),
            "w", encoding="utf-8")


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
        return [{"labels": x["metric"], "value": float(x["value"][1]),
                 "ts": x["value"][0]} for x in j["data"]["result"]]
    except Exception as e:
        return {"error": str(e)}


def alerts_now(base):
    try:
        j = api(base, "/api/v1/alerts")
        out = []
        for a in j["data"]["alerts"]:
            if a["labels"].get("alertname") not in (
                    "NalExporterSeriesAbsent", "NalExporterUpZero"):
                continue
            out.append({"name": a["labels"]["alertname"],
                        "state": a["state"],
                        "activeAt": a.get("activeAt"),
                        "value": a.get("value")})
        return out
    except Exception as e:
        return {"error": str(e)}


def probe(base):
    return {"present": query(base, PRESENT),
            "absent": query(base, "absent(" + PRESENT + ")"),
            "up_job": query(base, UP),
            "alerts": alerts_now(base)}


def parse_iso(s):
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$", s)
    base = m.group(1)
    frac = float("0." + (m.group(2) or "0"))
    dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc)
    return dt.timestamp() + frac


def main():
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    procs = []
    for arm in ARMS:
        adir = os.path.join(WORK, arm["name"])
        os.makedirs(adir)
        arm["modefile"] = os.path.join(adir, "mode.txt")
        arm["logfile"] = os.path.join(adir, "attempts.log")
        with open(arm["modefile"], "w") as f:
            f.write("healthy")
        cfg = os.path.join(adir, "prometheus.yml")
        with open(cfg, "w") as f:
            f.write(f"""global:
  scrape_interval: 5s
  scrape_timeout: 4s
  evaluation_interval: 15s
rule_files:
  - {RULES}
scrape_configs:
  - job_name: "net-assurance-lab"
    static_configs:
      - targets: ["127.0.0.1:{arm['exp_port']}"]
""")
        ep = subprocess.Popen(
            [sys.executable, EXPORTER, str(arm["exp_port"]),
             str(arm["period"]), arm["modefile"], arm["logfile"], arm["ts"]],
            stdout=open(os.path.join(adir, "exporter.out"), "w"),
            stderr=subprocess.STDOUT)
        procs.append(ep)
        pp = subprocess.Popen(
            [PROM, f"--config.file={cfg}",
             f"--storage.tsdb.path={os.path.join(adir, 'tsdb')}",
             f"--web.listen-address=127.0.0.1:{arm['prom_port']}",
             "--web.enable-lifecycle"],
            stdout=open(os.path.join(adir, "prom.out"), "w"),
            stderr=subprocess.STDOUT)
        procs.append(pp)
        arm["base"] = f"http://127.0.0.1:{arm['prom_port']}"
    emit({"type": "started", "arms": [a["name"] for a in ARMS]})

    # wait for healthy baseline on all arms
    deadline = time.time() + 90
    ready = set()
    while time.time() < deadline and len(ready) < len(ARMS):
        for arm in ARMS:
            if arm["name"] in ready:
                continue
            p = probe(arm["base"])
            pres = p["present"]
            up = p["up_job"]
            if (isinstance(pres, list) and pres and pres[0]["value"] == 1
                    and isinstance(up, list) and up and up[0]["value"] == 1):
                ready.add(arm["name"])
        if len(ready) < len(ARMS):
            time.sleep(2)
    emit({"type": "baseline_ready", "ready": sorted(ready)})
    # hold baseline
    t_end = time.time() + BASELINE_S
    while time.time() < t_end:
        rec = {"type": "poll", "phase": "baseline"}
        for arm in ARMS:
            rec[arm["name"]] = probe(arm["base"])
        emit(rec)
        time.sleep(POLL_S)

    flip_epoch = time.time()
    for arm in ARMS:
        with open(arm["modefile"], "w") as f:
            f.write("flaky")
    emit({"type": "flip_to_flaky", "flip_epoch": flip_epoch})

    t_end = time.time() + FLAKY_S
    while time.time() < t_end:
        rec = {"type": "poll", "phase": "flaky"}
        for arm in ARMS:
            rec[arm["name"]] = probe(arm["base"])
        emit(rec)
        time.sleep(POLL_S)
    t_end = time.time() + TAIL_S
    while time.time() < t_end:
        rec = {"type": "poll", "phase": "tail"}
        for arm in ARMS:
            rec[arm["name"]] = probe(arm["base"])
        emit(rec)
        time.sleep(POLL_S)

    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(2)
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass

    out = {"flip_epoch": flip_epoch, "t0_epoch": T0, "records": records,
           "arms": [{k: a[k] for k in ("name", "period", "ts",
                                       "prom_port", "exp_port")}
                    for a in ARMS]}
    with open(os.path.join(
            HERE, "2026-11-22-flaky-halfdead-live.json"), "w",
            encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    emit({"type": "done"})
    print("DONE", len(records))


if __name__ == "__main__":
    main()
