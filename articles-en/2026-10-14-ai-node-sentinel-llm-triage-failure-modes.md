# Before You Wire an LLM Into GPU Fault Triage: AI-Node-Sentinel's Integration Point and Six Measured Failure Modes

Author: Guangyi Zhao
Date: 2026-10-14
Subject: AI-Node-Sentinel (open-source project by the author, github.com/Ezra-Zhao/AI-Node-Sentinel), scaffold v0.1, Python 3.12.3
Environment: Linux x86_64 VM, repository code run unmodified; LLM experiments use local fake providers implementing the project's own protocol — no real model API was called

## 1. Problem and background

In a GPU cluster, the first signal of failing hardware is usually one line in the kernel log: an Xid. XID is NVIDIA's numbering scheme for GPU hardware and firmware errors — a GPU falling off the PCIe bus, an uncorrectable double-bit ECC error, an NVLink fault, a GSP firmware timeout each has its own code. The on-call ritual is manual: pull dmesg from a thousand GPUs, look up what each code means, then decide — drain the node, reset the GPU, reboot, or start an RMA. Decide slowly and the training job keeps retrying on broken hardware, burning GPU-hours that cost real money.

The obvious impulse is to hand this to an LLM agent. Let the model read telemetry, look up error codes, and recommend actions — isn't that exactly what agents are for?

My own open-source project, AI-Node-Sentinel, was scaffolded around that idea: telemetry comes in, XID events are extracted, a lookup table enriches them, triage rules are applied, and a structured report comes out, with a LangChain-based slot reserved for LLM reasoning. Let me state the honest status up front, because everything after this paragraph depends on it: the project is scaffold v0.1, and its README says so. The triage decision tree is a deliberate stub — every event gets NEEDS_HUMAN_REVIEW with confidence 0.0. The LangChain provider is also a stub that raises NotImplementedError on construction. All telemetry is synthetic, produced by a bundled simulator. Only three stages actually run: ingestion, lookup, and report rendering.

So this is not a write-up of a production diagnostic system. It is the opposite: I put the scaffold on the dissecting table and ran six fault-injection experiments to measure where this pipeline would break once an LLM is actually wired in. The results generalize to anyone attaching an LLM to an operations system, because none of the six breakpoints is a model-capability problem. They are wiring problems: an output contract that doesn't match, evidence fed too thin, one malformed record poisoning the whole batch, a prompt path coupled to the working directory, stateless single-event myopia, and corroborating signals discarded by the pipeline itself. A stronger model fixes none of these.

## 2. Method and architecture

The codebase is small: eight core Python files, roughly 470 lines including tests and the demo. Four parts. agent/schemas.py defines the data types: TelemetryEvent (a normalized event with source, kind, and payload), XidFinding (an XID event enriched by lookup), and TriageVerdict (action, confidence, rationale). tools/xid_lookup.py is a static table mapping codes to name, category, and severity, seeded only from NVIDIA's public XID documentation and Google Cloud's GPU troubleshooting guide; a miss returns None — it never guesses. tools/triage_rules.py holds the decision tree, currently the stub. agent/orchestrator.py is the TriageAgent: ingest, extract XID events, triage each one, render the report.

The LLM integration point lives in agent/llm.py: a minimal protocol, LLMProvider, requiring one method, reason(system_prompt, evidence) -> str. The orchestrator first computes the deterministic verdict; if a provider is present, it builds an evidence string, calls the provider, and appends the returned text to the verdict's rationale with an [LLM] prefix. The draft system prompt in prompts/triage_system.md instructs the model to cite only the evidence given, to say explicitly when a code is unknown, to return exactly one action with a confidence between 0 and 1, to force NEEDS_HUMAN_REVIEW whenever confidence is below 0.7, and to answer in JSON.

Method: five experiment groups against the unmodified repository, with the scripts and raw JSON archived alongside this article. (1) Baseline scale: the bundled simulator generates telemetry windows for 4, 16, and 64 nodes; I record event composition, verdict distribution, and pipeline latency. (2) Lookup coverage: table size plus ten out-of-table probe codes. (3) Malformed-data injection: events with a missing xid key, a non-numeric xid, and xid=None, mixed into otherwise good batches. (4) Fake-LLM experiments: a local provider that returns exactly the JSON the prompt demands, to observe what actually changes in the verdict; then a provider that always raises, to observe fault propagation. (5) Failure-mode probes: repeat faults on one GPU, the fate of corroborating events, and prompt loading from a different working directory.

## 3. Measurements

### 3.1 Baseline: the deterministic part is too fast to matter, and the verdicts are the stub's

The simulator emits one thermal and one ECC baseline event per GPU, then injects one or two XID events on about 35% of GPUs:

| Scale | Events | XID events | Verdicts | Unknown verdicts | Severity (critical/high/unknown) | Pipeline time |
|---|---|---|---|---|---|---|
| 4 nodes × 8 GPUs (seed 42) | 76 | 12 | 12 | 1 | 10 / 1 / 1 | ~0.1 ms |
| 16 nodes × 8 GPUs (seed 42) | 313 | 57 | 57 | 5 | 39 / 13 / 5 | ~0.2 ms |
| 64 nodes × 8 GPUs (seed 42) | 1,285 | 261 | 261 | 34 | 157 / 70 / 34 | ~0.7 ms |
| 64 nodes × 8 GPUs (seed 7) | 1,295 | 271 | 271 | 35 | 177 / 59 / 35 | ~0.7 ms |
| 64 nodes × 8 GPUs (seed 123) | 1,282 | 258 | 258 | 28 | 167 / 63 / 28 | ~0.7 ms |

Three observations. First, every verdict is NEEDS_HUMAN_REVIEW at confidence 0.0. That is stub behavior, not measured intelligence, and I record it as the control group for what follows. Second, roughly 1,300 events process in under a millisecond — about 1.77 million events per second on the raw single-run perf_counter timing (the table rounds to 0.1 ms; sub-millisecond figures are order-of-magnitude only, not a precise benchmark) — because lookup is a dictionary read. At this article's scale the deterministic part is free; streaming ingestion and window state will need their own measurement later, but the bulk of future latency and cost will come from the LLM step. Third, do not misread the 11–13% unknown share: the simulator's injection pool has eight codes, one of which (999) is a deliberately synthetic unknown, so the unknown rate is an artifact of pool design — one eighth by construction — not a field measurement of unknown codes in a real fleet.

The repository's six bundled tests all pass when invoked directly (determinism, known-code lookup, unknown codes not guessed, stub routing to human review, report shape). This machine has no pytest installed, so I ran the test functions directly rather than through the runner; noted for accuracy.

### 3.2 Lookup coverage: seven codes, everything else is "unknown"

The table contains exactly seven codes: 13, 31, 48, 74, 79, 119, 120. Ten out-of-table probe codes (43, 45, 56, 63, 64, 68, 92, 94, 109, 154) all return None and are treated exactly like 999: severity unknown, known=False, routed to human review. The routing behavior is right — refusing to guess is this pipeline's most important safety property. The coverage is another matter: any XID outside those seven earns the operator exactly one piece of information, "an unknown error occurred, go look." The table was hand-seeded from public documents; extending it is unglamorous work, and section 4.3 argues it is still not the first thing to fix.

### 3.3 Malformed data: one bad event poisons the batch

The orchestrator extracts the code with int(event.payload["xid"]) — no validation, no per-event isolation. Mixing malformed events into good batches:

| Injection | Outcome |
|---|---|
| One well-formed event | Completes, 1 verdict |
| Good + missing xid key + good | Entire run raises KeyError; completed verdicts are lost with it |
| Good + xid as a non-numeric string | Entire run raises ValueError |
| Good + xid=None | Entire run raises TypeError |

run() processes events in a list comprehension, so the first exception discards every verdict in the window. Translate to production: a dmesg parser will eventually emit a field-incomplete event, and when it does, the failure mode is not "one event undiagnosed" but "the whole window's verdicts vanish, as a process-level exception instead of a line in the report." Per-event isolation with a bad-record counter is table stakes for this kind of pipeline, and it is absent here.

### 3.4 The fake-LLM experiment: the output contract is broken, and the model doesn't get a vote

This is the experiment the article exists for. I implemented a fake provider that obeys the system prompt perfectly, returning JSON that recommends DRAIN_NODE at confidence 0.95 for XID 79 (GPU fallen off the bus). Wired into the orchestrator, the verdict's actual state:

| Field | Fake provider output | Final verdict |
|---|---|---|
| action | DRAIN_NODE | NEEDS_HUMAN_REVIEW (unchanged) |
| confidence | 0.95 | 0.0 (unchanged) |
| rationale | The full JSON | Appended verbatim as text, prefixed [LLM] |

The code makes the reason plain: the protocol returns a string, the orchestrator only concatenates it, nothing ever parses the JSON, and nothing overwrites the deterministic verdict. The prompt's output format and confidence gate are a gentlemen's agreement with the model that the code side never honors. Even if the real LangChain provider were implemented tomorrow and the model followed the format perfectly every time, the triage decision would remain 100% determined by the stub; the LLM's total influence would be a paragraph pasted into the rationale.

The second half of the experiment is evidence thickness. The exact evidence string the orchestrator assembles is: node=node-00 gpu=0 xid=79 name=GPU has fallen off the bus severity=critical ts=<timestamp>. That is all. The lookup entry has category and notes fields — including remediation hints and sourcing notes — and neither enters the evidence. The same GPU's thermal and ECC readings cannot enter it either, because the evidence is built inside the per-event triage function, whose signature has no window context at all. The prompt's first rule orders the model to cite only the evidence provided. The pipeline starves the evidence down to a restatement of the error name, then forbids the model from reaching beyond it. If the model gives an informative answer anyway, it can only do so by breaking the rule. That contradiction is a wiring decision, not a model defect.

Third: fault propagation. Replace the provider with one that always raises RuntimeError, and triage_event lets the exception straight through — the whole run dies, the same death as section 3.3. A provider is an external dependency; timeouts, rate limits, and network jitter are its normal weather. An optional reasoning step should degrade to the deterministic verdict, never take the batch down with it. There is no degradation path here.

### 3.5 The prompt path is coupled to the working directory

The orchestrator loads the prompt with a relative path, open("prompts/triage_system.md"). From the repository root it works. From /tmp, the identical code raises FileNotFoundError immediately. (The LangChain provider raising NotImplementedError on construction is an honest stub, not a defect.) The relative path is the kind of bug that bites exactly once, in production: services started by systemd, containers, or schedulers rarely have the repository root as their working directory, while a developer's terminal always does — which is why it never reproduces at a desk.

### 3.6 No memory, and corroboration blindness: two failure modes with one root

Repeat faults do not escalate. Three XID 79 events on the same GPU within three hours produce three verdicts that have never heard of each other: same action, same confidence, same rationale. Causality, stated precisely: the identical verdicts are directly caused by the decision tree being a stub — any architecture would produce them today. The architectural problem sits one layer down. The stub's own comments sketch the intended real rule — XID 79 twice in 24 hours on one GPU should mean drain plus reboot — but the orchestrator triages events one at a time, statelessly, so even once that rule is written, the pipeline has nowhere to put it. This is not only a missing rule; it is missing state.

Corroborating signals are filtered out by the pipeline itself. I built a three-event window by hand: one GPU reports an ECC double-bit error count of 17, then a temperature of 104 °C, then XID 13. The prompt's second rule says app-level faults like XID 13/31 should not trigger a drain recommendation without corroborating evidence — which implies corroboration should change the judgment when present. The measured result: three events in, one verdict out. The two non-XID events are dropped at the extraction stage; they produce no verdicts and are never attached to the XID 13 verdict as context. At baseline scale this is 1,024 of 1,285 events in the 64-node window. The pipeline demands corroboration-aware reasoning in its prompt while deleting the corroboration from its data path.

## 4. Analysis and trade-offs

### 4.1 Deterministic first, LLM second — and the order is not negotiable

The scaffold's best judgment call is its layering: lookup and rules in a deterministic core, the LLM as a downstream reasoning supplement, and — until the decision tree exists — everything routed to humans with an honest confidence of 0. The reasoning is simple. Drain, reset, reboot, and RMA are real operations on production hardware. Anything a table or a rule can decide should never be improvised by a probabilistic model at 3 a.m.; the LLM's value is synthesis and explanation, not authority.

Section 3.4 yields a counterintuitive corollary: the broken output contract is currently an accidental safety net. Because the model's JSON is never parsed into the verdict, a hallucinating model today can pollute a rationale but cannot drain a node. But it is an accident, not a design. The correct fix is not to preserve the break; it is to add parsing plus validation — actions must land inside the site's runbook vocabulary, confidence below 0.7 must be rewritten to human review in code (the prompt already states this rule; move it from prose into the program), and parse failure must degrade to the deterministic verdict alone. Whoever wires up the parsing without the validation has personally removed the safety net.

### 4.2 The failure-mode list, in fix order

None of the six failure modes needs a better model or a better prompt. All six are ordinary engineering, and I would fix them in this order:

1. Per-event isolation. Wrap each event's triage in exception handling; count and surface bad records in the report. Batch survival comes before everything else.
2. Honor the output contract. JSON parsing, vocabulary validation, and the confidence gate in code, per section 4.1.
3. Evidence assembly. Include the lookup's category and notes, and pass the triage function a per-GPU window summary — recent same-code counts, thermal and ECC extremes — so the prompt's "cite only the evidence" rule becomes executable.
4. A state layer. Repeat counting and escalation need window-level aggregation, which means restructuring from stateless per-event triage to aggregate-then-triage. It is an architectural change, so it goes after the contract and evidence fixes.
5. Resource paths and graceful degradation. Load the prompt as a package resource or absolute path; wrap provider calls with timeout and exception handling that fall back silently — but visibly in the report — to the deterministic verdict.
6. Corroboration plumbing. Stop discarding non-XID events at extraction; attach them to the same GPU's XID verdicts as context. It shares a root with item 3 but is listed separately: item 3 changes the evidence template, this one changes the data path.

Extending the lookup table is deliberately not on this list. It is data-dictionary work, not a failure mode; seven codes is thin coverage and the table should grow — after these six, because without them a 70-code table still dies batch-wide on the first malformed event.

### 4.3 A judgment: trustworthiness in systems like this comes from restraint, not from the model

The design choices I would defend most strongly in this scaffold are the things it refuses to do. Unknown codes are not assigned invented meanings. An unfinished decision tree issues no actions. Simulated data is labeled SIMULATED from the generator to the report header. The stub raises NotImplementedError instead of returning a fabricated rationale. Together these refusals make every output auditable: for any line in the report you can tell whether it came from the table, a rule, or a model. That is precisely what gets lost first when an LLM is bolted onto an operations system — once fluent model prose washes over the deterministic core's true state, the on-call engineer can no longer tell what was looked up from what was made up, and the report stops deserving trust. All six failure modes point at the same repair: make the model's scope, evidence, and failure behavior explicit in code, not implied by prompt wording.

## 5. Limitations and open questions

The limitations are material. First, all telemetry is synthetic, generated by the bundled simulator; its distributions are set by injection probabilities and the injection pool, so every proportion in this article validates pipeline behavior only and says nothing about fault distributions in a real fleet. Second, the LLM experiments use a local fake provider and verify wiring contracts and fault propagation; no real model was called, so this article makes no claim about any model's reasoning quality. How often a real model, fed evidence this thin, would reach beyond it and fabricate is a separate measurement that requires wiring one up. Third, the scale ceiling here is 64 nodes and about 1,300 events on a single VM; concurrent ingestion, persistence, and alerting channels are untested. Fourth, lookup coverage is reported as table size plus out-of-table probes; I did not diff the table against NVIDIA's complete published catalog, so no coverage denominator is claimed.

Three open questions remain. The aggregation grain for the state layer — per GPU, per node, or per NVLink domain — implies different escalation rules and false-positive costs, and calibrating it needs real fault sequences. The 0.7 confidence gate in the draft prompt was picked, not calibrated; once a real model is wired in, it should be set by replaying historical tickets. And once corroborating evidence enters triage, the baseline thermal and ECC stream is roughly four times the XID volume — what evidence assembly costs in tokens and context length has to be measured when the real model arrives.

## 6. References

1. AI-Node-Sentinel source (version measured here): github.com/Ezra-Zhao/AI-Node-Sentinel — key files: agent/orchestrator.py (orchestration and evidence assembly), agent/llm.py (LLMProvider protocol and LangChain stub), agent/schemas.py (data types), tools/xid_lookup.py (lookup table), tools/triage_rules.py (decision-tree stub), prompts/triage_system.md (draft system prompt), telemetry/simulator.py (simulator).
2. Experiment scripts and raw data for this article: data/2026-10-14-sentinel-bench.py and data/2026-10-14-sentinel-bench.json, archived with this article; every number can be re-checked by re-running the script.
3. NVIDIA, Xid Errors documentation: docs.nvidia.com/deploy/xid-errors — the authoritative source for the lookup metadata, also cited in the header of tools/xid_lookup.py.
4. Google Cloud, Troubleshooting GPU issues: cloud.google.com/compute/docs/troubleshooting/troubleshooting-gpus — cross-check source for the lookup table, as above.

---

Author: Guangyi Zhao. The code, experiments, and text in this article are clean-room work by the author: the subject is an open-source scaffold project maintained by the author, all telemetry is synthetic data from that project's simulator, and all experiments ran in the author's own local environment. No customer information, customer systems, or third-party non-public data are involved. Every number comes from the measurements listed at the top of this article; the simulated nature of the data and the limits of the conclusions are stated in the text and in section 5, and no scaffold state is presented as a production system.
