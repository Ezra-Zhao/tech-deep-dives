"""Injection-band discrimination bench (2026-10-28).

Question (pre-registered before any run of this bench):
  NalFaultLossAboveInjectionBand fires when
  nal_loss_ratio{scenario="fault_sustained"} > 0.75. The injection
  parameters stay exactly as configured in run_experiment.py
  (loss 0.20 each way, delay 40 ms + jitter 30 ms, flap 0.6 s down in
  every 2.5 s period, fault_proxy seed 1234). An extra, server-side
  discard stage (the shim, c2s only, probability q) adds loss the
  injection does not explain. How large must q be before the 0.75 rule
  actually fires (detection side), and does injection alone ever cross
  0.75 (false-positive side)?

Design:
  * Live layer: real lab components on loopback --
    traffic_gen (sustained 2000 pps x 5 s = 10,000 packets, packet
    size 256, grace 1.5 s, i.e. exactly fault_sustained's traffic)
    -> fault_proxy (parameters above, unchanged)
    -> extra-drop shim (q grid)
    -> echo_server.
    Grid q in {0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60} x 4 repeats.
    Extra-drop seeds differ per run (20000 + 100*run_index + rep);
    fault_proxy seed fixed at the lab default 1234. Ports rotate per
    run. Stage decomposition is recorded per run from the three logs
    (proxy JSONL by direction+action, shim stats, server stats,
    generator summary).
  * Alert evaluation: each live run's artifacts are assembled into a
    minimal results directory and pushed through the exporter's real
    collect() code path; nal_loss_ratio{scenario="fault_sustained"}
    is parsed back out and the rule expression (> 0.75) is evaluated
    on that value -- the same object Prometheus would see.
  * Model layer: a NumPy replica of the proxy decision logic (flap
    check first, then seeded-style Bernoulli loss per leg; injected
    delay shifts the return leg's flap phase; shim drop on c2s only).
    2,000 trials per q, flap phase uniform on [0, 2.5) s. Labelled a
    model, not a measurement: its q=0 distribution is anchored against
    the live q=0 runs and the two archived runs R0/R1 (loss 0.5897 /
    0.5275). The replica uses independent RNG streams per leg where
    the live proxy shares one stream; each draw is Bernoulli(0.20)
    either way, so the loss law is unchanged -- only draw correlation
    differs, and there is none to preserve.
  * Analytic layer: per-leg survival under the two flap-correlation
    extremes and the q that solves total loss = 0.75 for a range of
    injection-only loss values.

Progress is appended to a JSONL checkpoint after every live run, so a
killed bench can be resumed without repeating finished runs
(--resume skips (q, rep) pairs already in the checkpoint).

Output: 2026-10-28-injection-band-bench.json next to this script.
"""
import argparse
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
OUT = os.path.join(HERE, "2026-10-28-injection-band-bench.json")
PROGRESS = os.path.join(HERE, "2026-10-28-injection-band-progress.jsonl")
WORK = "/tmp/nal-injection-band-20261028"

Q_GRID = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
REPS = 4
THRESHOLD = 0.75


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def proxy_log_breakdown(path):
    """Count proxy decisions by (direction, action) + final summary."""
    counts = {}
    summary = None
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


def exporter_loss_ratio(run_dir, tmp_root):
    """Assemble a minimal results dir and read nal_loss_ratio back
    through prom_exporter.collect()."""
    sys.path.insert(0, SRC)
    import prom_exporter  # noqa: E402

    rdir = os.path.join(tmp_root, "results")
    if os.path.isdir(rdir):
        shutil.rmtree(rdir)
    os.makedirs(rdir)
    shutil.copy(os.path.join(run_dir, "fault_sustained.json"), rdir)
    shutil.copy(os.path.join(run_dir, "fault_proxy_log.jsonl"), rdir)
    meta = {"run_id": time.strftime("%Y%m%d-%H%M%S"),
            "python": sys.version.split()[0], "platform": sys.platform}
    with open(os.path.join(rdir, "run_meta.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    fault_cfg = {"loss_ratio": 0.20, "delay_ms": 40.0, "jitter_ms": 30.0,
                 "flap_period_s": 2.5, "flap_down_s": 0.6}
    text = prom_exporter.collect(rdir, fault_cfg)
    value = None
    for line in text.splitlines():
        if line.startswith('nal_loss_ratio{') and \
                'scenario="fault_sustained"' in line:
            value = float(line.rsplit(" ", 1)[1])
    return value


def run_one(q, rep, run_index):
    tag = f"q{int(round(q * 100)):02d}-r{rep}"
    run_dir = os.path.join(WORK, tag)
    os.makedirs(run_dir, exist_ok=True)
    server_port = 15100 + run_index
    shim_port = 16100 + run_index
    proxy_port = 17100 + run_index
    py = sys.executable
    extra_seed = 20000 + 100 * run_index + rep

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
             "--summary-out",
             os.path.join(run_dir, "fault_sustained.json")],
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
    exp_value = None
    exp_err = None
    try:
        exp_value = exporter_loss_ratio(run_dir, WORK)
    except Exception as e:  # recorded, not hidden
        exp_err = f"{type(e).__name__}: {e}"
    loss = valid.get("loss_rate")
    rec = {
        "tag": tag, "q": q, "rep": rep, "run_index": run_index,
        "extra_seed": extra_seed, "gen_rc": gen_rc,
        "ports": {"server": server_port, "shim": shim_port,
                  "proxy": proxy_port},
        "sent": valid.get("sent"), "echoed": valid.get("echoed"),
        "lost": valid.get("lost"), "loss_rate": loss,
        "alert_fires_on_summary": (loss is not None and
                                   loss > THRESHOLD),
        "exporter_loss_ratio": exp_value,
        "alert_fires_on_exporter": (exp_value is not None and
                                    exp_value > THRESHOLD),
        "exporter_error": exp_err,
        "proxy_decisions": counts, "proxy_summary": proxy_summary,
        "shim_stats": shim_stats, "server_stats": server_stats,
        "rtt_p99_ms": (valid.get("rtt_ms") or {}).get("p99"),
    }
    return rec


def simulate(trials=2000, seed=20261028):
    import numpy as np

    rng = np.random.default_rng(seed)
    n = 10000
    t_send = np.arange(n) / 2000.0
    rows = []
    for q in Q_GRID:
        losses = np.empty(trials)
        for t in range(trials):
            phase = rng.uniform(0.0, 2.5)
            flap_c = ((t_send + phase) % 2.5) < 0.6
            surv_c = (~flap_c) & (rng.random(n) >= 0.20)
            delay1 = (40.0 + rng.uniform(0.0, 30.0, size=n)) / 1000.0
            shim_surv = rng.random(n) >= q
            t_ret = t_send + delay1
            flap_s = ((t_ret + phase) % 2.5) < 0.6
            surv_s = (~flap_s) & (rng.random(n) >= 0.20)
            echoed = surv_c & shim_surv & surv_s
            losses[t] = 1.0 - echoed.mean()
        rows.append({
            "q": q, "trials": trials,
            "loss_mean": round(float(losses.mean()), 4),
            "loss_sd": round(float(losses.std(ddof=1)), 4),
            "loss_p05": round(float(np.percentile(losses, 5)), 4),
            "loss_p50": round(float(np.percentile(losses, 50)), 4),
            "loss_p95": round(float(np.percentile(losses, 95)), 4),
            "loss_min": round(float(losses.min()), 4),
            "loss_max": round(float(losses.max()), 4),
            "p_fire": round(float((losses > THRESHOLD).mean()), 4),
            "n_fire": int((losses > THRESHOLD).sum()),
        })
    return rows


def analytic():
    per_leg_surv = 0.76 * 0.80
    out = {
        "flap_duty": 0.6 / 2.5,
        "per_leg_survival": per_leg_surv,
        "per_leg_loss": 1 - per_leg_surv,
        "e2e_loss_legs_independent": 1 - per_leg_surv ** 2,
        "e2e_loss_flap_fully_correlated": 1 - 0.76 * 0.80 ** 2,
        "q_needed_by_injection_loss": {},
    }
    for l_inj in (0.50, 0.5275, 0.55, 0.5897, 0.60, 0.6303, 0.65):
        surv = 1 - l_inj
        q_need = 1 - (1 - THRESHOLD) / surv
        out["q_needed_by_injection_loss"][str(l_inj)] = round(q_need, 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qs", default=None,
                    help="comma list override for the q grid")
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--skip-sim", action="store_true")
    args = ap.parse_args()
    qs = ([float(x) for x in args.qs.split(",")] if args.qs
          else Q_GRID)

    done = {}
    if args.resume and os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                done[(rec["q"], rec["rep"])] = rec

    live = []
    if not args.skip_live:
        os.makedirs(WORK, exist_ok=True)
        idx = 0
        for q in qs:
            for rep in range(1, args.reps + 1):
                idx += 1
                if (q, rep) in done:
                    live.append(done[(q, rep)])
                    print(f"skip done q={q} rep={rep}", flush=True)
                    continue
                rec = run_one(q, rep, idx)
                live.append(rec)
                with open(PROGRESS, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, sort_keys=True) + "\n")
                print(f"done {rec['tag']} loss={rec['loss_rate']} "
                      f"fires={rec['alert_fires_on_summary']}",
                      flush=True)
    else:
        live = list(done.values())

    by_q = {}
    for q in qs:
        rs = [r for r in live if r["q"] == q]
        vals = [r["loss_rate"] for r in rs
                if r["loss_rate"] is not None]
        if vals:
            by_q[str(q)] = {
                "n": len(vals),
                "loss_values": vals,
                "loss_mean": round(sum(vals) / len(vals), 4),
                "loss_min": min(vals), "loss_max": max(vals),
                "n_fire": sum(1 for r in rs
                              if r["alert_fires_on_summary"]),
                "fire_rate": round(
                    sum(1 for r in rs if r["alert_fires_on_summary"])
                    / len(rs), 4) if rs else None,
            }

    result = {
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "lab": LAB,
        "threshold": THRESHOLD,
        "q_grid": qs, "reps_per_q": args.reps,
        "analytic": analytic(),
        "live_by_q": by_q,
        "live_runs": sorted(live, key=lambda r: (r["q"], r["rep"])),
        "simulation": (None if args.skip_sim else simulate()),
        "archived_runs_reference": {
            "R0_20261019-171627_loss": 0.5897,
            "R1_20261019-154535_loss": 0.5275,
        },
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
