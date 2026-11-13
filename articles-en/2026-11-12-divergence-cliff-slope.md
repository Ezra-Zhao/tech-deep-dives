# Half the Middle Band Is Genuinely Bad: Six Pooled Sets Measured — Whether Divergence Falls Off a Cliff or a Slope Is Decided by Failure Magnitude, Not Composition

Author: Guangyi Zhao
Date: 2026-11-12
Subject: Bloom-Counter (my own open-source project), BLIND7/BLIND3 scale estimators and the two-tier divergence guard frozen on 2026-11-04
Environment: Linux x86_64 VM, synthetic scenes generated locally, estimators computed in-process. All data is simulated; the article says so wherever it matters.

## 1. Problem and background

A two-tier divergence guard has one unresolved question. In my 2026-11-04 test I split the divergence between the BLIND7 and BLIND3 estimators into three tiers: at most 2% passes (GREEN), 2% to 15% is borderline (AMBER), above 15% rejects (RED). Across three earlier datasets, pooled AMBER occupancy was 0, 7, 0 — the same grading had an empty middle band on one dataset and nearly half the points in it on another. Whether a two-tier guard has a middle tier worth building depends on one thing: when divergence moves from the healthy band to the failure band, is the transition a cliff or a slope? And what decides which one you get was left open, with two candidate factors: the scene composition of the pool and its target density.

This article manipulates both factors. The design was frozen before any run (data/2026-11-12-divergence-cliff-prereg.md): three arms, two independent pools each, four new scenes per pool, 15 scale steps s. The HD arm replicates the earlier composition (about 54 targets per scene, buds about 36%); the LD arm cuts each scene to 14 targets (9 blooms, 5 buds); the MIX arm mixes four compositions in one pool (standard, bud-heavy, bloom-heavy, low-density; bud share from about 10% to 67%). Six predictions were frozen with the preregistration and are scored in the text.

The headline, against my preregistered intuition: mixing composition does not create a slope. One MIX pool is a textbook cliff; the other pool's slope is made of six AMBER points that are all good, and at bad onset its divergence jumps straight from 9.54% to 160.45%. What actually decides what lands in the middle band is failure magnitude. The harder BLIND7 overshoots in its failure band, the more its bad points land in RED; when the overshoot is only 11% to 13% (the low-density pool), the bad points lie entirely in AMBER and the pool has no RED at all. Section 4 turns this into a pre-check a practitioner can run before choosing a guard design.

## 2. Method

- Estimators and definitions are carried over unchanged: BLIND7 (kernel-7 morphology, blind 2-means upper-cluster median, reference 3806.0) and BLIND3 (kernel 3, reference 3740.0); divergence div = BLIND7 / BLIND3 − 1; BAD means BLIND7 relative error above 10%; tier lines are the 2% and 15% frozen on 2026-11-04.
- Scenes were generated with new seeds (2111 to 4818, unused in any earlier article). Actual placed targets, by generator ground truth: HD pools 209 and 211 targets, LD pools 56 each, MIX pools 180 each; nominal and actual counts agreed per scene, no placement losses.
- Sharpness measures (frozen): per pool, AMBER occupancy, transition steps (positions between the last GREEN and the first RED point as s descends), separation gap (smallest bad |div| minus largest good |div|), and the spread of per-scene first-bad scales.
- This run measures divergence sharpness only, not end-to-end deployment F1: the 2026-11-04 test already showed two-tier and single-tier deployment losses are indistinguishable on this bench, so no deployment benefit is claimed here.
- Memory discipline: scenes were loaded one at a time and only contour-area tables retained; pooled estimates merge the four scenes' area tables. Per-scene and pooled points come from the same run, not two experiments.

## 3. Measurements

### 3.1 The six pools

| Pool | Composition | AMBER | RED | Bad | Transition steps | Separation gap (pp) | First-bad spread (steps) |
|---|---|---|---|---|---|---|---|
| HD1 | standard, 209 targets | 2 | 7 | 9 | 1 | +11.38 | 4 |
| HD2 | standard, 211 targets | 1 | 8 | 9 | 1 | +4.68 | 1 |
| LD1 | low density, 56 targets | 8 | 0 | 4 | undefined (no RED) | +1.63 | 5 |
| LD2 | low density, 56 targets | 1 | 5 | 4 | 1 | +2.03 | 6 |
| MIX1 | mixed, 180 targets | 0 | 9 | 9 | 1 | +17.28 | 1 |
| MIX2 | mixed, 180 targets | 6 | 3 | 3 | 7 | +139.81 | 7 |

Of 88 estimable pooled points (plus 2 NOEST, both at s=0.07 in the LD pools): 38 GREEN, 18 AMBER, 32 RED. The 38 bad points split as 0 in GREEN, 7 in AMBER, 31 in RED. A single-threshold CONS rule (reject when |div| exceeds 5%) catches all 38 bad pooled points, sensitivity 1.0 — every pool's separation gap is positive, the narrowest being LD1 at +1.63 points. At the 5% line, all six pools are separable; the cliff-versus-slope argument is entirely about where the 15% RED line sits.

### 3.2 HD: a one-step transition, but the RED line cuts the cliff face

Both HD pools transition in one step, and their largest good divergence is 0.54% — the cliff shape from the earlier datasets replicates. But AMBER is not the zero I preregistered: HD1 has 2, HD2 has 1, and all three are bad points (divergences 14.99%, 11.86%, 5.22%). In HD1, the bad point at s=0.30 has divergence 15.15% and lands in RED, while the bad point at s=0.28 has 14.99% and lands in AMBER — the same failure band, split by 0.16 points. The 15% line cuts the lower edge of the HD failure band's front section (bad divergences there start at 5.22%), so tier assignment is extremely sensitive to exactly where the line is drawn. The middle band is not holding borderline cases; the line was drawn across the cliff face.

### 3.3 LD: failure magnitude shrinks, and the bad points lie down inside AMBER

LD1 is the only pool with no RED at all. Its four bad points (s=0.30 to 0.22) carry divergences of only 7.09% to 7.87%, and together with four good points they fill AMBER to 8 of 14 estimable points (57.1%). The failure itself is smaller: BLIND7 error on those four steps is only +10.88% to +12.83%, just over the BAD line, against +15.64% to +18.84% error and 15.15% to 19.51% divergence for the HD pools on the same four steps. Why low density fails more gently is not isolated by this design; one explanation consistent with the data, labeled unproven: with only five buds per scene, the bud contours killed by kernel 7 perturb the upper-cluster median less, and the 2-means split of the bloom cluster weakens with it. LD2 has the opposite shape — bad divergences of 19.1% to 19.6%, neatly in RED, with a single good AMBER point (s=0.15, divergence 13.08%, error +3.73%). Same density, two failure magnitudes: density is a directional clue, not a sufficient determinant.

The LD arm's heavier bill is in the per-scene view. Scenes 3313 and 3414 are bad from s=1.0 onward (BLIND7 error +15.31% and +11.93%), holding +10.60% to +15.89% across the whole s ≥ 0.35 range — while their divergences sit between −0.76% and +3.84%, with 11 of 12 points in GREEN and one in AMBER. Both estimators read the same contours through the same upper-median principle, so when a scene's own bloom-area median deviates from the calibration reference, they deviate together and divergence sees nothing. Pooling dilutes this scene-level bias (LD1 pooled at s=1.0 errs +6.99%, under the BAD line), which is why the pooled GREEN band's 38 points with zero bad are real; but per-scene GREEN holds 21 bad points in 154, 19 of them from the two LD pools. The first cost of low density is not noisier divergence — it is larger per-scene calibration sampling error, of a kind no divergence guard can see.

### 3.4 MIX: mixing builds no slope; the slope is good points drifting early

MIX1 refutes the preregistered intuition directly. Bud share inside the pool runs from about 10% to 67%, yet AMBER occupancy is 0, all nine bad points are in RED (divergence 17.87% to 142.25%), the largest good divergence is 0.59%, and the separation gap of +17.28 points is the second widest of the six pools. The four sub-scenes' first-bad spread is a single step (three scenes at 0.30, the low-density scene at 0.35): failure timing is set by the global s and kernel size, not by each scene's bud share, so there is nothing for mixing to desynchronize.

MIX2 looks different, but on inspection its slope is not the preregistered kind either. Its six AMBER points (s=0.30 to 0.15, divergence 5.65% to 9.54%) are all good (error +3.07% to +8.00%) — a pre-failure drift band. The actual bad points arrive at s=0.12 with divergences of 160.45%, 149.35%, and 268.25%: onset itself is still a cliff, with a sloping apron of good points in front of it. The pool's first-bad spread of 7 steps combines two unrelated events — the bloom-heavy scene 4717 jumping at s=0.12 (error +143.25%) and the standard scene 4515 crossing marginally at s=0.35 (error +10.57%) — and reports them as one number.

### 3.5 Preregistration scorecard

P1 (both HD pools AMBER 0, transition at most 1 step): half hit — transitions are 1 step each, but AMBER is 2 and 1, all bad (Section 3.2: the RED line cuts the cliff face). P2 (LD pools at least 2 AMBER in total, and LD healthy-band maximum divergence above HD): numerically hit (9 AMBER; healthy maxima 0.58% vs 0.54%), mechanistically missed — a 0.04-point difference is meaningless, healthy-band divergence was not raised by noise at all; the LD AMBER points come from shrunken failure magnitude, and the text scores it as a mechanism miss. P3 (MIX at least 2 AMBER and more than HD): numerically hit (6 vs 3), mechanistically missed — MIX2's AMBER points are good-point pre-drift, not desynchronized sub-population failures (MIX1's first-bad spread is 1 step). P4 (per-scene AMBER share above pooled): hit — 26.81% (85/317) vs 20.45% (18/88). P5 (some MIX pool spread at least 2 steps, both HD pools at most 1): missed — MIX2's spread is 7 steps, but HD1's is 4 steps, because scene 2313 produces a marginal bad point at s=0.65 (error +10.35%), returns to good at 0.5 and 0.4, and only fails for good from 0.30; the first-bad metric cannot distinguish that from desynchronization, as Section 3.4 shows for the same metric in MIX2. P6 (single-threshold CONS catches every pooled bad point): hit — 38/38.

## 4. Analysis and trade-offs

Ranked by strength of evidence, what decides cliff versus slope is: first, failure magnitude — how far BLIND7 overshoots in its failure band decides whether bad points land in RED or AMBER, and the LD1-versus-HD contrast on identical scale steps is the cleanest evidence in this run. Second, pre-onset drift of good points — MIX2's AMBER band is entirely this, a warning zone rather than a borderline-bad zone. Composition mixing and density sit behind both: mixing does nothing in MIX1, and density acts only indirectly, through failure magnitude and per-scene calibration sampling error. One counter-intuitive note: every pool's separation gap is positive, and read pool by pool the 5% line separates good from bad everywhere — the cliff/slope debate was only ever about the placement of the 15% RED line.

The pre-check for choosing a guard design (this run's deliverable): measure three things on a validation pool before fixing tiers. First, the smallest bad divergence: if it is under 15% — in this run 7 of 38 bad points are, the lowest at 5.22% — the RED tier cannot serve as the rejection line; use the 5% single threshold to reject, and treat AMBER as a rescue trigger (re-estimate with BLIND3; on LD1's four AMBER bad points BLIND3 errs only about +5%, so rescue has support). Second, AMBER's makeup: bad and good points mix there (7 bad, 11 good here), so AMBER can neither pass nor be rejected wholesale — it is the tier that needs a second measurement principle, which connects to the known-size marker guard of my 2026-11-06 test. Third, the deployment granularity: per-scene GREEN hides bad points (21/154), and no amount of tier refinement fixes common-mode scene bias; per-scene deployment needs a calibration-class signal such as a known-size reference, not a divergence tier.

Two things I deliberately did not do: redraw the RED line on this run's data (say, to 10%) and re-report — that is exactly the post-hoc line-moving the preregistration forbids; a new line needs this run as prior and a fresh dataset to validate. And I did not promote the shrunken-LD1-failure mechanism to a conclusion; isolating it needs an experiment that manipulates absolute bud count and bud share separately, now queued in the topic pool.

## 5. Limitations and open problems

- Two pools per arm: between-pool differences (LD1 vs LD2, MIX1 vs MIX2) are the same size as between-arm differences. The conclusions hold at the level of magnitudes and shapes — which points land in AMBER, where the line cuts — not as statistical tests of arm means. A quantitative density effect needs at least five pools per arm.
- The mechanism behind LD1's shrunken failure is unisolated: absolute bud count (5), bud share, and total contour count co-vary in this design, and Section 3.3's explanation is only one account consistent with the data.
- The first-bad spread metric is polluted by two event types — marginal non-monotone crossings (scene 2313) and extreme jumps (scene 4717) both produce large spreads. It is weakened as desynchronization evidence by this run's own data; future work should define onset as two consecutive BAD steps.
- The cause of MIX2's good-point pre-drift (six steps at 5.65% to 9.54% divergence) is unchecked: this run shows co-occurrence with the extreme onset at s=0.12, not a mechanism or a causal order.
- The size distribution of per-scene calibration sampling error (scenes 3313/3414 off by +12% to +15% already at s=1.0) is unmeasured: how many bloom samples keep a scene median within 5% is the next bill to pay before the LD findings become a deployment threshold.
- All evidence is still this simulator's portrait: the generator's radius distributions, the upper-median principle, and kernel morphology all come from one Bloom-Counter bench; the magnitudes do not transfer to other estimator pairs.

## 6. References

1. Earlier work in this series: Guangyi Zhao, "The Middle Band Is Empty: A Two-Tier Divergence Guard, Measured" (2026-11-04) — the 2%/15% tier lines, the 0/7/0 AMBER occupancy across three datasets, and the origin of this run's question; "Divergence From 0.4% to 170%: A Multi-Estimator Consistency Guard, Measured" (2026-10-29) — origin of the CONS 5% line and the BAD definition; "Three Votes, Take the Middle" (2026-11-05) and the known-size marker guard test (2026-11-06) — common-mode blindness, joining the third pre-check in Section 4.
2. Test context: the Bloom-Counter repository's simulator/generate.py (scene generation and ground truth) and detector/color_segmentation.py's _petal_mask (the morphology the areas come from); BLIND7/BLIND3 estimation code carried over from the 2026-10-25 bench (blind_cluster, estimate_from_areas), references 3806.0/3740.0 unchanged.
3. This run's data (archived under data/ in the project and mirrored into the tech-deep-dives repository): 2026-11-12-divergence-cliff-prereg.md (preregistration: arm compositions, seeds, sharpness measures, P1 to P6), 2026-11-12-divergence-cliff-bench.py (bench script), 2026-11-12-divergence-cliff-bench.json and its progress.jsonl (full pooled and per-scene points for all six pools), 2026-11-12-divergence-cliff-posthoc.py and 2026-11-12-divergence-cliff-posthoc.json (per-pool AMBER/RED detail, healthy-band maxima, prediction verdicts).

---

Author: Guangyi Zhao. The experiment design, code, and data in this article are clean-room work of my own: the scene generator, detector, estimators, and analysis scripts are my own project and hand-written code, the experiment ran only on my own machine, and it involves no client information and no third-party systems.
