"""Bloom-Counter input-resampling vs parameter-scaling bench (2026-10-24).

Follow-up to 2026-10-20 (calibration drift). That article compared:
  A3  native small frame + s^2-scaled thresholds + s-scaled kernel
  B   down-then-up images fed at baseline size with FIXED params
but never ran the head-to-head deployment question: given a native small
frame (1280*s x 960*s), which route serves it better --
  P  parameter scaling on the native frame (A3 recipe), or
  U  upsample the frame back to 1280x960 first, then fixed baseline params?
and, for the upsample route, at which pipeline stage do losses occur?

Routes per scale s:
  P        native frame, min_area=120*s^2, bloom=900*s^2, kernel=odd(7*s)>=3
  U_LINEAR up INTER_LINEAR -> 1280x960, params 120/900/7
  U_CUBIC  up INTER_CUBIC  -> 1280x960, params 120/900/7
  U_NEAREST up INTER_NEAREST -> 1280x960, params 120/900/7

Stage decomposition (per route, label-agnostic centre matching):
  stage1_mask     components in the raw HSV petal mask (no morphology)
  stage2_morph    contours after CLOSE+OPEN morphology
  stage3_minarea  stage2 contours passing the route's min_area
  stage4_final    detector output; matched-with-correct-label vs migrated
Also: matched contour area medians per class (post-morphology), bud
short-axis (min bounding-rect side) medians, and per-image detect time.

Scoring identical to 2026-10-17/20: greedy centre matching, label must
match for a hit, tol = max(38*g, 1.1*r) in the coordinates of the image
fed to the detector, where g is that image's geometric scale vs baseline
(1.0 for upsampled routes, s for the native route).

Usage: .venv/bin/python 2026-10-24-bloom-resample-bench.py <repo> <out_json>
"""
import json, math, os, sys, time
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "bloom-resample-bench.json"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_resample_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.22, 0.15, 0.10, 0.07]
INTERP = {"U_LINEAR": cv2.INTER_LINEAR, "U_CUBIC": cv2.INTER_CUBIC,
          "U_NEAREST": cv2.INTER_NEAREST}


def odd_kernel(s):
    k = int(round(BASE_KERNEL * s))
    if k % 2 == 0:
        k += 1
    return max(3, k)


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


def mask_stages(image, kernel_size):
    """Return (raw_mask_components, post_morph_contours) as centre+area+box dicts."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    raw = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        raw.append({"area": float(a), "cx": float(cents[i][0]), "cy": float(cents[i][1]),
                    "w": int(w), "h": int(h)})
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    m2 = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    m2 = cv2.morphologyEx(m2, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(m2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    post = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        post.append({"area": float(cv2.contourArea(cnt)), "cx": x + w / 2.0, "cy": y + h / 2.0,
                     "w": int(w), "h": int(h)})
    return raw, post


def match_label_agnostic(items, objects, geom_scale):
    """For each GT object, the nearest unused item within tol. Returns per-obj item or None."""
    used = set(); out = []
    for o in objects:
        best, bd = None, 1e9
        for i, c in enumerate(items):
            if i in used:
                continue
            dist = math.hypot(c["cx"] - o["cx"], c["cy"] - o["cy"])
            if dist < bd:
                bd, best = dist, i
        tol = max(38.0 * geom_scale, o["r"] * 1.1)
        if best is not None and bd <= tol:
            used.add(best); out.append(items[best])
        else:
            out.append(None)
    return out


def stage_stats(route_images):
    """route_images: list of (image, objects, geom_scale, kernel, min_area, bloom_min).
    Returns survival counts per class per stage + area/short-axis medians."""
    agg = {}
    for cls in ("bloom", "bud"):
        agg[cls] = {"n": 0, "s1_mask": 0, "s2_morph": 0, "s3_minarea": 0,
                    "areas": [], "short_axis": [], "migrated": 0, "correct": 0, "lost_final": 0}
    for image, objects, g, kernel, min_area, bloom_min in route_images:
        raw, post = mask_stages(image, kernel)
        m1 = match_label_agnostic(raw, objects, g)
        m2 = match_label_agnostic(post, objects, g)
        dets = detect_with(image, min_area, bloom_min, kernel)
        det_items = [{"cx": d.cx, "cy": d.cy, "label": d.label} for d in dets]
        for o, a, b in zip(objects, m1, m2):
            A = agg[o["label"]]; A["n"] += 1
            if a is not None:
                A["s1_mask"] += 1
            if b is not None:
                A["s2_morph"] += 1
                A["areas"].append(b["area"]); A["short_axis"].append(min(b["w"], b["h"]))
                if b["area"] >= min_area:
                    A["s3_minarea"] += 1
            # final: nearest detection (any label) to this object
            best, bd = None, 1e9
            for d in det_items:
                dist = math.hypot(d["cx"] - o["cx"], d["cy"] - o["cy"])
                if dist < bd:
                    bd, best = dist, d
            tol = max(38.0 * g, o["r"] * 1.1)
            if best is not None and bd <= tol:
                if best["label"] == o["label"]:
                    A["correct"] += 1
                else:
                    A["migrated"] += 1
            else:
                A["lost_final"] += 1
    out = {}
    for cls, A in agg.items():
        out[cls] = {"n": A["n"], "s1_mask": A["s1_mask"], "s2_morph": A["s2_morph"],
                    "s3_minarea": A["s3_minarea"],
                    "median_area_post_morph": round(float(np.median(A["areas"])), 1) if A["areas"] else None,
                    "median_short_axis_post_morph": round(float(np.median(A["short_axis"])), 1) if A["short_axis"] else None,
                    "final_correct": A["correct"], "final_migrated": A["migrated"],
                    "final_lost": A["lost_final"]}
    return out


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
     "scoring": "greedy centre matching, label must match, tol=max(38*geom_scale, 1.1*r) in fed-image coordinates",
     "native_down": "INTER_AREA", "scales": SCALES,
     "note": "U routes feed an image pixel-identical to the 2026-10-20 part-B down-up chain at r=s; P route is the 2026-10-20 A3 recipe."}

base_det = ColorSegmentationDetector()
R["baseline_sanity"] = micro([score(base_det.detect(im), objs, 1.0) for _, im, objs in bases])

R["results"] = {}
for s in SCALES:
    h = int(round(960 * s)); w = int(round(1280 * s))
    natives = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA), scaled_objects(objs, s))
               for _, im, objs in bases]
    entry = {"native_size": [w, h], "kernel_P": odd_kernel(s),
             "min_area_P": max(1, round(BASE_MIN * s * s)),
             "bloom_min_P": max(1, round(BASE_BLOOM * s * s))}
    routes = {}
    # Route P: native + scaled params
    routes["P_param_scaling"] = (
        [(im, objs) for im, objs in natives], s,
        max(1, round(BASE_MIN * s * s)), max(1, round(BASE_BLOOM * s * s)), odd_kernel(s))
    # Routes U: upsample to baseline + fixed params
    for name, interp in INTERP.items():
        if s == 1.0:
            ups = [(im, objs) for _, im, objs in bases]
        else:
            ups = [(cv2.resize(im, (1280, 960), interpolation=interp), objs_base)
                   for (im, _), (_, _, objs_base) in zip(natives, bases)]
        routes[name] = (ups, 1.0, BASE_MIN, BASE_BLOOM, BASE_KERNEL)
    for name, (imgs, g, mn, bm, k) in routes.items():
        t0 = time.perf_counter()
        rows = [score(detect_with(im, mn, bm, k), objs, g) for im, objs in imgs]
        dt = (time.perf_counter() - t0) / max(1, len(imgs))
        r_entry = micro(rows)
        r_entry["median_detect_s_per_image"] = round(dt, 4)
        r_entry["stages"] = stage_stats([(im, objs, g, k, mn, bm) for im, objs in imgs])
        entry[name] = r_entry
    R["results"][f"s={s}"] = entry
    print(f"s={s} done: " + " | ".join(
        f"{n} F1={entry[n]['f1']} budR={entry[n]['bud_recall']}" for n in
        ["P_param_scaling", "U_LINEAR", "U_CUBIC", "U_NEAREST"]), flush=True)

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print(json.dumps({"baseline": R["baseline_sanity"]}, indent=2))
