# The Total Was Right and the Structure Was Wrong: Stress-Testing a Flower-Counting Pipeline Against Light and Occlusion

Author: Guangyi Zhao

## 1. The problem

A crop-counting pipeline does not deliver one number. For yield estimates and labor scheduling, a grower needs two: how many flowers have opened, and how many buds are still closed. The first drives this week's harvest, the second next week's. The real deliverable is the split, not the sum.

My open-source project Bloom-Counter does exactly this: photos in, HSV color segmentation plus contour analysis out, with per-image bloom and bud counts aggregated by region and date. Its README carries a handsome scorecard: 6 simulated photos, 357 flowers, 99.7% detection recall. This article starts from an uncomfortable claim: that 99.7% proves nothing. Two reasons, both sitting in the code for anyone to check.

First, the simulator and the detector were tuned to each other. A comment on line 23 of `simulator/generate.py` says it plainly: the flower colors in BGR are "tuned to sit inside the detector's HSV petal ranges." The generator paints flowers to the detector's taste; the detector then counts them. A perfect score is structural.

Second, the simulator's `_place` function uses rejection sampling to guarantee that no two flowers ever overlap, and the demo's scoring in `examples/demo.py` is (detected blooms + buds) / (true blooms + buds) — totals only, no per-object matching, no per-class breakdown.

A real greenhouse inverts both assumptions: light swings across the day, leaves occlude as a matter of course, and flowers grow in clusters. So I took the unmodified detector and systematically broke the simulator's two hidden assumptions, measuring how it fails first, how badly, and whether two cheap remedies actually help.

## 2. Method

Detector: the stock `ColorSegmentationDetector` (`detector/color_segmentation.py`), parameters untouched: `min_area=120` px², `bloom_area_min=900` px² (a connected component at or above 900 px² counts as a bloom, below it as a bud), morphology kernel 7. It thresholds pink, white, and yellow petal ranges in HSV, applies closing and opening, then counts components.

Scenes: four 1280×960 images from the repo's own simulator (seeds 101/202/303/404), 210 objects in total: 134 blooms, 76 buds, each with a ground-truth center and radius.

Scoring: not the totals ratio. Greedy center-distance matching — a detection counts as a hit only if its center lands within max(38 px, 1.1 × radius) of a ground-truth object of the same label — yielding precision, recall, and F1, with bloom recall and bud recall reported separately, micro-averaged over the four scenes. Sanity check first: on the untouched scenes this stricter scoring still returns precision = recall = F1 = 1.000 with zero false positives. The baseline is perfect because the pair is co-tuned, which is the point.

Two stress groups:

- Lighting: parametric whole-image transforms standing in for time-of-day and weather: gamma 0.6 / 1.6 / 2.2, exposure −50 (α=0.78, β=−50) and overexposure +60 (α=1.25, β=+60), a left-to-right shadow gradient (0.35→1.0), a half-frame shadow (left 45% at ×0.40), a warm color cast (B×0.72, R×1.18), and low light (gamma 1.9 plus Gaussian noise σ=12).
- Occlusion: leaf-colored ellipses painted over 60% of objects at their true centers, with radius 0.5 / 0.8 / 1.1 × the object's radius; and extra blooms drawn beside existing ones at offsets of 2.2 / 1.6 / 1.2 / 0.8 / 0.45 × radius (+10 blooms per scene, true blooms rising to 174) to simulate clustering.

Two remedies: gray-world white balance followed by CLAHE on the V channel as preprocessing; and an area-based split estimator that, for bloom components much larger than the median single-bloom box area (5,889.5 px² in this batch), adds counts proportional to area.

Raw data and scripts: `data/2026-10-17-bloom-bench.json` and `data/2026-10-17-bloom-bench.py`, reproducible with one command in the repo's virtualenv.

## 3. Results

### 3.1 Lighting: demotion before disappearance

| Condition | Recall | Bloom recall | Bud recall | Blooms found / 134 | Buds found / 76 | Total error |
|---|---|---|---|---|---|---|
| Clean | 1.000 | 1.000 | 1.000 | 134 | 76 | 0.0% |
| Gamma 0.6 (brighter) | 1.000 | 1.000 | 1.000 | 134 | 76 | 0.0% |
| Gamma 1.6 (darker) | 1.000 | 1.000 | 1.000 | 134 | 76 | 0.0% |
| Low light, gamma 1.9 + noise | 1.000 | 1.000 | 1.000 | 134 | 76 | 0.0% |
| Gamma 2.2 (much darker) | 0.576 | 0.336 | 1.000 | 45 | 179 | +6.7% |
| Exposure −50 | 0.810 | 0.702 | 1.000 | 94 | 116 | 0.0% |
| Overexposure +60 | 1.000 | 1.000 | 1.000 | 135 | 90 | +7.1% |
| Shadow gradient 0.35→1.0 | 0.895 | 0.836 | 1.000 | 112 | 98 | 0.0% |
| Half-frame shadow ×0.40 | 0.905 | 0.851 | 1.000 | 114 | 96 | 0.0% |
| Warm cast | 0.638 | 1.000 | 0.000 | 135 | 25 | −23.8% |

Look at exposure −50 and the two shadow conditions: total error 0.0%. Under the repo demo's scoring, all three are perfect runs. Yet a quarter to a sixth of the blooms are gone, and twenty-odd phantom buds appeared. Splitting the first half-shadow scene makes it vivid: of 20 objects inside the shadow, 70% were recovered; of 28 in the light, all of them.

The mechanism is easy to trace. Dimming eats the petal mask from the edges first: V falls below the pink range's floor, the mask shrinks, and the component's area shrinks with it. Once area crosses below the 900 px² line, the object does not vanish — it is reclassified as a bud. This classifier demotes before it deletes: at gamma 2.2 only 45 blooms remain while "buds" swell to 179, and the total is off by just +6.7%.

The warm cast fails in the opposite direction. Blooms survive intact (white and yellow ranges back them up), but bud recall goes to exactly zero: buds exist in only one color range, pink, and the cast pushes their hue out of it. All 76 buds disappear; the 25 detected "buds" are fragment false positives.

Overexposure fails differently again: recall holds at 1.000 but precision drops to 0.933, with 15 false positives — washed-out leaf fragments impersonating buds. Getting brighter does not lose objects; it manufactures them.

The good news is real, too: gamma 0.6 brightening, darkening up to gamma 1.6, and low light with noise leave the detector untouched. Its robust zone is wider than I expected. Between the intact 1.9 run and the collapsed 2.2 run the failure threshold sits somewhere in that interval — but sampling is sparse, and the 1.9 run also carried noise rather than being a pure gamma control, so I cannot pin the cliff down.

### 3.2 Preprocessing: fixes global shifts, breaks clipped and noisy images

Gray-world white balance plus CLAHE on V splits cleanly by failure type (false positives below are totals across the four scenes):

| Condition | Recall before | Recall after | F1 after | Cost |
|---|---|---|---|---|
| Gamma 2.2 | 0.576 | 1.000 | 0.981 | 8 FP |
| Warm cast | 0.638 | 1.000 | 0.961 | 17 FP |
| Shadow gradient | 0.895 | 1.000 | 0.963 | 16 FP |
| Half-frame shadow | 0.905 | 1.000 | 0.959 | 18 FP |
| Gamma 1.6 (was perfect) | 1.000 | 1.000 | 0.970 | 13 FP |
| Overexposure +60 | 1.000 | 0.319 | 0.404 | Recall collapse |
| Low light + noise (was perfect) | 1.000 | 0.991 | 0.726 | 155 FP |

For global brightness and hue shifts the pipeline recovers almost everything. It is not free: on images that were already fine it invents 13–18 phantom buds. On overexposed images the highlights are clipped — the information is gone — and recall falls from perfect to 0.319. On the noisy low-light image it produces 155 false buds. One honest caveat: white balance and CLAHE were tested as one pipelined package, never ablated separately, so I cannot say which step does the damage in the bad cases. The operational conclusion stands either way: gate the preprocessing. Measure the frame first (mean luminance, cast statistics); turn it on only when a global shift is actually present.

### 3.3 Occlusion: small targets die first, and fragments impersonate buds

| Cover radius | Covered recall | Uncovered recall | Bloom recall | Bud recall | FP | Total error |
|---|---|---|---|---|---|---|
| 0.5 × radius | 0.690 | 1.000 | 1.000 | 0.382 | 4 | −20.5% |
| 0.8 × radius | 0.207 | 1.000 | 0.530 | 0.290 | 287 | +81.0% |
| 1.1 × radius | 0.014 | 1.000 | 0.321 | 0.290 | 98 | −22.4% |

At half-radius cover, every uncovered object is still found, but 31% of covered ones are gone — and buds take the hit. A bud's radius is only 11–17 px; cover its center and the surviving fragments fall below `min_area=120` and are discarded as noise. Blooms, being larger, keep a ring of petals and survive the same treatment.

At 0.8 × radius comes the strangest number in this study: total error +81%. Occlusion does not only delete; it creates. A partly covered bloom breaks into fragments, each landing in the 120–900 px² band, each booked as a bud: 297 buds detected against 76 real. A heavily leafed photo will undercount blooms and overcount buds at the same time — and the overcount is the bigger error.

One parameter ablation: dropping `min_area` from 120 to 40.

| Cover | min_area | Recall | Precision | Bud recall | FP |
|---|---|---|---|---|---|
| 0.5 × | 120 | 0.776 | 0.976 | 0.382 | 4 |
| 0.5 × | 40 | 0.981 | 0.808 | 0.947 | 49 |
| 0.8 × | 120 | 0.443 | 0.245 | 0.290 | 287 |
| 0.8 × | 40 | 0.510 | 0.226 | 0.474 | 366 |

Under light cover, lowering the floor genuinely rescues buds — at ten times the false positives, flipping total error from −20.5% to +21.4%. Under heavy cover it buys almost nothing and adds fragments. It is a precision-for-recall trade that only pays in the light-occlusion regime, not a fix (script: `data/2026-10-17-bloom-minarea-ablation.py`, results merged into the same raw data file).

### 3.4 Overlap: clustering always undercounts; area-splitting works in one band

| Offset | Blooms found / 174 | Raw error | After split correction |
|---|---|---|---|
| 2.2 × radius | 139 | −35 | +27 |
| 1.6 × radius | 117 | −57 | +20 |
| 1.2 × radius | 120 | −54 | +10 |
| 0.8 × radius | 125 | −49 | −4 |
| 0.45 × radius | 132 | −42 | −11 |

Once two blooms touch, morphological closing welds them into one component, and every offset undercounts by 42–57 blooms. Area-splitting genuinely helps in the 0.8–1.2 × band (−49 → −4, −54 → +10). At wider offsets it overcorrects (+27 at 2.2 ×). The overcorrection is mostly the estimator's own doing: it rescales every bloom box by area, and single-bloom radius naturally varies from 30 to 49 px, so a large lone bloom gets rounded up into "one and a half." The wider the offset, the less true merging there is, and the more this systematic inflation dominates. A second confound: at 2.2 × offset in these dense scenes, the added bloom often lands on a third flower, so the raw −35 at that end mixes three-way merges and is not a clean pairwise reading.

Combined stress (gamma 1.6 plus 0.8 × leaf cover) leaves recall at 0.429; preprocessing lifts it only to 0.500. Preprocessing repairs global shifts. It cannot repair something physically hidden, and that boundary deserves to be stated plainly.

## 4. What I take from this

Four things a practitioner can lift directly:

1. Acceptance metrics for a counting pipeline must be per-class, per-object matched precision/recall, plus an explicit error on the bloom-to-bud ratio. Totals alone certified three conditions in my runs as 0.0% error while a sixth to a quarter of the blooms were already wrong. I will change the repo demo's scoring and annotate the README's 99.7% with its methodology.
2. Under the two most common degradations — dimming and moderate occlusion — an area-threshold classifier's dominant failure is class migration, not misses. Watching the class mix drift is an earlier alarm than watching the total. The boundary matters: under extreme underexposure and 1.1 × cover, objects simply vanish (covered recall 0.014) and there is no migration to watch.
3. Preprocessing (white balance, CLAHE) should be conditional, triggered by measured global shift. On clipped or noisy input it is a net harm.
4. Small-class targets need their own protection strategy under occlusion. Lowering `min_area` only pays under light cover. The candidate beyond a single frame is cross-day tracking — yesterday's bud, hidden by a leaf today, restored from the time series. That idea is not validated by anything here (every experiment is a static single frame; wind sway and viewpoint shift are untested). It is a direction the failure modes point to, and it moves the roadmap's video / multi-frame de-duplication up in priority.

Why not jump straight to a trained detector? The `BloomDetector` interface is already there; swapping the backend touches nothing else. But without real annotated photos there is nothing to train on. What this study does is map the baseline's failure boundaries under light and occlusion, so that any future backend has to pass the same destructive test suite, with the numbers side by side.

## 5. Limitations and open problems

- Everything is still synthetic: program-drawn flowers, flat-painted leaf occluders, global parametric lighting. Real greenhouse light is directional and spectral; real leaves have texture and translucency. Treat these numbers as a lower bound on failure direction and magnitude, not as field accuracy.
- Lighting transforms are whole-image; local specular reflection and lens flare are not modeled.
- The white-balance/CLAHE pair was never ablated separately; their individual contributions and harms are entangled.
- At 2.2 × offset the overlap group is confounded by third-flower merges: the raw error there mixes them in, and the split correction overshoots (+27). Neither end of that row is a clean reading.
- Four scenes, 210 objects, no confidence intervals computed. The claims I kept are the ones consistent across conditions; exact point values (such as where the gamma cliff sits) need denser sampling.
- The split estimator's unit area is the median from this same batch; it must be recalibrated per cultivar and camera distance, and I have not tested that transfer.
- Real-photo validation is still missing. The roadmap's trained detector backend and a real annotated set have not been started. That remains the largest open problem on this line.

## 6. References

- Bloom-Counter repository (MIT; all code used here): https://github.com/Ezra-Zhao/Bloom-Counter . Detector: `detector/color_segmentation.py`; the co-tuning comment is on line 23 of `simulator/generate.py`, non-overlap placement in its `_place` function; totals-only scoring in `examples/demo.py`.
- This study's scripts and raw data: the companion `data/2026-10-17-bloom-bench.py`, `data/2026-10-17-bloom-minarea-ablation.py`, and `data/2026-10-17-bloom-bench.json` (4 scenes, seeds 101/202/303/404, fixed and re-runnable), archived with the article in the tech-deep-dives repository.
- OpenCV documentation: HSV color space and `inRange`, morphological operations, `createCLAHE`: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. All code and experiments described here are the author's own clean-room work: the detector, the simulator, and the stress-test scripts were written by the author, and the experiments ran on locally generated synthetic data. No client data, client imagery, or identifying information is involved.
