"""脚本化自查器（2026-10-22 对照实验用，规则在送审前冻结）。
定位：作者自查时挂的数字提取/对账脚本 + 词法清单。只做确定性检查：
  R1 合计复算：句内「a、b、c … 合计/总体积为 N」时验 sum(前项)==N
  R2 百分比复算：「X 中有 Y（P%）」「从 A 降到 B，下降了 P%」两类模板
  R3 公式复算：同段出现 precision/recall/F1 时按 2PR/(P+R) 复算 F1
  R4 均值复算：「分别为 v1、v2、v3，平均 M」算术均值；命中率加权均值模板
  R5 同指标多值对账：带指称锚点的指标（吞吐/数据集条数/LCP/重试）在全文出现
     两个不同值即报不一致（列出全部值，不判哪处错）
  R6 绝对词清单：逐句标出绝对化措辞（词法层命中，是否成立仍需人判）
  R7 归因句标记：标出「完全由/完全来自 … 没有贡献/没有影响」句（仅待复核标记）
  R8 出处句标记：标出「引用 + 因此/保证/必然」同句（仅待复核标记）
输出 JSON：每条 flag 含规则、原文句、脚本验算细节。脚本不做任何语义裁决：
R1–R5 的 flag 带验算结果（可直接判对错），R6–R8 只是定位标记。
"""
import json, os, re, sys

BASE = os.path.expanduser("~/workspace/your_files/顶刊技术文章")

def num(s):
    return float(s.replace(",", "").replace("，", ""))

def extract_bodies(path):
    txt = open(path, encoding="utf-8").read()
    bodies = {}
    for tag in ["A", "B", "C"]:
        m = re.search(rf"探针 {tag} 正文.*?====================\n(.*?)\n\n====================", txt, re.S)
        bodies[tag] = m.group(1).strip()
    return bodies

def sentences(text):
    parts = re.split(r"(?<=[。；])", text)
    return [p.strip() for p in parts if p.strip()]

FLAGS = []
def flag(probe, rule, sent, detail, tier):
    FLAGS.append(dict(probe=probe, rule=rule, tier=tier, sentence=sent, detail=detail))

ABS_WORDS = ["彻底", "在任何", "完全一致", "所有浏览器", "不存在任何",
             "零兼容性", "同样公平", "都不会再", "没有任何副作用"]

def check(probe, text):
    sents = sentences(text)
    # R1 合计复算
    for s in sents:
        if ("合计" in s) or ("总体积为" in s):
            vals = [num(x) for x in re.findall(r"(\d[\d,]*(?:\.\d+)?)", s)]
            if len(vals) >= 3:
                body, total = vals[:-1], vals[-1]
                if abs(sum(body) - total) > 0.51:
                    flag(probe, "R1-sum", s, f"分项和={sum(body):g}，文中合计={total:g}", "verdict")
    # R2a 占比：X 次/条中，有 Y 次（P%）
    for s in sents:
        m = re.search(r"(\d[\d,]*)\s*(?:次|条)[^。]*?有\s*(\d[\d,]*)\s*次[^。]*?（(\d+(?:\.\d+)?)%）", s)
        if m:
            x, y, p = num(m.group(1)), num(m.group(2)), num(m.group(3))
            real = y / x * 100
            if abs(real - p) > 0.6:
                flag(probe, "R2-pct", s, f"{y:g}/{x:g}={real:.1f}%，文中写 {p:g}%", "verdict")
        # R2b 降幅：从 A 降到 B，下降了 P%
        m = re.search(r"从\s*(\d[\d,]*)\s*(?:KB|ms|s)?\s*降到\s*(\d[\d,]*)\s*(?:KB|ms|s)?，下降了\s*(\d+(?:\.\d+)?)%", s)
        if m:
            a, b, p = num(m.group(1)), num(m.group(2)), num(m.group(3))
            real = (a - b) / a * 100
            if abs(real - p) > 0.6:
                flag(probe, "R2-pct", s, f"({a:g}-{b:g})/{a:g}={real:.1f}%，文中写 {p:g}%", "verdict")
    # R3 F1 复算（全文级：抓 precision/recall/F1 三值）
    mp = re.search(r"precision[^。\d]*(\d+(?:\.\d+)?)", text)
    mr = re.search(r"recall[^。\d]*(\d+(?:\.\d+)?)", text)
    mf = re.search(r"F1[^。\d]*(\d+(?:\.\d+)?)", text)
    if mp and mr and mf:
        p, r, f1 = float(mp.group(1)), float(mr.group(1)), float(mf.group(1))
        real = 2 * p * r / (p + r)
        if abs(real - f1) > 0.011:
            flag(probe, "R3-f1", "precision/recall/F1 同段", f"2*{p}*{r}/({p}+{r})={real:.3f}，文中 F1={f1}", "verdict")
    # R4a 算术均值：分别为 v1、v2、v3，平均 M
    for s in sents:
        m = re.search(r"分别为\s*((?:\d+(?:\.\d+)?\s*s?[、,，]\s*)+\d+(?:\.\d+)?)\s*s?，平均\s*(\d+(?:\.\d+)?)", s)
        if m:
            vals = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(1))]
            claim = float(m.group(2))
            real = sum(vals) / len(vals)
            if abs(real - claim) > 0.051:
                flag(probe, "R4-avg", s, f"均值={real:.2f}，文中写 {claim:g}", "verdict")
        # R4b 命中率加权均值：命中率 H%：命中时 X，未命中时 Y，平均 Z
        m = re.search(r"命中率为\s*(\d+(?:\.\d+)?)%：命中时[^。\d]*(\d+(?:\.\d+)?)\s*ms，未命中时[^。\d]*(\d+(?:\.\d+)?)\s*ms，因此平均[^。\d]*(\d+(?:\.\d+)?)\s*ms", s)
        if m:
            h, x, y, z = (float(m.group(i)) for i in range(1, 5))
            real = h / 100 * x + (1 - h / 100) * y
            if abs(real - z) > 0.11:
                flag(probe, "R4-weighted", s, f"加权均值={real:.1f} ms，文中写 {z:g} ms", "verdict")
    # R5 同指标多值对账
    def multi(rule, values, label):
        uniq = sorted(set(values))
        if len(uniq) > 1:
            flag(probe, "R5-xref", label, f"{rule} 出现多个不同值：{uniq}", "verdict")
    multi("吞吐", [num(x) for x in re.findall(r"吞吐(?:达到|为)\s*(\d[\d,]*)\s*次/秒", text)], "指标：吞吐")
    multi("数据集条数", [num(x) for x in re.findall(r"(?:数据集共|全部)\s*(\d[\d,]*)\s*条", text)], "指标：数据集条数")
    multi("LCP", [float(x) for x in re.findall(r"LCP[^。\d]{0,6}?(\d+(?:\.\d+)?)\s*s", text)], "指标：LCP")
    retries = ([0.0] if "零重试" in text else []) + [num(x) for x in re.findall(r"(\d[\d,]*)\s*次[^。]{0,4}重试", text)]
    multi("重试次数", retries, "指标：重试次数")
    # R6 绝对词
    for s in sents:
        hits = [w for w in ABS_WORDS if w in s]
        if hits:
            flag(probe, "R6-absolute", s, f"绝对化措辞：{hits}", "lexical")
    # R7 归因句标记
    for s in sents:
        if re.search(r"完全(由|来自)", s) and re.search(r"没有(任何)?(贡献|影响)", s):
            flag(probe, "R7-causal-flag", s, "单一归因句式：完全由/来自 X + 他因零贡献（脚本不能判证据是否足够）", "pointer")
    # R8 出处句标记
    for s in sents:
        if ("引用" in s) and re.search(r"因此|保证|必然", s):
            flag(probe, "R8-source-flag", s, "引用与强结论同句（脚本不能判出处是否支撑）", "pointer")

def main():
    bodies = extract_bodies(os.path.join(BASE, "data", "2026-10-22-probes.txt"))
    for tag, body in bodies.items():
        check(tag, body)
    out = dict(n_flags=len(FLAGS), flags=FLAGS)
    dest = os.path.join(BASE, "data", "2026-10-22-selfcheck-result.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
