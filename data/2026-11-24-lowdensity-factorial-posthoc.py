import json, statistics as st
d=json.load(open('/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-24-lowdensity-factorial-bench.json'))
BAND=[0.30,0.28,0.25,0.22]
cells={}
out={"pools":{},"cells":{}}
for name,p in d['pools'].items():
    pts=p['pooled_points']
    band=[x for x in pts if x['s'] in BAND and x['err7'] is not None]
    health=[x for x in pts if x['s']>=0.35 and x['err7'] is not None]
    rec={"band_err_median":round(st.median([x['err7'] for x in band]),4),"band_err_max":max(x['err7'] for x in band),
         "band_div_median":round(st.median([abs(x['div']) for x in band if x['div'] is not None]),4),
         "band_n_bad":sum(x['bad'] for x in band),
         "band_bad_divs":[x['div'] for x in band if x['bad']],
         "health_err_median":round(st.median([x['err7'] for x in health]),4),
         "band_points":[(x['s'],x['err7'],x['div'],x['bad']) for x in band],
         "all_points":[(x['s'],x['err7'],x['div'],x['bad'],x['noest']) for x in pts],
         "sharp":p['pooled_sharpness'],"scenes":p['scenes']}
    out["pools"][name]=rec
    cells.setdefault(p['arm'],[]).extend(band)
    cells.setdefault(p['arm']+"_health",[]).extend(health)
for cell in ["BLPL","BLPH","BHPL","BHPH"]:
    band=cells[cell]; health=cells[cell+"_health"]
    out["cells"][cell]={"band_err_median":round(st.median([x['err7'] for x in band]),4),
      "band_err_max":max(x['err7'] for x in band),"band_err_all":sorted(x['err7'] for x in band),
      "band_div_median":round(st.median([abs(x['div']) for x in band]),4),
      "band_n_bad":sum(x['bad'] for x in band),"band_n":len(band),
      "band_bad_div_median":round(st.median([abs(x['div']) for x in band if x['bad']]),4) if any(x['bad'] for x in band) else None,
      "health_err_median":round(st.median([x['err7'] for x in health]),4),
      "health_err_all":sorted(set(round(x['err7'],4) for x in health))}
json.dump(out, open('/home/hatch/workspace/your_files/顶刊技术文章/data/2026-11-24-lowdensity-factorial-posthoc.json','w'), indent=2, ensure_ascii=False)
print(json.dumps(out["cells"],indent=2,ensure_ascii=False))
for k,v in out["pools"].items(): print(k, v["band_err_median"], v["band_err_max"], v["band_div_median"], "bad",v["band_n_bad"],"health",v["health_err_median"], "bad_divs",v["band_bad_divs"])
print("elapsed",d["elapsed_sec"])
