# Three More Pixels of Radius, and Every Bud Is Gone: A Clutter-Size Scan With No Middle Ground Between 14.3% and 100%

Author: Guangyi Zhao

## 1. Problem and background

The 2026-11-07 test used exactly one clutter size: a same-colour disc of radius 12 pasted against real flowers. Bud migration peaked at 14.3% (gap −3, 8/56), and every migrated bud came from the largest end of the bud area distribution. That article's limitations section named the first extrapolation boundary in so many words: clutter came in one size only, and whether a larger disc — one whose added area exceeds a bud's distance to the classification threshold — would push *all* buds over the line was unmeasured. This article scans that dimension (preregistration frozen before the main run in data/2026-11-18-clutter-size-prereg.md, with six predictions P1–P6).

The headline result: migration rate versus clutter radius is not a ramp, it is a cliff — 14.3% at radius 12, 100% at radius 15, and no measured point in between. The reason is arithmetic. The bud alone-area distribution is bounded (242.0 to 499.5), so distances to the 900 threshold span only a 258-wide band (400.5 to 658). Between rc=12 and rc=15 the median effective addition at shallow touch jumps from 421 to 681 — one step wider than the whole distance band. Once the addition clears 658 (900 minus the smallest bud), the only remaining question is whether merging happens at all. The small end is equally abrupt: at rc ≤ 10 the largest median addition is about 318, short of the 400.5 minimum needed to move even the largest bud, and migration is zero everywhere. The distribution formula from 2026-11-07 (migrations ≈ merged buds whose alone area lies in [900 − addition, 900)) got its first direct test: 51 of 53 eligible cells predicted within ±2, pooled prediction 1057 against 1069 observed (−1.1%). Its two failures are the two most interesting cells — both in the partial-migration band, both under-predictions, both caused by the per-host spread of additions (a range of nearly 80) that a median-based formula flattens away.

One earlier conclusion expires here. "The deeper it presses, the safer it is" (2026-11-07: deep-overlap additions too small to migrate anything) is a small-disc privilege. An rc=15 disc still adds a median 427 at the deepest gap and migrates the same seven largest buds; from rc=18 up, deep additions start at 712 and every merged bud migrates. Deep-press safety lapses at rc=15 and is gone at rc=18.

## 2. Method

- Bases and hosts: identical in every detail to 2026-11-07. Four simulator scenes (seeds 101/202/303/404, 210 ground truths); the same host-selection function (16 directions, emptiest wins, blooms and buds interleaved) yields the same 112 hosts, 56 blooms and 56 buds. Host alone contour areas re-measured on the clean images: buds span min 242.0, median 344.25, max 499.5 (min/max identical to the full 76-bud distribution reported in 2026-11-07).
- Clutter: solid same-colour discs (pink/white/yellow rotating, the detector's three petal-mask target colours), radius rc ∈ {4, 6, 8, 10, 12, 15, 18, 21, 24}, signed edge-to-edge gap ∈ {−18, −8, −3, 0, 2, 4, 8}, one disc per host, drawn last. For small rc at deep gaps the nominal centre distance goes negative and is clamped to 0, recorded per trial (affects only the rc=4/6 deep cells; see Limitations). Full factorial: 63 cells × 112 hosts = 7056 host trials.
- Detection and outcomes: detector defaults (min_area=120, bloom_area_min=900, kernel 7, CLOSE then OPEN). Host outcomes by the contour method of 2026-11-07 (merged / correct / migrated / lost); addition = merged contour area − host alone area. End-to-end TP/FP/FN from the real detector per scene.
- Clutter-alone reference: each rc drawn at the centre of bare foliage backgrounds (seeds 7001–7004) through the same pipeline (area A_alone); the lone disc's detector label measured separately (seed 7001).
- Neighbour contamination: per-trial edge clearance from each disc to the nearest non-host truth was recorded; across all 63 cells the count of negative clearances is zero — no disc ever touched a neighbour, so the preregistered exclusion sensitivity has nothing to exclude and results are unchanged.
- Formula test (frozen in the preregistration): per cell, A_eff is the median addition over all merged hosts (blooms + buds); predicted migrations = merged buds with alone area ≥ 900 − A_eff. Cells with at least 5 merged buds count (53 cells).

## 3. Measurements

### 3.1 Alone reference: small discs are eaten by the opening, large discs are "blooms" by themselves

A_alone by rc: 0 at rc=4 and rc=6 (the disc exists in the mask, but the opening erodes it below the 120 floor — zero detections when placed alone); 172.0 at 8; 286.0 at 10; 406.0 at 12 — digit-for-digit the 2026-11-07 value; 664.0 at 15; 952.0 at 18; 1312.0 at 21; 1724.0 at 24. The lone disc's detector label flips with it: bud up to rc=15, bloom from rc=18. From radius 18, a disc that touches no flower at all is itself a false bloom. That is the same area ledger as the all-buds-migrate line of §3.2, seen from the other side.

### 3.2 The migration cliff at gap=−3

| rc | A_alone | median addition (gap=−3) | merged-bud migration rate |
|---|---|---|---|
| 4 | 0 | 42.8 | 0 (0/54) |
| 6 | 0 | 102.0 | 0 (0/56) |
| 8 | 172.0 | 184.5 | 0 (0/56) |
| 10 | 286.0 | 299.0 | 0 (0/56) |
| 12 | 406.0 | 421.0 | 14.3% (8/56) |
| 15 | 664.0 | 681.0 | 100% (56/56) |
| 18 | 952.0 | 970.8 | 100% (56/56) |
| 21 | 1312.0 | 1329.5 | 100% (56/56) |
| 24 | 1724.0 | 1738.0 | 100% (56/56) |

Three quantities replicate 2026-11-07 exactly at rc=12: A_alone 406, addition 421, migration 14.3% (8/56). Same hosts, same pipeline, same accounting — the cliff is not an artefact of a changed bench.

The cliff's arithmetic is §1: the bud distance band is 258 wide (400.5–658) and the addition step from rc=12 to rc=15 is 260. At rc=12 only buds within 421 of the threshold can cross (in theory alone area ≥479; in practice ≥457, because per-host addition spread lowers the effective line — §3.3). At rc=15 the addition 681 ≥ 658 pushes even the smallest bud (242.0) over. With an rc step of 3, the turning point is located only within (12, 15]; interpolating the addition curve puts the 658 crossing near rc≈14.7, but that is an interpolation, not a measurement — rc=13/14 migration rates are unmeasured (see Limitations).

The small end is arithmetic too: at rc=10 the largest per-gap median addition is about 318 (317.8 at gap=4), and crossing needs at least 400.5 — migration is not rare, it is geometrically impossible. The rc=4/6 discs are invisible alone (§3.1) yet still merge (merge rates at gap=−3 are of the same order as large discs) and still add 42.8/102.0 of area; they are harmless here because of their size, not because of their invisibility.

### 3.3 The distribution formula: right in total, low at the cliff edge

Of 53 eligible cells, 51 land within ±2 of observed migrations; the pooled prediction is 1057 against 1069 observed (−1.1%). As a bulk estimator the formula holds. The two failures sit in the partial-migration band and err in the same direction: rc=12/gap=−3 predicts 3, observes 8; rc=15/gap=−18 predicts 3, observes 7.

The mechanism is visible host by host. At rc=12/gap=−3, per-bud additions spread over 386.0–462.5 (IQR 405.8–443.2); the eight migrated buds drew additions with median 448.8, the non-migrated median 422.0 — the migrated set is selected for having drawn a large addition. The pooled median (421) sets the line at 479 and counts only the three buds above it; the observed migrations start at alone area 457 because those buds drew additions of 441–462. The transition even crosses over: the largest non-migrated bud has alone area 471.5 (its addition was only 395, total 866.5) — larger than the smallest migrated bud. In the transition band, neither alone area nor addition alone decides the outcome; their per-host sum does. rc=15/gap=−18 is the same shape: seven migrations, all from the largest buds (457–499.5, addition median 450.5), while the pooled-median line at 472.8 counts three.

The control case is rc=15/gap=−8: additions spread 578–693, yet the formula predicts 39 against 40 observed. Its 16 non-migrated buds all have alone area ≤288, and the largest of them totals 288 + 610 = 898 — two units short of the threshold. The formula is accurate there not because the spread is small (at 115 it is larger than in the failing cells) but because the threshold line falls in a sparse stretch of the bud distribution (no buds between 288 and 331.5), where spread cannot move the count. Whether the median formula works depends on whether its line lands in a dense or a sparse part of the distribution: in dense parts the count is hypersensitive to addition spread and the median version systematically under-predicts, because the migrated set is always the spread's upper tail; in sparse parts any reasonable statistic works.

### 3.4 Migration bandwidth: fixed at the top, expanding downward, starting at rc=15

The merging ceiling does not move with size: at gap=8 the merge rate and the migration count are zero at every rc (the band is set by the closing kernel, per the 2026-11-07 threshold law). All movement is at the deep end:

- rc ≤ 12: migration only in {−3, 0, 2, 4}, exactly as in 2026-11-07; deep additions (186.0/360.8 at rc=12) cannot reach the line.
- rc=15: the band expands to −8 (71.4%, 40/56) and −18 (12.5%, 7/56). At −8 the addition 614 is close to the all-buds line and only the smallest buds survive; at −18 the addition falls to 427.2 and the migrated set shrinks back to the largest buds — the rc=12 shallow-touch pattern, transplanted to the deepest gap.
- rc ≥ 18: migration is 100% in every gap cell where merging occurs. Deep additions (from 712.5) already clear 658, so gap stops being a variable: merged means migrated.

The posture rule of 2026-11-07 — light touch is the dangerous pose, deep press is safe — holds in full only for rc ≤ 12. At rc=15 it starts leaking (deep press injures the largest buds); at rc ≥ 18 it inverts completely.

### 3.5 Remaining accounts: blooms untouched, zero losses, FP accounting 63/63

Bloom hosts score correct in all 63 cells — addition only grows area, and a bloom has nowhere to migrate to. Losses are zero across all 7056 trials; same-colour addition never deletes a host. The end-to-end FP identity (FP ≈ migrations + unmerged surviving discs) holds within ±3 in all 63 cells, worst case 2 (rc=24/gap=4: predicted 81, observed 79; rc=24/gap=8: 112 vs 110 — the residual is discs merging with each other, the standing unexplained-unit account of this series). Two endpoints deserve explicit lines. At rc=15/gap=−3 the scene totals are TP 154, FP 58, FN 56: one all-buds migration event is simultaneously a recall collapse and the bulk of the FP count. And at gap=8, rc=15 and rc=24 produce nearly identical FP totals (112 vs 110) of opposite classes (bud-class vs bloom-class): read on totals alone the two clutter sizes look equivalent, while a class-wise downstream sees 110 phantom blooms written straight into its bloom count.

### 3.6 Prediction scorecard

- P1 (alone visibility): full hit. A_alone monotone; rc=4/6 zero with zero detections; survival from rc=8 (172); rc=12 replicates 406 exactly.
- P2 (distribution formula): full hit by the preregistered criteria — 51/53 cells within ±2 (96% vs the 80% line), pooled deviation −1.1% (vs the 15% line). A pass on criteria is not a clean bill of health: both failures under-predict in the same direction with an identified mechanism (§3.3), and the formula's domain is "threshold line in a sparse part of the distribution", not everywhere.
- P3 (all-buds turning point): full hit. Gap=−3 migration is monotone in rc (0/0/0/0/14.3%/100%/100%/100%/100%); 100% is reached at rc=15 (preregistered ≥70% with the turning point in {15, 18} — it sits at the interval's lower edge and arrives in one step, with no intermediate value); rc=12 replicates 14.3%.
- P4 (bandwidth expansion): half hit. The rc ≤ 12 band {−3, 0, 2, 4} and the gap=8 zero at all rc are exact, and the expansion direction is right — but expansion starts at rc=15, not the preregistered rc ≥ 18 (at rc=15, −8 already migrates 71.4% and −18 migrates 12.5%). The rc=15 deep additions (427/614) already reach the largest buds; expansion does not need to wait for the all-buds line.
- P5 (blooms and losses): full hit. Bloom correct 100% in all 63 cells; losses zero throughout.
- P6 (FP accounting and class): full hit. 63/63 cells within ±3; lone-disc labels are bud up to rc=15 and bloom from rc=18, flipping in step with A_alone crossing 900.

Five full hits, one half. P4's missed starting point and P2's two under-predictions are the same mistake: I reasoned about band edges from median quantities (pooled median addition, typical size), while band edges are set by distribution tails and per-host spread — medians are systematically one step late at an edge.

## 4. Analysis and trade-offs

First, a computable size line for deployment. Everything in this test is decided by three numbers: the threshold (900), the alone-area distribution of the small class, and the clutter addition curve. An addition above 900 − (smallest small-class area) (here 658) means all-buds migration; above 900 − (largest) (here 400.5) means migration starts; between the two is the partial band. For a new deployment, measure the local small-class area distribution's min and max and the expected clutter's shallow-touch median addition, and clutter sizes sort into three regimes: below the start line (ignore), in the band (estimate with the distribution formula), above the all-buds line (plan for total migration). That is more actionable than a posture rule like "keep clutter away from flowers".

Second, one word of the formula should change: A_eff should be a high quantile of the addition, not the median. §3.3's failures are not structural — the migrated set is chosen by the upper tail of per-host additions, so a median input must under-count the partial band. Recomputing rc=12/gap=−3 with the bud-specific addition p75 (443.2) sets the line at 456.8 and predicts 10 against 8 observed (error +2, inside tolerance): the bias flips sign and the magnitude is right. This is a post-hoc recomputation, not a preregistered validation, and the p75 choice itself has no independent support — it is recorded here as a candidate correction, to be preregistered before it is believed.

Third, deep-press reassurance has a size limit. Any field rule of the form "clutter pressing on a flower is safer than clutter beside it" holds only for small clutter. Once the disc radius approaches the bud diameter (here rc=15 against buds of r=11–16), deep press injures too; from rc=18 posture is irrelevant — contact means total migration. Large clutter can only be governed by keeping it out of the frame (or out of the mask's colour ranges), not by posture.

Fourth, large-clutter FPs are class contamination, not just count inflation. From rc=18, unmerged discs enter detections directly as blooms (110 phantom blooms at gap=8), rewriting class-wise readouts (bloom rate, bloom count); and the same disc is the migration agent when it touches a flower and a phantom bloom when it does not. Class-wise acceptance tests should carry large same-colour clutter as its own sample tier.

As in the previous instalments, none of this costs deployment compute: all three items are changes to acceptance-sample composition and estimation practice, not to detector parameters.

## 5. Limitations and open problems

- Turning-point resolution: the rc step is 3, so the turn is located only within (12, 15]; the interpolated crossing near rc≈14.7 is unmeasured, and whether rc=13/14 migration is 40% or 90% — the cliff's width — is unknown. A denser scan between 12 and 15 is a separate run.
- Half of the cliff's steepness is this distribution's shape: bud alone areas have a gap between 381 and 436 and bounded support. A wider, more continuous real-world small-class distribution would walk through intermediate rates under the same addition step. The cliff's *position* (set by the 658 and 400.5 lines) transfers; its steepness must be recomputed from the local distribution.
- Clamped centre distances at rc=4/6: at gap=−18 the nominal centre distance for buds is negative and clamps to 0 (concentric), so in those two cells "merged" is true by construction and additions are near zero (the concentric disc is eroded by the opening). This affects only the rc=4/6, gap=−18 readings and no migration conclusion (migration is zero there, as it is for the unclamped hosts in the same cells).
- Clutter is still one colour family (pink/white/yellow rotating) and one shape (solid disc). The 2026-11-08 shape account suggests square clutter has a wider effective contour band; under a shape change both A_alone and the addition curve move, and the turning rc moves with them. Unmeasured.
- Only the s=1 reference scale was tested. Under scaling, rc and bud areas shrink with s² while the threshold does not (the 2026-11-08 prescription scales the threshold with s²), so the two size lines shift relative position with the deployment convention. Unmeasured.
- All evidence remains this simulator and this detector: the numbers (the 658/400.5 lines, rc*=15, the A_alone table) must be re-measured on real photographs and other detectors. What transfers is the structure — migration is decided by the addition's position relative to the distribution's distance band, partial-band counts must be estimated from the addition's upper tail, and deep-press safety has a size limit.

## 6. References

1. Previous instalments: Guangyi Zhao, "Pressed Harder, Hurt Less" (2026-11-07) — origin of this test (its first limitation), the rc=12 comparison numbers and the distribution formula (its §3.2/3.3); "A 40% Higher Floor, and Not One Bud Hurt" (2026-11-08) — the bud area lower tail and threshold distances in another accounting; "One Bridge, Two Flowers Lost" (2026-11-16) — the rc=18 disc alone registering as a bloom, corroborating §3.1 here.
2. Code under test: the Bloom-Counter repository, simulator/generate.py (scenes and radius sampling: blooms 30–50, buds 11–17) and detector/color_segmentation.py (ColorSegmentationDetector; defaults min_area=120, bloom_area_min=900, morph_kernel=7).
3. This run's data (archived in the project data/ directory and mirrored with the Chinese version into the tech-deep-dives repository data/): 2026-11-18-clutter-size-prereg.md (preregistration, factor table, formula-test protocol, P1–P6), 2026-11-18-clutter-size-bench.py, 2026-11-18-clutter-size-bench.json with its progress.jsonl (per-trial records and per-cell summaries for 63 cells × 112 hosts), 2026-11-18-clutter-size-posthoc.py and 2026-11-18-clutter-size-posthoc.json (A_alone and bud distribution, per-cell formula errors, transition band and per-host addition spread, FP accounting).

---

Author: Guangyi Zhao. The experiment design, code and data in this article are clean-room work of my own: the scene generator, detector and analysis scripts are my own projects and hand-written code, the experiments ran only on my own machine, and no client information or third-party system is involved.
