"""Decomposition-aware alert bench, layer B: fresh live holdout (2026-11-01).

Pre-registration: data/2026-11-01-decomp-alert-prereg.md.
Same real components as 2026-10-28 (traffic_gen -> fault_proxy ->
extra-drop shim -> echo_server, injection parameters unchanged),
new extra-drop seeds (base 31000), q in {0, 0.15, 0.30} x 4 reps.
q=0.15/0.30 sit inside OLD's blind zone (q*~0.47) and above CAND's
frozen line (D > 0.10): the two rules make opposite predictions.

Rule inputs are parsed from the exporter's real collect() exposition
text -- the exact object Prometheus would scrape -- not from the raw
logs. Raw logs are kept per run for identity verification and
attribution post-mortems only.

Progress appended to a JSONL checkpoint after every run (resumable).
Output: 2026-11-01-decomp-alert-live.json next to this script.
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
SHIM = os.path.join(HERE, "2026-10-28-injection-band-shim.py")
OUT = os.path.join(HERE, "2026-11-01-decomp-alert-live.json")
PROGRESS = os.path.join(HERE, "2026-11-01-decomp-alert-live-progress.jsonl")
WORK = "/tmp/nal-decomp-alert-20261101"
Q_GRID = [0.0, 0.15, 0.30]
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
    """Push run artifacts through prom_exporter.collect() and parse the
    five quantities the candidate rule is allowed to use, plus
    nal_loss_ratio, from the exposition text."""
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
        shutil.copy(srv, os.path.join(rdir, "server_stats_fault_sustained.json"))
    meta = {"run_id": time.strftime("%Y%m%d-%H%M%S"),
            "python": sys.version.split()[0], "platform": sys.platform}
    with open(os.path.join(rdir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    fault_cfg = {"loss_ratio": 0.20, "delay_ms": 40.0, "jitter_ms": 30.0,
                 "flap_period_s": 2.5, "flap_down_s": 0.6}
    text = prom_exporter.collect(rdir, fault_cfg)
    vals = {"proxy": {}}
    for line in text.splitlines():
        if line.startswith('nal_packets_sent_total{') and 'fault_sustained' in line:
            vals["sent"] = float(line.rsplit(" ", 1)[1])
        elif line.startswith('nal_packets_echoed_total{') and 'fault_sustained' in line:
            vals["echoed"] = float(line.rsplit(" ", 1)[1])
        elif line.startswith('nal_loss_ratio{') and 'fault_sustained' in line:
            vals["loss_ratio"] = float(line.rsplit(" ", 1)[1])
        elif line.startswith('nal_fault_proxy_packets_total{'):
            kind = line.split('kind="')[1].split('"')[0]
            vals["proxy"][kind] = float(line.rsplit(" ", 1)[1])
    return vals


def run_one(q, rep, run_index):
    tag = f"q{int(round(q * 100)):02d}-r{rep}"
    run_dir = os.path.join(WORK, tag)
    os.makedirs(run_dir, exist_ok=True)
    server_port = 15200 + run_index
    shim_port = 16200 + run_index
    proxy_port = 17200 + run_index
    py = sys.executable
    extra_seed = 31000 + 100 * run_index + rep

    srv = subprocess.Popen(
        [py, os.path.join(SRC, "echo_server.py"), "--port", str(server_port),
         "--stats-out", os.path.join(run_dir, "server_stats.json")],
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
            [py, os.path.join(SRC, "traffic_gen.py"), "--mode", "sustained",
             "--rate-pps", "2000", "--duration-s", "5", "--port",
             str(proxy_port), "--csv-out",
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
        p = ev["proxy"]
        fc = p["forwarded"] - ev["echoed"]
        d = 1.0 - p["in_server"] / fc if fc else None
        rec.update({
            "F_c": fc, "D": d,
            "cand_fires": (d is not None and d > D_LINE),
            "old_fires": ev["loss_ratio"] > OLD_LINE,
            "exporter_matches_gen_loss":
                abs(ev["loss_ratio"] - (valid.get("loss_rate") or -1)) < 1e-12,
            "Fc_identity_ok": fc == counts.get("c2s:forward"),
            "Fs_identity_ok": ev["echoed"] == counts.get("s2c:forward"),
            "bench_gap_rate": 1.0 - p["in_client"] / ev["sent"],
            "proxy_to_shim_gap": (counts.get("c2s:forward") -
                                  (shim_stats or {}).get("in_client", 0)),
        })
    return rec


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
            print(f"done {rec['tag']} D={rec.get('D')} "
                  f"cand={rec.get('cand_fires')} old={rec.get('old_fires')} "
                  f"L={rec.get('gen_loss_rate')}", flush=True)
    by_q = {}
    for q in Q_GRID:
        rs = [r for r in live if r["q"] == q]
        by_q[str(q)] = {
            "n": len(rs),
            "D_values": [round(r["D"], 4) for r in rs if r.get("D") is not None],
            "cand_n_fire": sum(1 for r in rs if r.get("cand_fires")),
            "old_n_fire": sum(1 for r in rs if r.get("old_fires")),
            "loss_values": [r["gen_loss_rate"] for r in rs],
            "bench_gap_max": max((r.get("bench_gap_rate") or 0) for r in rs),
        }
    result = {"generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
              "prereg": "data/2026-11-01-decomp-alert-prereg.md",
              "D_line": D_LINE, "old_line": OLD_LINE,
              "q_grid": Q_GRID, "reps_per_q": REPS,
              "live_by_q": by_q, "live_runs": live}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
