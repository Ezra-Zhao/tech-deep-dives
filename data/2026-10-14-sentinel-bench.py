#!/usr/bin/env python3
"""AI-Node-Sentinel failure-mode experiments (2026-10-14).

Runs against the unmodified scaffold at ~/workspace/github/AI-Node-Sentinel.
Every experiment is labelled; results are dumped as JSON for the article.
No LLM API is called: the LLM experiments use local fake providers that
implement the repo's own LLMProvider protocol.
"""
import json, sys, time, traceback
from pathlib import Path

REPO = Path.home() / "workspace/github/AI-Node-Sentinel"
sys.path.insert(0, str(REPO))

from agent.orchestrator import TriageAgent
from agent.schemas import TelemetryEvent
from telemetry.simulator import simulate_cluster, XID_POOL
from tools.xid_lookup import XID_INFO, lookup_xid

R = {}

# ---- E1: baseline scale / composition / latency -------------------------
e1 = []
for nodes, gpus, seed in [(4, 8, 42), (16, 8, 42), (64, 8, 42), (64, 8, 7), (64, 8, 123)]:
    events = simulate_cluster(num_nodes=nodes, gpus_per_node=gpus, seed=seed)
    agent = TriageAgent()
    t0 = time.perf_counter()
    report = agent.run(events, node_count=nodes, simulated=True)
    dt = time.perf_counter() - t0
    kinds = {}
    for e in events:
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    unknown = sum(1 for v in report.verdicts if not v.finding.known)
    e1.append({
        "nodes": nodes, "gpus_per_node": gpus, "seed": seed,
        "events_total": len(events), "events_by_kind": kinds,
        "xid_verdicts": len(report.verdicts),
        "non_xid_events_dropped_from_verdicts": len(events) - len(report.verdicts),
        "unknown_xid_verdicts": unknown,
        "severity_breakdown": report.counts_by_severity(),
        "actions": sorted({v.action for v in report.verdicts}),
        "confidences": sorted({v.confidence for v in report.verdicts}),
        "run_seconds": round(dt, 4),
        "events_per_second": round(len(events) / dt) if dt > 0 else None,
    })
R["E1_baseline"] = e1

# ---- E2: lookup coverage -------------------------------------------------
R["E2_lookup"] = {
    "table_size": len(XID_INFO),
    "table_codes": sorted(XID_INFO.keys()),
    "simulator_pool": XID_POOL,
    "probe_codes_absent_from_table": [c for c in [43, 45, 56, 63, 64, 68, 92, 94, 109, 154] if lookup_xid(c) is None],
    "lookup_999": lookup_xid(999),
}

# ---- E3: malformed payload -> does one bad event kill the whole run? -----
def try_run(events, label):
    try:
        rep = TriageAgent().run(events, node_count=1, simulated=True)
        return {"label": label, "outcome": "completed", "verdicts": len(rep.verdicts)}
    except Exception as ex:
        return {"label": label, "outcome": "raised",
                "exception": f"{type(ex).__name__}: {ex}"}

good = TelemetryEvent.xid("node-00", 0, 79, "2026-10-01T00:00:00+00:00")
missing = TelemetryEvent(node_id="node-00", gpu_index=1, timestamp="2026-10-01T00:01:00+00:00",
                         source="dmesg", kind="xid", payload={})
stringy = TelemetryEvent(node_id="node-00", gpu_index=2, timestamp="2026-10-01T00:02:00+00:00",
                         source="dmesg", kind="xid", payload={"xid": "not-a-number"})
none_xid = TelemetryEvent(node_id="node-00", gpu_index=3, timestamp="2026-10-01T00:03:00+00:00",
                          source="dmesg", kind="xid", payload={"xid": None})
R["E3_malformed"] = [
    try_run([good], "single good event"),
    try_run([good, missing, good], "good + missing-xid-key + good"),
    try_run([good, stringy], "good + xid='not-a-number'"),
    try_run([good, none_xid], "good + xid=None"),
]

# ---- E4: fake LLM provider -> output contract -----------------------------
class FakeLLM:
    """Returns exactly the JSON the system prompt asks for."""
    def __init__(self, reply): self.reply = reply; self.seen_evidence = None; self.seen_prompt_head = None
    def reason(self, system_prompt, evidence):
        self.seen_evidence = evidence; self.seen_prompt_head = system_prompt[:60]
        return self.reply

import os
os.chdir(REPO)  # prompt file is opened by relative path; see E5
fake = FakeLLM('{"xid": 79, "assessment": "GPU fell off the bus.", "action": "DRAIN_NODE", "confidence": 0.95, "next_steps": ["drain", "reset"]}')
v = TriageAgent(llm=fake).triage_event(good)
R["E4_llm_contract"] = {
    "fake_llm_returned_action": "DRAIN_NODE", "fake_llm_returned_confidence": 0.95,
    "verdict_action_after_llm": v.action,
    "verdict_confidence_after_llm": v.confidence,
    "rationale_tail": v.rationale[-120:],
    "evidence_string_passed_to_llm": fake.seen_evidence,
    "evidence_contains_notes_field": "notes" in (fake.seen_evidence or ""),
    "evidence_contains_category_field": "category" in (fake.seen_evidence or ""),
    "evidence_contains_thermal_or_ecc": any(k in (fake.seen_evidence or "") for k in ("temp", "ecc", "sbe", "dbe")),
}

class ExplodingLLM:
    def reason(self, system_prompt, evidence): raise RuntimeError("simulated provider outage")
try:
    TriageAgent(llm=ExplodingLLM()).triage_event(good)
    R["E4_llm_exception"] = {"outcome": "completed"}
except Exception as ex:
    R["E4_llm_exception"] = {"outcome": "raised", "exception": f"{type(ex).__name__}: {ex}"}

# ---- E5: cwd dependence of the prompt path --------------------------------
os.chdir("/tmp")
fake2 = FakeLLM("{}")
try:
    TriageAgent(llm=fake2).triage_event(good)
    R["E5_cwd"] = {"cwd": "/tmp", "outcome": "completed"}
except Exception as ex:
    R["E5_cwd"] = {"cwd": "/tmp", "outcome": "raised", "exception": f"{type(ex).__name__}: {ex}"}
os.chdir(REPO)

# LangChain provider itself
try:
    from agent.llm import LangChainChatProvider
    LangChainChatProvider()
    R["E5_langchain_provider"] = {"outcome": "constructed"}
except Exception as ex:
    R["E5_langchain_provider"] = {"outcome": "raised", "exception": f"{type(ex).__name__}: {ex}"}

# ---- E6: flapping / corroboration blindness --------------------------------
flap = [TelemetryEvent.xid("node-00", 5, 79, f"2026-10-01T0{h}:00:00+00:00") for h in (1, 2, 3)]
rep = TriageAgent().run(flap, node_count=1, simulated=True)
R["E6_flapping"] = {
    "same_gpu_xid79_count": 3,
    "verdicts": [{"action": v.action, "confidence": v.confidence} for v in rep.verdicts],
    "any_escalation": len({v.action for v in rep.verdicts}) > 1,
}
# XID 13 (app-level per prompt rule 2) accompanied by severe ECC/thermal context
mixed = [
    TelemetryEvent(node_id="node-00", gpu_index=0, timestamp="2026-10-01T00:00:00+00:00",
                   source="dcgm", kind="ecc", payload={"sbe": 0, "dbe": 17}),
    TelemetryEvent(node_id="node-00", gpu_index=0, timestamp="2026-10-01T00:00:30+00:00",
                   source="dcgm", kind="thermal", payload={"temp_c": 104.0}),
    TelemetryEvent.xid("node-00", 0, 13, "2026-10-01T00:01:00+00:00", source="dmesg"),
]
rep2 = TriageAgent().run(mixed, node_count=1, simulated=True)
R["E6_corroboration"] = {
    "events_in": len(mixed), "verdicts_out": len(rep2.verdicts),
    "verdict_actions": [v.action for v in rep2.verdicts],
    "note": "ecc(dbe=17) and thermal(104C) events on the same GPU produce no verdict and are not attached to the XID 13 verdict",
}

print(json.dumps(R, indent=2, ensure_ascii=False))
Path(__file__).with_name("2026-10-14-sentinel-bench.json").write_text(json.dumps(R, indent=2, ensure_ascii=False))
