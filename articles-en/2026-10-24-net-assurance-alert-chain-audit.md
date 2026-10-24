# Ten Alert Rules, Two That Can Never Fire: An End-to-End Audit of the net-assurance-lab Alert Chain

Author: Guangyi Zhao

## 1. Problem and background

net-assurance-lab is a loopback network-reliability bench I built: a traffic generator, an application-layer fault-injection proxy, and a generated fault report, all running against 127.0.0.1. On 2026-10-19 I added a production-shaped monitoring module — a read-only Prometheus exporter, 10 alert rules (monitoring/rules/alerts.yml), and two Grafana dashboards (24 panels, 26 query targets). The verification at the time was thorough: real Prometheus 3.15.0 and Grafana 13.2.4 binaries, run end to end, and VERIFICATION.md recorded the live alert state — 2 of the 10 rules firing (NalLinkFlapDetected, NalBaselineP99LatencyHigh), the rest inactive, annotated as correct.

This article questions that word "correct". A rule that does not fire admits two explanations: the data never crossed the line, or the expression can never produce a result at all. The first is an alert doing its job; the second is a dead alert that fails silently. The 2026-10-19 record gave data-level reasons for three of the inactive rules (baseline loss, malformed echoes, result freshness), but NalFlapShareDominatesLoss was never reconciled on its own — and the run artifacts needed to recompute it still exist. In that run (20261019-171627, "R0" below), the proxy dropped 2,861 packets inside link-flap windows and 2,352 to random loss. By the rule's own annotation, its trigger condition — flap share exceeding random-loss share — held in R0. It did not fire, not because nothing was wrong, but because it cannot fire.

The headline: 2 of the 10 rules are structurally dead — NalFlapShareDominatesLoss and NalBaselineThroughputCollapse. Both share one root cause: they compare two series of the same metric that differ in exactly one label value, using a vector-to-vector operation, and PromQL's default vector matching requires both sides to carry identical label sets. Differ in one label and the match is empty — for any data, forever. Feed the real rule engine an echo throughput crushed to 10% of send, or a flap share at 3x the loss share, held for ten minutes: both rules still produce nothing. The fix is under two lines (an ignoring(cause) clause and a ratio-form rewrite), and with it both rules fire on schedule in the same test inputs. The other 8 rules each show at least one observed firing path in this audit; all 26 dashboard targets match series in the exporter output — the dashboards escaped the bug because every panel expression is a single-vector selector, with no vector-to-vector operation anywhere.

## 2. Method

The chain under test (all from the lab repository: monitoring/ and src/prom_exporter.py):

- The exporter: Python standard library only. On every scrape it re-reads the latest run's artifacts in results/latest/ — four scenario summaries, per-packet CSVs, server counters, the final summary line of the proxy decision log, and run_meta.json — and renders the nal_* metric families. It publishes a snapshot of the most recent finished run, so values are constant between runs. That premise shapes how for: and staleness must be read here, and the rules file's header comment says so honestly.
- The Prometheus configuration (monitoring/prometheus.yml): 5s scrape interval, 15s rule-group evaluation interval, and alerting.alertmanagers set to an empty list — no Alertmanager is wired, so alerts exist only on Prometheus' own /alerts page and API.
- The rules: 10 alerts across info / warning / critical. The for: distribution is 0s once (NalMalformedPacketEchoed, critical), 15s once (NalLinkFlapDetected, info), 1m seven times, and 5m once (NalResultsStale).

Four layers of testing, each closer to the real engine than the last:

1. Static: promtool check rules and check config, for syntax and configuration validity.
2. Semantic — alerts as code: Prometheus' own promtool test rules, feeding constructed input series and asserting which alerts must be firing and which must be absent at named evaluation times; plus 15 fixtures of my own that push synthetic results directories through the exporter's real collect() code path, covering threshold-equality boundaries (every expression uses strict greater-than, so equality must not fire) and single-rule flips. Every rule is judged on two tracks: first, "intent" recomputed directly from the run artifacts; second, what the expression actually produces under PromQL semantics. A disagreement between the tracks is the defect — the intent track exists so I am not merely testing my own paraphrase of the expression.
3. Live: a fresh download of the official Prometheus 3.15.0 release (tarball 111,651,578 bytes, gzip-verified), run with the repository's own prometheus.yml, the exporter pointed at a copy of run R0 (the repository itself untouched). Three things: instant queries comparing the suspect expressions against corrected variants; four snapshots of /api/v1/alerts over roughly 336 seconds, covering pending-to-firing transitions including the slowest rule (NalResultsStale, for: 5m); and a recovery test — the copy is patched into a "recovered" run (current run_id, baseline p99 back to 5 ms, proxy dropped_flap set to 0) and the alert set is re-read 45 seconds later.
4. Reconciliation: all 26 dashboard targets are matched against the exporter output, key panel values are checked against the underlying JSON artifacts, and the full alert sets of the two archived runs, R0 (20261019-171627) and R1 (20261019-154535), are computed side by side to see which rules run-to-run jitter can flip.

How this article itself was reviewed is recorded in the ledger and review notes for the series; every number below comes from data/2026-10-24-alert-chain-bench.json, data/2026-10-24-alert-chain-live.json, and the two promtool test files archived alongside them.

## 3. Measurements

### 3.1 Two archived runs, and the alert set "today"

Intent values recomputed from the artifacts:

| Input | R0 (20261019-171627) | R1 (20261019-154535) |
|---|---|---|
| Baseline loss ratio (burst / sustained) | 0 / 0 | 0 / 0 |
| Baseline p99 (burst / sustained, ms) | 12.486 / 120.452 | 5.517 / 6.952 |
| Fault-scenario loss ratio | 0.5897 | 0.5275 |
| Fault-scenario p99 (ms) | 443.359 | 245.775 |
| Proxy drops: flap / random loss | 2,861 / 2,352 | 2,595 / 2,680 |
| Flap share / loss share | 0.19377 / 0.15930 | 0.16115 / 0.16643 |
| Malformed packets echoed | 0 | 0 |

Evaluating the original expressions against R0 while it was fresh on 2026-10-19 (ignoring for: timing) gives exactly the 2 firing rules the live record showed. Evaluating the same bytes today adds NalResultsStale: in the live snapshot its value reads 438,034 seconds (about 5.07 days), because the run has been sitting there for five days. Not one byte of the run changed; the alert set moved with the wall clock. That is the necessary consequence of a snapshot exporter, and the reason NalResultsStale exists. R1 evaluated today fires 2 (flap detection, staleness): its worst baseline p99 is 6.952 ms, far under the 50 ms line, and its flap share genuinely is smaller than its loss share (0.16115 vs 0.16643), so NalFlapShareDominatesLoss should not fire on R1 by intent. That last fact matters in Section 3.2: it is why the defect is invisible on R1 and only surfaces on R0.

### 3.2 Evidence against the two dead rules

Live instant queries against R0 (real Prometheus 3.15.0, real exporter):

| Query | Result |
|---|---|
| nal_fault_proxy_drop_ratio{cause="flap"} | 1 series, 0.19377 |
| nal_fault_proxy_drop_ratio{cause="loss"} | 1 series, 0.15930 |
| The two compared as written (flap greater than loss) | empty |
| Same comparison with ignoring(cause) | 1 series, 0.19377 |
| Ratio form: flap / ignoring(cause) loss | 1 series, 1.21641 |
| Throughput as written (echo below 0.5 x send, baselines) | empty |
| Throughput ratio form: echo / ignoring(kind) send | 2 series, both 1 (burst and sustained echo equals send; R0 is healthy, so this correctly does not cross 0.5) |

Both sides of each comparison exist and are sizeable; the comparison itself returns nothing. The official Prometheus documentation describes vector matching as one-to-one by default, pairing entries only when they have the exact same set of labels and values, and its ignoring example states that without the keyword "there would have been no match as the metrics do not share the same set of labels" (reference 1). These two rules compare two slices of one metric: the drop-ratio slices differ only in cause, the throughput slices only in kind. The more precise the selectors, the more certain the label-set mismatch, and the more permanently empty the result.

The rule engine itself confirms it. promtool test rules (data/2026-10-24-promtool-test.yml) asserts against the original rule file: with flap share 0.30 against loss share 0.10 held for 10 minutes, NalFlapShareDominatesLoss produces zero alerts; with echo throughput at 10% of send (100 vs 1,000 pps) held for 10 minutes, NalBaselineThroughputCollapse produces zero alerts. Both assertions pass — passing means the engine, given a strongly true intent condition for a full ten minutes, still outputs nothing. The exporter fixtures agree: at 10% echo, the original semantics yield 0 alert instances and the corrected form yields 2 (one per baseline scenario); at 3x flap share, 0 versus 1.

The corrected forms were not left at the query layer. Both changes were written into a copy of the rules file (data/2026-10-24-alerts-patched.yml; ignoring(cause) for the flap rule, the ratio form echo / ignoring(kind) send below 0.5 for the throughput rule), and the same promtool tests were re-pointed to expect firing (data/2026-10-24-promtool-test-patched.yml): both rules are silent at the 30-second evaluation point (for: 1m not yet met) and firing at 2 minutes, with labels and annotations matching expectations exactly — SUCCESS. On the data side, the corrected ratio on live R0 data returns 1.21641, matching the artifact recomputation 2,861 / 2,352. One disclosure: this audit did not modify the repository's alerts.yml. The fix ships as a patched copy plus its tests in the experiment data; the article vouches for "the fix works", not for having merged it.

### 3.3 for:, recovery, and silences

for: behavior was tested on both the promtool harness and the live server. In promtool, the for: 0s malformed rule is firing at the first evaluation point (15s); the for: 15s flap rule is firing by the 1-minute evaluation point; the for: 5m staleness rule shows zero alerts at 4 minutes and is firing at 6 minutes. Live snapshots (R0 copy; seconds since server start, approximately):

| Time | NalLinkFlapDetected | NalBaselineP99LatencyHigh | NalResultsStale |
|---|---|---|---|
| ~62s | firing (value 1) | pending (value 120.452) | pending (value 438,034) |
| ~85s | firing | firing | pending |
| ~336s | firing | firing | firing |
| Recovery patch +45s | none | none | none |

The recovery patch touched only the scratch copy: run_id set to the current time, both baseline scenarios' p99 set to 5.0, the proxy summary's dropped_flap set to 0. Forty-five seconds later, /api/v1/alerts returned an empty array — all three firing alerts resolved. No rule in the file sets keep_firing_for, so per the official semantics an alert deactivates at the first evaluation where its condition no longer holds (reference 2); the measurement agrees. One model-level supplement: a state-machine simulation I wrote on the 15s evaluation grid (part D of data/2026-10-24-alert-chain-bench.py) shows a baseline-p99 excursion lasting only 45 seconds entering pending and rolling back without ever firing. That is model evidence only; the equivalent engine semantics are covered by the 4-minute and 6-minute promtool points above.

Silences get the shortest section: this stack has none. prometheus.yml sets alertmanagers to an empty list. Silences are an Alertmanager feature; with no Alertmanager there is no silence entry point and no notification path at all — a firing critical malformed-packet alert is one more row on a web page. Today, muting this system means editing a rule or editing data. For a bench whose consumer is the alerts page, that is acceptable; for anyone copying these rules toward production, it is the first thing to fix.

### 3.4 Threshold boundaries and the remaining rules

The 15 exporter fixtures (all through the real collect() code path):

| Fixture | Instances under original expressions | Note |
|---|---|---|
| Baseline loss exactly 0.05 (equality) | 0 | strict greater-than behaves |
| Baseline loss 0.06 | 2 | one instance per baseline scenario |
| Baseline p99 exactly 50 (equality) | 0 | |
| Baseline p99 at 60 | 2 | |
| Fault loss exactly 0.75 (equality) | 0 | |
| Fault loss 0.80 | 1 | |
| Fault p99 exactly 1000 (equality) | 0 | |
| Fault p99 at 1200 | 1 | |
| Flap drops zero | 0 | nal_link_flap_detected is 0; no false positive |
| One malformed packet echoed | 1 | the critical rule flips correctly |
| run_id set to now | 0 | staleness stays silent |
| run_id 25 hours old | 1 | staleness fires |
| One scenario summary deleted | 1 | NalExporterResultsMissing fires per missing group |

That completes the main ledger: 8 rules each have at least one measured firing path (live, promtool, or fixture), and 2 rules fire under no input, with the root cause identified.

### 3.5 Dashboard reconciliation

The two dashboards hold 24 panels and 26 query targets. Matched one by one against the R0 exporter output, all 26 return at least one series, and the key values agree with the artifacts (fault loss 0.5897; the p99 ladder; proxy counters 9,552 / 2,861 / 2,352 for forwarded / dropped_flap / dropped_loss). The dashboards avoided the dead-rule disease for a structural reason: all 26 targets are single-vector selectors. When a panel wants two series compared, it plots them on the same graph rather than comparing them inside PromQL. Grafana itself was not re-run in this audit (a 461 MB binary I did not download again); the dashboard evidence is expression-level reconciliation against the exporter, plus the dated 2026-10-19 live Grafana record in VERIFICATION.md — that time boundary is stated rather than smoothed over.

## 4. Analysis and trade-offs

Why did this survive an end-to-end verification? Three layers. First, promtool check validates syntax: a dead expression is perfectly legal PromQL, so the static layer reports SUCCESS. Second, the live observation explained inactivity in bulk: the record gave data reasons for three inactive rules, and the flap-share rule was swept into the same "correct" without an individual reconciliation. Third — the dangerous layer — on R0 the flap story did not look unalerted. NalLinkFlapDetected (info) fired, so "flap was detected" had its receipt; the share-comparison rule's silence left no visible hole on the page. An absent alert never raises its own hand, which is exactly what makes this failure mode expensive.

The practice I take from it is a single rule, cheap enough to impose on any alert repository: every alert ships with three test cases — intent true and firing, intent false and silent, threshold equality and silent — executed with promtool test rules whenever a rule changes. An alert that has never fired in any test is indistinguishable from a dead alert; the two dead rules here share precisely that biography, not a mistyped operator. On evidence grading: the root cause and the fix both carry live-engine proof (grade A); "per-rule reconciliation prevents this class" is an engineering claim extrapolated from one case (grade B).

One threshold I deliberately leave alone: the 50 ms baseline p99. R0's sustained p99 is 120.452 ms and R1's is 6.952 ms — same code, same host, two runs landing on opposite sides of the line, with host scheduling jitter as the documented cause, noted at the time with an explicit decision not to retune the threshold to hide it. I agree with keeping it: the rule's annotation points at host scheduling before link faults, so its reading is honest; an alert on a measurement bench that gets retuned to chase jitter into silence stops being a measurement tool. The cost is real, though: on this host the rule's signal-to-noise is inherently limited, and when it fires, check the host before the network.

One further blind spot is reasoning, not measurement, and is labeled as such for whoever merges the fix: NalExporterResultsMissing depends on a series the exporter itself emits, and it does fire when the exporter is alive but artifacts are missing (fixture-verified). If the exporter process dies outright, its input series disappears, and under instant-vector semantics the rule has nothing to evaluate — the blindness alert is itself blind to the exporter's death. The standard cure is a separate rule on scrape health (up or absent()), which this file does not have. I did not spend a live round on it: it would verify generic PromQL semantics rather than anything specific to this chain, so it is recorded as inference, not evidence.

Finally, the choice of fix forms. The flap rule needed only ignoring(cause) — the smallest possible change. For throughput I did not use the "add ignoring(kind) to the original comparison" variant; I used the ratio form, echo / ignoring(kind) send below 0.5, which says the same thing as the rule's annotation ("echo fell below half of send"), reads more directly, and is the form actually verified here (the other variant is outside this audit's test scope, and I make no syntax claim about it). The ratio form has one measured side effect: the fired alert's labels drop kind (the result carries scenario and mode only), which the promtool expectations exposed. I accept it — scenario is enough to locate the instance. Both corrected forms passed full-cycle promtool tests in the patched copy, while the repository file stays untouched: this article is an audit report, not a license to edit someone's alert configuration in passing — and since the lab doubles as a job-search proof artifact, its changes belong in a normal commit flow by its owner, wearing a different hat.

## 5. Limitations and open questions

- The bench is loopback-only, and its metrics describe snapshots of finished runs, not a live network's continuous state. What was measured here is expression semantics, timing semantics, and reconciliation behavior of an alert chain — none of it transfers to judging any real network's alerting quality.
- In this chain, for: measures "how long this bad snapshot has been continuously observed by scrapes", not "how long a network condition persisted" — the rules file's header declares exactly that. Point these rules at a streaming exporter and the meaning of for: changes; thresholds and durations would need re-derivation.
- Grafana was not re-run (see 3.5); the dashboard conclusion rests on expression reconciliation plus a five-day-old live record. Anyone needing same-day full-chain evidence should budget the Grafana download and one more round.
- Among the promtool positive controls, NalBaselineP99LatencyHigh's annotation embeds a templated $value, making exact-match assertions costly; its firing evidence comes from the live API rather than promtool. The other positive controls (flap, staleness, malformed) assert labels and annotations exactly.
- My offline PromQL evaluator covers only the expression shapes present in this file. Wherever it and the real engine could disagree, promtool and the live server are the authority — in this audit they agreed on every case.
- Open: the 0.75 ceiling of NalFaultLossAboveInjectionBand comes from a rough injection budget (20% random loss each way compounded with a 0.6/2.5 flap duty cycle, roughly 50–65% end-to-end); this audit verified only its equality boundary, not its discriminating power against a scenario with loss beyond the injection. How an up/absent-style blindness rule should be added, and how it should divide labor with the existing ten, is left to the fix-merge round.

## 6. References

1. Prometheus documentation, Querying / Operators, "Vector matching": one-to-one matching pairs entries with the exact same set of labels and values by default; ignoring / on change the matching, and the worked example notes that without ignoring(code) there would have been no match. https://prometheus.io/docs/prometheus/latest/querying/operators/
2. Prometheus documentation, Configuration / Alerting rules: the for: clause, pending versus firing, and deactivation at the first evaluation where the condition is not met when keep_firing_for is absent. https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
3. Prometheus documentation, Configuration / Unit testing for rules: the promtool test rules file format and assertions. https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/
4. Code under test (local repository net-assurance-lab): monitoring/rules/alerts.yml (the 10 rules as written), monitoring/prometheus.yml (empty alertmanagers list; scrape and evaluation intervals), src/prom_exporter.py (how collect() builds each metric), VERIFICATION.md monitoring supplement (the 2026-10-19 live record: 2 firing rules, all 26 dashboard targets returning series).
5. This audit's data (same convention as earlier entries in this series; archived in the project data/ and mirrored into the tech-deep-dives repository's data/ with the article): 2026-10-24-alert-chain-bench.py / .json (intent track and fixtures), 2026-10-24-alert-chain-live.json (live queries and four alert snapshots), 2026-10-24-promtool-test.yml (tests against the original rules), 2026-10-24-alerts-patched.yml and 2026-10-24-promtool-test-patched.yml (the fix copy and its expect-firing tests). The Prometheus binary is the official 3.15.0 release, gzip-verified after download, and is not redistributed with the repository.

---

Author: Guangyi Zhao. The experiment design, code, and data in this article are clean-room work of my own: the bench, the exporter, the fixtures, and the evaluator were all hand-written by me; every experiment ran on local loopback and local files only, and no client information or third-party system is involved.
