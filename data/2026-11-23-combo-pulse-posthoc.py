"""Posthoc summary for the 2026-11-23 combo/pulse bench.

Reads 2026-11-23-combo-pulse-bench.json (raw runs only) and writes
2026-11-23-combo-pulse-posthoc.json: per-arm gap median/max, gap
packets vs RcvbufErrors deltas, D max, L ranges, guard events,
pulse manipulation checks (pulse-off times, MemAvailable recovery
after pulse-off, PSI deltas, loadavg), and the pre-registered
prediction verdicts P1..P6. Definitions frozen in the prereg.
"""
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "2026-11-23-combo-pulse-bench.json")
OUT = os.path.join(HERE, "2026-11-23-combo-pulse-posthoc.json")


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def sixhop_gap_packets(rec):
    """Sum of nonnegative per-hop packet shortfalls, from the
    recorded counters (same accounting as previous rounds)."""
    ps = rec.get("proxy_summary") or {}
    dec = rec.get("proxy_decisions") or {}
    shim = rec.get("shim_stats") or {}
    srv = rec.get("server_stats") or {}
    sent = rec.get("sent")
    echoed = rec.get("echoed")
    hops = {}

    def diff(a, b):
        if a is None or b is None:
            return None
        return max(a - b, 0)

    hops["gen_to_proxy"] = diff(sent, ps.get("in_client"))
    c2s_fwd = dec.get("c2s:forward")
    hops["proxy_to_shim"] = diff(c2s_fwd, shim.get("in_client"))
    hops["shim_to_server"] = diff(shim.get("forwarded_server"),
                                  srv.get("received_total"))
    hops["server_to_shim"] = diff(srv.get("echoed"), shim.get("in_server"))
    s2c_in = sum(dec.get(f"s2c:{a}", 0)
                 for a in ("forward", "drop_loss", "drop_flap"))
    hops["shim_to_proxy"] = diff(shim.get("forwarded_client"), s2c_in)
    hops["proxy_to_gen"] = diff(dec.get("s2c:forward"), echoed)
    total = sum(v for v in hops.values() if v is not None)
    return hops, total


def pulse_segments(rec):
    """MemAvailable medians before/after the pulse-off moment,
    from the timestamped samples (t relative to generator start)."""
    off = rec.get("pulse_off_elapsed_s")
    samples = rec.get("mem_samples") or []
    if off is None:
        return {}
    during = [kb for t, kb in samples if 0 <= t < off]
    after = [kb for t, kb in samples if off <= t <= 6.5]
    return {
        "mem_median_during_pulse_kb": int(med(during)) if during else None,
        "mem_median_after_pulse_kb": int(med(after)) if after else None,
        "n_during": len(during), "n_after": len(after),
    }


def main():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    runs = data["runs"]
    arms = {}
    for rec in runs:
        arms.setdefault(rec["arm"], []).append(rec)
    out_arms = {}
    for arm, rs in sorted(arms.items()):
        gaps = [r["gap"] for r in rs]
        hops_total = 0
        hops_by_name = {}
        for r in rs:
            h, tot = sixhop_gap_packets(r)
            hops_total += tot
            for k, v in h.items():
                if v is not None:
                    hops_by_name[k] = hops_by_name.get(k, 0) + v
        segs = [pulse_segments(r) for r in rs]
        out_arms[arm] = {
            "n": len(rs),
            "spec": rs[0]["pressure_spec"],
            "gap_list_pct": [round(g * 100, 4) for g in gaps],
            "gap_median": med(gaps),
            "gap_max": max(gaps),
            "gap_mean": statistics.mean(gaps),
            "gap_packets_total": sum(r["gap_packets"] or 0 for r in rs),
            "sixhop_gap_packets_total": hops_total,
            "sixhop_by_hop_total": hops_by_name,
            "rcvbuf_delta_total": sum(r["rcvbuf_errors_delta"] or 0 for r in rs),
            "in_errors_delta_total": sum(r["in_errors_delta"] or 0 for r in rs),
            "D_list": [r["D"] for r in rs],
            "D_max": max(r["D"] for r in rs if r["D"] is not None),
            "L_list": [r["L"] for r in rs],
            "L_min": min(r["L"] for r in rs),
            "L_max": max(r["L"] for r in rs),
            "L_iso_mean": statistics.mean(r["L_iso"] for r in rs),
            "old_fires_any": any(r["old_fires"] for r in rs),
            "guard_killed_runs": [r["tag"] for r in rs if r["guard_killed"]],
            "iohogs_ops_total": sum(r["iohogs_ops"] or 0 for r in rs),
            "mem_min_kb_median": med([r["mem_samples_min_kb"] for r in rs]),
            "loadavg1_max": max((r["loadavg_before"] or [0])[0] for r in rs),
            "psi_io_full_us_median": med(
                [r["psi_delta"].get("io_full_total_us_delta") for r in rs]),
            "psi_mem_full_us_median": med(
                [r["psi_delta"].get("memory_full_total_us_delta") for r in rs]),
            "psi_cpu_some_us_median": med(
                [r["psi_delta"].get("cpu_some_total_us_delta") for r in rs]),
            "rtt_p99_median": med([r["rtt_p99_ms"] for r in rs]),
            "flap_c2s_pooled": (
                sum(r["proxy_decisions"].get("c2s:drop_flap", 0) for r in rs)
                / max(sum(sum(r["proxy_decisions"].get(f"c2s:{a}", 0)
                              for a in ("forward", "drop_loss", "drop_flap"))
                          for r in rs), 1)),
            "pulse_off_list_s": [r["pulse_off_elapsed_s"] for r in rs],
            "pulse_segments": segs,
            "identity_failures": [
                r["tag"] for r in rs
                if r["F_c"] is not None and r["F_c"] < 0],
        }
    c0 = out_arms["C0"]
    g_star = 1 - 0.25 / (1 - c0["L_iso_mean"]) if c0["L_iso_mean"] else None
    # g* solves 1-(1-g)(1-L_iso)=0.75 -> g = 1 - 0.25/(1-L_iso)
    verdicts = {
        "P1_C1_median_lt_20pct_and_max_lt_29.8pct": (
            out_arms["C1"]["gap_median"] < 0.20
            and out_arms["C1"]["gap_max"] < 0.298),
        "P2_C0_all_le_2pct": all(
            g <= 0.02 for g in
            [x / 100 for x in c0["gap_list_pct"]]),
        "P3_C1_median_ge_C0_plus_1pct": (
            out_arms["C1"]["gap_median"] >= c0["gap_median"] + 0.01),
        "P4_pulse_median_between": (
            c0["gap_median"] <= out_arms["C2"]["gap_median"]
            <= out_arms["C1"]["gap_median"]),
        "P5_rcvbuf_attribution": {},
        "P6_D_all_le_0.03_and_no_old": (
            all(a["D_max"] <= 0.03 for a in out_arms.values())
            and not any(a["old_fires_any"] for a in out_arms.values())),
    }
    for arm, a in out_arms.items():
        if a["gap_median"] > 0.005:
            verdicts["P5_rcvbuf_attribution"][arm] = (
                a["rcvbuf_delta_total"]
                >= 0.5 * a["sixhop_gap_packets_total"])
    manip = {
        "C1_mem_min_median_at_least_300MB_below_C0": (
            (c0["mem_min_kb_median"] - out_arms["C1"]["mem_min_kb_median"])
            >= 300 * 1024),
        "C1_psi_io_full_median_ge_3x_C0": (
            out_arms["C1"]["psi_io_full_us_median"]
            >= 3 * max(out_arms["C0"]["psi_io_full_us_median"], 1)),
        "C2_psi_io_full_median_lt_C1": (
            out_arms["C2"]["psi_io_full_us_median"]
            < out_arms["C1"]["psi_io_full_us_median"]),
        "pulse_off_within_2.0_plusminus_0.5s_all": all(
            off is not None and 1.5 <= off <= 2.5
            for arm in ("C2", "C3")
            for off in out_arms[arm]["pulse_off_list_s"]),
        "C2_mem_recovers_after_pulse": all(
            (s.get("mem_median_after_pulse_kb") or 0)
            > (s.get("mem_median_during_pulse_kb") or 0)
            for s in out_arms["C2"]["pulse_segments"] if s),
    }
    result = {
        "total_runs": len(runs),
        "ma0_median_kb": data.get("ma0_median_kb"),
        "g_star_from_C0_L_iso": g_star,
        "arms": out_arms,
        "verdicts": verdicts,
        "manipulation_checks": manip,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
