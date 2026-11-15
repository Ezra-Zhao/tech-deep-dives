"""Posthoc analysis for 2026-11-14 marker correction bench.
Reads the bench JSON only; computes preregistered verdicts P1-P6 and
guard ledgers. Writes 2026-11-14-marker-correction-posthoc.json.
"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(BASE, "2026-11-14-marker-correction-bench.json")))
SCALES = d["scales"]
FT, BAD = 0.08, 0.10
out = {}

val = d["validation_marker"]["per_scale"]
out["val_table"] = {f"s={s}": {"raw": val[f"s={s}"]["err_raw"], "corr": val[f"s={s}"]["err_corr"]} for s in SCALES}
out["cal_bias"] = {f"s={s}": d["calibration"]["per_scale"][f"s={s}"]["bias"] for s in SCALES}
out["cal_corr_insample"] = d["calibration"]["corrected_err_insample"]
out["cal_ref"] = d["calibration"]["ref_area"]
out["val_ref"] = d["validation_marker"]["ref_area"]

# P1/P2
band = [s for s in SCALES if 0.15 <= s <= 1.0]
out["P1_max_corr_err_015_10"] = max(abs(val[f"s={s}"]["err_corr"]) for s in band)
out["P2"] = {"s012": abs(val["s=0.12"]["err_corr"]), "s010": abs(val["s=0.1"]["err_corr"]),
             "s007": abs(val["s=0.07"]["err_corr"])}

# Retrospective ledgers
retro = d["retrospective"]
led = {}
for name, blk in retro.items():
    pooled_health_flags_raw = pooled_health_flags_corr = 0
    pooled_health_flags_raw_ge015 = pooled_health_flags_corr_ge015 = 0
    pooled_n = 0
    scene_bad = []
    scene_health_flags_corr_ge015 = scene_health_flags_raw_ge015 = 0
    scene_health_n_ge015 = 0
    for s in SCALES:
        row = blk[f"s={s}"]
        pooled_n += 1
        bad = row["errmed"] is not None and abs(row["errmed"]) > BAD
        if not bad:
            if row["D_raw"] is not None and abs(row["D_raw"]) > FT:
                pooled_health_flags_raw += 1
                if s >= 0.15: pooled_health_flags_raw_ge015 += 1
            if row["D_corr"] is not None and abs(row["D_corr"]) > FT:
                pooled_health_flags_corr += 1
                if s >= 0.15: pooled_health_flags_corr_ge015 += 1
        for ps in row["per_scene"]:
            b = ps["errmed"] is not None and abs(ps["errmed"]) > BAD
            if b:
                scene_bad.append({"set": name, "seed": ps["scene_seed"], "s": s,
                                  "errmed": ps["errmed"], "D_raw": ps["D_raw"], "D_corr": ps["D_corr"],
                                  "flag_raw": ps["D_raw"] is not None and abs(ps["D_raw"]) > FT,
                                  "flag_corr": ps["D_corr"] is not None and abs(ps["D_corr"]) > FT})
            elif s >= 0.15:
                scene_health_n_ge015 += 1
                if ps["D_raw"] is not None and abs(ps["D_raw"]) > FT: scene_health_flags_raw_ge015 += 1
                if ps["D_corr"] is not None and abs(ps["D_corr"]) > FT: scene_health_flags_corr_ge015 += 1
    led[name] = {"pooled_health_flags_raw": pooled_health_flags_raw,
                 "pooled_health_flags_corr": pooled_health_flags_corr,
                 "pooled_health_flags_raw_ge015": pooled_health_flags_raw_ge015,
                 "pooled_health_flags_corr_ge015": pooled_health_flags_corr_ge015,
                 "scene_bad_points": scene_bad,
                 "scene_health_n_ge015": scene_health_n_ge015,
                 "scene_health_flags_raw_ge015": scene_health_flags_raw_ge015,
                 "scene_health_flags_corr_ge015": scene_health_flags_corr_ge015}
out["retro_ledger"] = led

# holdout4
h4 = d["holdout4"]
out["holdout4_sanity"] = h4["baseline_sanity"]
out["holdout4_summary"] = h4["summary"]
h4flags = {}
for s in SCALES:
    p = h4["results"][f"s={s}"]["pooled"]
    h4flags[f"s={s}"] = {"errmed": p["errmed"], "D_raw": p["D_raw"], "D_corr": p["D_corr"],
                         "flag_raw": p["flag_raw"], "flag_corr": p["flag_corr"]}
out["holdout4_pooled"] = h4flags
h4_scene_bad = []
h4_scene_health_flags = {"raw": 0, "corr": 0, "n_ge015": 0}
for s in SCALES:
    for ps in h4["results"][f"s={s}"]["per_scene"]:
        b = ps["errmed"] is not None and abs(ps["errmed"]) > BAD
        if b:
            h4_scene_bad.append({"seed": ps["scene_seed"], "s": s, "errmed": ps["errmed"],
                                 "D_raw": ps["D_raw"], "D_corr": ps["D_corr"]})
        elif s >= 0.15:
            h4_scene_health_flags["n_ge015"] += 1
            if ps["D_raw"] is not None and abs(ps["D_raw"]) > FT: h4_scene_health_flags["raw"] += 1
            if ps["D_corr"] is not None and abs(ps["D_corr"]) > FT: h4_scene_health_flags["corr"] += 1
out["holdout4_scene_bad"] = h4_scene_bad
out["holdout4_scene_health_flags_ge015"] = h4_scene_health_flags

# injection
inj = d["injection"]
inj_rows = []
for g, blk in inj.items():
    for skey, row in blk.items():
        s = float(skey.split("=")[1])
        inj_rows.append({"g": g, "s": s, "errmed": row["errmed"],
                         "bad": row["errmed"] is not None and abs(row["errmed"]) > BAD,
                         "flag_raw": row["D_raw"] is not None and abs(row["D_raw"]) > FT,
                         "flag_corr": row["D_corr"] is not None and abs(row["D_corr"]) > FT,
                         "D_raw": row["D_raw"], "D_corr": row["D_corr"]})
out["injection"] = inj_rows
out["injection_bad_ge015"] = [r for r in inj_rows if r["bad"] and r["s"] >= 0.15]
out["injection_bad_lt015"] = [r for r in inj_rows if r["bad"] and r["s"] < 0.15]

json.dump(out, open(os.path.join(BASE, "2026-11-14-marker-correction-posthoc.json"), "w"),
          indent=2, ensure_ascii=False)
print(json.dumps({k: out[k] for k in ("P1_max_corr_err_015_10", "P2", "cal_ref", "val_ref")}, indent=1))
for name, L in led.items():
    print(name, "pooled health flags raw/corr:", L["pooled_health_flags_raw"], L["pooled_health_flags_corr"],
          "| ge015 raw/corr:", L["pooled_health_flags_raw_ge015"], L["pooled_health_flags_corr_ge015"],
          "| scene health ge015 flags raw/corr:", L["scene_health_flags_raw_ge015"], L["scene_health_flags_corr_ge015"],
          "of", L["scene_health_n_ge015"], "| scene BAD:", len(L["scene_bad_points"]))
print("holdout4 scene BAD:", h4_scene_bad)
print("holdout4 scene health flags ge015:", h4_scene_health_flags)
print("inj bad ge015:", len(out["injection_bad_ge015"]), "flagged corr:",
      sum(1 for r in out["injection_bad_ge015"] if r["flag_corr"]), "raw:",
      sum(1 for r in out["injection_bad_ge015"] if r["flag_raw"]))
print("inj bad lt015:", [(r["g"], r["s"], r["flag_raw"], r["flag_corr"]) for r in out["injection_bad_lt015"]])
