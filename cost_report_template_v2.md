# {db_name} — AWS RDS 비용 예측 리포트

> 📅 리포트 생성일: {report_date} | 리전: {aws_region} | 요금 기준일: {pricing_date}

---

## 📋 핵심 요약 (Executive Summary)

| 항목 | 내용 |
|------|------|
| **데이터베이스** | {db_name} (Oracle {oracle_version}) |
| **현재 서버** | CPU {cpu_cores}코어 / 메모리 {physical_memory}GB / DB {db_size}GB |
| **비교 패밀리** | {family_a} / {family_b} |
| **권장 인스턴스 (서버 매칭)** | {spec_family_a_instance} / {spec_family_b_instance} |
| **권장 인스턴스 (SGA 최적화)** | {sga_family_a_instance} / {sga_family_b_instance} |

### 💰 연간 비용 한눈에 보기 (Single-AZ, 인스턴스+스토리지+네트워크 합산)

| 시나리오 | {family_a} | {family_b} |
|---------|-----------|-----------|
| **SGA 최적화 · On-Demand** | ${comp_sga_family_a_od}/년 | ${comp_sga_family_b_od}/년 |
| **SGA 최적화 · 1년 RI** | ${comp_sga_family_a_ri1au}/년 | ${comp_sga_family_b_ri1au}/년 |
| **SGA 최적화 · 3년 RI** | ${comp_sga_family_a_ri3au}/년 | ${comp_sga_family_b_ri3au}/년 |
| **3년 TCO (SGA+3년RI)** | ${tco_sga_family_a_ri3} | ${tco_sga_family_b_ri3} |

> 💡 SGA 기반 최적화 + 3년 RI(All Upfront)가 가장 비용 효율적인 조합입니다.

---

## 1. 현재 서버 사양

### 서버 리소스

| 항목 | 값 |
|------|-----|
| CPU 코어 수 | {cpu_cores} |
| 물리 메모리 | {physical_memory} GB |
| 전체 DB 크기 | {db_size} GB |
| 인스턴스 구성 | {instance_config} |

### 성능 메트릭 (AWR)

| 항목 | 평균 | 피크 (P99) |
|------|------|-----------|
| CPU 사용률 | {avg_cpu}% | {peak_cpu}% |
| DB CPU/s | {avg_cpu_per_s} | {peak_cpu_per_s} |
| I/O 부하 | {avg_iops} IOPS | {peak_iops} IOPS |
| 메모리 사용량 | {avg_memory} GB | {peak_memory} GB |

### SGA 분석

| 항목 | 값 |
|------|-----|
| 현재 SGA 크기 | {current_sga} GB |
| 권장 SGA 크기 | {recommended_sga} GB |
| SGA 증가율 | {sga_increase_rate}% |

> **권장 SGA**는 Buffer Pool Advisory 데이터 기반으로 Physical Reads가 더 이상 감소하지 않는 최적 지점을 분석한 결과입니다.

### 스토리지 증가 추이

| 항목 | 현재 | 1년 후 | 2년 후 | 3년 후 |
|------|------|--------|--------|--------|
| **DB 크기** | {db_size} GB | {db_size_1y} GB | {db_size_2y} GB | {db_size_3y} GB |

| 항목 | 값 |
|------|-----|
| 최근 1년 증가량 | {yearly_growth} GB |
| 연간 증가율 | {yearly_growth_rate}% |

> 증가율이 확인되지 않을 경우 업계 평균 15~20%를 기본값으로 적용합니다.

---

## 2. RDS 인스턴스 권장 사양

### 2-1. 현재 서버 사양 매칭 (1:1 대응)

> 현재 온프레미스 서버와 동일한 수준의 리소스를 제공하는 RDS 인스턴스입니다.

| 항목 | {family_a} | {family_b} |
|------|-----|-----|
| **인스턴스 타입** | **{spec_family_a_instance}** | **{spec_family_b_instance}** |
| vCPU | {spec_family_a_vcpu} | {spec_family_b_vcpu} |
| 메모리 | {spec_family_a_memory} GB | {spec_family_b_memory} GB |
| 네트워크 대역폭 | {spec_family_a_network} Gbps | {spec_family_b_network} Gbps |

### 2-2. SGA 기반 최적화 권장 (비용 최적화)

> 권장 SGA({recommended_sga}GB) + 여유율({buffer_rate}%) 기준으로 산정합니다.

| 항목 | {family_a} | {family_b} |
|------|-----|-----|
| **인스턴스 타입** | **{sga_family_a_instance}** | **{sga_family_b_instance}** |
| vCPU | {sga_family_a_vcpu} | {sga_family_b_vcpu} |
| 메모리 | {sga_family_a_memory} GB | {sga_family_b_memory} GB |
| 네트워크 대역폭 | {sga_family_a_network} Gbps | {sga_family_b_network} Gbps |

> 💡 **{family_b} vs {family_a}**: 동일 사이즈에서 세대 차이에 따른 성능 향상이 있을 수 있습니다. 한 단계 낮은 사이즈로 비용 절감을 노릴 수 있습니다.

---

## 3. 스토리지 비용

### 스토리지 구성

| 항목 | 값 |
|------|-----|
| 스토리지 타입 | {storage_type} |
{storage_config_rows}

### 연도별 스토리지 비용 예측

| 항목 | 현재 (0년차) | 1년차 | 2년차 | 3년차 |
|------|-------------|-------|-------|-------|
| 예상 DB 크기 | {db_size} GB | {db_size_1y} GB | {db_size_2y} GB | {db_size_3y} GB |
| 스토리지 비용 | ${stor_cost_0y}/월 | ${stor_cost_1y}/월 | ${stor_cost_2y}/월 | ${stor_cost_3y}/월 |
{storage_extra_cost_rows}| **Single-AZ 월 합계** | **${stor_total_0y}** | **${stor_total_1y}** | **${stor_total_2y}** | **${stor_total_3y}** |
| **Multi-AZ 월 합계** | **${stor_maz_total_0y}** | **${stor_maz_total_1y}** | **${stor_maz_total_2y}** | **${stor_maz_total_3y}** |

> {storage_type} 요금: {storage_price_per_gb} ({aws_region} 기준). {storage_pricing_detail}
> {storage_note}

---

## 4. 네트워크 전송 비용

### AWR 기반 네트워크 트래픽 추정

| 트래픽 유형 | 일 평균 | 월 예상 (×30) |
|------------|--------|-------------|
| 클라이언트 ↔ DB (수신) | {sqlnet_recv_daily} GB | {sqlnet_recv_monthly} GB |
| 클라이언트 ↔ DB (송신) | {sqlnet_sent_daily} GB | {sqlnet_sent_monthly} GB |
| DB 간 통신 (DB Link) | {dblink_daily} GB | {dblink_monthly} GB |
| Redo 생성량 | {redo_daily} GB | {redo_monthly} GB |
| **합계** | **{net_total_daily} GB** | **{net_total_monthly} GB** |

### 배포 시나리오별 월 네트워크 비용

| 시나리오 | **월 비용** | **연 비용** |
|---------|-----------|-----------|
| **Single-AZ (같은 AZ)** | **$0** | **$0** |
| **Single-AZ (Cross-AZ App)** | **${net_cost_cross_az}** | **${net_cost_cross_az_yearly}** |
| **Multi-AZ (Cross-AZ App)** | **${net_cost_maz_cross_az}** | **${net_cost_maz_cross_az_yearly}** |
| + Read Replica (Cross-AZ) | ${net_cost_rr_cross_az} | ${net_cost_rr_cross_az_yearly} |
| + Read Replica (Cross-Region) | ${net_cost_rr_cross_region} | ${net_cost_rr_cross_region_yearly} |

> 💡 App과 RDS를 같은 AZ에 배치하면 네트워크 비용을 제거할 수 있습니다. 단, 단일 AZ 장애 시 영향도를 고려해야 합니다.

### 연도별 네트워크 비용 예측 (Cross-AZ 기준, 증가율 {yearly_growth_rate}%/년)

| 항목 | 현재 | 1년차 | 2년차 | 3년차 |
|------|------|-------|-------|-------|
| 월 트래픽 | {net_total_monthly} GB | {net_total_monthly_1y} GB | {net_total_monthly_2y} GB | {net_total_monthly_3y} GB |
| 월 비용 | ${net_cost_cross_az} | ${net_cost_cross_az_1y} | ${net_cost_cross_az_2y} | ${net_cost_cross_az_3y} |
| **연 비용** | **${net_cost_cross_az_yearly}** | **${net_cost_cross_az_yearly_1y}** | **${net_cost_cross_az_yearly_2y}** | **${net_cost_cross_az_yearly_3y}** |

---

## 5. 통합 비용 분석 (인스턴스 + 스토리지 + 네트워크)

> 네트워크 비용은 {net_scenario} 시나리오 기준입니다. 같은 AZ 배치 시 $0입니다.

### 5-1. 현재 서버 사양 매칭 — Single-AZ

| 요금 옵션 | {family_a} ({spec_family_a_instance}) | | {family_b} ({spec_family_b_instance}) | |
|-----------|:---:|:---:|:---:|:---:|
| | **월 합계** | **연 합계** | **월 합계** | **연 합계** |
| **On-Demand** | ${spec_family_a_od_total_monthly} | ${spec_family_a_od_total_yearly} | ${spec_family_b_od_total_monthly} | ${spec_family_b_od_total_yearly} |
| **1년 RI (All Upfront)** | ${spec_family_a_ri1au_total_monthly} | ${spec_family_a_ri1au_total_yearly} | ${spec_family_b_ri1au_total_monthly} | ${spec_family_b_ri1au_total_yearly} |
| **3년 RI (All Upfront)** | ${spec_family_a_ri3au_total_monthly} | ${spec_family_a_ri3au_total_yearly} | ${spec_family_b_ri3au_total_monthly} | ${spec_family_b_ri3au_total_yearly} |

### 5-2. 현재 서버 사양 매칭 — Multi-AZ

| 요금 옵션 | {family_a} ({spec_family_a_instance}) | | {family_b} ({spec_family_b_instance}) | |
|-----------|:---:|:---:|:---:|:---:|
| | **월 합계** | **연 합계** | **월 합계** | **연 합계** |
| **On-Demand** | ${spec_family_a_maz_od_total_monthly} | ${spec_family_a_maz_od_total_yearly} | ${spec_family_b_maz_od_total_monthly} | ${spec_family_b_maz_od_total_yearly} |
| **1년 RI (All Upfront)** | ${spec_family_a_maz_ri1au_total_monthly} | ${spec_family_a_maz_ri1au_total_yearly} | ${spec_family_b_maz_ri1au_total_monthly} | ${spec_family_b_maz_ri1au_total_yearly} |
| **3년 RI (All Upfront)** | ${spec_family_a_maz_ri3au_total_monthly} | ${spec_family_a_maz_ri3au_total_yearly} | ${spec_family_b_maz_ri3au_total_monthly} | ${spec_family_b_maz_ri3au_total_yearly} |

> ⚠️ Multi-AZ: {maz_storage_note}

### 5-3. SGA 기반 최적화 — Single-AZ

| 요금 옵션 | {family_a} ({sga_family_a_instance}) | | {family_b} ({sga_family_b_instance}) | |
|-----------|:---:|:---:|:---:|:---:|
| | **월 합계** | **연 합계** | **월 합계** | **연 합계** |
| **On-Demand** | ${sga_family_a_od_total_monthly} | ${sga_family_a_od_total_yearly} | ${sga_family_b_od_total_monthly} | ${sga_family_b_od_total_yearly} |
| **1년 RI (All Upfront)** | ${sga_family_a_ri1au_total_monthly} | ${sga_family_a_ri1au_total_yearly} | ${sga_family_b_ri1au_total_monthly} | ${sga_family_b_ri1au_total_yearly} |
| **3년 RI (All Upfront)** | ${sga_family_a_ri3au_total_monthly} | ${sga_family_a_ri3au_total_yearly} | ${sga_family_b_ri3au_total_monthly} | ${sga_family_b_ri3au_total_yearly} |

### 5-4. SGA 기반 최적화 — Multi-AZ

| 요금 옵션 | {family_a} ({sga_family_a_instance}) | | {family_b} ({sga_family_b_instance}) | |
|-----------|:---:|:---:|:---:|:---:|
| | **월 합계** | **연 합계** | **월 합계** | **연 합계** |
| **On-Demand** | ${sga_family_a_maz_od_total_monthly} | ${sga_family_a_maz_od_total_yearly} | ${sga_family_b_maz_od_total_monthly} | ${sga_family_b_maz_od_total_yearly} |
| **1년 RI (All Upfront)** | ${sga_family_a_maz_ri1au_total_monthly} | ${sga_family_a_maz_ri1au_total_yearly} | ${sga_family_b_maz_ri1au_total_monthly} | ${sga_family_b_maz_ri1au_total_yearly} |
| **3년 RI (All Upfront)** | ${sga_family_a_maz_ri3au_total_monthly} | ${sga_family_a_maz_ri3au_total_yearly} | ${sga_family_b_maz_ri3au_total_monthly} | ${sga_family_b_maz_ri3au_total_yearly} |

---

## 6. 전체 비용 비교 요약

### 연간 비용 비교 (Single-AZ, 인스턴스 + 스토리지 + 네트워크 합산)

| 요금 옵션 | 서버 매칭 {family_a} | 서버 매칭 {family_b} | SGA 최적화 {family_a} | SGA 최적화 {family_b} |
|-----------|-------------|-------------|--------------|--------------|
| | {spec_family_a_instance} | {spec_family_b_instance} | {sga_family_a_instance} | {sga_family_b_instance} |
| **On-Demand** | ${comp_spec_family_a_od} | ${comp_spec_family_b_od} | ${comp_sga_family_a_od} | ${comp_sga_family_b_od} |
| **1년 RI (All Upfront)** | ${comp_spec_family_a_ri1au} | ${comp_spec_family_b_ri1au} | ${comp_sga_family_a_ri1au} | ${comp_sga_family_b_ri1au} |
| **3년 RI (All Upfront)** | ${comp_spec_family_a_ri3au} | ${comp_spec_family_b_ri3au} | ${comp_sga_family_a_ri3au} | ${comp_sga_family_b_ri3au} |

### 3년 TCO 비교 (스토리지 증가분 {yearly_growth_rate}%/년 반영)

| 시나리오 | 서버 매칭 {family_a} | 서버 매칭 {family_b} | SGA 최적화 {family_a} | SGA 최적화 {family_b} |
|---------|-------------|-------------|--------------|--------------|
| On-Demand 3년 | ${tco_spec_family_a_od} | ${tco_spec_family_b_od} | ${tco_sga_family_a_od} | ${tco_sga_family_b_od} |
| 1년 RI × 3회 | ${tco_spec_family_a_ri1} | ${tco_spec_family_b_ri1} | ${tco_sga_family_a_ri1} | ${tco_sga_family_b_ri1} |
| **3년 RI 1회** | **${tco_spec_family_a_ri3}** | **${tco_spec_family_b_ri3}** | **${tco_sga_family_a_ri3}** | **${tco_sga_family_b_ri3}** |

### 3년 TCO 비용 구성 상세 (최적 시나리오: SGA 최적화 + 3년 RI)

| 비용 항목 | 1년차 | 2년차 | 3년차 | **3년 합계** |
|----------|-------|-------|-------|---------|
| 인스턴스 ({family_a}) | ${tco_detail_family_a_inst_1y} | ${tco_detail_family_a_inst_2y} | ${tco_detail_family_a_inst_3y} | **${tco_detail_family_a_inst_total}** |
| 스토리지 | ${tco_detail_stor_1y} | ${tco_detail_stor_2y} | ${tco_detail_stor_3y} | **${tco_detail_stor_total}** |
| 네트워크 | ${tco_detail_net_1y} | ${tco_detail_net_2y} | ${tco_detail_net_3y} | **${tco_detail_net_total}** |
| **합계 ({family_a})** | **${tco_detail_family_a_1y}** | **${tco_detail_family_a_2y}** | **${tco_detail_family_a_3y}** | **${tco_detail_family_a_total}** |
| 인스턴스 ({family_b}) | ${tco_detail_family_b_inst_1y} | ${tco_detail_family_b_inst_2y} | ${tco_detail_family_b_inst_3y} | **${tco_detail_family_b_inst_total}** |
| 스토리지 | ${tco_detail_stor_1y} | ${tco_detail_stor_2y} | ${tco_detail_stor_3y} | **${tco_detail_stor_total}** |
| 네트워크 | ${tco_detail_net_1y} | ${tco_detail_net_2y} | ${tco_detail_net_3y} | **${tco_detail_net_total}** |
| **합계 ({family_b})** | **${tco_detail_family_b_1y}** | **${tco_detail_family_b_2y}** | **${tco_detail_family_b_3y}** | **${tco_detail_family_b_total}** |

---

## 7. 이관 전략별 비용 비교 (Oracle → RDS for Oracle vs Aurora PostgreSQL)

> 동일 인스턴스 사이즈에서 RDS for Oracle(Replatform)과 Aurora PostgreSQL(Refactoring)의
> 비용을 비교합니다. SGA 최적화 기준 인스턴스를 사용합니다.

### {family_a} 계열 ({sga_family_a_instance}) — Single-AZ

| 요금 옵션 | RDS for Oracle (연간) | Aurora PostgreSQL (연간) | 절감액 | 절감률 |
|-----------|---------------------|------------------------|--------|--------|
| **On-Demand** | ${comp_sga_family_a_od} | ${refac_family_a_od_total_yearly} | ${refac_family_a_od_savings} | {refac_family_a_od_savings_rate}% |
| **1년 RI (No Upfront)** | ${comp_sga_family_a_ri1nu} | ${refac_family_a_ri1nu_total_yearly} | ${refac_family_a_ri1nu_savings} | {refac_family_a_ri1nu_savings_rate}% |
| **1년 RI (All Upfront)** | ${comp_sga_family_a_ri1au} | ${refac_family_a_ri1au_total_yearly} | ${refac_family_a_ri1au_savings} | {refac_family_a_ri1au_savings_rate}% |
| **3년 RI (No Upfront)** | ${comp_sga_family_a_ri3nu} | ${refac_family_a_ri3nu_total_yearly} | ${refac_family_a_ri3nu_savings} | {refac_family_a_ri3nu_savings_rate}% |
| **3년 RI (All Upfront)** | ${comp_sga_family_a_ri3au} | ${refac_family_a_ri3au_total_yearly} | ${refac_family_a_ri3au_savings} | {refac_family_a_ri3au_savings_rate}% |

### {family_b} 계열 ({sga_family_b_instance}) — Single-AZ

| 요금 옵션 | RDS for Oracle (연간) | Aurora PostgreSQL (연간) | 절감액 | 절감률 |
|-----------|---------------------|------------------------|--------|--------|
| **On-Demand** | ${comp_sga_family_b_od} | ${refac_family_b_od_total_yearly} | ${refac_family_b_od_savings} | {refac_family_b_od_savings_rate}% |
| **1년 RI (No Upfront)** | ${comp_sga_family_b_ri1nu} | ${refac_family_b_ri1nu_total_yearly} | ${refac_family_b_ri1nu_savings} | {refac_family_b_ri1nu_savings_rate}% |
| **1년 RI (All Upfront)** | ${comp_sga_family_b_ri1au} | ${refac_family_b_ri1au_total_yearly} | ${refac_family_b_ri1au_savings} | {refac_family_b_ri1au_savings_rate}% |
| **3년 RI (No Upfront)** | ${comp_sga_family_b_ri3nu} | ${refac_family_b_ri3nu_total_yearly} | ${refac_family_b_ri3nu_savings} | {refac_family_b_ri3nu_savings_rate}% |
| **3년 RI (All Upfront)** | ${comp_sga_family_b_ri3au} | ${refac_family_b_ri3au_total_yearly} | ${refac_family_b_ri3au_savings} | {refac_family_b_ri3au_savings_rate}% |

> 💡 Aurora PostgreSQL은 Oracle 대비 라이선스 비용이 없어 인스턴스 비용이 크게 절감됩니다.
> 단, PL/SQL → PL/pgSQL 변환 등 애플리케이션 코드 수정 비용은 별도 고려가 필요합니다.

---

## 8. 권장사항

### 비용 최적화 전략

1. **SGA 기반 인스턴스로 시작** — 실제 메모리 사용량 기준 최적화 사이즈로 시작하여 불필요한 비용 방지
2. **최신 세대 우선 검토** — 동일 사이즈에서 세대가 높을수록 성능 대비 비용 효율이 좋습니다
3. **부하 테스트 후 사이즈 확정** — POC 기간 동안 On-Demand로 운영하며 적정 사이즈 검증
4. **RI 전환 시점** — 프로덕션 안정화 후 3년 RI(All Upfront) 전환으로 최대 비용 절감
5. **스토리지 모니터링** — 연간 증가율({yearly_growth_rate}%)을 주기적으로 검증
6. **네트워크 비용 최소화** — App과 RDS를 같은 AZ에 배치하여 Cross-AZ 전송 비용 제거

### 단계별 접근

| 단계 | 기간 | 요금 모델 | 인스턴스 | 비고 |
|------|------|----------|---------|------|
| POC/테스트 | 1~2개월 | On-Demand | {sga_family_b_instance} | SGA 기반 최신 세대로 시작 |
| 프로덕션 안정화 | 2~3개월 | On-Demand | 부하 테스트 결과 반영 | 필요 시 스케일 업 |
| 비용 최적화 | 안정화 후 | 3년 RI (All Upfront) | 확정된 인스턴스 | 최대 절감 |

### Multi-AZ 필요성 검토

| 고려 항목 | 설명 |
|----------|------|
| SLA 요구사항 | 99.99% 이상 가용성 필요 시 Multi-AZ 권장 |
| 비용 증가 | 인스턴스 + 스토리지 모두 약 2배 |
| 대안 | Single-AZ + 자동 백업 + Cross-Region Read Replica |

---

## 📌 최종 요약

### 권장 구성

| 항목 | 권장 |
|------|------|
| **이관 전략** | Replatform (RDS for Oracle) |
| **인스턴스 사이징** | SGA 기반 최적화 |
| **요금 모델** | POC → On-Demand, 안정화 후 → 3년 RI (All Upfront) |
| **배포 방식** | SLA 요구사항에 따라 Single-AZ 또는 Multi-AZ |
| **네트워크** | App과 RDS 같은 AZ 배치 권장 |

### 예상 연간 비용 범위 (SGA 최적화 기준, Single-AZ)

| 패밀리 | On-Demand | 3년 RI (All Upfront) |
|--------|-----------|---------------------|
| **{family_a}** ({sga_family_a_instance}) | ${comp_sga_family_a_od}/년 | ${comp_sga_family_a_ri3au}/년 |
| **{family_b}** ({sga_family_b_instance}) | ${comp_sga_family_b_od}/년 | ${comp_sga_family_b_ri3au}/년 |

### 3년 TCO (SGA 최적화 + 3년 RI, 스토리지 증가분 포함)

| 패밀리 | 3년 TCO |
|--------|---------|
| **{family_a}** | **${tco_sga_family_a_ri3}** |
| **{family_b}** | **${tco_sga_family_b_ri3}** |

> 💡 위 비용에는 인스턴스 + 스토리지(연간 {yearly_growth_rate}% 증가 반영) + 네트워크(Cross-AZ 기준)가 모두 포함되어 있습니다.
> 실제 비용은 사용 패턴, 데이터 전송량, 백업 설정 등에 따라 달라질 수 있습니다.

---

## 부록

### A. 스토리지 요금 기준

| 항목 | 요금 ({aws_region}) |
|------|---------------------|
| gp3 스토리지 | $0.08/GB-월 |
| 추가 IOPS (3,000 초과) | $0.02/IOPS-월 |
| 추가 처리량 (125 MB/s 초과) | $0.04/MB/s-월 |
| 백업 스토리지 (보관 기간 초과분) | $0.095/GB-월 |

### B. 네트워크 전송 요금 기준

| 트래픽 경로 | 요금 ({aws_region}) |
|------------|---------------------|
| 같은 AZ 내 (Private IP) | 무료 |
| Cross-AZ (양방향) | $0.01/GB |
| 같은 리전 내 AWS 서비스 | 무료 |
| Cross-Region | $0.02/GB |
| 인터넷 Outbound (처음 10TB) | $0.09/GB |
| 인터넷 Inbound | 무료 |

### C. AWS 네트워크 과금 구간 상세

| 트래픽 경로 | 과금 | 비고 |
|------------|------|------|
| 같은 AZ 내 (App ↔ RDS) | **무료** | Private IP 사용 시 |
| Cross-AZ (App ↔ RDS) | **$0.01/GB** (양방향) | Multi-AZ 또는 App이 다른 AZ에 있는 경우 |
| Multi-AZ 복제 (RDS 내부) | **무료** | AWS 관리형 복제 |
| Read Replica (같은 리전, Cross-AZ) | **$0.01/GB** | Redo 기반 복제 트래픽 |
| Read Replica (Cross-Region) | **$0.02/GB** | 리전 간 전송 요금 |
| RDS → 인터넷 (Outbound) | **$0.09/GB** (처음 10TB) | 외부 연동 시 |
| RDS → 같은 리전 AWS 서비스 | **무료** | S3, Lambda 등 |

### D. 비용 산정 공식

```
월 인스턴스 비용 = 시간당 요금 × 730시간
월 스토리지 비용 = (DB 크기 × $0.08) + (추가 IOPS × $0.02) + (추가 처리량 × $0.04)
N년차 스토리지 = DB 크기 × (1 + 연간증가율)^N × $0.08
월 네트워크 비용 = (SQL*Net sent + received)(GB) × $0.01 × 2 (Cross-AZ 기준)
N년차 네트워크 = 월 네트워크 비용 × (1 + 연간증가율)^N × 12
3년 TCO = Σ(연도별 인스턴스 비용) + Σ(연도별 스토리지 비용) + Σ(연도별 네트워크 비용)
Multi-AZ 비용 = Single-AZ 인스턴스 비용 × 2 + Single-AZ 스토리지 비용 × 2 + 네트워크 비용
```

---

*본 리포트는 AWS 공개 요금 기준으로 작성되었으며, 실제 비용은 사용 패턴, 데이터 전송량, 백업 설정 등에 따라 달라질 수 있습니다.*
