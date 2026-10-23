# Give the Self-Check a Script — Do You Still Need a Second Model? A 24-Defect Controlled Comparison

Author: Guangyi Zhao

## 1. Problem and background

My previous cross-model review audit (2026-10-19) left one question untested. Its conclusion was that, for a solo author proofreading by eye alone, author self-checks and a second model's review catch different species of error, and neither replaces the other. But the conclusion had a loophole: what if the self-check is armed with a number-extraction script and a checklist? Would the division of labor survive? Three days later, here is the test.

The design is a paired probe comparison. I wrote three new short excerpts, planting 8 defects in each — 24 in total — modeled on defect shapes that actually occurred in this series' earlier review history: arithmetic and formula errors (sums, percentages, F1, means, weighted means) ×8, the same metric stated with two different values ×3, absolute wording ×3, single-cause attribution ×3, citations that do not support the claim ×3, internal contradictions ×3, and a conclusion that outruns its evidence ×1. Two checkers then audited the same texts independently, neither seeing the other's output:

- The script arm: a deterministic checker I wrote for self-review, eight rules frozen before any review call — sum recomputation, percentage recomputation, formula recomputation, mean recomputation, same-metric multi-value reconciliation, an absolute-word list, causal-sentence flagging, and citation-sentence flagging. The first five return a verdict; the sixth can only surface the wording itself; the last two can only point, never judge.
- The review arm: a second model (Gemini), with the same prompt this series has always used ("independent review; hunt factual errors, logical leaps, and overclaims"), one call per probe.

The headline result: the review arm scored 23 hits, 1 partial, 0 misses, 0 false alarms, plus 2 unplanted true findings. The script arm scored 14 hits, 7 pointers, 3 misses, 0 false alarms. Their union covers all 24 defects, but their intersection is only 13: the script uniquely caught 1, the reviewer uniquely caught 10. So the answer is neither "the script is enough" nor "the script is useless" — it is a question of order. Script first, model second; the two still catch different things, but the script drives the cost of one whole class to nearly zero.

## 2. Method

Three probes, deliberately different domains: database connection-pool tuning (backend), a customer-service text classifier evaluation (ML), and front-end bundle optimization (web performance), each about 400 Chinese characters. Every defect is registered in an answer key that was never sent with the texts. One discipline governed the planting: numeric defects were written in the natural shapes manuscripts actually use — "items … totaling N", "Y out of X (P%)", precision/recall/F1 stated side by side — with no special markers left for the script's regexes. The script's templates, in turn, came from the numeric phrasings in this series' first seven real manuscripts.

The script's eight rules sit in three tiers, and the results are unreadable without them:

- Verdict tier (R1–R5): sums, percentages, the F1 formula, arithmetic and weighted means, same-metric reconciliation. A hit comes with a computed verdict, e.g. "items sum to 34; the text states 31."
- Lexical tier (R6): an absolute-word list, flagged sentence by sentence. For absolute-wording defects, the defect lives on the surface of the wording, so surfacing the words counts as a hit; but the script surfaces words, it cannot judge whether evidence backs them — if a manuscript's absolute wording were truly backed by exhaustive evidence, R6 flags would be false alarms. In these probes, none of the three absolute claims had any such backing in the text (sensitivity of this convention is disclosed in Section 5).
- Pointer tier (R7–R8): causal phrasing ("entirely due to X" plus "Y contributed nothing") and citation phrasing (a citation in the same sentence as "therefore / guarantees / necessarily") get flagged for the author to adjudicate. The script declares upfront that it cannot judge these, so scoring records them as FLAG (located), never HIT.

The review arm ran one call per probe, with the current date injected into the prompt (a lesson from the 2026-10-19 date false alarm). Scoring uses exactly the 2026-10-19 rubric: HIT = the core contradiction is explicitly identified; FLAG = the relevant passage is mentioned but the core contradiction is not pinned; MISS = not mentioned. I did the coding myself, with per-defect justifications in the bench script; borderline calls are disclosed in Section 5. The script's rules were frozen before the review calls, the two arms never saw each other, and coding happened only after both arms' raw outputs were on disk.

## 3. Results

### 3.1 The ledger

| | HIT | FLAG | MISS | Extra true findings | False alarms |
|---|---|---|---|---|---|
| Script arm | 14 | 7 | 3 | 0 | 0 |
| Review arm (Gemini) | 23 | 1 | 0 | 2 | 0 |

The script emitted 21 flags, every one landing on a sentence containing a planted defect. The review arm used 1,005 prompt tokens and returned 3,241 tokens across three calls, about a minute of wall time. The script runs locally in the hundreds-of-milliseconds range, is free to re-run, and is deterministic.

### 3.2 By defect class

| Class | n | Script | Review |
|---|---|---|---|
| Numeric recomputation (sums / % / formulas / means) | 8 | 8 HIT | 7 HIT + 1 FLAG |
| Same metric, two values | 3 | 2 HIT + 1 FLAG | 3 HIT |
| Absolute wording | 3 | 3 HIT (lexical) | 3 HIT |
| Single-cause attribution | 3 | 3 FLAG | 3 HIT |
| Unsupported citation | 3 | 3 FLAG | 3 HIT |
| Internal contradiction | 3 | 1 HIT + 2 MISS | 3 HIT |
| Conclusion outruns evidence | 1 | 1 MISS | 1 HIT |

The script's strength boundary is suspiciously clean: whenever a defect reduces to a checkable relation (addition, percentage, formula, two values of one named metric), its 12 verdict-tier flags produced 11 hits and 1 pointer — all 8 numeric defects hit, 2 of 3 metric conflicts hit and 1 located, plus 1 hit that lands in the contradiction class (below). Whenever the contradiction lives in meaning, it cannot judge a single one. Of the 3 internal contradictions it caught only 1 — the one that happened to be numeric in shape ("zero retries" versus "17 retries", caught by multi-value reconciliation as if it were a metric conflict). The other two — "test set has zero overlap with training data" versus "300 training samples were augmented into the test set", and "no new dependency was introduced" versus "we introduced a new build plugin" — have no numbers and no list words; the script stayed silent. The scope defect (an offline-only evaluation declaring production readiness) likewise has no rule to hang on and was missed outright.

All 6 attribution and citation defects were located by the pointer tier and judged by none. What those 6 flags actually do is shrink the author's reading list from "re-read everything and hunt" to "return to these 6 sentences and ask whether the evidence is enough". Locating has value — but it converts the check into a judgment call by the author, who is precisely the person who wrote those sentences.

### 3.3 The reviewer's one partial is exactly the script's home turf

The review arm's only non-hit was the confusion-matrix sum in probe B: TP 820 + FP 70 + FN 110 + TN 900 = 1,900, while the text states a total of 1,850. The reviewer did pull the number cluster out — but what it did was compare the three totals already printed in the text (5,000, 1,850, 4,200) against each other and declare inconsistency. It never recomputed the four cells, and it even quoted 1,850 once as if it were the matrix sum. Its diagnosis stops at "the numbers disagree"; it never lands on which side is wrong, or by how much.

That failure mode is worth recording: an LLM's arithmetic is opportunistic. In this same run it recomputed 7 other numeric defects, including two-step ones (a weighted mean, an F1) — yet here it chose comparing printed totals over recomputing the parts. Also worth recording are its two extra findings, neither planted: it derived recall from the matrix (820/930 = 0.882) and flagged the mismatch with the stated 0.80 (verified — when planting the F1 error I had watched only the P/R/F1 triangle and missed that the matrix implied a different recall); and it noticed that probe C states the post-split bundle size as both 450 and 410 in different sentences (a second-order consequence of two planted numeric defects; verified). The script had no extra findings — it has no eyes outside its rules, which is both its limitation and the reason for its zero false alarms.

### 3.4 Relationship: intersection 13, union 24

Of 24 defects, both arms hit 13. The script's unique hit is 1 (the four-cell sum above). The reviewer's unique hits are 10 (attribution ×3, citations ×3, semantic contradictions ×2, scope ×1, metric conflict ×1). The earlier "neither can replace the other" needs revising into an asymmetric version: the reviewer independently covers most of the script's hits (13/14), while the script's unique contribution is a single defect — but that defect sits exactly on the reviewer's least reliable action, exhaustive recomputation. In the other direction, if the author diligently adjudicated every pointer flag, some of the 6 attribution/citation defects might be recovered by self-check alone; this run did not test author adjudication, so those FLAGs must not be read as hits.

## 4. Analysis and trade-offs

First, the workflow order should flip: script first. Not because it is stronger, but because it is cheap and deterministic — hundreds of milliseconds, zero marginal cost, runnable on every save — so manuscripts should stop carrying hundred-millisecond-detectable errors into a paid review. This series previously sent drafts straight to review, and review comments regularly included two or three pure-arithmetic items: review money spent on a calculator's job. Note this is a claim about cost and ordering only: whether clearing arithmetic first raises the reviewer's semantic recall was not tested here, and I do not claim it.

Second, the script's value is exhaustiveness, not its hit count. The reviewer's 7/8 on numeric defects looks only one short of the script's 8/8, but which one it drops can rotate every run — its recomputation is spot-checking, drawn to whatever looks salient. The script checks every relation its templates can extract, and ten runs give the same result. Keep the two apart: the reviewer's numeric hits are expected-value hits; the script's are deterministic given correct extraction — and extraction itself errs, as probe C showed when the reconciliation value-set absorbed one legitimate measurement from a retest series. That extraction layer is the script's own failure surface.

Third, pointer-tier rules should be used to generate the author's adjudication list, not to inflate automation stats. Counting the 7 FLAGs as "covered by self-check" would inflate self-check coverage from 14/24 to 21/24 while the 6 attribution and citation judgments still never happened. A checklist's job is to queue semantic judgments, not to make them — if the author makes them, they carry the author's blind spots; if a second model makes them, that is the outside-the-frame eye the earlier paper described. This is also why the two arms' scores must not be merged.

Fourth, a concrete change to this series' pipeline, effective immediately: the finalization flow becomes "script self-check clean (zero verdict-tier flags) → author adjudicates the pointer list, on record → cross-model review → process every comment". Script rules may grow, but only from defect shapes that have actually occurred — the weighted-mean template in this run, for instance, descends from the unplanted true finding in the 2026-10-19 probe.

Two trade-off disclosures. First, probe phrasing may lean toward the script's templates: templates and probes share an author, and although the rule was "no markers left in the probes", the author subconsciously knows which shapes are checkable — so the script's 8/8 on numeric defects should be read as a home-field score. The review arm had no such home field. Second, I did not test the full self-check form (author + script pointers + serious adjudication), nor longer real manuscripts — in long texts, resolving what a metric value refers to gets much harder, and R5 would likely degrade into a FLAG factory. Both are left as open problems.

## 5. Limitations and open problems

- Small sample: 3 short texts, 24 defects, one review model, one run. Under its temperature setting the review arm's results can drift between runs; 23/24 is not a stable constant.
- Coding was done by the author alone, with no second coder. Three borderline calls, disclosed: probe B's sum was scored FLAG for the review arm (strict — it flagged the cluster but never recomputed the parts); probe C's LCP conflict was scored FLAG for the script (strict — its value-set mixed in a legitimate measurement and never isolated the conflicting pair). The third is the lexical-tier convention: absolute wording is defined in this experiment as a wording defect, so surfacing the words counts as a hit; under the pointer tier's stricter convention the script falls to 11 hits and the intersection to 10 — but the union stays 24, so the main conclusion does not rest on this convention.
- The shared-author home-field problem (Section 4): numeric 8/8 is a within-template ceiling, not an estimate of recall on real manuscripts.
- Defect density is far above real manuscripts, and every defect is a textbook shape. Real attribution leaps rarely announce themselves with "entirely due to"; R7's locating recall on real drafts will be well below this run's 3/3.
- Not tested: the author's actual recovery rate when adjudicating the pointer list; script precision and false-alarm rate on long texts (5,000+ words); whether the reviewer's numeric spot-check rate decays with manuscript length.

## 6. References

- Previous in this series: 2026-10-19, "What a Second Model Actually Catches: A Cross-Model Review Audit" (this experiment answers its Section 5 open problem).
- Probe texts and answer key: data/2026-10-22-probes.txt. Checker: data/2026-10-22-selfcheck.py; raw output data/2026-10-22-selfcheck-result.json.
- Review-arm raw responses: review/2026-10-22-probeA-gemini-raw.json, probeB, probeC (model gemini-flash-latest, paid standard tier; combined usage prompt 1,005 / candidates 3,241).
- Scoring code and results: data/2026-10-22-selfcheck-vs-review-bench.py and its JSON output, with per-defect coding justifications.

---

Author: Guangyi Zhao. The probe texts, checker script, and experiments described here are the author's own clean-room work: defects were planted by hand, both checks ran locally and through the author's own API channel, and no client information is involved.
