# Pressed Harder, Hurt Less: The Harm Curve for Adjacent Clutter Peaks at a Light Touch, Not at Deep Overlap

Author: Guangyi Zhao

## 1. Problem and background

In the 2026-10-30 installment of this series I planted clutter at least 20 pixels away from every true flower, and I left a caveat in the limitations: real clutter can touch or lie on top of a flower, contour merging would then damage recall and classification together, and that article's perfect recall held only under separation. This article pays that debt. Three measurable questions: at what spacing does merging switch on; once merged, what exactly is damaged — misses, relabeling, or just extra false positives; and what role does the morphological closing kernel play in the curve?

The most counterintuitive result first: the harm does not peak at the deepest overlap. With clutter pressed 18 pixels into a flower, all 112 hosts came through unharmed. Pressed only 3 pixels in, the bud relabeling rate hit its maximum of 14.3%. The reason is a product of two curves. The deeper the press, the less clutter area sticks out beyond the host's silhouette (median added area falls from 437 at a light touch to 186 at the deepest press), and relabeling needs that added area to push a bud over the 900 px² classification threshold. Pressed deep, most of the disc hides inside the silhouette and cannot push anything. Between shallow press and light touch, the added area is nearly the whole disc while merging still holds, so the product peaks. At the other end, fully separated clutter (gap 35) does zero classification damage but turns into 112 independent false positives and drags precision to 0.652 — separation bills the precision account, not the classification account. The spacing with the most accurate total count (deep press, exactly 210 detections) is the one whose structure is easiest to misread, a mirror image of this series' first finding: right total, wrong structure.

The design was frozen before the run (data/2026-11-07-adjacent-clutter-prereg.md), with six pre-registered predictions scored in §3.6: two full hits, three halves, one miss — and the miss (P3) is exactly where the counterintuitive result comes from.

## 2. Method

Same base as the series: the simulator's four 1280×960 scenes (seeds 101/202/303/404), 210 ground-truth targets (134 blooms, 76 buds), and the Bloom-Counter color-segmentation pipeline (min_area=120, bloom_area_min=900, kernel 7). This article runs at the baseline scale s=1 only; the variable is distance, not scale.

Hosts and clutter: 28 hosts per scene chosen by rule (14 blooms, 14 buds; 112 in total), each host required to have a planting direction in which even the widest-gap clutter touches no other target (best of 16 candidate directions). Each host gets one disc of clutter per condition image: a solid circle of radius 12 (nominal area 452.4; measured standalone contour area 406.0), colored in rotation with the simulator's own pink/white/yellow — precisely the detector's three petal-mask colors, the harshest side for a color pipeline. The gap is a signed edge-to-edge distance in {-18, -8, -3, 0, 2, 4, 6, 8, 12, 20, 35}; center distance = host nominal radius + 12 + gap, negative values meaning the disc is drawn over the host. Gap 35 is the separation control. One disclosure up front: gaps are defined on nominal radii, while real silhouettes are irregular petal outlines, so the true mask-edge distance varies by a few pixels per host — this is why the merge rate at nominal gap 0 is 84.8% rather than 100%.

Host outcomes use a contour method that replicates the detector exactly (mask → close → open → contours → area filter and the 900 threshold): if the contour containing the host center also contains the clutter center, the pair is merged; if that contour's label matches the host's true label the outcome is correct, otherwise migrated; no qualifying contour means lost. End-to-end detector runs give scene-level TP/FP/FN, and non-host recall is tracked separately (1.000 at every gap, §3.5): the isolation design produced no spillover damage. Two mechanism arms: a closing-only arm (opening fixed at 7; closing kernel none/3/7/11/15; merge rate only) and a whole-kernel detector arm (morph_kernel 3/11, close and open changed together; host outcomes).

## 3. Measurements

### 3.1 The merge curve: a transition band from 0 to 6 pixels, no hard line

Main arm (kernel 7), merge rate by gap: 100% at -18 and -8, 97.3% at -3, 84.8% at 0, 66.1% at 2, 36.6% at 4, 7.1% at 6, and 0 from gap 8 onward. Merging does not switch off at one spacing; it decays across 0–6 pixels, because hosts with the same nominal gap have different true edge distances (irregular silhouettes), each with its own switch-off point. The 50% crossing sits at gap ≈ 3.1. As a deployment rule at kernel 7: an 8-pixel edge clearance zeroes merging; 6 pixels leaves a 7.1% tail.

### 3.2 The harm curve: peak at gap=-3, all relabeling, only buds, only the largest buds

Host correct rate: 100% at both deep-press gaps, a minimum of 92.9% at -3, 95.5% at 0, 97.3% at 2, 99.1% at 4, back to 100% from 6 on. Lost is zero at every gap — merging never makes a host vanish; the only damage form is migrated. All migration is in bud hosts: all 56 bloom hosts are correct at every gap (a bloom's standalone contour area is at least 2179, far above the 900 threshold; added clutter only inflates it). Bud migration rate: 14.3% (8/56) at -3, 8.9% (5/56) at 0, 5.4% (3/56) at 2, 1.8% (1/56) at 4, zero elsewhere.

Locating all eight migrated buds at gap=-3 individually: every one is a largest-class bud (radius 15–16) with standalone area 457.0–499.5 and merged area 909.0–935.5, and every merged contour contains exactly that one true target (no bridging to neighbors). The background distribution explains the count: across all 76 buds, standalone area has median 343.8, 75th percentile 436.5, maximum 499.5 — buds typically sit 400+ below the threshold, and one disc's added area (§3.3) reaches only the top slice of that distribution. This is where pre-registered P3 lost: I estimated a ≥50% migration rate from "452 added, most buds pushed over," without first measuring how far the bud area distribution sits from the threshold. The correct computation is distributional: with added area A, the migrated are exactly those whose standalone area falls in [900−A, 900).

### 3.3 Added area: the other half of the harm curve

Merged contour area minus the host's standalone area (median over merged hosts): 186.0 at gap=-18, 360.8 at -8, 421.0 at -3, 434.0 at 0, 437.0 at 2, 437.5 at 4. The disc's standalone contour area is 406.0, yet the light-touch addition slightly exceeds it — closing fills the concave wedges on both sides of the neck, so the union's polygon area is about 7% more than the sum of its parts. Reading §3.1 and §3.2 together, the harm curve is a product: migrations ≈ merge rate × P(standalone area ∈ [900 − added(gap), 900)). Deep press fails on added area (186 cannot push even the largest bud over), separation fails on merge rate (zero), so the peak must sit between shallow press and light touch; measured, it sits at -3. The area bookkeeping also validates independently: merged area against the prediction "host alone + clutter alone − analytic overlap" has median relative deviation 0.1%–2.1% per gap, 90th percentile under 5.7% — merging's area consequences are computable, not chaotic.

### 3.4 End-to-end: merging hides false positives, separation stockpiles them

| gap | TP | FP | FN | precision | recall | detections (truth 210) |
|---|---|---|---|---|---|---|
| -18 / -8 | 210 | 0 | 0 | 1.000 | 1.000 | 210 |
| -3 | 202 | 11 | 8 | 0.948 | 0.962 | 213 |
| 0 | 205 | 22 | 5 | 0.903 | 0.976 | 227 |
| 2 | 207 | 41 | 3 | 0.835 | 0.986 | 248 |
| 4 | 209 | 72 | 1 | 0.744 | 0.995 | 281 |
| 6 | 210 | 104 | 0 | 0.669 | 1.000 | 314 |
| ≥8 | 210 | 112 | 0 | 0.652 | 1.000 | 322 |

The FP column reconciles exactly: FP = migrations + unmerged clutter, exact in 10 of 11 gaps (gap=4: 72 = 1 + 71; gap=-3: 11 = 8 + 3). Only gap=35 is off by one (111 measured vs 112 booked; not located individually, presumably two discs merging with each other; recorded as unisolated). The table puts both costs in one frame: closer in, clutter is "swallowed" by hosts and FP falls, but the swallowing mechanism is relabeling (FN rises); further out, classification is clean and the cost is one FP per disc and a +53.3% count inflation. For counting, separated clutter is the most expensive; for class structure, deep press is cheapest and the light-touch band is the worst. Decide which number your downstream consumes before deciding which end to fear.

### 3.5 The closing kernel: the threshold moves with the kernel, at about 60% of the naive rate

Closing-only arm (opening fixed at 7), 50% merge crossings: no closing -0.87, kernel 3 → 0.27, kernel 7 → 3.09, kernel 11 → 5.57, kernel 15 → 8.0. A linear fit gives crossing ≈ 0.64×kernel − 1.7: every +4 of kernel buys about 2.6 pixels of extra reach. Pre-registered P5 guessed gap* ≈ kernel − 1 (6 at kernel 7); the measurement is about 60% of that. An explanation consistent with the data is two-stage: closing dilation can indeed throw a bridge up to kernel−1 wide, but the fixed opening at 7 then erodes thin necks — a bridge must not only form, it must be thick enough to survive the opening, and the surviving threshold shrinks to about six-tenths. The whole-kernel arm confirms the division of labor: at morph_kernel=11 (open also grows) merging is well below the closing-only 11 arm (at gap=6, 20.5% vs 42.9%), because opening at 11 eats necks harder; whole-kernel 3 tracks closing-only 3 closely (55.4% vs 53.6% at gap=0).

Host outcomes in the whole-kernel arm give a one-sided result inside this bench: kernel 3 is never worse than kernel 7 at any gap (99.1% vs 95.5% correct at gap=0; 100% vs 97.3% at gap=2), and kernel 11 is never better (91.96% at both -3 and 0). Do not read this as "shrink the kernel": the kernel's day job in this detector is merging one flower's scattered petals into a single contour, and this bench's flowers are unbroken silhouettes — the benefit side of the kernel simply never appears here; only its cost side was measured. Whether to change the kernel needs the benefit side measured on fragmenting scenes first; this article issues no such prescription.

### 3.6 Pre-registration scorecard

P1 half: merge rates are 97.3% at -3 and 84.8% at 0, short of the "≈100% for gap≤0" wording (nominal-vs-true silhouette deviation, disclosed in §2); "≤10% at gap≥8" hit exactly (0). P2 full: at gap=35, host correct 100% and scene recall 1.000. P3 miss: the bloom half hit (100% ≥ 90%), but bud migration peaked at 14.3% against a predicted ≥50% — the error was not measuring the bud-area-to-threshold distance first (§3.2). P4 half: lost ≤5% and "migration is the dominant damage form" hit, but the curve is not the predicted monotone step at the threshold; it is a valley at -3. P5 half: threshold moves monotonically with the kernel, whole-kernel 11 sits below closing-only 11, whole-kernel 3 tracks closing-only 3 — all directions hit; the κ−1 magnitude missed, measured ≈0.64κ−1.7. P6 full: area bookkeeping median deviation ≤2.1%, well inside the 15% line.

## 4. Analysis and trade-offs

First, a computable answer to "how far must clutter stay from a flower": on this bench (kernel 7, baseline scale), 8 pixels of edge clearance zeroes merging and 6 pixels leaves 7.1%; for other kernels extrapolate with crossing ≈0.64×kernel−1.7 and keep one step of margin. Conversely, if spacing in deployment is uncontrollable, treat bud classification inside the 0–6 pixel band as untrustworthy — not uniformly, but stratified by area: only buds whose standalone area sits within ~450 below the threshold (here, the radius-15+ buds) can be pushed over. Report that band to downstream as suspect instead of treating merging as uniform noise.

Second, fear the right posture. Deep overlap (8+ pixels) does zero classification damage in this color pipeline, because same-color clutter hides inside the silhouette and its added area runs out. The dangerous posture is the almost-touching band (-3 to +4): merging is likely, added area is nearly the whole disc, and migration and false positives hand off there. An inspection checklist gains more from "is anything next to a flower" than from "is anything on top of a flower."

Third, the kernel is the merge threshold's knob, and it is not free. Enlarging it pushes the band outward (kernel 15: 50% crossing at 8 pixels, still 2.7% merging at 12); shrinking it shows only gains inside this bench because the fragmentation cost is absent by construction. The correct order is the series' standing discipline: size the kernel to the scene's petal fragmentation first, then price its merging reach with this article's threshold law, then decide.

Fourth, for counting consumers, book separated clutter separately: at gap≥8 the 112 discs contribute +53.3% count inflation at precision 0.652. That is not a merging finding and not new (the 2026-10-30 baseline at s=1 has the same numbers), but with both curves now on one set of axes the point is sharper: the same clutter charges the FP account when far and the migration account when near, and no spacing is free. Which account you can afford depends on whether downstream reads totals or structure.

## 5. Limitations and open questions

- One clutter size (r=12) and one posture family (same-color solid discs). Smaller clutter adds less area and narrows the migration band; larger clutter (added area beyond the maximum bud-to-threshold distance, about 557 here) would push every bud over, and P3's 50% guess would hold at that size instead. The size dimension is unswept and is the first boundary on extrapolation.
- Only same-color clutter was tested. A leaf-green occluder is a different mechanism — it cuts holes in the mask and can split contours, plausibly damaging recall and shrinking areas; untested.
- Hosts are isolated by construction, so one disc bridging two true flowers (merging two targets into one detection, producing a miss and a relabeling together) is untested; it should be worse than anything here and is queued as a follow-up.
- Gaps are defined on nominal radii; per-host true edge distance jitters by a few pixels and contributes to the merge band's width. Redefining gap on measured contour edges would narrow the band but not move the crossing's location materially.
- The whole-kernel arm recorded host outcomes only, not scene-level end-to-end scores; kernel 3's fragmentation cost and kernel 11's full precision account are outside this article's evidence (§3.5 states this in place).
- The gap=35 FP reconciliation is off by one and was not located individually (presumed disc-to-disc merging); the other ten gaps reconcile exactly.
- Same simulator and detector family, digital images rather than field photographs: real fallen petals carry texture and translucent edges and should merge more softly than solid discs.

## 6. References

- Earlier in this series: 2026-10-30, "Zoom In Threefold and the Floor Leaks a Whole Layer" (separated-planting baseline and the limitation this article fulfils); 2026-10-17, "The Total Is Right and the Structure Is Wrong" (scoring rules and scenes); 2026-10-26, "Zooming In Is the Easy Direction" (area-drift band). Scenes, seeds and scoring match the earlier articles.
- This run's data: data/2026-11-07-adjacent-clutter-bench.json (all 11 gaps × main/closing-only/whole-kernel arms, per-class host outcomes, scene end-to-end); pre-registration: data/2026-11-07-adjacent-clutter-prereg.md (frozen before the run); post-hoc: data/2026-11-07-adjacent-clutter-posthoc.json (bud/bloom standalone area distributions, FP reconciliation, 50% crossing interpolation, the eight migrated buds located individually); script: data/2026-11-07-adjacent-clutter-bench.py.
- Bloom-Counter repository (MIT; detector and simulator): https://github.com/Ezra-Zhao/Bloom-Counter . Detector: detector/color_segmentation.py (_petal_mask, close/open morphology, area classification); simulator: simulator/generate.py (radius sampling: blooms 30–50, buds 11–17).
- OpenCV documentation: morphologyEx (MORPH_CLOSE / MORPH_OPEN), pointPolygonTest, contourArea: https://docs.opencv.org/4.x/ .

Author: Guangyi Zhao. All experiments, code and data in this article are the author's clean-room work and involve no customer information.
