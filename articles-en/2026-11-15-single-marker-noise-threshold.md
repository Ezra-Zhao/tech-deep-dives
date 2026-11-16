# One Marker Is Enough: Single-Reading Noise, Measured — the 8% Line Needs No Recalibration, and the False Flags Belong to the Gap Band

Author: Guangyi Zhao

## 1. The problem

The marker guard fitted to the three-estimator median (MED3) on 2026-11-06, and bias-corrected on 2026-11-14 down to an effective floor of s=0.12, was measured entirely under a laboratory protocol: the marker reading was the median of five replicates, and one pooled reading served every scene. Real deployment looks different — one marker in the frame, one reading per scene per frame. The per-scene ledger of 2026-11-14 still carried roughly 9/181 healthy false flags, measured with median readings; how much a single reading inflates the noise, and whether the per-scene threshold must be recalibrated because of it, is the account that article explicitly left to pool item 11.

My prior, written into the pre-registration before the main run (data/2026-11-15-single-marker-prereg.md), was pessimistic: single-reading error standard deviation would reach 2%–6% in the s=0.15–0.22 band, healthy false flags at the 8% line would triple against the median baseline, and the per-scene threshold would probably have to rise to 12%–20%, trading catch rate for false flags. All six predictions, P1–P6, bet on that script.

The measurements overturn most of it. Single-reading noise is several times smaller than I bet: after correction, the standard deviation is at most 0.22% for s ≥ 0.5, 1.05% at s=0.15 and 1.44% at s=0.12. In the retrospective pairing (five archived sets, 300 per-scene points, each paired with all 60 single readings), the healthy false-flag rate at the 8% line for s ≥ 0.15 is 4.13% — slightly below the median baseline of 4.80% on the same points, a ratio of 0.86, not three times above. The recalibrated threshold under the frozen definition comes out as 0.08 itself, in the pooled band and in each of the high, mid and low sub-bands separately: there is nothing to recalibrate. The source of the per-scene false flags also identifies itself: every healthy point whose pairing flag rate reaches 100% has a MED3 error of its own between +8.6% and +9.8% — inside the gap band between the 8% guard line and the 10% BAD line — and owes nothing to marker noise. The single reading only breaks down in the tail, s < 0.12: false flags of 15.9% (retrospective) to 25.0% (holdout five), while raising that band's line to 12% collapses the BAD catch from 97.8% to 56.1%, because the tail's three BAD points carry errors of only +10.9% to +15.9% and their D sits near the line to begin with. The conclusion is segmented: at s ≥ 0.12 the single-marker guard deploys exactly as it stands, 8% line unrecalibrated; below 0.12 the single-marker guard is unusable and no threshold rescues it, so the existing U_alert handling stays.

## 2. Method

- Marker protocol, guard definition and thresholds are carried over unchanged: a solid petal-pink disc of exactly 40 px radius on a foliage background with center jitter of ±60 px, scaled with the same pipeline, measured through kernel-3 morphology contour area, reference area 4912.0; bias correction uses the curve frozen on 2026-11-14 (piecewise-linear in log-s, fixed-point iteration ×3, divisor floored at 0.80) with no refitting allowed this round; D = MED3 / marker − 1, FLAG line 8%, BAD is a MED3 relative error above 10% in absolute value; MED3 is the median of BLIND7, BLIND3 and BLINDRAW (references 3806.0, 3740.0, 3718.5); the 15-tier s grid is the same as before.
- Arm A (noise): 60 fresh marker frames, seeds 13000–13059, never used by any earlier article; single readings per tier, raw and corrected in parallel. The 60 frames are also cut in order into 12 groups of five, and the median-of-5 error distribution is compared against the single-reading standard deviation.
- Arm B (retrospective pairing): archived per-scene MED3 points from five sets — replication, holdout one and holdout two (2026-11-05), holdout three (2026-11-06), holdout four (2026-11-14) — 4 scenes × 15 tiers = 300 points, of which 285 healthy and 15 BAD. Each point is paired with all 60 corrected single readings of its tier to form D; flag and catch rates are pairing rates (per-point alarm share over 60 readings, averaged over points). The threshold scan uses 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25; the recalibrated threshold is, per the frozen definition, the smallest scan line whose healthy pairing flag rate at s ≥ 0.12 is at most 5%, computed for the full band and per sub-band. The median baseline is recomputed on the same 300 points with the 2026-11-14 validation frames' corrected median reading, at the same 8% line.
- Arm C (holdout five): fresh scenes 2121, 2222, 2323, 2424 with compositions 35/18, 32/19, 36/17, 33/20 — 210 objects, never used before; per-scene MED3 computed fresh (60 points), each scene/tier paired with 3 dedicated single marker frames (seeds from 31000, disjoint from arm A), reporting flag and catch rates at the 8% line in pairing terms.
- The pairing is simulated: marker frames and scene frames are generated independently, with different backgrounds. In a real co-located shot the marker shares the scene's scaling — which is the marker method's whole premise — but the background interaction differs; this is recorded as a limitation.

## 3. Measurements

### 3.1 Single-reading noise: several times smaller than bet, out of control only in the tail

Error distribution of the 60 single readings (corrected):

| s | mean | sd | p5 to p95 | median-of-5 sd |
|---|---|---|---|---|
| 1.0 | 0.00% | 0.00% | 0.00% to 0.00% | 0.00% |
| 0.8 | +0.06% | 0.15% | −0.20% to +0.29% | 0.06% |
| 0.65 | −0.08% | 0.19% | −0.38% to +0.17% | 0.09% |
| 0.5 | −0.18% | 0.22% | −0.58% to +0.12% | 0.10% |
| 0.4 | −0.05% | 0.27% | −0.45% to +0.35% | 0.07% |
| 0.35 | −0.02% | 0.36% | −0.50% to +0.63% | 0.22% |
| 0.30 | −0.10% | 0.52% | −0.90% to +0.63% | 0.15% |
| 0.28 | +0.32% | 0.40% | −0.36% to +0.93% | 0.26% |
| 0.25 | −0.09% | 0.38% | −0.72% to +0.40% | 0.18% |
| 0.22 | +0.23% | 0.51% | −0.55% to +1.05% | 0.28% |
| 0.18 | −0.15% | 0.77% | −1.50% to +0.85% | 0.55% |
| 0.15 | +0.06% | 1.05% | −1.53% to +1.53% | 0.54% |
| 0.12 | +0.09% | 1.44% | −2.17% to +2.33% | 0.51% |
| 0.10 | +0.34% | 1.59% | −1.94% to +3.10% | 0.74% |
| 0.07 | +3.95% | 4.35% | −4.57% to +11.43% | 2.91% |

Three readings of this table. First, the noise is smaller than the pre-registration bet at every tier: the 0.15–0.22 band measures 0.51%–1.05% against a bet of 2%–6%, an overestimate by a factor of two to six. The mechanism is plain: the marker is a large solid disc in the same color mask as the flowers, its contour is clean and complete, and the only perturbations are foliage intruding at the contour edge and resampling quantization — both around the one-percent level while the marker still covers about 71 pixels at s=0.12 (4912 × s²). Second, the zero variance at s=1.0 is a simulator artifact and must not be extrapolated: at full resolution all 60 contour areas equal the reference 4912.0 exactly, because center jitter does not change the pixel count; a real camera at s=1 will not be this kind. Third, the tail is a different animal: at 0.07 the raw single readings average −16.34% with sd 4.05% and a clear left skew, and a correction curve fitted to the median bias (−21.0%) systematically over-corrects single readings, landing at a corrected mean of +3.95% with p95 at +11.43%. Below 0.12 the problem is not only noise size; the correction itself is mismatched to the single-reading distribution. Section 3.3 collects that bill.

The median-of-5 advantage is real but buys a non-binding term: its sd ratio against the single reading lands in the bet band of 0.40–0.70 on 8 of the 12 tiers in [0.15, 1.0] (0.4 and 0.30 come in lower, at 0.259 and 0.288 — the median is steadier than bet; 0.18 is 0.714, just above the band; at s=1.0 both sides are zero and the ratio is undefined). In the binding band it compresses sd from 1.44% to about 0.51% at s=0.12 — and the next section shows that this one point is not where false flags come from.

### 3.2 Retrospective pairing: false flags do not rise — the hot points are all in the gap band

Arm B at the 8% line (pairing rates):

| scope | healthy | false-flag rate | BAD | catch rate |
|---|---|---|---|---|
| all tiers (300 points) | 285 | 5.99% | 15 | 99.11% |
| s ≥ 0.15 | 229 | 4.13% | 11 | 99.70% |
| s ≥ 0.12 | 248 | 4.51% | 12 | 99.44% |
| high band s ≥ 0.30 | 135 | 4.81% | 5 | 100% |
| mid band 0.18–0.28 | 75 | 3.87% | 5 | 99.67% |
| low band 0.12–0.15 | 38 | 4.69% | 2 | 97.50% |
| tail s < 0.12 | 37 | 15.90% | 3 | 97.78% |

The median baseline on the same 300 points at the same line: healthy false flags 19/285 = 6.67% overall, 11/229 = 4.80% at s ≥ 0.15, BAD caught 15/15. The single-reading 4.13% against the baseline 4.80% is a ratio of 0.86 — not the threefold increase of the pre-registration, but a slight decrease. The two protocols differ by noise-level amounts, for a structural reason: the variance of D is the sum of two terms, the scatter of per-scene MED3 error (whose near-line population sits at 8%–10%) and the marker-reading noise (at most 1.44% for s ≥ 0.12). The first term is several times the second; swapping median for single readings barely moves the distribution of D.

Opening the 29 points whose pairing flag rate is at least 50% makes the point directly. Fourteen of them are healthy, and the six healthy points at a 100% flag rate carry MED3 errors that sit, without exception, in the gap band: scene 606 at +8.55% and +8.58% (s=0.8, 0.65), scene 1616 at +9.76%, +9.02%, +9.23% and +9.48% (s=0.5, 0.4, 0.35, 0.25), with 606 at s=0.22 (+8.91%, flag rate 88.3%) and 1616 at s=0.12 (+8.92%, 70.0%) behind them. For these points D is essentially MED3's own error (with the marker near truth, D ≈ error); the guard alarms by its 8% line and is booked as a false flag by the 10% BAD definition — the same near-line mechanism the 2026-11-14 article found in the pooled account, now appearing in bulk per-scene. The remaining high-flag healthy points concentrate in the tail (scene 303 at s=0.07, error −7.86%, flag rate 78.3%; scene 101 at s=0.07, −5.14%, 63.3%) — that part really is marker noise, and its size matches the tail breakdown of Section 3.1.

On the catch side, no BAD point's pairing catch rate at 8% falls below 93.3% (the lowest is 1616 at s=0.10, error +10.90%), and the 11 BAD points at s ≥ 0.15 pool to 99.70%. Single-reading noise eats no real failure.

### 3.3 The threshold scan: a cliff above 8%, and the recalibration answer is "do not move it"

Under the frozen definition (smallest scan line with healthy pairing flag rate ≤ 5%), the recalibrated threshold at s ≥ 0.12 is 0.08, and the high, mid and low sub-bands each return 0.08 on their own. This is not a coarse scan: at the 8% line the three sub-bands already sit at 4.81%, 3.87% and 4.69%, inside the 5% budget. Prediction P5's bet — a threshold of 0.12–0.20 with sub-bands differing by at least four points — misses in full.

The cost of raising the line is a cliff (s ≥ 0.12 scope): at 0.10 the false-flag rate falls to 0.40% but the BAD catch drops from 99.44% to 82.78%; at 0.12 false flags are 0.01% and the catch is 5.14%; at 0.15 the catch is zero. The mechanism sits in the BAD points' error distribution: the 12 BAD points at s ≥ 0.12 cluster between +10.14% and +11.67% (scene 606's three, the bulk of 1616, one point of 1414), and D tracks the error, so any line above roughly 11% releases this entire population at once. The two-point gap band between 8% and 10% is the guard's whole working space: healthy near-line points push up to +9.8% from below, true BAD points press down to +10.1% from above, and the two populations are 0.3 points apart. No threshold inside that band separates them; 8% at least keeps the catch side. Trading a catch rate of 99% for single digits, in exchange for false flags falling from 4.5% to near zero, is not a trade worth making.

The tail (s < 0.12) ledgers separately: its frozen-definition threshold is 0.12 (false flags 3.38%), but the same band's BAD catch collapses from 97.78% at the 8% line to 56.11%. The tail's three BAD points (1616 at s=0.10, +10.90%; holdout-four scenes 1717 and 2020 at s=0.10, +12.10% and +15.90%) are pushed back under a 12% line again and again by marker noise (corrected sd 1.59%–4.35% in this band, plus the mismatched correction at 0.07). The tail's verdict is not a higher line but no guard at all: at 8% it is too noisy (15.9% false flags), at 12% too blind (56.1% catch), and neither reaches a deployment standard. Handling stays as before — below 0.12 the deployment already routes to U_alert, and the guard does not speak there.

### 3.4 Holdout five: false-flag rates reproduce the retrospective estimates almost digit for digit

Holdout five's baseline sanity F1 is 1.000 (210 objects, mean per-scene). Pooled MED3 error runs from −2.63% to +2.14%, the largest per-scene absolute error over the 60 points is 8.37%, and the BAD count is zero — this pool's per-scene points sit far from the line overall, so the catch side has no fresh sample this round (recorded as a limitation; catch evidence rests on the retrospective 15 BAD points).

Healthy false-flag rates (8% line, 3 dedicated single readings per point): 4.17% at s ≥ 0.15 (48 points), against arm B's same-band estimate of 4.13% — a difference of 0.04 points; 5.13% at s ≥ 0.12, against 4.51%, a difference of 0.62 points. By band: high 5.95%, mid 2.08%, low 8.33%, tail 25.0%. Of the 8 points that alarm at all, five are gap-band points whose MED3 error hugs the line (2222 at s=0.35, −8.20%; 2424 at s=0.30, +8.37%, and s=0.28, +7.75%; 2222 at s=0.12, −8.33%; plus 2323 at s=0.10, +4.70%, alarming on part of its pairings), and three sit in the tail — including 2323 at s=0.07, whose MED3 error is only −0.14% and whose alarm comes purely from marker scatter (its three readings are 0.0725, 0.0780, 0.0725 against a true 0.07; the 0.0780 reading pushes D to −10.4%). Holdout five replays both retrospective conclusions, one each: in the mid bands the false flags are the gap band's account; in the tail they are the noise's account.

### 3.5 Settling the predictions

- P1 (single-reading sd: at most 1.0% for s ≥ 0.5; 2%–6% in the 0.15–0.22 band; at least 6% at s=0.07): half. The first clause hits with room to spare (measured maximum 0.22%); the second misses (measured 0.51%–1.05%, an overestimate by a factor of two to six); the third misses (measured 4.35%).
- P2 (median-of-5 to single sd ratio mostly within 0.40–0.70 over [0.15, 1.0]): half. Eight of twelve tiers land in the band (the s=1.0 ratio is undefined and counts as no hit); 0.4 and 0.30 fall below it (0.259, 0.288 — the median is steadier than bet) and 0.18 sits just above at 0.714.
- P3 (healthy false-flag rate at 8%, s ≥ 0.15, at least 3× the median baseline): miss. The measured ratio is 0.86, in the opposite direction — the single-reading rate is slightly below baseline.
- P4 (BAD pairing catch at 8%, s ≥ 0.15, at least 90%): hit, measured 99.70%.
- P5 (recalibrated threshold in 0.12–0.20, catch below 90% at that threshold, sub-band thresholds differing by at least four points): miss on all three clauses — the recalibrated threshold is 0.08, the catch there is 99.44%, and the high, mid and low sub-bands share one threshold. Only the tail returns 0.12, and that is the unusable band's account, not support for P5.
- P6 (holdout-five false-flag rate at 8% within 10 points of the retrospective same-band estimate; at the recalibrated threshold, within the retrospective estimate plus 5 points): hit. The measured differences are 0.04 points, and — the recalibrated threshold being 0.08 itself — 0.62 points on the second clause, inside the limit.

The three missed bets (P1's magnitude, P3, P5) fail at the same place: before the run I booked marker-reading noise as the dominant error source of the per-scene guard. The measured dominant term is MED3's own per-scene scatter — the 2026-11-14 per-scene residue (9/181) was mostly gap band to begin with, and in the pre-registration I had defaulted it onto the marker's account.

## 4. Analysis and trade-offs

The deployment prescription has three clauses. First, the single-marker guard deploys as-is at s ≥ 0.12: one marker, one reading per scene, corrected reading, 8% line. The five-replicate median can retire — the standard deviation it removes (1.44% to 0.51% at s=0.12) is not a binding term, and deployment saves four markers' worth of frame area and per-frame aggregation for a guard performance that is indistinguishable from the median protocol in pairing terms (false flags 4.51% against the baseline's 5.65% at s ≥ 0.12 on the same 300 points, baseline 14/248). Second, the 2026-11-14 effective floor of 0.12 extends from the pooled-median protocol to the single-reading protocol: this round's evidence shows the floor's cause is unchanged under single readings — at 0.12 the noise (1.44%) is still far below the gap band's width, and below 0.10 noise and correction mismatch take over. Third, the tail (s < 0.12) gets no single-marker guard: too noisy at 8%, too blind at 12%, it keeps the U_alert plus human-review handling. If a tail guard is ever required, the first thing to fix is not the threshold but the 0.07 correction curve's mismatch to single readings (refit on the single-reading distribution, or fall back to raw readings with a wider tolerance band) — another round's account.

One correction of record to an earlier conclusion: the 2026-11-14 article booked the per-scene residual false flags mainly to per-scene MED3 scatter; this round's pairing measurement supports that attribution and sizes it — gap-band healthy points (error 8%–10%) alarm under every marker protocol, a structural product of a guard line and a BAD line only two points apart, not a reading-noise effect. Any further reduction of per-scene false flags has exactly two levers with mechanical advantage: narrowing MED3's own per-scene scatter (per-scene calibration sampling error, pool item 21), or re-booking gap-band alarms as "near-line review" instead of false flags. Moving the marker or the threshold has no leverage; this round's data closes both of those roads.

The cost ledger favors the prescription: deployment gets cheaper. Markers drop from five to one; calibration remains the one-off 20 frames of 2026-11-14 (the curve is untouched); runtime cost per scene per frame is one contour-area measurement and one table-lookup correction, as before. What is given up — the tail guard and the median aggregation — is no loss: the first never held under a deployment protocol, and the second was buying a non-binding term.

## 5. Limitations and open questions

- All evidence is still this simulator's portrait: the marker's low noise presumes a solid disc measured cleanly in the same color mask. A real camera adds print color error, glare and partial occlusion — noise sources this round does not have — so the 1.44% single-reading sd at s=0.12 must not be carried into a real deployment; arm A must be re-measured on real frames first.
- The pairing is simulated: marker and scene frames have independent backgrounds, while a real co-located shot shares illumination and lens distortion between the two readings. This round cannot say whether that correlation shrinks or inflates the scatter of D.
- Holdout five contains zero BAD points: fresh catch-side evidence is absent, and the 99%-order catch rates rest entirely on the retrospective archive's 15 BAD points, whose errors concentrate at +10% to +16%. The single-reading catch for larger common-mode failures (the injection arm's +30% order) was not re-measured this round; algebra says it can only be easier to catch, but that is inference, not measurement.
- The median-of-5 standard deviations are estimated from 12 groups per tier, so each sd carries a sizable standard error of its own; the two out-of-band ratios (0.259, 0.288) may be small-sample fluctuation and were not re-validated.
- The 0.07 correction mismatch is attributed only qualitatively (a curve fitted to median bias, applied to a single-reading distribution): how much of it is the raw distribution's skew (mean −16.34% against a median bias of −21.0%) and how much is the 0.80 divisor floor biting was not decomposed this round. Rescuing the tail starts with that decomposition.
- The cause of per-scene MED3 scatter itself (scene bloom counts versus upper-cluster median error) remains pool item 21's account; this round proves it is the binding term and does not measure it.

## 6. References

1. Earlier articles in this series: Guangyi Zhao, "Three Votes Wrong Together — Who Raises the Alarm?" (2026-11-06), for the marker guard's definition and the five-replicate median protocol; "Correcting One Negative-Bias Curve Moved the Guard's Floor from 0.22 to 0.12" (2026-11-14), for the frozen correction curve, the pooled floor of 0.12, the per-scene residual false flags and this round's topic; "Three Votes, Take the Middle" (2026-11-05), for the MED3 definition and the three retrospective archives.
2. Code under test: the Bloom-Counter repository's simulator/generate.py (_foliage_background and the PINK constant) and detector/color_segmentation.py (_petal_mask); the marker measurement (morph_contours3) and the blind_cluster estimator are carried over from the 2026-11-06 bench; references 3806.0, 3740.0, 3718.5 and the marker reference 4912.0 are unchanged.
3. This round's data (archived under the project's data/ and mirrored into the tech-deep-dives repository's data/ with the Chinese article): 2026-11-15-single-marker-prereg.md (pre-registration: the three arms, the recalibration definition, P1–P6), 2026-11-15-single-marker-bench.py, 2026-11-15-single-marker-bench.json with its progress.jsonl (arm A's full per-tier readings, arm B's 300 per-point pairing rates, arm C's per-point triple readings), 2026-11-15-single-marker-posthoc.py and 2026-11-15-single-marker-posthoc.json (threshold scan, band and hot-point ledgers, prediction verdicts).

---

Author: Guangyi Zhao. The experiment design, code and data in this article are clean-room work of my own: the scene generator, detector, estimators and analysis scripts are my own project and hand-written code, the experiments ran only on my own machine, and no client information or third-party system is involved.
