"""多模型交叉审实测：数据集 A = 本线 2026-10-13 至 10-18 七篇文章的审稿记录逐条编码；
实验 B 的探针文本见 data/2026-10-19-probe.txt，Gemini 探针结果由运行者另存 JSON 后并入。
编码口径：每条意见的类别与处置直接抄自 review/*.md 原文归纳，脚本只做计数，不做判断。
类别：numeric 数字/口径、logic 因果/概念、overclaim 夸大/泛化、scope 范围限定、
      method 方法交代、structure 结构/交叉引用、style 文风。
处置：changed 改文（含补表/补实验呈现）、recheck 复核后原文成立不改、
      rejected 审稿方误报驳回、covered 已由他处覆盖、kept 作者保留原样。
"""
import json, os
from collections import Counter

BASE = os.path.expanduser("~/workspace/your_files/顶刊技术文章")

# 每篇：calls = 按时间序的 Gemini 调用结果；opinions = (类别, 处置)
ARTICLES = [
 dict(id="rea", date="2026-10-13", mode="gemini",
      calls=["503", "ok"],
      opinions=[("logic","changed"),("overclaim","changed"),("logic","changed"),
                ("method","changed"),("overclaim","changed"),("scope","changed"),
                ("scope","changed"),("style","kept")]),
 dict(id="go-diagnoser", date="2026-10-13", mode="human-fallback",
      calls=["429"],
      opinions=[("overclaim","changed"),("method","changed"),("numeric","recheck"),
                ("scope","recheck"),("style","recheck")]),
 dict(id="sentinel", date="2026-10-14", mode="gemini-delayed",
      calls=["ok"],
      opinions=[("structure","changed"),("logic","changed"),("method","changed"),
                ("overclaim","changed"),("numeric","rejected")]),
 dict(id="vuln-scanner", date="2026-10-15", mode="gemini",
      calls=["503", "503", "ok-alt-model"],
      opinions=[("numeric","changed"),("numeric","changed"),("structure","changed"),
                ("logic","changed"),("overclaim","changed")]),
 dict(id="wiper", date="2026-10-16", mode="gemini",
      calls=["ok"],
      opinions=[("method","recheck-changed"),("structure","changed"),("scope","changed")]),
 dict(id="bloom", date="2026-10-17", mode="gemini",
      calls=["ok"],
      opinions=[("numeric","changed"),("logic","changed"),("logic","changed"),
                ("overclaim","changed"),("overclaim","changed"),("method","changed"),
                ("method","changed"),("numeric","changed")]),
 dict(id="emotion-guard", date="2026-10-18", mode="human-fallback",
      calls=["503", "503", "503", "429"],
      opinions=[("numeric","changed"),("numeric","changed"),("method","changed"),
                ("numeric","recheck"),("scope","covered"),("numeric","recheck")]),
]

def is_ok(c): return c.startswith("ok")

out = {}
all_calls = [c for a in ARTICLES for c in a["calls"]]
out["calls"] = dict(total=len(all_calls), ok=sum(is_ok(c) for c in all_calls),
                    e503=sum(c == "503" for c in all_calls),
                    e429=sum(c == "429" for c in all_calls))
out["articles_total"] = len(ARTICLES)
out["articles_gemini_reviewed"] = sum(a["mode"].startswith("gemini") for a in ARTICLES)
out["articles_human_fallback"] = sum(a["mode"] == "human-fallback" for a in ARTICLES)
out["articles_same_day_gemini"] = sum(a["mode"] == "gemini" for a in ARTICLES)

gem_ops = [o for a in ARTICLES if a["mode"].startswith("gemini") for o in a["opinions"]]
hum_ops = [o for a in ARTICLES if a["mode"] == "human-fallback" for o in a["opinions"]]
out["opinions"] = dict(total=len(gem_ops) + len(hum_ops), gemini=len(gem_ops), human=len(hum_ops))
out["gemini_categories"] = dict(Counter(c for c, _ in gem_ops))
out["human_categories"] = dict(Counter(c for c, _ in hum_ops))
out["gemini_outcomes"] = dict(Counter(d for _, d in gem_ops))
out["human_outcomes"] = dict(Counter(d for _, d in hum_ops))
changed = lambda ops: sum(d.startswith("changed") or d == "recheck-changed" for _, d in ops)
out["changed"] = dict(gemini=changed(gem_ops), human=changed(hum_ops),
                      gemini_rate=round(changed(gem_ops) / len(gem_ops), 3),
                      human_rate=round(changed(hum_ops) / len(hum_ops), 3))
out["per_article"] = {a["id"]: dict(date=a["date"], mode=a["mode"], calls=a["calls"],
                                    n_opinions=len(a["opinions"])) for a in ARTICLES}

probe_path = os.path.join(BASE, "data", "2026-10-19-probe-result.json")
if os.path.exists(probe_path):
    out["probe"] = json.load(open(probe_path))

dest = os.path.join(BASE, "data", "2026-10-19-cross-review-bench.json")
json.dump(out, open(dest, "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
