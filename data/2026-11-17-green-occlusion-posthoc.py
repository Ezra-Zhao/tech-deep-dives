"""Posthoc summary for 2026-11-17 green occlusion bench: per-(host,rc)
dc curves, monotonicity check, prediction verdicts P1-P6."""
import json
import numpy as np

B = json.load(open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-17-green-occlusion-bench.json"))
cells = B["cells"]
out = {"alone": B["alone"], "green_alone": B["green_alone"], "curves": {}, "verdicts": {}}

# P1: green alone invisible; FP only in split cells
ga = B["green_alone"]
out["verdicts"]["P1_green_alone_zero"] = all(
    all(v == 0 for v in ga[rc]["n_contours_ge120"]) and all(v == 0 for v in ga[rc]["mask_px"])
    for rc in ga)
fp_nonsplit, fp_split = [], []
for k, c in cells.items():
    for t in c["trials"]:
        (fp_split if t["n_frag"] >= 2 else fp_nonsplit).append(t["fp"])
out["verdicts"]["P1_fp_nonsplit_max"] = max(fp_nonsplit) if fp_nonsplit else None
out["verdicts"]["P1_fp_split_mean"] = round(float(np.mean(fp_split)), 4) if fp_split else None
out["verdicts"]["P1_fp_total"] = int(sum(fp_nonsplit) + sum(fp_split))

for host in ("bloom", "bud"):
    for rc in (12, 24, 36):
        rows = [(c["dc"], c) for k, c in cells.items()
                if k.startswith(host + "|") and f"rc={rc}|" in k]
        rows.sort(key=lambda x: -x[0])
        # monotonicity of area_ratio median as dc decreases (skip separated dc=r+rc+10)
        seq = [c["area_ratio_median"] for dc, c in rows if dc <= B["hosts"][host] + rc]
        viol = [round(seq[i + 1] - seq[i], 4) for i in range(len(seq) - 1) if seq[i + 1] - seq[i] > 0.03]
        out["curves"][f"{host}|rc={rc}"] = {"rows": [
            {"dc": c["dc"], "bite": c["bite"], "area_ratio": c["area_ratio_median"],
             "mask_ratio": c["mask_ratio_median"], "split": c["split_rate"],
             "lost_f": c["lost_frag_rate"], "mig_f": c["migrated_frag_rate"],
             "cor_f": c["correct_frag_rate"], "lost_c": c["lost_center_rate"],
             "fp": c["fp_mean"], "fn": c["fn_mean"]} for _, c in rows],
            "mono_violations": viol}

# P2: bloom concentric
for rc in (12, 24, 36):
    c = cells[f"bloom|rc={rc}|dc=0"]
    out["verdicts"][f"P2_bloom_concentric_rc{rc}"] = {
        "area_ratio": c["area_ratio_median"], "mask_ratio": c["mask_ratio_median"],
        "correct_f": c["correct_frag_rate"], "lost_f": c["lost_frag_rate"]}

# P4: any bloom migrated cell; bud migrated anywhere
out["verdicts"]["P4_bloom_migrated_cells"] = {
    k: c["migrated_frag_rate"] for k, c in cells.items()
    if k.startswith("bloom|") and c["migrated_frag_rate"] > 0}
out["verdicts"]["P4_bud_migrated_max"] = max(
    c["migrated_frag_rate"] for k, c in cells.items() if k.startswith("bud|"))

# P5: bud deep cells
deep = {k: c["lost_frag_rate"] for k, c in cells.items()
        if k.startswith("bud|") and c["dc"] <= 6 and int(k.split("rc=")[1].split("|")[0]) >= 24}
out["verdicts"]["P5_bud_deep_lost"] = deep
deepest = {}
for rc in (12, 24, 36):
    c = cells[f"bud|rc={rc}|dc=0"]
    deepest[f"rc={rc}"] = c["lost_frag_rate"]
out["verdicts"]["P5_bud_concentric_lost"] = deepest

# P6: bloom rc=36, 6<=dc<=r-6=32 split rate; split-cell FP mean already in P1
band = {k: c["split_rate"] for k, c in cells.items()
        if k.startswith("bloom|rc=36|") and 6 <= c["dc"] <= 32}
out["verdicts"]["P6_bloom_rc36_split_band"] = band

# extras: bloom worst area loss at notch (dc=r), bud tangent/sep sanity,
# centre-vs-fragment lost divergence, total trials
out["extras"] = {
    "n_trials": sum(c["n"] for c in cells.values()),
    "bloom_sep_area_ratio": {rc: cells[f"bloom|rc={rc}|dc={38 + rc + 10}"]["area_ratio_median"] for rc in (12, 24, 36)},
    "bud_sep_area_ratio": {rc: cells[f"bud|rc={rc}|dc={15 + rc + 10}"]["area_ratio_median"] for rc in (12, 24, 36)},
    "max_fp_mean_cell": max((c["fp_mean"], k) for k, c in cells.items()),
    "cells_with_fp": {k: c["fp_mean"] for k, c in cells.items() if c["fp_mean"] > 0},
}
json.dump(out, open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-17-green-occlusion-posthoc.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(out, indent=2, ensure_ascii=False))
