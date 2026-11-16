"""Single-marker noise + per-scene threshold recalibration bench (2026-11-15).

Follow-up to 2026-11-06 / 2026-11-14 (marker guard). Pre-registration
frozen in data/2026-11-15-single-marker-prereg.md before this run.

Arm A: 60 fresh marker frames (seeds 13000-13059), single readings per
scale (raw + corrected with the frozen 2026-11-14 bias curve).
Arm B: 300 archived per-scene MED3 points (2026-11-05 x3 sets,
2026-11-06 holdout3, 2026-11-14 holdout4) paired with all 60 single
readings per scale; threshold sweep + median-of-5 baseline recompute.
Arm C: fresh holdout5 scenes (2121/2222/2323/2424), per-scene MED3
computed fresh, each scene/scale paired with 3 dedicated single
marker frames (seeds 31000+).

Usage: .venv/bin/python bench.py <repo> <out_json>
Progress appended to <out_json>.progress.jsonl.
"""
import json, math, os, statistics, sys, time
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "single-marker-bench.json"
BASE_DIR = "/home/hatch/workspace/your_files/顶刊技术文章/data"
PREV5 = os.path.join(BASE_DIR, "2026-11-05-median-vote-bench.json")
PREV6 = os.path.join(BASE_DIR, "2026-11-06-blind3-guard-bench.json")
PREV14 = os.path.join(BASE_DIR, "2026-11-14-marker-correction-bench.json")
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_single_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image, _foliage_background, PINK
from detector.color_segmentation import ColorSegmentationDetector

SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
REF7, REF3, REFRAW = 3806.0, 3740.0, 3718.5
MARKER_REF = 4912.0
BAD_ERR, FLAG_THR = 0.10, 0.08
THRESHOLDS = [0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25]
A_SEEDS = list(range(13000, 13060))
NEW = [(2121, 35, 18), (2222, 32, 19), (2323, 36, 17), (2424, 33, 20)]

# frozen 2026-11-14 calibration grid (bias per scale), verbatim
GRID_S = np.array(SCALES, dtype=float)
GRID_B = np.array([0.0, -0.0004, -0.0025, -0.0064, -0.0128, -0.0177, -0.0217,
                   -0.0275, -0.0296, -0.0382, -0.0472, -0.0593, -0.0792, -0.106, -0.21])

def b_hat(x):
    if x is None:
        return 0.0
    lx = math.log(max(x, 0.07))
    lg = np.log(GRID_S)
    return float(np.interp(lx, lg[::-1], GRID_B[::-1]))

def correct(sh):
    if sh is None:
        return None
    x = sh
    for _ in range(3):
        div = max(0.80, 1.0 + b_hat(x))
        x = sh / div
    return round(x, 4)

def morph_contours3(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ker)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = [float(cv2.contourArea(c)) for c in cnts if cv2.contourArea(c) > 0]
    return out

def marker_frame(seed):
    rng = np.random.default_rng(seed)
    img = _foliage_background(rng, 1280, 960)
    cx, cy = 640 + int(rng.integers(-60, 61)), 480 + int(rng.integers(-60, 61))
    cv2.circle(img, (cx, cy), 40, PINK, -1)
    return img

def marker_single(seed, s):
    img = marker_frame(seed)
    w = int(round(1280 * s)); h = int(round(960 * s))
    small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    areas = morph_contours3(small)
    if not areas:
        return None
    return round(math.sqrt(max(areas) / MARKER_REF), 4)

def morph_areas(image, kernel_size):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [float(cv2.contourArea(c)) for c in contours]

def raw_areas(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    return [float(stats[i][4]) for i in range(1, n)]

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
    return {"upper_median": float(np.median(hi))}

def estimate_from_areas(areas, ref):
    cl = blind_cluster(areas)
    if cl is None:
        return None
    return round(math.sqrt(cl["upper_median"] / ref), 4)

def med3v(a, b, c):
    vals = [v for v in (a, b, c) if v is not None]
    if len(vals) == 3:
        return round(statistics.median(vals), 4)
    if len(vals) == 2:
        return round(sum(vals) / 2.0, 4)
    return None

def err_of(sh, s):
    return round(sh / s - 1.0, 4) if sh is not None else None

def stats_of(errs):
    e = np.array([x for x in errs if x is not None], dtype=float)
    if len(e) == 0:
        return None
    return {"n": int(len(e)), "mean": round(float(np.mean(e)), 4),
            "sd": round(float(np.std(e)), 4),
            "p5": round(float(np.percentile(e, 5)), 4),
            "p95": round(float(np.percentile(e, 95)), 4),
            "min": round(float(np.min(e)), 4), "max": round(float(np.max(e)), 4),
            "mae": round(float(np.mean(np.abs(e))), 4)}

def band_of(s):
    if s >= 0.30:
        return "hi_ge_0.30"
    if s >= 0.18:
        return "mid_0.18_0.28"
    if s >= 0.12:
        return "low_0.12_0.15"
    return "sub_lt_0.12"

t0 = time.time()
R = {"prereg": {"doc": "data/2026-11-15-single-marker-prereg.md",
                "bad_err": BAD_ERR, "flag_thr": FLAG_THR, "thresholds": THRESHOLDS},
     "scales": SCALES}

# ---------- Arm A: single-reading noise, 60 fresh frames ----------
singles_raw = {s: [] for s in SCALES}
singles_corr = {s: [] for s in SCALES}
for seed in A_SEEDS:
    img = marker_frame(seed)
    for s in SCALES:
        w = int(round(1280 * s)); h = int(round(960 * s))
        small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        areas = morph_contours3(small)
        sh = round(math.sqrt(max(areas) / MARKER_REF), 4) if areas else None
        singles_raw[s].append(sh)
        singles_corr[s].append(correct(sh))
    del img
armA = {}
for s in SCALES:
    errs_raw = [err_of(v, s) for v in singles_raw[s]]
    errs_corr = [err_of(v, s) for v in singles_corr[s]]
    med5_errs = []
    for g in range(12):
        grp = [v for v in singles_corr[s][g * 5:(g + 1) * 5] if v is not None]
        if grp:
            med5_errs.append(err_of(round(float(np.median(grp)), 4), s))
    st = stats_of(errs_corr)
    st5 = stats_of(med5_errs)
    armA[f"s={s}"] = {"single_raw": stats_of(errs_raw), "single_corr": st,
                      "median5_corr": st5,
                      "sd_ratio_med5_over_single": round(st5["sd"] / st["sd"], 3) if st and st5 and st["sd"] > 0 else None,
                      "single_corr_values": singles_corr[s]}
    print(f"[A] s={s} single_corr sd={st['sd'] if st else None} mean={st['mean'] if st else None} med5sd={st5['sd'] if st5 else None}", flush=True)
R["armA_noise"] = armA

# ---------- Arm B: retrospective pairing over 300 archived points ----------
prev5 = json.load(open(PREV5))
prev6 = json.load(open(PREV6))
prev14 = json.load(open(PREV14))
points = []  # {set, scene, s, med, errmed}
for name in ("replication", "holdout1", "holdout2"):
    for s in SCALES:
        for ps in prev5["datasets"][name]["results"][f"s={s}"]["per_scene"]:
            points.append({"set": name, "scene": ps["scene_seed"], "s": s,
                           "med": ps["med"], "errmed": ps["errmed"]})
for s in SCALES:
    for ps in prev6["holdout3"]["results"][f"s={s}"]["per_scene"]:
        points.append({"set": "holdout3", "scene": ps["scene_seed"], "s": s,
                       "med": ps["med"], "errmed": ps["errmed"]})
for s in SCALES:
    for ps in prev14["holdout4"]["results"][f"s={s}"]["per_scene"]:
        points.append({"set": "holdout4", "scene": ps["scene_seed"], "s": s,
                       "med": ps["med"], "errmed": ps["errmed"]})
print(f"[B] archived points={len(points)}", flush=True)

def flag_rate(med, s, thr):
    vals = singles_corr[s]
    ok = [v for v in vals if v is not None]
    if med is None or not ok:
        return None
    hits = sum(1 for v in ok if abs(med / v - 1.0) > thr)
    return round(hits / len(ok), 4)

for p in points:
    p["is_bad"] = (p["errmed"] is not None and abs(p["errmed"]) > BAD_ERR)
    p["flag_rates"] = {f"thr={t}": flag_rate(p["med"], p["s"], t) for t in THRESHOLDS}
    base_guard = prev14["validation_marker"]["per_scale"][f"s={p['s']}"]["s_hat_corr"]
    p["baseline_median5_flag"] = (abs(p["med"] / base_guard - 1.0) > FLAG_THR) if p["med"] is not None else None

def aggregate(pts, thr_key=None, thr=None):
    healthy = [p for p in pts if not p["is_bad"] and p["med"] is not None]
    bad = [p for p in pts if p["is_bad"] and p["med"] is not None]
    out = {"n_points": len(pts), "n_healthy": len(healthy), "n_bad": len(bad)}
    if thr_key:
        hr = [p["flag_rates"][thr_key] for p in healthy if p["flag_rates"][thr_key] is not None]
        br = [p["flag_rates"][thr_key] for p in bad if p["flag_rates"][thr_key] is not None]
        out["healthy_flag_rate"] = round(float(np.mean(hr)), 4) if hr else None
        out["bad_catch_rate"] = round(float(np.mean(br)), 4) if br else None
    return out

armB = {"n_points_total": len(points)}
for t in THRESHOLDS:
    key = f"thr={t}"
    sel_all = points
    sel_ge12 = [p for p in points if p["s"] >= 0.12]
    sel_ge15 = [p for p in points if p["s"] >= 0.15]
    armB[key] = {"all_s": aggregate(sel_all, key), "s_ge_0.12": aggregate(sel_ge12, key),
                 "s_ge_0.15": aggregate(sel_ge15, key),
                 "bands": {b: aggregate([p for p in points if band_of(p["s"]) == b], key)
                           for b in ("hi_ge_0.30", "mid_0.18_0.28", "low_0.12_0.15", "sub_lt_0.12")}}
# median-of-5 baseline on same points at 8%
for label, sel in (("all_s", points), ("s_ge_0.12", [p for p in points if p["s"] >= 0.12]),
                   ("s_ge_0.15", [p for p in points if p["s"] >= 0.15])):
    healthy = [p for p in sel if not p["is_bad"] and p["med"] is not None]
    bad = [p for p in sel if p["is_bad"] and p["med"] is not None]
    armB.setdefault("baseline_median5_thr0.08", {})[label] = {
        "healthy_flags": int(sum(1 for p in healthy if p["baseline_median5_flag"])),
        "n_healthy": len(healthy),
        "healthy_flag_rate": round(float(np.mean([1.0 if p["baseline_median5_flag"] else 0.0 for p in healthy])), 4) if healthy else None,
        "bad_caught": int(sum(1 for p in bad if p["baseline_median5_flag"])),
        "n_bad": len(bad)}
# recalibrated thresholds per frozen definition: smallest scan line with
# healthy pairing flag rate <= 5% on the stated scope
def recal(scope_pts):
    for t in THRESHOLDS:
        a = aggregate(scope_pts, f"thr={t}")
        if a["healthy_flag_rate"] is not None and a["healthy_flag_rate"] <= 0.05:
            return {"thr": t, "healthy_flag_rate": a["healthy_flag_rate"],
                    "bad_catch_rate": a["bad_catch_rate"]}
    return {"thr": None}
armB["recalibrated"] = {
    "s_ge_0.12": recal([p for p in points if p["s"] >= 0.12]),
    "bands": {b: recal([p for p in points if band_of(p["s"]) == b])
              for b in ("hi_ge_0.30", "mid_0.18_0.28", "low_0.12_0.15", "sub_lt_0.12")}}
armB["points"] = points
R["armB_retro"] = armB
print(f"[B] recal={armB['recalibrated']}", flush=True)
print(f"[B] thr0.08 s_ge_0.15={armB['thr=0.08']['s_ge_0.15']} baseline={armB['baseline_median5_thr0.08']}", flush=True)
with open(PROG, "a") as f:
    f.write(json.dumps({"arm": "B", "recal": armB["recalibrated"]}) + "\n")

# ---------- Arm C: fresh holdout5 ----------
bases = []
for seed, nb, nd in NEW:
    pth = os.path.join(WORK, f"holdout5_{seed}.jpg")
    truth = generate_image(pth, nb, nd, seed=seed)
    bases.append((seed, cv2.imread(pth), truth["objects"]))
n_objects = sum(len(o) for _, _, o in bases)
det0 = ColorSegmentationDetector()
def score_quick(dets, objects):
    used = set(); tp = fp = 0
    for d in dets:
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        tol = max(38.0, objects[best]["r"] * 1.1) if best is not None else 0
        if best is not None and bd <= tol:
            used.add(best); tp += 1
        else:
            fp += 1
    fn = len(objects) - len(used)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    return round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0
sanity_f1 = float(np.mean([score_quick(det0.detect(im), objs) for _, im, objs in bases]))
print(f"[C] n_objects={n_objects} sanityF1(mean per-scene)={sanity_f1}", flush=True)

recal_thr = armB["recalibrated"]["s_ge_0.12"]["thr"]
c_points = []
for si, s in enumerate(SCALES):
    w = int(round(1280 * s)); h = int(round(960 * s))
    pooled_areas7, pooled_areas3, pooled_arear = [], [], []
    for idx, (seed, im, objs) in enumerate(bases):
        small = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
        a7 = morph_areas(small, 7); a3 = morph_areas(small, 3); ar = raw_areas(small)
        pooled_areas7 += a7; pooled_areas3 += a3; pooled_arear += ar
        e7 = estimate_from_areas(a7, REF7); e3 = estimate_from_areas(a3, REF3); er = estimate_from_areas(ar, REFRAW)
        pm = med3v(e7, e3, er)
        guards = []
        for k in range(3):
            gseed = 31000 + idx * 1000 + si * 10 + k
            sh = marker_single(gseed, s)
            guards.append(correct(sh))
        c_points.append({"scene": seed, "s": s, "med": pm, "errmed": err_of(pm, s),
                         "is_bad": (err_of(pm, s) is not None and abs(err_of(pm, s)) > BAD_ERR),
                         "guards_corr": guards})
    pe7 = estimate_from_areas(pooled_areas7, REF7); pe3 = estimate_from_areas(pooled_areas3, REF3)
    per = estimate_from_areas(pooled_arear, REFRAW)
    pmed = med3v(pe7, pe3, per)
    print(f"[C] s={s} pooled_med={pmed} err={err_of(pmed, s)}", flush=True)
    with open(PROG, "a") as f:
        f.write(json.dumps({"arm": "C", "s": s, "pooled_med": pmed}) + "\n")

def c_aggregate(pts, thr):
    healthy_rates, bad_rates = [], []
    for p in pts:
        if p["med"] is None:
            continue
        gs = [g for g in p["guards_corr"] if g is not None]
        if not gs:
            continue
        rate = float(np.mean([1.0 if abs(p["med"] / g - 1.0) > thr else 0.0 for g in gs]))
        (bad_rates if p["is_bad"] else healthy_rates).append(rate)
    return {"healthy_flag_rate": round(float(np.mean(healthy_rates)), 4) if healthy_rates else None,
            "n_healthy_points": len(healthy_rates),
            "bad_catch_rate": round(float(np.mean(bad_rates)), 4) if bad_rates else None,
            "n_bad_points": len(bad_rates)}
armC = {"n_objects": n_objects, "baseline_sanity_f1_mean": sanity_f1,
        "recal_thr_applied": recal_thr,
        "thr_0.08": {"all_s": c_aggregate(c_points, 0.08),
                     "s_ge_0.12": c_aggregate([p for p in c_points if p["s"] >= 0.12], 0.08),
                     "s_ge_0.15": c_aggregate([p for p in c_points if p["s"] >= 0.15], 0.08)},
        "points": c_points}
if recal_thr is not None:
    armC[f"thr_{recal_thr}"] = {"all_s": c_aggregate(c_points, recal_thr),
                               "s_ge_0.12": c_aggregate([p for p in c_points if p["s"] >= 0.12], recal_thr),
                               "s_ge_0.15": c_aggregate([p for p in c_points if p["s"] >= 0.15], recal_thr)}
R["armC_holdout5"] = armC
print(f"[C] thr0.08={armC['thr_0.08']}", flush=True)
if recal_thr is not None:
    print(f"[C] recal_thr={recal_thr} -> {armC[f'thr_{recal_thr}']}", flush=True)

R["elapsed_sec"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print("ALL DONE", R["elapsed_sec"])
