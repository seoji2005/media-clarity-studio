"""TASK-028 content-addressed artifact store.

계약은 `docs/tasks/TASK-028.md` §3.1~§3.2다. 요약하면 다음 네 가지를 지킨다.

1. **원본 불변** — 입력 파일과 기존 artifact를 어떤 실패 경로에서도 수정·삭제하지 않는다.
2. **no-overwrite** — 최종 CAS object는 덮어쓰지 않는다. 원자적 no-overwrite 승격을
   제공할 수 없는 filesystem에서는 덮어쓰는 fallback 대신 안정 오류로 실패한다.
3. **content-addressing** — SHA-256을 chunked streaming으로 계산한다. 입력 전체를 RAM에
   올리지 않는다. URI는 project root 기준 portable relative path다.
4. **검증 후에만 완료** — 승격한 바이트를 다시 열어 hash·size를 확인한 뒤에만
   `ArtifactRef/v1`을 만든다.

Python 3.12 표준 라이브러리만 사용한다.

**자동 삭제·GC·eviction이 없다.** 보관 정책 U-16이 미정이므로 이 모듈은 어떤 파일도
스스로 지우지 않는다. 실패한 임시 파일은 증거로 남고, 완료 artifact나 cache hit로
보이지 않는다.

**멀티프로세스 공격자에 대한 완전한 보안을 주장하지 않는다.** 이번 TASK는 local
synchronous runtime이며, 경로 검사는 사고와 설정 실수를 막는 수준이다.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence


SCHEMA_VERSION = "1.0.0"

#: CAS 최종 object가 사는 곳. project root 기준 relative.
CAS_ROOT = "artifacts/sha256"

#: 검증 전 임시 파일이 사는 곳. CAS lookup은 여기를 보지 않으므로 임시 파일이
#: 완료 artifact나 cache hit로 보일 수 없다.
INCOMING_ROOT = "artifacts/incoming"

#: streaming hash chunk. 입력 전체를 RAM에 올리지 않는다.
CHUNK_BYTES = 1 << 20

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: filesystem segment로 그대로 쓸 수 있는 식별자. 공통 identifier는 ':'을 허용하지만
#: Windows에서 쓸 수 없으므로 여기서는 더 좁힌다 (TASK-028 §3.1).
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

#: Windows 예약 장치명. 확장자가 붙어도 예약이다 (`CON.txt`).
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


# ---------------------------------------------------------------------------
# 안정 오류 코드 — 메시지 문구가 아니라 이 코드와 위치가 계약이다.
# ---------------------------------------------------------------------------

ERROR_CODES = (
    "E_JSON",
    "E_SCHEMA",
    "E_UNSAFE_PATH",
    "E_ARTIFACT_COLLISION",
    "E_ARTIFACT_MISSING",
    "E_ARTIFACT_CORRUPT",
    "E_ARTIFACT_PROMOTE",
    "E_INPUT_CHANGED",
    "E_RESUME_FINGERPRINT",
    "E_STATE_TRANSITION",
    "E_DAG_CYCLE",
    "E_DAG_DEPENDENCY",
    "E_DAG_DUPLICATE_STAGE",
    "E_STAGE_FAILED",
    "E_CHECKPOINT_INVALID",
)


class ContractViolation(RuntimeError):
    """안정 코드 + 위치를 가진 계약 위반.

    `location`은 실제 입력에서 해석되는 JSON Pointer이거나 계약된 filesystem 위치
    (project root 기준 relative path)다. 메시지에는 외부 절대 경로나 원본 텍스트를
    담지 않는다 (TASK-028 §3.7).
    """

    def __init__(
        self,
        code: str,
        location: str,
        message: str,
        temp_paths: Sequence[str] = (),
    ):
        if code not in ERROR_CODES:
            raise AssertionError(f"선언되지 않은 오류 코드: {code}")
        super().__init__(f"{code} {location} {message}")
        self.code = code
        self.location = location
        self.detail = message
        #: 이 실패로 **실제로 보존된** 임시 파일의 project root 기준 relative path.
        #: 파일만 orphan으로 남기면 복구·QC 증거가 되지 않으므로 호출자가 attempt record에
        #: 연결할 수 있게 예외에 실어 보낸다 (REVIEW-018 M-04). 성공 뒤 삭제된 경로는
        #: 여기에 담지 않는다.
        self.temp_paths: tuple[str, ...] = tuple(temp_paths)


# ---------------------------------------------------------------------------
# 경로 안전성 — filesystem을 바꾸기 **전에** 거부한다.
# ---------------------------------------------------------------------------


def path_segment_error(value: Any) -> str | None:
    """filesystem segment로 쓸 수 없는 식별자의 사유. 쓸 수 있으면 None.

    공통 `identifier`가 허용하는 `:`은 Windows에서 경로 구분 의미를 가지므로
    여기서는 거부한다. 결정적으로 안전한 이름으로 변환하지 않고 **거부**하는 쪽을
    택했다 — 조용한 변환은 서로 다른 ID를 같은 디렉터리로 접을 수 있다.
    """

    if not isinstance(value, str) or value == "":
        return "빈 식별자"
    if len(value) > 128:
        return "128자 초과"
    if _PATH_SEGMENT_RE.match(value) is None:
        return "허용 문자 밖 (A-Za-z0-9로 시작하고 A-Za-z0-9._- 만 허용)"
    if value in {".", ".."}:
        return "'.' 또는 '..'"
    if value.endswith(".") or value.endswith(" "):
        return "마지막 문자가 dot 또는 space (Windows 비호환)"
    if value.split(".")[0].upper() in _WINDOWS_RESERVED:
        return "Windows 예약 장치명"
    return None


def relative_path_error(value: Any) -> str | None:
    """portable relative path 위반 사유. 위반이 없으면 None.

    POSIX 절대 경로·Windows drive·UNC·`..`·빈 segment·Windows 비호환 segment를
    모두 거부한다. `schema_core.portable_relative_path_error`보다 엄격하다 —
    저쪽은 기록된 문자열의 모양만 보고, 이쪽은 실제로 파일을 만들 경로를 본다.
    """

    if not isinstance(value, str) or value == "":
        return "빈 경로"
    if value != value.strip():
        return "앞뒤 공백"
    if "\x00" in value:
        return "NUL 문자"
    if "\\" in value:
        return "역슬래시 (Windows 경로 구분자)"
    if value.startswith("//"):
        return "UNC 경로"
    if value.startswith("/"):
        return "POSIX 절대 경로"
    if _WINDOWS_DRIVE_RE.match(value):
        return "Windows drive 경로"
    for segment in value.split("/"):
        if segment == "":
            return "빈 경로 구간"
        if segment in {".", ".."}:
            return f"'{segment}' 구간"
        reason = path_segment_error(segment)
        if reason is not None:
            return f"경로 구간 {reason}"
    return None


def opaque_identity_error(value: Any) -> str | None:
    """외부 경로처럼 보이는 비민감 식별자의 위반 사유. 문제가 없으면 None.

    `source_identity`는 호출자가 주는 **불투명** 식별자다. 주석만으로는 production API의
    안전 경계가 되지 않으므로, 명백히 경로처럼 보이는 값을 filesystem을 바꾸기 전에
    거부한다 (REVIEW-018 M-03).

    **사유 문자열에 값 자체를 담지 않는다.** 담으면 거부하려던 경로가 예외 메시지와
    로그로 그대로 새어 나간다.
    """

    if not isinstance(value, str) or value == "":
        return "빈 식별자"
    if len(value) > 256:
        return "256자 초과"
    if value != value.strip():
        return "앞뒤 공백"
    if "\x00" in value:
        return "NUL 문자"
    if "\\" in value:
        return "역슬래시 (Windows 경로 구분자)"
    if value.startswith("//"):
        return "UNC 경로처럼 보인다"
    if value.startswith("/"):
        return "POSIX 절대 경로처럼 보인다"
    if _WINDOWS_DRIVE_RE.match(value):
        return "Windows drive 경로처럼 보인다"
    if value.startswith("~"):
        return "home 확장 경로처럼 보인다"
    if "/" in value:
        return "경로 구분자를 포함한다 (불투명 식별자여야 한다)"
    if value in {".", ".."} or ".." in value:
        return "traversal 구간을 포함한다"
    return None


def resolve_inside_root(root: Path, relative: str, location: str) -> Path:
    """`relative`가 root 안에 머무는 절대 경로로 해석한다.

    문자열 검사만으로는 symlink를 통한 탈출을 막지 못하므로, 이미 존재하는 상위
    경로를 `os.path.realpath`로 풀어 root 안인지 확인한다.
    """

    reason = relative_path_error(relative)
    if reason is not None:
        raise ContractViolation("E_UNSAFE_PATH", location, f"portable relative path가 아니다: {reason}")

    root_real = Path(os.path.realpath(root))
    target = root / relative

    # 존재하는 가장 깊은 조상을 실제 경로로 풀어 symlink 탈출을 잡는다.
    probe = target
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    probe_real = Path(os.path.realpath(probe))
    if probe_real != root_real and root_real not in probe_real.parents:
        raise ContractViolation(
            "E_UNSAFE_PATH", location, "project root 밖을 가리킨다 (symlink 포함)"
        )
    return target


# ---------------------------------------------------------------------------
# streaming hash
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureInjection:
    """결정적 실패·간섭 주입. **production 기본값은 없음(None)이다.**

    실제 subprocess worker나 thread 경쟁 대신 이 hook으로 중단 시나리오를 재현한다.
    호출자가 명시적으로 전달하지 않으면 어떤 hook도 실행되지 않는다.
    """

    #: chunk를 읽은 **직후** 호출된다. J-14의 "복사 중 입력 변경"을 결정적으로 만든다.
    on_chunk: Callable[[int], None] | None = None
    #: CAS 승격 **직후**, 최종 바이트 재검증 전에 호출된다. J-08의 중단 지점이며,
    #: 여기서 파일을 손상시키면 승격 후 재검증이 실제로 동작하는지 확인할 수 있다.
    after_promote: Callable[[str], None] | None = None
    #: stage의 모든 출력을 승격한 **직후**, 재검증 전에 호출된다 (§3.4 2→3 사이).
    after_stage_outputs: Callable[[tuple[Mapping[str, Any], ...]], None] | None = None
    #: 출력 재검증을 마치고 attempt를 `completed`로 전이하기 **직전**에 호출된다
    #: (§3.4 3→4 사이). "4번 전에 종료되면 완료로 간주하지 않는다"를 관측 가능하게 한다.
    before_completed_write: Callable[[str], None] | None = None


def _stat_identity(st: os.stat_result) -> tuple[int, int, int, int, int]:
    """복사 전후 비교용 descriptor stat. 내용이 바뀌면 최소 하나는 달라진다."""

    return (st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino, st.st_dev)


def hash_file(path: Path) -> tuple[str, int]:
    """(64 lowercase hex digest, byte size). chunked streaming."""

    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def content_hash_of(digest: str) -> str:
    return f"sha256:{digest}"


def digest_of(content_hash: str) -> str:
    if _CONTENT_HASH_RE.match(content_hash) is None:
        raise ContractViolation(
            "E_ARTIFACT_CORRUPT", "content_hash", "sha256:<64 lowercase hex> 형식이 아니다"
        )
    return content_hash.split(":", 1)[1]


def cas_relative_uri(digest: str) -> str:
    if _HEX64_RE.match(digest) is None:
        raise ContractViolation("E_ARTIFACT_CORRUPT", "content_hash", "64 lowercase hex가 아니다")
    return f"{CAS_ROOT}/{digest[:2]}/{digest}"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# artifact store
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WriteOutcome:
    """`add_file`의 결과. `deduped`는 같은 바이트가 이미 있었다는 뜻이다."""

    ref: dict[str, Any]
    deduped: bool
    temp_relative_path: str


class ArtifactStore:
    """project root 안의 content-addressed store.

    이 클래스는 **자기가 만든 것 외에는 아무 파일도 만들지 않고, 아무것도 지우지 않는다.**
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        if not self.project_root.is_dir():
            raise ContractViolation(
                "E_UNSAFE_PATH", "project_root", "project root 디렉터리가 없다"
            )

    # -- 경로 -------------------------------------------------------------

    def absolute(self, relative: str, location: str) -> Path:
        return resolve_inside_root(self.project_root, relative, location)

    def cas_path(self, digest: str) -> Path:
        return self.absolute(cas_relative_uri(digest), "artifact_uri")

    # -- 읽기 -------------------------------------------------------------

    def verify_ref(self, ref: Mapping[str, Any], location: str) -> int:
        """`ArtifactRef`가 가리키는 바이트를 **다시 열어** hash·size를 확인한다.

        존재하지 않으면 `E_ARTIFACT_MISSING`, 내용이 다르면 `E_ARTIFACT_CORRUPT`.
        어느 쪽도 기존 파일을 수정하지 않는다. 반환값은 검증한 byte 수다.
        """

        uri = ref.get("uri")
        reason = relative_path_error(uri)
        if reason is not None:
            raise ContractViolation("E_UNSAFE_PATH", f"{location}/uri", f"portable relative path가 아니다: {reason}")
        path = self.absolute(uri, f"{location}/uri")
        if not path.is_file():
            raise ContractViolation("E_ARTIFACT_MISSING", uri, "artifact 파일이 없다")
        digest, size = hash_file(path)
        expected_digest = digest_of(ref["content_hash"])
        if digest != expected_digest:
            raise ContractViolation("E_ARTIFACT_CORRUPT", uri, "content hash가 기록과 다르다")
        if size != ref["byte_size"]:
            raise ContractViolation("E_ARTIFACT_CORRUPT", uri, "byte size가 기록과 다르다")
        return size

    # -- 쓰기 -------------------------------------------------------------

    def add_file(
        self,
        source: Path,
        *,
        job_id: str,
        stage_id: str,
        kind: str = "blob",
        media_type: str = "application/octet-stream",
        parent_refs: Sequence[str] = (),
        created_at: str | None = None,
        injection: FailureInjection | None = None,
    ) -> WriteOutcome:
        """`source`의 바이트를 CAS에 넣고 검증된 `ArtifactRef/v1`을 만든다.

        순서가 계약이다.

        1. 같은 filesystem의 임시 파일에 exclusive create로 streaming 복사하며 hash·size 계산
        2. flush + fsync로 durability 처리
        3. 임시 파일을 **다시 열어** hash·size 재검증
        4. 입력 descriptor stat을 복사 전후 비교해 hashing 중 변경 탐지
        5. 원자적 **no-overwrite** 승격 (`os.link`)
        6. 승격된 최종 바이트를 다시 열어 hash·size 재검증
        7. 그 뒤에만 `ArtifactRef` 생성

        어느 단계에서 실패해도 원본 입력과 기존 CAS object는 바뀌지 않는다.
        """

        for name, value in (("job_id", job_id), ("stage_id", stage_id)):
            reason = path_segment_error(value)
            if reason is not None:
                raise ContractViolation("E_UNSAFE_PATH", name, f"안전한 경로 구간이 아니다: {reason}")

        source = Path(source)
        if not source.is_file():
            raise ContractViolation("E_ARTIFACT_MISSING", "stage_output", "stage 출력 파일이 없다")

        incoming_dir = self.absolute(INCOMING_ROOT, "incoming_root")
        incoming_dir.mkdir(parents=True, exist_ok=True)

        temp_name = f"{job_id}.{stage_id}.{os.getpid()}.{next(_TEMP_COUNTER)}.part"
        temp_relative = f"{INCOMING_ROOT}/{temp_name}"
        temp_path = self.absolute(temp_relative, "temp_path")

        try:
            digest, size = self._stream_to_temp(source, temp_path, injection)

            # 3. 임시 파일을 다시 열어 확인한다. 여기서 어긋나면 승격하지 않는다.
            written_digest, written_size = hash_file(temp_path)
            if written_digest != digest or written_size != size:
                raise ContractViolation(
                    "E_ARTIFACT_CORRUPT", temp_relative, "임시 파일의 hash·size가 계산값과 다르다"
                )

            final_relative = cas_relative_uri(digest)
            final_path = self.absolute(final_relative, "artifact_uri")
            final_path.parent.mkdir(parents=True, exist_ok=True)

            deduped = self._promote(
                temp_path, final_path, temp_relative, final_relative, digest, size
            )

            if injection is not None and injection.after_promote is not None:
                injection.after_promote(final_relative)

            # 6. 승격된 최종 바이트를 다시 확인한다.
            final_digest, final_size = hash_file(final_path)
            if final_digest != digest or final_size != size:
                raise ContractViolation(
                    "E_ARTIFACT_CORRUPT", final_relative, "승격된 artifact의 hash·size가 다르다"
                )
        except ContractViolation as error:
            # 실패로 **실제로 남은** 임시 파일만 증거로 싣는다. 아무것도 지우지 않는다
            # (REVIEW-018 M-04).
            error.temp_paths = self.surviving_temp_paths((temp_relative,))
            raise

        ref = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": f"sha256-{digest}",
            "kind": kind,
            "uri": final_relative,
            "content_hash": content_hash_of(digest),
            "byte_size": size,
            "media_type": media_type,
            "produced_by": {"stage_id": stage_id, "job_id": job_id},
            "created_at": created_at or utc_now(),
            "parent_refs": list(parent_refs),
            "is_estimate": False,
        }
        return WriteOutcome(ref=ref, deduped=deduped, temp_relative_path=temp_relative)

    # -- 내부 -------------------------------------------------------------

    def _stream_to_temp(
        self, source: Path, temp_path: Path, injection: FailureInjection | None
    ) -> tuple[str, int]:
        """입력을 chunk 단위로 읽어 임시 파일에 쓰면서 hash·size를 계산한다.

        입력 descriptor의 stat을 복사 **전후로** 비교해 hashing/copy 중 변경을 탐지한다.
        변경이 있으면 성공 artifact를 만들지 않고 `E_INPUT_CHANGED`로 실패한다.
        """

        digest_obj = hashlib.sha256()
        size = 0
        with open(source, "rb") as reader:
            before = _stat_identity(os.fstat(reader.fileno()))
            # exclusive create — 기존 임시 파일을 덮어쓰지 않는다.
            fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as writer:
                    index = 0
                    while True:
                        chunk = reader.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        writer.write(chunk)
                        digest_obj.update(chunk)
                        size += len(chunk)
                        if injection is not None and injection.on_chunk is not None:
                            injection.on_chunk(index)
                        index += 1
                    # 2. flush + fsync — 가능한 범위에서 durability 처리.
                    writer.flush()
                    os.fsync(writer.fileno())
            except OSError as exc:
                raise ContractViolation(
                    "E_ARTIFACT_PROMOTE", "temp_path", f"임시 파일 쓰기 실패: {exc.strerror}"
                ) from exc
            after = _stat_identity(os.fstat(reader.fileno()))

        if before != after:
            raise ContractViolation(
                "E_INPUT_CHANGED",
                "stage_output",
                "입력 파일이 hashing/copy 중에 바뀌었다 (descriptor stat 불일치)",
            )
        return digest_obj.hexdigest(), size

    def _promote(
        self,
        temp_path: Path,
        final_path: Path,
        temp_relative: str,
        final_relative: str,
        digest: str,
        size: int,
    ) -> bool:
        """원자적 **no-overwrite** 승격. 반환값은 dedupe hit 여부다.

        `os.link`는 대상이 있으면 `FileExistsError`로 실패하는 원자적 연산이다.
        `os.replace`는 덮어쓰므로 CAS 최종 경로에 쓰지 않는다. link를 지원하지 않는
        filesystem에서는 덮어쓰는 fallback 대신 `E_ARTIFACT_PROMOTE`로 실패한다.
        """

        try:
            os.link(temp_path, final_path)
        except FileExistsError:
            # 이미 있는 바이트를 **다시 hash·size 검증**한다. 같으면 dedupe hit,
            # 다르면 손상·collision이며 기존 파일을 수정하지 않는다.
            existing_digest, existing_size = hash_file(final_path)
            if existing_digest != digest or existing_size != size:
                raise ContractViolation(
                    "E_ARTIFACT_COLLISION",
                    final_relative,
                    "같은 경로에 다른 바이트가 있다 (손상 또는 hash collision)",
                )
            return True
        except OSError as exc:
            raise ContractViolation(
                "E_ARTIFACT_PROMOTE",
                final_relative,
                "원자적 no-overwrite 승격을 할 수 없다 "
                f"(hard link 미지원: {exc.strerror}). 덮어쓰기로 대체하지 않는다",
            ) from exc

        # 승격에 성공했으므로 임시 link를 정리한다. 이 unlink는 CAS object가 아니라
        # 방금 만든 임시 이름만 지운다 — 보관 정책(U-16)과 무관하다.
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        return False

    def surviving_temp_paths(self, candidates: Sequence[str]) -> tuple[str, ...]:
        """후보 중 **지금도 디스크에 있는** 임시 경로만 돌려준다.

        성공 승격 뒤 정리된 이름을 실패 증거로 기록하지 않기 위한 확인이다.
        """

        alive: list[str] = []
        for relative in candidates:
            if relative_path_error(relative) is not None:  # pragma: no cover - 내부 생성 경로
                continue
            if (self.project_root / relative).is_file():
                alive.append(relative)
        return tuple(alive)


def _counter() -> Iterator[int]:
    value = 0
    while True:
        yield value
        value += 1


_TEMP_COUNTER = iter(_counter())


def existing_temp_paths(project_root: Path) -> list[str]:
    """증거로 남아 있는 임시 파일 목록 (project root 기준 relative). 삭제하지 않는다."""

    incoming = Path(project_root) / INCOMING_ROOT
    if not incoming.is_dir():
        return []
    return sorted(f"{INCOMING_ROOT}/{entry.name}" for entry in incoming.iterdir() if entry.is_file())
