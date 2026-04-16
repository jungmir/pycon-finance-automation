# 파준위 회계 자동화 시스템 설계

**날짜:** 2026-04-17  
**대상:** 파이콘 한국 준비위원회(파준위) 회계팀  
**범위:** 파준위 회계팀이 수동으로 처리하던 Dooray 업무 관리 및 구글 시트 갱신 자동화

---

## 1. 배경 및 목적

파준위 회계 프로세스는 파준위-재무지원-포털(이하 파준위 포털)과 파이콘-재무지원-포털(이하 파이콘 포털) 두 개의 Dooray 프로젝트를 걸쳐 11단계로 진행된다. 이 중 파준위 회계팀이 담당하는 단계(2, 3, 5, 8, 10, 11)는 반복적이고 규칙적인 작업으로 자동화 적합도가 높다.

**자동화 대상 단계:**

| 단계 | 작업 내용 |
|------|-----------|
| Step 2 | 파준위 포털 신규 업무 감지 → 검토중 상태로 변경 |
| Step 3 | 검토 완료 업무 → 파이콘 포털로 복사 생성 |
| Step 5 | 파이콘 포털에서 파사모가 결제대기로 변경한 것을 감지 → 파준위 포털 상태를 결제대기로 동기화 |
| Step 8 | 파준위 포털 증빙 코멘트 → 파이콘 포털로 복사 |
| Step 10 | 파이콘 포털 파사모 완료 확인 → 파준위 포털 최종 상태 갱신 |
| Step 11 | Step 10 완료 직후 구글 시트 회계 장부 갱신 |

---

## 2. 전체 프로세스 흐름

```
[파준위 포털]                [자동화 엔진]              [파이콘 포털]

NEW (수동 등록)
    │
    ▼ 🤖 Step 2: 자동 감지
REVIEWING ─────────────────────────────────────────────────
    │                                                       │
    ▼ 🤖 Step 3: 자동 복사                                 ▼
COPIED_TO_PYCON ─────────────────────────────── 업무 생성됨
                                                     │
                                           파사모 검토 (수동, Step 4)
                                                     │
    ◀── 🤖 Step 5: 파사모 결제대기 감지 ── 결제대기 / 반려
    │
PAYMENT_PENDING
    │
파준위 결제 + 증빙 코멘트 (수동, Step 6, 7)
    │
    ▼ 🤖 Step 8: 자동 복사
EVIDENCE_COPIED ─────────────────────────────── 증빙 복사됨
                                                     │
                                           파사모 최종 승인 (수동, Step 9)
                                                     │
    ◀── 🤖 Step 10: 최종 상태 감지 ────── COMPLETED
    │
COMPLETED
    │
    ▼ 🤖 Step 11: 구글 시트 자동 갱신
SHEET_UPDATED ✅
```

**반려 케이스:** 파사모가 반려 시 자동화를 중단하고 Slack으로 수동 개입 요청.

---

## 3. 아키텍처

### 3.1 시스템 구성

```
┌─────────────────────────────────────────────────────────────┐
│                    Railway Container                        │
│                                                             │
│  ┌────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │   Poller   │───▶│ State Engine │───▶│    Handlers    │  │
│  │ (5분 주기) │    │ (전이 판단)  │    │  (단계별 실행) │  │
│  └────────────┘    └──────────────┘    └────────────────┘  │
│         │                                       │           │
│  ┌──────┴──────┐                    ┌───────────┴────────┐  │
│  │ State Store │                    │   Slack Notifier   │  │
│  │  (SQLite)   │                    │  (성공/실패 알림)  │  │
│  └─────────────┘                    └────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                                       │
         ▼                                       ▼
  ┌──────────────┐                    ┌──────────────────────┐
  │  Dooray API  │                    │  Google Sheets API   │
  │ 파준위 포털  │                    │    (회계 장부)       │
  │ 파이콘 포털  │                    └──────────────────────┘
  └──────────────┘
```

### 3.2 기술 스택

| 항목 | 선택 |
|------|------|
| 언어 | Python 3.12 |
| 폴링 스케줄러 | `schedule` 라이브러리 (5분 간격) |
| Dooray 연동 | `requests` (REST API) |
| Google Sheets 연동 | `gspread` + 서비스 계정 |
| 상태 저장 | SQLite (Railway Volume 마운트) |
| 알림 | Slack Incoming Webhook |
| 실행 환경 | Railway PaaS (Docker 컨테이너) |

---

## 4. 프로젝트 구조

```
pycon-finance-automation/
├── src/
│   ├── main.py                  # 진입점 — 폴링 루프
│   ├── state_engine.py          # 상태 머신 — 전이 판단
│   ├── handlers/
│   │   ├── step2_review.py      # 신규 → 검토중
│   │   ├── step3_copy.py        # 파이콘 포털 업무 복사
│   │   ├── step5_payment.py     # 결제대기 상태 동기화
│   │   ├── step8_evidence.py    # 증빙 코멘트 복사
│   │   ├── step10_sync.py       # 최종 상태 갱신
│   │   └── step11_sheets.py     # 구글 시트 갱신
│   ├── clients/
│   │   ├── dooray.py            # Dooray REST API 래퍼
│   │   └── sheets.py            # Google Sheets API 래퍼
│   ├── store.py                 # SQLite 상태 저장소
│   └── notifier.py              # Slack 알림
├── tests/
│   ├── test_state_engine.py
│   └── test_handlers.py
├── .env.example
├── Dockerfile
├── railway.toml
└── requirements.txt
```

---

## 5. 데이터 모델

### tasks 테이블
```sql
CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY,
    pajunwi_task_id TEXT UNIQUE,   -- 파준위 포털 업무 ID
    pycon_task_id   TEXT,          -- 파이콘 포털 업무 ID (Step 3 이후)
    state           TEXT,          -- 현재 상태
    last_comment_id TEXT,          -- 마지막으로 복사한 코멘트 ID (중복 방지)
    amount          INTEGER,       -- 금액 (시트 갱신용)
    created_at      DATETIME,
    updated_at      DATETIME
);
```

### state_history 테이블
```sql
CREATE TABLE state_history (
    id              INTEGER PRIMARY KEY,
    pajunwi_task_id TEXT,
    from_state      TEXT,
    to_state        TEXT,
    handler         TEXT,          -- 실행된 핸들러 이름
    success         BOOLEAN,
    error_msg       TEXT,
    executed_at     DATETIME
);
```

### 상태값 정의
| 상태 | 의미 |
|------|------|
| `NEW` | 파준위 포털 신규 업무 |
| `REVIEWING` | 검토중 (Step 2 완료) |
| `COPIED_TO_PYCON` | 파이콘 포털 복사 완료 (Step 3 완료) |
| `PAYMENT_PENDING` | 결제 대기 (파사모 승인 확인 후 파준위 포털 동기화 완료, Step 5 완료) |
| `EVIDENCE_COPIED` | 증빙 파이콘 포털 복사 완료 (Step 8 완료) |
| `COMPLETED` | 파준위 포털 최종 상태 갱신 완료 (Step 10 완료) |
| `SHEET_UPDATED` | 구글 시트 갱신 완료 (Step 11 완료) |
| `REJECTED` | 파사모 반려 — 수동 처리 필요 |

---

## 6. 오류 처리

| 상황 | 처리 방식 |
|------|-----------|
| Dooray API 일시 오류 | 지수 백오프로 3회 재시도 → 실패 시 건너뜀, 다음 폴링 재시도 |
| 핸들러 실행 실패 | state_history에 오류 기록, Slack 즉시 알림, 상태 변경 안 함 |
| 중복 처리 위험 | SQLite tasks 테이블로 처리 이력 추적, 멱등성 보장 |
| 파사모 반려 | 상태를 REJECTED로 변경 후 Slack 알림, 자동화 중단 |
| Google Sheets 실패 | Slack 알림으로 수동 갱신 요청 (Dooray 상태는 이미 갱신됨) |

### Slack 알림 형식
```
✅ [자동화] 업무 복사 완료
   파준위 #1234 → 파이콘 포털로 복사됨
   제목: 2026 파이콘 장소 답사 활동비

⚠️ [자동화] 파사모 반려 감지
   파이콘 포털 업무 #5678 반려됨 — 수동 확인 필요

❌ [자동화] 핸들러 오류
   step3_copy 실패 (업무 #1234) — 다음 폴링에서 재시도 예정
```

---

## 7. 환경변수

```env
DOORAY_API_TOKEN=...            # Dooray API 인증 토큰
DOORAY_DOMAIN=pycon.dooray.com  # Dooray 도메인

PAJUNWI_PROJECT_ID=...          # 파준위-재무지원-포털 프로젝트 ID
PYCON_PROJECT_ID=...            # 파이콘-재무지원-포털 프로젝트 ID

GOOGLE_SERVICE_ACCOUNT_JSON=... # Google 서비스 계정 JSON (base64 인코딩)
SPREADSHEET_ID=...              # 회계 장부 스프레드시트 ID

SLACK_WEBHOOK_URL=...           # Slack Incoming Webhook URL

POLL_INTERVAL_SECONDS=300       # 폴링 간격 (기본 5분)
DATABASE_PATH=/data/state.db    # SQLite 파일 경로 (Railway Volume)
```

---

## 8. 배포 (Railway)

```toml
# railway.toml
[build]
  builder = "dockerfile"

[deploy]
  startCommand = "python src/main.py"
  restartPolicyType = "always"
```

- Railway Volume을 `/data`에 마운트하여 SQLite 영속성 확보
- 크래시 시 자동 재시작 (`restartPolicyType = "always"`)
- Railway Secrets에 환경변수 등록

---

## 9. 미결 사항

- Dooray API 인증 방식 및 엔드포인트 확인 필요 (REST API 문서 검토)
- 파이콘 포털 업무 복사 시 어떤 필드를 포함할지 파사모 회계팀과 협의 필요
- 구글 시트 회계 장부 컬럼 구조 확인 필요 (어떤 필드를 어느 열에 쓸지)
- Dooray 업무 상태값 실제 문자열 확인 필요 (API 응답 기준)
