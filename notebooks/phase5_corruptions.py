import torch, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, json, warnings
from PIL import Image, ImageFilter
from nuscenes.nuscenes import NuScenes
from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
warnings.filterwarnings("ignore")

DATAROOT="/workspace/data/nuscenes"
RESULTS="/workspace/results"
os.makedirs(RESULTS, exist_ok=True)
device="cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device}")
nusc=NuScenes("v1.0-mini",dataroot=DATAROOT)
print(f"Loaded {len(nusc.scene)} scenes")

def corrupt_brightness(img, s):
    arr=np.array(img,dtype=np.float32)
    return Image.fromarray(np.clip(arr*(1.0+s*0.4),0,255).astype(np.uint8))

def corrupt_darkness(img, s):
    arr=np.array(img,dtype=np.float32)
    return Image.fromarray(np.clip(arr*(1.0-s*0.35),0,255).astype(np.uint8))

def corrupt_fog(img, s):
    arr=np.array(img,dtype=np.float32)
    fog=np.ones_like(arr)*(s*180)
    return Image.fromarray(np.clip(arr*(1-s*0.6)+fog*s*0.6,0,255).astype(np.uint8))

def corrupt_motion_blur(img, s):
    return img.filter(ImageFilter.BoxBlur(int(s*4)+1))

def corrupt_snow(img, s):
    arr=np.array(img,dtype=np.float32)
    h,w=arr.shape[:2]
    ys=np.random.randint(0,h,int(s*800))
    xs=np.random.randint(0,w,int(s*800))
    arr[ys,xs]=np.clip(arr[ys,xs]+200,0,255)
    return Image.fromarray(arr.astype(np.uint8))

def corrupt_rain(img, s):
    arr=np.array(img,dtype=np.float32)
    h,w=arr.shape[:2]
    for _ in range(int(s*600)):
        x=np.random.randint(0,w-1)
        y=np.random.randint(0,h-20)
        l=np.random.randint(5,20)
        arr[y:y+l,x]=np.clip(arr[y:y+l,x]*0.7+150,0,255)
    return Image.fromarray(arr.astype(np.uint8))

def corrupt_glare(img, s):
    arr=np.array(img,dtype=np.float32)
    h,w=arr.shape[:2]
    Y,X=np.ogrid[:h,:w]
    mask=np.exp(-((X-w//2)**2+(Y-h//3)**2)/(w*0.12)**2)
    return Image.fromarray(np.clip(arr+mask[:,:,None]*s*255,0,255).astype(np.uint8))

def lidar_corrupt(pts, ctype, s):
    np.random.seed(42)
    if ctype=="rain_dropout": return pts[np.random.random(len(pts))>s*0.8]
    elif ctype=="fog_dropout":
        dist=np.sqrt(pts[:,0]**2+pts[:,1]**2)
        return pts[dist<50*(1-s*0.6)]
    elif ctype=="snow_noise":
        noisy=pts.copy()
        noisy[:,:3]+=np.random.normal(0,s*0.3,pts[:,:3].shape)
        return noisy
    return pts

CORRUPTIONS={
    "clean":      (lambda img,s: img,  "none",        "baseline"),
    "glare":      (corrupt_glare,       "none",        "camera"),
    "brightness": (corrupt_brightness,  "none",        "camera"),
    "darkness":   (corrupt_darkness,    "none",        "camera"),
    "fog":        (corrupt_fog,         "fog_dropout", "camera+lidar"),
    "motion_blur":(corrupt_motion_blur, "none",        "camera"),
    "snow":       (corrupt_snow,        "snow_noise",  "camera+lidar"),
    "rain":       (corrupt_rain,        "rain_dropout","camera+lidar"),
}
SEVERITIES=[0.2,0.4,0.6,0.8,1.0]

print("Loading SegFormer...")
proc=SegformerImageProcessor.from_pretrained("nvidia/segformer-b2-finetuned-cityscapes-1024-1024")
model=SegformerForSemanticSegmentation.from_pretrained("nvidia/segformer-b2-finetuned-cityscapes-1024-1024").to(device).eval()
print("Model ready")

def mc_uncertainty(img, n=15):
    img_s=img.resize((512,512))
    inp=proc(images=img_s,return_tensors="pt").to(device)
    model.train()
    preds=[]
    with torch.no_grad():
        for _ in range(n):
            preds.append(torch.softmax(model(**inp).logits,dim=1).cpu().numpy())
    model.eval()
    preds=np.array(preds)
    return float(preds.mean(axis=0)[0].max(axis=0).mean()), float(preds.var(axis=0)[0].mean())

def edl_trust(unc, baseline, k=5.0):
    return float(1.0/(1.0+np.exp(k*(unc/(baseline+1e-10)-1.1))))

def plan_regime(trust):
    unc=1.0-(0.6*trust+0.4*0.6)
    if unc>0.6: return "CONSERVATIVE",float(50*(1-0.8*unc))
    if unc>0.3: return "CAUTIOUS",float(50*(1-0.8*unc))
    return "NORMAL",float(50*(1-0.8*unc))

scene=nusc.scene[0]
sample_token=scene["first_sample_token"]
for _ in range(5):
    s=nusc.get("sample",sample_token)
    if s["next"]: sample_token=s["next"]
sample=nusc.get("sample",sample_token)
cam_data=nusc.get("sample_data",sample["data"]["CAM_FRONT"])
img_clean=Image.open(os.path.join(DATAROOT,cam_data["filename"]))
lid_data=nusc.get("sample_data",sample["data"]["LIDAR_TOP"])
pts_clean=np.fromfile(os.path.join(DATAROOT,lid_data["filename"]),dtype=np.float32).reshape(-1,5)

print("Computing baseline...")
base_conf,base_unc=mc_uncertainty(img_clean)
print(f"Baseline: conf={base_conf:.3f} unc={base_unc:.6f}")

print(f"Running {len(CORRUPTIONS)} corruptions x {len(SEVERITIES)} severities...")
results={}
for corr_name,(cam_fn,lid_fn,affected) in CORRUPTIONS.items():
    results[corr_name]={"affected_sensors":affected,"severities":{}}
    for sev in SEVERITIES:
        img_corr=cam_fn(img_clean,sev)
        pts_corr=lidar_corrupt(pts_clean,lid_fn,sev) if lid_fn!="none" else pts_clean
        conf,unc=mc_uncertainty(img_corr)
        trust=edl_trust(unc,base_unc)
        lidar_ratio=len(pts_corr)/len(pts_clean)
        regime,velocity=plan_regime(trust)
        results[corr_name]["severities"][str(sev)]={
            "confidence":conf,"uncertainty":unc,
            "camera_trust":trust,"lidar_ratio":lidar_ratio,
            "regime":regime,"velocity_kmh":velocity,
            "unc_increase_pct":float((unc-base_unc)/base_unc*100)
        }
    avg_unc=np.mean([v["uncertainty"] for v in results[corr_name]["severities"].values()])
    avg_vel=np.mean([v["velocity_kmh"] for v in results[corr_name]["severities"].values()])
    print(f"  {corr_name:15s} avg_unc={avg_unc:.6f} avg_vel={avg_vel:.1f}km/h")

print("Generating figures...")
corr_names=list(CORRUPTIONS.keys())
sev_labels=[str(s) for s in SEVERITIES]

fig,axes=plt.subplots(2,3,figsize=(20,12))

unc_mat=np.array([[results[c]["severities"][str(s)]["uncertainty"] for s in SEVERITIES] for c in corr_names])
im1=axes[0,0].imshow(unc_mat,cmap="hot",aspect="auto")
plt.colorbar(im1,ax=axes[0,0],fraction=0.046)
axes[0,0].set_xticks(range(len(SEVERITIES))); axes[0,0].set_xticklabels(sev_labels)
axes[0,0].set_yticks(range(len(corr_names))); axes[0,0].set_yticklabels(corr_names)
axes[0,0].set_title("Camera Uncertainty per Corruption",fontweight="bold")
for i in range(len(corr_names)):
    for j in range(len(SEVERITIES)):
        axes[0,0].text(j,i,f"{unc_mat[i,j]:.5f}",ha="center",va="center",fontsize=7,
                      color="white" if unc_mat[i,j]>unc_mat.mean() else "black")

trust_mat=np.array([[results[c]["severities"][str(s)]["camera_trust"] for s in SEVERITIES] for c in corr_names])
im2=axes[0,1].imshow(trust_mat,cmap="RdYlGn",aspect="auto",vmin=0,vmax=1)
plt.colorbar(im2,ax=axes[0,1],fraction=0.046)
axes[0,1].set_xticks(range(len(SEVERITIES))); axes[0,1].set_xticklabels(sev_labels)
axes[0,1].set_yticks(range(len(corr_names))); axes[0,1].set_yticklabels(corr_names)
axes[0,1].set_title("Camera Trust Loop 1",fontweight="bold")
for i in range(len(corr_names)):
    for j in range(len(SEVERITIES)):
        axes[0,1].text(j,i,f"{trust_mat[i,j]:.2f}",ha="center",va="center",fontsize=8,
                      color="white" if trust_mat[i,j]<0.4 else "black")

vel_mat=np.array([[results[c]["severities"][str(s)]["velocity_kmh"] for s in SEVERITIES] for c in corr_names])
im3=axes[0,2].imshow(vel_mat,cmap="RdYlGn_r",aspect="auto",vmin=30,vmax=50)
plt.colorbar(im3,ax=axes[0,2],fraction=0.046)
axes[0,2].set_xticks(range(len(SEVERITIES))); axes[0,2].set_xticklabels(sev_labels)
axes[0,2].set_yticks(range(len(corr_names))); axes[0,2].set_yticklabels(corr_names)
axes[0,2].set_title("Planned Velocity km/h Loop 2",fontweight="bold")
for i in range(len(corr_names)):
    for j in range(len(SEVERITIES)):
        axes[0,2].text(j,i,f"{vel_mat[i,j]:.0f}",ha="center",va="center",fontsize=8,
                      color="white" if vel_mat[i,j]<40 else "black")

regime_counts={}
for c in corr_names:
    counts={"NORMAL":0,"CAUTIOUS":0,"CONSERVATIVE":0}
    for s in SEVERITIES:
        counts[results[c]["severities"][str(s)]["regime"]]+=1
    regime_counts[c]=counts

x=np.arange(len(corr_names)); w=0.25
axes[1,0].bar(x-w,[regime_counts[c]["NORMAL"] for c in corr_names],w,label="NORMAL",color="#2ecc71",alpha=0.8)
axes[1,0].bar(x,[regime_counts[c]["CAUTIOUS"] for c in corr_names],w,label="CAUTIOUS",color="#f39c12",alpha=0.8)
axes[1,0].bar(x+w,[regime_counts[c]["CONSERVATIVE"] for c in corr_names],w,label="CONSERVATIVE",color="#e74c3c",alpha=0.8)
axes[1,0].set_xticks(x); axes[1,0].set_xticklabels(corr_names,rotation=30,ha="right",fontsize=9)
axes[1,0].set_title("Regime Distribution per Corruption",fontweight="bold")
axes[1,0].legend(fontsize=9); axes[1,0].grid(True,alpha=0.3,axis="y")

colors_l=plt.cm.Set1(np.linspace(0,1,len(corr_names)))
for i,c in enumerate(corr_names):
    unc_pct=[results[c]["severities"][str(s)]["unc_increase_pct"] for s in SEVERITIES]
    axes[1,1].plot(SEVERITIES,unc_pct,"o-",color=colors_l[i],linewidth=2,markersize=6,label=c,alpha=0.85)
axes[1,1].set_xlabel("Severity"); axes[1,1].set_ylabel("Uncertainty increase %")
axes[1,1].set_title("Uncertainty Increase vs Severity",fontweight="bold")
axes[1,1].legend(fontsize=8,ncol=2); axes[1,1].grid(True,alpha=0.3)
axes[1,1].axhline(y=0,color="gray",linestyle="--",alpha=0.5)

avg_unc_increase={c:np.mean([results[c]["severities"][str(s)]["unc_increase_pct"] for s in SEVERITIES]) for c in corr_names}
sorted_corr=sorted(avg_unc_increase.items(),key=lambda x:x[1],reverse=True)
names_sorted=[x[0] for x in sorted_corr]
vals_sorted=[x[1] for x in sorted_corr]
bar_colors=["#e74c3c" if v>10 else "#f39c12" if v>5 else "#2ecc71" for v in vals_sorted]
axes[1,2].barh(range(len(names_sorted)),vals_sorted,color=bar_colors,alpha=0.85)
axes[1,2].set_yticks(range(len(names_sorted))); axes[1,2].set_yticklabels(names_sorted)
axes[1,2].set_xlabel("Mean uncertainty increase %")
axes[1,2].set_title("Corruption Impact Ranking",fontweight="bold")
axes[1,2].grid(True,alpha=0.3,axis="x")
for i,v in enumerate(vals_sorted):
    axes[1,2].text(v+0.1,i,f"{v:.1f}%",va="center",fontsize=9,fontweight="bold")

plt.suptitle("Phase 5: nuScenes-C Corruption Benchmark\n8 corruption types x 5 severities",fontsize=13,fontweight="bold")
plt.tight_layout()
plt.savefig(f"{RESULTS}/phase5_01_corruption_benchmark.png",dpi=150,bbox_inches="tight")
print("Saved: phase5_01_corruption_benchmark.png")

phase5_results={
    "phase":5,"title":"nuScenes-C Corruption Benchmark",
    "corruption_types":list(CORRUPTIONS.keys()),
    "severities":SEVERITIES,
    "baseline":{"confidence":base_conf,"uncertainty":base_unc},
    "corruption_ranking":[{"corruption":c,"mean_unc_increase_pct":float(v)} for c,v in sorted_corr],
    "key_findings":{
        "most_impactful":sorted_corr[0][0],
        "least_impactful":sorted_corr[-1][0],
        "conservative_corruptions":[c for c in corr_names if any(
            results[c]["severities"][str(s)]["regime"]=="CONSERVATIVE" for s in SEVERITIES)]
    }
}
with open(f"{RESULTS}/phase5_results.json","w") as f:
    json.dump(phase5_results,f,indent=2)

print("\n=== PHASE 5 COMPLETE ===")
print(f"Most impactful:  {sorted_corr[0][0]} ({sorted_corr[0][1]:.1f}%)")
print(f"Least impactful: {sorted_corr[-1][0]} ({sorted_corr[-1][1]:.1f}%)")
print(f"CONSERVATIVE triggered by: {phase5_results['key_findings']['conservative_corruptions']}")
