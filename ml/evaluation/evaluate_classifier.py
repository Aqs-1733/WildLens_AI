from __future__ import annotations
import argparse, json
from pathlib import Path


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("checkpoint",type=Path); parser.add_argument("dataset",type=Path); parser.add_argument("--split",default="test"); args=parser.parse_args()
    try:
        import torch
        from sklearn.metrics import classification_report, confusion_matrix
        from torch import nn
        from torch.utils.data import DataLoader
        from torchvision import datasets, models, transforms
    except ImportError as exc:
        raise SystemExit("评估需要torch、torchvision和scikit-learn") from exc
    ckpt=torch.load(args.checkpoint,map_location="cpu",weights_only=False); classes=ckpt["classes"]
    transform=transforms.Compose([transforms.Resize(256),transforms.CenterCrop(224),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    ds=datasets.ImageFolder(args.dataset/args.split,transform=transform)
    if ds.classes!=classes: raise SystemExit("checkpoint与数据集类别顺序不一致")
    model=models.efficientnet_b0(weights=None); model.classifier[1]=nn.Linear(model.classifier[1].in_features,len(classes)); model.load_state_dict(ckpt["model"]); model.eval()
    y_true=[]; y_pred=[]
    with torch.no_grad():
        for x,y in DataLoader(ds,batch_size=64,shuffle=False,num_workers=4):
            y_true.extend(y.tolist()); y_pred.extend(model(x).argmax(1).tolist())
    report=classification_report(y_true,y_pred,target_names=classes,output_dict=True,zero_division=0)
    output=args.checkpoint.with_suffix(".evaluation.json")
    output.write_text(json.dumps({"report":report,"confusion_matrix":confusion_matrix(y_true,y_pred).tolist()},ensure_ascii=False,indent=2),encoding="utf-8")
    print(output)
    return 0
if __name__=="__main__": raise SystemExit(main())
