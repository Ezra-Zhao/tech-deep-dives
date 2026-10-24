# 十条告警规则，两条永远不会响：net-assurance-lab 告警链路实测

作者：Guangyi Zhao

## 1. 问题与背景

net-assurance-lab 是我做的一个回环网络可靠性实验台：流量发生器、应用层故障注入代理、故障报告，全在本机 127.0.0.1 上跑。2026-10-19 给它加了一套生产形态的监控模块：一个只读运行产物的 Prometheus exporter、10 条告警规则（monitoring/rules/alerts.yml）、两个 Grafana 看板（24 个面板、26 个查询目标）。当时的验证做得很足：真 Prometheus 3.15.0 和真 Grafana 13.2.4 端到端跑通，VERIFICATION.md 里记着告警接口的实况——10 条规则里 2 条 firing（NalLinkFlapDetected、NalBaselineP99LatencyHigh），其余 inactive，并注明「正确」。

这篇要问的是那句「正确」。一条规则没响，有两种可能：数据没到线，或者表达式根本算不出结果。前者是告警在干活，后者是告警死了、只是死法安静。10-19 的验证记录给基线丢包、畸形包回显、结果新鲜这三条 inactive 都写了数据层面的理由，唯独 NalFlapShareDominatesLoss 的 inactive 没有单独对账。而手头恰好有当时的运行产物可以复算：那次运行（20261019-171627，下称 R0）里，代理因链路抖动窗口丢的包是 2,861 个，因随机丢包丢的是 2,352 个——按这条规则自己的注释，它的触发条件（抖动份额大于随机份额）在 R0 上是成立的。它没响，不是因为没事，是因为响不了。

结论先说。10 条规则里 2 条是结构性死规则：NalFlapShareDominatesLoss 和 NalBaselineThroughputCollapse。两条的病根是同一个——拿同一指标、只差一个标签取值的两条序列直接做向量对向量比较，而 PromQL 默认的向量匹配要求两侧标签集完全一致，差一个标签就匹配不上、结果恒为空集。这不是阈值没调好，是表达式在任何数据下都返回空：把回显吞吐压到发送的 10%、把抖动份额拉到随机份额的 3 倍，喂给真规则引擎持续 10 分钟，两条规则依然零触发。修法加起来不到两行（ignoring(cause) 和一个比值式改写），修完在同样的测试输入下都按各自的 for: 窗口正常触发。其余 8 条规则本轮都至少观测到一次真实触发路径；两个看板的 26 个查询目标全部能在 exporter 输出里对上序列——看板没沾这个病，因为面板表达式全是单向量选择器，没有一条做向量对向量运算。

## 2. 方法

被测链路（全部来自实验台仓库 monitoring/ 与 src/prom_exporter.py）：

- exporter：Python 标准库实现，每次抓取重读 results/latest/ 的运行产物（四个场景的汇总 JSON、逐包 CSV、服务器计数、代理决策日志末尾的 summary 行、run_meta.json），渲染 nal_* 指标族。它发布的是「最近一次已完成运行」的快照，数值在两次运行之间恒定——这个前提决定了后面 for: 和「陈旧」的读法，规则文件头注释里也如实写了。
- Prometheus 配置（monitoring/prometheus.yml）：抓取间隔 5s，规则组评估间隔 15s；alerting.alertmanagers 是空列表，即没有接 Alertmanager，告警只在 Prometheus 自己的 /alerts 页和 API 里可见。
- 规则：10 条，严重度三档 info / warning / critical。for: 分布：0s 一条（NalMalformedPacketEchoed，critical）、15s 一条（NalLinkFlapDetected，info）、1m 七条、5m 一条（NalResultsStale）。

测试分四层，越往下越接近真实引擎：

1. 静态层：promtool check rules 与 check config，确认语法与配置合法。
2. 语义层（规则当代码测）：用 Prometheus 官方的 promtool test rules 给规则喂构造好的输入序列，在指定评估时刻断言哪些告警应当 firing、哪些应当为空；另写 15 个夹具，把合成的 results 目录推过 exporter 真实的 collect() 代码路径，测阈值等值边界（表达式全是大于号，等值必须不触发）与单规则翻转。判读分两轨：先从运行产物直接算「作者意图」是否成立，再看表达式按 PromQL 语义实际产出什么——两轨不一致就是缺陷，意图轨保证我测的不是自己复述的表达式。
3. 活体层：重新从官方发布页下载 Prometheus 3.15.0（tar 包 111,651,578 字节，gzip 校验通过），用仓库自己的 prometheus.yml 起真服务，exporter 指向 R0 运行产物的一份副本（仓库本体不改）。做三件事：对可疑表达式及其修正式做即时查询对照；在约 336 秒的窗口里对 /api/v1/alerts 做四次快照，覆盖 pending 到 firing 的全过程（最慢的 NalResultsStale 需要 for: 5m）；最后把副本改成一个「已恢复」运行（run_id 换成当前时间、基线 p99 改回 5 ms、代理 dropped_flap 改 0），45 秒后再看告警是否全清。
4. 对账层：两个看板的全部 26 个查询目标逐个拿去 exporter 输出里匹配序列，并把关键面板值与底层 JSON 产物逐项核对；再把两个留档运行 R0（20261019-171627）与 R1（20261019-154535）的完整告警集并排算一遍，看运行间抖动会翻动哪些规则。

交叉审方式见台账与审稿记录；本节先把方法交代完，正文数字全部来自 data/2026-10-24-alert-chain-bench.json、data/2026-10-24-alert-chain-live.json 与两份 promtool 测试文件（同目录）。

## 3. 实测数据

### 3.1 两个留档运行与「今天」的告警集

从产物复算的意图值：

| 输入 | R0（20261019-171627） | R1（20261019-154535） |
|---|---|---|
| 基线丢包率（burst / sustained） | 0 / 0 | 0 / 0 |
| 基线 p99（burst / sustained，ms） | 12.486 / 120.452 | 5.517 / 6.952 |
| 故障场景丢包率 | 0.5897 | 0.5275 |
| 故障场景 p99（ms） | 443.359 | 245.775 |
| 代理丢弃：抖动 / 随机（个） | 2,861 / 2,352 | 2,595 / 2,680 |
| 抖动份额 / 随机份额 | 0.19377 / 0.15930 | 0.16115 / 0.16643 |
| 畸形包被回显 | 0 | 0 |

同一套规则、按原表达式求值（不计 for: 的时间条件）：R0 在 10-19 当天新鲜时触发集是 2 条（抖动检出、基线 p99），与 VERIFICATION.md 的活体记录一致；今天再评同一份 R0，多出 NalResultsStale——活体快照里它的取值是 438,034 秒（约 5.07 天），因为这份运行已经躺了五天。运行一个字节没变，告警集随墙钟变了，这是快照式 exporter 的必然结果，也是 NalResultsStale 存在的理由。R1 今天评是 2 条（抖动检出、陈旧）：它的基线 p99 最高 6.952 ms，离 50 ms 门槛很远；它的抖动份额也确实小于随机份额（0.16115 对 0.16643），NalFlapShareDominatesLoss 在 R1 上按意图本就不该响——这点在 3.2 里很关键，它解释了这个缺陷为什么在 R1 上看不出来、只在 R0 上露头。

### 3.2 两条死规则的取证

对 R0 的活体即时查询（真 Prometheus 3.15.0，真 exporter）：

| 查询 | 结果 |
|---|---|
| nal_fault_proxy_drop_ratio{cause="flap"} | 1 条序列，0.19377 |
| nal_fault_proxy_drop_ratio{cause="loss"} | 1 条序列，0.15930 |
| 两者按原式比较（flap 大于 loss） | 空 |
| 加 ignoring(cause) 后比较 | 1 条序列，0.19377 |
| 比值式 flap / ignoring(cause) loss | 1 条序列，1.21641 |
| 吞吐原式（echo 小于 0.5 倍 send，基线） | 空 |
| 吞吐比值式 echo / ignoring(kind) send | 2 条序列，均为 1（burst 与 sustained 回显等于发送，R0 健康，本就不该触发） |

两侧的数据都在、都不小，比较结果是空。Prometheus 官方文档对向量匹配的说法是：默认一对一匹配，两条目当且仅当标签集与对应取值完全相同时才配对，并特意给了 ignoring 的例子说不加这个关键字「就不会有任何匹配，因为两边指标不共享同一组标签」（见第 6 节出处 1）。这两条规则恰好都拿同一个指标的两个切片互比：drop_ratio 的两个切片只差 cause，throughput 的两个切片只差 kind——选择器写得越精确，两侧标签集差得越确定，匹配就越是恒空。

再用规则引擎本身定罪。promtool test rules（文件 data/2026-10-24-promtool-test.yml）对原版规则文件断言：抖动份额 0.30 对随机份额 0.10、持续 10 分钟，NalFlapShareDominatesLoss 零触发；回显吞吐为发送的 10%（100 对 1000 pps）、持续 10 分钟，NalBaselineThroughputCollapse 零触发。两条断言都通过——通过的意思是：引擎在意图条件强成立满 10 分钟后，依然什么都不产出。exporter 夹具轨复测一致：吞吐压到 10% 时原语义 0 实例、修正式 2 实例（两个基线场景各一）；抖动份额 3 倍时原语义 0 实例、修正式 1 实例。

修正式没有停在查询层。把两处改动写进规则副本（data/2026-10-24-alerts-patched.yml；抖动条加 ignoring(cause)，吞吐条改比值式 echo / ignoring(kind) send 小于 0.5），同一批 promtool 测试改成期望触发（data/2026-10-24-promtool-test-patched.yml）：两条规则在 30 秒评估点都还静默（for: 1m 未满），在 2 分钟评估点都 firing，标签与注释与预期逐字对上，测试 SUCCESS。活体层也验了数据侧：修正式在 R0 真数据上返回的比值 1.21641 与产物复算 2,861 / 2,352 一致。需要说明的是，本轮没有改仓库里的 alerts.yml——修复以补丁副本加测试文件的形式留在实验数据里，是否合入由我另行决定，文章只对「改法有效」负责。

### 3.3 for:、恢复与静默

for: 的行为在 promtool 正对照和活体两边都测了。promtool：for: 0s 的畸形包规则在第一个评估点（15s）即 firing；for: 15s 的抖动规则在 1 分钟评估点已 firing；for: 5m 的陈旧规则在 4 分钟评估点零触发、6 分钟评估点 firing。活体快照（R0 副本，启动后秒数）：

| 时刻 | NalLinkFlapDetected | NalBaselineP99LatencyHigh | NalResultsStale |
|---|---|---|---|
| 约 62s | firing（值 1） | pending（值 120.452） | pending（值 438,034） |
| 约 85s | firing | firing | pending |
| 约 336s | firing | firing | firing |
| 恢复补丁后 +45s | 无 | 无 | 无 |

恢复补丁只动了副本三处：run_id 换当前时间、两个基线场景的 p99 改 5.0、代理 summary 的 dropped_flap 改 0。45 秒后 /api/v1/alerts 返回空数组，三条 firing 全部解除。10 条规则都没有写 keep_firing_for，按官方语义，条件第一次不成立的评估即解除（出处 2）——实测与此一致。补充一个模型层结果：我用 15s 评估栅格写了个状态机仿真（data/2026-10-24-alert-chain-bench.py 的 D 部分），基线 p99 超标只持续 45 秒的瞬态尖峰只进 pending、到不了 firing 就回滚。这一条只算模型证据，引擎侧的同类语义已由上面 promtool 的 4 分钟与 6 分钟两个评估点实证。

静默的结论最短：这套栈里没有静默。prometheus.yml 的 alertmanagers 是空列表，静默是 Alertmanager 的功能，没有 Alertmanager 就没有静默入口，也没有任何通知路径——critical 级的畸形包规则就算触发，也只是 /alerts 页上多一行。想让它闭嘴，今天只能改规则或改数据。对一个以告警页为消费端的实验台，这可以接受；但任何人把这套规则原样搬进生产之前，这是第一件要补的事。

### 3.4 阈值边界与剩余规则

15 个 exporter 夹具的结果（全部走真实 collect() 代码路径）：

| 夹具 | 原式实例数 | 备注 |
|---|---|---|
| 基线丢包恰 0.05（等值） | 0 | 大于号语义正确 |
| 基线丢包 0.06 | 2 | 两个基线场景各一实例 |
| 基线 p99 恰 50（等值） | 0 | |
| 基线 p99 为 60 | 2 | |
| 故障丢包恰 0.75（等值） | 0 | |
| 故障丢包 0.80 | 1 | |
| 故障 p99 恰 1000（等值） | 0 | |
| 故障 p99 为 1200 | 1 | |
| 抖动丢弃为 0 | 0 | nal_link_flap_detected 为 0，不误报 |
| 畸形包回显 1 个 | 1 | critical 规则翻转正常 |
| run_id 为当前时间 | 0 | 陈旧规则不触发 |
| run_id 为 25 小时前 | 1 | 陈旧规则触发 |
| 删掉一个场景汇总文件 | 1 | NalExporterResultsMissing 按 group 触发 |

至此 8 条规则每条至少有一条实测触发路径（活体、promtool 或夹具），2 条死规则在任何输入下零触发且病根已定位——这是本篇的主账。

### 3.5 看板对账

两个看板共 24 个面板、26 个查询目标，逐个拿 R0 的 exporter 输出匹配：26 个全部命中至少一条序列，关键值与产物一致（故障丢包 0.5897、各档 p99、代理三类计数 9,552 / 2,861 / 2,352 分别对应 forwarded / dropped_flap / dropped_loss）。看板没沾死规则的病，原因在表达式形态：26 个目标全是单向量选择器，面板要对比两条序列时是把它们画在同一张图里，而不是在 PromQL 里互比。Grafana 本体本轮没有重跑（安装包 461 MB，未重复下载）；看板这一层的证据是表达式对 exporter 的对账，加上 2026-10-19 VERIFICATION.md 里 Grafana 13.2.4 活体渲染的留档记录，时效边界在此明说。

## 4. 分析与取舍

这个缺陷为什么能活过一次端到端验证？三层原因。第一，promtool check 只管语法：死表达式语法完全合法，编译毫无障碍，静态层给的是 SUCCESS。第二，活体观察时「没响」被成组解释了：当时记录给三条 inactive 写了数据理由，抖动份额那条被默认归进同一组「正确」，没有逐条对账。第三，也是最要命的一层，R0 上抖动这个故事看起来并不缺告警——NalLinkFlapDetected（info）响了，抖动被检出这件事有了交代，份额比较那条再哑，也没有在页面上留下一个显眼的空缺。缺席的告警不会自己举手，这正是它危险的地方。

由此得到的做法主张只有一条，但值得写进任何告警仓库的流程里：每条规则必须配三个用例——意图成立且触发、意图不成立且静默、阈值等值且静默——用 promtool test rules 在改规则时跑一遍。一条从没在任何测试里响过的规则，和一条死规则在外观上没有区别；本轮两条死规则的共同点不是写错了比较符，而是从写下到验证通过，没有任何一个环节要求它们响一次给我看。成本一侧：本篇这套测试（promtool 文件加夹具脚本）是一次性搭建，之后每次改规则的回归是秒级；收益是把「响不了」从运行期发现提前到提交期发现。证据等级：病根与修法都有真引擎实证（A）；「逐条对账能防住这类问题」是从这一个案例外推的工程主张（B）。

阈值那头有一个我选择不动的东西：基线 p99 的 50 ms。R0 的 sustained p99 是 120.452 ms，R1 是 6.952 ms，同代码同主机两次运行横跨门槛两侧，抖动来自宿主机调度，这点在 10-19 的验证记录里已经写明、且当时明确没有事后回调门槛去藏它。我同意保留：这条 warning 的注释第一句就把矛头指向宿主机调度而不是链路故障，读法是对的；一个实验台的告警如果为了让页面干净而追着抖动改门槛，它就不再是测量工具了。但这也意味着这条规则在当前主机上的信噪比先天有限——它响的时候，先查宿主机，别查网络。

还有一条只算推理、不算实测的盲点，标在这里供修规则时一并处理：NalExporterResultsMissing 依赖 exporter 自己吐出的 present 系列，exporter 进程活着但产物缺失时它能响（夹具已验）；可 exporter 进程若整个死了，它的输入系列随之消失，按即时向量语义规则同样算不出结果——防盲的告警对「 exporter 之死」本身是盲的。常规解法是另配一条基于抓取层 up 或 absent() 的规则，本文件里没有。本轮没有为它单独起一轮活体（杀 exporter 再等 for: 的成本不高，但它验证的是 PromQL 通用语义而非本链路特性），按推理记账，不冒充实测。

最后说取舍的另一面：修法为什么选比值式而不是只加 ignoring？抖动那条只加 ignoring(cause) 就够了，改动最小；吞吐那条我没有采用「在原比较式上加 ignoring(kind)」的写法，而是改成比值式 echo / ignoring(kind) send 小于 0.5——它与规则注释里「回显不足发送一半」是同一个意思，读起来也更直接，且是本轮实际验过的形态（另一种写法未在本轮测试范围内，不做语法断言）。比值式有个实测到的副作用：触发时告警标签会丢掉 kind（结果只剩 scenario 与 mode），我接受，因为实例定位靠 scenario 已经足够。两条修法都已在补丁副本上过 promtool 全周期测试，但仓库原文件保持未动：这篇是审计报告，不是顺手改人家告警配置的授权书，何况这个实验台还是求职证明物，改动留给仓库主人（也是我，但在另一个身份下）走正常提交流程。

## 5. 局限与未解问题

- 实验台是回环环境，指标描述的是已完成运行的快照，不是活网络的连续状态；这里测的是告警链路的表达式语义、时间语义与对账关系，结论不能搬去评价任何真实网络的告警质量。
- for: 在本链路里量的是「这份坏数据被连续抓取观察了多久」，不是「网络条件持续了多久」，规则文件头注释对此有明确声明；把这套规则接到流式 exporter 上时，for: 的含义会变，阈值与时长都要重估。
- Grafana 本轮未重跑（见 3.5），看板结论的证据构成是表达式对账加五天前的活体留档；若有人要求全链路同日证据，需要再下载 Grafana 本体补一轮。
- promtool 正对照里，NalBaselineP99LatencyHigh 的注释含 $value 模板，逐字断言成本高，本轮它的触发证据来自活体 API 而非 promtool；其余正对照（抖动、陈旧、畸形包）都做了标签与注释逐字断言。
- 离线 PromQL 求值器是我为夹具轨写的，只覆盖本文件出现的表达式形态；凡与真引擎结果冲突处，以 promtool 与活体为准——本轮两者在全部用例上一致。
- 未解问题：NalFaultLossAboveInjectionBand 的 0.75 上界来自注入参数的粗算（双向各 20% 随机丢弃叠加 0.6/2.5 的抖动占空比，量级 50% 至 65%），本轮只验了它的等值边界，没有构造「注入之外另有丢包」的场景去验这条上界告警的实际判别力；另外 up/absent 型防盲规则该怎么配、配上之后与现有 10 条如何分工，留待合入修复时一并处理。

## 6. 参考与出处

1. Prometheus 官方文档，Querying / Operators，「Vector matching」节：一对一匹配要求两侧条目标签集完全相同，ignoring / on 可改匹配口径，并给出不加 ignoring 则无任何匹配的例子。https://prometheus.io/docs/prometheus/latest/querying/operators/
2. Prometheus 官方文档，Configuration / Alerting rules：for: 的 pending 与 firing 语义；无 keep_firing_for 时，条件第一次不成立的评估即解除。https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
3. Prometheus 官方文档，Configuration / Unit testing for rules：promtool test rules 的测试文件格式与断言方式。https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/
4. 被测代码（本机仓库 net-assurance-lab）：monitoring/rules/alerts.yml（10 条规则原文）、monitoring/prometheus.yml（alertmanagers 空列表、抓取与评估间隔）、src/prom_exporter.py（collect 的指标构造）、VERIFICATION.md 监控补遗（2026-10-19 活体记录：2 条 firing 与 26 个面板目标全数返回序列）。
5. 本轮实验数据（与本系列前作同例，归档于本项目 data/，并随中文版同步至 tech-deep-dives 仓的 data/）：2026-10-24-alert-chain-bench.py / .json（意图轨与夹具轨）、2026-10-24-alert-chain-live.json（活体查询与四次告警快照）、2026-10-24-promtool-test.yml（原版规则测试）、2026-10-24-alerts-patched.yml 与 2026-10-24-promtool-test-patched.yml（修复副本与期望触发测试）。Prometheus 二进制为官方发布 3.15.0，下载后 gzip 校验通过，未随仓分发。

---

作者：Guangyi Zhao。本文的实验设计、代码与数据均为 clean-room 自有产出：被测实验台、exporter、夹具与求值器皆为本人手写，实验只在本机回环与本地文件上运行，不涉及任何客户信息与第三方系统。
