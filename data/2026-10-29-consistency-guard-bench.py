"""Bloom-Counter multi-estimator consistency guard bench (2026-10-29).

Follow-up to 2026-10-25 (s-estimation error chain). That bench found a
candidate signal it did not validate as a guard: the pooled divergence
between the BLIND7 and BLIND3 estimates was <=0.4% on every healthy
scale and +17%..+24% across the BLIND7 failure band (+80%/+171% at the
extreme scales). This bench tests that signal as a pre-registered guard.

Pre-registration (frozen in 2026-10-29-consistency-guard-prereg.md
before this script was run; thresholds derive only from the published
2026-10-25 pooled signal):
  BAD label (evaluator truth): |s_hat7 / s - 1| > 10%.
  CONS : reject BLIND7 if |s_hat7 / s_hat3 - 1| > 5%.
  SEP  : reject BLIND7 if BLIND7 cluster separation < 0.8 (2026-10-25 value).
  COUNT: reject BLIND7 if n7 < (2/3) * n_base, n_base = BLIND7 contour
         count of the same scene set at s=1 (per-scene: that scene's).
  Combos: OR (any rejects) and AND (all reject) over the three guards.
Deployment (pooled only): a rejected estimate falls back to the U route
(same convention as the 2026-10-25 guarded variant). Extra references:
CONS+RESCUE (on CONS rejection, route/run P with s_hat3) and ALWAYS-B3
(route/run P with s_hat3 throughout).
Datasets: replication = original scenes (101/202/303/404, 210 objects);
holdout = new scenes (505/606/707/808, 203 objects), calibration refs
unchanged (3806.0 / 3740.0). Scales identical to 2026-10-25.

Usage: .venv/bin/python 2026-10-29-consistency-guard-bench.py <repo> <out_json>
"""
import json, math, os, sys, time
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "consistency-guard-bench.json"
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_guard_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.07]
REF7, REF3 = 3806.0, 3740.0
BAD_ERR = 0.10
CONS_THR = 0.05
SEP_THR = 0.8
COUNT_FRAC = 2.0 / 3.0
DATASETS = {
    "replication": [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)],
    "holdout": [(505, 33, 19), (606, 31, 17), (707, 38, 21), (808, 29, 15)],
}


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


def guard_decisions(est7, est3, n_base):
    """est7/est3: estimate dicts. Returns per-guard reject booleans."""
    sh7, sh3 = est7["s_hat"], est3["s_hat"]
    cl7 = est7["cluster"]
    if sh7 is None or cl7 is None:
        return {"CONS": True, "SEP": True, "COUNT": True, "divergence": None,
                "note": "BLIND7 produced no estimate; all guards treat as reject"}
    div = (sh7 / sh3 - 1.0) if sh3 else None
    return {
        "CONS": bool(div is None or abs(div) > CONS_THR),
        "SEP": bool(cl7["separation_log"] is None or cl7["separation_log"] < SEP_THR),
        "COUNT": bool(cl7["n_total"] < COUNT_FRAC * n_base),
        "divergence": round(div, 4) if div is not None else None,
    }


def guard_metrics(rows):
    """rows: list of {bad: bool, rejects: {guard: bool}} -> per-guard confusion."""
    guards = list(rows[0]["rejects"].keys()) if rows else []
    out = {}
    for g in guards:
        tp = sum(1 for r in rows if r["rejects"][g] and r["bad"])
        fp = sum(1 for r in rows if r["rejects"][g] and not r["bad"])
        fn = sum(1 for r in rows if not r["rejects"][g] and r["bad"])
        tn = sum(1 for r in rows if not r["rejects"][g] and not r["bad"])
        out[g] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                  "accuracy": round((tp + tn) / max(1, tp + fp + fn + tn), 4),
                  "sensitivity_bad_recall": round(tp / max(1, tp + fn), 4) if (tp + fn) else None,
                  "specificity": round(tn / max(1, tn + fp), 4) if (tn + fp) else None,
                  "reject_precision": round(tp / max(1, tp + fp), 4) if (tp + fp) else None}
    return out


COMBOS = {
    "CONS": lambda d: d["CONS"],
    "SEP": lambda d: d["SEP"],
    "COUNT": lambda d: d["COUNT"],
    "CONS_or_SEP": lambda d: d["CONS"] or d["SEP"],
    "CONS_or_COUNT": lambda d: d["CONS"] or d["COUNT"],
    "SEP_or_COUNT": lambda d: d["SEP"] or d["COUNT"],
    "ANY_OR": lambda d: d["CONS"] or d["SEP"] or d["COUNT"],
    "CONS_and_SEP": lambda d: d["CONS"] and d["SEP"],
    "CONS_and_COUNT": lambda d: d["CONS"] and d["COUNT"],
    "ALL_AND": lambda d: d["CONS"] and d["SEP"] and d["COUNT"],
}

R = {"prereg": {"bad_err_threshold": BAD_ERR, "cons_threshold": CONS_THR,
                "sep_threshold": SEP_THR, "count_fraction": COUNT_FRAC,
                "refs": {"morph7": REF7, "morph3": REF3},
                "doc": "data/2026-10-29-consistency-guard-prereg.md"},
     "scales": SCALES,
     "datasets": {}}

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
    # n_base: BLIND7 contour count at s=1, pooled and per scene
    base_counts = [len(morph_areas(im, 7)) for _, im, _ in bases]
    n_base_pooled = sum(base_counts)
    ds = {"scenes": [s for s, _, _ in scenes], "n_objects": n_objects,
          "baseline_sanity": sanity, "n_base_pooled": n_base_pooled,
          "n_base_per_scene": base_counts, "results": {}}
    pooled_rows, scene_rows = [], []
    deploy = {}  # scale -> {policy: f1}
    for s in SCALES:
        w = int(round(1280 * s)); h = int(round(960 * s))
        natives = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA), scaled_objects(objs, s))
                   for _, im, objs in bases]
        nat_imgs = [im for im, _ in natives]
        # pooled estimates
        est7 = estimate_from_areas([a for im in nat_imgs for a in morph_areas(im, 7)], REF7)
        est3 = estimate_from_areas([a for im in nat_imgs for a in morph_areas(im, 3)], REF3)
        dec = guard_decisions(est7, est3, n_base_pooled)
        err7 = round(est7["s_hat"] / s - 1.0, 4) if est7["s_hat"] else None
        err3 = round(est3["s_hat"] / s - 1.0, 4) if est3["s_hat"] else None
        bad = bool(err7 is not None and abs(err7) > BAD_ERR)
        rejects = {name: bool(fn(dec)) for name, fn in COMBOS.items()}
        pooled_rows.append({"bad": bad, "rejects": rejects})
        # per-scene estimates
        per_scene = []
        for idx, im in enumerate(nat_imgs):
            e7 = estimate_from_areas(morph_areas(im, 7), REF7)
            e3 = estimate_from_areas(morph_areas(im, 3), REF3)
            d = guard_decisions(e7, e3, base_counts[idx])
            er = round(e7["s_hat"] / s - 1.0, 4) if e7["s_hat"] else None
            b = bool(er is not None and abs(er) > BAD_ERR) if er is not None else True
            rj = {name: bool(fn(d)) for name, fn in COMBOS.items()}
            scene_rows.append({"bad": b, "rejects": rj})
            per_scene.append({"scene_seed": scenes[idx][0], "s_hat7": e7["s_hat"], "s_hat3": e3["s_hat"],
                              "err7": er, "bad": b, "divergence": d["divergence"],
                              "sep7": e7["cluster"]["separation_log"] if e7["cluster"] else None,
                              "n7": e7["cluster"]["n_total"] if e7["cluster"] else 0,
                              "rejects": rj})
        # end-to-end (pooled): oracle / unguarded / U / P with each estimate
        u_res = detect_U(natives, bases_objs)
        p_oracle = detect_P(natives, s, s)
        p_b7 = detect_P(natives, s, est7["s_hat"]) if est7["s_hat"] else None
        p_b3 = detect_P(natives, s, est3["s_hat"]) if est3["s_hat"] else None
        oracle_route = route_of(s)
        oracle_f1 = p_oracle["f1"] if oracle_route == "P" else u_res["f1"]

        def deployed(route_owner_shat, p_res):
            rt = route_of(route_owner_shat)
            return (p_res["f1"] if rt == "P" else u_res["f1"]) if p_res else u_res["f1"]

        pol = {"ORACLE": oracle_f1, "U_ONLY": u_res["f1"],
               "UNGUARDED_B7": deployed(est7["s_hat"], p_b7),
               "ALWAYS_B3": deployed(est3["s_hat"], p_b3)}
        for name in COMBOS:
            pol["G_" + name + "_Ufb"] = u_res["f1"] if rejects[name] else pol["UNGUARDED_B7"]
        pol["CONS_RESCUE"] = deployed(est3["s_hat"], p_b3) if rejects["CONS"] else pol["UNGUARDED_B7"]
        deploy[f"s={s}"] = {k: round(v, 4) for k, v in pol.items()}
        ds["results"][f"s={s}"] = {
            "estimators_pooled": {"BLIND7": est7, "BLIND3": est3, "err7": err7, "err3": err3,
                                  "bad": bad, "divergence": dec["divergence"], "rejects": rejects},
            "per_scene": per_scene,
            "P_oracle_f1": p_oracle["f1"], "P_b7_f1": p_b7["f1"] if p_b7 else None,
            "P_b3_f1": p_b3["f1"] if p_b3 else None, "U_f1": u_res["f1"],
            "deployment": deploy[f"s={s}"],
        }
        with open(PROG, "a") as f:
            f.write(json.dumps({"dataset": ds_name, "s": s, "err7": err7, "err3": err3,
                                "div": dec["divergence"], "bad": bad, "rejects": rejects}) + "\n")
        print(f"[{ds_name}] s={s}: sh7={est7['s_hat']} sh3={est3['s_hat']} div={dec['divergence']} "
              f"bad={bad} CONS_rej={rejects['CONS']} SEP_rej={rejects['SEP']} COUNT_rej={rejects['COUNT']} "
              f"oracleF1={oracle_f1} ung={pol['UNGUARDED_B7']} U={u_res['f1']}", flush=True)
    ds["guard_metrics_pooled"] = guard_metrics(pooled_rows)
    ds["guard_metrics_per_scene"] = guard_metrics(scene_rows)
    # deployment summary
    policies = list(deploy[f"s={SCALES[0]}"].keys())
    summ = {}
    for pol_name in policies:
        f1s = [deploy[f"s={s}"][pol_name] for s in SCALES]
        losses = [round(deploy[f"s={s}"]["ORACLE"] - v, 4) for s, v in zip(SCALES, f1s)]
        summ[pol_name] = {"mean_f1": round(sum(f1s) / len(f1s), 4),
                          "total_loss_vs_oracle": round(sum(losses), 4),
                          "scales_with_loss_gt_0.01": sum(1 for x in losses if x > 0.01),
                          "worst_loss": round(max(losses), 4),
                          "per_scale_f1": {f"s={s}": v for s, v in zip(SCALES, f1s)},
                          "per_scale_loss": {f"s={s}": x for s, x in zip(SCALES, losses)}}
    ds["deployment_summary"] = summ
    R["datasets"][ds_name] = ds
    print(f"[{ds_name}] done: sanity F1={sanity['f1']} n_base={n_base_pooled} "
          f"metrics_pooled={json.dumps(ds['guard_metrics_pooled'].get('CONS'))}", flush=True)

R["elapsed_sec"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print(json.dumps({k: {"pooled_CONS": v["guard_metrics_pooled"]["CONS"],
                      "perscene_CONS": v["guard_metrics_per_scene"]["CONS"],
                      "deploy_UNGUARDED": v["deployment_summary"]["UNGUARDED_B7"],
                      "deploy_CONS_Ufb": v["deployment_summary"]["G_CONS_Ufb"]}
                  for k, v in R["datasets"].items()}, indent=2, ensure_ascii=False))
