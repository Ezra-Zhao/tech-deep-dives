"""Evaluation-protocol audit bench (2026-10-21).

Question (paper deep-read follow-up): Chili-Seg (Front. Plant Sci. 2026,
10.3389/fpls.2026.1955273) evaluates a flower instance-segmentation model
with a single class (nc=1), one aggregate test-set number per metric, no
per-image counting error, and no quantitative stress tiers -- while its
test set was curated (stable-light capture windows; heavy-occlusion and
blurred samples removed before the split). What does that protocol hide?

Method: run the UNMODIFIED Bloom-Counter detector once per condition
(10 lighting transforms + 3 leaf-cover tiers + 5 overlap offsets, same
transforms/seeds/scenes as the 2026-10-17 bench: 4 scenes, 210 base
targets, blooms 134 / buds 76), then score THE SAME predictions three
ways:

  A strict   : centre matching, label must match (bloom vs bud separate)
  B merged   : centre matching, label ignored (single-class, nc=1 style)
  C count    : total-count error and per-image count MAE only
               (tree/image-level regression style, cf. Dual-view paper)

Plus: category-migration count (detections that match a ground-truth
centre but with the wrong label -- correct under B, wrong under A), and
a curation simulation: recompute the pooled single-class headline after
dropping the hardest tiers, the way a curated test set would read.

Usage: .venv/bin/python 2026-10-21-eval-protocol-bench.py <repo> <out_json>
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "eval-protocol-bench.json"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_evalproto_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image, _draw_bloom, LEAF_BASE
from detector.color_segmentation import ColorSegmentationDetector

DET = ColorSegmentationDetector()
SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]


def tol(o):
    return max(38.0, o["r"] * 1.1)


def score_all(dets, objects):
    """Score one scene's predictions under protocols A, B, C + migration."""
    # --- A: label must match ---
    used = set(); tp_a = fp_a = 0
    per = {"bloom": [0, 0], "bud": [0, 0]}
    matched_det_a = set()
    for di, d in enumerate(dets):
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None and bd <= tol(objects[best]):
            used.add(best); matched_det_a.add(di); tp_a += 1; per[d.label][0] += 1
        else:
            fp_a += 1
    fn_a = len(objects) - len(used)
    for i, o in enumerate(objects):
        if i not in used:
            per[o["label"]][1] += 1
    # --- B: label ignored ---
    used_b = set(); tp_b = 0
    for d in dets:
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used_b:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None and bd <= tol(objects[best]):
            used_b.add(best); tp_b += 1
    fp_b = len(dets) - tp_b; fn_b = len(objects) - tp_b
    # --- migration: A-unmatched detections sitting on an A-unmatched GT
    #     centre of the other label (right place, wrong category) ---
    mig = 0
    unmatched_gt = [i for i in range(len(objects)) if i not in used]
    for di, d in enumerate(dets):
        if di in matched_det_a:
            continue
        for i in unmatched_gt:
            o = objects[i]
            if o["label"] != d.label and math.hypot(d.cx - o["cx"], d.cy - o["cy"]) <= tol(o):
                mig += 1
                break

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        return round(p, 4), round(r, 4), round(2 * p * r / (p + r), 4) if p + r else 0.0

    pa, ra, fa = prf(tp_a, fp_a, fn_a)
    pb, rb, fb = prf(tp_b, fp_b, fn_b)
    tb = sum(1 for o in objects if o["label"] == "bloom")
    td = sum(1 for o in objects if o["label"] == "bud")
    nb = sum(1 for d in dets if d.label == "bloom")
    nd = sum(1 for d in dets if d.label == "bud")
    return {
        "A_strict": {"tp": tp_a, "fp": fp_a, "fn": fn_a, "precision": pa, "recall": ra, "f1": fa,
                     "bloom_recall": round(per["bloom"][0] / max(1, tb), 4),
                     "bud_recall": round(per["bud"][0] / max(1, td), 4)},
        "B_merged": {"tp": tp_b, "fp": fp_b, "fn": fn_b, "precision": pb, "recall": rb, "f1": fb},
        "migration": mig,
        "det_total": len(dets), "true_total": len(objects),
        "det_blooms": nb, "det_buds": nd, "true_blooms": tb, "true_buds": td,
        "count_abs_err": abs(len(dets) - len(objects)),
        "bloom_count_err": nb - tb, "bud_count_err": nd - td,
    }


def micro(rows):
    """Micro-average a list of score_all rows."""
    def agg(key):
        tp = sum(r[key]["tp"] for r in rows); fp = sum(r[key]["fp"] for r in rows); fn = sum(r[key]["fn"] for r in rows)
        p = tp / (tp + fp) if tp + fp else 1.0; r_ = tp / (tp + fn) if tp + fn else 1.0
        return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 4), "recall": round(r_, 4),
                "f1": round(2 * p * r_ / (p + r_), 4) if p + r_ else 0.0}
    A = agg("A_strict"); B = agg("B_merged")
    tb = sum(r["true_blooms"] for r in rows); td = sum(r["true_buds"] for r in rows)
    # per-category recall from A tp split is not stored per row; recompute
    # from recalls weighted by class totals (rows carry class recalls)
    A["bloom_recall"] = round(sum(r["A_strict"]["bloom_recall"] * r["true_blooms"] for r in rows) / max(1, tb), 4)
    A["bud_recall"] = round(sum(r["A_strict"]["bud_recall"] * r["true_buds"] for r in rows) / max(1, td), 4)
    det = sum(r["det_total"] for r in rows); tru = sum(r["true_total"] for r in rows)
    return {"A_strict": A, "B_merged": B,
            "migration_total": sum(r["migration"] for r in rows),
            "det_total": det, "true_total": tru,
            "count_err_pct": round(100.0 * (det - tru) / max(1, tru), 2),
            "count_mae_per_image": round(sum(r["count_abs_err"] for r in rows) / max(1, len(rows)), 3),
            "bloom_count_err": sum(r["bloom_count_err"] for r in rows),
            "bud_count_err": sum(r["bud_count_err"] for r in rows)}


# ---------- transforms (identical to 2026-10-17 bench) ----------
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
    return np.clip(dark.astype(np.float32) + rng.normal(0, 12, dark.shape), 0, 255).astype(np.uint8)

LIGHTING = {
    "baseline": lambda im, s: im,
    "gamma_0.6_brighter": lambda im, s: gamma(im, 0.6),
    "gamma_1.6_darker": lambda im, s: gamma(im, 1.6),
    "gamma_2.2_much_darker": lambda im, s: gamma(im, 2.2),
    "exposure_+60_washout": lambda im, s: exposure(im, 1.25, 60),
    "exposure_-50_dim": lambda im, s: exposure(im, 0.78, -50),
    "shadow_gradient": lambda im, s: shadow_gradient(im),
    "half_shadow": lambda im, s: half_shadow(im),
    "warm_cast": lambda im, s: warm_cast(im),
    "low_light_+noise": lambda im, s: low_light_noise(im, s),
}

def leaf_cover(img, objects, cover_frac, radius_frac, seed):
    rng = np.random.default_rng(seed)
    out = img.copy()
    for o in objects:
        if rng.random() < cover_frac:
            r = max(6, int(o["r"] * radius_frac))
            cv2.ellipse(out, (o["cx"], o["cy"]), (r, int(r * 0.72)),
                        float(rng.uniform(0, 180)), 0, 360, LEAF_BASE, -1)
    return out

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


bases = []
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    bases.append((seed, cv2.imread(p), truth["objects"]))

R = {"detector": DET.name,
     "params": {"min_area": DET.min_area, "bloom_area_min": DET.bloom_area_min, "morph_kernel": DET.morph_kernel},
     "n_scenes": len(bases), "n_objects_base": sum(len(o) for _, _, o in bases),
     "protocols": "A=label-matched centre matching; B=label-agnostic centre matching (nc=1 style); C=count-only",
     "conditions": {}}

all_rows = {}   # condition -> per-scene rows (for pooled recomputation)
for name, fn in LIGHTING.items():
    rows = [score_all(DET.detect(fn(im, seed)), objs) for seed, im, objs in bases]
    all_rows[f"light:{name}"] = rows
    R["conditions"][f"light:{name}"] = micro(rows)
for rf in [0.5, 0.8, 1.1]:
    rows = [score_all(DET.detect(leaf_cover(im, objs, 0.6, rf, seed)), objs) for seed, im, objs in bases]
    all_rows[f"cover:x{rf}"] = rows
    R["conditions"][f"cover:x{rf}"] = micro(rows)
for om in [2.2, 1.6, 1.2, 0.8, 0.45]:
    rows = []
    for seed, im, objs in bases:
        out, new_objs = overlap_scene(im, objs, om, seed)
        rows.append(score_all(DET.detect(out), new_objs))
    all_rows[f"overlap:x{om}"] = rows
    R["conditions"][f"overlap:x{om}"] = micro(rows)

# pooled headline over ALL conditions (one test-set number, Chili-Seg style)
flat = [r for rows in all_rows.values() for r in rows]
R["pooled_all_conditions"] = micro(flat)

# curation simulation: drop hardest tiers (darkest light, heaviest cover,
# tightest overlap) -- mirrors removing heavy-occlusion/blur samples
hard = {"light:gamma_2.2_much_darker", "light:low_light_+noise", "cover:x1.1", "overlap:x0.45"}
kept = [r for k, rows in all_rows.items() if k not in hard for r in rows]
R["pooled_curated_drop_hardest"] = micro(kept)
R["curation_dropped_conditions"] = sorted(hard)

# mild-only subset (what a stable-light, screened test set approximates)
mild = {"light:baseline", "light:gamma_0.6_brighter", "light:gamma_1.6_darker",
        "light:exposure_+60_washout", "cover:x0.5", "overlap:x2.2", "overlap:x1.6"}
R["pooled_mild_only"] = micro([r for k, rows in all_rows.items() if k in mild for r in rows])
R["mild_conditions"] = sorted(mild)

# worst single condition under each protocol
conds = R["conditions"]
R["worst_condition_B_f1"] = min(conds.items(), key=lambda kv: kv[1]["B_merged"]["f1"])[0]
R["worst_condition_A_bud_recall"] = min(conds.items(), key=lambda kv: kv[1]["A_strict"]["bud_recall"])[0]
R["worst_condition_A_bloom_recall"] = min(conds.items(), key=lambda kv: kv[1]["A_strict"]["bloom_recall"])[0]

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print(json.dumps({"pooled_all": R["pooled_all_conditions"],
                  "pooled_curated": R["pooled_curated_drop_hardest"],
                  "pooled_mild": R["pooled_mild_only"]}, indent=2, ensure_ascii=False))
