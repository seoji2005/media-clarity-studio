"""TASK-028 재개 가능한 stage runtime 테스트.

fixture의 expected를 그대로 통과시키지 않는다. 실제 임시 project root에서 production
`JobRuntime`·`ArtifactStore` API를 호출하고, 계약을 어기는 mutation이 반드시 실패하는지
확인한다.
"""

from __future__ import annotations

import copy
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from media_clarity.artifact_store import (
    ArtifactStore,
    ContractViolation,
    FailureInjection,
)
from media_clarity.schema_core import JsonInputError, SchemaSet, load_strict, loads_strict
from media_clarity.job_runtime import (
    ATTEMPT_RECORD_POINTER,
    CACHE_KEY_FIELDS,
    EXPECTED_CASE_IDS,
    JOB_SCHEMA_FILE,
    JOB_SCHEMA_FILES,
    RUNTIME_VERSION,
    SCENARIOS,
    InjectedInterrupt,
    JobRuntime,
    JobSpec,
    StageContext,
    StageOutput,
    StageSpec,
    canonical_hash,
    canonical_json_bytes,
    deterministic_order,
    discover_fixtures,
    evaluate_fixture,
    job_fingerprint,
    job_schema_set,
    load_fixture,
    preflight,
    stage_cache_key,
    stage_cache_key_document,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "job_runtime"


def emit(text: str, counter: list[int] | None = None, name: str = "out.txt"):
    def run(context: StageContext) -> Sequence[StageOutput]:
        if counter is not None:
            counter[0] += 1
        target = context.workspace / name
        target.write_text(text, encoding="utf-8")
        return [StageOutput(name=name, path=target)]

    return run


class RuntimeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory(prefix="mcs-runtime-")
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.runtime = JobRuntime(self.root)

    def spec(self, **overrides: Any) -> JobSpec:
        stage = StageSpec(
            stage_id="extract",
            implementation_version="extract/1.0.0",
            config_hash=canonical_hash({"config": "a"}),
            dependency_fingerprint=canonical_hash({"deps": "a"}),
            **overrides,
        )
        return JobSpec(
            job_id="job-a", pipeline_id="pipe-a", stages=(stage,), source_identity="src-1"
        )

    def two_stage(self, alpha_config: str = "v1") -> JobSpec:
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
            ),
        )

    def attempts(self, spec: JobSpec, stage_id: str) -> list[dict[str, Any]]:
        return [record for _, record in self.runtime._read_attempts(spec, stage_id)]

    def manifest(self, spec: JobSpec) -> dict[str, Any]:
        return load_strict(self.runtime.manifest_path(spec))

    def assert_violation(self, code: str, callable_: Any, *args: Any, **kwargs: Any) -> ContractViolation:
        with self.assertRaises(ContractViolation) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception


# ---------------------------------------------------------------------------
# canonical JSON과 fingerprint
# ---------------------------------------------------------------------------


class CanonicalJsonTests(unittest.TestCase):
    def test_keys_are_sorted_with_deterministic_separators(self) -> None:
        self.assertEqual(
            canonical_json_bytes({"b": 1, "a": {"d": 2, "c": 3}}),
            b'{"a":{"c":3,"d":2},"b":1}',
        )

    def test_utf8_is_preserved_without_escaping(self) -> None:
        self.assertEqual(canonical_json_bytes({"k": "한글"}), '{"k":"한글"}'.encode("utf-8"))

    def test_nan_and_infinity_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    canonical_json_bytes({"k": value})

    def test_hash_is_stable_across_key_order(self) -> None:
        self.assertEqual(canonical_hash({"a": 1, "b": 2}), canonical_hash({"b": 2, "a": 1}))
        self.assertRegex(canonical_hash({"a": 1}), r"^sha256:[0-9a-f]{64}$")


class CacheKeyTests(RuntimeCase):
    def base_stage(self) -> StageSpec:
        return StageSpec(
            stage_id="extract",
            implementation_version="extract/1.0.0",
            config_hash=canonical_hash({"config": "a"}),
            dependency_fingerprint=canonical_hash({"deps": "a"}),
            source_hash=canonical_hash({"source": "a"}),
            chunking_hash=canonical_hash({"chunking": "a"}),
            model_hash=canonical_hash({"model": "a"}),
            context_hash=canonical_hash({"context": "a"}),
            random_seed=7,
            reproducibility_tier="T2",
        )

    def key(self, stage: StageSpec, inputs: Sequence[str] = (), deps: dict[str, str] | None = None) -> str:
        spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(stage,))
        return stage_cache_key(spec, stage, inputs, deps or {})

    def test_identical_inputs_give_an_identical_key(self) -> None:
        self.assertEqual(self.key(self.base_stage()), self.key(self.base_stage()))

    def test_every_contract_fingerprint_changes_the_key_on_its_own(self) -> None:
        """계약된 fingerprint를 하나씩만 바꿔도 key가 달라져야 한다."""

        baseline = self.key(self.base_stage())
        changes = {
            "implementation_version": "extract/2.0.0",
            "config_hash": canonical_hash({"config": "b"}),
            "dependency_fingerprint": canonical_hash({"deps": "b"}),
            "source_hash": canonical_hash({"source": "b"}),
            "chunking_hash": canonical_hash({"chunking": "b"}),
            "model_hash": canonical_hash({"model": "b"}),
            "context_hash": canonical_hash({"context": "b"}),
            "random_seed": 8,
            "reproducibility_tier": "T3",
        }
        for name, value in changes.items():
            with self.subTest(field=name):
                mutated = StageSpec(**{**self.base_stage().__dict__, name: value})
                self.assertNotEqual(self.key(mutated), baseline, f"{name}이 key를 바꾸지 않는다")

    def test_absence_is_part_of_the_canonical_value(self) -> None:
        """선택 항목을 조용히 빼지 않는다 — 없음도 값이다."""

        present = self.key(self.base_stage())
        absent = self.key(StageSpec(**{**self.base_stage().__dict__, "model_hash": None}))
        self.assertNotEqual(present, absent)

    def test_canonical_document_keeps_absent_fields_as_explicit_null(self) -> None:
        """부재를 key 계산에서 빼면 canonical 바이트가 달라진다.

        hash만 비교해서는 '항목을 통째로 생략'하는 구현을 구분할 수 없다. 그래서
        canonical 문서의 **모양 자체**를 고정한다 (§3.3).
        """

        bare = StageSpec(stage_id="extract", implementation_version="extract/1.0.0")
        spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(bare,))
        document = stage_cache_key_document(spec, bare, (), {})

        self.assertEqual(tuple(sorted(document)), CACHE_KEY_FIELDS)
        for optional in (
            "config_hash",
            "dependency_fingerprint",
            "source_hash",
            "chunking_hash",
            "model_hash",
            "context_hash",
            "random_seed",
            "reproducibility_tier",
        ):
            with self.subTest(field=optional):
                self.assertIn(optional, document, "선택 항목이 canonical 문서에서 빠졌다")
                self.assertIsNone(document[optional])

        # 값이 채워진 경우에도 필드 집합은 그대로다.
        filled = stage_cache_key_document(spec, self.base_stage(), (), {})
        self.assertEqual(tuple(sorted(filled)), CACHE_KEY_FIELDS)
        self.assertNotIn(None, list(filled.values()))

    def test_key_is_the_hash_of_the_canonical_document(self) -> None:
        """key는 문서를 **거르지 않고** 그대로 해싱한 값이다.

        선택 항목이 채워진 stage만 확인하면 'None인 항목을 빼고 해싱'하는 구현을
        구분할 수 없다. 값이 비어 있는 stage를 함께 확인한다.
        """

        import hashlib

        bare = StageSpec(stage_id="extract", implementation_version="extract/1.0.0")
        for label, stage in (("filled", self.base_stage()), ("bare", bare)):
            with self.subTest(stage=label):
                spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(stage,))
                document = stage_cache_key_document(spec, stage, (), {})
                expected = "sha256:" + hashlib.sha256(canonical_json_bytes(document)).hexdigest()
                self.assertEqual(stage_cache_key(spec, stage, (), {}), expected)
        self.assertIn(None, list(stage_cache_key_document(
            JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(bare,)), bare, (), {}
        ).values()))

    def test_stage_id_and_pipeline_id_are_part_of_the_key(self) -> None:
        stage = self.base_stage()
        other = StageSpec(**{**stage.__dict__, "stage_id": "other"})
        self.assertNotEqual(self.key(stage), self.key(other))

        spec_a = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(stage,))
        spec_b = JobSpec(job_id="job-a", pipeline_id="pipe-b", stages=(stage,))
        self.assertNotEqual(
            stage_cache_key(spec_a, stage, (), {}), stage_cache_key(spec_b, stage, (), {})
        )

    def test_input_hashes_are_order_independent_but_content_sensitive(self) -> None:
        stage = self.base_stage()
        one = self.key(stage, ["sha256:" + "a" * 64, "sha256:" + "b" * 64])
        flipped = self.key(stage, ["sha256:" + "b" * 64, "sha256:" + "a" * 64])
        different = self.key(stage, ["sha256:" + "c" * 64, "sha256:" + "b" * 64])
        self.assertEqual(one, flipped)
        self.assertNotEqual(one, different)

    def test_direct_dependency_cache_key_is_included(self) -> None:
        """upstream fingerprint가 바뀌면 출력 바이트가 같아도 downstream key가 바뀐다."""

        stage = self.base_stage()
        first = self.key(stage, deps={"alpha": "sha256:" + "1" * 64})
        second = self.key(stage, deps={"alpha": "sha256:" + "2" * 64})
        self.assertNotEqual(first, second)

    def test_path_and_mtime_are_not_part_of_identity(self) -> None:
        """같은 바이트를 다른 경로·mtime으로 넣어도 artifact identity는 같다."""

        store = ArtifactStore(self.root)
        first = store.add_file(
            self._write("dir-one/a.txt", "same"), job_id="job-a", stage_id="extract"
        )
        other = self._write("dir-two/b.txt", "same")
        os.utime(other, (0, 0))
        second = store.add_file(other, job_id="job-b", stage_id="convert")
        self.assertEqual(first.ref["content_hash"], second.ref["content_hash"])
        self.assertEqual(first.ref["uri"], second.ref["uri"])

    def _write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class JobFingerprintTests(RuntimeCase):
    def test_job_identity_fields_change_the_fingerprint(self) -> None:
        base = self.spec()
        self.assertEqual(job_fingerprint(base), job_fingerprint(self.spec()))
        changed_pipeline = JobSpec(
            job_id=base.job_id, pipeline_id="pipe-b", stages=base.stages, source_identity="src-1"
        )
        changed_source = JobSpec(
            job_id=base.job_id, pipeline_id="pipe-a", stages=base.stages, source_identity="src-2"
        )
        changed_topology = JobSpec(
            job_id=base.job_id,
            pipeline_id="pipe-a",
            stages=base.stages + (StageSpec(stage_id="extra", implementation_version="x/1"),),
            source_identity="src-1",
        )
        for name, spec in (
            ("pipeline_id", changed_pipeline),
            ("source_identity", changed_source),
            ("dag_topology", changed_topology),
        ):
            with self.subTest(field=name):
                self.assertNotEqual(job_fingerprint(spec), job_fingerprint(base))

    def test_stage_level_fingerprints_do_not_change_the_job_fingerprint(self) -> None:
        """§3.5가 성립하려면 stage config 변경이 job resume을 막아서는 안 된다.

        stage config가 job fingerprint에 들어가면 "A만 miss, 독립 C는 hit"가
        "job fingerprint가 달라 resume 거부"와 동시에 성립할 수 없다.
        """

        base = self.spec()
        for field in ("config_hash", "model_hash", "context_hash", "chunking_hash"):
            with self.subTest(field=field):
                mutated = StageSpec(
                    **{**base.stages[0].__dict__, field: canonical_hash({field: "changed"})}
                )
                changed = JobSpec(
                    job_id=base.job_id,
                    pipeline_id=base.pipeline_id,
                    stages=(mutated,),
                    source_identity=base.source_identity,
                )
                self.assertEqual(job_fingerprint(changed), job_fingerprint(base))
                self.assertNotEqual(
                    stage_cache_key(changed, mutated, (), {}),
                    stage_cache_key(base, base.stages[0], (), {}),
                )


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


class PreflightTests(RuntimeCase):
    def test_duplicate_dangling_and_cycle_are_rejected_before_any_write(self) -> None:
        cases = {
            "E_DAG_DUPLICATE_STAGE": (
                StageSpec(stage_id="alpha", implementation_version="a/1"),
                StageSpec(stage_id="alpha", implementation_version="a/2"),
            ),
            "E_DAG_DEPENDENCY": (
                StageSpec(stage_id="alpha", implementation_version="a/1", depends_on=("ghost",)),
            ),
            "E_DAG_CYCLE": (
                StageSpec(stage_id="alpha", implementation_version="a/1", depends_on=("beta",)),
                StageSpec(stage_id="beta", implementation_version="b/1", depends_on=("alpha",)),
            ),
        }
        for code, stages in cases.items():
            with self.subTest(code=code):
                spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=stages)
                self.assert_violation(code, preflight, spec, self.root)
                self.assertEqual(sorted(path.name for path in self.root.iterdir()), [])

    def test_self_dependency_is_a_cycle(self) -> None:
        spec = JobSpec(
            job_id="job-a",
            pipeline_id="pipe-a",
            stages=(
                StageSpec(stage_id="alpha", implementation_version="a/1", depends_on=("alpha",)),
            ),
        )
        error = self.assert_violation("E_DAG_CYCLE", preflight, spec, self.root)
        self.assertEqual(error.location, "dag/0/depends_on/0")

    def test_empty_dag_is_rejected(self) -> None:
        spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=())
        self.assert_violation("E_DAG_DEPENDENCY", preflight, spec, self.root)

    def test_unsafe_paths_and_identifiers_are_rejected_before_any_write(self) -> None:
        stages = (StageSpec(stage_id="alpha", implementation_version="a/1"),)
        cases = [
            {"jobs_root": "/etc"},
            {"jobs_root": "C:/Windows"},
            {"jobs_root": "//server/share"},
            {"jobs_root": "../outside"},
            {"jobs_root": "jobs/../../outside"},
            {"jobs_root": "jobs\\windows"},
            {"jobs_root": "jobs/with:colon"},
            {"jobs_root": "jobs/CON"},
            {"job_id": "job:a"},
            {"job_id": "../escape"},
            {"pipeline_id": "pipe/a"},
        ]
        for overrides in cases:
            with self.subTest(**overrides):
                spec = JobSpec(
                    **{
                        "job_id": "job-a",
                        "pipeline_id": "pipe-a",
                        "stages": stages,
                        **overrides,
                    }
                )
                self.assert_violation("E_UNSAFE_PATH", preflight, spec, self.root)
                self.assertEqual(sorted(path.name for path in self.root.iterdir()), [])

    def test_unsafe_stage_id_is_rejected(self) -> None:
        spec = JobSpec(
            job_id="job-a",
            pipeline_id="pipe-a",
            stages=(StageSpec(stage_id="stage:one", implementation_version="a/1"),),
        )
        error = self.assert_violation("E_UNSAFE_PATH", preflight, spec, self.root)
        self.assertEqual(error.location, "dag/0/stage_id")

    def test_topological_order_is_deterministic(self) -> None:
        stages = (
            StageSpec(stage_id="d", implementation_version="d/1", depends_on=("b", "c")),
            StageSpec(stage_id="b", implementation_version="b/1", depends_on=("a",)),
            StageSpec(stage_id="c", implementation_version="c/1", depends_on=("a",)),
            StageSpec(stage_id="a", implementation_version="a/1"),
        )
        spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=stages)
        order = deterministic_order(spec)
        self.assertEqual(order, ("a", "b", "c", "d"))
        for _ in range(5):
            self.assertEqual(deterministic_order(spec), order)

    def test_valid_dag_passes_preflight(self) -> None:
        self.assertEqual(preflight(self.two_stage(), self.root), ("alpha", "beta"))


# ---------------------------------------------------------------------------
# 실행·cache·resume
# ---------------------------------------------------------------------------


class HappyPathTests(RuntimeCase):
    def test_first_run_writes_artifact_checkpoint_and_manifest(self) -> None:
        spec = self.spec()
        result = self.runtime.run_job(spec, {"extract": emit("hello")})
        outcome = result.outcome("extract")

        self.assertEqual(result.status, "completed")
        self.assertEqual((outcome.cache_status, outcome.cache_reason), ("miss", "no_completed_checkpoint"))
        self.assertTrue(outcome.callable_invoked)
        self.assertEqual(outcome.verified_artifact_count, 1)
        self.assertEqual(outcome.verified_artifact_bytes, 5)

        records = self.attempts(spec, "extract")
        self.assertEqual([record["status"] for record in records], ["completed"])
        self.assertEqual(records[0]["runtime_version"], RUNTIME_VERSION)

        manifest = self.manifest(spec)
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["job_fingerprint"], job_fingerprint(spec))
        self.assertEqual(manifest["stages"][0]["attempt_status"], "completed")

    def test_records_and_manifest_satisfy_the_job_schema(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        manifest = self.manifest(spec)
        self.assertEqual(self.runtime.validate_manifest(manifest, "manifest.json"), [])
        for record in self.attempts(spec, "extract"):
            self.assertEqual(self.runtime.validate_attempt(record, "attempt.json"), [])

    def test_multi_stage_inputs_flow_from_dependencies(self) -> None:
        spec = self.two_stage()
        seen: list[tuple[str, ...]] = []

        def beta(context: StageContext) -> Sequence[StageOutput]:
            seen.append(tuple(ref["content_hash"] for ref in context.inputs))
            target = context.workspace / "beta.txt"
            target.write_text(
                "|".join(path.read_text(encoding="utf-8") for path in context.input_paths),
                encoding="utf-8",
            )
            return [StageOutput(name="beta.txt", path=target)]

        result = self.runtime.run_job(spec, {"alpha": emit("A"), "beta": beta})
        self.assertEqual(seen, [(result.outcome("alpha").outputs[0]["content_hash"],)])
        self.assertEqual(result.status, "completed")


class CacheTests(RuntimeCase):
    def test_second_run_is_a_verified_hit_without_calling_the_callable(self) -> None:
        spec = self.spec()
        calls = [0]
        self.runtime.run_job(spec, {"extract": emit("hello", calls)})
        self.assertEqual(calls[0], 1)

        result = self.runtime.run_job(spec, {"extract": emit("hello", calls)})
        outcome = result.outcome("extract")
        self.assertEqual(calls[0], 1)
        self.assertEqual((outcome.cache_status, outcome.cache_reason), ("hit", "verified_checkpoint"))
        self.assertFalse(outcome.callable_invoked)
        self.assertEqual(outcome.verified_artifact_count, 1)
        self.assertEqual(outcome.verified_artifact_bytes, 5)

    def test_each_fingerprint_change_is_its_own_miss(self) -> None:
        for field, value in (
            ("config_hash", canonical_hash({"config": "b"})),
            ("implementation_version", "extract/2.0.0"),
            ("dependency_fingerprint", canonical_hash({"deps": "b"})),
            ("model_hash", canonical_hash({"model": "b"})),
            ("context_hash", canonical_hash({"context": "b"})),
            ("chunking_hash", canonical_hash({"chunking": "b"})),
            ("source_hash", canonical_hash({"source": "b"})),
        ):
            with self.subTest(field=field):
                directory = self.root / field
                directory.mkdir()
                runtime = JobRuntime(directory)
                spec = self.spec()
                runtime.run_job(spec, {"extract": emit("hello")})
                changed = JobSpec(
                    job_id=spec.job_id,
                    pipeline_id=spec.pipeline_id,
                    source_identity=spec.source_identity,
                    stages=(StageSpec(**{**spec.stages[0].__dict__, field: value}),),
                )
                calls = [0]
                outcome = runtime.run_job(changed, {"extract": emit("hello", calls)}).outcome(
                    "extract"
                )
                self.assertEqual(
                    (outcome.cache_status, outcome.cache_reason), ("miss", "cache_key_changed")
                )
                self.assertEqual(calls[0], 1)

    def test_not_cacheable_stage_is_bypassed_every_run(self) -> None:
        stage = StageSpec(
            stage_id="extract", implementation_version="extract/1.0.0", cacheable=False
        )
        spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(stage,))
        calls = [0]
        self.runtime.run_job(spec, {"extract": emit("hello", calls)})
        outcome = self.runtime.run_job(spec, {"extract": emit("hello", calls)}).outcome("extract")
        self.assertEqual(calls[0], 2)
        self.assertEqual((outcome.cache_status, outcome.cache_reason), ("bypassed", "not_cacheable"))
        self.assertEqual(self.attempts(spec, "extract")[-1]["cacheable"], False)

    def test_upstream_change_invalidates_downstream_but_not_an_independent_branch(self) -> None:
        def branch(alpha_config: str) -> JobSpec:
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

        alpha, beta, charlie = [0], [0], [0]
        callables = {
            "alpha": emit("A", alpha),
            "beta": emit("B", beta),
            "charlie": emit("C", charlie),
        }
        first = self.runtime.run_job(branch("v1"), callables)
        self.assertEqual((alpha[0], beta[0], charlie[0]), (1, 1, 1))

        changed = self.runtime.run_job(branch("v2"), callables)
        # A의 출력 바이트는 그대로다 — 그런데도 B는 miss여야 한다.
        self.assertEqual(
            first.outcome("alpha").outputs[0]["content_hash"],
            changed.outcome("alpha").outputs[0]["content_hash"],
        )
        self.assertEqual(changed.outcome("alpha").cache_status, "miss")
        self.assertEqual(changed.outcome("beta").cache_status, "miss")
        self.assertEqual(changed.outcome("charlie").cache_status, "hit")
        self.assertEqual((alpha[0], beta[0], charlie[0]), (2, 2, 1))

    def test_cache_lookup_never_crosses_jobs(self) -> None:
        """계약되지 않은 전역 cross-job cache index를 만들지 않는다."""

        first = self.spec()
        self.runtime.run_job(first, {"extract": emit("hello")})
        other = JobSpec(
            job_id="job-b",
            pipeline_id=first.pipeline_id,
            stages=first.stages,
            source_identity=first.source_identity,
        )
        calls = [0]
        outcome = self.runtime.run_job(other, {"extract": emit("hello", calls)}).outcome("extract")
        self.assertEqual(outcome.cache_status, "miss")
        self.assertEqual(calls[0], 1)


class CheckpointIntegrityTests(RuntimeCase):
    def test_missing_or_tampered_artifact_blocks_the_hit(self) -> None:
        for mode, code in (("missing", "E_ARTIFACT_MISSING"), ("tampered", "E_ARTIFACT_CORRUPT")):
            with self.subTest(mode=mode):
                directory = self.root / mode
                directory.mkdir()
                runtime = JobRuntime(directory)
                spec = self.spec()
                result = runtime.run_job(spec, {"extract": emit("hello")})
                target = runtime.store.absolute(result.outcome("extract").outputs[0]["uri"], "uri")
                if mode == "missing":
                    target.unlink()
                else:
                    target.write_text("tampered bytes", encoding="utf-8")
                before = [
                    record for _, record in runtime._read_attempts(spec, "extract")
                ]
                self.assert_violation(
                    code, runtime.run_job, spec, {"extract": emit("hello")}
                )
                after = [record for _, record in runtime._read_attempts(spec, "extract")]
                self.assertEqual(before, after, "실패가 기존 evidence를 바꿨다")

    def test_running_attempt_is_never_used_as_a_completed_hit(self) -> None:
        spec = self.spec()

        def interrupt(uri: str) -> None:
            raise InjectedInterrupt(uri)

        with self.assertRaises(InjectedInterrupt):
            self.runtime.run_job(
                spec,
                {"extract": emit("hello")},
                injection=FailureInjection(after_promote=interrupt),
            )
        crashed = self.attempts(spec, "extract")
        self.assertEqual([record["status"] for record in crashed], ["running"])

        # CAS에는 orphan object가 남아 있다 — 그래도 hit가 되어서는 안 된다.
        self.assertTrue(
            any(path.is_file() for path in (self.root / "artifacts" / "sha256").rglob("*"))
        )

        calls = [0]
        outcome = self.runtime.run_job(spec, {"extract": emit("hello", calls)}).outcome("extract")
        self.assertEqual(outcome.cache_status, "miss")
        self.assertEqual(calls[0], 1)

    def test_completed_is_written_only_after_the_outputs_are_re_verified(self) -> None:
        """checkpoint를 artifact 재검증보다 먼저 쓰면 거짓 완료가 만들어진다.

        승격 직후·완료 기록 직전에 출력을 손상시켜 순서 계약(§3.4)을 관측한다.
        """

        spec = self.spec()

        def corrupt(refs: tuple[Any, ...]) -> None:
            target = self.runtime.store.absolute(refs[0]["uri"], "uri")
            target.write_text("corrupted after promotion", encoding="utf-8")

        self.assert_violation(
            "E_ARTIFACT_CORRUPT",
            self.runtime.run_job,
            spec,
            {"extract": emit("hello")},
            injection=FailureInjection(after_stage_outputs=corrupt),
        )
        records = self.attempts(spec, "extract")
        self.assertEqual([record["status"] for record in records], ["failed"])
        self.assertEqual(
            [record for record in records if record["status"] == "completed"],
            [],
            "재검증에 실패했는데 completed checkpoint가 남았다",
        )
        self.assertEqual(self.manifest(spec)["stages"], [])

    def test_interrupt_just_before_the_completed_write_is_not_a_completion(self) -> None:
        """§3.4 4번 전에 종료되면 완료가 아니다.

        재검증까지 끝난 뒤 completed 기록 **직전**에 중단시킨다. checkpoint를 재검증보다
        먼저 써 두는 구현이면 이 시점에 이미 completed record가 남아 다음 실행이 hit가 된다.
        """

        spec = self.spec()

        def interrupt(attempt_id: str) -> None:
            raise InjectedInterrupt(attempt_id)

        with self.assertRaises(InjectedInterrupt):
            self.runtime.run_job(
                spec,
                {"extract": emit("hello")},
                injection=FailureInjection(before_completed_write=interrupt),
            )
        crashed = self.attempts(spec, "extract")
        self.assertEqual(
            [record["status"] for record in crashed],
            ["running"],
            "완료 기록 전에 죽었는데 completed record가 남았다",
        )

        calls = [0]
        outcome = self.runtime.run_job(spec, {"extract": emit("hello", calls)}).outcome("extract")
        self.assertEqual(outcome.cache_status, "miss")
        self.assertEqual(calls[0], 1)

    def test_verify_checkpoint_rejects_a_non_completed_record(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        record = copy.deepcopy(self.attempts(spec, "extract")[0])
        record["status"] = "running"
        self.assert_violation(
            "E_CHECKPOINT_INVALID", self.runtime._verify_checkpoint, record, "attempt.json"
        )

    def test_completed_record_is_never_modified_by_a_later_run(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        path = self.runtime.attempts_dir(spec, "extract") / "a0001.json"
        before = path.read_bytes()
        for _ in range(3):
            self.runtime.run_job(spec, {"extract": emit("hello")})
        self.assertEqual(path.read_bytes(), before)


class InterruptionTests(RuntimeCase):
    def test_running_attempt_is_preserved_as_interrupted_with_a_new_id(self) -> None:
        spec = self.spec()

        def interrupt(uri: str) -> None:
            raise InjectedInterrupt(uri)

        with self.assertRaises(InjectedInterrupt):
            self.runtime.run_job(
                spec,
                {"extract": emit("hello")},
                injection=FailureInjection(after_promote=interrupt),
            )
        before = self.attempts(spec, "extract")
        self.assertEqual([record["attempt_id"] for record in before], ["a0001"])

        result = self.runtime.run_job(spec, {"extract": emit("hello")})
        after = {record["attempt_id"]: record for record in self.attempts(spec, "extract")}
        self.assertEqual(sorted(after), ["a0001", "a0002"])
        self.assertEqual(after["a0001"]["status"], "interrupted")
        self.assertEqual(after["a0002"]["status"], "completed")
        self.assertEqual(result.outcome("extract").attempt_id, "a0002")

    def test_stage_failure_records_evidence_without_a_completed_checkpoint(self) -> None:
        spec = self.spec()

        def boom(context: StageContext) -> Sequence[StageOutput]:
            (context.workspace / "partial.txt").write_text("partial", encoding="utf-8")
            raise RuntimeError("stage 내부 실패")

        self.assert_violation("E_STAGE_FAILED", self.runtime.run_job, spec, {"extract": boom})
        records = self.attempts(spec, "extract")
        self.assertEqual([record["status"] for record in records], ["failed"])
        self.assertEqual(records[0]["error_code"], "E_STAGE_FAILED")
        self.assertEqual(self.manifest(spec)["status"], "failed")
        self.assertEqual(self.manifest(spec)["stages"], [])

    def test_missing_callable_is_a_stage_failure(self) -> None:
        spec = self.spec()
        self.assert_violation("E_STAGE_FAILED", self.runtime.run_job, spec, {})
        self.assertEqual([r["status"] for r in self.attempts(spec, "extract")], ["failed"])

    def test_partial_resume_reuses_only_completed_stages(self) -> None:
        spec = self.two_stage()
        alpha, beta = [0], [0]

        def failing(context: StageContext) -> Sequence[StageOutput]:
            raise RuntimeError("beta 실패")

        self.assert_violation(
            "E_STAGE_FAILED",
            self.runtime.run_job,
            spec,
            {"alpha": emit("A", alpha), "beta": failing},
        )
        self.assertEqual(alpha[0], 1)

        result = self.runtime.run_job(spec, {"alpha": emit("A", alpha), "beta": emit("B", beta)})
        self.assertEqual(alpha[0], 1, "완료된 A를 다시 실행했다")
        self.assertEqual(beta[0], 1)
        self.assertEqual(result.outcome("alpha").cache_status, "hit")
        self.assertEqual(result.outcome("beta").cache_status, "miss")
        self.assertEqual(
            sorted(record["status"] for record in self.attempts(spec, "beta")),
            ["completed", "failed"],
        )


class ResumeFingerprintTests(RuntimeCase):
    def test_changed_job_identity_refuses_to_continue_the_existing_job(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        before = self.runtime.manifest_path(spec).read_bytes()

        changed = JobSpec(
            job_id=spec.job_id,
            pipeline_id="pipe-b",
            stages=spec.stages,
            source_identity=spec.source_identity,
        )
        error = self.assert_violation(
            "E_RESUME_FINGERPRINT", self.runtime.run_job, changed, {"extract": emit("hello")}
        )
        self.assertEqual(error.location, "job_fingerprint")
        self.assertEqual(self.runtime.manifest_path(spec).read_bytes(), before)

    def test_a_new_job_id_is_the_documented_way_forward(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        fresh = JobSpec(
            job_id="job-b", pipeline_id="pipe-b", stages=spec.stages, source_identity="src-1"
        )
        self.assertEqual(self.runtime.run_job(fresh, {"extract": emit("hello")}).status, "completed")

    def test_stage_config_change_still_resumes_the_same_job(self) -> None:
        """job identity가 아닌 stage fingerprint 변경은 resume을 막지 않는다."""

        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        changed = JobSpec(
            job_id=spec.job_id,
            pipeline_id=spec.pipeline_id,
            source_identity=spec.source_identity,
            stages=(
                StageSpec(
                    **{**spec.stages[0].__dict__, "config_hash": canonical_hash({"config": "b"})}
                ),
            ),
        )
        outcome = self.runtime.run_job(changed, {"extract": emit("hello")}).outcome("extract")
        self.assertEqual(outcome.cache_status, "miss")


# ---------------------------------------------------------------------------
# 관측과 민감정보
# ---------------------------------------------------------------------------


class ObservabilityTests(RuntimeCase):
    def test_attempt_record_carries_the_contracted_observations(self) -> None:
        stage = StageSpec(
            stage_id="extract",
            implementation_version="extract/1.0.0",
            config_hash=canonical_hash({"config": "a"}),
            dependency_fingerprint=canonical_hash({"deps": "a"}),
            model_hash=canonical_hash({"model": "a"}),
            context_hash=canonical_hash({"context": "a"}),
            chunking_hash=canonical_hash({"chunking": "a"}),
            source_hash=canonical_hash({"source": "a"}),
            random_seed=11,
            reproducibility_tier="T2",
        )
        spec = JobSpec(job_id="job-a", pipeline_id="pipe-a", stages=(stage,))
        self.runtime.run_job(spec, {"extract": emit("hello")})
        record = self.attempts(spec, "extract")[0]

        for key in (
            "stage_id",
            "attempt_id",
            "cache_key",
            "cache_status",
            "cache_reason",
            "started_at",
            "ended_at",
            "wall_duration_seconds",
            "attempt_number",
            "reproducibility_tier",
            "verified_artifact_count",
            "verified_artifact_bytes",
            "callable_invoked",
        ):
            with self.subTest(key=key):
                self.assertIn(key, record)
        self.assertEqual(
            sorted(record["fingerprints"]),
            [
                "chunking_hash",
                "config_hash",
                "context_hash",
                "dependency_fingerprint",
                "implementation_version",
                "model_hash",
                "random_seed",
                "source_hash",
            ],
        )
        self.assertEqual(record["outputs"][0]["byte_size"], 5)
        self.assertRegex(record["outputs"][0]["content_hash"], r"^sha256:[0-9a-f]{64}$")

    def test_unmeasured_fields_are_absent_rather_than_faked_as_zero(self) -> None:
        """측정하지 않은 GPU VRAM·CPU·RAM 값을 0으로 위조하지 않는다."""

        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        record = self.attempts(spec, "extract")[0]
        for forbidden in ("gpu_vram_bytes", "cpu_percent", "ram_bytes", "peak_vram_mb"):
            self.assertNotIn(forbidden, record)
        # 제공되지 않은 선택 fingerprint는 필드 자체가 없다.
        self.assertNotIn("model_hash", record["fingerprints"])
        self.assertNotIn("reproducibility_tier", record)

    def test_cache_hit_records_that_the_callable_was_not_invoked(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        outcome = self.runtime.run_job(spec, {"extract": emit("hello")}).outcome("extract")
        self.assertFalse(outcome.callable_invoked)
        self.assertEqual(outcome.verified_artifact_count, 1)
        self.assertEqual(outcome.verified_artifact_bytes, 5)


class SensitiveDataTests(RuntimeCase):
    SENTINEL = "SENTINEL-TRANSCRIPT-DO-NOT-LOG"

    def test_no_absolute_path_or_source_text_reaches_the_job_tree(self) -> None:
        external = self.root / "outside-input" / "PRIVATE-SOURCE-NAME.txt"
        external.parent.mkdir(parents=True)
        external.write_text(self.SENTINEL, encoding="utf-8")

        spec = self.spec()

        def stage(context: StageContext) -> Sequence[StageOutput]:
            target = context.workspace / "out.txt"
            target.write_text(external.read_text(encoding="utf-8"), encoding="utf-8")
            return [StageOutput(name="out.txt", path=target)]

        self.runtime.run_job(spec, {"extract": stage})

        job_tree = self.runtime.job_dir(spec)
        inspected = 0
        for path in job_tree.rglob("*.json"):
            inspected += 1
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(self.SENTINEL, text, f"{path.name}에 원문이 누출됐다")
            self.assertNotIn(str(self.root), text, f"{path.name}에 절대 경로가 누출됐다")
            self.assertNotIn("PRIVATE-SOURCE-NAME", text)
            self.assertNotIn("outside-input", text)
        self.assertGreater(inspected, 0)

    def test_error_messages_do_not_carry_absolute_paths(self) -> None:
        spec = self.spec()

        def boom(context: StageContext) -> Sequence[StageOutput]:
            raise RuntimeError(f"실패: {self.SENTINEL}")

        error = self.assert_violation(
            "E_STAGE_FAILED", self.runtime.run_job, spec, {"extract": boom}
        )
        self.assertNotIn(str(self.root), str(error))
        self.assertNotIn(self.SENTINEL, str(error))

    def test_artifact_refs_expose_only_relative_uris(self) -> None:
        spec = self.spec()
        result = self.runtime.run_job(spec, {"extract": emit("hello")})
        for ref in result.outcome("extract").outputs:
            self.assertFalse(ref["uri"].startswith("/"))
            self.assertNotIn(str(self.root), ref["uri"])


# ---------------------------------------------------------------------------
# JSON 입력 계약
# ---------------------------------------------------------------------------


class StrictJsonTests(RuntimeCase):
    def test_duplicate_keys_nan_and_infinity_are_rejected(self) -> None:
        for text in (
            '{"a": 1, "a": 2}',
            '{"a": NaN}',
            '{"a": Infinity}',
            '{"a": -Infinity}',
        ):
            with self.subTest(text=text):
                with self.assertRaises(JsonInputError):
                    loads_strict(text)

    def test_corrupt_manifest_json_is_a_stable_error(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        path = self.runtime.manifest_path(spec)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(
            json.dumps(manifest)[:-1] + ', "status": "queued"}', encoding="utf-8"
        )
        self.assert_violation(
            "E_CHECKPOINT_INVALID", self.runtime.run_job, spec, {"extract": emit("hello")}
        )

    def test_schema_violating_attempt_record_is_rejected(self) -> None:
        spec = self.spec()
        self.runtime.run_job(spec, {"extract": emit("hello")})
        path = self.runtime.attempts_dir(spec, "extract") / "a0001.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["status"] = "not-a-status"
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assert_violation(
            "E_SCHEMA", self.runtime.run_job, spec, {"extract": emit("hello")}
        )


class JobSchemaTests(unittest.TestCase):
    def test_schema_set_reuses_the_common_contract(self) -> None:
        schemas = job_schema_set()
        self.assertEqual(set(schemas.documents), set(JOB_SCHEMA_FILES))
        job = schemas.documents[JOB_SCHEMA_FILE]
        self.assertEqual(job["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertTrue(job["$id"].endswith(JOB_SCHEMA_FILE))
        self.assertIs(job["additionalProperties"], False)
        self.assertEqual(
            job["properties"]["schema_version"]["$ref"],
            "common-v1.schema.json#/$defs/schema_version",
        )

    def test_artifact_ref_is_reused_by_relative_ref(self) -> None:
        schemas = job_schema_set()
        attempt = schemas.documents[JOB_SCHEMA_FILE]["$defs"]["AttemptRecord"]
        for field in ("inputs", "outputs"):
            self.assertEqual(
                attempt["properties"][field]["items"]["$ref"],
                "common-v1.schema.json#/$defs/ArtifactRef",
            )

    def test_attempt_pointer_resolves(self) -> None:
        schemas = job_schema_set()
        node, document = schemas.resolve(f"{JOB_SCHEMA_FILE}#{ATTEMPT_RECORD_POINTER}", JOB_SCHEMA_FILE)
        self.assertEqual(document, JOB_SCHEMA_FILE)
        self.assertIs(node["additionalProperties"], False)

    def test_production_objects_are_closed(self) -> None:
        job = job_schema_set().documents[JOB_SCHEMA_FILE]
        for name, definition in job["$defs"].items():
            if definition.get("type") == "object":
                with self.subTest(definition=name):
                    self.assertIs(definition["additionalProperties"], False)


# ---------------------------------------------------------------------------
# J-01~J-16 fixture
# ---------------------------------------------------------------------------


class FixtureCoverageTests(unittest.TestCase):
    def test_every_case_id_is_present_exactly_once(self) -> None:
        found = [load_fixture(path)["case_id"] for path in discover_fixtures(FIXTURE_DIR)]
        self.assertEqual(len(found), len(EXPECTED_CASE_IDS))
        self.assertEqual(sorted(found), sorted(EXPECTED_CASE_IDS))
        self.assertEqual(len(set(found)), len(found), "중복 case ID")

    def test_every_scenario_is_bound_to_a_real_driver(self) -> None:
        scenarios = [load_fixture(path)["scenario"] for path in discover_fixtures(FIXTURE_DIR)]
        self.assertEqual(sorted(scenarios), sorted(SCENARIOS))
        self.assertEqual(len(set(scenarios)), len(scenarios))

    def test_every_fixture_actually_runs_the_production_api(self) -> None:
        for path in discover_fixtures(FIXTURE_DIR):
            with self.subTest(fixture=path.name):
                outcome = evaluate_fixture(path)
                self.assertTrue(outcome.passed, "\n".join(outcome.mismatches))
                self.assertTrue(outcome.observed, "관측값이 비었다")

    def test_a_tampered_expectation_makes_the_runner_fail(self) -> None:
        """runner가 expected를 그대로 통과시키지 않는다는 것을 직접 확인한다."""

        source = FIXTURE_DIR / "j-02.json"
        fixture = json.loads(source.read_text(encoding="utf-8"))
        fixture["expect"]["cache_status"] = "miss"
        with TemporaryDirectory(prefix="mcs-fixture-") as temporary:
            target = Path(temporary) / "j-02.json"
            target.write_text(json.dumps(fixture), encoding="utf-8")
            outcome = evaluate_fixture(target)
        self.assertFalse(outcome.passed)
        self.assertTrue(any("cache_status" in message for message in outcome.mismatches))

    def test_unknown_scenario_is_rejected(self) -> None:
        with TemporaryDirectory(prefix="mcs-fixture-") as temporary:
            target = Path(temporary) / "j-99.json"
            target.write_text(
                json.dumps(
                    {"case_id": "J-99", "title": "t", "scenario": "nope", "expect": {}}
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ContractViolation):
                load_fixture(target)


if __name__ == "__main__":
    unittest.main()
