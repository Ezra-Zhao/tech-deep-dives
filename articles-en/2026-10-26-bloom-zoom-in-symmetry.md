# Moving Closer Turned Out Simpler: A Symmetry Test for s > 1 — Only the Class Threshold Collapses, and Going Out of Frame Is a Framing Cost, Not a Detection Cost

Author: Guangyi Zhao

## 1. Problem and background

When I measured zooming out (s < 1) in the 2026-10-20 article, I left an untested prediction in the limitations: I had only measured moving farther away, never closer. By symmetry, I guessed that moving closer would make the area thresholds relatively looser and the morphology kernel relatively finer, and that the dominant failure would switch to large targets leaving the frame and overlapping targets merging. This article settles that debt. The verdict: the prediction was one-third right and two-thirds wrong, and the wrong parts are the more useful ones.

First, "moving closer" has to be split into two experiments, or the results lie. A camera moving closer to the same flower bed does two different things: each target grows on the sensor (geometric scaling), and the frame can no longer hold the whole scene (framing loss). The earlier study grew the canvas together with the image, which measures pure geometric scaling — nothing can leave a frame that grows. To measure framing, the frame must stay pinned at 1280×960 while the image is enlarged and only the centre is kept. So this study has two parts:

- Part E (expansion, pure geometry): the whole image is upscaled with INTER_LINEAR to 1280·s × 960·s, ground truth scales by s, the canvas grows with the image. This tests the symmetry of scaling itself.
- Part C (crop, real approach): after upscaling, the image is centre-cropped back to 1280×960 and ground truth is transformed accordingly. Framing loss is accounted separately from detection quality on the targets that remain in frame.

Scenes and scoring are identical to the three previous articles: the Bloom-Counter colour-segmentation pipeline (detector/color_segmentation.py, baseline parameters min_area=120, bloom_area_min=900, kernel 7), four simulated 1280×960 scenes (seeds 101/202/303/404), 210 targets (134 blooms, 76 buds), greedy centre matching with the label required to match, micro-averaged over the four scenes. s takes 1.0 / 1.25 / 1.5 / 2.0 / 2.5 / 3.0. Each scale is measured under three parameter strategies: S1 everything fixed; S2 both area thresholds scaled by s², kernel fixed at 7; S3 area thresholds by s² and the kernel scaled to the odd approximation of 7·s. Part E adds single-parameter ablations (at 1.5 / 2.0 / 3.0), a classification-threshold multiplier sweep, contour-area drift measurement, and an interpolation sensitivity check at s=2.0 (LINEAR / CUBIC / NEAREST). Baseline sanity check: F1 1.000; baseline median contour areas 3806.0 px² for blooms and 343.8 px² for buds, digit-for-digit consistent with the earlier articles.

Raw data and script: data/2026-10-26-bloom-zoom-in-bench.json and the bench script of the same name, reproducible with one command in the repository virtual environment.

## 2. Measurements

### 2.1 Part E with fixed parameters: one plateau, failure in a single direction

| s | S1 fixed F1 | Bloom recall | Bud recall | Detections (truth 210) |
|---|---|---|---|---|
| 1.0 | 1.000 | 1.000 | 1.000 | 210 |
| 1.25 | 1.000 | 1.000 | 1.000 | 210 |
| 1.5 | 0.900 | 1.000 | 0.724 | 210 |
| 2.0 | 0.6381 | 1.000 | 0.000 | 210 |
| 2.5 | 0.6381 | 1.000 | 0.000 | 210 |
| 3.0 | 0.6381 | 1.000 | 0.000 | 210 |

Set against the zoom-out direction, the shape is entirely different. Zooming out, fixed parameters produced a three-stage collapse (0.931 → 0.402 → 0.082 → 0.012 → 0), each stage failing for a different reason. Zooming in, there is exactly one step: at s=1.5, 21 large buds cross the fixed 900 threshold and are relabelled as blooms; by s=2.0 all 76 buds have migrated, and F1 pins at 0.6381 and never moves again — the detection count stays at 210 throughout, and the plateau's 76 false positives and 76 false negatives all come from the relabelling (each migrated bud contributes one false bloom and one missed bud). Bloom recall is 1.000 from start to finish.

The migration timing also checks out arithmetically. The bud median area is 343.8, so the median bud crosses 900 at s = √(900/343.8) ≈ 1.62. At s=1.5 the measured median is 798.8 — not yet across — but the upper tail of the distribution crosses first: that scale's detection composition is 155 bloom labels and 55 bud labels, the 21 extra blooms matching the 21 missing buds exactly. At s=2.0 the median is 1448.8, the whole distribution is across, and migration is complete. Stragglers first, then the whole class — exactly what the median crossing point predicts.

### 2.2 Ablation: of three parameters, only one is doing any work

| s | Scale min_area only | Scale class threshold only | Scale kernel only | S2 both areas | S3 full |
|---|---|---|---|---|---|
| 1.5 | 0.900 | 1.000 | 0.900 | 1.000 | 1.000 |
| 2.0 | 0.6381 | 1.000 | 0.6381 | 1.000 | 1.000 |
| 3.0 | 0.6381 | 1.000 | 0.6381 | 1.000 | 1.000 |

This is the starkest asymmetry with the zoom-out direction. Zooming out, the three parameters hit their limits in sequence as the size ratios closed in, skipping any one of them left a stage of collapse behind, and full scaling was the only fix. Zooming in, correcting the classification threshold alone by s² restores a perfect score at all three scales, and the other two parameters make no difference to a single digit. S2 and S3 agree digit-for-digit at all six scales (F1 1.000 everywhere).

The two idle parameters are idle for different reasons. min_area is a floor: it only bites when targets shrink towards it. Moving closer, every contour area grows as s² away from the floor — even the smallest bud is already at roughly 540 px² by s=1.25, more than four times the fixed floor — so it never gets a chance to be the bottleneck. The "relatively finer kernel" half of the prediction produced no visible failure at all. The contour count after morphology is exactly 210 at every scale and every kernel choice: a fixed kernel of 7, whose relative size at s=3 is a third of baseline, still closes each bloom's petals into one contour, because in these simulated blooms the petals are laid over the flower centre and the gaps are far smaller than the kernel's absolute size. Nor was there any merging: the simulator places targets at least 8 px apart, the gaps scale with s, and a relatively finer fixed kernel only makes bridging less likely; even the scaled kernel 7·s stays below the 8·s minimum gap. So "overlap merging" was not refuted here — the conditions for it never arose. Real dense canopies have genuine overlap already at baseline scale; that is a different experiment and is recorded as a limitation, not dressed up as a measurement.

The threshold sweep fills in the tolerance shape (within the S2 family, min_area already scaled, sweeping the bloom_area_min multiplier): at all three scales the shape is the same — multipliers from 0.7 to 1.3 give F1 1.000 throughout, while going low degrades immediately (0.948–0.976 at 0.55, back to the old 0.6381 plateau at 0.25). In the zoom-in direction the threshold should err high: thirty percent too high costs nothing, too low starts the migration at once. The high-side plateau is much wider than in the zoom-out direction (where at s=0.4 the plateau began at 0.55×), because the bloom distribution sits far above the threshold to begin with.

### 2.3 Area drift: the sign flips, the magnitude shrinks

| s | Bloom area ratio (measured/predicted) | Bud area ratio | Matched contours (blooms/buds) |
|---|---|---|---|
| 1.25 | 1.014 | 1.018 | 134/134, 76/76 |
| 1.5 | 1.016 | 1.033 | same |
| 2.0 | 1.032 | 1.054 | same |
| 2.5 | 1.032 | 1.063 | same |
| 3.0 | 1.037 | 1.071 | same |

Zooming out, contour areas fell systematically short of the s² prediction (blooms −1.4% to −10.4%, buds down to −32.7% over the measurable range). Zooming in, the sign flips completely and the magnitude is much smaller: blooms +1.4% to +3.7%, buds +1.8% to +7.1%. Two regularities survive: the smaller class still drifts about twice as much as the larger one, and not a single sample is lost — all 210 contours remain matchable at all six scales, with none of the zoom-out direction's truncated tail. For the cause I offer only an interpretation consistent with the data, not an isolated proof: the smoothing of upscale interpolation and the outward edge effect of closing dominate when targets grow, while downsampling and the erosive edge effect of opening dominate when targets shrink; the edge effects in the two directions have opposite signs. Practically, this is enough: scaling the threshold by s² in the zoom-in direction imports at most about 7% systematic error, and with the threshold sitting as far from both class distributions as Section 2.2 shows, that error never reaches the decision.

The interpolation check is a footnote: at s=2.0, LINEAR, CUBIC and NEAREST upscaling give digit-for-digit identical F1 under all three strategies. These numbers are not an artefact of one interpolation algorithm, at least on this synthetic data.

### 2.4 Part C: leaving the frame is real, but it belongs in the framing ledger

| s | Centres retained (of 210) | Uniform prediction 1/s² | Any part visible | Fully inside |
|---|---|---|---|---|
| 1.25 | 163 (77.6%) | 64.0% | 183 | 140 |
| 1.5 | 117 (55.7%) | 44.4% | 130 | 99 |
| 2.0 | 73 (34.8%) | 25.0% | 85 | 58 |
| 2.5 | 46 (21.9%) | 16.0% | 63 | 35 |
| 3.0 | 31 (14.8%) | 11.1% | 43 | 23 |

The real cost of moving closer is here, and it is an order-of-magnitude cost: at s=3 a frame holds 31 of the original scene's targets (14.8%). Measured retention runs systematically above the uniform 1/s² prediction because of the simulator's placement rule — target centres keep a margin of at least 30 px plus radius from the image edge, so the distribution never touches the border. A real flower bed has no such rule; its retention will sit closer to 1/s² or below. Read this column accordingly: 1/s² marks the order of magnitude, the measured values are the upper side for a margin-kept distribution, and neither is a field number.

The second ledger is the important one. Scored only against targets whose centres remain in frame, S3 gives bloom and bud recall of 1.000 at all six scales — classification is flawless (S2's F1 matches S3 at every scale; only the s=3.0 detection composition differs by one target). The F1 of 0.87–0.96 is not worse detection; it is precision docked by the visible fragments of neighbours that have already left the frame. Attributing the same detection set against two truth sets — centres-in-frame versus any-part-visible — shows that at every scale from 1.25 to 3.0 the large majority of detections match a visible target, only 3–6 detections per scale match nothing visible at all, and the extra hits (4–10 per scale) are all neighbours whose centres are out of frame but whose edges still show. In other words, the detector does its in-frame job exactly as cleanly as in Part E; the F1 gap is an accounting problem. When frames are stitched or counted one by one, those edge fragments will be double-counted across adjacent frames unless there is an explicit ownership rule (counting only targets whose centre is in frame is the cleanest under this study's scoring). With fixed parameters, Part C additionally inherits Part E's migration (bud recall 0.04 at s=2.0) — the two ledgers stack, which is precisely why the two parts had to be measured separately.

## 3. Analysis and trade-offs

Four takeaways:

1. Recalibrating for a closer camera is a one-parameter job. Scale the classification threshold by s² and stop; within the tested range up to s=3, min_area and the kernel can stay. The zoom-out direction is the exact opposite — scale everything or keep a stage of collapse. The deciding factor is not the direction but the failure mechanism: zoom-out failures are deletions (contours erased by the kernel, screened out by the noise floor — the information is gone), while zoom-in failure is relabelling (contour and area intact, only the tag is wrong). Relabelling is repairable after the fact — store each contour's area and the whole run can be re-thresholded later; deletion is not repairable at all. This is worth more than the F1 numbers: when judging how fragile a pipeline is to calibration drift, first ask whether its failures delete or merely relabel.
2. Symmetry lives in the formula, not in the failures. The s² scaling law holds in both directions (with even smaller drift when zooming in), but the number of failure stages, the dominant parameter, the sign and size of the area drift, and the sample survival rate — none of these are symmetric. Extrapolating zoom-out experience to zoom-in spends effort on a kernel problem that does not exist and misses the coverage problem that does.
3. Spend the zoom-in budget on coverage and counting rules, not on detection. Retention falls at roughly the 1/s² order, so per-area counts must be normalised by the area actually visible, and per-frame counting needs its edge ownership rule settled first (centre-in-frame is the cleanest under this scoring). Skip those two, and the totals are wrong no matter how high the detection F1 is. This is the spatial mirror of the first article's lesson — there the class structure was wrong behind a correct total; here it is the spatial structure.
4. Keep monitoring the smallest class, but flip the alarm direction. Zooming out, buds are deleted (recall drops). Zooming in, buds are relabelled into the large class (bud recall drops, the bloom count inflates, and the total does not move). A totals-only monitor never fires on the zoom-in migration — at s=2.0 the total count error is exactly 0.0% while the structure is completely wrong. Per-class recall, plus an upper alarm on the large class's count, is what covers this direction.

One road not taken, for the record: Part C only tests centre cropping. A human moving closer reframes deliberately, aiming at dense patches; that selective framing retains more than centre cropping but introduces sampling bias. It is a separate experiment and outside this article's conclusions.

## 4. Limitations and open questions

- Upscaling is digital resampling, not a real optical approach: a real camera moving closer also changes perspective, depth of field, occlusion and lighting angles. This study isolates geometric scaling and framing only. The interpolation check (three interpolations, identical results) shows the conclusions do not hinge on one interpolation algorithm; it is not a substitute for optical validation.
- The simulator places targets without overlap (at least 8 px apart) and with an edge margin: merging had no conditions to occur, and retention is systematically optimistic. Under real dense, edge-touching distributions both effects will be worse; the numbers here are this pipeline's readings on this distribution.
- The background is nearly noise-free: with min_area fixed, its relative threshold loosens as s grows (at s=3 it is effectively a ninth of baseline), which in a cluttered real background could admit more spurious contours. This experiment has no clutter to admit; the risk is identified, not measured.
- s stops at 3: beyond that, the kernel's relative size keeps shrinking and the regime where a single target fills the whole frame (petal texture becoming internal contour structure) is untested. The crop part's retained sample at s=3 is only 31 targets, so its proportions should be read to one significant figure.
- The flipped sign of the area drift is an interpretation consistent with the data (different edge-effect terms dominating in the two directions); no factor-isolation experiment was run (for example, measuring interpolation drift with morphology switched off), so it is not stated as settled.
- The standing boundary applies: one simulator, one detector, four scenes. Transfer to the broader class of area-threshold-plus-morphology pipelines is inference, not cross-pipeline measurement.

## 5. References

- Bloom-Counter repository (MIT, contains all code used in this study): https://github.com/Ezra-Zhao/Bloom-Counter . Detector detector/color_segmentation.py (the min_area, bloom_area_min and morph_kernel parameters, the HSV mask and the morphology pipeline); simulator simulator/generate.py (placement spacing and margin rules in the _place function).
- Predecessor: this repository's "Thresholds Are Not Constants, They Are Functions of Distance: Calibration Drift in an Area-Threshold Detector" (2026-10-20), whose limitations section posed the zoom-in prediction tested here; scenes, seeds and scoring are identical. "Upsampling Back to Full Size Wins: Input Resampling vs Parameter Scaling" (2026-10-24) and "Can You Trust an Estimated s?" (2026-10-25) are the series' other two branches.
- Experiment script and raw data for this article: this project's data/2026-10-26-bloom-zoom-in-bench.py and data/2026-10-26-bloom-zoom-in-bench.json (Part E: 6 scales × 3 strategies plus ablations, threshold sweep, area drift and interpolation check; Part C: framing ledger, dual-truth-set scoring and detection attribution).
- OpenCV documentation: resize and interpolation flags (INTER_LINEAR / INTER_CUBIC / INTER_NEAREST), morphological operations and structuring elements: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. All code and experiments described here are the author's own clean-room work: the detector, the simulator and the scaling bench scripts were written by the author, and the experiments were run locally on synthetic data. No client data, client images or identifiable information are involved.
