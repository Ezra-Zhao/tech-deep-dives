# tech-deep-dives

Deep-dive technical articles, one per day, each built on a real experiment I ran myself: measured data, reproducible steps, stated limitations. No survey fluff.

深度技术文章：每天一篇，每篇都有真跑出来的实测数据、可复现步骤和写明的局限。

Author / 作者：Guangyi Zhao

## Articles / 文章目录

| Date | 中文版 | English |
|---|---|---|
| 2026-10-13 | [让智能体自己拿 Ghidra 干活：REA 实测复盘——170 个 MCP 工具、一次口令恢复，和它到不了的地方](articles/2026-10-13-rea-mcp-ghidra-reverse-engineering.md) | [Letting an AI Agent Drive Ghidra: A Hands-On Test of REA's 170 MCP Tools, One Recovered Password, and the Limits](articles-en/2026-10-13-rea-mcp-ghidra-reverse-engineering.md) |
| 2026-10-13 | [诊断任务该用多大的并发池：Go-Diagnoser-Engine 的并发模型实测与源码取舍](articles/2026-10-13-go-diagnoser-engine-concurrency.md) | [How Big Should the Worker Pool Be? Measuring the Concurrency Model of a Go Diagnostics Engine](articles-en/2026-10-13-go-diagnoser-engine-concurrency.md) |
| 2026-10-14 | [给 GPU 故障诊断接一个 LLM 之前：AI-Node-Sentinel 的接线点设计与六个失效模式实测](articles/2026-10-14-ai-node-sentinel-llm-triage-failure-modes.md) | [Before You Wire an LLM Into GPU Fault Triage: AI-Node-Sentinel's Integration Point and Six Measure Failure Modes](articles-en/2026-10-14-ai-node-sentinel-llm-triage-failure-modes.md) |
| 2026-10-15 | [扫描器报出来的漏洞，有多少是真的：Web-Vuln-Scanner 检测管线与误报控制实测](articles/2026-10-15-web-vuln-scanner-false-positive-control.md) | [How Many of a Scanner's Findings Are Real? Web-Vuln-Scanner's Detection Pipeline and False-Positive Control, Measured](articles-en/2026-10-15-web-vuln-scanner-false-positive-control.md) |
| 2026-10-16 | [一句「可以便宜点吗」，客服 Agent 就把单下了：Wiper-Service-Agent 对话状态机实测](articles/2026-10-16-wiper-service-agent-state-machine.md) | ["Can You Make It Cheaper?" — and the Agent Booked the Order: A State-Machine Field Test of Wiper-Service-Agent](articles-en/2026-10-16-wiper-service-agent-state-machine.md) |
| 2026-10-17 | [总数全对，结构全错：Bloom-Counter 农业计数管线的光照与遮挡实测](articles/2026-10-17-bloom-counter-lighting-occlusion.md) | [The Total Was Right and the Structure Was Wrong: Stress-Testing a Flower-Counting Pipeline Against Light and Occlusion](articles-en/2026-10-17-bloom-counter-lighting-occlusion.md) |
| 2026-10-18 | [还没接上真模型，隐私账就已经欠下了：Emotion-Guard 幼儿园情绪识别的落地约束实测](articles/2026-10-18-emotion-guard-privacy-first-kindergarten.md) | [The Privacy Bill Comes Due Before the Real Model Arrives: Field Constraints of Emotion-Guard, a Kindergarten Emotion-Recognition Demo](articles-en/2026-10-18-emotion-guard-privacy-first-kindergarten.md) |
| 2026-10-19 | [让另一个模型审你的稿子，到底能审出什么：七篇文章、四十条意见的交叉审实测](articles/2026-10-19-cross-model-review-audit.md) | [What a Second Model Actually Catches: Seven Articles, Forty Review Comments, Measured](articles-en/2026-10-19-cross-model-review-audit.md) |
| 2026-10-20 | [阈值不是常数，是距离的函数：面积阈值检测器的标定漂移实测](articles/2026-10-20-bloom-counter-calibration-drift.md) | [Thresholds Are Not Constants: Calibration Drift in an Area-Threshold Detector, Measured](articles-en/2026-10-20-bloom-counter-calibration-drift.md) |

## Standards / 写作标准

- Every claim traces to a first-hand source: a paper, official docs, source code, or my own test logs.
- Every draft passes an independent cross-review by a second AI model before publication; the review method is recorded per article.
- Limitations are mandatory. An article that only reports successes does not ship.

## Clean-room disclosure / 声明

All code and experiments in this repository are my own clean-room work, written and run by me for learning, research, and documentation. They do not involve any client information, client code, or proprietary material of any employer or third party.

本仓库全部代码与实验均为作者 clean-room 自有产出，用于学习、研究与记录，不涉及任何客户信息、客户代码或任何雇主及第三方的专有材料。

## License

MIT — see [LICENSE](LICENSE).
