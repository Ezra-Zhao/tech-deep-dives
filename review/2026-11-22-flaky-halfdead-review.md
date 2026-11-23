# 交叉审记录：间歇成功型半死实测（2026-11-22）

- 审稿通道：额度池轮换——OVH 返回 429（本轮按硬停规矩不再重试）、
  Mistral 返回 429、Gemini 返回 402（预付额度耗尽）；最终由
  Pollinations（GPT-OSS 20B，openai-fast）审英文版，分三段送审
  （GET 长度上限所致），回执存 review/2026-11-22-flaky-halfdead-
  pollinations-raw-part{1,2,3}.txt；OVH/Mistral/Gemini 失败回执存
  review/2026-11-22-flaky-halfdead-{ovh,mistral,gemini}-raw.txt。
- 结果：第一段 PASS；第二、三段各报 NEEDS FIXES，实质异议 3 条，
  逐条回查原始数据后全部附理由驳回，无改文：
  1. 「B 的 present 变空应为 69/82 而非 54/82」——审稿方把 exporter
     成功次数（flaky 窗 14 次）当作轮询口径：轮询为 5 秒快照，一次
     成功亮约 10 秒≈2 个轮询，实测 present 为 1 的轮询 28 个、变空
     54 个，与 posthoc 逐轮询统计一致。驳回。
  2. 「C 首个成功间隔 85 秒无据」——据在 exporter 尝试账：flaky 窗
     成功时刻相对切换为 −0.8 秒与 84.2 秒，间隔 85.0 秒（posthoc
     success_gaps_s 首项）。送审 ground truth 摘要未含此项，系摘要
     不全非正文无据。驳回。
  3. 「『六分钟』夸大 pending 时长」——审稿方误读：原文「告警没有
     动静超过六分钟」指 firing 段持续 386.6 秒≈6.4 分钟，与
     pending 起点 +19.8 秒是两个量，正文两处分别明写。驳回。
  其余条目审稿方自标「matches / correct」。
- 终校：脚本化 26 项数字核对（posthoc 对中英文正文）全过。
- 预注册对账：P-A 命中；P-C/P-D 半中；P-B/P-UP/P-GAP 未中，
  正文第 3.4 节逐条认账。
