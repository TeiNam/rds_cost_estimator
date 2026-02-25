# RDS Cost Estimator

![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![Pydantic](https://img.shields.io/badge/Pydantic-2.0-E92063.svg)
![DuckDB](https://img.shields.io/badge/DuckDB-1.0-FFF000.svg)
![AWS](https://img.shields.io/badge/AWS-Cloud-FF9900.svg)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://qr.kakaopay.com/Ej74xpc815dc06149)

## 개요

온프레미스 Oracle DB의 AWR/Statspack 리포트를 입력하면, AWS RDS 이관 시 예상 비용을 분석하여 Markdown 리포트를 생성하는 CLI 도구입니다.

**주요 기능:**
- AWS Bedrock (Claude) 기반 문서 자동 파싱 (PDF/DOCX/TXT/MD)
- AWS Pricing API + RDS RI Offerings API를 통한 실시간 가격 조회
- DuckDB 인메모리 DB를 활용한 데이터 분석 및 리포트 생성
- 동적 인스턴스 패밀리 비교 (r6i/r7i, m6i/m7i 등 동일 카테고리 자동 확장)
- Aurora 엔진 인식 및 타겟 엔진 자동 추출 (aurora-postgresql, aurora-mysql)
- On-Demand / 1년 RI All Upfront / 3년 RI All Upfront 요금 옵션
- Single-AZ / Multi-AZ 배포 시나리오
- 스토리지(gp3/Aurora 클러스터) + 네트워크(Cross-AZ) 비용 포함 3년 TCO 분석
- Oracle 엔진 전용 Replatform vs Refactoring(Aurora PostgreSQL) 비용 비교

## 아키텍처

```
입력 파일 (PDF/DOCX/TXT/MD)
    │
    ▼
DocumentParser ─── 텍스트 추출
    │
    ▼
BedrockClient ─── Claude 모델로 구조화된 데이터 추출
    │
    ▼
DuckDB Store ─── 파싱 데이터 저장
    │
    ▼
Estimator ─── Pricing API / RDS RI Offerings API 병렬 조회
    │              └── RI 폴백: GetProducts 실패 시
    │                  DescribeReservedDBInstancesOfferings로 재조회
    ▼
DuckDB Store ─── 가격 데이터 저장 + 집계 쿼리
    │
    ▼
TemplateBuilder ─── 템플릿 데이터 구성 (스토리지/네트워크/TCO 계산)
    │
    ▼
ReportRenderer ─── 템플릿 기반 Markdown 리포트 생성
```

## 설치

```bash
# 저장소 클론
git clone <repository-url>

# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # macOS/Linux

# 의존성 설치
pip install -e .

# 개발 의존성 포함 설치
pip install -e ".[dev]"
```

## AWS 자격증명 설정

### 환경변수 (.env)

프로젝트 루트에 `.env` 파일을 생성합니다:

```bash
cp .env.example .env
```

```dotenv
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=ap-northeast-2
```

### AWS CLI 프로파일

```bash
# 프로파일 지정 실행
rds-cost-estimator report.md --profile my-profile
```

## 필요한 IAM 권한

이 도구는 3개의 AWS 서비스 API를 호출합니다. 아래 IAM 정책을 사용자 또는 역할에 연결해야 합니다.

### 최소 권한 IAM 정책

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockInvokeModel",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6"
            ]
        },
        {
            "Sid": "PricingGetProducts",
            "Effect": "Allow",
            "Action": [
                "pricing:GetProducts"
            ],
            "Resource": "*"
        },
        {
            "Sid": "RDSDescribeReservedOfferings",
            "Effect": "Allow",
            "Action": [
                "rds:DescribeReservedDBInstancesOfferings"
            ],
            "Resource": "*"
        }
    ]
}
```

### 권한별 설명

| AWS 서비스 | API 액션 | 용도 | 엔드포인트 리전 |
|-----------|---------|------|---------------|
| Bedrock Runtime | `bedrock:InvokeModel` | 입력 문서에서 서버 사양/AWR 메트릭 추출 | 기본 리전 |
| AWS Pricing | `pricing:GetProducts` | RDS 인스턴스 On-Demand/RI 가격 조회 | us-east-1 (고정) |
| Amazon RDS | `rds:DescribeReservedDBInstancesOfferings` | RI 가격 폴백 조회 (Pricing API에서 RI 데이터를 찾지 못할 때) | 대상 리전 |

> Pricing API는 `us-east-1` 엔드포인트만 지원하므로 해당 리전에 대한 접근이 필요합니다.
> RDS DescribeReservedDBInstancesOfferings는 `--region` 옵션으로 지정한 리전에서 호출됩니다.

### Bedrock 모델 접근 활성화

Bedrock Claude 모델을 사용하려면 AWS 콘솔에서 모델 접근을 먼저 활성화해야 합니다:

1. AWS 콘솔 → Amazon Bedrock → Model access
2. `Anthropic` → `Claude Sonnet 4.6` 모델 접근 요청
3. 승인 완료 후 사용 가능

## 사용법

### 기본 실행

```bash
# AWR 리포트 파일을 입력하여 비용 분석 리포트 생성
rds-cost-estimator report.md

# 또는 python -m 으로 실행
python -m rds_cost_estimator report.md
```

### CLI 옵션

```bash
rds-cost-estimator <input_file> [옵션]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `input_file` | (필수) | 입력 리포트 파일 경로 (PDF/DOCX/TXT/MD) |
| `--region` | `ap-northeast-2` | AWS 리전 코드 |
| `--engine` | `oracle-ee` | RDS 엔진 유형 |
| `--on-prem-cost` | (문서에서 추출) | 온프레미스 연간 유지비용 (USD) |
| `--current-instance` | (문서에서 추출) | 현재 RDS 인스턴스 유형 |
| `--recommended-instance-by-size` | (문서에서 추출) | 사이즈 기준 권장 인스턴스 |
| `--recommended-instance-by-sga` | (문서에서 추출) | SGA 기준 권장 인스턴스 |
| `-o, --output-dir` | `.` | 결과 파일 출력 디렉토리 |
| `--json` | `false` | JSON 파일도 함께 생성 |
| `--profile` | (없음) | AWS CLI 프로파일 이름 |
| `--bedrock-model` | `anthropic.claude-sonnet-4-6` | Bedrock 모델 ID |
| `--verbose` | `false` | DEBUG 로그 활성화 |

### 실행 예시

```bash
# 서울 리전, Oracle EE 기준 (기본값)
rds-cost-estimator dbcsi_report.md

# 도쿄 리전, JSON 출력 포함
rds-cost-estimator dbcsi_report.md --region ap-northeast-1 --json

# 출력 디렉토리 지정 + AWS 프로파일
rds-cost-estimator dbcsi_report.md -o ./output --profile prod-readonly

# 상세 로그 활성화
rds-cost-estimator dbcsi_report.md --verbose
```

## 출력 리포트 구성

생성되는 Markdown 리포트는 다음 섹션으로 구성됩니다:

1. **리포트 개요** - DB 이름, Oracle 버전, 리전, 생성일
2. **현재 서버 사양** - CPU, 메모리, DB 크기, AWR 메트릭, SGA 분석, 스토리지 증가 추이
3. **RDS 인스턴스 권장 사양** - 서버 매칭(1:1) + SGA 기반 최적화 (r6i/r7i)
4. **스토리지 비용** - gp3 기준 연도별 비용 예측
5. **네트워크 전송 비용** - AWR 기반 트래픽 추정, 시나리오별 비용
6. **통합 비용 (서버 매칭)** - 인스턴스 + 스토리지 + 네트워크 (Single-AZ / Multi-AZ)
7. **통합 비용 (SGA 최적화)** - 비용 최적화 인스턴스 기준
8. **전체 비용 비교 요약** - 연간 비교 + 3년 TCO
9. **권장사항** - 비용 최적화 전략, 단계별 접근, Multi-AZ 검토

## 프로젝트 구조

```
src/rds_cost_estimator/
├── __init__.py
├── __main__.py          # CLI 진입점
├── cli.py               # argparse 인수 파싱
├── models.py            # Pydantic v2 데이터 모델
├── document_parser.py   # PDF/DOCX/TXT/MD 텍스트 추출
├── bedrock_client.py    # AWS Bedrock Claude 호출
├── db_store.py          # DuckDB 인메모리 데이터 저장소
├── pricing_client.py    # AWS Pricing API + RDS RI Offerings API
├── estimator.py         # 핵심 오케스트레이션 로직
├── instance_utils.py    # 인스턴스 사양/스토리지 비용 유틸리티
├── template_builder.py  # 템플릿 v2 데이터 구성 (TCO/네트워크/비교)
├── cost_table.py        # 비용 집계 및 절감률 계산
├── renderer.py          # Markdown/JSON 리포트 생성
└── exceptions.py        # 커스텀 예외 클래스
```

## 개발

```bash
# 테스트 실행
pytest

# 타입 체크
mypy src/

# 린트
ruff check src/
```

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.12+ |
| 데이터 모델 | Pydantic v2 |
| 분석 DB | DuckDB (인메모리) |
| AWS SDK | boto3 |
| 문서 파싱 | pypdf, python-docx |
| AI 모델 | AWS Bedrock (Claude Sonnet 4.6) |
| 콘솔 출력 | Rich |
| 테스트 | pytest, pytest-asyncio, moto |
