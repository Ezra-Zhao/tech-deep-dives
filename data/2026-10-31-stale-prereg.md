# 预注册：陈旧标记的边界实测（2026-10-31，跑活体前冻结）

承接 2026-10-27 篇第 3.3 节与第 5 节标为推理的边界：普通抓取路径下，
抓取不再返回样本时 Prometheus 给序列打陈旧标记，absent() 的盲窗从
预注册的 360-380 秒塌到实测约 75 秒；但官方文档同节点名例外——带
自有时间戳的 exporter 序列停发后会把最后的值保留满 5 分钟回望期。
本轮把这条推理边界起活体验证，并加测第二条无抓取记账路径。

## 三条路径（同口径：抓取 5s、超时 4s、规则组评估 15s、for: 1m）

- C 普通抓取（对照复测）：仓库真 exporter（src/prom_exporter.py）
  服务运行 20261019-171627 产物副本，样本无自有时间戳（Prometheus
  以抓取时刻记账）。告警 absent(nal_exporter_results_present
  {group="scenario_summaries"})，与 2026-10-27 篇逐字同式。
- T 自带时间戳：自写极小 exporter，每次抓取只吐同一序列，值恒 1，
  每条样本带显式时间戳（毫秒，取该次请求时刻）；抓取配置
  honor_timestamps 用默认值 true（不显式关闭）。告警同 C 式。
- R 录制规则复刻：抓取同 C；另设录制规则组（评估 15s）
  record: nal_present_recorded，expr 为 C 的 present 序列。
  同一轮内并行两条告警：原序列 absent（同 C 式，作同轮内对照）与
  absent(nal_present_recorded)。

每条路径独立 Prometheus 3.15.0 实例、全新 TSDB、回环单机。
流程同构：等健康基线（present 为 1，R 路径另等 recorded 为 1）
并保持 30 秒，SIGTERM 杀 exporter（T 路径杀自写 exporter），
轮询至该路径主告警 firing 后再保持 20 秒收尾。
轮询每 5 秒记录 up、present、absent、recorded（R）、全部告警快照；
盲窗量法与 2026-10-27 篇一致：pending 取告警 API 的 activeAt，
firing 给区间（activeAt + for: ，首次轮询见到 firing）。

## 预注册预测（跑数前写死，错了照实报）

- P-C：C 路径 absent 盲窗落在 60-85 秒（复测 2026-10-27 的约 75 秒），
  present 即时查询在杀后第一个 5 秒轮询即为空。
- P-T：T 路径 present 在杀后仍可见约 300 秒（最后样本时间戳加
  5 分钟回望），absent 盲窗回到 5 分钟量级，落在 355-390 秒。
  依据：官方 Staleness 节对自带时间戳序列的例外表述。
- P-R：R 路径 recorded 序列在源头死后，由录制规则评估接手记账；
  官方 Staleness 节把「规则评估不再返回样本」与抓取并列为打陈旧
  标记的触发，故预测 recorded 在源序列陈旧（约 5 秒）后第一次
  返回空的评估（15 秒内）即被陈旧化，absent(nal_present_recorded)
  盲窗落在 65-100 秒（比 C 多至多一个评估对齐量级），不回到
  5 分钟量级。若实测回到 5 分钟量级，则说明录制规则输出不吃
  陈旧标记，预注册此条即被推翻、照实报。
- P-R2：R 路径内原序列 absent 盲窗与 C 路径一致（同轮内对照，
  差异在轮询与评估对齐量级内，即 15 秒内）。

## 判定口径

- 主结论量：三条路径主告警的 pending 时延（activeAt 减杀时刻）、
  firing 区间、present/recorded 即时查询首次变空的轮询时延。
- 数字以活体 JSON 为准；终校脚本化核对文中数字与 JSON。
- T 路径 exporter 只吐 present 一族，是刻意隔离：本轮问题只是
  时间戳对陈旧化的影响，不测该 exporter 的其他指标完备性。
