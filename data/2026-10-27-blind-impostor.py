"""Supplementary live run (2026-10-27 article): the impostor endpoint.

A dummy HTTP server occupies 127.0.0.1:9108 and answers every scrape
with HTTP 200 and one unrelated metric. Prometheus therefore reports
up == 1, but no nal_* series exists at all. This isolates the one cell
where absent() and up disagree in the opposite direction from the
kill case: the scrape layer is healthy, the watched series is gone.

Same Prometheus 3.15.0, same candidate rule file, same timing
(scrape 5s, group interval 15s, for: 1m) as the main live run.
Output: data/2026-10-27-blind-impostor-live.json
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "nal-blind-work")
PROM = os.path.join(WORK, "prometheus")
API = "http://127.0.0.1:9090"
RULES = ("NalExporterResultsMissing", "NalExporterDown",
         "NalExporterSeriesAbsent")
T0 = time.time()
records = []


class Dummy(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"# HELP other_metric Unrelated.\n# TYPE other_metric gauge\nother_metric 1\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def api(path, params=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def query(expr):
    try:
        j = api("/api/v1/query", {"query": expr})
        return [{"labels": x["metric"], "value": float(x["value"][1])}
                for x in j["data"]["result"]]
    except Exception as e:
        return {"error": str(e)}


def poll(phase):
    try:
        j = api("/api/v1/alerts")
        alerts = [{"name": a["labels"]["alertname"], "state": a["state"],
                   "activeAt": a.get("activeAt")}
                  for a in j["data"]["alerts"]
                  if a["labels"].get("alertname") in RULES]
    except Exception as e:
        alerts = {"error": str(e)}
    rec = {"type": "poll", "phase": phase,
           "t_rel_s": round(time.time() - T0, 1),
           "t_epoch": time.time(),
           "t_wall": datetime.now(timezone.utc).isoformat(),
           "up": query('up{job="net-assurance-lab"}'),
           "present": query(
               'nal_exporter_results_present{group="scenario_summaries"}'),
           "absent": query(
               'absent(nal_exporter_results_present'
               '{group="scenario_summaries"})'),
           "alerts": alerts}
    records.append(rec)
    return rec


def main():
    srv = HTTPServer(("127.0.0.1", 9108), Dummy)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    tsdb = os.path.join(WORK, "tsdb-impostor")
    if os.path.exists(tsdb):
        shutil.rmtree(tsdb)
    prom_log = open(os.path.join(WORK, "prometheus-impostor.log"), "wb")
    prom = subprocess.Popen(
        [PROM, "--config.file=" + os.path.join(
            HERE, "2026-10-27-blind-prometheus.yml"),
         "--storage.tsdb.path=" + tsdb,
         "--web.listen-address=127.0.0.1:9090"],
        cwd=HERE, stdout=prom_log, stderr=subprocess.STDOUT)
    fired_at = None
    try:
        end = time.time() + 200
        while time.time() < end:
            r = poll("impostor")
            states = {a["name"]: a["state"] for a in r["alerts"]} \
                if isinstance(r["alerts"], list) else {}
            if states.get("NalExporterSeriesAbsent") == "firing":
                fired_at = r["t_rel_s"]
                # hold 20 s to confirm the other two stay silent
                for _ in range(4):
                    time.sleep(5)
                    poll("impostor_hold")
                break
            time.sleep(5)
    finally:
        prom.terminate()
        try:
            prom.wait(timeout=15)
        except Exception:
            pass
        srv.shutdown()
    with open(os.path.join(HERE, "2026-10-27-blind-impostor-live.json"),
              "w", encoding="utf-8") as f:
        json.dump({"absent_firing_poll_t_rel_s": fired_at,
                   "records": records}, f, ensure_ascii=False, indent=1)
    print("absent firing poll t_rel:", fired_at)
    print("polls:", len(records))


if __name__ == "__main__":
    main()
