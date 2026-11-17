"""Bridge clutter bench (2026-11-16).

Fulfils the 2026-11-07 open problem: one petal-coloured disc planted at
the midpoint between TWO true flowers, bridging them into one contour.
Measures merged_both / merged_one rates and pair-level TP/FP/FN harm as a
function of the pair edge gap G and the bridge radius rc, for three pair
types (bloom-bloom, bud-bud, bloom-bud), against the rc=0 no-bridge
control and the published 2026-11-07 single-host curve.

Design frozen in data/2026-11-16-bridge-clutter-prereg.md.
Usage: python3 2026-11-16-bridge-clutter-bench.py <repo> <out_json_abs>
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

from simulator.generate import _foliage_background, _draw_bloom, _draw_bud
from detector.color_segmentation import ColorSegmentationDetector

W0, H0 = 1280, 960
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
PINK = (147, 20, 255)
R_BLOOM, R_BUD = 38, 15
PAIR_TYPES = {"BB": ("bloom", "bloom"), "bb": ("bud", "bud"), "Bb": ("bloom", "bud")}
RADII = {"bloom": R_BLOOM, "bud": R_BUD}
GS = [0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48]
RCS = [0, 6, 9, 12, 15, 18]
BG_SEEDS = [7001, 7002, 7003, 7004, 7005, 7006]
ANGLES = [0.0, math.pi / 2, math.pi / 4, -math.pi / 4, math.pi / 6, -math.pi / 3]


def log(obj):
    with open(PROG, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def contours_of(image, close_k=BASE_KERNEL, open_k=BASE_KERNEL):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    m = ColorSegmentationDetector._petal_mask(hsv)
    if close_k:
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
    if open_k:
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [(c, float(cv2.contourArea(c))) for c in cnts if float(cv2.contourArea(c)) >= BASE_MIN]


def containing(contours, x, y):
    for c, a in contours:
        if cv2.pointPolygonTest(c, (float(x), float(y)), False) >= 0:
            return (c, a)
    return None


def score_pair(dets, truths):
    """Series-standard greedy centre matching, label must match."""
    used = set(); tp = 0
    for d in dets:
        best, bd = None, 1e9
        for i, o in enumerate(truths):
            if i in used or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None and bd <= max(38.0, truths[best]["r"] * 1.1):
            used.add(best); tp += 1
    return tp, len(dets) - tp, len(truths) - tp


def draw_flower(img, rng, label, cx, cy, r):
    if label == "bloom":
        _draw_bloom(img, rng, cx, cy, r)
    else:
        _draw_bud(img, rng, cx, cy, r)


# ---------- backgrounds ----------
backgrounds = []
for s in BG_SEEDS:
    rng = np.random.default_rng(s)
    backgrounds.append(_foliage_background(rng, W0, H0))
log({"stage": "backgrounds", "n": len(backgrounds)})

det = ColorSegmentationDetector()

# ---------- alone references ----------
alone = {}
for label, r in (("bloom", R_BLOOM), ("bud", R_BUD)):
    areas = []
    for bi, bg in enumerate(backgrounds[:3]):
        img = bg.copy()
        rng = np.random.default_rng(9000 + bi)
        draw_flower(img, rng, label, 640, 480, r)
        hit = containing(contours_of(img), 640, 480)
        areas.append(round(hit[1], 1) if hit else None)
        del img
    alone[label] = areas
bridge_alone = {}
for rc in RCS[1:]:
    areas = []
    for bg in backgrounds[:3]:
        img = bg.copy()
        cv2.circle(img, (640, 480), rc, PINK, -1)
        hit = containing(contours_of(img), 640, 480)
        areas.append(round(hit[1], 1) if hit else None)
        del img
    bridge_alone[str(rc)] = areas
log({"stage": "alone", "alone": alone, "bridge_alone": bridge_alone})

# ---------- main factorial ----------
R = {"detector": "color-segmentation-v0.1",
     "base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM, "morph_kernel": BASE_KERNEL},
     "radii": RADII, "gaps": GS, "rcs": RCS, "bg_seeds": BG_SEEDS,
     "prereg": "data/2026-11-16-bridge-clutter-prereg.md",
     "alone": alone, "bridge_alone": bridge_alone,
     "cells": {}}

for ptype, (la, lb) in PAIR_TYPES.items():
    ra, rb = RADII[la], RADII[lb]
    for G in GS:
        d = ra + G + rb
        for rc in RCS:
            trials = []
            for rep in range(6):
                bg = backgrounds[rep]
                ang = ANGLES[rep]
                rng = np.random.default_rng(31000 + rep * 131 + G * 7 + rc)
                jx = int(rng.integers(-60, 61)); jy = int(rng.integers(-60, 61))
                mx, my = 640 + jx, 480 + jy
                ax = int(round(mx - (d / 2) * math.cos(ang))); ay = int(round(my - (d / 2) * math.sin(ang)))
                bx = int(round(mx + (d / 2) * math.cos(ang))); by = int(round(my + (d / 2) * math.sin(ang)))
                img = bg.copy()
                draw_flower(img, rng, la, ax, ay, ra)
                draw_flower(img, rng, lb, bx, by, rb)
                if rc > 0:
                    cv2.circle(img, (mx, my), rc, PINK, -1)
                cnts = contours_of(img)
                ha = containing(cnts, ax, ay)
                hb = containing(cnts, bx, by)
                hm = containing(cnts, mx, my) if rc > 0 else None
                merged_both = bool(ha and hb and ha[0] is hb[0])
                merged_one = False
                if rc > 0 and hm and not merged_both:
                    merged_one = bool((ha and ha[0] is hm[0]) or (hb and hb[0] is hm[0]))
                def outcome(hit, label):
                    if hit is None:
                        return "lost"
                    lab = "bloom" if hit[1] >= BASE_BLOOM else "bud"
                    return "correct" if lab == label else "migrated"
                truths = [{"label": la, "cx": ax, "cy": ay, "r": ra},
                          {"label": lb, "cx": bx, "cy": by, "r": rb}]
                tp, fp, fn = score_pair(det.detect(img), truths)
                trials.append({
                    "rep": rep, "merged_both": merged_both, "merged_one": merged_one,
                    "out_a": outcome(ha, la), "out_b": outcome(hb, lb),
                    "area_a": round(ha[1], 1) if ha else None,
                    "area_b": round(hb[1], 1) if hb else None,
                    "merged_area": round(ha[1], 1) if merged_both else None,
                    "tp": tp, "fp": fp, "fn": fn})
                del img
            n = len(trials)
            cell = {
                "n": n,
                "g_a": round(d / 2 - rc - ra, 1) if rc else None,
                "g_b": round(d / 2 - rc - rb, 1) if rc else None,
                "merged_both_rate": round(sum(t["merged_both"] for t in trials) / n, 4),
                "merged_one_rate": round(sum(t["merged_one"] for t in trials) / n, 4),
                "intact_rate": round(sum(1 for t in trials if t["out_a"] == "correct" and t["out_b"] == "correct" and not t["merged_both"]) / n, 4),
                "tp_hist": {str(k): sum(1 for t in trials if t["tp"] == k) for k in (0, 1, 2)},
                "fp_mean": round(sum(t["fp"] for t in trials) / n, 4),
                "fn_mean": round(sum(t["fn"] for t in trials) / n, 4),
                "merged_area_median": round(float(np.median([t["merged_area"] for t in trials if t["merged_area"] is not None])), 1) if any(t["merged_area"] is not None for t in trials) else None,
                "merged_area_ge900_rate": round(sum(1 for t in trials if t["merged_area"] is not None and t["merged_area"] >= 900) / max(1, sum(1 for t in trials if t["merged_area"] is not None)), 4) if any(t["merged_area"] is not None for t in trials) else None,
                "trials": trials}
            R["cells"][f"{ptype}|G={G}|rc={rc}"] = cell
            log({"stage": "cell", "pair": ptype, "G": G, "rc": rc,
                 "mb": cell["merged_both_rate"], "mo": cell["merged_one_rate"],
                 "fn_mean": cell["fn_mean"], "fp_mean": cell["fp_mean"]})

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
log({"stage": "DONE", "out": OUT})
