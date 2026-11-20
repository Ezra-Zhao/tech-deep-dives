"""Posthoc isolation for 2026-11-19 downscale-margin bench.

1) Rule-D feasible margin bands per scale, under the literal prereg
   wording (clean bud recall exactly equal to the m=0 cell) and under
   the no-worse reading (recall >= m=0 cell); the prereg parenthetical
   states the intent was 'no additional loss', so both are reported.
2) Per-bud accounting at s=0.3 / s=0.22: every bud's normalised contour
   area measured with a floor of 1 px (so sub-floor buds are visible),
   compared against the effective floors of the margin grid.
3) In-situ normalised contour areas of r=6 clutter (circle/square) per
   scale on the planted scenes, to explain radius-label leaks at
   m=0 / m=-0.15.
4) Precision monotonicity in m per scale, from the bench JSON.
Reads only the bench JSON + regenerates the same scenes.
"""
import json, math, os, sys
import numpy as np
import cv2

sys.path.insert(0, "/home/hatch/workspace/github/Bloom-Counter")
os.chdir("/home/hatch/workspace/github/Bloom-Counter")
src = open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-19-downscale-margin-bench.py").read().split("# ---------- Part A")[0]
g = {"__name__": "bench_head"}
exec(src, g)
load_scene, plant_clutter, contours_of = g["load_scene"], g["plant_clutter"], g["contours_of"]
odd_kernel, eff_floor = g["odd_kernel"], g["eff_floor"]
ORIG, SCALES, MARGINS = g["ORIG"], g["SCALES"], g["MARGINS"]

R = json.load(open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-19-downscale-margin-bench.json"))
out = {}

# ---- 1) feasible bands ----
bands = {}
for s in SCALES:
    entry = R["curve"][f"s={s}"]
    base = entry["m=0.0"]["clean"]["bud_recall"]
    lit, ge = [], []
    for m in MARGINS:
        cell = entry[f"m={m}"]
        leaks_ok = (cell["cluttered"]["pass_true_subfloor"]["passed"] == 0
                    and cell["cluttered"]["pass_radius_subfloor"]["passed"] == 0)
        if not leaks_ok:
            continue
        if cell["clean"]["bud_recall"] == base:
            lit.append(m)
        if cell["clean"]["bud_recall"] >= base:
            ge.append(m)
    bands[f"s={s}"] = {"base_bud_recall": base, "literal_feasible": lit, "noworse_feasible": ge,
                       "literal_max": max(lit) if lit else None, "noworse_max": max(ge) if ge else None,
                       "noworse_min": min(ge) if ge else None}
out["ruleD_bands"] = bands

# ---- 2) per-bud areas at s=0.3 / 0.22 with floor=1 ----
def bud_areas_floor1(s):
    w, h = int(round(1280 * s)), int(round(960 * s))
    rows = []
    for seed, nb, nd in ORIG:
        img, objs = load_scene(seed, nb, nd)
        small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        cnts = contours_of(small, odd_kernel(s))
        for o in objs:
            if o["label"] != "bud":
                continue
            cx, cy = o["cx"] * s, o["cy"] * s
            a = None
            for c, ar in cnts:
                if cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                    a = ar / (s * s)
                    break
            rows.append({"seed": seed, "r": o["r"], "area_norm_floor1": None if a is None else round(a, 1)})
        del img, small
    return rows

per = {}
for s in (0.3, 0.22):
    rows = bud_areas_floor1(s)
    floors = {f"m={m}": round(eff_floor(s, m) / (s * s), 2) for m in MARGINS}
    lost = {}
    for m in MARGINS:
        fl = eff_floor(s, m) / (s * s)
        lost[f"m={m}"] = sum(1 for r in rows if r["area_norm_floor1"] is None or r["area_norm_floor1"] < fl)
    per[f"s={s}"] = {"floors_norm": floors, "buds_below_floor_by_m": lost,
                     "no_contour": sum(1 for r in rows if r["area_norm_floor1"] is None),
                     "min_norm_floor1": None if not any(r["area_norm_floor1"] is not None for r in rows)
                     else min(r["area_norm_floor1"] for r in rows if r["area_norm_floor1"] is not None),
                     "rows": rows}
out["per_bud"] = per

# ---- 2b) RAW-area accounting (v2 correction): the normalised values above are
# rounded to 0.1, which manufactured apparent 'tolerance rescues' near the
# line. Recompute with raw contour areas: a bud is below a margin's floor iff
# raw_area < eff_floor (detector passes area >= min_area). ----
def bud_raw_areas(s):
    w, h = int(round(1280 * s)), int(round(960 * s))
    raws = []
    for seed, nb, nd in ORIG:
        img, objs = load_scene(seed, nb, nd)
        small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        cnts = contours_of(small, odd_kernel(s))
        for o in objs:
            if o["label"] != "bud":
                continue
            cx, cy = o["cx"] * s, o["cy"] * s
            a = None
            for c, ar in cnts:
                if cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                    a = round(ar, 3)
                    break
            raws.append(a)
        del img, small
    return raws

raw_acc = {}
for s in (0.3, 0.22):
    raws = bud_raw_areas(s)
    below = {}
    for m in MARGINS:
        fl = eff_floor(s, m)
        below[f"m={m}"] = sum(1 for a in raws if a is None or a < fl)
    det_lost = {}
    for m in MARGINS:
        cell = R["curve"][f"s={s}"][f"m={m}"]["clean"]
        det_lost[f"m={m}"] = 76 - int(round(cell["bud_recall"] * 76))
    raw_acc[f"s={s}"] = {"raw_areas_sorted": sorted(a for a in raws if a is not None),
                         "no_contour": sum(1 for a in raws if a is None),
                         "buds_below_floor_raw_by_m": below,
                         "detect_buds_lost_by_m": det_lost,
                         "exact_match_all_margins": below == det_lost}
out["raw_accounting"] = raw_acc

# r6-square raw areas per scale vs the m=0 effective floor
sq_raw = {}
for s in SCALES:
    w, h = int(round(1280 * s)), int(round(960 * s))
    raws = []
    for seed, nb, nd in ORIG:
        img, objs = load_scene(seed, nb, nd)
        cimg, items = plant_clutter(img, objs, seed)
        small = cv2.resize(cimg, (w, h), interpolation=cv2.INTER_AREA)
        cnts = contours_of(small, odd_kernel(s))
        for it in items:
            if it["r"] != 6 or it["shape"] != "square":
                continue
            cx, cy = it["cx"] * s, it["cy"] * s
            for c, ar in cnts:
                if cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                    raws.append(round(ar, 3))
                    break
        del img, cimg, small
    fl0 = eff_floor(s, 0.0)
    sq_raw[f"s={s}"] = {"floor_m0": fl0, "raw_sorted": sorted(raws),
                        "n_at_or_above_floor": sum(1 for a in raws if a >= fl0),
                        "bench_rs_leaks_m0": R["curve"][f"s={s}"]["m=0.0"]["cluttered"]["pass_radius_subfloor"]["passed"]
                        - R["curve"][f"s={s}"]["m=0.0"]["cluttered"]["pass_true_subfloor"]["passed"]}
out["r6_square_raw"] = sq_raw

# ---- 3) in-situ r=6 clutter contour norms per scale ----
insitu = {}
for s in SCALES:
    w, h = int(round(1280 * s)), int(round(960 * s))
    rows = {}
    for seed, nb, nd in ORIG:
        img, objs = load_scene(seed, nb, nd)
        cimg, items = plant_clutter(img, objs, seed)
        small = cv2.resize(cimg, (w, h), interpolation=cv2.INTER_AREA)
        cnts = contours_of(small, odd_kernel(s))
        for it in items:
            if it["r"] != 6:
                continue
            cx, cy = it["cx"] * s, it["cy"] * s
            a = None
            for c, ar in cnts:
                if cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                    a = ar / (s * s)
                    break
            rows.setdefault(f"r6_{it['shape']}", []).append(None if a is None else round(a, 1))
        del img, cimg, small
    insitu[f"s={s}"] = {k: {"n": len(v), "found": sum(1 for x in v if x is not None),
                            "median": None if not any(x is not None for x in v) else round(float(np.median([x for x in v if x is not None])), 1),
                            "max": None if not any(x is not None for x in v) else round(float(np.max([x for x in v if x is not None])), 1),
                            "above_120": sum(1 for x in v if x is not None and x >= 120)}
                        for k, v in rows.items()}
out["insitu_r6"] = insitu

# ---- 4) precision monotonicity ----
mono = {}
for s in SCALES:
    precs = [R["curve"][f"s={s}"][f"m={m}"]["cluttered"]["precision"] for m in MARGINS]
    mono[f"s={s}"] = {"precisions": precs, "monotonic_nondecreasing": all(b >= a for a, b in zip(precs, precs[1:]))}
out["precision_monotonic"] = mono

with open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-19-downscale-margin-posthoc.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(json.dumps({k: v for k, v in out.items() if k != "per_bud"}, indent=1, ensure_ascii=False))
for s in ("s=0.3", "s=0.22"):
    pb = out["per_bud"][s]
    print(s, "floors_norm", pb["floors_norm"])
    print(s, "below_by_m", pb["buds_below_floor_by_m"], "no_contour", pb["no_contour"], "min_norm_floor1", pb["min_norm_floor1"])
