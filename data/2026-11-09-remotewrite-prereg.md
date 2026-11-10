# 预注册：远端写入路径的 absent 盲窗实测（2026-11-09，跑活体前冻结）

承接 2026-10-31 篇第 5 节未解问题：远端写入（remote write）推入的
present 复刻序列停推后，既无抓取也无本地规则评估记账，量其 absent()
盲窗落在陈旧档（约 75 秒）还是回望档（约 370 秒），并与抓取/录制/
时间戳三档对照（前三档数字出自 2026-10-27 与 2026-10-31 两篇同口径
实测，本轮另跑直接抓取对照复测）。

## 两条路径（同口径：抓取 5s、超时 4s、规则组评估 15s、for: 1m、
## 回望期默认 300s、Prometheus 3.15.0、每路径全新 TSDB、回环单机）

- C 普通抓取（对照复测）：单个 Prometheus 直接抓取仓库真 exporter
  （src/prom_exporter.py）服务运行 20261019-171627 产物副本，样本无
  自有时间戳。告警 absent(nal_exporter_results_present
  {group="scenario_summaries"})，与 2026-10-27/10-31 篇逐字同式。
  死法：SIGTERM 杀 exporter（与前作同）。
- W 远端写入：发送端 Prometheus 抓取同一 exporter（同抓取口径），
  经 remote_write 把全部序列推给接收端 Prometheus（接收端以
  --web.enable-remote-write-receiver 启动、全新 TSDB、不抓取该
  exporter）。接收端告警同 C 式，作用于被推入的 present 序列。
  死法：只 SIGTERM 杀发送端，exporter 保持存活——隔离「停推」本身，
  排除源头死亡的混杂；杀后直连 exporter /metrics 验证其仍健康。

流程同构：等健康基线（C：present 为 1；W：接收端 present 为 1）并
保持 30 秒，执行死法，轮询至主告警 firing 后再保持 20 秒收尾。
轮询每 5 秒记录 present 即时查询、absent() 即时查询、全部告警快照；
W 路径另记接收端 up{job="net-assurance-lab"} 即时查询与 present
样本自带时间戳。盲窗量法与前作一致：pending 取告警 API 的
activeAt，firing 给区间（activeAt + for:，首次轮询见到 firing）；
W 路径另给「最后样本时间戳之后可见时长」的夹逼区间。

## 预注册预测（跑数前写死，错了照实报）

- P-C：C 路径 absent 盲窗落在 60–85 秒（复测前两轮的约 75 秒），
  present 即时查询在杀后第一个 5 秒轮询即为空。
- P-W1（主预测）：W 路径落在回望档——接收端 present 在停推后仍
  可见约 300 秒（最后样本时间戳 + 300 秒回望），absent 盲窗
  （firing 下界减杀时刻）落在 355–390 秒。依据：接收端从不抓取
  该序列，无人替它打陈旧标记；发送端的抓取陈旧标记是发送端本地
  TSDB 的记账，不随 remote_write 样本流传到接收端（官方文档
  Staleness 节只把陈旧标记定义在抓取/规则评估的本地记账上）。
  若实测落在 60–100 秒，则主预测被推翻，说明另有机制让接收端
  提前陈旧化，照实报并改判。
- P-W2：接收端全程（基线段含在内）查不到该 job 的 up 序列
  （up{job="net-assurance-lab"} 恒空）——接收端对被推序列没有任何
  抓取层记账，up 型规则在这条路径上结构性不存在。
- P-W3：杀发送端之后，直连 exporter /metrics 仍返回 200 且
  present 值为 1——本轮 W 的死亡纯粹是停推，源头未死。

## 判定口径

- 主结论量：两条路径主告警的 pending 时延、firing 区间、present
  即时查询首次变空的轮询时延；W 路径另报最后样本时间戳与可见
  时长夹逼。
- 发送端 SIGTERM 后可能刷完 remote_write 队列再退出，最后样本
  时间戳可晚于杀时刻数秒；可见时长以样本时间戳为锚、杀时刻口径
  并报，不混算。
- 数字以活体 JSON 为准；终校脚本化核对文中数字与 JSON。
