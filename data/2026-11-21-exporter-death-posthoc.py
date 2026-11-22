"""Post-hoc recomputation for the 2026-11-21 exporter-death run.

Reads data/2026-11-21-exporter-death-live.json (records as captured by
the live script) and derives the numbers the article cites: per-side
up-value timelines after the kill, the receiver/sender alert gap, the
last present sample's age at the kill, and the preregistration
verdicts. Nothing here re-runs anything; it only re-reads the live
records.
"""
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(
    HERE, "2026-11-21-exporter-death-live.json"), encoding="utf-8"))
records = d["records"]
summary = d["summary"]


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


kills = {}
for r in records:
    if r.get("type") == "event" and r.get("event") == "exporter_killed":
        kills[r["phase"]] = r["t_epoch_event"]


def polls(phase_prefix):
    return [r for r in records if r.get("type") == "poll"
            and r.get("phase", "").startswith(phase_prefix + ":")]


def up_timeline(phase_prefix, side_key):
    tk = kills[phase_prefix]
    out = []
    for r in polls(phase_prefix):
        side = r.get(side_key)
        if not side:
            continue
        v = side.get("up_job")
        val = v[0]["value"] if isinstance(v, list) and v else None
        out.append({"after_kill_s": round(r["t_epoch"] - tk, 1),
                    "up": val})
    return out


def first_after(timeline, pred, from_kill=0.0):
    for row in timeline:
        if row["after_kill_s"] >= from_kill and pred(row["up"]):
            return row["after_kill_s"]
    return None


out = {}
for phase, sides in (("exporter-death", ("receiver", "sender")),
                     ("control", ("local",))):
    tk = kills[phase]
    out[phase] = {"t_kill_epoch": tk}
    for side in sides:
        tl = up_timeline(phase, side)
        post = [x for x in tl if x["after_kill_s"] >= 0]
        ones_after_zero = []
        seen_zero = False
        for x in post:
            if x["up"] == 0:
                seen_zero = True
            elif seen_zero and x["up"] == 1:
                ones_after_zero.append(x["after_kill_s"])
        s = summary[phase][side] if side in summary[phase] else None
        last = s["last_present_sample_seen"] if s else None
        out[phase][side] = {
            "up_first_zero_poll_s": first_after(post, lambda v: v == 0),
            "up_ones_after_first_zero_s": ones_after_zero,
            "up_post_kill_nonempty": sum(1 for x in post
                                         if x["up"] is not None),
            "up_post_kill_polls": len(post),
            "last_present_sample_ts": last["ts"] if last else None,
            "last_present_sample_age_at_kill_s": (
                round(tk - last["ts"], 1) if last else None),
        }

ed = summary["exporter-death"]
recv, send = ed["receiver"], ed["sender"]
out["contrasts"] = {
    "receiver_absent_minus_sender_absent_pending_s": round(
        recv["absent_alert"]["pending_after_kill_s"]
        - send["absent_alert"]["pending_after_kill_s"], 1),
    "receiver_absent_minus_sender_absent_firing_lb_s": round(
        recv["absent_alert"]["firing_lower_bound_s"]
        - send["absent_alert"]["firing_lower_bound_s"], 1),
    "receiver_absent_minus_up_firing_lb_s": round(
        recv["absent_alert"]["firing_lower_bound_s"]
        - recv["up_alert"]["firing_lower_bound_s"], 1),
    "receiver_absent_same_activeAt_as_up": (
        recv["absent_alert"]["activeAt"] == recv["up_alert"]["activeAt"]),
    "sender_absent_same_activeAt_as_up": (
        send["absent_alert"]["activeAt"] == send["up_alert"]["activeAt"]),
}
out["prereg_verdicts"] = {
    "P-E1": ("hit" if recv["up_first_zero_poll_s"] <= 20
             and recv["up_alert"]["pending_after_kill_s"] <= 45
             and 75 <= recv["up_alert"]["firing_lower_bound_s"] <= 120
             else "miss"),
    "P-E2": ("hit" if 360 <= recv["absent_alert"][
        "firing_lower_bound_s"] <= 395 else "miss"),
    "P-E3": ("hit" if out["contrasts"][
        "receiver_absent_minus_up_firing_lb_s"] >= 240 else "miss"),
    "P-E4": ("hit" if send["present_first_empty_poll_s"] <= 10
             and 60 <= send["absent_alert"]["firing_lower_bound_s"] <= 90
             and 60 <= send["up_alert"]["firing_lower_bound_s"] <= 110
             else "miss"),
    "P-E5": ("hit" if recv["up_post_kill_nonempty_polls"]
             == recv["up_post_kill_total_polls"]
             and not out["exporter-death"]["receiver"][
                 "up_ones_after_first_zero_s"]
             and ed["flags"]["sender_alive_at_end"] else "miss"),
    "P-C": ("hit" if 60 <= summary["control"]["local"]["absent_alert"][
        "firing_lower_bound_s"] <= 85 else "miss"),
}
with open(os.path.join(HERE, "2026-11-21-exporter-death-posthoc.json"),
          "w", encoding="utf-8") as fo:
    json.dump(out, fo, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
