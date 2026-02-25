# 구현 계획: 코드 품질 개선

## 개요

15개 요구사항을 우선순위에 따라 4개 페이즈로 나누어 구현합니다.
각 페이즈는 독립적으로 테스트 가능하며, 이전 페이즈의 변경사항에 의존합니다.

- **페이즈 1**: 버그 수정 (요구사항 1, 14, 6, 5) — 비용 계산 정확도와 런타임 안정성
- **페이즈 2**: 리소스 안전성 및 렌더링 (요구사항 7, 4) — DuckDBStore 컨텍스트 매니저, 템플릿 치환
- **페이즈 3**: v1 정리 및 dead code 제거 (요구사항 9, 12, 13, 3) — 코드 단순화
- **페이즈 4**: 구조 개선 (요구사항 16, 8, 10, 2, 11, 15) — Refactoring 비교, 모듈 분리, 캐시, 리전 지원

## 태스크

### 페이즈 1: 버그 수정

- [x] 1. 월 시간 기준 통일 (요구사항 1)
  - `models.py`에 `HOURS_PER_MONTH = 730` 상수 추가
  - `pricing_client.py`의 `_parse_response`에서 RI 월정액 계산을 `hourly_fee * 24 * 30.4375` → `hourly_fee * HOURS_PER_MONTH`로 변경
  - `_parse_response`에서 `from rds_cost_estimator.models import HOURS_PER_MONTH` 추가
  - `_parse_ri_response`와 `fetch_ri_offering`은 이미 `hourly_fee * 730` 사용 중이므로 `HOURS_PER_MONTH` 상수 참조로 변경
  - 기존 테스트 통과 확인
  - _요구사항: 1_

- [x] 2. 네트워크 기본값 키 누락 수정 (요구사항 14)
  - `_fill_network_costs`에서 설정하는 모든 키를 열거하여 `_fill_network_defaults`와 비교
  - `_fill_network_defaults`에 누락된 키 추가 (현재 `_fill_network_costs`에서 설정하지만 defaults에 없는 키 확인)
  - 네트워크 데이터 없이 `_build_template_data` 호출 시 미치환 플레이스홀더가 없는지 테스트 추가
  - _요구사항: 14_

- [x] 3. TCO 연도 오프셋 수정 (요구사항 6)
  - `_fill_tco`에서 `for year in range(3)` → `for year in range(1, 4)`로 변경하여 1년차부터 시작
  - `_fill_storage_costs`에서 `for year in range(4)` → `for year in range(0, 4)`는 유지 (0y = 현재 기준 맞음)
  - `_fill_tco`의 `yearly_stor[yr_idx]` 인덱싱이 올바르게 1년차~3년차를 참조하도록 수정
  - TCO 연도별 비용이 증가율을 반영하는지 검증하는 테스트 추가
  - _요구사항: 6_

- [x] 4. asyncio deprecated API 교체 (요구사항 5)
  - `pricing_client.py`의 `asyncio.get_event_loop()` 5곳을 `asyncio.get_running_loop()`로 교체:
    - `fetch_on_demand` (Line ~388)
    - `fetch_reserved_option` (Line ~451)
    - `fetch_reserved` (Line ~575)
    - `fetch_all` (Line ~651)
    - `fetch_ri_offering` (Line ~766)
  - 기존 테스트 통과 확인
  - _요구사항: 5_

- [x] 5. 페이즈 1 체크포인트
  - 전체 테스트 스위트 실행하여 통과 확인
  - 문제 발생 시 수정

### 페이즈 2: 리소스 안전성 및 렌더링

- [x] 6. DuckDBStore 컨텍스트 매니저 지원 (요구사항 7)
  - `db_store.py`의 `DuckDBStore`에 `__enter__`/`__exit__` 메서드 추가
  - `__exit__`에서 `self.close()` 호출, 예외 전파하지 않음
  - `estimator.py`의 `run_v2()`에서 `self._db_store = DuckDBStore()` + `self._db_store.close()` → `with DuckDBStore() as store:` 패턴으로 변경
  - `tests/test_db_store.py`에 컨텍스트 매니저 테스트 추가
  - _요구사항: 7_

- [x] 7. 템플릿 치환 방식 안전성 강화 (요구사항 4)
  - `renderer.py`의 `render_markdown_v2`에서 1단계 치환 변경:
    - 기존: `template_content.replace("family_a", family_a).replace("family_b", family_b)`
    - 개선: 플레이스홀더 내부의 `family_a`/`family_b`만 치환하는 방식으로 변경
    - 접근법: 먼저 `{...}` 패턴 내부의 `family_a`/`family_b`를 치환, 그 외 텍스트는 보존
  - `tests/test_renderer.py`에 일반 텍스트 "family_a"가 치환되지 않는 테스트 추가
  - _요구사항: 4_

- [x] 8. 페이즈 2 체크포인트
  - 전체 테스트 스위트 실행하여 통과 확인

### 페이즈 3: v1 정리 및 dead code 제거

- [x] 9. v1 run() 경로 정리 (요구사항 9, 3)
  - `__main__.py`에서 `run_v2()`만 호출하는 것 확인 완료 → v1 `run()` 제거 가능
  - `estimator.py`에서 v1 전용 메서드 제거: `run()`, `_build_specs()`
  - `cli.py`에서 v1 전용 인수(`--recommended-instance` 등)가 있는지 확인 후 정리
  - v1 전용 테스트 정리 (있다면)
  - _요구사항: 9, 3_

- [x] 10. Dead code 정리 — PricingType 및 v1 전용 메서드 (요구사항 12)
  - `PricingType.RI_1YR`, `PricingType.RI_3YR` (Partial Upfront)가 v2 경로에서 사용되는지 확인
  - `fetch_reserved` (Partial Upfront 전용)가 v2에서 사용되지 않으면 제거
  - `_parse_response`의 RI 분기(Partial Upfront 전용)가 v2에서 사용되지 않으면 제거
  - `fetch_reserved_option`의 Partial Upfront 매핑은 유지 (범용 메서드)
  - _요구사항: 12_

- [x] 11. CostTable v2 호환성 확인 (요구사항 13)
  - `CostTable`이 v2 경로(`run_v2()`)에서 사용되는지 확인
  - v2에서 사용되지 않으면 `cost_table.py`를 deprecated 표시 또는 v1 제거와 함께 정리
  - v2에서 사용된다면 `compute_savings`가 v2 PricingType(`RI_1YR_NO_UPFRONT` 등)을 참조하도록 수정
  - `renderer.py`의 `render_console`, `render_markdown`이 `CostTable`을 사용하지만 v2에서는 `render_markdown_v2`만 사용 → v1 렌더러도 deprecated 처리
  - _요구사항: 13_

- [x] 12. 페이즈 3 체크포인트
  - 전체 테스트 스위트 실행하여 통과 확인
  - v1 관련 테스트가 제거/수정되었는지 확인

### 페이즈 4: 구조 개선

- [x] 13. Replatform vs Refactoring 비용 비교 섹션 (요구사항 16)
  - `estimator.py`의 `run_v2()`에서 소스 엔진이 Oracle 계열일 때 Aurora PostgreSQL 가격도 병렬 조회:
    - 동일 `target_instances`에 대해 `engine=REFACTORING_ENGINE`, `strategy=MigrationStrategy.REFACTORING`으로 InstanceSpec 추가 생성
    - 기존 `asyncio.gather` 호출에 포함하여 병렬 조회
  - Refactoring 전용 `refac_price_index` 딕셔너리 생성 (기존 `price_index`와 분리)
  - `_fill_refactoring_comparison` 메서드 신규 추가:
    - SGA 최적화 기준 인스턴스의 Replatform vs Refactoring 비용 비교
    - 각 요금 옵션별 절감액/절감률 계산
    - `refac_{family}_{opt}_monthly`, `refac_{family}_{opt}_total_yearly`, `refac_{family}_{opt}_savings`, `refac_{family}_{opt}_savings_rate` 키 설정
  - `_fill_refactoring_defaults` 메서드 신규 추가: 비Oracle 엔진 또는 조회 실패 시 기본값 설정
  - `_build_template_data`에서 `_fill_refactoring_comparison` 호출 추가
  - `cost_report_template_v2.md`에 "이관 전략별 비용 비교" 섹션 추가 (기존 섹션 7과 8 사이, 새 섹션 8)
  - 기존 섹션 8(권장사항) → 섹션 9로 번호 변경
  - `renderer.py`의 `render_markdown_v2`에서 비Oracle 엔진일 때 Refactoring 섹션 제거 후처리 추가
  - Refactoring 비교 관련 테스트 추가
  - _요구사항: 16_

- [x] 14. estimator.py 모듈 분리 (요구사항 8)
  - `instance_utils.py` 신규 생성: 상수(`_SIZE_SPECS`, `_M_SIZE_SPECS`, `_T_SIZE_SPECS`, `GP3_*`, `NET_*`, `_INSTANCE_PATTERN` 등)와 순수 함수(`get_instance_specs`, `extract_family_and_size`, `expand_instance_families`, `find_matching_instance`, `calc_storage_costs`) 이동
  - `template_builder.py` 신규 생성: `_fill_storage_costs`, `_fill_network_costs`, `_fill_network_defaults`, `_fill_instance_specs`, `_get_monthly`, `_fill_pricing`, `_fill_comparison`, `_fill_tco`, `_fill_refactoring_comparison`, `_fill_refactoring_defaults`, `_build_template_data` 메서드를 `TemplateBuilder` 클래스로 이동
  - `estimator.py`에서 이동된 함수/클래스를 import하여 사용
  - `estimator.py`가 500줄 이하인지 확인
  - 기존 테스트가 모두 통과하는지 확인
  - `tests/test_instance_utils.py`, `tests/test_template_builder.py` 신규 생성
  - _요구사항: 8_

- [x] 15. 불필요한 인스턴스 사이즈 제거 (요구사항 10)
  - `_SIZE_SPECS`(r 계열)에서 `micro`, `small`, `medium` 제거 (AWS RDS r 계열은 `large` 이상만 제공)
  - `_T_SIZE_SPECS`는 현재 사이즈 유지 (t3/t4g는 micro~2xlarge 제공)
  - `_M_SIZE_SPECS`는 현재 사이즈 유지 (m 계열은 large 이상)
  - `find_matching_instance`가 제거된 사이즈를 참조하지 않는지 확인
  - _요구사항: 10_

- [x] 16. 부분 캐시 히트 활용 (요구사항 2)
  - `fetch_all`에서 캐시 확인 로직 변경:
    - 기존: 전체 캐시 히트가 아니면 `records = []`로 초기화 후 전체 재조회
    - 개선: 캐시에 있는 PricingType은 수집, 누락된 것만 API 호출 후 파싱
  - 부분 캐시 히트 시나리오 테스트 추가
  - _요구사항: 2_

- [x] 17. 리전별 스토리지/네트워크 요금 동적 조회 (요구사항 11)
  - `instance_utils.py`(또는 신규 `region_pricing.py`)에 리전별 요금 딕셔너리 추가
  - `calc_storage_costs`에 `region` 파라미터 추가, 기본값은 `ap-northeast-2`
  - `_fill_network_costs`에서 네트워크 비용 상수도 리전별로 참조
  - 리전별 요금 차이가 반영되는 테스트 추가
  - _요구사항: 11_

- [x] 18. 테스트 커버리지 보강 (요구사항 15)
  - 각 페이즈에서 추가된 테스트 확인
  - 신규 모듈(`instance_utils.py`, `template_builder.py`)에 대한 테스트 파일 확인
  - Replatform vs Refactoring 비교 섹션 관련 테스트 확인
  - 전체 테스트 스위트 통과 확인
  - _요구사항: 15_

- [x] 19. 최종 체크포인트
  - 전체 테스트 스위트 실행
  - `estimator.py` 줄 수 확인 (500줄 이하)
  - `asyncio.get_event_loop()` 사용 없음 확인
  - 미치환 플레이스홀더 없음 확인
  - Refactoring 비교 섹션이 Oracle 엔진에서만 표시되는지 확인

## 의존성 관계

```
태스크 1 (월 시간) → 독립
태스크 2 (네트워크 기본값) → 독립
태스크 3 (TCO 오프셋) → 독립
태스크 4 (asyncio) → 독립
태스크 6 (컨텍스트 매니저) → 독립
태스크 7 (템플릿 치환) → 독립
태스크 9 (v1 정리) → 독립
태스크 10 (dead code) → 태스크 9 이후
태스크 11 (CostTable) → 태스크 9 이후
태스크 13 (Refactoring 비교) → 태스크 4 이후 (asyncio 교체 반영), 독립 구현 가능
태스크 14 (모듈 분리) → 태스크 9, 10, 13 이후 (제거된 코드 및 신규 메서드 반영)
태스크 15 (사이즈 제거) → 태스크 14 이후 (instance_utils.py에서 수정)
태스크 16 (부분 캐시) → 태스크 4 이후 (asyncio 교체 반영)
태스크 17 (리전 요금) → 태스크 14 이후 (instance_utils.py에서 수정)
```

## 참고 사항

- 각 페이즈 완료 후 체크포인트에서 전체 테스트를 실행합니다.
- v1 제거(태스크 9)는 `__main__.py`에서 `run_v2()`만 호출하는 것을 확인한 후 진행합니다.
- 모듈 분리(태스크 14)는 v1 정리 및 Refactoring 비교 구현 후 진행하여 불필요한 코드를 옮기지 않도록 합니다.
- Refactoring 비교(태스크 13)는 페이즈 4 첫 번째로 구현하여, 모듈 분리 시 `_fill_refactoring_comparison`/`_fill_refactoring_defaults`도 함께 이동합니다.
- 리전별 요금(태스크 17)은 MVP 수준으로 딕셔너리 기반 구현, Pricing API 동적 조회는 향후 확장.
