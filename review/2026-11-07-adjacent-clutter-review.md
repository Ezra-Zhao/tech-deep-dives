# 审稿记录：相邻杂物伤害曲线（2026-11-07）

- 稿件：articles/2026-11-07-adjacent-clutter-harm-curve.md
- 交叉审方式：多模型交叉审（额度池 OVH Meta-Llama-3.3-70B-Instruct）。
  额度池首轮：Mistral 429、OVH RemoteDisconnected、Pollinations 超长、
  Gemini 402、OpenAI 429，全池失败（pool-out 存档）；随后 OVH 直连重试
  一次成功（原始回执 review/2026-11-07-adjacent-clutter-ovh-raw.json）。
- 审稿结论：无事实错误/逻辑跳跃/夸大表述，建议通过，无具体改文意见；
  3 条一般性提醒（模拟数据适用范围、读者门槛、局限值得跟进）均已由
  正文第 5 节局限覆盖，附理由驳回、不改文。
- 作者终校：脚本化 36 项数字核对（合并率/正确率/花苞改判率/端到端
  TP-FP-FN/穿越点/面积分布/FP 对账/整核臂）全部通过；送审前作者自查
  修正 2 处（对账计数句、混入英文词的表述各一）。
- 关键数据：data/2026-11-07-adjacent-clutter-bench.json、
  预注册 data/2026-11-07-adjacent-clutter-prereg.md、
  事后复算 data/2026-11-07-adjacent-clutter-posthoc.json（含 8 个改判
  花苞逐个定位与附加面积中位数，附加面积为同管线复跑值）。
