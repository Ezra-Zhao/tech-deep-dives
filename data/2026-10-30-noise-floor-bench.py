"""Bloom-Counter zoom-in noise-floor bench (2026-10-30).

Fulfils the untested risk flagged in 2026-10-26: at s>1 a fixed min_area
is effectively a 1/s^2 relative floor. On the clean simulator background
nothing exists below the floor to let through; this bench plants known
clutter (petal-coloured patches in three size strata plus a blue
negative control) and measures, per scale and per parameter arm, how
many planted items the detector lets through.

Design frozen in 2026-10-30-noise-floor-prereg.md before the run:
  arms A fixed min / B min x s^2 / C min x s^2 + kernel scaled /
       D fully fixed reference (bloom threshold also fixed).
  bloom_area_min is scaled by s^2 in A/B/C to isolate the min_area
  variable from the classification migration proven in 2026-10-26.
Clutter pass = a detection not consumed by GT matching whose centre
falls within tolerance of the planted item's (scaled) centre.
Morphology survival is measured separately (mask + CLOSE + OPEN
contours, before the min_area filter), for k=7 and k=odd(7*s).

Usage: .venv/bin/python 2026-10-30-noise-floor-bench.py <repo> <out_json>
Progress lines append to <out_json>.progress.jsonl .
"""
import json, math, os, sys
import numpy as np
import cv2

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/github/Bloom-Counter"
OUT = sys.argv[2] if len(sys.argv) > 2 else "2026-10-30-noise-floor-bench.json"
PROG = OUT + ".progress.jsonl"
sys.path.insert(0, REPO)
os.chdir(REPO)
WORK = "/tmp/bloom_noise_bench"
os.makedirs(WORK, exist_ok=True)

from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector

SCENES = [(101, 30, 18), (202, 36, 20), (303, 28, 16), (404, 40, 22)]
BASE_MIN, BASE_BLOOM, BASE_KERNEL = 120, 900, 7
SCALES = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
W0, H0 = 1280, 960
COLORS = {"pink": (147, 20, 255), "white": (245, 245, 245), "yellow": (0, 215, 255),
          "blue": (255, 0, 0)}
SUB_R = [3, 4, 5, 6]      # nominal area 28..113, below min_area=120
MID_R = [7, 10]           # 154 / 314
LARGE_R = [14]            # 616


def odd_kernel(s):
    k = int(round(BASE_KERNEL * s))
    if k % 2 == 0:
        k += 1
    return max(3, k)


def stratum(r, control=False):
    if control:
        return "control_blue"
    if r in SUB_R:
        return "subfloor"
    if r in MID_R:
        return "mid"
    return "large"


def plant_clutter(img, objects, seed):
    """Draw clutter on a copy of img; return (img2, items). Items carry
    baseline-centre, equivalent radius r, nominal area, colour, shape."""
    rng = np.random.default_rng(90000 + seed)
    h, w = img.shape[:2]
    out = img.copy()
    items = []
    plan = []  # (r, colour, shape, control)
    vis_cols = ["pink", "white", "yellow"]
    idx = 0
    for r in SUB_R + MID_R + LARGE_R:
        for shape in ("circle", "square"):
            for _ in range(4):
                plan.append((r, vis_cols[idx % 3], shape, False)); idx += 1
    for _ in range(8):
        plan.append((10, "blue", "circle", True))
    placed = []  # (cx, cy, r)
    for r, colour, shape, control in plan:
        ok = False
        for _ in range(600):
            cx = int(rng.integers(30 + r, w - 30 - r))
            cy = int(rng.integers(30 + r, h - 30 - r))
            if any(math.hypot(cx - o["cx"], cy - o["cy"]) <= o["r"] + r + 20 for o in objects):
                continue
            if any(math.hypot(cx - x, cy - y) <= rr + r + 20 for x, y, rr in placed):
                continue
            ok = True
            break
        if not ok:
            continue
        placed.append((cx, cy, r))
        bgr = COLORS[colour]
        if shape == "circle":
            cv2.circle(out, (cx, cy), r, bgr, -1)
            nominal = math.pi * r * r
        else:
            side = int(round(r * math.sqrt(math.pi)))
            cv2.rectangle(out, (cx - side // 2, cy - side // 2),
                          (cx - side // 2 + side, cy - side // 2 + side), bgr, -1)
            nominal = float(side * side)
        items.append({"cx": cx, "cy": cy, "r": r, "colour": colour, "shape": shape,
                      "control": control, "stratum": stratum(r, control),
                      "nominal_area": round(nominal, 1)})
    return out, items


def detect_with(image, min_area, bloom_min, kernel_size):
    det = ColorSegmentationDetector(min_area=int(round(min_area)),
                                    bloom_area_min=int(round(bloom_min)),
                                    morph_kernel=int(kernel_size))
    return det.detect(image)


def morph_contours(image, kernel_size):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ColorSegmentationDetector._petal_mask(hsv)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [(float(cv2.contourArea(c)),
             (lambda b: (b[0] + b[2] / 2.0, b[1] + b[3] / 2.0))(cv2.boundingRect(c)))
            for c in contours]


def match_gt(dets, objects, geom):
    """Greedy centre matching, label must match (previous articles' rule).
    Returns (used_det_idx set, tp, per-class hits)."""
    used = set(); tp = 0
    per = {"bloom": 0, "bud": 0}
    order = list(range(len(dets)))
    for di in order:
        d = dets[di]
        best, bd = None, 1e9
        for i, o in enumerate(objects):
            if o.get("_used") or o["label"] != d.label:
                continue
            dist = math.hypot(d.cx - o["cx"], d.cy - o["cy"])
            if dist < bd:
                bd, best = dist, i
        if best is not None:
            tol = max(38.0 * geom, objects[best]["r"] * 1.1)
            if bd <= tol:
                objects[best]["_used"] = True
                used.add(di); tp += 1; per[d.label] += 1
    for o in objects:
        o.pop("_used", None)
    return used, tp, per


def evaluate(dets, objects, items, s):
    used, tp, per = match_gt(dets, [dict(o) for o in objects], s)
    fp_dets = [d for i, d in enumerate(dets) if i not in used]
    fn = len(objects) - tp
    # clutter matching over remaining detections
    taken = set()
    passed = []
    for it in items:
        cx, cy = it["cx"] * s, it["cy"] * s
        tol = max(18.0 * s, 1.2 * it["r"] * s + 6)
        best, bd = None, 1e9
        for j, d in enumerate(fp_dets):
            if j in taken:
                continue
            dist = math.hypot(d.cx - cx, d.cy - cy)
            if dist < bd:
                bd, best = dist, j
        hit = best is not None and bd <= tol
        if hit:
            taken.add(best)
        passed.append(hit)
    fp = len(dets) - tp
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / len(objects) if objects else 1.0
    res = {"tp": tp, "fp": fp, "fn": fn,
           "precision": round(prec, 4), "recall": round(rec, 4),
           "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
           "bloom_recall": round(per["bloom"] / max(1, sum(1 for o in objects if o["label"] == "bloom")), 4),
           "bud_recall": round(per["bud"] / max(1, sum(1 for o in objects if o["label"] == "bud")), 4),
           "det_total": len(dets),
           "clutter_passed": int(sum(passed)),
           "clutter_total": len(items),
           "fp_unmatched_to_clutter": int(fp - sum(passed)),
           "passed_labels": {}}
    for it, p in zip(items, passed):
        if p:
            pass
    # strata / breakdowns of pass rate
    def rate(sel):
        sub = [(it, p) for it, p in zip(items, passed) if sel(it)]
        return {"passed": int(sum(p for _, p in sub)), "total": len(sub),
                "rate": round(sum(p for _, p in sub) / len(sub), 4) if sub else None}
    res["pass_by_stratum"] = {st: rate(lambda it, st=st: it["stratum"] == st)
                              for st in ("subfloor", "mid", "large", "control_blue")}
    res["pass_by_radius"] = {f"r={r}": rate(lambda it, r=r: it["r"] == r and not it["control"])
                             for r in SUB_R + MID_R + LARGE_R}
    res["pass_by_colour"] = {c: rate(lambda it, c=c: it["colour"] == c)
                             for c in ("pink", "white", "yellow", "blue")}
    res["pass_by_shape"] = {sh: rate(lambda it, sh=sh: it["shape"] == sh and not it["control"])
                            for sh in ("circle", "square")}
    return res


def aggregate(rows):
    """Micro / pooled aggregation over scenes."""
    tp = sum(r["tp"] for r in rows); fp = sum(r["fp"] for r in rows); fn = sum(r["fn"] for r in rows)
    prec = tp / (tp + fp) if tp + fp else 1.0; rec = tp / (tp + fn) if tp + fn else 1.0
    agg = {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4), "recall": round(rec, 4),
           "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
           "det_total": sum(r["det_total"] for r in rows),
           "clutter_passed": sum(r["clutter_passed"] for r in rows),
           "clutter_total": sum(r["clutter_total"] for r in rows),
           "fp_unmatched_to_clutter": sum(r["fp_unmatched_to_clutter"] for r in rows)}
    agg["pass_rate"] = round(agg["clutter_passed"] / agg["clutter_total"], 4) if agg["clutter_total"] else None
    for key in ("pass_by_stratum", "pass_by_radius", "pass_by_colour", "pass_by_shape"):
        merged = {}
        for r in rows:
            for k, v in r[key].items():
                m = merged.setdefault(k, {"passed": 0, "total": 0})
                m["passed"] += v["passed"]; m["total"] += v["total"]
        for v in merged.values():
            v["rate"] = round(v["passed"] / v["total"], 4) if v["total"] else None
        agg[key] = merged
    tb = sum(r["tp"] for r in rows)  # placeholder, recalls recomputed below via rows' own weighting not needed
    return agg


def morph_survival(images_items, s, kernel_size):
    """Pooled morphology survival by stratum for one kernel choice."""
    stats = {}
    areas = {}
    for img, items in images_items:
        contours = morph_contours(img, kernel_size)
        for it in items:
            cx, cy = it["cx"] * s, it["cy"] * s
            tol = max(18.0 * s, 1.2 * it["r"] * s + 6)
            best, bd = None, 1e9
            for a, (x, y) in contours:
                d = math.hypot(x - cx, y - cy)
                if d < bd:
                    bd, best = d, a
            st = stats.setdefault(it["stratum"], [0, 0])
            st[1] += 1
            if best is not None and bd <= tol:
                st[0] += 1
                areas.setdefault(it["stratum"], []).append(best)
    return {k: {"survived": v[0], "total": v[1],
                "rate": round(v[0] / v[1], 4) if v[1] else None,
                "median_area": round(float(np.median(areas[k])), 1) if areas.get(k) else None}
            for k, v in stats.items()}


def log(obj):
    with open(PROG, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(json.dumps(obj, ensure_ascii=False), flush=True)


ARMS = {
    "A_fixed_min": lambda s: (BASE_MIN, BASE_BLOOM * s * s, BASE_KERNEL),
    "B_scaled_min": lambda s: (BASE_MIN * s * s, BASE_BLOOM * s * s, BASE_KERNEL),
    "C_scaled_min_kernel": lambda s: (BASE_MIN * s * s, BASE_BLOOM * s * s, odd_kernel(s)),
    "D_fully_fixed": lambda s: (BASE_MIN, BASE_BLOOM, BASE_KERNEL),
}

bases, cluttered = [], []
plant_report = {}
for seed, nb, nd in SCENES:
    p = os.path.join(WORK, f"scene_{seed}.jpg")
    truth = generate_image(p, nb, nd, seed=seed)
    img = cv2.imread(p)
    bases.append((seed, img, truth["objects"]))
    cimg, items = plant_clutter(img, truth["objects"], seed)
    cluttered.append((seed, cimg, truth["objects"], items))
    plant_report[str(seed)] = {"planted": len(items),
                               "by_stratum": {st: sum(1 for i in items if i["stratum"] == st)
                                              for st in ("subfloor", "mid", "large", "control_blue")}}
log({"stage": "planted", "report": plant_report,
     "total_items": sum(len(i) for _, _, _, i in cluttered)})

R = {"detector": "color-segmentation-v0.1",
     "base_params": {"min_area": BASE_MIN, "bloom_area_min": BASE_BLOOM, "morph_kernel": BASE_KERNEL},
     "scales": SCALES, "plant_report": plant_report,
     "arms": {k: "min/bloom/kernel per lambda in script" for k in ARMS},
     "prereg": "data/2026-10-30-noise-floor-prereg.md"}
# clean sanity for A/B
R["clean"] = {}
R["main"] = {}
R["morph"] = {}
for s in SCALES:
    w, h = int(round(W0 * s)), int(round(H0 * s))
    big_clean = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_LINEAR),
                  [{"label": o["label"], "cx": o["cx"] * s, "cy": o["cy"] * s, "r": o["r"] * s} for o in objs])
                 for _, im, objs in bases]
    big_clut = [(cv2.resize(im, (w, h), interpolation=cv2.INTER_LINEAR),
                 [{"label": o["label"], "cx": o["cx"] * s, "cy": o["cy"] * s, "r": o["r"] * s} for o in objs],
                 items)
                for _, im, objs, items in cluttered]
    clean_entry = {}
    for arm in ("A_fixed_min", "B_scaled_min"):
        mn, bm, k = ARMS[arm](s)
        rows = [evaluate(detect_with(im, mn, bm, k), objs, [], s) for im, objs in big_clean]
        clean_entry[arm] = aggregate(rows) if False else {
            "tp": sum(r["tp"] for r in rows), "fp": sum(r["fp"] for r in rows),
            "fn": sum(r["fn"] for r in rows),
            "f1": rows[0]["f1"] if all(r["f1"] == rows[0]["f1"] for r in rows) else None,
            "micro_f1": round(2 * sum(r["tp"] for r in rows) /
                              (2 * sum(r["tp"] for r in rows) + sum(r["fp"] for r in rows) + sum(r["fn"] for r in rows)), 4)}
    R["clean"][f"s={s}"] = clean_entry
    entry = {}
    for arm, fnp in ARMS.items():
        mn, bm, k = fnp(s)
        rows = [evaluate(detect_with(im, mn, bm, k), objs, items, s) for im, objs, items in big_clut]
        agg = aggregate(rows)
        agg["params"] = {"min_area": int(round(mn)), "bloom_min": int(round(bm)), "kernel": int(k)}
        agg["per_scene_pass"] = [r["clutter_passed"] for r in rows]
        entry[arm] = agg
    R["main"][f"s={s}"] = entry
    R["morph"][f"s={s}"] = {
        "k7": morph_survival([(im, items) for im, _, items in big_clut], s, BASE_KERNEL),
        "kScaled": morph_survival([(im, items) for im, _, items in big_clut], s, odd_kernel(s))}
    log({"stage": "scale_done", "s": s,
         "A_sub": entry["A_fixed_min"]["pass_by_stratum"]["subfloor"],
         "B_sub": entry["B_scaled_min"]["pass_by_stratum"]["subfloor"],
         "C_sub": entry["C_scaled_min_kernel"]["pass_by_stratum"]["subfloor"],
         "A_prec": entry["A_fixed_min"]["precision"], "B_prec": entry["B_scaled_min"]["precision"]})
    del big_clean, big_clut

with open(OUT, "w") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
log({"stage": "DONE", "out": OUT})
