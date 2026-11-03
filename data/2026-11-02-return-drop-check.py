"""Post-hoc numeric check for the 2026-11-02 return-drop article.

Recomputes every number the article cites from the bench JSON and
the archived forward bench, prints PASS/FAIL per item. Run after the
bench finishes; the article may only cite numbers that pass here.
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ret = json.load(open(os.path.join(
    HERE, "2026-11-02-return-drop-bench.json"), encoding="utf-8"))
fwd_ref = ret["forward_reference_by_q"]
byq = ret["return_by_q"]
runs = ret["return_runs"]

checks = []


def chk(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


# identities and exporter agreement across all 28 runs
ident_ok = sum(1 for r in runs if all(r["identities"].values()))
chk("identities_all_28", ident_ok == 28, f"{ident_ok}/28 runs all-true")
exp_ok = sum(1 for r in runs if r.get("exporter_matches_gen_loss"))
chk("exporter_eq_gen_loss_28", exp_ok == 28, f"{exp_ok}/28")

# hop gaps: report max abs per hop
for hop in ("proxy_to_shim_c2s", "shim_to_server", "server_to_shim_s2c",
            "shim_to_proxy_s2c"):
    mx = max(abs(r["hop_gaps"][hop]) for r in runs)
    print(f"  hop {hop}: max abs gap = {mx}")

# P1
q0 = byq["0.0"]
chk("P1_anchor", abs(q0["L_mean"] - fwd_ref["0.0"]["L_mean"]) <= 0.02
    and all(d <= 0.03 for d in q0["D_values"]),
    f"ret L_mean={q0['L_mean']} fwd={fwd_ref['0.0']['L_mean']} "
    f"D={q0['D_values']}")

# P2
chk("P2_iso_threshold",
    byq["0.4"]["old_iso_n_fire"] == 0 and byq["0.5"]["old_iso_n_fire"] == 4
    and byq["0.6"]["old_iso_n_fire"] == 4,
    f"iso fires: 0.4={byq['0.4']['old_iso_n_fire']}/4 "
    f"0.5={byq['0.5']['old_iso_n_fire']}/4 0.6={byq['0.6']['old_iso_n_fire']}/4")

# P3
med = ret["error_summary"]["abs_D_err_vs_shim_median"]
chk("P3_D_reads_return", med is not None and med <= 0.02
    and all(byq[str(q)]["cand_n_fire"] == 4
            for q in (0.2, 0.3, 0.4, 0.5, 0.6))
    and byq["0.0"]["cand_n_fire"] == 0,
    f"median|D-shim|={med} max={ret['error_summary']['abs_D_err_vs_shim_max']}")

# P4
dsrv_means = [byq[str(q)]["D_srv_mean"] for q in
              (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6)]
dret_med = ret["error_summary"]["abs_Dret_err_vs_q_median"]
chk("P4_flip", all(m <= 0.03 for m in dsrv_means) and dret_med <= 0.02,
    f"D_srv means={dsrv_means} median|D_ret-q|={dret_med}")
fwd_dret0 = all(abs(fwd_ref[str(q)]["D_ret_mean"]) < 0.0001
                for q in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6))
chk("P4_forward_mirror", fwd_dret0,
    "forward D_ret means all 0.0 in archived bench")

# P5
r60, f60 = byq["0.6"], fwd_ref["0.6"]
gap60 = r60["server_echoed_mean"] - f60["server_echoed_mean"]
chk("P5_server_work", gap60 >= 0.40 * r60["F_c_mean"],
    f"ret srv_echo={r60['server_echoed_mean']} fwd={f60['server_echoed_mean']} "
    f"gap={gap60:.0f} ret F_c_mean={r60['F_c_mean']}")

# algebraic identity (1-D) = (1-D_srv)(1-D_ret) per run
alg = max(abs((1 - r["D"]) - (1 - r["D_srv"]) * (1 - r["D_ret"]))
          for r in runs)
chk("algebra_split_identity", alg < 1e-9, f"max dev {alg:.2e}")

# per-q return vs forward L means (deployment and isolated)
for q in ("0.0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6"):
    print(f"  q={q}: ret L={byq[q]['L_mean']} (fwd {fwd_ref[q]['L_mean']}) "
          f"ret L_iso={byq[q]['L_iso_mean']} (fwd {fwd_ref[q]['L_iso_mean']}) "
          f"ret D={byq[q]['D_mean']} D_srv={byq[q]['D_srv_mean']} "
          f"D_ret={byq[q]['D_ret_mean']} | fwd D={fwd_ref[q]['D_mean']} "
          f"srvEcho ret={byq[q]['server_echoed_mean']} "
          f"fwd={fwd_ref[q]['server_echoed_mean']}")

n_fail = sum(1 for _, ok, _ in checks if not ok)
print(f"\n{len(checks) - n_fail}/{len(checks)} checks passed")
