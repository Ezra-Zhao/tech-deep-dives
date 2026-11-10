"""Post-hoc extraction for the 2026-11-09 remote-write article.

Reads ONLY the live JSON produced by 2026-11-09-remotewrite-live.py
and derives the numbers the article quotes: kill/exit epochs, the
last-pushed-sample timestamp bracket, up-series behaviour on the
receiver, absent() first-return polls, baseline startup-race polls.
Writes data/2026-11-09-remotewrite-posthoc.json. No live systems.
"""
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "2026-11-09-remotewrite-live.json"),
                   encoding="utf-8"))
recs = d["records"]
summ = d["summary"]


def iso_epoch(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def ev(phase, event):
    for r in recs:
        if r.get("type") == "event" and r.get("phase") == phase \
                and r.get("event") == event:
            return r
    return None


out = {}
for phase, kill_event in (("control", "exporter_killed"),
                          ("remotewrite", "sender_killed")):
    e = ev(phase, kill_event)
    t_kill = e["t_epoch_event"]
    entry = summ[phase]["absent_alert"]
    active = iso_epoch(entry["activeAt"])
    polls = [r for r in recs if r.get("type") == "poll"
             and r.get("phase", "").startswith(phase + ":")]
    post = [r for r in polls if r["t_epoch"] >= t_kill]
    o = {"t_kill_epoch": t_kill,
         "kill_event_emit_epoch": e["t_epoch"],
         "pending_after_kill_s": entry["pending_after_kill_s"],
         "firing_lower_bound_s": entry["firing_lower_bound_s"],
         "firing_poll_after_kill_s": entry["firing_poll_after_kill_s"],
         "present_first_empty_poll_s":
             summ[phase]["present_first_empty_poll_s"]}
    # absent() first returns 1 after kill
    fa = next((r for r in post if isinstance(r.get("absent"), list)
               and r["absent"]), None)
    o["absent_first_one_poll_s"] = (
        round(fa["t_epoch"] - t_kill, 1) if fa else None)
    # up behaviour on this instance
    up_post = [(round(r["t_epoch"] - t_kill, 1),
                r["up_job"][0]["value"] if isinstance(
                    r.get("up_job"), list) and r["up_job"] else None)
               for r in post]
    o["up_post_kill_values"] = sorted({v for _, v in up_post
                                       if v is not None})
    fu = next((r for r in post if isinstance(r.get("up_job"), list)
               and not r["up_job"]), None)
    o["up_first_empty_poll_s"] = (
        round(fu["t_epoch"] - t_kill, 1) if fu else None)
    o["up_last_nonempty_poll_s"] = max(
        (round(r["t_epoch"] - t_kill, 1) for r in post
         if isinstance(r.get("up_job"), list) and r["up_job"]),
        default=None)
    # baseline startup race: alert states seen during baseline phase
    base = [r for r in polls if r["phase"].endswith(":baseline")]
    o["baseline_polls"] = len(base)
    o["baseline_alert_states"] = [
        (round(r["t_epoch"] - t_kill, 1),
         [a["state"] for a in r["alerts"]]
         if isinstance(r.get("alerts"), list) else r.get("alerts"))
        for r in base if isinstance(r.get("alerts"), list)
        and r["alerts"]]
    o["baseline_any_firing"] = any(
        isinstance(r.get("alerts"), list)
        and any(a["state"] == "firing" for a in r["alerts"])
        for r in base)
    out[phase] = o

# W: last-pushed-sample timestamp bracket. The sender scraped every
# 5 s, so the last sample it could push carries a timestamp within
# one scrape interval before the kill, unless the graceful-shutdown
# queue flush pushed a sample scraped after SIGTERM was delivered -
# bounded by the sender's exit (the kill-event emit epoch, recorded
# right after sender.wait() returned).
w = out["remotewrite"]
t_kill = w["t_kill_epoch"]
t_exit = w["kill_event_emit_epoch"]
first_empty = t_kill + w["present_first_empty_poll_s"]
w["sender_exit_after_kill_s"] = round(t_exit - t_kill, 1)
w["last_sample_ts_bracket"] = [round(t_kill - 5, 1), round(t_exit, 1)]
w["visibility_after_last_sample_s"] = [
    round(first_empty - t_exit, 1), round(first_empty - (t_kill - 5), 1)]
# C vs W contrasts
c = out["control"]
out["contrasts"] = {
    "pending_diff_s": round(w["pending_after_kill_s"]
                            - c["pending_after_kill_s"], 1),
    "firing_lower_bound_diff_s": round(w["firing_lower_bound_s"]
                                       - c["firing_lower_bound_s"], 1),
    "firing_lower_bound_ratio": round(w["firing_lower_bound_s"]
                                      / c["firing_lower_bound_s"], 2),
}
out["prereg_verdicts"] = {
    "P-C": "hit" if 60 <= c["firing_lower_bound_s"] <= 85 else "miss",
    "P-W1": "hit" if 355 <= w["firing_lower_bound_s"] <= 390
            else "miss",
    "P-W3": summ["remotewrite"]["flags"]["exporter_alive_after_kill"],
}
with open(os.path.join(HERE, "2026-11-09-remotewrite-posthoc.json"),
          "w", encoding="utf-8") as fo:
    json.dump(out, fo, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
