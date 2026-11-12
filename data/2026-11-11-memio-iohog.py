"""Sync-write IO hog for the 2026-11-11 mem/io bench gap experiment.

Loops 4 KiB append writes, each followed by fdatasync, on its own
file. Counts completed sync writes into --stats-out every 50 ops
and once more on SIGTERM. Pure stdlib.
"""
import argparse
import json
import os
import signal
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--stats-out", required=True)
    args = ap.parse_args()
    state = {"ops": 0, "stop": False}

    def dump():
        with open(args.stats_out, "w", encoding="utf-8") as f:
            json.dump({"ops": state["ops"]}, f)

    def handle(signum, frame):
        state["stop"] = True

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    buf = b"i" * 4096
    print(f"iohog ready file={args.file}", flush=True)
    while not state["stop"]:
        os.write(fd, buf)
        os.fdatasync(fd)
        state["ops"] += 1
        if state["ops"] % 50 == 0:
            dump()
    dump()
    os.close(fd)
    print(f"iohog done ops={state['ops']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
