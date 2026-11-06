# Three Votes, Take the Middle: A Median-of-Three Estimators Test — Zero Bad Estimates in 45 Pooled Points, Beaten Only When All Three Votes Err Together

Author: Guangyi Zhao
Date: 2026-11-05
Subject: Bloom-Counter camera calibration — median voting across the BLIND7 / BLIND3 / BLINDRAW scale estimators, three datasets (one replication, two holdouts), pre-registered

## 1. Problem and background

Bloom-Counter's camera calibration has two estimators that fail at opposite ends. BLIND7 (morphology with the detector's own kernel 7, then blind 2-means clustering of contour areas to back out the scale factor s) fails at small s: once the kernel kills the bud contours, the clustering splits the bloom cluster instead, and the estimate runs +12% to +162% high. BLINDRAW (no morphology at all; clustering over raw petal-mask connected components) fails at the other end: at s=1.0 the petals fragment into hundreds of components, the upper-cluster median collapses to 751, and the estimate lands at −55.1% with an end-to-end F1 of 0.638. BLIND3 (kernel 3) sits between them — the most stable of the three, but with a systematic −3.5% to −9.1% low bias. The open question from the 2026-10-29 article was whether taking the median of the three works: a median only needs two of three votes alive, which in principle dodges both failure ends at once. This article tests that, and it sets the exam in unseen territory: BLINDRAW had never been computed on the two holdout scene sets before this run.

The headline: pooled, the median vote produced zero bad estimates (relative error over 10%) across all 45 points of three datasets — replication plus two holdouts — with a worst error of 4.29%. BLIND7 produced 9, 4, and 8 bad estimates on the same sets; BLINDRAW 1, 1, and 2. Deployed F1 loss was 0, 0, and −0.0024, tying the "just use BLIND3 everywhere" strategy, and the move-closer alarm was correct on all three sub-0.15 scales in every dataset. But three debits travel with that result. First, on holdout set 1 the median's mean absolute error (2.76%) actually lost to BLIND3 (2.05%): the median picked BLINDRAW in 9 of 15 scales there, and BLINDRAW carries a +4%-ish systematic bias on new scenes, which the vote inherited verbatim. Second, at s=1.0 on holdout 1 the error was +2.30%, narrowly missing the pre-registered 2% bar — the residue is a scene-level common-mode bias shared by all three estimators, which no median can remove. Third, the only three bad per-scene estimates all came from one scene (No. 606), where all three votes erred together by +10% to +11.5%. A median certifies the majority; when the majority is wrong in the same direction, it certifies the error.

Setup matches the earlier articles: the color-segmentation pipeline (base parameters min_area=120, bloom_area_min=900, kernel 7), estimator definitions and calibration references (3806.0 / 3740.0 / 3718.5) unchanged, the usual routing rule (ŝ ≥ 0.30 → P route, 0.15–0.30 → U, below 0.15 → U plus a move-closer alert), and "bad" defined as absolute relative error above 10%. Baseline sanity F1 was 1.000 on all three datasets.

## 2. Method

**Pre-registration.** Definitions, thresholds, and six predictions were frozen in data/2026-11-05-median-vote-prereg.md before any computation. Priors were allowed only from published data: the full three-estimator replication set (2026-10-25) and the pooled BLIND7/BLIND3 holdout results (2026-10-29 and 2026-11-04). MED3 is the median of the three ŝ values; if exactly one estimator yields no estimate, MED3 is the mean of the other two, flagged degraded (never triggered pooled in this run); if none yield one, MED3 has no estimate (never happened).

**Three datasets.** The replication set (seeds 101/202/303/404, 210 objects) is an in-sample check — the median idea came from this very data, so it can only verify reproduction, not generalization. The decisive evidence is the two holdouts: set 1 (505/606/707/808, 203 objects) and set 2 (909/1010/1111/1212, 209 objects), scene compositions copied verbatim from the original bench scripts, calibration references unchanged, 15 scales, identical pipeline parameters. Pooled is the deployment view; per-scene (60 points per dataset) is the stress view.

**Replication check.** Before writing, this run's pooled BLIND7/BLIND3 estimates were compared scale by scale against the three stored datasets from 2026-10-25, 2026-10-29, and 2026-11-04: 45/45 exact matches, and replication BLINDRAW matched 15/15 as well. The pipeline reproduction is exact; the holdout BLINDRAW numbers are genuinely new measurements.

**Policies compared.** ORACLE (true-s routing), ALWAYS-B7 (the unguarded status quo), ALWAYS-B3, ALWAYS-RAW, and MED3. Deployed F1 follows the earlier convention: a P choice runs with that policy's own ŝ-scaled parameters; a U choice scores the U route's F1. ALWAYS-B3 is included deliberately: the 2026-10-29 article already showed B3 alone has zero deployed loss, so MED3 first has to prove it is not worse than simply switching to B3.

**Six frozen predictions.** P1: pooled MED3 error at s=1.0 within 2% on both holdouts. P2: zero pooled MED3 bad estimates on both holdouts. P3: MED3 deployed F1 total loss within 0.005 of ALWAYS-B3's on every dataset. P4: alarm score 3/3 on both holdouts. P5: per-scene MED3 bad rate below BLIND7's, yet at least one per-scene MED3 bad estimate remains. P6: median-identity accounting — within the pooled failure band (s=0.15–0.30), MED3 equals BLINDRAW in a majority of scales, and at s=1.0 MED3 equals BLIND7 or BLIND3.

Raw data and scripts: data/2026-11-05-median-vote-bench.json, post-hoc summary data/2026-11-05-median-vote-posthoc.json, pre-registration and bench script under the same prefix in the project data/ directory.

## 3. Measurements

### 3.1 Pooled errors: the median's worst beats the others' typical

Replication (in-sample): BLIND7 jumps to +13.27% from s=0.30 down, reaching +80.90% and +162.00% at the extreme scales — 9 bad, mean absolute error 23.00%. BLINDRAW is bad only at s=1.0 (−55.06%); everywhere else it stays within ±4.43%, and across the failure band (0.15–0.30) its worst error is 1.00%. MED3's error series reads 0.00, −0.69, −0.72, −1.98, −2.15, −2.31, +0.20, +0.86, +1.00, +0.68, +0.22, +0.47, +0.42, +0.50, −3.14 — zero bad, worst 3.14%, mean absolute error 1.02%, the smallest of the four.

Holdout 1: BLIND7 has 4 bad (from +9.40% up to +97.70% and +139.29%), mean absolute error 20.61%. BLINDRAW has 1 bad (s=1.0, −53.50%) but sits systematically high mid-range at +3.55% to +4.29% — its merged-area calibration reference came from the replication scenes, and on new scenes the whole curve shifts up by roughly four points. MED3: zero bad, worst +4.29%, mean absolute error 2.76%. Note that here the median's mean error loses to BLIND3's 2.05%: BLIND3 is unusually accurate on this set (worst 6.58%), while the median selected BLINDRAW in 9 of 15 scales and inherited its +4% bias. The median picks the middle vote, not the most accurate one; when the middle vote carries a systematic bias, the output carries the same bias, merely fenced inside the safe zone.

Holdout 2: BLIND7 has 8 bad. BLINDRAW has 2 — beyond the usual s=1.0 collapse (−55.06%), it fails once more at s=0.8 (−26.64%): the raw mask's upper cluster holds 262 components against only 133 true blooms, partial petal fragmentation at that scale dragging the median down. That failure mode had previously appeared only per-scene; this is its first pooled appearance. MED3 selected BLIND7 at that scale (−1.51%) and walked away clean. Set totals for MED3: zero bad, worst 3.43%, mean absolute error 1.73% (BLIND3: 4.39%).

Across all three sets: MED3's pooled worst error (4.29%) is below BLIND3's worst on any single set (9.08%, 6.58%, 9.08%), and bad-estimate totals are 0 vs 21 (BLIND7), 0 vs 4 (BLINDRAW), 0 vs 0 (BLIND3). The difference from BLIND3 is in the shape of the error: B3's is a band of systematic low bias (−4% to −9% across the failure band), while MED3's is a small residual clamped from both sides (failure-band worst 1.00%, 4.29%, 2.20% across the three sets).

### 3.2 Median identity: in the failure band it *is* "pick RAW"; at s=1 it is "drop RAW"

Recording which estimator the median actually equals, per scale (the P6 ledger): across the failure band — 6 scales × 3 datasets = 18 points — MED3 equals BLINDRAW 18/18. The healthy band looks different: across 18 points at s ≥ 0.35, BLIND7 is the median 11 times, BLIND3 7 times, BLINDRAW never — at healthy scales RAW is always either the highest or the lowest vote, never the middle one. At s=1.0, the median equals BLIND7 on all three datasets.

This ledger exposes what median voting really is here: not a smoother, but a parameter-free automatic substitute. Whichever vote strays farthest gets fenced out by the other two; because the strays run in opposite directions at the two ends (BLIND7 high at small s, BLINDRAW low at large s), the same rule executes "trust RAW" inside the failure band and "drop RAW" at s=1, with no threshold and no need to know which end you are at. The price is structural: the switch can only pick one of the three, so the selected vote's own bias (BLINDRAW's +4% on holdout 1) becomes the output unaltered. Voting has no corrective power over a middle vote that is wrong-but-not-crazy.

### 3.3 End-to-end: tied with switching to B3, alarms perfect, one route miss

Deployed F1 total loss against ORACLE, summed over 15 scales:

| Policy | Replication | Holdout 1 | Holdout 2 |
|---|---|---|---|
| ALWAYS-B7 (unguarded) | 0.0169 | 0.0025 | 0.0122 |
| ALWAYS-B3 | 0.0000 | −0.0025 | −0.0024 |
| ALWAYS-RAW | 0.3619 | 0.3547 | 0.3684 |
| MED3 | 0.0000 | 0.0000 | −0.0024 |

Negative losses follow the standing convention: the U route occasionally beats the oracle's own routing on individual scales — an approximation artifact of the routing rule, not credit to the policy. MED3 minus ALWAYS-B3 is 0, +0.0025, 0 — inside P3's 0.005 allowance. But this table saturates, as established in 2026-10-29; an F1 tie is not equivalence. The separation lives in the error ledger (3.1) and the two accounts below.

Alarms: on the three scales with true s below 0.15, MED3 scores 3/3 on every dataset (P4 hits). ALWAYS-B7 scores 1/3 on replication and holdout 1 — the two extreme scales where its ŝ climbs back above 0.15 and the system silently accepts the frames. Route disagreements with ORACLE (P family vs U family): MED3 differs on exactly one scale across all 45 — holdout 2 at s=0.15, where ŝ=0.1467 slips under the alarm line and raises one extra move-closer alert (BLIND3 and BLINDRAW raise the same extra alert there; the true value sits on the threshold, the boundary coin-flip documented in 2026-10-29). For scale, ALWAYS-RAW's deployed loss above 0.35 comes almost entirely from a single scale, s=1.0, where ŝ=0.4494 routes to P with wrongly scaled parameters and F1 falls to 0.6381. RAW alone is a disaster; inside a vote it is the safest member. That asymmetry is the whole value of "fails at the other end."

### 3.4 Per-scene: the only bad estimates come from scene 606, where all three votes err together

Per-scene, 60 points per dataset: BLIND7 bad counts are 27, 20, 27; BLIND3 2, 1, 4; BLINDRAW 6, 14, 8; MED3 0, 3, 0. The first half of P5 hits (far below BLIND7 everywhere); the second half hits only on holdout 1 — I had predicted that BLINDRAW's per-scene instability would contaminate the median, and on replication and holdout 2 the per-scene median came out completely clean, so that guess stands refuted on two of three sets and is recorded as missed.

Holdout 1's three bad points deserve archiving one by one. All come from scene 606, at s=0.30, 0.28, and 0.25, where the three votes' errors are +11.07%/+5.17%/+11.50%, +10.14%/+5.07%/+11.29%, and +10.32%/+4.40%/+10.56% respectively — BLIND7 and BLINDRAW both cross the 10% line, and the median (which happens to be BLIND7's value) crosses with them. Scene 606 is not a new face: the consistency guard's only miss in the entire 2026-10-29 run was 606 at s=0.28. This scene's contour-area distribution pushes all three measurement pipelines in the same direction — they share the same contours and the same scene, so against scene-level common-mode error the "three estimators" are not three independent pieces of evidence. The median's failure condition is written right there: it defends against one vote dropping out, not against all three erring together.

### 3.5 Pre-registration scorecard

Six predictions: P1 half-hit — holdout 2 at s=1.0 is −1.38% (hit), holdout 1 is +2.30% against a 2% line (miss by 0.30 points; the three votes there are 1.023, 1.0246, 0.465, so the median correctly discarded RAW's failure and still inherited the +2.3% scene common-mode already measured in 2026-10-29 — the bar was lost to common mode, not to the vote). P2 full hit (0, 0). P3 full hit (differences 0, +0.0025, 0, all within 0.005). P4 full hit (3/3, 3/3). P5 half-hit (bad rate below BLIND7 on all sets; "at least one remains" true only on holdout 1). P6 full hit (failure band 18/18 equals BLINDRAW; s=1.0 equals BLIND7 on all three sets). Total: four full hits, two half-hits.

## 4. Analysis and trade-offs

First, my call on this bench: switch the calibration estimate to MED3 and retire the plan of guarding BLIND7 alone. The reason is not F1 — there MED3 merely ties B3 — it is the error and alarm ledgers: MED3 is the only policy with zero bad estimates in 45 pooled points, a worst error fenced at 4.29%, and a perfect alarm record. The guard route (CONS+RESCUE from 2026-10-29) carries 5 false rejections on holdout 1; the voting route has no "reject" action at all, and therefore no false-rejection ledger. The precondition matters and is empirical, not universal: the three votes fail in *different* directions here (kernel size, and morphology vs none, push the failures to opposite ends). Voting over three same-source estimators would only certify their shared error more confidently.

Second, the MED3 versus ALWAYS-B3 relationship, stated precisely: this run does not support "voting beats just using B3," nor the reverse. It supports: a lower error ceiling (4.29% vs 9.08%), far smaller failure-band errors (worst 4.29% vs 9.08%), and no need to know in advance which single estimator stays stable on new scenes — B3's steadiness across these three sets is only visible in hindsight, and at the time of the 2026-10-25 article its low bias could equally have flipped on some new set. What voting buys is robustness against having to bet on one estimator. The price is running two extra measurement pipelines (RAW is the cheapest — no morphology; B3 and B7 are one morphology-plus-clustering pass each), plus the occasions, like holdout 1, where mean error is slightly worse (2.76% vs 2.05%) because the middle vote carries a bias the vote cannot correct.

Third, the remaining risk collapses onto one word: common mode. Pooled, it is the +2.30% at s=1.0 that cost P1 its clean sweep; per-scene, it is 606's triple miss. Medians, consistency guards, and two-tier guards are all blind to it, because every signal built from the estimators' mutual relationships is blind when all three agree wrongly. Catching it requires a genuinely independent reading — a reference object of known size in the frame, or a second measurement principle unrelated to the area median. That is a different article, not a fourth same-source vote.

Fourth, a methodological note: the two half-misses (P1, P5) were the useful predictions. I had staked specific numbers on per-scene contamination and on the size of the s=1.0 common mode; the measurements corrected both (per-scene cleaner than expected, common mode more stubborn than expected). The voting line can close here: on the differential-failure problem it is this bench's best answer, and its boundary — common mode — now has a measured shape and a name.

## 5. Limitations and open questions

- All evidence still comes from one simulator family. The holdouts are new seeds from the same distribution, not a new camera or real field images; systematic bias of the simulator itself, shared by all three votes, is invisible to this design, and real inter-scene common mode will be larger.
- The median's output always equals one of the votes (true in all 45 pooled points of the identity ledger): it is a selection, not a fusion. No output is ever better than the best single vote; it only guarantees not picking the worst. Bias-corrected weighted fusion (e.g., de-biasing BLINDRAW from its history before voting) is untested.
- BLINDRAW's calibration reference (merged-area 3718.5) comes from the replication scenes, and its transfer bias on the holdouts (+4% on set 1, −0.4% to −2.2% mid-band on set 2) shows weaker cross-scene stability than the two morphology-based references. How much error a holdout-scene recalibration of the RAW reference would recover is untested — and it would change the frozen-reference convention, so it needs its own pre-registration.
- Whether per-scene MED3 also dodges RAW's fragmentation around s=0.8 on holdout 2 (it did pooled) is in the raw data but was not expanded point by point in this run; only the counts are reported.
- The degraded rule (mean of two when exactly one vote is missing) never triggered pooled; its behavior has samples only in the per-scene data and was not analyzed separately.
- Open questions, in queue order: an independent reading to guard BLIND3 itself remains unanswered — and after this run its nature has changed, since what now needs guarding is the three votes' shared blind spot; a field-reference-object method against common mode has not yet been designed or tested.

## 6. References

- Earlier articles in this series: 2026-10-25, "Can You Trust an Estimated s?" (the three estimator definitions, calibration references, and the tolerance sweep); 2026-10-29, "Divergence From 0.4% to 170%: A Consistency-Guard Validation" (the median-vote open question, scene 606's first miss, the first +2.3% common-mode reading); 2026-11-04, "The Middle Band Is Empty" (holdout set 2's pooled BLIND7/BLIND3 data). All priors for this run come from these three; raw data lives in the project data/ directory.
- This run's raw data: data/2026-11-05-median-vote-bench.json (three datasets × 15 scales: pooled and per-scene estimates, errors, deployed F1 and routing for all three estimators and MED3); pre-registration: data/2026-11-05-median-vote-prereg.md (frozen before the run, including the MED3 definition and P1–P6); post-hoc summary: data/2026-11-05-median-vote-posthoc.json (error statistics, route disagreements, false-alert ledger, median-identity ledger); script: data/2026-11-05-median-vote-bench.py.
- Detection and scoring: the Bloom-Counter color-segmentation pipeline (detector/color_segmentation.py; base parameters min_area=120, bloom_area_min=900, kernel 7); simulator seeds and scene compositions are in the bench script; scoring follows the 2026-10-17 convention (greedy center matching, label must match, tolerance max(38·g, 1.1·r)). The U-vs-P compute ratio cites the 2026-10-24 timing article (roughly 5–33× total time).

Author: Guangyi Zhao. All experiments, code, and data in this article are clean-room, original work; no client information is involved.
