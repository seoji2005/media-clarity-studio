# TASK-031 dependency lock 절차

이 디렉터리의 `*.in`은 네 개의 격리 환경에 넣을 **직접 dependency**만 고정한다.
한 환경으로 합치지 않는다. 실행 정본은
[`config/task-031-preflight.json`](../../config/task-031-preflight.json)이며,
Windows에서 만든 transitive hash lock과 CUDA stack이 아직 없으면
`python -m media_clarity.calibration validate --require-ready`가 반드시 실패한다.

## Windows 11에서 lock 만들기

1. RTX 4070 SUPER 대상 PC에서 manifest의 고정 경로
   `.task031-envs/<environment_id>/Scripts/python.exe`에 Python 3.12 격리 환경 네 개를 만든다.
2. 사용할 `uv`를 설치한다. version 문자열을 손으로 신뢰하지 않고 아래 environment evidence
   capture와 readiness live re-probe가 `uv --version` 결과·실행 파일 hash에 결박한다.
3. 각 input을 Windows x86_64 / Python 3.12 대상으로 해석한다. 예:

   ```powershell
   uv pip compile requirements/task-031/faster-whisper.in `
     --python-version 3.12 --python-platform windows `
     --generate-hashes --no-header --no-annotate `
     --output-file requirements/task-031/locks/faster-whisper-windows-py312.lock
   ```

4. 같은 방식으로 `download.in`, `qwen-asr.in`, `translation.in`을 각각 해석한다. validator는
   각 lock의 모든 resolved requirement가 exact pin과 SHA-256 hash를 갖는지뿐 아니라 해당 `.in`의
   **모든 direct `name==version`이 exact version으로 포함되는지** 검사한다. direct package 누락·교체,
   unrelated package만 든 lock은 실패한다. transitive package는 허용한다.
   GPU 환경은 실제 driver와 호환되는 PyTorch/CUDA/cuDNN 조합을 먼저 확인하고, 필요한
   공식 wheel index와 정확한 package pin을 해당 input에 반영한 뒤 **영향받는 lock 전체를
   다시 생성**한다. faster-whisper는 공식 요구대로 CUDA 12 cuBLAS와 cuDNN 9를 확인한다.
5. 각 input과 lock의 SHA-256과 `lock_status: "windows_resolved"`를 manifest에 기록하고,
   lock으로 각 고정 환경을 설치한다. 그 환경의 고정 Python으로 capture를 실행한다. 이 명령이
   resolver/direct package/Windows build/GPU/driver/CUDA runtime/PyTorch/cuDNN을 **실제로 probe**하고,
   닫힌 receipt와 SHA-256을 기록하며 manifest version field를 probe 값으로만 갱신한다.

   ```powershell
   $env:PYTHONPATH = "src"
   .task031-envs/faster-whisper/Scripts/python.exe -m media_clarity.calibration `
     capture-environment --environment-id faster-whisper
   ```

   `download`, `qwen-asr`, `translation`도 자기 고정 interpreter로 각각 실행한다.
   다른 interpreter·비-Windows host·direct package 불일치·CUDA probe 실패는 receipt를 만들지 않는다.
6. 네 receipt가 생긴 뒤 다음 hard gate를 실행한다.

   ```powershell
   $env:PYTHONPATH = "src"
   python -m media_clarity.calibration validate --require-ready --model-root .
   ```

readiness는 receipt의 outer digest와 내부 raw/parsed equality만 검사하고 끝내지 않는다. manifest에 고정된
네 Python executable을 다시 실행해 target-Windows live probe를 얻고 receipt와 exact equality로 비교한다.
따라서 임의의 non-empty resolver/CUDA 문자열, receipt 변조·재hash, environment drift는 실패한다.
lock·environment evidence·CUDA·model receipt 중 하나라도 없거나 digest/live 값이 다르면 모델 실행을
시작하지 않는다. 이 검사는 악의적인 local administrator에 대한 원격 attestation을 주장하지 않는다.
model weight와 calibration pack은 Git에 추가하지 않는다.
