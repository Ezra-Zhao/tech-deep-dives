# Split the Total Loss and the Blind Zone Shrinks from 47% to 10%: A Decomposition-Aware Alert, Measured

Author: Guangyi Zhao

## 1. Problem and background

In the 2026-10-28 instalment of this series I measured the discrimination power of net-assurance-lab's injection-band alert, NalFaultLossAboveInjectionBand. With the injection parameters untouched and an extra server-side drop stage of probability q added behind them, the incumbent rule — end-to-end loss above 0.75 — only starts firing at q ≈ 0.47. Almost half of the packets that survived the injection have to die on the server side, roughly 22 extra points of end-to-end loss, before it says anything; server-side faults at q ≤ 0.40 are indistinguishable from health. The same data exposed an attribution problem: a single total-loss number mixes three drop stages, and the runs where the rule fired early under deployment semantics were firing on bench loss between the traffic generator and the proxy, not on the server.

Section 4 of that paper proposed a direction: the exporter already publishes the proxy's per-stage counters, so compute the end-to-end loss the proxy counters imply, subtract it from the measured loss, and alert on the difference. Section 5 flagged it honestly as unimplemented — its bench immunity was an inference, not a measurement. This paper pays that debt: the candidate rule is implemented and run head-to-head against the 0.75 rule on the same q grid, scoring three things — detection threshold, bench-gap immunity, and attribution accuracy.

One constraint only shows up at implementation time, and it shapes everything below. The exporter (src/prom_exporter.py) publishes proxy counters aggregated over both directions: in_client and in_server are separate, but dropped_loss, dropped_flap and forwarded are sums across directions. There is no ready-made "packets forwarded toward the server" series. The per-stage counts exist, but not split by direction — so the expected loss cannot be read off; it has to be reconstructed from identities, and whether that reconstruction is sound is the first thing to verify.

The headline results: the reconstruction checks out run by run in 40 live runs (Section 3.1). The candidate's detection threshold sits at its own pre-registered line of 0.10 — at q = 0.10 it fires in 1 of 4 runs (straddling the line), and from q = 0.15 upward it fires everywhere, while on the holdout tiers where the two rules make opposite predictions (q = 0.15 and 0.30, end-to-end loss only 0.60 and 0.67) the incumbent stays silent in all 8 runs. And the candidate does not merely fire: its readout D equals the shim's own measured drop rate exactly in 39 of 40 runs, and the single exception is explained to the third decimal by a known 145-packet hop gap in that run (computed contribution 0.0240, observed difference 0.0239).

## 2. Method

Definitions, threshold and predictions were frozen in a pre-registration file (data/2026-11-01-decomp-alert-prereg.md) before any scoring ran.

The rule may use only five exporter quantities: sent, echoed, in_client, in_server, forwarded. Directional quantities are reconstructed:

- Return-leg forwards F_s = echoed, on the strength of the proxy's return-forward count matching the generator's received count run by run in prior data; every layer below re-verifies this identity and any violating run would be reported separately.
- Forward-leg forwards F_c = forwarded − echoed (the published counter is the two-direction sum; subtracting the return leg leaves the forward leg).
- Return-leg survival b = echoed / in_server.
- Expected echoes E_exp = F_c × b: the echoes the generator should receive if every forward-forwarded packet reached the server and was echoed, with only the return leg dropping at its measured rate. Expected loss L_exp = 1 − E_exp/sent; measured loss L = 1 − echoed/sent.
- Segment drop rate D = 1 − in_server/F_c. The segment it measures runs from the proxy's forward-forward counting point, through the shim's forward pass, the server, and the shim's return pass, to the proxy's return-input counting point — everything except the two proxy legs. Algebraically D and the expected-loss difference are the same signal at different scales (L − L_exp = D × E_exp/sent); the decision uses D, because its ground truth is the segment's drop rate itself and can be scored directly.

The frozen line is D > 0.10. The reasoning, recorded before scoring: it must clear the segment's hop-gap noise (in the entire 2026-10-28 grid there was exactly one 145-packet proxy-to-shim gap, about 2.7% of that run's F_c) by a wide margin, and it must sit far below the incumbent's ≈ 0.47 threshold. A D > 0.05 sensitivity line is reported alongside but never used as the primary verdict. The incumbent OLD rule is unchanged: L > 0.75.

Three evidence layers, labelled by nature and never blended:

- Layer A, archive re-scoring (old data, new rule): the 28 live runs of 2026-10-28, q grid 0 to 0.60 in seven tiers of four runs. Both rules are recomputed from the five permitted quantities only; shim accounts and per-direction proxy logs serve exclusively to verify the reconstruction identities and to score D.
- Layer B, fresh live holdout: the same real components and the same shim, injection parameters byte-identical (loss 0.20 each way, delay 40 ms + jitter 30 ms, flap 0.6/2.5, proxy seed 1234, traffic 2000 pps × 5 s), new extra-drop seeds (base 31000), q in {0, 0.15, 0.30} × 4 runs = 12 runs. The two non-zero tiers sit inside OLD's blind zone and above CAND's line — the tiers where the rules predict opposite outcomes. All five rule inputs are parsed out of the exporter's actual collect() exposition text, the very object Prometheus would scrape, not from raw logs.
- Layer C, synthetic perturbation (arithmetic, not measurement): take the eight q = 0 and q = 0.20 runs of layer A and inject bench gaps g in {0.1, 0.2, 0.3} by scaling in_client and every downstream count down proportionally (sent fixed) — packets swallowed between generator and proxy, survivors continuing with the injection's own survival profile — then rescore both rules.

The five pre-registered predictions (P1–P5) are settled in one place at the end of Section 3.5, misses included.

## 3. Measurements

### 3.1 The reconstruction identities: 40 for 40

Across layer A's 28 runs, reconstructed F_c equals the proxy log's per-direction forward count in 28 of 28 runs; F_s = echoed equals the return-forward count in 28 of 28; in_server equals the server's echoed count in 28 of 28. Layer B's 12 runs repeat all three at 12 of 12, and the exporter-parsed loss ratio equals the generator summary in every run. The load-bearing condition deserves naming: in all 40 runs, not one packet was lost on the final return hop between proxy and generator. Sections 3.4 and 5 return to this — it is the foundation of the reconstruction, and the first thing to re-verify off a loopback bench.

The only in-segment noise event in either layer is still layer A's: in the q = 0.10 run 2, 145 packets vanished between the proxy's forward count and the shim's input count. Every other run's proxy-to-shim gap is zero. Section 3.3 settles that run's account separately.

### 3.2 Layer A: the threshold moves from 0.47 to 0.10

The 28 re-scored runs (OLD deployment = total loss > 0.75; OLD isolated = loss relative to in_client > 0.75):

| q | D, four runs | CAND fires | OLD (deployment) | OLD (isolated) |
|---|---|---|---|---|
| 0 | 0.0000 ×4 | 0/4 | 0/4 | 0/4 |
| 0.10 | 0.0928 / 0.1227 / 0.0996 / 0.0975 | 1/4 | 0/4 | 0/4 |
| 0.20 | 0.1996 / 0.2057 / 0.1947 / 0.2020 | 4/4 | 1/4 | 0/4 |
| 0.30 | 0.3041 / 0.2964 / 0.2948 / 0.3066 | 4/4 | 1/4 | 0/4 |
| 0.40 | 0.4108 / 0.3976 / 0.4050 / 0.3931 | 4/4 | 3/4 | 0/4 |
| 0.50 | 0.5080 / 0.4958 / 0.5070 / 0.5031 | 4/4 | 4/4 | 4/4 |
| 0.60 | 0.5974 / 0.5973 / 0.5886 / 0.5968 | 4/4 | 4/4 | 4/4 |

The incumbent's old verdict reproduces under re-scoring: isolated-semantics silence through q = 0.40, full firing at 0.50, threshold ≈ 0.47 (analytic 0.4707, model interpolation 0.4705 in the 2026-10-28 paper). The candidate's transition band sits exactly on its own line: at q = 0.10 three runs read just below (0.0928–0.0996) and one above (0.1227, the segment-gap run of Section 3.1); from q = 0.20 up, everything crosses. Effective detection threshold ≈ 0.10–0.15, a third to a quarter of the incumbent's. In end-to-end terms (layer B numbers): at q = 0.15 the total loss is only about 6.9 points above the no-injection baseline and CAND already fires solidly; OLD needs about 22 points stacked on the baseline.

Sensitivity line, reported as promised: at D > 0.05, layer A's q = 0.10 tier becomes 4/4 and nothing else changes, q = 0 included. The 0.05 line is not unusable — it merely keeps only a twofold margin over the largest observed segment-noise event (2.4 points), where 0.10 keeps roughly fourfold.

### 3.3 Attribution: D reads out how much the segment dropped

Scoring D against the shim's own measured drop rate (dropped_extra / in_client — ground truth, never a rule input): exact agreement in 27 of 28 layer A runs and in all 12 layer B runs, 39 of 40 overall. The one exception is the Section 3.1 run: D = 0.1227 against the shim's 0.0988, a difference of 0.0239. That run's segment composition is fully known — 145 packets lost on the proxy-to-shim hop — and folding them through the run's counts puts their contribution to D at ≈ 0.0240, matching the observed 0.0239 to the third decimal. D did not misread: it reads the whole segment (shim plus that hop), the shim's ledger only covers its own stage, and the difference is exactly the hop's account. That is also the capability boundary: D localises to a segment; splitting inside the segment needs in-segment counters the exporter does not publish.

Against nominal q, layer A's absolute error has median 0.0038 and maximum 0.0227 (the gap run); layer B's eight non-zero runs err between −0.0095 and +0.0077. Since D equals the shim's realised rate exactly, D's run-to-run spread is the shim's Bernoulli sampling spread itself: at F_c ≈ 5500–6100 and q = 0.15 the sampling standard deviation is ≈ 0.0048, and layer B's four readings (0.1452, 0.1497, 0.1470, 0.1577) scatter at that scale.

The bench-immunity evidence lives in the two layer A runs where the old rule fired on the bench. q = 0.20 run 2: bench gap 29.8%, total loss 0.7655 crosses the line while the isolated loss is only 0.6658 — it fired on the bench; the same run's D = 0.2057, error 0.0057. q = 0.30 run 4: bench gap 21.8%, total loss 0.7693 crosses; D = 0.3066, error 0.0066. In both runs the bench inflated total loss by roughly 7–10 points while D's error stayed under 0.007. Over all 28 runs, the Pearson correlation of bench-gap rate with total loss's bench component is 0.9635; with D's error it is −0.0914 — the hand that shakes the total barely touches D. Mechanistically this is expected: bench-dropped packets never enter the proxy, so F_c and in_server shrink in proportion and their ratio holds; total loss keeps sent as its denominator and absorbs the blow in full.

### 3.4 Layer B: the holdout tiers where the rules disagree

Twelve fresh runs, new seeds, both verdicts computed from the five quantities parsed out of the exporter's exposition text:

| q | D, four runs | L range | CAND | OLD |
|---|---|---|---|---|
| 0 | 0.0000 ×4 | 0.5320–0.5421 | 0/4 | 0/4 |
| 0.15 | 0.1452 / 0.1497 / 0.1470 / 0.1577 | 0.6003–0.6147 | 4/4 | 0/4 |
| 0.30 | 0.2930 / 0.2969 / 0.2905 / 0.2937 | 0.6695–0.6760 | 4/4 | 0/4 |

At q = 0.30 the end-to-end loss tops out at 0.6760, still 7.4 points under the 0.75 line — the incumbent's silence matches its threshold arithmetic (isolated critical q ≈ 0.47) — while CAND reads 0.2905–0.2969, on the truth and far over its line. One environmental fact must be stated plainly: the host was quiet for these 12 runs, the bench gap is 0.0000 in every run (in_client a complete 10000 each time) and the in-segment gap is zero too. Layer B therefore validates detection and readout precision, not immunity; the immunity evidence is layer A (real gaps up to 29.8%) plus layer C, and layer B's cleanliness must not be passed off as more than it is.

### 3.5 Layer C and the pre-registration scorecard

Across layer C's 24 perturbations (8 runs × 3 gap levels), D's maximum movement is 0.0 at count precision — a ratio's invariance confirmed arithmetically, useful as an implementation check, worth no more than that. OLD's side: at g = 0.3 the four q = 0.20 runs move from L 0.6838–0.7655 to 0.7787–0.8358 and firing goes from 1/4 to 4/4; the four q = 0 runs at g = 0.3 reach at most L = 0.6767 and do not cross.

Scorecard for the five frozen predictions. P1 (layer A q = 0 readings at most 0.03): hit — all four are 0.0000. P2 (CAND 4/4 at every q ≥ 0.20, q = 0.10 a straddle tier, OLD's isolated verdict reproduced): hit. P3 (median error at most 0.02; the two bench-driven runs' D within ±0.03 of truth): hit — median 0.0038, errors 0.0057 and 0.0066. P4 (layer B: CAND 4/4 and OLD 0/4 at both 0.15 and 0.30): hit. P5 first half (layer C moves D by at most 0.005): hit, observed 0.0. P5 second half (a g = 0.3 bench gap pushes q = 0 runs over OLD's line): missed. I underestimated the gap a pure bench loss needs when freezing that prediction — starting from the q = 0 baseline, crossing 0.75 takes about 47.1%, a number my own 2026-10-28 paper had already computed in its Section 3.5 and which I failed to re-check before freezing; the g grid topped out at 0.3. The miss is in my prediction, not the data, and it reconfirms the incumbent's pure-bench margin. Process lesson, recorded separately from the results: before freezing predictions, re-read the numbers your previous paper already derived.

## 4. Analysis and trade-offs

The two rules answer different questions. The incumbent asks whether total loss exceeds what the injection can explain; with a single total as its only input, its threshold is set jointly by the injection bandwidth (a ≈ 52.8% baseline against a 75% line) and by bench noise, and when it fires it cannot say where the packets died. The candidate asks whether the segment between the two proxy counting points is dropping abnormally. Its decision quantity is a ratio measured on the current run, so injection fluctuation, injection bandwidth and generator-to-proxy bench loss never enter it by construction — which is how the threshold gets down to 0.10, and why firing comes with a magnitude (the readout is the estimate, typically within a point) and a location (one segment). What this generation buys with its price: its world is exactly one segment. Loss on the proxy legs themselves (the injection growing heavier) or on the generator-to-proxy stretch is invisible to it. It has to be deployed alongside the band alert, not instead of it — CAND owns out-of-segment loss, OLD owns the total. That division was fixed in the pre-registration, not invented after the results.

The 0.10 line, once more with its evidence on the table: below it there are exactly two noise observations — one segment-gap event at 2.4 points, and sampling scatter around half a point. 0.10 is about four times the largest observed event, 0.05 about two times. On this loopback bench 0.05 never misbehaved either, but on a real path the in-segment gap distribution has no prior bound, and a line at twice the largest seen noise bets the false-positive rate on never meeting a gap twice as large as the worst seen so far. I take 0.10, giving up detection of segment drops between 5% and 10% (roughly 2–5 end-to-end points) in exchange for the fourfold margin; the day in-segment counters land and gaps can be separated from genuine drops, the line can come down.

In PromQL the candidate needs no exporter change — the five quantities already exist: D is 1 − (in_server / (forwarded − echoed)), under the same for: conventions as the incumbent. The standing caveat from 2026-10-24 still applies: this exporter publishes snapshots of finished runs, so for: measures how long bad data has been scraped, not how long a network state persisted; porting these discrimination results to a streaming exporter means re-deriving the detection delay separately.

A closing note on the original "subtract the expectations" formulation: the pre-registration defined both L − L_exp and D. They are one signal, but only D has a directly scoreable ground truth and a threshold that does not drift with the injection baseline; L − L_exp survives as the human-readable end-to-end translation (in the q = 0.20 run 2: L = 0.7655, L_exp = 0.7048, difference 0.0607 end-to-end points). All verdicts in this paper use D; L_exp appears only in this paragraph, so no conclusion is drawn twice from the same signal.

## 5. Limitations and open questions

- All live evidence comes from one loopback bench on one host. Layer B's 12 runs had zero bench gap; immunity rests on layer A's re-scoring (real gaps up to 29.8%) plus layer C arithmetic. On a busier host or a real network, the in-segment gap distribution must be re-measured and the 0.10 line re-set against it.
- D stands on the identity F_s = echoed — no loss between the proxy's return-forward counting and the generator's counting. It held in all 40 runs, but on a loopback bench that hop can hardly lose packets; if a real path drops there, the loss folds into F_c's reconstruction error (F_c underestimated, D overestimated) — biased toward false positives. No run in this paper injects loss on that hop; that is the first debt outstanding.
- D localises to a segment, no finer: shim drops, server drops and in-segment hop gaps are indistinguishable inside it (the 0.0239 of Section 3.3 is precisely a hop gap impersonating segment drop — small and explainable that once, but structurally indistinguishable). Finer attribution needs in-segment counters or per-direction proxy counters from the exporter; this paper's whole point was to find how far one gets without touching the exporter.
- Whether D is blind or sensitive to return-direction segment drops was not measured: the shim drops forward traffic only. By counting-point positions, return traffic crosses the shim's return pass before the in_server counting point, so return drops should inflate D and be booked to the whole segment — an inference, not a measurement. The queued return-drop comparison study (already in the topic pool for the 0.75 rule) and this open question should be settled together.
- Four runs per tier still means firing rates resolve to 25 points; the shape of the transition near q = 0.10 is inferred from where the D readings themselves fall (clustered around the line), not from a denser grid. The saving grace is that D's readout carries per-run ground-truth scoring, which is harder evidence than firing counts — but a denser q sweep across 0.05–0.20 remains worth running.
- The P5 second-half miss is on the record in Section 3.5: a frozen prediction inconsistent with a number my own previous paper had already derived, frozen without the re-check. Process lesson only; it does not touch layers A or B.

## 6. References

1. Rules and counters: net-assurance-lab repository, monitoring/rules/alerts.yml, NalFaultLossAboveInjectionBand (nal_loss_ratio > 0.75, for: 1m; annotation gives the 50–65% injection band); counter definitions in src/prom_exporter.py, collect() (nal_fault_proxy_packets_total kinds in_client, in_server, dropped_loss, dropped_flap, forwarded, delayed — direction-aggregated, per the source).
2. Predecessor: Guangyi Zhao, "Only After Another 47% Dies Does It Speak: The Injection Band's 0.75 Ceiling, Measured" (2026-10-28) — the incumbent's critical q ≈ 0.47, the bench-confound decomposition, the 47.1% pure-bench crossing figure, and the decomposition-aware direction proposed in its Section 4 and marked unverified in its Section 5 all originate there; layer A's data source is that paper's 28-run archive (data/2026-10-28-injection-band-bench.json).
3. Injection implementation: same repository, src/fault_proxy.py (flap-first decide(), one RNG stream shared by both directions) and src/run_experiment.py fault_sustained parameters (loss 0.20, delay 40 ms, jitter 30 ms, flap 0.6/2.5, 2000 pps × 5 s).
4. Prometheus documentation, Configuration / Alerting rules: pending and firing semantics of for:. https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
5. This round's data (archived under data/ in this project and mirrored with the Chinese version in the tech-deep-dives repository): 2026-11-01-decomp-alert-prereg.md (pre-registration with the frozen line and five predictions), 2026-11-01-decomp-alert-bench.py and 2026-11-01-decomp-alert-bench.json (layer A re-scoring and layer C perturbations, full per-run accounts), 2026-11-01-decomp-alert-live.py, 2026-11-01-decomp-alert-live.json and its progress JSONL (layer B's 12 fresh live runs, exporter-parsed values and per-run checkpoints); the shim is reused from 2026-10-28-injection-band-shim.py.

---

Author: Guangyi Zhao. The experimental design, code and data in this article are clean-room work of my own: the bench under test, the exporter, the extra-drop shim and the re-scoring and live harnesses were all written by me, and the experiments ran only on local loopback and local files, involving no client information and no third-party systems.
