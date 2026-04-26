#!/usr/bin/env python3
"""Print a compact cloud/GPU environment report.

This script is intentionally non-fatal for optional packages so it can be run
both locally and on a fresh cloud instance.
"""

from __future__ import annotations

import importlib
import platform
import subprocess
import sys
from typing import Any


def _version(module_name: str) -> str:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - diagnostic path
        return f"unavailable ({exc.__class__.__name__}: {exc})"

    version: Any = getattr(module, "__version__", None)
    return str(version) if version is not None else "available"


def _print_package_versions() -> None:
    packages = [
        ("numpy", "numpy"),
        ("sklearn", "scikit-learn"),
        ("pandas", "pandas"),
        ("yaml", "PyYAML"),
        ("PIL", "Pillow"),
        ("cv2", "opencv-python"),
        ("torch", "torch"),
        ("torchvision", "torchvision"),
        ("transformers", "transformers"),
        ("sentence_transformers", "sentence-transformers"),
        ("accelerate", "accelerate"),
    ]

    print("\nPackages:")
    for module_name, display_name in packages:
        print(f"  {display_name}: {_version(module_name)}")


def _print_nvidia_smi() -> None:
    print("\nnvidia-smi:")
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except FileNotFoundError:
        print("  unavailable: nvidia-smi not found")
        return
    except subprocess.TimeoutExpired:
        print("  unavailable: command timed out")
        return

    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown error"
        print(f"  unavailable: {stderr}")
        return

    for line in result.stdout.strip().splitlines()[:12]:
        print(f"  {line}")


def _print_torch_cuda() -> None:
    print("\nTorch CUDA:")
    try:
        import torch
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"  torch unavailable: {exc.__class__.__name__}: {exc}")
        return

    print(f"  torch version: {torch.__version__}")
    print(f"  cuda built: {torch.version.cuda}")
    print(f"  cuda available: {torch.cuda.is_available()}")

    if not torch.cuda.is_available():
        return

    device_count = torch.cuda.device_count()
    print(f"  device count: {device_count}")
    for device_idx in range(device_count):
        props = torch.cuda.get_device_properties(device_idx)
        memory_gb = props.total_memory / (1024**3)
        capability = ".".join(str(part) for part in (props.major, props.minor))
        print(
            "  "
            f"cuda:{device_idx} {props.name} | "
            f"{memory_gb:.1f} GB | capability {capability}"
        )


def main() -> int:
    print("Environment:")
    print(f"  python: {sys.version.split()[0]}")
    print(f"  executable: {sys.executable}")
    print(f"  platform: {platform.platform()}")
    print(f"  machine: {platform.machine()}")

    _print_package_versions()
    _print_nvidia_smi()
    _print_torch_cuda()

    print("\nResult:")
    print("  Environment check completed. Review unavailable packages before cloud runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
