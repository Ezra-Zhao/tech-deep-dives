"""Shape-related area drift isolation bench (2026-11-20).
Prereg: data/2026-11-20-shape-drift-prereg.md (frozen before run).
Single-shape canvases, detector-identical mask+morph pipeline.
Factors: interpolation x morphology arm x scale. Checkpointed rows.
Usage: python3 bench.py <out_json>
"""
import json, math, os, sys
import numpy as np
import cv2
sys.path.insert(0, "/home/hatch/workspace/github/Bloom-Counter")
os.chdir("/home/hatch/workspace/github/Bloom-Counter")
from detector.color_segmentation import ColorSegmentationDetector

OUT = sys.argv[1]
PROG = OUT + ".progress.jsonl"
W = H = 240
BG = (40, 120, 40); PINK = (147, 20, 255)
INTERPS = {"LINEAR": cv2.INTER_LINEAR, "CUBIC": cv2.INTER_CUBIC, "NEAREST": cv2.INTER_NEAREST}
SCALES = [1.0, 1.5, 2.0, 2.5, 3.0]
ARMS = ["full", "close_only", "open_only", "none"]

def poly_pts(cx, cy, R, n, rot):
    return np.array([[int(round(cx + R*math.cos(rot + 2*math.pi*k/n))),
                      int(round(cy + R*math.sin(rot + 2*math.pi*k/n)))] for k in range(n)], np.int32)

def draw(shape, rep):
    img = np.zeros((H, W, 3), np.uint8); img[:] = BG
    rng = np.random.default_rng(7000 + rep)
    cx = W//2 + int(rng.integers(-6, 7)); cy = H//2 + int(rng.integers(-6, 7))
    rot = math.radians(5*rep)
    if shape == "circle6":
        cv2.circle(img, (cx, cy), 6, PINK, -1); nom = math.pi*36
    elif shape == "square11":
        cv2.rectangle(img, (cx-5, cy-5), (cx-5+11, cy-5+11), PINK, -1); nom = 121.0
    elif shape == "triangle17":
        cv2.fillPoly(img, [poly_pts(cx, cy, 10, 3, rot)], PINK); nom = (math.sqrt(3)/4)*17*17
    elif shape == "pentagon10":
        cv2.fillPoly(img, [poly_pts(cx, cy, 10, 5, rot)], PINK); nom = 2.5*100*math.sin(math.radians(72))
    elif shape == "hexagon7":
        cv2.fillPoly(img, [poly_pts(cx, cy, 7, 6, rot)], PINK); nom = (3*math.sqrt(3)/2)*49
    elif shape == "diamond16":
        pts = np.array([[cx, cy-8], [cx+8, cy], [cx, cy+8], [cx-8, cy]], np.int32)
        cv2.fillPoly(img, [pts], PINK); nom = 128.0
    elif shape == "circle12":
        cv2.circle(img, (cx, cy), 12, PINK, -1); nom = math.pi*144
    elif shape == "square21":
        cv2.rectangle(img, (cx-10, cy-10), (cx-10+21, cy-10+21), PINK, -1); nom = 441.0
    return img, (cx, cy), nom

SHAPES = ["circle6", "square11", "triangle17", "pentagon10", "hexagon7", "diamond16", "circle12", "square21"]

def run_arm(mask, arm):
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    m = mask
    if arm in ("full", "close_only"): m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
    if arm in ("full", "open_only"): m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    return m

def measure(img, cx, cy, s, interp, arm):
    if s != 1.0:
        img = cv2.resize(img, (int(round(W*s)), int(round(H*s))), interpolation=interp)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = ColorSegmentationDetector._petal_mask(hsv)
    m = run_arm(m, arm)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x, y = cx*s, cy*s
    for c in cnts:
        if cv2.pointPolygonTest(c, (float(x), float(y)), False) >= 0:
            return float(cv2.contourArea(c)) / (s*s)
    return None

rows = []
# background sanity: empty canvas mask must be all zero
bgimg = np.zeros((H, W, 3), np.uint8); bgimg[:] = BG
assert ColorSegmentationDetector._petal_mask(cv2.cvtColor(bgimg, cv2.COLOR_BGR2HSV)).max() == 0
for shape in SHAPES:
    for rep in range(16):
        img, (cx, cy), nom = draw(shape, rep)
        for s in SCALES:
            interps = ["LINEAR"] if s == 1.0 else list(INTERPS)
            for inm in interps:
                for arm in ARMS:
                    a = measure(img, cx, cy, s, INTERPS[inm], arm)
                    rows.append({"shape": shape, "rep": rep, "s": s, "interp": inm if s != 1.0 else "NA",
                                 "arm": arm, "nominal": round(nom, 1),
                                 "norm_area": None if a is None else round(a, 2)})
        with open(PROG, "a") as f: f.write(json.dumps({"shape": shape, "rep": rep}) + "\n")
    print("done", shape, flush=True)
json.dump({"rows": rows}, open(OUT, "w"), indent=1)
print("ROWS", len(rows))
