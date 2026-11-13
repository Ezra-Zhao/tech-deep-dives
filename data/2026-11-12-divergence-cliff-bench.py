"""Divergence cliff vs slope bench (2026-11-12). Prereg: 2026-11-12-divergence-cliff-prereg.md
Memory-light: one scene image at a time; only contour-area lists are retained.
"""
import json, math, os, sys, time, gc
import numpy as np
import cv2

REPO = "/home/hatch/workspace/github/Bloom-Counter"
BASE = "/home/hatch/workspace/your_files/顶刊技术文章/data"
OUT = os.path.join(BASE, "2026-11-12-divergence-cliff-bench.json")
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_cliff_bench"
os.makedirs(WORK, exist_ok=True)
from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
REF7, REF3 = 3806.0, 3740.0
POOLS = {
    "HD1": [(2111, 34, 20), (2212, 30, 17), (2313, 37, 21), (2414, 32, 18)],
    "HD2": [(2515, 35, 19), (2616, 31, 18), (2717, 36, 20), (2818, 33, 19)],
    "LD1": [(3111, 9, 5), (3212, 9, 5), (3313, 9, 5), (3414, 9, 5)],
    "LD2": [(3515, 9, 5), (3616, 9, 5), (3717, 9, 5), (3818, 9, 5)],
    "MIX1": [(4111, 34, 20), (4212, 18, 36), (4313, 52, 6), (4414, 9, 5)],
    "MIX2": [(4515, 34, 20), (4616, 18, 36), (4717, 52, 6), (4818, 9, 5)],
}
ARM = {"HD1": "HD", "HD2": "HD", "LD1": "LD", "LD2": "LD", "MIX1": "MIX", "MIX2": "MIX"}

def morph_areas(image, kernel_size):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [float(cv2.contourArea(c)) for c in contours]

def blind_cluster(areas):
    a = np.array(sorted(x for x in areas if x > 0), dtype=float)
    if len(a) < 8:
        return None
    la = np.log(a)
    c = np.array([np.percentile(la, 25), np.percentile(la, 75)])
    lab = None
    for _ in range(100):
        lab = np.argmin(np.abs(la[:, None] - c[None, :]), axis=1)
        nc = np.array([la[lab == k].mean() if np.any(lab == k) else c[k] for k in range(2)])
        if np.allclose(nc, c):
            break
        c = nc
    lo = a[lab == 0]; hi = a[lab == 1]
    if len(lo) == 0 or len(hi) == 0:
        return None
    return {"upper_median": round(float(np.median(hi)), 1), "n_total": int(len(a))}

def estimate(areas, ref):
    cl = blind_cluster(areas)
    if cl is None:
        return None, None
    return round(math.sqrt(cl["upper_median"] / ref), 4), cl["n_total"]

def tier(div):
    if div is None:
        return "NOEST"
    a = abs(div)
    return "GREEN" if a <= 0.02 else ("AMBER" if a <= 0.15 else "RED")

def point(s, areas7, areas3):
    sh7, n7 = estimate(areas7, REF7)
    sh3, n3 = estimate(areas3, REF3)
    div = round(sh7 / sh3 - 1.0, 4) if (sh7 and sh3) else None
    err7 = round(sh7 / s - 1.0, 4) if sh7 else None
    err3 = round(sh3 / s - 1.0, 4) if sh3 else None
    return {"s": s, "s_hat7": sh7, "s_hat3": sh3, "div": div, "err7": err7, "err3": err3,
            "bad": bool(err7 is not None and abs(err7) > 0.10), "noest": sh7 is None,
            "tier": tier(div), "n7": n7, "n3": n3}

R = {"prereg": "data/2026-11-12-divergence-cliff-prereg.md", "scales": SCALES, "pools": {}}
t0 = time.time()
for pool_name, scenes in POOLS.items():
    # per-scene areas per scale
    scene_data = []  # {seed, actual_blooms, actual_buds, by_scale: {s: (a7,a3)}}
    for seed, nb, nd in scenes:
        p = os.path.join(WORK, f"{pool_name}_{seed}.jpg")
        truth = generate_image(p, nb, nd, seed=seed)
        img = cv2.imread(p)
        by_scale = {}
        for s in SCALES:
            w = int(round(1280 * s)); h = int(round(960 * s))
            small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
            by_scale[str(s)] = (morph_areas(small, 7), morph_areas(small, 3))
            del small
        scene_data.append({"seed": seed, "nominal": [nb, nd],
                           "actual_blooms": truth["blooms"], "actual_buds": truth["buds"],
                           "by_scale": by_scale})
        del img
        gc.collect()
        print(f"[{pool_name}] scene {seed} done actual={truth['blooms']}+{truth['buds']}", flush=True)
    pooled_points, scene_points = [], []
    first_bad_idx = {}
    for si, s in enumerate(SCALES):
        a7 = [a for sd in scene_data for a in sd["by_scale"][str(s)][0]]
        a3 = [a for sd in scene_data for a in sd["by_scale"][str(s)][1]]
        pooled_points.append(point(s, a7, a3))
        for sd in scene_data:
            pt = point(s, sd["by_scale"][str(s)][0], sd["by_scale"][str(s)][1])
            pt["seed"] = sd["seed"]
            scene_points.append(pt)
            if pt["bad"] and sd["seed"] not in first_bad_idx:
                first_bad_idx[sd["seed"]] = si
    def sharp(points):
        est = [p for p in points if not p["noest"]]
        amber = sum(1 for p in est if p["tier"] == "AMBER")
        # transition steps: last GREEN index to first RED index after it (descending s order = list order)
        last_green = max([i for i, p in enumerate(points) if p["tier"] == "GREEN"], default=None)
        reds_after = [i for i, p in enumerate(points) if p["tier"] == "RED" and last_green is not None and i > last_green]
        # better: use last green before first red overall
        first_red = min([i for i, p in enumerate(points) if p["tier"] == "RED"], default=None)
        greens_before = [i for i, p in enumerate(points) if p["tier"] == "GREEN" and first_red is not None and i < first_red]
        trans = (first_red - max(greens_before)) if (first_red is not None and greens_before) else None
        good_divs = [abs(p["div"]) for p in est if not p["bad"]]
        bad_divs = [abs(p["div"]) for p in est if p["bad"]]
        gap = round(min(bad_divs) - max(good_divs), 4) if (good_divs and bad_divs) else None
        return {"n_points": len(points), "n_est": len(est), "n_noest": len(points) - len(est),
                "amber": amber, "amber_share_est": round(amber / max(1, len(est)), 4),
                "transition_steps_lastgreen_to_firstred": trans,
                "separation_gap_pp": round(gap * 100, 2) if gap is not None else None,
                "max_good_absdiv": round(max(good_divs), 4) if good_divs else None,
                "min_bad_absdiv": round(min(bad_divs), 4) if bad_divs else None,
                "n_bad": sum(1 for p in est if p["bad"]),
                "cons_catches_bad": sum(1 for p in est if p["bad"] and p["div"] is not None and abs(p["div"]) > 0.05)}
    fb = {}
    for sd in scene_data:
        idx = first_bad_idx.get(sd["seed"])
        fb[str(sd["seed"])] = (SCALES[idx] if idx is not None else None)
    fb_spread = None
    idxs = [v for v in first_bad_idx.values()]
    if len(idxs) >= 2:
        fb_spread = max(idxs) - min(idxs)
    pool_rec = {"arm": ARM[pool_name],
                "scenes": [{"seed": sd["seed"], "nominal": sd["nominal"],
                            "actual_blooms": sd["actual_blooms"], "actual_buds": sd["actual_buds"]} for sd in scene_data],
                "pooled_points": pooled_points, "scene_points": scene_points,
                "pooled_sharpness": sharp(pooled_points),
                "per_scene_sharpness_all": sharp(scene_points),
                "first_bad_scale_per_scene": fb, "first_bad_spread_steps": fb_spread}
    R["pools"][pool_name] = pool_rec
    with open(PROG, "a") as f:
        f.write(json.dumps({"pool": pool_name, "pooled_sharpness": pool_rec["pooled_sharpness"],
                            "first_bad": fb, "spread": fb_spread}) + "\n")
    print(f"[{pool_name}] pooled sharp={json.dumps(pool_rec['pooled_sharpness'])} first_bad={fb} spread={fb_spread}", flush=True)
    # free area lists
    del scene_data
    gc.collect()

R["elapsed_sec"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print("DONE", OUT, R["elapsed_sec"])
