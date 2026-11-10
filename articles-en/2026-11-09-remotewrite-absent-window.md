# The Source Is Alive, the Push Stopped, and the Blind Window Is Still Six Minutes: Measuring absent() on the Remote-Write Path

Author: Guangyi Zhao

## 1. Background

This is the fourth bookkeeping path whose absent() blind window I have measured in this series. The first three entries in the ledger: on the ordinary scrape path, a dead source is marked stale by the scrape layer at once and the blind window is about 75 s; a series replicated by a recording rule dies in the same evaluation cycle as its original, again about 75 s; and when samples carry their own timestamps, nobody writes a stale mark, the series lives out the full 5-minute lookback, and the window returns to about 370 s (measured under one discipline on 2026-10-27 and 2026-10-31). The 2026-10-31 article left one boundary unmeasured: a series ingested by remote write. The receiver neither scrapes it nor produces it by a local rule evaluation. When the push stops, which tier does its blind window land in — the stale tier or the lookback tier?

This is not an academic cell. Centralised receivers are a common deployment shape now: an edge Prometheus (often in agent mode) scrapes local targets and remote-writes the samples to a central receiver, where the alerts live. Push chains break in several ways — the sender process dies, an upgrade restarts it, a network partition opens — while the pushed source itself may be perfectly healthy. How long absent() takes to fire in that cell decides how long a broken push stays invisible.

The headline: the lookback tier. After the sender was killed, the exporter stayed alive for the entire run (a direct check right after the kill still returned present equal to 1), yet the receiver's present series lived on for another 301.0 s before disappearing, and the absent alert fired in the interval 366.8–371.1 s — nearly coincident with the timestamped path's 369.4–373.8 s. The same run's direct-scrape control fired with a lower bound of 70.1 s; the two tiers differ by 296.7 s, one lookback minus the stale path's few seconds of alignment. And one cell is worth more than the headline: on the receiver, even up is a pushed sample. After the sender died it froze at 1 for a full 296 s without moving, then vanished in the same poll as present. There is no fast death signal anywhere on this path; an up-based rule here is decoration.

The design was frozen to disk before any live run (data/2026-11-09-remotewrite-prereg.md). Of four predictions, the main one and two others hit; one missed as written — I had preregistered that the receiver would hold no up series at all, when in fact up is present, merely frozen. Section 3.3 owns that error.

## 2. Method

One discipline for both paths: Prometheus 3.15.0 (official tarball, 111,651,578 bytes, gzip verified; same version as the previous three articles, for comparability), scrape interval 5 s, scrape timeout 4 s, rule-group evaluation 15 s, for: 1m on the absent alert, lookback at the default 300 s, a fresh TSDB per path, loopback only.

- C, ordinary scrape (control, a re-measurement): one Prometheus scrapes the repository's real exporter (src/prom_exporter.py) serving a copy of run 20261019-171627; the alert is absent(nal_exporter_results_present{group="scenario_summaries"}), word for word the expression of the previous articles. The death is SIGTERM to the exporter, as before.
- W, remote write: a sender Prometheus scrapes the same exporter under the same settings and remote-writes everything to a receiver Prometheus (started with --web.enable-remote-write-receiver, fresh TSDB, never scraping the exporter; the alert is the same expression over the pushed series). The death is SIGTERM to the sender only — it exited within 0.1 s — while the exporter is left untouched and verified healthy immediately after the kill by fetching its /metrics directly, bypassing both Prometheus instances. Path W therefore measures a stopped push, uncontaminated by a dead source.

Each path runs the same phases: wait for a healthy baseline (present equal to 1; on W, present equal to 1 on the receiver), hold 30 s, apply the death, poll until the main alert fires, hold 20 s. The poller records instant queries for present, absent(), and up{job="net-assurance-lab"}, plus the full alert snapshot, every 5 s. Blind windows are measured as before: pending from the alert API's activeAt, firing as the interval [activeAt + for:, first poll that saw firing]. promtool check rules returned SUCCESS (1 rule).

Both paths show the same cold-start race disclosed in the 2026-10-31 article: the first rule evaluation ran before the series had ever arrived, so the absent alert sat pending for four early baseline polls, resolved as soon as the series appeared, never fired, and the baseline was clean before the kill. Every pending time below is the kill's own, distinct activeAt.

## 3. Measurements

### 3.1 Path C: 70.1 seconds, a third replication

In the first 5 s poll after the exporter was killed, present is already empty, absent() already returns 1, and up has flipped to 0. The alert enters pending 10.1 s after the kill (the first evaluation cycle) and its firing lower bound is 70.1 s, with the first poll to see firing also at 70.1 s. Against the two earlier rounds (pending 13.9 and 14.2 s; firing 73.9–75.1 and 74.2–75.5 s), this round is about 4 s faster, a matter of evaluation phase, and still inside the preregistered P-C band of 60–85 s. Three independent live runs now pin the direct-scrape tier to roughly 70–76 s; the comparisons below use this run's 70.1 s.

### 3.2 Path W: the series outlives the push by 301 seconds

At the moment the sender dies, the receiver knows nothing. It has no scrape, no connection state to inspect — only a sample stream that has stopped, and a stopped stream is only visible at query time. The receiver's instant query for present keeps returning 1 until the poll 301.0 s after the kill, which is the first to come back empty; absent() first returns 1 in that same poll. The alert shifts by the same amount: pending at 306.8 s (the first evaluation cycle after the lookback expired), firing interval 366.8–371.1 s. The preregistered main prediction P-W1 (355–390 s) hit.

Converted to the sample's own timeline, the bracket is tight. The sender scraped every 5 s, so the last pushed batch carries a timestamp within one scrape interval before the kill; the sender's graceful exit 0.1 s after SIGTERM bounds any shutdown queue flush to that same moment. The last sample's timestamp therefore sits between 5 s before the kill and 0.1 s after it, and the series remained visible for 300.9–306.0 s after that timestamp — the 300 s lookback plus query and evaluation alignment, the same shape as the timestamped path's bracket (303.1–308.1 s). The two paths converge for the same reason: the sample's time is decided elsewhere, and nothing in the receiver's local bookkeeping can write a stale mark when the stream stops.

The difference ledger against path C: pending is 296.7 s later, the firing lower bound is 296.7 s later — the two differences agree to the tenth of a second. The whole alert chain is translated by one lookback (300 s) minus the roughly 3 s of staleness and alignment on the scrape path. The firing lower bounds stand in a ratio of 5.23.

The source's survival is booked separately (preregistered P-W3): fetched directly right after the sender was killed, the exporter's /metrics returned the present line with value 1, and the exporter process was never touched during path W. So for the whole 366.8 s blind window the monitored object was alive and healthy; only the push segment of the observation chain was broken. When absent finally fires on a receiver, what it reports is not "the target died" but "I have heard nothing for six minutes" — and in this cell those two statements must not be confused.

### 3.3 up was pushed too — and then it froze at 1

Preregistered P-W2 said the receiver would hold no up series for the job at all, because the receiver keeps no scrape bookkeeping. As written, it missed. The receiver answered up{job="net-assurance-lab"} in 67 of 89 polls. I had forgotten one plain fact while writing the preregistration: up is not receiver-side bookkeeping. It is an ordinary series the sender produces while scraping, and remote write ships it like any other.

The substantive conclusion survived, in a worse form than preregistered. After the sender's death, the receiver's up takes exactly one value across every post-kill poll: 1.0. Its last non-empty appearance is the poll 296.0 s after the kill, and it first comes back empty in the very same poll as present, at 301.0 s. An up==0 rule on the receiver would wait forever for a 0 that never arrives: the last up sample in the stream says 1, no later sample overwrites it, and it can only expire with the lookback, together with every other pushed series. Contrast path C, where up flips to 0 in the first poll after the kill and stays visible — same metric, fastest signal on one path, a frozen tombstone on the other.

This error goes into the method ledger next to its sibling: P-W2 and the overturned cell of 2026-10-27 are the same family of mistake, a missing mechanism — there the stale mark, here the fact that up itself is a pushed sample. That is exactly what preregistration is for: the wrong reasoning is written down in advance, so the measurement can say precisely which step of it leaked.

## 4. Analysis

The four paths now fit in one table (one discipline throughout: for: 1m, lookback 300 s):

| Bookkeeping path | Who writes the stale mark | absent firing | Fast signal |
|---|---|---|---|
| Direct scrape | The scrape layer, the moment scraping stops | 70.1 s (this run; earlier rounds 73.9–75.5) | up flips to 0 within 5 s of the kill |
| Recording-rule replica | The rule-evaluation layer, the moment production stops | 74.1–75.2 s (2026-10-31) | Same as scrape |
| Samples carry own timestamps | Nobody | 369.4–373.8 s (2026-10-31) | up flips to 0 within 5 s of the kill |
| Remote-write receiver | Nobody | 366.8–371.1 s (this run) | None: up freezes at 1 |

There is exactly one sorting criterion: when a series stops, does the Prometheus that holds it have a local bookkeeping act that marks it stale? Scrapes and rule evaluations are local bookkeeping and mark on stopping. Timestamped samples and remote-written samples have their time decided elsewhere; locally there is nothing to mark with, so the series can only age out through the lookback. Before budgeting any blind-spot rule, ask who keeps the time for its target series. Four articles in, that is the one decision rule worth keeping.

Three actionable conclusions for central-receiver deployments. First, budget every absent rule that lives on a receiver in the lookback tier: roughly lookback plus for:, about 370 s at these settings. Budget it at the scrape tier's 75 s and, the day a push breaks, the team is blind for six minutes before the runbook even starts. Second, take the death signal back to the sender. The sender holds real scrape bookkeeping; its up and absent are fast. Alert on the sender's own health — process liveness, remote-write send success and queue backlog, all of which live on the sender — instead of asking the receiver to infer a death from a silent stream. Third, if receiver-side detection is truly the only option, the sole lever is shrinking the instance's lookback (--query.lookback-delta), and it is an instance-wide cut that changes the semantics of every instant query to buy one chain a shorter window; for most deployments that trade is not worth it. This is a judgement call, not a measurement from this run — evidence grade C, offered as a direction only.

One tempting misdesign deserves dismantling in advance: bolting a "heartbeat metric plus absent" chain onto the pushed series does not make it faster. A heartbeat is a pushed sample too; when the push stops it lives out the same lookback. This run's frozen up is the ready-made proof — in this cell a heartbeat and a business series are indistinguishable.

No repository rule files were changed in this round. The candidates and the measurement material stay in this project's data/, as in the previous articles.

## 5. Limitations and Open Questions

- The sender was a full Prometheus scraping and forwarding, which speaks the same remote-write protocol as the agent mode common in production; other pushers (direct-pushing exporters, OTLP gateways, vmagent) were not measured one by one. By the criterion of section 4 they belong to the same "time kept elsewhere" tier, but their queue-flush and exit behaviour differs, which moves the last-sample bracket by seconds, not the tier.
- The death was a graceful SIGTERM (exit in 0.1 s). Under kill -9, a host power loss, or a network partition, the sender cannot flush its queue; the last sample can only be older, never newer, so the window measured from the kill moment can only grow by seconds. These deaths were not measured individually.
- Path W killed the sender and spared the exporter. The mirror cell — the exporter dies behind a living sender — is unmeasured: there the sender keeps pushing up=0 while present is staled locally at the sender and stops, then ages out at the receiver by lookback. Which of up and absent speaks first in that cell, and by how much, is the next measurable boundary; it has been added to the topic pool.
- The scrape-timeout death (process hung, every scrape running into the timeout) remains unmeasured for every path; it is still owed in the topic pool. This round varied the bookkeeping path, not the manner of death.
- Only the present family and up were measured. High-cardinality pushed families are inferred to behave by the same mechanism, not verified series by series.
- Loopback, one sender, one receiver, for: 1m: the boundary conditions match the previous articles. The absolute figure of about 370 s is bound to the default 300 s lookback; chains with a different lookback setting should recompute from the framework of section 4 rather than copy the number.

## 6. References

1. Prometheus documentation, Querying / Basics, "Staleness": the lookback is 5 minutes by default; a series is marked stale when a scrape or a rule evaluation stops returning it; exporters whose samples carry their own timestamps are the named exception. https://prometheus.io/docs/prometheus/latest/querying/basics/
2. Prometheus documentation, Storage / Remote write, and the command-line flag --web.enable-remote-write-receiver: the receiver accepts samples at /api/v1/write into its local TSDB. https://prometheus.io/docs/prometheus/latest/storage/ and https://prometheus.io/docs/prometheus/latest/command-line/prometheus/
3. Prometheus documentation, Querying / Functions, absent(): returns 1 when the input vector is empty. https://prometheus.io/docs/prometheus/latest/querying/functions/
4. Code under test (local repository net-assurance-lab): src/prom_exporter.py (collect() renders nal_exporter_results_present and never writes sample timestamps).
5. Previous articles in this repository: "Blind-Spot Alerts, Measured" (2026-10-27, the source of the direct-scrape tier) and "Add a Timestamp to the Sample and the Blind Window Goes Back to Six Minutes" (2026-10-31, the recording-replica and timestamped tiers). This article takes up the remote-write boundary the latter booked as unmeasured.
6. This run's material (archived in this project's data/ and mirrored into the tech-deep-dives repository's data/ with the Chinese version): 2026-11-09-remotewrite-prereg.md (the preregistration, frozen before the run), 2026-11-09-remotewrite-rules.yml (the rule file shared by both paths; promtool check SUCCESS), 2026-11-09-remotewrite-live.py (the live harness), 2026-11-09-remotewrite-live-progress.jsonl (per-poll progress), 2026-11-09-remotewrite-live.json (full records and summary), 2026-11-09-remotewrite-posthoc.py and 2026-11-09-remotewrite-posthoc.json (the bracket and up-ledger recomputation), 2026-11-09-remotewrite-bench.json (versions, promtool result, preregistration verdicts). The Prometheus binary is the official 3.15.0 release and is not redistributed with the repository.

---

Author: Guangyi Zhao. The experiment design, code and data in this article are the author's own clean-room work: the test bench, the sender and receiver configurations, the rules and the live harness were all written by the author; the experiments ran only on local loopback and local files; the only processes killed were the author's own; no customer information or third-party system is involved.
