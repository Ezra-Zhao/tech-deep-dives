# A 1.2-Point mAP Gain That Cannot Say How Many Flowers Were Missed: An Evaluation Audit of Chili-Seg, With a Controlled Protocol Experiment

Author: Guangyi Zhao

## 1. Problem and background

This installment of the paper deep-read series takes a plant phenotyping / agricultural counting paper from the last three months and checks its evaluation protocol against three questions fixed in advance: does it match predictions to ground truth instance by instance, does it report results per category, and does it include quantitative stress tests for occlusion and illumination? The paper is Chili-Seg (Kuang et al., Frontiers in Plant Science 17:1955273, published 29 September 2026, doi:10.3389/fpls.2026.1955273), a chili-flower instance segmentation model built on YOLO11n-seg. It explicitly targets small objects, leaf occlusion, and variable illumination, and it names flower counting and robotic pollination as downstream uses. Its headline numbers look strong: detection precision 96.8%, mAP50 90.6%, mAP50-95 77.9%; mask precision 96.6%, mAP50 89.8%, mAP50-95 64.7%; 102.4 FPS on a Jetson AGX Orin.

I read the full text section by section, then re-ran the evaluation-protocol question on my own counting pipeline under controlled conditions. The finding, up front: the per-instance matching in Chili-Seg is real. The gaps are elsewhere. The model has exactly one class, and the paper contains no counting error of any kind. Its quantitative evidence on occlusion and illumination is zero — the robustness claims rest on selected figures. And the controlled experiment on my own pipeline shows what those two omissions can hide: on a classical pipeline that is extremely sensitive to size thresholds, scoring the same predictions under a different protocol moves the numbers by up to 41 points (an extreme value that is a property of that pipeline and does not transfer to deep models — see Sections 4 and 5), and by 7.2 points pooled over all conditions; changing only the composition of the test set moves the headline 5.4 points. For scale, the paper's entire mAP50 improvement over its baseline is 1.2 points.

## 2. Method

### 2.1 Audit protocol

The audit uses only the published full text, pinned to section numbers: dataset construction and screening (§2.1), the split (§2.1), the class count (§3.4.1 Table 1 and §3.4.2), metric definitions (§3.4.2), all result tables (§4.1–§4.2.5), the qualitative analysis (§4.3–§4.4), and the authors' own limitations (§4.6). The three questions were fixed before reading the results:

1. Per-instance matching: are predictions matched to ground truth one-to-one at instance level, or is only the total count compared?
2. Per-category reporting: are results broken down by category, developmental stage, size, or condition, or is there a single aggregate number?
3. Destructive testing: are occlusion and illumination evaluated in quantitative tiers (one row of numbers per tier), or only shown qualitatively?

### 2.2 Controlled protocol experiment

The experiment does not touch the Chili-Seg model — its data and code were not released with the paper (the data availability statement offers the raw data from the authors on request). What it tests is the evaluation protocol itself. I used my own Bloom-Counter detector (a classical color-segmentation pipeline, min_area=120, bloom_area_min=900, kernel 7, unchanged from the previous two installments) on four simulated scenes (seeds 101/202/303/404; 210 base targets: 134 blooms, 76 buds) under 18 conditions: 10 illumination transforms, 3 leaf-cover occlusion tiers, and 5 overlap offsets. The transforms and seeds are identical to the 2026-10-17 bench, and this run's strict-protocol numbers reproduce that bench item by item (gamma 2.2 F1 0.558 vs 0.5576; leaf cover x0.8 F1 0.315 vs 0.3153), so the two datasets cross-check each other.

The same predictions are scored three ways:

- Protocol A (strict): centre matching with the label required to match; bloom recall and bud recall reported separately. This is the protocol used throughout this series.
- Protocol B (single-class): centre matching with labels ignored, blooms and buds merged into one "flower" class. This mirrors the scoring logic of an nc=1 evaluation at a fixed operating point (Chili-Seg integrates an AP curve; I use fixed-point F1. The question both answer is the same: does a wrong category count as an error?).
- Protocol C (count-only): total count error and per-image count MAE only — the protocol of pure regression counting papers.

I also record category migrations: predictions whose centre lands within tolerance of a ground-truth centre but with the wrong label. Under B they are hits. Under A they are a false positive plus a false negative. Under C they do not even move the total.

## 3. Results

### 3.1 Audit: one pass, two gaps

The pass first. Chili-Seg's evaluation is genuinely instance-level: Box and Mask precision, recall, and mAP are computed separately, with IoU swept from 0.50 to 0.95 (§3.4.2). That is a firmer footing than count-only regression papers. The authors also ran five-seed repeated training (detection mAP50 90.34±0.30; Mask mAP50-95 64.30±0.29, Table 3) and stated plainly that they did not run scale-stratified AP or cross-variety, cross-region, cross-device validation (§4.6). I credit all of that below; this audit is about default omissions, not misconduct.

Gap one: no categories, and no counting. The training configuration sets nc=1 (§3.4.1, Table 1), and the metrics section confirms "only one chili flower category is considered" (§3.4.2). Yet the dataset section frames the collection as built for "developmental stage classification of chili flowers and buds" (§2.1) — the bud category vanishes by evaluation time. All eight result tables report a single aggregate: nothing by stage, object size, occlusion degree, or illumination condition. And although counting is named as a purpose (§4.2.5 calls instance identity essential for flower counting), the paper reports no per-image counting error anywhere — no MAE, no RMSE, no relative error — and its conclusion defers quantitative trait extraction to future work. A segmentation paper written for counting never tells the reader how far off a per-plant count would be. One detail hides inside the aggregate: detection recall is 80.6%, exactly the baseline's 80.6% (Tables 2 and 7), and mask recall 80.4% is likewise unchanged. The gains concentrate in precision and localization quality at high IoU thresholds, while recall at the reported operating point did not grow; on the authors' own screened test set, one flower in five is still not found, and that number is not in the abstract.

Gap two: the stress evidence is pictures, not numbers. The dataset was curated away from the hard cases before any split: capture was restricted to stable-light windows (06:00–11:00 and 15:00–17:00, §2.1), and the 1,875 retained originals are what remained after "manual screening to remove low-quality samples with severe motion blur or heavy occlusion" (§2.1). The split randomly partitions originals (636 train / 619 validation / 620 test) with no mention of grouping by plant or capture session, so multi-angle shots of the same plant can land in different subsets. Augmentation (brightness, contrast, Gaussian and salt-and-pepper noise) was applied to the training set only; the test set is unmodified originals. Then §4.3 presents occlusion and illumination evidence as a few selected rows of Figure 11, described in text as Chili-Seg executing "flawless predictions without committing any false-positive errors" and "successfully identifying and segmenting all target instances" — no denominator, no selection protocol, not one tiered number.

A footnote from the other end of the same three months: the dual-view apple flower counting paper by Vitousek et al. (Frontiers in Plant Science, 9 July 2026) is pure count regression — relative error 10.26%, no localization at all. One paper has instances and no counting evaluation; the other has a counting number and no instances. Both are missing the same middle layer: per-instance, per-category, per-condition counting evaluation.

### 3.2 Controlled experiment: same predictions, three protocols, three conclusions

Across the 18 conditions there are 3,980 ground-truth instances (2,612 blooms, 1,368 buds). Where the migrations live:

| Condition | A strict F1 | B single-class F1 | Gap (pts) | Migrations | Bloom recall | Bud recall | Count error |
|---|---|---|---|---|---|---|---|
| Exposure -50 (dimmed) | 0.809 | 1.000 | +19.1 | 40 | 0.702 | 1.000 | 0.00% |
| Shadow gradient | 0.895 | 1.000 | +10.5 | 22 | 0.836 | 1.000 | 0.00% |
| Half shadow | 0.905 | 1.000 | +9.5 | 20 | 0.851 | 1.000 | 0.00% |
| Gamma 2.2 (severe darkening) | 0.558 | 0.968 | +41.0 | 103 | 0.336 | 1.000 | +6.67% |
| Leaf cover, radius x0.8 | 0.315 | 0.529 | +21.4 | 223 | 0.530 | 0.289 | +80.95% |

The exposure -50 row deserves a slow read. Forty of 134 blooms were relabeled as buds. The total count is exact, per-image count MAE is 0, single-class F1 is a perfect 1.000. Under protocols B and C this is a flawless run; only the per-category view shows bloom recall at 0.702. I have hit this shape before — the 2026-10-17 installment was titled "the total is right and the structure is wrong" — but this time it is quantified as a protocol gap: migration failures are not underestimated by single-class scoring, they are defined as correct.

Pooled over all 18 conditions, protocol A gives F1 0.818 and protocol B gives 0.890, a 7.2-point gap. Migrations total 506 instances, 12.7% of all ground truth: one target in eight was assigned the wrong category, and protocol B scored every one as a hit. Protocol C looks calmer still: total count error -4.55%, while the per-category counts are off by -548 blooms (-21.0%) and +367 buds (+26.8%), two errors cancelling into a benign-looking total. Per-image count MAE is 8.04 flowers — a number no relative-error-only report would ever surface.

Test-set composition, isolated: pooling only the 7 mildest conditions (baseline, two mild lighting transforms, washout exposure, light cover, two loose overlap tiers) gives protocol-B F1 0.944, versus 0.890 over all 18. No model change — only the share of hard cases in the test set — buys 5.4 headline points. Simulating a Chili-Seg-style screening pass (dropping the 4 hardest tiers: severe darkening, low light with noise, heaviest cover, tightest overlap) moves protocol A from 0.818 to 0.846 and B from 0.890 to 0.893. Screening flatters the strict protocol more, because the dropped tiers are exactly where migrations and misses concentrate.

In fairness, protocol B is not a universal fig leaf. Under the warm color cast, bud recall collapses to exactly zero (all 76 buds missed), B and A agree at 0.724, and the -23.81% count error is impossible to hide — pure misses cannot be hidden. The +80.95% count error in the heavy-cover tier (fragmentation inflating the detection count) also raises an alarm. The precise statement is that single-class and count-only protocols are selectively blind: blind to "found it, labeled it wrong," which is exactly the failure mode that area-, color-, and stage-based classifiers produce most.

## 4. Analysis and trade-offs

Five checks to apply to any counting or phenotyping paper, each with its evidence from this audit:

1. Find the counting error first; if it is absent, record it as absent. Instance-level mAP is not a counting evaluation. Ask for per-image count MAE or relative error, even if it is derived by counting instances. Chili-Seg has none; the dual-view paper has only that. Each delivered half.
2. nc=1 is a design choice with a price that should be stated. When the task has real category structure (flower/bud, king/lateral, developmental stage), a single-class aggregate defines migration as success. Measured here: migrations up to 12.7% of ground truth, a per-condition protocol gap up to 41 points. When you see nc=1, ask what the merged categories were needed for downstream.
3. Robustness counts only as tiered numbers, not figures. One row per illumination and occlusion tier costs one batch run (the full 18-condition re-scoring here). Qualitative figures can illustrate; they cannot evidence. Superlatives without denominators ("flawless", "all instances") score zero.
4. Read the dataset section before the results. Screening rules, capture windows, and split design moved the headline more in this experiment (+5.4 points from composition alone) than the architecture change the audited paper claims (+1.2 mAP50 points). With a random split and no grouping, also ask about near-duplicate leakage.
5. Credit the honest parts. Chili-Seg reports multi-seed stability and discloses two unrun validations; its protocol is cleaner than the field's average. The problem is the field's defaults, not this paper's integrity. The point of an audit is to turn defaults into required fields, not to convict one paper.

Two trade-offs in my own design, stated plainly. First, I did not re-run Chili-Seg itself: its data and code are not public, and its self-built set (one site, one mutant line, 1,875 screened images) cannot be reproduced externally. Training some YOLO on unrelated data would add nothing to the audit questions. Fixing the predictions and varying only the scoring protocol isolates the variable that reproduction cannot. Second, the controlled pipeline is a classical color-threshold detector, not a learned model: its migration magnitudes are amplified by area-based classification, and the 41-point figure must not be carried over to YOLO-class models. What transfers is the mechanism — wherever the failure mode is category migration, single-class scoring cannot see it, regardless of model vintage.

## 5. Limitations and open questions

- The controlled pipeline is a classical color-segmentation detector, not a learned one. Migration magnitude is a property of this pipeline (classify by area; darken the image and classes migrate). How much a model like Chili-Seg migrates under equivalent stress is not measured here and cannot be, since its data are not public. The numbers prove the blind spot exists and can reach double digits; they are not an estimate of that model's true robustness. How far it actually drops under heavy occlusion is something the paper does not report, and this article does not invent.
- Protocol B here is fixed-operating-point centre-matching F1 standing in for an AP evaluation — structurally equivalent for the migration question, not numerically identical. AP also integrates confidence ranking; whether ranking hides or exposes migration along the PR curve is untested.
- The controlled scenes are still synthetic, with digital transforms, from the same simulator family as the previous two installments. Real field illumination and occlusion are messier, and the tier definitions (gamma values, leaf-cover radius multiples) are engineering approximations.
- This is a single-paper deep read. The audit questions were fixed in advance and every quoted number was checked against the publisher's full text, but no claim is made that "papers from the last three months generally do this" — the dual-view paper is a corroborating footnote, not a sample.
- Open for follow-ups: recompute protocol B as a true single-class AP curve and locate where migration hides along it; and add a small learned detector (e.g., a YOLO trained from scratch on synthetic data) to the controlled bench to measure the migration blind spot's magnitude for deep models.

## 6. References

- Kuang M, Li X, Hu Z, et al. Chili-Seg: a high-precision detection and instance segmentation model for chili flowers in complex environments. Front. Plant Sci. 17:1955273, 29 September 2026. doi:10.3389/fpls.2026.1955273 (audit subject; section numbers refer to the publisher's full-text HTML, read 21 October 2026)
- Vitousek M, Vrba J, Cejnek M, et al. Dual-view weakly-supervised learning for apple tree flower counting. Front. Plant Sci. 17:1869941, 9 July 2026. doi:10.3389/fpls.2026.1869941 (contrast case: pure regression counting, relative error 10.26%, no instance localization)
- Bloom-Counter repository (MIT; detector and simulator): https://github.com/Ezra-Zhao/Bloom-Counter — detector/color_segmentation.py, simulator/generate.py.
- Previous installments in this series: 2026-10-17, "Right Total, Wrong Structure: Lighting and Occlusion Stress Tests for an Agricultural Counting Pipeline," and 2026-10-20, "Thresholds Are Not Constants, They Are Functions of Distance." Scenes, seeds, and the strict scoring protocol are shared; this run's strict-protocol numbers were cross-checked item by item against the 2026-10-17 raw data.
- Experiment code and raw data for this article: data/2026-10-21-eval-protocol-bench.py and data/2026-10-21-eval-protocol-bench.json (18 conditions x 4 scenes; three-protocol scoring, migration counts, pooled and curation-simulation results).

---

Author: Guangyi Zhao. The code and experiments described here are the author's clean-room work: the detector, simulator, and evaluation scripts used in the controlled experiment were written by the author and run on locally generated synthetic data. The audit of the published paper is based on its public full text. No client data or identifiable information is involved.
