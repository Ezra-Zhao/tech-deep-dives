"""Bloom-Counter s-estimation end-to-end error chain bench (2026-10-25).

Follow-up to 2026-10-20 (calibration drift) and 2026-10-24 (resampling
vs param scaling). The 2026-10-20 article proposed, but never validated,
a field estimator: measure the median bloom contour area in a few frames
at a new camera position, divide by the baseline median (3806 px^2) and
take the square root to get s_hat, then scale all parameters by s_hat.
The 2026-10-24 article added a route rule that also consumes s:
  s >= 0.30 -> P route (native frame + scaled params, cheap)
  0.15 <= s < 0.30 -> U route (upsample to baseline size, fixed params)
  s < 0.15 -> alert "move closer", U as best effort
This bench measures the whole chain:
  (1) estimator bias: s_hat vs true s for four estimators (below);
  (2) downstream tolerance: P-route F1 vs imposed multiplicative error
      in the s used for scaling (sweep, estimator-independent);
  (3) end-to-end: P-route F1 with each estimator's s_hat vs oracle s;
  (4) route selection: chosen route and its F1 under each s_hat vs the
      route chosen with the true s.

Estimators (calibration refs are GT-matched medians on the baseline
frames, one per measurement pipeline, computed in this script):
  ORA7    GT-matched contours after baseline morphology (kernel 7),
          contourArea -- the 2026-10-20 drift-measurement method.
          Not field-deployable (needs labels); upper bound.
  BLIND7  same pipeline as ORA7 (kernel 7) but the bloom class is found
          blind: 1-D 2-means clustering on log contour areas, upper
          cluster median. This is the proposal implemented verbatim
          with the detector's own measurement code.
  BLIND3  same, but morphology kernel 3 (minimal closing/opening).
  BLINDRAW raw petal-mask connected components, pixel-count areas,
          no morphology at all; blind 2-means on log areas. Its
          calibration ref is the GT-matched *merged* pixel area per
          bloom (components assigned to a bloom summed), because a
          bloom's raw mask can be several components.
Guard (pre-registered before end-to-end scoring): a blind estimate is
trusted only if the two clusters are separated, ln(upper_median /
lower_median) >= 0.8. Otherwise the estimator is recorded as REFUSED.

Scoring identical to 2026-10-17/20/24: greedy centre matching, label
must match, tol = max(38*g, 1.1*r) in fed-image coordinates.

Usage: .venv/bin/python 2026-10-25-bloom-s-estimation-bench.py <repo> <out_json>
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "bloom-s-estimation-bench.json"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_s_est_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
SWEEP_F = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6]
GUARD_SEP = 0.8


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


# ---------- measurement pipelines ----------
def morph_contours(image, kernel_size):
    """[(contourArea, cx, cy)] after CLOSE+OPEN with kernel_size."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        out.append((float(cv2.contourArea(cnt)), x + w / 2.0, y + h / 2.0))
    return out


def raw_components(image):
    """[(pixel_area, cx, cy)] of raw petal-mask connected components."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    return [(float(stats[i][4]), float(cents[i][0]), float(cents[i][1])) for i in range(1, n)]


def blind_cluster(areas):
    """1-D 2-means on log areas (init: 25th/75th percentiles).
    Returns dict with upper/lower medians (raw area), sizes, separation."""
    a = np.array(sorted(x for x in areas if x > 0), dtype=float)
    if len(a) < 8:
        return None
    la = np.log(a)
    c = np.array([np.percentile(la, 25), np.percentile(la, 75)])
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
            "n_upper": int(len(hi)), "n_lower": int(len(lo)),
            "separation_log": round(math.log(med_hi / med_lo), 3) if med_lo > 0 else None}


def estimate(areas, ref):
    cl = blind_cluster(areas)
    if cl is None or not ref:
        return {"s_hat": None, "cluster": cl, "guard_pass": False}
    return {"s_hat": round(math.sqrt(cl["upper_median"] / ref), 4),
            "cluster": cl,
            "guard_pass": bool(cl["separation_log"] is not None and cl["separation_log"] >= GUARD_SEP)}


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


# ---------- base scenes ----------
bases = []
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    bases.append((seed, cv2.imread(p), truth["objects"]))
bases_objs = [objs for _, _, objs in bases]

R = {"detector": "color-segmentation-v0.1",
     "base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM, "morph_kernel": BASE_KERNEL},
     "n_scenes": len(bases), "n_objects": sum(len(o) for _, _, o in bases),
     "scales": SCALES, "sweep_factors": SWEEP_F, "guard_separation_log_min": GUARD_SEP,
     "route_rule": "P if s>=0.30; U if 0.15<=s<0.30; U+alert if s<0.15",
     "scoring": "greedy centre matching, label must match, tol=max(38*geom_scale, 1.1*r)"}

base_det = ColorSegmentationDetector()
R["baseline_sanity"] = micro([score(base_det.detect(im), objs, 1.0) for _, im, objs in bases])

# calibration references (GT-matched, baseline frames, matched frame by frame)
def calib_ref(fn, merge=False):
    meds_all = []
    for _, im, objs in bases:
        items = fn(im)
        used = set(); vals = []
        for o in objs:
            if o["label"] != "bloom":
                continue
            tol = max(38.0, o["r"] * 1.1)
            if merge:
                tot = 0.0; got = False
                for i, (a, cx, cy) in enumerate(items):
                    if i in used:
                        continue
                    if math.hypot(cx - o["cx"], cy - o["cy"]) <= tol:
                        used.add(i); tot += a; got = True
                if got:
                    vals.append(tot)
            else:
                best, bd = None, 1e9
                for i, (a, cx, cy) in enumerate(items):
                    if i in used:
                        continue
                    d = math.hypot(cx - o["cx"], cy - o["cy"])
                    if d < bd:
                        bd, best = d, i
                if best is not None and bd <= tol:
                    used.add(best); vals.append(items[best][0])
        meds_all += vals
    return round(float(np.median(meds_all)), 1), len(meds_all)

REF7, _ = calib_ref(lambda im: morph_contours(im, 7))
REF3, _ = calib_ref(lambda im: morph_contours(im, 3))
REFRAW, _ = calib_ref(raw_components, merge=True)
R["calibration_refs_median_bloom_area"] = {"morph7_contourArea": REF7, "morph3_contourArea": REF3,
                                           "raw_merged_pixel_area": REFRAW}
print("refs:", R["calibration_refs_median_bloom_area"], flush=True)

R["results"] = {}
for s in SCALES:
    w = int(round(1280 * s)); h = int(round(960 * s))
    natives = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA), scaled_objects(objs, s))
               for _, im, objs in bases]
    nat_imgs = [im for im, _ in natives]
    nat_objs = [objs for _, objs in natives]
    entry = {"native_size": [w, h]}

    # --- estimators, pooled and per-scene ---
    est = {}
    # ORA7 pooled
    ora_vals = []
    for im, objs in natives:
        items = morph_contours(im, 7)
        used = set()
        for o in objs:
            if o["label"] != "bloom":
                continue
            tol = max(38.0 * s, o["r"] * 1.1)
            best, bd = None, 1e9
            for i, (a, cx, cy) in enumerate(items):
                if i in used:
                    continue
                d = math.hypot(cx - o["cx"], cy - o["cy"])
                if d < bd:
                    bd, best = d, i
            if best is not None and bd <= tol:
                used.add(best); ora_vals.append(items[best][0])
    ora_med = float(np.median(ora_vals)) if ora_vals else None
    est["ORA7"] = {"s_hat": round(math.sqrt(ora_med / REF7), 4) if ora_med else None,
                   "median_area": round(ora_med, 1) if ora_med else None,
                   "n_matched_blooms": len(ora_vals),
                   "err_pct": round(100 * (math.sqrt(ora_med / REF7) / s - 1), 2) if ora_med else None}
    pipes = {"BLIND7": (lambda im: [a for a, _, _ in morph_contours(im, 7)], REF7),
             "BLIND3": (lambda im: [a for a, _, _ in morph_contours(im, 3)], REF3),
             "BLINDRAW": (lambda im: [a for a, _, _ in raw_components(im)], REFRAW)}
    for name, (fn, ref) in pipes.items():
        pooled = [a for im in nat_imgs for a in fn(im)]
        e = estimate(pooled, ref)
        e["err_pct"] = round(100 * (e["s_hat"] / s - 1), 2) if e["s_hat"] else None
        per_scene = []
        for im in nat_imgs:
            es = estimate(fn(im), ref)
            per_scene.append(es["s_hat"])
        e["per_scene_s_hat"] = per_scene
        if per_scene and all(v is not None for v in per_scene):
            e["per_scene_err_pct_range"] = [round(100 * (min(per_scene) / s - 1), 2),
                                            round(100 * (max(per_scene) / s - 1), 2)]
        est[name] = e
    entry["estimators"] = est

    # --- downstream tolerance sweep (P route, imposed error factor) ---
    sweep = {}
    for f in SWEEP_F:
        r = detect_P(natives, s, s * f)
        sweep[f"x{f}"] = {"f1": r["f1"], "bud_recall": r["bud_recall"], "bloom_recall": r["bloom_recall"],
                          "count_err_pct": r["count_err_pct"], "kernel": r["params"]["kernel"]}
    entry["P_sweep"] = sweep

    # --- end-to-end P with each estimator ---
    e2e = {"ORACLE": detect_P(natives, s, s)}
    for name in ("ORA7", "BLIND7", "BLIND3", "BLINDRAW"):
        sh = est[name]["s_hat"]
        if sh:
            r = detect_P(natives, s, sh)
            e2e[name] = {"f1": r["f1"], "bud_recall": r["bud_recall"], "bloom_recall": r["bloom_recall"],
                         "count_err_pct": r["count_err_pct"], "params": r["params"],
                         "delta_f1_vs_oracle": round(r["f1"] - e2e["ORACLE"]["f1"], 4)}
        else:
            e2e[name] = None
    entry["P_end_to_end"] = {k: (v if k == "ORACLE" else v) for k, v in e2e.items()}

    # --- route selection ---
    u_res = detect_U(natives, bases_objs)
    p_res = e2e["ORACLE"]
    routes = {}
    oracle_route = route_of(s)
    routes["ORACLE"] = {"route": oracle_route,
                        "f1": (p_res["f1"] if oracle_route == "P" else u_res["f1"])}
    for name in ("ORA7", "BLIND7", "BLIND3", "BLINDRAW"):
        sh = est[name]["s_hat"]
        rt = route_of(sh)
        # A system that picks the P route with s_hat also runs P with
        # s_hat-scaled params, so the deployed F1 of a P choice is this
        # estimator's own end-to-end P result, not the oracle's.
        own_p_f1 = e2e[name]["f1"] if e2e.get(name) else None
        routes[name] = {"route": rt, "s_hat": sh,
                        "f1": (own_p_f1 if rt == "P" else u_res["f1"]),
                        "agrees_with_oracle": rt == oracle_route or (rt.startswith("U") and oracle_route.startswith("U"))}
        # guarded variant: refused -> default U
        if name.startswith("BLIND"):
            if est[name].get("guard_pass"):
                grt = rt
                gf1 = own_p_f1 if grt == "P" else u_res["f1"]
            else:
                grt = "U_guarded_fallback"
                gf1 = u_res["f1"]
            routes[name + "_GUARDED"] = {"route": grt, "f1": gf1}
    entry["U_LINEAR"] = {"f1": u_res["f1"], "bud_recall": u_res["bud_recall"],
                         "bloom_recall": u_res["bloom_recall"], "count_err_pct": u_res["count_err_pct"]}
    entry["route_selection"] = routes
    R["results"][f"s={s}"] = entry
    print(f"s={s}: ORA7={est['ORA7']['s_hat']} B7={est['BLIND7']['s_hat']}(g={est['BLIND7']['guard_pass']}) "
          f"B3={est['BLIND3']['s_hat']}(g={est['BLIND3']['guard_pass']}) RAW={est['BLINDRAW']['s_hat']}(g={est['BLINDRAW']['guard_pass']}) "
          f"P_oracle={p_res['f1']} U={u_res['f1']}", flush=True)

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print(json.dumps({"baseline": R["baseline_sanity"], "refs": R["calibration_refs_median_bloom_area"]}, indent=2))
