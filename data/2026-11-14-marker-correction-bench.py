"""Marker-guard low-end bias correction bench (2026-11-14).

Follow-up to 2026-11-06 (marker guard). Pre-registration frozen in
data/2026-11-14-marker-correction-prereg.md before this script was run.

Calibration: marker frames seeds 9100-9119 (20 frames) -> bias curve b(s)
on log-s piecewise-linear grid. Correction: fixed-point iteration
x <- s_raw / (1 + b_hat(x)), 3 iterations, divisor floored at 0.80.
Validation marker frames: seeds 9200-9204 (5 replicates, deployment
protocol). Retrospective guard ledger: old three sets (MED3 from the
2026-11-05 archive) + holdout3 (MED3 from the 2026-11-06 archive),
D recomputed with validation-frame marker (raw and corrected).
Fresh: holdout4 (1717/1818/1919/2020, 210 objects) full run +
injection arm (g in {0.85,1.15,1.30} x s in {1.0,0.5,0.30,0.22,0.15,0.12}).

Usage: .venv/bin/python bench.py <repo> <out_json>
Progress appended to <out_json>.progress.jsonl.
"""
import json, math, os, statistics, sys, time
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "marker-correction-bench.json"
BASE_DIR = "/home/hatch/workspace/your_files/顶刊技术文章/data"
PREV5 = os.path.join(BASE_DIR, "2026-11-05-median-vote-bench.json")
PREV6 = os.path.join(BASE_DIR, "2026-11-06-blind3-guard-bench.json")
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_corr_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image, _foliage_background, _place, _draw_bloom, _draw_bud, PINK
from detector.color_segmentation import ColorSegmentationDetector

BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
REF7, REF3, REFRAW = 3806.0, 3740.0, 3718.5
BAD_ERR, FLAG_THR = 0.10, 0.08
NEW = [(1717, 34, 19), (1818, 31, 17), (1919, 36, 20), (2020, 33, 18)]
INJ_SCALES = [1.0, 0.5, 0.30, 0.22, 0.15, 0.12]
INJ_G = [0.85, 1.15, 1.30]
CAL_SEEDS = list(range(9100, 9120))
VAL_SEEDS = list(range(9200, 9205))

def odd_kernel(s):
    k = int(round(BASE_KERNEL * s))
    if k % 2 == 0:
        k += 1
    return max(3, k)

def detect_with(image, min_area, bloom_min, kernel_size):
    det = ColorSegmentationDetector(min_area=int(min_area),
                                    bloom_area_min=int(bloom_min),
                                    morph_kernel=int(kernel_size))
    return det.detect(image)

def score(dets, objects, geom_scale=1.0):
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
        tol = max(38.0 * geom_scale, objects[best]["r"] * 1.1) if best is not None else 0
        if best is not None and bd <= tol:
            used.add(best); tp += 1; per[d.label][0] += 1
        else:
            fp += 1
    fn = len(objects) - len(used)
    for i, o in enumerate(objects):
        if i not in used:
            per[o["label"]][1] += 1
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    tb = sum(1 for o in objects if o["label"] == "bloom")
    td = sum(1 for o in objects if o["label"] == "bud")
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_blooms": sum(1 for d in dets if d.label == "bloom"),
            "det_buds": sum(1 for d in dets if d.label == "bud"),
            "true_blooms": tb, "true_buds": td,
            "bloom_recall": round(per["bloom"][0] / max(1, tb), 4),
            "bud_recall": round(per["bud"][0] / max(1, td), 4)}

def micro(rows):
    tp = sum(r["tp"] for r in rows); fp = sum(r["fp"] for r in rows); fn = sum(r["fn"] for r in rows)
    prec = tp / (tp + fp) if tp + fp else 1.0; rec = tp / (tp + fn) if tp + fn else 1.0
    tb = sum(r["true_blooms"] for r in rows); td = sum(r["true_buds"] for r in rows)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_blooms": sum(r["det_blooms"] for r in rows), "true_blooms": tb,
            "det_buds": sum(r["det_buds"] for r in rows), "true_buds": td,
            "bloom_recall": round(sum(r["bloom_recall"] * r["true_blooms"] for r in rows) / max(1, tb), 4),
            "bud_recall": round(sum(r["bud_recall"] * r["true_buds"] for r in rows) / max(1, td), 4),
            "count_err_pct": round(100.0 * (sum(r["det_blooms"] + r["det_buds"] for r in rows) - (tb + td)) / max(1, tb + td), 2)}

def scaled_objects(objects, s):
    return [{"label": o["label"], "cx": o["cx"] * s, "cy": o["cy"] * s, "r": o["r"] * s}
            for o in objects]

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
    med_lo = float(np.median(lo)); med_hi = float(np.median(hi))
    return {"upper_median": round(med_hi, 1), "lower_median": round(med_lo, 1),
            "n_upper": int(len(hi)), "n_lower": int(len(lo)), "n_total": int(len(a)),
            "separation_log": round(math.log(med_hi / med_lo), 3) if med_lo > 0 else None}

def estimate_from_areas(areas, ref):
    cl = blind_cluster(areas)
    if cl is None:
        return {"s_hat": None, "cluster": None}
    return {"s_hat": round(math.sqrt(cl["upper_median"] / ref), 4), "cluster": cl}

def med3v(a, b, c):
    vals = [v for v in (a, b, c) if v is not None]
    if len(vals) == 3:
        return round(statistics.median(vals), 4)
    if len(vals) == 2:
        return round(sum(vals) / 2.0, 4)
    return None

def err_of(sh, s):
    return round(sh / s - 1.0, 4) if sh is not None else None

def route_of(s_val):
    if s_val is None:
        return "U_alert_fallback"
    if s_val >= 0.30:
        return "P"
    if s_val >= 0.15:
        return "U"
    return "U_alert"

def morph_contours3(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ker)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        a = cv2.contourArea(c)
        if a <= 0:
            continue
        out.append(float(a))
    return out

def marker_frame(seed):
    rng = np.random.default_rng(seed)
    img = _foliage_background(rng, 1280, 960)
    cx, cy = 640 + int(rng.integers(-60, 61)), 480 + int(rng.integers(-60, 61))
    cv2.circle(img, (cx, cy), 40, PINK, -1)
    return img

def marker_measure(img):
    areas = morph_contours3(img)
    return max(areas) if areas else None

def marker_shat(frames, s, ref):
    w = int(round(1280 * s)); h = int(round(960 * s))
    areas = [marker_measure(cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA)) for f in frames]
    ok = [a for a in areas if a]
    if not ok:
        return None, areas
    return round(math.sqrt(float(np.median(ok)) / ref), 4), areas

def gen_injected(path, n_blooms, n_buds, seed, g, width=1280, height=960):
    rng = np.random.default_rng(seed)
    img = _foliage_background(rng, width, height)
    bloom_radii = [int(round(v * g)) for v in rng.integers(30, 50, size=n_blooms)]
    bud_radii = [int(round(v * g)) for v in rng.integers(11, 17, size=n_buds)]
    centers = _place(rng, width, height, bloom_radii + bud_radii)
    truth = {"blooms": 0, "buds": 0, "objects": [], "simulated": True, "g": g}
    idx = 0
    for r in bloom_radii:
        if idx >= len(centers):
            break
        cx, cy = centers[idx]; idx += 1
        _draw_bloom(img, rng, cx, cy, r)
        truth["blooms"] += 1
        truth["objects"].append({"label": "bloom", "cx": cx, "cy": cy, "r": r})
    for r in bud_radii:
        if idx >= len(centers):
            break
        cx, cy = centers[idx]; idx += 1
        _draw_bud(img, rng, cx, cy, r)
        truth["buds"] += 1
        truth["objects"].append({"label": "bud", "cx": cx, "cy": cy, "r": r})
    cv2.putText(img, "SIMULATED", (width - 260, height - 24),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (110, 110, 110), 2)
    cv2.imwrite(path, img)
    return truth

def load_bases(name, scenes):
    lst = []
    for seed, nb, nd in scenes:
        p = os.path.join(WORK, f"{name}_{seed}.jpg")
        truth = generate_image(p, nb, nd, seed=seed)
        lst.append((seed, cv2.imread(p), truth["objects"]))
    return lst

def D_of(med, guard):
    if med is None or guard is None:
        return None
    return round(med / guard - 1.0, 4)

t0 = time.time()
R = {"prereg": {"flag_thr": FLAG_THR, "bad_err": BAD_ERR,
                "doc": "data/2026-11-14-marker-correction-prereg.md"},
     "scales": SCALES}

# ---------- calibration: bias curve from seeds 9100-9119 ----------
cal_frames = [marker_frame(sd) for sd in CAL_SEEDS]
cal_ref = float(np.median([marker_measure(f) for f in cal_frames]))
cal = {}
for s in SCALES:
    sh, areas = marker_shat(cal_frames, s, cal_ref)
    cal[f"s={s}"] = {"s_hat": sh, "bias": err_of(sh, s), "areas": areas}
R["calibration"] = {"ref_area": cal_ref, "per_scale": cal}
grid_s = np.array(SCALES, dtype=float)
grid_b = np.array([cal[f"s={s}"]["bias"] for s in SCALES], dtype=float)
print(f"cal ref={cal_ref} bias={ {s: cal[f's={s}']['bias'] for s in SCALES} }", flush=True)

def b_hat(x):
    if x is None:
        return 0.0
    lx = math.log(max(x, 0.07))
    lg = np.log(grid_s)
    return float(np.interp(lx, lg[::-1], grid_b[::-1]))

def correct(sh):
    if sh is None:
        return None
    x = sh
    for _ in range(3):
        div = max(0.80, 1.0 + b_hat(x))
        x = sh / div
    return round(x, 4)

# in-sample corrected errors on calibration set (for honesty: fit set)
cal_corr = {f"s={s}": err_of(correct(cal[f"s={s}"]["s_hat"]), s) for s in SCALES}
R["calibration"]["corrected_err_insample"] = cal_corr

# ---------- validation marker frames 9200-9204 ----------
val_frames = [marker_frame(sd) for sd in VAL_SEEDS]
val_ref = float(np.median([marker_measure(f) for f in val_frames]))
val = {}
for s in SCALES:
    sh, areas = marker_shat(val_frames, s, val_ref)
    shc = correct(sh)
    val[f"s={s}"] = {"s_hat_raw": sh, "err_raw": err_of(sh, s),
                     "s_hat_corr": shc, "err_corr": err_of(shc, s), "areas": areas}
R["validation_marker"] = {"ref_area": val_ref, "per_scale": val}
print(f"val ref={val_ref} raw={ {s: val[f's={s}']['err_raw'] for s in SCALES} }", flush=True)
print(f"val corr={ {s: val[f's={s}']['err_corr'] for s in SCALES} }", flush=True)

def mk(s):
    return val[f"s={s}"]["s_hat_raw"], val[f"s={s}"]["s_hat_corr"]

# ---------- retrospective guard ledger ----------
prev5 = json.load(open(PREV5))
prev6 = json.load(open(PREV6))
retro = {}
for name in ("replication", "holdout1", "holdout2"):
    blk = {}
    for s in SCALES:
        arch = prev5["datasets"][name]["results"][f"s={s}"]
        mr, mc = mk(s)
        row = {"med": arch["pooled"]["med"], "errmed": arch["pooled"]["errmed"],
               "D_raw": D_of(arch["pooled"]["med"], mr),
               "D_corr": D_of(arch["pooled"]["med"], mc), "per_scene": []}
        for ps in arch["per_scene"]:
            row["per_scene"].append({
                "scene_seed": ps["scene_seed"], "med": ps["med"], "errmed": ps["errmed"],
                "D_raw": D_of(ps["med"], mr), "D_corr": D_of(ps["med"], mc)})
        blk[f"s={s}"] = row
    retro[name] = blk
blk = {}
for s in SCALES:
    arch = prev6["holdout3"]["results"][f"s={s}"]
    mr, mc = mk(s)
    row = {"med": arch["pooled"]["med"], "errmed": arch["pooled"]["errmed"],
           "D_raw": D_of(arch["pooled"]["med"], mr),
           "D_corr": D_of(arch["pooled"]["med"], mc), "per_scene": []}
    for ps in arch["per_scene"]:
        row["per_scene"].append({
            "scene_seed": ps["scene_seed"], "med": ps["med"], "errmed": ps["errmed"],
            "D_raw": D_of(ps["med"], mr), "D_corr": D_of(ps["med"], mc)})
    blk[f"s={s}"] = row
retro["holdout3"] = blk
R["retrospective"] = retro
print("[retro] done", flush=True)

# ---------- fresh holdout4 ----------
bases = load_bases("holdout4", NEW)
bases_objs = [objs for _, _, objs in bases]
n_objects = sum(len(o) for o in bases_objs)
det0 = ColorSegmentationDetector()
sanity = micro([score(det0.detect(im), objs, 1.0) for _, im, objs in bases])
ds = {"scenes": [s for s, _, _ in NEW], "n_objects": n_objects,
      "baseline_sanity": sanity, "results": {}}
print(f"[holdout4] n={n_objects} sanityF1={sanity['f1']}", flush=True)

def detect_P(natives, true_s, s_used):
    mn = max(1, round(BASE_MIN * s_used * s_used))
    bm = max(1, round(BASE_BLOOM * s_used * s_used))
    k = odd_kernel(s_used)
    r = micro([score(detect_with(im, mn, bm, k), objs, true_s) for im, objs in natives])
    r["params"] = {"min_area": mn, "bloom_min": bm, "kernel": k}
    return r

def detect_U(natives):
    rows = []
    for (im, _), objs in zip(natives, bases_objs):
        up = cv2.resize(im, (1280, 960), interpolation=cv2.INTER_LINEAR)
        rows.append(score(detect_with(up, BASE_MIN, BASE_BLOOM, BASE_KERNEL), objs, 1.0))
    return micro(rows)

for s in SCALES:
    w = int(round(1280 * s)); h = int(round(960 * s))
    natives = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA), scaled_objects(objs, s))
               for _, im, objs in bases]
    nat_imgs = [im for im, _ in natives]
    est7 = estimate_from_areas([a for im in nat_imgs for a in morph_areas(im, 7)], REF7)
    est3 = estimate_from_areas([a for im in nat_imgs for a in morph_areas(im, 3)], REF3)
    estraw = estimate_from_areas([a for im in nat_imgs for a in raw_areas(im)], REFRAW)
    m_sh = med3v(est7["s_hat"], est3["s_hat"], estraw["s_hat"])
    mr, mc = mk(s)
    per_scene = []
    for idx, im in enumerate(nat_imgs):
        e7 = estimate_from_areas(morph_areas(im, 7), REF7)
        e3 = estimate_from_areas(morph_areas(im, 3), REF3)
        er_ = estimate_from_areas(raw_areas(im), REFRAW)
        pm = med3v(e7["s_hat"], e3["s_hat"], er_["s_hat"])
        per_scene.append({"scene_seed": NEW[idx][0], "med": pm, "errmed": err_of(pm, s),
                          "D_raw": D_of(pm, mr), "D_corr": D_of(pm, mc)})
    u_res = detect_U(natives)
    p_cache = {}
    def p_f1(sh):
        if sh is None:
            return None
        if sh not in p_cache:
            p_cache[sh] = detect_P(natives, s, sh)["f1"]
        return p_cache[sh]
    oracle_route = route_of(s)
    oracle_f1 = p_f1(s) if oracle_route == "P" else u_res["f1"]
    deploy = {"ORACLE": oracle_f1, "U_ONLY": u_res["f1"]}
    rt = route_of(m_sh)
    deploy["MED3"] = p_f1(m_sh) if rt == "P" else u_res["f1"]
    d_raw, d_corr = D_of(m_sh, mr), D_of(m_sh, mc)
    f_raw = d_raw is not None and abs(d_raw) > FLAG_THR
    f_corr = d_corr is not None and abs(d_corr) > FLAG_THR
    deploy["MED3_GUARD_RAW"] = u_res["f1"] if f_raw else deploy["MED3"]
    deploy["MED3_GUARD_CORR"] = u_res["f1"] if f_corr else deploy["MED3"]
    ds["results"][f"s={s}"] = {
        "pooled": {"sh7": est7["s_hat"], "sh3": est3["s_hat"], "shraw": estraw["s_hat"],
                   "med": m_sh, "errmed": err_of(m_sh, s),
                   "sh_marker_raw": mr, "sh_marker_corr": mc,
                   "D_raw": d_raw, "D_corr": d_corr,
                   "flag_raw": f_raw, "flag_corr": f_corr},
        "per_scene": per_scene, "U_f1": u_res["f1"],
        "deployment": {k: (round(v, 4) if v is not None else None) for k, v in deploy.items()},
        "oracle_route": oracle_route}
    with open(PROG, "a") as f:
        f.write(json.dumps({"set": "holdout4", "s": s, "med": m_sh,
                            "errmed": err_of(m_sh, s), "D_raw": d_raw, "D_corr": d_corr}) + "\n")
    print(f"[holdout4] s={s} med={m_sh} errmed={err_of(m_sh, s)} Draw={d_raw} Dcorr={d_corr}", flush=True)
loss = {}
for pol in ("MED3", "MED3_GUARD_RAW", "MED3_GUARD_CORR"):
    loss[pol] = round(sum(ds["results"][f"s={s}"]["deployment"]["ORACLE"] -
                          ds["results"][f"s={s}"]["deployment"][pol] for s in SCALES), 4)
ds["summary"] = {"deployment_loss_vs_oracle": loss,
                 "pooled_bad_med3": sum(1 for s in SCALES
                                        if ds["results"][f"s={s}"]["pooled"]["errmed"] is not None
                                        and abs(ds["results"][f"s={s}"]["pooled"]["errmed"]) > BAD_ERR)}
R["holdout4"] = ds
print(f"[holdout4] summary={ds['summary']}", flush=True)

# ---------- injection arm on holdout4 ----------
inj = {}
inj_bases = []
for seed, nb, nd in NEW:
    lst = []
    for g in INJ_G:
        p = os.path.join(WORK, f"inj_{seed}_g{g}.jpg")
        truth = gen_injected(p, nb, nd, seed=seed, g=g)
        lst.append((g, cv2.imread(p), truth))
    inj_bases.append(lst)
for g in INJ_G:
    inj[f"g={g}"] = {}
    for s in INJ_SCALES:
        w = int(round(1280 * s)); h = int(round(960 * s))
        imgs = [cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
                for lst in inj_bases for gg, im, _ in lst if gg == g]
        est7 = estimate_from_areas([a for im in imgs for a in morph_areas(im, 7)], REF7)
        est3 = estimate_from_areas([a for im in imgs for a in morph_areas(im, 3)], REF3)
        estraw = estimate_from_areas([a for im in imgs for a in raw_areas(im)], REFRAW)
        m_sh = med3v(est7["s_hat"], est3["s_hat"], estraw["s_hat"])
        mr, mc = mk(s)
        row = {"med": m_sh, "errmed": err_of(m_sh, s),
               "D_raw": D_of(m_sh, mr), "D_corr": D_of(m_sh, mc)}
        inj[f"g={g}"][f"s={s}"] = row
        print(f"[inj] g={g} s={s} med={m_sh} errmed={row['errmed']} Draw={row['D_raw']} Dcorr={row['D_corr']}", flush=True)
R["injection"] = inj

R["elapsed_sec"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print("ALL DONE", R["elapsed_sec"])
