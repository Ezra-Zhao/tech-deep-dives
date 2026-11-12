"""Post-hoc summary for 2026-11-11 mem/io bench gap bench.

Reads 2026-11-11-memio-gap-bench.json, computes per-tier gap /
L / L_iso / D distributions, six-hop gap packets, RcvbufErrors
attribution, PSI manipulation checks, flap shares, the analytic
top-line gap g*, and the preregistration verdicts P1-P8. Writes
2026-11-11-memio-gap-posthoc.json. Analysis only, no reruns.
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
SRCJ = os.path.join(HERE, "2026-11-11-memio-gap-bench.json")
OUT = os.path.join(HERE, "2026-11-11-memio-gap-posthoc.json")
TIERS = ["M0", "M1", "M2", "M3", "I0", "I1", "I2", "I3"]


def med(v):
    return statistics.median(v) if v else None


def six_hop_gap_packets(rec):
    """Directional hop gaps. Proxy summary 'forwarded' mixes both
    directions, so forward legs use the per-direction decision
    counts (c2s:forward / s2c:forward) instead."""
    ps = rec.get("proxy_summary") or {}
    dec = rec.get("proxy_decisions") or {}
    sh = rec.get("shim_stats") or {}
    sv = rec.get("server_stats") or {}
    sent = rec.get("sent")
    hops = {}
    def diff(a, b):
        return (a - b) if (a is not None and b is not None) else None
    hops["gen_to_proxy"] = diff(sent, ps.get("in_client"))
    hops["proxy_to_shim"] = diff(dec.get("c2s:forward"), sh.get("in_client"))
    hops["shim_to_server"] = diff(sh.get("forwarded_client"), sv.get("received"))
    hops["server_to_shim"] = diff(sv.get("echoed"), sh.get("in_server"))
    hops["shim_to_proxy"] = diff(sh.get("forwarded_server"), ps.get("in_server"))
    hops["proxy_to_gen"] = diff(dec.get("s2c:forward"), rec.get("echoed"))
    hops["total"] = sum(v for v in hops.values() if v is not None)
    return hops


def main():
    with open(SRCJ, encoding="utf-8") as f:
        bench = json.load(f)
    runs = bench["runs"]
    for r in runs:
        r["_hops"] = six_hop_gap_packets(r)
    tiers = {}
    for t in TIERS:
        tr = [r for r in runs if r["tier"] == t]
        gaps = [r["gap"] for r in tr]
        tiers[t] = {
            "n": len(tr),
            "gap_list_pct": [round(g * 100, 4) for g in gaps],
            "gap_median": med(gaps), "gap_mean": statistics.mean(gaps),
            "gap_max": max(gaps),
            "L_max": max(r["L"] for r in tr),
            "L_iso_mean": statistics.mean(r["L_iso"] for r in tr),
            "D_max": max(r["D"] for r in tr),
            "rcvbuf_delta_total": sum(r["rcvbuf_errors_delta"] or 0 for r in tr),
            "sixhop_gap_packets_total": sum(r["_hops"]["total"] for r in tr),
            "hops_total": {k: sum(r["_hops"][k] or 0 for r in tr)
                           for k in ("gen_to_proxy", "proxy_to_shim",
                                     "shim_to_server", "server_to_shim",
                                     "shim_to_proxy", "proxy_to_gen")},
            "psi_mem_full_us_median": med([r["psi_delta"].get(
                "memory_full_total_us_delta") or 0 for r in tr]),
            "psi_io_full_us_median": med([r["psi_delta"].get(
                "io_full_total_us_delta") or 0 for r in tr]),
            "psi_mem_some_us_median": med([r["psi_delta"].get(
                "memory_some_total_us_delta") or 0 for r in tr]),
            "psi_io_some_us_median": med([r["psi_delta"].get(
                "io_some_total_us_delta") or 0 for r in tr]),
            "pswpout_delta_total": sum(r["vm_delta"].get("pswpout") or 0 for r in tr),
            "pswpin_delta_total": sum(r["vm_delta"].get("pswpin") or 0 for r in tr),
            "pgsteal_delta_total": sum(r["vm_delta"].get("pgsteal_kswapd") or 0 for r in tr),
            "pgscan_delta_total": sum(r["vm_delta"].get("pgscan_kswapd") or 0 for r in tr),
            "mem_min_kb_median": med([r["mem_samples_min_kb"] for r in tr]),
            "mem_median_kb_median": med([r["mem_samples_median_kb"] for r in tr]),
            "loadavg1_max": max((r["loadavg_before"] or [0])[0] for r in tr),
            "flap_c2s_pooled": (
                sum(r["proxy_decisions"].get("c2s:drop_flap", 0) for r in tr)
                / max(1, sum(r["proxy_decisions"].get("c2s:drop_flap", 0)
                             + r["proxy_decisions"].get("c2s:forward", 0)
                             + r["proxy_decisions"].get("c2s:drop_loss", 0)
                             for r in tr))),
            "flap_s2c_pooled": (
                sum(r["proxy_decisions"].get("s2c:drop_flap", 0) for r in tr)
                / max(1, sum(r["proxy_decisions"].get("s2c:drop_flap", 0)
                             + r["proxy_decisions"].get("s2c:forward", 0)
                             + r["proxy_decisions"].get("s2c:drop_loss", 0)
                             for r in tr))),
            "guard_killed_any": any(r["guard_killed"] for r in tr),
            "rtt_p99_median": med([r["rtt_p99_ms"] for r in tr
                                   if r["rtt_p99_ms"] is not None]),
        }
    base_runs = [r for r in runs if r["tier"] in ("M0", "I0")]
    liso_base = statistics.mean(r["L_iso"] for r in base_runs)
    g_star = 1 - (1 - 0.75) / (1 - liso_base)
    all_L_iso = statistics.mean(r["L_iso"] for r in runs)
    verdicts = {
        "P1_mem_medians_nondecreasing": (
            [tiers[t]["gap_median"] for t in ("M0", "M1", "M2", "M3")]
            == sorted(tiers[t]["gap_median"] for t in ("M0", "M1", "M2", "M3"))),
        "P2_baselines_all_le_2pct": all(
            r["gap"] <= 0.02 for r in base_runs),
        "P3_M3_median_ge_M0_plus_2pct": (
            tiers["M3"]["gap_median"] - tiers["M0"]["gap_median"] >= 0.02),
        "P4_io_nondecreasing_and_I3_ge_I0_plus_1pct": (
            [tiers[t]["gap_median"] for t in ("I0", "I1", "I2", "I3")]
            == sorted(tiers[t]["gap_median"] for t in ("I0", "I1", "I2", "I3"))
            and tiers["I3"]["gap_median"] - tiers["I0"]["gap_median"] >= 0.01),
        "P5_rcvbuf_attribution_for_gap_tiers": {},
        "P6_D_all_le_0.03": all(r["D"] <= 0.03 for r in runs),
        "P7_no_old_fire": not any(r["old_fires"] for r in runs),
        "P8a_mem_psi_M3_ge_3x_M0": (
            (tiers["M3"]["psi_mem_full_us_median"] or 0)
            >= 3 * max(1, tiers["M0"]["psi_mem_full_us_median"] or 0)),
        "P8b_io_psi_I3_ge_3x_I0": (
            (tiers["I3"]["psi_io_full_us_median"] or 0)
            >= 3 * max(1, tiers["I0"]["psi_io_full_us_median"] or 0)),
    }
    for t in TIERS:
        if tiers[t]["gap_median"] > 0.005:
            tot = tiers[t]["sixhop_gap_packets_total"]
            verdicts["P5_rcvbuf_attribution_for_gap_tiers"][t] = (
                tiers[t]["rcvbuf_delta_total"] >= 0.5 * tot if tot else None)
    nonzero_runs = [r["tag"] for r in runs if r["gap"] and r["gap"] > 0]
    identity_fail = []
    for r in runs:
        if r["exporter_error"]:
            identity_fail.append((r["tag"], r["exporter_error"]))
        elif abs((r["exporter"].get("L") or 0) - (r["L"] or 0)) > 1e-9:
            identity_fail.append((r["tag"], "L mismatch"))
    out = {
        "ma0_median_kb": bench["ma0_median_kb"],
        "ma0_mb": bench["ma0_median_kb"] / 1024.0,
        "tiers_spec": bench["tiers"],
        "iohog_ops_by_tier": bench.get("iohog_ops_by_tier"),
        "tiers": tiers,
        "g_star_base": g_star, "L_iso_base_mean": liso_base,
        "L_iso_all_mean": all_L_iso,
        "nonzero_gap_runs": nonzero_runs,
        "identity_failures": identity_fail,
        "verdicts": verdicts,
        "total_runs": len(runs),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
