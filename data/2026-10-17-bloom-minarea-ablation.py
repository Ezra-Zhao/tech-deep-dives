"""Bloom-Counter min_area ablation under leaf occlusion (2026-10-17).

Companion to 2026-10-17-bloom-bench.py: same 4 scenes, same leaf-cover
protocol (60% of objects, radius x0.5 / x0.8), detector min_area 120
(default) vs 40. Results were merged into 2026-10-17-bloom-bench.json
under key "occlusion_min_area_ablation".
Usage: .venv/bin/python 2026-10-17-bloom-minarea-ablation.py <repo> <bench_json>
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
BENCH_JSON = sys.argv[2] if len(sys.argv) > 2 else "2026-10-17-bloom-bench.json"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image, LEAF_BASE
from detector.color_segmentation import ColorSegmentationDetector

SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]

def score(dets, objects):
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
        if best is not None and bd <= max(38.0, objects[best]["r"] * 1.1):
            used.add(best); tp += 1; per[d.label][0] += 1
        else:
            fp += 1
    fn = len(objects) - len(used)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    tb = sum(1 for o in objects if o["label"] == "bloom"); td = sum(1 for o in objects if o["label"] == "bud")
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_blooms": sum(1 for d in dets if d.label == "bloom"), "det_buds": sum(1 for d in dets if d.label == "bud"),
            "true_blooms": tb, "true_buds": td,
            "bloom_recall": round(per["bloom"][0] / max(1, tb), 4), "bud_recall": round(per["bud"][0] / max(1, td), 4)}

def micro(rows):
    tp = sum(r["tp"] for r in rows); fp = sum(r["fp"] for r in rows); fn = sum(r["fn"] for r in rows)
    prec = tp / (tp + fp) if tp + fp else 1.0; rec = tp / (tp + fn) if tp + fn else 1.0
    tb = sum(r["true_blooms"] for r in rows); td = sum(r["true_buds"] for r in rows)
    tot_d = sum(r["det_blooms"] + r["det_buds"] for r in rows); tot_t = tb + td
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_blooms": sum(r["det_blooms"] for r in rows), "true_blooms": tb,
            "det_buds": sum(r["det_buds"] for r in rows), "true_buds": td,
            "bloom_recall": round(sum(r["bloom_recall"] * r["true_blooms"] for r in rows) / max(1, tb), 4),
            "bud_recall": round(sum(r["bud_recall"] * r["true_buds"] for r in rows) / max(1, td), 4),
            "count_err_pct": round(100.0 * (tot_d - tot_t) / max(1, tot_t), 2)}

def leaf_cover(img, objects, cover_frac, radius_frac, seed):
    rng = np.random.default_rng(seed); out = img.copy()
    for o in objects:
        if rng.random() < cover_frac:
            r = max(6, int(o["r"] * radius_frac))
            cv2.ellipse(out, (o["cx"], o["cy"]), (r, int(r * 0.72)), float(rng.uniform(0, 180)), 0, 360, LEAF_BASE, -1)
    return out

bases = []
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    bases.append((seed, cv2.imread(p), truth["objects"]))

out_data = {}
for ma in [120, 40]:
    det = ColorSegmentationDetector(min_area=ma)
    for rf in [0.5, 0.8]:
        rows = [score(det.detect(leaf_cover(im, objs, 0.6, rf, seed)), objs) for seed, im, objs in bases]
        out_data[f"min_area_{ma}_cover_x{rf}"] = micro(rows)

print(json.dumps(out_data, indent=1))
if os.path.exists(BENCH_JSON):
    R = json.load(open(BENCH_JSON))
    R["occlusion_min_area_ablation"] = out_data
    json.dump(R, open(BENCH_JSON, "w"), indent=2, ensure_ascii=False)
