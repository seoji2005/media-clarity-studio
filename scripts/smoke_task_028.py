#!/usr/bin/env python3
"""TASK-028 smoke — 실제 artifact store와 job runtime을 임시 project root에서 돌린다.

FFmpeg·모델·네트워크를 쓰지 않는다. TASK-022 smoke의 의미를 바꾸지 않으며 별개 진입점이다.

확인하는 것:

1. 첫 실행이 artifact·completed checkpoint·manifest를 만든다.
2. 두 번째 실행이 callable을 부르지 않고 검증된 cache hit를 쓴다.
3. 승격 직후 중단해도 orphan object가 완료 stage로 가장하지 않는다.
4. 중단된 `running` attempt가 지워지지 않고 `interrupted`로 보존된다.
5. upstream fingerprint 변경이 downstream만 무효화하고 독립 branch는 재사용한다.
6. 기존 CAS object를 덮어쓰지 않으며 손상은 안정 오류로 거부된다.
7. job manifest·attempt record에 원본 텍스트와 외부 절대 경로가 없다.

실패하면 비정상 종료한다. 저장소에는 아무것도 쓰지 않는다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from media_clarity.artifact_store import (  # noqa: E402
    ArtifactStore,
    ContractViolation,
    FailureInjection,
)
from media_clarity.job_runtime import (  # noqa: E402
    InjectedInterrupt,
    JobRuntime,
    JobSpec,
    StageContext,
    StageOutput,
    StageSpec,
    canonical_hash,
    job_fingerprint,
)

SENTINEL = "SMOKE-SENTINEL-TRANSCRIPT"


def emit(text: str, counter: list[int], name: str = "out.txt"):
    def run(context: StageContext) -> Sequence[StageOutput]:
        counter[0] += 1
        target = context.workspace / name
        target.write_text(text, encoding="utf-8")
        return [StageOutput(name=name, path=target)]

    return run


def branch_spec(alpha_config: str) -> JobSpec:
    return JobSpec(
        job_id="smoke-job",
        pipeline_id="smoke-pipe",
        source_identity="smoke-source-1",
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


def run_smoke(root: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    runtime = JobRuntime(root)

    alpha, beta, charlie = [0], [0], [0]
    callables = {
        "alpha": emit(SENTINEL, alpha),
        "beta": emit("beta-output", beta),
        "charlie": emit("charlie-output", charlie),
    }

    # 1. 첫 실행
    first = runtime.run_job(branch_spec("v1"), callables)
    report["first_run_status"] = first.status
    report["first_calls"] = {"alpha": alpha[0], "beta": beta[0], "charlie": charlie[0]}
    report["first_cache_statuses"] = {
        entry.stage_id: entry.cache_status for entry in first.stages
    }
    alpha_ref = first.outcome("alpha").outputs[0]
    alpha_path = runtime.store.absolute(alpha_ref["uri"], "uri")
    report["artifact_uri"] = alpha_ref["uri"]
    report["artifact_uri_is_relative"] = not alpha_ref["uri"].startswith("/")
    report["artifact_exists"] = alpha_path.is_file()

    # 2. 검증된 cache hit
    baseline = (alpha[0], beta[0], charlie[0])
    second = runtime.run_job(branch_spec("v1"), callables)
    report["second_cache_statuses"] = {
        entry.stage_id: entry.cache_status for entry in second.stages
    }
    report["second_run_calls"] = {
        "alpha": alpha[0] - baseline[0],
        "beta": beta[0] - baseline[1],
        "charlie": charlie[0] - baseline[2],
    }
    report["cache_hit_verified_bytes"] = second.outcome("alpha").verified_artifact_bytes

    # 5. upstream 변경과 선택적 무효화 (출력 바이트는 그대로다)
    baseline = (alpha[0], beta[0], charlie[0])
    changed = runtime.run_job(branch_spec("v2"), callables)
    report["invalidation_cache_statuses"] = {
        entry.stage_id: entry.cache_status for entry in changed.stages
    }
    report["invalidation_calls"] = {
        "alpha": alpha[0] - baseline[0],
        "beta": beta[0] - baseline[1],
        "charlie": charlie[0] - baseline[2],
    }
    report["alpha_output_bytes_identical"] = (
        alpha_ref["content_hash"] == changed.outcome("alpha").outputs[0]["content_hash"]
    )

    # 6. dedupe와 손상 거부 — 기존 object를 덮어쓰지 않는다
    store = ArtifactStore(root)
    source = root / "smoke-input" / "a.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("dedupe me", encoding="utf-8")
    written = store.add_file(source, job_id="smoke-job", stage_id="alpha")
    target = store.absolute(written.ref["uri"], "uri")
    before = os.stat(target)
    other = root / "smoke-input" / "b.txt"
    other.write_text("dedupe me", encoding="utf-8")
    again = store.add_file(other, job_id="smoke-job", stage_id="alpha")
    after = os.stat(target)
    report["dedupe_same_uri"] = written.ref["uri"] == again.ref["uri"]
    report["dedupe_reported"] = again.deduped
    report["dedupe_inode_unchanged"] = before.st_ino == after.st_ino
    report["dedupe_mtime_unchanged"] = before.st_mtime_ns == after.st_mtime_ns

    target.write_text("corrupted", encoding="utf-8")
    third = root / "smoke-input" / "c.txt"
    third.write_text("dedupe me", encoding="utf-8")
    try:
        store.add_file(third, job_id="smoke-job", stage_id="alpha")
    except ContractViolation as error:
        report["corrupt_object_code"] = error.code
    else:
        report["corrupt_object_code"] = "NONE"
    report["corrupt_object_untouched"] = target.read_text(encoding="utf-8") == "corrupted"

    # 3·4. 승격 직후 중단과 running attempt 보존
    crash_root = root / "crash"
    crash_root.mkdir()
    crash_runtime = JobRuntime(crash_root)
    crash_spec = JobSpec(
        job_id="crash-job",
        pipeline_id="smoke-pipe",
        stages=(StageSpec(stage_id="alpha", implementation_version="alpha/1.0.0"),),
    )

    def interrupt(uri: str) -> None:
        raise InjectedInterrupt(uri)

    crash_calls = [0]
    try:
        crash_runtime.run_job(
            crash_spec,
            {"alpha": emit("crash-output", crash_calls)},
            injection=FailureInjection(after_promote=interrupt),
        )
        report["interrupt_raised"] = False
    except InjectedInterrupt:
        report["interrupt_raised"] = True
    crashed = [record for _, record in crash_runtime._read_attempts(crash_spec, "alpha")]
    report["crash_attempt_statuses"] = [record["status"] for record in crashed]
    report["orphan_object_present"] = any(
        path.is_file() for path in (crash_root / "artifacts" / "sha256").rglob("*")
    )

    resume_calls = [0]
    resumed = crash_runtime.run_job(crash_spec, {"alpha": emit("crash-output", resume_calls)})
    resumed_records = {
        record["attempt_id"]: record["status"]
        for _, record in crash_runtime._read_attempts(crash_spec, "alpha")
    }
    report["resume_cache_status"] = resumed.outcome("alpha").cache_status
    report["resume_calls"] = resume_calls[0]
    report["resume_attempt_states"] = resumed_records
    report["interrupted_attempt_preserved"] = resumed_records.get("a0001") == "interrupted"
    report["new_attempt_id"] = resumed.outcome("alpha").attempt_id

    # 7. 민감정보 누출 없음
    leaked_text = False
    leaked_path = False
    inspected = 0
    for path in (root / "jobs").rglob("*.json"):
        inspected += 1
        text = path.read_text(encoding="utf-8")
        leaked_text = leaked_text or SENTINEL in text
        leaked_path = leaked_path or str(root) in text
    report["job_records_inspected"] = inspected
    report["source_text_leaked"] = leaked_text
    report["absolute_path_leaked"] = leaked_path

    # job fingerprint 불일치는 기존 job에 이어 쓰지 않는다
    mismatched = JobSpec(
        job_id="smoke-job",
        pipeline_id="other-pipe",
        source_identity="smoke-source-1",
        stages=branch_spec("v2").stages,
    )
    try:
        runtime.run_job(mismatched, callables)
    except ContractViolation as error:
        report["resume_mismatch_code"] = error.code
        report["resume_mismatch_location"] = error.location
    else:
        report["resume_mismatch_code"] = "NONE"
        report["resume_mismatch_location"] = "NONE"
    report["job_fingerprint_differs"] = job_fingerprint(mismatched) != job_fingerprint(
        branch_spec("v2")
    )
    return report


EXPECTED = {
    "first_run_status": "completed",
    "first_calls": {"alpha": 1, "beta": 1, "charlie": 1},
    "first_cache_statuses": {"alpha": "miss", "beta": "miss", "charlie": "miss"},
    "artifact_uri_is_relative": True,
    "artifact_exists": True,
    "second_cache_statuses": {"alpha": "hit", "beta": "hit", "charlie": "hit"},
    "second_run_calls": {"alpha": 0, "beta": 0, "charlie": 0},
    "invalidation_cache_statuses": {"alpha": "miss", "beta": "miss", "charlie": "hit"},
    "invalidation_calls": {"alpha": 1, "beta": 1, "charlie": 0},
    "alpha_output_bytes_identical": True,
    "dedupe_same_uri": True,
    "dedupe_reported": True,
    "dedupe_inode_unchanged": True,
    "dedupe_mtime_unchanged": True,
    "corrupt_object_code": "E_ARTIFACT_COLLISION",
    "corrupt_object_untouched": True,
    "interrupt_raised": True,
    "crash_attempt_statuses": ["running"],
    "orphan_object_present": True,
    "resume_cache_status": "miss",
    "resume_calls": 1,
    "resume_attempt_states": {"a0001": "interrupted", "a0002": "completed"},
    "interrupted_attempt_preserved": True,
    "new_attempt_id": "a0002",
    "source_text_leaked": False,
    "absolute_path_leaked": False,
    "resume_mismatch_code": "E_RESUME_FINGERPRINT",
    "resume_mismatch_location": "job_fingerprint",
    "job_fingerprint_differs": True,
}


def main() -> int:
    with TemporaryDirectory(prefix="mcs-smoke-028-") as temporary:
        report = run_smoke(Path(temporary))

    failures = [
        f"{key}: 기대 {value!r} / 관측 {report.get(key)!r}"
        for key, value in EXPECTED.items()
        if report.get(key) != value
    ]
    if report.get("job_records_inspected", 0) <= 0:
        failures.append("job_records_inspected: manifest/attempt record를 하나도 읽지 못했다")
    if report.get("cache_hit_verified_bytes", 0) <= 0:
        failures.append("cache_hit_verified_bytes: cache hit에서 검증한 byte 수가 0이다")

    report["status"] = "FAIL" if failures else "PASS"
    if failures:
        report["failures"] = failures
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
