"""Bench-gap combined-factor + burst-pulse bench (2026-11-23).

Pre-registered in 2026-11-23-combo-pulse-prereg.md (frozen before
runs). Question: single-dimension upper bounds for the bench gap
(1 - in_client/sent) were CPU 9.69 points max (2026-11-03, 6 hogs
on 4 cores), memory-resident 0.46 points (2026-11-11, 1000 MB cap),
sync-IO 0 (2026-11-11, 4 writers) -- none near the 29.8% gap of
2026-10-28. Does combining all three at their previously tested
max tiers push the first-hop gap to >= 20 points, and/or does a
burst/pulse form (pressure only for the first 2.0 s of each 5 s
run) do it?

Design:
  * Live chain identical to 2026-10-28/11-03/11-11: traffic_gen
    (sustained 2000 pps x 5 s = 10,000 packets) -> fault_proxy
    (loss 0.20, delay 40 ms, jitter 30 ms, flap 0.6/2.5, seed 1234)
    -> extra-drop shim at q=0 -> echo_server. Shim seed base 71000.
  * Arms (4 reps each, 16 runs, order C0->C1->C2->C3):
      C0 baseline, no pressure.
      C1 combined sustained: 6 CPU hogs + memhog 1000 MB + 4 sync
         IO writers, present for the whole run.
      C2 combined pulse: same three sources, killed at t=+2.0 s
         after generator start (first 40% of the run).
      C3 CPU-only pulse: 6 CPU hogs, same 2.0 s window.
  * Pressure is started per run (pre-registered deviation from the
    per-tier startup of earlier rounds, required by the pulse
    arms): memhog ready + 2 s settle, IO writers 2 s warmup, CPU
    hogs 2 s warmup, then traffic starts.
  * Safety guard identical to 2026-11-11: a sampler thread reads
    MemAvailable every 0.25 s; two consecutive samples below
    120 MB kill the memhog (run kept, flagged guard_killed).
    Memhog capped at 1000 MB. No vm sysctls touched.
  * Checkpoint JSONL appended after every run; --resume skips
    (arm, rep) pairs already recorded.
Output: 2026-11-23-combo-pulse-bench.json next to this script.
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
OUT = os.path.join(HERE, "2026-11-23-combo-pulse-bench.json")
PROGRESS = OUT + ".progress.jsonl"
WORK = "/tmp/nal-combo-pulse-20261123"
IOWORK = os.path.join(HERE, "2026-11-23-combo-pulse-iohog-work")
REPS = 4
THRESHOLD = 0.75
GUARD_FLOOR_KB = 120 * 1024
MEMHOG_MB = 1000
CPU_HOGS = 6
IO_WRITERS = 4
PULSE_S = 2.0

ARMS = [
    {"arm": "C0", "cpu_hogs": 0, "memhog_mb": 0, "iohogs": 0,
     "pulse": False, "spec": "no pressure"},
    {"arm": "C1", "cpu_hogs": CPU_HOGS, "memhog_mb": MEMHOG_MB,
     "iohogs": IO_WRITERS, "pulse": False,
     "spec": "6 CPU hogs + memhog 1000 MB + 4 sync IO writers, sustained"},
    {"arm": "C2", "cpu_hogs": CPU_HOGS, "memhog_mb": MEMHOG_MB,
     "iohogs": IO_WRITERS, "pulse": True,
     "spec": "same as C1, all killed at t=+2.0 s (pulse, first 40%)"},
    {"arm": "C3", "cpu_hogs": CPU_HOGS, "memhog_mb": 0, "iohogs": 0,
     "pulse": True,
     "spec": "6 CPU hogs only, killed at t=+2.0 s (pulse)"},
]


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
    for kind in ("cpu", "memory", "io"):
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

HOG_SRC = "import time\nwhile True:\n    pass\n"


class Pressure:
    """One run's pressure set: CPU hogs + memhog + IO writers."""

    def __init__(self, arm_rec, tag):
        self.spec = arm_rec
        self.tag = tag
        self.cpu = []
        self.mem = None          # MemHog-like dict {proc, ready}
        self.io_procs = []
        self.io_stats = []
        self.io_ops = None
        self.guard_killed = False
        self.killed_at = None    # monotonic time of kill_all

    # -- memhog --
    def _start_mem(self, mb):
        ready_out = os.path.join(WORK, f"memhog-{self.tag}.ready")
        if os.path.exists(ready_out):
            os.remove(ready_out)
        proc = subprocess.Popen(
            [sys.executable, MEMHOG, "--mb", str(mb),
             "--ready-out", ready_out],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.mem = {"proc": proc, "ready": ready_out}
        deadline = time.time() + 120
        while time.time() < deadline:
            if os.path.exists(ready_out):
                time.sleep(2.0)
                return
            if proc.poll() is not None:
                raise RuntimeError(f"memhog died rc={proc.returncode}")
            time.sleep(0.2)
        raise RuntimeError("memhog not ready in 120 s")

    def mem_alive(self):
        return (self.mem is not None
                and self.mem["proc"].poll() is None)

    def kill_mem(self):
        if self.mem is not None:
            p = self.mem["proc"]
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
            self.mem = None

    def guard_kill_mem(self):
        self.guard_killed = True
        self.kill_mem()

    # -- io hogs --
    def _start_io(self, n):
        os.makedirs(IOWORK, exist_ok=True)
        for i in range(n):
            fpath = os.path.join(IOWORK, f"iohog-{self.tag}-{i}.bin")
            spath = os.path.join(IOWORK, f"iohog-{self.tag}-{i}.json")
            self.io_stats.append(spath)
            p = subprocess.Popen(
                [sys.executable, IOHOG, "--file", fpath,
                 "--stats-out", spath],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.io_procs.append(p)
        if n:
            time.sleep(2.0)

    def _stop_io(self):
        ops = 0
        for p in self.io_procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in self.io_procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        for spath in self.io_stats:
            d = load_json(spath)
            if d:
                ops += int(d.get("ops") or 0)
        self.io_procs = []
        self.io_ops = ops

    # -- cpu hogs --
    def _start_cpu(self, n):
        for _ in range(n):
            p = subprocess.Popen(
                [sys.executable, "-c", HOG_SRC],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.cpu.append(p)
        if n:
            time.sleep(2.0)

    def _stop_cpu(self):
        for p in self.cpu:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in self.cpu:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        self.cpu = []

    # -- whole set --
    def start(self):
        s = self.spec
        if s["memhog_mb"]:
            self._start_mem(s["memhog_mb"])
        if s["iohogs"]:
            self._start_io(s["iohogs"])
        if s["cpu_hogs"]:
            self._start_cpu(s["cpu_hogs"])

    def kill_all(self):
        if self.killed_at is None:
            self.killed_at = time.monotonic()
        self._stop_cpu()
        self.kill_mem()
        if self.io_procs:
            self._stop_io()

    def stop(self):
        self.kill_all()


class Sampler(threading.Thread):
    """Samples MemAvailable every 0.25 s with timestamps; guards
    the mem hog (two consecutive samples < 120 MB -> kill it)."""

    def __init__(self, pressure):
        super().__init__(daemon=True)
        self.samples = []        # list of (monotonic_ts, kb)
        self.pressure = pressure
        self.halt = threading.Event()
        self.low_streak = 0

    def run(self):
        while not self.halt.is_set():
            v = mem_available_kb()
            if v is not None:
                self.samples.append((time.monotonic(), v))
                if self.pressure is not None and self.pressure.mem_alive():
                    if v < GUARD_FLOOR_KB:
                        self.low_streak += 1
                        if self.low_streak >= 2:
                            self.pressure.guard_kill_mem()
                    else:
                        self.low_streak = 0
            self.halt.wait(0.25)


def run_one(arm_rec, rep, run_index):
    arm = arm_rec["arm"]
    tag = f"{arm}-r{rep}"
    run_dir = os.path.join(WORK, tag)
    os.makedirs(run_dir, exist_ok=True)
    server_port = 18300 + run_index
    shim_port = 19300 + run_index
    proxy_port = 20300 + run_index
    py = sys.executable
    extra_seed = 71000 + run_index
    la_before = loadavg()
    psi_before = {k: psi(k) for k in ("cpu", "memory", "io")}
    vm_before = vmstat(VMKEYS)
    udp_before = udp_counters()

    pressure = Pressure(arm_rec, tag)
    pressure.start()
    sampler = Sampler(pressure)
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
    pulse_timer = None
    t_gen = time.monotonic()
    try:
        gen = subprocess.Popen(
            [py, os.path.join(SRC, "traffic_gen.py"), "--mode",
             "sustained", "--rate-pps", "2000", "--duration-s", "5",
             "--port", str(proxy_port), "--csv-out",
             os.path.join(run_dir, "fault_sustained.csv"),
             "--summary-out",
             os.path.join(run_dir, "fault_sustained.json")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t_gen = time.monotonic()
        if arm_rec["pulse"]:
            pulse_timer = threading.Timer(PULSE_S, pressure.kill_all)
            pulse_timer.start()
        try:
            gen_rc = gen.wait(timeout=90)
        except subprocess.TimeoutExpired:
            gen.kill()
            gen_rc = -99
    finally:
        if pulse_timer is not None:
            pulse_timer.cancel()
        pressure.stop()
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
    psi_after = {k: psi(k) for k in ("cpu", "memory", "io")}
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
    raw = sampler.samples
    rel = [[round(ts - t_gen, 2), kb] for ts, kb in raw]
    vals = [kb for _, kb in rel]
    pulse_off = None
    if pressure.killed_at is not None and arm_rec["pulse"]:
        pulse_off = round(pressure.killed_at - t_gen, 3)
    rec = {
        "tag": tag, "arm": arm, "rep": rep,
        "run_index": run_index, "gen_rc": gen_rc,
        "pressure_spec": arm_rec["spec"],
        "cpu_hogs": arm_rec["cpu_hogs"],
        "memhog_mb": arm_rec["memhog_mb"],
        "iohogs": arm_rec["iohogs"],
        "pulse": arm_rec["pulse"],
        "pulse_off_elapsed_s": pulse_off,
        "iohogs_ops": pressure.io_ops,
        "guard_killed": bool(pressure.guard_killed),
        "loadavg_before": la_before,
        "mem_samples": rel,
        "mem_samples_min_kb": min(vals) if vals else None,
        "mem_samples_median_kb": (int(statistics.median(vals))
                                  if vals else None),
        "mem_samples_n": len(vals),
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
    done = {}
    if resume and os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                done[(rec["arm"], rec["rep"])] = rec
    os.makedirs(WORK, exist_ok=True)
    live = []
    idx = 0
    for arm_rec in ARMS:
        for rep in range(1, REPS + 1):
            idx += 1
            if (arm_rec["arm"], rep) in done:
                live.append(done[(arm_rec["arm"], rep)])
                print(f"skip done {arm_rec['arm']} rep={rep}", flush=True)
                continue
            rec = run_one(arm_rec, rep, idx)
            live.append(rec)
            with open(PROGRESS, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            print(f"done {rec['tag']} gap={rec['gap']} L={rec['L']} "
                  f"D={rec['D']} guard={rec['guard_killed']} "
                  f"pulse_off={rec['pulse_off_elapsed_s']}", flush=True)
    result = {
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "ma0_samples_kb": samples, "ma0_median_kb": ma0_kb,
        "arms": ARMS, "reps_per_arm": REPS, "threshold": THRESHOLD,
        "pulse_s": PULSE_S, "guard_floor_kb": GUARD_FLOOR_KB,
        "runs": sorted(live, key=lambda r: r["run_index"]),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
