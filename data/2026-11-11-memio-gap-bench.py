"""Bench-gap memory/IO tiers bench (2026-11-11).

Pre-registered in 2026-11-11-memio-gap-prereg.md (frozen before runs).
Question: the 2026-11-03 CPU-tier bench only produced a bench gap
(1 - in_client/sent) of at most 9.69 points at 1.5x CPU overcommit
and could not reproduce the 29.8% gap of 2026-10-28. Does the gap
jump on the memory axis (resident touched hog sized in fractions
of baseline MemAvailable) or on the disk-IO axis (4 KiB write +
fdatasync hog processes)?

Design:
  * Live chain identical to 2026-10-28/11-03: traffic_gen
    (sustained 2000 pps x 5 s = 10,000 packets) -> fault_proxy
    (loss 0.20, delay 40 ms, jitter 30 ms, flap 0.6/2.5, seed 1234)
    -> extra-drop shim at q=0 -> echo_server. No CPU hogs.
  * MEM arm tiers by hog MiB: M0=0, M1=0.5*MA0, M2=1.0*MA0,
    M3=1.6*MA0 (cap 1000 MiB). MA0 = median of 5 MemAvailable
    samples at bench start. Guard: a sampler thread kills the
    mem hog if MemAvailable < 120 MB twice in a row; the run is
    kept and flagged.
  * IO arm tiers by sync-writer count: I0=0, I1=1, I2=2, I3=4.
  * 4 repeats per tier, 32 runs. Per run: six-hop counts, exporter
    collect() readback, pre-run loadavg, in-run MemAvailable
    samples (min/median), PSI memory/io deltas, vmstat reclaim
    deltas, system UDP counter deltas, pressure-source actuals.
  * Checkpoint JSONL appended after every run; --resume skips
    (tier, rep) pairs already recorded.
Output: 2026-11-11-memio-gap-bench.json next to this script.
"""
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.expanduser("~/workspace/oxide-proofs/net-assurance-lab")
SRC = os.path.join(LAB, "src")
SHIM = os.path.join(HERE, "2026-10-28-injection-band-shim.py")
MEMHOG = os.path.join(HERE, "2026-11-11-memio-memhog.py")
IOHOG = os.path.join(HERE, "2026-11-11-memio-iohog.py")
OUT = os.path.join(HERE, "2026-11-11-memio-gap-bench.json")
PROGRESS = os.path.join(HERE, "2026-11-11-memio-gap-bench.json.progress.jsonl")
WORK = "/tmp/nal-memio-gap-20261111"
IOWORK = os.path.join(HERE, "2026-11-11-memio-iohog-work")
REPS = 4
THRESHOLD = 0.75
GUARD_FLOOR_KB = 120 * 1024


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


def psi(kind):
    out = {}
    try:
        with open(f"/proc/pressure/{kind}", encoding="utf-8") as f:
            for line in f:
                p = line.split()
                if p and p[0] in ("some", "full"):
                    d = {}
                    for kv in p[1:]:
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            d[k] = float(v)
                    out[p[0]] = d
    except OSError:
        pass
    return out


def vmstat(keys):
    out = {}
    try:
        with open("/proc/vmstat", encoding="utf-8") as f:
            for line in f:
                p = line.split()
                if len(p) == 2 and p[0] in keys:
                    out[p[0]] = int(p[1])
    except (OSError, ValueError):
        pass
    return out


VMKEYS = ("pgscan_kswapd", "pgsteal_kswapd", "pswpin", "pswpout")


def delta(after, before, key):
    if after is None or before is None:
        return None
    a = after.get(key)
    b = before.get(key)
    if a is None or b is None:
        return None
    return a - b


def psi_delta(after, before):
    out = {}
    for kind in ("memory", "io"):
        for lvl in ("some", "full"):
            a = (after.get(kind) or {}).get(lvl) or {}
            b = (before.get(kind) or {}).get(lvl) or {}
            if "total" in a and "total" in b:
                out[f"{kind}_{lvl}_total_us_delta"] = a["total"] - b["total"]
    return out


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


# ---------- pressure sources ----------

class MemHog:
    def __init__(self, mb, tag):
        self.mb = mb
        self.proc = None
        self.ready_out = os.path.join(WORK, f"memhog-{tag}.ready")
        self.guard_killed = False

    def start(self):
        if self.mb <= 0:
            return
        if os.path.exists(self.ready_out):
            os.remove(self.ready_out)
        self.proc = subprocess.Popen(
            [sys.executable, MEMHOG, "--mb", str(self.mb),
             "--ready-out", self.ready_out],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 120
        while time.time() < deadline:
            if os.path.exists(self.ready_out):
                time.sleep(2.0)
                return
            if self.proc.poll() is not None:
                raise RuntimeError(f"memhog died rc={self.proc.returncode}")
            time.sleep(0.2)
        raise RuntimeError("memhog not ready in 120 s")

    def guard_kill(self):
        self.guard_killed = True
        self.stop()

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


class IoHogs:
    def __init__(self, n, tag):
        self.n = n
        self.tag = tag
        self.procs = []
        self.stats_files = []

    def start(self):
        os.makedirs(IOWORK, exist_ok=True)
        for i in range(self.n):
            fpath = os.path.join(IOWORK, f"iohog-{self.tag}-{i}.bin")
            spath = os.path.join(IOWORK, f"iohog-{self.tag}-{i}.json")
            self.stats_files.append(spath)
            p = subprocess.Popen(
                [sys.executable, IOHOG, "--file", fpath,
                 "--stats-out", spath],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.procs.append(p)
        if self.n:
            time.sleep(2.0)

    def stop(self):
        ops = 0
        for p in self.procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        for spath in self.stats_files:
            d = load_json(spath)
            if d:
                ops += int(d.get("ops") or 0)
        self.procs = []
        return ops


class Sampler(threading.Thread):
    """Samples MemAvailable every 0.25 s; guards the mem hog."""

    def __init__(self, memhog):
        super().__init__(daemon=True)
        self.samples = []
        self.memhog = memhog
        self.halt = threading.Event()
        self.low_streak = 0

    def run(self):
        while not self.halt.is_set():
            v = mem_available_kb()
            if v is not None:
                self.samples.append(v)
                if self.memhog is not None and self.memhog.alive():
                    if v < GUARD_FLOOR_KB:
                        self.low_streak += 1
                        if self.low_streak >= 2:
                            self.memhog.guard_kill()
                    else:
                        self.low_streak = 0
            self.halt.wait(0.25)


def run_one(tier_rec, rep, run_index, pressure):
    tier = tier_rec["tier"]
    tag = f"{tier}-r{rep}"
    run_dir = os.path.join(WORK, tag)
    os.makedirs(run_dir, exist_ok=True)
    server_port = 18200 + run_index
    shim_port = 19200 + run_index
    proxy_port = 20200 + run_index
    py = sys.executable
    extra_seed = 61000 + run_index
    la_before = loadavg()
    psi_before = {"memory": psi("memory"), "io": psi("io")}
    vm_before = vmstat(VMKEYS)
    udp_before = udp_counters()

    sampler = Sampler(pressure if isinstance(pressure, MemHog) else None)
    sampler.start()
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
    sampler.halt.set()
    sampler.join(timeout=3)
    psi_after = {"memory": psi("memory"), "io": psi("io")}
    vm_after = vmstat(VMKEYS)
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
    c_in = counts.get("c2s:forward", 0) + counts.get("c2s:drop_loss", 0) \
        + counts.get("c2s:drop_flap", 0)
    s_in = counts.get("s2c:forward", 0) + counts.get("s2c:drop_loss", 0) \
        + counts.get("s2c:drop_flap", 0)
    samples = sampler.samples
    rec = {
        "tag": tag, "tier": tier, "arm": tier_rec["arm"], "rep": rep,
        "run_index": run_index, "gen_rc": gen_rc,
        "pressure_spec": tier_rec["spec"],
        "memhog_mb": tier_rec.get("memhog_mb"),
        "iohogs": tier_rec.get("iohogs"),
        "guard_killed": bool(isinstance(pressure, MemHog)
                             and pressure.guard_killed),
        "loadavg_before": la_before,
        "mem_samples_min_kb": min(samples) if samples else None,
        "mem_samples_median_kb": (int(statistics.median(samples))
                                  if samples else None),
        "mem_samples_n": len(samples),
        "psi_delta": psi_delta(psi_after, psi_before),
        "vm_delta": {k: delta(vm_after, vm_before, k) for k in VMKEYS},
        "rcvbuf_errors_delta": delta(udp_after, udp_before, "RcvbufErrors"),
        "in_errors_delta": delta(udp_after, udp_before, "InErrors"),
        "sent": sent, "echoed": echoed, "loss_rate": valid.get("loss_rate"),
        "exporter": exp, "exporter_error": exp_err,
        "proxy_summary": ps, "proxy_decisions": counts,
        "shim_stats": shim_stats, "server_stats": server_stats,
        "gap": gap,
        "gap_packets": (sent - in_client) if sent and in_client is not None else None,
        "L": L, "L_iso": L_iso, "F_c": F_c, "D": D,
        "old_fires": (L is not None and L > THRESHOLD),
        "flap_share_c2s": (counts.get("c2s:drop_flap", 0) / c_in) if c_in else None,
        "flap_share_s2c": (counts.get("s2c:drop_flap", 0) / s_in) if s_in else None,
        "rtt_p99_ms": (valid.get("rtt_ms") or {}).get("p99"),
    }
    return rec


def main():
    resume = "--resume" in sys.argv
    samples = []
    for _ in range(5):
        v = mem_available_kb()
        if v is not None:
            samples.append(v)
        time.sleep(1.0)
    ma0_kb = int(statistics.median(samples)) if samples else 0
    ma0_mb = ma0_kb / 1024.0
    tiers = []
    for name, frac in (("M0", 0.0), ("M1", 0.5), ("M2", 1.0), ("M3", 1.6)):
        mb = int(min(frac * ma0_mb, 1000)) if frac else 0
        tiers.append({"tier": name, "arm": "MEM",
                      "spec": f"memhog {mb} MiB ({frac}xMA0)",
                      "memhog_mb": mb, "iohogs": 0})
    for name, n in (("I0", 0), ("I1", 1), ("I2", 2), ("I3", 4)):
        tiers.append({"tier": name, "arm": "IO",
                      "spec": f"{n} sync writers",
                      "memhog_mb": 0, "iohogs": n})
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
    for trec in tiers:
        for rep in range(1, REPS + 1):
            idx += 1
            plan.append((trec, rep, idx))
    cur_tier = None
    pressure = None
    io_ops_by_tier = {}
    try:
        for trec, rep, run_index in plan:
            if cur_tier != trec["tier"]:
                if isinstance(pressure, IoHogs):
                    io_ops_by_tier[cur_tier] = pressure.stop()
                elif isinstance(pressure, MemHog):
                    pressure.stop()
                pressure = None
                cur_tier = trec["tier"]
                if (trec["tier"], rep) not in done or True:
                    if trec["arm"] == "MEM" and trec["memhog_mb"]:
                        pressure = MemHog(trec["memhog_mb"], trec["tier"])
                        pressure.start()
                    elif trec["arm"] == "IO" and trec["iohogs"]:
                        pressure = IoHogs(trec["iohogs"], trec["tier"])
                        pressure.start()
            if (trec["tier"], rep) in done:
                live.append(done[(trec["tier"], rep)])
                print(f"skip done {trec['tier']} rep={rep}", flush=True)
                continue
            rec = run_one(trec, rep, run_index, pressure)
            live.append(rec)
            with open(PROGRESS, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            print(f"done {rec['tag']} gap={rec['gap']} L={rec['L']} "
                  f"D={rec['D']} guard={rec['guard_killed']}", flush=True)
    finally:
        if isinstance(pressure, IoHogs):
            io_ops_by_tier[cur_tier] = pressure.stop()
        elif isinstance(pressure, MemHog):
            pressure.stop()
    for rec in live:
        if rec["arm"] == "IO":
            rec["iohog_ops_tier_total"] = io_ops_by_tier.get(rec["tier"])
    result = {
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "ma0_samples_kb": samples, "ma0_median_kb": ma0_kb,
        "tiers": tiers, "reps_per_tier": REPS, "threshold": THRESHOLD,
        "iohog_ops_by_tier": io_ops_by_tier,
        "runs": sorted(live, key=lambda r: r["run_index"]),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
