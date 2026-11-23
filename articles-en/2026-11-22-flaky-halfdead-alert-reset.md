# Half-Dead Is the Hardest to Alert On: An Intermittently Succeeding Exporter Kept the Alert Lit — the Successes Never Reset the Pending Timer, the Evaluation Phase Locked It In

Author: Guangyi Zhao

## 1. Problem and background

The earlier articles in this series measured clean deaths: process exit, process hang, a killed sender. This one changes the failure mode to something closer to the field — half-dead: the exporter is still alive, scrapes sometimes succeed and sometimes run into the 4-second timeout, and the success rate drops from fifty percent to four. My prior picture was simple: every successful sample zeroes the staleness and lookback accounting, the absent alert's pending timer gets reset again and again, and only when the gap between successes exceeds the 60-second `for:` does the alert fire once per long gap and clear on the next success. Under that picture, a 30-second success gap should never fire at all, and a 120-second gap should fire once per gap and clear every time.

The measurements dismantled most of that picture. At a 30-second success gap, the absent alert fired 80.3 seconds after the half-dead phase began and then never cleared for the remaining 386.6 seconds — during which the exporter succeeded 13 times, and in 22 polls `present` was visibly 1 while the alert sat in firing. The successes did not reset the pending timer. The reason is a quantity I had not accounted for: a successful sample stays visible for only about 10 seconds, rule evaluation looks once every 15 seconds, and the evaluation phase is locked against the scrape cycle — evaluation never once landed inside a visible window. The mirror image appeared at a 10-second success gap: the invisible window is only about 1 second, evaluation never landed inside that either, and the alert never even went pending. In a half-dead state, whether an absence alert fires is decided first by the relative geometry of the evaluation phase and the visible window, and only second by comparing the success gap with `for:`.

The design was frozen before the run (data/2026-11-22-flaky-halfdead-prereg.md): of six predictions, P-A hit, P-C and P-D half-hit, and P-B, P-UP and P-GAP missed. Section 3.4 settles each one.

## 2. Method

Same bench as the earlier articles: Prometheus 3.15.0, scrape interval 5 s, scrape timeout 4 s, rule-group evaluation 15 s, `for:` 1 minute, default 300 s lookback, a fresh TSDB per arm, loopback only. The target is a flaky exporter written for this run: a successful attempt returns `nal_exporter_results_present{group="scenario_summaries"} 1` within 0.2 s; a failed attempt hangs for 6 s and is failed by the client's 4 s timeout. A state file switches modes: in the healthy phase every attempt succeeds; in the flaky phase attempts cycle with period P — the first attempt of each period succeeds, the rest fail.

Four arms ran in parallel on the same wall clock, held a healthy baseline for about 35 s, then flipped to flaky together for 400 s:

| Arm | Period P | Success rate | Measured success gap | Sample timestamps |
|---|---|---|---|---|
| A dense | 2 | 50% | 10.0 s (first 5.0) | none |
| B sparse | 6 | ~16.7% | 30.0 s (first 25.0) | none |
| C rare | 24 | ~4.2% | 120.0 s (first 85.0) | none |
| D sparse, timestamped | 6 | ~16.7% | 30.0 s (first 25.0) | yes (request time, ms) |

The two rules are verbatim from the earlier articles — `absent(present)` and `up{job="net-assurance-lab"} == 0`, both `for:` 1 minute; the rule file passes promtool check (SUCCESS, 2 rules). All four arms were polled every 5 s for the instant queries `present`, `absent()` and `up` plus the full alert snapshot — 82 polls in the flaky window. The exporters logged every attempt with its outcome (attempts in the flaky window 83/83/84/84, successes 42/14/5/15), and the two ledgers were reconciled afterwards. Arm D matches arm B in rate and gap and differs only in timestamps, isolating the timestamp effect. Success rate and success gap move together in this design and are not orthogonalized; Section 5 bounds what may be concluded.

## 3. Measurements

### 3.1 The four arms, totalled

| Arm | Polls with present empty | Polls with up=0 | absent alert | up==0 alert |
|---|---|---|---|---|
| A (10 s gap) | 0/82 | 0/82 | never pending | never pending |
| B (30 s gap) | 54/82 | 54/82 | pending at +19.8 s after the flip, firing lower bound +80.3 s, then continuously firing for 386.6 s (still firing at the end) | same cycle, same start and end as absent |
| C (120 s gap) | 74/82 | 74/82 | same as B: pending +19.8 s, firing lower bound +80.3 s, never clears | same cycle as absent |
| D (30 s gap, timestamped) | 0/82 | 61/82 | never pending | pending at +4.8 s, firing lower bound +65.2 s, continuously firing for 401.6 s |

That arms B and C share alert timings to the microsecond is not a typo: all four arms flipped at the same instant and their scrape and evaluation phases sit on the same wall-clock beats, so both arms' absent expressions were first seen true inside the same long invisible window, with identical pending activeAt values. Arm C's first success gap was 85 s (a phase-alignment artefact), then exactly 120 s.

### 3.2 The visible window: a success buys about 10 seconds of light

Arm B's per-poll present sequence is a tidy repeating 11000: in each 30 s, about 10 s read 1 and 20 s read empty. The mechanism, taken apart: a successful scrape writes a sample at time t; the next scrape starts at t+5, runs into the 4 s timeout and is judged failed at t+9, and the failed scrape drops a stale marker on the series — present goes empty; it stays empty until the next success at t+30. So one success buys not 30 s of visibility but about 9–10 s: one scrape interval plus one timeout. Arm C is the same shape stretched: lit about 10 s in every 120 (present read 1 in 8/82 polls). Arm A is the mirror: the failed scrape drops its marker 9 s after a success and the next success arrives at 10 s, leaving an invisible window of about 1 s; the 5 s polls all landed on the lit side (present empty 0/82, up=0 also 0/82 — the poll phase happened to lock onto the success side too, which is part observation luck and is not generalized here).

Arm D's present never went empty (0/82): its samples carry their own timestamps, failed scrapes synthesize no stale markers for such series (established in the 2026-10-31 article), and the 300 s lookback covers the 30 s gaps whole. But arm D's `up` enjoys no such protection: up=0 in 61/82 polls, and its up==0 alert fired and never cleared — on one and the same exporter, two series met two different fates, and the dividing line is the timestamp.

### 3.3 Why the alert never clears: evaluation phase lock-in

Across arm B's 82 polls, the absent alert was absent for the first 4 polls, pending in 12, and firing in 66; after it first went pending, it was present in 78 consecutive polls without a single gap. In those 386.6 s the exporter succeeded 13 times, and in 22 polls the instant query for present returned 1 while the alert was firing — the successful samples really did reach the TSDB; these were not phantom successes on the exporter side. So why did the alert never clear?

Alert state follows evaluations, not samples. The rule group evaluates `absent()` every 15 s: true keeps the pending clock running, false clears the alert on the spot. Arm B's visible window is about 10 s on a 30 s cycle, and the 15 s evaluation beat forms a small-integer ratio with the 30 s scrape cycle, so once the evaluation phase sits inside the invisible window it sits there every cycle — the least common multiple of 30 and 15 is 30, the phase offset is frozen by the periodic structure, and it never drifts across the visible window over time. The 5 s polls can see present flicker; the 15 s evaluations, phase-locked, cannot. This is not a probabilistic miss but a beat resonance: whenever the success period and the evaluation interval form a small-integer ratio with an unlucky phase, the alert is structurally blind to intermittent success — lit, it never goes out; unlit (arm A), it never catches the roughly 1-second invisible window either.

Arm C pushes the same mechanism to its extreme: a 120 s success gap with the same roughly 10 s visible window and the same locked evaluation phase, so the preregistered picture of "one firing per gap, cleared by each success" never appeared — like arm B, it fired once and stayed lit. Arms B and C differ fourfold in success rate and their alert shapes are identical to the microsecond, which is the direct evidence that the rate is not the criterion: the criterion is the relative geometry of the visible window and the evaluation phase.

### 3.4 Preregistration scorecard

- P-A (arm A never fires): hit, and stronger than predicted — it never even went pending (the roughly 1 s invisible window was never caught by an evaluation).
- P-B (arm B never fires; pending reset gap by gap): missed. Arm B fired and stayed lit for the whole run; the "reset per gap" picture is replaced by the phase lock-in mechanism of Section 3.3.
- P-C (arm C fires in every long gap and clears on success): half-hit. It fired, with the first firing lower bound 80.3 s after the flip — about 81 s after the first gap began, inside the preregistered 60–105 s band; but "once per gap, cleared by success" missed — there was a single continuous firing.
- P-D (arm D: present never empty, absent never pending, up alert never fires): half-hit. The first two held; the third missed — the up==0 alert fired and never cleared, by the same mechanism as arm B (the invisible side of `up` occupies about 20 of every 30 s, and the evaluation phase is locked onto that side).
- P-UP (up follows absent; only arm C fires): missed. The up alert fired and stayed lit in arms B, C and D; only arm A stayed silent.
- P-GAP (pending episode length ≈ success gap): missed. Each arm produced a single continuous pending-to-firing episode of 386.6–401.6 s, unrelated to the success gap; pending survival is decided by evaluation phase, not by the gap, segment by segment.

## 4. Analysis and trade-offs

First, a note for whoever holds the pager: in a half-dead state, do not expect an absence-style alert (absent, up==0) to heal itself when the target intermittently recovers. Arm B's target genuinely came back every 30 s, lit for 10 s each time, and the alert did not move for over six minutes. Reading "the alert is still firing" as "the target is still dead" misjudges the half-dead case: alert state and target state decouple here, and they decouple because the evaluation beat cannot see brief recoveries. To tell dead from half-dead, look at the arrival ledger of successful samples themselves — the time of the last successful scrape — not at alert state.

Second, the criterion gets another layer. The earlier articles asked whether a stale marker is *produced* and *delivered*; this run adds: after the marker lands, how the expression's truth window sits against the evaluation beat. When the visible window (roughly one scrape interval plus one timeout) is shorter than the evaluation interval and the two periods form a small-integer ratio, evaluation is systematically blind to the visible window — and then neither `for:` nor the success gap is the main variable; the phase is. The knobs a deployment actually has all live on this layer: make the evaluation interval coprime with the scrape cycle (15 s to 16 s, say, so the phase slides every cycle and must sweep across the visible window within a few cycles), or stop judging half-death with absence expressions at all and use a direct quantity — time since the last successful scrape, from the change timestamp of `up` or the increments of a scrape-success counter — which routes around the phase problem entirely. Both are prescriptions derived from this run's mechanism and were not re-measured with changed parameters in this run; they are labelled mechanism-level inference (below grade B), not verified results.

Third, do not misread arm A's mirror image: arm A is not "healthy" — half of its scrapes failed; its invisible window was simply too short for evaluations or polls to catch. Absence alerts are unreliable for half-death in both directions — dense successes leak through unreported, sparse successes report and never clear — and that is exactly what makes half-death harder to alert on than full death: a full death keeps clean books (the earlier articles: firing in 61–79 s, clearing on recovery), while a half-death's books are stirred by phase.

No rule files in the repository were changed in this run; candidates and measurement material stay in this project's data/, as with the earlier articles.

## 5. Limitations and open questions

- Success rate and success gap move together and were not separated: this run establishes the "visible window × evaluation phase" mechanism and that rate is not the criterion (arms B and C, fourfold apart in rate, share one alert shape), but it does not answer the pure effect of rate at fixed gap or gap at fixed rate. A follow-up with randomized (Poisson-style) success intervals, rather than a fixed period, is needed to fully separate phase resonance from gap effects.
- Phase lock-in is mechanism inference backed by state-continuity evidence: evaluation instants were not logged individually; I infer "evaluation never saw false" from 78 consecutive polls with the alert present plus the flicker ledger of present. The one back door — an evaluation seeing false and the alert re-pending within 5 s, invisible to polls — is closed by the alert API itself: re-pending would refresh activeAt, and arms B and C's activeAt never changed across polls.
- Arm A's poll phase happened to lock onto the success side (0/82 empty for both present and up) and contains an element of observation luck: a different poll phase might show occasional empty polls for arm A. The alert-side statement "never pending", however, is a statement about evaluation phase and does not depend on the poll phase.
- The parameter prescriptions (coprime evaluation interval; time-since-last-success) were not re-measured; they are queued as the next topic: same bench, same flaky patterns, only evaluation_interval changed to 16 s, measuring whether arm B's alert starts clearing with the successes.
- The failure pattern is deterministic and periodic (equal success gaps); real half-death jitter is random, and under random jitter the phase drifts on its own, so the lock-in should be weaker than in this run — this run measures the worst-case shape, not the average case.
- Loopback, four arms on one wall clock, and `for:` 1 minute bound the absolute numbers (80.3 s and friends) to this bench, as in the earlier articles; the shape conclusions (visible window, phase lock-in) are not bound to it.

## 6. References

1. Prometheus documentation, Querying / Basics, "Staleness": a series is marked stale when a scrape no longer returns it; samples with their own timestamps get no synthesized stale markers. https://prometheus.io/docs/prometheus/latest/querying/basics/
2. Prometheus documentation, Alerting rules: the semantics of `for:` pending timing and evaluation intervals. https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
3. Prometheus documentation, Querying / Functions, absent(). https://prometheus.io/docs/prometheus/latest/querying/functions/
4. Earlier articles in this repository: "The Process Is Alive and the Scrape Still Walks the Full 4 Seconds" (2026-11-10, one of this run's starting points), "The Exporter Died Behind a Live Sender and the Receiver Fired in 79 Seconds" (2026-11-21), "Give Samples Their Own Timestamps and the Blind Window Goes Back to Six Minutes" (2026-10-31, source of arm D's timestamp setup).
5. This run's material (archived in this project's data/ and mirrored with the article into the tech-deep-dives repository's data/): 2026-11-22-flaky-halfdead-prereg.md (the preregistration, frozen before the run), 2026-11-22-flaky-halfdead-rules.yml (the two candidate rules, promtool check SUCCESS), 2026-11-22-flaky-exporter.py (the flaky target), 2026-11-22-flaky-halfdead-live.py (the live harness), 2026-11-22-flaky-halfdead-live-progress.jsonl (per-poll progress), 2026-11-22-flaky-halfdead-live.json (full record), 2026-11-22-flaky-halfdead-posthoc.py and 2026-11-22-flaky-halfdead-posthoc.json (alert-episode and attempt-ledger reconciliation), 2026-11-22-flaky-halfdead-bench.json (summary). The Prometheus binary is the official 3.15.0 release and is not redistributed with the repository.

---

Author: Guangyi Zhao. The experiment design, code and data in this article are clean-room work of my own: the flaky exporter, configurations, rules and live harness were all written by hand for this run, the experiment ran only on the local loopback, and process control touched only processes I started. No client information and no third-party systems are involved.
