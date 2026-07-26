from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def _bytes_gib(value: int) -> float:
    return round(value / 1024**3, 2)


def _system_memory() -> float | None:
    try:
        import psutil
        return _bytes_gib(psutil.virtual_memory().total)
    except Exception:
        if hasattr(os, "sysconf"):
            try:
                return _bytes_gib(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
            except Exception:
                return None
        return None


def _nvidia() -> list[dict]:
    command = shutil.which("nvidia-smi")
    if not command:
        return []
    try:
        result = subprocess.run(
            [command, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return []
    rows = []
    for line in result.stdout.splitlines():
        values = [value.strip() for value in line.split(",")]
        if len(values) >= 3:
            rows.append({"name": values[0], "memory_mib": int(float(values[1])), "driver": values[2]})
    return rows


def _torch() -> dict:
    try:
        import torch
        return {
            "installed": True,
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        }
    except Exception as exc:
        return {"installed": False, "error": type(exc).__name__}


def recommendation(vram_mib: int, cuda_available: bool) -> dict:
    if not cuda_available or vram_mib <= 0:
        return {
            "profile": "cpu-smoke-only",
            "batch_size": 4,
            "accumulation": 16,
            "workers": 0,
            "architecture": "mobilenet_v3_small",
            "note": "CPU仅建议先跑10至100类和少量样本；一万类完整训练会非常慢，但可用断点续训逐步推进。",
        }
    if vram_mib < 6000:
        return {"profile": "low-vram", "batch_size": 8, "accumulation": 8, "workers": 2, "architecture": "mobilenet_v3_small", "note": "先冻结主干训练分类头，再逐步解冻。"}
    if vram_mib < 10000:
        return {"profile": "8gb", "batch_size": 16, "accumulation": 4, "workers": 2, "architecture": "efficientnet_b0", "note": "适合iNat mini分阶段训练。"}
    if vram_mib < 16000:
        return {"profile": "12gb", "batch_size": 32, "accumulation": 2, "workers": 4, "architecture": "efficientnet_b0", "note": "可尝试全一万类mini数据，注意温度和磁盘空间。"}
    return {"profile": "high-vram", "batch_size": 64, "accumulation": 1, "workers": 6, "architecture": "convnext_tiny", "note": "可使用更大主干和更高分辨率。"}


def main() -> int:
    project = Path(__file__).resolve().parents[2]
    disk = shutil.disk_usage(project)
    gpus = _nvidia()
    torch_info = _torch()
    vram = max((gpu["memory_mib"] for gpu in gpus), default=0)
    rec = recommendation(vram, bool(torch_info.get("cuda_available")))
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_threads": os.cpu_count(),
        "ram_gib": _system_memory(),
        "project_disk_free_gib": _bytes_gib(disk.free),
        "nvidia_gpus": gpus,
        "torch": torch_info,
        "recommendation": rec,
    }
    output = project / "storage" / "logs" / "training_hardware.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告已保存：{output}")
    if disk.free < 120 * 1024**3:
        print("\n[警告] 项目所在磁盘剩余空间不足120GiB。建议把数据集放到空间更大的独立目录。")
    print("\n推荐首轮命令：")
    print(
        "uv run python ml/training/train_inat10k.py "
        "--dataset-root D:/WildLens_Datasets/inat2021 "
        "--profile mini --max-classes 100 --samples-per-class 50 --epochs 2 "
        f"--batch-size {rec['batch_size']} --accumulation {rec['accumulation']} "
        f"--workers {rec['workers']} --architecture {rec['architecture']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
