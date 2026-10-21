#!/usr/bin/env python3
import json, os, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

SERVER = "/tmp/godiag-bench/server"
BASE = "http://127.0.0.1:18099"

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE+path, data=data, method=method,
                               headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}

def wait_done(jid, timeout=30):
    t0=time.time()
    while time.time()-t0 < timeout:
        s,j = req("GET", f"/api/v1/jobs/{jid}")
        if s==200 and j.get("status")=="done": return j, time.time()-t0
        if s==200 and j.get("status")=="failed": return j, time.time()-t0
        time.sleep(0.005)
    return None, time.time()-t0

def start_server(workers, queue):
    env = dict(os.environ, PORT="18099", WORKERS=str(workers), QUEUE_SIZE=str(queue))
    p = subprocess.Popen([SERVER], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(100):
        try:
            s,_j = req("GET","/healthz")
            if s==200: return p
        except Exception: pass
        time.sleep(0.1)
    raise RuntimeError("server did not start")

def stop_server(p):
    p.terminate()
    try: out,_ = p.communicate(timeout=20)
    except Exception: p.kill(); out,_ = p.communicate()
    return out or ""

def submit(body):
    return req("POST","/api/v1/diagnose",body)

def pct(vals, q):
    v=sorted(vals); return v[min(len(v)-1, int(len(v)*q))]

results={}

# --- A: fan-out, sequential, workers=4 ---
p=start_server(4,100)
try:
    for label, body in [("1check",{"target":"node-a","checks":["connectivity"]}),
                        ("3checks",{"target":"node-a"})]:
        e2e=[]; checklat=[]
        for _ in range(30):
            s,j=submit(body); assert s==202,(s,j)
            job,dt=wait_done(j["id"]); e2e.append(dt*1000)
            checklat += [r["latency_ms"] for r in job["results"]]
        results[f"A_{label}"]={"e2e_ms_mean":round(sum(e2e)/len(e2e),1),"e2e_ms_p50":round(pct(e2e,0.5),1),
            "e2e_ms_p95":round(pct(e2e,0.95),1),"check_latency_ms_mean":round(sum(checklat)/len(checklat),1),
            "n_jobs":len(e2e),"n_checks":len(checklat)}
finally:
    stop_server(p)

# --- B: throughput scaling, 60 concurrent jobs, 3 checks each ---
for w in (1,2,4,8):
    p=start_server(w,200)
    try:
        t0=time.time()
        with ThreadPoolExecutor(max_workers=20) as ex:
            subs=list(ex.map(lambda i: submit({"target":f"node-{i}"}), range(60)))
        codes=[s for s,_ in subs]; ids=[j["id"] for s,j in subs if s==202]
        with ThreadPoolExecutor(max_workers=20) as ex:
            list(ex.map(wait_done, ids))
        wall=time.time()-t0
        results[f"B_workers{w}"]={"wall_s":round(wall,2),"jobs":len(ids),"accepted_202":codes.count(202),
            "rejected_503":codes.count(503),"jobs_per_s":round(len(ids)/wall,1)}
    finally:
        stop_server(p)

# --- C: backpressure, workers=1 queue=5, burst 30 ---
p=start_server(1,5)
try:
    with ThreadPoolExecutor(max_workers=30) as ex:
        subs=list(ex.map(lambda i: submit({"target":f"burst-{i}"}), range(30)))
    codes=[s for s,_ in subs]
    results["C_backpressure"]={"burst":30,"accepted_202":codes.count(202),"rejected_503":codes.count(503),"other":len(codes)-codes.count(202)-codes.count(503)}
    # drained jobs must all complete (no silent loss among accepted)
    ids=[j["id"] for s,j in subs if s==202]; done=0
    for jid in ids:
        job,_=wait_done(jid)
        if job and job.get("status")=="done": done+=1
    results["C_backpressure"]["accepted_eventually_done"]=done
finally:
    stop_server(p)

print(json.dumps(results, indent=1))
