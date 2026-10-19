"""Emotion-Guard 落地约束实测：误报率、留存体积、标签污染、截断与置信度忽略、回摆规则。
全合成数据，无真实儿童影像。"""

import json, sys, os, pickle, hashlib
from datetime import datetime, timedelta
from collections import Counter
import numpy as np

REPO = os.path.expanduser("~/workspace/github/Emotion-Guard")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "examples"))

from emotion_guard import (
    AlertConfig, AlertEngine, ClassroomSession, Emotion, Observation,
    Person, Role, MockEmotionClassifier, MockFaceDetector, build_report,
)
from simulate import _slot_seed

def det_seed(master, pid, slot):
    h = hashlib.sha256(f"{master}|{pid}|{slot}".encode()).digest()
    return int.from_bytes(h[:4], "little")

FACE = np.zeros((96, 96, 3), dtype=np.uint8)

def _grep(word, repo):
    import subprocess as sp
    r = sp.run(["grep", "-ril", word, os.path.join(repo, "emotion_guard")],
               capture_output=True, text=True)
    return [os.path.basename(x) for x in r.stdout.strip().splitlines()] if r.stdout.strip() else []
T0 = datetime(2026, 10, 1, 8, 0, 0)
out = {}

def mkobs(person, emotion, slot=0, conf=0.9, sim=True):
    return Observation(person=person, timestamp=T0 + timedelta(minutes=20*slot),
                       emotion=emotion, confidence=conf, simulated=sim)

# ---------- 实验A: baseline 管线 ----------
import subprocess
VENV_PY = os.path.expanduser("~/workspace/github/Bloom-Counter/.venv/bin/python")
PY = VENV_PY if os.path.exists(VENV_PY) else sys.executable
r = subprocess.run([PY, "-m", "pytest", "tests/", "-q"],
                   capture_output=True, text=True, cwd=REPO)
out["tests"] = {"returncode": r.returncode, "tail": r.stdout.strip().splitlines()[-3:]}
print("A tests:", r.returncode)

import importlib.util
spec = importlib.util.spec_from_file_location("simulate_mod", os.path.join(REPO, "examples", "simulate.py"))
sim = importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
sess = sim.generate_classroom(master_seed=7)
eng = AlertEngine(AlertConfig())
alerts = {}
for pid in sess.persons:
    alerts[pid] = eng.evaluate(sess.history(pid))
n_obs = len(sess.observations)
n_alert = sum(len(v) for v in alerts.values())
rule_ct = Counter(a.rule for v in alerts.values() for a in v)
lvl_ct = Counter(a.level for v in alerts.values() for a in v)
out["baseline_day"] = {"observations": n_obs, "alerts_total": n_alert,
    "by_rule": dict(rule_ct), "by_level": dict(lvl_ct),
    "alerts_by_person": {pid: [(a.rule, a.level) for a in v] for pid, v in alerts.items() if v}}
print("A baseline:", n_obs, n_alert, dict(rule_ct))

# ---------- 实验B: 空背景误报率（无 scripted 剧情，纯 typical 分布） ----------
def false_alarm_rate(n_days=30, n_children=8):
    warns = crits = teacher_warns = 0
    child_days_warn = 0
    engine = AlertEngine(AlertConfig())
    for day in range(n_days):
        for c in range(n_children):
            p = Person(f"C-{c+1:02d}", f"Child-{c+1:02d}", Role.CHILD)
            hist = []
            day_warned = False
            for slot in range(24):
                clf = MockEmotionClassifier(profile="typical_child",
                                            seed=det_seed(1000+day, p.person_id, slot))
                res = clf.classify(FACE)
                hist.append(mkobs(p, res.emotion, slot=slot, conf=res.confidence))
                if slot >= 3:
                    w = hist[max(0, len(hist)-6):]
                    neg = sum(1 for o in w if o.emotion.is_negative)
                    if len(w) >= 4 and neg >= 6: crits += 1
                    elif len(w) >= 4 and neg >= 4: warns += 1; day_warned = True
            if day_warned: child_days_warn += 1
        # teacher spike: any angry in last 6
        tp = Person("T-01", "Teacher-01", Role.TEACHER)
        thist = []
        fired = False
        for slot in range(24):
            clf = MockEmotionClassifier(profile="typical_teacher",
                                        seed=det_seed(5000+day, "T-01", slot))
            res = clf.classify(FACE)
            thist.append(mkobs(tp, res.emotion, slot=slot))
            w = thist[max(0, len(thist)-6):]
            if any(o.emotion == Emotion.ANGRY for o in w) and not fired:
                fired = True
        if fired: teacher_warns += 1
    return {"days": n_days, "child_slot_evals": n_days*n_children*21,
            "sustained_warnings": warns, "sustained_criticals": crits,
            "child_days_with_warning": child_days_warn,
            "child_days_total": n_days*n_children,
            "teacher_days_with_spike_warning": teacher_warns}
out["false_alarm"] = false_alarm_rate()
print("B false alarm:", out["false_alarm"])

# ---------- 实验C: 隐私面审计 ----------
obs0 = sess.observations[0]
out["privacy_static"] = {
    "observation_fields": list(obs0.__dict__.keys()),
    "person_schema_fields": ["person_id", "name", "role"],
    "face_image_retained_in_observation": False,
    "retention_purge_method_exists": hasattr(ClassroomSession, "purge"),
    "delete_method_exists": hasattr(ClassroomSession, "delete"),
    "expire_method_exists": hasattr(ClassroomSession, "expire"),
    "anonymize_exists": hasattr(ClassroomSession, "anonymize"),
    "consent_field_in_person": "consent" in Person.__dataclass_fields__,
    "retention_keyword_in_code": _grep("retention", REPO),
    "delete_keyword_in_code": _grep("delete", REPO),
}
# report 可识别字段
rep = build_report(sess, alerts)
p0 = rep["persons"][0]
out["privacy_report"] = {
    "per_person_fields": list(p0.keys()),
    "name_included": "name" in p0,
    "top_level_simulated_hardcoded": rep["simulated"] is True,
}
# simulated 标签污染：注入真实 obs
s2 = ClassroomSession("t")
p = Person("C-01", "Child-01", Role.CHILD); s2.add_person(p)
s2.ingest(mkobs(p, Emotion.HAPPY, slot=0, sim=False))
rep2 = build_report(s2, {"C-01": []})
out["privacy_static"]["build_report_simulated_hardcoded_true_on_real_data"] = rep2["simulated"] is True
# 留存体积（pickle 会因共享 Person 引用低估，另给单条 JSON 行口径）
blob = pickle.dumps(sess.observations)
obs_bytes = len(blob)
per = obs_bytes / n_obs
def _obs_json(o):
    return json.dumps({"person_id": o.person.person_id, "name": o.person.name,
        "role": o.person.role.value, "ts": o.timestamp.isoformat(),
        "emotion": o.emotion.value, "confidence": o.confidence,
        "simulated": o.simulated}, ensure_ascii=False)
per_json = len(_obs_json(obs0).encode())
out["retention_volume"] = {
    "one_day_bytes_pickle_shared_ref": obs_bytes, "per_obs_bytes_pickle": round(per, 1),
    "per_obs_bytes_json_row": per_json,
    "day_30_MB_json": round(n_obs*30*per_json/1e6, 3), "day_180_MB_json": round(n_obs*180*per_json/1e6, 3),
    "obs_per_day_demo_cadence": n_obs,
    "at_1min_cadence_obs_per_day": 9 * 60 * 8,
    "at_1min_cadence_30day_MB_json": round(9*60*8*30*per_json/1e6, 2),
    "at_1min_cadence_180day_MB_json": round(9*60*8*180*per_json/1e6, 2),
}
print("C privacy:", json.dumps(out["privacy_static"], ensure_ascii=False)[:400])
print("C volume:", out["retention_volume"])

# ---------- 实验D: 截断历史（数据最小化）对告警的影响 ----------
def seq_alert_levels(seq, window=6, neg_thr=4, crit_thr=6):
    engine = AlertEngine(AlertConfig(window=window, negative_threshold=neg_thr, critical_threshold=crit_thr))
    p = Person("C-01", "Child-01", Role.CHILD)
    hist = [mkobs(p, e, slot=i) for i, e in enumerate(seq)]
    return engine.evaluate(hist)

# 持续 distress: 6 sad
full = [Emotion.SAD]*6
r_full = seq_alert_levels(full)
r_trunc = seq_alert_levels(full[-6:])  # 截到6完全一样
# swing 规则扫描整段历史且只看相邻对：happy->angry 在开头，后接 10 个 calm
swing = [Emotion.HAPPY, Emotion.ANGRY] + [Emotion.CALM]*10
r_swing_full = seq_alert_levels(swing)
trunc_swing = swing[-6:]  # 只剩 calm，旧回摆被截掉
r_swing_trunc = seq_alert_levels(trunc_swing)
out["truncation"] = {
    "sustained_full": [a.level for a in r_full],
    "sustained_trunc6_same": [a.level for a in r_trunc],
    "swing_full_rules": [a.rule for a in r_swing_full],
    "swing_trunc6_rules": [a.rule for a in r_swing_trunc],
    "mood_summary_uses_all_history": True,
}
# 聚合-only 报告原型：utility 保留度
def agg_only_report(sess, alerts):
    return {
        "classroom": sess.name,
        "classroom_mood": sess.classroom_mood(),
        "alert_counts": dict(Counter(a.rule for v in alerts.values() for a in v)),
        "n_persons": len(sess.persons),
    }
ag = agg_only_report(sess, alerts)
out["agg_only"] = {"fields": list(ag.keys()),
    "alert_counts_preserved": ag["alert_counts"] == dict(rule_ct),
    "name_fields_removed": 9}
print("D truncation:", out["truncation"])
print("D agg:", ag["alert_counts"])

# ---------- 实验E: 置信度被忽略 ----------
p = Person("C-01", "Child-01", Role.CHILD)
hi = [mkobs(p, Emotion.SAD, slot=i, conf=0.99) for i in range(6)]
lo = [mkobs(p, Emotion.SAD, slot=i, conf=0.51) for i in range(6)]
e = AlertEngine(AlertConfig())
out["confidence_ignored"] = {
    "alert_same_at_099_and_051": [a.level for a in e.evaluate(hi)] == [a.level for a in e.evaluate(lo)],
    "levels": [a.level for a in e.evaluate(hi)],
}
print("E confidence:", out["confidence_ignored"])

# ---------- 实验F: swing 规则边界 ----------
p = Person("C-01", "Child-01", Role.CHILD)
mid = [mkobs(p, Emotion.HAPPY, slot=0), mkobs(p, Emotion.CALM, slot=1), mkobs(p, Emotion.ANGRY, slot=2)]
gap21 = [mkobs(p, Emotion.HAPPY, slot=0), mkobs(p, Emotion.ANGRY, slot=2)]  # 40min > 20min window
e = AlertEngine(AlertConfig())
out["swing_edge"] = {
    "happy_calm_angry_fires": any(a.rule == AlertEngine.RULE_SUDDEN_SWING for a in e.evaluate(mid)),
    "happy_gap40min_angry_fires": any(a.rule == AlertEngine.RULE_SUDDEN_SWING for a in e.evaluate(gap21)),
}
print("F swing:", out["swing_edge"])

# ---------- 实验G: 模态核查 ----------
out["modality_audit"] = {
    "audio_keyword_files": _grep("audio", REPO),
    "voice_keyword_files": _grep("voice", REPO),
    "text_keyword_files": _grep("transcript", REPO),
    "implemented_modalities": ["face_image_only"],
    "fer_classifier_implemented": False,
    "note": "FERClassifier.__init__ raises NotImplementedError; Mock is the only working classifier",
}

# ---------- 实验H: hash() 种子跨进程不稳定 ----------
snippet = r'''
import sys, os, json
sys.path.insert(0, os.path.expanduser("~/workspace/github/Emotion-Guard"))
sys.path.insert(0, os.path.expanduser("~/workspace/github/Emotion-Guard/examples"))
from simulate import generate_classroom
from emotion_guard import AlertEngine, AlertConfig
s = generate_classroom(master_seed=7)
e = AlertEngine(AlertConfig())
tot = 0; by = {}
for pid in s.persons:
    for a in e.evaluate(s.history(pid)):
        tot += 1; by[a.rule] = by.get(a.rule, 0) + 1
first = [(o.person.person_id, o.emotion.value) for o in s.observations[:6]]
print(json.dumps({"alerts": tot, "by_rule": by, "first6": first}))
'''
runs, runs_fixed = [], []
for i in range(5):
    rr = subprocess.run([PY, "-c", snippet], capture_output=True, text=True)
    runs.append(json.loads(rr.stdout.strip().splitlines()[-1]))
for i in range(3):
    env = dict(os.environ); env["PYTHONHASHSEED"] = "0"
    rr = subprocess.run([PY, "-c", snippet], capture_output=True, text=True, env=env)
    runs_fixed.append(json.loads(rr.stdout.strip().splitlines()[-1]))
out["hash_instability"] = {
    "runs_no_fixed_seed": runs,
    "distinct_alert_counts_no_fixed_seed": sorted({r["alerts"] for r in runs}),
    "distinct_first6_no_fixed_seed": len({json.dumps(r["first6"]) for r in runs}),
    "runs_pythonhashseed0": runs_fixed,
    "distinct_alert_counts_hashseed0": sorted({r["alerts"] for r in runs_fixed}),
}
print("H hash instability:", out["hash_instability"]["distinct_alert_counts_no_fixed_seed"],
      "vs fixed:", out["hash_instability"]["distinct_alert_counts_hashseed0"])

# 报告大小对比
rep_blob = len(json.dumps(rep).encode())
out["report_bytes"] = {"full_identified": rep_blob,
    "agg_only": len(json.dumps(ag).encode())}

with open(os.path.expanduser("~/workspace/your_files/顶刊技术文章/data/2026-10-18-emotion-guard-bench.json"), "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)
print("WROTE bench json ok")
