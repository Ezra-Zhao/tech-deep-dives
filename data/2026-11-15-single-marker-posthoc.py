"""Posthoc aggregation for 2026-11-15 single-marker bench. Read-only."""
import json, os
import numpy as np

BASE = "/home/hatch/workspace/your_files/顶刊技术文章/data"
d = json.load(open(os.path.join(BASE, "2026-11-15-single-marker-bench.json")))
out = {}

A = d["armA_noise"]
a_rows = {}
ratios_in = 0; ratios_tot = 0
for k, v in A.items():
    s = float(k.split("=")[1])
    a_rows[k] = {"single_raw": v["single_raw"], "single_corr": v["single_corr"],
                 "median5_corr": v["median5_corr"], "ratio": v["sd_ratio_med5_over_single"]}
    if 0.15 <= s <= 1.0:
        ratios_tot += 1
        if v["sd_ratio_med5_over_single"] is not None and 0.40 <= v["sd_ratio_med5_over_single"] <= 0.70:
            ratios_in += 1
out["armA"] = a_rows
out["p2_ratio_count"] = {"in_0.40_0.70": ratios_in, "of_scales_0.15_to_1.0": ratios_tot}

B = d["armB_retro"]
out["armB_sweep"] = {t: B[t] for t in ("thr=0.08", "thr=0.1", "thr=0.12", "thr=0.15", "thr=0.18", "thr=0.2", "thr=0.25")}
out["armB_baseline"] = B["baseline_median5_thr0.08"]
out["armB_recal"] = B["recalibrated"]
pts = B["points"]
hot = sorted([p for p in pts if p["flag_rates"]["thr=0.08"] is not None and p["flag_rates"]["thr=0.08"] >= 0.5],
             key=lambda p: -p["flag_rates"]["thr=0.08"])
out["armB_hot_points_flagrate_ge_0.5"] = [
    {"set": p["set"], "scene": p["scene"], "s": p["s"], "errmed": p["errmed"],
     "is_bad": p["is_bad"], "flag_rate_0.08": p["flag_rates"]["thr=0.08"]} for p in hot]
bad_pts = [p for p in pts if p["is_bad"]]
out["armB_bad_points"] = [{"set": p["set"], "scene": p["scene"], "s": p["s"], "errmed": p["errmed"],
                           "flag_rate_0.08": p["flag_rates"]["thr=0.08"]} for p in bad_pts]
# variance decomposition at s>=0.15: sd of D across pairings for healthy points
# implied marker contribution: for a healthy point, pairing sd of D approx (1+errmed)*sd_marker/s-ish; report A sd at bands
C = d["armC_holdout5"]
cpts = C["points"]
out["armC_summary_extra"] = {
    "max_abs_errmed": round(max(abs(p["errmed"]) for p in cpts if p["errmed"] is not None), 4),
    "n_bad": sum(1 for p in cpts if p["is_bad"]),
    "bands_thr0.08": {}}
for label, sel in (("hi_ge_0.30", [p for p in cpts if p["s"] >= 0.30]),
                   ("mid_0.18_0.28", [p for p in cpts if 0.18 <= p["s"] <= 0.28]),
                   ("low_0.12_0.15", [p for p in cpts if 0.12 <= p["s"] <= 0.15]),
                   ("sub_lt_0.12", [p for p in cpts if p["s"] < 0.12])):
    rates = []
    for p in sel:
        if p["med"] is None:
            continue
        gs = [g for g in p["guards_corr"] if g is not None]
        rates.append(float(np.mean([1.0 if abs(p["med"] / g - 1.0) > 0.08 else 0.0 for g in gs])))
    out["armC_summary_extra"]["bands_thr0.08"][label] = {
        "healthy_flag_rate": round(float(np.mean(rates)), 4) if rates else None, "n_points": len(rates)}
hot_c = [{"scene": p["scene"], "s": p["s"], "errmed": p["errmed"],
          "guards": p["guards_corr"]} for p in cpts
         if p["med"] is not None and any(g is not None and abs(p["med"] / g - 1.0) > 0.08 for g in p["guards_corr"])]
out["armC_points_with_any_flag"] = hot_c

# prediction verdicts (computed, wording in article)
b08 = B["thr=0.08"]
out["verdicts"] = {
    "P1": {"sd_ge_0.5_max": max(A[f"s={s}"]["single_corr"]["sd"] for s in (1.0, 0.8, 0.65, 0.5)),
           "sd_0.15_0.22": {s: A[f"s={s}"]["single_corr"]["sd"] for s in (0.22, 0.18, 0.15)},
           "sd_0.07": A["s=0.07"]["single_corr"]["sd"]},
    "P3": {"single_fp_s_ge_0.15": b08["s_ge_0.15"]["healthy_flag_rate"],
           "baseline_fp_s_ge_0.15": B["baseline_median5_thr0.08"]["s_ge_0.15"]["healthy_flag_rate"],
           "ratio": round(b08["s_ge_0.15"]["healthy_flag_rate"] / B["baseline_median5_thr0.08"]["s_ge_0.15"]["healthy_flag_rate"], 3)},
    "P4": {"bad_catch_s_ge_0.15": b08["s_ge_0.15"]["bad_catch_rate"]},
    "P5": {"recal_s_ge_0.12": B["recalibrated"]["s_ge_0.12"],
           "recal_bands": B["recalibrated"]["bands"]},
    "P6": {"c_fp_0.08_s_ge_0.15": C["thr_0.08"]["s_ge_0.15"]["healthy_flag_rate"],
           "b_fp_0.08_s_ge_0.15": b08["s_ge_0.15"]["healthy_flag_rate"],
           "c_fp_recal_s_ge_0.12": C["thr_0.08"]["s_ge_0.12"]["healthy_flag_rate"],
           "b_fp_recal_s_ge_0.12": b08["s_ge_0.12"]["healthy_flag_rate"]}}
with open(os.path.join(BASE, "2026-11-15-single-marker-posthoc.json"), "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(json.dumps(out["verdicts"], indent=2, ensure_ascii=False))
print("hot points:", len(out["armB_hot_points_flagrate_ge_0.5"]))
for h in out["armB_hot_points_flagrate_ge_0.5"]:
    print(h)
print("bad points:", len(out["armB_bad_points"]))
for h in out["armB_bad_points"]:
    print(h)
print("C bands:", out["armC_summary_extra"])
print("C any-flag points:", len(out["armC_points_with_any_flag"]))
for h in out["armC_points_with_any_flag"]:
    print(h)
print("P2 ratios:", out["p2_ratio_count"])
for k, v in a_rows.items():
    print(k, "raw_sd", v["single_raw"]["sd"], "corr_sd", v["single_corr"]["sd"], "corr_mean", v["single_corr"]["mean"], "p5", v["single_corr"]["p5"], "p95", v["single_corr"]["p95"], "med5sd", v["median5_corr"]["sd"], "ratio", v["ratio"])
