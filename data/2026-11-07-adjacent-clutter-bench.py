"""Adjacent / overlapping clutter bench (2026-11-07).

Fulfils the 2026-10-30 limitation: clutter was planted >=20 px away from
any true flower there, so recall stayed 1.000. This bench plants one
petal-coloured disc (r=12) per host target at signed edge-to-edge gaps
{-18..35} px and measures contour merging, host outcome
(correct/migrated/lost) and the role of the closing kernel.

Design frozen in data/2026-11-07-adjacent-clutter-prereg.md.
Usage: .venv/bin/python 2026-11-07-adjacent-clutter-bench.py <repo> <out_json>
Progress appended to <out_json>.progress.jsonl.
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "2026-11-07-adjacent-clutter-bench.json"
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_adj_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]
GAPS = [-18, -8, -3, 0, 2, 4, 6, 8, 12, 20, 35]
RC = 12
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
COLORS = [(147, 20, 255), (245, 245, 245), (0, 215, 255)]  # pink white yellow BGR
W0, H0 = 1280, 960
MAX_HOSTS = 28


def log(obj):
    with open(PROG, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def overlap_area(r1, r2, d):
    """Analytic circle-circle overlap area."""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2
    a1 = r1 * r1 * math.acos(max(-1, min(1, (d * d + r1 * r1 - r2 * r2) / (2 * d * r1))))
    a2 = r2 * r2 * math.acos(max(-1, min(1, (d * d + r2 * r2 - r1 * r1) / (2 * d * r2))))
    a3 = 0.5 * math.sqrt(max(0.0, (-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2)))
    return a1 + a2 - a3


def choose_hosts(objects):
    """Return host list with a planting direction each (see prereg)."""
    cands = []
    for idx, o in enumerate(objects):
        best = None  # (clearance, angle)
        for k in range(16):
            ang = 2 * math.pi * k / 16
            # clutter centre at the largest gap along this direction
            cx = o["cx"] + (o["r"] + RC + 35) * math.cos(ang)
            cy = o["cy"] + (o["r"] + RC + 35) * math.sin(ang)
            if not (RC + 4 <= cx <= W0 - RC - 4 and RC + 4 <= cy <= H0 - RC - 4):
                continue
            clearance = min(
                math.hypot(cx - p["cx"], cy - p["cy"]) - p["r"] - RC
                for j, p in enumerate(objects) if j != idx)
            if clearance < 6:
                continue
            if best is None or clearance > best[0]:
                best = (clearance, ang)
        if best is not None:
            cands.append((idx, best[1]))
    # interleave bloom / bud to keep class balance
    blooms = [c for c in cands if objects[c[0]]["label"] == "bloom"]
    buds = [c for c in cands if objects[c[0]]["label"] == "bud"]
    hosts = []
    bi = di = 0
    while len(hosts) < MAX_HOSTS and (bi < len(blooms) or di < len(buds)):
        if bi < len(blooms):
            hosts.append(blooms[bi]); bi += 1
        if len(hosts) >= MAX_HOSTS:
            break
        if di < len(buds):
            hosts.append(buds[di]); di += 1
    return hosts


def contours_of(image, close_k, open_k):
    """Detector-identical mask pipeline with separable close/open kernels.
    close_k=None means no closing. Returns list of (contour, area)."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    m = ColorSegmentationDetector._petal_mask(hsv)
    if close_k:
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
    if open_k:
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [(c, float(cv2.contourArea(c))) for c in cnts]


def host_outcome(contours, host, clutter_xy):
    """Contour-method outcome for one host (see prereg)."""
    hx, hy = host["cx"], host["cy"]
    hit = None
    for c, a in contours:
        if a < BASE_MIN:
            continue
        if cv2.pointPolygonTest(c, (float(hx), float(hy)), False) >= 0:
            hit = (c, a)
            break
    if hit is None:
        return {"outcome": "lost", "merged": False, "area": None}
    c, a = hit
    merged = cv2.pointPolygonTest(c, (float(clutter_xy[0]), float(clutter_xy[1])), False) >= 0
    label = "bloom" if a >= BASE_BLOOM else "bud"
    return {"outcome": "correct" if label == host["label"] else "migrated",
            "merged": bool(merged), "area": round(a, 1)}


def score_scene(dets, objects):
    """Series-standard greedy centre matching, label must match."""
    used = set(); tp = 0
    per = {"bloom": 0, "bud": 0}
    for d in dets:
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if i in used or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None and bd <= max(38.0, objects[best]["r"] * 1.1):
            used.add(best); tp += 1; per[d.label] += 1
    fp = len(dets) - tp
    fn = len(objects) - tp
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / len(objects) if objects else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "det_total": len(dets)}


def agg_hosts(rows):
    n = len(rows)
    out = {"n": n}
    for key in ("merged",):
        out[key + "_rate"] = round(sum(1 for r in rows if r[key]) / n, 4) if n else None
    for oc in ("correct", "migrated", "lost"):
        out[oc] = sum(1 for r in rows if r["outcome"] == oc)
        out[oc + "_rate"] = round(out[oc] / n, 4) if n else None
    areas = [r["area"] for r in rows if r["area"] is not None]
    out["median_area"] = round(float(np.median(areas)), 1) if areas else None
    return out


# ---------- bases & hosts ----------
bases = []
host_report = {}
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    img = cv2.imread(p)
    objs = truth["objects"]
    hosts = choose_hosts(objs)
    bases.append((seed, img, objs, hosts))
    host_report[str(seed)] = {
        "hosts": len(hosts),
        "bloom": sum(1 for i, _ in hosts if objs[i]["label"] == "bloom"),
        "bud": sum(1 for i, _ in hosts if objs[i]["label"] == "bud"),
        "eligible_total": len(hosts)}
    log({"stage": "hosts", "seed": seed, **host_report[str(seed)]})

R = {"detector": "color-segmentation-v0.1",
     "base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM, "morph_kernel": BASE_KERNEL},
     "gaps": GAPS, "clutter_r": RC, "host_report": host_report,
     "prereg": "data/2026-11-07-adjacent-clutter-prereg.md",
     "main": {}, "close_arm": {}, "det_kernel_arm": {}, "clean": {}}

det = ColorSegmentationDetector()
# clean baseline per scene (no clutter): detector + host-alone contour areas (k7)
clean_rows = []
host_alone_area = {}  # (seed, host_idx) -> contour area containing host, clean image
for seed, img, objs, hosts in bases:
    clean_rows.append(score_scene(det.detect(img), objs))
    cnts = contours_of(img, BASE_KERNEL, BASE_KERNEL)
    for hi, _ang in hosts:
        o = objs[hi]
        a = None
        for c, ar in cnts:
            if ar >= BASE_MIN and cv2.pointPolygonTest(c, (float(o["cx"]), float(o["cy"])), False) >= 0:
                a = ar; break
        host_alone_area[(seed, hi)] = a
R["clean"] = {"pooled": {
    "tp": sum(r["tp"] for r in clean_rows), "fp": sum(r["fp"] for r in clean_rows),
    "fn": sum(r["fn"] for r in clean_rows),
    "recall": round(sum(r["tp"] for r in clean_rows) /
                      sum(r["tp"] + r["fn"] for r in clean_rows), 4)}}
# clutter alone reference area: disc on bare foliage is not available; use
# mask area of an isolated disc planted far from everything in scene 101 copy
# (measured once, k7 pipeline).
_ref_img = bases[0][1].copy()
cv2.circle(_ref_img, (60, 60), RC, COLORS[0], -1)
_ref = [a for c, a in contours_of(_ref_img, BASE_KERNEL, BASE_KERNEL)
        if cv2.pointPolygonTest(c, (60.0, 60.0), False) >= 0]
R["clutter_alone_area_k7"] = round(_ref[0], 1) if _ref else None
log({"stage": "clean", **R["clean"]["pooled"], "clutter_alone": R["clutter_alone_area_k7"]})

CLOSE_KS = [None, 3, 7, 11, 15]
for gap in GAPS:
    main_rows, bloom_rows, bud_rows = [], [], []
    nonhost_stats = []
    scene_scores = []
    close_merge = {("none" if k is None else str(k)): [] for k in CLOSE_KS}
    detk_rows = {"3": [], "11": []}
    area_pairs = []  # (merged_area, host_alone + clutter_alone - overlap_contour_est)
    ci = 0
    for seed, img, objs, hosts in bases:
        cimg = img.copy()
        placements = []
        for hi, ang in hosts:
            o = objs[hi]
            d = o["r"] + RC + gap
            cx = int(round(o["cx"] + d * math.cos(ang)))
            cy = int(round(o["cy"] + d * math.sin(ang)))
            cv2.circle(cimg, (cx, cy), RC, COLORS[ci % 3], -1); ci += 1
            placements.append((hi, (cx, cy), d))
        # main arm
        cnts7 = contours_of(cimg, BASE_KERNEL, BASE_KERNEL)
        dets = det.detect(cimg)
        scene_scores.append(score_scene(dets, objs))
        host_idx_set = {hi for hi, _ in hosts}
        for hi, cxy, d in placements:
            o = objs[hi]
            r = host_outcome(cnts7, o, cxy)
            r["label"] = o["label"]
            r["overlap_frac"] = round(overlap_area(o["r"], RC, d) / (math.pi * o["r"] ** 2), 4)
            main_rows.append(r)
            (bloom_rows if o["label"] == "bloom" else bud_rows).append(r)
            if r["merged"] and r["area"] is not None:
                alone = host_alone_area.get((seed, hi))
                if alone is not None and R["clutter_alone_area_k7"]:
                    pred = alone + R["clutter_alone_area_k7"] - overlap_area(
                        math.sqrt(alone / math.pi), math.sqrt(R["clutter_alone_area_k7"] / math.pi), d)
                    area_pairs.append((r["area"], pred))
        # non-host recall for this scene
        nh_tp = 0; nh_tot = 0
        used = set()
        for dd in dets:
            best, bd = None, 1e9
            for i, o in enumerate(objs):
                if i in used or i in host_idx_set or o["label"] != dd.label:
                    continue
                dist = math.hypot(dd.cx - o["cx"], dd.cy - o["cy"])
                if dist < bd:
                    bd, best = dist, i
            if best is not None and bd <= max(38.0, objs[best]["r"] * 1.1):
                used.add(best); nh_tp += 1
        nh_tot = len(objs) - len(hosts)
        nonhost_stats.append((nh_tp, nh_tot))
        # close-only arm merge rates
        for k in CLOSE_KS:
            cnts = contours_of(cimg, k, BASE_KERNEL)
            key = "none" if k is None else str(k)
            for hi, cxy, d in placements:
                o = objs[hi]
                merged = False
                for c, a in cnts:
                    if a < BASE_MIN:
                        continue
                    if cv2.pointPolygonTest(c, (float(o["cx"]), float(o["cy"])), False) >= 0:
                        merged = cv2.pointPolygonTest(c, (float(cxy[0]), float(cxy[1])), False) >= 0
                        break
                close_merge[key].append(bool(merged))
        # detector whole-kernel arm
        for kk in ("3", "11"):
            dk = ColorSegmentationDetector(morph_kernel=int(kk))
            cnts = contours_of(cimg, int(kk), int(kk))
            for hi, cxy, d in placements:
                r = host_outcome(cnts, objs[hi], cxy)
                detk_rows[kk].append(r)
        del cimg
    pooled_scene = {
        "tp": sum(s["tp"] for s in scene_scores), "fp": sum(s["fp"] for s in scene_scores),
        "fn": sum(s["fn"] for s in scene_scores), "det_total": sum(s["det_total"] for s in scene_scores)}
    pooled_scene["precision"] = round(pooled_scene["tp"] / max(1, pooled_scene["tp"] + pooled_scene["fp"]), 4)
    pooled_scene["recall"] = round(pooled_scene["tp"] / max(1, pooled_scene["tp"] + pooled_scene["fn"]), 4)
    entry = {"all": agg_hosts(main_rows), "bloom": agg_hosts(bloom_rows), "bud": agg_hosts(bud_rows),
             "scene": pooled_scene,
             "nonhost_recall": round(sum(a for a, _ in nonhost_stats) / max(1, sum(b for _, b in nonhost_stats)), 4),
             "close_merge_rate": {k: round(sum(v) / len(v), 4) if v else None for k, v in close_merge.items()},
             "det_kernel": {kk: agg_hosts(rr) for kk, rr in detk_rows.items()}}
    if area_pairs:
        devs = [(m - p) / p for m, p in area_pairs if p > 0]
        entry["area_account"] = {"n": len(devs),
                                 "median_rel_dev": round(float(np.median(devs)), 4) if devs else None,
                                 "p90_abs_dev": round(float(np.percentile(np.abs(devs), 90)), 4) if devs else None}
    R["main"][f"gap={gap}"] = entry
    log({"stage": "gap_done", "gap": gap, "merged": entry["all"]["merged_rate"],
         "correct": entry["all"]["correct_rate"], "bud_migrated": entry["bud"]["migrated_rate"],
         "close": entry["close_merge_rate"]})

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
log({"stage": "DONE", "out": OUT})
