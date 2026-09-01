# TASK-031 dependency lock 절차

이 디렉터리의 `*.in`은 네 개의 격리 환경에 넣을 **직접 dependency**만 고정한다.
한 환경으로 합치지 않는다. 실행 정본은
[`config/task-031-preflight.json`](../../config/task-031-preflight.json)이며,
Windows에서 만든 transitive hash lock과 CUDA stack이 아직 없으면
`python -m media_clarity.calibration validate --require-ready`가 반드시 실패한다.

## Windows 11에서 lock 만들기

1. RTX 4070 SUPER 대상 PC에서 Python 3.12 격리 환경을 만든다.
2. 사용할 `uv`를 설치하고 `uv --version`의 정확한 값을 manifest의
   `resolver_version`에 기록한다.
3. 각 input을 Windows x86_64 / Python 3.12 대상으로 해석한다. 예:

   ```powershell
   uv pip compile requirements/task-031/faster-whisper.in `
     --python-version 3.12 --python-platform windows `
     --generate-hashes --no-header --no-annotate `
     --output-file requirements/task-031/locks/faster-whisper-windows-py312.lock
   ```

4. 같은 방식으로 `download.in`, `qwen-asr.in`, `translation.in`을 각각 해석한다.
   GPU 환경은 실제 driver와 호환되는 PyTorch/CUDA/cuDNN 조합을 먼저 확인하고, 필요한
   공식 wheel index와 정확한 package pin을 해당 input에 반영한 뒤 **영향받는 lock 전체를
   다시 생성**한다. faster-whisper는 공식 요구대로 CUDA 12 cuBLAS와 cuDNN 9를 확인한다.
5. 각 input과 lock의 SHA-256, `lock_status: "windows_resolved"`, 정확한
   `torch_version`·`cuda_version`·`cudnn_version`, `cuda_stack_status: "windows_locked"`를
   manifest에 기록한다. faster-whisper처럼 PyTorch를 쓰지 않는 환경은
   `torch_version: "not_applicable"`로 기록한다.
6. lock으로 새 환경을 설치한 뒤 다음 hard gate를 실행한다.

   ```powershell
   $env:PYTHONPATH = "src"
   python -m media_clarity.calibration validate --require-ready --model-root .
   ```

lock·CUDA·model receipt 중 하나라도 없거나 digest가 다르면 모델 실행을 시작하지 않는다.
model weight와 calibration pack은 Git에 추가하지 않는다.
