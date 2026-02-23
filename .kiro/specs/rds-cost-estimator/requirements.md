# 요구사항 문서

## 소개

AWS RDS 비용 예측기(RDS Cost Estimator)는 온프레미스 서버에서 AWS RDS로 이관 시 예상 비용을 분석하는 Python CLI 도구입니다.
AWS Pricing API를 호출하여 r6i, r7i, r7g 인스턴스 유형별로 1년 온디맨드, 1년 예약 인스턴스(RI), 3년 예약 인스턴스(RI) 가격을 비교하고,
RDS for Oracle(리플랫폼) 및 Aurora PostgreSQL(리팩토링) 이관 전략에 따른 비용 절감 효과를 표 형태로 출력합니다.

## 용어 정의

- **Estimator**: 비용 예측기 전체 시스템
- **PricingClient**: AWS Pricing API와 통신하는 클라이언트 모듈
- **InstanceSpec**: 인스턴스 유형, 리전, 엔진 등 인스턴스 사양을 나타내는 Pydantic 모델
- **CostRecord**: 단일 인스턴스의 온디맨드/RI 가격 정보를 담는 Pydantic 모델
- **CostTable**: 여러 CostRecord를 집계하여 비교표를 생성하는 모듈
- **ReportRenderer**: 비용 비교 결과를 콘솔 표로 출력하는 모듈
- **OnDemand**: 약정 없이 시간 단위로 과금되는 요금제
- **RI (Reserved Instance)**: 1년 또는 3년 약정으로 할인된 요금제
- **Replatform**: 애플리케이션 코드 변경 없이 RDS for Oracle로 이관하는 전략
- **Refactoring**: Aurora PostgreSQL 등 다른 엔진으로 전환하여 비용을 절감하는 전략
- **온프레미스 유지비용**: 사용자가 직접 입력하는 현재 서버 운영 예상 비용
- **DocumentParser**: 문서 파일(PDF/DOCX/TXT)에서 텍스트를 추출하고 Bedrock을 호출하여 인스턴스 사양 정보를 파싱하는 모듈
- **BedrockClient**: AWS Bedrock Runtime API를 호출하여 Claude 모델로 문서 분석을 수행하는 클라이언트 모듈
- **ParsedDocumentInfo**: Bedrock이 문서에서 추출한 인스턴스 사양 정보를 담는 Pydantic 모델

---

## 요구사항

### 요구사항 1: AWS Pricing API 연동

**사용자 스토리:** 개발자로서, AWS Pricing API를 통해 최신 RDS 인스턴스 가격을 조회하고 싶습니다. 그래야 수동으로 가격을 조사하지 않아도 됩니다.

#### 인수 기준

1. THE PricingClient SHALL AWS Pricing API(`us-east-1` 엔드포인트)를 통해 RDS 인스턴스 온디맨드 가격을 조회한다.
2. WHEN API 호출이 성공하면, THE PricingClient SHALL 응답 데이터를 CostRecord Pydantic 모델로 파싱하여 반환한다.
3. IF AWS Pricing API 호출이 실패하면, THEN THE PricingClient SHALL 오류를 로깅하고 `PricingAPIError` 예외를 발생시킨다.
4. THE PricingClient SHALL 1년 부분 선결제(Partial Upfront) RI 가격을 조회한다.
5. THE PricingClient SHALL 3년 부분 선결제(Partial Upfront) RI 가격을 조회한다.
6. WHEN 동일한 인스턴스 사양에 대해 반복 조회가 발생하면, THE PricingClient SHALL 캐시된 결과를 반환하여 불필요한 API 호출을 방지한다.

---

### 요구사항 2: 인스턴스 유형별 비용 조회

**사용자 스토리:** 클라우드 아키텍트로서, r6i, r7i, r7g 인스턴스 유형별 비용을 한눈에 비교하고 싶습니다. 그래야 최적의 인스턴스를 선택할 수 있습니다.

#### 인수 기준

1. THE Estimator SHALL r6i, r7i, r7g 인스턴스 패밀리에 대한 비용을 조회한다.
2. WHEN 인스턴스 사양(InstanceSpec)이 주어지면, THE Estimator SHALL 해당 인스턴스의 1년 온디맨드 연간 비용을 계산한다.
3. THE Estimator SHALL 1년 RI(부분 선결제) 총비용(선결제 + 월정액 × 12)을 계산한다.
4. THE Estimator SHALL 3년 RI(부분 선결제) 총비용(선결제 + 월정액 × 36)을 계산한다.
5. IF 특정 인스턴스 유형에 대한 가격 데이터가 존재하지 않으면, THEN THE Estimator SHALL 해당 항목을 "N/A"로 표시하고 나머지 조회를 계속 진행한다.
6. THE Estimator SHALL 현재 인스턴스(current instance)와 권장 인스턴스(recommended instance)를 각각 별도 행으로 표시한다.

---

### 요구사항 3: 이관 전략별 비용 비교

**사용자 스토리:** 마이그레이션 담당자로서, Replatform과 Refactoring 전략의 비용 차이를 비교하고 싶습니다. 그래야 이관 전략 결정에 근거 자료를 확보할 수 있습니다.

#### 인수 기준

1. THE Estimator SHALL RDS for Oracle 엔진 기준의 Replatform 비용을 계산한다.
2. THE Estimator SHALL Aurora PostgreSQL 엔진 기준의 Refactoring 비용을 계산한다.
3. WHEN Replatform 비용과 Refactoring 비용이 모두 계산되면, THE CostTable SHALL 두 전략의 연간 비용 차이(절감액)를 계산한다.
4. THE CostTable SHALL 온프레미스 유지비용 대비 각 전략의 절감률(%)을 계산한다.
5. IF 온프레미스 유지비용이 0 이하로 입력되면, THEN THE Estimator SHALL 입력 오류를 로깅하고 `InvalidInputError` 예외를 발생시킨다.

---

### 요구사항 4: 비용 비교표 출력

**사용자 스토리:** 의사결정자로서, 비용 비교 결과를 정렬된 표 형태로 확인하고 싶습니다. 그래야 빠르게 내용을 파악할 수 있습니다.

#### 인수 기준

1. THE ReportRenderer SHALL 인스턴스 유형, 이관 전략, 온디맨드 연간 비용, 1년 RI 비용, 3년 RI 비용, 온프레미스 대비 절감률을 포함하는 표를 콘솔에 출력한다.
2. THE ReportRenderer SHALL 비용 값을 USD 통화 형식(예: `$12,345.67`)으로 표시한다.
3. THE ReportRenderer SHALL 절감률을 소수점 첫째 자리까지 퍼센트(%)로 표시한다.
4. WHEN 출력 대상 데이터가 없으면, THE ReportRenderer SHALL "조회된 비용 데이터가 없습니다." 메시지를 출력한다.
5. WHERE `--output-format json` 옵션이 활성화되면, THE ReportRenderer SHALL 동일한 데이터를 JSON 형식으로 파일에 저장한다.

---

### 요구사항 5: CLI 인터페이스

**사용자 스토리:** 개발자로서, 커맨드라인에서 인수를 전달하여 도구를 실행하고 싶습니다. 그래야 스크립트나 자동화 파이프라인에 통합할 수 있습니다.

#### 인수 기준

1. THE Estimator SHALL `--region` 인수를 통해 AWS 리전을 지정할 수 있도록 한다 (기본값: `ap-northeast-2`).
2. THE Estimator SHALL `--current-instance` 인수를 통해 현재 사용 중인 인스턴스 유형을 지정할 수 있도록 한다.
3. THE Estimator SHALL `--recommended-instance` 인수를 통해 권장 인스턴스 유형을 지정할 수 있도록 한다.
4. THE Estimator SHALL `--on-prem-cost` 인수를 통해 온프레미스 연간 유지비용(USD)을 입력받는다.
5. THE Estimator SHALL `--engine` 인수를 통해 RDS 엔진(oracle-ee, aurora-postgresql 등)을 지정할 수 있도록 한다.
6. IF 필수 인수가 누락되면, THEN THE Estimator SHALL 사용법 안내 메시지를 출력하고 종료 코드 1로 종료한다.
7. WHERE `--profile` 옵션이 제공되면, THE Estimator SHALL 해당 AWS CLI 프로파일을 사용하여 인증한다.

---

### 요구사항 6: 로깅 및 예외 처리

**사용자 스토리:** 운영자로서, 도구 실행 중 발생하는 오류와 경고를 추적하고 싶습니다. 그래야 문제 발생 시 원인을 빠르게 파악할 수 있습니다.

#### 인수 기준

1. THE Estimator SHALL Python `logging` 모듈을 사용하여 INFO, WARNING, ERROR 레벨의 로그를 출력한다.
2. WHEN `--verbose` 플래그가 활성화되면, THE Estimator SHALL DEBUG 레벨 로그를 포함하여 출력한다.
3. IF 처리되지 않은 예외가 발생하면, THEN THE Estimator SHALL 스택 트레이스를 ERROR 레벨로 로깅하고 종료 코드 1로 종료한다.
4. THE Estimator SHALL 커스텀 예외 클래스(`PricingAPIError`, `InvalidInputError`)를 정의하여 오류 유형을 명확히 구분한다.

---

### 요구사항 8: Bedrock 기반 문서 파싱

**사용자 스토리:** 마이그레이션 담당자로서, 온프레미스 서버 사양서나 비용 보고서 등의 문서 파일을 제공하면 자동으로 인스턴스 사양 정보를 추출하고 싶습니다. 그래야 수동으로 CLI 인수를 입력하지 않아도 됩니다.

#### 인수 기준

1. WHEN `--input-file` 옵션으로 문서 경로가 지정되면, THE DocumentParser SHALL 해당 파일을 읽어 텍스트를 추출하고 AWS Bedrock(Claude 모델)을 호출하여 인스턴스 사양 정보를 파싱한다.
2. THE DocumentParser SHALL PDF(`.pdf`), Word(`.docx`), 텍스트(`.txt`) 파일 형식을 지원한다.
3. WHEN 지원하지 않는 파일 형식이 입력되면, THE DocumentParser SHALL `UnsupportedFileFormatError` 예외를 발생시킨다.
4. THE DocumentParser SHALL `--bedrock-model` 옵션으로 사용할 Bedrock 모델 ID를 지정할 수 있도록 한다 (기본값: `anthropic.claude-3-5-sonnet-20241022-v2:0`).
5. WHEN Bedrock API 호출이 실패하면, THE DocumentParser SHALL `DocumentParseError` 예외를 발생시킨다.
6. WHEN 문서 파싱이 성공하면, THE DocumentParser SHALL 추출된 정보(current_instance, recommended_instance, on_prem_cost, engine 등)를 `ParsedDocumentInfo` 모델로 반환한다.
7. WHEN 파싱 결과에 필수 필드(current_instance)가 누락된 경우, THE Estimator SHALL 누락된 필드를 CLI 인수로 보완할 수 있도록 한다.
8. WHEN `--input-file`이 지정되지 않으면, THE Estimator SHALL 기존 방식(직접 CLI 인수 입력)으로 동작하여 하위 호환성을 유지한다.
9. THE DocumentParser SHALL 문서에서 추출한 텍스트를 Bedrock에 전달할 때 구조화된 JSON 출력을 요청하는 프롬프트를 사용한다.

---

### 요구사항 7: 코드 품질 및 구조

**사용자 스토리:** 유지보수 담당자로서, 모듈화되고 타입이 명시된 코드를 원합니다. 그래야 기능 추가 및 버그 수정이 용이합니다.

#### 인수 기준

1. THE Estimator SHALL 모든 함수와 메서드에 Python 타입 힌트를 적용한다.
2. THE Estimator SHALL Pydantic v2 모델을 사용하여 입력 데이터 및 API 응답을 검증한다.
3. WHEN 단일 모듈이 500줄을 초과하면, THE Estimator SHALL 해당 모듈을 기능 단위로 분리한다.
4. THE Estimator SHALL `asyncio`를 활용하여 여러 인스턴스 유형에 대한 API 호출을 병렬로 처리한다.
5. THE Estimator SHALL `pyproject.toml` 또는 `requirements.txt`를 통해 의존성을 명시한다.
