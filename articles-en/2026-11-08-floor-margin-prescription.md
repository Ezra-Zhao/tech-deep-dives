# A 40% Margin on the Floor, Zero Buds Harmed: Measuring a Prescription for the Scaled min_area

Author: Guangyi Zhao

## 1. Problem and background

The 2026-10-30 article in this series established that when you move closer (scale s > 1), min_area must scale with s² or an entire layer of sub-floor clutter walks through. It also found that a scaled floor does not hold a line but a band: clutter whose nominal area sits within about ±7% of the floor still leaks, carried over by positive contour-area drift. That article deliberately stopped short of a prescription — raising the floor by a margin would compress the band, but whether the same margin would eat true buds whose contour areas live at the low end was unmeasured. This article measures that trade-off. Three quantities: where the low end of the bud contour-area distribution actually sits and how much it overlaps the ±7% drift band; how sub-floor leaks and true-bud recall move as the floor is raised by different margins; and which margin a rule frozen before the run finally selects.

The surprise up front: the binding constraint is neither the buds nor the round clutter — it is the square clutter. On the bud side there is room to spare: across 224 buds the smallest contour area is 242.0, more than twice the floor of 120, and the overlap between the bud distribution and the ±7% drift band [111.6, 128.4] is exactly zero. The stubborn cases are 16 squares whose edge rounding gives them a nominal area of 121: after upscaling, their normalised contour areas rise to a median of 129–137 with a maximum of 153, and they keep leaking until the margin reaches 0.40. True-bud recall, meanwhile, did not drop in any of the 35 (scale, margin) cells — not even at a margin of 1.00 (floor doubled to 240), although that cell survives only 2.0 area units below the smallest bud, 242, which is in-sample luck, not a prescribable setting.

The design was frozen before the run (data/2026-11-08-floor-margin-prereg.md), with six registered predictions and one prescription rule. The scorecard: three predictions fully right, three half right; the most informative miss is the prescription point itself (I bet 0.15; the data said 0.40, and the difference is the squares).

## 2. Method

Distribution part: 12 scene sets — the original 4 (seeds 101/202/303/404, 210 targets) plus two holdouts (505/606/707/808, 203 targets; 909/1010/1111/1212, 209 targets), 622 targets and 224 buds in total. At s=1, each ground-truth target's standalone contour area is measured through the detector's own pipeline (petal mask → closing 7 → opening 7 → contours; the contour must contain the target centre and be at least 120). On the original 4 sets I also measured normalised areas (contour area divided by s²) at s ∈ {1.5, 2.0, 2.5, 3.0} to watch the bud lower tail drift.

Cost-curve part: the original 4 scenes with clutter planted exactly as in 2026-10-30 (same RNG, same planting plan, same placement rules): 256 items — 112 true sub-floor items (nominal area < 120), 16 r=6 squares of nominal area 121, 64 mid-layer, 32 large, and 32 blue negative controls. Pure geometric upscale (INTER_LINEAR, canvas grows with the image), s ∈ {1.0, 1.5, 2.0, 2.5, 3.0}; margin m ∈ {0, 0.07, 0.15, 0.25, 0.40, 0.60, 1.00} with floor = 120·s²·(1+m); the classification threshold bloom_area_min = 900·s² carries no margin (variable isolation); kernel fixed at 7 (2026-10-30 showed the kernel is not the binding constraint). Each cell runs clean and planted images: clean images give true-bud recall; on planted images, detections are matched to ground truth first and the remainder greedily to clutter centres, as throughout the series.

The prescription rule, frozen in advance: the recommended margin is the smallest m for which radius-label sub-floor leaks (128 items) are zero at every scale and bud-recall loss is zero; report its headroom ratio against the smallest bud contour.

## 3. Measurements

### 3.1 The bud lower tail: twice the floor, zero band overlap

| Scene set | Buds | min | p5 | p25 | median | p75 | max |
|---|---|---|---|---|---|---|---|
| Original 4 | 76 | 242.0 | 247.9 | 276.9 | 343.8 | 436.5 | 499.5 |
| Holdout 1 | 72 | 242.5 | 255.5 | 277.8 | 347.5 | 448.1 | 492.5 |
| Holdout 2 | 76 | 246.0 | 250.9 | 281.4 | 369.8 | 457.9 | 499.5 |
| Pooled | 224 | 242.0 | 250.6 | 278.5 | 347.5 | 451.6 | 499.5 |

The three scene sets' bud minima cluster in a narrow 242.0–246.0 band — not one lucky draw. No pooled bud falls below 240, and none falls inside the ±7% drift band [111.6, 128.4]: the overlap is 0/224. Blooms start at 2179.0 and are not part of this discussion. The shape has a structural cause: the simulator's bud radius floor is 11, a nominal area of 380, and morphology trims the contour to about 242 — that is this pipeline's physical floor for a bud, separated from min_area=120 by more than a factor of two. The 2026-10-30 worry, that a margin would injure buds in the same band, has no buds in the band to injure — on this pipeline.

The lower tail also drifts in the helpful direction: the normalised bud minimum on the original sets rises from 242.0 at s=1 to 254.7, 259.0, 262.9 and 266.4 at s=1.5/2.0/2.5/3.0 (+10.1%). The zoom-in area drift pushes the smallest buds away from the floor, so the margin's safety headroom widens with s instead of narrowing.

### 3.2 Zero-margin replication against the 2026-10-30 arm

m=0 is exactly the 2026-10-30 scaled-floor arm. True sub-floor leaks replicate cell for cell: 0 at s=1 and 1.5, then 2 at each of s=2.0/2.5/3.0 (the same r=6 circles, nominal 113.1). Radius-label leaks (squares included) read 0, 16, 18, 18, 17 across the five scales — one square fewer than the earlier 18 at s=3.0 only, from my rewritten matching implementation; recorded as a replication difference of 1, immaterial to every conclusion.

### 3.3 The margin cost curve: circles clear at 0.07, squares hold out to 0.40

The true sub-floor side (112 items) is clean: from m=0.07 upward, leaks are zero at every scale. The arithmetic from the preregistration holds — a nominal-113.1 circle needs +13.7% drift to clear a floor raised 7% (normalised 128.4), while the measured normalised contour areas of round clutter top out at 123.8 (Section 3.4).

The squares (16 items) are a different story:

| s | m=0 | m=0.07 | m=0.15 | m=0.25 | m=0.40 |
|---|---|---|---|---|---|
| 1.5 | 16 | 8 | 6 | 0 | 0 |
| 2.0 | 16 | 16 | 1 | 1 | 0 |
| 2.5 | 16 | 16 | 6 | 1 | 0 |
| 3.0 | 15 | 15 | 4 | 4 | 0 |

(At s=1 all margins leak 0.) Square leaks do not decline smoothly; they linger through 0.15–0.25 and break only at 0.40. Total radius-label leaks therefore reach zero at every scale only at m=0.40; under the frozen rule the candidate set is {0.40, 0.60, 1.00} and the prescription takes the smallest: 0.40.

The recall side never pays: bud recall is 1.000 in all 35 (s, m) cells, on clean and planted images alike. Even m=1.00 loses nothing — but that cell deserves immediate cold water. Its normalised floor is 240 and the smallest bud at s=1 is 242.0, a gap of 2.0 (0.8%). It survived because this sample's minimum happened not to probe below 240; another seed set or a real camera would start eating buds at that margin. The prescription does not take it — not because it lost anything this time, but because it stands one step from the cliff.

Precision, for the record: on planted images it is monotonically non-decreasing in m at every scale (verified posthoc), rising from 0.686/0.652/0.648/0.648/0.648 at m=0 (s=1→3) to 0.766/0.764/0.761/0.755/0.755 at m=0.40, then pinning at 0.7664 from m=0.60 on. The remaining 64 false positives are all r=10 mid-layer (32) and large (32) clutter — the area filter's standing cost, which no margin can touch (2026-10-30, Section 3.1).

### 3.4 Mechanism: square contours grow faster than round ones under scaling

A posthoc isolation measured the normalised contour areas of the r=6 and r=7 clutter in situ (same pipeline, contour containing each item's centre):

| Item | s=1 median | s=1.5 | s=2.0 | s=2.5 | s=3.0 median (max) |
|---|---|---|---|---|---|
| r=6 circle (nominal 113.1) | 90.0 | 104.2 | 109.9 | 110.2 | 108.0 (123.8) |
| r=6 square (nominal 121) | 109.0 | 128.3 | 129.2 | 136.9 | 135.0 (153.2 at s=2) |
| r=7 circle (nominal 153.9) | 124.0 | 144.2 | 150.2 | 152.1 | 154.3 (161.8) |
| r=7 square (nominal 176) | 132.0 | 155.1 | 154.1 | 161.9 | 159.1 (176.4) |

Two facts carry the argument. First, every item's s=1 contour area is well below its nominal area (90 vs 113 for circles, 109 vs 121 for squares) — the opening operation trims a fifth before anything scales. Anyone who budgets a margin from nominal areas miscomputes the band on the first step. Second, squares' normalised contours grow more under scaling than circles': the square median rises from 109 to 135 (+24%), its maximum reaches 153.2 (+26.6% over nominal), while the circle median rises from 90 to 108 (+20%) and its maximum, 123.8, is only +9.5% over nominal. Prediction P4 assumed squares share the circles' drift band and would clear at 0.15; in reality the whole square group sits at 128–137, not just a tail. Interpolation bleeding at straight edges and corners plus closing fill is the explanation consistent with the data, but I did not separate the interpolation and morphology shares — recorded as unisolated. The actionable conclusion does not depend on it: set the margin from the worst shape's effective contour band, not from nominal areas.

The mid layer marks the margin's other boundary. At s=1 the r=7 contours are only 124 (circle) and 132 (square), so m=0.07 (floor 128.4) already kills the circles and m=0.15 (138) the squares; at s≥2 they drift above 150 and mostly survive until 0.25, clearing fully only at m=1.00. The r=10 items (nominal 314) pass at every margin. So a margin also sweeps some above-floor small clutter — pure profit here, since all of it is false positives. But in a deployment where legitimate small targets live between the floor and twice the floor, that stretch is exactly where a margin costs recall; measure your own distribution before borrowing 0.40.

### 3.5 Preregistration scorecard

P1 fully right: band overlap 0/224; holdout bud minima 242.5 and 246.0, both above 200. P2 fully right and stronger than predicted: recall 1.000 through m=0.60, and the m=1.00 loss was also 0 (predicted ≤3) — with the Section 3.3 caveat that zero loss is not the same as safe. P3 fully right: zero-margin true sub-floor leaks 0/0/2/2/2, a cell-for-cell replication. P4 half right: true sub-floor items clear at m=0.07 exactly as predicted; the square half missed — predicted single-digit leaks at 0.07 and zero at 0.15, measured 16/16 and 15/16 at s≥2 under 0.07 and full clearance only at 0.40, because the squares' drift band was estimated from nominal areas (Section 3.4). P5 half right: r=10 passes everywhere and r=7 clears fully at m=1.00, both as predicted; in between, r=7 starts falling at m=0.07 at s=1 (its s=1 contours are 124–132, far below the nominal 153.9), much earlier than the predicted 0.25, yet at high scales it lingers past 0.40. P6 half right: precision monotonicity held at all five scales; the smallest fully-clearing margin is 0.40, not the predicted 0.15. At that margin the normalised floor is 168 and the smallest bud, 242, is 1.44× it (266.4 vs 168, 1.59×, at s=3) — headroom is still thick.

## 4. Analysis and trade-offs

First, the prescription: add a 40% margin to the scaled floor — min_area = 168·s² for a base of 120. Across five scales it takes radius-label sub-floor leaks from 16–18 to 0, costs no bud recall at all, and lifts precision by 8.0–11.3 points as a side effect (part of that from sweeping r=7 small clutter). The frozen rule picks the smallest qualifying margin; 0.60 and 1.00 add no leak reduction on this bench while stepping toward the bud tail — at 1.00 only 0.8% separates floor from the smallest bud, which trades a steady state for luck.

Second, the transferable part is a rule, not the number: the margin ceiling is (smallest legitimate target's contour area ÷ floor − 1), here 242/120 − 1 ≈ 1.02, and the prescription uses under 40% of that ceiling, leaving the rest for unseen seeds, viewpoints and textures. Any deployment should measure its own smallest-target lower tail before setting a margin. The 0.40 figure is valid for distributions whose lower tail sits about twice the floor away — the measurement method is what travels.

Third, nominal areas are unreliable accounts. Clutter contours at s=1 run about 20% below nominal (morphology), then diverge by shape under scaling (squares outgrow circles). The 16 "121 squares" that 2026-10-30 filed as a labelling artefact turn out to be neither a mere label error nor the circles' siblings: their effective contour band is its own tier. Whenever items or targets are stratified by nominal area, re-measure effective areas through the pipeline first, then talk about bands and margins.

Fourth, the drift band must be split by shape. The "about ±7%" band of 2026-10-30 was the band for round clutter and buds; squares' effective band reaches +26.6%. Deployment clutter shapes are uncontrolled (fallen petals are near-round; label fragments are polygonal), so sizing the margin to the widest shape band is the conservative and correct default. If a scene is known to hold only near-round clutter, 0.07 already suffices and 0.40 is an insurance premium paid for shape uncertainty — free on this pipeline (zero recall cost), but a real cost on any pipeline whose lower tail hugs the floor, where it must be re-priced.

## 5. Limitations and open questions

- The prescription holds for the zoom-in direction only (s≥1, floor scaled by s²). Zooming out, bud contours drift downward (the 2026-10-20 article measured the low end at −32.7%), and the same margin would eat buds first. The zoom-out margin account — even a negative margin — is unmeasured and is now in the topic pool.
- The bud tail's "physical floor" comes from a simulator construction (radius ≥ 11). Real field buds have no such hard floor; their minimum is the tail of a continuous distribution. A real deployment must apply Section 4's rule to its own measured tail and must not import 242 as a constant.
- Clutter comes in two shapes, solid and textureless. Polygonal fragments and textured fallen petals are unmeasured; whether the squares' +26.6% is the worst shape band is unknown.
- The margin grid has no point between 0.25 and 0.40, so the true clearing point is only known to lie in (0.25, 0.40]; the prescription takes the grid point 0.40 and carries an unmeasured amount of conservatism. A tighter prescription needs a denser sweep of that interval.
- The mechanism behind squares outgrowing circles is unisolated (interpolation vs closing shares unmeasured); Section 3.4 offers only the data-consistent explanation.
- One cell (s=3.0, m=0) differs from the 2026-10-30 arm by one square (17 vs 18) due to my rewritten matcher; I verified cell by cell that this is the only mismatch, and it does not move the prescription.

## 6. References

- Earlier in this series: "Zoom In Three Times and the Floor Leaks a Whole Layer" (2026-10-30; the scaled floor, the ±7% drift band, and the undecided margin trade-off this article settles), "Zooming In Is Simpler Than You Think" (2026-10-26; bud area drift +1.8% to +7.1%), "A Threshold Is Not a Constant, It Is a Function of Distance" (2026-10-20; zoom-out bud contour underestimation down to −32.7%). Scenes, seeds and scoring rules are identical throughout.
- Preregistration, bench script and raw data for this article: data/2026-11-08-floor-margin-prereg.md (frozen before the run, prescription rule included), data/2026-11-08-floor-margin-bench.py, data/2026-11-08-floor-margin-bench.json (distributions, normalised lower tails, the full 5-scale × 7-margin grid), data/2026-11-08-floor-margin-posthoc.py and data/2026-11-08-floor-margin-posthoc.json (in-situ clutter contour isolation, prescription candidate recomputation, precision monotonicity check).
- Bloom-Counter repository (MIT; detector and simulator): https://github.com/Ezra-Zhao/Bloom-Counter — detector/color_segmentation.py; simulator/generate.py (bud radius sampling 11–17, bloom 30–50).
- OpenCV documentation: morphologyEx, findContours and contourArea, resize interpolation: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. All code and experiments described here are the author's clean-room work: the detector, simulator, clutter planting and measurement scripts were written by the author, and the experiments ran on locally generated synthetic data. No client data, client images or identifiable information are involved.
