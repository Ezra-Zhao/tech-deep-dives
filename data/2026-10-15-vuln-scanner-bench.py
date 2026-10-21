"""Bench harness for Web-Vuln-Scanner article (2026-10-15).

Runs the unmodified scanner repo (~/workspace/github/Web-Vuln-Scanner) against:
  A. the bundled intentionally-vulnerable demo app
  B. a hardened app written for this bench (escaped output, parameterized SQL,
     security headers, real 404s)
  C. a soft-404 app (returns HTTP 200 for every unknown path)
  D. a 'noisy text' app whose normal pages mention database errors in prose
  E. an app with a POST-only SQL-injectable form
  F. an app with a JSON reflected endpoint
Plus scope-guard probes and the bundled pytest suite.
All targets are local (127.0.0.1), all apps are written for this bench.
"""
import html
import json
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path.home() / "workspace/github/Web-Vuln-Scanner"
sys.path.insert(0, str(REPO))

import requests
from flask import Flask, Response, request
from werkzeug.serving import make_server

from scanner.crawler import crawl
from scanner.scope import authorize, ScopeError
from scanner.checks.xss import ReflectedXSSCheck
from scanner.checks.sqli import ErrorBasedSQLiCheck, ERROR_SIGNATURES, PAYLOADS
from scanner.checks.headers import SecurityHeadersCheck, EXPECTED_HEADERS
from scanner.checks.sensitive_files import SensitiveFilesCheck, PROBES

CHECKS = [ReflectedXSSCheck(), ErrorBasedSQLiCheck(), SecurityHeadersCheck(), SensitiveFilesCheck()]

results = {}

# ---------- extra bench apps ----------

def hardened_app():
    app = Flask("hardened")
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    db.executemany("INSERT INTO users VALUES (?,?)", [(1, "alice"), (2, "bob")])

    @app.after_request
    def add_headers(resp):
        resp.headers["Content-Security-Policy"] = "default-src 'self'"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=()"
        return resp

    @app.get("/")
    def index():
        return ('<h1>Hardened Shop</h1><a href="/search?q=phone">Search</a>'
                '<a href="/user?id=1">User</a>'
                '<form action="/search" method="get"><input name="q"></form>')

    @app.get("/search")
    def search():
        q = html.escape(request.args.get("q", ""))
        return f"<h1>Results for: {q}</h1>"

    @app.get("/user")
    def user():
        uid = request.args.get("id", "1")
        try:
            cur = db.execute("SELECT id, name FROM users WHERE id = ?", (int(uid),))
        except ValueError:
            return "<h1>Bad id</h1>", 400
        rows = cur.fetchall()
        if not rows:
            return "<h1>Not found</h1>", 404
        return "<ul>" + "".join(f"<li>{r[0]} {html.escape(r[1])}</li>" for r in rows) + "</ul>"

    return app


def soft404_app():
    app = Flask("soft404")

    @app.after_request
    def add_headers(resp):
        resp.headers["Content-Security-Policy"] = "default-src 'self'"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=()"
        return resp

    @app.get("/")
    def index():
        return '<h1>SPA shell</h1><a href="/search?q=x">Search</a>'

    @app.get("/search")
    def search():
        return f"<h1>Results for: {html.escape(request.args.get('q',''))}</h1>"

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catchall(path):
        # SPA-style fallback: every unknown path returns 200 + the app shell
        return "<h1>SPA shell</h1><p>route not matched, shell served anyway</p>", 200

    return app


def noisy_text_app():
    app = Flask("noisy")

    @app.get("/")
    def index():
        return '<h1>DB course notes</h1><a href="/article?topic=errors">Article</a>'

    @app.get("/article")
    def article():
        # Normal prose page: it *talks about* database errors. No injection exists.
        return ("<h1>Reading error messages</h1>"
                "<p>When a query fails you may see a database error or a note "
                "about SQL syntax in the log. This page explains what those mean.</p>")

    return app


def post_sqli_app():
    app = Flask("postsqli")
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    db.executemany("INSERT INTO users VALUES (?,?)", [(1, "alice"), (2, "bob")])

    @app.get("/")
    def index():
        return ('<h1>POST lookup</h1><form action="/lookup" method="post">'
                '<input name="id"><button>Go</button></form>')

    @app.post("/lookup")
    def lookup():
        uid = request.form.get("id", "1")
        try:
            cur = db.execute(f"SELECT id, name FROM users WHERE id = {uid}")
            rows = cur.fetchall()
        except Exception as e:
            return f"<h1>Database error</h1><pre>{e}</pre>", 500
        return "<ul>" + "".join(f"<li>{r[0]} {r[1]}</li>" for r in rows) + "</ul>"

    return app


def json_reflect_app():
    app = Flask("jsonapp")

    @app.get("/")
    def index():
        return '<h1>API demo</h1><a href="/api/search?q=phone">API search</a>'

    @app.get("/api/search")
    def api_search():
        q = request.args.get("q", "")
        # reflects input verbatim inside a JSON body
        return Response(json.dumps({"query": q, "results": []}),
                        mimetype="application/json")

    return app


def start(app, port):
    srv = make_server("127.0.0.1", port, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def scan(base):
    session = requests.Session()
    session.headers["User-Agent"] = "Web-Vuln-Scanner/0.1 (bench)"
    t0 = time.perf_counter()
    crawled = crawl(session, base, max_pages=20)
    crawl_s = time.perf_counter() - t0
    out = {
        "pages": len(crawled.pages),
        "forms": len(crawled.forms),
        "urls_with_params": crawled.urls_with_params,
        "crawl_seconds": round(crawl_s, 3),
        "checks": {},
        "total_findings": 0,
        "by_severity": {},
    }
    all_findings = []
    for chk in CHECKS:
        t0 = time.perf_counter()
        try:
            fs = chk.run(session, crawled)
            err = None
        except Exception as e:  # scanner cli catches per-check too
            fs, err = [], f"{type(e).__name__}: {e}"
        dt = time.perf_counter() - t0
        out["checks"][chk.name] = {
            "seconds": round(dt, 3),
            "count": len(fs),
            "titles": [f.title for f in fs],
            "error": err,
        }
        all_findings.extend(fs)
    out["total_findings"] = len(all_findings)
    for f in all_findings:
        out["by_severity"][f.severity] = out["by_severity"].get(f.severity, 0) + 1
    return out


def main():
    # static inventories
    results["inventories"] = {
        "sqli_payloads": PAYLOADS,
        "sqli_signature_groups": {k: v for k, v in ERROR_SIGNATURES},
        "expected_headers": EXPECTED_HEADERS,
        "sensitive_probes": [p[0] for p in PROBES],
        "sensitive_probe_count": len(PROBES),
    }

    # pytest suite
    r = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "pytest", "tests/", "-q"],
                       cwd=REPO, capture_output=True, text=True, timeout=300)
    results["pytest"] = {"exit": r.returncode, "tail": (r.stdout + r.stderr).strip().splitlines()[-3:]}

    # scope guard probes
    probes = {}
    def probe(name, fn):
        try:
            probes[name] = {"result": fn()}
        except ScopeError as e:
            probes[name] = {"scope_error": str(e)[:120]}
        except Exception as e:
            probes[name] = {"error": f"{type(e).__name__}: {e}"}
    probe("no_scheme", lambda: authorize("127.0.0.1:5000", confirmed=True))
    probe("unconfirmed", lambda: authorize("http://127.0.0.1:5000", confirmed=False))
    probe("confirmed_localhost", lambda: authorize("http://127.0.0.1:5000", confirmed=True))
    allow = Path("/tmp/bench-allowlist.txt")
    allow.write_text("example.com\n")
    probe("allowlist_mismatch", lambda: authorize("http://127.0.0.1:5000", allowlist_path=str(allow), confirmed=True))
    allow.write_text("127.0.0.1\n")
    probe("allowlist_match", lambda: authorize("http://127.0.0.1:5000", allowlist_path=str(allow), confirmed=True))
    results["scope_probes"] = probes

    # start servers
    sys.path.insert(0, str(REPO))
    from demo.vulnerable_app import app as vuln_app
    servers = [
        start(vuln_app, 5010),
        start(hardened_app(), 5011),
        start(soft404_app(), 5012),
        start(noisy_text_app(), 5013),
        start(post_sqli_app(), 5014),
        start(json_reflect_app(), 5015),
    ]
    time.sleep(0.5)
    try:
        results["A_demo_vulnerable"] = scan("http://127.0.0.1:5010")
        results["A_demo_repeat2"] = scan("http://127.0.0.1:5010")
        results["A_demo_repeat3"] = scan("http://127.0.0.1:5010")
        results["B_hardened"] = scan("http://127.0.0.1:5011")
        results["C_soft404"] = scan("http://127.0.0.1:5012")
        results["D_noisy_text"] = scan("http://127.0.0.1:5013")
        results["E_post_sqli_form"] = scan("http://127.0.0.1:5014")
        results["F_json_reflect"] = scan("http://127.0.0.1:5015")
    finally:
        for s in servers:
            s.shutdown()

    out = Path(__file__).with_name("2026-10-15-vuln-scanner-bench.json")
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps({k: (v if k in ("pytest", "scope_probes") else
                          {kk: vv for kk, vv in v.items() if kk in ("total_findings", "by_severity", "pages", "forms")} if isinstance(v, dict) else v)
                      for k, v in results.items()}, indent=2, ensure_ascii=False)[:4000])
    print("WROTE", out)


if __name__ == "__main__":
    main()
