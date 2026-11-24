# All Three Pressures at Once Pushed the Bench Gap to 56.6 Points and Through the Alert Line: Combined Factors and Burst Pulses, Measured

Author: Guangyi Zhao

## 1. Problem and background

This is the fourth round of one long investigation. On 2026-10-28, while measuring an injection-band alert, I watched the first-hop bench gap — gap = 1 − in_client/sent, the share of 10,000 generated packets that never reached the fault proxy — drift between 0% and 29.8% across 28 runs, wide enough to flip an alert verdict. Two controlled rounds then excluded the dimensions one at a time. CPU alone (2026-11-03: six busy-loop hogs on four cores, 1.5× overcommit) produced a median gap of 3.99 points and a maximum of 9.69. Memory residency and synchronous disk IO (2026-11-11) produced almost nothing: 0.46 points at a 1000 MB resident cap, and exactly zero for four sync writers. No single dimension came close to 29.8%.

Two questions remained, and this round answers both. First: if all three dimensions are applied together, each at the highest tier previously tested, does the gap reach 20 points? Second: does the shape of the pressure matter — what happens if the same load arrives as a burst, present only for the first 2 seconds of each 5-second run? The design, decision lines, and six predictions were frozen in writing before any run (data/2026-11-23-combo-pulse-prereg.md). The chain and the measurement are unchanged from the earlier rounds: generator → fault proxy (20% loss both ways, 40 ms delay plus 30 ms jitter, flap 0.6/2.5, seed 1234) → a q=0 counting shim → echo server, at 2000 pps for 5 s, 10,000 packets per run.

The short answer: combination is genuinely additive, not a max of the parts. The combined sustained arm produced gaps of 8.70 / 14.33 / 56.58 / 8.96 points — a median of 11.65 points, roughly 2.9× the CPU-only median. One run reached 56.58 points, past the 29.8% cold case and past this round's analytically required gap g* = 45.69 points; in that run the exporter read back a total loss L of 1.0, so the 0.75 alert line was crossed by measurement, for the first time in four rounds. Pulses were much weaker: 3.45 points median combined, 5.79 for CPU-only pulses. Of my six pre-registered predictions, the two that died — P1 (the combination cannot reach 29.8%) and P6 (decomposition immunity, no line crossing) — are the actual findings, scored openly in §3.5.

## 2. Method

- Four arms, four runs each, 16 runs total, in fixed order C0→C1→C2→C3 (the same non-randomized compromise as before, audited through per-run loadavg, PSI, and pressure-source readouts). C0 is the no-pressure baseline. C1, combined sustained: six pure-CPU hogs, a 1000 MB resident touched memory hog, and four synchronous IO writers (4 KB append + fdatasync), present for the whole run — each source at its previously tested maximum tier. C2, combined pulse: the identical three sources, ignited at generator start and all killed at t=+2.0 s, leaving the last 60% of each run unloaded. C3, CPU pulse: six CPU hogs only, same 2.0 s window, to test whether the pulse shape is explained by CPU alone.
- One methodological deviation, declared up front: earlier rounds started pressure sources once per tier; pulse arms force per-run ignition, so every pressure arm here starts its sources per run, with warmup (memory hog fully allocated, touched, and settled 2 s; IO writers 2 s; CPU hogs 2 s) before traffic starts. C1 therefore gets freshly warmed pressure each run, not the shared steady state of the earlier rounds. This is booked as a limitation in §5.
- The safety guard is the 2026-11-11 design, unchanged: a sampler thread reads MemAvailable every 0.25 s, and two consecutive samples below 120 MB kill the memory hog immediately (the run is kept and flagged). The memory hog is hard-capped at 1000 MB. No vm sysctls were touched. The guard never fired in 16 runs.
- Each run records: per-direction counts at all six hops, the exporter's real collect() readback of L and the five quantities behind the reconstructed D, pre-run loadavg, timestamped in-run MemAvailable samples, PSI cpu/memory/io stall deltas, vmstat reclaim deltas, system-wide UDP RcvbufErrors and InErrors deltas, per-run completed sync writes, and the measured pulse-off time.
- This round's host was busier than in either predecessor round, and the numbers must be read against that profile. MemAvailable was roughly 1.0–1.2 GB when the round was scoped and 1,926,964 KB (≈1.88 GB) at bench start; the C0 baseline saw pre-run loadavg up to 9.43 and a median RTT p99 of 281.1 ms (versus ≈137–141 ms on 2026-11-11), with system-wide PSI cpu-some deltas at a median of 7.83 s — other production lines share this 8 GB host. The baseline gap still stayed within 0.77 points (§3.1), but §5 books the drift of the memory baseline across the run window as this round's largest confound.

## 3. Measurements

### 3.1 The ledger: every combined run nonzero, the baseline leaked once

| Arm | Pressure | Gap per run (points) | Median | L range | Mean L_iso | Max D |
|---|---|---|---|---|---|---|
| C0 | none | 0.77 / 0 / 0 / 0 | 0 | 0.5343–0.5567 | 0.5397 | 0 |
| C1 | all three, sustained | 8.70 / 14.33 / 56.58 / 8.96 | 11.65 | 0.5909–1.0000 | 0.6801 | 0.9243 |
| C2 | all three, 2.0 s pulse | 0.92 / 1.98 / 4.92 / 5.60 | 3.45 | 0.5543–0.5930 | 0.5562 | 0.0599 |
| C3 | CPU only, 2.0 s pulse | 6.77 / 4.81 / 0 / 15.20 | 5.79 | 0.5362–0.6242 | 0.5509 | 0.0133 |

The baseline's single nonzero run lost 77 packets, and the system RcvbufErrors delta for that run was exactly 77 — the quiet-baseline signature is intact even on a busy host. C1, by contrast, has no small runs: its minimum, 8.70 points, is already close to the CPU-only historical maximum of 9.69. Combined pressure also moved the injection baseline itself: C1's mean isolated loss L_iso is 0.6801 against C0's 0.5397, and the pooled forward flap share rose from 24.2% to 28.6% — the same "scheduling lag smears the proxy's decisions" fingerprint as the CPU round, at several times the size. Both pulse arms kept L_iso within 1–2 points of baseline (0.5562 / 0.5509); once the pressure leaves, the proxy's rhythm mostly recovers.

### 3.2 C1 run 3: a 56.58-point gap, and a chain that collapsed rather than drifted

The largest run needs its own paragraph, because quoting it as a plain maximum would mislead. In C1-r3 the generator sent 10,000 packets; 4,342 reached the proxy (a first-hop gap of 5,658), the proxy forwarded 2,390, the server received 181, and the generator received zero echoes inside its collection window. The exporter read L = 1.0. The system RcvbufErrors delta that run was 6,217 — larger than the first-hop gap alone, so receive-buffer overflow was happening at more than one hop. The formal D value, 0.9243, must not be read as a decomposition failure: D's denominator F_c = forwarded − echoed uses the generator's received echo count, and with zero echoes F_c inflates to 2,390 and D loses its meaning. What the run establishes is that the return path as a whole did not come back within the window; whether those packets were dropped or merely delayed past the grace period cannot be separated with this round's data (§5). Excluding the run, C1's remaining median is 8.96 points, so the "combined median ≈ 9–12 points" conclusion does not rest on it. But the "the line can be crossed in practice" conclusion rests on exactly this run — and the pre-registration forbids deleting runs, so it stays, flagged.

### 3.3 Attribution: the gap spread downstream, receive buffers still dominate

Per-hop shortfalls, summed over each arm's four runs:

| Arm | Hop 1 | Proxy→shim | Shim→proxy | Proxy→generator | Six-hop total | RcvbufErrors total | Share |
|---|---|---|---|---|---|---|---|
| C0 | 77 | 0 | 0 | 0 | 77 | 77 | 100% |
| C1 | 8,857 | 559 | 819 | 143 | 10,378 | 8,851 | 85% |
| C2 | 1,342 | 197 | 354 | 4 | 1,897 | 1,897 | 100% |
| C3 | 2,678 | 0 | 101 | 0 | 2,779 | 1,493 | 54% |

On 2026-11-11, 191 of 192 hop-readings were exactly zero; the gap lived at the first hop only. Under combined pressure it spreads: C1 lost 819 packets on the shim→proxy hop and 559 on proxy→shim. Starved receivers are no longer only the proxy's front door. The dominant account is unchanged, though — pooled RcvbufErrors cover 54–100% of the six-hop shortfall in every arm. Per run the match is noisy (C1-r4: 896 gap packets against a RcvbufErrors delta of 282; C3-r4: 1,520 against 252), because the counter is system-wide, includes other processes, and misses overflows booked elsewhere. P5 was registered at the pooled level and passes there; I am not upgrading it to a per-run claim.

### 3.4 Pulses: manipulation verified, effect discounted by coverage — and one inversion I will not over-read

Every manipulation check passed. All eight pulse runs show measured kill times of 2.002–2.066 s (registered window 2.0 ± 0.5 s). In every C2 run, the post-pulse MemAvailable median exceeds the during-pulse median (run 1: 3,836,432 KB → 4,924,954 KB), confirming the memory hog's residency actually left. C2's median PSI io-full delta, 19,010 µs, sits well below C1's 53,903 µs; and C1's pressure demonstrably landed — its in-run MemAvailable minimum median of 945,698 KB is about 772 MB below C0's 1,735,832 KB, with PSI io-full at roughly 14.7× the baseline's.

Two findings follow. First, pulses are weaker than sustained pressure by roughly their coverage: the combined pulse median of 3.45 points is about 30% of the sustained median, against a 40% time coverage. Second, an inversion I did not predict: the CPU-only pulse median (C3, 5.79 points) came out above the combined pulse (C2, 3.45). But C3's runs are 6.77 / 4.81 / 0 / 15.20 — a median carried by two runs and a 15-point spread — while C2 climbs steadily. With four runs per arm, the honest statement is "no evidence that the combined pulse beats the CPU pulse," not the reverse. One more crack worth recording: C2's maximum D, 0.0599, crossed the 0.03 noise band that held through all three earlier rounds. It stays below the 0.10 CAND line, but "the decomposition is immune to pressure shape" needs a qualifier from this round on.

### 3.5 Pre-registered predictions, scored

- P1, the combination stays below the line: **wrong (half right)**. The median clause held (11.65 < 20 points); the maximum clause failed — 56.58 points exceeds both 29.8% and g* = 45.69 points. My registered reasoning was that the three dimensions' starvation windows would not align and the combination would behave like a max. The median behaved roughly that way (about 2.9× the largest single-dimension median, not a sum); the tail did not — the tail is chain collapse, not drift.
- P2, quiet baseline: **correct**. All four C0 gaps ≤ 0.02 (max 0.77 points).
- P3, the combination is detectable: **correct**. C1 median 11.65 points ≥ C0 median + 1 point, with every run nonzero.
- P4, the pulse sits between: **correct**. 0 ≤ 3.45 ≤ 11.65 points across C0 / C2 / C1 medians.
- P5, receive-buffer attribution: **correct at the registered pooled level**. RcvbufErrors totals cover 85% / 100% / 54% of the six-hop shortfall in C1 / C2 / C3, all ≥ 50%; per-run variance is as shown in §3.3.
- P6, decomposition immunity and no line crossing: **wrong**. C1-r3 read L = 1.0 through the 0.75 line with a formal D of 0.9243 (an artifact of the zero-echo denominator, §3.2 — but the line was crossed), and C2-r3's D of 0.0599 crossed the 0.03 noise band.

Four of six held. The two failures are the paper: both safety conclusions the single-dimension rounds had earned — "the line cannot be crossed by bench pressure" and "the decomposition is immune" — fail together under combined pressure.

## 4. Analysis and trade-offs

For anyone sizing the headroom of an injection-band alert, this round tightens the conditions under which earlier conclusions may be used. The CPU round showed CPU overcommit alone cannot cross the line; the memory/IO round excluded those two dimensions singly. This round shows the three single-dimension results do not compose: together they lift the median gap to ≈11.65 points, inflate the injection baseline L_iso by 14 points, spread the shortfall to downstream hops, and produce a tail run in which the bench gap alone (56.58 points > g* = 45.69) is sufficient to push L past 0.75 — in that run, the alert verdict is not trustworthy. The working rule I take from this: if the host being measured is simultaneously CPU-overcommitted, memory-tight, and sync-IO-saturated, stamp the measured L as bench-suspect before it enters any alert decision. With only one of the three present, the single-dimension bounds (9.69 / 0.46 / 0 points) remain usable headroom references.

The pulse result prices the shape variable cheaply. Burst pressure is a less efficient gap generator than sustained pressure: a 2 s ignition window (40% coverage) bought about 30% of the sustained median. For periodic burst loads in production — aligned cron jobs, batch sync writes — estimating the gap from sustained-pressure bounds is conservative in the safe direction. Estimating sustained risk from pulse data would understate it; the asymmetry is the part worth remembering.

I am deliberately not explaining the C2/C3 inversion in this round. At least three candidate causes are entangled: C2 spends seconds allocating 1000 MB before ignition, so its at-ignition host state differs from C3's; arm order puts C3 last while the host's background load kept shifting (MemAvailable medians rose to ≈4.9 GB during C2, quietly weakening the memory dimension in the later arms); and four runs per arm is too few to separate any of this. It goes on the next round's list as a hypothesis to test, not a conclusion to publish.

## 5. Limitations and open problems

- Small samples: four runs per arm. C1's median is visibly influenced by the collapsed run; §3.2 gives the exclusion median (8.96 points) alongside, but both figures rest on three to four samples and support magnitudes, not precision.
- Host-profile drift: MemAvailable moved from ≈1.0–1.2 GB at scoping, to 1.88 GB at bench start, to ≈4.9 GB medians during C2. Loadavg and PSI are system-wide and include other production lines. The memory dimension's relative strength therefore decayed across the window, and the pulse arms were measured against a progressively roomier host. Per-run MemAvailable sampling books the drift; it does not remove it. This is the round's largest confound.
- Per-run pressure startup is not perfectly commensurable with the earlier rounds' per-tier steady state (§2); cross-round median comparisons, including the 2.9× figure, carry that caveat.
- C1-r3's zero echoes cannot be split into "dropped" versus "delayed past the grace window" with this data. The next round needs either a longer silent collection tail on the generator or per-packet timestamps at proxy and shim to replay the collapse. That is the first item on its list.
- D is undefined in spirit when the return path dies (§3.2): the decomposition needs a return-path liveness precondition, below which D must not be reported at all. That rule has to be written into the next pre-registration before running, not patched in afterwards.
- All conclusions are scoped to this host profile (8 GB, shared with other lines, baseline loadavg up to ≈9.4 during the window). Nothing here is a general law about combined load.

## 6. References

- This round's pre-registration: data/2026-11-23-combo-pulse-prereg.md (frozen before the runs; six predictions and the safety guard).
- Raw data: data/2026-11-23-combo-pulse-bench.json (all 16 runs, including timestamped MemAvailable samples); post-hoc summary: data/2026-11-23-combo-pulse-posthoc.json; bench script: data/2026-11-23-combo-pulse-bench.py (checkpointed JSONL, `--resume` supported).
- Earlier rounds in this series: articles-en/2026-10-28-injection-band-discrimination.md (the 29.8% cold case and the measurement definitions), articles-en/2026-11-03-load-gap-cpu-tiers.md (CPU-only bound, 9.69 points), articles-en/2026-11-11-memio-gap-tiers.md (memory 0.46 points, IO zero). Their data and pre-registrations sit in data/ under the same date prefixes.
- The chain components (traffic_gen, fault_proxy, echo_server, prom_exporter) are my own lab code; the shim and the memory/IO hog scripts are archived with the earlier rounds' data files.

---

Author: Guangyi Zhao. The experiment design, code, and data in this article are clean-room work of my own and involve no client information. Every number above comes from the measurement files listed in §6 and can be re-checked against the pre-registration and the bench script.
