"""Server-side extra-drop shim for the injection-band experiment.

Sits between fault_proxy and the echo server on loopback:

    traffic_gen -> fault_proxy -> [this shim] -> echo_server

On the client-to-server direction only, each datagram that has already
survived the configured fault injection is discarded with probability
q (seeded RNG, decision counted and logged in the stats file). The
server-to-client direction is forwarded untouched. This is the literal
"loss beyond the injection, at the server side" condition: the packet
survived the proxy, then dies before the server can echo it, so no echo
is ever generated for it.

Clean-room, Python 3 standard library only. Connected-UDP pattern copied
from the lab's own components (unconnected sendto() is blocked with
EPERM on the build host; see net-assurance-lab VERIFICATION.md).
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
                    help="extra drop probability, c2s direction only")
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

    counters = {"in_client": 0, "dropped_extra": 0, "forwarded_client": 0,
                "in_server": 0, "forwarded_server": 0}
    client_locked = {"flag": False}
    stop = {"flag": False}

    def handle_sig(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    print(f"extra_drop_shim {args.listen_host}:{args.listen_port} -> "
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
                    print(f"extra_drop_shim client locked: {addr}",
                          flush=True)
                else:
                    data = s.recv(65535)
            except OSError:
                continue
            if s is front:
                counters["in_client"] += 1
                if rng.random() < args.q:
                    counters["dropped_extra"] += 1
                    continue
                try:
                    back.send(data)
                    counters["forwarded_client"] += 1
                except OSError:
                    pass
            else:
                counters["in_server"] += 1
                if client_locked["flag"]:
                    try:
                        front.send(data)
                        counters["forwarded_server"] += 1
                    except OSError:
                        pass

    with open(args.stats_out, "w", encoding="utf-8") as f:
        json.dump(counters, f, indent=2, sort_keys=True)
    print(f"extra_drop_shim counters: {counters}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
