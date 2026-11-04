"""Bench-load gap bench (2026-11-03).

Pre-registered in 2026-11-03-load-gap-prereg.md (frozen before runs).
Question: how does the generator->proxy bench gap
(1 - in_client/sent, first seen drifting 0-29.8% across the
2026-10-28 runs and sitting at exactly 0 in the quiet 2026-11-01/02
batches) move when host CPU load is controlled in tiers?

Design:
  * Live chain identical to 2026-10-28: traffic_gen (sustained
    2000 pps x 5 s = 10,000 packets) -> fault_proxy (loss 0.20,
    delay 40 ms, jitter 30 ms, flap 0.6/2.5, seed 1234, unchanged)
    -> extra-drop shim at q=0 (counts, never drops) -> echo_server.
  * Load tiers by number of pure-CPU busy-loop hog processes on
    this 4-core host: L0=0, L1=2, L2=4, L3=6. Hogs start before a
    tier's first run (3 s warm-up) and die after its last run.
  * 5 repeats per tier, 20 runs total. Per run: full six-hop count
    decomposition, exporter collect() readback (L and the five
    quantities behind D), pre-run loadavg + MemAvailable, and the
    system-wide UDP RcvbufErrors/InErrors deltas around the run.
  * Checkpoint JSONL appended after every run; --resume skips
    (tier, rep) pairs already recorded.
Output: 2026-11-03-load-gap-bench.json next to this script.
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
OUT = os.path.join(HERE, "2026-11-03-load-gap-bench.json")
PROGRESS = os.path.join(HERE, "2026-11-03-load-gap-progress.jsonl")
WORK = "/tmp/nal-load-gap-20261103"
TIERS = [("L0", 0), ("L1", 2), ("L2", 4), ("L3", 6)]
REPS = 5
THRESHOLD = 0.75


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def loadavg():
    try:
        with open("/proc/loadavg", encoding="utf-8") as f:
            p = f.read().split()
        return [float(p[0]), float(p[1]), float(p[2])]
    except OSError:
        return None


def mem_available_kb():
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


def udp_counters():
    out = {}
    try:
        with open("/proc/net/snmp", encoding="utf-8") as f:
            lines = f.read().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("Udp:") and "InDatagrams" in line:
                keys = line.split()[1:]
                vals = lines[i + 1].split()[1:]
                out = {k: int(v) for k, v in zip(keys, vals)}
                break
    except (OSError, ValueError):
        pass
    return out


def proxy_log_breakdown(path):
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


def exporter_readback(run_dir, tmp_root):
    sys.path.insert(0, SRC)
    import prom_exporter

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
    fault_cfg = {"loss_ratio": 0.20, "delay_ms": 40.0,
                 "jitter_ms": 30.0, "flap_period_s": 2.5,
                 "flap_down_s": 0.6}
    text = prom_exporter.collect(rdir, fault_cfg)
    vals = {}
    for line in text.splitlines():
        if 'scenario="fault_sustained"' not in line:
            continue
        try:
            value = float(line.rsplit(" ", 1)[1])
        except ValueError:
            continue
        if line.startswith("nal_loss_ratio{"):
            vals["L"] = value
        elif line.startswith("nal_packets_sent_total{"):
            vals["sent"] = value
        elif line.startswith("nal_packets_echoed_total{"):
            vals["echoed"] = value
        elif line.startswith("nal_fault_proxy_packets_total{"):
            for kind in ("in_client", "in_server", "forwarded",
                         "dropped_loss", "dropped_flap", "delayed"):
                if f'kind="{kind}"' in line:
                    vals[kind] = value
        elif line.startswith("nal_server_packets_total{"):
            for kind in ("received", "echoed"):
                if f'kind="{kind}"' in line:
                    vals["server_" + kind] = value
    return vals


HOG_SRC = "import time\nwhile True:\n    pass\n"


def start_hogs(n):
    hogs = []
    for _ in range(n):
        p = subprocess.Popen(
            [sys.executable, "-c", HOG_SRC],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        hogs.append(p)
    return hogs


def stop_hogs(hogs):
    for p in hogs:
        p.send_signal(signal.SIGTERM)
    for p in hogs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def run_one(tier, nhogs, rep, run_index):
    tag = f"{tier}-r{rep}"
    run_dir = os.path.join(WORK, tag)
    os.makedirs(run_dir, exist_ok=True)
    server_port = 18100 + run_index
    shim_port = 19100 + run_index
    proxy_port = 20100 + run_index
    py = sys.executable
    extra_seed = 51000 + run_index
    la_before = loadavg()
    mem_before = mem_available_kb()
    udp_before = udp_counters()

    srv = subprocess.Popen(
        [py, os.path.join(SRC, "echo_server.py"), "--port",
         str(server_port), "--stats-out",
         os.path.join(run_dir, "server_stats.json")],
        stdout=open(os.path.join(run_dir, "server.log"), "w"),
        stderr=subprocess.STDOUT)
    time.sleep(0.4)
    shim = subprocess.Popen(
        [py, SHIM, "--listen-port", str(shim_port), "--target-port",
         str(server_port), "--q", "0", "--seed", str(extra_seed),
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
            capture_output=True, text=True, timeout=90)
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
    udp_after = udp_counters()

    summary = load_json(os.path.join(run_dir, "fault_sustained.json"))
    valid = (summary or {}).get("valid_packets") or {}
    counts, proxy_summary = proxy_log_breakdown(
        os.path.join(run_dir, "fault_proxy_log.jsonl"))
    shim_stats = load_json(os.path.join(run_dir, "shim_stats.json"))
    server_stats = load_json(os.path.join(run_dir, "server_stats.json"))
    exp = {}
    exp_err = None
    try:
        exp = exporter_readback(run_dir, WORK)
    except Exception as e:
        exp_err = f"{type(e).__name__}: {e}"

    ps = proxy_summary or {}
    sent = valid.get("sent")
    echoed = valid.get("echoed")
    in_client = ps.get("in_client")
    in_server = ps.get("in_server")
    forwarded = ps.get("forwarded")
    gap = (1 - in_client / sent) if sent and in_client is not None else None
    L = exp.get("L", valid.get("loss_rate"))
    L_iso = (1 - echoed / in_client) if echoed is not None and in_client else None
    F_c = (forwarded - echoed) if forwarded is not None and echoed is not None else None
    D = (1 - in_server / F_c) if in_server is not None and F_c else None
    # directional flap shares from per-packet decisions
    c_in = counts.get("c2s:forward", 0) + counts.get("c2s:drop_loss", 0) \
        + counts.get("c2s:drop_flap", 0)
    s_in = counts.get("s2c:forward", 0) + counts.get("s2c:drop_loss", 0) \
        + counts.get("s2c:drop_flap", 0)
    rec = {
        "tag": tag, "tier": tier, "hogs": nhogs, "rep": rep,
        "run_index": run_index, "gen_rc": gen_rc,
        "loadavg_before": la_before, "mem_available_kb_before": mem_before,
        "rcvbuf_errors_delta": (
            udp_after.get("RcvbufErrors", 0) - udp_before.get("RcvbufErrors", 0)
            if udp_before and udp_after else None),
        "in_errors_delta": (
            udp_after.get("InErrors", 0) - udp_before.get("InErrors", 0)
            if udp_before and udp_after else None),
        "sent": sent, "echoed": echoed, "loss_rate": valid.get("loss_rate"),
        "exporter": exp, "exporter_error": exp_err,
        "proxy_summary": ps, "proxy_decisions": counts,
        "shim_stats": shim_stats, "server_stats": server_stats,
        "gap": gap, "gap_packets": (sent - in_client) if sent and in_client is not None else None,
        "L": L, "L_iso": L_iso, "F_c": F_c, "D": D,
        "old_fires": (L is not None and L > THRESHOLD),
        "flap_share_c2s": (counts.get("c2s:drop_flap", 0) / c_in) if c_in else None,
        "flap_share_s2c": (counts.get("s2c:drop_flap", 0) / s_in) if s_in else None,
        "rtt_p99_ms": (valid.get("rtt_ms") or {}).get("p99"),
        "wall_seconds": (summary or {}).get("valid_packets", {}).get("wall_seconds"),
    }
    return rec


def main():
    resume = "--resume" in sys.argv
    done = {}
    if resume and os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                done[(rec["tier"], rec["rep"])] = rec
    os.makedirs(WORK, exist_ok=True)
    live = []
    idx = 0
    plan = []
    for tier, nhogs in TIERS:
        for rep in range(1, REPS + 1):
            idx += 1
            plan.append((tier, nhogs, rep, idx))
    for tier, nhogs, rep, run_index in plan:
        if (tier, rep) in done:
            live.append(done[(tier, rep)])
            print(f"skip done {tier} rep={rep}", flush=True)
            continue
        # hogs are (re)started per run batch: start if this tier's
        # first pending run, keep across the tier, stop at tier end
        # -- handled by grouping below via marker files
        rec = run_one_guarded(tier, nhogs, rep, run_index, plan)
        live.append(rec)
        with open(PROGRESS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        print(f"done {rec['tag']} gap={rec['gap']} L={rec['L']} "
              f"D={rec['D']}", flush=True)
    result = {
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "tiers": TIERS, "reps_per_tier": REPS, "threshold": THRESHOLD,
        "runs": sorted(live, key=lambda r: r["run_index"]),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(f"wrote {OUT}", flush=True)
    return 0


_HOGS = {"tier": None, "procs": []}


def run_one_guarded(tier, nhogs, rep, run_index, plan):
    # switch hog set when the tier changes
    if _HOGS["tier"] != tier:
        stop_hogs(_HOGS["procs"])
        _HOGS["procs"] = start_hogs(nhogs) if nhogs else []
        _HOGS["tier"] = tier
        if nhogs:
            time.sleep(3.0)
    rec = run_one(tier, nhogs, rep, run_index)
    # stop hogs after the last run of this tier
    later = [p for p in plan if p[3] > run_index and p[0] == tier]
    if not later:
        stop_hogs(_HOGS["procs"])
        _HOGS["procs"] = []
        _HOGS["tier"] = None
        time.sleep(2.0)
    return rec


if __name__ == "__main__":
    sys.exit(main())
