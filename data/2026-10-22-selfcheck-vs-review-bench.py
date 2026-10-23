"""脚本化自查 vs 异模型审稿对照实验（2026-10-22）：评分编码与汇总。
探针：data/2026-10-22-probes.txt（3 篇、24 处植入缺陷，答案钥匙在文末）。
脚本臂：data/2026-10-22-selfcheck.py（规则送审前冻结），原始输出
  data/2026-10-22-selfcheck-result.json（21 条 flag）。
审稿臂：Gemini（gemini-flash-latest，付费档 standard）逐篇独立审稿，
  原始回执 review/2026-10-22-probe{A,B,C}-gemini-raw.json。
评分（与 2026-10-19 篇同一口径，作者编码、无第二编码员，边界条目在文中披露）：
  HIT  = 明确指出缺陷核心矛盾（脚本臂须给验算/对账结果或逐词摘出绝对措辞；
         审稿臂须点中核心矛盾）；
  FLAG = 只定位到相关句/数值堆，未给出核心矛盾的判定；
  MISS = 未提及。
本脚本只做计数，编码依据逐条写在 OUTCOMES 的 note 里，可对照原始材料复核。
"""
import json, os
from collections import Counter

BASE = os.path.expanduser("~/workspace/your_files/顶刊技术文章")

# id: (类别, 脚本臂, 审稿臂, 编码依据)
OUTCOMES = {
 "A1": ("numeric", "HIT", "HIT", "脚本 R1 验算 34!=31；Gemini 第1条同验算"),
 "A2": ("numeric", "HIT", "HIT", "脚本 R2 验算 76.7%；Gemini 第2条同验算"),
 "A3": ("xref", "HIT", "HIT", "脚本 R5 对账 3200/3800；Gemini 第4条并列两值"),
 "A4": ("absolute", "HIT", "HIT", "脚本 R6 逐词摘出彻底/在任何/都不会再；Gemini 第8条同摘"),
 "A5": ("causal", "FLAG", "HIT", "脚本 R7 只标句式不能判证据；Gemini 第7条指出无对照不能断言零贡献"),
 "A6": ("source", "FLAG", "HIT", "脚本 R8 只标引用+因此同句；Gemini 第6条指出引文上限50与结论200相反"),
 "A7": ("contradiction", "HIT", "HIT", "脚本 R5 对账重试 0/17（矛盾恰为数值形态）；Gemini 第5条并列两句"),
 "A8": ("numeric", "HIT", "HIT", "脚本 R4 加权验算 5.8ms；Gemini 第3条同验算"),
 "B1": ("numeric", "HIT", "FLAG", "脚本 R1 验算四格和 1900!=1850；Gemini 第1条只把文中现成总数 5000/1850/4200 互比，未重算四格之和、且把 1850 当作矩阵总和引用"),
 "B2": ("numeric", "HIT", "HIT", "脚本 R3 复算 F1=0.856；Gemini 第2条同复算"),
 "B3": ("xref", "HIT", "HIT", "脚本 R5 对账 5000/4200；Gemini 第1条并列三值判不一致"),
 "B4": ("absolute", "HIT", "HIT", "脚本 R6 逐词摘出；Gemini 第5条指出无分层公平证据"),
 "B5": ("causal", "FLAG", "HIT", "脚本 R7 只标句式；Gemini 第3条指出双变量同改无消融"),
 "B6": ("source", "FLAG", "HIT", "脚本 R8 只标句式；Gemini 第4条指出跨语言跨域不可保证"),
 "B7": ("contradiction", "MISS", "HIT", "脚本无语义矛盾规则；Gemini 第6条并列两句并指出数据泄露"),
 "B8": ("scope", "MISS", "HIT", "脚本无范围规则；Gemini 第7条指出未测时延并发不能下上线结论"),
 "C1": ("numeric", "HIT", "HIT", "脚本 R1 验算 480!=450；Gemini 第1条同验算"),
 "C2": ("numeric", "HIT", "HIT", "脚本 R2 验算 50.0%；Gemini 第2条同验算"),
 "C3": ("xref", "FLAG", "HIT", "脚本 R5 值集 [1.5,1.8,2.1] 混入复测组首值、未隔离指称对；Gemini 第5条并列三值判同一构建不一致"),
 "C4": ("absolute", "HIT", "HIT", "脚本 R6 逐词摘出；Gemini 第8条同摘并指出无全矩阵测试"),
 "C5": ("causal", "FLAG", "HIT", "脚本 R7 只标句式；Gemini 第6条指出 CDN 与 LCP 构成相关、无对照不能断言零贡献"),
 "C6": ("source", "FLAG", "HIT", "脚本 R8 只标句式；Gemini 第7条指出实验室数据与 RUM p95 无固定线性关系"),
 "C7": ("contradiction", "MISS", "HIT", "脚本无语义矛盾规则；Gemini 第3条并列两句判直接矛盾"),
 "C8": ("numeric", "HIT", "HIT", "脚本 R4 验算均值 2.40；Gemini 第4条同验算"),
}

def tally(arm_idx):
    c = Counter(v[arm_idx] for v in OUTCOMES.values())
    return dict(c)

def by_class(arm_idx):
    out = {}
    for cls in sorted(set(v[0] for v in OUTCOMES.values())):
        items = [v for v in OUTCOMES.values() if v[0] == cls]
        out[cls] = dict(n=len(items), **Counter(v[arm_idx] for v in items))
    return out

script_t, gemini_t = tally(1), tally(2)
union_hit = [k for k, v in OUTCOMES.items() if "HIT" in (v[1], v[2])]
both_hit = [k for k, v in OUTCOMES.items() if v[1] == v[2] == "HIT"]
script_only = [k for k, v in OUTCOMES.items() if v[1] == "HIT" and v[2] != "HIT"]
gemini_only = [k for k, v in OUTCOMES.items() if v[2] == "HIT" and v[1] != "HIT"]

result = {
 "planted": len(OUTCOMES),
 "script": dict(tally=script_t, by_class=by_class(1),
                n_flags=21, false_positives=0,
                note="21 条 flag 全部落在植入缺陷句上；C3 的值集混入一个合法测量值，计入该条 FLAG 而非误报"),
 "gemini": dict(tally=gemini_t, by_class=by_class(2),
                model="gemini-flash-latest", serviceTier="standard",
                usage={"prompt": 367 + 336 + 302, "candidates": 919 + 1275 + 1047},
                extra_valid_findings=[
                  "B 篇：由混淆矩阵复算 recall=820/930=0.882，与文中 0.80 不符（未植入、复核成立）",
                  "C 篇：分包后总体积文中另有 450 与 410 两值冲突（未植入、C1/C2 植入数字的二阶后果，复核成立）"],
                false_positives=0),
 "union_hit": len(union_hit), "both_hit": len(both_hit),
 "script_only_hit": script_only, "gemini_only_hit": gemini_only,
 "outcomes": {k: dict(cls=v[0], script=v[1], gemini=v[2], note=v[3]) for k, v in OUTCOMES.items()},
}
dest = os.path.join(BASE, "data", "2026-10-22-selfcheck-vs-review-bench.json")
json.dump(result, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(result, ensure_ascii=False, indent=1))
