import json
BASE = "/home/hatch/workspace/your_files/顶刊技术文章/data"
d = json.load(open(f"{BASE}/2026-11-12-divergence-cliff-bench.json"))
out = {"pools": {}}
tot_pool_amber = tot_pool_est = tot_scene_amber = tot_scene_est = 0
arm_healthy_max = {}
for name, p in d["pools"].items():
    pts = p["pooled_points"]
    amber_pts = [{"s": x["s"], "div": x["div"], "err7": x["err7"], "bad": x["bad"]} for x in pts if x["tier"] == "AMBER"]
    red_pts = [{"s": x["s"], "div": x["div"], "err7": x["err7"]} for x in pts if x["tier"] == "RED"]
    healthy = [abs(x["div"]) for x in pts if x["s"] >= 0.35 and x["div"] is not None]
    bad_pts = [{"s": x["s"], "div": x["div"], "err7": x["err7"], "tier": x["tier"]} for x in pts if x["bad"]]
    arm = p["arm"]
    arm_healthy_max.setdefault(arm, []).append(max(healthy) if healthy else None)
    sp = p["scene_points"]
    s_amber = sum(1 for x in sp if x["tier"] == "AMBER")
    s_est = sum(1 for x in sp if not x["noest"])
    tot_pool_amber += p["pooled_sharpness"]["amber"]; tot_pool_est += p["pooled_sharpness"]["n_est"]
    tot_scene_amber += s_amber; tot_scene_est += s_est
    out["pools"][name] = {"arm": arm, "amber_points": amber_pts, "red_points": red_pts,
                         "bad_points": bad_pts, "healthy_max_absdiv": max(healthy) if healthy else None,
                         "scene_amber": s_amber, "scene_est": s_est,
                         "scene_noest": sum(1 for x in sp if x["noest"]),
                         "pooled_noest_scales": [x["s"] for x in pts if x["noest"]]}
out["totals"] = {"pooled_amber": tot_pool_amber, "pooled_est": tot_pool_est,
                 "pooled_amber_share": round(tot_pool_amber / tot_pool_est, 4),
                 "scene_amber": tot_scene_amber, "scene_est": tot_scene_est,
                 "scene_amber_share": round(tot_scene_amber / tot_scene_est, 4),
                 "arm_healthy_max_absdiv": arm_healthy_max}
# HD1 scene 2313 early-bad detail
for name in ("HD1", "MIX2", "LD1"):
    p = d["pools"][name]
    out[f"{name}_scene_points_detail"] = [
        {"seed": x["seed"], "s": x["s"], "div": x["div"], "err7": x["err7"], "bad": x["bad"], "tier": x["tier"]}
        for x in p["scene_points"] if x["bad"] or x["tier"] in ("AMBER", "RED")]
out["prediction_verdicts"] = {
    "P1_hd_amber_zero_and_step_le1": False,
    "P1_detail": "HD amber 2 and 1 (not 0); transition steps both 1",
    "P2_ld_amber_ge2_and_healthy_max_gt_hd": None,
    "P3_mix_amber_ge2_and_gt_hd": True,
    "P4_scene_share_gt_pooled": tot_scene_amber / tot_scene_est > tot_pool_amber / tot_pool_est,
    "P5_mix_spread_ge2_and_hd_le1": False,
    "P5_detail": "MIX spreads 1 and 7; HD spreads 4 and 1 (HD1 scene 2313 first bad at s=0.65)",
    "P6_cons_catches_all_pooled_bad": all(p["pooled_sharpness"]["cons_catches_bad"] == p["pooled_sharpness"]["n_bad"] for p in d["pools"].values()),
}
ld_h = max(v for v in arm_healthy_max["LD"] if v is not None)
hd_h = max(v for v in arm_healthy_max["HD"] if v is not None)
out["prediction_verdicts"]["P2_ld_amber_ge2_and_healthy_max_gt_hd"] = bool(
    (d["pools"]["LD1"]["pooled_sharpness"]["amber"] + d["pools"]["LD2"]["pooled_sharpness"]["amber"] >= 2) and ld_h > hd_h)
out["ld_healthy_max"] = ld_h; out["hd_healthy_max"] = hd_h
json.dump(out, open(f"{BASE}/2026-11-12-divergence-cliff-posthoc.json", "w"), indent=2, ensure_ascii=False)
print(json.dumps(out, indent=2, ensure_ascii=False))
