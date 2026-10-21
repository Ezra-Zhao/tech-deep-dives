# Thresholds Are Not Constants: Calibration Drift in an Area-Threshold Detector, Measured

Author: Guangyi Zhao

## 1. Problem and background

My previous test of Bloom-Counter ended with an unpaid debt in its limitations section: the unit area used by the split estimator came from the same batch of scenes it was evaluated on, any change of camera distance would require recalibration, and I had not verified how that recalibration behaves. This article pays the debt — and finds that the threshold everyone worries about is not the only number that drifts, nor the first one to fail.

The detector (`detector/color_segmentation.py`) hard-codes three absolute pixel parameters: connected components smaller than `min_area=120` px² are discarded as noise; components at or above `bloom_area_min=900` px² are labelled open blooms, below it buds; and the morphological closing/opening kernel is 7 px. All three were tuned at 1280×960 from one fixed camera position. The textbook answer is simple: double the distance and every object halves in linear size and quarters in area, so rescale the area thresholds by the square of the scale factor and you are done. This article measures three things: whether that answer is right, how far it goes, and what it misses.

1. With nothing changed, how does the same scene fail as it is captured from farther away — and in what order?
2. If only the two area thresholds are rescaled by s², how much is recovered, and what exactly blocks the rest?
3. Are "lower resolution" and "greater distance" the same event? On site they are routinely conflated, and a lower-resolution camera triggers a recalibration reflex. Is that reflex justified?

## 2. Method

Scenes and scoring follow the previous article exactly: the repository's own simulator generates four 1280×960 scenes (seeds 101/202/303/404) with 210 targets in total (134 blooms, 76 buds); scoring is greedy centre matching where the label must also match, reported as micro-averaged precision/recall/F1 with bloom and bud recall separated. The matching tolerance is expressed in each image's own coordinates, max(38·s, 1.1×radius), so the relative tolerance is constant across scales. Baseline sanity check: on the original images the detector scores precision = recall = F1 = 1.000, identical to the previous article. The detector code is untouched; the three parameters are varied through its constructor.

Two experiment families, deliberately kept apart:

- Part A (geometric scaling, the distance simulation): the whole image is resampled with INTER_AREA to 1280·s × 960·s and ground-truth centres and radii are multiplied by s. s ∈ {1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.22}; in distance terms, s=0.5 is the same camera twice as far away (four times the area per frame), s=0.22 about 4.5×. Each scale is run under three parameter strategies: A1 everything fixed (120 / 900 / kernel 7); A2 both area thresholds scaled by s², kernel fixed at 7; A3 area thresholds by s² and kernel by 7·s rounded to an odd number (floor 3). Each scale also gets a threshold sweep — `bloom_area_min` at 0.25× to 1.3× of the theoretical 900·s² — and a one-parameter ablation (scale exactly one of the three parameters, keep the other two fixed) to attribute the fixed-parameter failure. Area drift is measured directly: the detector's internal pipeline (HSV mask plus morphology) is replicated, every contour is extracted, matched to ground truth by centre, and the median contour area per class is compared against the s² prediction.
- Part B (resolution loss with geometry unchanged): the image is downsampled by r with INTER_AREA and upsampled back to 1280×960 with INTER_LINEAR; ground truth does not move. r ∈ {1.0, 0.5, 0.33, 0.25, 0.167, 0.125}; the lowest tier keeps only 160×120 effective pixels. Fixed parameters are run as-is, plus the same `bloom_area_min` multiplier sweep.

Data and scripts: `data/2026-10-20-bloom-scale-bench.json` and `data/2026-10-20-bloom-scale-bench.py`; the ablation in `data/2026-10-20-bloom-scale-ablation.py` with its JSON alongside. Everything reruns with one command in the repository's virtualenv.

## 3. Measurements

### 3.1 Changing nothing: failure arrives in stages — noise floor first, classification threshold second

| s (≈ distance) | A1 fixed F1 | Bloom recall | Bud recall | Count error |
|---|---|---|---|---|
| 1.0 (baseline) | 1.000 | 1.000 | 1.000 | 0.0% |
| 0.8 (1.25×) | 1.000 | 1.000 | 1.000 | 0.0% |
| 0.65 (1.5×) | 0.931 | 1.000 | 0.645 | -12.9% |
| 0.5 (2×) | 0.402 | 0.515 | 0.000 | -36.7% |
| 0.4 (2.5×) | 0.082 | 0.104 | 0.000 | -36.7% |
| 0.3 (3.3×) | 0.012 | 0.015 | 0.000 | -38.1% |
| 0.22 (4.5×) | 0.000 | 0.000 | 0.000 | -51.9% |

At s=0.8 nothing happens, and that nothing is misleading: at baseline the median bloom contour is 3,806 px² and the median bud 343.8 px², an 11× separation, and any classification threshold between 630 and 1,170 (0.7×–1.3× of 900) scores a perfect F1. The threshold sits far from both classes, so a small distance change cannot hurt. That margin, not robustness, is what "no observed problem" means here.

The failure then arrives in stages, and the ablation attributes it cleanly (F1):

| s | Only min_area scaled | Only bloom threshold scaled | Only kernel scaled | Both thresholds (A2) | Everything (A3) |
|---|---|---|---|---|---|
| 0.65 | 1.000 | 0.931 | 0.934 | 1.000 | 1.000 |
| 0.5 | 0.692 | 0.776 | 0.401 | 0.998 | 1.000 |
| 0.4 | 0.300 | 0.776 | 0.064 | 0.915 | 1.000 |
| 0.3 | 0.018 | 0.765 | 0.000 | 0.768 | 1.000 |

Stage one (s=0.65) is purely `min_area`: bloom recall is still 1.000 while a third of the buds are gone. Buds have shrunk to a median contour near 132 px², and the fixed 120 px² noise floor starts deleting real buds as noise. Rescaling that single number by s² restores a perfect score; the other two parameters are irrelevant at this stage. Stage two (s=0.5) is the classification threshold: with only `min_area` scaled, bud recall returns to 1.000 but bloom recall stalls at 0.515 — the median bloom contour is now 913 px², so about half of all blooms fall under the fixed 900 line and are re-labelled as buds. With only the bloom threshold scaled the picture inverts (bloom recall 0.993, bud recall 0). Each threshold guards one end; both are needed.

The failure mode in stage two is the same one the previous article found under bad lighting: not missed detections but category migration. At s=0.5 with fixed parameters the detector still reports 133 objects, only 37% under the true count — but under label-consistent matching only 69 of them are hits. The other 64 detections are all labelled "bud", and since not a single true bud is hit, those 64 can only be re-labelled bloom components or their fragments; there is nowhere else for them to come from. One coincidence is worth flagging because it looks like a typo: the count error at s=0.4 is also -36.7%. It is not a copy error — the detector again reports 133 objects, but the composition has collapsed (69 blooms + 64 bud labels at s=0.5 become 14 + 119 at s=0.4). The total error stands still while the structure gives way, which is precisely the trap of total-count scoring.

### 3.2 Scaling only the area thresholds: works to s=0.5, then no threshold value helps

A2 (both thresholds by s², kernel fixed at 7) is perfect at s=0.8 and 0.65, reaches F1 0.998 at s=0.5 (one bloom lost), then falls to 0.915 at s=0.4 (bud recall 0.579), 0.768 at s=0.3 (bud recall 0.013), and 0.750 at s=0.22 (bud recall 0.000). Blooms stay healthy throughout (0.970 even at s=0.3); only buds collapse.

The threshold sweep shows why. The sweep is run inside the A2 family — `min_area` already scaled, only `bloom_area_min` moves. At s=0.22, F1 is 0.750 at every multiplier from 0.25× to 1.3×, literally constant. At s=0.3 it moves within 0.7625–0.7683, a range of 0.006. At s=0.4 it plateaus at 0.9147 once the threshold reaches 0.55× of theory and stays there to 1.3× (sweeping down to 0.25× is worse, for the opposite reason: surviving buds get re-labelled as blooms). In all three tiers the remaining loss sits entirely in bud recall (0.579 / 0.013 / 0.000) and does not respond to the threshold — the loss happens before classification, because the buds never reach the classifier. This does not contradict the ablation row where scaling only the bloom threshold lifts s=0.4 from 0.082 to 0.776: there `min_area` was fixed and the gain is on the bloom side (bloom recall back to 0.993, bud recall still 0). Different variable, different patients.

The direct contour count confirms the mechanism. With the kernel fixed at 7, the number of bud contours that can be centre-matched falls from 76 at baseline to 76 at s=0.5, 44 at s=0.4, 1 at s=0.3, and 0 at s=0.22. A bud is an ellipse whose minor-axis width is about 1.1× its radius: roughly 4.8–7.5 px at s=0.4 — right at the 7 px opening kernel — and 3.6–5.6 px at s=0.3, entirely below it. The opening operation erases the mask before any threshold is consulted. This is not a threshold problem; it is a length parameter, denominated in pixels, failing to scale with the image.

A3 scales the kernel too (7·s to the nearest odd number, floor 3: 5 at s=0.65 and 0.5, 3 at s≤0.4) and recovers F1 1.000 at s=0.5, 0.4 and 0.3, and 0.981 at s=0.22 (bloom recall 0.993, bud recall 0.908). The residue at s=0.22 is also explainable: 7×0.22≈1.5, so the floor of 3 keeps the kernel at about twice its proportional size, and a bud radius is by then only 2.4–3.7 px — the contour itself is dissolving into pixel quantisation.

### 3.3 Areas do not follow s² exactly either: the smaller the target, the more it shrinks

Dividing the matched median contour area by the s² prediction (baseline median × s²) gives a systematic shortfall that grows with distance and with smallness:

| s | Bloom area ratio (measured/predicted) | Bud area ratio | Matchable bud contours |
|---|---|---|---|
| 0.8 | 0.986 | 0.960 | 76/76 |
| 0.65 | 0.983 | 0.912 | 76/76 |
| 0.5 | 0.960 | 0.809 | 76/76 |
| 0.4 | 0.950 | 0.673 | 44/76 |
| 0.3 | 0.925 | — (1 left) | 1/76 |
| 0.22 | 0.896 | — (none) | 0/76 |

Blooms drift from -1.4% to -10.4%; buds reach -32.7% within the range where they can still be measured at all. Two causes: resampling and colour thresholding act at the boundary, and the perimeter-to-area ratio grows as targets shrink, so edge loss takes a larger share; and the opening operation erodes small masks proportionally harder. The late bud numbers also carry survivorship bias — the contours still matchable at s=0.4 are the larger survivors, so the true drift is worse than the table shows, and below s=0.3 there is no sample left to measure. Scoped to pipelines of this kind — colour thresholding plus morphology, classifying by absolute area — the conclusion is: s² is a first-order approximation for area calibration, not an exact law, and thresholds rescaled by it push borderline targets systematically toward the smaller class, more so the farther you go. Pipelines with a different segmentation front end (adaptive thresholding, edge-preserving filters, learned detectors) may drift differently or not at all; they were not measured here.

### 3.4 Resolution loss (down, then back up): geometry unchanged, thresholds basically fine

Part B is a different world. Downsampled to as little as 160×120 effective pixels (r=0.125, one sixty-fourth of the pixel count) and interpolated back to full size, the fixed-parameter detector scores F1 0.995, losing exactly two targets (one bloom, one bud). At r=0.167 it scores 0.998, and at r≥0.25 it is perfect. At every tier the multiplier sweep peaks at 1.0× — there is nothing to recalibrate.

The area drift even has the opposite sign for the two classes: the median bloom contour grows to 1.096× of baseline at r=0.125 (the low-pass blur fuses petal fragments into a single, slightly larger blob, and closing bridges the rest), while the median bud contour falls to 0.854×. But because the image arrives at the detector at the same pixel dimensions, both classes stay comfortably on their own sides of the 900 line and classification is untouched.

Put side by side, the governing variable is the size of a target in the detector's input image, not the sensor's nameplate resolution. Given the same framing (same field of view, same composition), a camera that outputs its picture scaled to the same input size is, on the threshold-geometry question alone, approximately Part B; a camera whose small native frames are fed to the detector as-is is Part A, where "resolution" and "distance" are mathematically the same event. The boundary matters and should be stated: Part B models a digital resampling chain (area-average down, bilinear up — in effect a low-pass filter). A real low-resolution sensor adds pixel aliasing, Bayer demosaicing and lens point-spread degradation, none of which were measured here, and whether those bite the colour segmentation is outside this article's claims. "We changed the camera, recalibrate" is therefore a question before it is a task: which of the two wirings did you actually change?

## 4. Analysis and trade-offs

Four takeaways:

1. Recalibrate the whole set, not just the classification threshold. Every parameter hard-coded in pixels carries a dimension: areas scale with s² (classification threshold, minimum area), lengths with s (morphological kernel, minimum spacing, NMS radius, and the like). The order in which they fail has nothing to do with execution order in code — morphology runs first, yet binds last here. What decides the order is the ratio between each parameter's value and the size of the objects it governs: as everything shrinks proportionally, whichever parameter collides with its objects first fails first. In this dataset buds are an order of magnitude smaller than blooms, so the order is `min_area` against the buds, then the classification threshold against the blooms, then the kernel reaching the buds' minor axis. A scene with a different size distribution would fail in a different order; the ratio test is what transfers. Fixing only the most visible threshold is why this pipeline stalls at F1 0.915 at s=0.4. The prescription has a floor: it holds while targets are still several pixels across and the kernel can be an odd number ≥3. Below that, pixel quantisation itself dominates (the s=0.22 residue is exactly this) and no rescaling recovers the target — the remedies left are a different camera position or a different detector.
2. The diagnostic method is more reusable than the result: once the other parameters have been excluded one by one, if sweeping a parameter across its reasonable range lands the metric on a plateau (here, movement of at most 0.006 at s≤0.3), the bottleneck is not that parameter — the loss is upstream or downstream of it. That is how the blame moved from the threshold to the kernel in this article, and the same move separated preprocessing damage from occlusion damage in the previous one.
3. Field recalibration can be an estimator instead of a full re-run: shoot a few frames at the new position, take the ratio of median bloom contour areas against the baseline median, take the square root as the estimate of s, and rescale the full set by it. This estimator's end-to-end accuracy is not validated here — in the experiment s was given exactly by the resampling, not estimated — so it is a candidate procedure supported by the drift data, not a result.
4. Monitor the smallest class. Every collapse in this article kills buds first and blooms later, and the same was true of the lighting and occlusion failures in the previous article. Per-class recall with a separate alarm line on the smallest class catches calibration drift one to two stages earlier than watching the total count.

One alternative deserves a note because I did not take it: normalising the detector input instead — upscaling small frames back to the baseline size before detection — moves the scaling from the parameter side to the image side. Part B shows upscaling itself does not hurt classification, but it cannot restore high-frequency content that a natively small frame never captured: an upscaled bud's minor axis is still blurred, and the kernel and thresholds still face the degraded mask. The two routes are therefore not equivalent. Parameter scaling preserves the pixels you actually have; input rescaling changes which pixels the parameters face. I took parameter scaling as the main line; a systematic run of the input-rescaling route was not done and is listed as unmeasured.

## 5. Limitations and open questions

- All scenes are synthetic and all scaling is digital resampling. INTER_AREA is one specific box-filter approximation; it is not a real lens's point-spread function or a real sensor's sampling, and it does not model the aliasing and Bayer demosaicing artefacts of a genuinely low-resolution sensor. Moving a real camera twice as far also changes perspective, depth of field and lighting angles; this article isolates geometric scale alone. The numbers are this pipeline's drift law under pure scaling, not a precision promise for a real camera move.
- Only moving away was measured (s<1), not moving closer (s>1). By symmetry I would predict relatively looser thresholds, a relatively finer kernel, and the dominant risk shifting to targets leaving the frame and to overlap merging — but that is a prediction, not a measurement.
- In the experiment s is ground truth, supplied by the resampling. In the field s must be estimated from a reference object or from area medians, and estimation error propagates directly into all three parameters; that error chain is unmeasured.
- The kernel rounding rule (7·s to odd, floor 3) is an engineering choice, not the only one. At s=0.22 the floor holds the kernel at twice its proportional size; how much of that tier's residual loss is rounding and how much is pixel quantisation cannot be separated here.
- Bud area drift has no samples below s=0.3 (the kernel has already erased the contours), so the small-target end of the drift curve is truncated; the -32.7% at s=0.4 itself carries survivorship bias and the true value is lower.
- Part B measures one degradation chain (INTER_AREA down, INTER_LINEAR up). A different interpolation, JPEG compression, or sensor noise could change the direction and size of the area drift.
- Still only four scenes and 210 targets, one simulator and one detector. Transfer of these conclusions to the broader family of "area threshold plus morphology" pipelines is inference, not cross-pipeline measurement.

## 6. References

- Bloom-Counter repository (MIT; all code used here): https://github.com/Ezra-Zhao/Bloom-Counter . Detector: `detector/color_segmentation.py` (the three parameters, the HSV mask and the morphology pipeline); simulator: `simulator/generate.py`.
- Previous article in this repository: "The Total Was Right and the Structure Was Wrong: Lighting and Occlusion Tests of the Bloom-Counter Pipeline" (2026-10-17). This article takes up the cross-distance calibration question its limitations section left open, using identical scenes, seeds and scoring.
- Experiment scripts and raw data for this article: `data/2026-10-20-bloom-scale-bench.py` and `data/2026-10-20-bloom-scale-bench.json` (Part A: 7 scales × 3 parameter strategies + threshold sweep + contour-area drift; Part B: 6 resolution tiers), and the ablation pair `data/2026-10-20-bloom-scale-ablation.py` / `.json` (4 scales × 6 parameter combinations).
- OpenCV documentation: `resize` and interpolation flags (INTER_AREA / INTER_LINEAR), morphological operations and structuring elements: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. All code and experiments described here are the author's own clean-room work: the detector, the simulator and the scaling test scripts were written by me, and the experiments were run locally on synthetic data. No client data, client images or identifiable information are involved.
