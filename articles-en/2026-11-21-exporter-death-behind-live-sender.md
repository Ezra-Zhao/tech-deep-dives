# The Exporter Died Behind a Live Sender, and the Receiver Fired in 79 Seconds: Stale Markers Travel with Remote Write, Measured

Author: Guangyi Zhao

## 1. Background

The cell I measured in the previous article (2026-11-09) was a dead push chain: the sender Prometheus was killed, the exporter stayed perfectly healthy, and the receiver's present series lived out the full 300 s lookback before vanishing — the absent alert fired in the interval 366.8–371.1 s, and up sat frozen at 1 the whole time. That article left the mirror-image cell unmeasured: the exporter dies behind a sender that stays alive — the sender keeps scraping and keeps pushing, only what it scrapes has changed. What shape do the receiver's three paths take in that cell?

My reasoning before the run went like this. On the sender, present gets marked stale and stops being produced; that stoppage is bookkeeping inside the sender's local TSDB and does not travel with the sample stream, so the receiver can only wait for the last sample to age out of its 300 s lookback — absent should again take about 370 s. Up, on the other hand, should be fast: the sender is alive, failed scrapes produce up=0 samples stamped with current time and pushed continuously, so a receiver-side up == 0 rule ought to fire within a minute or two. One slow signal, one fast signal, separated by a full lookback — that was the main prediction I froze into the preregistration.

The headline: the up half was right, and the present half was cleanly wrong. Within 5.1 s of the exporter being killed, the receiver's instant query for present was already empty. The absent and up == 0 alerts on the receiver went pending in the same evaluation cycle (19.0 s after the kill, activeAt identical to the microsecond) and share a firing lower bound of 79.0 s. The cause is a mechanism I had missed: a stale marker is itself a sample. The special NaN the sender's scrape layer appends to a discontinued series enters the remote-write queue like any other sample, is pushed to the receiver, stored there, and honoured by queries. The criterion from the previous article — "whose clock keeps the series' time?" — needs a revision: what decides the blind-window tier is whether a stale marker gets written, and whether a live channel delivers it to the machine answering the query.

The design was frozen to disk before any live run (data/2026-11-21-exporter-death-prereg.md). Of six predictions, P-E1, P-E4, P-E5 and P-C hit; P-E2 (the lookback-tier main prediction) and P-E3 (the two signals separated by at least 240 s) missed. Section 3.2 owns the error.

## 2. Method

One discipline, shared with the 2026-11-09 run: Prometheus 3.15.0 (official tarball, 111,651,578 bytes, gzip verified; the bench directory had been cleaned since, so the tarball was downloaded and unpacked again this round), scrape interval 5 s, scrape timeout 4 s, rule-group evaluation 15 s, lookback at the default 300 s, a fresh TSDB per path, loopback only. The exporter is the repository's real exporter (src/prom_exporter.py) serving a copy of run 20261019-171627.

- Path E, the main cell: a sender Prometheus scrapes the exporter and remote-writes everything to a receiver Prometheus (started with --web.enable-remote-write-receiver, fresh TSDB, never scraping the exporter). Both the receiver and the sender carry two candidate rules: absent(nal_exporter_results_present{group="scenario_summaries"}), word for word the expression of the earlier articles, and up{job="net-assurance-lab"} == 0, this run's new candidate — both with for: 1m. The death is SIGTERM to the exporter only: a direct fetch of its /metrics right after the kill returns connection refused (confirmed dead), while the sender process stays alive for the whole phase and is still running at the end.
- Path C, the control: one Prometheus scrapes the same exporter directly, carrying the same two rules, with the same SIGTERM death — a fourth replication of the direct-scrape tier.

Each path runs the same phases: wait for a healthy baseline (on E, present equal to 1 and up equal to 1 on the receiver), hold 30 s, apply the death, poll until the absent alert fires, hold 20 s. The poller records instant queries for present, absent(), and up, plus the full alert snapshot, every 5 s; on path E it records the sender's local view of the same queries at the same time. Blind windows are measured as before: pending from the alert API's activeAt, firing as the interval [activeAt + for:, first poll that saw firing]. promtool check rules returned SUCCESS (2 rules).

The usual cold-start disclosure: on path E, both instances' absent alerts sat pending for 3–4 early baseline polls (the first evaluation ran before the series had ever arrived), resolved as soon as the series appeared, never fired, and the baseline was clean before the kill. Every pending time below is the kill's own, distinct activeAt. Path C showed no such race this round.

## 3. Measurements

### 3.1 The receiver: both alerts fire in the same cycle

One poll straddles the kill (in that poll up and present are both still 1). By the 5.1 s poll, three things have flipped on the receiver at once: up is 0 for the first time, the instant query for present is empty for the first time, and absent() returns 1 for the first time. Up never returns to 1 afterwards, and present never reappears.

The two alerts' ledgers coincide digit for digit: pending at 19.0 s after the kill for both, the same activeAt down to the microsecond, a firing lower bound of 79.0 s for both, and the first poll to see firing at 81.7 s for both. In this cell, absent and up == 0 are not a fast signal and a slow signal; they are two spellings of the same signal, riding the same scrape cycle — in the first failed scrape, the up=0 sample and present's stale marker are produced together, pushed together, and the receiver's rule group sets both alerts pending in one evaluation.

Up's continuity is worth its own line (preregistered as P-E5): in all 21 post-kill polls the receiver's up series is non-empty. The stream never breaks — the sender keeps pushing; only the value changes from 1 to 0. This is the exact mirror of the 2026-11-09 kill-the-sender cell, where up froze at 1 for 296 s without moving: there the channel was dead and the value froze; here the channel is alive and the value flips at once.

### 3.2 Why present did not wait out the lookback: where my main prediction went wrong

First, the evidence. The receiver's last present sample carries a timestamp -0.0 s from the kill moment — the sample landed in the very instant of the kill. Five seconds later, that sample is already invisible to an instant query. The lookback is 300 s; expiry cannot make a roughly five-second-old sample disappear. Prometheus has exactly one mechanism that hides a fresh sample immediately: a stale marker (a sample whose value is the special NaN) appended after it. A query looking back first meets the marker, and the series is judged terminated.

The link my preregistered reasoning missed is this one. I had treated "the sender marks the series stale locally" as internal bookkeeping in the sender's TSDB — a stoppage that produces nothing downstream. In fact a stale marker is not a bookkeeping note; it is a real sample appended to the series. When the scrape layer finds a series missing from a scrape result, it appends that NaN marker sample, and the sample travels the same road as every other sample: into the local TSDB, and into the remote-write queue. The Remote-Write specification states this outright: senders must send stale markers when the discontinuation of a series is detectable, the marker being signalled by a special NaN value (0x7ff0000000000002) that must not be used otherwise (the 2.0 specification words the duty as MUST; this run's sender speaks protocol 1.0, and its behaviour is established directly by the measurement, with the spec text as mechanism corroboration). The receiver stores the marker in its own TSDB, and its query semantics are indistinguishable from a locally produced marker.

So the four-cell table from the previous article gets a new criterion. The old one asked whose clock keeps the series' time. The new one asks two questions: when production stops, does anyone write a stale marker for this series — and is there a live channel to carry that marker to the querying instance? In the kill-the-sender cell, no marker could even be produced (the process was dead), let alone delivered: lookback tier. In the explicit-timestamp cell, Prometheus by design does not synthesise stale markers for such samples: lookback tier. In this cell, the marker is produced and the channel is alive: stale tier. Whether the channel lives is the boundary between 79 s and 370 s on one and the same path.

### 3.3 The sender's local view, and the direct-scrape control

On the sender itself: present and up flip in the same 5.1 s poll; both alerts go pending at 4.0 s after the kill, with a firing lower bound of 64.0 s and first sighting at 66.4 s. The receiver trails the sender by exactly 15.0 s — the pending gap and the firing-lower-bound gap are the same 15.0 s — precisely one rule-group evaluation interval: pushing and queue flushing cost well under a second, and the extra time is the receiver's rule group running one beat out of phase with the sender's. Preregistered P-E4 (local absent inside 60–90 s, local up inside 60–110 s) hit.

Path C, the control: present and up flip in the 5.1 s poll as well; both alerts go pending at 1.1 s, firing lower bound 61.1 s, first sighting 65.8 s. The direct-scrape tier's previous three firing lower bounds were 73.9, 74.2 and 70.1 s; this round's 61.1 s is faster and still inside preregistered P-C's 60–85 s. The spread across four rounds is evaluation phase; the tier does not move. One more line for the ledger: on the direct path, too, up == 0 and absent share a cycle and an activeAt — the two rules were never at different speeds under scraping. The new information in this run is specific to the remote-write cell.

Five cells under one discipline (for: 1m, lookback 300 s):

| Cell | present empties | up behaviour | absent firing lower bound | up == 0 firing lower bound |
|---|---|---|---|---|
| Direct scrape (this run, C) | 5.1 s | flips to 0 at 5.1 s | 61.1 s | 61.1 s (same cycle) |
| Recording-rule replica (2026-10-31) | about 5 s | flips to 0 at 5.0 s | 74.1 s | not measured |
| Explicit sample timestamps (2026-10-31) | still visible at 303.1 s poll | flips to 0 at 5.0 s | 369.4 s | not measured |
| Remote write, sender killed (2026-11-09) | 301.0 s | frozen at 1, vanishes in the same poll | 366.8 s | never (no 0 sample ever arrives) |
| Remote write, exporter killed (this run, E receiver) | 5.1 s | flips to 0 at 5.1 s, keeps being pushed | 79.0 s | 79.0 s (same cycle) |

## 4. Analysis and Trade-offs

For centralised-receiver deployments, the first conclusion corrects an over-broad worry the previous article may have left behind. That article said receiver-side absent rules should budget the lookback tier — a statement that holds only for the stopped-push cell. When the sender is a live, genuine Prometheus and what died is a target behind it, the stale marker is pushed across, and both absent and up == 0 on the receiver are minute-scale (79 s under this discipline), not six minutes. The cell that truly needs the lookback budget is the sender itself dying or going unreachable.

Second, the revised criterion, offered as a replacement for the old framework: the blind-window tier of a series at a querying instance is decided by stale-marker production × delivery. Production depends on how the series is made — scrapes and recording rules write a marker the moment they stop returning the series; explicitly timestamped samples get none. Delivery depends on the channel — a local query is delivered by construction; remote write delivers while the sender lives and cannot deliver once it is dead. Fill in those two cells for any anti-blind rule before quoting it a number.

Third, choosing between the two rules. In this cell and in the direct-scrape cell, absent and up == 0 fire in the same cycle; there is no speed difference to argue about, so choose by semantics. Up == 0 says "the scrape is failing" — true for a dead exporter process, a refused port, a hanging endpoint. Absent says "this series is gone" — also true when the target lives but stops producing the series (output deleted, configuration changed, series renamed); in the 2026-10-27 article's deleted-output cell, up stayed 1 and only absent fired. Running both, with that division of meaning, is worth more than debating which is faster — and this run's data says that, sender alive, neither is slow on the receiver.

Fourth, a note for non-Prometheus receivers. This run's receiver is Prometheus itself, which stores and honours stale markers. Some third-party remote stores have historically treated stale NaNs inconsistently — ignoring them, or storing them as ordinary samples — and a receiver that ignores the marker drops this cell back to the lookback tier. That sentence is an inference (evidence grade C; no third-party receiver was measured this round), but it points at a ten-minute check worth doing before deployment: stop producing a test series at the sender and watch how many seconds it takes to disappear on your receiver. The answer decides your tier directly.

No repository rule files were changed in this run; the candidates and measurement material stay in this project's data/, as with the earlier articles.

## 5. Limitations and Open Questions

- Only Prometheus-to-Prometheus remote write over protocol 1.0 was measured. How third-party receivers (remote stores and gateways of various kinds) respect stale markers was not measured one by one; Section 4's fourth point supplies a verification method, not an answer. A sender in agent mode runs the same scrape and remote-write code and should land in the same tier by mechanism, but was not measured separately.
- The network-partition cell is unmeasured: with the sender alive but unable to push, stale markers would queue on the sender, the receiver's blind window should stretch by the partition's duration, and the alert should then fire promptly once delivery resumes. That is an inference, not a measurement.
- The exporter's death was a clean SIGTERM. In a hang death (SIGSTOP-style, every scrape running out the full 4 s timeout), the moment the sender writes present's marker may be delayed by seconds, and up=0 likewise waits for the in-flight scrape to be judged failed; the 2026-10-10 article measured the hang only on the direct-scrape path, not in this cell.
- The intermittently-succeeding half-death (scrapes straddling the timeout, succeeding now and then) is still unmeasured: each success refreshes the series, and how stale markers and lookback account for that is the next cell in the pool.
- This round's control firing lower bound, 61.1 s, is the fastest of four rounds; the spread against the earlier rounds (up to about 13 s) is attributed to evaluation phase, with no phase-controlled experiment to isolate it. The tier conclusion is unaffected, but quote the absolute number together with the earlier rounds (a band of roughly 61–76 s).
- Loopback, one sender, one receiver, for: 1m — the same scope boundaries as the earlier articles. The 79 s absolute figure is bound to this discipline; the receiver-versus-sender phase difference (15.0 s this round) will float between 0 and 15 s with deployment phase.

## 6. References

1. Prometheus documentation, Querying / Basics, "Staleness": the lookback defaults to 5 minutes; when a scrape or rule evaluation stops returning samples for a previously present series, the series is marked stale; exporters that set their own sample timestamps are the exception. https://prometheus.io/docs/prometheus/latest/querying/basics/
2. Prometheus Remote-Write specification (version 2.0, experimental): senders must send stale markers when the discontinuation of a series is detectable, and a stale marker is signalled by a special NaN value. This run's sender speaks protocol 1.0; its stale-marker propagation is established directly by this run's measurements, with the specification text as mechanism corroboration. https://prometheus.io/docs/specs/remote_write_spec_2_0/ (mirror at https://prometheus.cndevdoc.com/docs/specs/prw/remote_write_spec_2_0/, same text)
3. Prometheus documentation, Querying / Functions, absent(): returns 1 when the input vector is empty. https://prometheus.io/docs/prometheus/latest/querying/functions/
4. Code under test (local repository net-assurance-lab): src/prom_exporter.py (collect() renders nal_exporter_results_present and never writes sample timestamps).
5. Earlier articles in this repository: "The Source Is Alive, the Push Stopped, and the Blind Window Is Still Six Minutes" (2026-11-09, the kill-the-sender cell and this run's origin), "Give the Samples Timestamps and the Blind Window Goes Back to Six Minutes" (2026-10-31), "Anti-Blind Alerting, Measured: I Assumed absent() Waits Five Minutes" (2026-10-27).
6. This run's material (archived in this project's data/ and mirrored into the tech-deep-dives repository's data/ with the Chinese article): 2026-11-21-exporter-death-prereg.md (the preregistration, frozen before the run), 2026-11-21-exporter-death-rules.yml (the two candidate rules, promtool check SUCCESS), 2026-11-21-exporter-death-live.py (the live script), 2026-11-21-exporter-death-live-progress.jsonl (per-poll progress), 2026-11-21-exporter-death-live.json (full records and summary), 2026-11-21-exporter-death-posthoc.py and 2026-11-21-exporter-death-posthoc.json (timeline and preregistration recomputation), 2026-11-21-exporter-death-bench.json (version, promtool and contrast summary). The Prometheus binary is the official 3.15.0 release and is not distributed with the repository.

---

Author: Guangyi Zhao. The experiment design, code and data in this article are clean-room work of my own: the bench, the sender/receiver configurations, the rules and the live script were all written by hand; the experiment ran only on loopback and local files on my own machine; the only processes killed were ones I started; no client information and no third-party system is involved.
