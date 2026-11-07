"""Guard-for-MED3 bench (2026-11-06).

Follow-up to 2026-11-05 (median vote). Pre-registration frozen in
data/2026-11-06-blind3-guard-prereg.md before this script was run.

Guards (all use D = s_hat_MED3 / s_hat_guard - 1, FLAG if |D| > 0.08):
  MARKER  known-size disc (r=40, simulator PINK) on standalone calibration
          frames, 5 replicates (seeds 9000-9004), kernel-3 morph contour
          area median -> s_hat; ref = median area at s=1.
  SPACE   kernel-3 contour centroids' nearest-neighbour distance median,
          ref = replication pooled NN median at s=1.
  WIDTH   kernel-3 contour bbox max(w,h), blind 2-means upper-cluster
          median, ref = replication pooled upper median at s=1.
Sets: old three datasets (MED3 loaded from the 2026-11-05 bench archive;
SPACE/WIDTH computed fresh), new holdout3 (1313/1414/1515/1616, 206
objects, everything fresh incl. deployment), injection arm (holdout3
scenes with all radii x g in {0.85,1.15,1.30}, s in {1.0,0.5,0.30}).

Usage: .venv/bin/python 2026-11-06-blind3-guard-bench.py <repo> <prev_json> <out_json>
Progress appended to <out_json>.progress.jsonl.
"""
import json, math, os, statistics, sys, time
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
PREV = sys.argv[2] if len(sys.argv) > 2 else "/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-05-median-vote-bench.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else "blind3-guard-bench.json"
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_guard_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image, _foliage_background, _draw_bloom, _draw_bud, _place, PINK
from detector.color_segmentation import ColorSegmentationDetector

BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
REF7, REF3, REFRAW = 3806.0, 3740.0, 3718.5
BAD_ERR, FLAG_THR = 0.10, 0.08
OLD = {
    "replication": [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)],
    "holdout1": [(505, 33, 19), (606, 31, 17), (707, 38, 21), (808, 29, 15)],
    "holdout2": [(909, 34, 20), (1010, 30, 17), (1111, 37, 21), (1212, 32, 18)],
}
NEW = [(1313, 35, 19), (1414, 32, 18), (1515, 36, 20), (1616, 30, 16)]
INJ_SCALES = [1.0, 0.5, 0.30]
INJ_G = [0.85, 1.15, 1.30]

# ---------- shared estimator code (verbatim lineage from 2026-11-05 bench) ----------
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

# ---------- guard signals ----------
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
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        x, y, w, h = cv2.boundingRect(c)
        out.append({"cx": M["m10"] / M["m00"], "cy": M["m01"] / M["m00"],
                    "area": float(a), "w": int(w), "h": int(h)})
    return out

def nn_list(contours):
    if len(contours) < 3:
        return []
    pts = np.array([[c["cx"], c["cy"]] for c in contours])
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(d, 1e18)
    return list(d.min(axis=1))

def cluster_upper(vals):
    a = np.array(sorted(v for v in vals if v > 0), dtype=float)
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
    hi = a[lab == 1]
    return float(np.median(hi)) if len(hi) else None

def guard_signals(images):
    """Pooled + per-scene SPACE/WIDTH raw readings for a list of images."""
    pooled_nn, pooled_w, per = [], [], []
    for im in images:
        cs = morph_contours3(im)
        nnd = nn_list(cs)
        ws = [max(c["w"], c["h"]) for c in cs]
        pooled_nn += nnd; pooled_w += ws
        per.append({"nn_med": round(float(np.median(nnd)), 2) if nnd else None,
                    "width_up": cluster_upper(ws), "n_contours": len(cs)})
    return {"nn_med": round(float(np.median(pooled_nn)), 2) if pooled_nn else None,
            "width_up": cluster_upper(pooled_w), "per_scene": per}

def marker_frame(seed):
    rng = np.random.default_rng(seed)
    img = _foliage_background(rng, 1280, 960)
    cx, cy = 640 + int(rng.integers(-60, 61)), 480 + int(rng.integers(-60, 61))
    cv2.circle(img, (cx, cy), 40, PINK, -1)
    return img

def marker_measure(img):
    cs = morph_contours3(img)
    if not cs:
        return None
    return max(c["area"] for c in cs)

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

def scale_imgs(bases, s):
    w = int(round(1280 * s)); h = int(round(960 * s))
    return [cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA) for _, im, _ in bases]

def D_of(med, guard):
    if med is None or guard is None:
        return None
    return round(med / guard - 1.0, 4)

t0 = time.time()
prev = json.load(open(PREV))

# marker first (refs + per-scale)
mframes = [marker_frame(9000 + i) for i in range(5)]
mref = float(np.median([marker_measure(f) for f in mframes]))
marker = {}
for s in SCALES:
    w = int(round(1280 * s)); h = int(round(960 * s))
    areas = [marker_measure(cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA)) for f in mframes]
    ok = [a for a in areas if a]
    sh = round(math.sqrt(float(np.median(ok)) / mref), 4) if ok else None
    marker[f"s={s}"] = {"areas": areas, "s_hat": sh, "err": err_of(sh, s)}
print(f"marker ref={mref} errs={ {s: marker[f's={s}']['err'] for s in SCALES} }", flush=True)

R = {"prereg": {"flag_thr": FLAG_THR, "bad_err": BAD_ERR, "doc": "data/2026-11-06-blind3-guard-prereg.md"},
     "marker_ref_area": mref, "marker": marker, "scales": SCALES}

# refs for SPACE/WIDTH from replication s=1
rep = load_bases("replication", OLD["replication"])
gs1 = guard_signals([im for _, im, _ in rep])
REF_NN, REF_W = gs1["nn_med"], gs1["width_up"]
R["space_ref_nn"] = REF_NN; R["width_ref"] = REF_W
print(f"SPACE ref={REF_NN} WIDTH ref={REF_W}", flush=True)

def guard_block(images, s):
    g = guard_signals(images)
    sh_space = round(g["nn_med"] / REF_NN, 4) if g["nn_med"] else None
    sh_width = round(g["width_up"] / REF_W, 4) if g["width_up"] else None
    per = []
    for p in g["per_scene"]:
        per.append({"sh_space": round(p["nn_med"] / REF_NN, 4) if p["nn_med"] else None,
                    "sh_width": round(p["width_up"] / REF_W, 4) if p["width_up"] else None,
                    "n_contours": p["n_contours"]})
    return {"sh_space": sh_space, "err_space": err_of(sh_space, s),
            "sh_width": sh_width, "err_width": err_of(sh_width, s), "per_scene": per}

# ---------- old sets: guards fresh, MED3 from archive ----------
R["old"] = {}
base_cache = {"replication": rep}
for name, scenes in OLD.items():
    bases = base_cache.get(name) or load_bases(name, scenes)
    base_cache[name] = bases
    blk = {}
    for s in SCALES:
        imgs = scale_imgs(bases, s)
        gb = guard_block(imgs, s)
        arch = prev["datasets"][name]["results"][f"s={s}"]
        med_pooled = arch["pooled"]["med"]
        row = {"med": med_pooled, "errmed": arch["pooled"]["errmed"],
               "sh_marker": marker[f"s={s}"]["s_hat"],
               **{k: gb[k] for k in ("sh_space", "err_space", "sh_width", "err_width")},
               "D_marker": D_of(med_pooled, marker[f"s={s}"]["s_hat"]),
               "D_space": D_of(med_pooled, gb["sh_space"]),
               "D_width": D_of(med_pooled, gb["sh_width"]),
               "per_scene": []}
        for i, ps in enumerate(arch["per_scene"]):
            gscene = gb["per_scene"][i]
            row["per_scene"].append({
                "scene_seed": ps["scene_seed"], "med": ps["med"], "errmed": ps["errmed"],
                "sh_space": gscene["sh_space"], "sh_width": gscene["sh_width"],
                "err_space": err_of(gscene["sh_space"], s), "err_width": err_of(gscene["sh_width"], s),
                "D_marker": D_of(ps["med"], marker[f"s={s}"]["s_hat"]),
                "D_space": D_of(ps["med"], gscene["sh_space"]),
                "D_width": D_of(ps["med"], gscene["sh_width"])})
        blk[f"s={s}"] = row
        with open(PROG, "a") as f:
            f.write(json.dumps({"set": name, "s": s, "D_marker": row["D_marker"],
                                "D_space": row["D_space"], "errmed": row["errmed"]}) + "\n")
    R["old"][name] = blk
    print(f"[old:{name}] done", flush=True)

# ---------- new holdout3: full fresh run ----------
bases = load_bases("holdout3", NEW)
bases_objs = [objs for _, _, objs in bases]
n_objects = sum(len(o) for o in bases_objs)
det0 = ColorSegmentationDetector()
sanity = micro([score(det0.detect(im), objs, 1.0) for _, im, objs in bases])
ds = {"scenes": [s for s, _, _ in NEW], "n_objects": n_objects,
      "baseline_sanity": sanity, "results": {}}
print(f"[holdout3] n={n_objects} sanityF1={sanity['f1']}", flush=True)

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
    gb = guard_block(nat_imgs, s)
    per_scene = []
    for idx, im in enumerate(nat_imgs):
        e7 = estimate_from_areas(morph_areas(im, 7), REF7)
        e3 = estimate_from_areas(morph_areas(im, 3), REF3)
        er_ = estimate_from_areas(raw_areas(im), REFRAW)
        pm = med3v(e7["s_hat"], e3["s_hat"], er_["s_hat"])
        gscene = gb["per_scene"][idx]
        per_scene.append({"scene_seed": NEW[idx][0], "sh7": e7["s_hat"], "sh3": e3["s_hat"],
                          "shraw": er_["s_hat"], "med": pm, "errmed": err_of(pm, s),
                          "sh_space": gscene["sh_space"], "sh_width": gscene["sh_width"],
                          "err_space": err_of(gscene["sh_space"], s),
                          "err_width": err_of(gscene["sh_width"], s),
                          "D_marker": D_of(pm, marker[f"s={s}"]["s_hat"]),
                          "D_space": D_of(pm, gscene["sh_space"]),
                          "D_width": D_of(pm, gscene["sh_width"])})
    u_res = detect_U(natives)
    shats = {"B3": est3["s_hat"], "MED3": m_sh}
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
    for pol, sh in shats.items():
        rt = route_of(sh)
        deploy[pol] = p_f1(sh) if rt == "P" else u_res["f1"]
    # guarded MED3: if MARK-GUARD flags pooled, fall back to U
    d_mk = D_of(m_sh, marker[f"s={s}"]["s_hat"])
    flagged = d_mk is not None and abs(d_mk) > FLAG_THR
    deploy["MED3_GUARDED"] = u_res["f1"] if flagged else deploy["MED3"]
    ds["results"][f"s={s}"] = {
        "pooled": {"sh7": est7["s_hat"], "sh3": est3["s_hat"], "shraw": estraw["s_hat"],
                   "err7": err_of(est7["s_hat"], s), "err3": err_of(est3["s_hat"], s),
                   "errraw": err_of(estraw["s_hat"], s), "med": m_sh, "errmed": err_of(m_sh, s),
                   "sh_marker": marker[f"s={s}"]["s_hat"],
                   "sh_space": gb["sh_space"], "err_space": gb["err_space"],
                   "sh_width": gb["sh_width"], "err_width": gb["err_width"],
                   "D_marker": d_mk, "D_space": D_of(m_sh, gb["sh_space"]),
                   "D_width": D_of(m_sh, gb["sh_width"]), "marker_flag": flagged},
        "per_scene": per_scene, "U_f1": u_res["f1"],
        "deployment": {k: (round(v, 4) if v is not None else None) for k, v in deploy.items()},
        "oracle_route": oracle_route}
    with open(PROG, "a") as f:
        f.write(json.dumps({"set": "holdout3", "s": s, "med": m_sh,
                            "errmed": err_of(m_sh, s), "D_marker": d_mk}) + "\n")
    print(f"[holdout3] s={s} med={m_sh} errmed={err_of(m_sh, s)} Dmk={d_mk} flag={flagged}", flush=True)
loss = {}
for pol in ("B3", "MED3", "MED3_GUARDED"):
    loss[pol] = round(sum(ds["results"][f"s={s}"]["deployment"]["ORACLE"] -
                          ds["results"][f"s={s}"]["deployment"][pol] for s in SCALES), 4)
ds["summary"] = {"deployment_loss_vs_oracle": loss,
                 "pooled_bad_med3": sum(1 for s in SCALES
                                        if ds["results"][f"s={s}"]["pooled"]["errmed"] is not None
                                        and abs(ds["results"][f"s={s}"]["pooled"]["errmed"]) > BAD_ERR),
                 "marker_flags_pooled": sum(1 for s in SCALES if ds["results"][f"s={s}"]["pooled"]["marker_flag"])}
R["holdout3"] = ds
print(f"[holdout3] summary={ds['summary']}", flush=True)

# ---------- injection arm ----------
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
        gb = guard_block(imgs, s)
        row = {"med": m_sh, "errmed": err_of(m_sh, s),
               "sh7": est7["s_hat"], "sh3": est3["s_hat"], "shraw": estraw["s_hat"],
               "sh_marker": marker[f"s={s}"]["s_hat"], "sh_space": gb["sh_space"],
               "err_space": err_of(gb["sh_space"], s), "sh_width": gb["sh_width"],
               "err_width": err_of(gb["sh_width"], s),
               "D_marker": D_of(m_sh, marker[f"s={s}"]["s_hat"]),
               "D_space": D_of(m_sh, gb["sh_space"]), "D_width": D_of(m_sh, gb["sh_width"]),
               "n_objects_placed": sum(len(t["objects"]) for lst in inj_bases for gg, _, t in lst if gg == g)}
        inj[f"g={g}"][f"s={s}"] = row
        print(f"[inj] g={g} s={s} med={m_sh} errmed={row['errmed']} Dmk={row['D_marker']} Dsp={row['D_space']}", flush=True)
R["injection"] = inj

R["elapsed_sec"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print("ALL DONE", R["elapsed_sec"])
