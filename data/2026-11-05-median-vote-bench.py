"""Bloom-Counter three-estimator median vote bench (2026-11-05).

Follow-up to 2026-10-25 (s-estimation error chain) and 2026-10-29
(consistency guard). Pre-registration frozen in
data/2026-11-05-median-vote-prereg.md before this script was run.

Estimators (definitions and calibration refs unchanged from 2026-10-25):
  BLIND7   kernel-7 morphology + blind 2-means, ref 3806.0
  BLIND3   kernel-3 morphology + blind 2-means, ref 3740.0
  BLINDRAW raw petal-mask connected components (pixel areas) + blind
           2-means, ref 3718.5 (merged-reference calibration)
  MED3     median of the three s_hat values; if exactly one estimator
           produces no estimate, mean of the other two, flagged degraded;
           if none produce one, MED3 has no estimate.
Datasets: replication (101/202/303/404, 210 objects, in-sample check),
holdout1 (505/606/707/808, 203), holdout2 (909/1010/1111/1212, 209).
BLINDRAW has never been computed on the two holdout sets before.
Deployment: route by the policy's own s_hat (>=0.30 P with own-scaled
params, 0.15..0.30 U, <0.15 U+alert); policies ORACLE / B7 / B3 / RAW /
MED3. P is only executed when the policy's route is P.

Usage: .venv/bin/python 2026-11-05-median-vote-bench.py <repo> <out_json>
Progress is appended to <out_json>.progress.jsonl after every scale.
"""
import json, math, os, statistics, sys, time
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "median-vote-bench.json"
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_median_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
REF7, REF3, REFRAW = 3806.0, 3740.0, 3718.5
BAD_ERR = 0.10
DATASETS = {
    "replication": [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)],
    "holdout1": [(505, 33, 19), (606, 31, 17), (707, 38, 21), (808, 29, 15)],
    "holdout2": [(909, 34, 20), (1010, 30, 17), (1111, 37, 21), (1212, 32, 18)],
}
# Scene compositions copied verbatim from the original bench scripts:
# replication from 2026-10-25, holdout1 from 2026-10-29 (203 objects,
# 131 blooms / 72 buds), holdout2 from 2026-11-04 (209 objects).
# Replication check: pooled BLIND7/BLIND3 s_hat must match the stored
# benches scale by scale; any mismatch invalidates the run.

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

def med3(sh7, sh3, shraw):
    vals = [v for v in (sh7, sh3, shraw) if v is not None]
    if len(vals) == 3:
        m = statistics.median(vals)
        ident = "BLIND7" if m == sh7 else ("BLIND3" if m == sh3 else "BLINDRAW")
        return round(m, 4), ident, False
    if len(vals) == 2:
        return round(sum(vals) / 2.0, 4), "MEAN_OF_TWO", True
    return None, None, True

def detect_P(natives, true_s, s_used):
    mn = max(1, round(BASE_MIN * s_used * s_used))
    bm = max(1, round(BASE_BLOOM * s_used * s_used))
    k = odd_kernel(s_used)
    r = micro([score(detect_with(im, mn, bm, k), objs, true_s) for im, objs in natives])
    r["params"] = {"min_area": mn, "bloom_min": bm, "kernel": k}
    return r

def detect_U(natives, bases_objs):
    rows = []
    for (im, _), objs in zip(natives, bases_objs):
        up = cv2.resize(im, (1280, 960), interpolation=cv2.INTER_LINEAR)
        rows.append(score(detect_with(up, BASE_MIN, BASE_BLOOM, BASE_KERNEL), objs, 1.0))
    return micro(rows)

def route_of(s_val):
    if s_val is None:
        return "U_alert_fallback"
    if s_val >= 0.30:
        return "P"
    if s_val >= 0.15:
        return "U"
    return "U_alert"

def err_of(sh, s):
    return round(sh / s - 1.0, 4) if sh is not None else None

R = {"prereg": {"bad_err_threshold": BAD_ERR,
                "refs": {"morph7": REF7, "morph3": REF3, "raw": REFRAW},
                "doc": "data/2026-11-05-median-vote-prereg.md"},
     "scales": SCALES, "datasets": {}}
t0 = time.time()
for ds_name, scenes in DATASETS.items():
    bases = []
    for seed, nb, nd in scenes:
        p = os.path.join(WORK, f"{ds_name}_{seed}.jpg")
        truth = generate_image(p, nb, nd, seed=seed)
        bases.append((seed, cv2.imread(p), truth["objects"]))
    bases_objs = [objs for _, _, objs in bases]
    n_objects = sum(len(o) for _, _, o in bases)
    det0 = ColorSegmentationDetector()
    sanity = micro([score(det0.detect(im), objs, 1.0) for _, im, objs in bases])
    ds = {"scenes": [s for s, _, _ in scenes], "n_objects": n_objects,
          "baseline_sanity": sanity, "results": {}}
    print(f"[{ds_name}] n_objects={n_objects} sanityF1={sanity['f1']}", flush=True)
    for s in SCALES:
        w = int(round(1280 * s)); h = int(round(960 * s))
        natives = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA), scaled_objects(objs, s))
                   for _, im, objs in bases]
        nat_imgs = [im for im, _ in natives]
        # pooled estimates
        est7 = estimate_from_areas([a for im in nat_imgs for a in morph_areas(im, 7)], REF7)
        est3 = estimate_from_areas([a for im in nat_imgs for a in morph_areas(im, 3)], REF3)
        estraw = estimate_from_areas([a for im in nat_imgs for a in raw_areas(im)], REFRAW)
        m_sh, m_ident, m_deg = med3(est7["s_hat"], est3["s_hat"], estraw["s_hat"])
        # per-scene estimates
        per_scene = []
        for idx, im in enumerate(nat_imgs):
            e7 = estimate_from_areas(morph_areas(im, 7), REF7)
            e3 = estimate_from_areas(morph_areas(im, 3), REF3)
            er_ = estimate_from_areas(raw_areas(im), REFRAW)
            pm, pident, pdeg = med3(e7["s_hat"], e3["s_hat"], er_["s_hat"])
            per_scene.append({"scene_seed": scenes[idx][0],
                              "sh7": e7["s_hat"], "sh3": e3["s_hat"], "shraw": er_["s_hat"],
                              "err7": err_of(e7["s_hat"], s), "err3": err_of(e3["s_hat"], s),
                              "errraw": err_of(er_["s_hat"], s),
                              "med": pm, "med_ident": pident, "med_degraded": pdeg,
                              "errmed": err_of(pm, s)})
        # end-to-end (pooled): U once; P only for policies routed to P
        u_res = detect_U(natives, bases_objs)
        shats = {"B7": est7["s_hat"], "B3": est3["s_hat"], "RAW": estraw["s_hat"], "MED3": m_sh}
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
        ds["results"][f"s={s}"] = {
            "pooled": {"sh7": est7["s_hat"], "sh3": est3["s_hat"], "shraw": estraw["s_hat"],
                       "err7": err_of(est7["s_hat"], s), "err3": err_of(est3["s_hat"], s),
                       "errraw": err_of(estraw["s_hat"], s),
                       "med": m_sh, "med_ident": m_ident, "med_degraded": m_deg,
                       "errmed": err_of(m_sh, s),
                       "cl7": est7["cluster"], "cl3": est3["cluster"], "clraw": estraw["cluster"]},
            "per_scene": per_scene,
            "U_f1": u_res["f1"], "deployment": {k: round(v, 4) for k, v in deploy.items()},
            "oracle_route": oracle_route,
            "routes": {pol: route_of(sh) for pol, sh in shats.items()},
        }
        with open(PROG, "a") as f:
            f.write(json.dumps({"dataset": ds_name, "s": s,
                                "sh7": est7["s_hat"], "sh3": est3["s_hat"], "shraw": estraw["s_hat"],
                                "med": m_sh, "med_ident": m_ident,
                                "errmed": err_of(m_sh, s)}) + "\n")
        print(f"[{ds_name}] s={s}: sh7={est7['s_hat']} sh3={est3['s_hat']} raw={estraw['s_hat']} "
              f"med={m_sh}({m_ident}) errmed={err_of(m_sh, s)} oracleF1={oracle_f1} "
              f"MED3F1={deploy['MED3']} B3F1={deploy['B3']}", flush=True)
    # dataset summary
    summ = {}
    for pol in ("ORACLE", "B7", "B3", "RAW", "MED3"):
        f1s = [ds["results"][f"s={s}"]["deployment"][pol] for s in SCALES]
        losses = [round(ds["results"][f"s={s}"]["deployment"]["ORACLE"] - v, 4)
                  for s, v in zip(SCALES, f1s)]
        summ[pol] = {"total_loss_vs_oracle": round(sum(losses), 4),
                     "per_scale_f1": {f"s={s}": v for s, v in zip(SCALES, f1s)},
                     "per_scale_loss": {f"s={s}": x for s, x in zip(SCALES, losses)}}
    def badcount(key_err):
        return sum(1 for s in SCALES
                   if ds["results"][f"s={s}"]["pooled"][key_err] is not None
                   and abs(ds["results"][f"s={s}"]["pooled"][key_err]) > BAD_ERR)
    def alert_hits(pol_key):
        hits = 0
        for s in SCALES:
            if s >= 0.15:
                continue
            sh = {"B7": "sh7", "B3": "sh3", "RAW": "shraw", "MED3": "med"}[pol_key]
            v = ds["results"][f"s={s}"]["pooled"][sh]
            if v is not None and v < 0.15:
                hits += 1
        return hits
    ps_bad = {"B7": 0, "B3": 0, "RAW": 0, "MED3": 0, "n": 0}
    for s in SCALES:
        for ps in ds["results"][f"s={s}"]["per_scene"]:
            ps_bad["n"] += 1
            for pol, k in (("B7", "err7"), ("B3", "err3"), ("RAW", "errraw"), ("MED3", "errmed")):
                if ps[k] is None or abs(ps[k]) > BAD_ERR:
                    ps_bad[pol] += 1
    ds["summary"] = {"deployment": summ,
                     "pooled_bad": {"B7": badcount("err7"), "B3": badcount("err3"),
                                    "RAW": badcount("errraw"), "MED3": badcount("errmed")},
                     "alert_hits_of_3": {p: alert_hits(p) for p in ("B7", "B3", "RAW", "MED3")},
                     "per_scene_bad": ps_bad,
                     "med_ident_pooled": {f"s={s}": ds["results"][f"s={s}"]["pooled"]["med_ident"]
                                          for s in SCALES}}
    R["datasets"][ds_name] = ds
    print(f"[{ds_name}] done: pooled_bad={ds['summary']['pooled_bad']} "
          f"alert={ds['summary']['alert_hits_of_3']} per_scene_bad={ps_bad}", flush=True)

R["elapsed_sec"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print("ALL DONE", json.dumps({k: v["summary"]["pooled_bad"] for k, v in R["datasets"].items()}))
