"""Minimal timestamped exporter for the 2026-10-31 staleness article.

Serves ONLY nal_exporter_results_present (three groups, value 1), with
an explicit millisecond timestamp on every sample, taken at request
time. This isolates one variable against the lab exporter used in the
control phase: whether the sample carries its own timestamp.
Stdlib only, loopback only.
"""
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GROUPS = ("scenario_summaries", "run_meta", "fault_proxy_log")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/metrics":
            now_ms = int(time.time() * 1000)
            lines = [
                "# HELP nal_exporter_results_present 1 when the named "
                "group of run artifacts was found and parsed at scrape "
                "time.",
                "# TYPE nal_exporter_results_present gauge",
            ]
            for g in GROUPS:
                lines.append(
                    'nal_exporter_results_present{group="%s"} 1 %d'
                    % (g, now_ms))
            body = ("\n".join(lines) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type",
                             "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.rstrip("/") == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 9108), Handler)
    print("ts exporter on http://127.0.0.1:9108/metrics", flush=True)
    server.serve_forever()
