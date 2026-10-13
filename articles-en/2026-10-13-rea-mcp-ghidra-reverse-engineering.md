# Letting an AI Agent Drive Ghidra: A Hands-On Test of REA's 170 MCP Tools, One Recovered Password, and the Limits

Author: Guangyi Zhao
Date: 2026-10-13
Subject: morluto/rea (REA: Reverse Engineer Anything), npm package rea-agents 6.4.0, MIT license
Environment: Ubuntu 24.04 (Linux x64), Node 24.20; target is an ELF built from my own C source

## 1. Problem and background

Reverse-engineering an unfamiliar binary the traditional way means sitting in front of Ghidra, paging through assembly, following cross-references, guessing what each function does, and writing the conclusions down by hand. The slowness is not even the worst part. The worst part is how easily conclusions drift away from evidence: three days later I reread my own notes and cannot reconstruct what I actually saw when I wrote a given claim.

REA proposes a different division of labor. It does not implement decompilation itself. Instead, it standardizes the operating surface of reverse-engineering tools as MCP tools, so agents such as Claude Code, Codex, Cursor, or Gemini CLI can drive them directly: the agent asks the question, opens the binary, lists functions, pulls pseudocode, checks references, runs the target and diffs its behavior, then comes back with evidence attached. The human's job shifts from paging through assembly to asking the right questions and auditing the evidence chain.

Is that division real, or does it only demo well? I spent a day running it end to end, from install to password recovery, and I did not dodge the failures. Every number below comes from that day's logs and Evidence JSON files, and I re-checked each one against the raw files before finalizing this article. Anything I could not verify is either deleted or explicitly labeled as inference.

One ground rule up front: the only program analyzed here is one I wrote myself. The legal boundary is covered in Section 5, and it is not filler.

## 2. Method and architecture

REA is easiest to understand in four layers.

The first is the agent access layer. `rea mcp` starts an MCP server over stdio. I performed a real JSON-RPC handshake: `initialize` succeeded and `tools/list` returned 170 tools, with names like `open_binary`, `analyze_function`, `batch_decompile`, and `inspect_binary_layout`. `npx rea-agents setup` registers the server with the agent client you choose and installs an investigation-workflow skill that teaches the agent what to check first, what to check next, and how to follow up when the evidence is thin.

The second is the workflow layer, shared by the CLI and MCP. The CLI exposes a hundred-plus commands — `analyze`, `function`, `decompile`, `xrefs`, `search` for native analysis; `capture-process` for behavior capture; `compare-process-captures` for diffing two runs. The only difference is invocation: the CLI is a fresh process per call with results saved to disk, while MCP is a persistent session.

The third is the analysis-engine layer, and the most commonly misunderstood. Deep native analysis — decompiled pseudocode, function dossiers — is not implemented by REA. It bridges to one of three existing engines: Ghidra, through a Java bridge script (ReaGhidraBridge) running headless and talking over a local unix socket, requiring Ghidra 12.1.x; Hopper, through a Python bridge; and IDA, through IDA's own MCP registration, bring-your-own-license and bring-your-own-instance. REA is MIT-licensed, but that license grants you no commercial engine. IDA and Hopper still cost what they cost. Ghidra is free, which is why it is the route tested here.

A separate set of capabilities needs none of those engines: offline ELF layout parsing (through a Python environment you supply, pinned to pwntools 4.15.0, pyelftools 0.33, and Unicorn 2.1.2; read-only parsing of sections, segments, symbols, relocations, and mitigations, never executing the target), inspection of metadata embedded in Go binaries, purely static parsing of JavaScript and .NET files, and process behavior capture that actually runs the target under a PTY.

The fourth layer is the evidence layer, and in my judgment it is the real design center. Every call returns a structured Evidence record: an `evidence_id`, the target file's SHA-256, the provider and its version, the raw and normalized results, a confidence label such as observed or inferred, and an explicit list of limitations — what was not checked and what is inferred rather than seen. REA deliberately refuses to hand you a verdict. That is a different temperament from one-click report generators, and it is what makes automated follow-up questions defensible: every step can be traced back to specific evidence and open items.

Two further design notes. According to REA's own documentation, analysis runs entirely on your machine and target files are not uploaded to REA's servers. I did not verify that with packet capture, so treat it as a vendor claim, not a measurement — and note that what your agent does with tool results afterward is governed by your model provider's data policy, which is a separate question. The claimed target coverage is broad: beyond native binaries it lists Go, .NET, JavaScript/Electron, Android APKs, firmware, WASM, EVM bytecode, SQLite, pcap files, and crash dumps. This article tests exactly one of those lanes, native ELF, and draws no conclusions about the rest.

The target, `checkme`, is 30 lines of my own C: it takes a key on the command line, and `check_key()` first compares the length, then XORs the input byte-by-byte against a built-in constant and accumulates; only a zero sum passes. I built a symbolled and a stripped version. The correct key is 13 bytes. The question for the day: starting from "we do not know the answer," how far does this toolchain get, and at which step does a human — or an agent — still have to actually think?

## 3. Measurements

### 3.1 Readiness check: half the tool works out of the box

Installing `rea-agents` globally (version 6.4.0) took about 1 minute 51 seconds. `rea doctor` was refreshingly honest: Node and the host were healthy, but all three deep engines — Hopper, Ghidra, IDA — were missing, and the workflow skill was not installed. Out of the box you get only the built-in capabilities; deep decompilation requires bringing an engine. Doctor spelled out what was missing and how to fix each item, which already puts it ahead of tools that hand you a stack trace.

One piece of friction runs through everything: every rea command cold-starts in roughly 20 to 30 seconds, `rea --help` included. I did not profile where that time goes; my guess is Node loading the full tool catalog at startup, but that is a guess and I am labeling it as one. If you explore interactively at the rhythm you would use in Ghidra's GUI, this will wear on you. The tool rewards deciding your questions first and fetching evidence in batches.

### 3.2 Offline ELF layout: the manual jigsaw, done in one pass

I created a Python venv with pwntools — the versions landed exactly on REA's pins — pointed `REA_PWNTOOLS_PYTHON` at it, and ran `rea inspect-binary-layout ./checkme --json`. About 22 seconds later I had roughly 45 KB of Evidence JSON. I reopened that file while finalizing this article; the numbers are:

- 31 sections, 13 segments, 48 symbols, 11 relocations, with the file anchored by SHA-256;
- mitigations matching the build reality item by item: PIE on, NX on, non-executable stack, Full RELRO, and no stack canary — correct, because the source has no local arrays. The whole set is labeled inferred rather than observed, which is the honest label;
- a symbol table that names `main`, `check_key`, and `strlen` outright, so you know where to start;
- 12 limitations attached, including that link-time addresses are not runtime addresses and that relocation inventory completeness is unknown. Nothing swept under the rug.

This replaces the manual `checksec`-plus-`readelf` jigsaw with one structured pass. Repeating it on the stripped binary left only 9 dynamic symbols — the libc imports — with `check_key` and `main` gone. That is expected, and it draws the boundary of this lane precisely: layout only, no function recovery.

### 3.3 Behavior diffing: locate the divergence before reading code

Next, black-box capture. I ran `rea capture-process` once with a wrong key and once with the right one (about 30 seconds each, PTY startup included) and diffed them with `rea compare-process-captures`. The result names a first_divergence: terminal event 0, ACCESS DENIED on the left, ACCESS GRANTED on the right, with the exit dimension also marked changed. I checked the raw comparison JSON; its confidence is labeled derived — a conclusion computed from two captures rather than a single observation — which is the correct label.

On a toy target this looks trivial. The value is the ordering habit: confirm behaviorally which input decides success before you open the static analysis. Get the order right and you skip a lot of wandering later.

### 3.4 Ghidra deep analysis: it worked — the second time

First, the setup bill, because it is real: this machine had no Java. Temurin JDK 21 (198 MB, about 2 minutes) plus the Ghidra 12.1 release (542 MB, about 10 minutes), roughly 874 MB unpacked, plus `GHIDRA_INSTALL_DIR` and `JAVA_HOME` to set. Call it about 740 MB of downloads before the deep lane opens. Any honest evaluation has to count that.

Then `rea analyze ./checkme --provider ghidra --json`:

- Attempt one: about 3 minutes 26 seconds, failed with error code `cleanup_incomplete`. Ghidra's own log showed import and post-analysis succeeding, but REA's teardown refused to confirm cleanup because the process tree contained orphaned or PID-reused processes, and failed the whole run. My inclination is that its process-ownership checking clashed with this containerized environment, but I did not root-cause it — container PID namespaces and process reaping were never individually ruled out — so this is recorded as an unlocalized failure, not an explained one. No workaround was applied and it is not reported as a success.
- Attempt two: about 2 minutes 50 seconds, success — with a caveat. The overview's normalized result is only about 2.7 KB (the saved JSON file is about 4.4 KB): segment layout plus counts. It counted 30 procedures and 80 strings and gave pseudocode for none of them. Deep answers require naming the function you want.

So I named it: `rea function ./checkme check_key --provider ghidra --json` took about 2 minutes 42 seconds and returned a roughly 52 KB dossier with three things that matter. First, decompiled pseudocode matching the source logic line for line, with placeholder names like `param_1` and `DAT_00102004`: compare `strlen` against 0xd — 13 — then XOR the input byte-by-byte against the constant at `DAT_00102004` and accumulate; pass only if the sum is zero. Second, the full assembly listing: a 76-byte function body at 0x101189–0x1011d4, which I verified against the raw JSON. Third, the call graph edges: caller `main` at 0x1011d5, callee the `strlen` PLT thunk, with incoming reference addresses.

That closed the loop. Within this target's value range — password and constant are plain ASCII, so every XOR result lands between 0 and 127 — a zero sum is equivalent to byte-for-byte equality, so the 13 bytes at that address are the key; I read them out by file offset and confirmed. One precision worth adding: the pseudocode accumulates the XOR result truncated to a char, so with high-bit bytes, signed interpretation could in theory let several mismatches cancel out to zero. As a teaching target this check is fine; as a real password check it would be an exploitable weakness, and "sum equals zero" should never be mistaken for a cryptographic equality test. From opening an unfamiliar binary to recovering both the checking logic and the key, no human read any assembly. For completeness: with no engine configured, the same analyze command fails politely — a structured `provider_unavailable` error with remediation guidance instead of a crash.

### 3.5 The MCP channel, and the full timing table

`rea mcp` runs over stdio; the JSON-RPC `initialize` handshake succeeded, the server identifies as rea 6.4.0, and `tools/list` returned 170 tools. Scope discipline matters here: 170 is the catalog size. The tools I actually exercised and verified are a small subset — binary opening, layout inspection, behavior capture and comparison, Ghidra analysis, and the function dossier. The other 160-plus tools are unverified by this article, and a directory count must not be passed off as capability verification. Within the subset I used, CLI and MCP are two front doors to the same workflows.

Full run log, all from that day:

- Shallow repo clone (56 MB): success, about 28 s
- `npm i -g rea-agents`: success, about 1 min 51 s
- `rea doctor`: success, three engines reported missing, about 30 s
- Offline ELF layout, symbolled and stripped: both success, about 22 s each
- Process capture twice plus comparison: success, first behavioral divergence pinpointed, about 30 s each
- Analyze with no engine configured: failed cleanly with `provider_unavailable`, as expected, about 23 s
- JDK 21 plus Ghidra 12.1 download and unpack: success, about 740 MB, about 14 min
- Ghidra analyze, attempt one: failed, `cleanup_incomplete` (engine analysis succeeded, teardown verification failed), about 3 min 26 s
- Ghidra analyze, attempt two: success, segment-level overview only, about 2 min 50 s
- Ghidra function dossier for check_key: success, logic fully recovered, about 2 min 42 s
- MCP initialize plus tools/list: success, 170 tools, about 23 s

## 4. Analysis and trade-offs

Where the division of labor genuinely holds: it splits the Ghidra learning curve into two stages. First you understand what a function does by questioning an agent that fetches evidence; then you learn the tool itself against the assembly and pseudocode you already understand. For anyone studying malware analysis or binary fundamentals, that order beats staring at an empty Ghidra window. Behavior diffing is the second habit worth stealing: behavior first, statics second is the same discipline as comparing normal and anomalous samples in dynamic analysis.

Four selection judgments for anyone evaluating this stack:

First, Ghidra versus IDA. REA does not change either engine's economics. Ghidra is free and headless-friendly; the price is the setup bill above and minute-scale calls. IDA's recovery quality and ecosystem are their own argument, but the license is yours to buy — REA's MIT license does not extend to it. My recommended order: teams that already hold IDA licenses should use that integration; everyone else should get the workflow running on Ghidra first.

Second, CLI versus MCP. For one-off scripts and auditable reruns, use the CLI; evidence on disk is naturally traceable. For multi-step investigations where an agent keeps asking follow-ups, use MCP. A persistent session should amortize repeated cold starts in theory — but I did not measure per-call latency inside a session, and the handshake alone took about 23 seconds, the same order as a single CLI call. So "MCP is faster" is an architectural expectation in this article, not a measured result; measure session latency yourself before choosing on speed. Also, a persistent session means evidence management depends on session semantics; do not mix the two modes' outputs in one folder and expect clean accounting.

Third, is the evidence contract worth its verbosity? Every result carrying limitations and a confidence label looks like overhead until you are the reviewer: you no longer have to guess which sentence was observed and which was inferred. In report-writing, delivery, or graded casework, that verbosity is net profit. For a one-off glance at a binary, it is pure cost. Know which mode you are in.

Fourth, and most important: every step that requires judgment was left to the caller, by design. Understanding the pseudocode's semantics — why a zero XOR sum means byte equality here, and when it would not — was the caller's work. Deciding to read the bytes at `DAT_00102004` was the caller's work. Translating length 0xd into 13 characters was the caller's work. REA supplies evidence and open items; the conclusion belongs to whoever called it, and an agent that misreads pseudocode will produce a wrong conclusion that looks thoroughly evidenced. "Agent plus REA" does not mean unmanned reverse engineering. It means automated evidence collection with judgment still on the human side — and anyone who quietly drops the second half of that sentence will eventually be bitten by it.

## 5. Limitations and open questions

Measured limitations:

- Cold starts are slow: 20 to 30 seconds per CLI command, and Ghidra-backed calls are measured in minutes. Function-level answers must be requested one function at a time, so cost grows roughly linearly with function count. I did not test full deep analysis of a large binary and will not extrapolate to one.
- The `analyze` overview is shallow by design — layout and counts only. If you expect one command to hand you function-level conclusions, you will be disappointed; the design pushes you to arrive with a question and fetch named evidence.
- Against stripped, packed, or obfuscated targets, the layout lane degrades to dynamic symbols, and the deep lane inherits whatever recovery ability the engine itself has. REA adds no magic. My target was an unobfuscated program I wrote, so this article has no standing to quote recovery rates on real-world samples.
- The process-ownership check failed once on containerized Linux with `cleanup_incomplete` and passed on retry. Unattended batch runs need retries and failure logging budgeted in; do not assume a 100 percent first-pass success rate.
- Only the native ELF lane was tested. APK, firmware, WASM, EVM, and the rest of the coverage list went unexercised, and unexercised means unjudged.
- The ceiling on conclusion quality is the agent and the human reviewing it. Evidence chains can skip steps and pseudocode can be misread, and such errors arrive wearing Evidence IDs, which makes them look more credible, not less. That is the most dangerous failure mode in the whole setup.

Legal and compliance boundaries, which are not optional:

- Analyze only software you own or are explicitly authorized to analyze: your own programs, CTF and lab targets, samples you purchased under terms that allow it, client deliverables with written authorization.
- Unauthorized reverse engineering of commercial software can trip three wires at once: anti-reverse-engineering clauses in the EULA; DMCA Section 1201 anti-circumvention rules, where bypassing a technical protection measure can be unlawful in itself and legitimate purposes have only bounded exceptions; and unauthorized-access statutes. REA's own DISCLAIMER takes the same line: lawful research, education, interoperability, and software preservation.
- Commercial engine licenses are yours to obtain legitimately, and trial-license restrictions on automation and sharing outputs apply in full.
- Practical rule: learn on crackmes, CTF challenges, and programs you wrote — exactly what this article does. At work, with a client binary, confirm the authorization paperwork is in hand before you touch anything.

Open questions I am leaving for follow-up measurements rather than pre-spending conclusions: recovery-quality differences on the same target with the IDA provider, deep-lane behavior on a packed sample, and the context cost of accumulated evidence in long MCP sessions.

## 6. References and sources

- REA repository and documentation: morluto/rea (MIT), npm package rea-agents 6.4.0; architecture descriptions checked against its README, docs, and the ReaGhidraBridge sources under bridge/ghidra.
- Primary test materials: target source checkme.c (30 lines, my own), and the Evidence JSON files — layout_checkme.json (31 sections, 13 segments, 48 symbols, 11 relocations; provider pwntools 4.15.0 / pyelftools 0.33 / Unicorn 2.1.2), layout_stripped.json (9 dynamic symbols), capture_compare.json (first_divergence at terminal event 0), ghidra_func_checkkey.json (check_key dossier, Ghidra 12.1, 76-byte body at 0x101189–0x1011d4). Each was re-opened and re-checked before this article was finalized.
- Engine versions: Ghidra 12.1 PUBLIC, Temurin JDK 21, Node 24.20, Ubuntu 24.04.
- Legal reference: DMCA anti-circumvention provisions, 17 U.S.C. § 1201. Consult a lawyer for specific cases; this article is not legal advice.

---

Disclosure: All code, target programs, and experiments in this article are the author's own clean-room work. The experiments were run only against the author's own program. No client information, client code, or unauthorized software is involved in any way.

Author: Guangyi Zhao
