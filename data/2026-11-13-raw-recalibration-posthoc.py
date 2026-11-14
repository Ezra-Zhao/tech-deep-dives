"""Posthoc summary for 2026-11-13 RAW recalibration bench. Definitions frozen in prereg."""
import json

BASE = "/home/hatch/workspace/your_files/顶刊技术文章/data"
d = json.load(open(f"{BASE}/2026-11-13-raw-recalibration-bench.json"))
MAIN = [0.8, 0.65, 0.5, 0.4, 0.35, 0.30, 0.28, 0.25, 0.22, 0.18, 0.15, 0.12]  # prereg main band 0.12..0.8
MAIN = [s for s in d["scales"] if 0.12 <= s <= 0.8]

def mean(xs): return round(sum(xs) / len(xs), 4)
def mae(errs): return round(sum(abs(e) for e in errs) / len(errs), 4)

out = {"main_band": MAIN, "pools": {}}
for pool, pd_ in d["pools"].items():
    pts = pd_["pooled_points"]
    by_s = {p["s"]: p for p in pts}
    rec = {"cal_refs": pd_["cal_refs"], "self_refs": pd_["self_refs"], "variants": {}}
    for var in ("old", "R1", "R2", "R4"):
        key = f"err_raw_{var}"
        # main band excluding circular scale 0.5 for recal variants per prereg bias def:
        # prereg: bias = mean over main band excluding the circular档 (0.5 for R4; R1/R2 partially circular, also exclude 0.5 for comparability and report with-0.5 too)
        errs_ex = [by_s[s][key] for s in MAIN if s != 0.5 and by_s[s][key] is not None]
        errs_in = [by_s[s][key] for s in MAIN if by_s[s][key] is not None]
        all_errs = [p[key] for p in pts if p[key] is not None]
        rec["variants"][var] = {
            "bias_main_excl_cal": mean(errs_ex), "mae_main_excl_cal": mae(errs_ex),
            "bias_main_incl_cal": mean(errs_in), "mae_main_incl_cal": mae(errs_in),
            "mae_all15": mae(all_errs),
            "n_bad_all15": sum(1 for e in all_errs if abs(e) > 0.10),
            "err_by_scale": {str(p["s"]): p[key] for p in pts},
        }
    old_bias = rec["variants"]["old"]["bias_main_excl_cal"]
    for var in ("R1", "R2", "R4"):
        b = rec["variants"][var]["bias_main_excl_cal"]
        rec["variants"][var]["recovery_vs_old"] = (round(1 - abs(b) / abs(old_bias), 4) if old_bias else None)
    # MED3 comparison
    med = {}
    for tag in ("old", "R1", "R4"):
        key = f"err_med3_{tag}"
        errs_main = [by_s[s][key] for s in MAIN if by_s[s][key] is not None]
        all_errs = [p[key] for p in pts if p[key] is not None]
        med[tag] = {"mae_main_incl_cal": mae(errs_main), "n_bad_all15": sum(1 for e in all_errs if abs(e) > 0.10),
                    "err_by_scale": {str(p["s"]): p[key] for p in pts}}
    rec["med3"] = med
    # median identity counts (which estimator is the median) for old and R4
    ident = {"old": {}, "R4": {}}
    for p in pts:
        for tag, rk in (("old", "s_hat_raw_old"), ("R4", "s_hat_raw_R4")):
            vals = {"B7": p["s_hat7"], "B3": p["s_hat3"], "RAW": p[rk]}
            medv = p[f"s_hat_med3_{tag}"]
            name = [k for k, v in vals.items() if v == medv]
            ident[tag][str(p["s"])] = name[0] if name else None
    rec["med3_identity"] = ident
    # per-scene self-cal vs old
    scenes = {}
    for sp in pd_["scene_points"]:
        scenes.setdefault(str(sp["seed"]), []).append(sp)
    per_scene = {}
    for seed, sps in scenes.items():
        e_old = [x["err_raw_old"] for x in sps if x["s"] in MAIN and x["err_raw_old"] is not None]
        e_self = [x["err_raw_self"] for x in sps if x["s"] in MAIN and x["err_raw_self"] is not None]
        per_scene[seed] = {"mae_old_main": mae(e_old), "mae_self_main": mae(e_self),
                           "bias_old_main": mean(e_old), "bias_self_main": mean(e_self),
                           "err_old_by_scale": {str(x["s"]): x["err_raw_old"] for x in sps},
                           "err_self_by_scale": {str(x["s"]): x["err_raw_self"] for x in sps}}
    rec["per_scene"] = per_scene
    rec["per_scene_self_better"] = sum(1 for v in per_scene.values() if v["mae_self_main"] < v["mae_old_main"])
    out["pools"][pool] = rec

# prediction scoring
t1 = out["pools"]["T1"]["variants"]; t2 = out["pools"]["T2"]["variants"]
P = {}
P["P1"] = {"t1_bias": t1["old"]["bias_main_excl_cal"], "t2_bias": t2["old"]["bias_main_excl_cal"],
           "diff_pp": round(abs(t1["old"]["bias_main_excl_cal"] - t2["old"]["bias_main_excl_cal"]) * 100, 2)}
P["P1"]["hit"] = P["P1"]["diff_pp"] >= 1.5 and max(abs(t1["old"]["bias_main_excl_cal"]), abs(t2["old"]["bias_main_excl_cal"])) >= 0.02
for pool in ("T1", "T2"):
    v = out["pools"][pool]["variants"]
    P[f"P2_{pool}"] = {"recovery_R4": v["R4"]["recovery_vs_old"], "hit": (v["R4"]["recovery_vs_old"] is not None and v["R4"]["recovery_vs_old"] >= 0.60)}
    b_old, b_r1, b_r4 = v["old"]["bias_main_excl_cal"], v["R1"]["bias_main_excl_cal"], v["R4"]["bias_main_excl_cal"]
    overshoot = (b_r1 * b_old < 0) and abs(b_r1) >= 0.01
    P[f"P3_{pool}"] = {"bias_R1": b_r1, "bias_R4": b_r4, "gap_pp": round(abs(abs(b_r1) - abs(b_r4)) * 100, 2), "overshoot": overshoot,
                       "hit": (abs(abs(b_r1) - abs(b_r4)) >= 0.01) or overshoot}
P["P4"] = {"better_count_total": sum(out["pools"][p]["per_scene_self_better"] for p in ("T1", "T2"))}
P["P4"]["hit"] = P["P4"]["better_count_total"] >= 5
bad_old = sum(out["pools"][p]["med3"]["old"]["n_bad_all15"] for p in ("T1", "T2"))
bad_r4 = sum(out["pools"][p]["med3"]["R4"]["n_bad_all15"] for p in ("T1", "T2"))
mae_diffs = {p: round(abs(out["pools"][p]["med3"]["R4"]["mae_main_incl_cal"] - out["pools"][p]["med3"]["old"]["mae_main_incl_cal"]) * 100, 2) for p in ("T1", "T2")}
P["P5"] = {"med3_bad_old_30pts": bad_old, "med3_bad_R4_30pts": bad_r4, "mae_diff_pp": mae_diffs,
           "hit": bad_r4 <= bad_old and all(v < 0.5 for v in mae_diffs.values())}
s1 = {}
for pool in ("T1", "T2"):
    pts = d["pools"][pool]["pooled_points"]
    p1 = [p for p in pts if p["s"] == 1.0][0]
    s1[pool] = {v: p1[f"err_raw_{v}"] for v in ("old", "R1", "R2", "R4")}
P["P6"] = {"s1_errors": s1, "hit": all(e < -0.40 for pool in s1 for e in s1[pool].values())}
out["predictions"] = P
# ---- posthoc sensitivity (labelled posthoc in the article; not preregistered) ----
sens = {}
for pool, pd_ in d["pools"].items():
    by = {p["s"]: p for p in pd_["pooled_points"]}
    sp = {"estimators_healthy_band_s_ge_035": {}, "raw_bias_main_excl_cal_and_08": {},
          "per_scene_excl_cal": {}, "med3_identity_switches_old_to_R4": None}
    healthy = [s for s in MAIN if s >= 0.35]
    for name, k in (("B7", "s_hat7"), ("B3", "s_hat3"), ("RAW_old", "s_hat_raw_old")):
        errs = [round(by[s][k] / s - 1, 4) for s in healthy]
        sp["estimators_healthy_band_s_ge_035"][name] = {"bias": mean(errs), "mae": mae(errs)}
    for var in ("old", "R1", "R2", "R4"):
        errs = [by[s][f"err_raw_{var}"] for s in MAIN if s not in (0.5, 0.8)]
        sp["raw_bias_main_excl_cal_and_08"][var] = {"bias": mean(errs), "mae": mae(errs)}
    old_b = sp["raw_bias_main_excl_cal_and_08"]["old"]["bias"]
    r4_b = sp["raw_bias_main_excl_cal_and_08"]["R4"]["bias"]
    sp["raw_bias_main_excl_cal_and_08"]["recovery_R4_excl08"] = round(1 - abs(r4_b) / abs(old_b), 4) if old_b else None
    ident = out["pools"][pool]["med3_identity"]
    sp["med3_identity_switches_old_to_R4"] = sum(1 for s in ident["old"] if ident["old"][s] != ident["R4"][s])
    better = 0
    for seed, v in out["pools"][pool]["per_scene"].items():
        eo = [e for s, e in v["err_old_by_scale"].items() if float(s) in MAIN and float(s) != 0.5]
        es = [e for s, e in v["err_self_by_scale"].items() if float(s) in MAIN and float(s) != 0.5]
        sp["per_scene_excl_cal"][seed] = {"mae_old": mae(eo), "mae_self": mae(es), "bias_self": mean(es)}
        better += mae(es) < mae(eo)
    sp["per_scene_better_excl_cal"] = better
    sens[pool] = sp
out["posthoc_sensitivity"] = sens
out["predictions"] = P
json.dump(out, open(f"{BASE}/2026-11-13-raw-recalibration-posthoc.json", "w"), indent=2, ensure_ascii=False)
print(json.dumps(P, indent=2, ensure_ascii=False))
for pool in ("T1", "T2"):
    v = out["pools"][pool]["variants"]
    print(pool, {k: (v[k]["bias_main_excl_cal"], v[k]["mae_main_excl_cal"], v[k]["n_bad_all15"]) for k in v})
    print(pool, "MED3", {t: (out["pools"][pool]["med3"][t]["mae_main_incl_cal"], out["pools"][pool]["med3"][t]["n_bad_all15"]) for t in ("old", "R4")})
    print(pool, "per-scene better", out["pools"][pool]["per_scene_self_better"], "/4",
          {sd: (vv["mae_old_main"], vv["mae_self_main"], vv["bias_old_main"], vv["bias_self_main"]) for sd, vv in out["pools"][pool]["per_scene"].items()})
