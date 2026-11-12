"""Memory hog for the 2026-11-11 mem/io bench gap experiment.

Allocates --mb MiB in 64 MiB chunks, touches every page, signals
readiness via --ready-out, then keeps re-touching its pages in
round-robin passes so the kernel cannot cheaply reclaim or swap
them out. Pure stdlib. Killed by the bench parent (SIGTERM) at
tier end or by the MemAvailable guard.
"""
import argparse
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=int, required=True)
    ap.add_argument("--ready-out", required=True)
    args = ap.parse_args()
    chunks = []
    remaining = args.mb
    while remaining > 0:
        n = min(64, remaining)
        ba = bytearray(n * 1024 * 1024)
        for off in range(0, len(ba), 4096):
            ba[off] = 1
        ba[-1] = 1
        chunks.append(ba)
        remaining -= n
    with open(args.ready_out, "w", encoding="utf-8") as f:
        f.write(f"ready mb={args.mb}\n")
    print(f"memhog ready mb={args.mb}", flush=True)
    v = 2
    while True:
        for ba in chunks:
            for off in range(0, len(ba), 4096):
                ba[off] = v & 0xFF
            v += 1
        time.sleep(0.05)


if __name__ == "__main__":
    sys.exit(main())
