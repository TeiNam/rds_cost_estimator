# 코드 품질 개선 요구사항

## 개요
코드베이스 분석에서 발견된 15개 항목을 버그 수정, 설계 개선, 일관성 개선 세 카테고리로 분류하여 체계적으로 해결합니다.

---

## 요구사항 1: 월 시간 기준 통일

### 사용자 스토리
> 비용 산출 담당자로서, 온디맨드와 RI 비용 계산에 동일한 월 시간 기준이 적용되어야 합니다. 그래야 비용 비교가 정확합니다.

### 수용 기준
- [ ] `pricing_client.py` 전체에서 월 시간 상수를 `HOURS_PER_MONTH = 730`으로 통일
- [ ] `_parse_response`의 RI 월정액 계산(`hourly_fee * 24 * 30.4375`)을 `hourly_fee * 730`으로 변경
- [ ] `CostRecord.compute_annual_cost`의 `730 * 12` 계산 유지 (8,760시간/년)
- [ ] 기존 테스트가 모두 통과하고, 월 시간 기준 관련 테스트 추가

### 관련 파일
- `src/rds_cost_estimator/pricing_client.py`
- `src/rds_cost_estimator/models.py`
- `tests/test_estimator.py`

---

## 요구사항 2: 부분 캐시 히트 활용

### 사용자 스토리
> 비용 조회 시, 캐시에 일부 가격 유형만 있어도 해당 부분은 재조회하지 않아야 합니다. API 호출 횟수를 줄여 성능을 개선합니다.

### 수용 기준
- [ ] `fetch_all`에서 캐시에 존재하는 `PricingType`은 건너뛰고, 누락된 것만 API 조회
- [ ] 부분 캐시 히트 시 캐시된 레코드와 새로 조회한 레코드를 병합하여 반환
- [ ] 부분 캐시 히트 시나리오에 대한 테스트 추가

### 관련 파일
- `src/rds_cost_estimator/pricing_client.py`
- `tests/test_estimator.py`

---

## 요구사항 3: v1/v2 패밀리 확장 전략 통일

### 사용자 스토리
> 개발자로서, `run()`(v1)과 `run_v2()`의 패밀리 확장 로직이 일관되어야 합니다. 유지보수 시 혼란을 방지합니다.

### 수용 기준
- [ ] v1 `run()` 경로가 아직 필요한지 결정 (불필요하면 제거)
- [ ] 필요하다면 v1도 `_resolve_family_pair` 또는 동일한 패밀리 확장 로직 사용
- [ ] v1 제거 시 관련 테스트도 정리

### 관련 파일
- `src/rds_cost_estimator/estimator.py`
- `tests/test_estimator.py`

---

## 요구사항 4: 템플릿 치환 방식 안전성 강화

### 사용자 스토리
> 리포트 생성 시, 템플릿 치환이 의도치 않은 문자열을 변경하지 않아야 합니다.

### 수용 기준
- [ ] `render_markdown_v2`에서 단순 `str.replace` 대신 정규식 또는 구분자 기반 치환 사용
- [ ] `{family_a}`, `{family_b}` 패턴만 정확히 매칭하여 치환
- [ ] 템플릿 본문에 "family_a"라는 일반 텍스트가 있어도 치환되지 않는 테스트 추가

### 관련 파일
- `src/rds_cost_estimator/renderer.py`
- `tests/test_estimator.py` (또는 새 `tests/test_renderer.py`)

---

## 요구사항 5: asyncio deprecated API 교체

### 사용자 스토리
> Python 3.10+ 환경에서 deprecation 경고 없이 실행되어야 합니다.

### 수용 기준
- [ ] `asyncio.get_event_loop()` → `asyncio.new_event_loop()` 또는 `asyncio.run()` 패턴으로 교체
- [ ] Python 3.11+ 환경에서 deprecation 경고 없이 실행 확인

### 관련 파일
- `src/rds_cost_estimator/pricing_client.py`
- `src/rds_cost_estimator/estimator.py`

---

## 요구사항 6: TCO 연도 오프셋 수정

### 사용자 스토리
> TCO 보고서에서 1년차 비용은 1년차 증가분이 반영된 스토리지 비용이어야 합니다. 현재는 현재 크기 기준으로 계산되어 직관과 다릅니다.

### 수용 기준
- [ ] `_fill_tco`에서 `yearly_stor[0]`이 1년차(증가율 1회 적용) 비용을 나타내도록 수정
- [ ] 또는 현재 로직이 의도적이라면 템플릿/문서에 "1년차 = 현재 기준"임을 명시
- [ ] TCO 계산 관련 테스트에서 연도별 비용이 올바른지 검증

### 관련 파일
- `src/rds_cost_estimator/estimator.py`
- `cost_report_template_v2.md`
- `tests/test_estimator.py`

---

## 요구사항 7: DuckDBStore 컨텍스트 매니저 지원

### 사용자 스토리
> DuckDB 연결이 `with` 문으로 안전하게 관리되어야 합니다. `close()` 누락으로 인한 리소스 누수를 방지합니다.

### 수용 기준
- [ ] `DuckDBStore`에 `__enter__`/`__exit__` 메서드 추가
- [ ] `__exit__`에서 `close()` 자동 호출
- [ ] `estimator.py`와 `cli.py`에서 `with DuckDBStore(...) as store:` 패턴 사용
- [ ] 컨텍스트 매니저 테스트 추가

### 관련 파일
- `src/rds_cost_estimator/db_store.py`
- `src/rds_cost_estimator/estimator.py`
- `src/rds_cost_estimator/cli.py`
- `tests/test_db_store.py`

---

## 요구사항 8: estimator.py 모듈 분리 (500줄 제한)

### 사용자 스토리
> 개발자로서, 각 모듈이 500줄 이하로 유지되어야 코드 탐색과 유지보수가 쉽습니다.

### 수용 기준
- [ ] 템플릿 데이터 구성 로직(`_fill_*` 메서드들)을 `template_builder.py`로 분리
- [ ] 순수 함수들(`calc_storage_costs`, `get_instance_specs`, `extract_family_and_size`, `expand_instance_families`, `find_matching_instance`)을 `instance_utils.py`로 분리
- [ ] `estimator.py`가 500줄 이하로 유지
- [ ] 분리 후 모든 기존 테스트 통과

### 관련 파일
- `src/rds_cost_estimator/estimator.py` → 분리 대상
- `src/rds_cost_estimator/template_builder.py` (신규)
- `src/rds_cost_estimator/instance_utils.py` (신규)
- `tests/test_estimator.py`

---

## 요구사항 9: v1 run() 경로 정리

### 사용자 스토리
> v2가 메인 경로라면, v1 코드를 제거하여 코드베이스를 단순화합니다.

### 수용 기준
- [ ] v1 `run()` 메서드가 아직 사용되는지 확인 (CLI에서 호출 여부)
- [ ] 사용되지 않으면 `run()`, `_build_specs()`, `_build_cost_table()` 등 v1 전용 메서드 제거
- [ ] v1 전용 모델(`CostTable`, `CostTableRow` 등)이 v2에서도 사용되는지 확인 후 정리
- [ ] 관련 테스트 정리

### 관련 파일
- `src/rds_cost_estimator/estimator.py`
- `src/rds_cost_estimator/cost_table.py`
- `src/rds_cost_estimator/cli.py`
- `tests/test_estimator.py`

---

## 요구사항 10: 불필요한 인스턴스 사이즈 제거

### 사용자 스토리
> 인스턴스 사양 테이블에 실제 RDS에 존재하지 않는 사이즈(micro, small, medium 등)가 포함되면 혼란을 줍니다.

### 수용 기준
- [ ] `_SIZE_SPECS`에서 r 계열에 존재하지 않는 사이즈 제거 (또는 해당 사이즈가 다른 패밀리에서 사용되는지 확인)
- [ ] `_M_SIZE_SPECS`, `_T_SIZE_SPECS`는 해당 패밀리의 실제 사이즈만 포함
- [ ] 각 사양 테이블의 vCPU/메모리 값이 AWS 공식 문서와 일치하는지 검증

### 관련 파일
- `src/rds_cost_estimator/estimator.py`
- `tests/test_estimator.py`

---

## 요구사항 11: 리전별 스토리지/네트워크 요금 동적 조회

### 사용자 스토리
> `ap-northeast-2` 외 리전에서도 정확한 스토리지/네트워크 비용이 산출되어야 합니다.

### 수용 기준
- [ ] `GP3_STORAGE_PER_GB`, 네트워크 비용 상수를 하드코딩 대신 Pricing API 또는 설정 파일에서 조회
- [ ] 또는 최소한 리전 파라미터에 따라 다른 값을 사용하도록 구성
- [ ] 리전별 요금 차이가 반영되는 테스트 추가

### 관련 파일
- `src/rds_cost_estimator/estimator.py`
- `src/rds_cost_estimator/pricing_client.py`

---

## 요구사항 12: Dead code 정리 (PricingType)

### 사용자 스토리
> 사용되지 않는 코드를 제거하여 코드베이스를 깔끔하게 유지합니다.

### 수용 기준
- [ ] `PricingType.RI_1YR`, `PricingType.RI_3YR` (Partial Upfront)가 v2에서 사용되는지 확인
- [ ] 사용되지 않으면 제거하거나 deprecated 표시
- [ ] `fetch_reserved` (v1 전용)도 v1 제거 시 함께 정리

### 관련 파일
- `src/rds_cost_estimator/models.py`
- `src/rds_cost_estimator/pricing_client.py`

---

## 요구사항 13: CostTable v2 호환성

### 사용자 스토리
> `CostTable.compute_savings`가 v2의 가격 유형(`RI_1YR_NO_UPFRONT` 등)과 호환되어야 합니다.

### 수용 기준
- [ ] `CostTable`이 v2에서 사용되는지 확인
- [ ] 사용된다면 `compute_savings`가 v2 `PricingType`을 참조하도록 수정
- [ ] 사용되지 않으면 요구사항 9(v1 정리)와 함께 처리

### 관련 파일
- `src/rds_cost_estimator/cost_table.py`
- `src/rds_cost_estimator/models.py`

---

## 요구사항 14: 네트워크 기본값 키 누락 수정

### 사용자 스토리
> 네트워크 비용 데이터가 없을 때도 템플릿의 연도별 네트워크 비용 플레이스홀더가 올바르게 치환되어야 합니다.

### 수용 기준
- [ ] `_fill_network_defaults`에 `net_total_monthly_1y`, `net_total_monthly_2y`, `net_total_monthly_3y` 등 연도별 키 추가
- [ ] `_fill_network_costs`에서 설정하는 모든 키가 `_fill_network_defaults`에도 기본값으로 존재
- [ ] 네트워크 데이터 없이 리포트 생성 시 플레이스홀더가 남지 않는 테스트 추가

### 관련 파일
- `src/rds_cost_estimator/estimator.py`
- `tests/test_estimator.py`

---

## 요구사항 16: Replatform vs Refactoring 비용 비교 섹션

### 사용자 스토리
> 마이그레이션 담당자로서, 소스 DB가 Oracle일 때 RDS for Oracle(Replatform)과 Aurora PostgreSQL(Refactoring) 동일 사이즈의 비용을 나란히 비교하고 싶습니다. 그래야 이관 전략 결정에 정량적 근거를 확보할 수 있습니다.

### 수용 기준
- [ ] `run_v2()`에서 소스 엔진이 Oracle 계열(`oracle-ee`, `oracle-se2`)일 때, 동일 인스턴스 사이즈로 `aurora-postgresql` 엔진 가격도 함께 조회
- [ ] Aurora PostgreSQL 가격 조회 시 동일 패밀리/사이즈의 InstanceSpec을 `engine="aurora-postgresql"`, `strategy=REFACTORING`으로 생성
- [ ] `_build_template_data`에서 Replatform 비용과 Refactoring 비용을 별도 키로 data에 추가 (예: `refac_{family}_{opt}_monthly`, `refac_{family}_{opt}_total_yearly`)
- [ ] 템플릿(`cost_report_template_v2.md`)에 "이관 전략별 비용 비교" 섹션 추가: 동일 인스턴스 사이즈에서 Oracle vs Aurora PostgreSQL 비용을 나란히 표시
- [ ] 비교 섹션에 연간 비용 차이(절감액)와 절감률(%) 표시
- [ ] 소스 엔진이 Oracle이 아닌 경우 이 섹션은 생략 (또는 "해당 없음" 표시)
- [ ] Refactoring 가격 조회 실패 시 해당 항목을 "N/A"로 표시하고 나머지 리포트는 정상 생성

### 관련 파일
- `src/rds_cost_estimator/estimator.py`
- `src/rds_cost_estimator/pricing_client.py`
- `cost_report_template_v2.md`
- `tests/test_estimator.py`

---

## 요구사항 15: 테스트 커버리지 보강

### 사용자 스토리
> 위 모든 변경사항에 대해 충분한 테스트 커버리지가 확보되어야 합니다.

### 수용 기준
- [ ] 각 요구사항 수정 후 관련 테스트 추가/수정
- [ ] 전체 테스트 스위트 통과
- [ ] 새로 분리된 모듈(`template_builder.py`, `instance_utils.py`)에 대한 테스트 파일 생성
- [ ] Replatform vs Refactoring 비교 섹션 관련 테스트 추가

### 관련 파일
- `tests/` 디렉토리 전체

---

## 우선순위

| 순위 | 요구사항 | 카테고리 | 영향도 |
|------|----------|----------|--------|
| 1 | 요구사항 1: 월 시간 기준 통일 | 버그 | 비용 계산 정확도 |
| 2 | 요구사항 14: 네트워크 기본값 키 누락 | 버그 | 리포트 렌더링 오류 |
| 3 | 요구사항 6: TCO 연도 오프셋 | 버그 | 비용 계산 정확도 |
| 4 | 요구사항 5: asyncio deprecated API | 버그 | 런타임 경고 |
| 5 | 요구사항 16: Replatform vs Refactoring 비교 | 기능 | 이관 전략 의사결정 |
| 6 | 요구사항 7: DuckDBStore 컨텍스트 매니저 | 설계 | 리소스 안전성 |
| 7 | 요구사항 4: 템플릿 치환 안전성 | 설계 | 렌더링 안정성 |
| 8 | 요구사항 9: v1 run() 정리 | 설계 | 코드 단순화 |
| 9 | 요구사항 12: Dead code 정리 | 일관성 | 코드 정리 |
| 10 | 요구사항 13: CostTable 호환성 | 일관성 | v1/v2 정합성 |
| 11 | 요구사항 3: 패밀리 확장 통일 | 설계 | v1/v2 일관성 |
| 12 | 요구사항 8: estimator.py 분리 | 설계 | 유지보수성 |
| 13 | 요구사항 10: 불필요 사이즈 제거 | 일관성 | 데이터 정확도 |
| 14 | 요구사항 2: 부분 캐시 히트 | 설계 | 성능 |
| 15 | 요구사항 11: 리전별 요금 동적 조회 | 설계 | 다중 리전 지원 |
| 16 | 요구사항 15: 테스트 커버리지 | 품질 | 전체 |
