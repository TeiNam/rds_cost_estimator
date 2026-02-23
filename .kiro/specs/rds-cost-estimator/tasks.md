# 구현 계획: RDS Cost Estimator

## 개요

설계 문서의 컴포넌트 다이어그램을 기반으로, 의존성이 낮은 모듈부터 순차적으로 구현합니다.
예외 클래스 → 데이터 모델 → AWS 클라이언트 → 비즈니스 로직 → 출력 → CLI → 오케스트레이션 순서로 진행합니다.

## 태스크

- [x] 1. 프로젝트 초기 설정
  - `pyproject.toml` 생성 (의존성: boto3, pydantic, rich, anyio, pypdf, python-docx)
  - `src/rds_cost_estimator/` 디렉토리 구조 및 `__init__.py` 생성
  - `tests/conftest.py` 생성 (moto, boto3 세션 공통 픽스처)
  - _요구사항: 7.5_

- [x] 2. 예외 클래스 구현 (`exceptions.py`)
  - [x] 2.1 커스텀 예외 클래스 계층 구현
    - `RDSCostEstimatorError` 기본 예외 클래스 작성
    - `PricingAPIError`, `InvalidInputError`, `PricingDataNotFoundError` 구현
    - `DocumentParseError`, `UnsupportedFileFormatError` 구현
    - _요구사항: 6.4_

- [x] 3. Pydantic v2 데이터 모델 구현 (`models.py`)
  - [x] 3.1 열거형 및 핵심 모델 구현
    - `InstanceFamily`, `MigrationStrategy`, `PricingType` Enum 작성
    - `InstanceSpec`, `CostRecord` 모델 구현 (`annual_cost` 자동 계산 validator 포함)
    - `CostRow`, `CLIArgs`, `ParsedDocumentInfo` 모델 구현
    - _요구사항: 7.1, 7.2_
  - [ ]* 3.2 비용 계산 공식 속성 테스트 작성 (`test_cost_table.py`)
    - **속성 4: 비용 계산 공식 정확성**
    - **검증 요구사항: 2.2, 2.3, 2.4**

- [x] 4. AWS Bedrock 클라이언트 구현 (`bedrock_client.py`)
  - [x] 4.1 `BedrockClient` 클래스 구현
    - `__init__`: boto3 Session 및 model_id 초기화
    - `_build_prompt`: 구조화된 JSON 출력 요청 프롬프트 생성
    - `_parse_response`: Bedrock 응답에서 JSON 추출 후 `ParsedDocumentInfo` 변환
    - `invoke`: InvokeModel 호출, 실패 시 `DocumentParseError` 발생
    - _요구사항: 8.1, 8.5, 8.9_
  - [ ]* 4.2 Bedrock 호출 실패 속성 테스트 작성 (`test_bedrock_client.py`)
    - **속성 16: Bedrock 호출 실패 시 예외 발생**
    - **검증 요구사항: 8.5**
  - [ ]* 4.3 Bedrock 응답 JSON 라운드트립 속성 테스트 작성 (`test_bedrock_client.py`)
    - **속성 18: Bedrock 응답 JSON 라운드트립**
    - **검증 요구사항: 8.9**

- [x] 5. 문서 파서 구현 (`document_parser.py`)
  - [x] 5.1 `DocumentParser` 클래스 구현
    - `_detect_format`: 파일 확장자 감지, 비지원 형식 시 `UnsupportedFileFormatError` 발생
    - `_extract_text`: PDF(pypdf), DOCX(python-docx), TXT(내장 open) 텍스트 추출
    - `parse`: 텍스트 추출 후 `BedrockClient.invoke` 호출, `ParsedDocumentInfo` 반환
    - _요구사항: 8.1, 8.2, 8.3, 8.6_
  - [ ]* 5.2 비지원 파일 형식 속성 테스트 작성 (`test_document_parser.py`)
    - **속성 15: 비지원 파일 형식 예외 발생**
    - **검증 요구사항: 8.3**
  - [ ]* 5.3 문서 파싱 성공 속성 테스트 작성 (`test_document_parser.py`)
    - **속성 14: 문서 파싱 성공 시 모델 반환**
    - **검증 요구사항: 8.1, 8.6**
  - [ ]* 5.4 파일 형식별 텍스트 추출 단위 테스트 작성 (`test_document_parser.py`)
    - PDF/DOCX/TXT 각 형식별 정상 동작 확인
    - _요구사항: 8.2_

- [x] 6. AWS Pricing API 클라이언트 구현 (`pricing_client.py`)
  - [x] 6.1 `PricingClient` 클래스 구현
    - `__init__`: boto3 Session, 인메모리 캐시 딕셔너리 초기화
    - `_cache_key`: `InstanceSpec` + `PricingType` 조합 캐시 키 생성
    - `_build_filters`: GetProducts 요청용 필터 목록 생성
    - `_parse_response`: API 응답을 `CostRecord`로 파싱, 데이터 없으면 `PricingDataNotFoundError`
    - `fetch_on_demand`, `fetch_reserved`: 캐시 확인 후 API 호출, 실패 시 `PricingAPIError`
    - `fetch_all`: 온디맨드 + 1년 RI + 3년 RI 비동기 병렬 조회
    - _요구사항: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.4_
  - [ ]* 6.2 API 조회 완전성 속성 테스트 작성 (`test_pricing_client.py`)
    - **속성 1: API 조회 완전성**
    - **검증 요구사항: 1.1, 1.2, 1.4, 1.5**
  - [ ]* 6.3 API 실패 시 예외 발생 속성 테스트 작성 (`test_pricing_client.py`)
    - **속성 2: API 실패 시 예외 발생**
    - **검증 요구사항: 1.3**
  - [ ]* 6.4 캐싱 멱등성 속성 테스트 작성 (`test_pricing_client.py`)
    - **속성 3: 캐싱 멱등성 (동일 조회 시 API 1회만 호출)**
    - **검증 요구사항: 1.6**

- [x] 7. 체크포인트 - 모든 테스트 통과 확인
  - 모든 테스트가 통과하는지 확인하고, 문제가 있으면 사용자에게 질문합니다.

- [x] 8. 비용 집계 및 절감률 계산 구현 (`cost_table.py`)
  - [x] 8.1 `CostTable` 클래스 구현
    - `__init__`: `CostRecord` 목록과 `on_prem_annual_cost` 초기화
    - `compute_savings`: 각 레코드를 `CostRow`로 변환, 절감률 계산
    - `to_dict`: JSON 직렬화용 딕셔너리 목록 반환
    - _요구사항: 2.2, 2.3, 2.4, 3.3, 3.4_
  - [ ]* 8.2 절감 계산 정확성 속성 테스트 작성 (`test_cost_table.py`)
    - **속성 8: 절감 계산 정확성**
    - **검증 요구사항: 3.3, 3.4**

- [x] 9. 콘솔 표 및 JSON 출력 구현 (`renderer.py`)
  - [x] 9.1 `ReportRenderer` 클래스 구현
    - `render_console`: `rich.table`로 인스턴스 유형, 전략, 비용, 절감률 표 출력
    - USD 통화 형식(`$X,XXX.XX`) 및 절감률 소수점 첫째 자리 포맷 적용
    - 데이터 없을 때 "조회된 비용 데이터가 없습니다." 출력
    - `render_json`: `CostTable.to_dict()` 결과를 JSON 파일로 저장
    - _요구사항: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [ ]* 9.2 렌더링 출력 완전성 속성 테스트 작성 (`test_renderer.py`)
    - **속성 10: 렌더링 출력 완전성**
    - **검증 요구사항: 4.1, 4.2, 4.3**
  - [ ]* 9.3 JSON 직렬화 라운드트립 속성 테스트 작성 (`test_renderer.py`)
    - **속성 11: JSON 직렬화 라운드트립**
    - **검증 요구사항: 4.5**

- [x] 10. CLI 인터페이스 구현 (`cli.py`)
  - [x] 10.1 argparse 기반 CLI 인수 파싱 구현
    - `--region`, `--current-instance`, `--recommended-instance`, `--on-prem-cost` 인수 정의
    - `--engine`, `--profile`, `--verbose`, `--output-format`, `--output-file` 인수 정의
    - `--input-file`, `--bedrock-model` 인수 정의
    - 필수 인수 누락 시 사용법 출력 후 종료 코드 1 처리
    - `CLIArgs` Pydantic 모델로 파싱 결과 반환
    - _요구사항: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  - [ ]* 10.2 필수 인수 누락 시 종료 코드 속성 테스트 작성 (`test_cli.py`)
    - **속성 12: 필수 인수 누락 시 종료 코드 1**
    - **검증 요구사항: 5.6**
  - [ ]* 10.3 CLI 단위 테스트 작성 (`test_cli.py`)
    - `--region` 기본값 `ap-northeast-2` 확인
    - `--bedrock-model` 기본값 확인
    - `--verbose` 플래그 동작 확인
    - _요구사항: 5.1, 6.2, 8.4_

- [x] 11. 핵심 오케스트레이션 로직 구현 (`estimator.py`)
  - [x] 11.1 `Estimator` 클래스 구현
    - `__init__`: `CLIArgs`로 초기화, boto3 Session 생성 (`--profile` 적용)
    - `_build_specs`: current/recommended 인스턴스 × Replatform/Refactoring 전략 조합으로 `InstanceSpec` 목록 생성
    - `run`: `asyncio.gather`로 병렬 API 호출, `CostTable` 구성 후 반환
    - `on_prem_cost <= 0` 검증, `InvalidInputError` 발생
    - `--input-file` 지정 시 `DocumentParser` 호출, 누락 필드 CLI 인수로 보완
    - _요구사항: 2.1, 2.6, 3.1, 3.2, 3.5, 5.7, 7.4, 8.7, 8.8_
  - [ ]* 11.2 유효하지 않은 온프레미스 비용 속성 테스트 작성 (`test_estimator.py`)
    - **속성 9: 유효하지 않은 온프레미스 비용 입력 처리**
    - **검증 요구사항: 3.5**
  - [ ]* 11.3 두 인스턴스 행 존재 속성 테스트 작성 (`test_estimator.py`)
    - **속성 6: 두 인스턴스 행 존재**
    - **검증 요구사항: 2.6**
  - [ ]* 11.4 두 이관 전략 행 존재 속성 테스트 작성 (`test_estimator.py`)
    - **속성 7: 두 이관 전략 행 존재**
    - **검증 요구사항: 3.1, 3.2**
  - [ ]* 11.5 가격 데이터 없음(N/A) 처리 속성 테스트 작성 (`test_estimator.py`)
    - **속성 5: 가격 데이터 없음(N/A) 처리 시 전체 조회 계속 진행**
    - **검증 요구사항: 2.5**
  - [ ]* 11.6 누락 필드 CLI 인수 보완 속성 테스트 작성 (`test_estimator.py`)
    - **속성 17: 누락 필드 CLI 인수 보완**
    - **검증 요구사항: 8.7**
  - [ ]* 11.7 예외 발생 시 종료 코드 속성 테스트 작성 (`test_estimator.py`)
    - **속성 13: 예외 발생 시 종료 코드 1**
    - **검증 요구사항: 6.3**

- [x] 12. 진입점 구현 (`__main__.py`)
  - `main()` 함수 구현: CLI 파싱 → Estimator 실행 → 렌더링
  - `logging` 모듈 설정 (INFO 기본, `--verbose` 시 DEBUG)
  - 처리되지 않은 예외 캐치 → ERROR 로그 (스택 트레이스) + 종료 코드 1
  - `python -m rds_cost_estimator` 진입점 연결
  - _요구사항: 6.1, 6.2, 6.3_

- [x] 13. 최종 체크포인트 - 모든 테스트 통과 확인
  - 모든 테스트가 통과하는지 확인하고, 문제가 있으면 사용자에게 질문합니다.

## 참고 사항

- `*` 표시된 태스크는 선택 사항으로, MVP 구현 시 건너뛸 수 있습니다.
- 각 태스크는 이전 태스크를 기반으로 구축되므로 순서대로 진행합니다.
- 속성 기반 테스트는 Hypothesis 라이브러리를 사용하며 최소 100회 반복 실행합니다.
- AWS API 모킹은 moto 라이브러리를 사용합니다.
- 모든 함수와 메서드에 Python 타입 힌트를 적용합니다 (요구사항 7.1).
