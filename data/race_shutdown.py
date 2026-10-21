#!/usr/bin/env python3
import json, os, signal, subprocess, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
BASE="http://127.0.0.1:18099"
def req(method, path, body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(BASE+path, data=data, method=method, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp: return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, {}
    except Exception: return 0, {}
env=dict(os.environ, PORT="18099", WORKERS="4", QUEUE_SIZE="100")
p=subprocess.Popen(["/tmp/godiag-bench/server-race"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for _ in range(100):
    s,_=req("GET","/healthz")
    if s==200: break
    time.sleep(0.1)
# concurrent mixed load: submits + polls hammering the store
def work(i):
    s,j=req("POST","/api/v1/diagnose",{"target":f"race-{i}"})
    if s!=202: return s
    for _ in range(50):
        s2,j2=req("GET",f"/api/v1/jobs/{j['id']}")
        if s2==200 and j2.get("status")=="done": return 200
        time.sleep(0.005)
    return -1
with ThreadPoolExecutor(max_workers=20) as ex:
    res=list(ex.map(work, range(100)))
done=res.count(200)
# graceful shutdown with no jobs in flight
t0=time.time(); p.send_signal(signal.SIGTERM); out,_=p.communicate(timeout=30); shutdown_s=time.time()-t0
print(json.dumps({"race_load_jobs_ok":done,"race_load_total":len(res),
  "data_race_warnings": out.count("DATA RACE"), "shutdown_s":round(shutdown_s,2),
  "shutdown_log_tail":[l for l in out.splitlines() if "shutting" in l or "workers stopped" in l or "bye" in l]}, indent=1))
