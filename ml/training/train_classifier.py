"""Train an image classifier from an ImageFolder dataset.

Expected layout: root/train/<class>/*.jpg and root/val/<class>/*.jpg.
Install the optional vision dependencies before running.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--output", type=Path, default=Path("models/trained/species_classifier.pt"))
    args = parser.parse_args()
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader
        from torchvision import datasets, models, transforms
    except ImportError as exc:
        raise SystemExit("请先安装训练依赖：uv sync --extra vision，并另外安装 torchvision") from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    transform_train = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.65, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.2, 0.2, 0.2, 0.05),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    transform_eval = transforms.Compose([
        transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    train_set = datasets.ImageFolder(args.dataset / "train", transform=transform_train)
    val_set = datasets.ImageFolder(args.dataset / "val", transform=transform_eval)
    if train_set.classes != val_set.classes:
        raise SystemExit("train和val类别目录必须一致")
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=4, pin_memory=True)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False, num_workers=4, pin_memory=True)

    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(train_set.classes))
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best_accuracy = 0.0
    args.output.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                logits = model(images)
                loss = criterion(logits, labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running_loss += loss.item() * images.size(0)

        model.eval()
        correct = total = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                predictions = model(images).argmax(1)
                correct += int((predictions == labels).sum())
                total += labels.numel()
        accuracy = correct / max(total, 1)
        print(json.dumps({"epoch": epoch, "loss": running_loss / len(train_set), "val_accuracy": accuracy}, ensure_ascii=False))
        if accuracy >= best_accuracy:
            best_accuracy = accuracy
            torch.save({"model": model.state_dict(), "classes": train_set.classes, "accuracy": accuracy}, args.output)
    print(f"best val accuracy={best_accuracy:.4f}; saved={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
