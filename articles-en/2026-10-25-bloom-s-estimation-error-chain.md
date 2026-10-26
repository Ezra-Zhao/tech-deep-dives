# Can You Trust an Estimated s? The End-to-End Error Chain of Median-Area Scale Estimation, Measured

Author: Guangyi Zhao

## 1. Problem and background

This article settles two debts from earlier in this series.

The first is from the 2026-10-20 calibration-drift article, §4. There I proposed a deployment shortcut: after moving a camera, skip the full recalibration — shoot a few frames, measure the median bloom contour area, divide by the baseline median (3,806 px²), take the square root, and you have an estimate ŝ of the geometric scale s; then scale all three detector parameters by ŝ. I labelled it honestly at the time: the estimator had never been validated end-to-end, every experiment used the true s handed over by the resampler, and the recipe was a candidate, not a conclusion.

The second debt is from the 2026-10-24 resampling article, §4. Its route rule also consumes s: s ≥ 0.30 takes the parameter-scaling route (P, cheap), 0.15 ≤ s < 0.30 takes the input-upscaling route (U, expensive but robust), and s < 0.15 raises a "move the camera closer" alert. That article likewise closed by noting that route selection driven by an *estimated* s was untested.

Both debts are one error chain: how accurately can area be measured → how far ŝ drifts → how much F1 a drifted ŝ costs inside parameter scaling → how often it picks the wrong route, and at what price. This article measures the whole chain. The headline: estimator bias is not the main risk. The main risk is the step that measures the areas — if you measure them with the detector's own morphology pipeline, you are measuring a distribution that the kernel is actively killing, and ŝ inflates by a systematic 13% or more over a whole band of scales. Downstream tolerance, meanwhile, is asymmetric — underestimation is forgiven, overestimation is punished — and that asymmetry can be exploited by one fixed shrink factor.

Setup is identical to the three previous articles: the Bloom-Counter colour-segmentation pipeline (`detector/color_segmentation.py`; baseline parameters `min_area=120`, `bloom_area_min=900`, kernel 7), four simulated 1280×960 scenes (seeds 101/202/303/404), 210 objects (134 blooms, 76 buds), greedy centre matching with label agreement required, micro-averaged over the four scenes. Baseline sanity F1 = 1.000.

## 2. Method

Fifteen scales: 1.0 / 0.8 / 0.65 / 0.5 / 0.4 / 0.35 / 0.30 / 0.28 / 0.25 / 0.22 / 0.18 / 0.15 / 0.12 / 0.10 / 0.07, with 0.35, 0.28, 0.18 and 0.12 added to bracket the route boundaries at 0.30 and 0.15. Each scale starts from a native small frame produced by INTER_AREA downscaling (the same generation as part A of the earlier articles), and four things are measured:

**Four estimators.** Each estimator has a calibration step (on baseline frames, with ground-truth matching, measure its own median bloom area as the reference) and a field step (on the new frames, with no labels, measure a bloom median; ŝ = √(field median / reference)). They differ only in how area is measured:

- ORA7: ground-truth-matched contours after baseline morphology (kernel 7), `contourArea` — the method the 2026-10-20 article used to measure area drift. Reference 3,806.0, digit-for-digit the earlier baseline median. It needs labels, so it is not field-deployable; it is the upper bound for this estimator family.
- BLIND7: the ORA7 pipeline taken to the field verbatim — all contour areas after kernel-7 morphology, clustered by 1-D 2-means on log area, upper-cluster median as the bloom median. This is the most natural implementation of the 2026-10-20 proposal: reuse the detector's own measurement code.
- BLIND3: the same, but with a kernel of 3 (the smallest odd kernel; minimal closing and denoising). Reference 3,740.0 — this is the kernel-3 pipeline's own calibrated median on the same baseline frames, not a typo for 3,806; the 1.7% gap between the two references is the kernel's direct effect on area (§3.1).
- BLINDRAW: no morphology at all — connected-component pixel areas of the raw petal mask, clustered the same way. Its reference is the median *merged* pixel area per bloom on baseline frames (components belonging to one bloom summed), 3,718.5, because one bloom's raw mask is normally several components.

A trust guard for the blind estimators was fixed before any end-to-end scoring (pre-registered): an estimate is accepted only if cluster separation ln(upper median / lower median) ≥ 0.8, otherwise it is recorded as REFUSED. On baseline frames the log ratio of the two class medians is 2.40, so 0.8 is a lenient bar.

**Tolerance sweep (estimator-independent).** Run the P route with parameters scaled by s_used = f·s_true for f ∈ {0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6} and record F1. This separates "how much error the downstream can absorb" from "how much error the estimators actually make".

**End-to-end.** Each estimator's ŝ is fed both to the P route (parameters scaled by ŝ) and to the route rule, against an oracle that uses the true s. Execution semantics: choosing P means running P with that estimator's own ŝ parameters, not the oracle's; choosing U means U-LINEAR; s < 0.15 runs U and records an alert. Guarded variant: a refused blind estimate selects nothing and falls back to U.

Data and code: `data/2026-10-25-bloom-s-estimation-bench.json` and the bench script of the same name, reproducible in the repository virtualenv with one command.

## 3. Measurements

### 3.1 Estimator bias: the bound is a small one-sided underestimate; the blind implementations each collapse their own way

Pooled (four frames combined) relative error of ŝ, in %:

| true s | ORA7 | BLIND7 | BLIND3 | BLINDRAW |
|---|---|---|---|---|
| 1.0 | 0.0 | 0.0 | 0.0 | **-55.1** |
| 0.8 | -0.7 | -0.7 | -0.3 | -4.4 |
| 0.65 | -0.8 | -0.9 | -0.7 | -0.4 |
| 0.5 | -2.0 | -2.0 | -2.0 | +0.4 |
| 0.4 | -2.5 | -2.5 | -2.2 | +0.4 |
| 0.35 | -2.3 | -2.3 | -2.5 | -0.2 |
| 0.30 | -3.8 | **+13.3 (refused)** | -3.5 | +0.2 |
| 0.28 | -4.3 | **+13.8 (refused)** | -3.6 | +0.9 |
| 0.25 | -5.3 | **+12.4 (refused)** | -4.4 | +1.0 |
| 0.22 | -5.4 | **+12.7 (refused)** | -5.0 | +0.7 |
| 0.18 | -6.9 | **+13.7 (refused)** | -5.8 | +0.2 |
| 0.15 | -12.4 | **+15.6 (refused)** | -6.9 | +0.5 |
| 0.12 | -13.0 | +12.2 | -9.1 | +0.4 |
| 0.10 | -0.1 | **+80.9** | +0.5 (refused) | -0.2 |
| 0.07 | +37.0 | **+162.0** | -3.1 (refused) | -3.4 |

Start with the bound. ORA7's bias is the direct projection of the 2026-10-20 area drift: contour areas run systematically below the s² prediction (blooms -1.4% to -10.4%), so after the square root ŝ underestimates, from -0.7% at s=0.8 to -13.0% at s=0.12. Constant sign, predictable size — not frightening in itself. The tail is: at s=0.10 the error snaps back to -0.1% and at 0.07 it flips to +37.0%. That is not the estimator recovering; only 44 and then 6 of the 134 blooms can still be matched at those scales, the survivors are the largest of their class, and survivorship inflates the median. The matched-count sequence (134 → 133 → 130 → 126 → 118 → 97 → 44 → 6) is the real reading of that row: below s=0.10, ORA7's number is meaningless however close to the truth it looks.

BLIND7 agrees with ORA7 digit for digit while s ≥ 0.35 — buds alive, clusters separable, blind clustering finds the right upper cluster. Its cluster counts record the collapse: the lower (bud) cluster holds 44 members at s=0.4 and 18 at s=0.35, out of 76 true buds. Kernel 7 is killing buds, exactly as the morphology survival data in the previous articles showed. By s=0.30 bud contours are essentially gone, 2-means has nothing to split except the ~130 bloom contours themselves (68 + 63), the upper median lands at 439.5 against a true bloom median of 317.0 (ORA7's), and ŝ inflates +13.3%. From 0.28 down to 0.15 it stays pinned between +12% and +16%. This is not noise; it is a circular dependency — you are trying to estimate the very kill radius of the kernel, with a ruler the same kernel has already trimmed. The separation guard refuses all six of those scales (separations 0.595–0.729, all < 0.8): two halves of one class sit close together, and the guard can tell this is not a true bimodal split. But the guard is not complete. At s=0.12 separation is 0.833 and it passes, marginally, with +12.2% error. At s=0.10 and 0.07 it also passes, where the whole field holds 49 and 13 contours (per-frame estimates return nothing at all — no frame reaches 8 contours) and ŝ is off by +80.9% and +162.0%: with the sample size collapsed, the surviving contours are so dispersed that separation grows instead of shrinking. A separation-only guard controls the middle band; it does not control the extremes.

BLINDRAW collapses at the opposite end. At s=1.0 it reports -55.1%: at baseline scale a bloom's raw mask is fragmented — 445 connected components across four frames against 210 true objects — the upper cluster mixes fragments and whole flowers, its median is 751.0 against the merged reference 3,718.5, and the guard does not catch it (the split it finds is noise specks versus everything else, separation a misleading 6.621). But once s ≤ 0.65, downscaling squeezes petal gaps below a pixel, fragments merge on their own, and BLINDRAW becomes the most accurate estimator on the table: pooled error within ±1.0% at every scale down to 0.10, and -3.4% at 0.07; per-frame error stays within about ±2.3 points for s ≥ 0.12, widening to -4.4% and -6.3% at 0.10 and 0.07 — where the median bloom area is only 37 and 17 px, a single pixel of quantisation is already several percent of the area, so wider per-frame jitter is a matter of magnitude, not a new failure mode. The transition band is s=0.8: pooled -4.4% looks acceptable, but per-frame errors run -55.4% to -2.0% — two frames still fragmented, two already merged, and pooling hides the instability. This is the second time in this series that a pooled number has concealed per-frame instability; from here on, any pooled estimate I report comes with its per-frame range.

BLIND3 is the steadiest of the four. A kernel of 3 is enough to close petal fragments into whole blooms at baseline (reference 3,740.0, only 1.7% below the kernel-7 value) and small enough to keep buds alive to s=0.15 (cluster counts still 76 + 134 at s=0.30; 43 + 133 at 0.15). Its error is ORA7-shaped — one-sided, from the same area drift — but uniformly smaller in the band that matters: -3.5% to -6.9% across 0.15–0.30, -9.1% at 0.12. Per-frame error for s ≥ 0.30 stays inside -4.0% to +1.6%, so a single frame would have sufficed in these scenes; pooling four frames is insurance, not a requirement. At the bottom end the guard refuses BLIND3 twice — s=0.10 (separation 0.611) and s=0.07 (0.768) — even though its point estimates there are +0.5% and -3.1%: false refusals, whose only cost is falling back to U (see §3.4), i.e. compute, not accuracy.

One asymmetry is worth stating plainly: the two measurement pipelines fail at opposite ends. BLIND7's validity window is s ≥ 0.35 (buds not yet killed); BLINDRAW's is s ≤ 0.65 (fragments already merged; per-frame stable at ≤ 0.65, pooled-only at 0.8). Where both are valid (0.35–0.65) they agree. And BLIND3 covers almost the whole range in point accuracy, but the *guard* only certifies it down to 0.12. "The estimate is accurate" and "the estimate is certifiably trustworthy from observables alone" are two different claims, and the gap between them is widest exactly where deployment is hardest.

### 3.2 Downstream tolerance: a wide plateau, asymmetric — underestimating is safer than overestimating

P-route F1 under an imposed error factor f (selected scales):

| f | s=1.0 | s=0.5 | s=0.3 | s=0.22 | s=0.15 |
|---|---|---|---|---|---|
| 0.6 | 0.762 | 0.867 | 0.910 | 0.969 | 0.912 |
| 0.7 | 0.924 | 1.000 | 1.000 | 0.998 | 0.912 |
| 0.8 | 1.000 | 1.000 | 1.000 | 0.998 | 0.912 |
| 0.9 | 1.000 | 1.000 | 1.000 | 0.993 | 0.912 |
| 1.0 (oracle) | 1.000 | 1.000 | 1.000 | 0.981 | 0.846 |
| 1.1 | 1.000 | 1.000 | 1.000 | 0.958 | 0.846 |
| 1.25 | 1.000 | 1.000 | 0.963 | 0.909 | 0.846 |
| 1.4 | 0.993 | 0.942 | 0.929 | 0.868 | 0.782 |
| 1.6 | 0.919 | 0.797 | 0.775 | 0.723 | 0.636 |

Three readings. First, the plateau is wide: at s ≥ 0.5, any f between 0.7 and 1.25 is lossless or nearly so (the sole exception is f=0.7 at s=1.0, 0.924). A ±10% estimation error, on its own, costs almost nothing anywhere — the two class medians sit 11× apart, and the plateau the 2026-10-20 threshold sweep found is what absorbs the error.

Second, the plateau is asymmetric, and the asymmetry grows as s shrinks. On the underestimate side, at s=0.22 every f from 0.7 to 0.9 *beats* the oracle (0.998 / 0.998 / 0.993 against 0.981), and at s=0.15 the whole f ≤ 0.9 region sits at 0.912 against the oracle's 0.846. On the overestimate side there is no such region: at s=0.22, f=1.1 is already 0.958 and f=1.6 is 0.723. The mechanism is visible in bud recall. Overestimating raises both area thresholds and (in ratio) pushes `bloom_area_min` into the bloom distribution while `min_area` eats buds — bud recall at f=1.6 collapses at every scale (0.658 at s=1.0, 0.276 at 0.5, 0.145 at 0.22, 0 at 0.15). Underestimating lowers `min_area`, which at small scales rescues the buds that morphology leaves with contour areas of 2 px (bud recall at s=0.15 goes from 0.276 at f=1.0 to 0.566 at f ≤ 0.9); its own failure mode — `bloom_area_min` sinking so low that buds are reclassified as blooms — only bites at large scales (bud recall 0.342 at s=1.0, f=0.6). The two failure modes trade places around s≈0.3.

Third, the cleanest single number in the sweep: **f=0.9 is never worse than the oracle at any of the 15 scales**, and strictly better at three (0.25, 0.22, 0.15); f=0.8 also never loses in this bench, but at large scales it sits closer to the f=0.7 reclassification cliff. In other words, shrinking the s you actually use by a deliberate 10% dominates using the true s — because the area drift of §3.1 already biases every honest estimator low, and the downstream prefers it that way. Below s=0.15, note, the sweep goes flat for f ≤ 1.1 (F1 identical at 0.12 and 0.10): both the kernel floor of 3 and the surviving morphology output stop responding to the thresholds, and P is insensitive to s_used there — dead is dead, at any dosage.

### 3.3 End-to-end parameter scaling: real damage concentrates in BLIND7's unguarded band, plus one disaster at s=1.0

Delta of end-to-end P-route F1 against the oracle, by estimator (nonzero entries and the total-loss rows only; every unlisted scale is Δ=0 for that estimator):

- ORA7: +0.005 at s=0.25, +0.012 at 0.22, +0.066 at 0.15 (F1 0.912 versus 0.846, bud recall 0.276 → 0.566) — its systematic underestimate is harmless-to-helpful for P, for the reason in §3.2. The exception is s=0.07, -0.175 (0.536 versus 0.711): the survivorship-inflated ŝ=0.096 raises the classification threshold back into the surviving blooms. The bound itself breaks at the bottom, and in the harmful direction.
- BLIND7: 0 down to s=0.30, then -0.015 (0.28), -0.015 (0.25), -0.023 (0.22), -0.067 (0.18; bud recall 0.447 against the oracle's 0.763), 0 again at 0.15 and 0.12 by coincidence of the flat region, and finally -0.382 at 0.10 (0.367 versus 0.749) and -0.687 at 0.07 (0.024 versus 0.711). If — and only if — BLIND7's ŝ drives the P parameters directly, its +13% plateau converts into a slow bleed, and its extreme-scale blowups convert into a rout.
- BLIND3: zero everywhere except the same bonuses as ORA7 (+0.012 at 0.22, +0.066 at 0.15). In this experiment the deployable estimator's end-to-end record is indistinguishable from the labelled bound's.
- BLINDRAW: zero everywhere except s=1.0, where it is catastrophic: F1 0.638, bud recall exactly 0. With ŝ=0.449 the parameters become `min_area=24`, `bloom_area_min=182`, kernel 3; at baseline scale every bud (median 344 px) clears 182 and is classified as a bloom, so all 210 detections come out "bloom" and the score is exactly the bloom share of the scene. This is the largest single end-to-end loss in this article, and it happens at the scale everyone assumes is safe — because at s=1.0 there is no distance problem at all, only a measurement problem nobody checks.

### 3.4 Route selection: 60 estimator-scale decisions, 3 coarse disagreements, and the guard makes BLIND7 whole

Route labels (coarse P-versus-U) disagreed with the oracle in 3 of 60 estimator decisions (4 estimators × 15 scales, guarded variants excluded):

- ORA7 at s=0.30 (ŝ=0.289) and BLIND3 at s=0.30 (ŝ=0.289) choose U where the oracle chooses P. F1 identical (1.000 either way); the cost is compute only — U costs roughly 5–33× the P route per the timing measurements of the 2026-10-24 article (not re-measured here).
- BLIND7 at s=0.28 (ŝ=0.319) chooses P where the oracle chooses U, and runs it with its own parameters: deployed F1 0.983 against 1.000. This is the only route disagreement in the whole table that costs accuracy.

Alert flags tell a separate story: ORA7 and BLIND3 raise a spurious "move closer" alert at s=0.15 (their ŝ fall below 0.15), while BLIND7 misses the alert at s=0.10 and s=0.07 (its inflated ŝ stays above 0.15). Alert errors do not change execution — U runs either way — but a spurious alert costs a truck roll and a missed alert costs a warning, so they belong in the ledger even at ΔF1 = 0.

With the guard and fall-back-to-U rule, BLIND7's deployed F1 equals the oracle-route F1 at all 15 scales: in the refused band it goes U (recovering the s=0.28 loss entirely), where it is not refused (s ≥ 0.35 and 0.12) its estimate is serviceable, and at 0.10/0.07 — where the guard passes a bad number — the bad number still lands on U, so execution is safe even though the alert is missed. Route architecture absorbs what the estimator cannot fix, because U is a safe default: it needs no s at all. The one disaster the guard does *not* absorb is BLINDRAW at s=1.0: its route label agrees with the oracle (P), the guard passes, and the damage arrives through the parameters, not the route — deployed F1 0.638. A separation-only guard has nothing to say about fragmentation, because fragmentation at baseline does not look like two overlapping classes; it looks like one very well separated split between specks and everything else.

Finally, a signal the data offers for free: two independent measurement pipelines agree or they don't. BLIND7 versus BLIND3 ŝ differ by at most 0.4% for s ≥ 0.35, then jump to +17.4% at s=0.30 and stay between +17% and +24% across the whole band where BLIND7 is broken, reaching +80% at 0.10 and +171% at 0.07. Cross-estimator disagreement is large exactly where one of them is lying, and near zero where both are healthy. I record this as a candidate guard derived from this dataset — unlike the pre-registered separation guard, it was not fixed before scoring, so it is presented as a protocol proposal to validate, not as a validated result.

## 4. Analysis and takeaways

1. **The 2026-10-20 estimator proposal survives, with one word changed: measure with a pipeline that keeps both classes alive.** The bias of the estimator family itself is a one-sided underestimate of at most -13% down to s=0.12, and §3.2 shows the downstream absorbs that without loss — at small scales it even gains. But the measurement must not reuse the kernel-7 morphology whose scaling you are trying to calibrate: that version is exact while buds survive (s ≥ 0.35) and then flips to a +13–16% plateau precisely where the kernel starts killing buds. A kernel of 3 for the *measurement* step (the detector itself is untouched) removes the circularity in this experiment, with end-to-end results indistinguishable from the labelled bound.
2. **Err low: apply a fixed 0.9 shrink to the s you use.** In the sweep, s_used = 0.9·s_true never loses to the oracle at any of 15 scales and wins at three; the loss surface is asymmetric because the two failure modes — min-area starvation of buds at small scales, classification-threshold migration at large scales — sit on opposite sides, and the small-scale side is the fragile one in every article of this series. A shrink factor is a crude instrument, but it is free, it is one line, and here it dominates the truth. If you take one number from this article, take that one — bounded to this pipeline family, as §5 insists.
3. **Route selection is robust to estimation error — spend your worry on the parameters, not the route.** Across 60 decisions there was exactly one accuracy-costing route error, and a refused-estimate-falls-back-to-U rule erased it. The reason is structural: U needs no s, so every estimation failure that ends at U is a compute bill, not an accuracy loss. The failures that hurt are the ones that stay on P with wrong parameters (BLIND7 unguarded) or arrive at s=1.0 disguised as "no problem" (BLINDRAW). Alert flags are the weak point of the route layer: spurious and missed alerts both occurred at ΔF1 = 0, invisible to any F1-only monitoring.
4. **Guards need more than one observable, and this bench maps which observable fails where.** Separation catches the mid-band bimodality collapse (6 of 6 refusals correct) and false-refuses twice at the bottom (BLIND3 at 0.10/0.07 — cheap, because refusal falls back to U). It misses fragmentation at baseline (component count 445 versus a calibration expectation of ~210 at comparable density is the observable that *would* have spoken) and it misses sample-size collapse at the extremes (49 and 13 contours). Cross-estimator agreement (§3.4) separates cleanly in this dataset. None of the additional signals beyond separation is validated here; the honest protocol today is: separation guard + fall back to U on refusal + never let a single unguarded ŝ write parameters directly.
5. **Estimator validity windows are complementary, so the field protocol should be a portfolio, not a choice.** Kernel-7 measurement for s ≥ 0.35, kernel-3 measurement as the default across the range, raw-mask measurement as the cross-check for s ≤ 0.65 — with agreement between any two as the acceptance test and U as the default on disagreement. That protocol is assembled from this bench's windows; validating the assembled protocol end-to-end is future work, not a result of this article.

## 5. Limitations and open problems

- Everything is still synthetic: the native small frames are INTER_AREA downscales of clean rendered scenes. There is no sensor aliasing, Bayer demosaicing, lens PSF or read noise. In a real frame the raw mask will be dirtier, fragmentation and merging will occur at different scales, and every validity window reported here will move. The numbers are this pipeline's error chain under pure geometric scaling, not a field accuracy promise.
- Calibration and test scenes come from the same simulator and the same four seeds; the references (3,806 / 3,740 / 3,718.5) and the test frames share a distribution. Per-frame ranges capture sampling variation only, not the distribution shift a real new camera position brings (different cultivar, growth stage, illumination). An estimator validated this way has passed the easy half of the field problem.
- The blind class-finding is one specific choice — 1-D 2-means on log areas with percentile initialisation. A different clustering rule moves the failure boundaries (the largest-log-gap rule, for instance, splits off noise specks first on raw areas). The conclusions about *measurement pipelines* (kernel 7 circularity, raw fragmentation) are statements about the area distributions themselves; the exact scales at which a given clustering rule notices are implementation details.
- The guard threshold (separation ≥ 0.8) was pre-registered, but it was still chosen by me, on this pipeline, with knowledge of the baseline separation (2.40). Its hit/miss record here — mid-band perfect, extremes blind, two false refusals — is one dataset's record, not a characterised detector.
- The 0.9 shrink prescription is an empirical dominance result on 15 scales × 210 objects from one simulator. One or two objects are worth ~0.005 F1 at the extreme scales, and the f-grid is coarse (0.8 and 0.9 both never lose; nothing between 0.9 and 1.0 was probed). Treat 0.9 as "shrink a little, in the direction the drift already points", not as a tuned constant.
- s > 1 (moving closer) remains unmeasured, for estimators as for everything else in this series; the topic pool carries it as a separate item. Fragmentation at s > 1 should, by the logic of §3.1, get worse for every measurement pipeline — a prediction, not a result.
- Route costs cite the previous article's timing ratios (5–33×) from one machine and one OpenCV build; they were not re-measured, and the absolute milliseconds transfer nowhere.

## 6. References

- Bloom-Counter repository (MIT; all code used here): https://github.com/Ezra-Zhao/Bloom-Counter . Detector `detector/color_segmentation.py` (HSV petal mask, morphology pipeline, `min_area` / `bloom_area_min` / `morph_kernel`); simulator `simulator/generate.py`.
- Earlier in this series: "The total is right and the structure is wrong" (2026-10-17, scenes and scoring); "Thresholds are not constants, they are functions of distance" (2026-10-20, area drift, the estimator proposal in §4, the untested-items list in §5); "Upscaling back to full size wins" (2026-10-24, P-versus-U head-to-head, stage decomposition, route rule and timing ratios).
- This experiment: `data/2026-10-25-bloom-s-estimation-bench.py` and `data/2026-10-25-bloom-s-estimation-bench.json` (calibration references; per-scale estimator errors, cluster counts and separations, per-frame estimates; tolerance sweep; end-to-end P results; route selections and guarded variants).
- OpenCV documentation: `resize` and interpolation flags, `connectedComponentsWithStats`, `contourArea`, morphology: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. All code and experiments described here are the author's clean-room work: the detector, the simulator and the estimation bench were written by the author, all experiments ran on locally generated synthetic data, and no customer data, customer images or identifying information are involved.
