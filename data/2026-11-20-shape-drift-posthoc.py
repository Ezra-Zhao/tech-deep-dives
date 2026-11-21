import json, statistics as st
D = json.load(open("/home/hatch/workspace/github/tech-deep-dives/data/2026-11-20-shape-drift-bench.json"))["rows"]
def sel(shape, s, interp, arm):
    return [r["norm_area"] for r in D if r["shape"]==shape and r["s"]==s and r["interp"]==interp and r["arm"]==arm and r["norm_area"] is not None]
def nom(shape): return next(r["nominal"] for r in D if r["shape"]==shape)
def med(shape,s,i,a):
    v=sel(shape,s,i,a); return round(st.median(v),2) if v else None
def mx(shape,s,i,a):
    v=sel(shape,s,i,a); return round(max(v),2) if v else None
def drift(shape,s,i,a):
    m=med(shape,s,i,a); return None if m is None else round((m/nom(shape)-1)*100,2)
out={}
shapes=["circle6","square11","triangle17","pentagon10","hexagon7","diamond16","circle12","square21"]
out["full_linear"]={sh:{f"s={s}":{"median":med(sh,s,"LINEAR","full"),"max":mx(sh,s,"LINEAR","full"),"drift_med_pct":drift(sh,s,"LINEAR","full"),"n_found":len(sel(sh,s,"LINEAR","full"))} for s in [1.0,1.5,2.0,2.5,3.0]} for sh in shapes}
# s=1 uses interp NA
for sh in shapes:
    out["full_linear"][sh]["s=1.0"]={"median":med(sh,1.0,"NA","full"),"max":mx(sh,1.0,"NA","full"),"drift_med_pct":round((med(sh,1.0,"NA","full")/nom(sh)-1)*100,2),"n_found":len(sel(sh,1.0,"NA","full"))}
# decomposition pooled s in {2,2.5,3}: median of per-s medians of norm area
def pooled_med(shape,i,a):
    ms=[med(shape,s,i,a) for s in [2.0,2.5,3.0]]; return round(st.median(ms),2)
def base_med(shape,a):
    return med(shape,1.0,"NA",a)
out["decomp"]={}
for sh in shapes:
    n=nom(sh)
    def delta(i,a): return round((pooled_med(sh,i,a)-base_med(sh,a))/n*100,2)
    d_none_n=delta("NEAREST","none"); d_none_l=delta("LINEAR","none"); d_none_c=delta("CUBIC","none")
    interp_share=round(d_none_l-d_none_n,2)
    close_share=round(delta("NEAREST","close_only")-d_none_n,2)
    open_share=round(delta("NEAREST","open_only")-d_none_n,2)
    total=delta("LINEAR","full")
    resid=round(total-(d_none_n+interp_share+close_share+open_share),2)
    out["decomp"][sh]={"base_none_nearest_pct":d_none_n,"interp_share_pts":interp_share,"cubic_minus_linear_none_pts":round(d_none_c-d_none_l,2),
                       "close_share_pts":close_share,"open_share_pts":open_share,"total_full_linear_pts":total,"interaction_residual_pts":resid,
                       "full_nearest_total_pts":delta("NEAREST","full")}
# band width full+LINEAR pooled s>=2: (max over pooled rows - median)/nominal
out["band"]={}
for sh in shapes:
    vals=[]
    for s in [2.0,2.5,3.0]: vals+=sel(sh,s,"LINEAR","full")
    out["band"][sh]={"median":round(st.median(vals),2),"max":round(max(vals),2),"band_width_pts":round((max(vals)-st.median(vals))/nom(sh)*100,2),"n":len(vals)}
json.dump(out, open("/home/hatch/workspace/github/tech-deep-dives/data/2026-11-20-shape-drift-posthoc.json","w"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
