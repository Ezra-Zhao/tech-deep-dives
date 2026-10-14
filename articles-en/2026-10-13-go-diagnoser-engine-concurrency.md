# How Big Should the Worker Pool Be? Measuring the Concurrency Model of a Go Diagnostics Engine

Author: Guangyi Zhao
Date: 2026-10-13
Subject: Go-Diagnoser-Engine (open source, github.com/Ezra-Zhao/Go-Diagnoser-Engine), Go 1.24, zero third-party dependencies
Test setup: Linux x86_64 VM, 2 vCPUs, server and load client on the same host

## 1. Problem and background

Running diagnostics against a fleet of nodes has two failure modes callers hate. Wait synchronously and one slow check hangs the request. Spawn goroutines without limits and a traffic spike takes the service itself down before any node gets diagnosed. So I built Go-Diagnoser-Engine as an asynchronous service: POST /api/v1/diagnose submits a job and returns a job ID, GET /api/v1/jobs/{id} is polled for structured results. Execution sits behind a bounded worker pool fed by a bounded queue, and the checks inside one job fan out in parallel.

The structure is easy to write. The numbers are the hard part. How many workers? How deep a queue? Does a job with three checks cost three times the latency of a one-check job, or roughly the same? When the queue fills up, do you block or reject — and can you predict the rejection count in advance? This article answers those questions by actually loading the service, then goes back to the source to judge which design choices the data supports and which ones only looked reasonable while I was typing them.

One disclosure up front, because everything else depends on it: the project is a scaffold, and its README says so. The three registered checks (connectivity, disk_usage, service_health) are simulated — each sleeps a random 50–200 ms and passes with 90% probability, and every result is labeled SIMULATED. The real probes (ICMP/TCP, disk scraping, /healthz queries) are still TODOs in the code. So this article measures the concurrency skeleton, not diagnostic ability. The throughput, latency, backpressure, and race behavior below are real measurements; swap in real probes and some of the numbers will move. Section 5 spells out which conclusions break first.

## 2. Method and architecture

The codebase is 523 lines across 6 Go files. go.mod contains a module path and a Go version and nothing else — no third-party dependencies. cmd/server is the entrypoint: it reads PORT, WORKERS, and QUEUE_SIZE, wires the parts together, and owns graceful shutdown. internal/api holds the net/http routes, registered with Go 1.22 method-and-pattern syntax. internal/engine is the worker pool and check registry. internal/store is a concurrency-safe in-memory job store. pkg/models holds the shared types.

Four concurrency decisions, all deliberate:

First, a fixed worker pool instead of a goroutine per request. Workers are long-lived goroutines; the pool size defaults to runtime.NumCPU() and is overridable via WORKERS. The concurrency ceiling is a deployment parameter, not something that drifts with traffic.

Second, a bounded queue with fail-fast submission. Submit uses a non-blocking select: if the queue is full, the API returns 503 immediately instead of parking the HTTP request. The cost is pushed to the caller, who must retry. Whether that trade is fair is a data question, answered in section 3.3.

Third, per-job fan-out. runJob starts one goroutine per check and collects results into a preallocated slice indexed by check position — each goroutine writes only its own slot, so there is no mutex and no result channel to drain. A sync.WaitGroup joins them, and each check runs under its own 30-second context timeout so one slow probe cannot stall the whole job.

Fourth, cooperative shutdown. On SIGINT or SIGTERM, main closes the HTTP server (15-second budget), then engine.Shutdown cancels the engine context and waits for workers to drain, also capped at 15 seconds.

Method: I copied the repository verbatim into a scratch directory and built it (8.7 MB binary; 11 MB with -race). A Python load script, archived with the raw results alongside this article, ran four experiments. A: 30 one-check jobs and 30 three-check jobs submitted sequentially, comparing end-to-end latency. B: 60 three-check jobs submitted concurrently at pool sizes 1, 2, 4, and 8, measuring wall time and completions per second. C: queue squeezed to 5 with a single worker, a burst of 30 concurrent submissions, counting 202s against 503s. D: the race-detector build under 100 concurrent jobs with aggressive polling, plus a SIGTERM shutdown check.

## 3. Measurements

### 3.1 Fan-out is real: three checks cost 19% more, not 200%

Experiment A (30 jobs per row, 4 workers):

| Configuration | Mean end-to-end | p50 | p95 | Mean per-check latency |
|---|---|---|---|---|
| One check (connectivity only) | 139.8 ms | 151.5 ms | 198.6 ms | 135.6 ms |
| Three checks (all) | 166.5 ms | 169.9 ms | 201.9 ms | 126.0 ms |

Tripling the checks raised mean end-to-end latency by 19%. Had the fan-out secretly been serial, three checks would have landed near three times a single latency, around 400 ms. The numbers also agree with theory. A single check is uniform on 50–200 ms; a parallel job finishes with its slowest check, whose expected value is 50 + 150 × 3/4 = 162.5 ms. Measured: 166.5 ms, within 2.5%. Per-check means (135.6 and 126.0 ms) also sit close to the uniform expectation of 125 ms. This experiment validates two things at once: the fan-out is genuinely parallel, and my description of the simulated delay distribution was accurate.

Where did the extra 27 ms (166.5 minus 139.8) go? I did not take segmented timings, so this is a labeled guess, not a finding: timer wakeups landing together, plus lock traffic when results are stored, are the plausible contributors. What matters more is the boundary of the claim — the fan-out dividend comes from checks waiting on each other. Make the checks CPU-bound and this arithmetic has to be redone.

### 3.2 Throughput scales almost linearly — do not celebrate yet

Experiment B (60 three-check jobs per row, 20 client threads submitting and polling):

| Workers | Wall time | Completion rate | Speedup vs 1 worker |
|---|---|---|---|
| 1 | 9.71 s | 6.2 jobs/s | 1.0 |
| 2 | 4.98 s | 12.0 jobs/s | 1.9 |
| 4 | 2.58 s | 23.2 jobs/s | 3.7 |
| 8 | 1.34 s | 44.9 jobs/s | 7.2 |

Eight workers on a 2-vCPU box delivering 7.2× the single-worker rate looks too good, and it is — for the right reason. A simulated check does no work at all; it parks on a timer. Worker count is therefore pure concurrency, and the rate is simply workers divided by per-job time. The single-worker prediction is 1 / 0.1625 ≈ 6.15 jobs/s; measured 6.2.

What this actually proves is narrow but worth having: the pool has no hidden serial bottleneck — neither the queue nor the store's locking ate the scaling. It proves nothing about real probes. Add CPU-heavy parsing or classification and a 2-vCPU box will saturate around 2–4 workers, possibly regressing beyond that. Make the probes network-bound and the bottleneck moves to the targets or to connection counts. Extrapolating this line into production claims is the most common way load tests like this one get abused, so the line stops here.

### 3.3 Backpressure you can compute in advance

Experiment C used the tightest settings: 1 worker, queue depth 5, one burst of 30 concurrent submissions. Result: 6 accepted with 202, 24 rejected with 503. The 6 is not luck. Total admission capacity is workers plus queue depth — one job running, five waiting — and the seventh submission onward failed fast. No request was parked. All six accepted jobs were later polled to completion; nothing accepted was silently dropped.

The gap is on the response side. A 503 from this API carries one error string: no Retry-After, no queue depth, nothing a client can schedule a retry against. For a machine-facing API, fixing that outranks adding any new check.

### 3.4 Races and shutdown

Experiment D ran 100 jobs against the -race build with submissions, execution, and polling all hammering the same in-memory store. The race detector reported nothing, and all 100 jobs completed. The code supports the result: every store access goes through one sync.RWMutex and reads return copies; fan-out writes land in disjoint slice slots, and the WaitGroup join establishes the happens-before edge before results are persisted.

One honest footnote. My first run of this experiment saw only 92 of 100 jobs finish inside the polling budget. The cause was my harness, not the server: the -race build answers each request more slowly, and my poll loop gave up too early. Widening the budget to 20 seconds and rerunning produced 100 out of 100. I am leaving this in because it is exactly how load tests lie — the observer's limit masquerading as the system's failure.

Shutdown: SIGTERM on an idle server produced the full sequence (shutting down, all workers stopped, bye) in about 1.0 second. That test had no jobs in flight. What shutdown does to in-flight work was not measured — but reading the code turned up a real problem, covered next.

### 3.5 A small defect found along the way: unstable result order

With all checks selected, the order of the results array is not stable. In a sample of 20 jobs, two orders appeared (connectivity, disk_usage, service_health in 17; service_health first in 3). The cause sits in resolveChecks: for the "all checks" case it ranges over a map, Go map iteration order is randomized, results are filled by that list's indices, and the randomness leaks straight into the API response. Clients must match results by name, never by position. The fix is a one-line ordered registry, but the lesson generalizes: any map inside your service is a randomness source waiting to surface at the API boundary.

## 4. Analysis and trade-offs

Four judgments I would reuse, each tied to evidence above:

Make the concurrency ceiling explicit, not traffic-dependent. A fixed pool plus a bounded queue turns admission capacity into a computable constant — workers plus queue depth — and the measured 503 boundary matched that constant exactly. Alerting, capacity planning, and rate policy all need a number like that. A goroutine per request is faster at low load and has a ceiling nobody can state.

Async submission buys a predictable submit path. A submit request only validates, creates a record, and enqueues; the HTTP layer's 10 s read and 30 s write timeouts can never be touched by a slow check. The price is client-side polling and, until server-sent events exist (they are on the roadmap, not in the code), delayed completion awareness.

Pick the simplest fan-out primitive that is actually correct. An indexed slice plus a WaitGroup beat a result channel here: less code, no collection loop, and a clean race-detector run to back it. The precondition is that checks share no writes and have no ordering dependencies. The day checks need to hand intermediate results to each other, this structure gets replaced, not stretched.

Zero dependencies is a deliberate constraint with an expiry date. Standard library only — ServeMux routing from Go 1.22, crypto/rand job IDs — keeps the build and audit surface small at 523 lines. The missing production pieces (metrics, rate limiting, structured logging) are equally obvious. For a scaffold this is the right call; the call expires the day real probes land.

Three spots in the code do not survive scrutiny, in order of severity:

Shutdown semantics disagree with job status. engine.Shutdown cancels the context first, and the worker loop selects between the cancellation case and the queue — when both are ready, the choice is random. A queued job may be abandoned with its status stuck at queued forever. Worse, an in-flight job whose checks abort on cancellation still flows into SetResults and gets marked done, indistinguishable from a job that ran to completion. With an in-memory store the process exits and none of this matters; the roadmap's durable store turns it into real semantic debt. Abandoned jobs need an explicit terminal state.

The store never evicts. Every job record lives in the map for the life of the process. Fine for a scaffold; a long-running service needs a TTL or a capacity cap. This one is not a risk, it is a certainty with a date.

Submit has a narrow shutdown race. Its select includes the context-done case, the queue-send case, and a default. If shutdown begins while the queue still has room, the send case can win and enqueue a job nobody will ever run. Rare, but precisely the kind of rare that costs an afternoon when it fires. Checking the context once before the select closes it.

## 5. Limitations and open questions

The largest limitation is the one from section 1: every load in this article is a timer. Linear throughput scaling therefore certifies the skeleton, not the probes; the fan-out latency dividend assumes checks that wait; memory and GC behavior under this load would be meaningless to report, so they are not reported.

Method limits, stated plainly: one batch per configuration (30 jobs per row in A, 60 in B, a single burst in C), no repeated trials and no confidence intervals. Client and server shared a host, so polling cost excludes any network. The box is a shared 2-vCPU VM; treat the digits as magnitudes and ratios, not as constants of nature.

Three open questions gate the next round of code. Once real probes exist, should pool size be tuned to CPU or to what the targets can absorb — those two tuning curves need separate load runs. How should queue depth, the 503 rate, and client retry policy interact — that needs a retrying client in the loop. And when the durable store lands, the shutdown and terminal-state semantics from section 4 get fixed first, followed by a shutdown test with jobs actually in flight.

## 6. References

1. Go-Diagnoser-Engine source (the version measured here): github.com/Ezra-Zhao/Go-Diagnoser-Engine — internal/engine/engine.go (pool and fan-out), internal/engine/checks.go (simulated checks and registry), internal/api/router.go (routes and the 503 path), internal/store/store.go (in-memory store), cmd/server/main.go (wiring and shutdown).
2. Raw data and load scripts archived with this article in the project ledger's data directory (2026-10-13-go-diagnoser-bench.json, bench.py, race_shutdown.py); every number above can be reproduced from them.
3. Go documentation: net/http ServeMux method and pattern routing (Go 1.22+), sync.WaitGroup, and the happens-before definitions in the Go memory model (pkg.go.dev, go.dev/ref/mem).

---

Author: Guangyi Zhao. All code, experiments, and text in this article are clean-room work by the author: the system under test is the author's own open-source scaffold, load was generated in a self-hosted environment, and no client information, client systems, or third-party non-public data are involved. All figures come from the measurements described above; the simulated nature of the workload is stated in the text and no simulated result is presented as real diagnostic performance.
