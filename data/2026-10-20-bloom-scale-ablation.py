import sys, os, json, math
sys.path.insert(0, "/home/hatch/workspace/github/Bloom-Counter")
os.chdir("/home/hatch/workspace/github/Bloom-Counter")
sys.path.insert(0, "/home/hatch/workspace/your_files/顶刊技术文章/data")
# reuse functions by importing the bench module is messy (it runs); copy minimal helpers inline
import numpy as np, cv2
from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector
WORK="/tmp/bloom_scale_bench"
SCENES=[(101,30,18),(202,36,20),(303,28,16),(404,40,22)]
bases=[]
for seed,nb,nd in SCENES:
    p=os.path.join(WORK,f"scene_{seed}.jpg")
    truth=generate_image(p,nb,nd,seed=seed)
    bases.append((seed,cv2.imread(p),truth["objects"]))

def score(dets, objects, s):
    used=set(); tp=fp=0; per={"bloom":[0,0],"bud":[0,0]}
    for d in dets:
        best,bd=None,1e9
        for i,o in enumerate(objects):
            if i in used or o["label"]!=d.label: continue
            dist=math.hypot(d.cx-o["cx"],d.cy-o["cy"])
            if dist<bd: bd,best=dist,i
        tol=max(38.0*s, objects[best]["r"]*1.1) if best is not None else 0
        if best is not None and bd<=tol: used.add(best); tp+=1; per[d.label][0]+=1
        else: fp+=1
    fn=len(objects)-len(used)
    prec=tp/(tp+fp) if tp+fp else 1.0; rec=tp/(tp+fn) if tp+fn else 1.0
    tb=sum(1 for o in objects if o["label"]=="bloom"); td=sum(1 for o in objects if o["label"]=="bud")
    return {"tp":tp,"fp":fp,"fn":fn,"precision":round(prec,4),"recall":round(rec,4),
            "f1":round(2*prec*rec/(prec+rec),4) if prec+rec else 0.0,
            "det_blooms":sum(1 for d in dets if d.label=="bloom"),"det_buds":sum(1 for d in dets if d.label=="bud"),
            "true_blooms":tb,"true_buds":td,
            "bloom_recall":round(per["bloom"][0]/max(1,tb),4),"bud_recall":round(per["bud"][0]/max(1,td),4)}
def micro(rows):
    tp=sum(r["tp"] for r in rows); fp=sum(r["fp"] for r in rows); fn=sum(r["fn"] for r in rows)
    prec=tp/(tp+fp) if tp+fp else 1.0; rec=tp/(tp+fn) if tp+fn else 1.0
    tb=sum(r["true_blooms"] for r in rows); td=sum(r["true_buds"] for r in rows)
    return {"precision":round(prec,4),"recall":round(rec,4),"f1":round(2*prec*rec/(prec+rec),4) if prec+rec else 0.0,
            "det_blooms":sum(r["det_blooms"] for r in rows),"det_buds":sum(r["det_buds"] for r in rows),
            "bloom_recall":round(sum(r["bloom_recall"]*r["true_blooms"] for r in rows)/max(1,tb),4),
            "bud_recall":round(sum(r["bud_recall"]*r["true_buds"] for r in rows)/max(1,td),4),"fp":fp}
def det(im,mi,bl,k):
    return ColorSegmentationDetector(min_area=int(mi),bloom_area_min=int(bl),morph_kernel=int(k)).detect(im)
def odd(s):
    k=int(round(7*s));
    if k%2==0: k+=1
    return max(3,k)

out={}
for s in [0.65,0.5,0.4,0.3]:
    w,h=int(round(1280*s)),int(round(960*s))
    imgs=[(cv2.resize(im,(w,h),interpolation=cv2.INTER_AREA),
           [{"label":o["label"],"cx":o["cx"]*s,"cy":o["cy"]*s,"r":o["r"]*s} for o in objs]) for _,im,objs in bases]
    mi_s, bl_s = max(1,round(120*s*s)), max(1,round(900*s*s))
    conds={
      "only_minArea_scaled": (mi_s,900,7),
      "only_bloomMin_scaled": (120,bl_s,7),
      "only_kernel_scaled": (120,900,odd(s)),
      "thresholds_scaled_kernel_fixed (=A2)": (mi_s,bl_s,7),
      "all_scaled (=A3)": (mi_s,bl_s,odd(s)),
      "all_fixed (=A1)": (120,900,7),
    }
    out[f"s={s}"]={}
    for name,(mi,bl,k) in conds.items():
        out[f"s={s}"][name]=micro([score(det(im,mi,bl,k),objs,s) for im,objs in imgs])
    print(s, {k:(v["f1"],v["bloom_recall"],v["bud_recall"]) for k,v in out[f"s={s}"].items()}, flush=True)
json.dump(out, open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-10-20-bloom-scale-ablation.json","w"), indent=2)
print("saved")
