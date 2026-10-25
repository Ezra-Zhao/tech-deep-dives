# Upscaling Back to Calibration Size Wins: Input Resampling vs. Parameter Scaling, Measured

Author: Guangyi Zhao

## 1. Problem and background

In the previous article in this series I left a judgement on the record that sounded reasonable and had no measurements behind it: upscaling a small frame back to the calibration size before detection (the "upsampling route") cannot recover high-frequency information that is no longer in the native small frame — a bud's blurred short axis stays blurred — so the two routes "are not equivalent", and I adopted parameter scaling as the main conclusion while listing the upsampling route as untested. This article tests that sentence. Short version: within the range measured here, the sentence is wrong, and wrong in an instructive way. The losing route is the parameter scaling I had picked, and it does not lose to missing information. It loses to the quantisation floors of two integer parameters.

The setup. When the camera moves farther away, or a lower-resolution camera is fitted, the detector receives a native small frame (s times the 1280×960 baseline, s<1). There are two deployment options:

- Parameter scaling (route P): feed the small frame as-is, with the full rescaling prescription from the previous article — area thresholds by s², morphological kernel to the odd number nearest 7·s (floor 3). This is route A3 of the previous article: F1 1.000 at s=0.3, 0.981 at s=0.22.
- Input resampling (route U): upscale the small frame back to 1280×960 first, then run the untouched baseline parameters (`min_area=120`, `bloom_area_min=900`, kernel 7). No parameter changes; the image changes instead.

The detector is still Bloom-Counter's colour-segmentation pipeline (`detector/color_segmentation.py`: a three-band HSV petal mask, morphological close then open, classification by connected-component area). Scenes, seeds and scoring match the two previous articles exactly: four simulator scenes (seeds 101/202/303/404), 210 objects (134 blooms, 76 buds), greedy centre matching where a hit requires the label to agree. The question the previous article left open was specific: after a bud's short axis blurs, at which stage does the upsampling route lose? I designed a stage-by-stage decomposition to answer it — and found the question pointed the wrong way. The first stage losses are not in the upsampling route at all.

## 2. Method

For each scale s, the baseline image is downscaled with INTER_AREA into a native small frame (the same generation process as part A of the previous article), then split four ways: route P detects on the native frame with the prescription above; route U upscales back to 1280×960 with one of three interpolations (INTER_LINEAR, INTER_CUBIC, INTER_NEAREST) and detects with baseline parameters. Scales: 1.0 / 0.8 / 0.65 / 0.5 / 0.4 / 0.3 / 0.22 / 0.15, with 0.15 one step beyond the previous article's range; plus two extreme tiers, 0.10 (128×96) and 0.07 (90×67), added to locate each route's cliff. Ground truth follows the route: route P is scored against scaled ground truth in native-frame coordinates (tolerance max(38·s, 1.1·radius)), route U against the original ground truth. Two replication checks: route P reproduces the previous article's A3 digit for digit at overlapping tiers (F1 1.000 at s=0.3, 0.981 at s=0.22); and the images route U-LINEAR feeds the detector are pixel-identical to the previous article's part-B down-then-up chain at r=s, with scores tracking part B (part B: perfect at r=0.25, F1 0.998 at r=0.167; here U-LINEAR is perfect at s=0.22 and 0.998 at s=0.15).

To answer "at which stage", every route also gets a stage-survival count (label-agnostic centre matching, run independently per stage, so a ±1 non-monotonicity can occur between stages — a matching artefact, flagged where it appears):

- Stage 1, mask: how many ground-truth objects match a component of the raw HSV mask;
- Stage 2, morphology: how many match a contour after close+open, recording contour area and the median bounding-box short side;
- Stage 3, area gate: how many of those contours pass the route's `min_area`;
- Stage 4, final: of the detector's output, how many are correct, how many migrated (detected, but reclassified into the other class), how many are lost outright.

Timing is measured separately: 30 repeated detections per route per tier, median, detection call only (no I/O, no upscale); the upscale itself is timed separately. Raw data and scripts: `data/2026-10-24-bloom-resample-bench.json` and the bench script of the same name; timing in `data/2026-10-24-bloom-resample-timing.json` and its script. Everything reruns with one command in the repository's virtualenv.

## 3. Measurements

### 3.1 Headline scores: all four routes are perfect down to s=0.3; the split below 0.22 runs opposite to my prediction

| s (native frame) | P param-scaling F1 | U-LINEAR F1 | U-CUBIC F1 | U-NEAREST F1 |
|---|---|---|---|---|
| 1.0–0.3 (six tiers) | 1.000 | 1.000 | 1.000 | 1.000 |
| 0.22 (282×211) | 0.981 | 1.000 | 1.000 | 1.000 |
| 0.15 (192×144) | 0.846 | 0.998 | 1.000 | 1.000 |
| 0.10 (128×96) | 0.749 | 0.961 | 0.991 | 0.976 |
| 0.07 (90×67) | 0.711 | 0.788 | 0.954 | 0.866 |

At s≥0.3 there is nothing to choose: all four routes are perfect. The split starts at 0.22, where route P's bud recall drops to 0.908 (F1 0.981, four-scene micro-average under the Section-1 scoring rule, digit-identical to A3 in the previous article). At s=0.15 route P's bud recall collapses to 0.276 (F1 0.846, count error −26.7%); at 0.10 it is 0.013; at 0.07, zero. The upsampling routes are perfect or near-perfect at both 0.22 and 0.15 under all three interpolations — U-LINEAR at 0.15 loses exactly one bloom (bloom recall 0.993, bud recall 1.000). The upsampling cliff only appears two tiers lower, and each interpolation falls off it differently (Section 3.3).

One misreading to head off: upsampling creates no information. Route U wins not because interpolation restores detail, but because it sidesteps two quantisation floors inside route P. The stage data shows which floors.

### 3.2 Where route P loses: the information is still in the mask; it dies in morphology and in the discreteness of contour area

Bud stage survival (n=76):

| Route and tier | Stage 1 mask | Stage 2 morphology | Stage 3 area gate | Final correct |
|---|---|---|---|---|
| P, s=0.22 | 76 | 76 | 69 | 69 |
| P, s=0.15 | 76 | 43 | 21 | 21 |
| P, s=0.10 | 76 | 1 | 1 | 1 |
| P, s=0.07 | 72 | 0 | 0 | 0 |
| U-LINEAR, s=0.15 | 76 | 76 | 76 | 76 |
| U-LINEAR, s=0.10 | 76 | 75 | 63 | 64 |
| U-LINEAR, s=0.07 | 73 | 61 | 33 | 33 |

The row that matters is route P at s=0.10: the raw HSV mask of the native frame still contains all 76 buds. The information is there — colour segmentation on a 128×96 image finds every one of them. What kills them is the next step: after the opening operation, one is left. The previous article had half of this: the kernel is scaled to the odd number nearest 7·s with a floor of 3, while the theoretical kernel 7s at s=0.22 / 0.15 / 0.10 / 0.07 is 1.54 / 1.05 / 0.70 / 0.49, so the floor inflates it to 1.9× / 2.9× / 4.3× / 6.1× the intended size. Meanwhile a bud's short axis (full width 1.1×radius, radius 11–16 px) shrinks to about 1.8–2.6 px at s=0.15, and the median bounding-box short side of matched post-morphology contours is exactly 3 px — the same width as the kernel. Opening a mask with an element as wide as the target itself leaves survival to chance.

The second floor sits at stage 3 and is quieter: `cv2.contourArea` measures the area of the contour polygon, not a pixel count. For contours of a few hundred pixels the difference is negligible; for fragments of a few pixels the polygon area is systematically smaller than the pixel count. Route P's ratio of median bud contour area to the s² prediction slides from 0.960 at s=0.8 to 0.743 at s=0.3, 0.571 at s=0.22 and 0.259 at s=0.15 (survivors only; the true drift is worse). At s=0.15, the 43 buds that survive morphology have a median contour area of 2.0 px², while the tier's s²-scaled `min_area` is 3 — the median itself sits under the gate, and the gate halves the survivors again (43→21). The previous article attributed the residual loss at s≤0.3 to "pixel discreteness becoming dominant"; this article resolves that phrase into two concrete mechanisms: the integer kernel floor, and the systematic under-measurement of tiny contours. Blooms, being large, tolerate route P much longer: 133/134 still survive at s=0.15, dropping to 127 at s=0.10 and 119 at s=0.07, lost mainly at stage 2.

Why route U escapes: after upscaling to calibration size, the kernel of 7 acts in baseline coordinates — equivalent to a "fractional kernel" of 7s in native coordinates — and no integer floor exists. Contour areas also return to the hundreds-of-pixels regime, where polygon approximation error is negligible again. Route U's price is not accuracy. It is compute (Section 3.4).

### 3.3 The blur on the upsampling route is real, but the classification margins absorb it first; its own cliff is at s≤0.10, and each interpolation falls differently

The failure mode I had predicted for route U — the bud's blurred short axis shrinks its area until it crosses a gate — is not fabricated; the mechanism exists and measures out as follows (U-LINEAR, median matched post-morphology contour area). Buds shrink from the baseline median of 343.8 px² to 329.8 (s=0.3), 319.2 (0.22), 314.8 (0.15), 243.5 (0.10) and 127.0 (0.07): relative drift −4.1% / −7.2% / −8.4% / −29.2% / −63.1%. Blooms drift the other way: 3926.5 / 4025.2 / 4146.5 / 4192.8 / 3977.5, i.e. +3.2% / +5.8% / +8.9% / +10.2% / +4.5% (the 0.07 figure is survivor-only and not directly comparable to 0.10). The interpolation's low-pass eats a ring off small targets (a bud has a single pink band; edge pixels whose saturation dips fall out of the mask) while welding a large target's petal fragments into one piece — the same signed drift as part B of the previous article.

It costs nothing at s≥0.15 because of the margins: at baseline calibration the bud median area is 2.9× `min_area`, `bloom_area_min=900` is 2.6× the bud median and 1/4.2 of the bloom median. A ±10% drift is far from every gate. Which is also why the per-class detail (the drift curves) can degrade steadily while the headline score does not move at all — a pattern this series keeps meeting: an unmoving metric does not mean an unchanging process, only that nothing has hit a gate yet.

Route U starts losing at s≤0.10, and the failure mode splits by interpolation:

- U-LINEAR loses at the left tail of the area gate. At s=0.10 the bud median is still 243.5, but the distribution's left tail crosses 120 first: 75 buds survive morphology, 63 pass the gate. At s=0.07 all three stages leak (73→61→33) and the gate remains the largest single cut (−28). Blooms begin migrating in parallel (2 reclassified as buds at s=0.10, 10 at s=0.07, as the smallest blooms blur below 900). F1 goes 0.961 → 0.788.
- U-CUBIC holds up best. Its ringing keeps edge pixels saturated, so bud area drifts far less: median 315.0 at s=0.10 (−8.4%), with all 76 buds surviving every stage, and 254.0 at s=0.07 (−26.1%), where F1 is still 0.954. Its losses likewise concentrate at the area gate (73→63), plus 4 migrated blooms.
- U-NEAREST does not lose targets; it invents them. At s=0.07 its bud recall is still 0.961, the best of the three — but block replication turns edges into jagged fragments: 57 false positives, count error +24.3%, precision 0.782. At s=0.10 it already has 6 false positives. It "wins" on recall and is the first to fail the actual deliverable, a count. A pipeline that reports recall without precision will systematically hide this failure mode.

One more comparison worth recording: at s=0.07, route P's mask stage already drops 4 buds (72/76), while U-CUBIC's mask has all 76. In a native frame of a few pixels per bud, the centre pixel's colour is already a petal-and-foliage mixture and the HSV decision starts flipping; masking after upscaling averages neighbourhood colour first, and some mixed pixels land back inside the petal band. Upscaling does not "restore" colour — the two sampling orders simply judge mixed pixels differently, and with a different colour distribution the sign of this effect could reverse. I report it as one observation, not a law.

### 3.4 Route U's real price: compute, roughly 5–33×

Median detection time over 30 repetitions (detection call only, excluding I/O):

| s | P detection | U-LINEAR detection | Upscale itself | U total / P |
|---|---|---|---|---|
| 0.5 | 2.5 ms | 11.9 ms | 1.0 ms | ≈5× |
| 0.22 | 0.8 ms | 12.5 ms | 0.8 ms | ≈17× |
| 0.15 | 0.5 ms | 11.1 ms | 0.8 ms | ≈24× |
| 0.10 | 0.3 ms | 9.4 ms | 0.6 ms | ≈33× |

Route U's cost is essentially independent of s — it always processes 1280×960 — while route P's falls with pixel count. On this machine both are milliseconds per frame, which is nothing for a single photo; folded into a video stream or an edge device it stops being nothing: at 30 fps the frame budget is 33 ms, and route U on this machine takes about 40% of it, against under 1 ms for route P in the tiers where P still works. That is the genuine trade-off axis between the routes: not accuracy against accuracy, but accuracy against compute — and on the accuracy side, at s≥0.3 there is no difference to trade.

## 4. Analysis and trade-offs

Four takeaways:

1. The deployment prescription changes, on this evidence (scope: area-threshold pipelines of this kind). On this pipeline, upscaling a native small frame back to calibration size and detecting with the original parameters is the more robust default — it loses nothing down to s=0.15 (about 6.7× the distance), while full parameter scaling starts dropping buds at s=0.22. This corrects the previous article's "the two routes are not equivalent; we adopt parameter scaling" verdict: the non-equivalence was real, the direction was backwards. The reason for the error is worth stating plainly: part B of that article proved only that "upscaling does not hurt classification", never ran the two routes head-to-head at the same tiers, and never decomposed route P's losses by stage — so a plausible-sounding mechanism ("blur cannot be undone") was written down as a conclusion inside an item that was itself listed as untested. This is the second time this series has hit the same class of mistake; the previous article's external review caught an over-attributed cause, and this time the untested assertion was hiding in my own "untested" list.
2. At small scales, what breaks first is often not the signal but the parameters' representation. At s=0.10 the native frame's mask contains all 76 buds; the bottleneck is not the sensor, it is inside the detector: kernel sizes that must be odd integers (floor 3), and a contour-area function that approximates polygons. Such quantisation floors share a signature — completely harmless at calibration scale (a kernel of 7, contours of hundreds of pixels), suddenly dominant when targets shrink to single-digit pixels. When auditing a classical pipeline for cross-scale deployment, checking every parameter that is "written in pixels and can only take integer values" pays off before suspecting sensor resolution. The upsampling route, at bottom, moves the target back into the coordinate system those parameters were tuned in, returning quantisation error to its calibrated magnitude.
3. Interpolation choice only matters at the extreme tiers; do not agonise early. At s≥0.15 the three interpolations are indistinguishable. If a deployment genuinely runs at s≤0.10 (frame width barely over a hundred pixels), pick CUBIC and avoid NEAREST — the latter's recall looks good, but it buys that recall with false positives and fails first at the counting deliverable. Any production line that reports recall without precision will hide exactly this.
4. Choose the route by s band: at s≥0.3 the routes tie on accuracy, so take P and save the compute; at 0.15≤s<0.3 take U and stay off P's bud cliff; below s=0.15 both routes are trading accuracy for something, and the first question should be whether the camera can move closer or the sensor can change, not how to squeeze the algorithm. U-CUBIC's 0.954 at s=0.07 sits near this synthetic setup's ceiling; it is not a deployment promise.

## 5. Limitations and open questions

- Everything is still synthetic: native small frames are INTER_AREA downscales of clean synthetic images, with no real sensor's pixel aliasing, Bayer demosaicing, lens point-spread or read noise. Real small frames have dirtier mixed pixels, and whether Section 3.3's closing observation (mask-after-upscale finding more buds) survives real images is entirely untested.
- Only this one pipeline family (HSV mask + morphology + area thresholds) is measured. Learned detectors natively expect a fixed input size — upscaling is their normal mode — and nothing here transfers to them. Other classical pipelines (adaptive thresholds, edge-based methods) have their quantisation floors in different places; each needs its own measurement.
- Stage survival counts come from independent per-stage matching, not from tracking individual objects stage to stage; the ±1 non-monotonicity in U-LINEAR's s=0.10 bud row (63 past the gate, 64 finally correct) is that artefact. Stage attribution of losses is therefore approximate, and an individual object can be booked to the wrong side of a stage boundary.
- Timing was measured on one machine and one OpenCV version (5.0.0), medians of 30 runs. The absolute milliseconds do not travel; what travels is the shape — U roughly constant, P falling with pixel count — and the rough magnitude of the ratio.
- Still only 4 scenes and 210 objects. At the extreme tiers one or two objects are worth about 0.005 of F1, so the interpolation ordering at s=0.07 (CUBIC > NEAREST > LINEAR) is directional evidence, not a settled ranking.
- Route U inherits the calibration wholesale: if the baseline parameters were tuned to the wrong operating point in the first place, U faithfully re-applies that error to every frame. The "miscalibration plus upsampling" combination is untested here.
- s is still given by the resampling, not estimated. The error chain of estimating s in the field and choosing a route by the estimate (takeaway 4) is unmeasured; it merges with the s-estimation error-chain item already in the topic pool.

## 6. References and sources

- Bloom-Counter repository (MIT; all code used here): https://github.com/Ezra-Zhao/Bloom-Counter . Detector `detector/color_segmentation.py` (HSV mask, morphology pipeline, the `min_area` / `bloom_area_min` / `morph_kernel` parameters); simulator `simulator/generate.py` (bud ellipse axes defined in `_draw_bud`).
- Previous articles in this repository: "Thresholds Are Not Constants, They Are Functions of Distance: Calibration Drift of an Area-Threshold Detector, Measured" (2026-10-20) — this article takes up its Section 4 untested item and Section 5 limitations; route P is its A3 and route U-LINEAR's input is its part-B chain. And "The Total Was Right, the Structure Was Wrong: Light and Occlusion Measurements on the Bloom-Counter Agricultural Counting Pipeline" (2026-10-17), the source of the scenes and scoring rule.
- This experiment's scripts and raw data: project `data/2026-10-24-bloom-resample-bench.py` and `data/2026-10-24-bloom-resample-bench.json` (10 scales × 4 routes, headline scores, stage survival, area and short-side medians); timing in `data/2026-10-24-bloom-resample-timing.py` and `data/2026-10-24-bloom-resample-timing.json` (medians of 30 runs).
- OpenCV documentation: `resize` and interpolation flags (INTER_AREA / INTER_LINEAR / INTER_CUBIC / INTER_NEAREST), the polygon-area definition of `contourArea`, morphology operations: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. All code and experiments described here are the author's own clean-room work: the detector, the simulator and the resampling comparison scripts were written by the author, experiments ran on locally synthesised data, and no customer data, customer images or identifiable information are involved.
