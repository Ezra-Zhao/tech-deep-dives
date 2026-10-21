# How Many of a Scanner's Findings Are Real? Web-Vuln-Scanner's Detection Pipeline and False-Positive Control, Measured

Author: Guangyi Zhao
Date: 2026-10-15
Subject: Web-Vuln-Scanner (open-source project by the author, github.com/Ezra-Zhao/Web-Vuln-Scanner), scaffold v0.1, Python 3.12.3
Environment: Linux x86_64 VM; every target is the author's own application on 127.0.0.1 (the bundled demo app plus five target apps written for these experiments). No third-party system was scanned.

## 1. Problem and background

A vulnerability scanner's report has a question that rarely gets asked to its face: how many of these findings are real?

The cost of a false positive is not "a second look." One fake high-severity SQL injection drags the on-call engineer through a full incident loop — confirm, reproduce, read the code — until it turns out the page merely mentioned database errors in its prose. Enough false positives and nobody reads the report carefully anymore; the real findings get swept away with the noise. In a detection pipeline, false-positive control is not polish. It is what decides whether the report deserves trust.

My own open-source project, Web-Vuln-Scanner, is a small ethics-first scanner: it refuses to run without an explicit target and an explicit authorization confirmation. It currently implements four checks — reflected XSS, error-based SQL injection, security response headers, and sensitive-path probing. The honest status, stated up front: scaffold v0.1, and the README says so. Stored XSS, blind SQLi, CSRF, and authenticated scanning are not implemented; they sit in the source as TODOs, not claimed features.

This is not a usage tutorial. I ran the pipeline against six targets: the bundled intentionally vulnerable demo app; a hardened app written the careful way; a single-page-app shell that answers HTTP 200 for every unknown path; an article site whose prose legitimately talks about database errors; an app whose only form is POST and whose backend really is injectable; and an API app that reflects input verbatim into a JSON response. The six targets measure four things: whether real vulnerabilities are caught, whether clean targets stay clean, what shape the false positives take, and where the pipeline's field of view ends. The headline result: each check's logic is restrained in its own way, but the two checks that did produce false positives — sensitive-path probing and error-based SQLi — are missing the same thing: a baseline. Without a "first look at what the normal response looks like" step, a soft-404 site makes the sensitive-path check go 14 for 14 wrong, and one ordinary sentence about a "database error" buys you a high-severity injection alert.

## 2. Method and architecture

The codebase totals 846 lines including the demo app and tests. The pipeline is four serial stages: scope.py validates authorization; crawler.py crawls the same host collecting pages, forms, and parameterized URLs; the four checks run independently against the crawl results; report.py emits a console and JSON report. Checks share no state, and the CLI wraps each check so one check's exception cannot kill the scan.

Each check's decision logic, stated precisely, because every conclusion below follows from it:

Reflected XSS (scanner/checks/xss.py): generates an 8-hex-character random token, builds a payload of the form `"><svg/onload=alert('TOKEN')>`, and injects it into every URL parameter and form field. A high-severity finding requires both the token and the complete payload to appear verbatim in the response body. Escaped reflection (quotes or angle brackets encoded) cannot match, because the full payload string no longer appears.

Error-based SQLi (scanner/checks/sqli.py): four payloads only (single quote, double quote, two tautologies). The response body is matched against six database error-signature groups — SQLite, MySQL/MariaDB, PostgreSQL, MSSQL, Oracle, and a generic group — 21 regular expressions in total, including generic words like `syntax error` and `database error`. A match is a high-severity finding, at most one per parameter. The check never sends a baseline request and never diffs the response against the un-injected one.

Security headers (scanner/checks/headers.py): examines exactly one response — the base page. Missing Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, or Permissions-Policy headers are reported individually; HSTS is checked on HTTPS targets; a Server header earns an info-level version-disclosure note.

Sensitive files (scanner/checks/sensitive_files.py): a fixed table of 14 probe paths (.git/HEAD, .env, admin, backup.zip, db.sqlite, and so on), requested one by one without following redirects. HTTP 200 with a non-empty body is a finding, at a per-path preset severity from info to high. The response content is never examined — the source's own TODOs admit soft-404 detection and content sniffing are unimplemented.

The crawler's field of view bounds the checks': same-host links only, at most 20 pages by default, and only pages served as text/html are recorded — a non-HTML response is skipped entirely, neither stored nor parsed for links.

Method: the repository ran unmodified. The demo target is the bundled demo/vulnerable_app.py; the other five targets were written for this article and are archived with the experiment script. Every target went through the full pipeline (crawl plus four checks) with per-check request counts and timings recorded; the demo scan was repeated three times for stability; the authorization guard got five dedicated probes; and the JSON endpoint got one manual payload-reflection probe. Scripts and raw JSON are archived with this article so every number can be re-run.

## 3. Measurements

### 3.1 Demo app: all four planted problem classes caught, 31 requests per run

The demo app plants four problem classes: reflected XSS on /search, string-concatenated SQL with verbose error echo on /user, no security headers at all, and exposed /admin and /.git/HEAD. The scan reported 13 findings:

| Check | Requests | Findings | What |
|---|---|---|---|
| Crawl | 4 | 4 pages, 1 form, 2 parameterized URLs | — |
| reflected-xss | 3 | 3 | parameter q, parameter id, form field q |
| error-based-sqli | 9 | 1 | parameter id (SQLite error disclosed) |
| security-headers | 1 | 6 | all five headers missing, plus Server version disclosure |
| sensitive-files | 14 | 3 | /robots.txt, /.git/HEAD, /admin |

Thirty-one requests total; per-check time 0.04–0.19 s; a full local run finishes in under a second. Three repeated runs agreed exactly: 13 findings each time, same severity distribution (high 5, medium 2, low 3, info 3). The pipeline is deterministic; there is no random component in its verdicts.

One hit deserves unpacking. XSS also fired on /user?id= — SQLi's home turf. The XSS payload was concatenated into the SQL statement, the database errored, and the error page echoed the exception — payload included, unescaped — inside a pre element. So the payload was reflected, through the error page. That is a true positive, but the reflection path is "via verbose error disclosure," not "the app renders the parameter into a normal page." A reader who only sees the title "Reflected XSS via parameter 'id'" will go looking in the wrong place: the check supplies the evidence string, but not the context in which the reflection happened. That is a reporting debt.

The bundled test suite — 11 tests covering the four checks against the demo app plus the scope guard — passes under pytest in 1.61 s.

### 3.2 Hardened app: zero vulnerability findings, one unavoidable info

The second target was written the careful way: html.escape on output, parameterized queries with type validation, all five security headers set, real 404s for unknown paths, no sensitive paths. Result: XSS, SQLi, and sensitive-files all returned 0. The single finding was the security-headers info — the Server header disclosing the Werkzeug version.

That info is worth a sentence of its own. It is not the application code's fault: the development server adds the Server header at the response layer, and my hardened app did not attempt to suppress it. Against any target running on a framework dev server with default settings, this info will very likely appear regardless of how disciplined the application code is. The lesson for report readers: judge info-level items by which layer produced them, and do not charge the framework's default behavior to the application.

The positive conclusion matters just as much: on a "written properly" baseline, the four checks produced zero vulnerability-class findings. False positives are not this pipeline's default state. They appear on specific site shapes — the next three sections.

### 3.3 Soft 404: 14 of 14 probes wrong, a report that is 93% noise

The third target mimics the common SPA/fallback shape: every unknown path returns 200 with the app shell. It sets all five security headers and escapes its search output — an app with nothing planted. The scan reported 15 findings, 14 of them from sensitive-files: the entire 14-path probe table hit, including .env (high), db.sqlite (high), database.sql (high), .git/HEAD (high), backup.zip, phpinfo.php. The 15th finding was the Server version-disclosure info, same as section 3.2. All 14 sensitive-path hits are false positives — a 100% false-positive rate for that check — and 14 of the report's 15 findings, 93%, are noise.

The cause is written into the decision rule: status 200 plus a non-empty body, content never examined. On a site where every path is a 200, the probe table's length is the false-positive count. The source's TODO already names the fix — fetch one random nonexistent path as a soft-404 sample and compare similarity — but until that lands, this check's output on SPA-shaped sites should be stamped untrusted as a block, not interleaved with real findings sorted by high severity. The practical damage is exactly there: the four high-severity findings at the top of the report are all fake, and the reader's trust in any real finding further down is spent along with them.

### 3.4 No baseline comparison: one sentence of prose buys a high-severity alert

The fourth target is an article site whose page legitimately discusses database errors — the prose contains the phrases "database error" and "SQL syntax" — and whose topic parameter feeds no SQL query at all. There is no injection. The scan reported one high-severity finding: "Possible SQL injection via parameter 'topic' (Generic SQL error disclosed)."

The mechanism is easy to dissect. The check appends its four payloads to the parameter one at a time and matches every response against the error signatures. The article's prose contains signature words regardless of any payload, so the first payload already matches; the verdict has nothing to do with whether injection occurred. The missing step is the baseline: never request the page without a payload and check whether the signature words were already there. Baseline comparison is the textbook move for injection detection — this project's own blind-SQLi TODO sketches exactly that, comparing true-condition and false-condition responses — but the error-based path never got one. And because the generic signature group uses everyday words like "database error," the tripwire is low: any site that writes about database operations can set it off.

This and section 3.3 are the same disease in two organs: the verdict asks only "is the thing I am looking for in this response," never "was it already there before I attacked."

### 3.5 POST forms: a real injection in plain sight, skipped by design

The fifth target has a single POST form whose backend query is string-concatenated with verbose errors — a real, exploitable SQL injection. The SQLi check reported 0. By design it tests GET forms and URL parameters only; POST forms are skipped, with a TODO saying so. The miss is a scope boundary, not an implementation bug — but nothing in the report mentions that this form was never tested. The reader sees a clean zero.

The same target produced a telling contrast. The XSS check does test POST forms, and it reported one high. Its HTML payload happened to contain quotes that broke the backend SQL; the error page echoed the payload unescaped, and the XSS check duly confirmed a reflected XSS — the same echo path as section 3.1. What it recorded is an XSS, not a SQLi. But that response objectively carried a full database error message, and no part of the pipeline ever matched it: the SQLi check had skipped the form, and the XSS check does not look at error signatures. The evidence appeared in the traffic and no check was responsible for claiming it. That is the price of hermetic check separation: every check answers for its own conclusions, and nobody answers for coverage completeness. A "not covered" section in the report — which forms, which parameters, which checks never ran on them — costs little and turns this silent miss into a stated boundary.

### 3.6 JSON endpoints: outside the crawler's field of view

The sixth target's home page links to a JSON endpoint, /api/search?q=, which places q verbatim into its JSON response. I verified with a separate manual probe: the endpoint returns 200 with Content-Type application/json, and both the token and the complete payload appear verbatim in the body — had this endpoint been probed, the XSS check's match condition would have been satisfied. In the real scan it was never probed. The crawler fetched the link, saw a non-HTML content type, and skipped it: the endpoint entered neither the page list nor the parameterized-URL list, so neither injection check ever saw it as input. The target's six findings were all headers-class; injection findings were 0.

The characterization needs restraint. Verbatim reflection inside an application/json response is not the same as XSS in an HTML context; modern browsers will not execute it as a page. Calling this a "missed XSS" would overstate it. The real conclusion is about the field of view: this pipeline can only see the HTML-page portion of an application. API endpoints — JSON backends, mobile APIs — are entirely outside it, and the report never tells you how large the visible portion was. For a scaffold that calls itself a web scanner, that belongs in the report, not just the README.

### 3.7 The authorization guard: five probes

The last experiment measures not detection quality but whether the pipeline will run at all — five probes against scope.py:

| Probe | Result |
|---|---|
| Target without an http(s) scheme | Refused (ScopeError: explicit URL required) |
| Authorization not confirmed | Refused (ScopeError) |
| Confirmed, local target | Allowed |
| Allowlist not containing the target host | Refused |
| Allowlist containing the target host | Allowed |

All five matched the design: no default target, no confirmation no scan, and an allowlist, when given, actually narrows scope. The guard is enforced in code rather than advised in documentation — not a given among learning-grade scanners, and worth recording.

## 4. Analysis and trade-offs

### 4.1 The four checks' false-positive control, graded individually

Ranked by decision method, the four checks are not equally armored. XSS carries the hardest evidence: a random token plus the complete payload as a dual condition excludes escaped reflection and static content by construction, and it produced a clean zero on the hardened target. Its only weakness is context expression — reflection via an error page is reported identically to reflection in normal rendering (sections 3.1 and 3.5). Sensitive-path probing has the weakest decision rule — status code only, zero content verification — and it fails wholesale on the most common modern deployment shape, the SPA. SQLi sits between: its payloads and signatures are not unreasonable, but the missing baseline makes it systematically wrong on sites that talk about databases, and the more generic the signature words, the worse it gets. Headers is the most deterministic check — a header is present or it is not — with one caveat: the Server info originates at the server layer, not in application code, and should not be graded alongside headers the application itself failed to set.

### 4.2 Fix order: baselines before breadth

In return-on-effort order. First, baselines and soft-404 sampling: the sensitive-path check should first fetch one random path as a baseline and downgrade or drop probe responses that closely resemble it; the SQLi check should send a baseline request before injecting, and skip any parameter whose normal response already contains the signature words. This one item treats sections 3.3 and 3.4 together — it is the hinge of false-positive control. Second, content sniffing: a .git/HEAD hit should begin with "ref:", an .env hit should contain key-value lines; verify content after a probe hits before assigning high severity. The source TODO already has this idea; it ranks after baselines because the baseline helps all 14 probes at once, while sniffing rules are written per path. Third, a not-covered section in the report: POST forms, non-HTML endpoints, pages beyond the crawl cap — listed explicitly, so misses become stated boundaries instead of silence. Fourth, and only then, breadth: POST SQLi, stored XSS, and blind SQLi are all on the TODO list, but breadth widens the promise; widen it before the baselines land and you manufacture false positives at a larger scale.

The judgment underneath the ordering: a scanner's credibility comes first from "what it reports is mostly real," and only second from "it reports a lot." This pipeline currently leans the other way — coverage grows, at least in its TODO plans, while the baselines that make verdicts trustworthy are still missing.

### 4.3 One judgment: false-positive control means giving every verdict a refutation procedure

Looking across the four checks, the reliable verdict (XSS) has a shared structure: its evidence is exclusive. A random token cannot pre-exist in the page; the complete payload appearing verbatim excludes escaping. The unreliable two lack exactly that. A 200 status is not exclusive evidence — a soft 404 is also a 200. A signature word in the prose is not exclusive evidence — it was there with no injection at all. Doing false-positive control on a detection pipeline means, in engineering terms, attaching a refutation procedure to every verdict class: first prove "without my attack, it is not there," then report "after my attack, it appeared." Baseline requests, soft-404 samples, and random tokens are three implementations of the same idea. That is why baselines rank ahead of every breadth item in section 4.2 — the gap is not a missing patch on one check, it is a missing step in the verdict methodology.

## 5. Limitations and open questions

The limitations, stated plainly. First, all six targets are minimal local apps, each isolating one site shape. Real sites mix shapes — an SPA with a genuinely exposed file, an article site with a real injection — and this article does not measure how false and true positives interact in mixed shapes. Second, the hardened app was written by the author against the checks' own list, a "studying to the test" bias: it proves the checks stay quiet on an ideal baseline, not that they stay equally quiet on mediocre real-world code. Third, every experiment ran over loopback; the timing figures are local orders of magnitude only (section 3.1's 0.04–0.19 s is one demo run's per-check times; across all six targets, per-check times spanned 0.003–0.23 s). Under real network latency, the 14 serial sensitive-path requests and the per-parameter serial payloads will stretch totals considerably, and concurrency and timeout behavior went unmeasured — the per-request timeout is a uniform 10 s in the source, and worst-case waits were not exercised. Fourth, the XSS-via-error-page path is classified here as a true positive because the payload does enter an HTML response unescaped; its exploitability in a real browser depends on the error page's content type and context, which this article did not verify at browser level. Fifth, the targets and the demo all run on the Flask/Werkzeug stack; other stacks change Server headers and error-page shapes, and the conclusions generalize only to similar shapes.

Three open questions remain. What similarity algorithm and threshold should define a soft-404 baseline — too loose leaks real files, too tight resurrects false positives — needs a corpus of real SPA samples to calibrate. After SQLi gains baseline filtering, will targets whose pages echo the same error stack with and without injection lose true positives to the filter? That needs a dedicated target shape to measure. And at what granularity should a not-covered list be reported — endpoints, parameters, or a check-by-endpoint matrix — is a question to settle after one real round of using it.

## 6. References

1. Web-Vuln-Scanner source (version measured here): github.com/Ezra-Zhao/Web-Vuln-Scanner — key files: scanner/cli.py (pipeline assembly, per-check failure isolation), scanner/scope.py (authorization guard), scanner/crawler.py (crawl and field of view), scanner/checks/xss.py, scanner/checks/sqli.py, scanner/checks/headers.py, scanner/checks/sensitive_files.py (the four checks and their TODOs), demo/vulnerable_app.py (demo target).
2. Experiment scripts and raw data for this article: data/2026-10-15-vuln-scanner-bench.py and data/2026-10-15-vuln-scanner-bench.json (per-check results, request counts, authorization probes, and the JSON reflection probe for all six targets), archived with this article; every number can be re-checked by re-running the script.
3. OWASP Testing Guide and OWASP ASVS: the conventional framing for injection testing and security headers; used as background orientation only, no specific figures quoted.

---

Author: Guangyi Zhao. The code, experiments, and text in this article are clean-room work by the author: the subject is an open-source scaffold project maintained by the author, every target is a locally built application, and all scanning happened on 127.0.0.1 loopback addresses. No third-party system was probed, and no customer information, customer systems, or third-party non-public data are involved. Every number comes from the measurements listed at the top of this article, and no scaffold state is presented as a mature product.
