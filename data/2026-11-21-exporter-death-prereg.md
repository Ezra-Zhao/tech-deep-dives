# 预注册：存活发送端之后的 exporter 之死实测（2026-11-21，跑活体前冻结）

承接 2026-11-09 篇第 5 节未解问题：上一篇杀的是发送端、exporter 存活，
接收端 present 活满回望期、up 冻结在 1（firing 366.8–371.1 秒、无快速
信号）。本篇把死法反过来：remote_write 发送端 Prometheus 保持存活、
继续抓取与推送，只 SIGTERM exporter 本身。量接收端三条路径的形态，
并与杀发送端格、直接抓取格对照。

## 台架（与 2026-11-09 篇同口径）

Prometheus 3.15.0（官方 tar 包 111,651,578 字节、gzip 校验通过，本轮
重新下载解压）、抓取间隔 5s、超时 4s、规则组评估 15s、for: 1m、回望期
默认 300s、每路径全新 TSDB、回环单机。exporter 为仓库真 exporter
（src/prom_exporter.py）服务运行 20261019-171627 产物副本。

- E 主格（远端写入、杀 exporter）：发送端 Prometheus 抓取 exporter 并
  remote_write 推给接收端（--web.enable-remote-write-receiver、全新
  TSDB、不抓取 exporter）。接收端与发送端本地各挂两条候选规则：
  absent(present)（与前作逐字同式）与 up{job="net-assurance-lab"} == 0
  （本篇新增候选，两条同 for: 1m）。死法：只 SIGTERM exporter，发送端
  不动；杀后直连 exporter /metrics 应失败、发送端进程应存活。
- C 对照格（直接抓取、杀 exporter）：单个 Prometheus 直接抓取同一
  exporter、只挂 absent 规则，死法同为 SIGTERM exporter——直接抓取档
  的第四次复测。

流程同构：等健康基线（接收端 present 为 1 且 up 为 1）并保持 30 秒，
执行死法，轮询（每 5 秒记 present、absent()、up 即时查询与全部告警
快照，E 格同时记发送端本地同组查询）至 absent 告警 firing，再保持
20 秒收尾。盲窗量法与前作一致：pending 取告警 API 的 activeAt，
firing 给区间（activeAt + for:，首次轮询见到 firing）。

## 预注册预测（跑数前写死，错了照实报）

- P-E1（接收端 up 快速翻转）：发送端活着，抓取失败样本带当前时间戳
  持续被推到接收端——接收端 up 在杀后 20 秒内（轮询粒度 5 秒）首次
  见到 0；up==0 告警 pending 在杀后 45 秒内，firing 下界落在
  75–120 秒。与 2026-11-09 杀发送端时 up 冻结在 1、301.0 秒才消失
  形成对照。
- P-E2（接收端 present 回望档）：present 在发送端本地被陈旧化停产，
  停产样本不随 remote_write 传到接收端，接收端只能按回望过期——
  present 即时查询首次变空落在杀后 290–315 秒，absent 告警 pending
  落在 300–335 秒，firing 下界落在 360–395 秒（中心约 370 秒，与
  2026-11-09 杀发送端格的 366.8 秒同档）。
- P-E3（两信号差）：接收端 absent firing 下界与 up==0 firing 下界
  之差不小于 240 秒——同一格里最快的信号与最慢的信号差出一个
  回望期的量级。
- P-E4（发送端本地对照）：发送端本地 present 即时查询在杀后 10 秒
  内变空（本地陈旧化）；本地 absent firing 下界落在 60–90 秒；
  本地 up==0 firing 下界落在 60–110 秒。即发送端本地两条信号都快，
  慢的只有接收端的 absent。
- P-E5（up 连续性）：接收端 up 序列杀后全程不变空（发送端持续推送），
  且首次见 0 之后取值恒为 0（exporter 不复活）；发送端进程在 E 格
  收尾时仍存活。
- P-C（对照复测）：C 格 absent firing 下界落在 60–85 秒（前三轮
  70.1–75.5 秒）。

## 判定口径

- 主结论量：E 格接收端两条告警各自的 pending 时延与 firing 区间、
  present/up 即时查询的翻转时刻；发送端本地同组量；C 格 absent
  firing 区间。
- 数字以活体 JSON 为准；终校脚本化核对文中数字与 JSON。
- 安全边界：只杀本轮自己启动的进程，不改 lab 仓原件（exporter 喂
  副本目录），重活串行。
