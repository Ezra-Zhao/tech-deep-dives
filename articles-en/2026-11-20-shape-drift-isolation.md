# Changing the Interpolation Won't Save You: Shape Drift Is Contour Quantization Recovering, Not Halo

Author: Guangyi Zhao
Date: 2026-11-20
Subject: An orthogonal isolation of interpolation, closing and opening in the upscaling area drift of an area-threshold detection pipeline, and the effective contour band widths of circles, squares, triangles, pentagons, hexagons and diamonds

## 1. Problem and background

My 2026-11-08 article left one mechanism unisolated. Clutter upscaled by the pipeline grew by shape: a square of side 11 gained a median +24% in normalized contour area (maximum +26.6% of nominal), a same-size circle only +20% median and +9.5% maximum. I offered a one-line explanation "consistent with the data" — interpolation halo at right-angle corners plus closing filling those corners — and explicitly logged it as unmeasured: how much each factor contributes was unknown, and whether polygonal fragments (triangles, multi-angle shards) have an even wider effective band than squares was untested.

This article isolates both. The method is a single-shape bench with a full factorial design: 3 interpolations (INTER_LINEAR, INTER_CUBIC, INTER_NEAREST) × 4 morphology arms (full pipeline close7→open7, close only, open only, none) × 5 scale factors, measuring how each shape's normalized contour area moves with each factor. The design and six predictions were frozen in a pre-registration before any run (data/2026-11-20-shape-drift-prereg.md); the scorecard is in section 5: two predictions fully right, two half right, two wrong — and the two wrong ones overturn my own earlier mechanism guess, which is the most valuable part.

The findings, up front. First, interpolation halo is essentially innocent: switching LINEAR for NEAREST, which creates no new pixel values at all, does not reduce the square's total drift — it raises it slightly (+19.54 growth points vs +16.74, in the accounting of section 3). Second, the bulk of the drift is contour quantization recovering: contourArea measures the polygon through boundary-pixel centres, which systematically underestimates small shapes; upscaling makes the shape larger in pixel terms, the relative underestimate shrinks on its own, and the normalized area "grows" back — a bare square with no morphology and NEAREST still gains +11.21 points. Third, closing-as-corner-filling is real only for acute shapes (+7.4 to +7.7 absolute area points for triangle and diamond) and exactly zero for the square, whose corners have nothing to fill. Fourth, polygons do have wider effective bands than squares: diamond 15.0, triangle 13.4, hexagon 13.0 points, against the square's 4.6 — the worst shape for margin purposes is not the square, it is the acute polygon.

## 2. Method

The bench is a clean-room single-shape canvas: 240×240, solid background BGR(40,120,40) asserted to produce an empty petal mask, shapes drawn alone at the centre in the same pink BGR(147,20,255) as the clutter planted in 2026-11-08. The pipeline is the Bloom-Counter detector verbatim: BGR→HSV→ColorSegmentationDetector._petal_mask (imported, not reimplemented) → morphology arm → findContours(RETR_EXTERNAL) → contourArea, taking the contour that contains the shape's centre; normalized area = contourArea / s².

Six small shapes (nominal area 113–128): circle r=6 (113.1), square side 11 (121), equilateral triangle (nominal 125.2 at side 17, drawn at circumradius 10), regular pentagon (circumradius 10, 237.8 — about twice the others, see limitation one; read it as a mid-size sample), regular hexagon (circumradius 7, 127.3), diamond (diagonal 16, 128.0); plus two size controls: circle r=12 (452.4) and square side 21 (441). Sixteen replicates per shape (centre jitter ±6 px, polygons also rotated 0°–75°), giving 8 shapes × 16 replicates × (4 arms at s=1, plus 3 interpolations × 4 arms at four larger scales) = 6,656 readings. Raw data: data/2026-11-20-shape-drift-bench.json; post-hoc summary: data/2026-11-20-shape-drift-posthoc.json.

The decomposition accounting was frozen in the pre-registration: on medians pooled over s ∈ {2.0, 2.5, 3.0}, each arm's growth Δ = pooled normalized median − its own s=1 median, in percentage points of nominal area. Interpolation share = Δ(none, LINEAR) − Δ(none, NEAREST); closing and opening shares analogously against the none arm under NEAREST; total = Δ(full, LINEAR); the interaction residual is what remains. This accounting answers "where does the growth come from", not "who contributes the area" — section 3.3 gives absolute areas as a cross-check.

Replication anchors first: at s=1 under the full pipeline, the circle's normalized median is 90.0 and the square's 109.0 — digit-for-digit the values measured in situ in 2026-11-08; the square under full+LINEAR reads 129.25 at s=2 (in situ: 129.2) and 134.78 at s=3 (in situ: 135.0). The isolated bench reproduces the field measurement, so its factor split is entitled to explain it.

## 3. Measurements

### 3.1 The drift landscape under the full pipeline

Median drift of normalized area vs nominal, full+LINEAR:

| Shape | s=1 | s=1.5 | s=2.0 | s=2.5 | s=3.0 |
|---|---|---|---|---|---|
| Circle r=6 | −20.4% | −14.9% | −5.2% | −8.5% | +3.2% |
| Square side 11 | −9.9% | −4.5% | +6.8% | +5.8% | +11.4% |
| Triangle | −12.1% | +0.1% | +16.1% | +10.8% | +24.3% |
| Pentagon | −2.7% | +1.5% | +8.4% | +5.6% | +13.1% |
| Hexagon | −7.3% | −0.4% | +9.5% | +6.1% | +16.2% |
| Diamond | −6.3% | +0.5% | +10.4% | +6.3% | +25.3% |
| Circle r=12 | −10.3% | −8.9% | −4.2% | −6.3% | −0.8% |
| Square side 21 | −2.7% | −1.2% | +4.1% | +3.4% | +6.2% |

Three readings. Every shape starts underestimated at s=1 (−2.7% to −20.4%), the circle deepest. Growth then stratifies by shape: at s=3 the acute group (triangle, diamond, hexagon) reaches +16% to +25%, the square +11.4%, the circle only +3.2% — "squares grow faster than circles" survives, but squares are not the fastest growers; acute polygons are. And the size controls are clean: at roughly 4× the area, s=3 drift is −0.8% (circle) and +6.2% (square) — drift shrinks with size, as a perimeter/area boundary effect should.

The curves are not monotone: most shapes dip at s=2.5 (circle −5.2% → −8.5% → +3.2%). That is pixel-grid alignment quantization, not physics; the decomposition therefore pools s ∈ {2.0, 2.5, 3.0} instead of trusting adjacent-scale differences.

### 3.2 Decomposition: the interpolation share is negative

Growth in percentage points of nominal area (own s=1 baseline, pooled s ∈ {2.0, 2.5, 3.0}):

| Shape | Base (none+NEAREST) | Interpolation share | Closing share | Opening share | Total (full+LINEAR) | Interaction |
|---|---|---|---|---|---|---|
| Circle r=6 | +6.79 | −0.49 | +4.93 | +1.34 | +15.25 | +2.68 |
| Square side 11 | +11.21 | −1.91 | 0.00 | +8.33 | +16.74 | −0.89 |
| Triangle | +9.88 | −1.53 | +5.95 | +9.27 | +28.18 | +4.61 |
| Pentagon | +5.95 | −0.88 | +3.28 | +0.64 | +11.04 | +2.05 |
| Hexagon | +7.89 | −1.45 | +3.02 | +3.80 | +16.79 | +3.53 |
| Diamond | +4.69 | +1.37 | +6.00 | +2.81 | +16.60 | +1.73 |
| Circle r=12 | +3.45 | −0.32 | +2.35 | −0.96 | +6.02 | +1.50 |
| Square side 21 | +5.80 | −0.98 | 0.00 | +2.28 | +6.86 | −0.24 |

The base term is the largest single block everywhere: do nothing but upscale with NEAREST — no new pixel values, a strictly binary mask — and normalized area still grows +3.45 to +11.21 points. The only possible source is the measurement itself: contourArea threads a polygon through boundary-pixel centres, cutting inside the true boundary; the larger the shape in pixels, the smaller the relative cut. Most of the "upscaling drift" is the s=1 underestimate being recovered, not area created by upscaling.

The interpolation share is negative for every shape except the diamond (−0.32 to −1.91): after mask thresholding, LINEAR's halo does not add area, it removes a little. The 2026-11-08 sentence blaming "interpolation halo at right-angle corners" for the square's drift had the sign wrong — the halo pixels mostly fall below the mask threshold and are cut. The one interpolation with a real area effect is CUBIC: in the none arm it exceeds LINEAR by +1.35 to +4.98 points on all eight shapes, because ringing pushes a ring of outside pixels over the threshold. CUBIC is not this pipeline's default (LINEAR is), so the effect is registered, not operational.

One accounting warning on the opening share: it is a growth difference, and the open arm's s=1 baseline is the most eroded (triangle: 110.0 vs 129.0 for the none arm), so identical endpoints produce larger "growth". The square's +8.33 opening share is mostly that baseline artefact — in absolute terms (next section) opening removes area from the square (−1.9), as erosion should. Read base, interpolation and closing shares directly from this table; read opening only together with section 3.3.

### 3.3 Absolute areas: closing fills acute corners only

Pooled normalized medians, s ∈ {2.0, 2.5, 3.0}, absolute values:

| Shape | s=1 none | NEAREST none | NEAREST close | NEAREST open | NEAREST full | LINEAR full |
|---|---|---|---|---|---|---|
| Circle r=6 | 96.0 | 103.68 | 109.25 | 99.20 | 107.25 | 107.25 |
| Square side 11 | 121.0 | 134.56 | 134.56 | 132.64 | 132.64 | 129.25 |
| Triangle | 129.0 | 141.36 | 148.80 | 133.96 | 145.64 | 145.25 |
| Hexagon | 127.0 | 137.04 | 140.89 | 132.88 | 139.38 | 139.38 |
| Diamond | 128.0 | 134.00 | 141.68 | 129.60 | 139.84 | 141.25 |

Closing's absolute increment (close-only minus none, both NEAREST): circle +5.6, square 0.0, triangle +7.4, hexagon +3.9, diamond +7.7. Corner filling is real for acute shapes — the 7×7 elliptical kernel fills exactly the notches between a polygon's vertices and its short edges, and sharper corners collect more fill — and exactly zero for the axis-aligned square, whose boundary offers the kernel nothing concave to fill; it had already been rounded to 109.0 by the opening at s=1. Opening's absolute effect is negative for every shape (−1.9 to −7.4), as expected.

So the square's "+24%" from 2026-11-08 finally decomposes as: cut to 109.0 at s=1 (−9.9%), then roughly +11 points of quantization recovery, about −2 net morphology, −2 to 0 interpolation, landing at +6.8% (s=2) to +11.4% (s=3) of nominal — the earlier +24% was the relative rise from the s=1 pipeline reading 109.0 to 135.0, consistent under conversion. The circle's +20% is the same story with a deeper baseline (90.0, −20.4%) and slower recovery, reaching only +3.2% by s=3.

### 3.4 Effective band widths: the worst shape is the acute polygon

Band width, per the pre-registration, = (max − median)/nominal over the 48 full+LINEAR readings at s ≥ 2: diamond 15.0, triangle 13.4, hexagon 13.0, circle r=6 8.3, pentagon 8.1, square 4.6, and the large controls 3.4 (circle r=12) and 2.0 (square side 21) points.

Two footnotes. The circle's 8.3 is mostly not replicate scatter — circles are rotation-invariant and jittered only in position, so their replicate spread is near zero; their pooled band is the non-monotone s-curve of section 3.1 (107.25 at s=2 to 116.67 at s=3) unfolding inside the pool. The square's 4.6 is likewise mostly s-trend. The polygons' bands contain genuine rotation scatter: the same triangle at a different heading recovers and fills differently — precisely the part a deployment cannot control. Updated conclusion: priced by worst shape, the margin premium belongs to acute polygons, whose bands run 8–10 points wider than the square's; their median drift is also higher (+24.3% triangle, +25.3% diamond at s=3), so a median-plus-band margin for acute clutter costs roughly 1.5× the square's.

## 4. Analysis and trade-offs

Three operational consequences. First, do not expect an interpolation change to fix drift: LINEAR and NEAREST differ by under 2 points here, and CUBIC is worse. The lever that exists is the measurement itself — pixel-count area (countNonZero) instead of contourArea, or explicitly modelling the quantization-recovery curve (drift as a function of pixel scale) in calibration — not the resampler. Second, the shape premium on margins must be priced on acute polygons: the 0.40 prescription of 2026-11-08 was priced on the square's band; if a scene's clutter is mostly petal shards and label corners, the premium goes up; if clutter is known to be round or square only, 0.40 still suffices. Third, calibration strata should be by pixel scale, not nominal area: at equal nominal area, a 2× difference in pixel size changes total growth by about 10 points (square side 11: +16.74 vs side 21: +6.86) — stratifying by nominal area while ignoring pixel scale is the same mistake this series keeps meeting in new clothes.

The correction to the earlier article should be stated plainly: of the two halves of its mechanism sentence, the interpolation half had the wrong sign, and the closing half holds only for acute shapes. Its operational conclusions (price margins on the worst shape's effective band; the 0.40 prescription) did not depend on the mechanism and still stand — but the identity of the worst shape changes to the acute polygon. That is the return on logging unisolated mechanisms as limitations: conclusions first, mechanism later, and a later refutation does not reach the conclusions.

## 5. Limitations and open questions

One: two nominal-area notes. The triangle's nominal area is counted at side 17 (125.2), while the drawn polygon at circumradius 10 has a continuous area of about 129.9 — a 3.7% accounting gap; all drift rates use 125.2, within-shape comparisons are unaffected, and cross-shape comparisons should remember the gap. The pentagon's nominal area is misstated in the pre-registration — I hand-computed (5/2)R²sin72° as 118.9; the correct value is 237.8 and is what all computations used. The pentagon was therefore drawn at about twice the small shapes' size and can only be read as a mid-size sample in cross-shape comparisons (its total growth, +11.04, sits between the small and large groups, consistent with the size effect). The pre-registration text is left uncorrected, and the error is logged here.

Two: the bench is a solid background, a single shape, no texture; agreement with the in-situ measurement rests on the s=1 and s=2/3 anchors (matched digit-for-digit). Textured real petal shards, and drift while adjacent to a host (the merging regime of 2026-11-07), are out of scope.

Three: the quantization-recovery account is a qualitative attribution consistent with the positive NEAREST/none-arm growth; it has not been nailed down by the direct experiment — re-measuring the same images with pixel-count area and watching the drift vanish. That experiment is queued in the topic pool.

Four: rotation scatter was measured for polygons over 0°–75°. The square and circle are rotation-invariant only in their axis-aligned reading; a square rotated 45° is the diamond arm, with the widest band of all (15.0). Square clutter at arbitrary headings should be priced at the diamond rate.

Five: CUBIC's overshoot share was measured only in the none arm (+1.35 to +4.98); its per-shape difference from LINEAR under the full pipeline was not expanded. This pipeline does not use CUBIC by default, so the item is registered only.

Pre-registration scorecard: P1 fully right (square drift +6.8% at s=2 and +11.4% at s=3, both inside the registered bands; circle below square at both). P2 wrong (interpolation share −1.91 for the square, −0.49 for the circle — opposite sign to "halo adds area"). P3 half right (closing share exceeds opening for circle and diamond; for the square closing is 0, and for the triangle closing is smaller in growth accounting but larger in absolute accounting, +7.4 vs −7.4 — the pre-registration failed to specify the accounting, and the lesson is recorded in section 3.2). P4 half right (triangle, diamond and hexagon bands, 13.0–15.0, all exceed the square's 4.6; but the circle's pooled band, 8.3, exceeds the square's — mostly s-trend, not scatter — and the hexagon sits with the triangle, not near the circle). P5 fully right (CUBIC exceeds LINEAR in the none arm on all eight shapes, by +1.35 to +4.98). P6 fully right (large-shape total growth: circle 6.02 vs 15.25, square 6.86 vs 16.74; median drift smaller in the same direction).

## 6. References

- Earlier articles in this series: 2026-11-08 (the square's +24% / maximum +26.6% and the circle's +20% / +9.5%, with the unisolated mechanism sentence), 2026-10-30 (clutter planting and the band-width concept), 2026-11-18 (the adjacent size-scan evidence), all under articles/ in this repository.
- This article's data: data/2026-11-20-shape-drift-bench.json (6,656 individual readings), pre-registration data/2026-11-20-shape-drift-prereg.md, post-hoc summary data/2026-11-20-shape-drift-posthoc.json (including the absolute-area table and the pentagon nominal-value correction note).
- Pipeline source: the Bloom-Counter detector, detector/color_segmentation.py — _petal_mask and the morphology order (close then open, 7×7 elliptical kernel), imported unmodified.
- OpenCV documentation: cv2.contourArea (polygon area through boundary-pixel centres) and the cv2.resize interpolation flags (INTER_LINEAR / INTER_CUBIC / INTER_NEAREST definitions and overshoot behaviour), docs.opencv.org.

——
Author: Guangyi Zhao. The bench code, experimental design and all data in this article are clean-room, original work; no client data or third-party restricted material was used. The correction to the earlier article's mechanism explanation is verifiable item by item against this article's raw data.
