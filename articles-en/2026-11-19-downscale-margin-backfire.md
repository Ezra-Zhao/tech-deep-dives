# Forty Percent of Margin, Thirty Percent of Buds: The Zoom-Out Boundary of a Floor-Margin Prescription, Measured

Author: Guangyi Zhao

## 1. Problem and background

The 2026-11-08 article in this series set a prescription for a scaled area floor: min_area = 120·s²·(1+m) with margin m = 0.40. Zooming in (s from 1.0 to 3.0), that margin drove sub-floor clutter leaks to zero at all five scales and cost not a single true bud. That article closed with an explicit limitation: the prescription had only been measured zooming in. Zooming out (s<1), bud contours drift downward, and the same raised floor might eat buds first. This article measures that bill. Three questions: where does the +0.40 margin start to backfire in the zoom-out direction, and how many buds does it eat; conversely, what can a lowered floor (a negative margin) buy back zoomed out, and what does it cost in leaks; and, under a rule frozen before the run, what does the feasible margin band look like scale by scale — can one prescription serve both directions?

Two results surprised me. First, the backfire point is much later than I preregistered: +0.40 stays free all the way down to s=0.4, the cliff opens at s=0.3 (3 buds lost), and at s=0.22 it widens sharply — bud recall falls from the m=0 baseline of 0.9079 to 0.6974, so that cell loses 30.3% of all buds in total, 21.1 points of it eaten by the margin on top of the baseline. Second, I had assumed the baseline losses at s=0.22 were morphological — buds shredded below recognition, beyond any floor's reach. The opposite is true: all 7 lost buds still have intact contours, merely shrunk below the s² line. A negative margin of −0.15 buys 5 of them back at zero leak cost, and −0.25 buys them all. The feasible band does not slide in one direction as s falls; it narrows from both ends — the ceiling collapses below s=0.4, while the floor of the band actually rises above zero at s=0.8/0.5/0.4, because at those scales even m=0 leaks a few square clutter items.

The design was frozen before the run (data/2026-11-19-downscale-margin-prereg.md), with six preregistered predictions and prescription rule D. Section 3.6 settles them one by one: two full hits, three half hits, one miss — and the miss (P4) is the most informative of the six.

## 2. Method

Scenes and clutter are verbatim from the earlier work: the original 4 scenes (seeds 101/202/303/404; 210 targets, 134 blooms and 76 buds), and the 2026-10-30/2026-11-08 clutter planting with the same rng, plan, and placement rules (64 items per scene, 256 in total: 112 true sub-floor, 16 squares of nominal area 121 at r=6, 64 mid-layer, 32 large, 32 blue negative controls). Clutter is planted on the s=1 image and then shrunk with the scene — clutter recedes with everything else, as it would physically.

Three conventions differ from the zoom-in article, each inherited unchanged from the established zoom-out deployment route: shrinking is INTER_AREA to a native small frame (zooming in used INTER_LINEAR enlargement; the interpolation follows the direction's convention); the detector runs the P/A3 route — min_area and bloom_area_min scaled by s², kernel scaled as odd(7s) (the odd approximation of 7s, minimum 3; the exact function of the 2026-10-20 A3 and 2026-10-24 P routes). The zoom-in article held the kernel at 7 because it had proven the kernel is not the binding constraint in that direction; zoomed out, an unscaled kernel kills buds morphologically before any floor matters (the 2026-10-20 A2 arm has bud recall 0 at s=0.22), so it is not a deployable baseline. The margin applies only to min_area: floor = round(120·s²·(1+m)); bloom_area_min = round(900·s²) carries no margin, isolating the variable. Scales {1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.22} are the 2026-10-20 A-group grid verbatim; margins {-0.60, -0.40, -0.25, -0.15, -0.07, 0, 0.07, 0.15, 0.25, 0.40} stop on the positive side at the prescription value 0.40 (the floor is monotone in m, so larger margins can only recall less) and reach −0.60 on the negative side to probe the discount boundary. Every cell runs a clean and a cluttered pass; scoring is the 2026-11-08 evaluate verbatim (label must match, centre-tolerance matching; leftover detections are greedily matched to clutter centres and counted as leaks).

Distribution arm: at each scale, the same pipeline (scaled kernel, m=0 floor) measures every ground-truth target's individual normalised contour area. A posthoc pass re-measures every bud at s=0.3 and s=0.22 against a 1-pixel floor (so sub-floor buds stay visible) and measures the planted r=6 clutter contours in situ.

Rule D, frozen before the run: a margin is feasible at a scale if clean-image bud recall is no worse than the same scale's m=0 cell (the frozen text says "exactly equal", with the parenthetical "no additional loss"; both readings are reported in Section 3.5) and both true-sub-floor and radius-label leak counts on the cluttered image are zero.

One integer-rounding disclosure up front: at s=0.22 the nominal floor is only 5.8, and the margin grid maps to effective floors {2,3,4,5,5,6,6,7,7,8} (the computation is round(120×0.0484×(1+m)): m=-0.15 gives round(4.94)=5, m=+0.40 gives round(8.13)=8) — −0.15 and −0.07 are both 5, 0 and 0.07 are both 6, 0.15 and 0.25 are both 7. Those pairs must tie at that scale; everything below is read by effective floor, not nominal margin.

## 3. Measurements

### 3.1 Distribution: the lower tail drifts down, but slower than the median

| s | bud min (normalised) | p5 | median | missing (m=0) | bloom min |
|---|---|---|---|---|---|
| 1.0 | 242.0 | 247.9 | 343.8 | 0 | 2179.0 |
| 0.8 | 225.8 | 237.3 | 330.1 | 0 | 2188.3 |
| 0.65 | 205.9 | 221.0 | 316.6 | 0 | 2162.1 |
| 0.5 | 198.0 | 203.5 | 295.0 | 0 | 2066.0 |
| 0.4 | 184.4 | 193.7 | 292.1 | 0 | 2046.9 |
| 0.3 | 155.6 | 166.7 | 255.6 | 0 | 1966.7 |
| 0.22 | 124.0 | 124.0 | 206.6 | 7 | 1890.5 |

The median falls from 343.8 to 206.6 at s=0.22 (survivors' basis), matching the 2026-10-20 kernel-7 median drift exactly at s=0.8 (0.960). The lower tail resists better than the median: the min-to-baseline ratio is 0.818 at s=0.5 and 0.643 at s=0.3, against median ratios of 0.858 and 0.743. That is why +0.40 survives to s=0.4 — the normalised floor of 168 meets the min between 0.4 (184.4) and 0.3 (155.6), not at 0.5. The "7 missing" at s=0.22 must be read under the other basis: re-measured against a 1-pixel floor, all 76 buds have a centre-containing contour, the smallest normalised area being 82.6. They did not disintegrate; they shrank whole below the m=0 floor line (normalised 124.0). That fact decides how the negative-margin rescue in Section 3.3 works.

### 3.2 The m=0 replication: checking against the 2026-10-20 A3 arm

m=0 is the zoom-out deployment baseline itself. Clean-image bud recall: 1.000 at s≥0.3 and 0.9079 (69/76) at s=0.22 — the A3 bud figure to the digit. Overall recall at 0.22 is 0.9571 against A3's 0.9619, a one-bloom difference (this run loses 2 blooms, A3 lost 1) from the different scoring implementation (the 2026-11-08 evaluate versus the 2026-10-20 scorer); no scale's verdict depends on it. Those 2 blooms sit at recall 0.9851 under every margin — a floor-independent fixed loss at s=0.22.

### 3.3 The cost curve: the ceiling holds to 0.4, the floor collapses below 0.3

Clean-image bud recall (of 76):

| s | m=-0.60 | -0.40 | -0.25 | -0.15 | -0.07 | 0 | +0.07 | +0.15 | +0.25 | +0.40 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 0.8 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 0.65 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 0.5 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 0.4 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| 0.3 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.9605 |
| 0.22 | 1.000 | 1.000 | 1.000 | 0.9737 | 0.9737 | 0.9079 | 0.9079 | 0.7895 | 0.7895 | 0.6974 |

The positive side has a completely different shape from the zoom-in direction. Zooming in, recall against margin was a flat line (35 of 35 cells perfect). Zooming out, it is a cliff: flat through s=0.4, a single notch at s=0.3 (0.9605, 3 buds, only at the top margin), then a collapse at s=0.22 from +0.15 onward (0.7895 → 0.6974). Per-bud accounting (the 1-pixel-floor re-measurement, computed on raw contour areas) proves the cliff is the floor line itself, exact to the item: at both s=0.3 and s=0.22, in all 10 margin cells, the number of buds whose raw area falls below the effective floor equals the number the detector lost — at s=0.22 the sub-floor counts {0, 0, 0, 2, 2, 7, 7, 16, 16, 23} (m from −0.60 to +0.40) and the loss counts are the same column of numbers. Not one bud slipped through on a neighbouring detection's tolerance claim; the scoring tolerance's share of either ledger in this run is zero. What does exist in bulk is on-the-line items: small contours quantise to half-integer areas, and the seven smallest buds at s=0.22 measure {4.0, 4.0, 5.5, 5.5, 5.5, 5.5, 5.5} raw — collisions with integer floors are the norm, not a coincidence (Section 4, point four).

The negative side is the other ledger, and the most quotable result of the run: the s=0.22 baseline losses (7 buds) are all floor losses (Section 3.1), so lowering the floor buys them back one by one — m=-0.15 (effective floor 5) recovers 5 (0.9737); m=-0.25 and −0.40 (floors 4 and 3) recover all of them (1.000, with overall recall back to 0.9905, only the 2 floor-independent blooms missing). The rescue count reads directly off the area-versus-line positions: at floor 5 only the two 4.0 buds remain below the line (the five 5.5 buds are over it); at floor 4 the two 4.0 buds sit exactly on the line (the detector's >= admits them); below that there is nothing left to rescue — 7 is the entire sub-floor stock. The price is paid in leaks: at m=-0.15 both leak counts are still zero and precision (0.7574) is even a hair above the m=0 value (0.7556); from −0.25 leaks appear (1 true sub-floor, 2 radius-label); at −0.60 (floor 2) the same 7 buds are back but leaks have grown to 15 true and 26 radius-label, with precision down to 0.6361. At s=0.22, −0.15 is a free lunch; every step beyond it trades leaks for recall that has already been fully bought.

### 3.4 The leak side: zoomed out, even m=0 is not clean — the square tail crosses mid-way

In the zoom-in article the m=0 scaled floor was clean on the true-sub-floor basis and leaked squares only at high s. The zoom-out leak ledger (cluttered image, radius-label / true-sub-floor):

| s | m=-0.60 | -0.40 | -0.25 | -0.15 | -0.07 | 0 | from +0.07 |
|---|---|---|---|---|---|---|---|
| 1.0 | 64/48 | 32/16 | 32/16 | 16/0 | 0/0 | 0/0 | 0/0 |
| 0.8 | 60/44 | 34/18 | 20/5 | 15/2 | 1/0 | 1/0 | 0/0 |
| 0.65 | 54/38 | 42/26 | 15/2 | 13/0 | 5/0 | 0/0 | 0/0 |
| 0.5 | 43/27 | 19/4 | 10/2 | 5/0 | 5/0 | 5/0 | 0/0 |
| 0.4 | 43/27 | 22/8 | 19/6 | 7/2 | 5/0 | 1/0 | 0/0 |
| 0.3 | 44/30 | 18/6 | 1/0 | 1/0 | 1/0 | 0/0 | 0/0 |
| 0.22 | 26/15 | 2/1 | 2/1 | 0/0 | 0/0 | 0/0 | 0/0 |

(Denominators: 128 radius-label, 112 true sub-floor.)

Three facts. First, the true-sub-floor count at m=0 is zero at every scale — the baseline floor itself has no true leaks; everything it leaks is one of the nominal-121 r=6 squares. Second, the m=0 square leaks are not zero: 1 at s=0.8, 5 at s=0.5, 1 at s=0.4. In-situ measurement explains them: the r=6 squares' median normalised contour falls with s (109.0 → 86.0 at s=0.5 → 77.8 at s=0.3), but the spread widens from nothing — at s=1 all 16 squares measure exactly 109.0 (max equals median), while shrinking and resampling gives each square its own jitter, putting the max at 121.9 at s=0.8 and 5 items at or above 120.0 at s=0.5, matching the leak counts at those two scales item for item; re-checked on raw areas, the single s=0.4 leak reconciles too — the three scales' leaking squares measure raw 78.0 against a floor of 77, five at exactly 30.0 against 30, and one at exactly 19.0 against 19, all own-contour passes on or over the line (the square sub-floor ledger matches the leak counts at all seven scales; posthoc data file). Circles in the same scenes never reach 120 (median 90.0 → 61.1): what crosses the line is still only squares, and this time not by median drift but by tail widening. Third, negative-margin leaks grow steeply with discount depth and generally shrink as s falls (true leaks at m=-0.60 fall from 48 at s=1 to 15 at s=0.22, with a local uptick at s=0.3), because the clutter contours are shrinking too — the window for a negative margin is wider zoomed out than at s=1, which is exactly why −0.15 is free at s=0.22 but leaks 16 squares at s=1.

Precision is monotone non-decreasing in m at every scale except s=0.22 (0.7574 at −0.15/−0.07, 0.7556 at 0, 0.7471 at +0.15/+0.25, 0.7645 at +0.40): there, raising the floor first kills true buds rather than false detections, and numerator and denominator shrink together. At m=+0.40 precision is 0.7664 for every s in [0.4, 1.0] — the same plateau as zooming in, the remaining false detections being the same 32 r=10 mid-layer and 32 large items that no margin governs, in both directions.

### 3.5 The feasible band: it narrows from both ends, and its lower edge rises above zero

Rule D, scale by scale (the "no worse than m=0" reading; the literal-equality reading changes only the s=0.22 lower edge — see the note):

| s | feasible band | ceiling set by | lower edge set by |
|---|---|---|---|
| 1.0 | [-0.07, +0.40] | grid top (higher untested) | square leaks from −0.15 |
| 0.8 | [+0.07, +0.40] | grid top | m=0 leaks 1 square; a positive margin is required |
| 0.65 | [0, +0.40] | grid top | square leaks from −0.07 |
| 0.5 | [+0.07, +0.40] | grid top | m=0 leaks 5 squares |
| 0.4 | [+0.07, +0.40] | grid top | m=0 leaks 1 square |
| 0.3 | [0, +0.25] | +0.40 eats 3 buds | leaks from −0.07 (1 square) |
| 0.22 | [-0.15, +0.07] | collapse from +0.15 | leaks from −0.25; −0.15 rescues 5 buds for free |

Note: rule D's frozen text asks for recall "exactly equal" to m=0, with the parenthetical "no additional loss". At s=0.22 the negative margins recall *more* than baseline (an improvement, not an additional loss): under the literal reading they are infeasible and the lower edge is 0; under the parenthetical's intent they are feasible and it is −0.15. The ceiling (+0.07) and every other scale are identical under both readings. This article reports the intent reading and logs the wording defect in the limitations.

This table is the answer to the direction question. The band does not translate; it narrows from both ends as s falls, asymmetrically — the ceiling holds until s<0.4, the lower edge rises above zero at the three middle scales (there the baseline floor needs a positive margin to stay clean), then sinks back below zero at s=0.22 (there the baseline starts losing buds and a negative margin turns into a rescue tool). No single number — 0.40, 0, or any negative value — is the prescription at all seven scales.

### 3.6 Preregistration scorecard

P1, full hit: m=0 bud recall is 1.000 at s≥0.3 and 0.9079 at s=0.22, the A3 figure to the digit (the one-bloom overall difference is in Section 3.2). P2, full hit: the s=0.5 bud min is 198.0, inside [150, 210]; the s=0.3 survivors' min (124.0) is still above 120; the min crosses 168 between s=0.4 and 0.3, inside the preregistered interval [0.3, 0.65]. P3, half hit: +0.40 is indeed free at s≥0.8 — and stays free to 0.4 — but the first cost lands at s=0.3, not the preregistered 0.5, and recall there (0.9605) sits just above the ≤0.95 I bet on; the backfire is real and steepens with falling s, one scale later than registered. P4, miss: at s=0.22, m=-0.40 recovers all 7 baseline-lost buds against a bet of at most 3. My error was attributing the baseline losses to morphology and fragmentation; the 1-pixel-floor re-measurement shows all 7 buds with intact contours, shrunk below the line — that cliff was a floor cliff from the start, and the loss composition of the 2026-10-20 A3 arm should be re-read accordingly. P5, half hit: the m=-0.40 leak at s=1 (32 radius-label against a bet of ≥12, plus 16 true) and the general decline of leaks with falling s both land; the main clause misses — m≥-0.15 is not leak-free (−0.15 leaks 16 squares at s=1), and m=0 itself leaks squares at three scales, neither of which was in the preregistered picture. P6, half hit: the s=1 ceiling of 0.40 lands and the "directions need separate prescriptions" conclusion stands, but the boundary is not at 0.5 (the ceiling is still 0.40 at s=0.4), the ceilings at s≤0.3 are 0.25/0.07 rather than the ≤0 I bet on, and the lower edge rising above zero was entirely outside the registration.

## 4. Analysis and trade-offs

First, rewrite the prescription as a band indexed by s, not a number. At s≥0.4 the zoom-in prescription carries over unchanged: min_area = 168·s² is leak-free and cost-free on both sides of s=1, so across the two articles the verified domain of +0.40 is now s in [0.4, 3.0]. At s=0.3 the ceiling drops to +0.25. At s=0.22 the band is [-0.15, +0.07], with −0.15 its best point (5 of 7 baseline losses recovered, zero leaks, precision undamaged). In deployment this is a small (s, m) lookup table; s is a quantity this pipeline already estimates (the estimators of 2026-10-25), so no new machinery is needed.

Second, the instinct "zoomed out, lower the floor to save recall" holds only at the deepest scale, and for a different reason than usually assumed. From s=0.3 to 1.0 baseline bud recall is already perfect; a negative margin has nothing to rescue and only leaks to pay (at s=1, −0.15 already leaks 16 squares). A discount becomes a rescue only when the baseline itself is losing buds *and* those losses are proven, item by item, to be floor losses. Establish the loss composition before touching the floor — P4's error was skipping that step. A cliff's cause cannot be guessed from the recall number; the lost targets' contours have to be measured (the 1-pixel-floor re-measurement is the ready-made tool).

Third, square clutter bounds the margin band in both directions, by different mechanisms: zooming in, median drift (the whole square population's contours grow +24%); zooming out, tail widening (the median falls while the max crosses the baseline). Sizing a clutter band from nominal areas or median drift systematically understates it in the zoom-out direction; the band must be set by the worst shape's upper tail. This sharpens the fourth conclusion of 2026-11-08: the "drift band" is an upper-tail quantity, not a median one.

Fourth, at small scales contour areas are quantised, and on-the-line items are the norm rather than a coincidence. Bud raw areas at s=0.22 arrive in runs of 4.0/5.5/6.0/7.0; the squares' maximum at s=0.5 is exactly 30.0 and at s=0.4 exactly 19.0. Every m=0 square leak in this run and every bud loss at s=0.22 is explained item by item by an own-contour area against the floor, and a substantial share of those targets sit exactly on the floor, admitted or excluded by the detector's >= convention. The floor's rounding rule (round versus floor, a nominal difference of one pixel) is therefore not an implementation detail at small s but a real parameter that flips several targets; the s=0.22 band being only three integer floors wide is partly this effect. The same accounting also settles a methodological worry I brought into the run: the scoring tolerance at s=0.22 is 8.4 pixels, comparable to a bud's diameter, and I expected it to claim a share of sub-floor targets off-ledger — its measured share is zero; the ledger needs no such pocket.

## 5. Limitations and open problems

- The band is measured only down to s=0.22, where it has already narrowed to three effective integer floors (5/6/7). Whether it closes entirely at s=0.15/0.10 (ceiling below the lower edge, no feasible margin) is unmeasured and is now in the topic pool.
- Rule D's recall clause is worded defectively ("exactly equal" versus the parenthetical intent); the s=0.22 lower edge depends on the reading. Both readings are reported; the ceiling and all other scales do not.
- The square tail-widening mechanism is not isolated: the shares of INTER_AREA block averaging and the shrinking kernel (7→5→3) are not separated; Section 3.4 offers only the explanation compatible with the data (zero spread at s=1, spread appearing under shrinking).
- The zoom-out route scales its kernel while the zoom-in article held it at 7; the two margin numbers are valid on their own deployment baselines. The "+0.40 domain [0.4, 3.0]" is a splice of the two baselines, verified to coincide exactly at s=1 (same kernel, same parameters), but any other detector must re-measure rather than inherit it.
- The bud lower tail's hard floor still comes from the simulator's radius minimum (r≥11); a real field's bud tail is a continuous distribution and the backfire scale will move with it. What transfers is the lookup-table method and the loss-composition check, not the numbers 0.4/0.3/0.22.
- At s=0.22 the effective floors are single-digit and the nominal margins map to them inconsistently (Section 2), so that scale's conclusions are stated by effective floor; and most of that scale's targets are decided by on-the-line cases (Section 4, point four), whose composition will differ under a new seed batch — the s=0.22 band edges (the −0.15 lower edge in particular) should be quoted at a granularity of ±1 integer floor.

## 6. References

- Earlier in this series: "The Floor Plus Forty Percent, and Not One Bud Harmed" (2026-11-08; the +0.40 prescription and the unmeasured zoom-out limitation this article settles), "Thresholds Are Not Constants, They Are Functions of Distance" (2026-10-20; the A3 baseline and bud drift), "Zoom In Threefold, and the Floor Leaks a Whole Layer" (2026-10-30; the original clutter planting and the ±7% drift band), "Zooming In Turned Out Simpler" (2026-10-26) — same scenes, seeds, and planting conventions throughout.
- This round's preregistration, scripts, and raw data: data/2026-11-19-downscale-margin-prereg.md (frozen before the run, including rule D), data/2026-11-19-downscale-margin-bench.py, data/2026-11-19-downscale-margin-bench.json (distribution plus the full 7-scale × 10-margin grid), data/2026-11-19-downscale-margin-posthoc.py and data/2026-11-19-downscale-margin-posthoc.json (rule-D bands under both readings, per-bud raw-area accounting exact at every cell, r=6 square raw-area accounting, precision monotonicity).
- Bloom-Counter repository (MIT; detector and simulator): https://github.com/Ezra-Zhao/Bloom-Counter . Detector: detector/color_segmentation.py; simulator: simulator/generate.py (bud radii sampled 11–17, blooms 30–50).
- OpenCV documentation: resize and INTER_AREA, morphologyEx, findContours and contourArea: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. The code and experiments described here are the author's own clean-room work: the detector, simulator, clutter planting, and measurement scripts were all written by the author, and the experiments were run on locally generated synthetic data. No client data, client images, or identifiable information is involved.
