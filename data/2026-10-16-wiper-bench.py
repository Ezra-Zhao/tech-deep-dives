"""Wiper-Service-Agent state-machine bench (2026-10-16).

Runs scripted conversations against the unmodified repo code (MockLLM,
simulated catalog/pricing) and records state traces, quote math, intent
collisions, persistence and isolation checks. No network, no WhatsApp.
Usage: python3 wiper_bench.py <repo_path> <out_json>
"""
import json, sys, os, copy
repo = sys.argv[1] if len(sys.argv) > 1 else "/tmp/wiper/repo"
outp = sys.argv[2] if len(sys.argv) > 2 else "bench.json"
sys.path.insert(0, repo)
os.chdir(repo)

from wiper_agent.agent import WiperServiceAgent
from wiper_agent.schemas import State
from wiper_agent.llm import MockLLM
from wiper_agent.store import FileConversationStore, MemoryConversationStore
from tools.wiper_db import SIMULATED_FITMENTS, lookup, known_models
from tools.pricing import build_quote, blade_price

R = {}

def trace(agent, phone, msgs):
    steps = []
    for m in msgs:
        r = agent.handle_message(phone, m)
        conv = agent._convs.get(phone)
        steps.append({
            "msg": m, "state_after": r.state.name,
            "reply": r.text,
            "quote_total": (conv.quote.total if conv and conv.quote else None),
            "haggled": (conv.haggled if conv else None),
            "result": (conv.result if conv else None),
            "language": (conv.language if conv else None),
            "order_intent": (r.order_intent.to_dict() if r.order_intent else None),
        })
    return steps

# A. pricing math for every fitment
pricing = []
for f in SIMULATED_FITMENTS:
    q = build_quote(f); qh = build_quote(f, haggled=True)
    sub = q.driver_price + q.passenger_price + q.rear_price
    pricing.append({
        "vehicle": f"{f.make} {f.model} {f.year_start}-{f.year_end}",
        "sizes": [f.driver_in, f.passenger_in, f.rear_in],
        "prices": [q.driver_price, q.passenger_price, q.rear_price],
        "subtotal": round(sub, 2), "discount": q.discount, "total": q.total,
        "expected_total": round(sub * 0.9, 2),
        "haggle_discount": qh.discount, "haggle_total": qh.total,
        "expected_haggle_total": round(sub * 0.85, 2),
        "math_ok": q.total == round(sub * 0.9, 2) and qh.total == round(sub * 0.85, 2),
    })
R["pricing_all_fitments"] = pricing
R["blade_price_tiers"] = {str(s): blade_price(s) for s in [12, 14, 20, 21, 24, 25, 28]}

# B. happy paths
a = WiperServiceAgent()
R["happy_split_zh"] = trace(a, "b1", ["你好", "Toyota Camry", "2018", "怎么安装", "好的，要了"])
a = WiperServiceAgent()
R["happy_oneshot"] = trace(a, "b2", ["Toyota Camry 2018", "要了"])
a = WiperServiceAgent()
R["happy_spanish"] = trace(a, "b3", ["Hola", "Toyota Corolla 2021", "¿Cuánto cuesta?", "¿Incluye instalación?", "Vale, sí"])

# C. lookup miss
a = WiperServiceAgent()
R["lookup_miss_unknown"] = trace(a, "c1", ["BMW X5 2020"])
a = WiperServiceAgent()
R["lookup_miss_year"] = trace(a, "c2", ["Toyota Camry 2005"])
a = WiperServiceAgent()
R["missing_year_then_complete"] = trace(a, "c3", ["Honda Civic", "2020"])

# D. haggle once / twice
a = WiperServiceAgent()
R["haggle_twice"] = trace(a, "d1", ["Nissan Altima 2019", "太贵了", "再便宜点", "还能便宜吗"])

# E. FAQ in QUOTE: all six topics
faq_msgs = {"install": "怎么安装", "warranty": "保修多久", "lifespan": "能用多久",
            "payment": "怎么付款", "pickup": "哪里自取", "shipping": "能邮寄吗"}
faq_res = {}
for topic, msg in faq_msgs.items():
    a = WiperServiceAgent()
    steps = trace(a, "e1", ["Toyota Camry 2018", msg])
    faq_res[topic] = {"msg": msg, "state_after": steps[-1]["state_after"],
                      "quote_total_after": steps[-1]["quote_total"], "reply": steps[-1]["reply"]}
R["faq_in_quote"] = faq_res

# F. FAQ / decline outside QUOTE
a = WiperServiceAgent()
R["faq_at_greeting"] = trace(a, "f1", ["怎么安装"])
a = WiperServiceAgent()
R["faq_at_collect"] = trace(a, "f2", ["Toyota Camry", "怎么安装", "2018"])
a = WiperServiceAgent()
R["decline_at_greeting"] = trace(a, "g1", ["不要了"])
a = WiperServiceAgent()
R["decline_at_collect"] = trace(a, "g2", ["Toyota Camry", "算了"])
a = WiperServiceAgent()
R["decline_at_quote"] = trace(a, "g3", ["Toyota Camry 2018", "算了"])

# G. vehicle change in QUOTE
a = WiperServiceAgent()
R["vehicle_change_valid"] = trace(a, "h1", ["Toyota Camry 2018", "Honda Civic 2020"])
a = WiperServiceAgent()
steps = trace(a, "h2", ["Toyota Camry 2018", "BMW X5 2020"])
conv = a._convs["h2"]
R["vehicle_change_invalid"] = {"steps": steps,
    "stale_quote_total_after_miss": conv.quote.total if conv.quote else None,
    "stale_fitment": (f"{conv.fitment.make} {conv.fitment.model}" if conv.fitment else None),
    "vehicle_now": conv.vehicle.to_dict(), "state": conv.state.name}
a = WiperServiceAgent()
R["vehicle_change_year_only"] = trace(a, "h3", ["Toyota Camry 2018", "2025"])

# H. intent collisions: direct MockLLM parse + agent effect where relevant
mock = MockLLM(); cat = known_models()
collisions = [
    "可以便宜点吗", "不要太贵了", "好的，多少钱", "我想买，先问问保修",
    "能便宜点吗", "I don't know", "another question", "yes but too expensive",
    "no, how much is it", "好的", "OK", "先看看保修再说", "不买了太贵",
]
col = []
for t in collisions:
    p = mock.parse(t, cat)
    col.append({"text": t, "intent": p.intent.name, "faq_topic": p.faq_topic,
                "make": p.make, "model": p.model, "year": p.year})
R["intent_collisions_parse"] = col
# agent-level: the dangerous one — haggle phrased with 可以 in QUOTE
a = WiperServiceAgent()
R["agent_collision_haggle_with_keyi"] = trace(a, "i1", ["Toyota Camry 2018", "可以便宜点吗"])
a = WiperServiceAgent()
R["agent_collision_buy_then_faq"] = trace(a, "i2", ["Toyota Camry 2018", "我想买，先问问保修"])
a = WiperServiceAgent()
R["agent_collision_dont_know_at_quote"] = trace(a, "i3", ["Toyota Camry 2018", "I don't know"])
a = WiperServiceAgent()
R["agent_collision_dont_know_at_collect"] = trace(a, "i4", ["Toyota Camry", "I don't know"])

# I. DONE restart
a = WiperServiceAgent()
steps = trace(a, "j1", ["Toyota Camry 2018", "要了", "你好"])
conv = a._convs["j1"]
R["done_restart"] = {"steps": steps, "vehicle_after_restart": conv.vehicle.to_dict(),
                     "quote_after_restart": conv.quote, "haggled_after_restart": conv.haggled,
                     "history_len_after_restart": len(conv.history)}

# J. persistence roundtrip mid-quote (file store, fresh agent instance)
import tempfile
tmpd = tempfile.mkdtemp()
path = os.path.join(tmpd, "convs.json")
a1 = WiperServiceAgent(store=FileConversationStore(path))
trace(a1, "k1", ["Toyota Camry 2018", "太贵了"])
a2 = WiperServiceAgent(store=FileConversationStore(path))
conv2 = a2._get_conv("k1")
R["persistence_roundtrip"] = {
    "state": conv2.state.name, "vehicle": conv2.vehicle.to_dict(),
    "quote_total": conv2.quote.total if conv2.quote else None,
    "haggled": conv2.haggled, "language": conv2.language,
    "history_len": len(conv2.history),
    "continue_reply_state": a2.handle_message("k1", "保修多久").state.name}

# K. multi-customer isolation
a = WiperServiceAgent()
trace(a, "iso-a", ["Toyota Camry 2018"])
trace(a, "iso-b", ["Honda Civic"])
steps_a = trace(a, "iso-a", ["太贵了"])
steps_b = trace(a, "iso-b", ["2020"])
R["isolation"] = {"a_quote_after_haggle": steps_a[-1]["quote_total"],
                  "b_state": steps_b[-1]["state_after"], "b_quote": steps_b[-1]["quote_total"],
                  "a_vehicle": a._convs["iso-a"].vehicle.to_dict(),
                  "b_vehicle": a._convs["iso-b"].vehicle.to_dict()}

# L. unknown / gibberish in QUOTE and GREETING
a = WiperServiceAgent()
R["gibberish_at_quote"] = trace(a, "l1", ["Toyota Camry 2018", "asdf qwer"])
a = WiperServiceAgent()
R["gibberish_at_greeting"] = trace(a, "l2", ["asdf qwer", "Toyota Camry 2018"])


# N. second-round edge cases
a = WiperServiceAgent()
R["haggle_then_change_then_haggle"] = trace(a, "x1", ["Nissan Altima 2019", "太贵了", "Honda Civic 2020", "太贵了"])
a = WiperServiceAgent()
R["miss_then_decline_stale_quote"] = trace(a, "x2", ["Toyota Camry 2018", "2025", "算了"])
a = WiperServiceAgent()
R["confirm_at_collect"] = trace(a, "x3", ["Toyota Camry", "好的"])
a = WiperServiceAgent()
R["askprice_at_greeting"] = trace(a, "x4", ["多少钱"])
a = WiperServiceAgent()
R["haggle_at_collect"] = trace(a, "x6", ["Toyota Camry", "太贵了"])

# M. counts
R["meta"] = {"catalog_size": len(SIMULATED_FITMENTS), "known_models": cat,
             "repo_commit": os.popen("git rev-parse HEAD").read().strip()}

with open(outp, "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1)
print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in R.items()}, ensure_ascii=False))
print("pricing math_ok all:", all(p["math_ok"] for p in pricing))

# ---- second round (appended before write in archived version: merged) ----
