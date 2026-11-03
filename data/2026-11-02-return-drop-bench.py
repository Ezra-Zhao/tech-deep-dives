"""Return-drop control bench (2026-11-02).

Pre-registration: data/2026-11-02-return-drop-prereg.md (frozen before
any run). Control for 2026-10-28 (forward drop) and 2026-11-01
(decomposition-aware alert): identical components, injection
parameters, traffic and q grid; the only change is the extra-drop
shim drops the server-to-client direction (the echoes) instead of
the client-to-server direction (the requests).

Questions, in the preregistration's order:
  P1 q=0 anchor vs the forward bench.
  P2 Does the OLD rule (end-to-end loss > 0.75) keep the same
     isolated detection threshold (fires 0/4 at q=0.40, 4/4 at 0.50)?
  P3 Does the segment rate D = 1 - in_server/F_c read the return
     drop rate, and does CAND (D > 0.10) fire as in the forward case?
  P4 Does the segment split flip: D_srv ~ 0 and D_ret ~ q here,
     mirroring the forward bench (D_srv = D, D_ret = 0 exactly)?
  P5 Server work: server_echoed ~ F_c here vs ~ F_c*(1-q) forward.

Rule inputs are parsed from the exporter's real collect()
exposition text. Raw logs are kept per run for identity checks and
attribution only. Progress is appended to a JSONL checkpoint after
every run (resumable: rerunning skips (q, rep) pairs already done).

Output: 2026-11-02-return-drop-bench.json next to this script,
including a per-q comparison block against the archived forward
bench (2026-10-28-injection-band-bench.json, recomputed from its
per-run records with the same formulas).
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.expanduser("~/workspace/oxide-proofs/net-assurance-lab")
SRC = os.path.join(LAB, "src")
SHIM = os.path.join(HERE, "2026-11-02-return-drop-shim.py")
FORWARD = os.path.join(HERE, "2026-10-28-injection-band-bench.json")
OUT = os.path.join(HERE, "2026-11-02-return-drop-bench.json")
PROGRESS = os.path.join(HERE, "2026-11-02-return-drop-progress.jsonl")
WORK = "/tmp/nal-return-drop-20261102"
Q_GRID = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
REPS = 4
D_LINE = 0.10
OLD_LINE = 0.75


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def proxy_log_breakdown(path):
    counts, summary = {}, None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec.get("summary"), dict):
                    summary = rec["summary"]
                    continue
                key = f"{rec.get('dir')}:{rec.get('action')}"
                counts[key] = counts.get(key, 0) + 1
    except OSError:
        pass
    return counts, summary


def exporter_quantities(run_dir, tmp_root):
    sys.path.insert(0, SRC)
    import prom_exporter

    rdir = os.path.join(tmp_root, "results")
    if os.path.isdir(rdir):
        shutil.rmtree(rdir)
    os.makedirs(rdir)
    shutil.copy(os.path.join(run_dir, "fault_sustained.json"), rdir)
    shutil.copy(os.path.join(run_dir, "fault_proxy_log.jsonl"), rdir)
    srv = os.path.join(run_dir, "server_stats.json")
    if os.path.exists(srv):
        shutil.copy(srv, os.path.join(
            rdir, "server_stats_fault_sustained.json"))
    meta = {"run_id": time.strftime("%Y%m%d-%H%M%S"),
            "python": sys.version.split()[0], "platform": sys.platform}
    with open(os.path.join(rdir, "run_meta.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    fault_cfg = {"loss_ratio": 0.20, "delay_ms": 40.0, "jitter_ms": 30.0,
                 "flap_period_s": 2.5, "flap_down_s": 0.6}
    text = prom_exporter.collect(rdir, fault_cfg)
    vals = {"proxy": {}, "server": {}}
    for line in text.splitlines():
        if line.startswith('nal_packets_sent_total{') and \
                'fault_sustained' in line:
            vals["sent"] = float(line.rsplit(" ", 1)[1])
        elif line.startswith('nal_packets_echoed_total{') and \
                'fault_sustained' in line:
            vals["echoed"] = float(line.rsplit(" ", 1)[1])
        elif line.startswith('nal_loss_ratio{') and \
                'fault_sustained' in line:
            vals["loss_ratio"] = float(line.rsplit(" ", 1)[1])
        elif line.startswith('nal_fault_proxy_packets_total{'):
            kind = line.split('kind="')[1].split('"')[0]
            vals["proxy"][kind] = float(line.rsplit(" ", 1)[1])
        elif line.startswith('nal_server_packets_total{') and \
                'fault_sustained' in line:
            kind = line.split('kind="')[1].split('"')[0]
            vals["server"][kind] = float(line.rsplit(" ", 1)[1])
    return vals


def derived(ev, counts, shim, server_raw):
    p = ev["proxy"]
    fc = p["forwarded"] - ev["echoed"]
    in_srv = p["in_server"]
    srv_recv = ev["server"].get("received_total")
    srv_echo = ev["server"].get("echoed")
    out = {"F_c": fc}
    out["D"] = 1.0 - in_srv / fc if fc else None
    out["D_srv"] = (1.0 - srv_recv / fc) if fc and srv_recv is not None \
        else None
    out["D_ret"] = (1.0 - in_srv / srv_echo) if srv_echo else None
    out["L_iso"] = 1.0 - ev["echoed"] / p["in_client"] \
        if p.get("in_client") else None
    out["cand_fires"] = out["D"] is not None and out["D"] > D_LINE
    out["old_fires"] = ev["loss_ratio"] > OLD_LINE
    out["old_iso_fires"] = out["L_iso"] is not None and \
        out["L_iso"] > OLD_LINE
    out["bench_gap_rate"] = 1.0 - p["in_client"] / ev["sent"] \
        if ev.get("sent") else None
    shim_in_srv = (shim or {}).get("in_server")
    dropped = (shim or {}).get("dropped_extra")
    out["shim_return_measured"] = (dropped / shim_in_srv) \
        if shim_in_srv else None
    out["identities"] = {
        "Fc_eq_c2s_forward": fc == counts.get("c2s:forward"),
        "echoed_eq_s2c_forward": ev["echoed"] == counts.get("s2c:forward"),
        "proxy_in_server_eq_shim_forwarded_server":
            in_srv == (shim or {}).get("forwarded_server"),
        "server_received_eq_shim_forwarded_client":
            srv_recv == (shim or {}).get("forwarded_client"),
        "shim_in_server_eq_server_echoed":
            shim_in_srv == srv_echo,
        "server_raw_matches_exporter":
            (server_raw or {}).get("received_total") == srv_recv and
            (server_raw or {}).get("echoed") == srv_echo,
    }
    out["hop_gaps"] = {
        "proxy_to_shim_c2s": counts.get("c2s:forward", 0) -
            ((shim or {}).get("in_client") or 0),
        "shim_to_server": ((shim or {}).get("forwarded_client") or 0) -
            (srv_recv or 0),
        "server_to_shim_s2c": (srv_echo or 0) - (shim_in_srv or 0),
        "shim_to_proxy_s2c": ((shim or {}).get("forwarded_server") or 0) -
            in_srv,
    }
    return out


def run_one(q, rep, run_index):
    tag = f"q{int(round(q * 100)):02d}-r{rep}"
    run_dir = os.path.join(WORK, tag)
    os.makedirs(run_dir, exist_ok=True)
    server_port = 15300 + run_index
    shim_port = 16300 + run_index
    proxy_port = 17300 + run_index
    py = sys.executable
    extra_seed = 42000 + 100 * run_index + rep

    srv = subprocess.Popen(
        [py, os.path.join(SRC, "echo_server.py"), "--port",
         str(server_port), "--stats-out",
         os.path.join(run_dir, "server_stats.json")],
        stdout=open(os.path.join(run_dir, "server.log"), "w"),
        stderr=subprocess.STDOUT)
    time.sleep(0.4)
    shim = subprocess.Popen(
        [py, SHIM, "--listen-port", str(shim_port), "--target-port",
         str(server_port), "--q", str(q), "--seed", str(extra_seed),
         "--stats-out", os.path.join(run_dir, "shim_stats.json")],
        stdout=open(os.path.join(run_dir, "shim.log"), "w"),
        stderr=subprocess.STDOUT)
    time.sleep(0.3)
    proxy = subprocess.Popen(
        [py, os.path.join(SRC, "fault_proxy.py"), "--listen-port",
         str(proxy_port), "--target-port", str(shim_port),
         "--loss", "0.20", "--delay-ms", "40", "--jitter-ms", "30",
         "--flap-period-s", "2.5", "--flap-down-s", "0.6",
         "--seed", "1234", "--log-out",
         os.path.join(run_dir, "fault_proxy_log.jsonl")],
        stdout=open(os.path.join(run_dir, "proxy.log"), "w"),
        stderr=subprocess.STDOUT)
    time.sleep(0.5)
    gen_rc = None
    try:
        r = subprocess.run(
            [py, os.path.join(SRC, "traffic_gen.py"), "--mode",
             "sustained", "--rate-pps", "2000", "--duration-s", "5",
             "--port", str(proxy_port), "--csv-out",
             os.path.join(run_dir, "fault_sustained.csv"),
             "--summary-out", os.path.join(run_dir, "fault_sustained.json")],
            capture_output=True, text=True, timeout=60)
        gen_rc = r.returncode
    finally:
        time.sleep(0.3)
        proxy.send_signal(signal.SIGINT)
        try:
            proxy.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proxy.kill()
        shim.send_signal(signal.SIGTERM)
        try:
            shim.wait(timeout=10)
        except subprocess.TimeoutExpired:
            shim.kill()
        srv.send_signal(signal.SIGTERM)
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
    time.sleep(0.2)

    summary = load_json(os.path.join(run_dir, "fault_sustained.json"))
    valid = (summary or {}).get("valid_packets") or {}
    counts, proxy_summary = proxy_log_breakdown(
        os.path.join(run_dir, "fault_proxy_log.jsonl"))
    shim_stats = load_json(os.path.join(run_dir, "shim_stats.json"))
    server_stats = load_json(os.path.join(run_dir, "server_stats.json"))
    ev, ev_err = None, None
    try:
        ev = exporter_quantities(run_dir, WORK)
    except Exception as e:
        ev_err = f"{type(e).__name__}: {e}"
    rec = {"tag": tag, "q": q, "rep": rep, "run_index": run_index,
           "extra_seed": extra_seed, "gen_rc": gen_rc,
           "exporter": ev, "exporter_error": ev_err,
           "gen_loss_rate": valid.get("loss_rate"),
           "proxy_decisions": counts, "proxy_summary": proxy_summary,
           "shim_stats": shim_stats, "server_stats": server_stats}
    if ev:
        rec.update(derived(ev, counts, shim_stats, server_stats))
        rec["exporter_matches_gen_loss"] = abs(
            ev["loss_ratio"] - (valid.get("loss_rate") or -1)) < 1e-12
    return rec


def forward_reference():
    d = load_json(FORWARD)
    if not d:
        return None
    per_q = {}
    for r in d["live_runs"]:
        cnt = r["proxy_decisions"]
        summ = r["proxy_summary"] or {}
        fc = cnt.get("c2s:forward")
        in_srv = summ.get("in_server")
        srv = r["server_stats"] or {}
        iso = 1.0 - r["echoed"] / summ["in_client"] \
            if r.get("echoed") is not None and summ.get("in_client") \
            else None
        row = {
            "L": r["loss_rate"], "L_iso": iso,
            "D": 1.0 - in_srv / fc if fc and in_srv is not None else None,
            "D_srv": 1.0 - srv["received_total"] / fc
            if fc and srv.get("received_total") is not None else None,
            "D_ret": 1.0 - in_srv / srv["echoed"]
            if in_srv and srv.get("echoed") else None,
            "F_c": fc, "server_echoed": srv.get("echoed"),
            "old_iso_fires": iso is not None and iso > OLD_LINE,
        }
        per_q.setdefault(str(r["q"]), []).append(row)
    out = {}
    for q, rows in per_q.items():
        def mean(key):
            vals = [x[key] for x in rows if x.get(key) is not None]
            return round(sum(vals) / len(vals), 4) if vals else None
        out[q] = {"n": len(rows), "L_mean": mean("L"),
                  "L_iso_mean": mean("L_iso"), "D_mean": mean("D"),
                  "D_srv_mean": mean("D_srv"), "D_ret_mean": mean("D_ret"),
                  "F_c_mean": mean("F_c"),
                  "server_echoed_mean": mean("server_echoed"),
                  "old_iso_n_fire": sum(1 for x in rows
                                        if x["old_iso_fires"])}
    return out


def summarize(live):
    by_q = {}
    for q in Q_GRID:
        rs = [r for r in live if r["q"] == q]
        def vals(key):
            return [r[key] for r in rs if r.get(key) is not None]
        def mean(key):
            v = vals(key)
            return round(sum(v) / len(v), 4) if v else None
        by_q[str(q)] = {
            "n": len(rs),
            "L_values": vals("gen_loss_rate"), "L_mean": mean("gen_loss_rate"),
            "L_iso_values": [round(v, 4) for v in vals("L_iso")],
            "L_iso_mean": mean("L_iso"),
            "D_values": [round(v, 4) for v in vals("D")],
            "D_mean": mean("D"),
            "D_srv_values": [round(v, 4) for v in vals("D_srv")],
            "D_srv_mean": mean("D_srv"),
            "D_ret_values": [round(v, 4) for v in vals("D_ret")],
            "D_ret_mean": mean("D_ret"),
            "cand_n_fire": sum(1 for r in rs if r.get("cand_fires")),
            "old_n_fire": sum(1 for r in rs if r.get("old_fires")),
            "old_iso_n_fire": sum(1 for r in rs if r.get("old_iso_fires")),
            "F_c_mean": mean("F_c"),
            "server_echoed_mean": mean("server_stats") if False else None,
            "bench_gap_max": max((r.get("bench_gap_rate") or 0)
                                 for r in rs) if rs else None,
        }
        se = [ (r.get("server_stats") or {}).get("echoed") for r in rs]
        se = [x for x in se if x is not None]
        by_q[str(q)]["server_echoed_mean"] = round(sum(se) / len(se), 1) \
            if se else None
    errs = [abs(r["D"] - r["shim_return_measured"]) for r in live
            if r.get("D") is not None and
            r.get("shim_return_measured") is not None]
    errs_sorted = sorted(errs)
    med = errs_sorted[len(errs_sorted) // 2] if errs_sorted else None
    if errs_sorted and len(errs_sorted) % 2 == 0:
        med = (errs_sorted[len(errs_sorted)//2 - 1] +
               errs_sorted[len(errs_sorted)//2]) / 2
    dret_errs = sorted(abs(r["D_ret"] - r["q"]) for r in live
                       if r.get("D_ret") is not None)
    dret_med = None
    if dret_errs:
        n = len(dret_errs)
        dret_med = dret_errs[n // 2] if n % 2 else \
            (dret_errs[n//2 - 1] + dret_errs[n//2]) / 2
    return by_q, {"abs_D_err_vs_shim_median": med,
                   "abs_D_err_vs_shim_max": max(errs) if errs else None,
                   "abs_Dret_err_vs_q_median": dret_med}


def main():
    done = {}
    if os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                done[(rec["q"], rec["rep"])] = rec
    live = []
    os.makedirs(WORK, exist_ok=True)
    idx = 0
    for q in Q_GRID:
        for rep in range(1, REPS + 1):
            idx += 1
            if (q, rep) in done:
                live.append(done[(q, rep)])
                print(f"skip done q={q} rep={rep}", flush=True)
                continue
            rec = run_one(q, rep, idx)
            live.append(rec)
            with open(PROGRESS, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            print(f"done {rec['tag']} L={rec.get('gen_loss_rate')} "
                  f"D={rec.get('D')} cand={rec.get('cand_fires')} "
                  f"old={rec.get('old_fires')}", flush=True)
    by_q, errs = summarize(live)
    result = {"generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
              "prereg": "data/2026-11-02-return-drop-prereg.md",
              "D_line": D_LINE, "old_line": OLD_LINE,
              "q_grid": Q_GRID, "reps_per_q": REPS,
              "return_by_q": by_q, "error_summary": errs,
              "forward_reference_by_q": forward_reference(),
              "return_runs": sorted(live, key=lambda r: (r["q"], r["rep"]))}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
