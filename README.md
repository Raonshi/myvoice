# MyVoice

현재 버전은 2.0.0입니다.

MyVoice는 사용자 본인의 음성 샘플을 재사용 가능한 Voice Profile로 등록하고, TXT/Markdown 대본을 세그먼트별로 합성해 AAC-LC 내레이션으로 만드는 로컬 우선 macOS 데스크톱/CLI 프로젝트입니다.

## 현재 구현 범위

- reference 음성의 형식·무음·레벨 품질 검증
- 앞뒤 무음 제거, EBU R128 기반 음량 안정화, mono 24 kHz PCM16 reference 전처리
- 길이·무음 비율·레벨을 종합한 reference 품질 점수와 최적 primary 자동 선택
- Voice Profile과 원본 해시·동의 정보 저장
- TXT 및 Markdown AST 파싱
- YAML 발음 사전과 결정론적 텍스트 정규화
- 길이·문단·문장 기반 segmentation
- Chatterbox Multilingual V3 지연 로딩 adapter
- 세그먼트 WAV 캐시, 중단 후 resume, 선택 segment regenerate
- master WAV 병합 및 FFmpeg AAC-LC mono 192 kbps 인코딩
- Typer/Rich CLI와 Bash/Zsh에서 동작하는 기본 대화형 터미널 메뉴
- 등록·생성·Voice 관리·Job 재개/세그먼트 재생성·환경 진단을 제공하는 네이티브 macOS SwiftUI 앱
- 모델 다운로드가 필요 없는 test-tone 기반 통합 테스트

## 요구 환경

- Python 3.11 또는 3.12
- FFmpeg와 FFprobe
- 실제 합성 시 PyTorch, torchaudio와 프로젝트가 고정한 공식 Chatterbox Git revision
- Apple Silicon Mac과 MPS 실행 환경 권장
- Intel Mac에서는 CPU 합성 호환

Chatterbox의 공식 프로젝트는 Python 3.11에서 개발·시험되었다고 안내합니다. 이 프로젝트는 3.11과 3.12를 허용하지만, TTS extra 설치가 플랫폼별 native dependency와 충돌하면 Python 3.11 환경을 우선 사용하세요. PyPI 0.1.7은 Multilingual V3 선택 인자를 포함하지 않아, 이 프로젝트는 V3 API가 포함된 공식 Git commit을 고정합니다.

Apple Silicon에서는 Rosetta로 실행되는 x86_64 Python보다 네이티브 arm64 Python을 사용하세요. `--device auto`는 실제 MPS 연산을 시험한 뒤 성공하면 Apple GPU를 사용하고, 사용할 수 없으면 CPU로 전환합니다. `--device mps`를 명시한 경우에는 CPU로 조용히 전환하지 않고 진단 가능한 오류를 반환합니다.

안정성을 위해 PyTorch가 지원하지 않는 일부 MPS 연산에는 CPU fallback을 허용합니다. `PYTORCH_ENABLE_MPS_FALLBACK`을 사용자가 미리 지정한 경우 그 설정을 존중합니다. 수치 정확도나 성능 회귀 위험이 있는 MPS fast-math, 강제 Metal matmul, `torch.compile`, 반정밀도 변환은 기본으로 활성화하지 않습니다.

## 설치

macOS에서 FFmpeg를 설치합니다.

```bash
brew install ffmpeg
```

프로젝트 환경과 기본 CLI/TUI를 설치합니다.

```bash
uv sync --extra dev
```

실제 Chatterbox 합성 기능까지 설치합니다. 큰 PyTorch 패키지와 모델 파일이 필요합니다.

```bash
uv sync --extra dev --extra tts
```

환경 상태를 확인합니다.

```bash
uv run myvoice doctor
```

Apple Silicon에서 `MPS built`, `MPS available`, `MPS operation`, `Auto device`가 각각 `OK`, `OK`, `OK`, `mps`인지 확인하세요.

## 녹음 준비

등록에는 고정된 파일 개수나 파일당 최소 길이를 요구하지 않습니다. 지원 형식의 유효한 음성 파일이 하나 이상 있으면 등록할 수 있으며, 분량보다 실제로 합성에 사용될 reference 한 개의 품질이 더 중요합니다.

자연스러운 결과를 얻으려면 다음 조건을 권장합니다.

- 한 사람이 중간에 끊지 않고 자연스럽게 말한 선명한 6~10초 구간
- 생성 언어와 같은 언어·억양으로 녹음된 reference
- 평소 말투, 속도, 높낮이가 드러나는 완전한 문장과 다양한 발음
- 일정한 마이크 거리와 입력 레벨, clipping 없이 충분한 음량
- 배경 음악, 다른 화자, 환경 소음, 강한 리버브와 긴 무음이 없는 원본
- 과도한 노이즈 제거, 음정 변경, 속도 변경이나 여러 녹음을 인위적으로 이어 붙이지 않은 음성

Chatterbox Multilingual은 화자 조건에 앞부분 최대 약 6초, 생성 조건에 최대 약 10초를 사용합니다. 더 긴 파일이 반드시 더 자연스러운 결과를 만들지는 않습니다. 여러 파일을 등록하면 MyVoice는 각 파일의 앞뒤 무음을 제거하고 목표 음량으로 안정화한 뒤, 유효 길이·무음 비율·peak level을 점수화해 가장 깨끗한 파일을 primary reference로 선택합니다. 원본의 음색을 훼손할 수 있는 강한 denoise, pitch 또는 속도 변경은 적용하지 않습니다.

입력 형식은 WAV, FLAC, AAC, M4A, MP3, OGG를 허용하며 FFmpeg가 내부 WAV 형식으로 변환합니다.

## 기본 사용법

### macOS 데스크톱 앱

개발 환경에서 앱을 빌드하고 실행합니다.

```bash
./script/build_and_run.sh
```

생성된 앱은 `dist/MyVoiceDesktop.app`에 있습니다. 앱의 사이드바에서 다음 기능을 모두 사용할 수 있습니다.

- 음성 샘플 폴더 분석과 Voice Profile 등록·교체
- TXT/Markdown 대본, Voice Profile, 출력 AAC, 처리 장치, 발음 사전 선택 후 생성 또는 dry run
- Voice Profile 상세 확인과 삭제
- 생성 Job 및 세그먼트 상태 확인, 실패한 Job 재개, 텍스트 수정 후 개별 세그먼트 재생성
- Python, FFmpeg, Chatterbox, PyTorch와 Apple Silicon MPS 진단

앱은 기본적으로 프로젝트의 `.venv/bin/myvoice`, Homebrew 설치 경로, `PATH` 순서로 기존 CLI 백엔드를 찾습니다. 별도 위치에 설치했다면 MyVoice 설정에서 실행 파일의 절대 경로를 지정하세요. 앱과 CLI는 같은 application data 폴더와 같은 서비스 로직을 사용하므로 한쪽에서 만든 Voice와 Job을 다른 쪽에서도 이어서 사용할 수 있습니다.

### CLI/TUI

본인 목소리이거나 명시적 사용 권한이 있다는 확인과 함께 Voice Profile을 만듭니다.

```bash
uv run myvoice enroll ./voice_samples \
  --name youtube \
  --language ko \
  --i-have-rights
```

대본 구조와 segment만 미리 확인합니다. TTS 모델은 실행하지 않습니다.

```bash
uv run myvoice speak ./script.md \
  --voice youtube \
  --output ./narration.aac \
  --dry-run
```

실제 음성을 생성합니다.

```bash
uv run myvoice speak ./script.md \
  --voice youtube \
  --output ./narration.aac \
  --device auto
```

작업과 segment를 확인합니다.

```bash
uv run myvoice jobs list
uv run myvoice inspect <job-id>
```

중단된 작업을 재개하거나 한 segment만 다시 만듭니다.

```bash
uv run myvoice resume <job-id>
uv run myvoice regenerate <job-id> seg-0023
uv run myvoice regenerate <job-id> seg-0023 --text "수정한 낭독 문장입니다."
```

기존 CLI 인터페이스는 2.0.0에서도 그대로 유지됩니다. 인자 없이 실행하면 현재 Bash/Zsh 터미널 안에서 숫자로 조작하는 메뉴가 열립니다.

```bash
uv run myvoice
```

```text
MyVoice — Voice cloning TTS

[1] Enroll voice
[2] Generate AAC
[3] List voices
[4] List jobs
[0] Exit
Select:
```

Enroll 완료 후에는 바로 Generate 단계로 이동할지 묻습니다. Generate를 시작하면 저장된 enrollment 목록이 번호와 함께 표시되며, 사용할 목소리를 목록에서 선택합니다. 방금 만든 profile은 기본 선택으로 표시되지만 다른 profile도 선택할 수 있습니다.

## 발음 사전

`examples/pronunciation.yaml` 형식을 복사해 사용합니다.

```bash
uv run myvoice speak script.md \
  --voice youtube \
  --output narration.aac \
  --pronunciation-dict pronunciation.yaml
```

정규화 결과는 각 job의 `script.normalized.txt`에 저장됩니다. 의미, 숫자, 고유명사가 바뀌지 않았는지 실제 생성 전에 검수하세요.

## 데이터 위치

기본 저장 위치는 운영체제의 application data 디렉터리입니다. 테스트나 이동식 환경에서는 `MYVOICE_DATA_DIR`로 바꿀 수 있습니다.

```bash
export MYVOICE_DATA_DIR="$PWD/work/myvoice-data"
```

Voice Profile에는 전처리된 reference 음성과 원본 해시가 들어갑니다. 이 폴더는 생체정보에 준하는 민감한 데이터로 취급해야 합니다.

## 개발 및 테스트

```bash
uv run pytest
swift test
./script/build_and_run.sh --verify
```

테스트는 실제 Chatterbox 모델 대신 짧은 PCM tone을 생성해 enrollment, segmentation, resume, regenerate, WAV assembly 경로를 검증합니다. 실제 모델 smoke test와 청취 품질 평가는 별도의 GPU/MPS 환경에서 수행해야 합니다.

## 문제 해결

Chatterbox의 `Sampling n/1000`에서 1000은 완료해야 하는 작업량이 아니라 생성 가능한 최대 speech token 수입니다. MyVoice는 이를 완료율로 오해하지 않도록 Sampling 진행 표시에서 퍼센트와 진행 막대를 제거하고 생성 토큰 수·경과 시간·속도만 표시합니다. 자연스러운 발화 종료를 뜻하는 EOS token이 나오면 1000 이전에 Sampling이 끝나고 다음 단계로 진행하는 것이 정상입니다. 1000/1000에 도달하는 경우가 반복되거나 긴 무음이 생성된다면 정상적인 조기 종료가 아니므로 해당 segment를 다시 생성하고 입력 문장을 더 짧게 나누세요.

MyVoice는 같은 작업의 segment마다 동일한 reference 음성을 다시 분석하지 않고 준비된 화자 조건을 메모리에서 재사용합니다. reference 파일, 장치 또는 exaggeration이 바뀌면 조건을 자동으로 다시 준비합니다.

MPS를 명시했는데 사용할 수 없다는 오류가 나오면 다음 명령으로 네이티브 arm64 실행과 실제 MPS 연산 결과를 확인하세요.

```bash
uv run myvoice doctor
```

Chatterbox는 세그먼트를 32-bit float WAV로 저장할 수 있습니다. MyVoice는 병합 전에 이를 mono 24 kHz PCM16 WAV로 자동 표준화하므로 별도 변환은 필요하지 않습니다.

합성은 끝났지만 병합 또는 AAC 인코딩에서 중단된 job은 완료된 세그먼트를 다시 생성하지 않고 재개할 수 있습니다.

```bash
uv run myvoice jobs list
uv run myvoice resume <job-id>
```

재개가 실패하면 job의 상태와 실제 오류를 확인합니다.

```bash
uv run myvoice inspect <job-id>
```

## 제한 사항

- Enrollment는 모델 fine-tuning이 아니라 품질 분석과 전처리를 거친 reference를 저장하는 방식입니다.
- Chatterbox V3가 현재 여러 reference를 한 호출에 직접 받지 않으므로, 품질 점수가 가장 높은 유효 reference를 primary prompt로 사용합니다. 다른 reference와 각 품질 분석 결과는 profile에 보존됩니다.
- 강한 denoise와 자동 음질 복원은 음색 손상을 피하기 위해 구현하지 않았습니다.
- 터미널 TUI는 빠른 등록과 생성 흐름에 집중하며, 전체 관리 기능은 macOS 앱 또는 개별 CLI 명령에서 제공합니다.
- Chatterbox가 생성하는 오디오에는 upstream 프로젝트의 Perth 비가청 워터마크가 포함됩니다.
- 모델 및 weight의 라이선스와 배포 조건은 사용 시점에 다시 검토하세요.

## 책임 있는 사용

본인 목소리 또는 명시적으로 사용 허가를 받은 화자의 음성만 등록하세요. 생성 음성을 신원 사칭, 사기, 기만 또는 해당 플랫폼 정책을 위반하는 목적으로 사용해서는 안 됩니다.
