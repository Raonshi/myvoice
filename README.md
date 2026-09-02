# MyVoice

MyVoice는 사용자 본인의 음성 샘플을 재사용 가능한 Voice Profile로 등록하고, TXT/Markdown 대본을 세그먼트별로 합성해 AAC-LC 내레이션으로 만드는 로컬 우선 CLI/TUI 프로젝트입니다.

## 현재 구현 범위

- 5개 이상, 파일당 10초 이상 음성 검증
- mono 24 kHz PCM16 reference 전처리
- Voice Profile과 원본 해시·동의 정보 저장
- TXT 및 Markdown AST 파싱
- YAML 발음 사전과 결정론적 텍스트 정규화
- 길이·문단·문장 기반 segmentation
- Chatterbox Multilingual V3 지연 로딩 adapter
- 세그먼트 WAV 캐시, 중단 후 resume, 선택 segment regenerate
- master WAV 병합 및 FFmpeg AAC-LC mono 192 kbps 인코딩
- Typer/Rich CLI와 Bash/Zsh에서 동작하는 기본 대화형 터미널 메뉴
- 모델 다운로드가 필요 없는 test-tone 기반 통합 테스트

## 요구 환경

- Python 3.11 또는 3.12
- FFmpeg와 FFprobe
- 실제 합성 시 PyTorch, torchaudio와 프로젝트가 고정한 공식 Chatterbox Git revision
- Chatterbox 모델을 실행할 수 있는 CPU, CUDA GPU 또는 Apple Silicon MPS 환경

Chatterbox의 공식 프로젝트는 Python 3.11에서 개발·시험되었다고 안내합니다. 이 프로젝트는 3.11과 3.12를 허용하지만, TTS extra 설치가 플랫폼별 native dependency와 충돌하면 Python 3.11 환경을 우선 사용하세요. PyPI 0.1.7은 Multilingual V3 선택 인자를 포함하지 않아, 이 프로젝트는 V3 API가 포함된 공식 Git commit을 고정합니다.

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

## 녹음 준비

같은 사람의 음성을 동일한 마이크와 비슷한 거리에서 녹음하세요.

- 음원 파일 최소 5개
- 각 파일의 실제 발화 길이 최소 10초
- 권장 총 발화 길이 60~120초
- 배경 음악, 다른 사람의 말, clipping, 강한 리버브 금지
- 실제 영상에서 원하는 자연스러운 설명 톤 권장

입력 형식은 WAV, FLAC, AAC, M4A, MP3, OGG를 허용하며 FFmpeg가 내부 WAV 형식으로 변환합니다.

## 기본 사용법

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

인자 없이 실행하면 별도의 GUI나 전체화면 프레임워크 없이, 현재 Bash/Zsh 터미널 안에서 숫자로 조작하는 메뉴가 열립니다.

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
```

테스트는 실제 Chatterbox 모델 대신 짧은 PCM tone을 생성해 enrollment, segmentation, resume, regenerate, WAV assembly 경로를 검증합니다. 실제 모델 smoke test와 청취 품질 평가는 별도의 GPU/MPS 환경에서 수행해야 합니다.

## 제한 사항

- MVP의 enrollment는 모델 fine-tuning이 아니라 전처리 reference를 저장하는 방식입니다.
- Chatterbox V3가 현재 여러 reference를 한 호출에 직접 받지 않으므로, 가장 긴 유효 reference를 primary prompt로 사용합니다. 다른 reference는 profile에 보존됩니다.
- 강한 denoise와 자동 음질 복원은 음색 손상을 피하기 위해 구현하지 않았습니다.
- 대화형 터미널 메뉴는 enrollment, 저장된 voice 선택, dry-run, 전체 생성을 제공합니다. 세그먼트별 상세 편집·재생은 CLI의 `inspect`와 `regenerate`를 사용합니다.
- Chatterbox가 생성하는 오디오에는 upstream 프로젝트의 Perth 비가청 워터마크가 포함됩니다.
- 모델 및 weight의 라이선스와 배포 조건은 사용 시점에 다시 검토하세요.

## 책임 있는 사용

본인 목소리 또는 명시적으로 사용 허가를 받은 화자의 음성만 등록하세요. 생성 음성을 신원 사칭, 사기, 기만 또는 해당 플랫폼 정책을 위반하는 목적으로 사용해서는 안 됩니다.
