from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the hierarchical iNat checkpoint as a species ONNX model")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--output", type=Path, default=Path("models/onnx/wildlife_species.onnx"))
    parser.add_argument("--opset", type=int, default=18)
    args = parser.parse_args()
    try:
        import torch
        from torch import nn
        from torchvision import models
    except ImportError as exc:
        raise SystemExit("请先执行：uv sync --extra training --extra vision") from exc

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    classes = checkpoint["classes"]
    architecture = checkpoint.get("architecture", "efficientnet_b0")
    image_size = int(checkpoint.get("image_size", 224))
    hierarchy_vocab = checkpoint.get("hierarchy_vocab") or {}

    class Model(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            if architecture == "mobilenet_v3_small":
                self.backbone = models.mobilenet_v3_small(weights=None)
                feature_dim = self.backbone.classifier[0].in_features
                self.backbone.classifier = nn.Identity()
            elif architecture == "efficientnet_b0":
                self.backbone = models.efficientnet_b0(weights=None)
                feature_dim = self.backbone.classifier[1].in_features
                self.backbone.classifier = nn.Identity()
            elif architecture == "convnext_tiny":
                self.backbone = models.convnext_tiny(weights=None)
                feature_dim = self.backbone.classifier[2].in_features
                self.backbone.classifier[2] = nn.Identity()
            else:
                raise ValueError(f"unsupported architecture: {architecture}")
            self.dropout = nn.Dropout(0.2)
            self.heads = nn.ModuleDict({"species": nn.Linear(feature_dim, len(classes))})
            for rank in ("kingdom", "phylum", "class", "order", "family", "genus"):
                self.heads[rank] = nn.Linear(feature_dim, len(hierarchy_vocab.get(rank) or ["Unknown"]))

        def forward(self, images):
            features = self.dropout(self.backbone(images))
            return self.heads["species"](features)

    model = Model()
    model.load_state_dict(checkpoint["model"], strict=True)
    model.eval()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, image_size, image_size)
    torch.onnx.export(
        model,
        dummy,
        args.output,
        input_names=["images"],
        output_names=["species_logits"],
        dynamic_axes={"images": {0: "batch"}, "species_logits": {0: "batch"}},
        opset_version=args.opset,
        do_constant_folding=True,
    )
    metadata = {
        "architecture": architecture,
        "image_size": image_size,
        "unknown_threshold": float(checkpoint.get("unknown_threshold", 0.25)),
        "dataset": checkpoint.get("dataset", "iNaturalist 2021"),
        "profile": checkpoint.get("profile", "mini"),
        "top1": float(checkpoint.get("best_top1", 0.0)),
        "top5": float(checkpoint.get("best_top5", 0.0)),
        "classes": classes,
    }
    metadata_path = args.output.with_suffix(".classes.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"onnx": str(args.output), "metadata": str(metadata_path), "classes": len(classes)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
