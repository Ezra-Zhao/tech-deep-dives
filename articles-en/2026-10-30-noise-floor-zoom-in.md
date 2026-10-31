# Zoom In Threefold and the Floor Leaks a Whole Stratum: A Noise-Floor Measurement for an Unscaled min_area

Author: Guangyi Zhao

## 1. Problem and background

My 2026-10-26 zoom-in study (s > 1) found that only the classification threshold collapses when a camera moves closer; min_area and the morphology kernel seemed not to matter. That article flagged one risk it could not measure: its background was nearly noise-free. With min_area held fixed, its *relative* threshold loosens as s grows — at s=3 it is effectively one ninth of the baseline floor (120/9 ≈ 13 px²). On a clean background there is nothing to let through. In a real flower bed, small clutter in the petal colour ranges (fallen petals, coloured fragments, tag pieces) only needs to be magnified past that loosened floor to become a false detection. This article pays that debt.

Three measurable questions. First, how does the pass rate of sub-floor clutter (nominal area below min_area = 120 at baseline scale) grow with s under a fixed min_area — gradual, or switching on stratum by stratum? Second, does scaling min_area by s² hold the floor, and where exactly does what leaks, leak? Third, how much does the relatively shrinking morphology kernel (a fixed kernel of 7 is one third its relative size at s=3) contribute independently — comparing kernel scaling against floor-only scaling separates the two mechanisms.

The design was frozen before the run (data/2026-10-30-noise-floor-prereg.md), with six preregistered predictions scored at the end. A pilot probe on a blank green background was used only to choose size strata that sit just below the floor at s=1; pilot data is not part of the main results.

## 2. Method

Same base as the earlier articles: the simulator's four 1280×960 scenes (seeds 101/202/303/404), 210 ground-truth objects (134 blooms, 76 buds), the Bloom-Counter colour-segmentation pipeline (base parameters min_area = 120, bloom_area_min = 900, kernel 7), greedy centre matching with label agreement, micro-averaged over four scenes.

Clutter is planted in memory (no second JPEG pass): 64 items per scene, 256 in total. 224 are visible-colour items in the exact simulator colours that feed the detector's three HSV ranges in `_petal_mask` (pink/white/yellow: 76/76/72), half circles and half squares (square side round(r·√π) so nominal areas match the same radius stratum). Strata by equivalent radius: sub-floor r = 3/4/5/6 (circle nominal areas 28.3/50.3/78.5/113.1, all below 120), 128 items; mid r = 7/10 (153.9/314.2), 64; large r = 14 (615.8), 32. A further 32 blue circles (r = 10) are a negative control — blue hue ≈ 120 sits outside the pink range (125–170), the white range demands saturation ≤ 70, and the yellow range is 18–40, so blue should never pass. Placement is rejection-sampled: at least 20 px clear of every ground-truth object and of previously planted items, and at least 30+r px from the frame edge. Clutter never overlaps or touches a flower, by design: this study measures floor admission, not occlusion merging (see Limitations).

Scaling is pure geometric enlargement (INTER_LINEAR, canvas grows with the image), s ∈ {1.0, 1.25, 1.5, 2.0, 2.5, 3.0}. Four parameter arms:

- A, fixed floor: min_area = 120, kernel 7.
- B, scaled floor: min_area = 120·s², kernel 7.
- C, floor and kernel scaled: min_area = 120·s², kernel the odd approximation of 7·s.
- D, fully fixed reference: nothing scaled.

In arms A/B/C, bloom_area_min is always scaled by s² to isolate the variable: the 2026-10-26 study proved an unscaled classification threshold produces bud→bloom migration, which would contaminate the false-positive count. Arm D keeps everything fixed to show the two bills stacked, as in a real "change nothing" deployment.

A planted item counts as *passed* when a detection not consumed by ground-truth matching greedily matches its scaled centre (any label, tolerance max(18·s, 1.2·r·s+6)). I also measure *morphology survival* separately: replicate the detector's mask plus morphology (close, then open) and check whether any contour reaches the item's centre. Survival is not passing — the min_area filter sits between them, and the gap between the two numbers is what the floor actually filters. Clean scenes (no clutter) are run under arms A/B as a sanity control.

One planting correction affects every "sub-floor" number below, and I am stating it up front rather than burying it: square rounding makes the r=6 squares 11 px on a side, nominal area 121 — 0.8% *above* the 120 floor. By planted area they were never sub-floor; only the radius label put them there. Wherever scaled-floor leakage is discussed, I also give the nominal-area correction: the true sub-floor set (nominal area < 120) has 112 items, excluding those 16 squares. Radius×shape cross-counts were not stored per item; the correction is inferred from the marginals, which is sound here because the mid/large strata pass at 100% in every arm and scale (below), so shape marginals minus the saturated 48+48 give the sub-floor shape split. The inference and corrected table are in data/2026-10-30-noise-floor-posthoc.json.

## 3. Results

### 3.1 Baseline: at s=1 the floor holds — but everything above it passes anyway

Clean control first: arms A and B score F1 = 1.000 at all six scales (TP 210, FP 0), matching the earlier S2 result.

With clutter at s=1, all four arms coincide by construction: 306 detections, TP 210, FP 96, precision 0.6863, count inflated by +45.7%. The FP composition is clean: sub-floor 0/128, blue control 0/32, mid plus large 96/96 — all pass. At baseline distance the floor itself leaks nothing. But any clutter larger than the floor is completely invisible to an area-only sieve, at any distance. That is this pipeline's standing cost — 96 FPs at this article's planted density — and it is worth memorising before the scaling discussion, because arm B's plateau below is exactly this baseline.

### 3.2 Arm A: not a gradual leak — strata switching on

| s | Sub-floor passed (/128) | r=3 | r=4 | r=5 | r=6 | Precision | F1 | Detections (truth 210) |
|---|---|---|---|---|---|---|---|---|
| 1.0 | 0 (0%) | 0/32 | 0/32 | 0/32 | 0/32 | 0.6863 | 0.814 | 306 |
| 1.25 | 45 (35.2%) | 0 | 0 | 13 | 32/32 | 0.5983 | 0.7487 | 351 |
| 1.5 | 72 (56.3%) | 0 | 8 | 32/32 | 32/32 | 0.5556 | 0.7143 | 378 |
| 2.0 | 101 (78.9%) | 5 | 32/32 | 32/32 | 32/32 | 0.5160 | 0.6807 | 407 |
| 2.5 | 128 (100%) | 32/32 | 32/32 | 32/32 | 32/32 | 0.4839 | 0.6522 | 434 |
| 3.0 | 128 (100%) | same | same | same | same | 0.4839 | 0.6522 | 434 |

Admission is a staircase, one size stratum at a time. The switch-on point is predictable from the area law: an item of nominal area a crosses 120 at s* = √(120/a) — for circles, 1.03 (r=6), 1.24 (r=5), 1.55 (r=4), 2.06 (r=3). Observed full switch-on lags the prediction by about half a step (r=6 full at 1.25, r=5 partial 13 at 1.25 and full at 1.5, r=4 partial 8 at 1.5 and full at 2.0, r=3 partial 5 at 2.0 and full at 2.5). The lag is consistent with opening erosion: post-morphology contour areas run below nominal × s² (at s=1.25 the median surviving sub-floor contour is 92.0 against a nominal median × s² of about 100), so the upper tail of each stratum crosses first — the same shape the 2026-10-26 migration showed.

By s=2.5 every planted sub-floor item passes. Arm A reports 434 detections against 210 true objects (+106.7%), precision 0.4839 — more than half of what it reports is false. Ground-truth recall stays 1.000 throughout: nothing real is lost; what breaks is the count and precision. As with the zoom-in migration, a recall-only monitor is blind in this direction too.

### 3.3 Arms B and C: the scaled floor holds, and what leaks sits in its drift band

| s | B sub-floor (radius label, /128) | B true sub-floor (nominal, /112) | C sub-floor (radius label, /128) | B precision | C precision |
|---|---|---|---|---|---|
| 1.0 | 0 | 0 | 0 | 0.6863 | 0.6863 |
| 1.25 | 5 | 0 | 5 | 0.6752 | 0.6752 |
| 1.5 | 16 | 0 | 8 | 0.6522 | 0.6688 |
| 2.0 | 18 | 2 | 18 | 0.6481 | 0.6481 |
| 2.5 | 18 | 2 | 15 | 0.6481 | 0.6542 |
| 3.0 | 18 | 2 | 18 | 0.6481 | 0.6481 |

Preregistered prediction P1 said arm B would leak "about zero" at every scale. By radius label it did not: B leaks 16–18 items from s=1.5 on. Decomposing that leak reverses the reading. Every leaked item is in the r=6 stratum (r=3/4/5 leak 0/32 in arm B at every scale), and 16 of them are the nominal-121 squares — above the floor by 0.8%, scaled in step with it, passed correctly by the area law. The mislabelling was mine, not the floor's. Under the nominal correction, arm B's true sub-floor leakage is 0 up to s=1.5 and 2/112 (1.8%) from s=2.0 on, then flat. Those last 2 are r=6 circles (nominal 113.1, 5.8% below the floor): passing requires their measured contour area to exceed nominal × s² by at least 6.1%. The 2026-10-26 study measured zoom-in contour drift for bud-sized objects at +1.8% to +7.1%, so these two sit at the top edge of the known drift band — consistent with the data, though I did not isolate their individual contour composition, and closing merging with neighbouring texture is an alternative I cannot exclude (see Limitations). The actionable statement survives either way: the scaled floor holds not as a mathematical line but as a band about ±7% wide. Clutter whose nominal area lies within ±7% of the floor can go either way and should be treated as uncertain.

Arm C differs from B in exactly one clear place: at s=1.5, C leaks 8 against B's 16, all r=6 squares — their scaled area, 121×2.25 = 272.3, sits only 0.8% above the scaled floor of 270, precisely where a kernel of 11 erodes a little more and pushes half of them back under. Everywhere else the arms agree or differ by at most 3 (s=2.5: C 15, B 18), with no systematic advantage. Kernel scaling is not the lever for the noise floor; the next section shows why.

Arm B's precision slides only from 0.6863 to 0.6481 and then pins: detections flat at 324 from s=2.0, overcount a flat +54.3%. Against arm A's 434 and +106.7% at s=3, scaling the floor saves exactly the sub-floor stratum's 110 FPs (of 224 visible items, B passes 114, A passes all 224). B's remaining overcount is not floor business: 96 mid/large items plus the 18 r=6-label items — the standing cost of §3.1.

### 3.4 Mechanism: the shrinking kernel admits contours; the floor admits detections

| s | Sub-floor morphology survival, k=7 (/128) | Survival, kernel scaled (/128) | Median surviving contour area, k=7 |
|---|---|---|---|
| 1.0 | 96 (75.0%) | 96 (75.0%) | 63.5 |
| 1.25 | 126 (98.4%) | 95 (74.2%) | 92.0 |
| 1.5 | 128 (100%) | 94 (73.4%) | 138.5 |
| 2.0 | 128 (100%) | 96 (75.0%) | 286.5 |
| 2.5 | 128 (100%) | 96 (75.0%) | 436.5 |
| 3.0 | 128 (100%) | 96 (75.0%) | 644.5 |

Under a fixed kernel, sub-floor morphology survival climbs from 75% at s=1 to 100% by s=1.5 — the r=3 stratum that opening erases wholesale at baseline escapes the fixed kernel's erosion radius as soon as it is magnified. The median surviving contour area grows from 63.5 to 644.5, a factor of 10.2 against the s² factor of 9 — about 13% above the area law (63.5×9 = 571.5 vs 644.5 observed), in the same direction as the zoom-in positive area drift. With the kernel scaled, survival pins at 73–75% (94–96 items) at every scale: the r=3 stratum stays erased and the relative morphology floor is preserved exactly. (Its median surviving area at s=3, 745.0, is higher than k=7's — a survivor-pool composition effect, not a weaker kernel.)

The key comparison: survival differs by 25 percentage points between kernel choices (128 vs ≈96 from s=1.5), yet final pass counts under B and C are nearly identical. Survival is not passing. The extra contours the fixed kernel lets live grow in step with s², and the scaled min_area removes them wholesale at the next step. The binding constraint on admission is the area floor, not morphology survival — the exact mirror image of the zoom-out direction, where the kernel is the killer (contours are erased before the floor ever sees them, and the information is gone) while here the kernel merely delivers contours to a door that area controls. Same parameter pair, opposite binding constraint per direction: the third time this series has measured "the s² law is symmetric; the failures are not."

### 3.5 Arm D: change nothing, and the two bills stack

Arm D's sub-floor admission is identical to A's at every scale (the floor bill and the classification bill do not interact — itself a small verification), and migration stacks on top: 21 buds relabelled at s=1.5 (TP 189), all 76 by s≥2.0 (TP 134, recall 0.6381). At s=3 its 300 FPs reconcile exactly: 224 clutter passes plus 76 migration-generated false blooms (fp_unmatched_to_clutter is precisely 76). Arms A/B/C reconcile just as cleanly: fp_unmatched_to_clutter is 0 at every scale, so every FP corresponds to a planted item — there are no unexplained detections. The blue control passes 0/32 in every arm and scale and its morphology survival is 0 too: all leakage is area-floor business, with no colour-drift contribution.

### 3.6 Preregistration scorecard

P1 (A monotone rising; B/C about zero): A holds (0 → 35.2% → 56.3% → 78.9% → 100%). B/C fail by radius label and approximately hold under the nominal-area correction (true leakage 0/0/0/2/2/2); the leak composition is fully disclosed in §3.3, and the miss traces to the preregistration not anticipating the 121 rounding — a design blemish, not a data problem. P2 (mid/large pass everywhere): holds, 96/96 at every scale. P3 (blue control all zero): holds. P4 (clean A/B perfect): holds. P5 (A precision falls with s, B/C flat, recall unaffected): holds — A to 0.4839, B/C pinned at 0.648–0.669, recall 1.000 in A/B/C throughout. P6 (k=7 survival rises with s but the scaled floor catches it; C ≈ B): holds, with one disclosed exception in the marginal band at s=1.5 (C 8 vs B 16).

## 4. Analysis and trade-offs

1. **At zoom-in, min_area must scale with s².** The cost asymmetry is extreme. Unscaled, the whole sub-floor stratum is admitted by s=2.5, precision falls from 0.686 to 0.484, and the count error doubles to +106.7%. Scaled, the change costs one parameter and leakage drops to 1.8% inside a drift band. The 2026-10-26 statement that min_area "makes no difference" zooming in holds only on a background with no visible-colour clutter below the floor; real scenes should be assumed to have such clutter, so scale the floor first and discuss the rest afterwards.
2. **Admission is a staircase with a computable warning line.** Each size stratum switches on near s* = √(120/a), lagging by about half a step (opening erosion). Operationally: inventory the smallest visible-colour clutter in a scene, compute the s at which it switches on, and either do not move the camera past that s or have floor scaling in place before crossing it. That turns "the noise got worse" into a line you can calculate in advance.
3. **The floor holds as a ±7% band, not a line.** The nominal-121 squares (+0.8%) pass under the scaled floor, and two nominal-113 circles (−5.8%) were carried over the line by positive drift. Adding margin to the floor (setting it one drift-width higher) would narrow the band, but it would also threaten real buds whose area distribution's lower tail may overlap the same band — I did not measure that overlap, so I am not prescribing the margin here; it is the missing measurement between this result and a deployable rule.
4. **Do not spend kernel scaling on the noise floor.** A 25-point survival gap produced almost no pass gap: effort spent scaling the kernel for clutter defence is effort spent on a non-binding step. The kernel's bill comes due in the zoom-out direction, where it drives deletion-type failure. Decide where each parameter earns its keep by asking which failure type it governs — deletion or admission — and which step actually binds.
5. **Do not let the scaling discussion hide the standing cost.** At this planted density, precision at s=1 is already only 0.686: 96 above-floor items that an area sieve cannot see at all. Floor scaling fixes the increment (110 sub-floor admissions); the standing 96 need shape, texture, or finer colour discrimination — a different pipeline change, out of scope here, but any citation of this article's precision numbers should carry the baseline composition with it.

## 5. Limitations and open questions

- Clutter items are solid-colour circles and squares in the detector's own target colours — the harsh side for a colour-segmentation pipeline (real fallen petals *are* that colour, but real clutter usually has texture, shadow, and translucent edges). Pass rates transfer to "clutter in target colours" as a class; absolute precision belongs to this planted density (64 items per scene against ≈52 true objects — deliberately dense stress, not a field-density estimate).
- Clutter is forcibly separated from flowers (≥20 px): real clutter can touch or overlap a flower, and contour merging would then damage recall and classification too. This article's "recall 1.000 throughout" holds only under separation. Adjacent/occluding clutter is the next experiment.
- The r=6-square nominal-121 blemish is disclosed in §2 with a corrected accounting; the shape split is inferred from marginals under the empirically saturated mid/large strata (verified at all six scales), not from per-item cross-counts. Had any mid/large scale not saturated, the inference would not hold.
- The mechanism behind arm B's two r=6-circle leaks is not isolated: positive area drift suffices (+6.1% needed; the measured drift band tops out at +7.1%), but closing merging with adjacent foliage texture could produce the same area, and I did not re-measure those two contours individually.
- The floor-margin versus true-bud lower-tail trade-off (point 3 in §4) is unmeasured: how much the bud area distribution's low end overlaps the drift band decides whether a margin is even available. That is the last dataset needed before this result becomes a prescription.
- Digital zoom rather than optical approach, one simulator and one detector family, four scenes — the standing boundaries of this series, not repeated here.

## 6. References

- Bloom-Counter repository (MIT; all code used here): https://github.com/Ezra-Zhao/Bloom-Counter . Detector: detector/color_segmentation.py (the three HSV ranges in `_petal_mask`, min_area, and the morphology pipeline); simulator: simulator/generate.py (scene and placement rules).
- Previous article in this repository: "Moving closer is simpler: the s>1 symmetry test" (2026-10-26), whose Limitations section flagged the noise-floor risk measured here; same scenes, seeds, and scoring rules. Its area-drift figures (buds +1.8% to +7.1%) supply the drift band used in §3.3.
- Preregistration, bench script, and raw data for this article: data/2026-10-30-noise-floor-prereg.md (frozen before the run), data/2026-10-30-noise-floor-bench.py, data/2026-10-30-noise-floor-bench.json (all four arms × six scales: admission, scoring, morphology survival), data/2026-10-30-noise-floor-posthoc.json (nominal-area correction and its inference notes).
- OpenCV documentation: morphologyEx (MORPH_CLOSE / MORPH_OPEN), findContours and contourArea: https://docs.opencv.org/4.x/ .

---

Author: Guangyi Zhao. All code and experiments described here are the author's clean-room work: the detector, simulator, clutter planting, and measurement scripts were written by the author, and the experiments ran on locally generated synthetic data. No client data, client images, or identifiable information is involved.
