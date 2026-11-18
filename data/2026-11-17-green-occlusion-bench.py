"""Green (heterochromatic) occlusion clutter bench (2026-11-17).

Fulfils the 2026-11-07 open problem: a leaf-green disc drawn ON TOP of a
true flower is not in the petal mask, so instead of merging (same-colour
case) it digs holes, notches and splits the host contour. Measures recall
loss, contour-area underestimation, mask-vs-contour divergence and split
fragmentation as a function of occluder radius rc and centre distance dc,
for one bloom (r=38) and one bud (r=15) host, against the published
2026-11-07 same-colour curve.

Design frozen in data/2026-11-17-green-occlusion-prereg.md.
Usage: python3 2026-11-17-green-occlusion-bench.py <repo> <out_json_abs>
Progress appended to <out_json>.progress.jsonl.
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2]
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)

from simulator.generate import _foliage_background, _draw_bloom, _draw_bud, LEAF_BASE
from detector.color_segmentation import ColorSegmentationDetector

W0, H0 = 1280, 960
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
GREEN = LEAF_BASE  # BGR (45, 110, 55), simulator foliage base colour
HOSTS = {"bloom": 38, "bud": 15}
RCS = [12, 24, 36]
BG_SEEDS = [7001, 7002, 7003, 7004, 7005, 7006]
ANGLES = [0.0, math.pi / 2, math.pi / 4, -math.pi / 4, math.pi / 6, -math.pi / 3]


def log(obj):
    with open(PROG, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def mask_and_contours(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    m = ColorSegmentationDetector._petal_mask(hsv)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BASE_KERNEL, BASE_KERNEL))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = [(c, float(cv2.contourArea(c))) for c in cnts
           if float(cv2.contourArea(c)) >= BASE_MIN]
    return m, out


def containing(contours, x, y):
    for c, a in contours:
        if cv2.pointPolygonTest(c, (float(x), float(y)), False) >= 0:
            return (c, a)
    return None


def host_fragments(contours, cx, cy, r):
    frags = []
    for c, a in contours:
        pts = c.reshape(-1, 2)
        dmin = float(np.min(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)))
        inside = cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0
        if dmin <= r + 4 or inside:
            frags.append(a)
    return sorted(frags, reverse=True)


def mask_px_in(mask, cx, cy, r):
    sub = np.zeros(mask.shape, dtype=np.uint8)
    cv2.circle(sub, (cx, cy), r, 255, -1)
    return int(np.count_nonzero(mask & sub))


def label_of(area):
    return "bloom" if area >= BASE_BLOOM else "bud"


def score_single(dets, truth):
    used_tp = 0
    for d in dets:
        if d.label == truth["label"]:
            dist = math.hypot(d.cx - truth["cx"], d.cy - truth["cy"])
            if dist <= max(38.0, truth["r"] * 1.1):
                used_tp = 1
                break
    return used_tp, len(dets) - used_tp, 1 - used_tp


# --- pre-run assertion: pure green block must be invisible to petal mask ---
_solid = np.zeros((60, 60, 3), dtype=np.uint8)
_solid[:] = GREEN
_pm = ColorSegmentationDetector._petal_mask(cv2.cvtColor(_solid, cv2.COLOR_BGR2HSV))
assert int(np.count_nonzero(_pm)) == 0, "green colour leaks into petal mask"
log({"stage": "green_mask_assertion", "mask_px": 0})

# ---------- backgrounds ----------
backgrounds = []
for s in BG_SEEDS:
    rng = np.random.default_rng(s)
    backgrounds.append(_foliage_background(rng, W0, H0))
log({"stage": "backgrounds", "n": len(backgrounds)})

det = ColorSegmentationDetector()

# ---------- alone references ----------
alone = {}
for label, r in HOSTS.items():
    areas, mpx = [], []
    for bi, bg in enumerate(backgrounds):
        img = bg.copy()
        rng = np.random.default_rng(9000 + bi)
        if label == "bloom":
            _draw_bloom(img, rng, 640, 480, r)
        else:
            _draw_bud(img, rng, 640, 480, r)
        m, cnts = mask_and_contours(img)
        hit = containing(cnts, 640, 480)
        areas.append(round(hit[1], 1) if hit else None)
        mpx.append(mask_px_in(m, 640, 480, r))
        del img
    alone[label] = {"areas": areas, "mask_px": mpx,
                    "area_median": round(float(np.median([a for a in areas if a])), 1),
                    "mask_px_median": int(np.median(mpx))}
green_alone = {}
for rc in RCS:
    ncs, mpx = [], []
    for bg in backgrounds:
        img = bg.copy()
        cv2.circle(img, (640, 480), rc, GREEN, -1)
        m, cnts = mask_and_contours(img)
        ncs.append(len(cnts))
        mpx.append(mask_px_in(m, 640, 480, rc))
        del img
    green_alone[str(rc)] = {"n_contours_ge120": ncs, "mask_px": mpx}
log({"stage": "alone", "alone": alone, "green_alone": green_alone})

# ---------- main factorial ----------
R = {"detector": "color-segmentation-v0.1",
     "base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM,
                     "morph_kernel": BASE_KERNEL},
     "hosts": HOSTS, "rcs": RCS, "bg_seeds": BG_SEEDS,
     "green_bgr": list(GREEN),
     "prereg": "data/2026-11-17-green-occlusion-prereg.md",
     "alone": alone, "green_alone": green_alone, "cells": {}}

for label, r in HOSTS.items():
    ref_area = alone[label]["area_median"]
    ref_mpx = alone[label]["mask_px_median"]
    for rc in RCS:
        dc_candidates = [r + rc + 10, r + rc, r + rc - 12, r + 6, r, r - 6, 12, 6, 0]
        dcs = sorted({d for d in dc_candidates if d >= 0}, reverse=True)
        for dc in dcs:
            trials = []
            for rep in range(6):
                bg = backgrounds[rep]
                ang = ANGLES[rep]
                rng = np.random.default_rng(41000 + rep * 149 + dc * 7 + rc * 3 + r)
                hx = 640 + int(rng.integers(-60, 61))
                hy = 480 + int(rng.integers(-60, 61))
                ox = int(round(hx + dc * math.cos(ang)))
                oy = int(round(hy + dc * math.sin(ang)))
                img = bg.copy()
                if label == "bloom":
                    _draw_bloom(img, rng, hx, hy, r)
                else:
                    _draw_bud(img, rng, hx, hy, r)
                cv2.circle(img, (ox, oy), rc, GREEN, -1)
                m, cnts = mask_and_contours(img)
                frags = host_fragments(cnts, hx, hy, r)
                hit = containing(cnts, hx, hy)
                def outcome(area, true_label):
                    if area is None:
                        return "lost"
                    return "correct" if label_of(area) == true_label else "migrated"
                largest = frags[0] if frags else None
                mp = mask_px_in(m, hx, hy, r)
                tp, fp, fn = score_single(det.detect(img),
                                          {"label": label, "cx": hx, "cy": hy, "r": r})
                trials.append({
                    "rep": rep, "n_frag": len(frags),
                    "largest_area": round(largest, 1) if largest else None,
                    "frag_areas": [round(a, 1) for a in frags],
                    "area_ratio": round(largest / ref_area, 4) if largest else 0.0,
                    "mask_px": mp,
                    "mask_ratio": round(mp / ref_mpx, 4),
                    "out_center": outcome(hit[1] if hit else None, label),
                    "out_frag": outcome(largest, label),
                    "tp": tp, "fp": fp, "fn": fn})
                del img
            n = len(trials)
            cell = {
                "n": n, "dc": dc, "bite": r + rc - dc,
                "area_ratio_median": round(float(np.median([t["area_ratio"] for t in trials])), 4),
                "mask_ratio_median": round(float(np.median([t["mask_ratio"] for t in trials])), 4),
                "split_rate": round(sum(1 for t in trials if t["n_frag"] >= 2) / n, 4),
                "lost_center_rate": round(sum(1 for t in trials if t["out_center"] == "lost") / n, 4),
                "lost_frag_rate": round(sum(1 for t in trials if t["out_frag"] == "lost") / n, 4),
                "migrated_frag_rate": round(sum(1 for t in trials if t["out_frag"] == "migrated") / n, 4),
                "correct_frag_rate": round(sum(1 for t in trials if t["out_frag"] == "correct") / n, 4),
                "fp_mean": round(sum(t["fp"] for t in trials) / n, 4),
                "fn_mean": round(sum(t["fn"] for t in trials) / n, 4),
                "trials": trials}
            R["cells"][f"{label}|rc={rc}|dc={dc}"] = cell
            log({"stage": "cell", "host": label, "rc": rc, "dc": dc,
                 "ar": cell["area_ratio_median"], "mr": cell["mask_ratio_median"],
                 "split": cell["split_rate"], "lost_f": cell["lost_frag_rate"],
                 "mig_f": cell["migrated_frag_rate"], "fp": cell["fp_mean"]})

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
log({"stage": "DONE", "out": OUT})
