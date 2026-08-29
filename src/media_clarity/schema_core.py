"""공용 JSON Schema 부분집합 검사기 (TASK-028에서 TASK-006 구현을 추출).

TASK-006의 `eval_contracts`와 TASK-028의 `job_runtime`이 **같은** schema 해석을 쓰도록
한 곳에 모은다. 두 모듈이 각자 keyword 해석을 복제하면 조용히 갈라진다
(TASK-028 §3.6).

여기에 있는 것:

- duplicate key와 `NaN`/`Infinity`를 거부하는 JSON 로더
- 실제 `schemas/*.schema.json` 파일을 읽고 상대 `$ref`를 해석하는 `SchemaSet`
- `SUPPORTED_KEYWORDS` **부분집합만** 검사하는 `SchemaValidator`
- 안정 코드 + 위치를 담는 `Finding`과 결정적 정렬
- schema `pattern`이 모양만 고정하는 값의 의미 검사
  (`utc_timestamp_error`, `portable_relative_path_error`)

Python 3.12 표준 라이브러리만 사용한다. 외부 jsonschema package를 추가하지 않는다.

**Draft 2020-12 전체 구현이 아니다.** `SUPPORTED_KEYWORDS`에 나열한 부분집합만
정확히 검사하고, 그 밖의 keyword가 schema에 나타나면 데이터 오류가 아니라
계약 결함으로 보고 `SchemaContractError`를 던진다. `pattern`은 ECMA-262가 아니라
Python `re`로 해석하므로, schema에는 두 문법에서 뜻이 같은 표현만 쓴다.

이 모듈은 **읽기 전용**이다. 검증 실패에서 입력이나 기존 artifact를 수정·삭제하지 않는다.
"""

from __future__ import annotations

import datetime
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "1.0.0"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"

#: 모든 schema set이 공유하는 공통 계약 파일. 버전 고정 검사의 기준이다.
COMMON_SCHEMA_FILE = "common-v1.schema.json"

#: 이 validator가 **정확히** 검사하는 keyword. 그 밖의 keyword는 지원하지 않는다.
SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "properties",
        "patternProperties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        # 프로젝트 확장 annotation. JSON Schema 표준 keyword가 아니며, 이 validator가
        # 값에 따라 stdlib 의미 검사를 추가로 수행한다 (현재 "utc_timestamp" 하나).
        "x-mcs-semantic",
    }
)

#: `x-mcs-semantic`으로 요청할 수 있는 의미 검사.
SEMANTIC_CHECKS = frozenset({"utc_timestamp"})

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class SchemaContractError(RuntimeError):
    """schema 자체가 이 validator의 지원 범위를 벗어났다 — 데이터 오류가 아니다."""


class JsonInputError(ValueError):
    """JSON 자체가 계약을 어겼다 (중복 key, NaN/Infinity, 파싱 실패)."""


@dataclass(frozen=True, order=True)
class Finding:
    """안정 코드 + 위반 위치. 정렬 키로 그대로 쓰므로 필드 순서가 곧 출력 순서다."""

    location: str
    code: str
    message: str

    def as_line(self) -> str:
        return f"{self.code} {self.location} {self.message}"


def sort_findings(findings: Iterable[Finding]) -> list[Finding]:
    """결정적인 순서 — (위치, 코드, 메시지) 사전순."""

    return sorted(findings)


# ---------------------------------------------------------------------------
# JSON 로딩 — duplicate key와 NaN/Infinity를 거부한다.
# ---------------------------------------------------------------------------


def _reject_constant(name: str) -> Any:
    raise JsonInputError(f"JSON 상수 {name}는 허용하지 않는다 (finite 값만 허용)")


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise JsonInputError(f"중복 key: {key!r}")
        seen[key] = value
    return seen


def loads_strict(text: str) -> Any:
    """duplicate key와 NaN/Infinity를 거부하는 JSON 파서."""

    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def load_strict(path: Path) -> Any:
    return loads_strict(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# schema 로딩과 $ref 해석
# ---------------------------------------------------------------------------


class SchemaSet:
    """실제 schema 파일 묶음. `$ref`는 같은 디렉터리의 파일 이름으로 해석한다.

    `filenames`는 이 묶음이 읽을 파일 목록이다. 공통 계약 파일은 상대 `$ref` 대상이자
    버전 고정 기준이므로 반드시 포함해야 한다.
    """

    def __init__(self, directory: Path, filenames: Sequence[str]):
        if COMMON_SCHEMA_FILE not in filenames:
            raise SchemaContractError(
                f"schema 묶음에 {COMMON_SCHEMA_FILE}가 없다 — 상대 $ref를 해석할 수 없다"
            )
        self.directory = directory
        self.filenames = tuple(filenames)
        self.documents: dict[str, Any] = {}
        for name in self.filenames:
            path = directory / name
            if not path.is_file():
                raise SchemaContractError(f"schema 파일이 없다: {path}")
            document = load_strict(path)
            self._assert_root_contract(name, document)
            self.documents[name] = document
        self._assert_pinned_version()
        for name, document in self.documents.items():
            self._assert_supported(document, f"{name}#")

    def _assert_pinned_version(self) -> None:
        pinned = self.documents[COMMON_SCHEMA_FILE]["$defs"]["schema_version"].get("const")
        if pinned != SCHEMA_VERSION:
            raise SchemaContractError(
                f"{COMMON_SCHEMA_FILE}의 schema_version const({pinned!r})가 "
                f"모듈 상수 SCHEMA_VERSION({SCHEMA_VERSION!r})와 다르다"
            )

    @staticmethod
    def _assert_root_contract(name: str, document: Any) -> None:
        if not isinstance(document, dict):
            raise SchemaContractError(f"{name}: root가 객체가 아니다")
        if document.get("$schema") != SCHEMA_DIALECT:
            raise SchemaContractError(f"{name}: $schema는 {SCHEMA_DIALECT}여야 한다")
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id.endswith(name):
            raise SchemaContractError(f"{name}: 안정적인 $id가 파일 이름과 맞지 않는다")

    def _assert_supported(self, node: Any, location: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{location}/{key}"
                if location.endswith("/properties") or location.endswith("/$defs"):
                    self._assert_supported(value, child)
                    continue
                if location.endswith("/patternProperties"):
                    self._assert_supported(value, child)
                    continue
                if key not in SUPPORTED_KEYWORDS:
                    raise SchemaContractError(
                        f"{child}: 지원하지 않는 JSON Schema keyword {key!r}. "
                        "이 validator는 SUPPORTED_KEYWORDS 부분집합만 검사한다."
                    )
                if key == "x-mcs-semantic":
                    if value not in SEMANTIC_CHECKS:
                        raise SchemaContractError(
                            f"{child}: 알 수 없는 x-mcs-semantic 값 {value!r}. "
                            f"지원: {', '.join(sorted(SEMANTIC_CHECKS))}"
                        )
                    continue
                if key in {"enum", "const", "required"}:
                    continue
                self._assert_supported(value, child)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                self._assert_supported(item, f"{location}/{index}")

    def resolve(self, ref: str, current: str) -> tuple[Any, str]:
        """`$ref`를 (schema 노드, 소속 문서 이름)으로 해석한다."""

        if ref.startswith("#"):
            document_name = current
            pointer = ref[1:]
        else:
            file_part, _, fragment = ref.partition("#")
            document_name = file_part
            pointer = fragment
            if document_name not in self.documents:
                raise SchemaContractError(f"알 수 없는 $ref 대상: {ref}")
        node: Any = self.documents[document_name]
        for token in [t for t in pointer.split("/") if t != ""]:
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or token not in node:
                raise SchemaContractError(f"해석할 수 없는 $ref: {ref}")
            node = node[token]
        return node, document_name


# ---------------------------------------------------------------------------
# Draft 2020-12 부분집합 검사기
# ---------------------------------------------------------------------------


_TYPE_TABLE: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "boolean": (bool,),
    "number": (int, float),
    "integer": (int,),
    "null": (type(None),),
}


def _is_type(value: Any, expected: str) -> bool:
    if expected == "boolean":
        return isinstance(value, bool)
    if expected in {"number", "integer"} and isinstance(value, bool):
        return False
    if expected == "integer":
        return isinstance(value, int)
    return isinstance(value, _TYPE_TABLE[expected])


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


class SchemaValidator:
    """SUPPORTED_KEYWORDS만 검사한다. 그 이상을 주장하지 않는다."""

    def __init__(self, schemas: SchemaSet):
        self.schemas = schemas

    def validate(
        self,
        instance: Any,
        schema_file: str,
        location: str,
        pointer: str = "",
    ) -> list[Finding]:
        """`schema_file`(선택적으로 그 안의 `pointer`) 기준으로 검사한다.

        `pointer`는 하나의 schema 파일이 여러 production 문서 형태를 담을 때 쓴다
        (예: `job-v1.schema.json#/$defs/AttemptRecord`). 기본값은 root schema다.
        """

        findings: list[Finding] = []
        root = self.schemas.documents[schema_file]
        if pointer:
            root, schema_file = self.schemas.resolve(f"{schema_file}#{pointer}", schema_file)
        self._check(instance, root, schema_file, location, findings)
        return findings

    def _fail(self, findings: list[Finding], location: str, message: str) -> None:
        findings.append(Finding(location=location, code="E_SCHEMA", message=message))

    def _check(
        self,
        instance: Any,
        schema: Any,
        document: str,
        location: str,
        findings: list[Finding],
    ) -> None:
        if not isinstance(schema, dict):
            raise SchemaContractError(f"{location}: schema 노드가 객체가 아니다")

        if "$ref" in schema:
            target, target_document = self.schemas.resolve(schema["$ref"], document)
            self._check(instance, target, target_document, location, findings)
            return

        declared_type = schema.get("type")
        if declared_type is not None:
            expected = [declared_type] if isinstance(declared_type, str) else list(declared_type)
            if not any(_is_type(instance, name) for name in expected):
                self._fail(
                    findings,
                    location,
                    f"type 불일치: {'|'.join(expected)} 필요, {type(instance).__name__} 발견",
                )
                return

        if "const" in schema and instance != schema["const"]:
            self._fail(findings, location, f"const 불일치: {schema['const']!r} 필요")
            return

        if "enum" in schema and not any(
            instance == option and _is_type(instance, "boolean") == _is_type(option, "boolean")
            for option in schema["enum"]
        ):
            self._fail(findings, location, f"enum 밖의 값: {instance!r}")
            return

        if isinstance(instance, str):
            self._check_string(instance, schema, location, findings)
        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            self._check_number(instance, schema, location, findings)
        if isinstance(instance, list):
            self._check_array(instance, schema, document, location, findings)
        if isinstance(instance, dict):
            self._check_object(instance, schema, document, location, findings)

    def _check_string(
        self, instance: str, schema: Mapping[str, Any], location: str, findings: list[Finding]
    ) -> None:
        minimum = schema.get("minLength")
        if minimum is not None and len(instance) < minimum:
            self._fail(findings, location, f"minLength {minimum} 미만")
        maximum = schema.get("maxLength")
        if maximum is not None and len(instance) > maximum:
            self._fail(findings, location, f"maxLength {maximum} 초과")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, instance) is None:
            self._fail(findings, location, f"pattern 불일치: {pattern}")
            return
        if schema.get("x-mcs-semantic") == "utc_timestamp":
            reason = utc_timestamp_error(instance)
            if reason is not None:
                findings.append(
                    Finding(location, "E_TIMESTAMP", f"RFC 3339 UTC timestamp가 아니다: {reason}")
                )

    def _check_number(
        self, instance: float, schema: Mapping[str, Any], location: str, findings: list[Finding]
    ) -> None:
        if isinstance(instance, float) and not math.isfinite(instance):
            self._fail(findings, location, "finite 숫자가 아니다")
            return
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            self._fail(findings, location, f"minimum {minimum} 미만")
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            self._fail(findings, location, f"maximum {maximum} 초과")
        exclusive_min = schema.get("exclusiveMinimum")
        if exclusive_min is not None and instance <= exclusive_min:
            self._fail(findings, location, f"exclusiveMinimum {exclusive_min} 이하")
        exclusive_max = schema.get("exclusiveMaximum")
        if exclusive_max is not None and instance >= exclusive_max:
            self._fail(findings, location, f"exclusiveMaximum {exclusive_max} 이상")

    def _check_array(
        self,
        instance: list[Any],
        schema: Mapping[str, Any],
        document: str,
        location: str,
        findings: list[Finding],
    ) -> None:
        min_items = schema.get("minItems")
        if min_items is not None and len(instance) < min_items:
            self._fail(findings, location, f"minItems {min_items} 미만")
        max_items = schema.get("maxItems")
        if max_items is not None and len(instance) > max_items:
            self._fail(findings, location, f"maxItems {max_items} 초과")
        if schema.get("uniqueItems") is True:
            seen: set[str] = set()
            for index, item in enumerate(instance):
                key = _canonical(item)
                if key in seen:
                    self._fail(findings, f"{location}/{index}", "uniqueItems 위반")
                seen.add(key)
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(instance):
                self._check(item, item_schema, document, f"{location}/{index}", findings)

    def _check_object(
        self,
        instance: dict[str, Any],
        schema: Mapping[str, Any],
        document: str,
        location: str,
        findings: list[Finding],
    ) -> None:
        properties = schema.get("properties") or {}
        pattern_properties = schema.get("patternProperties") or {}
        for name in schema.get("required") or []:
            if name not in instance:
                # 없는 leaf를 가리키면 JSON Pointer로 해석되지 않는다. 실제로 존재하는
                # 부모 객체를 가리키고 누락 필드 이름은 메시지에 담는다 (REVIEW-016 R-03-R2).
                self._fail(findings, location, f"필수 필드 누락: {name}")

        additional = schema.get("additionalProperties")
        for key in instance:
            child = f"{location}/{key}"
            if key in properties:
                self._check(instance[key], properties[key], document, child, findings)
                continue
            matched = False
            for pattern, subschema in pattern_properties.items():
                if re.search(pattern, key) is not None:
                    self._check(instance[key], subschema, document, child, findings)
                    matched = True
                    break
            if matched:
                continue
            if additional is False:
                self._fail(findings, child, "허용되지 않은 추가 필드 (닫힌 객체)")
            elif isinstance(additional, dict):
                self._check(instance[key], additional, document, child, findings)


# ---------------------------------------------------------------------------
# 의미 검사 — schema pattern이 모양만 고정하는 값의 실제 유효성
# ---------------------------------------------------------------------------

_TIMESTAMP_RE = re.compile(
    r"^(?P<y>[0-9]{4})-(?P<mo>[0-9]{2})-(?P<d>[0-9]{2})"
    r"T(?P<h>[0-9]{2}):(?P<mi>[0-9]{2}):(?P<s>[0-9]{2})(?:\.[0-9]+)?Z$"
)


def utc_timestamp_error(value: Any) -> str | None:
    """실제 달력·시각으로 성립하지 않는 UTC timestamp의 사유. 성립하면 None.

    schema의 `pattern`은 모양만 고정하므로 `2026-99-99T99:99:99Z`가 통과한다
    (REVIEW-014 R-01). 여기서 stdlib `datetime`으로 월별 일수와 윤년, 시·분·초
    범위를 실제로 검사한다. 외부 dependency를 쓰지 않는다.

    **경계:** RFC 3339가 허용하는 윤초(`:60`)는 `datetime`이 표현하지 못하므로
    거부한다. 이 프로젝트의 timestamp는 윤초를 쓰지 않는다.
    """

    if not isinstance(value, str):
        return "문자열이 아니다"
    match = _TIMESTAMP_RE.match(value)
    if match is None:
        return "Z로 끝나는 RFC 3339 UTC 형식이 아니다"
    try:
        datetime.datetime(
            int(match.group("y")),
            int(match.group("mo")),
            int(match.group("d")),
            int(match.group("h")),
            int(match.group("mi")),
            int(match.group("s")),
            tzinfo=datetime.timezone.utc,
        )
    except ValueError as exc:
        return str(exc)
    return None


# ---------------------------------------------------------------------------
# 경로 규칙 — run 산출물만 portable relative path로 제한한다.
# ---------------------------------------------------------------------------


def portable_relative_path_error(value: Any) -> str | None:
    """run 산출물 경로 위반 사유. 위반이 없으면 None.

    `ArtifactRef.uri`에는 적용하지 않는다. 그쪽은 외부 입력 URI를 표현할 수 있는
    불투명 문자열이다.
    """

    if not isinstance(value, str) or value == "":
        return "빈 경로"
    if value != value.strip():
        return "앞뒤 공백"
    if "\\" in value:
        return "역슬래시 (Windows 경로 구분자)"
    if value.startswith("/"):
        return "POSIX 절대 경로"
    if _WINDOWS_DRIVE_RE.match(value):
        return "Windows drive 경로"
    if value.startswith("//"):
        return "UNC 경로"
    if "\x00" in value:
        return "NUL 문자"
    segments = value.split("/")
    for segment in segments:
        if segment == "":
            return "빈 경로 구간"
        if segment == "..":
            return ".. traversal"
        if segment == ".":
            return "'.' 구간"
    return None
