"""TASK-031 target-Windows environment probe.

표준 라이브러리만 사용하며 각 고정 가상환경 안에서 interpreter와 NVIDIA 도구의
실측값을 수집한다. readiness는 같은 probe를 다시 실행하므로 비어 있지 않은 version
문자열을 선언하는 것만으로는 통과할 수 없다.
"""

from __future__ import annotations

import csv
import ctypes
import hashlib
import importlib.metadata
import io
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


class EnvironmentProbeError(RuntimeError):
    """현재 interpreter가 고정 target environment를 증명하지 못했다."""


_CUDA_VERSION_RE = re.compile(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)*)")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_implementation_sha256() -> str:
    """receipt를 collector와 readiness caller 구현 양쪽에 결박한다."""

    digest = hashlib.sha256()
    for path in sorted((Path(__file__), Path(__file__).with_name("preflight.py"))):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _run_text(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EnvironmentProbeError(f"명령 실행 실패: {command[0]}: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise EnvironmentProbeError(
            f"명령이 {completed.returncode}로 종료됨: {command[0]}: {detail}"
        )
    return completed.stdout.strip()


def _canonical_architecture(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"amd64", "x64", "x86_64"}:
        return "x86_64"
    return normalized


def _windows_version() -> tuple[str, str]:
    build = platform.version().split(".")[-1]
    try:
        major = "11" if int(build) >= 22000 else platform.release()
    except ValueError:
        major = platform.release()
    return major, build


def _nvidia_probe() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        raise EnvironmentProbeError("nvidia-smi를 찾을 수 없다")
    executable_path = Path(executable).resolve()
    query = _run_text(
        (
            str(executable_path),
            "--query-gpu=uuid,name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        )
    )
    rows = list(csv.reader(io.StringIO(query)))
    if len(rows) != 1 or len(rows[0]) != 4:
        raise EnvironmentProbeError("정확히 한 target GPU의 NVIDIA query가 필요하다")
    uuid, name, driver_version, memory_mib = (item.strip() for item in rows[0])
    try:
        reported_vram_mib = int(float(memory_mib))
    except ValueError as error:
        raise EnvironmentProbeError("NVIDIA memory.total을 정수 MiB로 읽을 수 없다") from error
    status = _run_text((str(executable_path),))
    match = _CUDA_VERSION_RE.search(status)
    if match is None:
        raise EnvironmentProbeError("nvidia-smi에서 driver-supported CUDA version을 읽을 수 없다")
    return {
        "uuid": uuid,
        "name": name,
        "driver_version": driver_version,
        "reported_vram_mib": reported_vram_mib,
        "driver_supported_cuda_version": match.group(1),
        "nvidia_smi_path": str(executable_path),
        "nvidia_smi_sha256": _sha256_file(executable_path),
    }


def _load_windows_library(names: Sequence[str]) -> Any:
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise EnvironmentProbeError("Windows DLL loader를 사용할 수 없다")
    errors: list[str] = []
    for name in names:
        try:
            return loader(name)
        except OSError as error:
            errors.append(str(error))
    raise EnvironmentProbeError(f"필수 CUDA DLL을 load할 수 없다: {'; '.join(errors)}")


def _cuda_runtime_version() -> str:
    library = _load_windows_library(("cudart64_12.dll",))
    value = ctypes.c_int()
    function = library.cudaRuntimeGetVersion
    function.argtypes = [ctypes.POINTER(ctypes.c_int)]
    function.restype = ctypes.c_int
    result = function(ctypes.byref(value))
    if result != 0:
        raise EnvironmentProbeError(f"cudaRuntimeGetVersion 실패: {result}")
    return str(value.value)


def _cudnn_version() -> str:
    library = _load_windows_library(("cudnn64_9.dll", "cudnn64_8.dll"))
    function = library.cudnnGetVersion
    function.argtypes = []
    function.restype = ctypes.c_size_t
    value = int(function())
    if value <= 0:
        raise EnvironmentProbeError("cudnnGetVersion이 유효한 값을 반환하지 않았다")
    return str(value)


def _runtime_probe(environment_id: str) -> dict[str, Any]:
    if environment_id == "download":
        return {
            "cuda_stack_status": "not_applicable",
            "torch_version": "",
            "cuda_version": "",
            "cudnn_version": "",
            "cuda_available": False,
        }
    if environment_id == "faster-whisper":
        try:
            import ctranslate2  # type: ignore[import-not-found]
        except ImportError as error:
            raise EnvironmentProbeError("ctranslate2를 import할 수 없다") from error
        if int(ctranslate2.get_cuda_device_count()) < 1:
            raise EnvironmentProbeError("CTranslate2가 CUDA device를 찾지 못했다")
        return {
            "cuda_stack_status": "windows_locked",
            "torch_version": "not_applicable",
            "cuda_version": _cuda_runtime_version(),
            "cudnn_version": _cudnn_version(),
            "cuda_available": True,
        }
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError as error:
        raise EnvironmentProbeError("torch를 import할 수 없다") from error
    cuda_version = torch.version.cuda
    cudnn_version = torch.backends.cudnn.version()
    if not torch.cuda.is_available() or not cuda_version or not cudnn_version:
        raise EnvironmentProbeError("PyTorch CUDA/cuDNN probe가 준비되지 않았다")
    return {
        "cuda_stack_status": "windows_locked",
        "torch_version": str(torch.__version__),
        "cuda_version": str(cuda_version),
        "cudnn_version": str(cudnn_version),
        "cuda_available": True,
    }


def collect_local_environment_probe(
    environment: Mapping[str, Any], repo_root: Path
) -> dict[str, Any]:
    """manifest가 고정한 interpreter 안에서 receipt payload 하나를 수집한다."""

    if platform.system() != "Windows":
        raise EnvironmentProbeError("environment evidence는 target Windows에서만 생성한다")
    expected_python = (repo_root.resolve() / environment["python_executable_path"]).resolve()
    actual_python = Path(sys.executable).resolve()
    if os.path.normcase(str(expected_python)) != os.path.normcase(str(actual_python)):
        raise EnvironmentProbeError(
            f"고정 interpreter가 아니다: expected={expected_python}, actual={actual_python}"
        )
    os_version, os_build = _windows_version()
    resolver_path_value = shutil.which("uv")
    if resolver_path_value is None:
        raise EnvironmentProbeError("uv resolver를 찾을 수 없다")
    resolver_path = Path(resolver_path_value).resolve()
    resolver_raw = _run_text((str(resolver_path), "--version"))
    match = re.fullmatch(r"uv\s+([^\s]+)(?:\s+.*)?", resolver_raw)
    if match is None:
        raise EnvironmentProbeError("uv --version 출력을 해석할 수 없다")
    direct_packages = []
    for item in environment["direct_packages"]:
        try:
            version = importlib.metadata.version(item["name"])
        except importlib.metadata.PackageNotFoundError as error:
            raise EnvironmentProbeError(f"direct package가 설치되지 않았다: {item['name']}") from error
        direct_packages.append({"name": item["name"], "version": version})
    direct_packages.sort(key=lambda item: item["name"])
    return {
        "probe_implementation_sha256": probe_implementation_sha256(),
        "host": {
            "os": "windows",
            "os_version": os_version,
            "os_build": os_build,
            "architecture": _canonical_architecture(platform.machine()),
        },
        "python": {
            "version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "executable_path": environment["python_executable_path"],
            "executable_sha256": _sha256_file(actual_python),
        },
        "resolver": {
            "name": "uv",
            "version": match.group(1),
            "raw_output": resolver_raw,
            "executable_path": str(resolver_path),
            "executable_sha256": _sha256_file(resolver_path),
        },
        "direct_packages": direct_packages,
        "gpu": _nvidia_probe(),
        "runtime": _runtime_probe(environment["environment_id"]),
    }
