"""Hierarchical iNaturalist 2021 trainer for 100 to 10,000 species.

This script reads the official COCO-like iNaturalist annotations directly, so it
never needs to copy 500,000 images into ImageFolder directories. It is designed
for Windows PCs and supports staged training, AMP, gradient accumulation,
checkpoint resume, top-1/top-5 metrics and taxonomy metadata export.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RANKS = ("kingdom", "phylum", "class", "order", "family", "genus")
LOSS_WEIGHTS = {
    "species": 1.0,
    "genus": 0.18,
    "family": 0.12,
    "order": 0.08,
    "class": 0.05,
    "phylum": 0.03,
    "kingdom": 0.02,
}


@dataclass(slots=True)
class Category:
    category_id: int
    scientific_name: str
    common_name: str
    ranks: dict[str, str]

    def as_json(self, model_index: int) -> dict[str, Any]:
        return {
            "index": model_index,
            "category_id": self.category_id,
            "scientific_name": self.scientific_name,
            "common_name_zh": "",
            "common_name_en": self.common_name,
            **self.ranks,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an iNaturalist 2021 hierarchical classifier")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--profile", choices=["mini", "full"], default="mini")
    parser.add_argument("--train-root", type=Path)
    parser.add_argument("--train-annotations", type=Path)
    parser.add_argument("--val-root", type=Path)
    parser.add_argument("--val-annotations", type=Path)
    parser.add_argument("--max-classes", type=int, default=10000)
    parser.add_argument("--samples-per-class", type=int, default=0, help="0 means use every available image")
    parser.add_argument("--kingdom", action="append", default=[], help="Optional kingdom filter; may be repeated")
    parser.add_argument(
        "--architecture",
        choices=["mobilenet_v3_small", "efficientnet_b0", "convnext_tiny"],
        default="mobilenet_v3_small",
    )
    parser.add_argument("--weights", choices=["default", "none"], default="default")
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--freeze-backbone-epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--accumulation", type=int, default=4)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.05)
    parser.add_argument("--label-smoothing", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("models/trained/inat10k"))
    parser.add_argument("--resume", type=Path)
    parser.add_argument(
        "--init-backbone",
        type=Path,
        help="Initialize only matching backbone weights from a smaller-class checkpoint",
    )
    parser.add_argument("--save-every", type=int, default=1)
    parser.add_argument("--limit-train-batches", type=int, default=0, help="Developer smoke-test only")
    parser.add_argument("--limit-val-batches", type=int, default=0, help="Developer smoke-test only")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    train_name = "train_mini" if args.profile == "mini" else "train"
    train_root = args.train_root or args.dataset_root
    train_annotations = args.train_annotations or args.dataset_root / f"{train_name}.json"
    val_root = args.val_root or args.dataset_root
    val_annotations = args.val_annotations or args.dataset_root / "val.json"
    missing = [path for path in (train_root, train_annotations, val_root, val_annotations) if not path.exists()]
    if missing:
        raise SystemExit("缺少数据文件：\n" + "\n".join(str(path) for path in missing))
    return train_root, train_annotations, val_root, val_annotations


def read_annotation(path: Path) -> dict:
    print(f"读取标注：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def category_from_json(raw: dict) -> Category:
    scientific = str(raw.get("name") or raw.get("scientific_name") or f"taxon_{raw['id']}")
    common = str(raw.get("common_name") or raw.get("english_name") or "")
    ranks = {
        "kingdom": str(raw.get("kingdom") or "Unknown"),
        "phylum": str(raw.get("phylum") or "Unknown"),
        "class": str(raw.get("class") or raw.get("class_name") or "Unknown"),
        "order": str(raw.get("order") or raw.get("order_name") or "Unknown"),
        "family": str(raw.get("family") or "Unknown"),
        "genus": str(raw.get("genus") or "Unknown"),
    }
    return Category(int(raw["id"]), scientific, common, ranks)


def resolve_image_path(root: Path, file_name: str) -> Path:
    normalized = Path(file_name.replace("\\", "/"))
    candidates = [root / normalized, root / normalized.name]
    if len(normalized.parts) > 1:
        candidates.append(root / Path(*normalized.parts[1:]))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def choose_categories(annotation: dict, args: argparse.Namespace) -> list[Category]:
    categories = [category_from_json(item) for item in annotation["categories"]]
    if args.kingdom:
        allowed = {value.lower() for value in args.kingdom}
        categories = [item for item in categories if item.ranks["kingdom"].lower() in allowed]
    categories.sort(key=lambda item: item.category_id)
    return categories[: max(1, min(args.max_classes, len(categories)))]


def build_hierarchy(categories: list[Category]) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]]]:
    vocabularies: dict[str, dict[str, int]] = {}
    for rank in RANKS:
        values = sorted({category.ranks[rank] or "Unknown" for category in categories})
        vocabularies[rank] = {name: index for index, name in enumerate(values)}
    metadata = [category.as_json(index) for index, category in enumerate(categories)]
    return vocabularies, metadata


def records_from_annotation(
    annotation: dict,
    root: Path,
    selected_categories: list[Category],
    samples_per_class: int,
    seed: int,
) -> list[tuple[Path, int]]:
    category_to_index = {item.category_id: index for index, item in enumerate(selected_categories)}
    image_by_id = {int(item["id"]): str(item["file_name"]) for item in annotation["images"]}
    grouped: dict[int, list[tuple[Path, int]]] = defaultdict(list)
    for item in annotation["annotations"]:
        category_id = int(item["category_id"])
        if category_id not in category_to_index:
            continue
        file_name = image_by_id.get(int(item["image_id"]))
        if not file_name:
            continue
        grouped[category_id].append((resolve_image_path(root, file_name), category_to_index[category_id]))
    rng = random.Random(seed)
    records: list[tuple[Path, int]] = []
    for category in selected_categories:
        rows = grouped.get(category.category_id, [])
        rng.shuffle(rows)
        if samples_per_class > 0:
            rows = rows[:samples_per_class]
        records.extend(rows)
    rng.shuffle(records)
    return records


def main() -> int:
    args = parse_args()
    try:
        import torch
        from PIL import Image, ImageFile
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
        from torchvision import models, transforms
    except ImportError as exc:
        raise SystemExit("请先执行：uv sync --extra training --extra vision") from exc

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    train_root, train_json, val_root, val_json = resolve_paths(args)
    train_annotation = read_annotation(train_json)
    val_annotation = read_annotation(val_json)
    categories = choose_categories(train_annotation, args)
    vocabularies, class_metadata = build_hierarchy(categories)
    train_records = records_from_annotation(train_annotation, train_root, categories, args.samples_per_class, args.seed)
    val_records = records_from_annotation(val_annotation, val_root, categories, 0, args.seed + 1)
    if not train_records or not val_records:
        raise SystemExit("没有找到可训练图片，请检查数据根目录与annotation中的file_name")

    category_targets = []
    for category in categories:
        category_targets.append({rank: vocabularies[rank][category.ranks[rank] or "Unknown"] for rank in RANKS})

    class INatDataset(Dataset):
        def __init__(self, records: list[tuple[Path, int]], transform: Any) -> None:
            self.records = records
            self.transform = transform

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int):
            path, species_index = self.records[index]
            try:
                with Image.open(path) as image:
                    image = image.convert("RGB")
                    tensor = self.transform(image)
            except Exception:
                # The official dataset should be valid, but a deterministic black image keeps
                # a single damaged sample from killing a multi-hour Windows training run.
                tensor = torch.zeros(3, args.image_size, args.image_size)
            labels = {"species": species_index, **category_targets[species_index]}
            return tensor, labels

    train_transform = transforms.Compose([
        transforms.RandomResizedCrop(args.image_size, scale=(0.55, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandAugment(num_ops=2, magnitude=7),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    resize_size = int(args.image_size / 0.875)
    val_transform = transforms.Compose([
        transforms.Resize(resize_size),
        transforms.CenterCrop(args.image_size),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    train_set = INatDataset(train_records, train_transform)
    val_set = INatDataset(val_records, val_transform)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pin_memory = device.type == "cuda"
    train_loader = DataLoader(
        train_set,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.workers,
        pin_memory=pin_memory,
        persistent_workers=args.workers > 0,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_set,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_memory,
        persistent_workers=args.workers > 0,
    )

    class HierarchicalNatureModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            if args.architecture == "mobilenet_v3_small":
                weights = models.MobileNet_V3_Small_Weights.DEFAULT if args.weights == "default" else None
                self.backbone = models.mobilenet_v3_small(weights=weights)
                feature_dim = self.backbone.classifier[0].in_features
                self.backbone.classifier = nn.Identity()
            elif args.architecture == "efficientnet_b0":
                weights = models.EfficientNet_B0_Weights.DEFAULT if args.weights == "default" else None
                self.backbone = models.efficientnet_b0(weights=weights)
                feature_dim = self.backbone.classifier[1].in_features
                self.backbone.classifier = nn.Identity()
            else:
                weights = models.ConvNeXt_Tiny_Weights.DEFAULT if args.weights == "default" else None
                self.backbone = models.convnext_tiny(weights=weights)
                feature_dim = self.backbone.classifier[2].in_features
                self.backbone.classifier[2] = nn.Identity()
            self.dropout = nn.Dropout(0.2)
            self.heads = nn.ModuleDict({"species": nn.Linear(feature_dim, len(categories))})
            for rank in RANKS:
                self.heads[rank] = nn.Linear(feature_dim, len(vocabularies[rank]))

        def forward(self, images):
            features = self.dropout(self.backbone(images))
            return {name: head(features) for name, head in self.heads.items()}

        def freeze_backbone(self, frozen: bool) -> None:
            for parameter in self.backbone.parameters():
                parameter.requires_grad = not frozen
            for parameter in self.heads.parameters():
                parameter.requires_grad = True

    model = HierarchicalNatureModel().to(device)
    start_epoch = 1
    best_top1 = 0.0
    best_top5 = 0.0
    history: list[dict[str, Any]] = []
    resume_payload = None
    if args.resume:
        resume_payload = torch.load(args.resume, map_location="cpu", weights_only=False)
        model.load_state_dict(resume_payload["model"])
        start_epoch = int(resume_payload.get("epoch", 0)) + 1
        best_top1 = float(resume_payload.get("best_top1", 0.0))
        best_top5 = float(resume_payload.get("best_top5", 0.0))
        history = list(resume_payload.get("history") or [])
    elif args.init_backbone:
        source = torch.load(args.init_backbone, map_location="cpu", weights_only=False)
        source_state = source.get("model") or source
        current_state = model.state_dict()
        compatible = {
            name: value
            for name, value in source_state.items()
            if name.startswith("backbone.")
            and name in current_state
            and tuple(value.shape) == tuple(current_state[name].shape)
        }
        if not compatible:
            raise SystemExit("初始化权重中没有与当前主干匹配的参数，请检查architecture是否一致")
        model.load_state_dict(compatible, strict=False)
        print(f"已从 {args.init_backbone} 载入 {len(compatible)} 个主干参数。")

    frozen = start_epoch <= args.freeze_backbone_epochs
    model.freeze_backbone(frozen)
    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=args.lr,
        weight_decay=args.weight_decay,
    )
    if resume_payload and resume_payload.get("optimizer"):
        try:
            optimizer.load_state_dict(resume_payload["optimizer"])
        except ValueError:
            print("优化器参数组已因解冻阶段变化而重新初始化。")
    criterion = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = args.output_dir / "classes.json"
    metadata_path.write_text(json.dumps(class_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "hierarchy_vocab.json").write_text(
        json.dumps(vocabularies, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    def validate() -> tuple[float, float, float, list[float]]:
        model.eval()
        total = 0
        correct1 = 0
        correct5 = 0
        loss_total = 0.0
        correct_confidences: list[float] = []
        with torch.inference_mode():
            for batch_index, (images, labels) in enumerate(val_loader, start=1):
                if args.limit_val_batches and batch_index > args.limit_val_batches:
                    break
                images = images.to(device, non_blocking=True)
                targets = {name: value.to(device, non_blocking=True) for name, value in labels.items()}
                with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                    outputs = model(images)
                    loss = sum(LOSS_WEIGHTS[name] * criterion(outputs[name], targets[name]) for name in outputs)
                probabilities = outputs["species"].softmax(dim=1)
                top5 = probabilities.topk(min(5, len(categories)), dim=1).indices
                correct_matrix = top5.eq(targets["species"].view(-1, 1))
                correct1 += int(correct_matrix[:, :1].sum().item())
                correct5 += int(correct_matrix.any(dim=1).sum().item())
                total += targets["species"].numel()
                loss_total += float(loss.item()) * images.size(0)
                max_probs, predictions = probabilities.max(dim=1)
                mask = predictions.eq(targets["species"])
                correct_confidences.extend(max_probs[mask].detach().cpu().tolist())
        return loss_total / max(total, 1), correct1 / max(total, 1), correct5 / max(total, 1), correct_confidences

    print(json.dumps({
        "device": str(device),
        "architecture": args.architecture,
        "classes": len(categories),
        "train_images": len(train_set),
        "val_images": len(val_set),
        "effective_batch": args.batch_size * args.accumulation,
        "frozen_backbone": frozen,
    }, ensure_ascii=False, indent=2))

    for epoch in range(start_epoch, args.epochs + 1):
        should_freeze = epoch <= args.freeze_backbone_epochs
        if should_freeze != frozen:
            frozen = should_freeze
            model.freeze_backbone(frozen)
            optimizer = torch.optim.AdamW(
                (parameter for parameter in model.parameters() if parameter.requires_grad),
                lr=args.lr * (0.3 if not frozen else 1.0),
                weight_decay=args.weight_decay,
            )
            print(f"Epoch {epoch}: backbone {'冻结' if frozen else '已解冻'}")
        model.train()
        optimizer.zero_grad(set_to_none=True)
        running_loss = 0.0
        seen = 0
        started = time.perf_counter()
        for batch_index, (images, labels) in enumerate(train_loader, start=1):
            if args.limit_train_batches and batch_index > args.limit_train_batches:
                break
            images = images.to(device, non_blocking=True)
            targets = {name: value.to(device, non_blocking=True) for name, value in labels.items()}
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                outputs = model(images)
                loss = sum(LOSS_WEIGHTS[name] * criterion(outputs[name], targets[name]) for name in outputs)
                scaled_loss = loss / max(1, args.accumulation)
            scaler.scale(scaled_loss).backward()
            if batch_index % args.accumulation == 0 or batch_index == len(train_loader):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            running_loss += float(loss.item()) * images.size(0)
            seen += images.size(0)
            if batch_index % 100 == 0:
                speed = seen / max(time.perf_counter() - started, 0.001)
                print(f"epoch={epoch} batch={batch_index}/{len(train_loader)} loss={running_loss/max(seen,1):.4f} speed={speed:.1f} img/s")

        val_loss, top1, top5, correct_confidences = validate()
        unknown_threshold = 0.25
        if correct_confidences:
            values = sorted(correct_confidences)
            unknown_threshold = float(values[max(0, int(len(values) * 0.08) - 1)])
            unknown_threshold = max(0.12, min(0.80, unknown_threshold))
        epoch_result = {
            "epoch": epoch,
            "train_loss": running_loss / max(seen, 1),
            "val_loss": val_loss,
            "top1": top1,
            "top5": top5,
            "unknown_threshold_calibration": unknown_threshold,
            "duration_seconds": round(time.perf_counter() - started, 1),
            "backbone_frozen": frozen,
        }
        history.append(epoch_result)
        print(json.dumps(epoch_result, ensure_ascii=False))
        improved = top1 > best_top1
        best_top1 = max(best_top1, top1)
        best_top5 = max(best_top5, top5)
        payload = {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "epoch": epoch,
            "best_top1": best_top1,
            "best_top5": best_top5,
            "unknown_threshold": unknown_threshold,
            "architecture": args.architecture,
            "image_size": args.image_size,
            "classes": class_metadata,
            "hierarchy_vocab": vocabularies,
            "history": history,
            "profile": args.profile,
            "dataset": "iNaturalist 2021",
        }
        torch.save(payload, args.output_dir / "last.pt")
        if improved:
            torch.save(payload, args.output_dir / "best.pt")
        if args.save_every > 0 and epoch % args.save_every == 0:
            torch.save(payload, args.output_dir / f"epoch_{epoch:03d}.pt")
        (args.output_dir / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"训练完成：best top1={best_top1:.4f}, best top5={best_top5:.4f}")
    print(f"最佳权重：{args.output_dir / 'best.pt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
