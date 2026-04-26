# pycon-finance-automation

파이콘 한국 파준위(파이콘 준비위원회)의 지출 결재 프로세스를 자동화하는 서비스입니다.  
두레이(Dooray) 업무 상태를 폴링하여 결재가 완료되면 구글 시트 지출 장부에 자동으로 기록합니다.

## 흐름

```
두레이 파준위 프로젝트에 지출 업무 등록
          ↓
[NEW] → [REVIEWING] → [PAYMENT_WAITING] → [COPIED_TO_PYCON]
                                                   ↓
                              [SHEET_UPDATED] ← [COMPLETED] ← [PAYMENT_IN_PROGRESS]
```

| 상태 | 설명 |
|------|------|
| NEW | 파준위 두레이에 업무가 등록됨 |
| REVIEWING | 검토자가 업무를 검토 중 (두레이 워크플로: 검토 중) |
| PAYMENT_WAITING | 검토 완료, 결제 대기 중 (두레이 워크플로: 결제 대기 중) |
| COPIED_TO_PYCON | 파이콘 두레이 프로젝트에 결제 업무 복사됨 |
| PAYMENT_IN_PROGRESS | 파이콘 측에서 결제 진행 중 (두레이 워크플로: 결제 중) |
| COMPLETED | 결제 완료 (파이콘 두레이 워크플로: 결제 완료) |
| SHEET_UPDATED | 구글 시트 지출 장부에 기록 완료 |
| REJECTED | 반려 처리 (터미널 상태) |

## 환경 변수

| 변수 | 설명 | 필수 |
|------|------|------|
| `DOORAY_API_TOKEN` | 두레이 API 토큰 | ✅ |
| `PAJUNWI_PROJECT_ID` | 파준위 두레이 프로젝트 ID | ✅ |
| `PYCON_PROJECT_ID` | 파이콘 두레이 프로젝트 ID | ✅ |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | 구글 서비스 계정 JSON (Base64 인코딩) | ✅ |
| `SPREADSHEET_ID` | 구글 시트 ID (URL의 `/d/{ID}/` 부분) | ✅ |
| `SLACK_WEBHOOK_URL` | 슬랙 Incoming Webhook URL | ✅ |
| `POLL_INTERVAL_SECONDS` | 폴링 간격 (초, 기본값: 300) | ❌ |
| `DATABASE_PATH` | SQLite DB 경로 (기본값: `/data/state.db`) | ❌ |

## 로컬 실행

### 요구 사항

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

### 설정

```bash
# 의존성 설치
uv sync

# 환경 변수 설정
export DOORAY_API_TOKEN=your_token
export PAJUNWI_PROJECT_ID=your_pajunwi_project_id
export PYCON_PROJECT_ID=your_pycon_project_id
export GOOGLE_SERVICE_ACCOUNT_JSON=$(base64 -i service_account.json)
export SPREADSHEET_ID=your_spreadsheet_id
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# 실행
uv run python -m src.main
```

### 테스트

```bash
uv run pytest
uv run pytest --cov=src  # 커버리지 포함
```

## Railway 배포

### 최초 배포

1. [Railway](https://railway.com)에서 프로젝트 생성
2. GitHub 레포지토리 연결
3. **Variables** 탭에서 위 환경 변수 모두 입력
4. **Volumes** 탭에서 볼륨 추가: 마운트 경로 `/data` (SQLite 데이터 영속화)
5. Railway가 `Dockerfile`을 자동으로 감지하여 빌드 및 배포

### 업데이트 배포

`master` 브랜치에 push하면 Railway가 자동으로 재배포합니다.

## 구글 시트 설정

1. [Google Cloud Console](https://console.cloud.google.com)에서 서비스 계정 생성
2. **Google Sheets API** 활성화
3. 서비스 계정 키(JSON) 다운로드 후 Base64 인코딩:
   ```bash
   base64 -i service_account.json | tr -d '\n'
   ```
4. 파준위 장부 구글 시트를 서비스 계정 이메일에 **편집자** 권한으로 공유
5. 시트에 `지출` 워크시트가 있어야 합니다 (열 순서: 대분류, 소분류, 내용, 날짜, 담당자, 금액, 비고)

## 슬랙 알림

- **업무 복사**: 파준위 업무가 파이콘 프로젝트로 복사될 때
- **업무 반려**: 검토 중 또는 결제 중 반려될 때
- **핸들러 오류**: 상태 처리 중 예외 발생 시
- **일일 하트비트**: 매일 09:00 활성 업무 수 및 전환 횟수 요약
- **시트 기록 실패**: 구글 시트 기록 실패 시

슬랙 워크스페이스에서 Incoming Webhook을 생성하여 `SLACK_WEBHOOK_URL` 환경 변수에 설정합니다.
