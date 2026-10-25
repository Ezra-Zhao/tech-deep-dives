import json, math, os, sys, time, statistics
import numpy as np, cv2
REPO="/home/hatch/workspace/github/Bloom-Counter"
sys.path.insert(0, REPO); os.chdir(REPO)
from simulator.generate import generate_image
from detector.color_segmentation import ColorSegmentationDetector
WORK="/tmp/bloom_resample_bench"; os.makedirs(WORK, exist_ok=True)
SCENES=[(101,30,18),(202,36,20),(303,28,16),(404,40,22)]
bases=[]
for seed,nb,nd in SCENES:
    p=os.path.join(WORK,f"scene_{seed}.jpg")
    truth=generate_image(p,nb,nd,seed=seed)
    bases.append(cv2.imread(p))
def odd_kernel(s):
    k=int(round(7*s))
    if k%2==0: k+=1
    return max(3,k)
out={}
for s in [1.0,0.5,0.22,0.15,0.10]:
    h=int(round(960*s)); w=int(round(1280*s))
    natives=[cv2.resize(im,(w,h),interpolation=cv2.INTER_AREA) for im in bases]
    ups=[cv2.resize(im,(1280,960),interpolation=cv2.INTER_LINEAR) for im in natives] if s!=1.0 else bases
    res={}
    for name, imgs, mn, bm, k in [
        ("P", natives, max(1,round(120*s*s)), max(1,round(900*s*s)), odd_kernel(s)),
        ("U_LINEAR", ups, 120, 900, 7)]:
        det=ColorSegmentationDetector(min_area=int(mn), bloom_area_min=int(bm), morph_kernel=int(k))
        times=[]
        for rep in range(30):
            im=imgs[rep % len(imgs)]
            t0=time.perf_counter(); det.detect(im); times.append(time.perf_counter()-t0)
        res[name]={"median_s": round(statistics.median(times),4), "min_s": round(min(times),4)}
    # upsample cost itself
    if s!=1.0:
        uts=[]
        for rep in range(30):
            im=natives[rep % len(natives)]
            t0=time.perf_counter(); cv2.resize(im,(1280,960),interpolation=cv2.INTER_LINEAR); uts.append(time.perf_counter()-t0)
        res["upsample_median_s"]=round(statistics.median(uts),4)
    out[f"s={s}"]=res
    print(f"s={s}", res, flush=True)
json.dump(out, open("/home/hatch/workspace/your_files/顶刊技术文章/data/2026-10-24-bloom-resample-timing.json","w"), indent=2)
