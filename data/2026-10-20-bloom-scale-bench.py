"""Bloom-Counter distance / resolution calibration-drift bench (2026-10-20).

Follow-up to 2026-10-17. Question: the detector classifies by absolute
pixel-area thresholds (min_area=120, bloom_area_min=900, morph_kernel=7).
When the same scene is captured from farther away (geometric scale s) or
by a lower-resolution sensor (down-then-up resampling, geometry unchanged),
how do those thresholds drift, does the textbook s^2 rescaling fix them,
and where does it break?

Parts:
  A  Geometric scaling: resize by s (INTER_AREA), GT scaled by s.
     A1 fixed params / A2 s^2-scaled thresholds, kernel fixed /
     A3 s^2 thresholds + kernel scaled to odd approx of 7*s.
     Plus a brute-force sweep of bloom_area_min multipliers per scale.
  B  Resolution-only: down by r then up back to 1280x960 (INTER_LINEAR).
     Geometry / GT unchanged. Fixed params + threshold sweep.
  Area drift: raw contour areas (replicating detector internals) matched
     to GT, median area per class per condition vs the s^2 prediction.

Scoring: same greedy centre matching as 2026-10-17, tolerance expressed in
the image's own coordinates: tol = max(38*s_geom, 1.1*r_obj) where s_geom
is the geometric scale of that image (1.0 for part B).

Usage: .venv/bin/python 2026-10-20-bloom-scale-bench.py <repo> <out_json>
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "bloom-scale-bench.json"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_scale_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7


def odd_kernel(s):
    k = int(round(BASE_KERNEL * s))
    if k % 2 == 0:
        k += 1
    return max(3, k)


def extract_contours(image, kernel_size):
    """Replicate detector internals, returning contour-level records."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        x, y, w, h = cv2.boundingRect(cnt)
        out.append({"area": area, "x": x, "y": y, "w": w, "h": h,
                    "cx": x + w / 2.0, "cy": y + h / 2.0})
    return out


class ParamDetector(ColorSegmentationDetector):
    pass


def detect_with(image, min_area, bloom_min, kernel_size):
    det = ColorSegmentationDetector(min_area=int(min_area),
                                    bloom_area_min=int(bloom_min),
                                    morph_kernel=int(kernel_size))
    return det.detect(image)


def score(dets, objects, geom_scale=1.0):
    used = set(); tp = fp = 0
    per = {"bloom": [0, 0], "bud": [0, 0]}
    for d in dets:
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        tol = max(38.0 * geom_scale, objects[best]["r"] * 1.1) if best is not None else 0
        if best is not None and bd <= tol:
            used.add(best); tp += 1; per[d.label][0] += 1
        else:
            fp += 1
    fn = len(objects) - len(used)
    for i, o in enumerate(objects):
        if i not in used:
            per[o["label"]][1] += 1
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    tb = sum(1 for o in objects if o["label"] == "bloom")
    td = sum(1 for o in objects if o["label"] == "bud")
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_blooms": sum(1 for d in dets if d.label == "bloom"),
            "det_buds": sum(1 for d in dets if d.label == "bud"),
            "true_blooms": tb, "true_buds": td,
            "bloom_recall": round(per["bloom"][0] / max(1, tb), 4),
            "bud_recall": round(per["bud"][0] / max(1, td), 4)}


def micro(rows):
    tp = sum(r["tp"] for r in rows); fp = sum(r["fp"] for r in rows); fn = sum(r["fn"] for r in rows)
    prec = tp / (tp + fp) if tp + fp else 1.0; rec = tp / (tp + fn) if tp + fn else 1.0
    tb = sum(r["true_blooms"] for r in rows); td = sum(r["true_buds"] for r in rows)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_blooms": sum(r["det_blooms"] for r in rows), "true_blooms": tb,
            "det_buds": sum(r["det_buds"] for r in rows), "true_buds": td,
            "bloom_recall": round(sum(r["bloom_recall"] * r["true_blooms"] for r in rows) / max(1, tb), 4),
            "bud_recall": round(sum(r["bud_recall"] * r["true_buds"] for r in rows) / max(1, td), 4),
            "count_err_pct": round(100.0 * (sum(r["det_blooms"] + r["det_buds"] for r in rows) - (tb + td)) / max(1, tb + td), 2)}


def scaled_objects(objects, s):
    return [{"label": o["label"], "cx": o["cx"] * s, "cy": o["cy"] * s, "r": o["r"] * s}
            for o in objects]


def matched_areas(image, objects, kernel_size, geom_scale):
    """Contour areas matched (label-agnostic) to GT centres."""
    conts = extract_contours(image, kernel_size)
    areas = {"bloom": [], "bud": []}
    used = set()
    for o in objects:
        best, bd = None, 1e9
        for i, c in enumerate(conts):
            if i in used:
                continue
            dist = math.hypot(c["cx"] - o["cx"], c["cy"] - o["cy"])
            if dist < bd:
                bd, best = dist, i
        tol = max(38.0 * geom_scale, o["r"] * 1.1)
        if best is not None and bd <= tol:
            used.add(best)
            areas[o["label"]].append(conts[best]["area"])
    return areas


# ---------- base scenes ----------
bases = []
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    bases.append((seed, cv2.imread(p), truth["objects"]))

R = {"detector": "color-segmentation-v0.1",
     "base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM, "morph_kernel": BASE_KERNEL},
     "n_scenes": len(bases),
     "n_objects": sum(len(o) for _, _, o in bases),
     "scoring": "greedy centre matching, label must match, tol=max(38*geom_scale, 1.1*r) in image coordinates",
     "resize_down": "INTER_AREA", "resize_up": "INTER_LINEAR"}

# sanity: replica contours vs detector at baseline
base_det = ColorSegmentationDetector()
sanity = micro([score(base_det.detect(im), objs, 1.0) for _, im, objs in bases])
R["baseline_sanity"] = sanity

# baseline median contour areas (kernel 7)
base_areas = {"bloom": [], "bud": []}
for _, im, objs in bases:
    a = matched_areas(im, objs, BASE_KERNEL, 1.0)
    base_areas["bloom"] += a["bloom"]; base_areas["bud"] += a["bud"]
R["baseline_median_contour_area"] = {
    k: (round(float(np.median(v)), 1) if v else None) for k, v in base_areas.items()}
R["baseline_matched_contours"] = {k: len(v) for k, v in base_areas.items()}

# ---------- Part A: geometric scaling ----------
SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.22]
MULTS = [0.25, 0.4, 0.55, 0.7, 0.85, 1.0, 1.15, 1.3]
R["partA_geometric"] = {}
for s in SCALES:
    h = int(round(960 * s)); w = int(round(1280 * s))
    imgs = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA), scaled_objects(objs, s))
            for _, im, objs in bases]
    entry = {"image_size": [w, h], "s2": round(s * s, 4),
             "theory_bloom_min": round(BASE_BLOOM * s * s, 1),
             "theory_min_area": round(BASE_MIN * s * s, 1),
             "kernel_scaled": odd_kernel(s)}
    entry["A1_fixed"] = micro([score(detect_with(im, BASE_MIN, BASE_BLOOM, BASE_KERNEL), objs, s)
                               for im, objs in imgs])
    entry["A2_s2_thresholds_kernel_fixed"] = micro(
        [score(detect_with(im, max(1, round(BASE_MIN * s * s)), max(1, round(BASE_BLOOM * s * s)), BASE_KERNEL), objs, s)
         for im, objs in imgs])
    entry["A3_s2_thresholds_kernel_scaled"] = micro(
        [score(detect_with(im, max(1, round(BASE_MIN * s * s)), max(1, round(BASE_BLOOM * s * s)), odd_kernel(s)), objs, s)
         for im, objs in imgs])
    # threshold sweep (thresholds-only scaling family: min_area s^2, kernel fixed 7)
    sweep = {}
    for m in MULTS:
        t = max(1, round(BASE_BLOOM * s * s * m))
        sweep[f"x{m}"] = micro([score(detect_with(im, max(1, round(BASE_MIN * s * s)), t, BASE_KERNEL), objs, s)
                                for im, objs in imgs])
        sweep[f"x{m}"]["bloom_min_used"] = t
    entry["sweep_kernel_fixed"] = sweep
    best_key = max(MULTS, key=lambda m: (sweep[f"x{m}"]["f1"], -abs(m - 1.0)))
    entry["sweep_best"] = {"mult": best_key, "bloom_min": sweep[f"x{best_key}"]["bloom_min_used"],
                           "f1": sweep[f"x{best_key}"]["f1"]}
    # raw area drift (kernel fixed 7)
    areas = {"bloom": [], "bud": []}
    for im, objs in imgs:
        a = matched_areas(im, objs, BASE_KERNEL, s)
        areas["bloom"] += a["bloom"]; areas["bud"] += a["bud"]
    med = {}
    for k in ("bloom", "bud"):
        if areas[k]:
            m = float(np.median(areas[k]))
            med[k] = {"median_area": round(m, 1), "n_matched": len(areas[k]),
                      "median_over_s2": round(m / (s * s), 1),
                      "ratio_to_baseline_median": round(m / (R["baseline_median_contour_area"][k] * s * s), 4)
                      if R["baseline_median_contour_area"][k] else None}
        else:
            med[k] = {"median_area": None, "n_matched": 0}
    entry["matched_area_drift_kernel7"] = med
    R["partA_geometric"][f"s={s}"] = entry
    print(f"A s={s} done", flush=True)

# ---------- Part B: resolution-only (down-up) ----------
RES = [1.0, 0.5, 0.33, 0.25, 0.167, 0.125]
R["partB_resolution_downup"] = {}
for r in RES:
    if r == 1.0:
        imgs = [(im, objs) for _, im, objs in bases]
    else:
        imgs = []
        for _, im, objs in bases:
            small = cv2.resize(im, (int(round(1280 * r)), int(round(960 * r))),
                               interpolation=cv2.INTER_AREA)
            back = cv2.resize(small, (1280, 960), interpolation=cv2.INTER_LINEAR)
            imgs.append((back, objs))
    entry = {"effective_pixels": [int(round(1280 * r)), int(round(960 * r))]}
    entry["B1_fixed"] = micro([score(detect_with(im, BASE_MIN, BASE_BLOOM, BASE_KERNEL), objs, 1.0)
                               for im, objs in imgs])
    sweep = {}
    for m in MULTS:
        t = max(1, round(BASE_BLOOM * m))
        sweep[f"x{m}"] = micro([score(detect_with(im, BASE_MIN, t, BASE_KERNEL), objs, 1.0)
                                for im, objs in imgs])
        sweep[f"x{m}"]["bloom_min_used"] = t
    entry["sweep"] = sweep
    best_key = max(MULTS, key=lambda m: (sweep[f"x{m}"]["f1"], -abs(m - 1.0)))
    entry["sweep_best"] = {"mult": best_key, "bloom_min": sweep[f"x{best_key}"]["bloom_min_used"],
                           "f1": sweep[f"x{best_key}"]["f1"]}
    areas = {"bloom": [], "bud": []}
    for im, objs in imgs:
        a = matched_areas(im, objs, BASE_KERNEL, 1.0)
        areas["bloom"] += a["bloom"]; areas["bud"] += a["bud"]
    med = {}
    for k in ("bloom", "bud"):
        if areas[k]:
            m = float(np.median(areas[k]))
            med[k] = {"median_area": round(m, 1), "n_matched": len(areas[k]),
                      "ratio_to_baseline_median": round(m / R["baseline_median_contour_area"][k], 4)
                      if R["baseline_median_contour_area"][k] else None}
        else:
            med[k] = {"median_area": None, "n_matched": 0}
    entry["matched_area_drift"] = med
    R["partB_resolution_downup"][f"r={r}"] = entry
    print(f"B r={r} done", flush=True)

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print(json.dumps({"baseline": R["baseline_sanity"],
                  "baseline_median": R["baseline_median_contour_area"]}, indent=2))
