"""Bloom-Counter lighting & occlusion bench (2026-10-17).

Runs the UNMODIFIED repo detector (detector/color_segmentation.py) on
simulated scenes from the repo's own simulator, then violates the
simulator's two hidden assumptions:
  (a) uniform, detector-friendly lighting  -> gamma / exposure / shadow
      gradient / half-shadow / warm cast / low-light noise transforms
  (b) flowers never overlap (simulator._place enforces non-overlap)
      -> leaf occluders painted over known flower centres, and extra
         blooms drawn at controlled offsets from existing blooms.
Scoring is centre-distance matching against ground truth (not just raw
counts), micro-averaged over 4 scenes. Two cheap mitigations are also
measured: gray-world white balance + CLAHE on V (for lighting), and an
area-based split estimator (for merged/overlapping blooms).

Usage: .venv/bin/python 2026-10-17-bloom-bench.py <repo> <out_json>
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "bloom-bench.json"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image, _draw_bloom, LEAF_BASE
from detector.color_segmentation import ColorSegmentationDetector

DET = ColorSegmentationDetector()
SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]

# ---------- scoring ----------
def score(dets, objects):
    """Greedy centre-distance matching, label must match."""
    used = set(); tp = fp = 0
    per_label = {"bloom": [0, 0], "bud": [0, 0]}  # tp, fn
    for d in dets:
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None and bd <= max(38.0, objects[best]["r"] * 1.1):
            used.add(best); tp += 1; per_label[d.label][0] += 1
        else:
            fp += 1
    fn = len(objects) - len(used)
    for i, o in enumerate(objects):
        if i not in used:
            per_label[o["label"]][1] += 1
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    nb = sum(1 for d in dets if d.label == "bloom"); nd = sum(1 for d in dets if d.label == "bud")
    tb = sum(1 for o in objects if o["label"] == "bloom"); td = sum(1 for o in objects if o["label"] == "bud")
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "det_blooms": nb, "det_buds": nd, "true_blooms": tb, "true_buds": td,
            "bloom_recall": round(per_label["bloom"][0] / max(1, tb), 4),
            "bud_recall": round(per_label["bud"][0] / max(1, td), 4)}

def micro(rows):
    tp = sum(r["tp"] for r in rows); fp = sum(r["fp"] for r in rows); fn = sum(r["fn"] for r in rows)
    prec = tp / (tp + fp) if tp + fp else 1.0; rec = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_blooms": sum(r["det_blooms"] for r in rows), "true_blooms": sum(r["true_blooms"] for r in rows),
            "det_buds": sum(r["det_buds"] for r in rows), "true_buds": sum(r["true_buds"] for r in rows),
            "bloom_recall": round(sum(r["bloom_recall"] * r["true_blooms"] for r in rows) / max(1, sum(r["true_blooms"] for r in rows)), 4),
            "bud_recall": round(sum(r["bud_recall"] * r["true_buds"] for r in rows) / max(1, sum(r["true_buds"] for r in rows)), 4),
            "count_err_pct": round(100.0 * (sum(r["det_blooms"] + r["det_buds"] for r in rows) - sum(r["true_blooms"] + r["true_buds"] for r in rows)) / max(1, sum(r["true_blooms"] + r["true_buds"] for r in rows)), 2)}

# ---------- lighting transforms (BGR uint8 in/out) ----------
def gamma(img, g):
    lut = np.array([min(255, int(((i / 255.0) ** g) * 255)) for i in range(256)], dtype=np.uint8)
    return cv2.LUT(img, lut)

def exposure(img, alpha, beta):
    return np.clip(img.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)

def shadow_gradient(img, lo=0.35):
    h, w = img.shape[:2]
    ramp = np.linspace(lo, 1.0, w, dtype=np.float32)[None, :, None]
    return np.clip(img.astype(np.float32) * ramp, 0, 255).astype(np.uint8)

def half_shadow(img, frac=0.45, f=0.40):
    out = img.astype(np.float32); out[:, : int(img.shape[1] * frac)] *= f
    return np.clip(out, 0, 255).astype(np.uint8)

def warm_cast(img):
    out = img.astype(np.float32); out[:, :, 0] *= 0.72; out[:, :, 2] *= 1.18
    return np.clip(out, 0, 255).astype(np.uint8)

def low_light_noise(img, seed):
    dark = gamma(img, 1.9)
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 12, dark.shape)
    return np.clip(dark.astype(np.float32) + noise, 0, 255).astype(np.uint8)

def wb_clahe(img):
    """Gray-world white balance + CLAHE on the V channel."""
    f = img.astype(np.float32)
    means = f.reshape(-1, 3).mean(axis=0); gray = means.mean()
    for c in range(3):
        f[:, :, c] *= gray / max(1.0, means[c])
    f = np.clip(f, 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    hsv[:, :, 2] = clahe.apply(hsv[:, :, 2])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

LIGHTING = {
    "baseline": lambda im, s: im,
    "gamma_0.6_brighter": lambda im, s: gamma(im, 0.6),
    "gamma_1.6_darker": lambda im, s: gamma(im, 1.6),
    "gamma_2.2_much_darker": lambda im, s: gamma(im, 2.2),
    "exposure_+60_washout": lambda im, s: exposure(im, 1.25, 60),
    "exposure_-50_dim": lambda im, s: exposure(im, 0.78, -50),
    "shadow_gradient_0.35-1.0": lambda im, s: shadow_gradient(im),
    "half_shadow_x0.40": lambda im, s: half_shadow(im),
    "warm_cast": lambda im, s: warm_cast(im),
    "low_light_+noise": lambda im, s: low_light_noise(im, s),
}

# ---------- build base scenes ----------
bases = []
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    bases.append((seed, cv2.imread(p), truth["objects"]))

R = {"detector": DET.name, "params": {"min_area": DET.min_area, "bloom_area_min": DET.bloom_area_min, "morph_kernel": DET.morph_kernel},
     "n_scenes": len(bases), "scoring": "greedy centre-distance matching, label must match, tol=max(38px, 1.1*r)"}

# ---------- lighting sweep ----------
R["lighting"] = {}
for name, fn in LIGHTING.items():
    R["lighting"][name] = micro([score(DET.detect(fn(im, seed)), objs) for seed, im, objs in bases])

# mitigation on the harsh conditions
R["lighting_mitigated_wb_clahe"] = {}
for name in ["gamma_1.6_darker", "gamma_2.2_much_darker", "exposure_+60_washout", "shadow_gradient_0.35-1.0", "half_shadow_x0.40", "warm_cast", "low_light_+noise"]:
    fn = LIGHTING[name]
    R["lighting_mitigated_wb_clahe"][name] = micro([score(DET.detect(wb_clahe(fn(im, seed))), objs) for seed, im, objs in bases])

# shadow side split: recall inside vs outside the shadowed half
seed0, im0, objs0 = bases[0]
sh = half_shadow(im0)
left = [o for o in objs0 if o["cx"] < im0.shape[1] * 0.45]; right = [o for o in objs0 if o["cx"] >= im0.shape[1] * 0.45]
dl = DET.detect(sh)
def recall_subset(dets, subset):
    hit = 0
    for o in subset:
        for d in dets:
            if d.label == o["label"] and math.hypot(d.cx - o["cx"], d.cy - o["cy"]) <= max(38.0, o["r"] * 1.1):
                hit += 1; break
    return round(hit / max(1, len(subset)), 4)
R["half_shadow_split_scene1"] = {"n_left": len(left), "n_right": len(right),
                                 "recall_in_shadow": recall_subset(dl, left), "recall_in_light": recall_subset(dl, right)}

# ---------- occlusion: leaf cover over known centres ----------
def leaf_cover(img, objects, cover_frac, radius_frac, seed):
    rng = np.random.default_rng(seed)
    out = img.copy(); covered, uncovered = [], []
    for o in objects:
        if rng.random() < cover_frac:
            r = max(6, int(o["r"] * radius_frac))
            cv2.ellipse(out, (o["cx"], o["cy"]), (r, int(r * 0.72)), float(rng.uniform(0, 180)), 0, 360, LEAF_BASE, -1)
            covered.append(o)
        else:
            uncovered.append(o)
    return out, covered, uncovered

R["occlusion_leaf_cover60"] = {}
for rf in [0.5, 0.8, 1.1]:
    rows, cov_rec, unc_rec = [], [], []
    for seed, im, objs in bases:
        out, cov, unc = leaf_cover(im, objs, 0.6, rf, seed)
        dets = DET.detect(out)
        rows.append(score(dets, objs))
        cov_rec.append(recall_subset(dets, cov) * max(1, len(cov))); unc_rec.append(recall_subset(dets, unc) * max(1, len(unc)))
        R.setdefault("_cov_n", []).append(len(cov)); R.setdefault("_unc_n", []).append(len(unc))
    agg = micro(rows)
    agg["recall_covered_objects"] = round(sum(cov_rec) / max(1, sum(R["_cov_n"][-4:])), 4)
    agg["recall_uncovered_objects"] = round(sum(unc_rec) / max(1, sum(R["_unc_n"][-4:])), 4)
    R["occlusion_leaf_cover60"][f"radius_x{rf}"] = agg
R.pop("_cov_n", None); R.pop("_unc_n", None)

# ---------- occlusion: overlapping blooms at controlled offsets ----------
def overlap_scene(img, objects, offset_mult, seed, n_extra=10):
    rng = np.random.default_rng(seed)
    out = img.copy()
    blooms = [o for o in objects if o["label"] == "bloom"]
    chosen = blooms[:: max(1, len(blooms) // n_extra)][:n_extra]
    new_objs = list(objects)
    for o in chosen:
        cx = int(min(img.shape[1] - 60, o["cx"] + o["r"] * offset_mult)); cy = o["cy"]
        _draw_bloom(out, rng, cx, cy, o["r"])
        new_objs.append({"label": "bloom", "cx": cx, "cy": cy, "r": o["r"]})
    return out, new_objs

# unit bloom box area from baseline detections (for split estimator)
unit_areas = []
for seed, im, objs in bases:
    for d in DET.detect(im):
        if d.label == "bloom":
            unit_areas.append(d.w * d.h)
UNIT = float(np.median(unit_areas)) if unit_areas else 1.0
R["split_estimator_unit_box_area_median"] = UNIT

def split_corrected_blooms(dets):
    return sum(max(1, int(round((d.w * d.h) / UNIT))) if d.label == "bloom" else 0 for d in dets)

R["occlusion_overlap"] = {}
for om in [2.2, 1.6, 1.2, 0.8, 0.45]:
    rows, corr = [], []
    for seed, im, objs in bases:
        out, new_objs = overlap_scene(im, objs, om, seed)
        dets = DET.detect(out)
        rows.append(score(dets, new_objs))
        corr.append(split_corrected_blooms(dets))
    agg = micro(rows)
    agg["split_corrected_blooms"] = int(sum(corr))
    agg["bloom_count_err_raw"] = agg["det_blooms"] - agg["true_blooms"]
    agg["bloom_count_err_split_corrected"] = int(sum(corr)) - agg["true_blooms"]
    R["occlusion_overlap"][f"offset_x{om}"] = agg

# ---------- combined worst case ----------
R["combined_gamma1.6+cover0.8"] = micro([score(DET.detect(leaf_cover(gamma(im, 1.6), objs, 0.6, 0.8, seed)[0]), objs) for seed, im, objs in bases])
R["combined_gamma1.6+cover0.8+wb_clahe"] = micro([score(DET.detect(wb_clahe(leaf_cover(gamma(im, 1.6), objs, 0.6, 0.8, seed)[0])), objs) for seed, im, objs in bases])

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print(json.dumps(R, indent=2, ensure_ascii=False))
