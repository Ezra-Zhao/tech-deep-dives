"""Floor-margin vs bud lower-tail bench (2026-11-08).

Fulfils the undecided trade-off in 2026-10-30 sec.4.3: raising the
scaled min_area floor by a margin m should suppress the +/-7% drift
band leaks, but might kill true buds whose contour areas sit in the
same band. Part A measures the bud contour-area lower tail on 12 scene
sets (original + 2 holdouts) and its normalised drift at s>1. Part B
replants the exact 2026-10-30 clutter (same rng/plan) on the original
4 scenes and sweeps m x s on clean + cluttered images.

Design frozen in data/2026-11-08-floor-margin-prereg.md.
Usage: .venv/bin/python 2026-11-08-floor-margin-bench.py <repo> <out_json>
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "2026-11-08-floor-margin-bench.json"
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_margin_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

ORIG = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]
HOLD1 = [(505, 33, 19), (606, 31, 17), (707, 38, 21), (808, 29, 15)]
HOLD2 = [(909, 34, 20), (1010, 30, 17), (1111, 37, 21), (1212, 32, 18)]
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 1.5, 2.0, 2.5, 3.0]
MARGINS = [0.0, 0.07, 0.15, 0.25, 0.40, 0.60, 1.00]
COLORS = {"pink": (147, 20, 255), "white": (245, 245, 245), "yellow": (0, 215, 255),
          "blue": (255, 0, 0)}
SUB_R = [3, 4, 5, 6]
MID_R = [7, 10]
LARGE_R = [14]


def log(obj):
    with open(PROG, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def load_scene(seed, nb, nd):
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    return cv2.imread(p), truth["objects"]


def contours_of(image, kernel_size=BASE_KERNEL):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    m = ColorSegmentationDetector._petal_mask(hsv)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [(c, float(cv2.contourArea(c))) for c in cnts]


def gt_areas(image, objects, s=1.0):
    """Contour area (normalised by s^2) of the contour holding each GT centre."""
    cnts = contours_of(image)
    rows = []
    for o in objects:
        cx, cy = o["cx"] * s, o["cy"] * s
        a = None
        for c, ar in cnts:
            if ar >= BASE_MIN * s * s and cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                a = ar / (s * s)
                break
        rows.append({"label": o["label"], "r": o["r"], "area_norm": None if a is None else round(a, 1)})
    return rows


def quantiles(vals):
    if not vals:
        return None
    v = np.array(vals)
    return {"n": len(v), "min": round(float(v.min()), 1),
            "p5": round(float(np.percentile(v, 5)), 1),
            "p25": round(float(np.percentile(v, 25)), 1),
            "median": round(float(np.median(v)), 1),
            "p75": round(float(np.percentile(v, 75)), 1),
            "max": round(float(v.max()), 1)}


# ---------- clutter planting: verbatim plan/rng from 2026-10-30 ----------
def stratum(r, control=False):
    if control:
        return "control_blue"
    if r in SUB_R:
        return "subfloor"
    if r in MID_R:
        return "mid"
    return "large"


def plant_clutter(img, objects, seed):
    rng = np.random.default_rng(90000 + seed)
    h, w = img.shape[:2]
    out = img.copy()
    items = []
    plan = []
    vis_cols = ["pink", "white", "yellow"]
    idx = 0
    for r in SUB_R + MID_R + LARGE_R:
        for shape in ("circle", "square"):
            for _ in range(4):
                plan.append((r, vis_cols[idx % 3], shape, False)); idx += 1
    for _ in range(8):
        plan.append((10, "blue", "circle", True))
    placed = []
    for r, colour, shape, control in plan:
        ok = False
        for _ in range(600):
            cx = int(rng.integers(30 + r, w - 30 - r))
            cy = int(rng.integers(30 + r, h - 30 - r))
            if any(math.hypot(cx - o["cx"], cy - o["cy"]) <= o["r"] + r + 20 for o in objects):
                continue
            if any(math.hypot(cx - x, cy - y) <= rr + r + 20 for x, y, rr in placed):
                continue
            ok = True
            break
        if not ok:
            continue
        placed.append((cx, cy, r))
        bgr = COLORS[colour]
        if shape == "circle":
            cv2.circle(out, (cx, cy), r, bgr, -1)
            nominal = math.pi * r * r
        else:
            side = int(round(r * math.sqrt(math.pi)))
            cv2.rectangle(out, (cx - side // 2, cy - side // 2),
                          (cx - side // 2 + side, cy - side // 2 + side), bgr, -1)
            nominal = float(side * side)
        items.append({"cx": cx, "cy": cy, "r": r, "colour": colour, "shape": shape,
                      "control": control, "stratum": stratum(r, control),
                      "nominal_area": round(nominal, 1)})
    return out, items


def detect_with(image, min_area, bloom_min, kernel_size):
    det = ColorSegmentationDetector(min_area=int(round(min_area)),
                                    bloom_area_min=int(round(bloom_min)),
                                    morph_kernel=int(kernel_size))
    return det.detect(image)


def evaluate(dets, objects, items, s):
    used_obj = set(); tp = 0
    per = {"bloom": 0, "bud": 0}
    det_used = set()
    for di, d in enumerate(dets):
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used_obj or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None and bd <= max(38.0 * s, objects[best]["r"] * s * 1.1):
            used_obj.add(best); det_used.add(di); tp += 1; per[d.label] += 1
    fp_dets = [d for i, d in enumerate(dets) if i not in det_used]
    taken = set(); passed = []
    for it in items:
        cx, cy = it["cx"] * s, it["cy"] * s
        tol = max(18.0 * s, 1.2 * it["r"] * s + 6)
        best, bd = None, 1e9
        for j, d in enumerate(fp_dets):
            if j in taken:
                continue
            dist = math.hypot(d.cx - cx, d.cy - cy)
            if dist < bd:
                bd, best = dist, j
        hit = best is not None and bd <= tol
        if hit:
            taken.add(best)
        passed.append(hit)
    fp = len(dets) - tp
    fn = len(objects) - tp
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / len(objects) if objects else 1.0
    res = {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
           "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
           "bud_recall": round(per["bud"] / max(1, sum(1 for o in objects if o["label"] == "bud")), 4),
           "bloom_recall": round(per["bloom"] / max(1, sum(1 for o in objects if o["label"] == "bloom")), 4),
           "det_total": len(dets), "clutter_passed": int(sum(passed))}

    def rate(sel):
        sub = [(it, p) for it, p in zip(items, passed) if sel(it)]
        return {"passed": int(sum(p for _, p in sub)), "total": len(sub),
                "rate": round(sum(p for _, p in sub) / len(sub), 4) if sub else None}
    res["pass_true_subfloor"] = rate(lambda it: it["stratum"] == "subfloor" and it["nominal_area"] < 120)
    res["pass_r6_square"] = rate(lambda it: it["r"] == 6 and it["shape"] == "square")
    res["pass_radius_subfloor"] = rate(lambda it: it["stratum"] == "subfloor")
    res["pass_by_radius"] = {f"r={r}": rate(lambda it, r=r: it["r"] == r and not it["control"])
                             for r in SUB_R + MID_R + LARGE_R}
    res["pass_mid"] = rate(lambda it: it["stratum"] == "mid")
    res["pass_large"] = rate(lambda it: it["stratum"] == "large")
    res["pass_control"] = rate(lambda it: it["control"])
    return res


def pooled(rows):
    tp = sum(r["tp"] for r in rows); fp = sum(r["fp"] for r in rows); fn = sum(r["fn"] for r in rows)
    prec = tp / (tp + fp) if tp + fp else 1.0; rec = tp / (tp + fn) if tp + fn else 1.0
    out = {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
           "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
           "det_total": sum(r["det_total"] for r in rows),
           "clutter_passed": sum(r["clutter_passed"] for r in rows)}
    buds = sum(r["bud_recall"] * 1 for r in rows)  # placeholder replaced below by caller counts
    for key in ("pass_true_subfloor", "pass_r6_square", "pass_radius_subfloor", "pass_mid", "pass_large", "pass_control"):
        p = sum(r[key]["passed"] for r in rows); t = sum(r[key]["total"] for r in rows)
        out[key] = {"passed": p, "total": t, "rate": round(p / t, 4) if t else None}
    merged = {}
    for r in rows:
        for k, v in r["pass_by_radius"].items():
            mm = merged.setdefault(k, {"passed": 0, "total": 0})
            mm["passed"] += v["passed"]; mm["total"] += v["total"]
    for v in merged.values():
        v["rate"] = round(v["passed"] / v["total"], 4) if v["total"] else None
    out["pass_by_radius"] = merged
    return out


R = {"base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM, "morph_kernel": BASE_KERNEL},
     "scales": SCALES, "margins": MARGINS, "prereg": "data/2026-11-08-floor-margin-prereg.md"}

# ---------- Part A: distributions ----------
dist = {}
all_bud, all_bloom = [], []
for name, scenes in (("orig", ORIG), ("hold1", HOLD1), ("hold2", HOLD2)):
    rows = []
    for seed, nb, nd in scenes:
        img, objs = load_scene(seed, nb, nd)
        rows.extend(gt_areas(img, objs, 1.0))
        del img
    buds = [r["area_norm"] for r in rows if r["label"] == "bud" and r["area_norm"] is not None]
    blooms = [r["area_norm"] for r in rows if r["label"] == "bloom" and r["area_norm"] is not None]
    all_bud += buds; all_bloom += blooms
    dist[name] = {"bud": quantiles(buds), "bloom": quantiles(blooms),
                  "bud_missing": sum(1 for r in rows if r["label"] == "bud" and r["area_norm"] is None),
                  "bud_in_drift_band_111.6_128.4": sum(1 for a in buds if 111.6 <= a <= 128.4),
                  "bud_below_150": sum(1 for a in buds if a < 150),
                  "bud_below_180": sum(1 for a in buds if a < 180),
                  "bud_below_192": sum(1 for a in buds if a < 192),
                  "bud_below_240": sum(1 for a in buds if a < 240)}
    log({"stage": "dist", "set": name, "bud_min": dist[name]["bud"]["min"],
         "bud_n": dist[name]["bud"]["n"], "band": dist[name]["bud_in_drift_band_111.6_128.4"]})
dist["all"] = {"bud": quantiles(all_bud), "bloom": quantiles(all_bloom),
               "bud_in_drift_band_111.6_128.4": sum(1 for a in all_bud if 111.6 <= a <= 128.4)}
R["distribution_s1"] = dist

# orig lower tail vs s (normalised)
tail = {}
orig_bases = []
for seed, nb, nd in ORIG:
    img, objs = load_scene(seed, nb, nd)
    orig_bases.append((seed, img, objs))
for s in SCALES:
    rows = []
    for seed, img, objs in orig_bases:
        big = cv2.resize(img, (int(round(1280 * s)), int(round(960 * s))), interpolation=cv2.INTER_LINEAR)
        rows.extend(gt_areas(big, objs, s))
        del big
    buds = [r["area_norm"] for r in rows if r["label"] == "bud" and r["area_norm"] is not None]
    tail[f"s={s}"] = {"bud": quantiles(buds),
                      "bud_missing": sum(1 for r in rows if r["label"] == "bud" and r["area_norm"] is None)}
    log({"stage": "tail", "s": s, "bud_min_norm": tail[f"s={s}"]["bud"]["min"]})
R["orig_tail_vs_s"] = tail

# ---------- Part B: margin x scale cost curve ----------
cluttered = []
plant_report = {}
for seed, img, objs in orig_bases:
    cimg, items = plant_clutter(img, objs, seed)
    cluttered.append((seed, cimg, objs, items))
    plant_report[str(seed)] = len(items)
R["plant_report"] = plant_report
log({"stage": "planted", "report": plant_report})

R["curve"] = {}
for s in SCALES:
    w, h = int(round(1280 * s)), int(round(960 * s))
    big_clean = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_LINEAR),
                  [{"label": o["label"], "cx": o["cx"] * s, "cy": o["cy"] * s, "r": o["r"] * s} for o in objs])
                 for _, im, objs in orig_bases]
    big_clut = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_LINEAR),
                 [{"label": o["label"], "cx": o["cx"] * s, "cy": o["cy"] * s, "r": o["r"] * s} for o in objs],
                 items)
                for _, im, objs, items in cluttered]
    n_bud = sum(1 for _, objs in big_clean for o in objs if o["label"] == "bud")
    entry = {}
    for m in MARGINS:
        floor = BASE_MIN * s * s * (1 + m)
        bloom_min = BASE_BLOOM * s * s
        clean_rows = [evaluate(detect_with(im, floor, bloom_min, BASE_KERNEL), objs, [], s)
                      for im, objs in big_clean]
        clut_rows = [evaluate(detect_with(im, floor, bloom_min, BASE_KERNEL), objs, items, s)
                     for im, objs, items in big_clut]
        cp = pooled(clean_rows); kp = pooled(clut_rows)
        # exact pooled bud recall from per-row tp accounting: recompute via fn split is
        # not separable; use per-row bud_recall weighted by scene bud counts
        bud_counts = [sum(1 for o in objs if o["label"] == "bud") for _, objs in big_clean]
        cp["bud_recall"] = round(sum(r["bud_recall"] * c for r, c in zip(clean_rows, bud_counts)) / sum(bud_counts), 4)
        kp["bud_recall"] = round(sum(r["bud_recall"] * c for r, c in zip(clut_rows, bud_counts)) / sum(bud_counts), 4)
        entry[f"m={m}"] = {"floor": int(round(floor)), "clean": cp, "cluttered": kp}
        log({"stage": "cell", "s": s, "m": m, "clean_bud_recall": cp["bud_recall"],
             "true_sub_leak": kp["pass_true_subfloor"], "sq_leak": kp["pass_r6_square"],
             "clut_prec": kp["precision"]})
    R["curve"][f"s={s}"] = entry
    del big_clean, big_clut
    with open(OUT, "w") as f:
        json.dump(R, f, indent=2, ensure_ascii=False)

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
log({"stage": "DONE", "out": OUT})
