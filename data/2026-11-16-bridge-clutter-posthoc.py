"""Posthoc summary for 2026-11-16 bridge clutter bench. Reads bench JSON only."""
import json, statistics as st

P = "/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-16-bridge-clutter-bench.json"
R = json.load(open(P))
cells = R["cells"]

def cell(pt, G, rc):
    return cells[f"{pt}|G={G}|rc={rc}"]

out = {}
out["alone_median"] = {k: (st.median([a for a in v if a is not None]) if any(a is not None for a in v) else None) for k, v in R["alone"].items()}
out["bridge_alone_median"] = {k: (st.median([a for a in v if a is not None]) if any(a is not None for a in v) else None) for k, v in R["bridge_alone"].items()}

# merged_both tables
for pt in ("BB", "bb", "Bb"):
    tab = {}
    for rc in R["rcs"]:
        tab[str(rc)] = {str(G): cell(pt, G, rc)["merged_both_rate"] for G in R["gaps"]}
    out[f"mb_{pt}"] = tab
    tab1 = {}
    for rc in R["rcs"]:
        tab1[str(rc)] = {str(G): cell(pt, G, rc)["merged_one_rate"] for G in R["gaps"]}
    out[f"mo_{pt}"] = tab1

# symmetric pairs: merged_both as function of per-side gap g = G/2 - rc
from collections import defaultdict
gmap = defaultdict(list)
for pt in ("BB", "bb"):
    for rc in R["rcs"][1:]:
        for G in R["gaps"]:
            g = G / 2 - rc
            c = cell(pt, G, rc)
            gmap[g].append(c["merged_both_rate"])
out["sym_by_g"] = {str(g): {"mean": round(sum(v) / len(v), 4), "n_cells": len(v), "vals": v} for g, v in sorted(gmap.items())}

# Bb binding side g_bud = G/2 + 11.5 - rc
gmapb = defaultdict(list)
for rc in R["rcs"][1:]:
    for G in R["gaps"]:
        g = G / 2 + 11.5 - rc
        gmapb[g].append(cell("Bb", G, rc)["merged_both_rate"])
out["Bb_by_gbud"] = {str(g): {"mean": round(sum(v) / len(v), 4), "n_cells": len(v)} for g, v in sorted(gmapb.items())}

# max G with merged_both >= 0.5 per rc per pair type
out["maxG_mb50"] = {}
for pt in ("BB", "bb", "Bb"):
    per = {}
    for rc in R["rcs"][1:]:
        gs = [G for G in R["gaps"] if cell(pt, G, rc)["merged_both_rate"] >= 0.5]
        per[str(rc)] = max(gs) if gs else None
    out["maxG_mb50"][pt] = per

# pair harm in fully-merged cells (merged_both_rate == 1.0)
for pt in ("BB", "bb", "Bb"):
    rows = []
    for rc in R["rcs"][1:]:
        for G in R["gaps"]:
            c = cell(pt, G, rc)
            if c["merged_both_rate"] == 1.0:
                rows.append((G, rc, c["tp_hist"], c["fp_mean"], c["fn_mean"], c["merged_area_median"], c["merged_area_ge900_rate"]))
    out[f"fullmerge_{pt}"] = rows

# bb merged area >=900 overall across merged trials
bb_areas = []
for rc in R["rcs"][1:]:
    for G in R["gaps"]:
        for t in cell("bb", G, rc)["trials"]:
            if t["merged_area"] is not None:
                bb_areas.append(t["merged_area"])
out["bb_merged_area"] = {"n": len(bb_areas), "ge900_rate": round(sum(1 for a in bb_areas if a >= 900) / len(bb_areas), 4) if bb_areas else None,
                         "median": round(st.median(bb_areas), 1) if bb_areas else None,
                         "min": min(bb_areas) if bb_areas else None, "max": max(bb_areas) if bb_areas else None}
all_areas = {}
for pt in ("BB", "Bb"):
    arr = []
    for rc in R["rcs"][1:]:
        for G in R["gaps"]:
            for t in cell(pt, G, rc)["trials"]:
                if t["merged_area"] is not None:
                    arr.append(t["merged_area"])
    all_areas[pt] = {"n": len(arr), "ge900_rate": round(sum(1 for a in arr if a >= 900) / len(arr), 4) if arr else None,
                     "median": round(st.median(arr), 1) if arr else None}
out["merged_area_stats"] = all_areas

# control rc=0
out["control_rc0"] = {}
for pt in ("BB", "bb", "Bb"):
    out["control_rc0"][pt] = {str(G): {"mb": cell(pt, G, 0)["merged_both_rate"], "intact": cell(pt, G, 0)["intact_rate"],
                                       "tp_hist": cell(pt, G, 0)["tp_hist"], "fp_mean": cell(pt, G, 0)["fp_mean"], "fn_mean": cell(pt, G, 0)["fn_mean"]} for G in R["gaps"]}

# bridge-alone FP behaviour: cells where neither merge happened -> fp from bridge disc itself
fp_free = []
for pt in ("BB", "bb", "Bb"):
    for rc in R["rcs"][1:]:
        for G in R["gaps"]:
            c = cell(pt, G, rc)
            if c["merged_both_rate"] == 0 and c["merged_one_rate"] == 0:
                fp_free.append((pt, G, rc, c["fp_mean"], c["fn_mean"], c["intact_rate"]))
out["bridge_free_cells"] = fp_free

# Bb merged_one band summary
mo_bb = [(G, rc, cell("Bb", G, rc)["merged_one_rate"]) for rc in R["rcs"][1:] for G in R["gaps"]]
out["Bb_mo_full"] = [(G, rc, r) for (G, rc, r) in mo_bb if r == 1.0]
out["Bb_mo_any"] = [(G, rc, r) for (G, rc, r) in mo_bb if r > 0]

# outcomes inside fully merged bb cells: tp hist aggregate
agg = {"BB": [0, 0, 0], "bb": [0, 0, 0], "Bb": [0, 0, 0]}
fpm = {"BB": [], "bb": [], "Bb": []}; fnm = {"BB": [], "bb": [], "Bb": []}
for pt in agg:
    for rc in R["rcs"][1:]:
        for G in R["gaps"]:
            c = cell(pt, G, rc)
            if c["merged_both_rate"] == 1.0:
                for k in (0, 1, 2):
                    agg[pt][k] += c["tp_hist"][str(k)]
                fpm[pt].append(c["fp_mean"]); fnm[pt].append(c["fn_mean"])
out["fullmerge_tp_hist_agg"] = agg
out["fullmerge_fp_fn_mean"] = {pt: {"fp": round(sum(fpm[pt]) / len(fpm[pt]), 4) if fpm[pt] else None,
                                    "fn": round(sum(fnm[pt]) / len(fnm[pt]), 4) if fnm[pt] else None,
                                    "n_cells": len(fpm[pt])} for pt in agg}

# global totals
tot_trials = sum(c["n"] for c in cells.values())
out["total_trials"] = tot_trials

with open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-16-bridge-clutter-posthoc.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False)[:9000])
