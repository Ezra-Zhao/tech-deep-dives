"""Posthoc summary for the 2026-11-22 flaky half-dead live run.

Reads the live JSON + per-arm exporter attempt logs (copied next to
the bench JSON by the caller / present in rw-work/run22) and computes,
per arm: attempt counts and success gaps in flaky mode, present-empty
polls, absent/up alert pending episodes (start, duration, fired?)
from poll records, and firing intervals relative to the preceding
success gap start. Writes 2026-11-22-flaky-halfdead-posthoc.json and
2026-11-22-flaky-halfdead-bench.json (merged summary).
"""
import json
import os
import re
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(HERE, "2026-11-22-flaky-halfdead-live.json")
WORK = os.path.join(HERE, "rw-work", "run22")


def parse_iso(s):
    m = re.match(r"(.*T\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$", s)
    base = m.group(1)
    frac = float("0." + (m.group(2) or "0"))
    dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc)
    return dt.timestamp() + frac


def val(x):
    if isinstance(x, list) and x:
        return x[0]["value"]
    return None


def main():
    with open(LIVE, encoding="utf-8") as f:
        live = json.load(f)
    flip = live["flip_epoch"]
    polls = [r for r in live["records"] if r.get("type") == "poll"]
    summary = {"flip_epoch": flip, "arms": {}}
    for arm in live["arms"]:
        name = arm["name"]
        # exporter attempts
        attempts = []
        logp = os.path.join(WORK, name, "attempts.log")
        if os.path.exists(logp):
            with open(logp, encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 4:
                        attempts.append({"epoch": float(parts[0]),
                                         "idx": int(parts[1]),
                                         "mode": parts[2],
                                         "outcome": parts[3]})
        flaky_att = [a for a in attempts if a["epoch"] >= flip - 6]
        succ = [a["epoch"] for a in flaky_att if a["outcome"] == "success"]
        gaps = [round(succ[i + 1] - succ[i], 1) for i in range(len(succ) - 1)]
        # polls in flaky phase
        fp = [r for r in polls if r["phase"] in ("flaky", "tail")]
        pres_empty = sum(1 for r in fp if val(r[name]["present"]) is None)
        pres_one = sum(1 for r in fp if val(r[name]["present"]) == 1)
        up_zero = sum(1 for r in fp if val(r[name]["up_job"]) == 0)
        up_one = sum(1 for r in fp if val(r[name]["up_job"]) == 1)
        # alert episodes per alert name
        episodes = {}
        for alert in ("NalExporterSeriesAbsent", "NalExporterUpZero"):
            eps = []
            cur = None
            for r in fp:
                al = {a["name"]: a for a in r[name]["alerts"]
                      if isinstance(r[name]["alerts"], list)}
                a = al.get(alert)
                if a and a["state"] in ("pending", "firing"):
                    if cur is None:
                        cur = {"start_epoch": parse_iso(a["activeAt"]),
                               "fired": a["state"] == "firing",
                               "first_firing_poll_rel": None}
                    if a["state"] == "firing":
                        if not cur["fired"]:
                            cur["fired"] = True
                        if cur["first_firing_poll_rel"] is None:
                            cur["first_firing_poll_rel"] = r["t_rel_s"]
                            cur["first_firing_epoch"] = r["t_epoch"]
                    cur["last_seen_epoch"] = r["t_epoch"]
                else:
                    if cur is not None:
                        cur["duration_s"] = round(
                            cur["last_seen_epoch"] - cur["start_epoch"], 1)
                        cur["start_rel_flip"] = round(
                            cur["start_epoch"] - flip, 1)
                        eps.append(cur)
                        cur = None
            if cur is not None:
                cur["duration_s"] = round(
                    cur["last_seen_epoch"] - cur["start_epoch"], 1)
                cur["start_rel_flip"] = round(cur["start_epoch"] - flip, 1)
                cur["open_at_end"] = True
                eps.append(cur)
            episodes[alert] = eps
        summary["arms"][name] = {
            "period": arm["period"], "timestamped": arm["ts"] == "1",
            "attempts_flaky_window": len(flaky_att),
            "successes_flaky_window": len(succ),
            "success_gaps_s": gaps,
            "polls_flaky_tail": len(fp),
            "present_empty_polls": pres_empty,
            "present_one_polls": pres_one,
            "up_zero_polls": up_zero, "up_one_polls": up_one,
            "episodes": episodes,
        }
    with open(os.path.join(HERE, "2026-11-22-flaky-halfdead-posthoc.json"),
              "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    bench = {"live_file": "2026-11-22-flaky-halfdead-live.json",
             "prometheus": "3.15.0", "summary": summary}
    with open(os.path.join(HERE, "2026-11-22-flaky-halfdead-bench.json"),
              "w", encoding="utf-8") as f:
        json.dump(bench, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
