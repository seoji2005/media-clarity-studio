"""Small non-media TASK-032 contract and controlled-resume fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from media_clarity.artifact_store import ArtifactStore
from media_clarity.job_runtime import (
    InjectedInterrupt,
    JobRuntime,
    JobSpec,
    StageContext,
    StageOutput,
    StageSpec,
    canonical_hash,
    canonical_json_bytes,
)
from media_clarity.schema_core import load_strict

from .contracts import (
    CANDIDATE_ORDER,
    STRATA,
    load_pack_ref,
    validate_decision_rule,
    validate_pack_pair,
    validate_recovery_fixture_report,
)


class SyntheticFixtureError(AssertionError):
    """The deterministic fixture failed its own invariant."""


def _write_source(root: Path, sequence: int, name: str, payload: bytes) -> Path:
    path = root / "fixture-sources" / f"{sequence:04d}-{name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


class _FixtureStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = ArtifactStore(root)
        self.sequence = 0

    def bytes(
        self,
        name: str,
        payload: bytes,
        *,
        kind: str,
        media_type: str,
        stage_id: str = "fixture-evidence",
    ) -> Mapping[str, Any]:
        self.sequence += 1
        source = _write_source(self.root, self.sequence, name, payload)
        return self.store.add_file(
            source,
            job_id="task032-synthetic-contract",
            stage_id=stage_id,
            kind=kind,
            media_type=media_type,
        ).ref

    def json(self, name: str, document: Any) -> Mapping[str, Any]:
        return self.bytes(
            name,
            canonical_json_bytes(document),
            kind="text",
            media_type="application/json",
        )


def _synthetic_clip(store: _FixtureStore, role: str, index: int, stratum: str) -> dict[str, Any]:
    clip_id = f"{role}-clip-{index + 1:02d}"
    original = store.bytes(
        f"{clip_id}-original.wav",
        b"synthetic-original:" + clip_id.encode("ascii"),
        kind="audio",
        media_type="audio/wav",
    )
    evaluated = store.bytes(
        f"{clip_id}-evaluated.wav",
        b"synthetic-evaluated:" + clip_id.encode("ascii"),
        kind="audio",
        media_type="audio/wav",
    )
    reference = store.json(f"{clip_id}-reference.json", {"clip_id": clip_id, "fixture_only": True})
    spans = store.json(f"{clip_id}-spans.json", {"clip_id": clip_id, "spans": []})
    annotations = store.json(f"{clip_id}-annotations.json", {"clip_id": clip_id, "items": []})
    non_speech = stratum == "silence_non_speech"
    tts_engine = "" if non_speech else ("fixture-tts-a" if index % 2 == 0 else "fixture-tts-b")
    return {
        "clip_id": clip_id,
        "source_id": f"fixture-source-{role}-{index + 1:02d}",
        "stratum": stratum,
        "duration_seconds": 1.0,
        "source_class": "synthetic_non_sensitive",
        "source_kind": "non_speech" if non_speech else "tts",
        "license_id": "self-generated-synthetic-fixture",
        "upload_classification": "work_allowed_non_sensitive",
        "tts_engine_id": tts_engine,
        "original_audio_ref": dict(original),
        "evaluated_audio_ref": dict(evaluated),
        "reference_transcript_ref": dict(reference),
        "language_spans_ref": dict(spans),
        "item_annotations_ref": dict(annotations),
        "degradation_recipe": "fixture-byte-marker-v1",
        "original_hash": original["content_hash"],
        "evaluated_hash": evaluated["content_hash"],
    }


def decision_rule_document(primary_hash: str, reserve_hash: str) -> dict[str, Any]:
    """Return the exact TASK-032 §5.1/§5.2 rule, not a tunable default."""

    report = {
        "schema_version": "1.0.0",
        "kind": "AsrScreenDecisionRule/v1",
        "candidate_order": list(CANDIDATE_ORDER),
        "primary_pack_hash": primary_hash,
        "reserve_pack_hash": reserve_hash,
        "primary_metric": "fatal_clip_rate",
        "denominator": "all_scored_clips",
        "tier_order": [
            "fatal_rate_and_safety_cells",
            "human_correction_seconds_per_audio_minute",
            "japanese_cer_and_english_wer",
            "mixed_and_names_numbers_terms_error_rate",
        ],
        "source_cluster_key": "source_id",
        "bootstrap": {
            "method": "percentile_cluster_bootstrap",
            "iterations": 10000,
            "seed": 32061,
            "confidence_level": 0.95,
            "sidedness": "bilateral",
            "minimum_source_groups": 5,
        },
        "mpe": {
            "fatal_clip_rate": {
                "formula": "max(event_numerator/eligible_clip_count,absolute_floor)",
                "event_numerator": 1,
                "absolute_floor": 0.01,
                "denominator_key": "eligible_clip_count",
            },
            "correction_time": {
                "formula": "max(absolute_seconds_per_audio_minute,slower_mean_fraction*pairwise_slower_mean)",
                "absolute_seconds_per_audio_minute": 3.0,
                "slower_mean_fraction": 0.05,
            },
            "text_error_rates": 0.01,
            "safety_cell_event_count": 1,
        },
        "pairwise_policy": {
            "difference": "A-minus-B-lower-is-better",
            "materially_better": "ci_upper_lt_negative_mpe",
            "equivalent": "whole_ci_within_plus_minus_mpe",
            "indeterminate": "otherwise_or_ci_missing_or_source_groups_below_minimum",
            "fatal_safety_veto": "A_safety_cells_must_all_be_lte_B",
            "tier_descent": "equivalent_only_and_fatal_safety_cells_equal",
            "text_tier_win": "all_applicable_ci_upper_lte_mpe_and_one_ci_upper_lt_negative_mpe",
            "unique_bottom": "exactly_one_candidate_loses_to_each_other_candidate",
        },
        "reserve_policy": {
            "trigger": "no_unique_bottom_on_primary",
            "participants": "all_three_candidates",
            "primary_verdict": "reserve_required",
            "combined_rule": "same_rule_on_primary_plus_reserve",
            "unresolved_verdict": "inconclusive",
        },
    }
    return report


def build_contract_fixture(root: Path) -> dict[str, Any]:
    """Create two tiny synthetic packs and a CAS-bound decision rule."""

    fixture = _FixtureStore(root)
    pack_refs: dict[str, Mapping[str, Any]] = {}
    pack_documents: dict[str, Mapping[str, Any]] = {}
    for role in ("primary", "reserve"):
        document = {
            "schema_version": "1.0.0",
            "kind": "AsrScreenPackManifest/v1",
            "pack_id": f"task032-{role}-synthetic-fixture",
            "role": role,
            "purpose": "synthetic_fixture",
            "total_duration_seconds": 6.0,
            "clips": [
                _synthetic_clip(fixture, role, index, stratum)
                for index, stratum in enumerate(STRATA)
            ],
        }
        ref = fixture.json(f"{role}-pack.json", document)
        loaded, load_findings = load_pack_ref(ref, store=fixture.store, location=f"fixture/{role}")
        if load_findings or loaded is None:
            raise SyntheticFixtureError(load_findings[0].as_line())
        pack_refs[role] = ref
        pack_documents[role] = loaded

    pack_findings = validate_pack_pair(
        pack_documents["primary"], pack_documents["reserve"], store=fixture.store
    )
    if pack_findings:
        raise SyntheticFixtureError(pack_findings[0].as_line())

    rule = decision_rule_document(
        pack_refs["primary"]["content_hash"], pack_refs["reserve"]["content_hash"]
    )
    rule_ref = fixture.json("decision-rule.json", rule)
    rule_findings = validate_decision_rule(
        rule,
        primary_pack_ref=pack_refs["primary"],
        reserve_pack_ref=pack_refs["reserve"],
    )
    if rule_findings:
        raise SyntheticFixtureError(rule_findings[0].as_line())
    return {
        "schema_version": "1.0.0",
        "kind": "AsrScreenSyntheticContractFixture/v1",
        "purpose": "synthetic_fixture_only",
        "primary_pack_ref": dict(pack_refs["primary"]),
        "reserve_pack_ref": dict(pack_refs["reserve"]),
        "decision_rule_ref": dict(rule_ref),
        "candidate_output_generated": False,
        "target_windows_compatibility": "not_evaluated",
    }


def _emit_unit(calls: dict[str, int], name: str, text: str):
    def run(context: StageContext) -> Sequence[StageOutput]:
        calls[name] += 1
        target = context.workspace / f"{name}.json"
        target.write_bytes(canonical_json_bytes({"fixture": True, "unit": name, "text": text}))
        return [StageOutput(name=target.name, path=target, kind="text", media_type="application/json")]

    return run


def run_recovery_fixture(root: Path) -> dict[str, Any]:
    """Interrupt each candidate once after unit 1, then prove exact resume behavior."""

    candidates: list[dict[str, Any]] = []
    for candidate_id in CANDIDATE_ORDER:
        candidate_root = root / candidate_id
        candidate_root.mkdir(parents=True, exist_ok=True)
        runtime = JobRuntime(candidate_root)
        stages = (
            StageSpec(
                stage_id="unit-001",
                implementation_version="task032-synthetic-unit/1.0.0",
                config_hash=canonical_hash({"candidate": candidate_id, "unit": 1}),
                random_seed=32061,
                reproducibility_tier="T2",
            ),
            StageSpec(
                stage_id="unit-002",
                implementation_version="task032-synthetic-unit/1.0.0",
                depends_on=("unit-001",),
                config_hash=canonical_hash({"candidate": candidate_id, "unit": 2}),
                random_seed=32061,
                reproducibility_tier="T2",
            ),
        )
        spec = JobSpec(
            job_id=f"sentinel-{candidate_id}",
            pipeline_id="task032-synthetic-recovery",
            source_identity=f"synthetic-{candidate_id}",
            stages=stages,
        )
        calls = {"unit-001": 0, "unit-002": 0}
        interrupted = {"done": False}
        unit_1 = _emit_unit(calls, "unit-001", candidate_id)

        def interrupt_once(context: StageContext) -> Sequence[StageOutput]:
            calls["unit-002"] += 1
            if not interrupted["done"]:
                interrupted["done"] = True
                raise InjectedInterrupt(candidate_id)
            target = context.workspace / "unit-002.json"
            target.write_bytes(
                canonical_json_bytes(
                    {"fixture": True, "unit": "unit-002", "text": candidate_id}
                )
            )
            return [
                StageOutput(
                    name=target.name,
                    path=target,
                    kind="text",
                    media_type="application/json",
                )
            ]

        try:
            runtime.run_job(spec, {"unit-001": unit_1, "unit-002": interrupt_once})
        except InjectedInterrupt:
            pass
        else:  # pragma: no cover - fixture invariant
            raise SyntheticFixtureError(f"{candidate_id}: controlled interruption did not occur")

        manifest_before = load_strict(runtime.manifest_path(spec))
        unit_1_before = dict(manifest_before["stages"][0])
        unit_1_record_before = dict(runtime._read_attempts(spec, "unit-001")[0][1])
        result = runtime.run_job(spec, {"unit-001": unit_1, "unit-002": interrupt_once})
        unit_1_after = result.outcome("unit-001")
        unit_2_after = result.outcome("unit-002")
        attempts_2 = [record for _, record in runtime._read_attempts(spec, "unit-002")]
        statuses = [record["status"] for record in attempts_2]

        if calls != {"unit-001": 1, "unit-002": 2}:
            raise SyntheticFixtureError(f"{candidate_id}: unexpected callable counts {calls}")
        if unit_1_after.cache_status != "hit" or unit_1_after.callable_invoked:
            raise SyntheticFixtureError(f"{candidate_id}: completed unit was not reused")
        if unit_1_after.attempt_id != unit_1_before["attempt_id"]:
            raise SyntheticFixtureError(f"{candidate_id}: completed attempt identity changed")
        if list(unit_1_after.outputs) != unit_1_record_before["outputs"]:
            raise SyntheticFixtureError(f"{candidate_id}: completed output refs changed")
        if statuses != ["interrupted", "completed"]:
            raise SyntheticFixtureError(f"{candidate_id}: interrupted attempt was not preserved")
        if unit_2_after.attempt_id != "a0002" or unit_2_after.cache_status != "miss":
            raise SyntheticFixtureError(f"{candidate_id}: incomplete unit did not get a fresh attempt")

        candidates.append(
            {
                "candidate_id": candidate_id,
                "interruption_count": 1,
                "ordered_units": ["unit-001", "unit-002"],
                "unit_001_attempt_id_before": unit_1_before["attempt_id"],
                "unit_001_attempt_id_after": unit_1_after.attempt_id,
                "unit_001_cache_status_after": unit_1_after.cache_status,
                "unit_002_attempt_statuses": statuses,
                "unit_002_completed_attempt_id": unit_2_after.attempt_id,
            }
        )
    report = {
        "schema_version": "1.0.0",
        "kind": "AsrScreenSyntheticRecoveryFixture/v1",
        "candidate_order": list(CANDIDATE_ORDER),
        "candidates": candidates,
        "candidate_output_generated": False,
        "target_windows_compatibility": "not_evaluated",
    }
    report_findings = validate_recovery_fixture_report(report)
    if report_findings:
        raise SyntheticFixtureError(report_findings[0].as_line())
    return report
