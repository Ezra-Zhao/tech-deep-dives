"""BLINDRAW recalibration bench (2026-11-13). Prereg: 2026-11-13-raw-recalibration-prereg.md
Memory-light: one scene image at a time; only contour-area lists retained.
"""
import json, math, os, sys, time, gc
import numpy as np
import cv2

REPO = "/home/hatch/workspace/github/Bloom-Counter"
BASE = "/home/hatch/workspace/your_files/顶刊技术文章/data"
OUT = os.path.join(BASE, "2026-11-13-raw-recalibration-bench.json")
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_recal_bench"
os.makedirs(WORK, exist_ok=True)
from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
REF7, REF3, REFRAW = 3806.0, 3740.0, 3718.5
CAL_S = 0.5
POOLS = {
    "T1": [(5111, 34, 20), (5212, 30, 17), (5313, 37, 21), (5414, 32, 18)],
    "T2": [(6111, 35, 19), (6212, 31, 18), (6313, 36, 20), (6414, 33, 19)],
}

def areas_all(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    out = {}
    # BLINDRAW areas are connected-component PIXEL areas (stats), exactly as in
    # 2026-10-25/11-05 benches -- NOT cv2.contourArea. A first run of this bench
    # used contourArea for raw and was invalidated (s=1 anchor check: +5.6%
    # instead of the known ~-55% fragmentation value); files kept with
    # '-contourarea-invalid' suffix. This is the corrected rerun.
    n_cc, _labels, stats, _cents = cv2.connectedComponentsWithStats(mask, 8)
    out["raw"] = [float(stats[i][4]) for i in range(1, n_cc)]
    for k in (7, 3):
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out[f"m{k}"] = [float(cv2.contourArea(c)) for c in cs]
    return out

def blind_upper(areas):
    a = np.array(sorted(x for x in areas if x > 0), dtype=float)
    if len(a) < 8:
        return None, int(len(a))
    la = np.log(a)
    c = np.array([np.percentile(la, 25), np.percentile(la, 75)])
    lab = None
    for _ in range(100):
        lab = np.argmin(np.abs(la[:, None] - c[None, :]), axis=1)
        nc = np.array([la[lab == k].mean() if np.any(lab == k) else c[k] for k in range(2)])
        if np.allclose(nc, c):
            break
        c = nc
    hi = a[lab == 1]
    if len(hi) == 0:
        return None, int(len(a))
    return round(float(np.median(hi)), 1), int(len(a))

def est(areas, ref):
    um, n = blind_upper(areas)
    if um is None:
        return None, None, n
    return round(math.sqrt(um / ref), 4), um, n

def err(sh, s):
    return round(sh / s - 1.0, 4) if sh else None

R = {"prereg": "data/2026-11-13-raw-recalibration-prereg.md", "scales": SCALES,
     "refs_old": {"morph7": REF7, "morph3": REF3, "raw": REFRAW}, "cal_scale": CAL_S, "pools": {}}
t0 = time.time()
for pool_name, scenes in POOLS.items():
    scene_data = []
    for seed, nb, nd in scenes:
        p = os.path.join(WORK, f"{pool_name}_{seed}.jpg")
        truth = generate_image(p, nb, nd, seed=seed)
        img = cv2.imread(p)
        by_scale = {}
        for s in SCALES:
            w = int(round(1280 * s)); h = int(round(960 * s))
            small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
            aa = areas_all(small)
            by_scale[str(s)] = aa
            del small
        scene_data.append({"seed": seed, "nominal": [nb, nd],
                           "actual_blooms": truth["blooms"], "actual_buds": truth["buds"],
                           "by_scale": by_scale})
        del img; gc.collect()
        print(f"[{pool_name}] scene {seed} done actual={truth['blooms']}+{truth['buds']}", flush=True)
    # calibration references (scenes sorted by seed ascending = list order)
    cal_refs = {}
    for k in (1, 2, 4):
        pooled_cal = [a for sd in scene_data[:k] for a in sd["by_scale"][str(CAL_S)]["raw"]]
        um, n = blind_upper(pooled_cal)
        cal_refs[f"R{k}"] = {"ref": round(um / (CAL_S ** 2), 1) if um else None,
                             "cal_upper_median_at_cal_s": um, "n_cal_areas": n,
                             "cal_seeds": [sd["seed"] for sd in scene_data[:k]]}
    self_refs = {}
    for sd in scene_data:
        um, n = blind_upper(sd["by_scale"][str(CAL_S)]["raw"])
        self_refs[str(sd["seed"])] = round(um / (CAL_S ** 2), 1) if um else None
    pooled_points, scene_points = [], []
    for s in SCALES:
        a7 = [a for sd in scene_data for a in sd["by_scale"][str(s)]["m7"]]
        a3 = [a for sd in scene_data for a in sd["by_scale"][str(s)]["m3"]]
        ar = [a for sd in scene_data for a in sd["by_scale"][str(s)]["raw"]]
        sh7, _, _ = est(a7, REF7); sh3, _, _ = est(a3, REF3)
        sh_old, um_old, _ = est(ar, REFRAW)
        rec = {"s": s, "s_hat7": sh7, "s_hat3": sh3, "raw_upper_median": um_old,
               "s_hat_raw_old": sh_old, "err_raw_old": err(sh_old, s)}
        meds = {}
        for kname in ("R1", "R2", "R4"):
            refk = cal_refs[kname]["ref"]
            shk = round(math.sqrt(um_old / refk), 4) if (um_old and refk) else None
            rec[f"s_hat_raw_{kname}"] = shk; rec[f"err_raw_{kname}"] = err(shk, s)
        for tag, rawkey in (("old", "s_hat_raw_old"), ("R1", "s_hat_raw_R1"), ("R4", "s_hat_raw_R4")):
            vals = [v for v in (sh7, sh3, rec[rawkey]) if v is not None]
            med = round(float(np.median(vals)), 4) if len(vals) == 3 else None
            meds[tag] = med; rec[f"s_hat_med3_{tag}"] = med; rec[f"err_med3_{tag}"] = err(med, s)
        pooled_points.append(rec)
        for sd in scene_data:
            ars = sd["by_scale"][str(s)]["raw"]
            sho, _, _ = est(ars, REFRAW)
            refself = self_refs[str(sd["seed"])]
            um_s, _ = blind_upper(ars)
            sh_self = round(math.sqrt(um_s / refself), 4) if (um_s and refself) else None
            scene_points.append({"seed": sd["seed"], "s": s,
                                 "s_hat_raw_old": sho, "err_raw_old": err(sho, s),
                                 "s_hat_raw_self": sh_self, "err_raw_self": err(sh_self, s)})
    pool_rec = {"scenes": [{"seed": sd["seed"], "nominal": sd["nominal"],
                            "actual_blooms": sd["actual_blooms"], "actual_buds": sd["actual_buds"]} for sd in scene_data],
                "cal_refs": cal_refs, "self_refs": self_refs,
                "pooled_points": pooled_points, "scene_points": scene_points}
    R["pools"][pool_name] = pool_rec
    with open(PROG, "a") as f:
        f.write(json.dumps({"pool": pool_name, "cal_refs": cal_refs}) + "\n")
    print(f"[{pool_name}] cal_refs={json.dumps(cal_refs)}", flush=True)
    del scene_data; gc.collect()

R["elapsed_sec"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print("DONE", OUT, R["elapsed_sec"])
