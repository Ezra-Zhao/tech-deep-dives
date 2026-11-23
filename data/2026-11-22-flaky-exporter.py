"""Flaky exporter for the 2026-11-22 half-dead experiment.

Usage: flaky-exporter.py PORT PERIOD MODEFILE LOGFILE TIMESTAMPED(0/1)

Serves nal_exporter_results_present{group="scenario_summaries"} 1.
Mode file content "healthy": every attempt succeeds fast.
Mode file content "flaky": attempt counter cycles with PERIOD; the
first attempt of each period succeeds fast, the rest hang 6 s (the
Prometheus scrape timeout is 4 s, so those scrapes fail).
Every attempt is logged (epoch, index, mode, outcome) to LOGFILE.
"""
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
PERIOD = int(sys.argv[2])
MODEFILE = sys.argv[3]
LOGFILE = sys.argv[4]
TIMESTAMPED = sys.argv[5] == "1"

counter = {"n": 0}
lock = threading.Lock()
loglock = threading.Lock()


def log_attempt(idx, mode, outcome):
    with loglock:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f} {idx} {mode} {outcome}\n")


def mode_now():
    try:
        with open(MODEFILE, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "healthy"


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        mode = mode_now()
        with lock:
            counter["n"] += 1
            idx = counter["n"]
        if mode == "healthy":
            success = True
        else:
            success = (idx % PERIOD) == 1 or PERIOD == 1
        if success:
            log_attempt(idx, mode, "success")
            ts = f" {int(time.time()*1000)}" if TIMESTAMPED else ""
            body = ('nal_exporter_results_present{group="scenario_summaries"} 1'
                    + ts + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            log_attempt(idx, mode, "hang")
            time.sleep(6)
            try:
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except Exception:
                pass

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
