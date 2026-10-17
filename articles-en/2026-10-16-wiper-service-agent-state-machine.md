# "Can You Make It Cheaper?" — and the Agent Booked the Order: A State-Machine Field Test of Wiper-Service-Agent

Author: Guangyi Zhao
Date: 2026-10-16
Subject: Wiper-Service-Agent (my own open-source project, github.com/Ezra-Zhao/Wiper-Service-Agent), scaffold v0.2, commit 9675291, Python 3.12.3
Environment: Linux x86_64 VM, agent exercised in-process. No WhatsApp connection, no real messages sent, no real customer data. The fitment catalog, price table, and NLU are the repository's own simulated implementations, and the article says so wherever it matters.

## 1. Problem and background

The hard part of a WhatsApp service agent for a small shop is not wiring up a model. It is walking one conversation down a path where money changes hands: ask for the vehicle, look up the size, quote a price, answer questions, record an order intent. Misread the customer once and the cost is real — hear a haggle as an order and the shop holds an order nobody placed; hear a hesitant "I don't know" as a rejection and a nearly closed sale is shut down on the spot.

Wiper-Service-Agent is the agent I built for a wiper-blade shop. The conversation is not left to a language model. An explicit state machine runs it — GREETING → COLLECT_VEHICLE → QUOTE → DONE, four states — and the understanding layer defaults to a deterministic rule-based parser (MockLLM, marked SIMULATED in the repo). The real LLM parser (RealLLMProvider) is only ever asked to parse a message into an intent and vehicle slots; it never decides prices, sizes, or whether a deal closed. That division of labor is written into the README. Status, honestly: scaffold v0.2, a simulated catalog of 8 fitment records across 5 makes, a demo price table. This is not ready to take real orders.

So this article does not measure whether the demo runs — the bundled demo and all 56 tests pass (I re-ran them: 56 passed; the README still says 44, which is stale). It measures how the machine behaves off the demo path: 27 scripted conversations, 62 messages, 13 intent-collision probes, a full recomputation of quotes for all 8 catalog records, one persistence round-trip, and one two-customer isolation check. The headline first: the main flow is steadier than I expected, the quote math is exact to the cent, and all six FAQ topics stay inside the quoting state. But the intent layer's substring matching produces three misreadings that would cost a real shop money — the worst being the title of this article. Under the default rule-based parser (MockLLM), a customer in the QUOTE state who asks "可以便宜点吗" ("can you make it cheaper?") is taken straight to DONE with a confirmed order intent, at the full, undiscounted price. Scope, stated once and binding for the whole article: every intent-layer finding here is about that default parser; behavior under the real LLM parser is a separate question, revisited in §5.

## 2. Method and architecture

The core package, tools, and WhatsApp boundary total 1,659 lines, including a 258-line webhook server. Conversation state lives in a Conversation object: current state, three vehicle slots (make / model / year), the fitment result, the quote, a boolean haggled flag (has the one-time haggle discount been used), the outcome (confirmed / declined), detected language and confidence, and full history.

The transition rules, state by state — everything later follows from these:

GREETING: a message carrying all three vehicle slots goes straight to a fitment lookup — found means QUOTE; a miss (a year outside the catalog range, say) falls back to COLLECT_VEHICLE with a "not found" reply. A partial vehicle moves to COLLECT_VEHICLE and asks for what is missing. Anything else gets the greeting text and the state stays GREETING. This state has no branch for decline, FAQ, or price questions. None.

COLLECT_VEHICLE: only two things are handled — a decline (DONE, marked declined) and completing the slots (lookup). Confirm, price, haggle, and FAQ intents are all unhandled here and get the same "what's still missing" reply.

QUOTE: the fullest state. Haggle (once only, an extra 5%), FAQ (answered without leaving QUOTE), price question (re-present the quote), confirm (DONE / confirmed), decline (DONE / declined), a message carrying vehicle info (re-run the lookup — treated as a vehicle change), and anything else re-presents the quote with a nudge.

DONE: intercepted in handle_message. Any new message after DONE discards the conversation and starts a fresh one — vehicle, quote, and haggle flag all reset. I verified the reset by round-trip.

Intent parsing (MockLLM.parse) is where this article lives. The precedence order in code is: decline > confirm > haggle > FAQ > price > greeting > provide-vehicle > unknown. Keywords match by substring (`w in low`); only three short tokens — sí, да, نه — get word-boundary matching. The confirm list contains everyday words: "买" (buy), "好的" (okay), "可以" (can/sure), "ok", "yes". The decline list contains a bare "no". Vehicle extraction only recognizes catalog vehicles: a (make, model) pair from the simulated catalog must both appear as substrings; the year is the first 4-digit number matching (19|20)\d\d.

The two tools: wiper_db.lookup searches the 8 simulated fitments by make, model, and year range. pricing.build_quote prices blades in three length tiers (up to 20" $12.99, 21–24" $14.99, 25"+ $16.99), takes 10% off the subtotal (the code comment calls it a bundle discount), and a further 5% after a successful haggle.

Method: repository code unmodified, conversations driven in-process under different "phone numbers" (arbitrary string IDs), logging every message, resulting state, quote total, haggle flag, and full order intent. Quotes for all 8 fitments were recomputed independently and compared. Collisions were first classified by calling parse directly, then the three worst were replayed inside real conversations to observe the consequences. The bench script and raw JSON are archived with this article and can be re-run.

## 3. Measurements

### 3.1 The main flow: split vehicle entry, a full Spanish run, exact quote math

The standard path (hello → Toyota Camry → 2018 → how do I install it → okay, I'll take it) walks GREETING → COLLECT_VEHICLE → QUOTE → QUOTE → DONE and produces a confirmed intent with vehicle, sizes (26/20"), and a $26.98 total. All three slots in one message jump straight to QUOTE. A full Spanish run (Hola → Corolla 2021 → ¿Cuánto cuesta? → ¿Incluye instalación? → Vale, sí) answers in Spanish at every step, locks the language to es on the first message, and records detected_language: es on the final intent.

All 8 quote recomputations matched. Camry, worked in full: $16.99 + $12.99 = $29.98 subtotal, $26.98 after 10% off, $25.48 after the haggle (85% of subtotal). The RAV4, the only record with a rear blade: $42.97 subtotal, $38.67 quoted, $36.52 haggled. One bookkeeping discrepancy worth recording: the comment describes the 10% as a driver+passenger bundle discount, but the discount base is the whole subtotal including the rear blade — the RAV4's $4.30 discount is computed on all three blades. The error favors the customer; the books should still say what the code does. A rounding note, so nobody's calculator disagrees: the Quote's discount field is rounded to cents on its own (the Camry's exact 10% is 2.998, stored as 3.0), while the total is computed from the unrounded discount and then rounded. I reconciled all 16 combinations (8 records, with and without haggle): discount plus total reproduces the subtotal exactly in every case.

### 3.2 Haggle once, and only once — until the vehicle changes

Altima 2019 quotes at $26.98. "太贵了" (too expensive) drops it to $25.48 and sets the flag. "再便宜点" and "还能便宜吗" both get "that's already my lowest," and the total does not move. As a one-shot allowance enforced by a boolean and a recomputation, there is no path around it. That part holds.

What the tests never covered is haggling across a vehicle change. Haggle the Altima down to $25.48, then name a Civic 2020: the lookup rebuilds the quote without the haggle, the new total is back to $26.98 — and the haggled flag stays set. Haggle again and the agent replies "this is already the lowest price" about a price that was never discounted. The customer is told something factually false. The cause is granularity: the flag lives on the conversation, not on the quote. A vehicle change neither carries the discount over nor clears the flag; of the two coherent choices, the code makes neither.

### 3.3 FAQ only lives inside QUOTE

In QUOTE, all six FAQ topics (install, warranty, lifespan, payment, pickup, shipping) answer correctly, stay in QUOTE, leave the quote untouched, and close with an ordering prompt. That matches the documented design — FAQ must not break the sales flow — and it held in every probe.

Ask before the quote and the question disappears. At GREETING, "怎么安装" (how do I install it?) gets only the greeting; the question is neither answered nor logged (no FAQ note is recorded). At COLLECT, the same question gets a repeat of "which year is it?", the question vanishes, and after completing the vehicle the customer has to ask again. Price and haggle attempts at COLLECT meet the same fate. There is no holding area in this machine for "remember this, answer it when we get there." Out-of-flow input is not refused; it is silently dropped, and the reply gives the customer no sign their question was never heard — it just reads as a non sequitur.

Declines are state-dependent too. "算了" (forget it) at COLLECT and at QUOTE correctly ends as declined. "不要了" (I don't want it) as the very first message is not handled at all — GREETING has no decline branch — and earns a cheerful greeting. Minor on its own; included because it shows GREETING's intent coverage is not partial, it is zero.

### 3.4 Intent collisions: 13 probes, three failure families

Feeding everyday phrasings to parse, 7 of 13 came back with a classification visibly at odds with what the speaker meant, in three families:

Confirm words are too broad and outrank everything else they co-occur with. "可以便宜点吗" (can you make it cheaper?) classifies as CONFIRM — "可以" is in the confirm list and confirm is checked before haggle. "好的，多少钱" (okay, how much?) is CONFIRM, not a price question. "我想买，先问问保修" (I do want to buy, but first let me ask about the warranty) is CONFIRM — "买" fires confirm even though the FAQ topic was correctly detected as warranty and never gets used. "yes but too expensive" is CONFIRM for the same structural reason.

The decline list contains a bare substring. "no" is matched as a substring, so "I don't know" and "another question" both classify as DECLINE — both contain "no". The codebase already has a word-boundary mechanism for short tokens (CONFIRM_TOKENS / DECLINE_TOKENS); "no" simply was not put in it.

Decline outranks haggle. "不要太贵了" (don't make it too expensive) and "不买了太贵" classify as DECLINE. Whether the first of those is really a refusal is debatable — it reads more like a haggle opening — but the machine offers no clarifying move. Between "kill the conversation" and "treat as haggle," it picks kill.

The three worst, replayed inside real conversations:

- In QUOTE, "可以便宜点吗" → straight to DONE, a confirmed order intent at the full $26.98. The customer asked for a discount; the system recorded a sale.
- In QUOTE, "我想买，先问问保修" → straight to DONE, confirmed, warranty question never answered. The buying intent was genuine, but the flow closed before the customer's actual question, leaving the human follow-up holding a "confirmed" record and an unanswered conversation.
- In QUOTE, "I don't know" → straight to DONE, declined, logged as "declined at quote." The customer was undecided; the system recorded a rejection. The same sentence at COLLECT ends the same way.

Controls, so the word lists are not condemned wholesale: "能便宜点吗" (the same haggle without "可以") classifies correctly as HAGGLE; "先看看保修再说" goes to FAQ; "好的" and "OK" in QUOTE are legitimately CONFIRM. What breaks is the compound sentence — and real customers rarely speak in single keywords.

### 3.5 Changing vehicles: an off-catalog car is quietly merged into the old one

In QUOTE, "Honda Civic 2020" correctly re-quotes a new vehicle (same $26.98 total, but sizes change from 26/20 to 26/18, so the change is visible). "BMW X5 2020" produces the reply "Found it! Toyota Camry 2020." BMW and X5 are not in the simulated catalog, so vehicle extraction fails entirely and only the year, 2020, is captured; slot merging folds that year into the old vehicle, the lookup succeeds for a Camry 2020, and a fresh Camry quote is presented with total confidence. The customer thinks they asked about a BMW. The agent quoted them a Camry. At no point does anything say "I can't find that car."

The same off-catalog car at the start of a conversation behaves almost honestly: extraction fails and the agent asks which vehicle — phrased as "still missing the vehicle," which will confuse a customer who just named one, but at least nothing is fabricated. Two different failures should not be conflated here: that was an extraction failure (make and model never parsed, slots incomplete, so all it can do is ask). A lookup failure is different — "Toyota Camry 2005" as a first message parses completely, misses the catalog, and gets an explicit "not found" with a fallback to COLLECT, which I also tested. In QUOTE, the pre-existing slots mask the failure and turn it into a silent substitution. The only difference is whether old slot values exist to paper over the gap.

A year-only change has the mirror-image problem. "2025" merges into Camry, falls outside the catalog range (2018–2024), and this time the lookup properly misses: the state falls back to COLLECT and asks the customer to double-check. The handling is right; the cleanup is not — the old $26.98 quote stays attached to the conversation. When the customer then gives up ("算了"), the declined order intent carries that stale quote, with the vehicle field reading Camry 2025: a car with no fitment, wearing a 2018 quote, filed as if the customer had rejected a real offer.

### 3.6 Persistence and isolation: two passing grades

Mid-conversation — quoted and haggled — I restored the conversation into a brand-new agent instance from the same JSON file store. State QUOTE, vehicle, haggled total $25.48, the flag, and all 4 history entries came back exact, and the restored conversation answered a warranty question while staying in QUOTE. The to_dict / from_dict round-trip is lossless. Two interleaved customers (one haggling, one completing a vehicle) never leaked slots, quotes, or flags into each other; keying by phone number holds.

Gibberish in QUOTE ("asdf qwer") re-presents the quote with a nudge and changes nothing. Not smart, but it neither crashes nor closes anything — and in context it is the intent layer's most trustworthy behavior. Only UNKNOWN gets this treatment. Every failure above came from a match that was almost right.

## 4. Analysis and trade-offs

### 4.1 What the architecture genuinely gets right: the parser never holds the pen on a deal

Read against the design, the result worth keeping is the division of authority. The state machine owns the flow, the tools own the numbers, and the parsing layer — rules today, an LLM tomorrow — only emits intents and slots. Exact quote math, a hard one-time haggle cap, FAQ containment, and lossless persistence all follow from decisions being kept in deterministic code. Swapping in RealLLMProvider will improve parsing, but its intents still pass through the same transition table, and it still cannot mint a price or close a deal. For a small-shop agent that is the right border: language may be probabilistic; the ledger may not.

### 4.2 The defects are not in the machine; they are in its entry contract

None of the three measured problem families is a wrongly drawn transition. The table's flaw is that it trusts whatever the entrance hands it: whatever intent parse returns gets executed, whatever the slot merger produces gets looked up. Every business-harming action in the tests — the wrongly closed order, the wrongly quoted car, the fabricated intent record — happened at a point where input was over-trusted:

- CONFIRM and DECLINE are irreversible (DONE, plus a recorded intent), yet they are triggered by the weakest evidence in the system: a single substring. Irreversible actions should demand stronger evidence than reversible ones (re-presenting a quote, answering an FAQ). The current precedence inverts that — the irreversible intents are checked first.
- Slot merging overwrites field by field and cannot distinguish "the customer added the year" from "the customer changed cars and the new car failed extraction." The second case should route to clarification, not be healed with stale values.
- haggled and quote have mismatched lifetimes. A quote can be replaced while its flag persists; a failed lookup retreats while its quote persists. Derived state has no rule that says "a new quote invalidates everything derived from the old one."

### 4.3 Fix order: gate the irreversible actions first, upgrade the NLU later

In cost-benefit order. First, move short words like "no" out of the substring lists into the existing word-boundary sets, and tighten confirm words like "可以" and "买" with co-occurrence conditions (confirm only when no haggle or price wording is present). That is an afternoon of word-list and ordering work and it dismantles most of §3.4. Second, reorder precedence so reversible intents win: FAQ, price, and haggle are evaluated before confirm and decline, and confirm only stands when the sentence carries no other request. "Wants to buy, but first the warranty" then gets its answer and stays in QUOTE instead of being closed early. Third, give CONFIRM a read-back step: before DONE, echo vehicle and total — "shall I book this?" — and record the intent only on an explicit yes. One extra CONFIRMING state holds it, and it mirrors what a human clerk does anyway. Fourth, add a merge rule: when a message carries a year or vehicle-like text but extraction comes back empty and inconsistent with the current vehicle, do not merge — clarify; and when a lookup miss retreats to COLLECT, clear the quote and the haggle flag with it. Fifth, and only then, swap MockLLM for RealLLMProvider, with this article's 13 probes plus real conversation logs as the regression set. A better brain fixes part of the compound-sentence problem; it fixes none of the merging or lifecycle problems, because those belong to the machine itself.

The judgment underneath the ordering: in a demo, the thing most easily overlooked is not answer quality but closing correctness. A wrong FAQ answer gets asked again. A wrongly recorded confirmed intent gets acted on — the owner preps stock, reaches out, and finds nobody there.

## 5. Limitations and open questions

Stated plainly. First, everything ran on MockLLM; the collision patterns are specific to a rule-based parser. A real LLM endpoint would very likely handle the compound sentences better, but I did not re-run the 13 probes against RealLLMProvider, so the post-swap error rate is unmeasured. Second, the catalog has 8 simulated records at demo prices. In a real catalog of hundreds of records, extraction failures get rarer but not harmless — the silent-merge mechanism is size-independent, and the claim here is about the mechanism. Third, the scripts were written backwards from the transition table, so they cover the paths I could think of; real customers' speech-to-text errors, code-switching, and two cars in one sentence were only spot-checked, not systematically tested. Fourth, the WhatsApp boundary layer (webhook signature verification, Cloud API delivery, usage counters) is out of scope — this round exercised the in-process agent API only; the repo's own tests, all 56 passing, cover parts of that layer, but no end-to-end message test was run. Fifth, beyond Spanish, the Russian and Persian flows were verified only at greeting and language-detection level, following the repo's own test coverage; the templates have not had native-speaker review, which the README also states.

Three open questions. Adding a CONFIRMING read-back state will cost some completion rate — how much is only knowable with real traffic. How fine-grained the merge-clarification rule should be (year conflicts only, or any "vehicle-like text, empty extraction") needs real conversation logs to calibrate. And two cars in one order — a customer buying for themselves and a family member — does not fit the one-conversation-one-vehicle data model at all; whether that is a notes-field workaround or a multi-intent model change is undecided.

## 6. References

1. Wiper-Service-Agent source (version tested, commit 9675291): github.com/Ezra-Zhao/Wiper-Service-Agent. Key files: wiper_agent/agent.py (state machine, slot merging, language upgrade), wiper_agent/llm.py (MockLLM precedence and word lists, the RealLLMProvider parsing contract), wiper_agent/conversation.py and store.py (state and persistence), wiper_agent/schemas.py (the four states and data models), tools/wiper_db.py (8 simulated fitments, marked SIMULATED in the file header), tools/pricing.py (three price tiers and discounts), tools/faq.py (six FAQ topics, five-language templates).
2. Bench script and raw data for this article: data/2026-10-16-wiper-bench.py and data/2026-10-16-wiper-bench.json (27 conversation traces, 13 intent-collision probes, 8 quote recomputations, persistence round-trip, two-customer isolation), archived with the article; the numbers can be reproduced by running the script against a clone of the repository.
3. Repository test suite: tests/run_tests.py — 56 passed, 0 failed in this run (the README Quickstart says 44, which is out of date).

---

Author: Guangyi Zhao. The code, experiments, and text in this article are clean-room work of my own: the subject is an open-source scaffold I maintain, every conversation was script-generated, no WhatsApp account was connected, and no real customer's chats, phone numbers, or orders were used. No client information, client systems, or third-party non-public data are involved. All vehicles, prices, and language templates are the repository's simulated data and are not presented as real product information; the scaffold is not presented as a production system in service.
