"""TASK-028 재개 가능한 synchronous stage runtime.

계약은 `docs/tasks/TASK-028.md` §3.3~§3.7이다.

이 모듈이 보장하는 것:

- **결정적 cache key** — canonical JSON(UTF-8, key 정렬, 결정적 separator, NaN/Infinity 금지)
  바이트의 SHA-256. 선택 항목은 **부재 자체가 canonical 값**으로 들어간다.
- **검증된 hit만 재사용** — completed checkpoint와 모든 출력 artifact의 존재·hash·size를
  다시 확인한 뒤에만 stage를 건너뛴다.
- **원본 불변·no-overwrite** — CAS 최종 object는 `artifact_store`가 덮어쓰지 않는다.
  manifest·attempt record 같은 metadata만 same-directory temp + atomic replace로 전이한다.
- **중단 안전** — attempt를 `running`으로 먼저 기록하고, artifact를 승격·재검증한 **뒤에야**
  `completed`로 전이한다. 남은 `running` record는 지우지 않고 `interrupted`로 보존한다.

이 모듈이 하지 않는 것:

- 실제 ASR·번역·OCR·metric 알고리즘 (TASK-028 §6)
- 모델·GPU·VRAM sampler, subprocess worker supervision, 비동기 scheduler, 멀티프로세스 실행
- 자동 삭제·GC·retention (U-16 미정)
- 전역 cross-job cache index — cache lookup은 **같은 job의 기존 completed attempt**만 본다

**job fingerprint와 stage cache key를 구분한다.** job fingerprint는 기존 job에 이어 쓸 수
있는지를 정하는 job-level identity(pipeline ID·runtime/schema version·source identity·DAG
topology)만 담는다. 개별 stage의 config/model/context/implementation 변경은 job fingerprint를
바꾸지 않고 **그 stage의 cache key**를 바꾼다. 이 구분이 없으면 §3.5의 "A의 fingerprint가
바뀌면 A와 downstream만 miss이고 독립 branch는 재사용한다"가 "job fingerprint가 다르면 resume을
거부한다"와 동시에 성립할 수 없다.

Python 3.12 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping, Sequence

from media_clarity.artifact_store import (
    ERROR_CODES,
    ArtifactStore,
    ContractViolation,
    FailureInjection,
    content_hash_of,
    opaque_identity_error,
    path_segment_error,
    relative_path_error,
    resolve_inside_root,
    utc_now,
)
from media_clarity.schema_core import (
    DEFAULT_SCHEMA_DIR,
    COMMON_SCHEMA_FILE,
    SCHEMA_VERSION,
    Finding,
    JsonInputError,
    SchemaSet,
    SchemaValidator,
    load_strict,
    sort_findings,
)


#: runtime 계약 버전. cache key와 job fingerprint 양쪽에 들어간다.
RUNTIME_VERSION = "task-028/1.0.0"

JOB_SCHEMA_FILE = "job-v1.schema.json"
JOB_SCHEMA_FILES = (COMMON_SCHEMA_FILE, JOB_SCHEMA_FILE)

ATTEMPT_RECORD_POINTER = "/$defs/AttemptRecord"
ARTIFACT_REF_POINTER = "/$defs/ArtifactRef"

JOBS_ROOT = "jobs"

#: J-01~J-16. runner와 unit test가 각각 이 목록으로 누락·중복을 검사한다.
EXPECTED_CASE_IDS = tuple(f"J-{index:02d}" for index in range(1, 17))


class InjectedInterrupt(BaseException):
    """중단 주입 신호. `Exception`이 아니므로 stage 실패로 오분류되지 않는다.

    실제 프로세스 강제 종료를 흉내 내되 결정적으로 재현한다. production 기본값에서는
    어떤 주입도 실행되지 않으므로 이 예외가 발생하지 않는다.
    """


def job_schema_set(directory: Path | None = None) -> SchemaSet:
    return SchemaSet(directory or DEFAULT_SCHEMA_DIR, JOB_SCHEMA_FILES)


# ---------------------------------------------------------------------------
# canonical JSON — cache key와 fingerprint의 유일한 바이트 표현
# ---------------------------------------------------------------------------


def canonical_json_bytes(value: Any) -> bytes:
    """UTF-8 · key 정렬 · 결정적 separator · NaN/Infinity 금지.

    `allow_nan=False`이므로 float NaN/Infinity가 fingerprint에 들어가면 조용히
    통과하지 않고 `ValueError`가 난다.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return content_hash_of(hashlib.sha256(canonical_json_bytes(value)).hexdigest())


# ---------------------------------------------------------------------------
# 사양
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageSpec:
    """한 stage의 실행 사양.

    선택 fingerprint는 **없으면 None**이며, None도 canonical cache key에 그대로 들어간다.
    조용히 key 계산에서 빠지지 않는다 (§3.3).
    """

    stage_id: str
    implementation_version: str
    depends_on: tuple[str, ...] = ()
    config_hash: str | None = None
    dependency_fingerprint: str | None = None
    source_hash: str | None = None
    chunking_hash: str | None = None
    model_hash: str | None = None
    context_hash: str | None = None
    random_seed: int | None = None
    reproducibility_tier: str | None = None
    #: 필요한 fingerprint를 제공할 수 없거나 stage가 비결정적이면 False.
    cacheable: bool = True


@dataclass(frozen=True)
class JobSpec:
    """job-level identity와 DAG."""

    job_id: str
    pipeline_id: str
    stages: tuple[StageSpec, ...]
    #: 호출자가 제공한 **비민감** 입력 식별자. 외부 절대 경로를 넣지 않는다.
    source_identity: str | None = None
    #: project root 기준 job 디렉터리 위치. 호출자가 바꿀 수 있으므로 preflight에서 검사한다.
    jobs_root: str = JOBS_ROOT


@dataclass(frozen=True)
class StageOutput:
    """stage가 workspace에 만든 파일 하나."""

    name: str
    path: Path
    kind: str = "blob"
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class StageContext:
    """stage callable이 받는 것. 외부 절대 경로를 기록하지 않는다."""

    job_id: str
    stage_id: str
    attempt_id: str
    workspace: Path
    inputs: tuple[Mapping[str, Any], ...]
    input_paths: tuple[Path, ...]


StageCallable = Callable[[StageContext], Sequence[StageOutput]]


@dataclass(frozen=True)
class StageOutcome:
    stage_id: str
    cache_status: str
    cache_reason: str
    cache_key: str
    attempt_id: str
    attempt_status: str
    #: project root 기준 **실제** attempt record 경로. manifest는 이 값만 기록한다
    #: (REVIEW-019 M-01-R1) — record 내부 ID에서 경로를 다시 만들어 내지 않는다.
    attempt_path: str
    callable_invoked: bool
    outputs: tuple[Mapping[str, Any], ...]
    verified_artifact_count: int
    verified_artifact_bytes: int


@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: str
    job_fingerprint: str
    stages: tuple[StageOutcome, ...]

    def outcome(self, stage_id: str) -> StageOutcome:
        for entry in self.stages:
            if entry.stage_id == stage_id:
                return entry
        raise KeyError(stage_id)


# ---------------------------------------------------------------------------
# preflight — filesystem을 **바꾸기 전에** 전부 거부한다.
# ---------------------------------------------------------------------------


#: attempt 상태별 필수·금지 필드 (TASK-028 §3.4, REVIEW-018 M-01).
#: schema는 "있어도 된다"만 말하므로, 상태가 실제로 뜻하는 바는 이 표가 고정한다.
ATTEMPT_STATE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "running": {
        "required": (),
        "forbidden": (
            "ended_at",
            "wall_duration_seconds",
            "interrupted_at",
            "error_code",
            "error_location",
        ),
    },
    "interrupted": {
        # 언제 죽었는지는 관측하지 못했다. ended_at을 지어내지 않고, 전이를 **관측한**
        # 시각과 안정 code/location만 남긴다 (REVIEW-018 M-02).
        "required": ("interrupted_at", "error_code", "error_location"),
        "forbidden": ("ended_at", "wall_duration_seconds"),
    },
    "failed": {
        # 실패 evidence가 없는 failed record는 복구·QC 증거가 아니다 (REVIEW-019 M-01-R3).
        "required": ("ended_at", "wall_duration_seconds", "error_code", "error_location"),
        "forbidden": ("interrupted_at",),
    },
    "completed": {
        "required": ("ended_at", "wall_duration_seconds"),
        "forbidden": ("interrupted_at", "error_code", "error_location"),
    },
}

#: 완료가 아닌 attempt는 출력을 가질 수 없다. 출력이 있다는 것은 완료했다는 뜻이다.
_TERMINAL_WITHOUT_OUTPUTS = ("running", "interrupted", "failed")

#: 상태가 강제하는 정확한 error code. 다른 코드가 적히면 전이 근거를 신뢰할 수 없다.
_REQUIRED_ERROR_CODE = {"interrupted": "E_STATE_TRANSITION"}

#: 계약된 attempt ID 모양. 숫자 부분은 attempt_number와 같아야 한다.
_ATTEMPT_ID_RE = re.compile(r"^a([0-9]{4,})$")


def check_attempt_semantics(record: Mapping[str, Any], location: str) -> list[Finding]:
    """schema를 통과한 attempt record가 **의미상으로도** 성립하는지 검사한다.

    schema만으로는 `outputs=[]`·종료 시각 없음·검증 수 0인 `completed` record가 통과한다.
    그런 record를 cache hit로 쓰면 callable을 건너뛴 거짓 완료가 된다 (REVIEW-018 M-01).

    반환하는 finding의 코드는 `E_CHECKPOINT_INVALID`이고, 위치는 실제 record 파일과
    그 안의 JSON Pointer다.
    """

    findings: list[Finding] = []

    def fail(where: str, message: str) -> None:
        findings.append(Finding(where, "E_CHECKPOINT_INVALID", message))

    status = record.get("status")
    rules = ATTEMPT_STATE_RULES.get(status)
    if rules is None:  # pragma: no cover - schema enum이 이미 거른다
        fail(f"{location}/status", f"알 수 없는 attempt 상태: {status!r}")
        return findings

    for name in rules["required"]:
        if name not in record:
            fail(location, f"{status} attempt에 필수 필드가 없다: {name}")
    for name in rules["forbidden"]:
        if name in record:
            fail(f"{location}/{name}", f"{status} attempt에 있을 수 없는 필드다: {name}")

    outputs = record.get("outputs")
    if not isinstance(outputs, list):  # pragma: no cover - schema가 이미 거른다
        fail(f"{location}/outputs", "outputs가 배열이 아니다")
        return findings

    count = record.get("verified_artifact_count")
    total = record.get("verified_artifact_bytes")

    if status == "completed":
        if not outputs:
            # 이번 TASK의 stage 계약에는 zero-output stage가 없다. 빈 완료 record는
            # 완료 증거가 아니라 손상이다.
            fail(f"{location}/outputs", "completed attempt에 출력이 하나도 없다")
        if count != len(outputs):
            fail(
                f"{location}/verified_artifact_count",
                f"검증한 artifact 수({count})가 outputs 수({len(outputs)})와 다르다",
            )
        expected_bytes = sum(
            entry.get("byte_size", 0) for entry in outputs if isinstance(entry, dict)
        )
        if total != expected_bytes:
            fail(
                f"{location}/verified_artifact_bytes",
                f"검증한 byte 합({total})이 outputs의 byte_size 합({expected_bytes})과 다르다",
            )
    else:
        if outputs:
            fail(
                f"{location}/outputs",
                f"{status} attempt는 출력을 가질 수 없다 (완료하지 않았다)",
            )
        if count != 0:
            fail(f"{location}/verified_artifact_count", f"{status} attempt의 검증 수는 0이어야 한다")
        if total != 0:
            fail(f"{location}/verified_artifact_bytes", f"{status} attempt의 검증 byte는 0이어야 한다")

    if status in _TERMINAL_WITHOUT_OUTPUTS and record.get("cache_status") == "hit":
        fail(f"{location}/cache_status", f"{status} attempt가 hit로 기록됐다")

    # 저장된 error code는 선언된 안정 코드 집합에 속해야 한다 (REVIEW-019 M-01-R3).
    stored_code = record.get("error_code")
    if stored_code is not None and stored_code not in ERROR_CODES:
        fail(f"{location}/error_code", f"선언되지 않은 오류 코드다: {stored_code!r}")
    expected_code = _REQUIRED_ERROR_CODE.get(status)
    if expected_code is not None and stored_code != expected_code:
        fail(
            f"{location}/error_code",
            f"{status} attempt의 error_code는 {expected_code!r}여야 한다 (발견: {stored_code!r})",
        )

    return sort_findings(findings)


def check_attempt_identity(
    record: Mapping[str, Any],
    location: str,
    *,
    job_id: str,
    stage_id: str,
    file_stem: str,
) -> list[Finding]:
    """record 내부 정체성이 **실제 파일·job·stage**와 맞는지 검사한다.

    record 안의 상태만 보면 `a0001.json` 안에 `attempt_id="a9999"`를 써 넣어도 통과한다.
    그러면 cache hit가 성립하고 manifest가 존재하지 않는 attempt 파일을 가리킨다
    (REVIEW-019 M-01-R1).
    """

    findings: list[Finding] = []

    def fail(where: str, message: str) -> None:
        findings.append(Finding(where, "E_CHECKPOINT_INVALID", message))

    if record.get("job_id") != job_id:
        fail(
            f"{location}/job_id",
            f"record의 job_id가 현재 job과 다르다 (기대 {job_id!r}, 발견 {record.get('job_id')!r})",
        )
    if record.get("stage_id") != stage_id:
        fail(
            f"{location}/stage_id",
            f"record의 stage_id가 현재 stage와 다르다 "
            f"(기대 {stage_id!r}, 발견 {record.get('stage_id')!r})",
        )

    attempt_id = record.get("attempt_id")
    if attempt_id != file_stem:
        fail(
            f"{location}/attempt_id",
            f"record의 attempt_id가 파일 이름과 다르다 "
            f"(파일 {file_stem!r}, 발견 {attempt_id!r})",
        )
        return sort_findings(findings)

    match = _ATTEMPT_ID_RE.match(attempt_id) if isinstance(attempt_id, str) else None
    if match is None:
        fail(f"{location}/attempt_id", "계약된 aNNNN 모양이 아니다")
        return sort_findings(findings)
    if int(match.group(1)) != record.get("attempt_number"):
        fail(
            f"{location}/attempt_number",
            f"attempt_number({record.get('attempt_number')!r})가 "
            f"attempt_id {attempt_id!r}의 숫자와 다르다",
        )
    return sort_findings(findings)


def check_attempt_uniqueness(
    records: Sequence[tuple[Path, Mapping[str, Any]]], relative: Callable[[Path], str]
) -> list[Finding]:
    """같은 stage 디렉터리에서 attempt ID·number 중복을 거부한다."""

    findings: list[Finding] = []
    seen_ids: dict[str, str] = {}
    seen_numbers: dict[int, str] = {}
    for path, record in records:
        location = relative(path)
        attempt_id = record.get("attempt_id")
        number = record.get("attempt_number")
        if isinstance(attempt_id, str):
            if attempt_id in seen_ids:
                findings.append(
                    Finding(
                        f"{location}/attempt_id",
                        "E_CHECKPOINT_INVALID",
                        f"attempt_id {attempt_id!r}가 중복이다 (먼저: {seen_ids[attempt_id]})",
                    )
                )
            else:
                seen_ids[attempt_id] = location
        if isinstance(number, int):
            if number in seen_numbers:
                findings.append(
                    Finding(
                        f"{location}/attempt_number",
                        "E_CHECKPOINT_INVALID",
                        f"attempt_number {number}가 중복이다 (먼저: {seen_numbers[number]})",
                    )
                )
            else:
                seen_numbers[number] = location
    return sort_findings(findings)


def _check_identifier(value: str, location: str) -> None:
    reason = path_segment_error(value)
    if reason is not None:
        raise ContractViolation("E_UNSAFE_PATH", location, f"안전한 경로 구간이 아니다: {reason}")


def deterministic_order(spec: JobSpec) -> tuple[str, ...]:
    """결정적 topological 실행 순서.

    준비된 stage가 여러 개면 **선언 순서**로 고른다. 집합 순회 순서에 의존하지 않는다.
    """

    order_index = {stage.stage_id: index for index, stage in enumerate(spec.stages)}
    remaining = {stage.stage_id: set(stage.depends_on) for stage in spec.stages}
    resolved: list[str] = []
    while remaining:
        ready = sorted(
            (stage_id for stage_id, deps in remaining.items() if not deps),
            key=lambda stage_id: order_index[stage_id],
        )
        if not ready:
            cycle = sorted(remaining)
            raise ContractViolation(
                "E_DAG_CYCLE",
                f"dag/{order_index[cycle[0]]}",
                f"의존 cycle을 해소할 수 없다: {', '.join(cycle)}",
            )
        for stage_id in ready:
            resolved.append(stage_id)
            del remaining[stage_id]
        for deps in remaining.values():
            deps.difference_update(ready)
    return tuple(resolved)


def check_seed_inputs(
    seed_inputs: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    known_stages: Sequence[str],
    validator: SchemaValidator,
    store: ArtifactStore | None = None,
) -> None:
    """외부에서 들어온 seed `ArtifactRef`를 **filesystem을 바꾸기 전에** 검사한다.

    `seed_inputs`는 public API의 외부 입력 통로다. 검사 없이 `content_hash`를 바로
    indexing하면 raw `KeyError`가 밖으로 새고, 그 전에 job 디렉터리까지 만들어진다
    (REVIEW-018 M-05).

    위치는 `seed_inputs/<stage>/<index>` 이하로, 실제 입력에서 해석된다.
    """

    if seed_inputs is None:
        return
    if not isinstance(seed_inputs, Mapping):
        raise ContractViolation("E_SCHEMA", "seed_inputs", "seed_inputs는 매핑이어야 한다")

    # `sorted()`는 key 타입이 섞이면 raw TypeError를 낸다. 정렬 **전에** 모든 key의
    # 타입과 값을 검사한다 (REVIEW-019 M-05-R1). 사유에 key 값을 복제하지 않는다.
    for key in seed_inputs:
        if not isinstance(key, str):
            raise ContractViolation(
                "E_SCHEMA",
                "seed_inputs",
                f"stage key는 문자열이어야 한다 ({type(key).__name__} 발견)",
            )
        reason = path_segment_error(key)
        if reason is not None:
            raise ContractViolation(
                "E_SCHEMA", "seed_inputs", f"안전한 stage 식별자가 아닌 key다: {reason}"
            )

    for stage_id in sorted(seed_inputs):
        location = f"seed_inputs/{stage_id}"
        if stage_id not in known_stages:
            raise ContractViolation("E_SCHEMA", location, "DAG에 없는 stage의 seed 입력이다")
        entries = seed_inputs[stage_id]
        if not isinstance(entries, (list, tuple)):
            raise ContractViolation("E_SCHEMA", location, "seed 입력은 배열이어야 한다")
        for index, entry in enumerate(entries):
            where = f"{location}/{index}"
            if not isinstance(entry, Mapping):
                raise ContractViolation("E_SCHEMA", where, "seed 입력 항목은 객체여야 한다")
            findings = sort_findings(
                validator.validate(dict(entry), COMMON_SCHEMA_FILE, where, ARTIFACT_REF_POINTER)
            )
            if findings:
                first = findings[0]
                raise ContractViolation(
                    "E_SCHEMA", first.location, f"seed ArtifactRef schema 위반: {first.message}"
                )
            if store is not None:
                # runtime은 seed artifact를 실제로 읽어 stage에 넘긴다. 존재·hash·size도
                # mutation 전에 확인한다.
                store.verify_ref(entry, where)


def preflight(
    spec: JobSpec,
    project_root: Path,
    seed_inputs: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    validator: SchemaValidator | None = None,
    store: ArtifactStore | None = None,
) -> tuple[str, ...]:
    """DAG·식별자·경로·seed 입력을 검사하고 결정적 실행 순서를 돌려준다.

    이 함수는 **어떤 파일도 만들지 않는다.** 실패하면 filesystem은 그대로다.
    """

    _check_identifier(spec.job_id, "job_id")
    _check_identifier(spec.pipeline_id, "pipeline_id")

    # source_identity는 호출자가 주는 불투명 식별자다. 외부 절대 경로가 manifest에
    # 복제되지 않도록 mutation 전에 거부한다 (REVIEW-018 M-03).
    if spec.source_identity is not None:
        reason = opaque_identity_error(spec.source_identity)
        if reason is not None:
            raise ContractViolation(
                "E_UNSAFE_PATH",
                "source_identity",
                f"비민감 불투명 식별자가 아니다: {reason}",
            )

    reason = relative_path_error(spec.jobs_root)
    if reason is not None:
        raise ContractViolation("E_UNSAFE_PATH", "jobs_root", f"portable relative path가 아니다: {reason}")
    # symlink를 통한 root 탈출까지 확인한다. 디렉터리를 만들지는 않는다.
    resolve_inside_root(project_root, spec.jobs_root, "jobs_root")

    if not spec.stages:
        raise ContractViolation("E_DAG_DEPENDENCY", "dag", "stage가 하나도 없다")

    seen: set[str] = set()
    for index, stage in enumerate(spec.stages):
        _check_identifier(stage.stage_id, f"dag/{index}/stage_id")
        if stage.stage_id in seen:
            raise ContractViolation(
                "E_DAG_DUPLICATE_STAGE",
                f"dag/{index}/stage_id",
                f"중복 stage ID: {stage.stage_id}",
            )
        seen.add(stage.stage_id)
        if not stage.implementation_version:
            raise ContractViolation(
                "E_SCHEMA", f"dag/{index}/implementation_version", "implementation_version이 비었다"
            )

    for index, stage in enumerate(spec.stages):
        for position, dependency in enumerate(stage.depends_on):
            if dependency not in seen:
                raise ContractViolation(
                    "E_DAG_DEPENDENCY",
                    f"dag/{index}/depends_on/{position}",
                    f"존재하지 않는 dependency: {dependency}",
                )
            if dependency == stage.stage_id:
                raise ContractViolation(
                    "E_DAG_CYCLE", f"dag/{index}/depends_on/{position}", "자기 자신에 의존한다"
                )

    if validator is not None:
        check_seed_inputs(seed_inputs, tuple(seen), validator, store)

    return deterministic_order(spec)


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------


def job_fingerprint(spec: JobSpec) -> str:
    """job-level identity — 기존 job에 이어 쓸 수 있는지를 정한다.

    개별 stage의 config/model/context/implementation은 **들어가지 않는다.** 그것들이
    바뀌면 job resume이 거부되는 것이 아니라 해당 stage와 downstream이 cache miss가 된다.
    """

    return canonical_hash(
        {
            "kind": "job_fingerprint",
            "runtime_version": RUNTIME_VERSION,
            "schema_version": SCHEMA_VERSION,
            "pipeline_id": spec.pipeline_id,
            "source_identity": spec.source_identity,
            "dag": [
                {"stage_id": stage.stage_id, "depends_on": sorted(stage.depends_on)}
                for stage in spec.stages
            ],
        }
    )


#: cache key canonical 문서가 **반드시** 담아야 하는 key. 선택 항목이 없더라도
#: 필드 자체는 남고 값이 null이 된다 — 부재가 곧 canonical 값이다 (§3.3).
CACHE_KEY_FIELDS = (
    "chunking_hash",
    "config_hash",
    "context_hash",
    "dependency_cache_keys",
    "dependency_fingerprint",
    "implementation_version",
    "input_artifact_hashes",
    "kind",
    "model_hash",
    "pipeline_id",
    "random_seed",
    "reproducibility_tier",
    "runtime_version",
    "schema_version",
    "source_hash",
    "stage_id",
)


def stage_cache_key_document(
    spec: JobSpec,
    stage: StageSpec,
    input_artifact_hashes: Sequence[str],
    dependency_cache_keys: Mapping[str, str],
) -> dict[str, Any]:
    """cache key를 만드는 canonical 문서.

    선택 항목은 값이 없어도 **key를 남기고 null을 넣는다.** 조용히 빼면 canonical
    바이트가 달라져 기존 cache가 통째로 무효가 되고, "부재 자체가 canonical 값"이라는
    §3.3 계약이 깨진다. 테스트가 `CACHE_KEY_FIELDS`로 이 모양을 고정한다.

    path·mtime·파일명은 절대 들어가지 않는다.
    """

    return {
        "kind": "stage_cache_key",
        "runtime_version": RUNTIME_VERSION,
        "schema_version": SCHEMA_VERSION,
        "pipeline_id": spec.pipeline_id,
        "stage_id": stage.stage_id,
        "implementation_version": stage.implementation_version,
        "input_artifact_hashes": sorted(input_artifact_hashes),
        "config_hash": stage.config_hash,
        "dependency_fingerprint": stage.dependency_fingerprint,
        "source_hash": stage.source_hash,
        "chunking_hash": stage.chunking_hash,
        "model_hash": stage.model_hash,
        "context_hash": stage.context_hash,
        "random_seed": stage.random_seed,
        "reproducibility_tier": stage.reproducibility_tier,
        "dependency_cache_keys": dict(dependency_cache_keys),
    }


def stage_cache_key(
    spec: JobSpec,
    stage: StageSpec,
    input_artifact_hashes: Sequence[str],
    dependency_cache_keys: Mapping[str, str],
) -> str:
    """stage cache key — canonical JSON 바이트의 SHA-256.

    `dependency_cache_keys`가 들어가므로, upstream fingerprint가 바뀌면 출력 바이트가
    우연히 같아도 downstream은 miss가 된다 (§3.5).
    """

    return canonical_hash(
        stage_cache_key_document(spec, stage, input_artifact_hashes, dependency_cache_keys)
    )


def _fingerprint_fields(stage: StageSpec) -> dict[str, Any]:
    """attempt record에 남길 **제공된** fingerprint만. 없는 항목은 필드를 두지 않는다."""

    fields: dict[str, Any] = {"implementation_version": stage.implementation_version}
    for name in (
        "config_hash",
        "dependency_fingerprint",
        "source_hash",
        "chunking_hash",
        "model_hash",
        "context_hash",
        "random_seed",
    ):
        value = getattr(stage, name)
        if value is not None:
            fields[name] = value
    return fields


# ---------------------------------------------------------------------------
# metadata 원자적 기록 — CAS object가 아니라 상태 전이에만 쓴다.
# ---------------------------------------------------------------------------


def write_json_atomic(path: Path, payload: Any) -> None:
    """같은 디렉터리의 임시 파일 + atomic replace.

    **CAS 최종 object에는 절대 쓰지 않는다.** 여기서 다루는 것은 manifest와 attempt
    record 같은 상태 metadata뿐이며, 정상 상태 전이는 덮어쓰기가 맞다 (§3.4-12).
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.tmp"
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False)
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


# ---------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------


class JobRuntime:
    """local synchronous stage runtime.

    한 프로세스 안에서 순차 실행한다. worker supervision·멀티프로세스 scheduler는
    이 TASK의 범위 밖이다 (§6).
    """

    def __init__(self, project_root: Path, schemas: SchemaSet | None = None):
        self.project_root = Path(project_root).resolve()
        self.store = ArtifactStore(self.project_root)
        self.schemas = schemas or job_schema_set()
        self.validator = SchemaValidator(self.schemas)

    # -- 경로 -------------------------------------------------------------

    def job_dir(self, spec: JobSpec) -> Path:
        return resolve_inside_root(
            self.project_root, f"{spec.jobs_root}/{spec.job_id}", "job_dir"
        )

    def manifest_path(self, spec: JobSpec) -> Path:
        return self.job_dir(spec) / "manifest.json"

    def attempts_dir(self, spec: JobSpec, stage_id: str) -> Path:
        return self.job_dir(spec) / "stages" / stage_id / "attempts"

    def work_dir(self, spec: JobSpec, stage_id: str, attempt_id: str) -> Path:
        return self.job_dir(spec) / "stages" / stage_id / "work" / attempt_id

    def relative(self, path: Path) -> str:
        return path.relative_to(self.project_root).as_posix()

    # -- schema -----------------------------------------------------------

    def validate_manifest(self, manifest: Any, location: str) -> list[Finding]:
        return sort_findings(self.validator.validate(manifest, JOB_SCHEMA_FILE, location))

    def validate_attempt(self, record: Any, location: str) -> list[Finding]:
        return sort_findings(
            self.validator.validate(record, JOB_SCHEMA_FILE, location, ATTEMPT_RECORD_POINTER)
        )

    def check_manifest_semantics(
        self, manifest: Mapping[str, Any], spec: JobSpec, location: str
    ) -> list[Finding]:
        """기존 manifest가 현재 spec·실제 attempt graph와 모순되지 않는지 검사한다.

        schema만으로는 job identity·pipeline·완료 stage 집합이 모순인 manifest가 통과하고,
        그 위에 조용히 덮어써진다 (REVIEW-019 M-01-R2). `job_fingerprint` 자체의 불일치는
        호출자가 `E_RESUME_FINGERPRINT`로 먼저 처리하므로 여기서는 다루지 않는다.
        """

        findings: list[Finding] = []

        def fail(where: str, message: str) -> None:
            findings.append(Finding(where, "E_CHECKPOINT_INVALID", message))

        for field, expected in (
            ("schema_version", SCHEMA_VERSION),
            ("runtime_version", RUNTIME_VERSION),
            ("job_id", spec.job_id),
            ("pipeline_id", spec.pipeline_id),
        ):
            if manifest.get(field) != expected:
                fail(
                    f"{location}/{field}",
                    f"{field}가 현재 job과 다르다 (기대 {expected!r}, 발견 {manifest.get(field)!r})",
                )

        # source_identity는 **존재 여부까지** 일치해야 한다.
        if ("source_identity" in manifest) != (spec.source_identity is not None):
            fail(
                f"{location}/source_identity",
                "source_identity의 존재 여부가 현재 job과 다르다",
            )
        elif spec.source_identity is not None and manifest.get("source_identity") != spec.source_identity:
            fail(f"{location}/source_identity", "source_identity 값이 현재 job과 다르다")

        declared = [
            {"stage_id": stage.stage_id, "depends_on": list(stage.depends_on)}
            for stage in spec.stages
        ]
        if manifest.get("dag") != declared:
            fail(f"{location}/dag", "DAG topology 또는 선언 순서가 현재 job과 다르다")

        dag_stage_ids = {stage.stage_id for stage in spec.stages}
        states = manifest.get("stages")
        if not isinstance(states, list):  # pragma: no cover - schema가 이미 거른다
            fail(f"{location}/stages", "stages가 배열이 아니다")
            return sort_findings(findings)

        seen: dict[str, int] = {}
        for index, state in enumerate(states):
            where = f"{location}/stages/{index}"
            stage_id = state.get("stage_id")
            if stage_id not in dag_stage_ids:
                fail(f"{where}/stage_id", f"DAG에 없는 stage다: {stage_id!r}")
                continue
            if stage_id in seen:
                fail(
                    f"{where}/stage_id",
                    f"stage state가 중복이다: {stage_id!r} (먼저: stages/{seen[stage_id]})",
                )
                continue
            seen[stage_id] = index
            findings.extend(self._check_stage_state(state, spec, where))

        if manifest.get("status") == "completed":
            missing = sorted(dag_stage_ids - set(seen))
            if missing:
                fail(
                    f"{location}/stages",
                    f"completed manifest에 없는 stage가 있다: {', '.join(missing)}",
                )
            for stage_id, index in sorted(seen.items()):
                if states[index].get("attempt_status") != "completed":
                    fail(
                        f"{location}/stages/{index}/attempt_status",
                        "completed manifest의 stage가 completed attempt를 가리키지 않는다",
                    )

        return sort_findings(findings)

    def _check_stage_state(
        self, state: Mapping[str, Any], spec: JobSpec, location: str
    ) -> list[Finding]:
        """stage state가 **실제로 존재하는** attempt record와 일치하는지 확인한다."""

        findings: list[Finding] = []

        def fail(where: str, message: str) -> None:
            findings.append(Finding(where, "E_CHECKPOINT_INVALID", message))

        relative = state.get("attempt_path")
        if relative is None:
            fail(location, "stage state에 attempt_path가 없다")
            return findings
        reason = relative_path_error(relative)
        if reason is not None:
            fail(f"{location}/attempt_path", f"portable relative path가 아니다: {reason}")
            return findings

        path = resolve_inside_root(self.project_root, relative, f"{location}/attempt_path")
        if not path.is_file():
            fail(f"{location}/attempt_path", "가리키는 attempt record 파일이 없다")
            return findings

        try:
            record = load_strict(path)
        except JsonInputError as exc:
            fail(f"{location}/attempt_path", f"attempt record JSON 오류: {exc}")
            return findings
        if not isinstance(record, dict):
            fail(f"{location}/attempt_path", "attempt record가 객체가 아니다")
            return findings

        # 가리키는 record가 schema를 어기면 그것이 먼저다 — 코드를 E_SCHEMA로 보존한다.
        schema_findings = self.validate_attempt(record, self.relative(path))
        if schema_findings:
            return list(schema_findings)

        for field, state_field in (
            ("attempt_id", "attempt_id"),
            ("stage_id", "stage_id"),
            ("cache_key", "cache_key"),
        ):
            if record.get(field) != state.get(state_field):
                fail(
                    f"{location}/{state_field}",
                    f"manifest의 {state_field}가 실제 record와 다르다 "
                    f"(manifest {state.get(state_field)!r}, record {record.get(field)!r})",
                )
        if record.get("job_id") != spec.job_id:
            fail(f"{location}/attempt_path", "가리키는 record의 job_id가 현재 job과 다르다")
        if record.get("status") != state.get("attempt_status"):
            fail(
                f"{location}/attempt_status",
                f"manifest의 attempt_status가 실제 record status와 다르다 "
                f"(manifest {state.get('attempt_status')!r}, record {record.get('status')!r})",
            )
        return findings

    def _require_semantic(self, findings: Sequence[Finding]) -> None:
        """semantic finding은 코드와 위치를 그대로 보존해 올린다."""

        if findings:
            first = findings[0]
            raise ContractViolation(first.code, first.location, first.message)

    def _require_valid(self, findings: Sequence[Finding], what: str) -> None:
        if findings:
            first = findings[0]
            code = first.code if first.code in ERROR_CODES else "E_SCHEMA"
            raise ContractViolation(code, first.location, f"{what}: {first.message}")

    # -- attempt record ---------------------------------------------------

    def _read_attempts(self, spec: JobSpec, stage_id: str) -> list[tuple[Path, dict[str, Any]]]:
        directory = self.attempts_dir(spec, stage_id)
        if not directory.is_dir():
            return []
        records: list[tuple[Path, dict[str, Any]]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                record = load_strict(path)
            except JsonInputError as exc:
                raise ContractViolation(
                    "E_CHECKPOINT_INVALID", self.relative(path), f"attempt record JSON 오류: {exc}"
                ) from exc
            location = self.relative(path)
            self._require_valid(self.validate_attempt(record, location), "attempt record")
            # schema를 통과해도 의미상 완료되지 않은 record가 있다. cache lookup **전에**
            # 걸러야 거짓 hit가 생기지 않는다 (REVIEW-018 M-01).
            self._require_semantic(check_attempt_semantics(record, location))
            # record 내부 ID가 실제 파일·job·stage와 맞는지도 함께 본다 (REVIEW-019 M-01-R1).
            self._require_semantic(
                check_attempt_identity(
                    record,
                    location,
                    job_id=spec.job_id,
                    stage_id=stage_id,
                    file_stem=path.stem,
                )
            )
            records.append((path, record))
        self._require_semantic(check_attempt_uniqueness(records, self.relative))
        return records

    def _next_attempt_id(self, records: Sequence[tuple[Path, dict[str, Any]]]) -> tuple[str, int]:
        number = max((record["attempt_number"] for _, record in records), default=0) + 1
        return f"a{number:04d}", number

    def _preserve_running_attempts(
        self, spec: JobSpec, stage_id: str, records: Sequence[tuple[Path, dict[str, Any]]]
    ) -> list[str]:
        """남아 있는 `running` record를 **지우지 않고** `interrupted`로 전이한다.

        기존 attempt ID를 새 실행이 재사용하지 않는다 (§3.4-10).
        """

        preserved: list[str] = []
        for path, record in records:
            if record["status"] != "running":
                continue
            location = self.relative(path)
            transitioned = dict(record)
            transitioned["status"] = "interrupted"
            transitioned["error_code"] = "E_STATE_TRANSITION"
            transitioned["error_location"] = location
            # 언제 죽었는지는 관측하지 못했다. 전이를 **관측한** 시각만 남기고
            # ended_at·duration을 지어내지 않는다 (REVIEW-018 M-02).
            transitioned["interrupted_at"] = utc_now()
            self._require_valid(self.validate_attempt(transitioned, location), "attempt record")
            self._require_valid(
                check_attempt_semantics(transitioned, location), "interrupted attempt record"
            )
            write_json_atomic(path, transitioned)
            preserved.append(record["attempt_id"])
        return preserved

    # -- cache ------------------------------------------------------------

    def _lookup_cache(
        self,
        spec: JobSpec,
        stage: StageSpec,
        cache_key: str,
        records: Sequence[tuple[Path, dict[str, Any]]],
    ) -> tuple[str, str, tuple[Path, dict[str, Any]] | None]:
        """`(cache_status, cache_reason, (path, record))`.

        **completed record만** 후보다. `running` record는 어떤 경우에도 hit가 되지 않는다.
        전역 cross-job cache index는 만들지 않는다 — 같은 job의 기록만 본다.

        후보는 **실제 `(path, record)` 연결을 유지한 채** 돌려준다. record만 넘기면
        호출자가 record 내부 ID로 경로를 다시 만들게 되고, 그 ID가 조작되면 존재하지
        않는 파일을 가리키게 된다 (REVIEW-019 M-01-R1).
        """

        if not stage.cacheable:
            return "bypassed", "not_cacheable", None

        completed = [(path, record) for path, record in records if record["status"] == "completed"]
        if not completed:
            return "miss", "no_completed_checkpoint", None
        for path, record in completed:
            if record["cache_key"] == cache_key:
                return "hit", "verified_checkpoint", (path, record)
        return "miss", "cache_key_changed", None

    def _verify_checkpoint(self, record: Mapping[str, Any], location: str) -> tuple[int, int]:
        """hit 후보의 모든 출력 artifact를 다시 열어 확인한다.

        누락·손상이면 hit로 쓰지 않고 안정 오류로 실패한다. 기존 evidence는 건드리지 않는다.
        """

        if record["status"] != "completed":
            raise ContractViolation(
                "E_CHECKPOINT_INVALID", location, "completed가 아닌 attempt를 hit로 쓸 수 없다"
            )
        count = 0
        total = 0
        for index, ref in enumerate(record["outputs"]):
            total += self.store.verify_ref(ref, f"{location}/outputs/{index}")
            count += 1
        return count, total

    # -- 실행 -------------------------------------------------------------

    def run_job(
        self,
        spec: JobSpec,
        callables: Mapping[str, StageCallable],
        *,
        injection: FailureInjection | None = None,
        seed_inputs: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> JobResult:
        """DAG를 결정적 순서로 실행한다.

        `seed_inputs`는 dependency가 없는 stage에 외부 입력 `ArtifactRef`를 주는 통로다.
        `callables`는 stage ID → callable. cache hit인 stage의 callable은 호출되지 않는다.
        """

        order = preflight(spec, self.project_root, seed_inputs, self.validator, self.store)
        stages = {stage.stage_id: stage for stage in spec.stages}
        fingerprint = job_fingerprint(spec)

        manifest_path = self.manifest_path(spec)
        if manifest_path.is_file():
            existing = self._load_manifest(manifest_path)
            if existing["job_fingerprint"] != fingerprint:
                raise ContractViolation(
                    "E_RESUME_FINGERPRINT",
                    "job_fingerprint",
                    "job fingerprint가 기존 job과 다르다 — 새 job ID를 사용해야 한다",
                )
            # fingerprint가 같아도 manifest 자체가 모순일 수 있다. 사용하거나
            # 덮어쓰기 **전에** 거부한다 (REVIEW-019 M-01-R2).
            self._require_semantic(
                self.check_manifest_semantics(existing, spec, self.relative(manifest_path))
            )

        # preflight를 통과한 뒤에야 디렉터리를 만든다.
        self.job_dir(spec).mkdir(parents=True, exist_ok=True)

        outcomes: dict[str, StageOutcome] = {}
        produced: dict[str, tuple[Mapping[str, Any], ...]] = {}
        keys: dict[str, str] = {}
        #: 이번 실행이 새로 쓴 attempt record. 비어 있으면 새 evidence가 없다는 뜻이므로
        #: 실패해도 기존 manifest를 건드리지 않는다 (REVIEW-019 M-01-R1/R2).
        progress: list[str] = []

        try:
            for stage_id in order:
                stage = stages[stage_id]
                inputs = self._collect_inputs(stage, produced, seed_inputs)
                cache_key = stage_cache_key(
                    spec,
                    stage,
                    [ref["content_hash"] for ref in inputs],
                    {dependency: keys[dependency] for dependency in stage.depends_on},
                )
                keys[stage_id] = cache_key
                outcome = self._run_stage(
                    spec, stage, cache_key, inputs, callables, injection, progress
                )
                outcomes[stage_id] = outcome
                produced[stage_id] = outcome.outputs
                self._write_manifest(spec, fingerprint, "running", order, outcomes)
        except ContractViolation:
            if progress:
                # 이번 실행이 실제로 남긴 evidence가 있을 때만 실패 상태를 기록한다.
                self._write_manifest(spec, fingerprint, "failed", order, outcomes)
            raise

        status = "completed"
        self._write_manifest(spec, fingerprint, status, order, outcomes)
        return JobResult(
            job_id=spec.job_id,
            status=status,
            job_fingerprint=fingerprint,
            stages=tuple(outcomes[stage_id] for stage_id in order),
        )

    def _collect_inputs(
        self,
        stage: StageSpec,
        produced: Mapping[str, tuple[Mapping[str, Any], ...]],
        seed_inputs: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    ) -> tuple[Mapping[str, Any], ...]:
        refs: list[Mapping[str, Any]] = []
        for dependency in stage.depends_on:
            refs.extend(produced[dependency])
        if seed_inputs is not None:
            refs.extend(seed_inputs.get(stage.stage_id, ()))
        return tuple(refs)

    def _run_stage(
        self,
        spec: JobSpec,
        stage: StageSpec,
        cache_key: str,
        inputs: tuple[Mapping[str, Any], ...],
        callables: Mapping[str, StageCallable],
        injection: FailureInjection | None,
        progress: list[str],
    ) -> StageOutcome:
        records = self._read_attempts(spec, stage.stage_id)
        # cache hit 여부와 **무관하게** 남아 있는 running attempt를 먼저 interrupted로
        # 보존한다. hit를 먼저 돌려주면 running record가 영원히 running으로 남는다
        # (REVIEW-018 M-02).
        if self._preserve_running_attempts(spec, stage.stage_id, records):
            records = self._read_attempts(spec, stage.stage_id)
        cache_status, cache_reason, hit = self._lookup_cache(spec, stage, cache_key, records)

        if hit is not None:
            hit_path, hit_record = hit
            location = self.relative(hit_path)
            count, total = self._verify_checkpoint(hit_record, location)
            return StageOutcome(
                stage_id=stage.stage_id,
                cache_status=cache_status,
                cache_reason=cache_reason,
                cache_key=cache_key,
                attempt_id=hit_record["attempt_id"],
                attempt_status="completed",
                attempt_path=location,
                callable_invoked=False,
                outputs=tuple(hit_record["outputs"]),
                verified_artifact_count=count,
                verified_artifact_bytes=total,
            )

        attempt_id, attempt_number = self._next_attempt_id(records)
        attempt_path = self.attempts_dir(spec, stage.stage_id) / f"{attempt_id}.json"

        started_at = utc_now()
        started_monotonic = time.monotonic()
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": RUNTIME_VERSION,
            "job_id": spec.job_id,
            "stage_id": stage.stage_id,
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "status": "running",
            "cache_status": cache_status,
            "cache_reason": cache_reason,
            "cache_key": cache_key,
            "cacheable": stage.cacheable,
            "callable_invoked": False,
            "started_at": started_at,
            "fingerprints": _fingerprint_fields(stage),
            "inputs": [dict(ref) for ref in inputs],
            "outputs": [],
            "verified_artifact_count": 0,
            "verified_artifact_bytes": 0,
            "temp_paths": [],
        }
        if stage.reproducibility_tier is not None:
            record["reproducibility_tier"] = stage.reproducibility_tier

        # 4. callable을 부르기 **전에** running attempt를 원자적으로 기록한다.
        self._require_valid(self.validate_attempt(record, self.relative(attempt_path)), "attempt record")
        write_json_atomic(attempt_path, record)
        progress.append(self.relative(attempt_path))

        workspace = self.work_dir(spec, stage.stage_id, attempt_id)
        workspace.mkdir(parents=True, exist_ok=True)
        context = StageContext(
            job_id=spec.job_id,
            stage_id=stage.stage_id,
            attempt_id=attempt_id,
            workspace=workspace,
            inputs=inputs,
            input_paths=tuple(
                self.store.absolute(ref["uri"], f"inputs/{index}/uri")
                for index, ref in enumerate(inputs)
            ),
        )

        callable_ = callables.get(stage.stage_id)
        if callable_ is None:
            self._fail_attempt(
                attempt_path,
                record,
                started_monotonic,
                "E_STAGE_FAILED",
                self.relative(attempt_path),
            )
            raise ContractViolation(
                "E_STAGE_FAILED", self.relative(attempt_path), "stage callable이 등록되지 않았다"
            )

        record["callable_invoked"] = True
        try:
            outputs = list(callable_(context))
        except InjectedInterrupt:
            # 프로세스가 죽은 것을 흉내 낸다 — record는 running 그대로 남는다.
            raise
        except ContractViolation as error:
            self._fail_attempt(
                attempt_path,
                record,
                started_monotonic,
                error.code,
                error.location,
                self.store.surviving_temp_paths(error.temp_paths),
            )
            raise
        except Exception as exc:
            self._fail_attempt(
                attempt_path,
                record,
                started_monotonic,
                "E_STAGE_FAILED",
                self.relative(attempt_path),
            )
            raise ContractViolation(
                "E_STAGE_FAILED",
                self.relative(attempt_path),
                f"stage callable이 실패했다: {type(exc).__name__}",
            ) from exc

        refs: list[Mapping[str, Any]] = []
        temp_paths: list[str] = []
        try:
            for output in sorted(outputs, key=lambda item: item.name):
                written = self.store.add_file(
                    output.path,
                    job_id=spec.job_id,
                    stage_id=stage.stage_id,
                    kind=output.kind,
                    media_type=output.media_type,
                    injection=injection,
                )
                temp_paths.append(written.temp_relative_path)
                refs.append(written.ref)
        except InjectedInterrupt:
            raise
        except ContractViolation as error:
            # 실패로 **실제 남은** temp만 기록한다. 성공 뒤 정리된 이름은 증거가 아니다.
            self._fail_attempt(
                attempt_path,
                record,
                started_monotonic,
                error.code,
                error.location,
                self.store.surviving_temp_paths(tuple(temp_paths) + error.temp_paths),
            )
            raise

        if injection is not None and injection.after_stage_outputs is not None:
            injection.after_stage_outputs(tuple(refs))

        # 6. 승격된 artifact를 **다시 열어** 검증한 뒤에야 completed로 전이한다.
        verified_count = 0
        verified_bytes = 0
        try:
            for index, ref in enumerate(refs):
                verified_bytes += self.store.verify_ref(ref, f"outputs/{index}")
                verified_count += 1
        except ContractViolation as error:
            # 실패로 **실제 남은** temp만 기록한다. 성공 뒤 정리된 이름은 증거가 아니다.
            self._fail_attempt(
                attempt_path,
                record,
                started_monotonic,
                error.code,
                error.location,
                self.store.surviving_temp_paths(tuple(temp_paths) + error.temp_paths),
            )
            raise

        if injection is not None and injection.before_completed_write is not None:
            injection.before_completed_write(attempt_id)

        record["status"] = "completed"
        record["outputs"] = [dict(ref) for ref in refs]
        record["verified_artifact_count"] = verified_count
        record["verified_artifact_bytes"] = verified_bytes
        record["ended_at"] = utc_now()
        record["wall_duration_seconds"] = round(time.monotonic() - started_monotonic, 6)
        self._require_valid(self.validate_attempt(record, self.relative(attempt_path)), "attempt record")
        write_json_atomic(attempt_path, record)

        return StageOutcome(
            stage_id=stage.stage_id,
            cache_status=cache_status,
            cache_reason=cache_reason,
            cache_key=cache_key,
            attempt_id=attempt_id,
            attempt_status="completed",
            attempt_path=self.relative(attempt_path),
            callable_invoked=True,
            outputs=tuple(refs),
            verified_artifact_count=verified_count,
            verified_artifact_bytes=verified_bytes,
        )

    def _fail_attempt(
        self,
        attempt_path: Path,
        record: dict[str, Any],
        started_monotonic: float,
        error_code: str,
        error_location: str,
        temp_paths: Sequence[str] = (),
    ) -> None:
        """실패 evidence를 남긴다. completed checkpoint는 만들지 않는다.

        안정 code·location과 **실제로 보존된** temp 경로를 함께 남겨야 복구·QC 증거가
        된다. 파일만 orphan으로 남기는 것은 증거가 아니다 (REVIEW-018 M-04).
        """

        record["status"] = "failed"
        record["error_code"] = error_code
        record["error_location"] = error_location
        record["temp_paths"] = list(temp_paths)
        record["ended_at"] = utc_now()
        record["wall_duration_seconds"] = round(time.monotonic() - started_monotonic, 6)
        location = self.relative(attempt_path)
        self._require_valid(self.validate_attempt(record, location), "failed attempt record")
        self._require_valid(check_attempt_semantics(record, location), "failed attempt record")
        write_json_atomic(attempt_path, record)

    # -- manifest ---------------------------------------------------------

    def _load_manifest(self, path: Path) -> dict[str, Any]:
        try:
            manifest = load_strict(path)
        except JsonInputError as exc:
            raise ContractViolation(
                "E_CHECKPOINT_INVALID", self.relative(path), f"manifest JSON 오류: {exc}"
            ) from exc
        self._require_valid(self.validate_manifest(manifest, self.relative(path)), "manifest")
        return manifest

    def _write_manifest(
        self,
        spec: JobSpec,
        fingerprint: str,
        status: str,
        order: Sequence[str],
        outcomes: Mapping[str, StageOutcome],
    ) -> None:
        path = self.manifest_path(spec)
        created_at = utc_now()
        if path.is_file():
            created_at = self._load_manifest(path)["created_at"]
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": RUNTIME_VERSION,
            "job_id": spec.job_id,
            "pipeline_id": spec.pipeline_id,
            "status": status,
            "created_at": created_at,
            "updated_at": utc_now(),
            "job_fingerprint": fingerprint,
            "dag": [
                {"stage_id": stage.stage_id, "depends_on": list(stage.depends_on)}
                for stage in spec.stages
            ],
            "stages": [
                {
                    "stage_id": stage_id,
                    "cache_key": outcomes[stage_id].cache_key,
                    "cache_status": outcomes[stage_id].cache_status,
                    "cache_reason": outcomes[stage_id].cache_reason,
                    "attempt_id": outcomes[stage_id].attempt_id,
                    "attempt_status": outcomes[stage_id].attempt_status,
                    # record 내부 ID에서 경로를 다시 만들지 않는다. 실제로 읽거나 쓴
                    # 파일 경로만 기록한다 (REVIEW-019 M-01-R1).
                    "attempt_path": outcomes[stage_id].attempt_path,
                }
                for stage_id in order
                if stage_id in outcomes
            ],
        }
        if spec.source_identity is not None:
            manifest["source_identity"] = spec.source_identity
        self._require_valid(self.validate_manifest(manifest, self.relative(path)), "manifest")
        write_json_atomic(path, manifest)


# ---------------------------------------------------------------------------
# J-01~J-16 fixture scenario driver
#
# 아래 driver는 **production API만** 호출한다. fixture의 expected 값을 읽어
# 그대로 통과시키지 않는다 — 관측값은 전부 실제 실행 결과다.
# ---------------------------------------------------------------------------


def _write_source(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _emit(text: str, name: str = "out.txt") -> StageCallable:
    def run(context: StageContext) -> Sequence[StageOutput]:
        target = context.workspace / name
        target.write_text(text, encoding="utf-8")
        return [StageOutput(name=name, path=target)]

    return run


def _counting(text: str, counter: list[int], name: str = "out.txt") -> StageCallable:
    def run(context: StageContext) -> Sequence[StageOutput]:
        counter[0] += 1
        target = context.workspace / name
        target.write_text(text, encoding="utf-8")
        return [StageOutput(name=name, path=target)]

    return run


def _simple_spec(**overrides: Any) -> JobSpec:
    stage = StageSpec(
        stage_id="extract",
        implementation_version="extract/1.0.0",
        config_hash=canonical_hash({"config": "a"}),
        dependency_fingerprint=canonical_hash({"deps": "a"}),
        **overrides,
    )
    return JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(stage,), source_identity="src-1")


def _capture(error: ContractViolation) -> dict[str, Any]:
    return {"code": error.code, "location": error.location}


def _scenario_j01(root: Path) -> dict[str, Any]:
    """새 deterministic stage 성공 → artifact·completed attempt·manifest가 schema를 통과한다."""

    runtime = JobRuntime(root)
    spec = _simple_spec()
    result = runtime.run_job(spec, {"extract": _emit("hello")})
    outcome = result.outcome("extract")
    manifest = runtime._load_manifest(runtime.manifest_path(spec))
    attempt = load_strict(
        runtime.attempts_dir(spec, "extract") / f"{outcome.attempt_id}.json"
    )
    artifact = runtime.store.absolute(outcome.outputs[0]["uri"], "uri")
    return {
        "job_status": result.status,
        "cache_status": outcome.cache_status,
        "cache_reason": outcome.cache_reason,
        "attempt_status": attempt["status"],
        "callable_invoked": attempt["callable_invoked"],
        "manifest_status": manifest["status"],
        "manifest_schema_findings": len(
            runtime.validate_manifest(manifest, "manifest.json")
        ),
        "attempt_schema_findings": len(runtime.validate_attempt(attempt, "attempt.json")),
        "artifact_exists": artifact.is_file(),
        "artifact_uri_is_relative": relative_path_error(outcome.outputs[0]["uri"]) is None,
        "verified_artifact_count": outcome.verified_artifact_count,
    }


def _scenario_j02(root: Path) -> dict[str, Any]:
    """같은 입력·fingerprint 재실행 → callable 호출 없이 검증된 hit."""

    runtime = JobRuntime(root)
    spec = _simple_spec()
    calls = [0]
    runtime.run_job(spec, {"extract": _counting("hello", calls)})
    first_calls = calls[0]
    result = runtime.run_job(spec, {"extract": _counting("hello", calls)})
    outcome = result.outcome("extract")
    return {
        "first_calls": first_calls,
        "second_calls": calls[0] - first_calls,
        "cache_status": outcome.cache_status,
        "cache_reason": outcome.cache_reason,
        "callable_invoked": outcome.callable_invoked,
        "verified_artifact_count": outcome.verified_artifact_count,
    }


def _scenario_j03(root: Path) -> dict[str, Any]:
    """config·implementation·dependency·model·context·chunking를 하나씩 바꾸면 각각 miss."""

    observations: dict[str, Any] = {}
    for field_name, changed in (
        ("config_hash", canonical_hash({"config": "b"})),
        ("implementation_version", "extract/2.0.0"),
        ("dependency_fingerprint", canonical_hash({"deps": "b"})),
        ("model_hash", canonical_hash({"model": "b"})),
        ("context_hash", canonical_hash({"context": "b"})),
        ("chunking_hash", canonical_hash({"chunking": "b"})),
    ):
        directory = root / field_name
        directory.mkdir()
        runtime = JobRuntime(directory)
        spec = _simple_spec()
        runtime.run_job(spec, {"extract": _emit("hello")})
        changed_stage = StageSpec(
            **{**spec.stages[0].__dict__, field_name: changed}
        )
        changed_spec = JobSpec(
            job_id=spec.job_id,
            pipeline_id=spec.pipeline_id,
            stages=(changed_stage,),
            source_identity=spec.source_identity,
        )
        calls = [0]
        result = runtime.run_job(changed_spec, {"extract": _counting("hello", calls)})
        outcome = result.outcome("extract")
        observations[field_name] = {
            "cache_status": outcome.cache_status,
            "cache_reason": outcome.cache_reason,
            "calls": calls[0],
        }
    return observations


def _scenario_j04(root: Path) -> dict[str, Any]:
    """cacheable=false → 동일 fingerprint여도 bypassed로 실행하고 이유를 기록한다."""

    runtime = JobRuntime(root)
    stage = StageSpec(
        stage_id="extract",
        implementation_version="extract/1.0.0",
        config_hash=canonical_hash({"config": "a"}),
        cacheable=False,
    )
    spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(stage,))
    calls = [0]
    runtime.run_job(spec, {"extract": _counting("hello", calls)})
    result = runtime.run_job(spec, {"extract": _counting("hello", calls)})
    outcome = result.outcome("extract")
    attempt = load_strict(
        runtime.attempts_dir(spec, "extract") / f"{outcome.attempt_id}.json"
    )
    return {
        "calls": calls[0],
        "cache_status": outcome.cache_status,
        "cache_reason": outcome.cache_reason,
        "recorded_reason": attempt["cache_reason"],
        "cacheable": attempt["cacheable"],
    }


def _scenario_j05(root: Path) -> dict[str, Any]:
    """같은 hash·size의 기존 CAS object → dedupe하며 새 바이트를 덮어쓰지 않는다."""

    store = ArtifactStore(root)
    source = _write_source(root, "input/a.txt", "same bytes")
    first = store.add_file(source, job_id="job-a", stage_id="extract")
    target = store.absolute(first.ref["uri"], "uri")
    before = os.stat(target)

    other = _write_source(root, "input/b.txt", "same bytes")
    second = store.add_file(other, job_id="job-a", stage_id="extract")
    after = os.stat(target)
    return {
        "same_uri": first.ref["uri"] == second.ref["uri"],
        "first_deduped": first.deduped,
        "second_deduped": second.deduped,
        "inode_unchanged": before.st_ino == after.st_ino,
        "bytes_unchanged": before.st_size == after.st_size,
        "content_unchanged": target.read_text(encoding="utf-8") == "same bytes",
    }


def _scenario_j06(root: Path) -> dict[str, Any]:
    """손상된 기존 CAS object → hit로 쓰거나 덮어쓰지 않고 안정 오류."""

    store = ArtifactStore(root)
    source = _write_source(root, "input/a.txt", "original")
    written = store.add_file(source, job_id="job-a", stage_id="extract")
    target = store.absolute(written.ref["uri"], "uri")
    target.write_text("corrupted", encoding="utf-8")

    again = _write_source(root, "input/again.txt", "original")
    try:
        store.add_file(again, job_id="job-a", stage_id="extract")
    except ContractViolation as error:
        captured = _capture(error)
    else:
        captured = {"code": "NONE", "location": "NONE"}
    return {
        **captured,
        "existing_untouched": target.read_text(encoding="utf-8") == "corrupted",
        "verify_rejects": _verify_code(store, written.ref),
    }


def _verify_code(store: ArtifactStore, ref: Mapping[str, Any]) -> str:
    try:
        store.verify_ref(ref, "outputs/0")
    except ContractViolation as error:
        return error.code
    return "NONE"


def _scenario_j07(root: Path) -> dict[str, Any]:
    """stage callable 실패 → completed checkpoint·final manifest 없이 evidence 보존."""

    runtime = JobRuntime(root)
    spec = _simple_spec()

    def boom(context: StageContext) -> Sequence[StageOutput]:
        (context.workspace / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("stage 내부 실패")

    try:
        runtime.run_job(spec, {"extract": boom})
    except ContractViolation as error:
        captured = _capture(error)
    else:
        captured = {"code": "NONE", "location": "NONE"}
    records = [record for _, record in runtime._read_attempts(spec, "extract")]
    manifest = runtime._load_manifest(runtime.manifest_path(spec))
    return {
        "code": captured["code"],
        "attempt_statuses": [record["status"] for record in records],
        "completed_count": sum(1 for record in records if record["status"] == "completed"),
        "recorded_error": records[0].get("error_code"),
        "manifest_status": manifest["status"],
        "manifest_stage_entries": len(manifest["stages"]),
    }


def _scenario_j08(root: Path) -> dict[str, Any]:
    """artifact 승격 후 checkpoint 전 중단 → orphan을 완료 stage로 가장하지 않는다."""

    runtime = JobRuntime(root)
    spec = _simple_spec()

    def interrupt(uri: str) -> None:
        raise InjectedInterrupt(uri)

    interrupted = False
    try:
        runtime.run_job(
            spec,
            {"extract": _emit("hello")},
            injection=FailureInjection(after_promote=interrupt),
        )
    except InjectedInterrupt:
        interrupted = True

    records_after_crash = [record for _, record in runtime._read_attempts(spec, "extract")]
    orphan_present = any(
        path.is_file()
        for path in (runtime.project_root / "artifacts" / "sha256").rglob("*")
        if path.is_file()
    )

    calls = [0]
    result = runtime.run_job(spec, {"extract": _counting("hello", calls)})
    outcome = result.outcome("extract")
    records_after_resume = [record for _, record in runtime._read_attempts(spec, "extract")]
    return {
        "interrupted": interrupted,
        "crash_statuses": [record["status"] for record in records_after_crash],
        "orphan_object_present": orphan_present,
        "resume_cache_status": outcome.cache_status,
        "resume_calls": calls[0],
        "resume_statuses": sorted(record["status"] for record in records_after_resume),
        "preserved_attempt_ids": sorted(
            record["attempt_id"] for record in records_after_resume
        ),
    }


def _two_stage_spec(job_id: str = "job-a") -> JobSpec:
    return JobSpec(
        job_id=job_id,
        pipeline_id="pipe-a",
        stages=(
            StageSpec(
                stage_id="alpha",
                implementation_version="alpha/1.0.0",
                config_hash=canonical_hash({"alpha": 1}),
            ),
            StageSpec(
                stage_id="beta",
                implementation_version="beta/1.0.0",
                depends_on=("alpha",),
                config_hash=canonical_hash({"beta": 1}),
            ),
        ),
    )


def _scenario_j09(root: Path) -> dict[str, Any]:
    """A 완료 뒤 B 실패 → 재개하면 A는 hit, B만 새 attempt."""

    runtime = JobRuntime(root)
    spec = _two_stage_spec()
    alpha_calls = [0]

    def failing(context: StageContext) -> Sequence[StageOutput]:
        raise RuntimeError("beta 실패")

    try:
        runtime.run_job(
            spec, {"alpha": _counting("A", alpha_calls), "beta": failing}
        )
    except ContractViolation:
        pass
    first_alpha = alpha_calls[0]

    beta_calls = [0]
    result = runtime.run_job(
        spec,
        {"alpha": _counting("A", alpha_calls), "beta": _counting("B", beta_calls)},
    )
    beta_records = [record for _, record in runtime._read_attempts(spec, "beta")]
    return {
        "alpha_calls_first_run": first_alpha,
        "alpha_calls_on_resume": alpha_calls[0] - first_alpha,
        "alpha_cache_status": result.outcome("alpha").cache_status,
        "beta_cache_status": result.outcome("beta").cache_status,
        "beta_calls_on_resume": beta_calls[0],
        "beta_attempt_ids": sorted(record["attempt_id"] for record in beta_records),
        "beta_statuses": sorted(record["status"] for record in beta_records),
        "job_status": result.status,
    }


def _scenario_j10(root: Path) -> dict[str, Any]:
    """남은 running attempt → interrupted로 보존하고 새 attempt ID로 실행한다."""

    runtime = JobRuntime(root)
    spec = _simple_spec()

    def interrupt(uri: str) -> None:
        raise InjectedInterrupt(uri)

    try:
        runtime.run_job(
            spec,
            {"extract": _emit("hello")},
            injection=FailureInjection(after_promote=interrupt),
        )
    except InjectedInterrupt:
        pass
    before = [record for _, record in runtime._read_attempts(spec, "extract")]

    result = runtime.run_job(spec, {"extract": _emit("hello")})
    after = [record for _, record in runtime._read_attempts(spec, "extract")]
    return {
        "before_statuses": [record["status"] for record in before],
        "before_ids": [record["attempt_id"] for record in before],
        "after_statuses": sorted(record["status"] for record in after),
        "after_ids": sorted(record["attempt_id"] for record in after),
        "new_attempt_id": result.outcome("extract").attempt_id,
        "reused_old_id": result.outcome("extract").attempt_id in [
            record["attempt_id"] for record in before
        ],
    }


def _scenario_j11(root: Path) -> dict[str, Any]:
    """job fingerprint가 바뀐 resume → 기존 job에 이어 쓰지 않고 거부한다."""

    runtime = JobRuntime(root)
    spec = _simple_spec()
    runtime.run_job(spec, {"extract": _emit("hello")})
    manifest_before = load_strict(runtime.manifest_path(spec))

    changed = JobSpec(
        job_id=spec.job_id,
        pipeline_id="pipe-b",  # job-level identity 변경
        stages=spec.stages,
        source_identity=spec.source_identity,
    )
    try:
        runtime.run_job(changed, {"extract": _emit("hello")})
    except ContractViolation as error:
        captured = _capture(error)
    else:
        captured = {"code": "NONE", "location": "NONE"}
    manifest_after = load_strict(runtime.manifest_path(spec))
    return {
        **captured,
        "manifest_unchanged": manifest_before == manifest_after,
        "fingerprint_differs": job_fingerprint(spec) != job_fingerprint(changed),
    }


def _scenario_j12(root: Path) -> dict[str, Any]:
    """완료 checkpoint의 artifact가 누락·변조 → cache hit를 거부한다."""

    observations: dict[str, Any] = {}
    for mode in ("missing", "tampered"):
        directory = root / mode
        directory.mkdir()
        runtime = JobRuntime(directory)
        spec = _simple_spec()
        result = runtime.run_job(spec, {"extract": _emit("hello")})
        target = runtime.store.absolute(result.outcome("extract").outputs[0]["uri"], "uri")
        if mode == "missing":
            target.unlink()
        else:
            target.write_text("tampered bytes", encoding="utf-8")
        try:
            runtime.run_job(spec, {"extract": _emit("hello")})
        except ContractViolation as error:
            observations[mode] = _capture(error)
        else:
            observations[mode] = {"code": "NONE", "location": "NONE"}
        records = [record for _, record in runtime._read_attempts(spec, "extract")]
        observations[mode]["evidence_preserved"] = [record["status"] for record in records]
    return observations


_UNSAFE_PATHS = (
    "/etc/passwd",
    "C:/Windows/system32",
    "//server/share",
    "../outside",
    "jobs/../../outside",
    "jobs//empty",
    "jobs/trailing.",
    "jobs/CON",
    "jobs/with:colon",
    "jobs\\windows",
)


def _scenario_j13(root: Path) -> dict[str, Any]:
    """unsafe path를 preflight에서 거부하고 filesystem을 바꾸지 않는다."""

    project = root / "project"
    project.mkdir()
    runtime = JobRuntime(project)
    before = sorted(path.name for path in project.iterdir())

    codes: dict[str, str] = {}
    for candidate in _UNSAFE_PATHS:
        spec = JobSpec(
            job_id="job-a",
            pipeline_id="pipe-a",
            stages=(StageSpec(stage_id="extract", implementation_version="e/1.0.0"),),
            jobs_root=candidate,
        )
        try:
            runtime.run_job(spec, {"extract": _emit("hello")})
        except ContractViolation as error:
            codes[candidate] = error.code
        else:
            codes[candidate] = "NONE"

    # symlink를 통한 root 탈출.
    outside = root / "outside"
    outside.mkdir()
    symlink_code = "UNSUPPORTED"
    try:
        (project / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pass
    else:
        spec = JobSpec(
            job_id="job-a",
            pipeline_id="pipe-a",
            stages=(StageSpec(stage_id="extract", implementation_version="e/1.0.0"),),
            jobs_root="escape/jobs",
        )
        try:
            runtime.run_job(spec, {"extract": _emit("hello")})
        except ContractViolation as error:
            symlink_code = error.code
        else:
            symlink_code = "NONE"

    after = sorted(path.name for path in project.iterdir())
    return {
        "codes": codes,
        "symlink_escape_code": symlink_code,
        "filesystem_unchanged": before == [name for name in after if name != "escape"],
    }


def _scenario_j14(root: Path) -> dict[str, Any]:
    """입력이 hashing/copy 중 바뀌면 성공 artifact를 만들지 않는다.

    thread 경쟁이나 sleep 대신 chunk reader hook으로 결정적으로 재현한다.
    """

    store = ArtifactStore(root)
    source = _write_source(root, "input/a.txt", "x" * (2 * 1024 * 1024))

    def mutate(index: int) -> None:
        if index == 0:
            with open(source, "r+b") as handle:
                handle.seek(0)
                handle.write(b"Y")
            os.utime(source, (0, 0))

    try:
        store.add_file(
            source,
            job_id="job-a",
            stage_id="extract",
            injection=FailureInjection(on_chunk=mutate),
        )
    except ContractViolation as error:
        captured = _capture(error)
    else:
        captured = {"code": "NONE", "location": "NONE"}

    cas = root / "artifacts" / "sha256"
    promoted = sorted(path.name for path in cas.rglob("*") if path.is_file()) if cas.is_dir() else []
    return {**captured, "promoted_artifacts": promoted}


def _scenario_j15(root: Path) -> dict[str, Any]:
    """DAG cycle·없는 dependency·중복 stage ID를 실행 전에 거부한다."""

    project = root / "project"
    project.mkdir()
    runtime = JobRuntime(project)

    cases = {
        "cycle": (
            StageSpec(stage_id="alpha", implementation_version="a/1", depends_on=("beta",)),
            StageSpec(stage_id="beta", implementation_version="b/1", depends_on=("alpha",)),
        ),
        "dangling": (
            StageSpec(stage_id="alpha", implementation_version="a/1", depends_on=("ghost",)),
        ),
        "duplicate": (
            StageSpec(stage_id="alpha", implementation_version="a/1"),
            StageSpec(stage_id="alpha", implementation_version="a/2"),
        ),
        "self_dependency": (
            StageSpec(stage_id="alpha", implementation_version="a/1", depends_on=("alpha",)),
        ),
    }
    observations: dict[str, Any] = {}
    for name, stages in cases.items():
        spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=stages)
        try:
            runtime.run_job(spec, {"alpha": _emit("A"), "beta": _emit("B")})
        except ContractViolation as error:
            observations[name] = _capture(error)
        else:
            observations[name] = {"code": "NONE", "location": "NONE"}
    observations["filesystem_unchanged"] = sorted(
        path.name for path in project.iterdir()
    ) == []
    return observations


def _branch_spec(alpha_config: str) -> JobSpec:
    return JobSpec(
        job_id="job-a",
        pipeline_id="pipe-a",
        source_identity="src-1",
        stages=(
            StageSpec(
                stage_id="alpha",
                implementation_version="alpha/1.0.0",
                config_hash=canonical_hash({"alpha": alpha_config}),
            ),
            StageSpec(
                stage_id="beta",
                implementation_version="beta/1.0.0",
                depends_on=("alpha",),
                config_hash=canonical_hash({"beta": 1}),
            ),
            StageSpec(
                stage_id="charlie",
                implementation_version="charlie/1.0.0",
                config_hash=canonical_hash({"charlie": 1}),
            ),
        ),
    )


def _scenario_j16(root: Path) -> dict[str, Any]:
    """A fingerprint 변경 → A와 downstream만 miss, 독립 C는 계속 hit.

    A의 출력 바이트는 **일부러 그대로** 둔다. dependency cache key가 downstream key에
    들어가지 않으면 B가 hit가 되어버리는 것을 잡기 위해서다.
    """

    runtime = JobRuntime(root)
    alpha, beta, charlie = [0], [0], [0]
    callables = {
        "alpha": _counting("A", alpha),
        "beta": _counting("B", beta),
        "charlie": _counting("C", charlie),
    }
    first = runtime.run_job(_branch_spec("v1"), callables)
    baseline = (alpha[0], beta[0], charlie[0])
    alpha_hash_before = first.outcome("alpha").outputs[0]["content_hash"]

    changed = runtime.run_job(_branch_spec("v2"), callables)
    alpha_hash_after = changed.outcome("alpha").outputs[0]["content_hash"]
    return {
        "first_statuses": {
            entry.stage_id: entry.cache_status for entry in first.stages
        },
        "first_calls": {"alpha": baseline[0], "beta": baseline[1], "charlie": baseline[2]},
        "changed_statuses": {
            entry.stage_id: entry.cache_status for entry in changed.stages
        },
        "changed_reasons": {
            entry.stage_id: entry.cache_reason for entry in changed.stages
        },
        "calls_after_change": {
            "alpha": alpha[0] - baseline[0],
            "beta": beta[0] - baseline[1],
            "charlie": charlie[0] - baseline[2],
        },
        # A의 출력 바이트가 **그대로**인데도 B가 miss여야 한다. 이 값을 관측으로
        # 남겨야 "dependency cache key를 downstream key에 넣는다"가 실제로 확인된다.
        "alpha_output_bytes_identical": alpha_hash_before == alpha_hash_after,
    }


SCENARIOS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "j01_happy_path": _scenario_j01,
    "j02_verified_hit": _scenario_j02,
    "j03_fingerprint_miss": _scenario_j03,
    "j04_not_cacheable": _scenario_j04,
    "j05_dedupe": _scenario_j05,
    "j06_corrupt_object": _scenario_j06,
    "j07_stage_failure": _scenario_j07,
    "j08_interrupt_before_checkpoint": _scenario_j08,
    "j09_partial_resume": _scenario_j09,
    "j10_running_attempt": _scenario_j10,
    "j11_job_fingerprint": _scenario_j11,
    "j12_broken_checkpoint": _scenario_j12,
    "j13_unsafe_path": _scenario_j13,
    "j14_input_changed": _scenario_j14,
    "j15_dag_preflight": _scenario_j15,
    "j16_selective_invalidation": _scenario_j16,
}


# ---------------------------------------------------------------------------
# fixture runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureOutcome:
    case_id: str
    path: Path
    passed: bool
    mismatches: tuple[str, ...]
    observed: Mapping[str, Any]


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = load_strict(path)
    for key in ("case_id", "title", "scenario", "expect"):
        if key not in fixture:
            raise ContractViolation(
                "E_SCHEMA", path.name, f"fixture에 필수 필드가 없다: {key}"
            )
    if fixture["scenario"] not in SCENARIOS:
        raise ContractViolation(
            "E_SCHEMA", path.name, f"알 수 없는 scenario: {fixture['scenario']}"
        )
    return fixture


def evaluate_fixture(path: Path) -> FixtureOutcome:
    """fixture를 **실제 production API로 실행**하고 관측값을 기대값과 비교한다.

    fixture의 `expect`를 읽어 그대로 성공시키지 않는다. 관측값은 임시 project root에서
    `ArtifactStore`·`JobRuntime`을 호출한 결과다.
    """

    fixture = load_fixture(path)
    with TemporaryDirectory(prefix="mcs-task-028-") as temporary:
        observed = SCENARIOS[fixture["scenario"]](Path(temporary))

    mismatches: list[str] = []
    expected = fixture["expect"]
    for key in sorted(set(expected) | set(observed)):
        if key not in expected:
            mismatches.append(f"기대에 없는 관측 항목: {key}")
        elif key not in observed:
            mismatches.append(f"관측되지 않은 기대 항목: {key}")
        elif expected[key] != observed[key]:
            mismatches.append(f"{key}: 기대 {expected[key]!r} / 관측 {observed[key]!r}")
    return FixtureOutcome(
        case_id=fixture["case_id"],
        path=path,
        passed=not mismatches,
        mismatches=tuple(mismatches),
        observed=observed,
    )


def discover_fixtures(directory: Path) -> list[Path]:
    return sorted(directory.glob("j-*.json"))


def run_fixtures(directory: Path) -> list[FixtureOutcome]:
    return [evaluate_fixture(path) for path in discover_fixtures(directory)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TASK-028 J-01~J-16 fixture runner")
    parser.add_argument("--fixtures", required=True, type=Path)
    args = parser.parse_args(argv)

    outcomes = run_fixtures(args.fixtures)
    failures = 0
    seen: list[str] = []
    for outcome in outcomes:
        seen.append(outcome.case_id)
        mark = "PASS" if outcome.passed else "FAIL"
        print(f"{mark} {outcome.case_id} {outcome.path.name}")
        for mismatch in outcome.mismatches:
            print(f"     {mismatch}")
        if not outcome.passed:
            failures += 1

    missing = [case for case in EXPECTED_CASE_IDS if case not in seen]
    duplicates = sorted({case for case in seen if seen.count(case) > 1})
    unexpected = sorted(set(seen) - set(EXPECTED_CASE_IDS))
    for label, values in (("누락", missing), ("중복", duplicates), ("계약 밖", unexpected)):
        if values:
            print(f"{label} case: {', '.join(values)}")
            failures += len(values)

    print(f"실행 {len(outcomes)}건 / 기대 {len(EXPECTED_CASE_IDS)}건 / 실패 {failures}건")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover - CLI 진입점
    sys.exit(main())
