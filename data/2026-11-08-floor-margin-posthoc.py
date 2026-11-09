"""Posthoc isolation for 2026-11-08 floor-margin bench.

Measures, in situ on the planted cluttered scenes, the normalised
morph-pipeline contour area of every r=6 / r=7 clutter item (the items
whose pass/fail flips with margin), per shape and scale. Also derives
the prescription cell from the frozen rule in the prereg: smallest m
with zero radius-label subfloor leaks at every s and zero bud loss.
Reads only the bench JSON + regenerates the same planted scenes.
"""
import json, math, os, sys
import numpy as np
import cv2

sys.path.insert(0, "/home/hatch/workspace/github/Bloom-Counter")
os.chdir("/home/hatch/workspace/github/Bloom-Counter")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "bench", "/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-08-floor-margin-bench.py")
# Do NOT exec the bench (it would rerun). Re-implement the two helpers by
# importing constants from the bench source text is fragile; instead
# duplicate the tiny planting logic by exec'ing only up to the marker.
src = open(spec.origin).read().split("# ---------- Part A")[0]
g = {"__name__": "bench_head"}
exec(src, g)
load_scene, plant_clutter, contours_of = g["load_scene"], g["plant_clutter"], g["contours_of"]
ORIG, SCALES = g["ORIG"], g["SCALES"]

out = {"in_situ_contour_norm": {}}
for s in SCALES:
    rows = {}
    for seed, nb, nd in ORIG:
        img, objs = load_scene(seed, nb, nd)
        cimg, items = plant_clutter(img, objs, seed)
        big = cv2.resize(cimg, (int(round(1280 * s)), int(round(960 * s))),
                         interpolation=cv2.INTER_LINEAR)
        cnts = contours_of(big)
        for it in items:
            if it["r"] not in (6, 7):
                continue
            cx, cy = it["cx"] * s, it["cy"] * s
            a = None
            for c, ar in cnts:
                if cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                    a = ar / (s * s)
                    break
            key = f"r={it['r']}_{it['shape']}"
            rows.setdefault(key, []).append(None if a is None else round(a, 1))
        del img, cimg, big
    out["in_situ_contour_norm"][f"s={s}"] = {
        k: {"n": len(v), "found": sum(1 for x in v if x is not None),
            "min": None if not any(x is not None for x in v) else round(float(np.min([x for x in v if x is not None])), 1),
            "median": None if not any(x is not None for x in v) else round(float(np.median([x for x in v if x is not None])), 1),
            "max": None if not any(x is not None for x in v) else round(float(np.max([x for x in v if x is not None])), 1)}
        for k, v in rows.items()}

R = json.load(open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-08-floor-margin-bench.json"))
# frozen prescription rule: smallest m, zero radius-subfloor leaks at all s, zero bud loss
cands = []
for m in R["margins"]:
    ok = True
    for s in R["scales"]:
        cell = R["curve"][f"s={s}"][f"m={m}"]
        if cell["cluttered"]["pass_radius_subfloor"]["passed"] != 0:
            ok = False
        if cell["clean"]["bud_recall"] != 1.0:
            ok = False
    if ok:
        cands.append(m)
out["prescription_candidates"] = cands
out["prescription_m"] = cands[0] if cands else None
out["bud_min_norm_by_s"] = {f"s={s}": R["orig_tail_vs_s"][f"s={s}"]["bud"]["min"] for s in R["scales"]}
out["precision_monotonic_by_s"] = {}
for s in R["scales"]:
    precs = [R["curve"][f"s={s}"][f"m={m}"]["cluttered"]["precision"] for m in R["margins"]]
    out["precision_monotonic_by_s"][f"s={s}"] = all(b >= a for a, b in zip(precs, precs[1:]))
with open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-08-floor-margin-posthoc.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
