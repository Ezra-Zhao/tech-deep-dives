"""Clutter size scan bench (2026-11-18).

Fulfils the 2026-11-07 first extrapolation boundary: clutter was r=12
only. This bench reuses the identical 112 hosts (same scenes, same
selection rule) and scans same-colour disc radius rc in
{4,6,8,10,12,15,18,21,24} x gap in {-18,-8,-3,0,2,4,8}, measuring
migration rate vs size, the all-buds-migrate turning point, and the
2026-11-07 distribution formula (migrations ~= merged buds whose alone
area >= 900 - median effective addition).

Design frozen in data/2026-11-18-clutter-size-prereg.md.
Usage: .venv/bin/python 2026-11-18-clutter-size-bench.py <repo> <out_json>
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
WORK = "/tmp/bloom_size_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image, _foliage_background
from detector.color_segmentation import ColorSegmentationDetector

SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]
GAPS = [-18, -8, -3, 0, 2, 4, 8]
RCS = [4, 6, 8, 10, 12, 15, 18, 21, 24]
SEL_RC = 12  # host-selection radius, identical to 2026-11-07
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
COLORS = [(147, 20, 255), (245, 245, 245), (0, 215, 255)]  # pink white yellow BGR
W0, H0 = 1280, 960
MAX_HOSTS = 28


def log(obj):
    with open(PROG, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def choose_hosts(objects):
    """Identical to 2026-11-07 (selection radius SEL_RC)."""
    cands = []
    for idx, o in enumerate(objects):
        best = None
        for k in range(16):
            ang = 2 * math.pi * k / 16
            cx = o["cx"] + (o["r"] + SEL_RC + 35) * math.cos(ang)
            cy = o["cy"] + (o["r"] + SEL_RC + 35) * math.sin(ang)
            if not (SEL_RC + 4 <= cx <= W0 - SEL_RC - 4 and SEL_RC + 4 <= cy <= H0 - SEL_RC - 4):
                continue
            clearance = min(
                math.hypot(cx - p["cx"], cy - p["cy"]) - p["r"] - SEL_RC
                for j, p in enumerate(objects) if j != idx)
            if clearance < 6:
                continue
            if best is None or clearance > best[0]:
                best = (clearance, ang)
        if best is not None:
            cands.append((idx, best[1]))
    blooms = [c for c in cands if objects[c[0]]["label"] == "bloom"]
    buds = [c for c in cands if objects[c[0]]["label"] == "bud"]
    hosts = []
    bi = di = 0
    while len(hosts) < MAX_HOSTS and (bi < len(blooms) or di < len(buds)):
        if bi < len(blooms):
            hosts.append(blooms[bi]); bi += 1
        if len(hosts) >= MAX_HOSTS:
            break
        if di < len(buds):
            hosts.append(buds[di]); di += 1
    return hosts


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
    return [(c, float(cv2.contourArea(c))) for c in cnts]


def containing(contours, x, y):
    for c, a in contours:
        if a < BASE_MIN:
            continue
        if cv2.pointPolygonTest(c, (float(x), float(y)), False) >= 0:
            return (c, a)
    return None


def score_scene(dets, objects):
    used = set(); tp = 0
    for d in dets:
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None and bd <= max(38.0, objects[best]["r"] * 1.1):
            used.add(best); tp += 1
    fp = len(dets) - tp
    fn = len(objects) - tp
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / len(objects) if objects else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_total": len(dets),
            "fp_labels": {"bloom": sum(1 for d in dets if d.label == "bloom"),
                          "bud": sum(1 for d in dets if d.label == "bud")}}


# ---------- bases, hosts, alone areas ----------
bases = []
host_report = {}
host_alone = {}  # (seed, idx) -> area
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    img = cv2.imread(p)
    objs = truth["objects"]
    hosts = choose_hosts(objs)
    bases.append((seed, img, objs, hosts))
    cnts = contours_of(img)
    for hi, _ang in hosts:
        o = objs[hi]
        hit = containing(cnts, o["cx"], o["cy"])
        host_alone[(seed, hi)] = round(hit[1], 1) if hit else None
    host_report[str(seed)] = {
        "hosts": len(hosts),
        "bloom": sum(1 for i, _ in hosts if objs[i]["label"] == "bloom"),
        "bud": sum(1 for i, _ in hosts if objs[i]["label"] == "bud")}
    log({"stage": "hosts", "seed": seed, **host_report[str(seed)]})

bud_alone = sorted(v for (s, i), v in host_alone.items()
                   if v is not None and
                   next(o for ss, im, oo, hh in bases if ss == s for o in [oo[i]])["label"] == "bud")
log({"stage": "bud_alone_dist", "n": len(bud_alone),
     "min": bud_alone[0] if bud_alone else None,
     "median": float(np.median(bud_alone)) if bud_alone else None,
     "max": bud_alone[-1] if bud_alone else None})

# ---------- clutter alone reference per rc ----------
alone_ref = {}
for rc in RCS:
    areas = []
    for s in (7001, 7002, 7003, 7004):
        rng = np.random.default_rng(s)
        bg = _foliage_background(rng, W0, H0)
        cv2.circle(bg, (640, 480), rc, COLORS[0], -1)
        cnts = contours_of(bg)
        hit = containing(cnts, 640, 480)
        areas.append(round(hit[1], 1) if hit else 0.0)
        del bg
    alone_ref[str(rc)] = {"areas": areas,
                          "median": round(float(np.median(areas)), 1)}
    log({"stage": "clutter_alone", "rc": rc, **alone_ref[str(rc)]})

det = ColorSegmentationDetector()
R = {"detector": "color-segmentation-v0.1",
     "base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM,
                     "morph_kernel": BASE_KERNEL},
     "rcs": RCS, "gaps": GAPS, "host_report": host_report,
     "bud_alone_sorted": bud_alone,
     "clutter_alone": alone_ref,
     "prereg": "data/2026-11-18-clutter-size-prereg.md",
     "cells": {}}

for rc in RCS:
    for gap in GAPS:
        rows = []
        scene_scores = []
        ci = 0
        for seed, img, objs, hosts in bases:
            cimg = img.copy()
            placements = []
            host_idx_set = {hi for hi, _ in hosts}
            for hi, ang in hosts:
                o = objs[hi]
                d_nom = o["r"] + rc + gap
                d = max(d_nom, 0)
                cx = int(round(o["cx"] + d * math.cos(ang)))
                cy = int(round(o["cy"] + d * math.sin(ang)))
                cv2.circle(cimg, (cx, cy), rc, COLORS[ci % 3], -1); ci += 1
                nbr_clear = min(
                    math.hypot(cx - q["cx"], cy - q["cy"]) - q["r"] - rc
                    for j, q in enumerate(objs) if j != hi and j not in host_idx_set)
                nbr_clear_all = min(
                    math.hypot(cx - q["cx"], cy - q["cy"]) - q["r"] - rc
                    for j, q in enumerate(objs) if j != hi)
                placements.append((hi, (cx, cy), d, nbr_clear, nbr_clear_all))
            cnts = contours_of(cimg)
            scene_scores.append(score_scene(det.detect(cimg), objs))
            for hi, cxy, d, nbr_clear, nbr_clear_all in placements:
                o = objs[hi]
                hit = containing(cnts, o["cx"], o["cy"])
                alone = host_alone.get((seed, hi))
                if hit is None:
                    rows.append({"label": o["label"], "alone": alone,
                                 "merged": False, "outcome": "lost",
                                 "area": None, "addition": None,
                                 "nbr_clear": round(nbr_clear, 1),
                                 "nbr_clear_all": round(nbr_clear_all, 1),
                                 "d_actual": d})
                    continue
                c, a = hit
                merged = cv2.pointPolygonTest(
                    c, (float(cxy[0]), float(cxy[1])), False) >= 0
                label = "bloom" if a >= BASE_BLOOM else "bud"
                rows.append({
                    "label": o["label"], "alone": alone,
                    "merged": bool(merged),
                    "outcome": "correct" if label == o["label"] else "migrated",
                    "area": round(a, 1),
                    "addition": round(a - alone, 1) if alone else None,
                    "nbr_clear": round(nbr_clear, 1),
                    "nbr_clear_all": round(nbr_clear_all, 1),
                    "d_actual": d})
            del cimg
        buds_m = [r for r in rows if r["label"] == "bud" and r["merged"]]
        buds_mig = [r for r in buds_m if r["outcome"] == "migrated"]
        blooms = [r for r in rows if r["label"] == "bloom"]
        adds = [r["addition"] for r in rows if r["merged"] and r["addition"] is not None]
        cell = {
            "n": len(rows),
            "merged_rate": round(sum(1 for r in rows if r["merged"]) / len(rows), 4),
            "bud_merged": len(buds_m), "bud_migrated": len(buds_mig),
            "bud_mig_rate_merged": round(len(buds_mig) / len(buds_m), 4) if buds_m else None,
            "bloom_correct_rate": round(sum(1 for r in blooms if r["outcome"] == "correct") / len(blooms), 4),
            "lost_total": sum(1 for r in rows if r["outcome"] == "lost"),
            "addition_median_merged": round(float(np.median(adds)), 1) if adds else None,
            "scene": {"tp": sum(s["tp"] for s in scene_scores),
                      "fp": sum(s["fp"] for s in scene_scores),
                      "fn": sum(s["fn"] for s in scene_scores),
                      "det_total": sum(s["det_total"] for s in scene_scores)},
            "nbr_clear_neg": sum(1 for r in rows if r["nbr_clear"] < 0),
            "nbr_clear_all_neg": sum(1 for r in rows if r["nbr_clear_all"] < 0),
            "rows": rows}
        R["cells"][f"rc={rc}|gap={gap}"] = cell
        log({"stage": "cell", "rc": rc, "gap": gap,
             "merged": cell["merged_rate"], "bud_mig": cell["bud_mig_rate_merged"],
             "bud_mig_n": len(buds_mig), "add_med": cell["addition_median_merged"],
             "fp": cell["scene"]["fp"], "nbr_neg": cell["nbr_clear_neg"]})

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
log({"stage": "DONE", "out": OUT})
