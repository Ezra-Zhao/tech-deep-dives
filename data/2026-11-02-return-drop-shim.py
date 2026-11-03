"""Return-direction extra-drop shim for the 2026-11-02 control bench.

Mirror image of 2026-10-28-injection-band-shim.py with the drop moved
to the opposite direction:

    traffic_gen -> fault_proxy -> [this shim] -> echo_server

The client-to-server direction is forwarded untouched, so the server
receives and echoes every packet the proxy forwards. On the
server-to-client direction only, each echo is discarded with
probability q (seeded RNG, counted in the stats file). The packet
therefore does all the server work and dies on its way back -- the
literal "loss beyond the injection, on the return path" condition.

Counters (kept name-compatible with the forward shim where the
meaning is the same):
  in_client        datagrams received on the client (proxy) side
  forwarded_client datagrams passed on to the server (== in_client
                   unless a send fails)
  in_server        echoes received from the server
  dropped_extra    echoes discarded by the q decision (return only)
  forwarded_server echoes passed back toward the proxy

Clean-room, Python 3 standard library only. Connected-UDP pattern
copied from the lab's own components (unconnected sendto() is blocked
with EPERM on the build host; see net-assurance-lab VERIFICATION.md).
"""
import argparse
import json
import random
import select
import signal
import socket
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen-host", default="127.0.0.1")
    ap.add_argument("--listen-port", type=int, required=True)
    ap.add_argument("--target-host", default="127.0.0.1")
    ap.add_argument("--target-port", type=int, required=True)
    ap.add_argument("--q", type=float, required=True,
                    help="extra drop probability, s2c direction only")
    ap.add_argument("--seed", type=int, default=999)
    ap.add_argument("--stats-out", required=True)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    front = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    front.bind((args.listen_host, args.listen_port))
    front.setblocking(False)
    back = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    back.connect((args.target_host, args.target_port))
    back.setblocking(False)

    counters = {"in_client": 0, "forwarded_client": 0,
                "in_server": 0, "dropped_extra": 0, "forwarded_server": 0}
    client_locked = {"flag": False}
    stop = {"flag": False}

    def handle_sig(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    print(f"return_drop_shim {args.listen_host}:{args.listen_port} -> "
          f"{args.target_host}:{args.target_port} q={args.q} "
          f"seed={args.seed}", flush=True)
    while not stop["flag"]:
        try:
            r, _, _ = select.select([front, back], [], [], 0.05)
        except OSError:
            continue
        for s in r:
            try:
                if s is front and not client_locked["flag"]:
                    data, addr = front.recvfrom(65535)
                    front.connect(addr)
                    client_locked["flag"] = True
                    print(f"return_drop_shim client locked: {addr}",
                          flush=True)
                else:
                    data = s.recv(65535)
            except OSError:
                continue
            if s is front:
                counters["in_client"] += 1
                try:
                    back.send(data)
                    counters["forwarded_client"] += 1
                except OSError:
                    pass
            else:
                counters["in_server"] += 1
                if rng.random() < args.q:
                    counters["dropped_extra"] += 1
                    continue
                if client_locked["flag"]:
                    try:
                        front.send(data)
                        counters["forwarded_server"] += 1
                    except OSError:
                        pass

    with open(args.stats_out, "w", encoding="utf-8") as f:
        json.dump(counters, f, indent=2, sort_keys=True)
    print(f"return_drop_shim counters: {counters}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
