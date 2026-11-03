# Dropped on the Way Back, Counted All the Same: A Return-Drop Control Test — End-to-End Algebra Is Equivalent, the Decomposition Ledger Flips

Author: Guangyi Zhao

## 1. Problem and background

Two entries in this series carry the same footnote: the shim only ever dropped the forward path; the return path was never measured.

The first is from 2026-10-28. I added an extra-drop shim on the server side of net-assurance-lab and measured the discrimination of the injection-band alert (end-to-end loss above 0.75): the extra drop probability q had to reach about 0.47 before the alert fired. That article stated its limit plainly — the shim dropped client-to-server requests, modelling a server that discards on receive; if a real fault drops the server's replies instead, the end-to-end algebra is the same (survival rates multiply) but the shape of the decomposition ledger differs, and no return-direction run existed.

The second is from 2026-11-01. I split total loss apart and reconstructed a segment drop rate D from five numbers the exporter already publishes (the share dropped between the proxy's forward exit and its return entry). Its detection edge sits near 0.10 and its reading is the segment's drop rate itself. That article also stated, as an open problem, whether D is blind or sensitive to return-direction drops: by counter position it should register them in the whole-segment account, but that was inference, not measurement.

This article flips the shim and changes nothing else: requests pass untouched, and the server's replies are dropped with probability q. Three questions, in preregistered order: is end-to-end loss, and the 0.75 rule's detection edge, equivalent to forward dropping; does D still read the return drop rate; and how exactly does the decomposition ledger change shape. The short answer: the equivalent parts are cleaner than expected — under the isolated accounting the 0.75 rule's firing pattern matches the forward bench tier for tier (0/4 at q=0.40, 4/4 from 0.50 on), and D equals the shim's measured return drop rate exactly, run for run, all 28 runs. The flipped part is just as complete: the segment split D_srv / D_ret swaps values wholesale — in the forward bench all of D sat in the forward sub-segment (D_ret exactly 0 in every run), here all of it sits in the return sub-segment (D_srv exactly 0 in every run). Neither rule can tell direction by itself; the server counters can. In the return bench the server did all the work before the drop: at q=0.60 it echoed an average of 3,908 packets per run that then died on the way back.

One cross-bench difference has to be dealt with in the open, or a reader subtracting the two articles' tables will draw the wrong conclusion: mid-grid end-to-end loss in the return bench runs 1.2 to 3.5 points below the archived forward bench. That is not a direction effect. Section 3.4 gives the evidence — the forward bench carried its own already-documented bench-load confound, while this bench's 28 runs had zero bench gap throughout. Direction-controlled quantities (D, the segment split, isolated firing patterns) align item for item; uncontrolled total-loss means must not be subtracted across days. That is exactly why this series has reported dual accounting since 2026-10-28.

## 2. Method

The preregistration was frozen to disk before any run (data/2026-11-02-return-drop-prereg.md), with the control setup, six quantity definitions and five predictions P1–P5; no line was moved afterwards.

- Chain and parameters: traffic_gen to fault_proxy to return-drop shim to echo_server, all on loopback on one host. Injection parameters are byte-identical to the forward bench — loss 0.20 both ways, delay 40 ms, jitter 30 ms, flap 0.6/2.5, proxy seed 1234; traffic is sustained 2000 pps for 5 s, 10,000 packets. The only difference from 2026-10-28 is the shim's direction.
- Return shim (data/2026-11-02-return-drop-shim.py): the forward direction is passed through untouched; on the return direction, each server echo is dropped with probability q and counted, the rest are forwarded to the proxy. Seed base 42000, disjoint from the forward bench's 20000 and the decomposition holdout's 31000. The q grid matches the forward bench: 0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, four repetitions each, 28 runs, ports rotating per run.
- Judgement goes through the real exporter: each run's artifacts are pushed through prom_exporter's collect(), and both rules and every reading are parsed from its exposition text (sent, echoed, the proxy's in_client/in_server/forwarded, the server's received_total/echoed) — the exact object Prometheus would scrape. Raw logs are used only for identity checks and attribution.
- Quantities (frozen in the preregistration): L is deployment-accounting total loss, L_iso uses the proxy's in_client as denominator; OLD is L or L_iso above 0.75; F_c equals forwarded minus echoed (the 2026-11-01 reconstruction); D equals 1 minus in_server over F_c, with CAND keeping its frozen line D above 0.10. New in this bench, the segment split: D_srv equals 1 minus server_received over F_c (forward sub-segment), D_ret equals 1 minus in_server over server_echoed (return sub-segment); algebraically (1-D) equals (1-D_srv) times (1-D_ret), so the three are not independent. The forward baseline comes from the archived 28 runs of 2026-10-28, recomputed with the same formulas before this bench ran: its D_srv equals D in every run and D_ret is exactly 0.0000 in all 28.

## 3. Measurements

### 3.1 Identities and bench state: an unusually clean batch of 28

Six reconstruction identities (F_c equals the proxy's forward-direction forwarded count; echoed equals its return-direction forwarded count; the proxy's in_server equals the shim's forwarded_server; the server's received count equals the shim's forwarded_client; the shim's return input equals the server's echoed count; the raw server counters match the exporter's published values) hold in every run, 28/28; the exporter's loss ratio equals the generator's summary in every run, 28/28. All four hop gaps (proxy-to-shim, shim-to-server, server-to-shim, shim-to-proxy) are zero in every run, and the generator-to-proxy bench gap is also zero in every run — in_client is a full 10,000 each time. Contrast with the forward bench, whose gap peaked at 29.8% and which contained one 145-packet inter-hop gap inside the segment. This batch's cleanliness is the precondition for the "exactly equal" statements below, and for the attribution in 3.4; it does not guarantee the next batch, and the limitations section returns to that.

### 3.2 End to end and the two rules: firing patterns align tier for tier

Per-tier means (return L and L_iso coincide tier for tier because the bench gap is zero throughout; the forward column uses its isolated accounting):

| q | Return L_iso mean | Forward L_iso mean | Return D mean | Forward D mean | OLD isolated (return/forward) | CAND (return/forward) |
|---|---|---|---|---|---|---|
| 0 | 0.5265 | 0.5280 | 0.0000 | 0.0000 | 0/4 / 0/4 | 0/4 / 0/4 |
| 0.10 | 0.5749 | 0.6043 | 0.1027 | 0.1031 | 0/4 / 0/4 | 4/4 / 1/4 |
| 0.20 | 0.6200 | 0.6549 | 0.1989 | 0.2005 | 0/4 / 0/4 | 4/4 / 4/4 |
| 0.30 | 0.6688 | 0.6939 | 0.3027 | 0.3005 | 0/4 / 0/4 | 4/4 / 4/4 |
| 0.40 | 0.7143 | 0.7299 | 0.4030 | 0.4016 | 0/4 / 0/4 | 4/4 / 4/4 |
| 0.50 | 0.7624 | 0.7747 | 0.5020 | 0.5035 | 4/4 / 4/4 | 4/4 / 4/4 |
| 0.60 | 0.8081 | 0.8123 | 0.5978 | 0.5950 | 4/4 / 4/4 | 4/4 / 4/4 |

OLD's isolated conclusion reproduces in full: silent through q=0.40, fully firing from 0.50, detection edge near 0.47 unmoved by drop direction (P2 confirmed). Deployment accounting here equals isolated accounting; the forward bench's deployment column had early firings at q=0.20, 0.30, 0.40 (1/4, 1/4, 3/4) which the 2026-10-28 article attributed run by run to bench-gap lift, and which simply do not occur in a zero-gap batch — a bench-state difference, not a direction finding.

One tier of CAND needs its own paragraph: q=0.10 is the preregistration's declared borderline tier, with no directional prediction. The return bench's four D readings are 0.1014 to 0.1049, all just above the line, firing 4/4; the forward bench's are 0.0928 to 0.1227, three below and one above (that one being the 145-packet hop-gap run), firing 1/4. But the two D means differ by only 0.0004 (0.1027 vs 0.1031); with about 6,100 shim inputs, a single reading's sampling standard deviation at q=0.10 is about 0.0038, the return mean sits 0.0027 from nominal (about 0.7 of that deviation), and the largest single-run deviation is 0.0049, within 1.3 deviations. At a threshold, fire counts are a coin flip; the readings are the evidence, and the readings agree.

### 3.3 D reads the return path: exact, and the split flips wholesale

Against the shim's own measured return drop rate (dropped_extra over its return input — ground truth, never a rule input): the difference from D across 28 runs has median 0.0 and maximum about 1e-16, i.e. D is exactly equal in every run (P3 confirmed, stronger than predicted; CAND fires 4/4 at every tier from 0.20 up and 0/4 at q=0). Against nominal q, the D means deviate by -0.0022 to +0.0030 per tier, the same magnitude as the forward bench — that is the shim's own Bernoulli sampling spread, not reading error.

The segment split flips without any ambiguity (P4 confirmed):

- Return bench: the D_srv mean is 0.0000 at every tier (zero in every run), and D_ret equals D in every run, its means tracking q from 0.1027 to 0.5978 with a whole-grid median error against nominal q of 0.0035.
- Forward bench (archived recomputation): D_ret is exactly 0.0000 in every run, and D_srv equals D.
- The split identity (1-D) equals (1-D_srv) times (1-D_ret) has maximum deviation 0 across the return bench's 28 runs — with one sub-segment exactly zero and no hop gaps anywhere, the identity holds as a counting equality, not an approximation.

So the inference left open on 2026-11-01 — return drops raise D and land in the whole-segment account — is confirmed by measurement, and the measurement goes one step further: given server counters, the split locates the drop within the segment. The exporter already publishes the server counters (nal_server_packets_total), so the split, like D itself, needs no exporter change.

### 3.4 Why the return bench's total loss runs lower: not direction — the forward bench's load

Subtracting the two benches' L_iso means leaves +2.9 (q=0.10), +3.5 (0.20), +2.5 (0.30), +1.6 (0.40), +1.2 (0.50), +0.4 (0.60) points, forward higher. Read naively, that looks like a direction effect. Three lines of evidence say it is not:

First, the anchors agree. The two q=0 baselines are nearly identical: L_iso means 0.5265 vs 0.5280, forward flap shares 23.99% vs 23.97%, return flap shares 3.06% vs 3.30%, random-loss shares of the same magnitude. On a quiet bench, both benches measure the same injection band.

Second, algebraic self-consistency. Under isolated accounting, end-to-end survival should equal baseline survival times segment survival, so predicted L_iso equals 1 minus (1 minus the q=0 baseline) times (1 minus the D mean). The return bench, fed its own baseline, lands within -0.0002 to -0.0030 of prediction at every tier — 0.3 points at worst. The forward bench, fed its own baseline into the same formula, sits systematically high mid-grid, by +2.8, +3.2 and +2.4 points at q=0.10 to 0.30, converging at the ends. That deviation is not new: section 3.3 of the 2026-10-28 article recorded isolated live means running 1 to 3 points above its model mid-grid and attributed the lift to bench load raising the injection baseline; its pooled forward flap share in the loaded runs reached 26.96%.

Third, the share ledger matches. Recomputed after the fact: pooled over all 28 runs, the forward bench's forward flap share is 26.96% and its return flap share 4.57%, while its own q=0 runs alone give 23.97% and 3.30% — the excess concentrates in its bench-gap, load-heavy runs. The return bench pools to 23.99% and 2.99%, essentially its own q=0 anchor (23.99% and 3.06%): the whole batch ran quiet.

Conclusion: drop direction has no measurable effect on the end-to-end algebra (on a clean bench the product formula is accurate to 0.3 points), and the cross-bench mean difference is the forward bench's load confound. Its magnitude, about 3 points mid-grid, doubles as a practical warning: subtract live means from different days without checking both batches' bench state, and you will read load as mechanism.

### 3.5 Server work done for nothing: about four thousand extra echoes per run

The most operationally meaningful part of the flip is the server counters themselves (P5 confirmed). In the return bench, the server's received and echoed counts equal F_c exactly in every run (28/28): the forward sub-segment loses nothing, the server generates an echo for every request that survived injection, and then a share q of those echoes dies at the return shim. In the forward bench the server only ever saw what the shim passed: at q=0.60 its mean echoed count is 2,207, against 6,115 in the return bench — a difference of 3,908 packets, about 64% of that tier's mean F_c. Same end-to-end loss reading, same D; in the forward fault the server did about four tenths of the work, in the return fault it did all of it and then had six tenths thrown away. The echo server's cost is negligible, so in this bench 3,908 is a packet count, not money; carried to a real service, compute already spent on request handling and response generation, plus return-path bandwidth already used, are waste unique to return-side drops. That carry-over is reasoning, not this bench's measurement, and I record only its direction, not a magnitude.

### 3.6 Preregistration scorecard

P1 (q=0 anchor: L mean within 0.02 of the forward 0.5315, all D at most 0.03) confirmed — measured mean 0.5265, all four D exactly 0. P2 (OLD isolated: 0/4 at 0.40, 4/4 at 0.50 and 0.60) confirmed, tier for tier identical to forward. P3 (median |D minus shim truth| at most 0.02; CAND 4/4 from q=0.20 up, 0/4 at 0) confirmed and stronger — median error 0.0, exact in every run. P4 (D_srv tier means at most 0.03; median |D_ret minus q| at most 0.02; mirror of forward) confirmed — D_srv zero in every run, median error 0.0035. P5 (server echoed approximately F_c; at q=0.60 the two directions' echoed means differ by at least 40% of mean F_c) confirmed — the difference is about 64%. All five predictions hold. The one quantity the preregistration declined to predict, the q=0.10 borderline tier, landed at return 4/4 vs forward 1/4 with D means 0.0004 apart; section 3.2 accounts for it separately.

## 4. Analysis and trade-offs

Lined up across three articles, the decomposition-aware reading is now a closed loop. Total loss (OLD) answers "is anything dropping beyond the injection" — edge near 0.47, direction-blind, bench-sensitive. The segment rate D answers "how much is the segment between the proxy's two counting points dropping" — edge near 0.10, immune to bench gap (the 2026-11-01 layer-A evidence), blind to direction inside the segment. The split D_srv / D_ret answers "forward sub-segment or return sub-segment" — shown here to work whenever server counters exist, from the same inputs, again with no exporter change. Three layers, three different questions; together they localise: it fired, by how much, and in which direction.

Whether direction is worth splitting out depends on the response path it feeds. Forward drops point at the receive side (server ingress, inbound path, receive queues); return drops point at the reply side. On end-to-end monitoring the two are indistinguishable — in this bench L and D agree to reading precision, tier for tier — so without the split, localisation means logging into the server and reading counters by hand, while every input the split needs (the proxy's in_server, forwarded, echoed and the server's received, echoed) is already published by the exporter. My judgement (engineering judgement, evidence grade B): anywhere D is already deployed, computing D_srv and D_ret alongside costs next to nothing, and not computing them is the waste. What this bench does not settle is their alert thresholds: the two benches give sub-segment noise baselines that are nearly extreme samples — one exactly zero throughout, the other carrying a single 0.024 gap event — and that is too little to set a line on.

There is also a methodological yield here that matters more than the headline result. This control could separate "direction" from "load" only because both benches carried their own q=0 anchors and per-run decomposition ledgers. The forward bench's load confound had been caught by its decomposition ledger at publication time and written into its limitations, so today's cross-bench comparison had a ledger to audit, quantitatively (flap shares 26.96% vs 23.99%). Had it published means alone, this article's first conclusion would have been misread as a direction effect. A decomposition ledger is not decoration on a conclusion; it is the control group you leave for the next article.

## 5. Limitations and open problems

- "Exactly equal" is a property of this batch of bench runs, not of the method. All four hop gaps were zero in every run because this host happened to be quiet; a single 145-packet inter-hop gap in the forward bench already pushed D's deviation from shim truth to 0.0239. The same holds for the split: a gap on any hop between sub-segments is booked into the neighbouring sub-segment's account, and split accuracy degrades with gap size. What this bench proves is that the identities and the reading hold, not that they are exact in any environment.
- Cross-bench comparison is still weaker than an interleaved one: the two benches ran five days apart under different bench states, and the direction-equivalence conclusion stands on three legs (anchors, algebraic self-consistency, share attribution) rather than on a same-session A/B that alternates shim direction run by run. That interleaved control would remove the load confound by design; it is the cleanest debt this experiment group still owes.
- Simultaneous two-direction drops were not measured. If both sub-segments drop at non-zero rates, the split identity still yields two separable readings algebraically (the counting points are in series), but the interaction of two Bernoulli stages and of gap contamination is unmeasured — and the mirror shape in this bench, where one side is always exactly zero, is precisely the easiest case.
- Server cost is measured in packets only. The echo server's reply costs almost nothing, so the 3,908 wasted echoes state no real cost in this bench; real services have entirely different request-handling and response-generation cost structures, and the size of return-drop waste has to be measured per service, not carried over from these numbers.
- Four repetitions per tier still give a 25-point resolution on fire rates; the borderline tier's inconsistent counts (4/4 vs 1/4 at q=0.10) are expected behaviour at that resolution, and this article's use of reading means and positions instead of counts deserves a recheck against a denser grid (q from 0.05 to 0.20 in fine steps).
- No alert thresholds are proposed for D_srv and D_ret (see section 4): their noise baselines are too thin. Deploy them in record-only mode first and set lines from observed distributions.

## 6. References

1. Guangyi Zhao, "Only After Another 47% Does It Complain: Measuring the Discrimination of the 0.75 Injection Band" (2026-10-28) — the forward bench's 28 archived runs (this bench's forward baseline, data/2026-10-28-injection-band-bench.json), the detection edge near q=0.47, the load attribution for mid-grid means above model, and the original "return drops unmeasured" limitation.
2. Guangyi Zhao, "Split the Total Loss and the Blind Zone Shrinks from 47% to 10%: A Decomposition-Aware Alert Test" (2026-11-01) — D's definition and frozen 0.10 line, the F_c reconstruction identities, the bench-gap immunity evidence, and the original open problem on D and return-direction drops.
3. Context under test: net-assurance-lab, monitoring/rules/alerts.yml, NalFaultLossAboveInjectionBand (nal_loss_ratio above 0.75); exporter counter definitions in src/prom_exporter.py collect() of the same repository (proxy counters are two-direction totals; server counters are nal_server_packets_total); injection implementation in src/fault_proxy.py and the fault_sustained parameters in src/run_experiment.py.
4. Prometheus documentation, Configuration / Alerting rules: pending and firing semantics of for. https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
5. This bench's data (archived in this project's data/ and synced with the Chinese version to the tech-deep-dives repository's data/): 2026-11-02-return-drop-prereg.md (preregistration with the frozen quantities and P1–P5), 2026-11-02-return-drop-shim.py (return-drop shim), 2026-11-02-return-drop-bench.py, 2026-11-02-return-drop-bench.json and the same-prefix progress.jsonl (28 live runs in full: exporter-parsed values, per-run identities and hop gaps, the archived forward recomputation), 2026-11-02-return-drop-posthoc.json (post-hoc algebraic self-consistency and flap-share recomputation), 2026-11-02-return-drop-check.py (final numeric check script, 9 of 9 passed).

---

Author: Guangyi Zhao. The experiment design, code and data in this article are clean-room work of my own: the test bench, the exporter, the return-drop shim and the control scripts were all written by me; experiments ran only on loopback and local files on one host, and involve no customer information and no third-party systems.
