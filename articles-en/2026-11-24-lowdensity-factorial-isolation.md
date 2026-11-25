# Neither Factor Is the Answer: A Factorial Isolation of the Low-Density Failure Shrinkage — Two Pools in the Same Cell Differ More Than the Factors Do

Author: Guangyi Zhao
Date: 2026-11-24
Subject: Bloom-Counter scale estimation, factorial experiment, estimator guards

## 1. Problem and background

The 2026-11-12 article left one mechanism unisolated. In the low-density pool LD1 (9 blooms and 5 buds per scene), the bad points in the failure band were only mildly bad: errors of +10.88% to +12.83%, divergence 7.09% to 7.87%, the whole band sitting inside AMBER territory. In HD1 — same composition, higher density — bad points ran from +13.72% to +107.43%, with divergence mostly above 15%. Same estimator failing at the same scale, one pool barely over the line, the other far over it.

LD1 and HD1 differed in two ways at once: buds per scene (5 vs about 19) and total targets per scene (14 vs about 54, targets meaning blooms plus buds); bud proportion was nearly identical (about 36%). Topic 20 in the pool asked for a clean isolation: manipulate absolute bud count and bud proportion separately, measure how failure-band overshoot and divergence move with each factor, and pin down what makes an LD1-style AMBER failure.

This article is that isolation, and the headline is a negative result: neither factor has a clean main effect. The difference between two pools in the same cell is generally larger than any between-level factor difference. LD1's shrinkage is attributable neither to bud count nor to proportion in this design; it looks like a property of that particular pool's composition — re-pool a different set of scenes at identical parameters and the failure magnitude moves from barely-bad to far-bad. Of six preregistered predictions, one and a half survived; Section 3.4 accounts for each.

## 2. Method

- Estimators unchanged from the whole series: BLIND7 (kernel-7 morphology, reference area 3806.0) and BLIND3 (kernel 3, reference 3740.0), both running 2-means blind clustering over contour areas and inverting the upper-cluster median into a scale estimate. Divergence div = BLIND7 / BLIND3 − 1; BAD means |BLIND7 error| above 10%; tiers GREEN up to 2%, AMBER 2–15%, RED above 15%.
- Factorial design: bud count B at two levels (6 / 18 per scene), bud proportion P at two levels (30% / 60%, set via bloom count), four cells — B-low P-low (6 buds, 14 blooms, total 20), B-low P-high (6 buds, 4 blooms, total 10), B-high P-low (18 buds, 42 blooms, total 60), B-high P-high (18 buds, 12 blooms, total 30). Two independent pools of 4 scenes per cell, 32 scenes total, fresh seeds from 5101. Actual placed counts matched nominal counts in all 32 scenes.
- Fifteen scale levels (1.0 down to 0.07). The failure band was preregistered as s in {0.30, 0.28, 0.25, 0.22} (where LD1's bad points sat); the healthy band is s at or above 0.35. Band summaries use medians and maxima of pooled points.
- One mathematical caveat, stated in the preregistration: total targets equal buds divided by proportion — a derived quantity, not a third independent factor. This design separates absolute-count effects, proportion effects, and their interaction; a total-count effect cannot be separated from them here.

## 3. Measurements

### 3.1 Band medians crowd into 11–18%; no cell reproduces LD1's tidy shrinkage

| Cell | Failure-band err7 median | Band max | Band div median | Bad points | Healthy-band err7 median |
|---|---|---|---|---|---|
| B-low P-low | +11.37% | +15.10% | 5.59% | 4/8 | +7.03% |
| B-low P-high | +18.39% | +21.43% | 9.95% | 8/8 | +10.46% |
| B-high P-low | +14.31% | +16.23% | 15.22% | 8/8 | +2.21% |
| B-high P-high | +13.55% | +20.63% | 10.89% | 4/8 | +4.30% |

Paired comparisons reverse. For bud count: at P-low, B-high exceeds B-low by 2.94 points (+14.31% vs +11.37%); at P-high the sign flips, B-high is 4.84 points lower (+13.55% vs +18.39%). For proportion: at B-low, P-high exceeds P-low by 7.02 points; at B-high, P-high is 0.76 points lower. Under preregistered rule P6, a main effect that holds in one pairing and reverses in the other is an interaction pattern, and neither main effect may be claimed.

### 3.2 The large numbers live inside the cells: replicate pools differ by up to 9 points

| Pool | Failure-band err7 median | Bad | Healthy-band err7 median |
|---|---|---|---|
| B-low P-low pool 1 | +8.43% | 0/4 | +4.88% |
| B-low P-low pool 2 | +14.41% | 4/4 | +10.18% |
| B-low P-high pool 1 | +20.91% | 4/4 | +14.81% |
| B-low P-high pool 2 | +16.73% | 4/4 | +6.48% |
| B-high P-low pool 1 | +15.10% | 4/4 | +0.20% |
| B-high P-low pool 2 | +14.11% | 4/4 | +4.54% |
| B-high P-high pool 1 | +9.36% | 0/4 | +3.29% |
| B-high P-high pool 2 | +18.49% | 4/4 | +6.01% |

Within-cell pool differences in band median: 5.98 points (B-low P-low) and 9.13 points (B-high P-high) — larger than any paired factor difference in 3.1. B-high P-high pool 1 has zero bad band points; pool 2 is bad at all four levels, with identical parameters and only the scene seeds changed. In this bench, how badly a pool fails is first a sampling question: which four scene sets got pooled matters more than the factor levels.

### 3.3 The healthy band is not flat either: B-low cells carry a +7% to +10% baseline bias

The B-high cells sit at +2.21% and +4.30% healthy-band medians; the B-low cells sit at +7.03% and +10.46%. B-low P-high pool 1 is already at +15.05% at s=1.0, above the BAD line before the failure band even starts, with all six healthy levels above +13.55%. The old data rhyme: LD1's healthy band carried +4.89% to +6.99% bias, HD1's only +0.80% to +3.01% (2026-11-12 raw data). This may be the other face of the shrinkage: the upper-cluster median in small pools carries a composition-dependent baseline bias, and band overshoot stacks on top of it. No decision rule was preregistered for this observation, so it is recorded as an observation, not a conclusion; it points toward per-scene calibration sampling error and full recalibration (topics 21 and 22), not toward more cells in this factorial.

### 3.4 The six preregistered predictions, accounted

- P1 (bud-count main effect): missed. Holds at P-low, reverses at P-high; the B-low maximum (+21.43%) also breaks the preregistered +14% cap.
- P2 (proportion main effect): missed. Holds at B-low (+7.02 points), reverses at B-high (−0.76 points).
- P3 (divergence follows the same factor): missed. Band div medians rank B-high P-low highest (15.22%) and B-low P-low lowest (5.59%), which does not match the err7 ranking (B-low P-high highest).
- P4 (healthy band unaffected): missed. Healthy-band medians span 8.25 points across cells, over the 5-point line.
- P5 (AMBER failures live on the B-low side): hit. Bad-point div medians in the B-low cells are 6.21% and 9.95%, all inside AMBER. Note the scope: B-low P-high failures are not shrunk (median +18.39%, 8/8 bad) — AMBER describes the divergence shape, not the error size, as in the earlier articles.
- P6 (interaction check): triggered. Both main effects are recorded as missed; no main effect is claimed.

## 4. Analysis and trade-offs

The useful output of this round is a denial. LD1's shrunken failure magnitude cannot be credited to low bud count, and proportion was nearly identical between LD1 and HD1 to begin with; bud count shows no stable effect here either. Two candidate explanations remain, and this data cannot separate them: pool-composition sampling (replicate pools differ by 6–9 points at identical parameters, so LD1 may simply have drawn a mild set of scenes), and the baseline-bias observation of 3.3 (small pools carry a positive upper-median bias that shifts where the failure band starts, relative to the line).

Two consequences for guard deployment. First, do not write any prescription of the form "low-density scenes fail more gently": the B-low cells here produced a +21.43% band error and an 8/8 all-bad cell. Gentleness was one pool's individual reading. Second, the AMBER divergence shape on the B-low side is real (P5), but since its cause is not a density factor, tiering guard thresholds by density has no basis; if thresholds move at all, they should move with a pool's own baseline bias — a recalibration question, not a density question.

## 5. Limitations and open questions

- Two pools per cell is a coarse variance estimate; "within-cell differences exceed factor differences" is a description of this sample. Quantifying variance components needs four or more pools per cell, which this round did not run.
- Total count is derived (Section 2). The B-low P-high cell has only 10 targets per scene; its frequent low-scale NOEST points and tiny upper clusters are confounded with "high proportion" by construction.
- The healthy-band baseline bias (3.3) had no preregistered decision rule; whether it is the same phenomenon as the common-mode bias of the 2026-11-13 recalibration article is unchecked.
- The failure band is four levels wide; factor behaviour below s=0.18 was not measured, and several pools return NOEST at s=0.07, so the deep tail is absent from the verdict.
- All conclusions are about this simulator (the Bloom-Counter generator and detector morphology), not about real agricultural counting pipelines.

## 6. References

- This round: data/2026-11-24-lowdensity-factorial-bench.json (raw), data/2026-11-24-lowdensity-factorial-prereg.md (preregistration), data/2026-11-24-lowdensity-factorial-posthoc.json (post-hoc summary).
- Prior data: data/2026-11-12-divergence-cliff-bench.json (per-level LD1/HD1 err7 and div); "Half the Middle Band Is Genuinely Bad" (2026-11-12, articles-en/ in the same repository).
- Estimator definitions: "Can You Trust an Estimated s?" (2026-10-25) and "Divergence From 0.4% to 170%" (2026-10-29), same repository, raw data under data/.

---

Author: Guangyi Zhao. The experiments, code, and text in this article are clean-room work of the author's own and involve no client information; every number can be recomputed from the raw data under data/ in the same repository.
