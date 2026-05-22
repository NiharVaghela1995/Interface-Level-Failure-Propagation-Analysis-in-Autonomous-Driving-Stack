"""
Phase 2: Multi-Camera GradCAM + Cross-Modal Sensor Trust Analysis
Loop 1 diagnostic: which sensor did the model trust per spatial region?
Run on RunPod with: python phase2_bevfusion.py
"""

import torch, numpy as np, matplotlib.pyplot as plt
import os, json, warnings
from PIL import Image
from nuscenes.nuscenes import NuScenes
from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
from pytorch_grad_cam.utils.image import show_cam_on_image
warnings.filterwarnings('ignore')

DATAROOT = '/workspace/av_research/data/nuscenes'
RESULTS  = '/workspace/av_research/results'
os.makedirs(RESULTS, exist_ok=True)
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f'Device: {device} | GPU: {torch.cuda.get_device_name(0)}')

nusc = NuScenes('v1.0-mini', dataroot=DATAROOT)
scene = nusc.scene[0]
sample_token = scene['first_sample_token']
for _ in range(8):
    s = nusc.get('sample', sample_token)
    if s['next']: sample_token = s['next']
sample = nusc.get('sample', sample_token)
print(f'Scene: {scene["description"]}')
print(f'Annotations: {len(sample["anns"])}')

def load_cam(cam_name):
    d = nusc.get('sample_data', sample['data'][cam_name])
    return Image.open(os.path.join(DATAROOT, d['filename']))

def load_lidar():
    d = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
    return np.fromfile(os.path.join(DATAROOT, d['filename']), dtype=np.float32).reshape(-1,5)

def add_glare(img, intensity=0.65):
    arr = np.array(img, dtype=np.float32)
    h,w = arr.shape[:2]
    Y,X = np.ogrid[:h,:w]
    mask = np.exp(-((X-w//2)**2+(Y-h//3)**2)/(w*0.12)**2)
    return Image.fromarray(np.clip(arr+mask[:,:,None]*intensity*255,0,255).astype(np.uint8))

def lidar_dropout(pts, rate=0.35, seed=42):
    np.random.seed(seed)
    return pts[np.random.random(len(pts))>rate]

img_front = load_cam('CAM_FRONT')
img_back  = load_cam('CAM_BACK')
img_left  = load_cam('CAM_FRONT_LEFT')
img_glare = add_glare(img_front)
lidar_pts = load_lidar()
lidar_rain = lidar_dropout(lidar_pts)
print(f'LiDAR clean: {len(lidar_pts)} pts | rain: {len(lidar_rain)} pts')

print('Loading SegFormer (camera backbone proxy)...')
proc  = SegformerImageProcessor.from_pretrained("nvidia/segformer-b2-finetuned-cityscapes-1024-1024")
model = SegformerForSemanticSegmentation.from_pretrained("nvidia/segformer-b2-finetuned-cityscapes-1024-1024").to(device).eval()
print('Model ready')

def gradcam_sal(img):
    img_s = img.resize((512,512))
    arr   = np.array(img_s)/255.0
    inp   = proc(images=img_s, return_tensors='pt').to(device)
    pv    = inp['pixel_values'].requires_grad_(True)
    model.train()
    out   = model(pixel_values=pv).logits
    model.zero_grad()
    out[:,11].mean().backward()
    sal = np.abs(pv.grad.squeeze().cpu().numpy()).max(axis=0)
    sal = (sal-sal.min())/(sal.max()-sal.min()+1e-8)
    model.eval()
    return sal, arr, img_s

def mc_unc(img, n=20):
    img_s = img.resize((512,512))
    inp   = proc(images=img_s, return_tensors='pt').to(device)
    model.train()
    preds = []
    with torch.no_grad():
        for _ in range(n):
            preds.append(torch.softmax(model(**inp).logits,dim=1).cpu().numpy())
    model.eval()
    preds = np.array(preds)
    var   = preds.var(axis=0)[0].mean(axis=0)
    conf  = float(preds.mean(axis=0)[0].max(axis=0).mean())
    return var, conf, float(var.mean())

cameras = {'CAM_FRONT':img_front, 'CAM_FRONT_GLARE':img_glare,
           'CAM_BACK':img_back,   'CAM_FRONT_LEFT':img_left}

print('Computing GradCAM + uncertainty for all cameras...')
sal_res, unc_res = {}, {}
for name, img in cameras.items():
    sal, arr, img_s = gradcam_sal(img)
    var, conf, mu   = mc_unc(img)
    sal_res[name] = (sal, arr, img_s)
    unc_res[name] = (var, conf, mu)
    print(f'  {name:25s} conf={conf:.3f} unc={mu:.6f}')

fig, axes = plt.subplots(3, 4, figsize=(20, 14))
for i,(name,img) in enumerate(cameras.items()):
    sal,arr,img_s = sal_res[name]
    var,conf,mu   = unc_res[name]
    overlay = show_cam_on_image(arr.astype(np.float32), sal)
    color = 'red' if 'GLARE' in name else 'green'
    axes[0,i].imshow(img_s); axes[0,i].axis('off')
    axes[0,i].set_title(name, fontsize=9)
    axes[1,i].imshow(overlay); axes[1,i].axis('off')
    axes[1,i].set_title(f'GradCAM conf={conf:.3f}', fontsize=8, color=color)
    im = axes[2,i].imshow(var, cmap='hot'); axes[2,i].axis('off')
    axes[2,i].set_title(f'Uncertainty={mu:.5f}', fontsize=8, color=color)
    plt.colorbar(im, ax=axes[2,i], fraction=0.046)

plt.suptitle('Phase 2: Multi-Camera GradCAM + Uncertainty (Loop 1 Diagnostic)', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{RESULTS}/phase2_01_multicam.png', dpi=150, bbox_inches='tight')
print('Saved: phase2_01_multicam.png')

def lidar_bev(pts, rng=50, res=0.2):
    size = int(2*rng/res)
    bev  = np.zeros((size,size))
    m    = (np.abs(pts[:,0])<rng)&(np.abs(pts[:,1])<rng)
    xi   = ((pts[m,0]+rng)/res).astype(int).clip(0,size-1)
    yi   = ((pts[m,1]+rng)/res).astype(int).clip(0,size-1)
    np.maximum.at(bev,(xi,yi),pts[m,2]+2)
    return bev

bev_c = lidar_bev(lidar_pts)
bev_r = lidar_bev(lidar_rain)

def trust(unc_val, bev):
    c = 1.0 - min(unc_val*200, 1.0)
    l = min(bev.mean()*10, 1.0)
    t = c+l+1e-8
    return c/t, l/t

ct_c,lt_c = trust(unc_res['CAM_FRONT'][2], bev_c)
ct_g,lt_g = trust(unc_res['CAM_FRONT_GLARE'][2], bev_r)

fig, axes = plt.subplots(1,3,figsize=(18,6))
axes[0].imshow(bev_c, cmap='plasma', origin='lower')
axes[0].set_title(f'LiDAR BEV Clean ({len(lidar_pts)} pts)', color='green')
axes[1].imshow(bev_r, cmap='plasma', origin='lower')
axes[1].set_title(f'LiDAR BEV Rain ({len(lidar_rain)} pts)', color='red')
x = np.arange(2)
axes[2].bar(x-0.2,[ct_c,ct_g],0.35,label='Camera',color='steelblue',alpha=0.8)
axes[2].bar(x+0.2,[lt_c,lt_g],0.35,label='LiDAR', color='darkorange',alpha=0.8)
axes[2].set_xticks(x); axes[2].set_xticklabels(['Clean','Degraded'])
axes[2].set_ylabel('Relative trust'); axes[2].set_ylim(0,1)
axes[2].legend(); axes[2].grid(True,alpha=0.3,axis='y')
axes[2].set_title('Adaptive Sensor Trust (Loop 1)', fontweight='bold')
for i,(c,l) in enumerate(zip([ct_c,ct_g],[lt_c,lt_g])):
    axes[2].text(i-0.2,c+0.02,f'{c:.2f}',ha='center',fontsize=9,color='steelblue')
    axes[2].text(i+0.2,l+0.02,f'{l:.2f}',ha='center',fontsize=9,color='darkorange')
plt.suptitle('Phase 2: Cross-Modal Sensor Trust Balance', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{RESULTS}/phase2_02_trust.png', dpi=150, bbox_inches='tight')
print('Saved: phase2_02_trust.png')

results = {
    'phase':2, 'scene':scene['description'],
    'lidar_clean':int(len(lidar_pts)), 'lidar_rain':int(len(lidar_rain)),
    'dropout_pct':float((1-len(lidar_rain)/len(lidar_pts))*100),
    'uncertainty':{k:{'conf':v[1],'unc':v[2]} for k,v in unc_res.items()},
    'trust':{'clean':{'cam':ct_c,'lidar':lt_c},'degraded':{'cam':ct_g,'lidar':lt_g}}
}
with open(f'{RESULTS}/phase2_results.json','w') as f:
    json.dump(results,f,indent=2)

print('\n=== PHASE 2 COMPLETE ===')
print(f'Clean    -> cam={ct_c:.2f} lidar={lt_c:.2f}')
print(f'Degraded -> cam={ct_g:.2f} lidar={lt_g:.2f}')
