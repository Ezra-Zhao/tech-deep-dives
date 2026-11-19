"""Posthoc for clutter size scan (2026-11-18): distribution-formula
verification, turning point, migration band, FP accounting, neighbour
sensitivity. Formula/prediction口径 frozen in the prereg."""
import json
import numpy as np

D = json.load(open("2026-11-18-clutter-size-bench.json"))
cells = D["cells"]
RCS, GAPS = D["rcs"], D["gaps"]
out = {}

out["clutter_alone_median"] = {rc: D["clutter_alone"][str(rc)]["median"] for rc in RCS}
out["bud_alone"] = {"n": len(D["bud_alone_sorted"]),
                    "min": D["bud_alone_sorted"][0],
                    "median": float(np.median(D["bud_alone_sorted"])),
                    "max": D["bud_alone_sorted"][-1],
                    "sorted": D["bud_alone_sorted"]}

# migration / merged / addition tables
mig, merged_rate, add_med, bloom_ok, lost = {}, {}, {}, {}, {}
for rc in RCS:
    for gap in GAPS:
        c = cells[f"rc={rc}|gap={gap}"]
        key = f"rc={rc}|gap={gap}"
        mig[key] = {"bud_merged": c["bud_merged"], "bud_migrated": c["bud_migrated"],
                    "rate": c["bud_mig_rate_merged"]}
        merged_rate[key] = c["merged_rate"]
        add_med[key] = c["addition_median_merged"]
        bloom_ok[key] = c["bloom_correct_rate"]
        lost[key] = c["lost_total"]
out["migration"] = mig
out["merged_rate"] = merged_rate
out["addition_median"] = add_med
out["bloom_correct_min"] = min(bloom_ok.values())
out["lost_total_all"] = sum(lost.values())

# distribution formula per prereg
formula = {}
ok_cells = 0
elig = 0
pred_tot = obs_tot = 0
for rc in RCS:
    for gap in GAPS:
        c = cells[f"rc={rc}|gap={gap}"]
        a_eff = c["addition_median_merged"]
        if a_eff is None or c["bud_merged"] < 5:
            continue
        thr = 900 - a_eff
        pred = sum(1 for r in c["rows"] if r["label"] == "bud" and r["merged"]
                   and r["alone"] is not None and r["alone"] >= thr)
        obs = c["bud_migrated"]
        formula[f"rc={rc}|gap={gap}"] = {"a_eff": a_eff, "thr": round(thr, 1),
                                         "pred": pred, "obs": obs,
                                         "diff": pred - obs}
        elig += 1
        pred_tot += pred
        obs_tot += obs
        if abs(pred - obs) <= 2:
            ok_cells += 1
out["formula"] = {"cells": formula, "eligible": elig, "within2": ok_cells,
                  "pred_total": pred_tot, "obs_total": obs_tot}

# turning point at gap=-3 and band per rc
out["gap-3_rates"] = {rc: mig[f"rc={rc}|gap=-3"]["rate"] for rc in RCS}
out["gap-3_add"] = {rc: add_med[f"rc={rc}|gap=-3"] for rc in RCS}
band = {}
for rc in RCS:
    band[rc] = [g for g in GAPS if (mig[f"rc={rc}|gap={g}"]["bud_migrated"] or 0) > 0]
out["migration_band_gaps"] = band

# transition band in alone-area terms at gap=-3 per rc
trans = {}
for rc in RCS:
    c = cells[f"rc={rc}|gap=-3"]
    mig_a = [r["alone"] for r in c["rows"] if r["label"] == "bud" and r["merged"]
             and r["outcome"] == "migrated"]
    non_a = [r["alone"] for r in c["rows"] if r["label"] == "bud" and r["merged"]
             and r["outcome"] != "migrated"]
    trans[str(rc)] = {"mig_min": min(mig_a) if mig_a else None,
                      "mig_max": max(mig_a) if mig_a else None,
                      "nonmig_max": max(non_a) if non_a else None,
                      "nonmig_min": min(non_a) if non_a else None,
                      "n_mig": len(mig_a), "n_non": len(non_a)}
out["transition_gap-3"] = trans

# FP accounting per prereg: FP ~= migrated + unmerged surviving clutter
fpacc = {}
fp_ok = fp_elig = 0
for rc in RCS:
    survives = D["clutter_alone"][str(rc)]["median"] >= 120
    for gap in GAPS:
        c = cells[f"rc={rc}|gap={gap}"]
        unmerged = sum(1 for r in c["rows"] if not r["merged"])
        pred_fp = c["bud_migrated"] + (unmerged if survives else 0)
        obs_fp = c["scene"]["fp"]
        fpacc[f"rc={rc}|gap={gap}"] = {"pred": pred_fp, "obs": obs_fp,
                                       "diff": pred_fp - obs_fp}
        fp_elig += 1
        if abs(pred_fp - obs_fp) <= 3:
            fp_ok += 1
out["fp_accounting"] = {"cells": fpacc, "eligible": fp_elig, "within3": fp_ok}

# neighbour sensitivity: any nbr_clear<0 placements?
neg = {k: cells[k]["nbr_clear_neg"] for k in cells if cells[k]["nbr_clear_neg"]}
neg_all = {k: cells[k]["nbr_clear_all_neg"] for k in cells if cells[k]["nbr_clear_all_neg"]}
out["nbr_clear_neg_cells"] = neg
out["nbr_clear_all_neg_cells"] = neg_all
# recompute migration excluding nbr_clear_all<0 rows, gap=-3
sens = {}
for rc in RCS:
    c = cells[f"rc={rc}|gap=-3"]
    rows = [r for r in c["rows"] if r["label"] == "bud" and r["merged"] and r["nbr_clear_all"] >= 0]
    sens[str(rc)] = {"n": len(rows),
                     "mig_rate": round(sum(1 for r in rows if r["outcome"] == "migrated") / len(rows), 4) if rows else None}
out["sensitivity_gap-3_excl_nbrneg"] = sens

# merged rate at gap=8 per rc (P4 upper edge) and gap=-18 rates
out["merged_gap8"] = {rc: merged_rate[f"rc={rc}|gap=8"] for rc in RCS}
out["gap-18_rates"] = {rc: mig[f"rc={rc}|gap=-18"]["rate"] for rc in RCS}
out["gap-8_mig"] = {rc: mig[f"rc={rc}|gap=8"]["bud_migrated"] for rc in RCS}
# per-rc A_eff at gap=-3 vs thresholds: full migration needs >= 900-min_bud
out["full_mig_threshold"] = round(900 - D["bud_alone_sorted"][0], 1)

# per-host addition spread in the two formula-failure cells + one near cell
spread = {}
for key in ("rc=12|gap=-3", "rc=15|gap=-18", "rc=15|gap=-8", "rc=12|gap=0"):
    rows = [r for r in cells[key]["rows"] if r["label"] == "bud" and r["merged"]]
    mig_r = [r for r in rows if r["outcome"] == "migrated"]
    non_r = [r for r in rows if r["outcome"] != "migrated"]
    adds = [r["addition"] for r in rows]
    spread[key] = {
        "bud_add_min": min(adds), "bud_add_max": max(adds),
        "bud_add_iqr": [round(float(np.percentile(adds, 25)), 1),
                        round(float(np.percentile(adds, 75)), 1)],
        "mig_add_median": round(float(np.median([r["addition"] for r in mig_r])), 1) if mig_r else None,
        "nonmig_add_median": round(float(np.median([r["addition"] for r in non_r])), 1) if non_r else None,
        "mig_alone_range": [min(r["alone"] for r in mig_r), max(r["alone"] for r in mig_r)] if mig_r else None,
        "nonmig_max_alone": max(r["alone"] for r in non_r) if non_r else None}
out["bud_addition_spread"] = spread
# lone-disc detector label (measured separately on foliage bg, seed 7001,
# same detector): rc<=15 -> bud, rc>=18 -> bloom; recorded here verbatim
out["lone_disc_label"] = {"8": "bud", "12": "bud", "15": "bud",
                          "18": "bloom", "24": "bloom"}

json.dump(out, open("2026-11-18-clutter-size-posthoc.json", "w"), indent=2, ensure_ascii=False)
print(json.dumps({k: out[k] for k in ("clutter_alone_median", "bud_alone", "gap-3_rates",
                                      "gap-3_add", "migration_band_gaps", "merged_gap8",
                                      "gap-18_rates", "full_mig_threshold",
                                      "bloom_correct_min", "lost_total_all")},
                 ensure_ascii=False, indent=1))
print("formula:", out["formula"]["eligible"], "eligible, within2:", out["formula"]["within2"],
      "pred/obs totals:", out["formula"]["pred_total"], out["formula"]["obs_total"])
print("fp:", out["fp_accounting"]["eligible"], "cells, within3:", out["fp_accounting"]["within3"])
print("nbr_neg cells:", neg, "nbr_all_neg cells:", neg_all)
