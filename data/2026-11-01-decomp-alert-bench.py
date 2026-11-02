"""Decomposition-aware alert bench, layers A + C (2026-11-01).

Pre-registration: data/2026-11-01-decomp-alert-prereg.md (frozen before
this script was run). Candidate rule, exporter-observables only:

  F_s = echoed                       (proxy s2c forwards; identity
                                      verified per run, not assumed)
  F_c = forwarded - echoed           (proxy c2s forwards)
  D   = 1 - in_server / F_c          (drop rate of the segment between
                                      proxy c2s forward and proxy s2c
                                      input: shim + server + hops)
  E_exp = F_c * echoed / in_server
  L_exp = 1 - E_exp / sent ; L = 1 - echoed / sent
  CAND fires iff D > 0.10 ; OLD fires iff L > 0.75.

Layer A: re-score the 28 archived live runs of 2026-10-28
(data/2026-10-28-injection-band-bench.json) using ONLY the five
exporter quantities (sent, echoed, proxy in_client, in_server,
forwarded). Ground truth (shim stats, per-direction proxy decisions)
is read separately and used ONLY to verify the reconstruction
identities and to score |D - q| -- never as a rule input.

Layer C: arithmetic perturbation (NOT a measurement): scale in_client,
F_c and in_server of archived q=0 / q=0.20 runs by (1-g) for
g in {0.1, 0.2, 0.3} -- a bench gap that removes packets before the
proxy with the injection's own survival profile -- and re-evaluate
OLD's L and CAND's D.

Output: 2026-11-01-decomp-alert-bench.json next to this script.
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
SRC28 = os.path.join(HERE, "2026-10-28-injection-band-bench.json")
OUT = os.path.join(HERE, "2026-11-01-decomp-alert-bench.json")
D_LINE = 0.10
D_LINE_SENS = 0.05
OLD_LINE = 0.75


def score(sent, echoed, in_client, in_server, forwarded):
    f_s = echoed
    f_c = forwarded - echoed
    d = 1.0 - in_server / f_c if f_c else None
    e_exp = f_c * echoed / in_server if in_server else None
    l_obs = 1.0 - echoed / sent
    l_exp = 1.0 - e_exp / sent if e_exp is not None else None
    return {
        "F_c_reconstructed": f_c, "F_s_assumed": f_s, "D": d,
        "E_exp": e_exp, "L_obs": l_obs, "L_exp": l_exp,
        "L_minus_Lexp": (l_obs - l_exp) if l_exp is not None else None,
        "cand_fires": (d is not None and d > D_LINE),
        "cand_fires_sens05": (d is not None and d > D_LINE_SENS),
        "old_fires": l_obs > OLD_LINE,
        "bench_gap_rate": 1.0 - in_client / sent,
        "isolated_loss": 1.0 - echoed / in_client,
    }


def main():
    with open(SRC28, encoding="utf-8") as f:
        arch = json.load(f)
    rows = []
    for r in arch["live_runs"]:
        ps = r["proxy_summary"]
        s = score(r["sent"], r["echoed"], ps["in_client"],
                  ps["in_server"], ps["forwarded"])
        # --- ground truth, verification only ---
        dec = r["proxy_decisions"]
        fc_true = dec.get("c2s:forward")
        fs_true = dec.get("s2c:forward")
        shim = r["shim_stats"]
        q_meas = (shim["dropped_extra"] / shim["in_client"]
                  if shim["in_client"] else 0.0)
        s.update({
            "tag": r["tag"], "q": r["q"], "rep": r["rep"],
            "sent": r["sent"], "echoed": r["echoed"],
            "in_client": ps["in_client"], "in_server": ps["in_server"],
            "forwarded": ps["forwarded"],
            "F_c_true": fc_true, "F_s_true": fs_true,
            "Fc_identity_ok": s["F_c_reconstructed"] == fc_true,
            "Fs_identity_ok": s["F_s_assumed"] == fs_true,
            "proxy_to_shim_gap": (fc_true - shim["in_client"]
                                  if fc_true is not None else None),
            "in_server_eq_server_echoed":
                ps["in_server"] == r["server_stats"]["echoed"],
            "shim_measured_drop": q_meas,
            "D_err_vs_q": (s["D"] - r["q"]) if s["D"] is not None else None,
            "D_err_vs_qmeas": (s["D"] - q_meas) if s["D"] is not None else None,
        })
        rows.append(s)

    by_q = {}
    for q in sorted({r["q"] for r in rows}):
        rs = [r for r in rows if r["q"] == q]
        ds = [r["D"] for r in rs]
        by_q[str(q)] = {
            "n": len(rs),
            "D_values": [round(x, 4) for x in ds],
            "D_min": round(min(ds), 4), "D_max": round(max(ds), 4),
            "D_mean": round(statistics.mean(ds), 4),
            "cand_n_fire": sum(r["cand_fires"] for r in rs),
            "cand05_n_fire": sum(r["cand_fires_sens05"] for r in rs),
            "old_n_fire": sum(r["old_fires"] for r in rs),
            "old_iso_n_fire": sum(r["isolated_loss"] > OLD_LINE for r in rs),
            "abs_D_err_median": round(statistics.median(
                abs(r["D_err_vs_q"]) for r in rs), 4),
            "bench_gap_max": round(max(r["bench_gap_rate"] for r in rs), 4),
        }

    # bench-gap immunity: correlation of bench gap with L error and D error
    def pearson(xs, ys):
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        return cov / (vx * vy) ** 0.5 if vx and vy else None

    gaps = [r["bench_gap_rate"] for r in rows]
    # L's "error" = L_obs minus the run's isolated loss (bench contribution)
    l_bench_part = [r["L_obs"] - r["isolated_loss"] for r in rows]
    d_err = [r["D_err_vs_q"] for r in rows]

    layer_c = []
    for r in rows:
        if r["q"] not in (0.0, 0.20):
            continue
        ps_in_client = r["sent"] * (1 - r["bench_gap_rate"])
        for g in (0.1, 0.2, 0.3):
            keep = 1 - g
            # perturbation: in_server scales with F_c by (1-g);
            # F_c itself = forwarded - echoed, so rebuild forwarded.
            fc_p = r["F_c_reconstructed"] * keep
            in_server_p = r["in_server"] * keep
            echoed_p = r["echoed"] * keep
            forwarded_p = fc_p + echoed_p
            in_client_p = ps_in_client * keep
            s2 = score(r["sent"], echoed_p, in_client_p,
                       in_server_p, forwarded_p)
            layer_c.append({
                "tag": r["tag"], "q": r["q"], "g": g,
                "L_before": round(r["L_obs"], 4),
                "L_after": round(s2["L_obs"], 4),
                "old_fires_after": s2["old_fires"],
                "D_before": round(r["D"], 4),
                "D_after": round(s2["D"], 4),
                "D_delta": round(abs(s2["D"] - r["D"]), 6),
            })

    out = {
        "prereg": "data/2026-11-01-decomp-alert-prereg.md",
        "source_archive": "data/2026-10-28-injection-band-bench.json",
        "D_line": D_LINE, "D_line_sens": D_LINE_SENS, "old_line": OLD_LINE,
        "layerA_rows": rows,
        "layerA_by_q": by_q,
        "identities": {
            "Fc_identity_ok_n": sum(r["Fc_identity_ok"] for r in rows),
            "Fs_identity_ok_n": sum(r["Fs_identity_ok"] for r in rows),
            "in_server_eq_server_echoed_n":
                sum(r["in_server_eq_server_echoed"] for r in rows),
            "n_runs": len(rows),
            "proxy_to_shim_gap_nonzero":
                [{"tag": r["tag"], "gap": r["proxy_to_shim_gap"]}
                 for r in rows if r["proxy_to_shim_gap"]],
        },
        "bench_immunity": {
            "pearson_gap_vs_L_bench_part": round(pearson(gaps, l_bench_part), 4),
            "pearson_gap_vs_D_err": round(pearson(gaps, d_err), 4),
            "abs_D_err_median_all": round(statistics.median(
                abs(x) for x in d_err), 4),
            "abs_D_err_max_all": round(max(abs(x) for x in d_err), 4),
        },
        "layerC_perturbation": layer_c,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(json.dumps({"by_q": by_q, "identities": out["identities"],
                      "bench_immunity": out["bench_immunity"]},
                     indent=1))
    print("layerC sample:", json.dumps(layer_c[:3], indent=1))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
