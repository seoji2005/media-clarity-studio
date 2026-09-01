"""TASK-031 dependency/model preflight.

이 모듈은 모델을 고르거나 성능을 주장하지 않는다. 계약에서 고정한 네 dependency
환경과 다섯 model revision을 닫힌 manifest로 검사하고, 실제 실행 전에는 다음을
모두 요구한다.

- Windows 11 / Python 3.12에서 해석한 hash lock
- 해당 환경에서 고정한 CUDA/PyTorch 정보
- exact revision으로 받은 로컬 model tree와 receipt

기본 `validate`는 저장소에 보존할 준비 manifest만 검사한다. `--require-ready`는 위
실행 증거가 하나라도 없으면 fail-closed한다. 모델 다운로드는 명시적
`download --allow-network`에서만 가능하며 remote inference나 사용자 미디어 업로드를
수행하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from media_clarity.job_runtime import write_json_atomic
from media_clarity.schema_core import (
    DEFAULT_SCHEMA_DIR,
    REPO_ROOT,
    Finding,
    JsonInputError,
    SchemaSet,
    SchemaValidator,
    load_strict,
    portable_relative_path_error,
    sort_findings,
)


PREFLIGHT_SCHEMA_FILE = "calibration-preflight-v1.schema.json"
PREFLIGHT_SCHEMA_FILES = ("common-v1.schema.json", PREFLIGHT_SCHEMA_FILE)
DEFAULT_MANIFEST_PATH = REPO_ROOT / "config" / "task-031-preflight.json"
MODEL_RECEIPT_NAME = ".mcs-model-receipt.json"

PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^;\s]+)$")
HASH_LINE_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}(?:\s|$)")

EXPECTED_TARGET = {
    "os": "windows",
    "os_version": "11",
    "architecture": "x86_64",
    "python_version": "3.12",
    "gpu": "NVIDIA GeForce RTX 4070 SUPER",
    "vram_mib": 12288,
}

EXPECTED_ENVIRONMENTS = {
    "download": {
        "input": "requirements/task-031/download.in",
        "lock": "requirements/task-031/locks/download-windows-py312.lock",
        "packages": {
            "huggingface-hub": (
                "1.29.0",
                "https://pypi.org/project/huggingface-hub/1.29.0/",
            )
        },
    },
    "faster-whisper": {
        "input": "requirements/task-031/faster-whisper.in",
        "lock": "requirements/task-031/locks/faster-whisper-windows-py312.lock",
        "packages": {
            "faster-whisper": (
                "1.2.1",
                "https://pypi.org/project/faster-whisper/1.2.1/",
            )
        },
    },
    "qwen-asr": {
        "input": "requirements/task-031/qwen-asr.in",
        "lock": "requirements/task-031/locks/qwen-asr-windows-py312.lock",
        "packages": {
            "qwen-asr": ("0.0.6", "https://pypi.org/project/qwen-asr/0.0.6/")
        },
    },
    "translation": {
        "input": "requirements/task-031/translation.in",
        "lock": "requirements/task-031/locks/translation-windows-py312.lock",
        "packages": {
            "accelerate": ("1.12.0", "https://pypi.org/project/accelerate/1.12.0/"),
            "sentencepiece": (
                "0.2.1",
                "https://pypi.org/project/sentencepiece/0.2.1/",
            ),
            "transformers": (
                "5.16.1",
                "https://pypi.org/project/transformers/5.16.1/",
            ),
        },
    },
}

EXPECTED_MODELS = {
    "Systran/faster-whisper-large-v3": {
        "role": "asr",
        "revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
        "license": "MIT",
        "environment_id": "faster-whisper",
        "local_dir": "models/task-031/faster-whisper-large-v3",
    },
    "Qwen/Qwen3-ASR-1.7B": {
        "role": "asr",
        "revision": "7278e1e70fe206f11671096ffdd38061171dd6e5",
        "license": "Apache-2.0",
        "environment_id": "qwen-asr",
        "local_dir": "models/task-031/qwen3-asr-1.7b",
    },
    "google/madlad400-3b-mt": {
        "role": "translation",
        "revision": "fa184c675da0b5c9e1c8694fccd4e12e2d422094",
        "license": "Apache-2.0",
        "environment_id": "translation",
        "local_dir": "models/task-031/madlad400-3b-mt",
    },
    "Qwen/Qwen3.5-4B": {
        "role": "translation",
        "revision": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
        "license": "Apache-2.0",
        "environment_id": "translation",
        "local_dir": "models/task-031/qwen3.5-4b",
    },
    "Qwen/Qwen3-ForcedAligner-0.6B": {
        "role": "alignment",
        "revision": "c7cbfc2048c462b0d63a45797104fc9db3ad62b7",
        "license": "Apache-2.0",
        "environment_id": "qwen-asr",
        "local_dir": "models/task-031/qwen3-forced-aligner-0.6b",
    },
}

ERROR_CODES = (
    "E_SCHEMA",
    "E_PATH",
    "E_DEPENDENCY_SET",
    "E_DEPENDENCY_MISSING",
    "E_DEPENDENCY_DIGEST",
    "E_DEPENDENCY_PIN",
    "E_LOCK_PENDING",
    "E_LOCK_MISSING",
    "E_LOCK_DIGEST",
    "E_LOCK_HASH",
    "E_LOCK_UNTRACKED",
    "E_CUDA_PENDING",
    "E_MODEL_SET",
    "E_MODEL_IDENTITY",
    "E_MODEL_ROOT_REQUIRED",
    "E_MODEL_MISSING",
    "E_MODEL_RECEIPT",
    "E_MODEL_TREE",
    "E_NETWORK_NOT_ALLOWED",
    "E_MODEL_DOWNLOAD",
)


def preflight_schema_set(schema_dir: Path = DEFAULT_SCHEMA_DIR) -> SchemaSet:
    return SchemaSet(schema_dir, PREFLIGHT_SCHEMA_FILES)


def _finding(location: str, code: str, message: str) -> Finding:
    return Finding(location=location, code=code, message=message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_file(repo_root: Path, value: Any, location: str) -> tuple[Path | None, list[Finding]]:
    reason = portable_relative_path_error(value)
    if reason is not None:
        return None, [_finding(location, "E_PATH", reason)]
    root = repo_root.resolve()
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root):
        return None, [_finding(location, "E_PATH", "저장소 root 밖을 가리킨다")]
    return candidate, []


def _parse_dependency_input(path: Path, location: str) -> tuple[list[tuple[str, str]], list[Finding]]:
    packages: list[tuple[str, str]] = []
    findings: list[Finding] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = PIN_RE.fullmatch(stripped)
        line_location = f"{location}:{line_number}"
        if match is None:
            findings.append(
                _finding(line_location, "E_DEPENDENCY_PIN", "직접 dependency는 name==version이어야 한다")
            )
            continue
        name, version = match.groups()
        canonical_name = name.lower().replace("_", "-")
        if canonical_name in seen:
            findings.append(_finding(line_location, "E_DEPENDENCY_PIN", "중복 package pin"))
            continue
        seen.add(canonical_name)
        packages.append((canonical_name, version))
    if packages != sorted(packages):
        findings.append(_finding(location, "E_DEPENDENCY_PIN", "package pin은 이름순이어야 한다"))
    return packages, findings


def _check_lock(
    environment: Mapping[str, Any], index: int, repo_root: Path, require_ready: bool
) -> list[Finding]:
    findings: list[Finding] = []
    location = f"manifest/dependency_environments/{index}"
    lock_path, path_findings = _repo_file(repo_root, environment.get("lock_path"), f"{location}/lock_path")
    findings.extend(path_findings)
    if lock_path is None:
        return findings
    status = environment.get("lock_status")
    recorded_hash = environment.get("lock_sha256")
    if status == "pending_windows_resolution":
        if recorded_hash != "":
            findings.append(_finding(f"{location}/lock_sha256", "E_LOCK_UNTRACKED", "pending lock에 digest가 있다"))
        if lock_path.exists():
            findings.append(_finding(f"{location}/lock_path", "E_LOCK_UNTRACKED", "lock 파일은 있지만 manifest가 pending이다"))
        if require_ready:
            findings.append(_finding(location, "E_LOCK_PENDING", "Windows hash lock이 아직 해석되지 않았다"))
        return findings
    if status != "windows_resolved":
        return findings
    if not lock_path.is_file():
        findings.append(_finding(f"{location}/lock_path", "E_LOCK_MISSING", "기록된 lock 파일이 없다"))
        return findings
    actual_hash = _sha256_file(lock_path)
    if actual_hash != recorded_hash:
        findings.append(_finding(f"{location}/lock_sha256", "E_LOCK_DIGEST", "lock 파일 SHA-256 불일치"))
    lock_text = lock_path.read_text(encoding="utf-8")
    logical_requirements: list[str] = []
    pending = ""
    for raw in lock_text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        continuation = stripped.endswith("\\")
        fragment = stripped[:-1].rstrip() if continuation else stripped
        pending = f"{pending} {fragment}".strip()
        if not continuation:
            logical_requirements.append(pending)
            pending = ""
    if pending:
        logical_requirements.append(pending)
    if not logical_requirements or not all(
        "==" in requirement and HASH_LINE_RE.search(requirement)
        for requirement in logical_requirements
    ):
        findings.append(_finding(f"{location}/lock_path", "E_LOCK_HASH", "모든 lock requirement에 sha256 hash가 필요하다"))
    if not environment.get("resolver_version"):
        findings.append(_finding(f"{location}/resolver_version", "E_LOCK_PENDING", "lock resolver version이 없다"))
    return findings


def validate_manifest(
    manifest: Mapping[str, Any], repo_root: Path = REPO_ROOT, require_ready: bool = False
) -> list[Finding]:
    """닫힌 schema와 고정 후보/dependency identity를 검사한다."""

    schema_findings = SchemaValidator(preflight_schema_set()).validate(
        manifest, PREFLIGHT_SCHEMA_FILE, "manifest"
    )
    if schema_findings:
        return sort_findings(schema_findings)

    findings: list[Finding] = []
    if manifest["target_system"] != EXPECTED_TARGET:
        findings.append(_finding("manifest/target_system", "E_MODEL_IDENTITY", "TASK-031 target system 불일치"))

    environments = manifest["dependency_environments"]
    by_environment = {item["environment_id"]: item for item in environments}
    if len(by_environment) != len(environments) or set(by_environment) != set(EXPECTED_ENVIRONMENTS):
        findings.append(_finding("manifest/dependency_environments", "E_DEPENDENCY_SET", "환경 ID 집합이 정확히 네 개가 아니다"))

    for index, environment in enumerate(environments):
        location = f"manifest/dependency_environments/{index}"
        environment_id = environment["environment_id"]
        expected_paths = EXPECTED_ENVIRONMENTS.get(environment_id)
        if expected_paths is None:
            continue
        expected_input = expected_paths["input"]
        expected_lock = expected_paths["lock"]
        if environment["dependency_input_path"] != expected_input:
            findings.append(_finding(f"{location}/dependency_input_path", "E_DEPENDENCY_SET", "고정 input 경로 불일치"))
        if environment["lock_path"] != expected_lock:
            findings.append(_finding(f"{location}/lock_path", "E_DEPENDENCY_SET", "고정 lock 경로 불일치"))

        dependency_path, path_findings = _repo_file(
            repo_root, environment["dependency_input_path"], f"{location}/dependency_input_path"
        )
        findings.extend(path_findings)
        if dependency_path is not None:
            if not dependency_path.is_file():
                findings.append(_finding(f"{location}/dependency_input_path", "E_DEPENDENCY_MISSING", "dependency input 파일이 없다"))
            else:
                actual_digest = _sha256_file(dependency_path)
                if actual_digest != environment["dependency_input_sha256"]:
                    findings.append(_finding(f"{location}/dependency_input_sha256", "E_DEPENDENCY_DIGEST", "dependency input SHA-256 불일치"))
                parsed, pin_findings = _parse_dependency_input(
                    dependency_path, environment["dependency_input_path"]
                )
                findings.extend(pin_findings)
                declared = sorted(
                    (item["name"].lower().replace("_", "-"), item["version"])
                    for item in environment["direct_packages"]
                )
                if parsed != declared:
                    findings.append(_finding(f"{location}/direct_packages", "E_DEPENDENCY_SET", "input pin과 manifest package 집합이 다르다"))
                declared_with_sources = {
                    item["name"].lower().replace("_", "-"): (
                        item["version"],
                        item["official_source"],
                    )
                    for item in environment["direct_packages"]
                }
                if declared_with_sources != expected_paths["packages"]:
                    findings.append(_finding(f"{location}/direct_packages", "E_DEPENDENCY_SET", "고정 package version 또는 공식 출처 불일치"))

        findings.extend(_check_lock(environment, index, repo_root, require_ready))
        cuda_status = environment["cuda_stack_status"]
        cuda_values = (
            environment["torch_version"],
            environment["cuda_version"],
            environment["cudnn_version"],
        )
        if environment_id == "download":
            if cuda_status != "not_applicable" or any(cuda_values):
                findings.append(_finding(location, "E_CUDA_PENDING", "download 환경에는 CUDA stack을 기록하지 않는다"))
        elif require_ready and (cuda_status != "windows_locked" or not all(cuda_values)):
            findings.append(_finding(location, "E_CUDA_PENDING", "Windows에서 검증한 torch/CUDA/cuDNN lock이 없다"))

    models = manifest["models"]
    by_model = {item["model_id"]: item for item in models}
    if len(by_model) != len(models) or set(by_model) != set(EXPECTED_MODELS):
        findings.append(_finding("manifest/models", "E_MODEL_SET", "후보 model ID 집합이 정확히 다섯 개가 아니다"))
    local_dirs: set[str] = set()
    for index, model in enumerate(models):
        location = f"manifest/models/{index}"
        expected = EXPECTED_MODELS.get(model["model_id"])
        if expected is not None:
            actual = {key: model[key] for key in expected}
            if actual != expected:
                findings.append(_finding(location, "E_MODEL_IDENTITY", "role/revision/license/environment/local_dir 불일치"))
        path_reason = portable_relative_path_error(model["local_dir"])
        if path_reason is not None or not model["local_dir"].startswith("models/task-031/"):
            findings.append(_finding(f"{location}/local_dir", "E_PATH", path_reason or "TASK-031 model 경로 밖"))
        if model["local_dir"] in local_dirs:
            findings.append(_finding(f"{location}/local_dir", "E_MODEL_SET", "model local_dir 중복"))
        local_dirs.add(model["local_dir"])

    return sort_findings(findings)


def _model_tree_stats(directory: Path) -> tuple[str, int, int, list[Finding]]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    findings: list[Finding] = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(directory).as_posix()
        if relative == MODEL_RECEIPT_NAME:
            continue
        if path.is_symlink():
            findings.append(_finding(relative, "E_MODEL_TREE", "model tree에 symlink를 허용하지 않는다"))
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        file_hash = _sha256_file(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hash))
        file_count += 1
        total_bytes += size
    if file_count == 0:
        findings.append(_finding(".", "E_MODEL_TREE", "model tree가 비어 있다"))
    return digest.hexdigest(), file_count, total_bytes, findings


def _receipt_document(model: Mapping[str, Any], directory: Path) -> tuple[dict[str, Any], list[Finding]]:
    tree_hash, file_count, total_bytes, findings = _model_tree_stats(directory)
    return (
        {
            "schema_version": "1.0.0",
            "model_id": model["model_id"],
            "revision": model["revision"],
            "license": model["license"],
            "file_count": file_count,
            "total_bytes": total_bytes,
            "tree_sha256": tree_hash,
        },
        findings,
    )


def validate_readiness(
    manifest: Mapping[str, Any], model_root: Path | None, repo_root: Path = REPO_ROOT
) -> list[Finding]:
    """실행 직전 lock/CUDA/model receipt까지 검사한다."""

    findings = validate_manifest(manifest, repo_root=repo_root, require_ready=True)
    if any(finding.code == "E_SCHEMA" for finding in findings):
        return sort_findings(findings)
    if model_root is None:
        findings.append(_finding("model_root", "E_MODEL_ROOT_REQUIRED", "--model-root가 필요하다"))
        return sort_findings(findings)
    root = model_root.resolve()
    for index, model in enumerate(manifest.get("models", [])):
        if not isinstance(model, dict) or "local_dir" not in model:
            continue
        target = (root / model["local_dir"]).resolve()
        location = f"manifest/models/{index}"
        if not target.is_relative_to(root):
            findings.append(_finding(f"{location}/local_dir", "E_PATH", "model root 밖을 가리킨다"))
            continue
        if not target.is_dir():
            findings.append(_finding(location, "E_MODEL_MISSING", "model directory가 없다"))
            continue
        receipt_path = target / MODEL_RECEIPT_NAME
        if not receipt_path.is_file():
            findings.append(_finding(location, "E_MODEL_RECEIPT", "model receipt가 없다"))
            continue
        try:
            receipt = load_strict(receipt_path)
        except (OSError, JsonInputError) as error:
            findings.append(_finding(location, "E_MODEL_RECEIPT", f"receipt를 읽을 수 없다: {error}"))
            continue
        expected_receipt, tree_findings = _receipt_document(model, target)
        findings.extend(
            _finding(f"{location}/{item.location}", item.code, item.message)
            for item in tree_findings
        )
        if receipt != expected_receipt:
            findings.append(_finding(location, "E_MODEL_RECEIPT", "receipt identity 또는 model tree digest 불일치"))
    return sort_findings(findings)


def _download_models(
    manifest: Mapping[str, Any], model_ids: Sequence[str], model_root: Path, allow_network: bool
) -> list[Finding]:
    if not allow_network:
        return [_finding("download", "E_NETWORK_NOT_ALLOWED", "모델 다운로드에는 --allow-network가 필요하다")]
    manifest_findings = validate_manifest(manifest, require_ready=False)
    if manifest_findings:
        return manifest_findings
    download_environment = next(
        item for item in manifest["dependency_environments"] if item["environment_id"] == "download"
    )
    if download_environment["lock_status"] != "windows_resolved":
        return [_finding("download", "E_LOCK_PENDING", "download 환경의 Windows hash lock을 먼저 확정해야 한다")]
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return [_finding("download", "E_DEPENDENCY_MISSING", "고정 download 환경에 huggingface-hub가 없다")]

    by_model = {item["model_id"]: item for item in manifest["models"]}
    findings: list[Finding] = []
    for model_id in model_ids:
        model = by_model.get(model_id)
        if model is None:
            findings.append(_finding("download", "E_MODEL_SET", f"manifest에 없는 model: {model_id}"))
            continue
        target = (model_root.resolve() / model["local_dir"]).resolve()
        if not target.is_relative_to(model_root.resolve()):
            findings.append(_finding("download", "E_PATH", f"model root 밖 경로: {model_id}"))
            continue
        target.mkdir(parents=True, exist_ok=True)
        try:
            snapshot_download(repo_id=model_id, revision=model["revision"], local_dir=target)
        except Exception as error:
            findings.append(
                _finding("download", "E_MODEL_DOWNLOAD", f"{model_id}@{model['revision']} 다운로드 실패: {error}")
            )
            continue
        receipt, tree_findings = _receipt_document(model, target)
        findings.extend(tree_findings)
        if not tree_findings:
            write_json_atomic(target / MODEL_RECEIPT_NAME, receipt)
    return sort_findings(findings)


def _print_findings(findings: Iterable[Finding], as_json: bool) -> None:
    findings = list(findings)
    if as_json:
        print(
            json.dumps(
                [
                    {"location": item.location, "code": item.code, "message": item.message}
                    for item in findings
                ],
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return
    for item in findings:
        print(item.as_line(), file=sys.stderr)


def _load_manifest(path: Path) -> Mapping[str, Any]:
    value = load_strict(path)
    if not isinstance(value, dict):
        raise JsonInputError("preflight manifest root는 객체여야 한다")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TASK-031 dependency/model preflight")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--json", action="store_true", help="finding을 JSON으로 출력")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="준비 manifest를 검사")
    validate_parser.add_argument("--require-ready", action="store_true")
    validate_parser.add_argument("--model-root", type=Path)

    download_parser = subparsers.add_parser("download", help="exact revision model snapshot을 준비")
    download_parser.add_argument("--model-root", type=Path, required=True)
    download_parser.add_argument("--model-id", action="append", required=True)
    download_parser.add_argument("--allow-network", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = _load_manifest(args.manifest)
    except (OSError, JsonInputError) as error:
        _print_findings([_finding("manifest", "E_SCHEMA", str(error))], args.json)
        return 2

    if args.command == "validate":
        if args.require_ready:
            findings = validate_readiness(manifest, args.model_root)
        else:
            findings = validate_manifest(manifest)
    else:
        findings = _download_models(
            manifest, args.model_id, args.model_root, args.allow_network
        )
    if findings:
        _print_findings(findings, args.json)
        return 1
    if not args.json:
        if args.command == "validate" and not args.require_ready:
            print("TASK-031 준비 manifest 검증 통과 (실행 readiness는 별도 검사)")
        elif args.command == "validate":
            print("TASK-031 실행 preflight 통과")
        else:
            print("TASK-031 model snapshot 준비 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
